# -*- coding: utf-8 -*-
"""
messenger_gestta.py
-------------------
Sincroniza as marcacoes de empresas SUSPENSAS e INATIVAS nos contatos do Messenger
do Gestta, usando como fonte da verdade o estado das empresas monitorado pelo Bot
Gerson (data/estado_empresas.json).

Regra de negocio:
- Cada contato do Gestta tem um campo `name` no formato "<codigos> - NOME ...".
  Os codigos das empresas-cliente ficam embutidos nesse texto, separados por "/"
  (ex.: "09/55/884 - JOSIAS").
- SUSPENSA: se ALGUM codigo do contato estiver suspenso, o nome recebe o sufixo
  "[SUSPENSA: <codigos>]".
- INATIVA (status INATIVA, BAIXA ou DEVOLVIDA). A automacao de mensagens do Gestta
  ignora qualquer contato com "inativo/inativa" no nome, entao:
    * TODOS os codigos inativos -> "[#INATIVO: <codigos>]" (contato ignorado);
    * SO PARTE inativa          -> "[ENCERRADA: <codigos>]" (sem "inativ", o
                                   contato continua recebendo mensagens).
- "#INATIVO" fora de colchetes e MANUAL (usado tambem para inativar a PESSOA,
  nao a empresa): o bot so padroniza a grafia (INATIVA, (INATIVO), [inativo]...
  -> "#INATIVO") e NUNCA o remove. Contato com varios codigos, #INATIVO manual e
  empresas mistas (parte ativa) entra na lista "revisar" para conferencia humana.
- Marcacoes do bot ([SUSPENSA], [ENCERRADA], [#INATIVO: ...]) sao limpas quando
  deixam de valer, DESDE QUE pelo menos um codigo do contato seja conhecido pelo
  Gerson. Se nenhum for conhecido, as marcacoes sao preservadas (remocao arriscada).
- O Gerson e a fonte da verdade: marcacoes divergentes sao sobrescritas.

Idempotente: rodar varias vezes produz o mesmo resultado.
Por padrao roda em DRY-RUN (nao escreve). Use --apply para gravar.

API do Gestta (descoberta via inspecao):
  Listar:    GET  https://api.gestta.com.br/messenger-admin/company/contact?page=&limit=&sort=name
             -> { docs:[{_id,name,phone_number,...}], totalDocs, hasNextPage, nextPage, ... }
  Atualizar: PUT  https://api.gestta.com.br/messenger-admin/company/contact/<id>
             body: {"name": "...", "phone_number": "..."}
  Auth:      header  Authorization: JWT <token>   (token expira ~24h)

O token e lido de (nesta ordem):
  1. variavel de ambiente GESTTA_JWT
  2. arquivo config/gestta_token.txt (dentro de Bot_Gerson)
O token deve incluir (ou nao) o prefixo "JWT " - o modulo normaliza.
"""

import os
import re
import sys
import json
import time
import logging

try:
    import requests
except ImportError:
    requests = None

# ----------------------------------------------------------------------------
# Configuracao
# ----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ESTADO_PATH = os.path.join(BASE_DIR, "data", "estado_empresas.json")
TOKEN_FILE = os.path.join(BASE_DIR, "config", "gestta_token.txt")

API_BASE = "https://api.gestta.com.br/messenger-admin/company/contact"
STATUS_SUSPENSA_PREFIX = "SUSPENSA"   # cobre "SUSPENSA", "SUSPENSA (MANUTENCAO)", etc.
# Status que contam como empresa inativa (ja normalizados pelo Gerson; as
# variacoes cruas ficam aqui por seguranca).
STATUS_INATIVOS = {"INATIVA", "INATIVO", "BAIXA", "BAIXADA", "DEVOLVIDA"}
TAG_INATIVO_MANUAL = "#INATIVO"
PAGE_LIMIT = 200

logger = logging.getLogger("messenger_gestta")

# Regex de marcacao de suspensa: qualquer par de colchetes contendo "suspensa".
# Cobre [SUSPENSA], [ SUSPENSA], [881 SUSPENSA], [239, 994 SUSPENSA], [SUSPENSA: 46] ...
_TAG_RE = re.compile(r"\s*\[[^\]]*suspensa[^\]]*\]", re.IGNORECASE)
# Marcacao do BOT de contato todo inativo: "[#INATIVO: 55, 884]" (o ":" a diferencia
# de um "[INATIVO]" manual).
_TAG_INAT_BOT_RE = re.compile(r"\s*\[\s*#\s*inativ[oa]s?\s*:[^\]]*\]", re.IGNORECASE)
# Marcacao do BOT de contato parcialmente inativo: "[ENCERRADA: 55]".
_TAG_ENC_RE = re.compile(r"\s*\[\s*encerrad[oa]s?\b[^\]]*\]", re.IGNORECASE)
# Inativacao MANUAL em qualquer grafia: #INATIVO, INATIVA, (inativo), [INATIVO] ...
_MANUAL_INAT_RE = re.compile(
    r"[\(\[\{]\s*#?\s*inativ[oa]s?\s*[\)\]\}]|#\s*inativ[oa]s?\b|\binativ[oa]s?\b",
    re.IGNORECASE,
)


