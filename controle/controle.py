# -*- coding: utf-8 -*-
"""
controle.py — o "porteiro" entre a Libby e o Docker da VPS.

A Libby precisa ver e ligar/desligar os bots, mas dar a ELA o docker.sock seria
dar root na VPS a uma aplicacao aberta na internet: com ele da para ler as
variaveis de ambiente (senhas) de qualquer container, inclusive do Postgres
compartilhado, ou derrubar tudo. Este processo e o unico que fala com o Docker,
e so sabe fazer uma lista FECHADA de coisas com uma lista FECHADA de containers:

    GET  /bots                         status dos tres bots
    GET  /bots/<bot>/logs?linhas=N     ultimas N linhas do log (max 500)
    POST /bots/<bot>/<acao>            acao = ligar | desligar | reiniciar

Os nomes dos containers estao fixos aqui (BOTS), nunca vem de quem chama: mesmo
com a Libby invadida, o maximo alcancavel e ligar/desligar estes tres bots e ler
os logs deles. Nada de criar container, exec, inspecionar outro container, etc.

Autenticacao: header X-Controle-Token igual a CONTROLE_TOKEN (comparacao em
tempo constante). Sem token configurado (ou curto demais), o processo nem sobe.
Nao publica porta: so e alcancavel pela rede docker libby_bots, onde esta a Libby.

So biblioteca padrao: fala HTTP com o Docker Engine pelo socket unix.
"""
from __future__ import annotations

import hmac
import http.client
import json
import os
import socket
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# Chave usada na URL -> nome do container (docker-compose.yml). Lista fechada.
BOTS = {
    "bip": "disbot_bip",
    "rebecca": "disbot_rebecca",
    "gerson": "disbot_gerson",
}
ACOES = {"ligar": "start", "desligar": "stop", "reiniciar": "restart"}

SOCKET = os.environ.get("DOCKER_SOCKET", "/var/run/docker.sock")
PORTA = int(os.environ.get("CONTROLE_PORTA", "8090"))
TOKEN = os.environ.get("CONTROLE_TOKEN", "").strip()
# Tempo que o Docker espera o bot encerrar sozinho antes de matar (SIGKILL).
ESPERA_PARADA_SEG = 20
MAX_LINHAS = 500


def _log(msg: str) -> None:
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


# ---------------------------------------------------------------- Docker API

class _ConexaoUnix(http.client.HTTPConnection):
    def __init__(self, caminho: str, timeout: float):
        super().__init__("localhost", timeout=timeout)
        self._caminho = caminho

    def connect(self):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(self._caminho)
        self.sock = s


def _docker(metodo: str, caminho: str, timeout: float = 15) -> tuple[int, bytes]:
    c = _ConexaoUnix(SOCKET, timeout)
    try:
        c.request(metodo, caminho, headers={"Host": "docker"})
        r = c.getresponse()
        return r.status, r.read()
    finally:
        c.close()


def _demux(bruto: bytes) -> bytes:
    """Logs de container sem TTY vem multiplexados: cada bloco tem 8 bytes de
    cabecalho (stream, 0, 0, 0, tamanho em 4 bytes big-endian) + o texto."""
    if not bruto or bruto[0] not in (0, 1, 2):
        return bruto
    partes, i = [], 0
    while i + 8 <= len(bruto):
        n = int.from_bytes(bruto[i + 4:i + 8], "big")
        partes.append(bruto[i + 8:i + 8 + n])
        i += 8 + n
    return b"".join(partes)


def _memoria_mb(container: str):
    """Memoria em uso (MB), sem o cache de arquivo -- o mesmo numero do
    `docker stats`. None se nao der para ler."""
    st, corpo = _docker("GET", f"/containers/{container}/stats?stream=false&one-shot=true")
    if st != 200:
        return None
    m = json.loads(corpo).get("memory_stats") or {}
    uso = m.get("usage")
    if uso is None:
        return None
    s = m.get("stats") or {}
    cache = s.get("inactive_file", s.get("total_inactive_file", 0)) or 0
    return round(max(uso - cache, 0) / 1024 / 1024, 1)


def status(chave: str) -> dict:
    container = BOTS[chave]
    st, corpo = _docker("GET", f"/containers/{container}/json")
    if st == 404:
        return {"bot": chave, "container": container, "estado": "inexistente"}
    if st != 200:
        return {"bot": chave, "container": container, "estado": "erro",
                "detalhe": f"Docker respondeu HTTP {st}"}
    d = json.loads(corpo)
    s = d.get("State") or {}
    out = {
        "bot": chave,
        "container": container,
        "estado": s.get("Status"),            # running, exited, restarting...
        "rodando": bool(s.get("Running")),
        "iniciado_em": s.get("StartedAt"),
        "parado_em": s.get("FinishedAt"),
        "codigo_saida": s.get("ExitCode"),
        # 137 sozinho e ambiguo (docker stop que estourou a espera OU falta de
        # memoria); este campo desfaz a duvida.
        "sem_memoria": bool(s.get("OOMKilled")),
        "reinicios": d.get("RestartCount", 0),
        "limite_mb": round(((d.get("HostConfig") or {}).get("Memory") or 0) / 1024 / 1024) or None,
        "memoria_mb": None,
    }
    if out["rodando"]:
        try:
            out["memoria_mb"] = _memoria_mb(container)
        except Exception:  # noqa -- memoria e enfeite; nao derruba o status
            pass
    return out


