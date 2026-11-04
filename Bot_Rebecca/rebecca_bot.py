import discord
from discord.ext import tasks, commands
import imaplib
import email
from email.header import decode_header, make_header
import re
import os
import json
import requests
import csv
import hashlib
from io import StringIO, BytesIO
from datetime import datetime
from difflib import SequenceMatcher

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from dotenv import load_dotenv
from config import get_logger
import sys
import atexit
from pathlib import Path
from contextlib import contextmanager

load_dotenv()
logger = get_logger()

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_PASS = os.getenv("GMAIL_PASS")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

# === CONFIGURAÇÃO DE LOCKFILE ===
BOT_DIR = Path(__file__).parent.resolve()
# Onde fica o que o bot APRENDE (estado). Na VM e a propria pasta do bot; no
# container e um volume (BOT_DATA_DIR), senao todo deploy apagaria o estado.
DATA_DIR = Path(os.getenv("BOT_DATA_DIR") or BOT_DIR)
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOCKFILE_PATH = BOT_DIR / "bot_rebecca.lock"

# === CONFIGURAÇÃO DO GOOGLE SHEETS ===
# Planilha pública - exporta como CSV
SHEET_ID = "1PAE1LgiEOWJs1emuR5Unt9e-CUWVFjaNtymCUqS-cV4"
SHEET_GID = "0"  # gid da aba "12.2025"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}"

# === CONFIGURAÇÃO DO MAPEAMENTO DE RESPONSÁVEIS ===
RESPONSAVEIS_JSON_PATH = BOT_DIR / "responsaveis_discord.json"

# === CONFIGURAÇÃO DO CONTROLE "JÁ PROCESSEI" ===
# O bot NÃO depende mais da flag de lido/não-lido do Gmail, porque qualquer
# pessoa que abrisse o e-mail no Gmail fazia o bot nunca vê-lo (notificação
# perdida em silêncio). Em vez disso, ele aplica uma label própria aos e-mails
# que já processou e busca apenas os que ainda não têm essa label.
GMAIL_LABEL_PROCESSADO = "DEC-processado"

# Arquivo com os X-GM-MSGID já processados (rede de segurança caso a label
# falhe ou seja removida manualmente). O X-GM-MSGID é estável, diferente do
# ID de sequência IMAP, que muda quando a pasta muda.
PROCESSADOS_JSON_PATH = DATA_DIR / "emails_processados.json"

# Quantos IDs manter no histórico local (evita o arquivo crescer sem limite)
MAX_HISTORICO_PROCESSADOS = 500

# === CONFIGURAÇÃO DO AVISO DE PROCURAÇÕES (SEFAZ/RJ) ===
# Segundo tipo de e-mail do fornecedor: relatório de procurações, enviado
# quase todo dia com conteúdo praticamente igual. Notifica apenas o
# @Legalização, com o relatório em PDF anexo.
ASSUNTO_PROCURACOES = "Aviso de procurações - SEFAZ/RJ"

# Seções do relatório que entram na notificação, na ordem de exibição.
# As seções "recusadas" e "renunciadas" ficam de fora de propósito: somam
# ~84 empresas de histórico e seriam mais ruído que ação.
SECOES_PROCURACOES = [
    "Procurações vencendo nos próximos 30 dias",
    "Procurações pendentes de aceite",
    "Procurações vencidas nos últimos 12 meses",
]

# Arquivo que guarda a "impressão digital" do último relatório enviado, para
# só notificar quando alguma empresa entra ou sai das seções acompanhadas.
PROCURACOES_ESTADO_PATH = DATA_DIR / "procuracoes_estado.json"

# ID do cargo Legalização no Discord
LEGALIZACAO_ROLE_ID = "1299045050881151006"

# ID da Fabiana (responsável geral - fallback quando não encontra responsável)
FABIANA_USER_ID = "1285344147292684359"

# ID do Hugo (para receber relatório de empresas sem responsável)
HUGO_USER_ID = "1285316758009544844"

# Limites do Discord para embeds: 25 fields e 6000 caracteres no total.
# Uma empresa com muitas notificações estourava o limite e o envio falhava
# com "400 Bad Request: Must be 25 or fewer in length".
EMBED_MAX_FIELDS = 25
EMBED_MAX_CHARS = 5800  # margem abaixo de 6000

