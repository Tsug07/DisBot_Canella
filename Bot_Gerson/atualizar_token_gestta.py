# -*- coding: utf-8 -*-
"""
atualizar_token_gestta.py
-------------------------
Renova o token (JWT) do Messenger do Gestta lendo-o de um Chrome logado, via
protocolo DevTools (porta de depuracao remota). NAO usa e-mail/senha: apenas le
o token que a sessao logada guardou no localStorage ('user-jwt') e grava em
config/gestta_token.txt (consumido por messenger_gestta.py).

Dois modos:

1) Conectar a um Chrome JA rodando com porta de depuracao:
     python atualizar_token_gestta.py --porta 9222

2) SUBIR um Chrome headless proprio (com o perfil salvo, ja logado), ler o token
   e FECHAR o Chrome ao final -- ideal para agendar (DisC0ntrol/Agendador):
     python atualizar_token_gestta.py --launch
   Flags do modo --launch:
     --profile   pasta do perfil (padrao C:\\chrome_gestta)  -> deve estar LOGADO
     --chrome    caminho do chrome.exe (autodetecta se omitido)
     --porta     porta de depuracao (padrao 9222)
     --visivel   sobe o Chrome visivel em vez de headless (para semear/depurar)

IMPORTANTE (perfil): faca login UMA vez de forma visivel para semear o perfil:
     python atualizar_token_gestta.py --launch --visivel
   Depois disso, o modo headless reaproveita a sessao salva no perfil.
   O mesmo --profile NAO pode ser usado por dois Chromes ao mesmo tempo.

Dependencias: requests, websocket-client, psutil (todas ja no requirements.txt).
  pip install websocket-client
"""

import os
import re
import sys
import json
import time
import base64
import shutil
import logging
import threading
import subprocess

import requests

try:
    import websocket  # websocket-client
except ImportError:
    websocket = None

try:
    import psutil
except ImportError:
    psutil = None

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "config", "gestta_token.txt")
# Contador de recusas de credencial (trava anti-bloqueio de conta). Fica em data/
# porque precisa sobreviver a reinicios do bot -- o Auth0 conta as tentativas do
# lado dele, entao reiniciar o Gerson nao pode zerar a protecao.
RECUSAS_FILE = os.path.join(BASE_DIR, "data", "gestta_recusas_login.json")

# Carrega as variaveis de ambiente do arquivo .env na pasta config (o script
# pode ser executado diretamente, sem passar pelo gerson_bot.py).
if load_dotenv is not None:
    load_dotenv(dotenv_path=os.path.join(BASE_DIR, "config", ".env"))

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9222
DEFAULT_PROFILE = r"C:\chrome_gestta"
GESTTA_URL = "https://app.gestta.com.br"
GESTTA_URL_HINT = "gestta.com.br"
ONVIO_LOGIN = "https://onvio.com.br/login/#/"
MESSENGER_URL = "https://app.gestta.com.br/attendance/#/chat/pending"
# Launcher do Messenger dentro do Onvio: é ELE que faz o handoff/SSO para o Gestta.
# Numa sessão recém-logada, ir direto na MESSENGER_URL NÃO autentica — tem que passar
# por aqui (equivale a clicar em "Messenger" no menu "Minhas Aplicações").
MESSENGER_LAUNCH = "https://onvio.com.br/br-messenger/"
AUTH_HOST = "auth.thomsonreuters.com"

