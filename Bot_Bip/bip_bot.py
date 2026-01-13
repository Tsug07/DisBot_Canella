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
# TODO: Configurar o CHANNEL_ID correto para o bot BIP
CHANNEL_ID_BIP = int(os.getenv("CHANNEL_ID_BIP", "0"))

# === CONFIGURAÇÃO DE LOCKFILE ===
BOT_DIR = Path(__file__).parent.resolve()
LOCKFILE_PATH = BOT_DIR / "bot_bip.lock"

# === CONFIGURAÇÃO DO GOOGLE SHEETS ===
# Planilha pública - exporta como CSV
SHEET_ID = "1PAE1LgiEOWJs1emuR5Unt9e-CUWVFjaNtymCUqS-cV4"
SHEET_GID = "0"  # gid da aba "12.2025"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}"

# === CONFIGURAÇÃO DO MAPEAMENTO DE RESPONSÁVEIS ===
RESPONSAVEIS_JSON_PATH = BOT_DIR / "responsaveis_discord.json"

# TODO: Configurar os IDs corretos para o bot BIP
# ID do cargo para mencionar (template - ajustar conforme necessário)
CARGO_ROLE_ID = "0000000000000000000"

# IDs de fallback (quando não encontra responsável na planilha)
FABIANA_USER_ID = "1285344147292684359"
LAIS_ELI_USER_ID = "1314633355727339592"  # Lais/Eli

# ID do cargo Legalização (para alertas de procuração)
LEGALIZACAO_ROLE_ID = "1299045050881151006"

# ID do Hugo (para receber relatório de empresas sem responsável)
HUGO_USER_ID = "1285316758009544844"