# Quantas vezes um mesmo lote de e-mails pode falhar inteiro antes de ser
# marcado como processado mesmo assim. Sem esse limite, um erro que se repete
# sempre (ex.: limite do Discord) faz o bot reenviar o lote a cada ciclo.
MAX_TENTATIVAS_LOTE = 3
tentativas_lote = {}  # frozenset(msgids) -> nº de tentativas falhas

# Cache dos dados da planilha (empresa -> {responsavel, situacao})
empresa_responsavel_cache = {}
# Cache do mapeamento (responsável -> discord_id)
responsavel_discord_cache = {}

# Status negativos que bloqueiam notificação (exceto SUSPENSA/SUSPENSO)
# Valores reais da planilha: BAIXA, DEVOLVIDA, INATIVA
STATUS_NEGATIVOS = ["BAIXA", "DEVOLVIDA", "INATIVA"]

def criar_lockfile():
    """Cria o arquivo de lock com o PID do processo."""
    # No container o Docker ja garante uma instancia so, e a trava atrapalha:
    # o PID se repete entre reinicios (o bot costuma ser sempre o PID 1), entao
    # depois de um `docker restart` o lock antigo apontaria para o PROPRIO
    # processo, e o bot se recusaria a subir -- laco de reinicio infinito.
    if os.getenv("BOT_SEM_LOCK") == "1":
        logger.info("BOT_SEM_LOCK=1: trava de instancia unica desligada (container).")
        return
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
@contextmanager
def _gravacao_atomica(caminho):
    """Abre um temporario ao lado de `caminho` e so troca pelo definitivo no fim.

    Se o processo morrer no meio da escrita (um `docker stop`, queda de luz na
    VM), o arquivo antigo continua inteiro. Sem isso, um JSON cortado ao meio
    vira historico vazio na proxima leitura e o bot reenvia avisos ja dados."""
    tmp = Path(str(caminho) + ".tmp")
    with open(tmp, 'w', encoding='utf-8') as f:
        yield f
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, caminho)


