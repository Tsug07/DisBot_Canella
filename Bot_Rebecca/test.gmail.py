import imaplib
from dotenv import load_dotenv
import os

load_dotenv()

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASS = os.getenv("GMAIL_PASS")

print(f"Testando login com: {GMAIL_USER}")
print(f"Senha carregada: {'Sim' if GMAIL_PASS else 'Não'}")

try:
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(GMAIL_USER, GMAIL_PASS)
    print("✅ Login bem-sucedido!")
    mail.logout()
except Exception as e:
    print(f"❌ Erro: {e}")