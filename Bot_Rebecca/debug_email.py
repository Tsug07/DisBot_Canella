"""
Script de debug para visualizar o conteúdo dos emails da pasta DEC.
Marca um email como não lido antes de rodar, e este script mostrará o HTML completo.
"""

import imaplib
import email
from email.header import decode_header
import os
from dotenv import load_dotenv

load_dotenv()

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASS = os.getenv("GMAIL_PASS")


def decode_text(string):
    """Decodifica texto de header de email."""
    try:
        text, enc = decode_header(string)[0]
        if isinstance(text, bytes):
            return text.decode(enc or "utf-8", errors="ignore")
        return text
    except:
        return string


def debug_emails():
    """Conecta ao Gmail e mostra o conteúdo dos emails não lidos na pasta DEC."""

    print("=" * 80)
    print("DEBUG - Leitura de Emails da Pasta DEC")
    print("=" * 80)

    try:
        # Conecta ao Gmail
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_PASS)
        print(f"✓ Conectado como: {GMAIL_USER}")

        # Seleciona a pasta DEC
        mail.select("DEC")
        print("✓ Pasta 'DEC' selecionada")

        # Busca emails não lidos
        result, data = mail.search(None, "UNSEEN")
        email_ids = data[0].split()

        print(f"\n📧 Emails não lidos encontrados: {len(email_ids)}")
        print("=" * 80)

        if not email_ids:
            print("\nNenhum email não lido na pasta DEC.")
            print("Marque um email como não lido e rode novamente.")
            mail.logout()
            return

        for idx, eid in enumerate(email_ids, 1):
            # Usa PEEK para não marcar como lido
            res, msg = mail.fetch(eid, "(BODY.PEEK[])")

            for response in msg:
                if isinstance(response, tuple):
                    msg_email = email.message_from_bytes(response[1])

                    subject = decode_text(msg_email["Subject"])
                    sender = msg_email["From"]
                    date = msg_email["Date"]

                    print(f"\n{'#' * 80}")
                    print(f"EMAIL {idx}/{len(email_ids)}")
                    print(f"{'#' * 80}")
                    print(f"De: {sender}")
                    print(f"Data: {date}")
                    print(f"Assunto: {subject}")
                    print("-" * 80)

                    # Extrai o corpo do email
                    body_plain = ""
                    body_html = ""

                    if msg_email.is_multipart():
                        for part in msg_email.walk():
                            content_type = part.get_content_type()

                            if content_type == "text/plain":
                                try:
                                    body_plain = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                except:
                                    body_plain = "[Erro ao decodificar texto plano]"

                            elif content_type == "text/html":
                                try:
                                    body_html = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                except:
                                    body_html = "[Erro ao decodificar HTML]"
                    else:
                        content_type = msg_email.get_content_type()
                        try:
                            payload = msg_email.get_payload(decode=True).decode("utf-8", errors="ignore")
                            if content_type == "text/html":
                                body_html = payload
                            else:
                                body_plain = payload
                        except:
                            body_plain = "[Erro ao decodificar]"

                    # Mostra o conteúdo
                    print("\n📄 CORPO DO EMAIL (TEXT/PLAIN):")
                    print("-" * 40)
                    if body_plain:
                        print(body_plain[:5000])  # Limita a 5000 chars
                        if len(body_plain) > 5000:
                            print(f"\n... [truncado - total: {len(body_plain)} caracteres]")
                    else:
                        print("[Vazio ou não disponível]")

                    print("\n📄 CORPO DO EMAIL (TEXT/HTML):")
                    print("-" * 40)
                    if body_html:
                        print(body_html[:10000])  # Limita a 10000 chars
                        if len(body_html) > 10000:
                            print(f"\n... [truncado - total: {len(body_html)} caracteres]")
                    else:
                        print("[Vazio ou não disponível]")

                    # Salva o HTML completo em arquivo para análise
                    output_file = f"email_debug_{idx}.html"
                    with open(output_file, "w", encoding="utf-8") as f:
                        f.write(f"<!-- De: {sender} -->\n")
                        f.write(f"<!-- Data: {date} -->\n")
                        f.write(f"<!-- Assunto: {subject} -->\n\n")
                        f.write(body_html if body_html else body_plain)

                    print(f"\n💾 HTML completo salvo em: {output_file}")

        mail.logout()
        print("\n" + "=" * 80)
        print("✓ Debug finalizado!")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ ERRO: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    debug_emails()