def carregar_processados():
    """
    Carrega do disco o conjunto de X-GM-MSGID já processados.

    Rede de segurança do controle "já processei": se a label do Gmail falhar
    ou for removida à mão, este histórico impede o reenvio das notificações.
    """
    try:
        if PROCESSADOS_JSON_PATH.exists():
            with open(PROCESSADOS_JSON_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                ids = set(data.get("processados", []))
                logger.info(f"Histórico local carregado: {len(ids)} e-mail(s) já processado(s)")
                return ids
        logger.info("Histórico local ainda não existe - será criado no primeiro processamento")
        return set()
    except Exception as e:
        logger.error(f"Erro ao carregar histórico de processados: {e}")
        # Em caso de erro retorna vazio: a label do Gmail continua protegendo
        # contra reprocessamento, então o pior caso é um reenvio, não um silêncio.
        return set()


def salvar_processados(msgids):
    """
    Grava no disco os X-GM-MSGID já processados, mantendo apenas os mais
    recentes (MAX_HISTORICO_PROCESSADOS) para o arquivo não crescer sem limite.
    """
    try:
        ids = list(msgids)[-MAX_HISTORICO_PROCESSADOS:]
        with _gravacao_atomica(PROCESSADOS_JSON_PATH) as f:
            json.dump(
                {
                    "_descricao": "X-GM-MSGID dos e-mails DEC já processados pelo bot. "
                                  "Não editar à mão; apagar este arquivo pode causar reenvio.",
                    "atualizado_em": datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                    "processados": ids,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
    except Exception as e:
        logger.error(f"Erro ao salvar histórico de processados: {e}")


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

            # Colunas da planilha: A=Nº, B=EMPRESA, C=SITUAÇÃO,
            #                      D=PESSOAL, E=FISCAL, F=CONTÁBIL, G=LEGALIZA/CONTROLE
            # Coluna B (índice 1) = Nome da empresa
            # Coluna C (índice 2) = Situação da empresa
            # Coluna E (índice 4) = Responsável FISCAL (usado para notificações do DEC)
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
    # Junta todos os pedaços do cabeçalho: o assunto do aviso de procurações
    # vem como "Aviso de =?utf-8?q?procura=C3=A7=C3=B5es?= - SEFAZ/RJ", e ler
    # só o primeiro pedaço devolvia "Aviso de ", que nunca batia com o filtro.
    try:
        return str(make_header(decode_header(string)))
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

        # IMPORTANTE: o DEC-SEFAZ já envia as datas em DD/MM/YYYY.
        # Esta checagem vem PRIMEIRO porque uma data como "04/08/2026" também
        # casaria com '%m/%d/%Y' e seria invertida para 08/04/2026.
        if re.match(r'\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}', date_string):
            return date_string

        # Outros formatos (ISO/americano), convertidos para o padrão BR
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S', '%m/%d/%Y %H:%M:%S']:
            try:
                dt = datetime.strptime(date_string, fmt)
                return dt.strftime('%d/%m/%Y %H:%M:%S')
            except ValueError:
                continue

        # Se não conseguiu converter, retorna o original
        return date_string
    except Exception as e:
        logger.warning(f"Erro ao formatar data '{date_string}': {e}")
        return date_string


# ------------------------------------------
# FUNÇÃO PARA EXTRAIR UM CAMPO DA TABELA DE NOTIFICAÇÃO
# ------------------------------------------
def buscar_campo(label, table_html):
    """
    Extrai o valor de um campo da tabela de notificação.

    Tolera as duas formas já enviadas pelo fornecedor (OCF):
    - '<b>Categoria: </b>AVISO'  (formato até jan/2026)
    - '<b>Categoria:</b> AVISO'  (formato atual - os dois-pontos colaram na tag)
    """
    return re.search(
        r'<b>\s*' + re.escape(label) + r'\s*:?\s*</b>\s*:?\s*([^<]+)',
        table_html
    )


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
        r'Mensagens não lidas dos últimos 90 dias:\s*</h[1-6]>(.*?)(?:\*{10,}|Mensagens lidas dos últimos 90 dias:)',
        body,
        re.DOTALL
    )

    if not unread_section_match:
        logger.warning("Seção de mensagens não lidas não encontrada no email")
        return notifications

    # Trabalha apenas com a seção de não lidas
    unread_body = unread_section_match.group(1)
    logger.info(f"Seção de mensagens não lidas extraída ({len(unread_body)} caracteres)")

    # Encontra todos os blocos que começam com CNPJ dentro de <h3> ou <h4>
    # O fornecedor (OCF) já enviou os dois formatos: <h4> até jan/2026, <h3> depois.
    cnpj_pattern = r'<h[34]>CNPJ:\s*([\d./-]+)\s*\|\s*Cliente:\s*([^<]+)'
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
            data_hora_match = buscar_campo('Data e Hora envio', table_html)
            tipo_receita_match = buscar_campo('Tipo de Receita', table_html)
            categoria_match = buscar_campo('Categoria', table_html)
            tipo_mensagem_match = buscar_campo('Tipo de Mensagem', table_html)
            assunto_match = buscar_campo('Assunto', table_html)
            
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
# FUNÇÕES DO AVISO DE PROCURAÇÕES (SEFAZ/RJ)
# ------------------------------------------
def extrair_procuracoes(body):
    """
    Extrai as seções do relatório de procurações do corpo HTML.

    O e-mail tem o formato:
        <h3>Procurações vencendo nos próximos 30 dias</h3>
        <table><thead>...CNPJ|Nome|Validade...</thead>
               <tbody><tr><td>CNPJ</td><td>Nome</td><td>Validade</td></tr>...</tbody></table>
        <hr>
        <h3>Procurações pendentes de aceite</h3>
        ...

    Quando uma seção não tem dados, traz "Nenhuma procuração encontrada".

    Retorna um dict {nome_da_secao: [(cnpj, nome, validade), ...]} contendo
    apenas as seções listadas em SECOES_PROCURACOES.
    """
    secoes = {}

    for titulo in SECOES_PROCURACOES:
        # Pega o conteúdo entre este <h3> e o próximo <hr> (fim da seção).
        # re.escape no título por causa dos acentos e caracteres especiais.
        trecho = re.search(
            r'<h3>\s*' + re.escape(titulo) + r'\s*</h3>(.*?)(?:<hr>|</body>)',
            body,
            re.DOTALL | re.IGNORECASE,
        )

        if not trecho:
            logger.debug(f"Seção de procurações não encontrada: '{titulo}'")
            secoes[titulo] = []
            continue

        linhas = re.findall(
            r'<tr>\s*<td>([\d./-]+)</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*</tr>',
            trecho.group(1),
        )

        secoes[titulo] = [
            (cnpj.strip(), nome.strip(), validade.strip())
            for cnpj, nome, validade in linhas
        ]

    return secoes


def calcular_hash_procuracoes(secoes):
    """
    Gera uma impressão digital do conteúdo das seções acompanhadas.

    Serve para detectar mudança real: se nenhuma empresa entrou nem saiu
    das seções, o hash é igual e o bot não notifica de novo (o e-mail chega
    quase todo dia com o mesmo conteúdo).
    """
    partes = []
    for titulo in SECOES_PROCURACOES:
        for cnpj, nome, validade in sorted(secoes.get(titulo, [])):
            partes.append(f"{titulo}|{cnpj}|{nome}|{validade}")
    conteudo = "\n".join(partes)
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


def carregar_estado_procuracoes():
    """Carrega o hash e as empresas do último relatório de procurações enviado."""
    try:
        if PROCURACOES_ESTADO_PATH.exists():
            with open(PROCURACOES_ESTADO_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"Erro ao carregar estado das procurações: {e}")
        return {}


def salvar_estado_procuracoes(hash_atual, secoes):
    """Grava o hash e as chaves das empresas do relatório recém-enviado."""
    try:
        chaves = {
            titulo: sorted(f"{c}|{v}" for c, _, v in secoes.get(titulo, []))
            for titulo in SECOES_PROCURACOES
        }
        with _gravacao_atomica(PROCURACOES_ESTADO_PATH) as f:
            json.dump(
                {
                    "_descricao": "Estado do último aviso de procurações enviado ao "
                                  "Discord. Usado para notificar só quando há mudança.",
                    "atualizado_em": datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
                    "hash": hash_atual,
                    "empresas_por_secao": chaves,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
    except Exception as e:
        logger.error(f"Erro ao salvar estado das procurações: {e}")


def comparar_procuracoes(secoes):
    """
    Compara o relatório atual com o último enviado.

    Retorna (houve_mudanca, resumo_das_diferencas), onde o resumo lista
    quantas empresas entraram e saíram de cada seção.
    """
    estado = carregar_estado_procuracoes()
    hash_atual = calcular_hash_procuracoes(secoes)

    if not estado:
        return True, ["Primeiro relatório de procurações enviado"]

    if estado.get("hash") == hash_atual:
        return False, []

    anterior = estado.get("empresas_por_secao", {})
    diferencas = []

    for titulo in SECOES_PROCURACOES:
        antes = set(anterior.get(titulo, []))
        agora = {f"{c}|{v}" for c, _, v in secoes.get(titulo, [])}

        entraram = agora - antes
        sairam = antes - agora

        if entraram or sairam:
            partes = []
            if entraram:
                partes.append(f"+{len(entraram)}")
            if sairam:
                partes.append(f"-{len(sairam)}")
            diferencas.append(f"{titulo}: {' / '.join(partes)}")

    return True, diferencas or ["Dados atualizados"]


def gerar_pdf_procuracoes(secoes, data_email):
    """
    Monta o relatório de procurações em PDF e devolve os bytes.

    Uma tabela por seção, com cabeçalho repetido quando a tabela quebra
    entre páginas. Retorna None se a geração falhar, para que o bot possa
    cair no resumo em texto em vez de não avisar nada.
    """
    try:
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=15 * mm,
            rightMargin=15 * mm,
            topMargin=15 * mm,
            bottomMargin=15 * mm,
            title="Aviso de Procurações - SEFAZ/RJ",
            author="Bot Rebecca",
        )

        estilos = getSampleStyleSheet()
        estilo_titulo = ParagraphStyle(
            "TituloRelatorio",
            parent=estilos["Title"],
            fontSize=16,
            spaceAfter=2 * mm,
        )
        estilo_sub = ParagraphStyle(
            "SubTitulo",
            parent=estilos["Normal"],
            fontSize=9,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#555555"),
            spaceAfter=6 * mm,
        )
        estilo_secao = ParagraphStyle(
            "TituloSecao",
            parent=estilos["Heading2"],
            fontSize=12,
            spaceBefore=4 * mm,
            spaceAfter=2 * mm,
            textColor=colors.HexColor("#1F3864"),
        )
        estilo_celula = ParagraphStyle(
            "Celula", parent=estilos["Normal"], fontSize=8, leading=10
        )
        estilo_vazio = ParagraphStyle(
            "Vazio",
            parent=estilos["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#777777"),
            spaceAfter=3 * mm,
        )

        elementos = [
            Paragraph("Aviso de Procurações - SEFAZ/RJ", estilo_titulo),
            Paragraph(
                f"CANELLA &amp; SANTOS CONTABILIDADE EIRELI<br/>"
                f"Relatório do e-mail de {data_email} &nbsp;|&nbsp; "
                f"Gerado em {datetime.now().strftime('%d/%m/%Y às %H:%M')}",
                estilo_sub,
            ),
        ]

        for titulo in SECOES_PROCURACOES:
            linhas = secoes.get(titulo, [])
            elementos.append(
                Paragraph(f"{titulo} ({len(linhas)})", estilo_secao)
            )

            if not linhas:
                elementos.append(
                    Paragraph("Nenhuma procuração nesta situação.", estilo_vazio)
                )
                continue

            dados = [["CNPJ", "Empresa", "Validade"]]
            for cnpj, nome, validade in linhas:
                dados.append([
                    Paragraph(cnpj, estilo_celula),
                    Paragraph(nome, estilo_celula),
                    Paragraph(validade, estilo_celula),
                ])

            tabela = Table(
                dados,
                colWidths=[34 * mm, 112 * mm, 24 * mm],
                repeatRows=1,  # repete o cabeçalho ao quebrar a página
            )
            tabela.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3864")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (2, 1), (2, -1), "CENTER"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#F2F2F2")]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]))
            elementos.append(tabela)
            elementos.append(Spacer(1, 3 * mm))

        doc.build(elementos)
        return buffer.getvalue()

    except Exception as e:
        logger.error(f"Erro ao gerar PDF das procurações: {e}")
        return None


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

        # Busca os e-mails que o bot ainda NÃO processou.
        # Usa a ausência da label própria, e não a flag de não-lido: assim
        # alguém abrir o e-mail no Gmail não faz o bot deixar de processá-lo.
        result, data = mail.search(
            None, 'X-GM-RAW', f'"-label:{GMAIL_LABEL_PROCESSADO}"'
        )
        email_ids = data[0].split()

        logger.info(f"Total de e-mails ainda não processados na pasta DEC: {len(email_ids)}")

        # Histórico local como segunda barreira contra reprocessamento
        ja_processados = carregar_processados()

        all_notifications = []
        # Relatórios de procurações encontrados (segundo tipo de e-mail)
        avisos_procuracoes = []
        # (id_sequencia, msgid) dos e-mails processados, para receberem
        # a label DEPOIS que as notificações forem enviadas ao Discord.
        processed_ids = []

        for idx, eid in enumerate(email_ids, 1):
            # BODY.PEEK[] em vez de RFC822: não altera a flag de lido.
            # X-GM-MSGID vem junto para identificar o e-mail de forma estável.
            res, msg = mail.fetch(eid, "(X-GM-MSGID BODY.PEEK[])")

            # Extrai o X-GM-MSGID da resposta (vem nos metadados, não no corpo)
            msgid = None
            for response in msg:
                meta = response[0] if isinstance(response, tuple) else response
                if meta:
                    m_id = re.search(rb'X-GM-MSGID\s+(\d+)', meta)
                    if m_id:
                        msgid = m_id.group(1).decode()
                        break

            # Se o histórico local já conhece este e-mail, apenas reaplica a
            # label (que deve ter sido perdida) e segue sem reenviar nada.
            if msgid and msgid in ja_processados:
                logger.info(
                    f"[{idx}] E-mail já consta no histórico local (msgid {msgid}) "
                    f"- reaplicando label, sem reenviar"
                )
                processed_ids.append((eid, msgid))
                continue

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
                        processed_ids.append((eid, msgid))

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

                    # Verifica se é o aviso de procurações
                    elif ASSUNTO_PROCURACOES in subject:
                        logger.info(f">> Email de PROCURAÇÕES encontrado! Processando...")
                        processed_ids.append((eid, msgid))

                        secoes = extrair_procuracoes(body)
                        total = sum(len(v) for v in secoes.values())

                        if total:
                            for titulo in SECOES_PROCURACOES:
                                logger.info(f"   -> {titulo}: {len(secoes.get(titulo, []))}")
                            avisos_procuracoes.append({
                                'secoes': secoes,
                                'data_email': msg_email["Date"] or "",
                            })
                        else:
                            logger.warning(
                                ">> E-mail de procurações sem dados nas seções acompanhadas"
                            )
                    else:
                        logger.debug(f"E-mail descartado - assunto não corresponde")

        mail.logout()
        logger.info(f"Total de notificações para enviar ao Discord: {len(all_notifications)}")
        if avisos_procuracoes:
            logger.info(f"Avisos de procurações para processar: {len(avisos_procuracoes)}")
        return all_notifications, processed_ids, avisos_procuracoes

    except Exception as e:
        logger.error(f"Erro ao verificar e-mails: {str(e)}")
        return [], [], []


