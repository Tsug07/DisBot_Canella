import discord
import asyncio
import gspread
from google.oauth2.service_account import Credentials
from discord import app_commands
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import logging
import shutil
from pathlib import Path
import sys
import atexit

# === CONFIGURAÇÃO DE CAMINHOS ===
# Define o diretório base do bot (onde está o main.py)
BOT_DIR = Path(__file__).parent.resolve()
CONFIG_DIR = BOT_DIR / "config"
DATA_DIR = BOT_DIR / "data"
LOGS_DIR = BOT_DIR / "logs"
BACKUPS_DIR = BOT_DIR / "backups"

# Cria diretórios se não existirem
for directory in [CONFIG_DIR, DATA_DIR, LOGS_DIR, BACKUPS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Carrega as variáveis de ambiente do arquivo .env na pasta config
load_dotenv(dotenv_path=CONFIG_DIR / ".env")

# === CONFIGURAÇÃO DE LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOGS_DIR / 'bot_logs.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# === CONFIGURAÇÕES ===
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
DISCORD_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID')) if os.getenv('DISCORD_CHANNEL_ID') else 0
# Canal específico para alterações
DISCORD_SUSPENSE_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_SUSPENSE_ID')) if os.getenv('DISCORD_CHANNEL_SUSPENSE_ID') else 0
# Canal geral para boas-vindas e notificações gerais. Se não configurado, usa DISCORD_CHANNEL_ID
DISCORD_CHANNEL_GENERAL = int(os.getenv('DISCORD_CHANNEL_GENERAL')) if os.getenv('DISCORD_CHANNEL_GENERAL') else DISCORD_CHANNEL_ID
GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID')
PATH_CREDENTIALS = CONFIG_DIR / os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
DIA_RELATORIO_MENSAL = int(os.getenv('DIA_RELATORIO_MENSAL', '5'))  # Dia do mês para enviar relatório

STATUS_MONITORADOS = ["INATIVA", "BAIXA", "DEVOLVIDA", "SUSPENSA"]

# Mapeamento de variações de status e regimes para valores normalizados
MAPEAMENTO_STATUS = {
    # Status normais
    "ATIVA": "ATIVA",
    "ATIVO": "ATIVA",
    "ATIVA (CONSULTORIA)": "ATIVA",
    "ATIVO (CONSULTORIA)": "ATIVA",
    "ATIVA (LEGALIZAÇÃO)": "ATIVA",
    "ATIVO (LEGALIZAÇÃO)": "ATIVA",
    "ATIVA (MANUTENÇÃO)": "ATIVA",
    "ATIVO (MANUTENÇÃO)": "ATIVA",
    "INATIVA": "INATIVA",
    "INATIVO": "INATIVA",  # Normaliza INATIVO para INATIVA
    "BAIXA": "BAIXA",
    "BAIXADA": "BAIXA",
    "DEVOLVIDA": "DEVOLVIDA",
    "SUSPENSA": "SUSPENSA",
    "SUSPENSA RFB": "SUSPENSA",  # Variação
    "SUSPENSA-RFB": "SUSPENSA",
    "SUSPENSA_RFB": "SUSPENSA",
    "SUSPENSA (MANUTENÇÃO)": "SUSPENSA",
    "SUSPENSA MANUTENÇÃO": "SUSPENSA",
    "SUSPENSA (LEGALIZAÇÃO)": "SUSPENSA",
    "SUSPENSA LEGALIZAÇÃO": "SUSPENSA",
    

    # Regimes como status (quando aparecem na coluna de status)
    "SN": "SN",
    "SN-EXCEDENTE": "SN-EXCEDENTE",  # Variação
    "SN EXCEDENTE": "SN-EXCEDENTE",
    "LP": "LP",
    "LR": "LR",  # Lucro Real = Lucro Presumido para simplificar
    "LR-NUCLEO": "LR-NUCLEO",  # Variação
    "LR NUCLEO": "LR-NUCLEO",
    "LP-NUCLEO": "LP-NUCLEO",
    "LP NUCLEO": "LP-NUCLEO",
    "MEI": "MEI",
    "IGREJA": "IGREJA",
    "ISENTO": "ISENTO",
}

MAPEAMENTO_REGIME = {
    "SN": "SN",
    "SIMPLES NACIONAL": "SN",
    "SIMPLES": "SN",
    "SN-EXCEDENTE": "SN-EXCEDENTE",
    "SN EXCEDENTE": "SN-EXCEDENTE",

    "LP": "LP",
    "LUCRO PRESUMIDO": "LP",
    "LR": "LR",
    "LUCRO REAL": "LR",
    "LR-NUCLEO": "LR-NUCLEO",
    "LR NUCLEO": "LR-NUCLEO",
    "LP-NUCLEO": "LP-NUCLEO",
    "LP NUCLEO": "LP-NUCLEO",

    "MEI": "MEI",
    "MICROEMPREENDEDOR": "MEI",

    "IGREJA": "IGREJA",
    "RELIGIOSO": "IGREJA",
    "ORGANIZACAO RELIGIOSA": "IGREJA",

    "ISENTO": "ISENTO",
    "ISENTA": "ISENTO",
}

def normalizar_status(valor):
    """Normaliza variações de status para valores padrão."""
    if not valor:
        return ""
    valor_upper = str(valor).upper().strip()
    return MAPEAMENTO_STATUS.get(valor_upper, valor_upper)

def normalizar_regime(valor):
    """Normaliza variações de regime tributário para valores padrão."""
    if not valor:
        return ""
    valor_upper = str(valor).upper().strip()
    return MAPEAMENTO_REGIME.get(valor_upper, valor_upper)

def eh_status_monitorado(status):
    """Verifica se o status é um dos monitorados (considerando variações)."""
    status_normalizado = normalizar_status(status)

    # Verifica se o status normalizado está na lista de monitorados
    return status_normalizado in STATUS_MONITORADOS

# === FUNÇÕES DE CONTROLE DE LOCKFILE ===
LOCKFILE_PATH = DATA_DIR / "bot_gerson.lock"

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
                        print(f"ERRO: Bot_Gerson já está em execução (PID: {old_pid})")
                        sys.exit(1)
                else:
                    os.kill(old_pid, 0)  # Não mata o processo, apenas verifica
                    logger.error(f"Bot já está rodando (PID: {old_pid}). Encerrando...")
                    print(f"ERRO: Bot_Gerson já está em execução (PID: {old_pid})")
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

# === FUNÇÕES DE CONTROLE DE PRIMEIRO CARREGAMENTO ===
def verificar_primeiro_carregamento():
    """Verifica se é o primeiro carregamento da aplicação."""
    flag_path = DATA_DIR / "primeiro_carregamento.flag"
    if flag_path.exists():
        logger.info("Primeiro carregamento já foi realizado. Notificações serão enviadas normalmente.")
        return True
    logger.info("Primeira execução detectada. Será feito um carregamento sem notificações.")
    return False

def marcar_primeiro_carregamento():
    """Marca que o primeiro carregamento foi concluído."""
    flag_path = DATA_DIR / "primeiro_carregamento.flag"
    try:
        flag_path.touch()
        logger.info("Primeiro carregamento finalizado. Flag criada.")
    except Exception as e:
        logger.error(f"Erro ao criar flag de primeiro carregamento: {e}")

# === BOT SETUP ===
class MyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.sheet_data = {}
        self.ultima_verificacao = None
        self.historico_alteracoes = {}  # Histórico de alterações por mês
        self.historico_suspensas = {}  # Histórico de empresas suspensas por semana
        self.ultimo_relatorio_enviado = None  # Data do último relatório enviado
        self.ultimo_relatorio_suspensas_enviado = None  # Data do último relatório semanal de suspensas
        self.primeiro_carregamento_completo = verificar_primeiro_carregamento()  # Flag de primeiro carregamento

    async def setup_hook(self):
        await self.tree.sync()
        print("Comandos sincronizados com sucesso!")

    async def on_ready(self):
        print(f"O Bot {self.user} está online!")
        logger.info(f"O Bot {self.user} está online!")

        # Inicializa Google Sheets em thread separada para não bloquear o loop
        def init_sheets():
            gc = gspread.authorize(
                Credentials.from_service_account_file(PATH_CREDENTIALS, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
            )
            return gc.open_by_key(GOOGLE_SHEET_ID).sheet1

        self.sheet = await asyncio.to_thread(init_sheets)

        # Carrega histórico de alterações
        self.historico_alteracoes = self.carregar_historico()

        # Carrega histórico de suspensas
        self.historico_suspensas = self.carregar_historico_suspensas()

        # Inicia tarefas em paralelo
        self.loop.create_task(self.monitorar_planilha())
        self.loop.create_task(self.verificar_relatorio_mensal())
        self.loop.create_task(self.verificar_relatorio_semanal_suspensas())

    async def on_member_join(self, member):
        """Envia mensagem de boas-vindas quando um novo membro entra no servidor."""
        logger.info(f"Novo membro entrou: {member} (ID: {getattr(member, 'id', 'unknown')})")
        try:
            canal = self.get_channel(DISCORD_CHANNEL_GENERAL)
            if canal:
                embed = discord.Embed(
                    title="👋 Seja bem-vindo(a) à Canella & Santos!",
                    description=(
                        f"Olá, {member.mention}! Seja bem-vindo(a) ao Discord oficial da **Canella & Santos**.\n\n"
                        "Este espaço é utilizado para comunicação interna, alertas importantes e alinhamentos entre as equipes.\n\n"
                        "📌 **Por onde começar:**\n"
                        "• Confira os comunicados em **#comunicado-financeiro**\n"
                        "• Acompanhe notificações em **#alerta-geral** e **#alertas-empresas**\n"
                        "• Utilize os canais do seu time, como **#time-canella**\n\n"
                        "📎 **Boas práticas:**\n"
                        "• Utilize cada canal conforme o tema\n"
                        "• Mantenha a comunicação clara e profissional\n"
                        "• Evite mensagens fora do contexto de trabalho\n\n"
                        "🆘 **Precisa de ajuda?**\n"
                        "Entre em contato com seu líder ou utilize os canais apropriados.\n\n"
                        "Desejamos uma excelente experiência e um ótimo trabalho!"
                    ),
                    color=0x4CAF50,
                )

                # Adiciona o logo como thumbnail
                logo_path = BOT_DIR / "logo_canella.jpg"
                if logo_path.exists():
                    file = discord.File(str(logo_path), filename="logo_canella.jpg")
                    embed.set_thumbnail(url="attachment://logo_canella.jpg")
                    embed.set_footer(text="Canella & Santos • Comunicação Interna")
                    await canal.send(file=file, embed=embed)
                else:
                    embed.set_footer(text="Canella & Santos • Comunicação Interna")
                    await canal.send(embed=embed)
                    logger.warning("Logo não encontrado, enviando embed sem imagem")

                logger.info(f"Mensagem de boas-vindas enviada para {member} (ID: {member.id})")
            else:
                logger.warning("Canal de boas-vindas (DISCORD_CHANNEL_ID) não encontrado.")
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem de boas-vindas: {e}")

    async def reconectar_sheets(self):
        """Reconecta ao Google Sheets em caso de erro de conexão."""
        try:
            logger.info("Tentando reconectar ao Google Sheets...")
            print("Reconectando ao Google Sheets...")

            def init_sheets():
                gc = gspread.authorize(
                    Credentials.from_service_account_file(PATH_CREDENTIALS, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
                )
                return gc.open_by_key(GOOGLE_SHEET_ID).sheet1

            self.sheet = await asyncio.to_thread(init_sheets)
            logger.info("Reconexão ao Google Sheets bem-sucedida!")
            print("Reconexão bem-sucedida!")
            return True
        except Exception as e:
            logger.error(f"Erro ao reconectar ao Google Sheets: {e}")
            print(f"Erro ao reconectar: {e}")
            return False

    async def monitorar_planilha(self):
        print("Monitorando planilha do Google Sheets...")
        logger.info("Monitorando planilha do Google Sheets...")
        print(f"ID da planilha: {GOOGLE_SHEET_ID}")
        logger.info(f"ID da planilha: {GOOGLE_SHEET_ID}")
        print("Modo: Verificação contínua a cada 2.5 minutos (TESTE)")
        logger.info("Modo: Verificação contínua a cada 2.5 minutos (TESTE)")

        # Carrega dados salvos, se existirem
        self.sheet_data = self.carregar_estado()

        # Contador de tentativas de reconexão
        tentativas_reconexao = 0
        MAX_TENTATIVAS_RECONEXAO = 3

        # === HORÁRIOS ESPECÍFICOS (COMENTADO PARA TESTES) ===
        # Descomente o bloco abaixo para ativar verificações apenas nos horários: 09:00, 11:00, 13:00, 15:00
        # HORARIOS_VERIFICACAO = [9, 11, 13, 15]
        # ultima_hora_verificada = None

        while True:
            try:
                agora = datetime.now()
                # hora_atual = agora.hour

                # === VERIFICAÇÃO POR HORÁRIOS ESPECÍFICOS (COMENTADO) ===
                # Descomente este bloco e comente o bloco "VERIFICAÇÃO CONTÍNUA" abaixo para usar horários
                # if hora_atual in HORARIOS_VERIFICACAO and ultima_hora_verificada != hora_atual:
                #     self.ultima_verificacao = agora.strftime('%d/%m/%Y %H:%M:%S')
                #     print(f"\n{'='*60}")
                #     print(f"Verificação agendada - {self.ultima_verificacao}")
                #     print(f"{'='*60}")
                #     logger.info(f"Verificação agendada - {self.ultima_verificacao}")

                # === VERIFICAÇÃO CONTÍNUA (ATIVO PARA TESTES) ===
                self.ultima_verificacao = agora.strftime('%d/%m/%Y %H:%M:%S')
                print(f"\nVerificando planilha... {self.ultima_verificacao}")
                logger.info(f"Verificando planilha... {self.ultima_verificacao}")

                # Executa a chamada síncrona em thread separada para não bloquear o loop
                data = await asyncio.to_thread(self.sheet.get_all_values)

                print(f"Dados obtidos com sucesso! ({len(data)} linhas)")
                logger.info(f"Dados obtidos com sucesso! ({len(data)} linhas)")
                novos_dados = {}
                if len(data) <= 1:  # Verifica se há dados além do cabeçalho
                    print("Planilha vazia ou contém apenas cabeçalho")
                    logger.warning("Planilha vazia ou contém apenas cabeçalho")
                    await asyncio.sleep(150)  # 2.5 minutos
                    continue

                # Pula a primeira linha (cabeçalho)
                for idx, row in enumerate(data[1:], start=2):  # start=2 porque idx 1 é o cabeçalho
                    # Verifica se a linha tem pelo menos as colunas essenciais (A, B, C)
                    if len(row) < 3:
                        continue

                    # A=0, B=1, C=2, D=3
                    codigo = row[0]  # Coluna A
                    nome = row[1]    # Coluna B
                    status = row[2]  # Coluna C
                    regime_tributario = row[3] if len(row) > 3 else ""  # Coluna D (opcional)

                    # Verifica campos obrigatórios (código, nome e status)
                    # Regime tributário é opcional e pode ser adicionado depois
                    if not all([codigo, nome, status]):
                        continue

                    codigo = str(codigo).strip()
                    nome = str(nome).strip()
                    status_bruto = str(status).upper().strip()
                    regime_bruto = str(regime_tributario).upper().strip()

                    # Normaliza os valores
                    status = normalizar_status(status_bruto)
                    regime_tributario = normalizar_regime(regime_bruto)

                    # Log se houver normalização
                    if status != status_bruto:
                        logger.info(f"Status normalizado: '{status_bruto}' -> '{status}' ({codigo})")
                    if regime_tributario != regime_bruto:
                        logger.info(f"Regime normalizado: '{regime_bruto}' -> '{regime_tributario}' ({codigo})")

                    # PROTEÇÃO: Se a empresa já existe e tinha regime, mas agora veio vazio da planilha
                    # mantém o regime anterior (leitura temporária incompleta do Sheets)
                    if codigo in self.sheet_data:
                        dados_anterior = self.sheet_data[codigo]
                        regime_anterior = dados_anterior.get("regime_tributario", "") if isinstance(dados_anterior, dict) else ""

                        # Se tinha regime antes e agora veio vazio, mantém o anterior
                        if regime_anterior and not regime_tributario:
                            logger.warning(f"Regime vazio detectado temporariamente para {codigo} - {nome} (era {regime_anterior}). Mantendo regime anterior.")
                            regime_tributario = regime_anterior

                    # Armazena em formato de dicionário (valores normalizados)
                    # Permite regime vazio para empresas novas sem regime ainda definido
                    novos_dados[codigo] = {
                        "status": status,
                        "regime_tributario": regime_tributario if regime_tributario else ""
                    }

                    # Verifica alterações ou novas empresas
                    if codigo in self.sheet_data:
                        dados_anterior = self.sheet_data[codigo]
                        status_anterior = dados_anterior.get("status") if isinstance(dados_anterior, dict) else dados_anterior
                        regime_anterior = dados_anterior.get("regime_tributario", "") if isinstance(dados_anterior, dict) else ""
                        
                        # Verifica mudança de status
                        if status != status_anterior:
                            print(f"\nAlteração detectada na linha {idx}:")
                            print(f"   Empresa: {codigo} - {nome}")
                            print(f"   Status anterior: {status_anterior}")
                            print(f"   Novo status: {status}")
                            logger.info(f"Alteração detectada na linha {idx}: {codigo} - {nome} ({status_anterior} -> {status})")

                            # Registra alteração no histórico
                            self.registrar_alteracao(
                                tipo="status",
                                codigo=codigo,
                                nome=nome,
                                valor_anterior=status_anterior,
                                valor_novo=status
                            )

                            # Notifica sobre status monitorado (problema)
                            if eh_status_monitorado(status):
                                await self.enviar_mensagem(codigo, nome, status)
                                # Registra empresa suspensa para relatório semanal
                                if status == "SUSPENSA":
                                    self.registrar_empresa_suspensa(codigo, nome)
                            # Notifica quando volta a ficar ATIVA (resolução)
                            elif status.upper() == "ATIVA" and eh_status_monitorado(status_anterior):
                                await self.enviar_mensagem_reativacao(codigo, nome, status_anterior)
                            else:
                                print(f"   Status não requer notificação: {status}")
                                logger.info(f"Status não requer notificação: {status}")
                        
                        # Verifica mudança de regime tributário
                        regime_anterior_valido = regime_anterior if regime_anterior else ""
                        regime_novo_valido = regime_tributario if regime_tributario else ""

                        if regime_novo_valido != regime_anterior_valido:
                            if regime_anterior_valido and regime_novo_valido:
                                # Mudança de regime (já tinha um regime antes e tem um novo diferente)
                                print(f"\nAlteração de Regime Tributário detectada na linha {idx}:")
                                print(f"   Empresa: {codigo} - {nome}")
                                print(f"   Regime anterior: {regime_anterior_valido}")
                                print(f"   Novo regime: {regime_novo_valido}")
                                logger.info(f"Alteração de regime tributário na linha {idx}: {codigo} - {nome} ({regime_anterior_valido} -> {regime_novo_valido})")

                                # Registra alteração no histórico
                                self.registrar_alteracao(
                                    tipo="regime_tributario",
                                    codigo=codigo,
                                    nome=nome,
                                    valor_anterior=regime_anterior_valido,
                                    valor_novo=regime_novo_valido
                                )

                                # NÃO notifica mudança de regime se o status atual for negativo
                                if self.primeiro_carregamento_completo:
                                    if eh_status_monitorado(status):
                                        logger.info(f"   Mudança de regime com status negativo ({status}): registrando sem notificar Discord")
                                        print(f"   Status negativo ({status}): não notificando mudança de regime")
                                    else:
                                        await self.enviar_mensagem_regime_tributario(codigo, nome, regime_anterior_valido, regime_novo_valido)
                            elif regime_novo_valido and not regime_anterior_valido:
                                # Regime definido pela primeira vez (empresa já existia, mas sem regime)
                                print(f"\nRegime tributário definido na linha {idx}:")
                                print(f"   Empresa: {codigo} - {nome}")
                                print(f"   Regime tributário: {regime_novo_valido}")
                                logger.info(f"Regime tributário definido: {codigo} - {nome} (Regime: {regime_novo_valido})")

                                # Registra no histórico
                                self.registrar_alteracao(
                                    tipo="regime_tributario",
                                    codigo=codigo,
                                    nome=nome,
                                    valor_anterior="Não definido",
                                    valor_novo=regime_novo_valido
                                )

                                # NÃO notifica definição de regime se o status atual for negativo
                                if self.primeiro_carregamento_completo:
                                    if eh_status_monitorado(status):
                                        logger.info(f"   Regime definido com status negativo ({status}): registrando sem notificar Discord")
                                        print(f"   Status negativo ({status}): não notificando definição de regime")
                                    else:
                                        await self.enviar_mensagem_regime_definido(codigo, nome, regime_novo_valido)
                    else:
                        # Nova empresa detectada
                        print(f"\nNova empresa detectada na linha {idx}:")
                        print(f"   Empresa: {codigo} - {nome}")
                        print(f"   Status inicial: {status}")
                        print(f"   Regime tributário: {regime_tributario if regime_tributario else 'Não definido'}")
                        logger.info(f"Nova empresa detectada na linha {idx}: {codigo} - {nome} (Status: {status}, Regime: {regime_tributario if regime_tributario else 'Não definido'})")

                        # Só envia notificação se não for o primeiro carregamento E se o status NÃO for negativo
                        if self.primeiro_carregamento_completo:
                            # NÃO notifica empresas novas com status negativo
                            # Empresas já criadas inativas/baixas/devolvidas/suspensas não precisam de notificação
                            if eh_status_monitorado(status):
                                logger.info(f"   Nova empresa com status negativo ({status}): registrando sem notificar Discord")
                                print(f"   Nova empresa com status negativo ({status}): apenas registrando")
                            else:
                                # Notifica apenas empresas novas com status ATIVA
                                await self.enviar_mensagem_nova_empresa(codigo, nome, status, regime_tributario)
                        else:
                            logger.info(f"   Primeira carga: anotando {codigo} sem notificar Discord")

                # FIM DO LOOP - Atualiza dados salvos APÓS processar TODAS as linhas
                # PROTEÇÃO: Não salva se os dados novos forem muito menores que os anteriores
                # (indica leitura incompleta/erro de conexão)
                dados_anteriores_count = len(self.sheet_data)
                dados_novos_count = len(novos_dados)

                if dados_anteriores_count > 0 and dados_novos_count < dados_anteriores_count * 0.5:
                    # Se os novos dados têm menos de 50% dos anteriores, provavelmente houve erro
                    logger.warning(f"PROTEÇÃO ATIVADA: Dados novos ({dados_novos_count}) muito menores que anteriores ({dados_anteriores_count}). NÃO salvando estado.")
                    print(f"⚠️ PROTEÇÃO: Leitura incompleta detectada ({dados_novos_count}/{dados_anteriores_count} registros). Estado NÃO será salvo.")
                    # Não atualiza self.sheet_data nem salva
                    await asyncio.sleep(150)
                    continue

                self.sheet_data = novos_dados
                await self.salvar_estado(novos_dados)

                # Se for a primeira carga, marca como completa APÓS salvar tudo
                if not self.primeiro_carregamento_completo:
                    marcar_primeiro_carregamento()
                    self.primeiro_carregamento_completo = True

                # === PARA HORÁRIOS ESPECÍFICOS (COMENTADO) ===
                # Descomente as linhas abaixo ao usar horários específicos
                # ultima_hora_verificada = hora_atual
                # print(f"{'='*60}")
                # print(f"Verificação concluída às {agora.strftime('%H:%M:%S')}")
                # print(f"Próxima verificação: {self._proxima_verificacao(hora_atual)}")
                # print(f"{'='*60}\n")
                # logger.info(f"Verificação concluída. Próxima: {self._proxima_verificacao(hora_atual)}")

            except gspread.exceptions.APIError as e:
                print(f"Erro de API do Google Sheets: {e}")
                logger.error(f"Erro de API do Google Sheets: {e}")
                # Tenta reconectar
                if tentativas_reconexao < MAX_TENTATIVAS_RECONEXAO:
                    tentativas_reconexao += 1
                    logger.warning(f"Tentativa de reconexão {tentativas_reconexao}/{MAX_TENTATIVAS_RECONEXAO}")
                    if await self.reconectar_sheets():
                        tentativas_reconexao = 0  # Reset em caso de sucesso
                else:
                    logger.error("Máximo de tentativas de reconexão atingido. Aguardando próximo ciclo...")
                    tentativas_reconexao = 0  # Reset para próximo ciclo

            except Exception as e:
                print(f"Erro ao monitorar planilha: {e}")
                logger.error(f"Erro ao monitorar planilha: {e}")
                # Verifica se é erro de conexão e tenta reconectar
                if "transport" in str(e).lower() or "connection" in str(e).lower() or "timeout" in str(e).lower():
                    logger.warning("Erro de conexão detectado. Tentando reconectar...")
                    await self.reconectar_sheets()

            # === MODO TESTE: Verifica a cada 2.5 minutos ===
            await asyncio.sleep(150)

            # === PARA HORÁRIOS ESPECÍFICOS (COMENTADO) ===
            # Descomente a linha abaixo e comente o asyncio.sleep(150) acima para usar horários
            # await asyncio.sleep(300)  # Verifica a cada 5 minutos se está na hora de executar


    # === Funções auxiliares ===
    def _proxima_verificacao(self, hora_atual):
        """Calcula o horário da próxima verificação."""
        HORARIOS_VERIFICACAO = [9, 11, 13, 15]
        for hora in HORARIOS_VERIFICACAO:
            if hora > hora_atual:
                return f"{hora:02d}:00"
        # Se passou de todas as horas de hoje, retorna a primeira de amanhã
        return "09:00 (amanhã)"

    def carregar_estado(self):
        caminho = DATA_DIR / "estado_empresas.json"
        if caminho.exists():
            try:
                with open(caminho, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                    ultima_verificacao = dados.get("ultima_verificacao", "Nunca")
                    registros = dados.get("registros", {})
                    print(f"Estado carregado ({len(registros)} registros).")
                    print(f"Última verificação: {ultima_verificacao}")
                    return registros
            except Exception as e:
                print(f"Erro ao carregar estado: {e}")
        print("Nenhum estado salvo encontrado. Criando novo...")
        return {}

    async def salvar_estado(self, dados):
        """Salva o estado em arquivo de forma assíncrona."""
        caminho = DATA_DIR / "estado_empresas.json"

        def _salvar():
            estado_completo = {
                "ultima_verificacao": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                "registros": dados
            }
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(estado_completo, f, indent=4, ensure_ascii=False)

            # Backup automático
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = BACKUPS_DIR / f"estado_empresas_backup_{timestamp}.json"
            shutil.copy(caminho, backup_path)
            return estado_completo, backup_path

        try:
            estado_completo, backup_path = await asyncio.to_thread(_salvar)
            print(f"Estado salvo com sucesso em {estado_completo['ultima_verificacao']}")
            logger.info(f"Estado salvo com sucesso. Backup: {backup_path}")
        except Exception as e:
            print(f"Erro ao salvar estado: {e}")
            logger.error(f"Erro ao salvar estado: {e}")

    def carregar_historico(self):
        """Carrega o histórico de alterações mensal."""
        caminho = DATA_DIR / "historico_alteracoes.json"
        if caminho.exists():
            try:
                with open(caminho, "r", encoding="utf-8") as f:
                    historico = json.load(f)
                    print(f"Histórico carregado ({len(historico)} competências).")
                    logger.info(f"Histórico carregado ({len(historico)} competências).")
                    return historico
            except Exception as e:
                print(f"Erro ao carregar histórico: {e}")
                logger.error(f"Erro ao carregar histórico: {e}")
        return {}

    async def salvar_historico(self):
        """Salva o histórico de alterações de forma assíncrona."""
        caminho = DATA_DIR / "historico_alteracoes.json"

        def _salvar():
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(self.historico_alteracoes, f, indent=4, ensure_ascii=False)

        try:
            await asyncio.to_thread(_salvar)
            logger.info("Histórico salvo com sucesso.")
        except Exception as e:
            print(f"Erro ao salvar histórico: {e}")
            logger.error(f"Erro ao salvar histórico: {e}")

    def carregar_historico_suspensas(self):
        """Carrega o histórico de empresas suspensas por semana."""
        caminho = DATA_DIR / "historico_suspensas.json"
        if caminho.exists():
            try:
                with open(caminho, "r", encoding="utf-8") as f:
                    historico = json.load(f)
                    print(f"Histórico de suspensas carregado ({len(historico)} semanas).")
                    logger.info(f"Histórico de suspensas carregado ({len(historico)} semanas).")
                    return historico
            except Exception as e:
                print(f"Erro ao carregar histórico de suspensas: {e}")
                logger.error(f"Erro ao carregar histórico de suspensas: {e}")
        return {}

    async def salvar_historico_suspensas(self):
        """Salva o histórico de empresas suspensas de forma assíncrona."""
        caminho = DATA_DIR / "historico_suspensas.json"

        def _salvar():
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(self.historico_suspensas, f, indent=4, ensure_ascii=False)

        try:
            await asyncio.to_thread(_salvar)
            logger.info("Histórico de suspensas salvo com sucesso.")
        except Exception as e:
            print(f"Erro ao salvar histórico de suspensas: {e}")
            logger.error(f"Erro ao salvar histórico de suspensas: {e}")

    def _obter_semana_ano(self, data=None):
        """Retorna a chave da semana no formato YYYY-WNN (ex: 2025-W01)."""
        if data is None:
            data = datetime.now()
        # isocalendar retorna (ano, numero_semana, dia_da_semana)
        ano_iso, semana_iso, _ = data.isocalendar()
        return f"{ano_iso}-W{semana_iso:02d}"

    def registrar_empresa_suspensa(self, codigo, nome):
        """Registra uma empresa suspensa no histórico semanal."""
        agora = datetime.now()
        semana = self._obter_semana_ano(agora)

        if semana not in self.historico_suspensas:
            self.historico_suspensas[semana] = {
                "empresas": [],
                "total": 0
            }

        # Verifica se a empresa já foi registrada nesta semana
        empresas_codigos = [e["codigo"] for e in self.historico_suspensas[semana]["empresas"]]
        if codigo not in empresas_codigos:
            self.historico_suspensas[semana]["empresas"].append({
                "codigo": codigo,
                "nome": nome,
                "data_hora": agora.strftime("%d/%m/%Y %H:%M:%S")
            })
            self.historico_suspensas[semana]["total"] += 1

            # Agenda o salvamento do histórico (não bloqueia)
            asyncio.create_task(self.salvar_historico_suspensas())

            logger.info(f"Empresa suspensa registrada: {codigo} - {nome} (Semana: {semana})")
        else:
            logger.info(f"Empresa {codigo} já registrada como suspensa nesta semana ({semana})")

    def registrar_alteracao(self, tipo, codigo, nome, valor_anterior, valor_novo):
        """Registra uma alteração no histórico mensal."""
        agora = datetime.now()
        competencia = agora.strftime("%Y-%m")  # Formato: 2025-01

        if competencia not in self.historico_alteracoes:
            self.historico_alteracoes[competencia] = {
                "alteracoes": [],
                "estatisticas": {
                    "total_alteracoes": 0,
                    "alteracoes_status": 0,
                    "alteracoes_regime": 0
                }
            }

        alteracao = {
            "tipo": tipo,
            "codigo": codigo,
            "nome": nome,
            "valor_anterior": valor_anterior,
            "valor_novo": valor_novo,
            "data_hora": agora.strftime("%d/%m/%Y %H:%M:%S")
        }

        self.historico_alteracoes[competencia]["alteracoes"].append(alteracao)
        self.historico_alteracoes[competencia]["estatisticas"]["total_alteracoes"] += 1

        if tipo == "status":
            self.historico_alteracoes[competencia]["estatisticas"]["alteracoes_status"] += 1
        elif tipo == "regime_tributario":
            self.historico_alteracoes[competencia]["estatisticas"]["alteracoes_regime"] += 1

        # Agenda o salvamento do histórico (não bloqueia)
        asyncio.create_task(self.salvar_historico())

        logger.info(f"Alteração registrada: {tipo} - {codigo} - {nome} (Competência: {competencia})")

    async def verificar_relatorio_mensal(self):
        """Verifica diariamente se deve enviar o relatório mensal."""
        await self.wait_until_ready()
        print(f"Sistema de relatório mensal iniciado (Dia configurado: {DIA_RELATORIO_MENSAL}, Horário: 09:00)")
        logger.info(f"Sistema de relatório mensal iniciado (Dia configurado: {DIA_RELATORIO_MENSAL}, Horário: 09:00)")

        while not self.is_closed():
            try:
                agora = datetime.now()

                # Verifica se é o dia de enviar o relatório
                if agora.day == DIA_RELATORIO_MENSAL:
                    # Verifica se ainda não enviou hoje e se já são 9 horas da manhã
                    if self.ultimo_relatorio_enviado != agora.date() and agora.hour == 9:
                        print(f"\n{'='*60}")
                        print(f"Gerando relatório mensal automático...")
                        print(f"{'='*60}")
                        logger.info("Gerando relatório mensal automático...")

                        # Envia relatório do mês anterior
                        mes_anterior = (agora.replace(day=1) - timedelta(days=1))
                        competencia = mes_anterior.strftime("%Y-%m")

                        await self.enviar_relatorio_mensal(competencia)
                        self.ultimo_relatorio_enviado = agora.date()

                        print(f"{'='*60}")
                        print(f"Relatório mensal enviado com sucesso!")
                        print(f"Competência: {competencia}")
                        print(f"{'='*60}\n")
                        logger.info(f"Relatório mensal enviado! Competência: {competencia}")

            except Exception as e:
                print(f"Erro ao verificar relatório mensal: {e}")
                logger.error(f"Erro ao verificar relatório mensal: {e}")

            # Verifica a cada 30 minutos (mais frequente para garantir que pega às 09:00)
            await asyncio.sleep(1800)

    async def verificar_relatorio_semanal_suspensas(self):
        """Verifica se deve enviar o relatório semanal de empresas suspensas (toda segunda-feira às 08:30)."""
        await self.wait_until_ready()
        print("Sistema de relatório semanal de suspensas iniciado (Segunda-feira às 08:30)")
        logger.info("Sistema de relatório semanal de suspensas iniciado (Segunda-feira às 08:30)")

        while not self.is_closed():
            try:
                agora = datetime.now()

                # Verifica se é segunda-feira (weekday() == 0)
                if agora.weekday() == 0:
                    # Verifica se ainda não enviou hoje e se já são 8:30
                    if self.ultimo_relatorio_suspensas_enviado != agora.date():
                        if agora.hour == 8 and agora.minute >= 30:
                            print(f"\n{'='*60}")
                            print(f"Gerando relatório semanal de empresas suspensas...")
                            print(f"{'='*60}")
                            logger.info("Gerando relatório semanal de empresas suspensas...")

                            # Envia relatório da semana anterior
                            semana_anterior = self._obter_semana_ano(agora - timedelta(days=7))

                            await self.enviar_relatorio_semanal_suspensas(semana_anterior)
                            self.ultimo_relatorio_suspensas_enviado = agora.date()

                            print(f"{'='*60}")
                            print(f"Relatório semanal de suspensas enviado com sucesso!")
                            print(f"Semana: {semana_anterior}")
                            print(f"{'='*60}\n")
                            logger.info(f"Relatório semanal de suspensas enviado! Semana: {semana_anterior}")

            except Exception as e:
                print(f"Erro ao verificar relatório semanal de suspensas: {e}")
                logger.error(f"Erro ao verificar relatório semanal de suspensas: {e}")

            # Verifica a cada 15 minutos para garantir que pega às 08:30
            await asyncio.sleep(900)

    async def enviar_relatorio_semanal_suspensas(self, semana):
        """Envia o relatório semanal de empresas suspensas."""
        canal = self.get_channel(DISCORD_SUSPENSE_CHANNEL_ID)

        if not canal:
            logger.error("Canal de suspensas não encontrado para envio do relatório semanal")
            print("ERRO: Canal de suspensas não encontrado")
            return

        if semana not in self.historico_suspensas:
            print(f"Nenhuma empresa suspensa registrada para a semana {semana}")
            logger.info(f"Sem empresas suspensas para relatório: {semana}")

            # Envia mensagem informando que não houve suspensões
            embed = discord.Embed(
                title=f"Relatório Semanal de Empresas Suspensas",
                description=f"**Semana: {semana}**\n\nNenhuma empresa foi suspensa nesta semana.",
                color=0x4CAF50  # Verde - bom sinal
            )
            embed.set_footer(text="Canella & Santos • Comunicação Interna")
            await canal.send("@everyone", embed=embed)
            return

        dados = self.historico_suspensas[semana]
        empresas = dados["empresas"]
        total = dados["total"]

        # Cria o embed principal
        embed = discord.Embed(
            title=f"Relatório Semanal de Empresas Suspensas",
            description=f"**Semana: {semana}**\n\nResumo das empresas que tiveram o status alterado para SUSPENSA durante a semana.",
            color=0xE91E63  # Rosa - cor de suspensa
        )

        # Aviso importante sobre atendimento
        embed.add_field(
            name="ATENÇÃO - Procedimento de Atendimento",
            value="Caso algum cliente dessas empresas entre em contato pelo Messenger ou qualquer outro canal solicitando algum serviço, "
                  "**o mesmo deve ser informado sobre o bloqueio no sistema** e **encaminhado imediatamente ao setor financeiro** "
                  "para regularização da situação antes de qualquer atendimento.",
            inline=False
        )

        # Estatísticas gerais
        embed.add_field(
            name="Total de Empresas Suspensas",
            value=f"**{total}** empresa{'s' if total > 1 else ''}",
            inline=False
        )

        # Lista as empresas (limita a 15 no embed para não exceder limite)
        empresas_texto = []
        for i, emp in enumerate(empresas):
            if i >= 15:
                empresas_texto.append(f"\n_... e mais {total - 15} empresas_")
                break
            empresas_texto.append(f"• **{emp['codigo']}** - {emp['nome']}\n  └ {emp['data_hora']}")

        if empresas_texto:
            # Verifica se o texto excede o limite do Discord (1024 caracteres por field)
            texto_empresas = "\n".join(empresas_texto)
            if len(texto_empresas) <= 1024:
                embed.add_field(
                    name="Empresas Suspensas",
                    value=texto_empresas,
                    inline=False
                )
            else:
                # Divide em múltiplos fields se necessário
                partes = []
                parte_atual = []
                tamanho_atual = 0

                for linha in empresas_texto:
                    if tamanho_atual + len(linha) + 1 > 1000:
                        partes.append("\n".join(parte_atual))
                        parte_atual = [linha]
                        tamanho_atual = len(linha)
                    else:
                        parte_atual.append(linha)
                        tamanho_atual += len(linha) + 1

                if parte_atual:
                    partes.append("\n".join(parte_atual))

                for idx, parte in enumerate(partes[:3]):  # Máximo 3 fields
                    embed.add_field(
                        name=f"Empresas Suspensas {f'(Parte {idx+1})' if len(partes) > 1 else ''}",
                        value=parte,
                        inline=False
                    )

        embed.add_field(
            name="Ação Necessária",
            value="Verifique a situação de cada empresa e tome as providências necessárias para regularização.",
            inline=False
        )

        # Calcula a data do próximo relatório (próxima segunda-feira às 08:30)
        agora = datetime.now()
        dias_ate_segunda = (7 - agora.weekday()) % 7
        if dias_ate_segunda == 0:
            dias_ate_segunda = 7  # Se hoje é segunda, próximo é semana que vem
        proxima_segunda = agora + timedelta(days=dias_ate_segunda)
        proximo_relatorio = proxima_segunda.strftime("%d/%m/%Y") + " às 08:30"

        embed.add_field(
            name="📅 Próximo Relatório",
            value=f"**{proximo_relatorio}**",
            inline=False
        )

        embed.set_footer(text=f"Canella & Santos • Semana: {semana}")

        # Envia mensagem de alerta antes do embed
        mensagem_alerta = (
            "@everyone\n"
            "🚨 **RELATÓRIO SEMANAL DE EMPRESAS SUSPENSAS** 🚨\n\n"
            "⚠️ Atenção equipe! Segue o relatório semanal com todas as empresas que foram suspensas. "
            "Verifiquem com atenção antes de realizar qualquer atendimento!"
        )
        await canal.send(mensagem_alerta)
        await canal.send(embed=embed)
        logger.info(f"Relatório semanal de suspensas enviado: {semana}")

        # Se houver muitas empresas, envia também um PDF detalhado
        if total > 10:
            await self.enviar_relatorio_suspensas_pdf(canal, semana, empresas)

    async def enviar_relatorio_suspensas_pdf(self, canal, semana, empresas):
        """Gera e envia relatório de empresas suspensas em PDF."""
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import cm

            # Cria o arquivo PDF
            pdf_filename = DATA_DIR / f"relatorio_suspensas_{semana}.pdf"
            doc = SimpleDocTemplate(
                str(pdf_filename),
                pagesize=A4,
                title=f"Relatório Semanal de Suspensas - {semana} - Canella & Santos",
                author="Canella & Santos Contabilidade",
                subject="Relatório Semanal de Empresas Suspensas"
            )
            elements = []

            # Estilos
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=16,
                textColor=colors.HexColor('#E91E63'),
                spaceAfter=30,
                alignment=1  # Center
            )

            heading_style = ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading2'],
                fontSize=12,
                textColor=colors.HexColor('#C2185B'),
                spaceAfter=12,
            )

            # Estilo para aviso
            aviso_style = ParagraphStyle(
                'AvisoStyle',
                parent=styles['Normal'],
                fontSize=9,
                textColor=colors.HexColor('#C2185B'),
                spaceAfter=12,
                borderColor=colors.HexColor('#E91E63'),
                borderWidth=1,
                borderPadding=8,
                backColor=colors.HexColor('#FCE4EC'),
            )

            # Título
            elements.append(Paragraph(f"RELATÓRIO SEMANAL DE EMPRESAS SUSPENSAS", title_style))
            elements.append(Paragraph(f"Semana: {semana}", styles['Normal']))
            elements.append(Paragraph(f"CANELLA & SANTOS CONTABILIDADE EIRELI", styles['Normal']))
            elements.append(Spacer(1, 0.5*cm))

            # Aviso importante
            aviso_texto = (
                "<b>ATENÇÃO - PROCEDIMENTO DE ATENDIMENTO:</b><br/>"
                "Caso algum cliente dessas empresas entre em contato pelo Messenger ou qualquer outro canal "
                "solicitando algum serviço, o mesmo deve ser informado sobre o bloqueio no sistema e "
                "encaminhado imediatamente ao setor financeiro para regularização da situação antes de qualquer atendimento."
            )
            elements.append(Paragraph(aviso_texto, aviso_style))
            elements.append(Spacer(1, 0.5*cm))

            # Estatísticas gerais
            elements.append(Paragraph("RESUMO", heading_style))
            stats_data = [
                ['Total de Empresas Suspensas', str(len(empresas))],
            ]
            stats_table = Table(stats_data, colWidths=[12*cm, 5*cm])
            stats_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FCE4EC')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E91E63'))
            ]))
            elements.append(stats_table)
            elements.append(Spacer(1, 0.5*cm))

            # Lista de empresas
            elements.append(Paragraph("EMPRESAS SUSPENSAS", heading_style))
            elements.append(Spacer(1, 0.3*cm))

            # Tabela de empresas
            data = [['Código', 'Nome da Empresa', 'Data/Hora da Suspensão']]

            for emp in empresas:
                data.append([
                    emp['codigo'],
                    emp['nome'][:40] + ('...' if len(emp['nome']) > 40 else ''),
                    emp['data_hora']
                ])

            table = Table(data, colWidths=[3*cm, 9*cm, 5*cm])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E91E63')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#FCE4EC')),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#FCE4EC'), colors.HexColor('#F8BBD9')])
            ]))
            elements.append(table)
            elements.append(Spacer(1, 0.5*cm))

            # Rodapé
            elements.append(Paragraph(
                f"Relatório gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
                styles['Normal']
            ))

            # Gera o PDF
            def _gerar_pdf():
                doc.build(elements)

            await asyncio.to_thread(_gerar_pdf)

            # Envia o arquivo
            await canal.send(
                "📄 Relatório detalhado em PDF:",
                file=discord.File(str(pdf_filename))
            )

            logger.info(f"Relatório de suspensas em PDF enviado: {semana}")
            print(f"Relatório de suspensas em PDF enviado: {pdf_filename}")

        except ImportError:
            logger.warning("ReportLab não instalado. Não foi possível gerar PDF de suspensas.")
            await canal.send("⚠️ PDF não disponível: ReportLab não instalado.")
        except Exception as e:
            logger.error(f"Erro ao gerar relatório de suspensas em PDF: {e}")
            print(f"Erro ao gerar relatório de suspensas: {e}")

    async def enviar_relatorio_mensal(self, competencia):
        """Envia o relatório mensal de alterações."""
        canal = self.get_channel(DISCORD_CHANNEL_ID)

        if not canal:
            logger.error("Canal do Discord não encontrado para envio do relatório mensal")
            print("ERRO: Canal do Discord não encontrado")
            return

        if competencia not in self.historico_alteracoes:
            print(f"Nenhuma alteração registrada para a competência {competencia}")
            logger.warning(f"Sem alterações para relatório: {competencia}")

            # Envia mensagem informando que não houve alterações
            embed = discord.Embed(
                title=f"📊 Relatório Mensal - {competencia}",
                description=f"Nenhuma alteração registrada nesta competência.",
                color=0x9E9E9E
            )
            embed.set_footer(text="Canella & Santos • Comunicação Interna")
            await canal.send("@everyone", embed=embed)
            return

        dados = self.historico_alteracoes[competencia]
        alteracoes = dados["alteracoes"]
        stats = dados["estatisticas"]

        # Formata a competência para exibição
        data_comp = datetime.strptime(competencia, "%Y-%m")
        mes_nome = data_comp.strftime("%B/%Y").upper()
        mes_nome_pt = {
            "JANUARY": "JANEIRO", "FEBRUARY": "FEVEREIRO", "MARCH": "MARÇO",
            "APRIL": "ABRIL", "MAY": "MAIO", "JUNE": "JUNHO",
            "JULY": "JULHO", "AUGUST": "AGOSTO", "SEPTEMBER": "SETEMBRO",
            "OCTOBER": "OUTUBRO", "NOVEMBER": "NOVEMBRO", "DECEMBER": "DEZEMBRO"
        }
        for en, pt in mes_nome_pt.items():
            mes_nome = mes_nome.replace(en, pt)

        # Cria o embed principal
        embed = discord.Embed(
            title=f"Relatório Mensal - {mes_nome}",
            description=f"Resumo das alterações registradas no período",
            color=0x2196F3
        )

        # Estatísticas gerais
        embed.add_field(
            name="Estatísticas Gerais",
            value=f"**Total de Alterações:** {stats['total_alteracoes']}\n"
                  f"**Alterações de Status:** {stats['alteracoes_status']}\n"
                  f"**Alterações de Regime:** {stats['alteracoes_regime']}",
            inline=False
        )

        # Agrupa alterações por empresa
        empresas_alteradas = {}
        for alt in alteracoes:
            codigo = alt["codigo"]
            if codigo not in empresas_alteradas:
                empresas_alteradas[codigo] = {
                    "nome": alt["nome"],
                    "alteracoes": []
                }
            empresas_alteradas[codigo]["alteracoes"].append(alt)

        # Lista as empresas com alterações (limita a 10 no embed)
        empresas_texto = []
        for i, (codigo, dados_emp) in enumerate(empresas_alteradas.items()):
            if i >= 10:
                empresas_texto.append(f"\n_... e mais {len(empresas_alteradas) - 10} empresas_")
                break

            num_alt = len(dados_emp["alteracoes"])
            empresas_texto.append(f"**{codigo}** - {dados_emp['nome']} ({num_alt} alteração{'ões' if num_alt > 1 else ''})")

        if empresas_texto:
            embed.add_field(
                name=f"Empresas Alteradas ({len(empresas_alteradas)})",
                value="\n".join(empresas_texto),
                inline=False
            )

        embed.set_footer(text=f"Canella & Santos • Competência: {competencia}")

        await canal.send("@everyone", embed=embed)
        logger.info(f"Relatório mensal enviado: {competencia}")

        # Sempre gera e envia o PDF detalhado
        await self.enviar_relatorio_detalhado(canal, competencia, alteracoes, empresas_alteradas)

    async def enviar_relatorio_anual(self, canal, ano, competencias_ano):
        """Envia o relatório anual consolidado de alterações."""

        if not canal:
            logger.error("Canal do Discord não encontrado para envio do relatório anual")
            print("ERRO: Canal do Discord não encontrado")
            return

        # Consolida dados de todas as competências do ano
        total_alteracoes = 0
        total_alteracoes_status = 0
        total_alteracoes_regime = 0
        todas_alteracoes = []
        empresas_alteradas_ano = {}

        for competencia in sorted(competencias_ano):
            dados = self.historico_alteracoes[competencia]
            stats = dados["estatisticas"]
            alteracoes = dados["alteracoes"]

            total_alteracoes += stats["total_alteracoes"]
            total_alteracoes_status += stats["alteracoes_status"]
            total_alteracoes_regime += stats["alteracoes_regime"]
            todas_alteracoes.extend(alteracoes)

            # Agrupa empresas
            for alt in alteracoes:
                codigo = alt["codigo"]
                if codigo not in empresas_alteradas_ano:
                    empresas_alteradas_ano[codigo] = {
                        "nome": alt["nome"],
                        "alteracoes": []
                    }
                empresas_alteradas_ano[codigo]["alteracoes"].append(alt)

        # Cria o embed principal
        embed = discord.Embed(
            title=f"📊 Relatório Anual - {ano}",
            description=f"Resumo consolidado de todas as alterações do ano",
            color=0x2196F3
        )

        # Estatísticas gerais
        embed.add_field(
            name="Estatísticas Gerais",
            value=f"**Total de Alterações:** {total_alteracoes}\n"
                  f"**Alterações de Status:** {total_alteracoes_status}\n"
                  f"**Alterações de Regime:** {total_alteracoes_regime}\n"
                  f"**Empresas Afetadas:** {len(empresas_alteradas_ano)}\n"
                  f"**Meses com Alterações:** {len(competencias_ano)}",
            inline=False
        )

        # Resumo por mês
        resumo_meses = []
        mes_nome_pt = {
            "JANUARY": "JAN", "FEBRUARY": "FEV", "MARCH": "MAR",
            "APRIL": "ABR", "MAY": "MAI", "JUNE": "JUN",
            "JULY": "JUL", "AUGUST": "AGO", "SEPTEMBER": "SET",
            "OCTOBER": "OUT", "NOVEMBER": "NOV", "DECEMBER": "DEZ"
        }

        for competencia in sorted(competencias_ano):
            dados = self.historico_alteracoes[competencia]
            stats = dados["estatisticas"]
            data_comp = datetime.strptime(competencia, "%Y-%m")
            mes_nome = data_comp.strftime("%B").upper()
            mes_abrev = mes_nome_pt.get(mes_nome, mes_nome[:3])

            resumo_meses.append(f"**{mes_abrev}:** {stats['total_alteracoes']} alterações")

        if resumo_meses:
            # Divide em colunas se houver muitos meses
            if len(resumo_meses) > 6:
                metade = len(resumo_meses) // 2
                embed.add_field(
                    name="Resumo por Mês (1º Semestre)",
                    value="\n".join(resumo_meses[:metade]),
                    inline=True
                )
                embed.add_field(
                    name="Resumo por Mês (2º Semestre)",
                    value="\n".join(resumo_meses[metade:]),
                    inline=True
                )
            else:
                embed.add_field(
                    name="Resumo por Mês",
                    value="\n".join(resumo_meses),
                    inline=False
                )

        # Top 10 empresas com mais alterações
        empresas_ordenadas = sorted(
            empresas_alteradas_ano.items(),
            key=lambda x: len(x[1]["alteracoes"]),
            reverse=True
        )

        top_empresas = []
        for i, (codigo, dados_emp) in enumerate(empresas_ordenadas[:10]):
            num_alt = len(dados_emp["alteracoes"])
            top_empresas.append(f"{i+1}. **{codigo}** - {dados_emp['nome'][:30]}... ({num_alt}x)")

        if top_empresas:
            embed.add_field(
                name="Top 10 Empresas com Mais Alterações",
                value="\n".join(top_empresas),
                inline=False
            )

        embed.set_footer(text=f"Canella & Santos • Ano: {ano}")

        await canal.send("@everyone", embed=embed)
        logger.info(f"Relatório anual enviado: {ano}")

        # Sempre gera e envia o PDF detalhado anual
        await self.enviar_relatorio_anual_detalhado(canal, ano, todas_alteracoes, empresas_alteradas_ano, competencias_ano)

    async def enviar_relatorio_detalhado(self, canal, competencia, alteracoes, empresas_alteradas):
        """Gera e envia relatório detalhado em PDF com todas as alterações."""
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import cm

            # Formata a competência para exibição
            data_comp = datetime.strptime(competencia, "%Y-%m")
            mes_nome = data_comp.strftime("%B/%Y").upper()
            mes_nome_pt = {
                "JANUARY": "JANEIRO", "FEBRUARY": "FEVEREIRO", "MARCH": "MARÇO",
                "APRIL": "ABRIL", "MAY": "MAIO", "JUNE": "JUNHO",
                "JULY": "JULHO", "AUGUST": "AGOSTO", "SEPTEMBER": "SETEMBRO",
                "OCTOBER": "OUTUBRO", "NOVEMBER": "NOVEMBRO", "DECEMBER": "DEZEMBRO"
            }
            for en, pt in mes_nome_pt.items():
                mes_nome = mes_nome.replace(en, pt)

            # Cria o arquivo PDF
            pdf_filename = DATA_DIR / f"relatorio_detalhado_{competencia}.pdf"
            doc = SimpleDocTemplate(
                str(pdf_filename),
                pagesize=A4,
                title=f"Relatório Mensal de Alterações - {mes_nome} - Canella & Santos",
                author="Canella & Santos Contabilidade",
                subject="Relatório Mensal de Alterações"
            )
            elements = []

            # Estilos
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=16,
                textColor=colors.HexColor('#2196F3'),
                spaceAfter=30,
                alignment=1  # Center
            )

            heading_style = ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading2'],
                fontSize=12,
                textColor=colors.HexColor('#1976D2'),
                spaceAfter=12,
            )

            # Título
            elements.append(Paragraph(f"RELATÓRIO DETALHADO DE ALTERAÇÕES", title_style))
            elements.append(Paragraph(f"Competência: {mes_nome}", styles['Normal']))
            elements.append(Paragraph(f"CANELLA & SANTOS CONTABILIDADE EIRELI", styles['Normal']))
            elements.append(Spacer(1, 0.5*cm))

            # Estatísticas gerais
            elements.append(Paragraph("ESTATÍSTICAS GERAIS", heading_style))
            stats_data = [
                ['Total de Alterações', str(len(alteracoes))],
                ['Empresas Afetadas', str(len(empresas_alteradas))],
                ['Alterações de Status', str(sum(1 for a in alteracoes if a['tipo'] == 'status'))],
                ['Alterações de Regime', str(sum(1 for a in alteracoes if a['tipo'] == 'regime_tributario'))],
            ]
            stats_table = Table(stats_data, colWidths=[12*cm, 5*cm])
            stats_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#E3F2FD')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#2196F3'))
            ]))
            elements.append(stats_table)
            elements.append(Spacer(1, 0.5*cm))

            # Detalhamento por empresa
            elements.append(Paragraph("DETALHAMENTO POR EMPRESA", heading_style))
            elements.append(Spacer(1, 0.3*cm))

            for codigo, dados_emp in sorted(empresas_alteradas.items()):
                # Nome da empresa
                elements.append(Paragraph(f"<b>{codigo}</b> - {dados_emp['nome']}", styles['Normal']))

                # Tabela de alterações dessa empresa
                alteracoes_emp = dados_emp['alteracoes']
                data = [['Tipo', 'De', 'Para', 'Data/Hora']]

                for alt in alteracoes_emp:
                    tipo_display = 'Status' if alt['tipo'] == 'status' else 'Regime'
                    data.append([
                        tipo_display,
                        str(alt['valor_anterior'])[:30],
                        str(alt['valor_novo'])[:30],
                        alt['data_hora']
                    ])

                table = Table(data, colWidths=[3*cm, 4*cm, 4*cm, 4.5*cm])
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2196F3')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))
                elements.append(table)
                elements.append(Spacer(1, 0.4*cm))

            # Gera o PDF
            def _gerar_pdf():
                doc.build(elements)

            await asyncio.to_thread(_gerar_pdf)

            # Envia o arquivo
            await canal.send(
                "📄 Relatório detalhado em PDF:",
                file=discord.File(str(pdf_filename))
            )

            logger.info(f"Relatório detalhado em PDF enviado: {competencia}")
            print(f"Relatório detalhado em PDF enviado: {pdf_filename}")

        except ImportError:
            # Se reportlab não estiver instalado, gera arquivo TXT como fallback
            logger.warning("ReportLab não instalado. Gerando relatório em TXT.")
            await self.enviar_relatorio_detalhado_txt(canal, competencia, alteracoes, empresas_alteradas)
        except Exception as e:
            logger.error(f"Erro ao gerar relatório detalhado em PDF: {e}")
            print(f"Erro ao gerar relatório detalhado: {e}")
            # Tenta enviar em TXT como fallback
            try:
                await self.enviar_relatorio_detalhado_txt(canal, competencia, alteracoes, empresas_alteradas)
            except Exception as e2:
                logger.error(f"Erro ao gerar relatório TXT de fallback: {e2}")

    async def enviar_relatorio_detalhado_txt(self, canal, competencia, alteracoes, empresas_alteradas):
        """Gera e envia relatório detalhado em TXT (fallback quando PDF não disponível)."""
        try:
            # Formata a competência para exibição
            data_comp = datetime.strptime(competencia, "%Y-%m")
            mes_nome = data_comp.strftime("%B/%Y").upper()
            mes_nome_pt = {
                "JANUARY": "JANEIRO", "FEBRUARY": "FEVEREIRO", "MARCH": "MARÇO",
                "APRIL": "ABRIL", "MAY": "MAIO", "JUNE": "JUNHO",
                "JULY": "JULHO", "AUGUST": "AGOSTO", "SEPTEMBER": "SETEMBRO",
                "OCTOBER": "OUTUBRO", "NOVEMBER": "NOVEMBRO", "DECEMBER": "DEZEMBRO"
            }
            for en, pt in mes_nome_pt.items():
                mes_nome = mes_nome.replace(en, pt)

            # Cria o conteúdo do arquivo TXT
            txt_filename = DATA_DIR / f"relatorio_detalhado_{competencia}.txt"

            def _gerar_txt():
                with open(txt_filename, 'w', encoding='utf-8') as f:
                    f.write("="*80 + "\n")
                    f.write("RELATÓRIO DETALHADO DE ALTERAÇÕES\n")
                    f.write(f"Competência: {mes_nome}\n")
                    f.write("CANELLA & SANTOS CONTABILIDADE EIRELI\n")
                    f.write("="*80 + "\n\n")

                    # Estatísticas
                    f.write("ESTATÍSTICAS GERAIS\n")
                    f.write("-"*80 + "\n")
                    f.write(f"Total de Alterações: {len(alteracoes)}\n")
                    f.write(f"Empresas Afetadas: {len(empresas_alteradas)}\n")
                    f.write(f"Alterações de Status: {sum(1 for a in alteracoes if a['tipo'] == 'status')}\n")
                    f.write(f"Alterações de Regime: {sum(1 for a in alteracoes if a['tipo'] == 'regime_tributario')}\n")
                    f.write("\n" + "="*80 + "\n\n")

                    # Detalhamento por empresa
                    f.write("DETALHAMENTO POR EMPRESA\n")
                    f.write("="*80 + "\n\n")

                    for codigo, dados_emp in sorted(empresas_alteradas.items()):
                        f.write(f"Empresa: {codigo} - {dados_emp['nome']}\n")
                        f.write("-"*80 + "\n")

                        for alt in dados_emp['alteracoes']:
                            tipo_display = 'Status' if alt['tipo'] == 'status' else 'Regime Tributário'
                            f.write(f"  • Tipo: {tipo_display}\n")
                            f.write(f"    De: {alt['valor_anterior']}\n")
                            f.write(f"    Para: {alt['valor_novo']}\n")
                            f.write(f"    Data/Hora: {alt['data_hora']}\n")
                            f.write("\n")

                        f.write("\n")

                    f.write("="*80 + "\n")
                    f.write(f"Relatório gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")

            await asyncio.to_thread(_gerar_txt)

            # Envia o arquivo
            await canal.send(
                "📄 Relatório detalhado em TXT:",
                file=discord.File(str(txt_filename))
            )

            logger.info(f"Relatório detalhado em TXT enviado: {competencia}")
            print(f"Relatório detalhado em TXT enviado: {txt_filename}")

        except Exception as e:
            logger.error(f"Erro ao gerar relatório detalhado em TXT: {e}")
            print(f"Erro ao gerar relatório detalhado TXT: {e}")

    async def enviar_relatorio_anual_detalhado(self, canal, ano, alteracoes, empresas_alteradas, competencias):
        """Gera e envia relatório anual detalhado em PDF com todas as alterações do ano."""
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import cm

            # Cria o arquivo PDF
            pdf_filename = DATA_DIR / f"relatorio_anual_{ano}.pdf"
            doc = SimpleDocTemplate(
                str(pdf_filename),
                pagesize=A4,
                title=f"Relatório Anual de Alterações - {ano} - Canella & Santos",
                author="Canella & Santos Contabilidade",
                subject="Relatório Anual de Alterações"
            )
            elements = []

            # Estilos
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=18,
                textColor=colors.HexColor('#2196F3'),
                spaceAfter=30,
                alignment=1  # Center
            )

            heading_style = ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading2'],
                fontSize=14,
                textColor=colors.HexColor('#1976D2'),
                spaceAfter=12,
            )

            subheading_style = ParagraphStyle(
                'CustomSubHeading',
                parent=styles['Heading3'],
                fontSize=11,
                textColor=colors.HexColor('#0D47A1'),
                spaceAfter=8,
            )

            # Título
            elements.append(Paragraph(f"RELATÓRIO ANUAL DE ALTERAÇÕES - {ano}", title_style))
            elements.append(Paragraph(f"CANELLA & SANTOS CONTABILIDADE EIRELI", styles['Normal']))
            elements.append(Spacer(1, 0.5*cm))

            # Estatísticas gerais
            elements.append(Paragraph("ESTATÍSTICAS GERAIS", heading_style))
            stats_data = [
                ['Total de Alterações', str(len(alteracoes))],
                ['Empresas Afetadas', str(len(empresas_alteradas))],
                ['Alterações de Status', str(sum(1 for a in alteracoes if a['tipo'] == 'status'))],
                ['Alterações de Regime', str(sum(1 for a in alteracoes if a['tipo'] == 'regime_tributario'))],
                ['Meses com Alterações', str(len(competencias))],
            ]
            stats_table = Table(stats_data, colWidths=[13*cm, 4*cm])
            stats_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#E3F2FD')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#2196F3'))
            ]))
            elements.append(stats_table)
            elements.append(Spacer(1, 0.5*cm))

            # Resumo por mês
            elements.append(Paragraph("RESUMO POR MÊS", heading_style))
            mes_nome_pt = {
                "JANUARY": "JANEIRO", "FEBRUARY": "FEVEREIRO", "MARCH": "MARÇO",
                "APRIL": "ABRIL", "MAY": "MAIO", "JUNE": "JUNHO",
                "JULY": "JULHO", "AUGUST": "AGOSTO", "SEPTEMBER": "SETEMBRO",
                "OCTOBER": "OUTUBRO", "NOVEMBER": "NOVEMBRO", "DECEMBER": "DEZEMBRO"
            }

            resumo_data = [['Mês', 'Alterações', 'Status', 'Regime']]
            for competencia in sorted(competencias):
                dados = self.historico_alteracoes[competencia]
                stats = dados["estatisticas"]
                data_comp = datetime.strptime(competencia, "%Y-%m")
                mes_nome = data_comp.strftime("%B/%Y").upper()
                for en, pt in mes_nome_pt.items():
                    mes_nome = mes_nome.replace(en, pt)

                resumo_data.append([
                    mes_nome,
                    str(stats['total_alteracoes']),
                    str(stats['alteracoes_status']),
                    str(stats['alteracoes_regime'])
                ])

            resumo_table = Table(resumo_data, colWidths=[7*cm, 3.5*cm, 3.5*cm, 3*cm])
            resumo_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2196F3')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.beige, colors.lightgrey])
            ]))
            elements.append(resumo_table)
            elements.append(Spacer(1, 0.7*cm))

            # Detalhamento por empresa
            elements.append(Paragraph("DETALHAMENTO POR EMPRESA", heading_style))
            elements.append(Spacer(1, 0.3*cm))

            for codigo, dados_emp in sorted(empresas_alteradas.items()):
                # Nome da empresa
                elements.append(Paragraph(f"<b>{codigo}</b> - {dados_emp['nome']}", subheading_style))

                # Tabela de alterações dessa empresa
                alteracoes_emp = dados_emp['alteracoes']
                data = [['Tipo', 'De', 'Para', 'Data/Hora']]

                for alt in alteracoes_emp:
                    tipo_display = 'Status' if alt['tipo'] == 'status' else 'Regime'
                    data.append([
                        tipo_display,
                        str(alt['valor_anterior'])[:25],
                        str(alt['valor_novo'])[:25],
                        alt['data_hora']
                    ])

                table = Table(data, colWidths=[2.5*cm, 4.5*cm, 4.5*cm, 4.5*cm])
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2196F3')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black)
                ]))
                elements.append(table)
                elements.append(Spacer(1, 0.4*cm))

            # Rodapé
            elements.append(Spacer(1, 1*cm))
            elements.append(Paragraph(
                f"Relatório gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
                styles['Normal']
            ))

            # Gera o PDF
            def _gerar_pdf():
                doc.build(elements)

            await asyncio.to_thread(_gerar_pdf)

            # Envia o arquivo
            await canal.send(
                f"📄 Relatório anual detalhado em PDF - {ano}:",
                file=discord.File(str(pdf_filename))
            )

            logger.info(f"Relatório anual detalhado em PDF enviado: {ano}")
            print(f"Relatório anual detalhado em PDF enviado: {pdf_filename}")

        except ImportError:
            logger.warning("ReportLab não instalado. Não foi possível gerar PDF anual.")
            await canal.send("⚠️ Erro: ReportLab não instalado. Instale com: `pip install reportlab`")
        except Exception as e:
            logger.error(f"Erro ao gerar relatório anual detalhado em PDF: {e}")
            print(f"Erro ao gerar relatório anual detalhado: {e}")
            await canal.send(f"⚠️ Erro ao gerar relatório anual em PDF: {str(e)}")

    async def enviar_mensagem(self, codigo, nome, status):
        # Define o canal baseado no status
        # Empresas SUSPENSAS vão para o canal específico de suspensas
        if status == "SUSPENSA":
            canal = self.get_channel(DISCORD_SUSPENSE_CHANNEL_ID)
            canal_nome = "suspensas"
        else:
            canal = self.get_channel(DISCORD_CHANNEL_ID)
            canal_nome = "principal"

        # Cores para cada status
        cores = {
            "INATIVA": 0xFF9800,      # Laranja
            "BAIXA": 0xF44336,        # Vermelho
            "DEVOLVIDA": 0x9C27B0,    # Roxo
            "SUSPENSA": 0xE91E63      # Rosa
        }

        embed = discord.Embed(
            title="Alteração de Status - Empresa",
            description=f"**{codigo}** - {nome}",
            color=cores.get(status, 0x2196F3)
        )
        embed.add_field(name="Novo Status", value=f"**{status}**", inline=False)
        embed.add_field(name="Data/Hora", value=self.ultima_verificacao, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # Campo vazio para padronizar

        # Adiciona aviso especial para empresas suspensas
        if status == "SUSPENSA":
            embed.add_field(
                name="Procedimento de Atendimento",
                value="Caso o cliente entre em contato solicitando algum serviço, "
                      "**informe sobre o bloqueio no sistema** e **encaminhe ao setor financeiro** para regularização.",
                inline=False
            )

        embed.set_footer(text="Canella & Santos • Comunicação Interna")

        await canal.send("@everyone", embed=embed)
        logger.info(f"Mensagem enviada ({canal_nome}): {codigo} - {nome} -> {status}")
        print(f"Mensagem enviada ({canal_nome}): {codigo} - {nome} -> {status}")

    async def enviar_mensagem_nova_empresa(self, codigo, nome, status, regime_tributario=""):
        canal = self.get_channel(DISCORD_CHANNEL_ID)
        status_display = "ATIVA" if not eh_status_monitorado(status) else status

        embed = discord.Embed(
            title="✨ Nova Empresa Cadastrada",
            description=f"**{codigo}** - {nome}",
            color=0x4CAF50
        )
        embed.add_field(name="Status Inicial", value=f"**{status_display}**", inline=True)
        embed.add_field(name="Regime Tributário", value=f"**{regime_tributario if regime_tributario else '—'}**", inline=True)
        embed.add_field(name="Data/Hora", value=self.ultima_verificacao, inline=False)
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # Campo vazio para padronizar
        embed.set_footer(text="Canella & Santos • Comunicação Interna")

        await canal.send("@everyone", embed=embed)
        logger.info(f"Mensagem de nova empresa enviada: {codigo} - {nome}")
        print(f"Mensagem de nova empresa enviada: {codigo} - {nome} ({status_display})")

    async def enviar_mensagem_reativacao(self, codigo, nome, status_anterior):
        """Envia notificação quando empresa volta a ficar ATIVA."""
        # Define o canal baseado no status anterior
        # Reativações de empresas que estavam SUSPENSAS vão para o canal específico
        if status_anterior == "SUSPENSA":
            canal = self.get_channel(DISCORD_SUSPENSE_CHANNEL_ID)
            canal_nome = "suspensas"
        else:
            canal = self.get_channel(DISCORD_CHANNEL_ID)
            canal_nome = "principal"

        # Mapeamento de status anteriores
        status_info = {
            "INATIVA": ("INATIVA", 0xFF9800),     # Laranja
            "BAIXA": ("BAIXA", 0xF44336),          # Vermelho
            "DEVOLVIDA": ("DEVOLVIDA", 0x9C27B0),  # Roxo
            "SUSPENSA": ("SUSPENSA", 0xE91E63)     # Rosa
        }

        status_desc, _ = status_info.get(status_anterior, (status_anterior, 0x4CAF50))

        embed = discord.Embed(
            title="Empresa Reativada",
            description=f"**{codigo}** - {nome}",
            color=0x4CAF50  # Verde para reativação
        )
        embed.add_field(
            name="Status Anterior",
            value=f"**{status_desc}**",
            inline=True
        )
        embed.add_field(
            name="Novo Status",
            value=f"**ATIVA** ",
            inline=True
        )
        embed.add_field(name="Data/Hora", value=self.ultima_verificacao, inline=False)
        embed.add_field(
            name="Informação",
            value=f"Empresa voltou ao status ativo após estar {status_desc.lower()}.",
            inline=False
        )
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # Campo vazio para padronizar
        embed.set_footer(text="Canella & Santos • Comunicação Interna")

        await canal.send("@everyone", embed=embed)
        logger.info(f"Mensagem de reativação enviada ({canal_nome}): {codigo} - {nome} ({status_anterior} -> ATIVA)")
        print(f"Mensagem de reativação enviada ({canal_nome}): {codigo} - {nome} ({status_anterior} -> ATIVA)")

    async def enviar_mensagem_regime_tributario(self, codigo, nome, regime_anterior, regime_novo):
        """Envia notificação quando há mudança de regime tributário."""
        canal = self.get_channel(DISCORD_CHANNEL_ID)
        
        # Mapeamento de regimes para descrição e cores
        regimes_map = {
            "SN": ("Simples Nacional", 0x4CAF50),                    # Verde
            "SN-EXCEDENTE": ("Simples Nacional - Excedente", 0x8BC34A),  # Verde claro
            "LP": ("Lucro Presumido", 0x2196F3),                     # Azul
            "LP-NUCLEO": ("Lucro Presumido - Núcleo", 0x1976D2), 
            "LR":  ("Lucro Real", 0x2196F3),     
            "LR-NUCLEO":  ("Lucro Real - Núcleo", 0x2196F3),                         # Azul escuro
            "IGREJA": ("Organização Religiosa", 0x9C27B0),           # Roxo
            "MEI": ("Microempreendedor Individual", 0xFF9800),       # Laranja
            "ISENTO": ("Regime Isento", 0xFFC107)                    # Amarelo
        }
        
        regime_novo_nome, cor = regimes_map.get(regime_novo, (regime_novo, 0x2196F3))
        regime_anterior_nome = regimes_map.get(regime_anterior, (regime_anterior, 0x2196F3))[0]
        
        embed = discord.Embed(
            title="Alteração de Regime Tributário",
            description=f"**{codigo}** - {nome}",
            color=cor
        )
        embed.add_field(
            name="Regime Anterior",
            value=f"**{regime_anterior_nome}** ({regime_anterior})",
            inline=True
        )
        embed.add_field(
            name="Novo Regime",
            value=f"**{regime_novo_nome}** ({regime_novo})",
            inline=True
        )
        embed.add_field(name="Data/Hora", value=self.ultima_verificacao, inline=False)
        embed.add_field(
            name="Ação Necessária",
            value="Revisar documentação e conformidade legal.",
            inline=False
        )
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # Campo vazio para padronizar
        embed.set_footer(text="Canella & Santos • Comunicação Interna")

        await canal.send("@everyone", embed=embed)
        logger.info(f"Notificação de regime tributário enviada: {codigo} - {nome} ({regime_anterior} -> {regime_novo})")
        print(f"Notificação de regime tributário: {codigo} - {nome} ({regime_anterior} -> {regime_novo})")

    async def enviar_mensagem_regime_definido(self, codigo, nome, regime_tributario):
        """Envia notificação quando o regime tributário é definido pela primeira vez."""
        canal = self.get_channel(DISCORD_CHANNEL_ID)

        # Mapeamento de regimes para descrição e cores
        regimes_map = {
            "SN": ("Simples Nacional", 0x4CAF50),
            "SN-EXCEDENTE": ("Simples Nacional - Excedente", 0x8BC34A),
            "LP": ("Lucro Presumido", 0x2196F3),
            "LP-NUCLEO": ("Lucro Presumido - Núcleo", 0x1976D2),
            "LR": ("Lucro Real", 0x2196F3),
            "LR-NUCLEO": ("Lucro Real - Núcleo", 0x2196F3),
            "IGREJA": ("Organização Religiosa", 0x9C27B0),
            "MEI": ("Microempreendedor Individual", 0xFF9800),
            "ISENTO": ("Regime Isento", 0xFFC107)
        }

        regime_nome, cor = regimes_map.get(regime_tributario, (regime_tributario, 0x2196F3))

        embed = discord.Embed(
            title="Regime Tributário Definido",
            description=f"**{codigo}** - {nome}",
            color=cor
        )
        embed.add_field(
            name="Regime Tributário",
            value=f"**{regime_nome}** ({regime_tributario})",
            inline=False
        )
        embed.add_field(name="Data/Hora", value=self.ultima_verificacao, inline=False)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.set_footer(text="Canella & Santos • Comunicação Interna")

        await canal.send("@everyone", embed=embed)
        logger.info(f"Notificação de regime definido enviada: {codigo} - {nome} (Regime: {regime_tributario})")
        print(f"Notificação de regime definido: {codigo} - {nome} (Regime: {regime_tributario})")


# === COMANDOS MANUAIS ===
bot = MyBot()

@bot.tree.command(name="help", description="Mostra todos os comandos disponíveis")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Comandos Disponíveis",
        description="Lista de todos os comandos do bot",
        color=0x2196F3
    )

    embed.add_field(
        name="/ping",
        value="Testa a latência do bot",
        inline=False
    )

    embed.add_field(
        name="/status",
        value="Mostra status do bot e informações de monitoramento",
        inline=False
    )

    embed.add_field(
        name="/relatorio [mes] [ano]",
        value="Gera relatório mensal de alterações\n"
              "* Sem parâmetros: mês atual\n"
              "* Com parâmetros: mês/ano específico\n"
              "Exemplo: `/relatorio 11 2024`",
        inline=False
    )

    embed.add_field(
        name="/historico",
        value="Mostra todas as competências com alterações registradas\n"
              "(Visão resumida por mês)",
        inline=False
    )

    embed.add_field(
        name="/relatorio-anual [ano]",
        value="Gera relatório anual consolidado de alterações\n"
              "* Sem parâmetros: ano atual\n"
              "* Com parâmetro: ano específico\n"
              "* Inclui PDF detalhado com todas as alterações do ano\n"
              "Exemplo: `/relatorio-anual 2024`",
        inline=False
    )

    embed.add_field(
        name="/relatorio-suspensas [semana]",
        value="Gera relatório semanal de empresas suspensas\n"
              "* Sem parâmetros: semana atual\n"
              "* Com parâmetro: semana específica (formato YYYY-WNN)\n"
              "Exemplo: `/relatorio-suspensas 2025-W01`",
        inline=False
    )

    embed.add_field(
        name="/historico-suspensas",
        value="Mostra todas as semanas com empresas suspensas registradas\n"
              "(Visão resumida por semana)",
        inline=False
    )

    embed.add_field(
        name="/empresas-suspensas",
        value="Lista todas as empresas **atualmente** suspensas no sistema\n"
              "* Gera PDF com código, status e regime tributário\n"
              "* Baseado nos dados mais recentes da planilha",
        inline=False
    )

    embed.add_field(
        name="Notificações Automáticas",
        value="* Quando empresa fica INATIVA/BAIXA/DEVOLVIDA/SUSPENSA\n"
              "* Quando empresa volta a ficar ATIVA\n"
              "* Quando há mudança de regime tributário\n"
              f"* Relatório mensal automático (dia {DIA_RELATORIO_MENSAL})\n"
              "* Relatório semanal de suspensas (Segunda-feira 08:30)",
        inline=False
    )

    embed.set_footer(text="Canella & Santos • Comunicação Interna")

    await interaction.response.send_message(embed=embed)
    logger.info(f"Comando /help executado por {interaction.user}")