# User-agent de Chrome comum no Windows. O headless usa "HeadlessChrome/..." por
# padrao, que o Auth0 reconhece e RECUSA -- sem dizer o motivo: o POST da senha
# some, a pagina volta para a landing e o log so mostra que o token nao apareceu.
# Foi a causa provavel da falha intermitente de 04/09/2026 (mesmo .env que
# funcionou aas 08:18 falhou aas 14:19). Sobrescrivivel por env caso a versao
# fique velha demais e passe a chamar atencao por isso.
UA_PADRAO = os.environ.get(
    "GESTTA_CHROME_UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

# Credenciais para login automatico (opcional). Se ausentes, o fluxo so funciona
# enquanto a sessao do perfil estiver viva; sem elas, cai no aviso de login manual.
ONVIO_EMAIL = os.environ.get("GESTTA_ONVIO_EMAIL", "")
ONVIO_SENHA = os.environ.get("GESTTA_ONVIO_SENHA", "")
# Chave secreta TOTP (base32) do autenticador. Se definida, o bot gera o codigo
# 2FA localmente (preferido). Sem ela, cai no leitor de e-mail (Gmail).
ONVIO_TOTP_SECRET = os.environ.get("GESTTA_ONVIO_TOTP_SECRET", "")
# Debug do login: registra no log a estrutura das telas (ids/nomes dos campos,
# NUNCA valores/senha). Ligue com GESTTA_LOGIN_DEBUG=1 para mapear/depurar.
LOGIN_DEBUG = os.environ.get("GESTTA_LOGIN_DEBUG", "0") in ("1", "true", "True")

logger = logging.getLogger("atualizar_token_gestta")


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------
def _decodificar_exp(jwt):
    """Retorna o timestamp 'exp' do JWT (ou None)."""
    try:
        payload = jwt.replace("JWT ", "").split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        return data.get("exp")
    except Exception:
        return None


# Margem padrao de validade: um token com menos que isto e considerado "vencendo"
# e dispara a renovacao. Precisa ser MAIOR que o intervalo do laco de renovacao do
# gerson_bot (GESTTA_TOKEN_INTERVALO_H, padrao 6h), senao o token pode vencer entre
# duas verificacoes. Acompanha o .env automaticamente: 6h de laco -> 8h de margem.
try:
    _INTERVALO_LOOP_H = int(os.environ.get("GESTTA_TOKEN_INTERVALO_H", "6"))
except ValueError:
    _INTERVALO_LOOP_H = 6
MARGEM_PADRAO_SEG = max(2, _INTERVALO_LOOP_H + 2) * 3600


def token_valido(caminho=TOKEN_FILE, margem_seg=None):
    """True se o arquivo de token existe e ainda tem >margem_seg de validade.

    margem_seg=None usa MARGEM_PADRAO_SEG (intervalo do laco + 2h de folga)."""
    if margem_seg is None:
        margem_seg = MARGEM_PADRAO_SEG
    if not os.path.exists(caminho):
        return False
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            tok = f.read().strip().strip('"')
        exp = _decodificar_exp(tok)
        return bool(exp) and (exp - time.time()) > margem_seg
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Trava anti-bloqueio de conta
# ---------------------------------------------------------------------------
# Uma senha errada custa MUITO mais que uma execucao falha: o Auth0 bloqueia a
# conta apos algumas tentativas, e ai nem a senha certa entra. Aconteceu na Libby
# em 01/09/2026, com 6 rodadas seguidas -- e o Gerson usa a MESMA conta Onvio,
# repetindo o login a cada 6h indefinidamente.
#
# So conta como recusa quando o Auth0 exibe a mensagem de credencial invalida na
# tela. Falha de rede, Chrome que nao subiu ou pagina lenta NAO contam: travar por
# causa delas deixaria a integracao parada sem motivo.
LIMITE_RECUSAS = 3

# Serializa os logins: o Chrome usa um perfil UNICO (C:\chrome_gestta) e dois
# processos no mesmo perfil se atrapalham (o segundo nao abre, ou corrompe a
# sessao salva -- que e justamente o que faz o SSO silencioso funcionar).
# O Gerson tem 3 caminhos que podem disparar renovacao em threads separadas:
# o laco de 6h, o sync por evento e a reconciliacao diaria.
_LOCK_LOGIN = threading.Lock()

# O threading.Lock so vale DENTRO do processo. O bot e a linha de comando
# (--launch avulso) sao processos diferentes e colidiriam no mesmo perfil: o
# segundo Chrome nao sobe e o DevTools nunca responde -- comprovado em teste.
# Este arquivo serve de aviso entre processos.
LOGIN_LOCK_FILE = os.path.join(BASE_DIR, "data", "gestta_login_em_andamento.lock")
LOGIN_LOCK_TTL = 600   # 10 min: acima disso o lock e considerado orfao


def _lock_arquivo_ativo():
    """(ativo, idade_seg) do lock entre processos. Lock velho e ignorado (orfao)."""
    try:
        idade = time.time() - os.path.getmtime(LOGIN_LOCK_FILE)
        return (idade < LOGIN_LOCK_TTL), int(idade)
    except Exception:  # noqa
        return False, 0


def _criar_lock_arquivo():
    try:
        os.makedirs(os.path.dirname(LOGIN_LOCK_FILE), exist_ok=True)
        with open(LOGIN_LOCK_FILE, "w", encoding="utf-8") as f:
            f.write("%d %s" % (os.getpid(), time.strftime("%Y-%m-%d %H:%M:%S")))
    except Exception:  # noqa
        pass


def _remover_lock_arquivo():
    try:
        if os.path.exists(LOGIN_LOCK_FILE):
            os.remove(LOGIN_LOCK_FILE)
    except Exception:  # noqa
        pass

# Endpoint barato usado para confirmar que o token REALMENTE funciona.
_URL_VALIDACAO = ("https://api.gestta.com.br/messenger-admin/company/contact"
                  "?page=1&limit=1&sort=name")


def _validar_token(token, timeout=30):
    """True se a API aceita o token (HTTP 200).

    O 'exp' do JWT diz quando o token expira, nao se ele vale: um token revogado
    (troca de senha, sessao encerrada no Onvio) continua com exp no futuro e passa
    no token_valido(). Sem esta checagem, um token assim seria gravado e so daria
    erro depois, na hora de escrever nos contatos."""
    try:
        r = requests.get(_URL_VALIDACAO,
                         headers={"Authorization": token, "Accept": "application/json"},
                         timeout=timeout)
        if r.status_code == 200:
            return True
        logger.warning("[token] A API recusou o token recem-obtido (HTTP %s).", r.status_code)
        return False
    except Exception as e:  # noqa
        # Sem rede nao da para validar. Nao descarta o token por isso: o 'exp'
        # ja foi conferido e derrubar um token bom por instabilidade de rede
        # seria pior que aceita-lo.
        logger.warning("[token] Nao foi possivel validar o token na API (%s); "
                       "aceitando com base no 'exp'.", str(e)[:120])
        return True


def _ler_recusas():
    try:
        with open(RECUSAS_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        return int(d.get("recusas", 0) or 0), str(d.get("motivo", "") or ""), str(d.get("quando", "") or "")
    except Exception:  # noqa
        return 0, "", ""


def marcar_recusa(motivo):
    """Registra uma recusa de credencial. Trava o login ao atingir LIMITE_RECUSAS."""
    n, _, _ = _ler_recusas()
    n += 1
    try:
        os.makedirs(os.path.dirname(RECUSAS_FILE), exist_ok=True)
        with open(RECUSAS_FILE, "w", encoding="utf-8") as f:
            json.dump({"recusas": n, "motivo": str(motivo)[:300],
                       "quando": time.strftime("%Y-%m-%d %H:%M:%S")}, f,
                      ensure_ascii=False, indent=2)
    except Exception as e:  # noqa
        logger.error("Nao foi possivel gravar o contador de recusas: %s", e)
    if n >= LIMITE_RECUSAS:
        logger.error("[login] %d recusas seguidas — login TRAVADO ate alguem corrigir "
                     "a credencial no .env. Isto evita o BLOQUEIO da conta no Onvio.", n)
    else:
        logger.warning("[login] Credencial recusada (%d/%d). Motivo: %s",
                       n, LIMITE_RECUSAS, str(motivo)[:160])
    return n


def login_travado():
    """Motivo pelo qual o login esta travado, ou '' se pode tentar."""
    n, motivo, quando = _ler_recusas()
    if n >= LIMITE_RECUSAS:
        return ("%d tentativas de login foram RECUSADAS seguidas (ultima em %s: %s). "
                "Corrija GESTTA_ONVIO_EMAIL/SENHA/TOTP_SECRET no .env e rode "
                "'python atualizar_token_gestta.py --destravar'. Insistir bloqueia "
                "a conta no Onvio." % (n, quando or "?", motivo or "sem detalhe"))
    return ""


def limpar_recusas():
    """Libera o login. Chamado quando a credencial e corrigida ou apos sucesso."""
    n, _, _ = _ler_recusas()
    try:
        if os.path.exists(RECUSAS_FILE):
            os.remove(RECUSAS_FILE)
    except Exception:  # noqa
        pass
    return n


def salvar_token(token, caminho=TOKEN_FILE):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(token)
    return caminho


# ---------------------------------------------------------------------------
# DevTools (CDP)
# ---------------------------------------------------------------------------
def _listar_abas(host, porta):
    r = requests.get(f"http://{host}:{porta}/json", timeout=5)
    r.raise_for_status()
    return r.json()


def _ler_localstorage_key(ws_url, chave, origin=None):
    """Abre o websocket DevTools e le localStorage[chave] da aba.

    Chrome >= 111 exige liberar a origem no lancamento (--remote-allow-origins=*);
    tambem enviamos o header Origin coerente para maxima compatibilidade.
    """
    if websocket is None:
        raise RuntimeError("Biblioteca 'websocket-client' nao instalada. "
                           "Rode: pip install websocket-client")
    ws = websocket.create_connection(ws_url, timeout=8, suppress_origin=False,
                                     origin=origin)
    try:
        expr = f"window.localStorage.getItem({json.dumps(chave)})"
        ws.send(json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": expr, "returnByValue": True},
        }))
        for _ in range(10):
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                return (((msg.get("result") or {}).get("result") or {}).get("value"))
        return None
    finally:
        ws.close()


