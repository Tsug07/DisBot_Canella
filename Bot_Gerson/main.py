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
DISCORD_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID')) if os.getenv('DISCORD_CHANNEL_ID') else 0  # Canal específico para alterações
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
    "INATIVA": "INATIVA",
    "INATIVO": "INATIVA",  # Normaliza INATIVO para INATIVA
    "BAIXA": "BAIXA",
    "BAIXADA": "BAIXA",
    "DEVOLVIDA": "DEVOLVIDA",
    "SUSPENSA": "SUSPENSA",
    "SUSPENSA RFB": "SUSPENSA",  # Variação
    "SUSPENSA-RFB": "SUSPENSA",
    "SUSPENSA_RFB": "SUSPENSA",

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
        self.ultimo_relatorio_enviado = None  # Data do último relatório enviado
        self.primeiro_carregamento_completo = verificar_primeiro_carregamento()  # Flag de primeiro carregamento

    async def setup_hook(self):
        await self.tree.sync()
        print("Comandos sincronizados com sucesso!")

    async def on_ready(self):
        print(f"O Bot {self.user} está online!")
        logger.info(f"O Bot {self.user} está online!")
        self.gc = gspread.authorize(
            Credentials.from_service_account_file(PATH_CREDENTIALS, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
        )
        self.sheet = self.gc.open_by_key(GOOGLE_SHEET_ID).sheet1

        # Carrega histórico de alterações
        self.historico_alteracoes = self.carregar_historico()

        # Inicia tarefas em paralelo
        self.loop.create_task(self.monitorar_planilha())
        self.loop.create_task(self.verificar_relatorio_mensal())

    async def on_member_join(self, member):
        """Envia mensagem de boas-vindas quando um novo membro entra no servidor."""
        logger.info(f"Novo membro entrou: {member} (ID: {getattr(member, 'id', 'unknown')})")
        try:
            canal = self.get_channel(DISCORD_CHANNEL_GENERAL)
            if canal:
                embed = discord.Embed(
                    title="Seja bem-vindo(a)!",
                    description=f"Seja bem-vindo(a), {member.mention}! \n\nSinta-se em casa — confira os canais e as regras.",
                    color=0x4CAF50,
                )
                embed.set_footer(text="CANELLA & SANTOS CONTABILIDADE EIRELI")
                await canal.send(embed=embed)
                logger.info(f"Mensagem de boas-vindas enviada para {member} (ID: {member.id})")
            else:
                logger.warning("Canal de boas-vindas (DISCORD_CHANNEL_ID) não encontrado.")
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem de boas-vindas: {e}")

    async def monitorar_planilha(self):
        print("Monitorando planilha do Google Sheets...")
        logger.info("Monitorando planilha do Google Sheets...")
        print(f"ID da planilha: {GOOGLE_SHEET_ID}")
        logger.info(f"ID da planilha: {GOOGLE_SHEET_ID}")

        # Carrega dados salvos, se existirem
        self.sheet_data = self.carregar_estado()

        while True:
            try:
                self.ultima_verificacao = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                print(f"\nVerificando planilha... {self.ultima_verificacao}")
                logger.info(f"Verificando planilha... {self.ultima_verificacao}")
                data = self.sheet.get_all_records()
                print(f"Dados obtidos com sucesso! ({len(data)-1} linhas, excluindo cabeçalho)")
                logger.info(f"Dados obtidos com sucesso! ({len(data)-1} linhas)")
                novos_dados = {}

                # Buscar dados por posição das colunas em vez de nomes
                data = self.sheet.get_all_values()  # Pega todos os valores brutos
                if len(data) <= 1:  # Verifica se há dados além do cabeçalho
                    print("Planilha vazia ou contém apenas cabeçalho")
                    logger.warning("Planilha vazia ou contém apenas cabeçalho")
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
                            # Notifica quando volta a ficar ATIVA (resolução)
                            elif status.upper() == "ATIVA" and eh_status_monitorado(status_anterior):
                                await self.enviar_mensagem_reativacao(codigo, nome, status_anterior)
                            else:
                                print(f"   Status não requer notificação: {status}")
                                logger.info(f"Status não requer notificação: {status}")
                        
                        # Verifica mudança de regime tributário
                        # Só processa se houver mudança real (desconsiderando variações de vazio)
                        regime_anterior_valido = regime_anterior if regime_anterior else ""
                        regime_novo_valido = regime_tributario if regime_tributario else ""

                        if regime_novo_valido != regime_anterior_valido:
                            if regime_anterior_valido:
                                # Mudança de regime (já tinha um regime antes)
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

                                if self.primeiro_carregamento_completo:
                                    await self.enviar_mensagem_regime_tributario(codigo, nome, regime_anterior_valido, regime_novo_valido)
                            elif regime_novo_valido and not regime_anterior_valido:
                                # Regime definido pela primeira vez (empresa já existia, mas sem regime)
                                # Só notifica se passou do primeiro carregamento
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

                                if self.primeiro_carregamento_completo:
                                    await self.enviar_mensagem_regime_definido(codigo, nome, regime_novo_valido)
                    else:
                        # Nova empresa detectada - notifica imediatamente
                        print(f"\nNova empresa detectada na linha {idx}:")
                        print(f"   Empresa: {codigo} - {nome}")
                        print(f"   Status inicial: {status}")
                        print(f"   Regime tributário: {regime_tributario if regime_tributario else 'Não definido'}")
                        logger.info(f"Nova empresa detectada na linha {idx}: {codigo} - {nome} (Status: {status}, Regime: {regime_tributario if regime_tributario else 'Não definido'})")

                        # Só envia notificação se não for o primeiro carregamento
                        if self.primeiro_carregamento_completo:
                            await self.enviar_mensagem_nova_empresa(codigo, nome, status, regime_tributario)
                        else:
                            logger.info(f"   Primeira carga: anotando {codigo} sem notificar Discord")

                # Atualiza dados salvos
                self.sheet_data = novos_dados
                self.salvar_estado(novos_dados)
                
                # Se for a primeira carga, marca como completa APÓS salvar tudo
                if not self.primeiro_carregamento_completo:
                    marcar_primeiro_carregamento()
                    self.primeiro_carregamento_completo = True

            except Exception as e:
                print(f"Erro ao monitorar planilha: {e}")
                logger.error(f"Erro ao monitorar planilha: {e}")

            await asyncio.sleep(30)


    # === Funções auxiliares ===
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

    def salvar_estado(self, dados):
        caminho = DATA_DIR / "estado_empresas.json"
        try:
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

    def salvar_historico(self):
        """Salva o histórico de alterações."""
        caminho = DATA_DIR / "historico_alteracoes.json"
        try:
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(self.historico_alteracoes, f, indent=4, ensure_ascii=False)
            logger.info("Histórico salvo com sucesso.")
        except Exception as e:
            print(f"Erro ao salvar histórico: {e}")
            logger.error(f"Erro ao salvar histórico: {e}")

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

        # Salva o histórico
        self.salvar_historico()

        logger.info(f"Alteração registrada: {tipo} - {codigo} - {nome} (Competência: {competencia})")

    async def verificar_relatorio_mensal(self):
        """Verifica diariamente se deve enviar o relatório mensal."""
        await self.wait_until_ready()
        print(f"Sistema de relatório mensal iniciado (Dia configurado: {DIA_RELATORIO_MENSAL})")
        logger.info(f"Sistema de relatório mensal iniciado (Dia configurado: {DIA_RELATORIO_MENSAL})")

        while not self.is_closed():
            try:
                agora = datetime.now()

                # Verifica se é o dia de enviar o relatório
                if agora.day == DIA_RELATORIO_MENSAL:
                    # Verifica se já enviou hoje
                    if self.ultimo_relatorio_enviado != agora.date():
                        print(f"\nGerando relatório mensal...")
                        logger.info("Gerando relatório mensal...")

                        # Envia relatório do mês anterior
                        mes_anterior = (agora.replace(day=1) - timedelta(days=1))
                        competencia = mes_anterior.strftime("%Y-%m")

                        await self.enviar_relatorio_mensal(competencia)
                        self.ultimo_relatorio_enviado = agora.date()

                        print(f"Relatório mensal enviado!")
                        logger.info("Relatório mensal enviado!")

            except Exception as e:
                print(f"Erro ao verificar relatório mensal: {e}")
                logger.error(f"Erro ao verificar relatório mensal: {e}")

            # Verifica a cada 1 hora
            await asyncio.sleep(3600)

    async def enviar_relatorio_mensal(self, competencia):
        """Envia o relatório mensal de alterações."""
        canal = self.get_channel(DISCORD_CHANNEL_ID)

        if competencia not in self.historico_alteracoes:
            print(f"Nenhuma alteração registrada para a competência {competencia}")
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

        embed.set_footer(text=f"CANELLA & SANTOS CONTABILIDADE EIRELI * Competência: {competencia}")

        await canal.send("@everyone", embed=embed)
        logger.info(f"Relatório mensal enviado: {competencia}")

        # Se houver muitas alterações, cria um arquivo detalhado
        if stats['total_alteracoes'] > 20:
            await self.enviar_relatorio_detalhado(canal, competencia, alteracoes, empresas_alteradas)

    async def enviar_mensagem(self, codigo, nome, status):
        canal = self.get_channel(DISCORD_CHANNEL_ID)
        
        # Cores para cada status
        cores = {
            "INATIVO": 0xFF9800,      # Laranja
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
        embed.set_footer(text="CANELLA & SANTOS CONTABILIDADE EIRELI")
        
        await canal.send("@everyone", embed=embed)
        logger.info(f"Mensagem enviada: {codigo} - {nome} -> {status}")
        print(f"Mensagem enviada: {codigo} - {nome} -> {status}")

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
        embed.set_footer(text="CANELLA & SANTOS CONTABILIDADE EIRELI")

        await canal.send("@everyone", embed=embed)
        logger.info(f"Mensagem de nova empresa enviada: {codigo} - {nome}")
        print(f"Mensagem de nova empresa enviada: {codigo} - {nome} ({status_display})")

    async def enviar_mensagem_reativacao(self, codigo, nome, status_anterior):
        """Envia notificação quando empresa volta a ficar ATIVA."""
        canal = self.get_channel(DISCORD_CHANNEL_ID)

        # Mapeamento de status anteriores
        status_info = {
            "INATIVO": ("INATIVA", 0xFF9800),      # Laranja
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
        embed.set_footer(text="CANELLA & SANTOS CONTABILIDADE EIRELI")

        await canal.send("@everyone", embed=embed)
        logger.info(f"Mensagem de reativação enviada: {codigo} - {nome} ({status_anterior} -> ATIVA)")
        print(f"Mensagem de reativação enviada: {codigo} - {nome} ({status_anterior} -> ATIVA)")

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
        embed.set_footer(text="CANELLA & SANTOS CONTABILIDADE EIRELI")
        
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
        embed.set_footer(text="CANELLA & SANTOS CONTABILIDADE EIRELI")

        await canal.send(embed=embed)
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
        name="Notificações Automáticas",
        value="* Quando empresa fica INATIVA/BAIXA/DEVOLVIDA/SUSPENSA\n"
              "* Quando empresa volta a ficar ATIVA\n"
              "* Quando há mudança de regime tributário\n"
              f"* Relatório mensal automático (dia {DIA_RELATORIO_MENSAL})",
        inline=False
    )

    embed.set_footer(text="CANELLA & SANTOS CONTABILIDADE EIRELI")

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
    embed.set_footer(text="CANELLA & SANTOS CONTABILIDADE EIRELI")

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

    embed.set_footer(text=f"Use /relatorio para gerar o relatório de um mês específico")

    await interaction.response.send_message(embed=embed)
    logger.info(f"Comando /historico executado por {interaction.user}")

bot.run(DISCORD_TOKEN)