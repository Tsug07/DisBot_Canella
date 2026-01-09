import discord
from discord.ext import tasks, commands
import imaplib
import email
from email.header import decode_header
import re
import os
import json
import requests
import csv
from io import StringIO
from datetime import datetime
from difflib import SequenceMatcher
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

# === CONFIGURAÇÃO DO GOOGLE SHEETS ===
# Planilha pública - exporta como CSV
SHEET_ID = "1PAE1LgiEOWJs1emuR5Unt9e-CUWVFjaNtymCUqS-cV4"
SHEET_GID = "0"  # gid da aba "12.2025"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}"

# === CONFIGURAÇÃO DO MAPEAMENTO DE RESPONSÁVEIS ===
RESPONSAVEIS_JSON_PATH = BOT_DIR / "responsaveis_discord.json"

# ID do cargo Legalização no Discord
LEGALIZACAO_ROLE_ID = "1299045050881151006"

# ID da Fabiana (responsável geral - fallback quando não encontra responsável)
FABIANA_USER_ID = "1285344147292684359"

# ID do Hugo (para receber relatório de empresas sem responsável)
HUGO_USER_ID = "1285316758009544844"

# Cache dos dados da planilha (empresa -> {responsavel, situacao})
empresa_responsavel_cache = {}
# Cache do mapeamento (responsável -> discord_id)
responsavel_discord_cache = {}

# Status negativos que bloqueiam notificação (exceto SUSPENSA/SUSPENSO)
# Valores reais da planilha: BAIXA, DEVOLVIDA, INATIVA
STATUS_NEGATIVOS = ["BAIXA", "DEVOLVIDA", "INATIVA"]

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