def _recarregar_aba(ws_url, origin=None, espera=6):
    """Recarrega a aba (Page.reload) para o app re-emitir um JWT novo pela sessao Onvio
    ainda viva. Best-effort: se falhar, apenas segue para a leitura."""
    if websocket is None:
        return
    try:
        ws = websocket.create_connection(ws_url, timeout=8, suppress_origin=False,
                                         origin=origin)
        try:
            ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            ws.send(json.dumps({"id": 2, "method": "Page.reload",
                                "params": {"ignoreCache": True}}))
        finally:
            ws.close()
        time.sleep(espera)
    except Exception:
        pass


def obter_token_do_chrome(host=DEFAULT_HOST, porta=DEFAULT_PORT, recarregar=False):
    """Localiza a aba do Gestta e devolve o JWT (com prefixo 'JWT ').

    Se recarregar=True, recarrega a aba antes de ler para forcar um token novo
    (util no Chrome persistente cuja sessao Onvio segue viva)."""
    abas = _listar_abas(host, porta)
    alvos = [a for a in abas if a.get("type") == "page"
             and GESTTA_URL_HINT in (a.get("url") or "")]
    if not alvos:
        raise RuntimeError(
            f"Nenhuma aba do Gestta encontrada no Chrome em {host}:{porta}. "
            "Abra https://app.gestta.com.br logado nesse Chrome."
        )
    origin = f"http://{host}:{porta}"
    for aba in alvos:
        ws_url = aba.get("webSocketDebuggerUrl")
        if not ws_url:
            continue
        if recarregar:
            _recarregar_aba(ws_url, origin=origin)
        raw = _ler_localstorage_key(ws_url, "user-jwt", origin=origin)
        if not raw:
            continue
        token = json.loads(raw) if str(raw).strip().startswith('"') else raw
        token = str(token).strip().strip('"')
        if token:
            if not token.upper().startswith("JWT "):
                token = "JWT " + token
            return token
    raise RuntimeError("Aba do Gestta encontrada, mas sem 'user-jwt' no localStorage "
                       "(sessao pode ter deslogado).")