# Cache dos dados da planilha (empresa -> {responsavel_dp, responsavel, situacao})
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
                        print(f"ERRO: Bot_Bip já está em execução (PID: {old_pid})")
                        sys.exit(1)
                else:
                    os.kill(old_pid, 0)  # Não mata o processo, apenas verifica
                    logger.error(f"Bot já está rodando (PID: {old_pid}). Encerrando...")
                    print(f"ERRO: Bot_Bip já está em execução (PID: {old_pid})")
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
    """Baixa a planilha do Google Sheets e extrai empresa -> {responsavel_dp, responsavel, situacao}."""
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
            # Coluna D (índice 3) = Responsável DP
            # Coluna E (índice 4) = Responsável
            if len(row) >= 5:
                empresa = row[1].strip().upper() if row[1] else ""
                situacao = row[2].strip().upper() if len(row) > 2 and row[2] else ""
                responsavel_dp = row[3].strip() if len(row) > 3 and row[3] else ""
                responsavel = row[4].strip() if row[4] else ""

                # Ignora filiais (variações: FILIAL, FIL., FILIAL 1, etc.)
                if re.search(r'\bFILIAL\b|\bFIL\.\b|\bFIL\b', empresa, re.IGNORECASE):
                    continue

                # Carrega todas as empresas (mesmo sem responsável) para verificar status
                if empresa:
                    empresa_responsavel_cache[empresa] = {
                        'responsavel_dp': responsavel_dp,  # Responsável DP (coluna D)
                        'responsavel': responsavel,  # Responsável (coluna E)
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
        # Empresa não encontrada na planilha - deve notificar (fallback)
        return True, None

    situacao = dados_empresa.get('situacao', '')

    # Status negativos bloqueiam notificação, EXCETO SUSPENSA/SUSPENSO
    if situacao in STATUS_NEGATIVOS:
        return False, situacao

    return True, situacao


def buscar_responsaveis_empresa(nome_cliente: str, threshold: float = 0.80) -> list[str]:
    """
    Busca os responsáveis (DP e geral) de uma empresa pelo nome.
    Usa busca por similaridade se não encontrar match exato.

    Args:
        nome_cliente: Nome do cliente do email
        threshold: Similaridade mínima para considerar match (padrão 80%)

    Retorna lista de IDs do Discord dos responsáveis encontrados.
    Lista vazia se empresa não encontrada ou sem responsáveis mapeados.
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
            return []

    # Extrai ambos os responsáveis dos dados da empresa
    responsavel_dp = dados_empresa.get('responsavel_dp', '')
    responsavel = dados_empresa.get('responsavel', '')

    discord_ids = []

    # Busca o ID do Discord do responsável DP (coluna D)
    if responsavel_dp:
        discord_id_dp = responsavel_discord_cache.get(responsavel_dp)
        if discord_id_dp:
            discord_ids.append(discord_id_dp)
            logger.debug(f"Responsável DP '{responsavel_dp}' -> Discord ID '{discord_id_dp}'")
        else:
            logger.debug(f"Responsável DP '{responsavel_dp}' não tem ID Discord mapeado")

    # Busca o ID do Discord do responsável geral (coluna E)
    if responsavel:
        discord_id = responsavel_discord_cache.get(responsavel)
        if discord_id and discord_id not in discord_ids:  # Evita duplicatas
            discord_ids.append(discord_id)
            logger.debug(f"Responsável '{responsavel}' -> Discord ID '{discord_id}'")
        else:
            logger.debug(f"Responsável '{responsavel}' não tem ID Discord mapeado")

    if discord_ids:
        logger.debug(f"Empresa '{nome_cliente}' -> {len(discord_ids)} responsável(is) encontrado(s)")
    else:
        logger.debug(f"Empresa '{nome_cliente}' -> Nenhum responsável com ID Discord mapeado")

    return discord_ids


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
# FUNÇÃO PARA EXTRAIR ALERTA DE PROCURAÇÃO
# ------------------------------------------
def extract_procuracao_alert(body, subject):
    """
    Extrai alerta de empresas sem procuração do corpo do e-mail HTML.
    Retorna um dicionário com os dados do alerta ou None se não for esse tipo de email.

    Formato do email de alerta:
    - Assunto contém: "ALERTA: X Empresa(s) sem Procuração"
    - HTML contém tabela com Nome da Empresa e CNPJ
    """
    try:
        # Verifica se é um email de alerta de procuração
        if "sem Procuração" not in subject and "sem Procuração" not in body:
            return None

        # Extrai todas as empresas da tabela
        empresas = []

        # Padrão para encontrar linhas da tabela com empresa e CNPJ
        # Busca por <strong>NOME</strong> seguido de CNPJ no formato XX.XXX.XXX/XXXX-XX
        pattern = r'<strong>([^<]+)</strong>\s*</td>\s*<td[^>]*>\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})'
        matches = re.findall(pattern, body, re.DOTALL)

        for nome, cnpj in matches:
            empresas.append({
                'nome': nome.strip(),
                'cnpj': cnpj.strip()
            })

        if not empresas:
            logger.warning("Alerta de procuração detectado mas nenhuma empresa extraída")
            return None

        # Extrai a data do footer
        data_match = re.search(r'Data:\s*(\d{2}/\d{2}/\d{4},?\s*\d{2}:\d{2}:\d{2})', body)
        data_alerta = data_match.group(1) if data_match else datetime.now().strftime('%d/%m/%Y, %H:%M:%S')

        alert = {
            'tipo': 'procuracao',
            'empresas': empresas,
            'total': len(empresas),
            'data': data_alerta
        }

        logger.info(f"Alerta de procuração extraído: {len(empresas)} empresa(s)")
        return alert

    except Exception as e:
        logger.error(f"Erro ao extrair alerta de procuração: {e}")
        return None


# ------------------------------------------
# FUNÇÃO PARA LIMPAR ENTIDADES HTML
# ------------------------------------------
def limpar_html(texto):
    """Remove tags e entidades HTML de um texto."""
    # Remove tags HTML
    texto_limpo = re.sub(r'<[^>]+>', ' ', texto)
    # Remove entidades HTML comuns
    entidades = {
        '&nbsp;': ' ', '&ccedil;': 'ç', '&Ccedil;': 'Ç',
        '&atilde;': 'ã', '&Atilde;': 'Ã', '&aacute;': 'á', '&Aacute;': 'Á',
        '&eacute;': 'é', '&Eacute;': 'É', '&iacute;': 'í', '&Iacute;': 'Í',
        '&oacute;': 'ó', '&Oacute;': 'Ó', '&uacute;': 'ú', '&Uacute;': 'Ú',
        '&otilde;': 'õ', '&Otilde;': 'Õ', '&ecirc;': 'ê', '&Ecirc;': 'Ê',
        '&quot;': '"', '&ldquo;': '"', '&rdquo;': '"',
        '&ndash;': '-', '&mdash;': '-', '&amp;': '&',
    }
    for entidade, char in entidades.items():
        texto_limpo = texto_limpo.replace(entidade, char)
    # Remove espaços extras
    return ' '.join(texto_limpo.split())


# ------------------------------------------
# FUNÇÃO PARA EXTRAIR NOTIFICAÇÃO DO E-MAIL ECAC (FORMATO LISTA)
# ------------------------------------------
def extract_ecac_notification_lista(body, subject):
    """
    Extrai notificações do formato de lista (tabela com múltiplas mensagens).
    Retorna lista de dicionários com os dados das notificações.

    Formato: Email com tabela contendo Assunto e Data de Envio
    - Empresa está no header do email
    - Cada linha da tabela é uma mensagem
    """
    try:
        notifications = []

        # Extrai empresa do header (está dentro de um <p> após o <h1>)
        empresa_match = re.search(
            r'<h1[^>]*>.*?Mensagens Não Lidas.*?</h1>\s*<p[^>]*>([^<]+)</p>',
            body,
            re.DOTALL | re.IGNORECASE
        )
        if not empresa_match:
            # Tenta extrair do assunto: "📬 EMPRESA: X Mensagem(ns)..."
            empresa_match_subject = re.search(r'📬\s*([^:]+):\s*\d+\s*Mensagem', subject)
            if empresa_match_subject:
                empresa = empresa_match_subject.group(1).strip()
            else:
                return None
        else:
            empresa = empresa_match.group(1).strip()

        # Extrai linhas da tabela (cada <tr> no tbody)
        # Padrão: <td>Assunto</td> <td>Data</td>
        rows = re.findall(
            r'<tr>\s*<td[^>]*>\s*([^<]+)\s*</td>\s*<td[^>]*>\s*(\d{2}/\d{2}/\d{4})\s*</td>\s*</tr>',
            body,
            re.DOTALL
        )

        if not rows:
            return None

        for assunto, data_envio in rows:
            notification = {
                'empresa': empresa,
                'assunto': assunto.strip(),
                'data_envio': data_envio.strip(),
                'resumo': ''  # Formato lista não tem resumo
            }
            notifications.append(notification)
            logger.info(f"Notificação extraída (lista): {empresa} - {assunto.strip()}")

        return notifications if notifications else None

    except Exception as e:
        logger.error(f"Erro ao extrair notificação ECAC (lista): {e}")
        return None


# ------------------------------------------
# FUNÇÃO PARA EXTRAIR NOTIFICAÇÃO DO E-MAIL ECAC (FORMATO INDIVIDUAL)
# ------------------------------------------
def extract_ecac_notification_individual(body, subject):
    """
    Extrai notificação do formato individual (uma mensagem com detalhes).
    Retorna dicionário com os dados da notificação ou None.

    Formato: Email com info-label/info-value e message-body
    """
    try:
        empresa = None
        assunto = None
        data_envio = None
        resumo = ""

        # Extrai empresa
        empresa_match = re.search(
            r'<span class="info-label">Empresa:</span>\s*<span class="info-value">([^<]+)</span>',
            body,
            re.DOTALL
        )
        if empresa_match:
            empresa = empresa_match.group(1).strip()

        # Extrai assunto
        assunto_match = re.search(
            r'<span class="info-label">Assunto:</span>\s*<span class="info-value">([^<]+)</span>',
            body,
            re.DOTALL
        )
        if assunto_match:
            assunto = assunto_match.group(1).strip()

        # Extrai data de envio
        data_match = re.search(
            r'<span class="info-label">Data de Envio:</span>\s*<span class="info-value">([^<]+)</span>',
            body,
            re.DOTALL
        )
        if data_match:
            data_envio = data_match.group(1).strip()

        # Extrai corpo da mensagem
        corpo_match = re.search(
            r'<div class="message-body">\s*<p>(.*?)</p>\s*</div>',
            body,
            re.DOTALL
        )
        if corpo_match:
            corpo_html = corpo_match.group(1)
            corpo_limpo = limpar_html(corpo_html)
            resumo = corpo_limpo[:300] + "..." if len(corpo_limpo) > 300 else corpo_limpo

        if empresa and assunto and data_envio:
            notification = {
                'empresa': empresa,
                'assunto': assunto,
                'data_envio': data_envio,
                'resumo': resumo
            }
            logger.info(f"Notificação extraída (individual): {empresa} - {assunto}")
            return notification

        return None

    except Exception as e:
        logger.error(f"Erro ao extrair notificação ECAC (individual): {e}")
        return None


# ------------------------------------------
# FUNÇÃO PRINCIPAL PARA EXTRAIR NOTIFICAÇÃO DO E-MAIL ECAC
# ------------------------------------------
def extract_ecac_notification(body, subject):
    """
    Extrai notificações do corpo do e-mail HTML do ECAC.
    Retorna lista de dicionários com os dados das notificações ou None.

    Suporta dois formatos:
    - Formato lista (2026): tabela com múltiplas mensagens
    - Formato individual: uma mensagem com info-label/info-value
    """
    # Primeiro tenta o formato de lista (novo)
    if "Mensagens Não Lidas" in body or "Lista de Mensagens" in body:
        result = extract_ecac_notification_lista(body, subject)
        if result:
            return result

    # Tenta o formato individual (antigo)
    result = extract_ecac_notification_individual(body, subject)
    if result:
        return [result]  # Retorna como lista para manter consistência

    logger.warning("Não foi possível extrair notificação do email ECAC")
    return None

# ------------------------------------------
# FUNÇÃO PARA LER OS E-MAILS DA PASTA ECAC
# ------------------------------------------
def check_emails():
    """
    Lê emails não lidos da pasta ECAC.
    Cada email do Bip SERPRO contém uma notificação individual.
    Retorna tupla (notificações, alertas_procuração).
    """
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_PASS)
        logger.info("Conectado ao Gmail com sucesso")

        # Seleciona a pasta ECAC
        mail.select("ECAC")
        logger.info("Pasta 'ECAC' selecionada")

        # Busca apenas emails não lidos
        _, data = mail.search(None, "UNSEEN")
        email_ids = data[0].split()

        logger.info(f"Total de e-mails não lidos na pasta ECAC: {len(email_ids)}")

        all_notifications = []
        alertas_procuracao = []

        for idx, eid in enumerate(email_ids, 1):
            _, msg = mail.fetch(eid, "(RFC822)")
            for response in msg:
                if isinstance(response, tuple):
                    msg_email = email.message_from_bytes(response[1])
                    subject = decode(msg_email["Subject"])
                    sender = msg_email["From"]

                    logger.info(f"[{idx}] De: {sender} | Assunto: {subject}")

                    # Conteúdo do email (prioriza HTML)
                    body = ""
                    if msg_email.is_multipart():
                        for part in msg_email.walk():
                            content_type = part.get_content_type()
                            if content_type == "text/html":
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                break
                            elif content_type == "text/plain" and not body:
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    else:
                        body = msg_email.get_payload(decode=True).decode("utf-8", errors="ignore")

                    # Verifica se é um email do Bip SERPRO (formato esperado)
                    if "Bip SERPRO" in sender or "info-label" in body or "Mensagens Não Lidas" in body:
                        # Primeiro verifica se é um alerta de procuração
                        alerta = extract_procuracao_alert(body, subject)
                        if alerta:
                            logger.info(f">> Alerta de procuração encontrado! {alerta['total']} empresa(s)")
                            alertas_procuracao.append(alerta)
                            continue

                        logger.info(f">> Email Bip SERPRO encontrado! Processando...")

                        # Extrai as notificações do email (pode retornar lista)
                        notifs = extract_ecac_notification(body, subject)

                        if notifs:
                            for notif in notifs:
                                logger.info(f"   -> Empresa: {notif['empresa']}")
                                logger.info(f"   -> Assunto: {notif['assunto']}")
                                all_notifications.append(notif)
                        else:
                            logger.warning(f">> E-mail não contém notificação no padrão esperado")
                    else:
                        logger.debug(f"E-mail descartado - não é do Bip SERPRO")

        mail.logout()
        logger.info(f"Total de notificações para enviar ao Discord: {len(all_notifications)}")
        logger.info(f"Total de alertas de procuração: {len(alertas_procuracao)}")
        return all_notifications, alertas_procuracao

    except Exception as e:
        logger.error(f"Erro ao verificar e-mails: {str(e)}")
        return [], []


# ------------------------------------------
# FUNÇÃO PARA ENVIAR ALERTA DE PROCURAÇÃO
# ------------------------------------------
async def enviar_alerta_procuracao(channel, alerta):
    """
    Envia alerta de empresas sem procuração no Discord.
    Menciona o cargo Legalização.
    Divide em múltiplos embeds se houver mais de 20 empresas (limite Discord: 25 campos).
    """
    try:
        # Menção ao cargo Legalização
        mencao = f"<@&{LEGALIZACAO_ROLE_ID}>"

        empresas = alerta['empresas']
        total_empresas = alerta['total']

        # Divide em lotes de 20 empresas (margem de segurança do limite de 25)
        EMPRESAS_POR_EMBED = 20
        total_lotes = (len(empresas) + EMPRESAS_POR_EMBED - 1) // EMPRESAS_POR_EMBED

        for lote_idx in range(total_lotes):
            inicio = lote_idx * EMPRESAS_POR_EMBED
            fim = min(inicio + EMPRESAS_POR_EMBED, len(empresas))
            empresas_lote = empresas[inicio:fim]

            # Título e descrição variam conforme número de lotes
            if total_lotes == 1:
                titulo = "⚠️ ALERTA: Empresas sem Procuração"
                descricao = f"Bip identificou **{total_empresas}** empresa(s) sem procuração autorizada no eCAC."
            else:
                titulo = f"⚠️ ALERTA: Empresas sem Procuração ({lote_idx + 1}/{total_lotes})"
                descricao = f"Lote {lote_idx + 1} de {total_lotes} - Total: **{total_empresas}** empresa(s)"

            embed = discord.Embed(
                title=titulo,
                description=descricao,
                color=discord.Color.red(),
            )

            # Lista cada empresa do lote
            for idx, empresa in enumerate(empresas_lote, inicio + 1):
                nome = empresa['nome']
                # Limita tamanho do nome (Discord limite: 256 para field name)
                if len(nome) > 200:
                    nome = nome[:200] + "..."

                embed.add_field(
                    name=f"{idx}. {nome}",
                    value=f"📋 CNPJ: `{empresa['cnpj']}`",
                    inline=False
                )

            # Adiciona data do alerta no último lote
            if lote_idx == total_lotes - 1:
                embed.set_footer(text=f"Data do alerta: {alerta['data']}")

            # Só menciona no primeiro lote
            if lote_idx == 0:
                await channel.send(mencao, embed=embed)
            else:
                await channel.send(embed=embed)

            logger.info(f">> Alerta de procuração lote {lote_idx + 1}/{total_lotes} enviado")

        logger.info(f">> Alerta de procuração completo: {total_empresas} empresa(s)")

    except Exception as e:
        logger.error(f"Erro ao enviar alerta de procuração: {e}")


# ------------------------------------------
# TAREFA AUTOMÁTICA DE CHECAR GMAIL
# ------------------------------------------
@tasks.loop(seconds=150)  # 2.5 minutos
async def email_monitor():
    try:
        channel = bot.get_channel(CHANNEL_ID_BIP)
        if channel is None:
            logger.error(f"Canal Discord com ID {CHANNEL_ID_BIP} não encontrado")
            return

        notifications, alertas_procuracao = check_emails()

        logger.info(f">> Total de notificacoes coletadas: {len(notifications)}")
        logger.info(f">> Total de alertas de procuração: {len(alertas_procuracao)}")

        # Processa alertas de procuração (menciona cargo Legalização)
        for alerta in alertas_procuracao:
            await enviar_alerta_procuracao(channel, alerta)

        if not notifications:
            return

        # Agrupa notificações por empresa
        empresas_agrupadas = {}
        for notif in notifications:
            empresa = notif['empresa']
            if empresa not in empresas_agrupadas:
                empresas_agrupadas[empresa] = []
            empresas_agrupadas[empresa].append(notif)

        logger.info(f">> Agrupado em {len(empresas_agrupadas)} empresa(s)")

        # Envia mensagem separadora com data e hora
        agora = datetime.now().strftime('%d/%m/%Y - %H:%M:%S')
        await channel.send(f"**📬 Notificações ECAC [{agora}]**")
        logger.info(f">> Mensagem separadora enviada: Notificações ECAC [{agora}]")

        enviadas = 0
        empresas_sem_responsavel = []
        empresas_ignoradas = []

        for empresa, notifs in empresas_agrupadas.items():
            logger.info(f">> Processando empresa: {empresa} ({len(notifs)} notificação(ões))")

            # Verifica se a empresa tem status negativo
            deve_notificar, situacao = verificar_situacao_empresa(empresa)
            if not deve_notificar:
                logger.info(f">> Empresa '{empresa}' ignorada - situação: {situacao}")
                empresas_ignoradas.append((empresa, situacao))
                continue

            # Busca os responsáveis pela empresa (DP e geral)
            discord_ids = buscar_responsaveis_empresa(empresa)

            # Monta a menção baseado nos responsáveis encontrados
            if discord_ids:
                # Encontrou pelo menos um responsável - menciona todos
                mencao = " ".join([f"<@{uid}>" for uid in discord_ids])
                logger.info(f">> Empresa '{empresa}' -> {len(discord_ids)} responsável(is) encontrado(s)")
            else:
                # Nenhum responsável encontrado - fallback para Fabiana e Lais/Eli
                mencao = f"<@{FABIANA_USER_ID}> <@{LAIS_ELI_USER_ID}>"
                logger.info(f">> Empresa '{empresa}' sem responsável -> mencionando Fabiana e Lais/Eli")
                empresas_sem_responsavel.append(empresa)

            # Divide notificações em lotes de 5 para não exceder limite do embed
            NOTIFS_POR_EMBED = 5
            total_lotes = (len(notifs) + NOTIFS_POR_EMBED - 1) // NOTIFS_POR_EMBED

            for lote_idx in range(total_lotes):
                inicio = lote_idx * NOTIFS_POR_EMBED
                fim = min(inicio + NOTIFS_POR_EMBED, len(notifs))
                notifs_lote = notifs[inicio:fim]

                # Cria o embed para este lote
                if total_lotes == 1:
                    titulo = "📨 Mensagem da Caixa Postal e-CAC"
                    descricao = f"Bip identificou **{len(notifs)}** mensagem(ns) para esta empresa."
                else:
                    titulo = f"📨 Caixa Postal e-CAC ({lote_idx + 1}/{total_lotes})"
                    descricao = f"Lote {lote_idx + 1} de {total_lotes} - Total: **{len(notifs)}** mensagem(ns)"

                embed = discord.Embed(
                    title=titulo,
                    description=descricao,
                    color=discord.Color.orange(),
                )

                # Informações da empresa (só no primeiro lote)
                if lote_idx == 0:
                    embed.add_field(name="🏢 Empresa", value=empresa, inline=False)

                # Lista cada notificação do lote
                for idx, n in enumerate(notifs_lote, inicio + 1):
                    # Formata os detalhes da notificação
                    assunto = n['assunto']
                    # Limita tamanho do assunto
                    if len(assunto) > 150:
                        assunto = assunto[:150] + "..."

                    detalhes = (
                        f"📅 **Data:** {n['data_envio']}\n"
                        f"📌 **Assunto:** {assunto}"
                    )

                    # Adiciona resumo curto se houver
                    if n.get('resumo'):
                        resumo = n['resumo']
                        if len(resumo) > 150:
                            resumo = resumo[:150] + "..."
                        detalhes += f"\n📝 {resumo}"

                    # Limita o tamanho total do campo (Discord limite: 1024)
                    if len(detalhes) > 900:
                        detalhes = detalhes[:900] + "..."

                    embed.add_field(
                        name=f"Mensagem {idx}",
                        value=detalhes,
                        inline=False
                    )

                # Só menciona no primeiro lote
                if lote_idx == 0:
                    await channel.send(mencao, embed=embed)
                else:
                    await channel.send(embed=embed)

                logger.info(f">> Lote {lote_idx + 1}/{total_lotes} enviado | Empresa: {empresa}")

            enviadas += 1

        # Envia relatório de empresas sem responsável (se houver)
        if empresas_sem_responsavel:
            empresas_unicas = list(dict.fromkeys(empresas_sem_responsavel))

            relatorio = f"<@{HUGO_USER_ID}> **📋 Relatório - Empresas não encontradas na planilha:**\n\n"
            for idx, emp in enumerate(empresas_unicas, 1):
                relatorio += f"{idx}. {emp}\n"

            relatorio += f"\n*Total: {len(empresas_unicas)} empresa(s)*"

            await channel.send(relatorio)
            logger.info(f">> Relatório enviado: {len(empresas_unicas)} empresa(s) não encontradas")

        if enviadas > 0:
            logger.info(f">> Resumo: {enviadas} empresa(s) notificada(s)")

        if empresas_ignoradas:
            logger.info(f">> Empresas ignoradas por status negativo: {len(empresas_ignoradas)}")
            for emp, status in empresas_ignoradas:
                logger.info(f"   -> {emp}: {status}")

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
    logger.info("Bip está online!")
    logger.info(f"Bot conectado como: {bot.user}")
    logger.info(f"Canal Discord: {CHANNEL_ID_BIP}")
    logger.info("=" * 50)

    # Envia mensagem de inicialização no canal
    try:
        channel = bot.get_channel(CHANNEL_ID_BIP)
        if channel:
            # await channel.send("**Bip Bot iniciado!** Monitorando a caixa ECAC a cada 60 segundos...")
            logger.info("Mensagem de inicialização enviada ao Discord")
        else:
            logger.warning(f"Canal {CHANNEL_ID_BIP} não encontrado para mensagem de inicialização")
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem de inicialização: {e}")

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