@bot.tree.command(name="ping", description="Responde com Pong!")
async def ping(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Pong!",
        description=f"Latência: {bot.latency * 1000:.2f}ms",
        color=0x00FF00
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="status", description="Status do bot e informações de monitoramento")
async def status(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Status do Bot",
        color=0x00FF00
    )
    embed.add_field(
        name="Empresas Monitoradas",
        value=f"**{len(bot.sheet_data)}**",
        inline=True
    )
    embed.add_field(
        name="Última Verificação",
        value=f"**{bot.ultima_verificacao or 'Iniciando...'}**",
        inline=True
    )
    embed.add_field(
        name="Status",
        value="**Online**",
        inline=True
    )
    embed.set_footer(text="Canella & Santos • Comunicação Interna")

    await interaction.response.send_message(embed=embed)
    logger.info(f"Comando /status executado por {interaction.user}")

@bot.tree.command(name="relatorio", description="Gera relatório mensal de alterações")
@app_commands.describe(
    mes="Mês (1-12). Deixe vazio para o mês atual.",
    ano="Ano (ex: 2024). Deixe vazio para o ano atual."
)
async def relatorio(interaction: discord.Interaction, mes: int = None, ano: int = None):
    """
    Gera relatório mensal de alterações.

    Args:
        mes: Mês (1-12). Se não informado, usa o mês atual.
        ano: Ano (ex: 2025). Se não informado, usa o ano atual.
    """
    await interaction.response.defer()  # Indica que o bot está processando

    try:
        # Define a competência
        if mes is None or ano is None:
            # Usa o mês atual
            agora = datetime.now()
            competencia = agora.strftime("%Y-%m")
        else:
            # Valida o mês
            if mes < 1 or mes > 12:
                await interaction.followup.send("Mês inválido! Use um valor entre 1 e 12.")
                return

            competencia = f"{ano}-{mes:02d}"

        # Verifica se há dados para a competência
        if competencia not in bot.historico_alteracoes:
            await interaction.followup.send(
                f"Nenhuma alteração registrada para a competência {competencia}."
            )
            logger.info(f"Comando /relatorio executado por {interaction.user} - Sem dados para {competencia}")
            return

        # Envia o relatório
        await bot.enviar_relatorio_mensal(competencia)

        await interaction.followup.send(
            f"Relatório da competência {competencia} enviado com sucesso!"
        )
        logger.info(f"Comando /relatorio executado por {interaction.user} - Competência: {competencia}")

    except Exception as e:
        await interaction.followup.send(f"Erro ao gerar relatório: {str(e)}")
        logger.error(f"Erro no comando /relatorio: {e}")