# ---------------------------------------------------------------------------
# Fluxo SSO completo (Onvio -> Messenger), dirigido por CDP
# ---------------------------------------------------------------------------
def _abrir_ws(host, porta):
    """Devolve (ws, contador_id) para a primeira aba 'page' do Chrome."""
    abas = _listar_abas(host, porta)
    page = next((a for a in abas if a.get("type") == "page"
                 and a.get("webSocketDebuggerUrl")), None)
    if not page:
        raise RuntimeError(f"Nenhuma aba 'page' no Chrome em {host}:{porta}.")
    origin = f"http://{host}:{porta}"
    ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=10,
                                     suppress_origin=False, origin=origin)
    return ws, [0]


def _cdp(ws, contador, method, params=None, timeout=15):
    contador[0] += 1
    mid = contador[0]
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    fim = time.time() + timeout
    while time.time() < fim:
        try:
            msg = json.loads(ws.recv())
        except Exception:
            break
        if msg.get("id") == mid:
            return msg
    return None


def _eval(ws, contador, expr):
    r = _cdp(ws, contador, "Runtime.evaluate",
             {"expression": expr, "returnByValue": True, "awaitPromise": True})
    return (((r or {}).get("result") or {}).get("result") or {}).get("value")


def _disfarcar(ws, contador):
    """Tira as marcas de automacao que o Auth0 usa para recusar o login.

    A flag --disable-blink-features NAO apaga navigator.webdriver sozinha. Este
    script roda ANTES de qualquer script da pagina (addScriptToEvaluateOnNewDocument),
    entao o Auth0 ja encontra o navegador "limpo" quando carrega."""
    try:
        _cdp(ws, contador, "Page.addScriptToEvaluateOnNewDocument", {"source":
             "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
             "window.chrome=window.chrome||{runtime:{}};"
             "Object.defineProperty(navigator,'languages',{get:()=>['pt-BR','pt','en-US']});"
             "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});"})
    except Exception:  # noqa
        pass
    # Aviso util no diagnostico: se o UA ainda anuncia headless, a flag nao pegou.
    try:
        ua = _eval(ws, contador, "navigator.userAgent") or ""
        if "Headless" in ua:
            logger.warning("[login] user-agent ainda anuncia headless (%s) — "
                           "o Auth0 pode recusar o login.", ua[:90])
    except Exception:  # noqa
        pass


def _navegar(ws, contador, url, espera=5):
    _cdp(ws, contador, "Page.enable")
    _cdp(ws, contador, "Page.navigate", {"url": url})
    time.sleep(espera)


def _gerar_totp(secret):
    """Gera o código TOTP de 6 dígitos a partir da chave base32 do autenticador."""
    import pyotp
    s = re.sub(r"\s+", "", secret or "")  # remove espaços do secret
    return pyotp.TOTP(s).now()


TEM_CODIGO_JS = ("!!document.querySelector(\"input[name='code'],input#code,"
                 "input[autocomplete='one-time-code'],input[inputmode='numeric']\")")


def _dump_estrutura(ws, contador):
    """Devolve (string JSON) a estrutura da pagina: inputs e botoes/links visiveis
    (apenas ids/nomes/textos — NUNCA valores). Usado no modo debug do login."""
    js = ("(function(){function d(el){return {tag:el.tagName,id:el.id,"
          "name:el.getAttribute('name'),type:el.getAttribute('type'),"
          "txt:(el.innerText||'').trim().slice(0,35),vis:el.offsetParent!==null};}"
          "var ins=[].slice.call(document.querySelectorAll('input')).map(d);"
          "var bts=[].slice.call(document.querySelectorAll('button,a,[role=button]'))"
          ".map(d).filter(function(x){return x.vis&&x.txt;});"
          "return JSON.stringify({url:location.pathname,inputs:ins,botoes:bts.slice(0,15)});})()")
    try:
        return _eval(ws, contador, js)
    except Exception:  # noqa
        return "?"


def _js_set_input(seletores, valor):
    """Gera JS que preenche o 1o input visivel que casar com os seletores (React-safe)."""
    return (
        "(function(){var set=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;"
        "var sels=%s;var el=null;for(var i=0;i<sels.length;i++){el=document.querySelector(sels[i]);"
        "if(el&&el.offsetParent!==null)break;el=null;}"
        "if(!el)return false;set.call(el,%s);"
        "el.dispatchEvent(new Event('input',{bubbles:true}));"
        "el.dispatchEvent(new Event('change',{bubbles:true}));return true;})()"
        % (json.dumps(seletores), json.dumps(valor))
    )


def _js_click(seletores):
    return (
        "(function(){var sels=%s;for(var i=0;i<sels.length;i++){var el=document.querySelector(sels[i]);"
        "if(el&&el.offsetParent!==null){el.click();return true;}}return false;})()"
        % json.dumps(seletores)
    )