# ----------------------------------------------------------------------------
# Fonte da verdade: estado do Gerson
# ----------------------------------------------------------------------------
def _norm_code(code):
    """Normaliza um codigo: remove zeros a esquerda. '09' -> '9', '007' -> '7'."""
    s = str(code).strip().lstrip("0")
    return s if s else "0"


def carregar_estado(estado_path=ESTADO_PATH):
    """Le estado_empresas.json e devolve (suspensas, inativas, conhecidas): sets de
    codigos normalizados.

    Faz retry em caso de leitura parcial (o Gerson pode estar gravando o arquivo
    no mesmo instante); com a gravacao atomica do Gerson isso vira redundancia segura."""
    data = None
    for tentativa in range(4):
        try:
            with open(estado_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            break
        except (json.JSONDecodeError, ValueError):
            if tentativa == 3:
                raise
            time.sleep(0.4)
    registros = data.get("registros", data)  # compat: pode ser {registros:{...}} ou {...}
    suspensas, inativas, conhecidas = set(), set(), set()
    for codigo, info in registros.items():
        if not str(codigo).strip().isdigit():
            continue  # ignora chaves nao-numericas (ex.: 'BPO', 'Adv')
        c = _norm_code(codigo)
        conhecidas.add(c)
        status = str((info or {}).get("status", "")).upper().strip()
        if status.startswith(STATUS_SUSPENSA_PREFIX):
            suspensas.add(c)
        elif status in STATUS_INATIVOS:
            inativas.add(c)
    return suspensas, inativas, conhecidas


# ----------------------------------------------------------------------------
# Parsing do nome do contato
# ----------------------------------------------------------------------------
def _limpar_separadores(texto):
    """Arruma o que sobra depois de tirar um 'INATIVO' do meio do nome:
    espacos duplos, ' - - ' e separadores pendurados nas pontas."""
    texto = re.sub(r"(?:\s*-\s*){2,}", " - ", texto)
    texto = re.sub(r"\s{2,}", " ", texto)
    texto = re.sub(r"^[\s\-–|/,;:]+", "", texto)
    texto = re.sub(r"[\s\-–|/,;:]+$", "", texto)
    return texto


def analisar_nome(name):
    """
    Separa o `name` em (base, tags, manuais):
      base    - nome sem nenhuma marcacao
      tags    - {'inativo': [...], 'encerrada': [...], 'suspensa': [...]} com o texto
                original das marcacoes entre colchetes encontradas
      manuais - ocorrencias de inativacao manual (#INATIVO, INATIVA, (inativo)...)
    """
    resto = name or ""
    tags = {}
    for chave, rx in (("inativo", _TAG_INAT_BOT_RE), ("encerrada", _TAG_ENC_RE),
                      ("suspensa", _TAG_RE)):
        tags[chave] = [m.strip() for m in rx.findall(resto)]
        resto = rx.sub("", resto)
    manuais = _MANUAL_INAT_RE.findall(resto)
    if manuais:
        resto = _limpar_separadores(_MANUAL_INAT_RE.sub(" ", resto))
    else:
        resto = resto.rstrip()
    return resto, tags, manuais


_COD = r"\d+(?:\s*/\s*\d+)*"
# Codigos no INICIO: "09/55/884 - JOSIAS", "187 Andrade", "[555] - SIMONE".
# Nao aceita numero colado em letra/digito ("1º CARTORIO", "24 99981-1412").
_COD_INICIO_RE = re.compile(r"^\s*\[?\s*(" + _COD + r")\s*\]?\s*/?(?=\s*-|\s+[^\d\s/]|\s*$)")


def _codigos_do_texto(texto):
    # So contam codigos no INICIO. Numeros soltos ("Loja 05", "santos61", "A3") nao
    # sao codigos, e codigos DEPOIS do nome ("Aline - 754/755") sao a convencao de
    # contato ja inativado manualmente (guarda de qual empresa a pessoa era): o bot
    # nao mexe nesses contatos.
    m = _COD_INICIO_RE.match(texto)
    if not m:
        return []
    vistos, out = set(), []
    for g in re.findall(r"\d+", m.group(1)):
        c = _norm_code(g)
        if c not in vistos:
            vistos.add(c)
            out.append(c)
    return out


def extrair_codigos(name):
    """
    Extrai os codigos de empresa embutidos no inicio do `name` (ignorando as
    marcacoes), normalizando zeros a esquerda.
    """
    if not name:
        return []
    return _codigos_do_texto(analisar_nome(name)[0])


def _ordenar(codigos):
    return sorted(codigos, key=lambda x: int(x) if x.isdigit() else 0)


def _delta(rotulo, antes, depois):
    """Classifica a mudanca de UMA marcacao: '+' adicionou, '-' removeu, '~' mudou."""
    if not antes and depois:
        return [rotulo + "+"]
    if antes and not depois:
        return [rotulo + "-"]
    if antes and depois and (len(antes) > 1 or antes[0] != depois):
        return [rotulo + "~"]
    return []


def calcular_novo_nome(name, suspensas, inativas, conhecidas):
    """
    Devolve (novo_nome, acoes, alerta):
      acoes  - lista do que mudou: 'suspensa+/-/~', 'inativo+/-/~' ([#INATIVO: ..]),
               'encerrada+/-/~', 'normalizado' (grafia do #INATIVO manual).
               Lista vazia = nada a fazer.
      alerta - None | 'skip_risk' (marcacoes preservadas: nenhum codigo conhecido)
                    | 'revisar'   (#INATIVO manual em contato com empresas mistas)
    """
    name = name or ""
    base, tags, manuais = analisar_nome(name)
    codigos = _codigos_do_texto(base)
    tem_manual = bool(manuais)
    alerta = None

    partes = [base]
    if tem_manual:
        partes.append(TAG_INATIVO_MANUAL)

    tag_inat = tag_enc = tag_susp = None
    if not any(c in conhecidas for c in codigos):
        # Sem codigo conhecido nao da para afirmar nada: preserva as marcacoes.
        preservadas = tags["inativo"] + tags["encerrada"] + tags["suspensa"]
        partes += preservadas
        if preservadas:
            alerta = "skip_risk"
        acoes = []
    else:
        inat = _ordenar([c for c in codigos if c in inativas])
        susp = _ordenar([c for c in codigos if c in suspensas])
        todos_inativos = bool(inat) and len(inat) == len(codigos)
        if todos_inativos and not tem_manual:
            tag_inat = "[#INATIVO: " + ", ".join(inat) + "]"
        elif inat:
            # Parcial, ou ja tem #INATIVO manual (contato ja ignorado): so registra.
            tag_enc = "[ENCERRADA: " + ", ".join(inat) + "]"
        if susp:
            tag_susp = "[SUSPENSA: " + ", ".join(susp) + "]"
        partes += [t for t in (tag_inat, tag_enc, tag_susp) if t]
        if tem_manual and len(codigos) > 1 and inat and not todos_inativos:
            alerta = "revisar"
        acoes = (_delta("inativo", tags["inativo"], tag_inat)
                 + _delta("encerrada", tags["encerrada"], tag_enc)
                 + _delta("suspensa", tags["suspensa"], tag_susp))

    grafia_manual_errada = tem_manual and manuais != [TAG_INATIVO_MANUAL]
    if not acoes and not grafia_manual_errada:
        # Nada mudou de fato: nao reescreve so por espaco/ordem das marcacoes.
        return name, [], alerta
    novo = " ".join(p for p in partes if p)
    if novo == name:
        return name, [], alerta
    if grafia_manual_errada:
        acoes.append("normalizado")
    return novo, acoes, alerta


# ----------------------------------------------------------------------------
# Cliente HTTP do Gestta
# ----------------------------------------------------------------------------
def _tentar_renovar_do_chrome():
    """Tenta renovar o token subindo um Chrome headless proprio (SSO automatico).
    Best-effort: qualquer erro apenas gera aviso no log."""
    try:
        import atualizar_token_gestta as _refresh
    except Exception:  # noqa
        return
    host = os.environ.get("GESTTA_CHROME_HOST", "127.0.0.1")
    try:
        porta = int(os.environ.get("GESTTA_CHROME_PORT", "9222"))
    except ValueError:
        porta = 9222
    try:
        # launch=True: sobe um Chrome headless com o perfil salvo, faz o SSO do
        # Onvio sozinho, le o token e fecha (nao depende de um Chrome ja aberto).
        ok, msg = _refresh.renovar(host, porta, launch=True, forcar=True)
        logger.info("Renovacao de token Gestta: %s", msg)
    except Exception as e:  # noqa
        logger.warning("Nao foi possivel renovar token do Gestta: %s", e)


def obter_token():
    # 1) variavel de ambiente tem prioridade (ex.: setada manualmente)
    tok = os.environ.get("GESTTA_JWT")
    if tok:
        tok = tok.strip().strip('"')
        return tok if tok.upper().startswith("JWT ") else "JWT " + tok

    # 2) arquivo de token; se ausente/expirado, tenta renovar do Chrome logado
    try:
        import atualizar_token_gestta as _refresh
        # Margem curta (1h) DE PROPOSITO: aqui o token vai ser usado agora, entao
        # so interessa saber se ele aguenta esta operacao. A margem larga do laco
        # de renovacao (MARGEM_PADRAO_SEG) faria esta chamada sob demanda subir um
        # Chrome sem necessidade, com um token que ainda funciona perfeitamente.
        if not _refresh.token_valido(TOKEN_FILE, margem_seg=3600):
            _tentar_renovar_do_chrome()
    except Exception:  # noqa
        pass

    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            tok = f.read().strip().strip('"')
    if not tok:
        raise RuntimeError(
            "Token do Gestta nao encontrado. Defina GESTTA_JWT, crie "
            "config/gestta_token.txt, ou deixe um Chrome logado no Gestta com "
            "porta de depuracao (ver atualizar_token_gestta.py)."
        )
    tok = tok.strip().strip('"')
    if not tok.upper().startswith("JWT "):
        tok = "JWT " + tok
    return tok


def _headers(token):
    return {"Authorization": token, "Accept": "application/json", "Content-Type": "application/json"}


def listar_contatos(token, session=None):
    """Gera todos os contatos (dicts com _id, name, phone_number)."""
    s = session or requests.Session()
    page = 1
    while True:
        r = s.get(API_BASE, headers=_headers(token),
                  params={"page": page, "limit": PAGE_LIMIT, "sort": "name"}, timeout=30)
        r.raise_for_status()
        j = r.json()
        for d in j.get("docs", []):
            yield d
        if not j.get("hasNextPage"):
            break
        page += 1
        if page > 100:  # trava de seguranca
            break


def atualizar_contato(token, contact_id, novo_nome, phone_number, session=None):
    s = session or requests.Session()
    r = s.put(API_BASE + "/" + str(contact_id), headers=_headers(token),
              data=json.dumps({"name": novo_nome, "phone_number": phone_number or ""}),
              timeout=30)
    r.raise_for_status()
    return r.json() if r.content else {}


# ----------------------------------------------------------------------------
# Sincronizacao
# ----------------------------------------------------------------------------
def sincronizar(apply=False, token=None, estado_path=ESTADO_PATH, limite=None, session=None):
    """
    Percorre todos os contatos e aplica (ou simula) as marcacoes.
    Retorna um dict com o resumo e a lista de alteracoes.
    """
    if requests is None:
        raise RuntimeError("A biblioteca 'requests' e necessaria. Instale com: pip install requests")

    suspensas, inativas, conhecidas = carregar_estado(estado_path)
    token = token or obter_token()
    session = session or requests.Session()

    resumo = {"total": 0, "alterados": 0, "skip_risk": 0, "revisar": 0,
              "aplicados": 0, "erros": 0}
    for rot in ("suspensa", "inativo", "encerrada"):
        for sinal in "+-~":
            resumo[rot + sinal] = 0
    resumo["normalizado"] = 0
    alteracoes, riscos, revisar, erros = [], [], [], []

    for c in listar_contatos(token, session=session):
        resumo["total"] += 1
        name = c.get("name", "") or ""
        novo, acoes, alerta = calcular_novo_nome(name, suspensas, inativas, conhecidas)
        if alerta:
            resumo[alerta] += 1
            (riscos if alerta == "skip_risk" else revisar).append(
                {"id": c.get("_id"), "name": name, "codigos": extrair_codigos(name)})
        if not acoes:
            continue

        resumo["alterados"] += 1
        for a in acoes:
            resumo[a] += 1
        registro = {"id": c.get("_id"), "acao": ",".join(acoes), "antes": name, "depois": novo}
        alteracoes.append(registro)

        if apply:
            try:
                atualizar_contato(token, c.get("_id"), novo, c.get("phone_number"), session=session)
                resumo["aplicados"] += 1
                logger.info("Gestta: %s | %r -> %r", registro["acao"], name, novo)
                time.sleep(0.15)  # gentileza com a API
            except Exception as e:  # noqa
                resumo["erros"] += 1
                erros.append({"id": c.get("_id"), "erro": str(e)})
                logger.error("Gestta: erro ao atualizar %s: %s", c.get("_id"), e)

        if limite and len(alteracoes) >= limite:
            break

    return {"resumo": resumo, "alteracoes": alteracoes, "riscos": riscos,
            "revisar": revisar, "erros": erros}


# ----------------------------------------------------------------------------
# Hook para o Gerson: atualizar apenas UMA empresa (por codigo)
# ----------------------------------------------------------------------------
def atualizar_por_codigo(codigo, apply=True, token=None, estado_path=ESTADO_PATH, session=None):
    """
    Reavalia e atualiza somente os contatos que contem `codigo` no nome.
    Ideal para chamar no momento em que o Gerson detecta mudanca de status
    de UMA empresa (evita varrer os 2000+ contatos toda vez).
    """
    if requests is None:
        raise RuntimeError("A biblioteca 'requests' e necessaria.")
    suspensas, inativas, conhecidas = carregar_estado(estado_path)
    token = token or obter_token()
    session = session or requests.Session()
    alvo = _norm_code(codigo)

    resultado = {"codigo": alvo, "verificados": 0, "aplicados": 0,
                 "alteracoes": [], "erros": []}
    for c in listar_contatos(token, session=session):
        name = c.get("name", "") or ""
        if alvo not in extrair_codigos(name):
            continue
        resultado["verificados"] += 1
        novo, acoes, _alerta = calcular_novo_nome(name, suspensas, inativas, conhecidas)
        if not acoes:
            continue
        acao = ",".join(acoes)
        resultado["alteracoes"].append({"id": c.get("_id"), "acao": acao,
                                         "antes": name, "depois": novo})
        if apply:
            try:
                atualizar_contato(token, c.get("_id"), novo, c.get("phone_number"), session=session)
                resultado["aplicados"] += 1
                logger.info("Gestta[cod %s]: %s | %r -> %r", alvo, acao, name, novo)
            except Exception as e:  # noqa
                resultado["erros"].append({"id": c.get("_id"), "erro": str(e)})
    return resultado


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def _main(argv):
    import argparse
    ap = argparse.ArgumentParser(
        description="Sincroniza as marcacoes [SUSPENSA], [ENCERRADA] e [#INATIVO] nos contatos do Gestta.")
    ap.add_argument("--apply", action="store_true", help="Grava as alteracoes (padrao: dry-run).")
    ap.add_argument("--codigo", help="Atualiza apenas os contatos de um codigo de empresa.")
    ap.add_argument("--limite", type=int, help="Limita o numero de alteracoes (para testes).")
    ap.add_argument("--estado", default=ESTADO_PATH, help="Caminho do estado_empresas.json.")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.codigo:
        res = atualizar_por_codigo(args.codigo, apply=args.apply, estado_path=args.estado)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    res = sincronizar(apply=args.apply, estado_path=args.estado, limite=args.limite)
    r = res["resumo"]
    print("\n=== RESUMO %s ===" % ("APLICADO" if args.apply else "DRY-RUN"))
    print(f"  contatos totais ..... {r['total']}")
    print(f"  contatos alterados .. {r['alterados']}")
    for rot, desc in (("suspensa", "[SUSPENSA]"), ("inativo", "[#INATIVO: ..]"),
                      ("encerrada", "[ENCERRADA]")):
        print(f"  {desc:<16} add={r[rot + '+']} remove={r[rot + '-']} atualiza={r[rot + '~']}")
    print(f"  #INATIVO padronizado  {r['normalizado']}")
    print(f"  PULADOS (arriscados)  {r['skip_risk']}")
    print(f"  REVISAR (manual)      {r['revisar']}")
    if args.apply:
        print(f"  aplicados ........... {r['aplicados']}")
        print(f"  erros ............... {r['erros']}")
    print("\n=== EXEMPLOS ===")
    for a in res["alteracoes"][:15]:
        print(f"  [{a['acao']}] {a['antes']!r}\n        -> {a['depois']!r}")
    if res["riscos"]:
        print("\n=== PULADOS (marcacao preservada, codigos desconhecidos pelo Gerson) ===")
        for x in res["riscos"][:15]:
            print(f"  {x['name']!r}  (codigos {x['codigos']})")
    if res["revisar"]:
        print("\n=== REVISAR (#INATIVO manual com empresas ativas e inativas) ===")
        for x in res["revisar"]:
            print(f"  {x['name']!r}  (codigos {x['codigos']})")


if __name__ == "__main__":
    _main(sys.argv[1:])