# ------------------------------------------
# FUNÇÃO PARA MARCAR E-MAILS COMO PROCESSADOS
# ------------------------------------------
def marcar_como_processados(processed_ids):
    """
    Marca os e-mails como processados pelo bot, de duas formas independentes:

    1. Aplica a label GMAIL_LABEL_PROCESSADO no Gmail (critério da busca)
    2. Grava o X-GM-MSGID no histórico local (rede de segurança)

    Também marca como lido, para manter a pasta visualmente organizada - mas,
    diferente de antes, a flag de lido NÃO é mais o que controla o
    reprocessamento, então alguém abrir o e-mail não causa nenhum efeito.

    Chamada somente DEPOIS do envio ao Discord, para que uma falha de envio
    não faça as notificações serem perdidas silenciosamente.
    """
    if not processed_ids:
        return

    # Grava o histórico local primeiro: é a barreira que sobrevive a falhas
    # de rede no Gmail e garante que nada seja reenviado.
    msgids = [mid for _, mid in processed_ids if mid]
    if msgids:
        historico = carregar_processados()
        historico.update(msgids)
        salvar_processados(historico)
        logger.info(f">> {len(msgids)} e-mail(s) registrado(s) no histórico local")

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_PASS)
        mail.select("DEC")

        for eid, _ in processed_ids:
            # X-GM-LABELS cria a label automaticamente se ela não existir
            mail.store(eid, '+X-GM-LABELS', GMAIL_LABEL_PROCESSADO)
            mail.store(eid, '+FLAGS', '\\Seen')

        mail.logout()
        logger.info(
            f">> {len(processed_ids)} e-mail(s) marcado(s) com a label "
            f"'{GMAIL_LABEL_PROCESSADO}'"
        )

    except Exception as e:
        # O histórico local já foi gravado acima, então mesmo com esta falha
        # o e-mail não será reprocessado: a label é reaplicada no próximo ciclo.
        logger.error(f"Erro ao aplicar label nos e-mails: {str(e)}")


