# -*- coding: utf-8 -*-
"""
ler_2fa_gmail.py
----------------
Lê o código de autenticação de dois fatores (2FA) do Onvio/Thomson Reuters
diretamente da caixa do Gmail, via IMAP.

E-mail do 2FA (formato observado):
  Remetente: Thomson Reuters <access.info@thomsonreuters.com>
  Assunto:   "Seu código de autenticação de dois fatores"
  Corpo:     "... seu código de autenticação de dois fatores para Onvio:\n263091\n..."
  (código = 6 dígitos)

Configuração (no .env da VM):
  GESTTA_GMAIL_USER          -> a conta Gmail que recebe o código
                                (ex.: hugoalmeida.canellaesantos@gmail.com)
  GESTTA_GMAIL_APP_PASSWORD  -> "senha de app" gerada no Google (NÃO a senha normal)
  GESTTA_GMAIL_IMAP_HOST     -> opcional (padrão imap.gmail.com)

Pré-requisitos no Google:
  - IMAP habilitado (Gmail -> Configurações -> Encaminhamento e POP/IMAP).
  - Verificação em duas etapas ativa na conta Google e uma "senha de app" gerada.
"""

import os
import re
import ssl
import time
import email
import imaplib
import logging
from email.header import decode_header

logger = logging.getLogger("ler_2fa_gmail")

IMAP_HOST = os.environ.get("GESTTA_GMAIL_IMAP_HOST", "imap.gmail.com")
REMETENTE_2FA = "access.info@thomsonreuters.com"
ASSUNTO_HINT = "autentica"          # casa "autenticação de dois fatores"
CODIGO_RE = re.compile(r"\b(\d{6})\b")


def _decode(s):
    if not s:
        return ""
    partes = decode_header(s)
    out = ""
    for texto, enc in partes:
        if isinstance(texto, bytes):
            out += texto.decode(enc or "utf-8", errors="ignore")
        else:
            out += texto
    return out


def _corpo_texto(msg):
    """Extrai o texto do e-mail (prefere text/plain, cai para text/html)."""
    if msg.is_multipart():
        # tenta text/plain primeiro
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="ignore")
                except Exception:
                    pass
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                try:
                    html = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="ignore")
                    return re.sub(r"<[^>]+>", " ", html)
                except Exception:
                    pass
        return ""
    try:
        return msg.get_payload(decode=True).decode(
            msg.get_content_charset() or "utf-8", errors="ignore")
    except Exception:
        return str(msg.get_payload())


def _extrair_codigo(corpo):
    """Pega o código de 6 dígitos, de preferência logo após 'Onvio:'."""
    m = re.search(r"Onvio:?\s*([\s\S]{0,40})", corpo, re.IGNORECASE)
    if m:
        c = CODIGO_RE.search(m.group(1))
        if c:
            return c.group(1)
    c = CODIGO_RE.search(corpo)
    return c.group(1) if c else None


def obter_codigo_2fa(usuario=None, senha_app=None, desde_epoch=None,
                     timeout=120, intervalo=5):
    """
    Aguarda e devolve o código 2FA mais recente recebido do Thomson Reuters.

    - desde_epoch: só considera e-mails recebidos DEPOIS deste timestamp (evita
      pegar um código antigo). Passe time.time() logo antes de disparar o login.
    - timeout/intervalo: quanto tempo esperar o e-mail chegar (segundos).
    """
    usuario = usuario or os.environ.get("GESTTA_GMAIL_USER")
    senha_app = senha_app or os.environ.get("GESTTA_GMAIL_APP_PASSWORD")
    if not usuario or not senha_app:
        raise RuntimeError("Defina GESTTA_GMAIL_USER e GESTTA_GMAIL_APP_PASSWORD no .env.")

    fim = time.time() + timeout
    while time.time() < fim:
        try:
            M = imaplib.IMAP4_SSL(IMAP_HOST, ssl_context=ssl.create_default_context())
            M.login(usuario, senha_app)
            try:
                M.select("INBOX")
                # busca e-mails do remetente do 2FA (mais recentes por último)
                typ, dados = M.search(None, 'FROM', REMETENTE_2FA)
                ids = dados[0].split() if dados and dados[0] else []
                for msg_id in reversed(ids[-10:]):  # olha os 10 mais recentes
                    typ, raw = M.fetch(msg_id, "(RFC822)")
                    if typ != "OK" or not raw or not raw[0]:
                        continue
                    msg = email.message_from_bytes(raw[0][1])
                    assunto = _decode(msg.get("Subject", ""))
                    if ASSUNTO_HINT.lower() not in assunto.lower():
                        continue
                    # filtra por data (só e-mails após o início do login)
                    if desde_epoch:
                        data_msg = email.utils.parsedate_to_datetime(msg.get("Date"))
                        if data_msg and data_msg.timestamp() < desde_epoch - 60:
                            continue
                    codigo = _extrair_codigo(_corpo_texto(msg))
                    if codigo:
                        logger.info("Código 2FA obtido do Gmail.")
                        return codigo
            finally:
                try:
                    M.logout()
                except Exception:
                    pass
        except Exception as e:  # noqa
            logger.warning("Tentativa de ler 2FA falhou: %s", e)
        time.sleep(intervalo)

    raise RuntimeError("Não chegou nenhum e-mail de 2FA do Thomson Reuters no tempo esperado.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Teste: lê o código mais recente já presente na caixa (sem filtro de data).
    print("Código 2FA mais recente:", obter_codigo_2fa(timeout=15, intervalo=3))