def _fazer_login_auth0(ws, contador, inicio_epoch):
    """Preenche credenciais na tela Auth0 e resolve o 2FA por e-mail (Gmail).
    Retorna True se acha que completou o login. Requer GESTTA_ONVIO_EMAIL/SENHA."""
    if not ONVIO_EMAIL or not ONVIO_SENHA:
        logger.warning("Login automatico indisponivel: defina GESTTA_ONVIO_EMAIL e GESTTA_ONVIO_SENHA no .env.")
        return False

    sel_email = ["input#username", "input[name='username']", "input[type='email']",
                 "input[autocomplete='username']"]
    sel_senha = ["input#password", "input[name='password']", "input[type='password']"]
    sel_submit = ["button[data-action-button-primary='true']", "button[value='default']",
                  "button[type='submit']", "button[name='action']"]

    # Etapa identificador (se a pagina pedir so o e-mail antes da senha)
    _eval(ws, contador, _js_set_input(sel_email, ONVIO_EMAIL))
    tem_senha = _eval(ws, contador,
                      "!!document.querySelector(\"input[type='password']\")")
    if not tem_senha:
        _eval(ws, contador, _js_click(sel_submit))
        time.sleep(4)
        _eval(ws, contador, _js_set_input(sel_email, ONVIO_EMAIL))

    # Preenche senha e envia
    _eval(ws, contador, _js_set_input(sel_senha, ONVIO_SENHA))
    _eval(ws, contador, _js_click(sel_submit))
    time.sleep(6)

    if LOGIN_DEBUG:
        logger.info("[login][debug] pos-senha: %s", _dump_estrutura(ws, contador))

    # Credencial recusada: o Auth0 responde com um texto na propria tela e NAO
    # avanca para o 2FA. Sem checar isto, o fluxo seguia ate o fim e terminava em
    # "token nao apareceu" -- que parece problema de sessao, quando a causa e a
    # senha. O texto vem em pt/en conforme o idioma da conta.
    _msg = _eval(ws, contador,
        "(function(){var t=(document.body?document.body.innerText:'');"
        "var m=t.match(/(Verifique se seu e-?mail e senha[^.]*\\.|"
        "Your e-?mail or password[^.]*\\.|"
        "senha (?:esta|est\\u00e1) incorreta[^.]*\\.|"
        "[^.]*conta est\\u00e1 bloqueada[^.]*\\.?|"
        "conta (?:foi )?bloqueada[^.]*\\.|"
        "account (?:has been |is )?(?:locked|blocked)[^.]*\\.|"
        "too many (?:failed )?attempts[^.]*\\.)/i);"
        "return m?m[0].trim():'';})()")
    if _msg:
        logger.error("[login] O Onvio RECUSOU a credencial -> %s", str(_msg)[:160])
        marcar_recusa(str(_msg))
        return False

    # Tela de ESCOLHA de metodo (Auth0 /u/mfa-login-options): seleciona o
    # autenticador (app / codigo de uso unico), evitando e-mail/sms/backup.
    url = _eval(ws, contador, "location.href") or ""
    if "mfa-login-options" in url or not _eval(ws, contador, TEM_CODIGO_JS):
        escolhido = _eval(ws, contador,
            "(function(){"
            # seletor exato do Auth0: botao do fator 'otp' (autenticador)
            "var b=document.querySelector(\"button[value^='otp'],.ulp-action-form-otp button,"
            "li._selector-item-otp button\");"
            "if(b&&b.offsetParent!==null){b.click();return b.getAttribute('aria-label')||'otp';}"
            # fallback por texto
            "var kw=/autentic|c[oó]digo de uso|senha de uso|uso [uú]nico|"
            "one.?time|token|google authenticator|aplicativo/i;"
            "var bad=/e-?mail|sms|telefone|recupera|backup/i;"
            "var els=[].slice.call(document.querySelectorAll('button,a,[role=button],li'));"
            "for(var i=0;i<els.length;i++){var t=(els[i].innerText||'').trim();"
            "if(t&&kw.test(t)&&!bad.test(t)&&els[i].offsetParent!==null){els[i].click();return t.slice(0,40);}}"
            "return false;})()")
        if escolhido:
            logger.info("[login] Metodo 2FA escolhido: %s", escolhido)
            time.sleep(5)
            if LOGIN_DEBUG:
                logger.info("[login][debug] pos-escolha: %s", _dump_estrutura(ws, contador))

    # 2FA: se ha campo de codigo, obtem o codigo — preferindo o TOTP local
    # (autenticador); se nao houver secret, cai no leitor de e-mail (Gmail).
    tem_codigo = _eval(ws, contador, TEM_CODIGO_JS)
    if tem_codigo:
        codigo = None
        if ONVIO_TOTP_SECRET:
            try:
                codigo = _gerar_totp(ONVIO_TOTP_SECRET)
                logger.info("[login] 2FA via TOTP (autenticador, gerado localmente).")
            except Exception as e:  # noqa
                logger.error("[login] Falha ao gerar TOTP: %s", e)
        if not codigo:
            logger.info("[login] 2FA: lendo codigo no Gmail...")
            try:
                import ler_2fa_gmail
                codigo = ler_2fa_gmail.obter_codigo_2fa(desde_epoch=inicio_epoch, timeout=120)
            except Exception as e:  # noqa
                logger.error("[login] Nao foi possivel obter o codigo 2FA: %s", e)
                return False
        _eval(ws, contador, _js_set_input(
            ["input[name='code']", "input#code", "input[autocomplete='one-time-code']",
             "input[inputmode='numeric']"], codigo))
        # marca "lembrar deste dispositivo", se existir
        _eval(ws, contador,
              "(function(){var c=document.querySelector(\"input[name='rememberBrowser'],"
              "input#rememberBrowser,input[type='checkbox']\");"
              "if(c&&!c.checked)c.click();return !!c;})()")
        _eval(ws, contador, _js_click(sel_submit))
        time.sleep(6)
    return True


