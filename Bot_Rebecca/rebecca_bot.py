import discord
from discord.ext import tasks, commands
import imaplib
import email
from email.header import decode_header
import re
import os
from datetime import datetime
from dotenv import load_dotenv
from config import get_logger
import sys
import atexit
from pathlib import Path

load_dotenv()
logger = get_logger()

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASS = os.getenv("GMAIL_PASS")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

# === CONFIGURAÇÃO DE LOCKFILE ===
BOT_DIR = Path(__file__).parent.resolve()
LOCKFILE_PATH = BOT_DIR / "bot_rebecca.lock"

def criar_lockfile():
    """Cria o arquivo de lock com o PID do processo."""
    try:
        if LOCKFILE_PATH.exists():
            # Verifica se o processo ainda está rodando
            with open(LOCKFILE_PATH, 'r') as f:
                old_pid = int(f.read().strip())

            # Tenta verificar se o processo existe (funciona no Windows e Linux)
            try:
                if sys.platform == "win32":
                    import psutil
                    if psutil.pid_exists(old_pid):
                        logger.error(f"Bot já está rodando (PID: {old_pid}). Encerrando...")
                        print(f"ERRO: Bot_Rebecca já está em execução (PID: {old_pid})")
                        sys.exit(1)
                else:
                    os.kill(old_pid, 0)  # Não mata o processo, apenas verifica
                    logger.error(f"Bot já está rodando (PID: {old_pid}). Encerrando...")
                    print(f"ERRO: Bot_Rebecca já está em execução (PID: {old_pid})")
                    sys.exit(1)
            except (ProcessLookupError, OSError, ImportError):
                # Processo não existe mais, pode remover o lockfile antigo
                logger.warning(f"Lockfile antigo encontrado (PID: {old_pid}), mas processo não existe. Removendo...")
                LOCKFILE_PATH.unlink()

        # Cria novo lockfile com o PID atual
        with open(LOCKFILE_PATH, 'w') as f:
            f.write(str(os.getpid()))

        logger.info(f"Lockfile criado com sucesso (PID: {os.getpid()})")

        # Registra função para remover lockfile ao encerrar
        atexit.register(remover_lockfile)

    except Exception as e:
        logger.error(f"Erro ao criar lockfile: {e}")
        sys.exit(1)

def remover_lockfile():
    """Remove o arquivo de lock ao encerrar o bot."""
    try:
        if LOCKFILE_PATH.exists():
            LOCKFILE_PATH.unlink()
            logger.info("Lockfile removido com sucesso")
    except Exception as e:
        logger.error(f"Erro ao remover lockfile: {e}")

bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())


# ------------------------------------------
# FUNÇÃO PARA DECODIFICAR TEXTOS DE E-MAIL
# ------------------------------------------
def decode(string):
    try:
        text, enc = decode_header(string)[0]
        if isinstance(text, bytes):
            return text.decode(enc or "utf-8", errors="ignore")
        return text
    except:
        return string


# ------------------------------------------
# FUNÇÃO PARA FORMATAR DATA NO PADRÃO BRASILEIRO
# ------------------------------------------
def format_date_br(date_string):
    """
    Garante que a data esteja no formato brasileiro DD/MM/YYYY HH:MM:SS
    Aceita diversos formatos de entrada e converte para o padrão BR
    """
    try:
        # Remove espaços extras
        date_string = date_string.strip()

        # Tenta detectar e converter diferentes formatos
        # Formato: YYYY-MM-DD HH:MM:SS ou YYYY/MM/DD HH:MM:SS (padrão americano)
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S', '%m/%d/%Y %H:%M:%S']:
            try:
                dt = datetime.strptime(date_string, fmt)
                return dt.strftime('%d/%m/%Y %H:%M:%S')
            except ValueError:
                continue

        # Se já estiver no formato DD/MM/YYYY HH:MM:SS, retorna como está
        if re.match(r'\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}', date_string):
            return date_string

        # Se não conseguiu converter, retorna o original
        return date_string
    except Exception as e:
        logger.warning(f"Erro ao formatar data '{date_string}': {e}")
        return date_string


