"""
Marca os e-mails ANTIGOS da pasta DEC como já processados, para que o bot
comece a trabalhar apenas a partir dos e-mails novos.

Quando usar:
- Na primeira execução após a implantação do controle "já processei"
- Depois de resetar a conta/instalação do bot

O que faz:
1. Aplica a label 'DEC-processado' nos e-mails já existentes na pasta
2. Grava os X-GM-MSGID no histórico local (emails_processados.json)

Por padrão roda em modo simulação (não altera nada). Para aplicar de verdade:

    python inicializar_processados.py --aplicar

Para manter os N e-mails mais recentes DE FORA (ou seja, o bot ainda vai
processá-los e notificar), use:

    python inicializar_processados.py --aplicar --manter-recentes 2
"""

import argparse
import email
import imaplib
import re
import sys
from email.header import decode_header

from dotenv import load_dotenv
import os

from config import get_logger

load_dotenv()
logger = get_logger()

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASS = os.getenv("GMAIL_PASS")

from rebecca_bot import (
    GMAIL_LABEL_PROCESSADO,
    PROCESSADOS_JSON_PATH,
    carregar_processados,
    salvar_processados,
)


def decode_assunto(valor):
    try:
        texto, enc = decode_header(valor or "")[0]
        if isinstance(texto, bytes):
            return texto.decode(enc or "utf-8", errors="ignore")
        return texto or ""
    except Exception:
        return valor or ""


def main():
    parser = argparse.ArgumentParser(
        description="Marca e-mails antigos da pasta DEC como já processados."
    )
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="Aplica as alterações. Sem esta flag, apenas simula.",
    )
    parser.add_argument(
        "--manter-recentes",
        type=int,
        default=0,
        metavar="N",
        help="Deixa os N e-mails mais recentes DE FORA, para o bot processá-los.",
    )
    args = parser.parse_args()

    modo = "APLICANDO" if args.aplicar else "SIMULAÇÃO (nada será alterado)"
    print("=" * 72)
    print(f"Inicialização do controle 'já processei' - modo: {modo}")
    print("=" * 72)

    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(GMAIL_USER, GMAIL_PASS)
    # readonly na simulação, para não haver risco de alteração acidental
    mail.select("DEC", readonly=not args.aplicar)

    # Busca os e-mails que ainda não têm a label
    res, data = mail.search(None, "X-GM-RAW", f'"-label:{GMAIL_LABEL_PROCESSADO}"')
    ids = data[0].split()
    print(f"\nE-mails sem a label '{GMAIL_LABEL_PROCESSADO}': {len(ids)}")

    if args.manter_recentes > 0:
        manter = ids[-args.manter_recentes:]
        ids = ids[: -args.manter_recentes]
        print(f"Mantendo {len(manter)} e-mail(s) recente(s) de fora (o bot vai processá-los)")

    if not ids:
        print("\nNada a marcar. O bot já está pronto para processar só os novos.")
        mail.logout()
        return 0

    print(f"Serão marcados como processados: {len(ids)} e-mail(s)\n")

    historico = carregar_processados()
    novos = []

    for eid in ids:
        res, msg = mail.fetch(eid, "(X-GM-MSGID BODY.PEEK[HEADER.FIELDS (DATE SUBJECT)])")
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
        assunto = decode_assunto(me["Subject"])[:52]
        print(f"  ID {eid.decode():>4} | {me['Date']} | {assunto}")

        if msgid:
            novos.append(msgid)

        if args.aplicar:
            mail.store(eid, "+X-GM-LABELS", GMAIL_LABEL_PROCESSADO)
            mail.store(eid, "+FLAGS", "\\Seen")

    if args.aplicar:
        historico.update(novos)
        salvar_processados(historico)
        mail.logout()
        print(f"\n{'=' * 72}")
        print(f"CONCLUÍDO: {len(ids)} e-mail(s) marcado(s) com a label.")
        print(f"Histórico local: {len(historico)} ID(s) em {PROCESSADOS_JSON_PATH.name}")
        print("O bot agora processará apenas os e-mails novos.")
    else:
        mail.logout()
        print(f"\n{'=' * 72}")
        print("SIMULAÇÃO - nada foi alterado.")
        print("Para aplicar de verdade, rode novamente com --aplicar")

    return 0


if __name__ == "__main__":
    sys.exit(main())