def obter_token_via_sso(host=DEFAULT_HOST, porta=DEFAULT_PORT):
    """
    Fluxo completo e automatico, dirigido por CDP:
      1. abre o Messenger; se ja logado, le o token e retorna;
      2. senao, vai ao login do Onvio e clica "Entrar";
      3. se cair na tela de login da Thomson Reuters (Auth0), faz login com
         credenciais do .env + 2FA lido do Gmail;
      4. volta ao Messenger e le o token.
    """
    if websocket is None:
        raise RuntimeError("Biblioteca 'websocket-client' nao instalada.")
    travado = login_travado()
    if travado:
        raise RuntimeError("Login BLOQUEADO pela trava de seguranca: " + travado)
    ws, c = _abrir_ws(host, porta)
    try:
        def ler():
            v = _eval(ws, c, "window.localStorage.getItem('user-jwt')")
            if not v:
                return None
            t = json.loads(v) if str(v).strip().startswith('"') else v
            t = str(t).strip().strip('"')
            return t or None

        def ler_com_retry(tentativas=6, intervalo=2.5):
            for _ in range(tentativas):
                t = ler()
                if t:
                    return t
                time.sleep(intervalo)
            return None

        # Apaga as marcas de automacao ANTES de qualquer navegacao, senao o Auth0
        # ja recebe navigator.webdriver=true na primeira pagina que carregar.
        _disfarcar(ws, c)

        # 'etapa' registra ate onde o fluxo chegou, para o erro final dizer o que
        # de fato falhou em vez do generico "verifique credenciais/2FA" -- que em
        # 04/09/2026 mandou investigar credencial que estava correta.
        etapa = "abertura do Messenger"

        # 1) caminho rápido: se a sessão do Gestta ainda estiver viva, o token
        #    já aparece indo direto no Messenger.
        _navegar(ws, c, MESSENGER_URL, espera=6)
        tok = ler()
        # 2) senão, faz login no Onvio e usa o launcher do Messenger p/ o handoff
        if not tok:
            inicio = time.time()
            etapa = "abertura do login do Onvio"
            _navegar(ws, c, ONVIO_LOGIN, espera=4)
            clicou = _eval(ws, c,
                  "(function(){var b=[].slice.call(document.querySelectorAll('button'))"
                  ".find(function(x){return x.innerText.trim()==='Entrar'&&x.offsetParent!==null});"
                  "if(b){b.click();return true}return false})()")
            if not clicou:
                logger.warning("[login] Botao 'Entrar' nao encontrado no Onvio "
                               "(pagina pode nao ter carregado a tempo).")
            time.sleep(8)  # aguarda redirect (SSO silencioso ou tela de login)
            # 3) se caiu na tela de login da Thomson Reuters, faz login + 2FA
            url_atual = _eval(ws, c, "location.href") or ""
            if AUTH_HOST in url_atual:
                etapa = "login/2FA na tela da Thomson Reuters"
                logger.info("[login] Tela de login detectada; tentando login automatico...")
                _fazer_login_auth0(ws, c, inicio)
                time.sleep(5)
                # Se continuamos no host do Auth0, o login nao passou -- e ai a
                # causa E credencial/2FA, ao contrario dos outros casos.
                url_pos = _eval(ws, c, "location.href") or ""
                if AUTH_HOST in url_pos:
                    raise RuntimeError(
                        "Login recusado na tela da Thomson Reuters (ainda em "
                        + AUTH_HOST + " apos enviar as credenciais). Verifique "
                        "GESTTA_ONVIO_EMAIL/SENHA/TOTP_SECRET no .env.")
            else:
                logger.info("[login] SSO silencioso (sessao do perfil ainda viva).")
            # 4) HANDOFF: acessa o launcher do Messenger no Onvio (equivale a clicar
            #    em "Messenger"); ele redireciona para o Gestta já autenticado.
            etapa = "handoff do Messenger (br-messenger)"
            _navegar(ws, c, MESSENGER_LAUNCH, espera=8)
            tok = ler_com_retry()
            # fallback: garante estar na rota do chat e tenta de novo
            if not tok:
                _navegar(ws, c, MESSENGER_URL, espera=6)
                tok = ler_com_retry()
        if not tok:
            url_final = _eval(ws, c, "location.href") or "?"
            raise RuntimeError(
                "Token 'user-jwt' nao apareceu no localStorage. Etapa: " + etapa
                + ". URL final: " + str(url_final)[:120]
                + ". As credenciais NAO foram recusadas nesta tentativa — causas "
                  "provaveis: pagina lenta (esperas fixas do fluxo) ou o Auth0 "
                  "recusando o navegador automatizado.")
        # Token obtido => a credencial esta boa. Zera recusas antigas para que
        # falhas espacadas no tempo nao se acumulem ate travar sem necessidade.
        if limpar_recusas():
            logger.info("[login] Login OK — contador de recusas zerado.")
        return tok if tok.upper().startswith("JWT ") else "JWT " + tok
    finally:
        try:
            ws.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Lancamento de Chrome proprio (headless por padrao)