# ------------------------------------------
# ENVIO DO AVISO DE PROCURAÇÕES AO DISCORD
# ------------------------------------------
async def enviar_aviso_procuracoes(channel, secoes, data_email):
    """
    Envia o relatório de procurações ao Discord como PDF anexo,
    mencionando apenas o @Legalização.

    Só envia quando há mudança real em relação ao último relatório, porque o
    e-mail chega quase todo dia com o mesmo conteúdo.
    """
    houve_mudanca, diferencas = comparar_procuracoes(secoes)

    if not houve_mudanca:
        logger.info(">> Procurações sem mudança desde o último aviso - nada enviado")
        return False

    # Formata a data do e-mail para exibição
    data_formatada = data_email
    try:
        from email.utils import parsedate_to_datetime
        data_formatada = parsedate_to_datetime(data_email).strftime('%d/%m/%Y')
    except Exception:
        data_formatada = datetime.now().strftime('%d/%m/%Y')

    vencendo = len(secoes.get(SECOES_PROCURACOES[0], []))
    pendentes = len(secoes.get(SECOES_PROCURACOES[1], []))
    vencidas = len(secoes.get(SECOES_PROCURACOES[2], []))

    embed = discord.Embed(
        title="📄 Aviso de Procurações - SEFAZ/RJ",
        description=(
            "Relatório de procurações em anexo (PDF).\n"
            f"*Alterações desde o último aviso: {'; '.join(diferencas)}*"
        ),
        color=discord.Color.blue(),
    )
    embed.add_field(name="⏳ Vencendo em 30 dias", value=str(vencendo), inline=True)
    embed.add_field(name="✍️ Pendentes de aceite", value=str(pendentes), inline=True)
    embed.add_field(name="⚠️ Vencidas (12 meses)", value=str(vencidas), inline=True)
    embed.set_footer(text=f"E-mail de {data_formatada}")

    pdf_bytes = gerar_pdf_procuracoes(secoes, data_formatada)
    mencao = f"<@&{LEGALIZACAO_ROLE_ID}>"

    try:
        if pdf_bytes:
            nome_arquivo = (
                f"procuracoes_{datetime.now().strftime('%d-%m-%Y')}.pdf"
            )
            arquivo = discord.File(BytesIO(pdf_bytes), filename=nome_arquivo)
            await channel.send(mencao, embed=embed, file=arquivo)
            logger.info(
                f">> Aviso de procurações enviado com PDF ({len(pdf_bytes)} bytes)"
            )
        else:
            # Sem o PDF, avisa de todo modo: melhor um resumo que silêncio
            embed.description = (
                "⚠️ Não foi possível gerar o PDF - veja o resumo abaixo.\n"
                f"*Alterações: {'; '.join(diferencas)}*"
            )
            for titulo in SECOES_PROCURACOES:
                linhas = secoes.get(titulo, [])
                if linhas:
                    texto = "\n".join(
                        f"• {nome} — vence {validade}"
                        for _, nome, validade in linhas[:10]
                    )
                    if len(linhas) > 10:
                        texto += f"\n*... e mais {len(linhas) - 10}*"
                    embed.add_field(name=titulo, value=texto[:1024], inline=False)
            await channel.send(mencao, embed=embed)
            logger.warning(">> Aviso de procurações enviado SEM PDF (fallback)")

        # Só grava o estado após o envio dar certo, para que uma falha de
        # rede não faça o aviso ser perdido silenciosamente.
        salvar_estado_procuracoes(calcular_hash_procuracoes(secoes), secoes)
        return True

    except Exception as e:
        logger.error(f"Erro ao enviar aviso de procurações: {e}")
        return False


