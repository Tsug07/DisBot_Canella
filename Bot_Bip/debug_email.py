"""
Script de debug para visualizar o conteúdo dos emails da pasta ECAC.
Salva o HTML completo em arquivos para análise do formato.
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
    """Conecta ao Gmail e mostra o conteúdo dos emails na pasta ECAC."""

    print("=" * 80)
    print("DEBUG - Leitura de Emails da Pasta ECAC")
    print("=" * 80)

    try:
        # Conecta ao Gmail
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_PASS)
        print(f"Conectado como: {GMAIL_USER}")

        # Seleciona a pasta ECAC
        status, select_data = mail.select("ECAC")
        total_na_pasta = int(select_data[0].decode())
        print(f"Pasta 'ECAC' selecionada - Total: {total_na_pasta} emails")

        # Busca emails não lidos primeiro
        result, data = mail.search(None, "UNSEEN")
        email_ids = data[0].split()

        print(f"\nEmails nao lidos: {len(email_ids)}")

        # Se não houver não lidos, busca os lidos
        if not email_ids:
            print("Nenhum email nao lido. Buscando emails lidos...")
            result, data = mail.search(None, "SEEN")
            email_ids = data[0].split()
            print(f"Emails lidos encontrados: {len(email_ids)}")

            if not email_ids:
                print("\nNenhum email na pasta ECAC.")
                mail.logout()
                return

            # Pega apenas os 3 mais recentes para debug
            email_ids = email_ids[-3:]
            print(f"Analisando os {len(email_ids)} mais recentes...")

        print("=" * 80)

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

                    # Mostra o conteúdo resumido
                    print("\nCORPO DO EMAIL (TEXT/PLAIN):")
                    print("-" * 40)
                    if body_plain:
                        print(body_plain[:3000])
                        if len(body_plain) > 3000:
                            print(f"\n... [truncado - total: {len(body_plain)} caracteres]")
                    else:
                        print("[Vazio ou nao disponivel]")

                    print("\nCORPO DO EMAIL (TEXT/HTML):")
                    print("-" * 40)
                    if body_html:
                        print(body_html[:5000])
                        if len(body_html) > 5000:
                            print(f"\n... [truncado - total: {len(body_html)} caracteres]")
                    else:
                        print("[Vazio ou nao disponivel]")

                    # Salva o HTML completo em arquivo para análise
                    debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_output")
                    os.makedirs(debug_dir, exist_ok=True)
                    output_file = os.path.join(debug_dir, f"ecac_email_debug_{idx}.html")
                    with open(output_file, "w", encoding="utf-8") as f:
                        f.write(f"<!-- De: {sender} -->\n")
                        f.write(f"<!-- Data: {date} -->\n")
                        f.write(f"<!-- Assunto: {subject} -->\n\n")
                        f.write(body_html if body_html else body_plain)

                    print(f"\nHTML completo salvo em: {output_file}")

        mail.logout()
        print("\n" + "=" * 80)
        print("Debug finalizado!")
        print("Abra os arquivos .html no navegador para ver o formato completo.")
        print("=" * 80)

    except Exception as e:
        print(f"\nERRO: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    debug_emails()