# ---------------------------------------------------------------------------
def _detectar_chrome():
    candidatos = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        shutil.which("chrome"), shutil.which("google-chrome"), shutil.which("chromium"),
    ]
    for c in candidatos:
        if c and os.path.exists(c):
            return c
    return None


def _diagnostico_chrome(proc):
    """Le o stderr do Chrome que morreu e devolve o motivo (ou '').

    Sem isto, um Chrome que nem chegou a subir vira apenas 'DevTools nao respondeu',
    que parece problema de rede e manda investigar o lugar errado."""
    try:
        if proc is None or proc.poll() is None:
            return ""   # ainda vivo: o problema nao foi o lancamento
        err = b""
        if proc.stderr is not None:
            err = proc.stderr.read() or b""
        txt = err.decode("utf-8", "ignore").strip()
        if not txt:
            return f" (Chrome encerrou com codigo {proc.returncode} e sem mensagem.)"
        linhas = [l for l in txt.splitlines() if l.strip()][-3:]
        return " Chrome disse: " + " | ".join(linhas)[:300]
    except Exception:  # noqa
        return ""


def _matar_arvore(proc):
    """Encerra o processo do Chrome e seus filhos."""
    if proc is None:
        return
    try:
        if psutil is not None:
            p = psutil.Process(proc.pid)
            for child in p.children(recursive=True):
                try:
                    child.kill()
                except Exception:
                    pass
            p.kill()
        else:
            proc.terminate()
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass


def _esperar_devtools(host, porta, timeout=25):
    fim = time.time() + timeout
    while time.time() < fim:
        try:
            requests.get(f"http://{host}:{porta}/json/version", timeout=2)
            return True
        except Exception:
            time.sleep(0.7)
    return False