@bot.tree.command(name="historico", description="Mostra competências com alterações registradas")
async def historico(interaction: discord.Interaction):
    """Mostra as competências que têm alterações registradas."""

    if not bot.historico_alteracoes:
        await interaction.response.send_message("Nenhum histórico de alterações registrado ainda.")
        return

    embed = discord.Embed(
        title="Histórico de Alterações",
        description="Competências com alterações registradas",
        color=0x9C27B0
    )

    # Ordena as competências (mais recente primeiro)
    competencias_ordenadas = sorted(bot.historico_alteracoes.keys(), reverse=True)

    # Lista as competências
    for competencia in competencias_ordenadas[:12]:  # Limita a 12 meses
        dados = bot.historico_alteracoes[competencia]
        stats = dados["estatisticas"]

        # Formata a data
        data_comp = datetime.strptime(competencia, "%Y-%m")
        mes_nome = data_comp.strftime("%B/%Y")

        embed.add_field(
            name=f"{mes_nome}",
            value=f"**{stats['total_alteracoes']}** alterações\n"
                  f"└ {stats['alteracoes_status']} status\n"
                  f"└ {stats['alteracoes_regime']} regimes",
            inline=True
        )

    embed.set_footer(text=f"Canella & Santos • Use /relatorio para relatórios mensais")

    await interaction.response.send_message(embed=embed)
    logger.info(f"Comando /historico executado por {interaction.user}")