def montar_embeds_empresa(cliente, cnpj, notifs):
    """Monta um ou mais embeds para a empresa, respeitando os limites do Discord."""
    def novo_embed(parte):
        titulo = "🚨 Notificações SEFAZ/RJ"
        if parte > 1:
            titulo += f" (continuação {parte})"
        embed = discord.Embed(
            title=titulo,
            description=f"Rebecca identificou **{len(notifs)}** notificação(ões) fiscal(is).",
            color=discord.Color.red(),
        )
        embed.add_field(name="🏢 Cliente", value=cliente, inline=False)
        embed.add_field(name="📋 CNPJ", value=cnpj, inline=False)
        return embed

    embeds = [novo_embed(1)]
    for idx, n in enumerate(notifs, 1):
        nome = f"Notificação {idx}"
        detalhes = (
            f"📅 {n['data_hora']}\n"
            f"💰 {n['tipo_receita']} | ⚠️ {n['categoria']} | 📝 {n['tipo_mensagem']}\n"
            f"📌 {n['assunto_notificacao']}"
        )[:1024]
        atual = embeds[-1]
        if (len(atual.fields) >= EMBED_MAX_FIELDS
                or len(atual) + len(nome) + len(detalhes) > EMBED_MAX_CHARS):
            atual = novo_embed(len(embeds) + 1)
            embeds.append(atual)
        atual.add_field(name=nome, value=detalhes, inline=False)
    return embeds