# ------------------------------------------
# FUNÇÕES PARA CARREGAR PLANILHA E MAPEAMENTO
# ------------------------------------------
def carregar_mapeamento_discord():
    """Carrega o mapeamento de responsáveis para IDs do Discord do arquivo JSON."""
    global responsavel_discord_cache
    try:
        if RESPONSAVEIS_JSON_PATH.exists():
            with open(RESPONSAVEIS_JSON_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                responsavel_discord_cache = data.get("responsaveis", {})
                logger.info(f"Mapeamento Discord carregado: {len(responsavel_discord_cache)} responsáveis")
        else:
            logger.warning(f"Arquivo de mapeamento não encontrado: {RESPONSAVEIS_JSON_PATH}")
            responsavel_discord_cache = {}
    except Exception as e:
        logger.error(f"Erro ao carregar mapeamento Discord: {e}")
        responsavel_discord_cache = {}


def carregar_planilha_empresas():
    """Baixa a planilha do Google Sheets e extrai empresa -> {responsavel, situacao}."""
    global empresa_responsavel_cache
    try:
        logger.info("Baixando planilha do Google Sheets...")
        response = requests.get(SHEET_URL, timeout=30)
        response.raise_for_status()

        # Decodifica o CSV
        content = response.content.decode('utf-8')
        reader = csv.reader(StringIO(content))

        empresa_responsavel_cache = {}
        for idx, row in enumerate(reader):
            # Pula cabeçalho (primeira linha)
            if idx == 0:
                continue

            # Coluna B (índice 1) = Nome da empresa
            # Coluna C (índice 2) = Situação da empresa
            # Coluna E (índice 4) = Responsável
            if len(row) >= 5:
                empresa = row[1].strip().upper() if row[1] else ""
                situacao = row[2].strip().upper() if len(row) > 2 and row[2] else ""
                responsavel = row[4].strip() if row[4] else ""

                # Ignora filiais (variações: FILIAL, FIL., FILIAL 1, etc.)
                if re.search(r'\bFILIAL\b|\bFIL\.\b|\bFIL\b', empresa, re.IGNORECASE):
                    continue

                # Carrega todas as empresas (mesmo sem responsável) para verificar status
                if empresa:
                    empresa_responsavel_cache[empresa] = {
                        'responsavel': responsavel,  # Pode ser vazio
                        'situacao': situacao
                    }

        logger.info(f"Planilha carregada: {len(empresa_responsavel_cache)} empresas mapeadas")

    except requests.RequestException as e:
        logger.error(f"Erro ao baixar planilha: {e}")
    except Exception as e:
        logger.error(f"Erro ao processar planilha: {e}")


def calcular_similaridade(texto1: str, texto2: str) -> float:
    """Calcula a similaridade entre dois textos (0.0 a 1.0)."""
    return SequenceMatcher(None, texto1, texto2).ratio()


def verificar_situacao_empresa(nome_cliente: str, threshold: float = 0.80) -> tuple[bool, str | None]:
    """
    Verifica se uma empresa deve ser notificada com base na situação.

    Args:
        nome_cliente: Nome do cliente do email
        threshold: Similaridade mínima para considerar match (padrão 80%)

    Retorna uma tupla (deve_notificar, situacao):
        - deve_notificar: True se deve notificar, False se deve ignorar
        - situacao: Status da empresa na planilha ou None se não encontrada
    """
    nome_normalizado = nome_cliente.strip().upper()

    # Tenta match exato
    dados_empresa = empresa_responsavel_cache.get(nome_normalizado)

    # Se não encontrou, busca por similaridade
    if not dados_empresa:
        for empresa_planilha in empresa_responsavel_cache.keys():
            score = calcular_similaridade(nome_normalizado, empresa_planilha)
            if score >= threshold:
                dados_empresa = empresa_responsavel_cache[empresa_planilha]
                break

    if not dados_empresa:
        # Empresa não encontrada na planilha - deve notificar (fallback para Fabiana)
        return True, None

    situacao = dados_empresa.get('situacao', '')

    # Status negativos bloqueiam notificação, EXCETO SUSPENSA/SUSPENSO
    if situacao in STATUS_NEGATIVOS:
        return False, situacao

    return True, situacao


def buscar_responsavel_empresa(nome_cliente: str, threshold: float = 0.80) -> str | None:
    """
    Busca o responsável de uma empresa pelo nome.
    Usa busca por similaridade se não encontrar match exato.

    Args:
        nome_cliente: Nome do cliente do email
        threshold: Similaridade mínima para considerar match (padrão 80%)

    Retorna o ID do Discord do responsável ou None se não encontrar.
    """
    # Normaliza o nome para busca
    nome_normalizado = nome_cliente.strip().upper()

    # 1. Primeiro tenta match exato
    dados_empresa = empresa_responsavel_cache.get(nome_normalizado)

    # 2. Se não encontrou, busca por similaridade
    if not dados_empresa:
        melhor_match = None
        melhor_score = 0.0

        for empresa_planilha in empresa_responsavel_cache.keys():
            score = calcular_similaridade(nome_normalizado, empresa_planilha)
            if score > melhor_score and score >= threshold:
                melhor_score = score
                melhor_match = empresa_planilha

        if melhor_match:
            dados_empresa = empresa_responsavel_cache[melhor_match]
            logger.info(f"Match por similaridade ({melhor_score:.0%}): '{nome_cliente}' -> '{melhor_match}'")
        else:
            logger.debug(f"Empresa não encontrada na planilha: {nome_cliente}")
            return None

    # Extrai responsável dos dados da empresa
    responsavel = dados_empresa.get('responsavel', '')

    # Busca o ID do Discord do responsável
    discord_id = responsavel_discord_cache.get(responsavel)

    if not discord_id:
        logger.debug(f"Responsável '{responsavel}' não tem ID Discord mapeado")
        return None

    logger.debug(f"Empresa '{nome_cliente}' -> Responsável '{responsavel}' -> Discord ID '{discord_id}'")
    return discord_id


def atualizar_caches():
    """Recarrega os caches da planilha e mapeamento."""
    carregar_mapeamento_discord()
    carregar_planilha_empresas()


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
# FUNÇÃO PARA EXTRAIR NOTIFICAÇÕES NÃO LIDAS DO E-MAIL
# ------------------------------------------
def extract_all_notifications(body):
    """
    Extrai apenas as notificações NÃO LIDAS encontradas no corpo do e-mail HTML.
    Retorna uma lista de dicionários com os dados de cada notificação.

    O email contém duas seções:
    - "Mensagens não lidas dos últimos 90 dias:" (queremos estas)
    - "Mensagens lidas dos últimos 90 dias:" (ignoramos estas)

    As seções são separadas por uma linha de asteriscos.
    """

    notifications = []

    # Extrai apenas a seção de mensagens NÃO LIDAS
    # Procura o conteúdo entre "Mensagens não lidas" e o separador de asteriscos
    unread_section_match = re.search(
        r'Mensagens não lidas dos últimos 90 dias:</h3>(.*?)(?:\*{10,}|Mensagens lidas dos últimos 90 dias:)',
        body,
        re.DOTALL
    )

    if not unread_section_match:
        logger.warning("Seção de mensagens não lidas não encontrada no email")
        return notifications

    # Trabalha apenas com a seção de não lidas
    unread_body = unread_section_match.group(1)
    logger.info(f"Seção de mensagens não lidas extraída ({len(unread_body)} caracteres)")

    # Encontra todos os blocos que começam com CNPJ dentro de <h4>
    cnpj_pattern = r'<h4>CNPJ:\s*([\d./-]+)\s*\|\s*Cliente:\s*([^<]+)'
    cnpj_matches = list(re.finditer(cnpj_pattern, unread_body))
    
    for i, cnpj_match in enumerate(cnpj_matches):
        cnpj = cnpj_match.group(1).strip()
        cliente = cnpj_match.group(2).strip()
        
        # Posição onde termina o CNPJ/Cliente
        start_pos = cnpj_match.end()

        # Posição onde começa o próximo CNPJ (ou fim do texto)
        end_pos = cnpj_matches[i + 1].start() if i + 1 < len(cnpj_matches) else len(unread_body)
        
        # Extrai o bloco de texto entre este CNPJ e o próximo
        block = unread_body[start_pos:end_pos]
        
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

                    # Conteúdo do email (prioriza HTML para extrair as seções corretamente)
                    body = ""
                    if msg_email.is_multipart():
                        for part in msg_email.walk():
                            content_type = part.get_content_type()
                            # Prioriza HTML pois contém as seções "não lidas" e "lidas"
                            if content_type == "text/html":
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                break
                            elif content_type == "text/plain" and not body:
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
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

        if not notifications:
            return

        # Agrupa notificações por CNPJ (empresa)
        empresas_agrupadas = {}
        for notif in notifications:
            cnpj = notif['cnpj']
            if cnpj not in empresas_agrupadas:
                empresas_agrupadas[cnpj] = {
                    'cliente': notif['cliente'],
                    'cnpj': cnpj,
                    'notificacoes': []
                }
            empresas_agrupadas[cnpj]['notificacoes'].append(notif)

        logger.info(f">> Agrupado em {len(empresas_agrupadas)} empresa(s)")

        # Envia mensagem separadora com data e hora
        agora = datetime.now().strftime('%d/%m/%Y - %H:%M:%S')
        await channel.send(f"**📬 Notificações DEC [{agora}]**")
        logger.info(f">> Mensagem separadora enviada: Notificações DEC [{agora}]")

        enviadas = 0
        empresas_sem_responsavel = []

        empresas_ignoradas = []

        for cnpj, dados in empresas_agrupadas.items():
            cliente = dados['cliente']
            notifs = dados['notificacoes']

            logger.info(f">> Processando empresa: {cliente} ({len(notifs)} notificação(ões))")

            # Verifica se a empresa tem status negativo (exceto SUSPENSA/SUSPENSO)
            deve_notificar, situacao = verificar_situacao_empresa(cliente)
            if not deve_notificar:
                logger.info(f">> Empresa '{cliente}' ignorada - situação: {situacao}")
                empresas_ignoradas.append((cliente, situacao))
                continue

            # Verifica se alguma notificação é NOTIFICAÇÃO + CADASTRO
            tem_notificacao_cadastro = any(
                n['categoria'].upper() == "NOTIFICAÇÃO" and n['tipo_mensagem'].upper() == "CADASTRO"
                for n in notifs
            )

            # Cria o embed principal
            embed = discord.Embed(
                title="🚨 Notificações SEFAZ/RJ",
                description=f"Rebecca identificou **{len(notifs)}** notificação(ões) fiscal(is).",
                color=discord.Color.red(),
            )

            # Informações da empresa
            embed.add_field(name="🏢 Cliente", value=cliente, inline=False)
            embed.add_field(name="📋 CNPJ", value=cnpj, inline=False)

            # Lista cada notificação
            for idx, n in enumerate(notifs, 1):
                # Formata os detalhes da notificação
                detalhes = (
                    f"📅 {n['data_hora']}\n"
                    f"💰 {n['tipo_receita']} | ⚠️ {n['categoria']} | 📝 {n['tipo_mensagem']}\n"
                    f"📌 {n['assunto_notificacao']}"
                )
                embed.add_field(
                    name=f"Notificação {idx}",
                    value=detalhes,
                    inline=False
                )

            # Busca o responsável pela empresa
            discord_id = buscar_responsavel_empresa(cliente)

            # Monta a menção
            if tem_notificacao_cadastro:
                # Tem NOTIFICAÇÃO + CADASTRO = @Legalização + Responsável
                if discord_id:
                    mencao = f"<@&{LEGALIZACAO_ROLE_ID}> <@{discord_id}>"
                    logger.info(f">> Notificação CADASTRO -> mencionando @Legalização + Responsável")
                else:
                    mencao = f"<@&{LEGALIZACAO_ROLE_ID}> <@{FABIANA_USER_ID}>"
                    logger.info(f">> Notificação CADASTRO -> mencionando @Legalização + Fabiana")
                    empresas_sem_responsavel.append(cliente)
            else:
                # Só outras categorias = só o responsável
                if discord_id:
                    mencao = f"<@{discord_id}>"
                    logger.info(f">> Responsável encontrado -> mencionando ID {discord_id}")
                else:
                    mencao = f"<@{FABIANA_USER_ID}>"
                    logger.info(f">> Responsável não encontrado -> mencionando Fabiana")
                    empresas_sem_responsavel.append(cliente)

            await channel.send(mencao, embed=embed)
            logger.info(f">> Mensagem enviada com sucesso! | Cliente: {cliente}")
            enviadas += 1

        # Envia relatório de empresas sem responsável (se houver)
        if empresas_sem_responsavel:
            empresas_unicas = list(dict.fromkeys(empresas_sem_responsavel))

            relatorio = f"<@{HUGO_USER_ID}> **📋 Relatório - Empresas sem responsável mapeado:**\n\n"
            for idx, empresa in enumerate(empresas_unicas, 1):
                relatorio += f"{idx}. {empresa}\n"

            relatorio += f"\n*Total: {len(empresas_unicas)} empresa(s)*"

            await channel.send(relatorio)
            logger.info(f">> Relatório enviado: {len(empresas_unicas)} empresa(s) sem responsável")

        if enviadas > 0:
            logger.info(f">> Resumo: {enviadas} empresa(s) notificada(s)")
        else:
            # Nenhuma notificação enviada - envia mensagem de parabéns
            await channel.send("🎉 **Parabéns!** Nenhuma notificação pendente no momento. Tudo em dia!")
            logger.info(">> Nenhuma notificação pendente - mensagem de parabéns enviada")

        if empresas_ignoradas:
            logger.info(f">> Empresas ignoradas por status negativo: {len(empresas_ignoradas)}")
            for empresa, status in empresas_ignoradas:
                logger.info(f"   -> {empresa}: {status}")

    except Exception as e:
        logger.error(f"Erro na tarefa de monitoramento: {str(e)}")


# ------------------------------------------
# TAREFA PARA ATUALIZAR CACHE DA PLANILHA (DIÁRIA)
# ------------------------------------------
@tasks.loop(hours=24)
async def atualizar_cache_planilha():
    """Atualiza o cache da planilha uma vez por dia."""
    logger.info("Atualizando cache da planilha (tarefa diária)...")
    atualizar_caches()
    logger.info("Cache da planilha atualizado com sucesso")


@bot.event
async def on_ready():
    logger.info("=" * 50)
    logger.info("Rebecca está online!")
    logger.info(f"Bot conectado como: {bot.user}")
    logger.info(f"Canal Discord: {CHANNEL_ID}")
    logger.info("=" * 50)

    # Carrega os caches de empresas e responsáveis
    atualizar_caches()

    # Inicia as tarefas
    email_monitor.start()
    atualizar_cache_planilha.start()


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