@bot.tree.command(name="relatorio-anual", description="Gera relatório anual consolidado de alterações")
@app_commands.describe(
    ano="Ano (ex: 2024). Deixe vazio para o ano atual."
)
async def relatorio_anual(interaction: discord.Interaction, ano: int = None):
    """
    Gera relatório anual consolidado de alterações.

    Args:
        ano: Ano (ex: 2025). Se não informado, usa o ano atual.
    """
    await interaction.response.defer()  # Indica que o bot está processando

    try:
        # Define o ano
        if ano is None:
            agora = datetime.now()
            ano = agora.year

        # Filtra as competências do ano solicitado
        competencias_ano = [
            comp for comp in bot.historico_alteracoes.keys()
            if comp.startswith(f"{ano}-")
        ]

        if not competencias_ano:
            await interaction.followup.send(
                f"Nenhuma alteração registrada para o ano {ano}."
            )
            logger.info(f"Comando /relatorio-anual executado por {interaction.user} - Sem dados para {ano}")
            return

        # Envia o relatório anual
        await bot.enviar_relatorio_anual(interaction.channel, ano, competencias_ano)

        await interaction.followup.send(
            f"Relatório anual de {ano} enviado com sucesso!"
        )
        logger.info(f"Comando /relatorio-anual executado por {interaction.user} - Ano: {ano}")

    except Exception as e:
        await interaction.followup.send(f"Erro ao gerar relatório anual: {str(e)}")
        logger.error(f"Erro no comando /relatorio-anual: {e}")