# ------------------------------------------
# FUNÇÃO PARA EXTRAIR TODAS AS NOTIFICAÇÕES DO E-MAIL
# ------------------------------------------
def extract_all_notifications(body):
    """
    Extrai TODAS as notificações encontradas no corpo do e-mail HTML.
    Retorna uma lista de dicionários com os dados de cada notificação.
    
    Formato esperado no HTML:
    <h4>CNPJ: XX.XXX.XXX/XXXX-XX | Cliente: NOME<br><br>
    <table>
        <tr><td><b>Data e Hora envio: </b>DD/MM/YYYY HH:MM:SS</td></tr>
        <tr><td><b>Tipo de Receita: </b>XXX</td></tr>
        ...
    </table>
    """
    
    notifications = []
    
    # Primeiro, encontra todos os blocos que começam com CNPJ dentro de <h4>
    # Padrão: <h4>CNPJ: ... | Cliente: ...<br>
    cnpj_pattern = r'<h4>CNPJ:\s*([\d./-]+)\s*\|\s*Cliente:\s*([^<]+)'
    cnpj_matches = list(re.finditer(cnpj_pattern, body))
    
    for i, cnpj_match in enumerate(cnpj_matches):
        cnpj = cnpj_match.group(1).strip()
        cliente = cnpj_match.group(2).strip()
        
        # Posição onde termina o CNPJ/Cliente
        start_pos = cnpj_match.end()
        
        # Posição onde começa o próximo CNPJ (ou fim do texto)
        end_pos = cnpj_matches[i + 1].start() if i + 1 < len(cnpj_matches) else len(body)
        
        # Extrai o bloco de texto entre este CNPJ e o próximo
        block = body[start_pos:end_pos]
        
        # Agora procura por cada tabela dentro deste bloco
        # Cada tabela representa uma notificação
        table_pattern = r'<table>.*?</table>'
        table_matches = re.finditer(table_pattern, block, re.DOTALL)
        
        for table_match in table_matches:
            table_html = table_match.group(0)
            
            # Extrai os dados de cada campo da tabela
            data_hora_match = re.search(r'<b>Data e Hora envio:\s*</b>([^<]+)', table_html)
            tipo_receita_match = re.search(r'<b>Tipo de Receita:\s*</b>([^<]+)', table_html)
            categoria_match = re.search(r'<b>Categoria:\s*</b>([^<]+)', table_html)
            tipo_mensagem_match = re.search(r'<b>Tipo de Mensagem:\s*</b>([^<]+)', table_html)
            assunto_match = re.search(r'<b>Assunto:\s*</b>([^<]+)', table_html)
            
            # Verifica se todos os campos foram encontrados
            if all([data_hora_match, tipo_receita_match, categoria_match,
                    tipo_mensagem_match, assunto_match]):

                # Formata a data para o padrão brasileiro
                data_hora_original = data_hora_match.group(1).strip()
                data_hora_formatada = format_date_br(data_hora_original)

                notification = {
                    'cnpj': cnpj,
                    'cliente': cliente,
                    'data_hora': data_hora_formatada,
                    'tipo_receita': tipo_receita_match.group(1).strip(),
                    'categoria': categoria_match.group(1).strip(),
                    'tipo_mensagem': tipo_mensagem_match.group(1).strip(),
                    'assunto_notificacao': assunto_match.group(1).strip()
                }
                notifications.append(notification)
    
    return notifications

# ------------------------------------------
# FUNÇÃO PARA LER OS E-MAILS DA PASTA DEC
# ------------------------------------------
def check_emails():
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_PASS)
        logger.info("Conectado ao Gmail com sucesso")

        # Seleciona a pasta DEC
        mail.select("DEC")
        logger.info("Pasta 'DEC' selecionada")

        # Busca apenas emails não lidos
        result, data = mail.search(None, "UNSEEN")
        email_ids = data[0].split()
        
        logger.info(f"Total de e-mails não lidos na pasta DEC: {len(email_ids)}")

        all_notifications = []

        for idx, eid in enumerate(email_ids, 1):
            res, msg = mail.fetch(eid, "(RFC822)")
            for response in msg:
                if isinstance(response, tuple):
                    msg_email = email.message_from_bytes(response[1])
                    subject = decode(msg_email["Subject"])
                    sender = msg_email["From"]
                    
                    logger.debug(f"[{idx}] De: {sender} | Assunto: {subject}")

                    # Conteúdo do email
                    body = ""
                    if msg_email.is_multipart():
                        for part in msg_email.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                break
                    else:
                        body = msg_email.get_payload(decode=True).decode("utf-8", errors="ignore")

                    # Verifica se é um e-mail DEC-SEFAZ
                    if "Aviso de mensagens - Consulta DEC-SEFAZ/RJ" in subject:
                        logger.info(f">> Email DEC-SEFAZ encontrado! Processando...")

                        # Extrai TODAS as notificações do corpo do e-mail
                        notifications = extract_all_notifications(body)

                        if notifications:
                            logger.info(f">> Encontradas {len(notifications)} notificacao(es) no e-mail")
                            for notif in notifications:
                                logger.info(f"   -> Cliente: {notif['cliente']} | CNPJ: {notif['cnpj']}")
                                logger.info(f"      Categoria: {notif['categoria']} | Tipo: {notif['tipo_mensagem']}")
                                all_notifications.append(notif)
                        else:
                            logger.warning(f">> E-mail DEC-SEFAZ nao contem notificacoes no padrao esperado")
                    else:
                        logger.debug(f"E-mail descartado - assunto não corresponde")

        mail.logout()
        logger.info(f"Total de notificações para enviar ao Discord: {len(all_notifications)}")
        return all_notifications
    
    except Exception as e:
        logger.error(f"Erro ao verificar e-mails: {str(e)}")
        return []