def remover_notificacoes_duplicadas(notifications):
    """Remove notificações repetidas entre e-mails do mesmo lote.

    O aviso do DEC repete todo dia as mensagens ainda não lidas; quando o bot
    fica parado por alguns dias, os e-mails acumulados trazem as mesmas
    notificações várias vezes.
    """
    vistas = set()
    unicas = []
    for n in notifications:
        chave = (n['cnpj'], n['data_hora'], n['tipo_receita'], n['categoria'],
                 n['tipo_mensagem'], n['assunto_notificacao'])
        if chave not in vistas:
            vistas.add(chave)
            unicas.append(n)
    return unicas


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

        notifications, processed_ids, avisos_procuracoes = check_emails()

        logger.info(f">> Total de notificacoes coletadas: {len(notifications)}")

        # Processa o aviso de procurações (independente das notificações do DEC)
        for aviso in avisos_procuracoes:
            await enviar_aviso_procuracoes(
                channel, aviso['secoes'], aviso['data_email']
            )

        if not notifications:
            # Marca e-mails sem notificações pendentes para não reprocessar
            marcar_como_processados(processed_ids)
            return

        total_antes = len(notifications)
        notifications = remover_notificacoes_duplicadas(notifications)
        if len(notifications) < total_antes:
            logger.info(f">> {total_antes - len(notifications)} notificação(ões) duplicada(s) removida(s)")

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
        empresas_com_falha = []

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

            embeds = montar_embeds_empresa(cliente, cnpj, notifs)

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

            # Uma falha numa empresa não pode derrubar o lote inteiro: antes, a
            # exceção impedia a marcação dos e-mails e o bot reenviava tudo
            # a cada ciclo.
            try:
                # Menciona só na primeira mensagem; as continuações vão sem menção
                for i, embed in enumerate(embeds):
                    await channel.send(mencao if i == 0 else None, embed=embed)
                logger.info(f">> Mensagem enviada com sucesso! | Cliente: {cliente}"
                            + (f" ({len(embeds)} partes)" if len(embeds) > 1 else ""))
                enviadas += 1
            except Exception as e:
                logger.error(f">> Falha ao enviar notificações de {cliente}: {e}")
                empresas_com_falha.append(cliente)

        # Envia relatório de empresas sem responsável (se houver)
        if empresas_sem_responsavel:
            empresas_unicas = list(dict.fromkeys(empresas_sem_responsavel))

            relatorio = f"<@{HUGO_USER_ID}> **📋 Relatório - Empresas sem responsável mapeado:**\n\n"
            for idx, empresa in enumerate(empresas_unicas, 1):
                relatorio += f"{idx}. {empresa}\n"

            relatorio += f"\n*Total: {len(empresas_unicas)} empresa(s)*"

            await channel.send(relatorio)
            logger.info(f">> Relatório enviado: {len(empresas_unicas)} empresa(s) sem responsável")

        if empresas_com_falha:
            chave_lote = frozenset(mid for _, mid in processed_ids)
            if enviadas == 0:
                # Nada saiu: provável problema geral (Discord fora do ar etc.).
                # Tenta de novo no próximo ciclo, até o limite de tentativas.
                tentativas_lote[chave_lote] = tentativas_lote.get(chave_lote, 0) + 1
                if tentativas_lote[chave_lote] < MAX_TENTATIVAS_LOTE:
                    raise RuntimeError(
                        f"nenhuma empresa enviada (tentativa "
                        f"{tentativas_lote[chave_lote]}/{MAX_TENTATIVAS_LOTE})"
                    )
            tentativas_lote.pop(chave_lote, None)

            # Avisa o Hugo das empresas que falharam e segue em frente, para
            # não reenviar ao Discord as que já foram notificadas
            falhas = "\n".join(f"{i}. {c}" for i, c in enumerate(empresas_com_falha, 1))
            await channel.send(
                f"<@{HUGO_USER_ID}> **⚠️ Falha ao enviar notificações de "
                f"{len(empresas_com_falha)} empresa(s)** (ver log):\n{falhas}"[:2000]
            )
            logger.warning(f">> {len(empresas_com_falha)} empresa(s) com falha no envio")

        if enviadas > 0:
            logger.info(f">> Resumo: {enviadas} empresa(s) notificada(s)")
        elif not empresas_com_falha:
            # Nenhuma notificação enviada - envia mensagem de parabéns
            await channel.send("🎉 **Parabéns!** Nenhuma notificação pendente no momento. Tudo em dia!")
            logger.info(">> Nenhuma notificação pendente - mensagem de parabéns enviada")

        if empresas_ignoradas:
            logger.info(f">> Empresas ignoradas por status negativo: {len(empresas_ignoradas)}")
            for empresa, status in empresas_ignoradas:
                logger.info(f"   -> {empresa}: {status}")

        # Só marca como processado após o envio ao Discord ter concluído com
        # sucesso. Se algo acima falhar, a exceção abaixo impede a marcação e o
        # e-mail continua sem a label, para ser reprocessado no próximo ciclo.
        marcar_como_processados(processed_ids)

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