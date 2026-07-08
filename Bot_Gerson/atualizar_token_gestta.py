# -*- coding: utf-8 -*-
"""
atualizar_token_gestta.py
-------------------------
Renova o token (JWT) do Messenger do Gestta lendo-o de um Chrome que já está
logado no Gestta, via protocolo DevTools (porta de depuração remota).

NÃO usa e-mail/senha: apenas lê o token que a própria sessão logada guardou no
localStorage do navegador (chave 'user-jwt'). O token grava em
config/gestta_token.txt, que é lido por messenger_gestta.py.

Pré-requisito na VM:
  Um Chrome logado no Gestta, iniciado com a porta de depuração aberta, ex.:
    chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\\chrome_gestta"
  (use o .bat de exemplo iniciar_chrome_gestta.bat). Mantenha uma aba aberta em
  https://app.gestta.com.br logada. O token dura ~24h; enquanto a sessão do
  Chrome continuar válida, este script sempre pega um token fresco.

Uso:
  python atualizar_token_gestta.py                # porta 9222
  python atualizar_token_gestta.py --porta 9223
  python atualizar_token_gestta.py --host 127.0.0.1 --porta 9222

Dependências: requests (já usado no projeto) e websocket-client.
  pip install websocket-client
"""

import os
import sys
import json
import base64
import time
import logging

import requests

try:
    import websocket  # websocket-client
except ImportError:
    websocket = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "config", "gestta_token.txt")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9222
GESTTA_URL_HINT = "gestta.com.br"

logger = logging.getLogger("atualizar_token_gestta")


def _decodificar_exp(jwt):
    """Retorna o timestamp 'exp' do JWT (ou None)."""
    try:
        payload = jwt.replace("JWT ", "").split(".")[1]
        payload += "=" * (-len(payload) % 4)  # padding base64
        data = json.loads(base64.urlsafe_b64decode(payload))
        return data.get("exp")
    except Exception:
        return None


def _listar_abas(host, porta):
    r = requests.get(f"http://{host}:{porta}/json", timeout=5)
    r.raise_for_status()
    return r.json()


def _ler_localstorage_key(ws_url, chave):
    """Abre o websocket DevTools e lê localStorage[chave] da aba."""
    if websocket is None:
        raise RuntimeError("Biblioteca 'websocket-client' não instalada. "
                           "Rode: pip install websocket-client")
    ws = websocket.create_connection(ws_url, timeout=8)
    try:
        expr = f"window.localStorage.getItem({json.dumps(chave)})"
        ws.send(json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {"expression": expr, "returnByValue": True},
        }))
        # aguarda a resposta com id=1
        for _ in range(10):
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                return (((msg.get("result") or {}).get("result") or {}).get("value"))
        return None
    finally:
        ws.close()


def obter_token_do_chrome(host=DEFAULT_HOST, porta=DEFAULT_PORT):
    """Localiza a aba do Gestta no Chrome de depuração e devolve o JWT (com prefixo 'JWT ')."""
    abas = _listar_abas(host, porta)
    alvos = [a for a in abas if a.get("type") == "page"
             and GESTTA_URL_HINT in (a.get("url") or "")]
    if not alvos:
        raise RuntimeError(
            f"Nenhuma aba do Gestta encontrada no Chrome em {host}:{porta}. "
            "Abra https://app.gestta.com.br logado nesse Chrome."
        )
    for aba in alvos:
        ws_url = aba.get("webSocketDebuggerUrl")
        if not ws_url:
            continue
        raw = _ler_localstorage_key(ws_url, "user-jwt")
        if not raw:
            continue
        token = json.loads(raw) if raw.strip().startswith('"') else raw
        token = str(token).strip().strip('"')
        if token:
            if not token.upper().startswith("JWT "):
                token = "JWT " + token
            return token
    raise RuntimeError("Aba do Gestta encontrada, mas sem 'user-jwt' no localStorage "
                       "(sessão pode ter deslogado).")


def salvar_token(token, caminho=TOKEN_FILE):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(token)
    return caminho


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


def renovar(host=DEFAULT_HOST, porta=DEFAULT_PORT, forcar=False, caminho=TOKEN_FILE):
    """
    Renova o token se necessário. Retorna (ok:bool, mensagem:str).
    Se 'forcar' for False e o token atual ainda for válido, não faz nada.
    """
    if not forcar and token_valido(caminho):
        return True, "Token atual ainda válido; nada a fazer."
    try:
        token = obter_token_do_chrome(host, porta)
    except Exception as e:  # noqa
        return False, f"Falha ao ler token do Chrome: {e}"
    salvar_token(token, caminho)
    exp = _decodificar_exp(token)
    resta = int((exp - time.time()) / 3600) if exp else "?"
    return True, f"Token renovado (validade ~{resta}h). Salvo em {caminho}."


def _main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Renova o token do Gestta a partir de um Chrome logado.")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--porta", type=int, default=DEFAULT_PORT)
    ap.add_argument("--forcar", action="store_true", help="Renova mesmo se o token atual ainda for válido.")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ok, msg = renovar(args.host, args.porta, forcar=args.forcar)
    print(("OK: " if ok else "ERRO: ") + msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    _main(sys.argv[1:])
