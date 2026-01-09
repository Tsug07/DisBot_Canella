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

# ID do responsável geral (fallback quando não encontra responsável)
RESPONSAVEL_FALLBACK_ID = "0000000000000000000"

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
        # Empresa não encontrada na planilha - deve notificar (fallback)
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
# FUNÇÃO PARA EXTRAIR NOTIFICAÇÃO DO E-MAIL ECAC
# ------------------------------------------
def extract_ecac_notification(body, subject):
    """
    Extrai a notificação do corpo do e-mail HTML do ECAC.
    Retorna um dicionário com os dados da notificação ou None se não encontrar.

    Formato do email ECAC (Bip SERPRO):
    - Assunto: "EMPRESA - Assunto da mensagem - DATA"
    - HTML contém: Empresa, Assunto, Data de Envio, e corpo da mensagem
    """

    try:
        # Extrai empresa do HTML
        empresa_match = re.search(
            r'<span class="info-label">Empresa:</span>\s*<span class="info-value">([^<]+)</span>',
            body,
            re.DOTALL
        )

        # Extrai assunto do HTML
        assunto_match = re.search(
            r'<span class="info-label">Assunto:</span>\s*<span class="info-value">([^<]+)</span>',
            body,
            re.DOTALL
        )

        # Extrai data de envio do HTML
        data_match = re.search(
            r'<span class="info-label">Data de Envio:</span>\s*<span class="info-value">([^<]+)</span>',
            body,
            re.DOTALL
        )

        # Extrai corpo da mensagem
        corpo_match = re.search(
            r'<div class="message-body">\s*<p>(.*?)</p>\s*</div>',
            body,
            re.DOTALL
        )

        if empresa_match and assunto_match and data_match:
            empresa = empresa_match.group(1).strip()
            assunto = assunto_match.group(1).strip()
            data_envio = data_match.group(1).strip()

            # Extrai resumo do corpo (limpa HTML e pega primeiros 300 chars)
            resumo = ""
            if corpo_match:
                corpo_html = corpo_match.group(1)
                # Remove tags HTML
                corpo_limpo = re.sub(r'<[^>]+>', ' ', corpo_html)
                # Remove entidades HTML comuns
                corpo_limpo = corpo_limpo.replace('&nbsp;', ' ')
                corpo_limpo = corpo_limpo.replace('&ccedil;', 'ç')
                corpo_limpo = corpo_limpo.replace('&atilde;', 'ã')
                corpo_limpo = corpo_limpo.replace('&aacute;', 'á')
                corpo_limpo = corpo_limpo.replace('&eacute;', 'é')
                corpo_limpo = corpo_limpo.replace('&iacute;', 'í')
                corpo_limpo = corpo_limpo.replace('&oacute;', 'ó')
                corpo_limpo = corpo_limpo.replace('&uacute;', 'ú')
                corpo_limpo = corpo_limpo.replace('&otilde;', 'õ')
                corpo_limpo = corpo_limpo.replace('&ecirc;', 'ê')
                corpo_limpo = corpo_limpo.replace('&quot;', '"')
                # Remove espaços extras
                corpo_limpo = ' '.join(corpo_limpo.split())
                resumo = corpo_limpo[:300] + "..." if len(corpo_limpo) > 300 else corpo_limpo

            notification = {
                'empresa': empresa,
                'assunto': assunto,
                'data_envio': data_envio,
                'resumo': resumo
            }

            logger.info(f"Notificação extraída: {empresa} - {assunto}")
            return notification
        else:
            logger.warning("Não foi possível extrair todos os campos do email ECAC")
            return None

    except Exception as e:
        logger.error(f"Erro ao extrair notificação ECAC: {e}")
        return None

# ------------------------------------------
# FUNÇÃO PARA LER OS E-MAILS DA PASTA ECAC
# ------------------------------------------
def check_emails():
    """
    Lê emails não lidos da pasta ECAC.
    Cada email do Bip SERPRO contém uma notificação individual.
    Retorna lista de notificações extraídas.
    """
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_PASS)
        logger.info("Conectado ao Gmail com sucesso")

        # Seleciona a pasta ECAC
        mail.select("ECAC")
        logger.info("Pasta 'ECAC' selecionada")

        # Busca apenas emails não lidos
        result, data = mail.search(None, "UNSEEN")
        email_ids = data[0].split()

        logger.info(f"Total de e-mails não lidos na pasta ECAC: {len(email_ids)}")

        all_notifications = []

        for idx, eid in enumerate(email_ids, 1):
            res, msg = mail.fetch(eid, "(RFC822)")
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
                    if "Bip SERPRO" in sender or "info-label" in body:
                        logger.info(f">> Email Bip SERPRO encontrado! Processando...")

                        # Extrai a notificação do email
                        notif = extract_ecac_notification(body, subject)

                        if notif:
                            logger.info(f"   -> Empresa: {notif['empresa']}")
                            logger.info(f"   -> Assunto: {notif['assunto']}")
                            all_notifications.append(notif)
                        else:
                            logger.warning(f">> E-mail não contém notificação no padrão esperado")
                    else:
                        logger.debug(f"E-mail descartado - não é do Bip SERPRO")

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
        channel = bot.get_channel(CHANNEL_ID_BIP)
        if channel is None:
            logger.error(f"Canal Discord com ID {CHANNEL_ID_BIP} não encontrado")
            return

        notifications = check_emails()

        logger.info(f">> Total de notificacoes coletadas: {len(notifications)}")

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

            # Busca o responsável pela empresa
            discord_id = buscar_responsavel_empresa(empresa)

            # FASE DE TESTE: Se encontrar na planilha -> marca Hugo, senão -> @everyone
            if discord_id:
                mencao = f"<@{HUGO_USER_ID}>"
                logger.info(f">> Empresa encontrada na planilha -> mencionando Hugo (teste)")
            else:
                mencao = "@everyone"
                logger.info(f">> Empresa não encontrada na planilha -> mencionando @everyone (teste)")
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