@bot.tree.command(name="relatorio-suspensas", description="Gera relatório semanal de empresas suspensas")
@app_commands.describe(
    semana="Semana no formato YYYY-WNN (ex: 2025-W01). Deixe vazio para a semana atual."
)
async def relatorio_suspensas(interaction: discord.Interaction, semana: str = None):
    """
    Gera relatório semanal de empresas suspensas.

    Args:
        semana: Semana no formato YYYY-WNN (ex: 2025-W01). Se não informado, usa a semana atual.
    """
    await interaction.response.defer()  # Indica que o bot está processando

    try:
        # Define a semana
        if semana is None:
            semana = bot._obter_semana_ano()

        # Valida o formato da semana
        if not semana.startswith("20") or "-W" not in semana:
            await interaction.followup.send(
                f"Formato de semana inválido! Use o formato YYYY-WNN (ex: 2025-W01)."
            )
            return

        # Verifica se há dados para a semana
        if semana not in bot.historico_suspensas:
            await interaction.followup.send(
                f"Nenhuma empresa suspensa registrada para a semana {semana}."
            )
            logger.info(f"Comando /relatorio-suspensas executado por {interaction.user} - Sem dados para {semana}")
            return

        # Envia o relatório
        await bot.enviar_relatorio_semanal_suspensas(semana)

        await interaction.followup.send(
            f"Relatório de suspensas da semana {semana} enviado com sucesso!"
        )
        logger.info(f"Comando /relatorio-suspensas executado por {interaction.user} - Semana: {semana}")

    except Exception as e:
        await interaction.followup.send(f"Erro ao gerar relatório de suspensas: {str(e)}")
        logger.error(f"Erro no comando /relatorio-suspensas: {e}")

