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
import sys
import json
import time
import base64
import shutil
import logging
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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "config", "gestta_token.txt")

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

# Credenciais para login automatico (opcional). Se ausentes, o fluxo so funciona
# enquanto a sessao do perfil estiver viva; sem elas, cai no aviso de login manual.
ONVIO_EMAIL = os.environ.get("GESTTA_ONVIO_EMAIL", "")
ONVIO_SENHA = os.environ.get("GESTTA_ONVIO_SENHA", "")

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


def token_valido(caminho=TOKEN_FILE, margem_seg=3600):
    """True se o arquivo de token existe e ainda tem >margem_seg de validade."""
    if not os.path.exists(caminho):
        return False
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            tok = f.read().strip().strip('"')
        exp = _decodificar_exp(tok)
        return bool(exp) and (exp - time.time()) > margem_seg
    except Exception:
        return False


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


def _navegar(ws, contador, url, espera=5):
    _cdp(ws, contador, "Page.enable")
    _cdp(ws, contador, "Page.navigate", {"url": url})
    time.sleep(espera)


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
    sel_submit = ["button[type='submit']", "button[name='action']", "button[value='default']"]

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

    # 2FA por e-mail: o Auth0 envia o codigo ao chegar na tela de desafio.
    tem_codigo = _eval(ws, contador,
                       "!!document.querySelector(\"input[name='code'],input#code,"
                       "input[autocomplete='one-time-code'],input[inputmode='numeric']\")")
    if tem_codigo:
        logger.info("[login] Tela de 2FA detectada; lendo codigo no Gmail...")
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

        # 1) caminho rápido: se a sessão do Gestta ainda estiver viva, o token
        #    já aparece indo direto no Messenger.
        _navegar(ws, c, MESSENGER_URL, espera=6)
        tok = ler()
        # 2) senão, faz login no Onvio e usa o launcher do Messenger p/ o handoff
        if not tok:
            inicio = time.time()
            _navegar(ws, c, ONVIO_LOGIN, espera=4)
            _eval(ws, c,
                  "(function(){var b=[].slice.call(document.querySelectorAll('button'))"
                  ".find(function(x){return x.innerText.trim()==='Entrar'&&x.offsetParent!==null});"
                  "if(b){b.click();return true}return false})()")
            time.sleep(8)  # aguarda redirect (SSO silencioso ou tela de login)
            # 3) se caiu na tela de login da Thomson Reuters, faz login + 2FA
            url_atual = _eval(ws, c, "location.href") or ""
            if AUTH_HOST in url_atual:
                logger.info("[login] Tela de login detectada; tentando login automatico...")
                _fazer_login_auth0(ws, c, inicio)
                time.sleep(5)
            # 4) HANDOFF: acessa o launcher do Messenger no Onvio (equivale a clicar
            #    em "Messenger"); ele redireciona para o Gestta já autenticado.
            _navegar(ws, c, MESSENGER_LAUNCH, espera=8)
            tok = ler_com_retry()
            # fallback: garante estar na rota do chat e tenta de novo
            if not tok:
                _navegar(ws, c, MESSENGER_URL, espera=6)
                tok = ler_com_retry()
        if not tok:
            raise RuntimeError("Nao foi possivel obter o token via SSO/login "
                               "(sessao expirou e/ou login automatico falhou; verifique credenciais/2FA).")
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
        flags += ["--headless=new", "--disable-gpu"]
    flags.append(ONVIO_LOGIN)  # abre no login do Onvio; o SSO usa a sessao do perfil

    proc = subprocess.Popen(flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not _esperar_devtools(host, porta):
            raise RuntimeError(f"DevTools nao respondeu em {host}:{porta} apos o lancamento.")
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
    salvar_token(token, caminho)
    exp = _decodificar_exp(token)
    resta = int((exp - time.time()) / 3600) if exp else "?"
    return True, f"Token renovado (validade ~{resta}h). Salvo em {caminho}."


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
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ok, msg = renovar(args.host, args.porta, forcar=args.forcar, launch=args.launch,
                      chrome=args.chrome, profile=args.profile, headless=(not args.visivel),
                      recarregar=args.recarregar, sso=args.sso)
    print(("OK: " if ok else "ERRO: ") + msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    _main(sys.argv[1:])