def logs(chave: str, linhas: int) -> str:
    linhas = max(1, min(int(linhas), MAX_LINHAS))
    st, corpo = _docker("GET", f"/containers/{BOTS[chave]}/logs"
                               f"?stdout=1&stderr=1&tail={linhas}")
    if st != 200:
        raise RuntimeError(f"Docker respondeu HTTP {st} ao ler o log")
    return _demux(corpo).decode("utf-8", "replace")


def executar(chave: str, acao: str) -> tuple[bool, str]:
    verbo = ACOES[acao]
    sufixo = f"?t={ESPERA_PARADA_SEG}" if verbo in ("stop", "restart") else ""
    st, corpo = _docker("POST", f"/containers/{BOTS[chave]}/{verbo}{sufixo}",
                        timeout=ESPERA_PARADA_SEG + 30)
    if st == 204:
        return True, "ok"
    if st == 304:   # ja estava no estado pedido
        return True, "já estava " + ("ligado" if verbo == "start" else "desligado")
    try:
        detalhe = json.loads(corpo).get("message", "")
    except Exception:  # noqa
        detalhe = corpo[:200].decode("utf-8", "replace")
    return False, f"Docker respondeu HTTP {st}: {detalhe}"


# ---------------------------------------------------------------- HTTP

class Porteiro(BaseHTTPRequestHandler):
    server_version = "disbot-controle"

    def log_message(self, *a):   # o acesso comum nao interessa; as acoes sim
        pass

    def _responder(self, codigo: int, dados) -> None:
        corpo = json.dumps(dados, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _autorizado(self) -> bool:
        recebido = self.headers.get("X-Controle-Token", "")
        return hmac.compare_digest(recebido.encode(), TOKEN.encode())

    def _partes(self):
        u = urlparse(self.path)
        return [p for p in u.path.split("/") if p], parse_qs(u.query)

    def do_GET(self):
        if not self._autorizado():
            return self._responder(401, {"erro": "token invalido"})
        partes, qs = self._partes()
        try:
            if partes == ["bots"]:
                return self._responder(200, {"bots": [status(k) for k in BOTS]})
            if len(partes) == 3 and partes[0] == "bots" and partes[2] == "logs":
                if partes[1] not in BOTS:
                    return self._responder(404, {"erro": "bot desconhecido"})
                n = (qs.get("linhas") or ["40"])[0]
                if not n.isdigit():
                    return self._responder(400, {"erro": "linhas invalido"})
                return self._responder(200, {"bot": partes[1], "log": logs(partes[1], int(n))})
        except Exception as e:  # noqa
            _log(f"ERRO {self.path}: {e}")
            return self._responder(502, {"erro": f"falha ao falar com o Docker: {e}"})
        return self._responder(404, {"erro": "rota inexistente"})

    def do_POST(self):
        if not self._autorizado():
            _log(f"RECUSADO (token invalido) POST {self.path} de {self.client_address[0]}")
            return self._responder(401, {"erro": "token invalido"})
        partes, _ = self._partes()
        if not (len(partes) == 3 and partes[0] == "bots"):
            return self._responder(404, {"erro": "rota inexistente"})
        chave, acao = partes[1], partes[2]
        if chave not in BOTS or acao not in ACOES:
            return self._responder(404, {"erro": "bot ou acao desconhecida"})
        quem = (self.headers.get("X-Controle-Usuario") or "?")[:80]
        try:
            ok, msg = executar(chave, acao)
        except Exception as e:  # noqa
            ok, msg = False, f"falha ao falar com o Docker: {e}"
        # Fica no `docker logs disbot_controle`: quem desligou o que, e quando.
        _log(f"{'OK' if ok else 'FALHOU'} {acao} {chave} por {quem} -- {msg}")
        return self._responder(200 if ok else 502, {"ok": ok, "mensagem": msg})


def main():
    if len(TOKEN) < 32:
        sys.exit("CONTROLE_TOKEN ausente ou curto demais (minimo 32 caracteres). "
                 "Gere com: openssl rand -hex 32")
    if not os.path.exists(SOCKET):
        sys.exit(f"Socket do Docker nao encontrado em {SOCKET} (volume nao montado?)")
    _log(f"Porteiro dos bots ouvindo na porta {PORTA}; bots: {', '.join(BOTS)}")
    ThreadingHTTPServer(("0.0.0.0", PORTA), Porteiro).serve_forever()


if __name__ == "__main__":
    main()
