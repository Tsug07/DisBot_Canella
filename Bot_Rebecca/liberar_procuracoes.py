"""
Libera o e-mail de procurações mais recente para o bot processá-lo.

Por que existe: o script inicializar_processados.py marca TODOS os e-mails da
pasta DEC, e os avisos de procurações ficam na mesma pasta. Sem este utilitário,
o primeiro relatório de procurações nunca seria enviado ao Discord.

Uso:
    python liberar_procuracoes.py              # simula, não altera nada
    python liberar_procuracoes.py --aplicar    # libera o mais recente
"""

import argparse
import email
import imaplib
import os
import re
import sys
from email.header import decode_header

from dotenv import load_dotenv

from config import get_logger

load_dotenv()
logger = get_logger()

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASS = os.getenv("GMAIL_PASS")

from rebecca_bot import (
    ASSUNTO_PROCURACOES,
    GMAIL_LABEL_PROCESSADO,
    carregar_processados,
    salvar_processados,
)


def dec(valor):
    try:
        saida = ""
        for texto, enc in decode_header(valor or ""):
            saida += (
                texto.decode(enc or "utf-8", errors="ignore")
                if isinstance(texto, bytes)
                else str(texto)
            )
        return saida
    except Exception:
        return valor or ""


def main():
    parser = argparse.ArgumentParser(
        description="Libera o aviso de procurações mais recente para o bot processar."
    )
    parser.add_argument(
        "--aplicar", action="store_true", help="Aplica. Sem a flag, apenas simula."
    )
    parser.add_argument(
        "--quantidade",
        type=int,
        default=1,
        metavar="N",
        help="Quantos avisos recentes liberar (padrão: 1).",
    )
    args = parser.parse_args()

    print("=" * 72)
    print(f"Liberar aviso de procurações - modo: "
          f"{'APLICANDO' if args.aplicar else 'SIMULAÇÃO'}")
    print("=" * 72)

    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(GMAIL_USER, GMAIL_PASS)
    mail.select("DEC", readonly=not args.aplicar)

    res, data = mail.search(None, "ALL")
    ids = data[0].split()

    # Varre do mais recente para trás procurando os avisos de procurações
    encontrados = []
    for eid in reversed(ids):
        res, msg = mail.fetch(eid, "(X-GM-MSGID BODY.PEEK[HEADER.FIELDS (SUBJECT DATE)])")
        msgid = None
        cabecalho = b""
        for resp in msg:
            meta = resp[0] if isinstance(resp, tuple) else resp
            if meta:
                m = re.search(rb"X-GM-MSGID\s+(\d+)", meta)
                if m:
                    msgid = m.group(1).decode()
            if isinstance(resp, tuple) and resp[1]:
                cabecalho = resp[1]

        me = email.message_from_bytes(cabecalho)
        assunto = dec(me["Subject"])
        if ASSUNTO_PROCURACOES in assunto:
            encontrados.append((eid, msgid, me["Date"], assunto))
            if len(encontrados) >= args.quantidade:
                break

    if not encontrados:
        print("\nNenhum aviso de procurações encontrado na pasta DEC.")
        mail.logout()
        return 1

    print(f"\nAvisos de procurações a liberar: {len(encontrados)}\n")
    historico = carregar_processados()

    for eid, msgid, data_email, assunto in encontrados:
        print(f"  ID {eid.decode():>4} | {data_email}")
        print(f"       {assunto}")
        if args.aplicar:
            # Remove a label para o bot voltar a enxergar o e-mail
            mail.store(eid, "-X-GM-LABELS", GMAIL_LABEL_PROCESSADO)
            # E tira do histórico local, que é a segunda barreira
            historico.discard(msgid)

    if args.aplicar:
        salvar_processados(historico)
        mail.logout()
        print(f"\n{'=' * 72}")
        print(f"LIBERADO: {len(encontrados)} aviso(s).")
        print("No próximo ciclo (até 60s) o bot enviará o PDF ao @Legalização.")
    else:
        mail.logout()
        print(f"\n{'=' * 72}")
        print("SIMULAÇÃO - nada foi alterado.")
        print("Para aplicar, rode novamente com --aplicar")

    return 0


if __name__ == "__main__":
    sys.exit(main())
