# -*- coding: utf-8 -*-
"""
messenger_gestta.py
-------------------
Sincroniza a marcacao de empresas SUSPENSAS nos contatos do Messenger do Gestta,
usando como fonte da verdade o estado das empresas monitorado pelo Bot Gerson
(data/estado_empresas.json).

Regra de negocio:
- Cada contato do Gestta tem um campo `name` no formato "<codigos> - NOME ...".
  Os codigos das empresas-cliente ficam embutidos nesse texto, separados por "/"
  (ex.: "09/55/884 - JOSIAS").
- Se ALGUM codigo do contato pertencer a uma empresa com status SUSPENSA no Gerson,
  o nome recebe o sufixo padronizado "[SUSPENSA: <codigos>]".
- Se nenhum codigo estiver suspenso, qualquer marcacao antiga de suspensa e removida
  (limpeza), DESDE QUE pelo menos um dos codigos do contato seja conhecido pelo Gerson.
  Se nenhum codigo for conhecido, a marcacao manual e preservada (remocao arriscada).
- O Gerson e a fonte da verdade: marcacoes manuais divergentes sao sobrescritas.

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
PAGE_LIMIT = 200

logger = logging.getLogger("messenger_gestta")

# Regex de marcacao de suspensa: qualquer par de colchetes contendo "suspensa".
# Cobre [SUSPENSA], [ SUSPENSA], [881 SUSPENSA], [239, 994 SUSPENSA], [SUSPENSA: 46] ...
_TAG_RE = re.compile(r"\s*\[[^\]]*suspensa[^\]]*\]", re.IGNORECASE)


# ----------------------------------------------------------------------------
# Fonte da verdade: estado do Gerson
# ----------------------------------------------------------------------------
def _norm_code(code):
    """Normaliza um codigo: remove zeros a esquerda. '09' -> '9', '007' -> '7'."""
    s = str(code).strip().lstrip("0")
    return s if s else "0"


def carregar_estado(estado_path=ESTADO_PATH):
    """Le estado_empresas.json e devolve (suspensas:set, conhecidas:set) de codigos normalizados.

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
    suspensas, conhecidas = set(), set()
    for codigo, info in registros.items():
        if not str(codigo).strip().isdigit():
            continue  # ignora chaves nao-numericas (ex.: 'BPO', 'Adv')
        c = _norm_code(codigo)
        conhecidas.add(c)
        status = str((info or {}).get("status", "")).upper()
        if status.startswith(STATUS_SUSPENSA_PREFIX):
            suspensas.add(c)
    return suspensas, conhecidas


# ----------------------------------------------------------------------------
# Parsing do nome do contato
# ----------------------------------------------------------------------------
def extrair_codigos(name):
    """
    Extrai os codigos de empresa embutidos no inicio do `name`.
    Considera o trecho ANTES do primeiro ' - <letra>' (que separa os codigos do nome
    da pessoa) e pega todos os grupos de digitos, normalizando zeros a esquerda.
    """
    if not name:
        return []
    seg = re.split(r"\s*-\s*[A-Za-zÀ-ÿ]", name, maxsplit=1)[0]
    grupos = re.findall(r"\d+", seg)
    vistos, out = set(), []
    for g in grupos:
        c = _norm_code(g)
        if c not in vistos:
            vistos.add(c)
            out.append(c)
    return out


def tem_marcacao(name):
    return bool(_TAG_RE.search(name or ""))


def remover_marcacao(name):
    return _TAG_RE.sub("", name or "").rstrip()


def calcular_novo_nome(name, suspensas, conhecidas):
    """
    Devolve (novo_nome, acao) onde acao em:
      'add'      - adiciona marcacao (nao tinha)
      'fmt'      - reformatar/atualizar marcacao existente
      'remove'   - remove marcacao (empresa conhecida e ativa)
      'skip_risk'- tinha marcacao mas nenhum codigo conhecido -> preserva
      'none'     - nada a fazer
    """
    codigos = extrair_codigos(name)
    suspensos = [c for c in codigos if c in suspensas]
    tinha = tem_marcacao(name)
    base = remover_marcacao(name)

    if suspensos:
        suspensos_ord = sorted(suspensos, key=lambda x: int(x) if x.isdigit() else 0)
        novo = base + " [SUSPENSA: " + ", ".join(suspensos_ord) + "]"
        if novo == name:
            return name, "none"
        return novo, ("fmt" if tinha else "add")

    # nenhum codigo suspenso
    if tinha:
        algum_conhecido = any(c in conhecidas for c in codigos)
        if not algum_conhecido:
            return name, "skip_risk"      # preserva marcacao humana (codigos desconhecidos)
        if base == name:
            return name, "none"
        return base, "remove"

    return name, "none"


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
        if not _refresh.token_valido(TOKEN_FILE):
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

    suspensas, conhecidas = carregar_estado(estado_path)
    token = token or obter_token()
    session = session or requests.Session()

    resumo = {"total": 0, "add": 0, "fmt": 0, "remove": 0, "skip_risk": 0,
              "aplicados": 0, "erros": 0}
    alteracoes, riscos, erros = [], [], []

    for c in listar_contatos(token, session=session):
        resumo["total"] += 1
        name = c.get("name", "") or ""
        novo, acao = calcular_novo_nome(name, suspensas, conhecidas)
        if acao == "none":
            continue
        if acao == "skip_risk":
            resumo["skip_risk"] += 1
            riscos.append({"id": c.get("_id"), "name": name,
                           "codigos": extrair_codigos(name)})
            continue

        resumo[acao] += 1
        registro = {"id": c.get("_id"), "acao": acao, "antes": name, "depois": novo}
        alteracoes.append(registro)

        if apply:
            try:
                atualizar_contato(token, c.get("_id"), novo, c.get("phone_number"), session=session)
                resumo["aplicados"] += 1
                logger.info("Gestta: %s | %r -> %r", acao, name, novo)
                time.sleep(0.15)  # gentileza com a API
            except Exception as e:  # noqa
                resumo["erros"] += 1
                erros.append({"id": c.get("_id"), "erro": str(e)})
                logger.error("Gestta: erro ao atualizar %s: %s", c.get("_id"), e)

        if limite and len(alteracoes) >= limite:
            break

    return {"resumo": resumo, "alteracoes": alteracoes, "riscos": riscos, "erros": erros}


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
    suspensas, conhecidas = carregar_estado(estado_path)
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
        novo, acao = calcular_novo_nome(name, suspensas, conhecidas)
        if acao in ("none", "skip_risk"):
            continue
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
    ap = argparse.ArgumentParser(description="Sincroniza marcacao [SUSPENSA] nos contatos do Gestta.")
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
    print(f"  adicionar tag ....... {r['add']}")
    print(f"  reformatar tag ...... {r['fmt']}")
    print(f"  remover tag ......... {r['remove']}")
    print(f"  PULADOS (arriscados)  {r['skip_risk']}")
    if args.apply:
        print(f"  aplicados ........... {r['aplicados']}")
        print(f"  erros ............... {r['erros']}")
    print("\n=== EXEMPLOS ===")
    for a in res["alteracoes"][:15]:
        print(f"  [{a['acao']}] {a['antes']!r}\n        -> {a['depois']!r}")
    if res["riscos"]:
        print("\n=== PULADOS (marcacao manual, codigos desconhecidos pelo Gerson) ===")
        for x in res["riscos"][:15]:
            print(f"  {x['name']!r}  (codigos {x['codigos']})")


if __name__ == "__main__":
    _main(sys.argv[1:])