@bot.tree.command(name="historico-suspensas", description="Mostra semanas com empresas suspensas registradas")
async def cmd_historico_suspensas(interaction: discord.Interaction):
    """Mostra as semanas que têm empresas suspensas registradas."""

    if not bot.historico_suspensas:
        await interaction.response.send_message("Nenhum histórico de empresas suspensas registrado ainda.")
        return

    embed = discord.Embed(
        title="Histórico de Empresas Suspensas",
        description="Semanas com empresas suspensas registradas",
        color=0xE91E63
    )

    # Ordena as semanas (mais recente primeiro)
    semanas_ordenadas = sorted(bot.historico_suspensas.keys(), reverse=True)

    # Lista as semanas (limita a 12)
    for semana in semanas_ordenadas[:12]:
        dados = bot.historico_suspensas[semana]
        total = dados["total"]

        embed.add_field(
            name=f"Semana {semana}",
            value=f"**{total}** empresa{'s' if total > 1 else ''} suspensa{'s' if total > 1 else ''}",
            inline=True
        )

    embed.set_footer(text=f"Canella & Santos • Use /relatorio-suspensas para relatório detalhado")

    await interaction.response.send_message(embed=embed)
    logger.info(f"Comando /historico-suspensas executado por {interaction.user}")

@bot.tree.command(name="empresas-suspensas", description="Lista todas as empresas atualmente suspensas")
async def cmd_empresas_suspensas(interaction: discord.Interaction):
    """Lista todas as empresas que estão atualmente com status SUSPENSA."""
    await interaction.response.defer()  # Indica que o bot está processando

    try:
        # Busca dados diretamente da planilha para ter código, nome, status e regime
        data = await asyncio.to_thread(bot.sheet.get_all_values)

        # Filtra empresas suspensas
        empresas_suspensas_lista = []
        for row in data[1:]:  # Pula o cabeçalho
            if len(row) < 3:
                continue

            codigo = str(row[0]).strip()
            nome = str(row[1]).strip()
            status_bruto = str(row[2]).upper().strip()
            regime_bruto = str(row[3]).upper().strip() if len(row) > 3 else ""

            # Normaliza os valores
            status = normalizar_status(status_bruto)
            regime = normalizar_regime(regime_bruto)

            if status == "SUSPENSA":
                empresas_suspensas_lista.append({
                    "codigo": codigo,
                    "nome": nome,
                    "status": status,
                    "regime": regime if regime else "Não definido"
                })

        if not empresas_suspensas_lista:
            embed = discord.Embed(
                title="Empresas Atualmente Suspensas",
                description="Nenhuma empresa está suspensa no momento.",
                color=0x4CAF50  # Verde - bom sinal
            )
            embed.set_footer(text="Canella & Santos • Comunicação Interna")
            await interaction.followup.send(embed=embed)
            return

        total = len(empresas_suspensas_lista)

        # Ordena por código numérico (extrai número do código)
        def extrair_numero(codigo):
            try:
                # Remove caracteres não numéricos e converte para int
                numeros = ''.join(filter(str.isdigit, codigo))
                return int(numeros) if numeros else 0
            except:
                return 0

        empresas_suspensas_lista.sort(key=lambda x: extrair_numero(x["codigo"]))

        # Cria o embed principal
        embed = discord.Embed(
            title="Empresas Atualmente Suspensas",
            description=f"Lista de todas as empresas com status **SUSPENSA** no sistema.",
            color=0xE91E63  # Rosa - cor de suspensa
        )

        # Aviso importante sobre atendimento
        embed.add_field(
            name="ATENÇÃO - Procedimento de Atendimento",
            value="Caso algum cliente dessas empresas entre em contato pelo Messenger ou qualquer outro canal solicitando algum serviço, "
                  "**o mesmo deve ser informado sobre o bloqueio no sistema** e **encaminhado imediatamente ao setor financeiro** "
                  "para regularização da situação antes de qualquer atendimento.",
            inline=False
        )

        # Estatísticas gerais
        embed.add_field(
            name="Total de Empresas Suspensas",
            value=f"**{total}** empresa{'s' if total > 1 else ''}",
            inline=False
        )

        # Lista as empresas (limita a 10 no embed)
        empresas_texto = []
        for i, emp in enumerate(empresas_suspensas_lista):
            if i >= 10:
                empresas_texto.append(f"\n_... e mais {total - 10} empresas (veja o PDF)_")
                break
            empresas_texto.append(f"• **{emp['codigo']}** - {emp['nome']}")

        if empresas_texto:
            texto_empresas = "\n".join(empresas_texto)
            if len(texto_empresas) <= 1024:
                embed.add_field(
                    name="Empresas",
                    value=texto_empresas,
                    inline=False
                )

        embed.set_footer(text=f"Canella & Santos • Dados atualizados em: {bot.ultima_verificacao or 'N/A'}")

        # Envia mensagem de alerta antes do embed
        mensagem_alerta = (
            "@everyone\n"
            "🚨 **RELATÓRIO DE EMPRESAS SUSPENSAS** 🚨\n\n"
            "⚠️ Atenção equipe! Segue abaixo a lista atualizada de todas as empresas que estão com o status **SUSPENSA** no sistema. "
            "Verifiquem com atenção antes de realizar qualquer atendimento!"
        )
        await interaction.followup.send(mensagem_alerta)

        # Envia o embed com os dados
        await interaction.channel.send(embed=embed)

        # Sempre gera e envia o PDF detalhado
        await enviar_pdf_empresas_suspensas_atuais(interaction.channel, empresas_suspensas_lista)

        logger.info(f"Comando /empresas-suspensas executado por {interaction.user} - {total} empresas")

    except Exception as e:
        await interaction.followup.send(f"Erro ao listar empresas suspensas: {str(e)}")
        logger.error(f"Erro no comando /empresas-suspensas: {e}")