# ------------------------------------------
# TAREFA AUTOMÁTICA DE CHECAR GMAIL
# ------------------------------------------
@tasks.loop(seconds=60)
async def email_monitor():
    try:
        channel = bot.get_channel(CHANNEL_ID)
        if channel is None:
            logger.error(f"Canal Discord com ID {CHANNEL_ID} não encontrado")
            return
        
        notifications = check_emails()

        logger.info(f">> Total de notificacoes coletadas: {len(notifications)}")

        # Envia mensagem separadora com data e hora se houver notificações
        if notifications:
            agora = datetime.now().strftime('%d/%m/%Y - %H:%M:%S')
            await channel.send(f"**📬 Notificações DEC [{agora}]**")
            logger.info(f">> Mensagem separadora enviada: Notificações DEC [{agora}]")

        enviadas = 0
        ignoradas = 0

        for info in notifications:
            # Filtra apenas notificações com Categoria: NOTIFICAÇÃO e Tipo de Mensagem: CADASTRO
            if info['categoria'].upper() != "NOTIFICAÇÃO" or info['tipo_mensagem'].upper() != "CADASTRO":
                logger.info(f">> Notificacao IGNORADA - Categoria: {info['categoria']} | Tipo: {info['tipo_mensagem']}")
                ignoradas += 1
                continue

            logger.info(f">> Enviando notificacao para Discord - Cliente: {info['cliente']}")

            embed = discord.Embed(
                title="🚨 Nova Notificação SEFAZ/RJ",
                description="Rebecca identificou uma nova notificação fiscal.",
                color=discord.Color.red(),
            )

            # Adiciona informações estruturadas (menos compacto)
            embed.add_field(name="🏢 Cliente", value=info['cliente'], inline=False)
            embed.add_field(name="📋 CNPJ", value=info['cnpj'], inline=False)
            embed.add_field(name="📅 Data e Hora", value=info['data_hora'], inline=False)
            embed.add_field(name="💰 Tipo de Receita", value=info['tipo_receita'], inline=False)
            embed.add_field(name="⚠️ Categoria", value=info['categoria'], inline=False)
            embed.add_field(name="📝 Tipo de Mensagem", value=info['tipo_mensagem'], inline=False)
            embed.add_field(name="📌 Assunto da Notificação", value=info['assunto_notificacao'], inline=False)

            await channel.send("@everyone", embed=embed)
            logger.info(f">> Mensagem enviada com sucesso! | Cliente: {info['cliente']}")
            enviadas += 1

        if enviadas > 0 or ignoradas > 0:
            logger.info(f">> Resumo: {enviadas} enviada(s), {ignoradas} ignorada(s)")
    
    except Exception as e:
        logger.error(f"Erro na tarefa de monitoramento: {str(e)}")


@bot.event
async def on_ready():
    logger.info("=" * 50)
    logger.info("Rebecca está online!")
    logger.info(f"Bot conectado como: {bot.user}")
    logger.info(f"Canal Discord: {CHANNEL_ID}")
    logger.info("=" * 50)
    email_monitor.start()


# === INICIALIZAÇÃO DO BOT ===
if __name__ == "__main__":
    # Cria lockfile para evitar múltiplas instâncias
    criar_lockfile()

    try:
        bot.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot encerrado pelo usuário")
    except Exception as e:
        logger.error(f"Erro fatal ao executar o bot: {e}")
    finally:
        remover_lockfile()