def obter_token_lancando_chrome(chrome=None, profile=DEFAULT_PROFILE,
                                host=DEFAULT_HOST, porta=DEFAULT_PORT,
                                headless=True):
    """Sobe um Chrome (headless por padrao) com o perfil salvo, le o token e fecha."""
    # Checa a trava ANTES de subir o Chrome: sem isto, um login travado ainda
    # pagava o custo de lancar e matar o navegador a cada ciclo, sem chance de
    # dar certo.
    travado = login_travado()
    if travado:
        raise RuntimeError("Login BLOQUEADO pela trava de seguranca: " + travado)
    chrome = chrome or _detectar_chrome()
    if not chrome:
        raise RuntimeError("chrome.exe nao encontrado. Passe --chrome com o caminho.")

    flags = [
        chrome,
        f"--remote-debugging-port={porta}",
        "--remote-allow-origins=*",
        f"--user-data-dir={profile}",
        "--no-first-run", "--no-default-browser-check",
    ]
    if headless:
        # --user-agent e --disable-blink-features: sem eles o Auth0 identifica o
        # navegador como automatizado e recusa o login silenciosamente (ver UA_PADRAO).
        # --window-size: sem viewport real, elementos ficam com offsetParent nulo e
        # os cliques do fluxo (que exigem visibilidade) simplesmente nao acontecem.
        flags += ["--headless=new", "--disable-gpu", "--window-size=1568,900",
                  "--user-agent=" + UA_PADRAO,
                  "--disable-blink-features=AutomationControlled"]
    flags.append(ONVIO_LOGIN)  # abre no login do Onvio; o SSO usa a sessao do perfil

    # stderr preservado: e por ele que aparece o motivo real de o Chrome nao subir
    # (perfil em uso por outro processo, biblioteca ausente, permissao).
    proc = subprocess.Popen(flags, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        if not _esperar_devtools(host, porta):
            raise RuntimeError(
                f"Chrome nao subiu: DevTools nao respondeu em {host}:{porta} "
                f"apos o lancamento.{_diagnostico_chrome(proc)}")
        time.sleep(2)  # aguarda a primeira aba abrir
        # fluxo completo: clica "Entrar" (SSO silencioso) e le o token no Messenger
        return obter_token_via_sso(host, porta)
    finally:
        _matar_arvore(proc)


# ---------------------------------------------------------------------------
# Orquestracao
# ---------------------------------------------------------------------------
def renovar(host=DEFAULT_HOST, porta=DEFAULT_PORT, forcar=False, caminho=TOKEN_FILE,
            launch=False, chrome=None, profile=DEFAULT_PROFILE, headless=True,
            recarregar=False, sso=False):
    """
    Renova o token se necessario. Retorna (ok:bool, mensagem:str).
    - launch=True : sobe um Chrome proprio (headless), faz o SSO Onvio->Messenger,
                    le o token e fecha (RECOMENDADO para a VM).
    - sso=True    : conecta a um Chrome ja rodando e executa o fluxo SSO completo
                    (navega, clica "Entrar", le o token).
    - recarregar  : (connect-mode simples) recarrega a aba do Messenger antes de ler.
    - launch=False e sso=False: conecta e le a aba do Gestta ja aberta/logada.
    """
    if not forcar and token_valido(caminho):
        return True, "Token atual ainda valido; nada a fazer."

    # Um login por vez (perfil unico do Chrome). Se outra thread ja esta logando,
    # espera a vez em vez de subir um segundo Chrome no mesmo perfil.
    if not _LOCK_LOGIN.acquire(timeout=300):
        return False, ("Outra renovacao esta em andamento ha mais de 5 min "
                       "(login travado ou Chrome preso).")
    try:
        # Quem esperou no lock pode ter sido atendido pela renovacao que acabou
        # de rodar: reconfere antes de subir mais um Chrome a toa.
        if not forcar and token_valido(caminho):
            return True, "Token renovado por outra tarefa enquanto esta aguardava."

        # Outro PROCESSO (ex.: o bot rodando enquanto alguem chama a CLI) pode
        # estar logando agora. Subir um segundo Chrome no mesmo perfil faz o
        # DevTools nunca responder -- melhor recusar com uma mensagem clara.
        ativo, idade = _lock_arquivo_ativo()
        if ativo:
            return False, ("Outro processo esta renovando o token ha %ds "
                           "(perfil unico do Chrome). Tente novamente em instantes." % idade)
        _criar_lock_arquivo()
        try:
            try:
                if launch:
                    token = obter_token_lancando_chrome(chrome=chrome, profile=profile,
                                                        host=host, porta=porta, headless=headless)
                elif sso:
                    token = obter_token_via_sso(host, porta)
                else:
                    token = obter_token_do_chrome(host, porta, recarregar=recarregar)
            except Exception as e:  # noqa
                return False, f"Falha ao obter token: {e}"

            # Confirma na API antes de gravar: nunca substituir um token que funciona
            # por outro que o servidor ja rejeita.
            if not _validar_token(token):
                return False, ("Token obtido, mas a API o REJEITOU (HTTP != 200). "
                               "Mantido o token anterior.")

            salvar_token(token, caminho)
            exp = _decodificar_exp(token)
            resta = int((exp - time.time()) / 3600) if exp else "?"
            return True, f"Token renovado e validado (validade ~{resta}h). Salvo em {caminho}."
        finally:
            # Sempre remove o lock de arquivo, inclusive nas saidas por erro --
            # senao um lock orfao bloquearia as renovacoes ate o TTL de 10 min.
            _remover_lock_arquivo()
    finally:
        _LOCK_LOGIN.release()


def _main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Renova o token do Gestta a partir de um Chrome logado.")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--porta", type=int, default=DEFAULT_PORT)
    ap.add_argument("--forcar", action="store_true", help="Renova mesmo se o token atual ainda for valido.")
    ap.add_argument("--launch", action="store_true", help="Sobe um Chrome proprio (headless), le o token e fecha.")
    ap.add_argument("--visivel", action="store_true", help="Com --launch: sobe o Chrome visivel (para semear/depurar).")
    ap.add_argument("--profile", default=DEFAULT_PROFILE, help="Pasta do perfil do Chrome (deve estar logado).")
    ap.add_argument("--chrome", default=None, help="Caminho do chrome.exe (autodetecta se omitido).")
    ap.add_argument("--reload", dest="recarregar", action="store_true",
                    help="Recarrega a aba do Messenger antes de ler (Chrome persistente ja logado).")
    ap.add_argument("--sso", action="store_true",
                    help="Connect-mode: executa o fluxo SSO completo (clica 'Entrar' e le o token).")
    ap.add_argument("--destravar", action="store_true",
                    help="Zera o contador de recusas e libera o login (apos corrigir o .env).")
    ap.add_argument("--status", action="store_true",
                    help="Mostra a validade do token e o estado da trava de login.")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.destravar:
        n = limpar_recusas()
        print("Login destravado (%d recusa(s) descartada(s))." % n if n
              else "Nada a destravar: o login nao estava travado.")
        sys.exit(0)

    if args.status:
        exp = None
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                exp = _decodificar_exp(f.read().strip().strip('"'))
        if exp:
            print("Token: valido por mais %.1f h (margem de renovacao: %.0f h)."
                  % ((exp - time.time()) / 3600, MARGEM_PADRAO_SEG / 3600))
        else:
            print("Token: ausente ou ilegivel em " + TOKEN_FILE)
        n, motivo, quando = _ler_recusas()
        trava = login_travado()
        if trava:
            print("Login: TRAVADO -> " + trava)
        elif n:
            print("Login: liberado, mas com %d/%d recusa(s) registrada(s) "
                  "(ultima em %s: %s)." % (n, LIMITE_RECUSAS, quando, motivo[:120]))
        else:
            print("Login: liberado, sem recusas registradas.")
        sys.exit(0)

    ok, msg = renovar(args.host, args.porta, forcar=args.forcar, launch=args.launch,
                      chrome=args.chrome, profile=args.profile, headless=(not args.visivel),
                      recarregar=args.recarregar, sso=args.sso)
    print(("OK: " if ok else "ERRO: ") + msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    _main(sys.argv[1:])