async def enviar_pdf_empresas_suspensas_atuais(canal, empresas):
    """Gera e envia PDF com todas as empresas atualmente suspensas."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm

        # Cria o arquivo PDF
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = DATA_DIR / f"empresas_suspensas_atuais_{timestamp}.pdf"
        doc = SimpleDocTemplate(
            str(pdf_filename),
            pagesize=A4,
            title="Empresas Atualmente Suspensas - Canella & Santos",
            author="Canella & Santos Contabilidade",
            subject="Relatório de Empresas Suspensas"
        )
        elements = []

        # Estilos
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#E91E63'),
            spaceAfter=30,
            alignment=1  # Center
        )

        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=12,
            textColor=colors.HexColor('#C2185B'),
            spaceAfter=12,
        )

        aviso_style = ParagraphStyle(
            'AvisoStyle',
            parent=styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#C2185B'),
            spaceAfter=12,
            borderColor=colors.HexColor('#E91E63'),
            borderWidth=1,
            borderPadding=8,
            backColor=colors.HexColor('#FCE4EC'),
        )

        # Título
        elements.append(Paragraph("EMPRESAS ATUALMENTE SUSPENSAS", title_style))
        elements.append(Paragraph(f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", styles['Normal']))
        elements.append(Paragraph("CANELLA & SANTOS CONTABILIDADE EIRELI", styles['Normal']))
        elements.append(Spacer(1, 0.5*cm))

        # Aviso importante
        aviso_texto = (
            "<b>ATENÇÃO - PROCEDIMENTO DE ATENDIMENTO:</b><br/>"
            "Caso algum cliente dessas empresas entre em contato pelo Messenger ou qualquer outro canal "
            "solicitando algum serviço, o mesmo deve ser informado sobre o bloqueio no sistema e "
            "encaminhado imediatamente ao setor financeiro para regularização da situação antes de qualquer atendimento."
        )
        elements.append(Paragraph(aviso_texto, aviso_style))
        elements.append(Spacer(1, 0.5*cm))

        # Estatísticas gerais
        elements.append(Paragraph("RESUMO", heading_style))
        stats_data = [
            ['Total de Empresas Suspensas', str(len(empresas))],
        ]
        stats_table = Table(stats_data, colWidths=[12*cm, 5*cm])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FCE4EC')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E91E63'))
        ]))
        elements.append(stats_table)
        elements.append(Spacer(1, 0.5*cm))

        # Lista de empresas
        elements.append(Paragraph("LISTA DE EMPRESAS SUSPENSAS", heading_style))
        elements.append(Spacer(1, 0.3*cm))

        # Tabela de empresas
        data = [['Código', 'Nome da Empresa', 'Regime Tributário']]

        for emp in empresas:
            nome = emp.get('nome', 'N/A')
            data.append([
                emp['codigo'],
                nome[:35] + ('...' if len(nome) > 35 else ''),
                emp['regime'][:20] + ('...' if len(emp['regime']) > 20 else '')
            ])

        table = Table(data, colWidths=[2.5*cm, 10*cm, 4.5*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E91E63')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#FCE4EC')),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#FCE4EC'), colors.HexColor('#F8BBD9')])
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.5*cm))

        # Rodapé
        elements.append(Paragraph(
            f"Relatório gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            styles['Normal']
        ))

        # Gera o PDF
        def _gerar_pdf():
            doc.build(elements)

        await asyncio.to_thread(_gerar_pdf)

        # Envia o arquivo
        await canal.send(
            "📄 Relatório completo em PDF:",
            file=discord.File(str(pdf_filename))
        )

        logger.info(f"PDF de empresas suspensas atuais enviado: {pdf_filename}")
        print(f"PDF de empresas suspensas atuais enviado: {pdf_filename}")

    except ImportError:
        logger.warning("ReportLab não instalado. Não foi possível gerar PDF.")
        await canal.send("⚠️ PDF não disponível: ReportLab não instalado.")
    except Exception as e:
        logger.error(f"Erro ao gerar PDF de empresas suspensas atuais: {e}")
        print(f"Erro ao gerar PDF: {e}")

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