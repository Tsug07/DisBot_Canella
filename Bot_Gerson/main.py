import discord
import asyncio
import gspread
from google.oauth2.service_account import Credentials
from discord import app_commands
import json
import os
from datetime import datetime
from dotenv import load_dotenv
import logging
import shutil

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# === CONFIGURAÇÃO DE LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_logs.log', encoding='utf-8'),
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
PATH_CREDENTIALS = os.getenv('GOOGLE_CREDENTIALS_FILE')

STATUS_MONITORADOS = ["INATIVO", "BAIXA", "DEVOLVIDA", "SUSPENSA"]

# === BOT SETUP ===
class MyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.sheet_data = {}
        self.ultima_verificacao = None

    async def setup_hook(self):
        await self.tree.sync()
        print("Comandos sincronizados com sucesso!")

    async def on_ready(self):
        print(f"✅ O Bot {self.user} está online!")
        logger.info(f"✅ O Bot {self.user} está online!")
        self.gc = gspread.authorize(
            Credentials.from_service_account_file(PATH_CREDENTIALS, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
        )
        self.sheet = self.gc.open_by_key(GOOGLE_SHEET_ID).sheet1
        await self.monitorar_planilha()

    async def on_member_join(self, member):
        """Envia mensagem de boas-vindas quando um novo membro entra no servidor."""
        logger.info(f"👋 Novo membro entrou: {member} (ID: {getattr(member, 'id', 'unknown')})")
        try:
            canal = self.get_channel(DISCORD_CHANNEL_GENERAL)
            if canal:
                embed = discord.Embed(
                    title="Seja bem-vindo(a)!",
                    description=f"Seja bem-vindo(a), {member.mention}! 🎉\n\nSinta-se em casa — confira os canais e as regras.",
                    color=0x4CAF50,
                )
                embed.set_footer(text="CANELLA & SANTOS CONTABILIDADE EIRELI")
                await canal.send(embed=embed)
                logger.info(f"✅ Mensagem de boas-vindas enviada para {member} (ID: {member.id})")
            else:
                logger.warning("Canal de boas-vindas (DISCORD_CHANNEL_ID) não encontrado.")
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem de boas-vindas: {e}")

    async def monitorar_planilha(self):
        print("📊 Monitorando planilha do Google Sheets...")
        logger.info("📊 Monitorando planilha do Google Sheets...")
        print(f"🔍 ID da planilha: {GOOGLE_SHEET_ID}")
        logger.info(f"🔍 ID da planilha: {GOOGLE_SHEET_ID}")

        # Carrega dados salvos, se existirem
        self.sheet_data = self.carregar_estado()

        while True:
            try:
                self.ultima_verificacao = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                print(f"\n⏳ Verificando planilha... {self.ultima_verificacao}")
                logger.info(f"⏳ Verificando planilha... {self.ultima_verificacao}")
                data = self.sheet.get_all_records()
                print(f"✅ Dados obtidos com sucesso! ({len(data)-1} linhas, excluindo cabeçalho)")
                logger.info(f"✅ Dados obtidos com sucesso! ({len(data)-1} linhas)")
                novos_dados = {}

                # Buscar dados por posição das colunas em vez de nomes
                data = self.sheet.get_all_values()  # Pega todos os valores brutos
                if len(data) <= 1:  # Verifica se há dados além do cabeçalho
                    print("⚠️ Planilha vazia ou contém apenas cabeçalho")
                    logger.warning("⚠️ Planilha vazia ou contém apenas cabeçalho")
                    continue

                # Pula a primeira linha (cabeçalho)
                for idx, row in enumerate(data[1:], start=2):  # start=2 porque idx 1 é o cabeçalho
                    # Verifica se a linha tem todas as colunas necessárias (A, B, C, D)
                    if len(row) < 4:
                        continue

                    # A=0, B=1, C=2, D=3
                    codigo = row[0]  # Coluna A
                    nome = row[1]    # Coluna B
                    status = row[2]  # Coluna C
                    regime_tributario = row[3]  # Coluna D

                    if not all([codigo, nome, status, regime_tributario]):  # Verifica se algum campo está vazio
                        continue

                    codigo = str(codigo).strip()
                    nome = str(nome).strip()
                    status = str(status).upper().strip()
                    regime_tributario = str(regime_tributario).upper().strip()

                    # Armazena em formato de dicionário
                    novos_dados[codigo] = {
                        "status": status,
                        "regime_tributario": regime_tributario
                    }

                    # Verifica alterações ou novas empresas
                    if codigo in self.sheet_data:
                        dados_anterior = self.sheet_data[codigo]
                        status_anterior = dados_anterior.get("status") if isinstance(dados_anterior, dict) else dados_anterior
                        regime_anterior = dados_anterior.get("regime_tributario", "") if isinstance(dados_anterior, dict) else ""
                        
                        # Verifica mudança de status
                        if status != status_anterior:
                            print(f"\n🔄 Alteração detectada na linha {idx}:")
                            print(f"   Empresa: {codigo} - {nome}")
                            print(f"   Status anterior: {status_anterior}")
                            print(f"   Novo status: {status}")
                            logger.info(f"🔄 Alteração detectada na linha {idx}: {codigo} - {nome} ({status_anterior} → {status})")
                            
                            if status in STATUS_MONITORADOS:
                                await self.enviar_mensagem(codigo, nome, status)
                            else:
                                print(f"   ❌ Status não monitorado: {status}")
                                logger.info(f"Status não monitorado: {status}")
                        
                        # Verifica mudança de regime tributário (apenas notifica se houve mudança anterior)
                        if regime_tributario != regime_anterior and regime_anterior:
                            print(f"\n📋 Alteração de Regime Tributário detectada na linha {idx}:")
                            print(f"   Empresa: {codigo} - {nome}")
                            print(f"   Regime anterior: {regime_anterior}")
                            print(f"   Novo regime: {regime_tributario}")
                            logger.info(f"📋 Alteração de regime tributário na linha {idx}: {codigo} - {nome} ({regime_anterior} → {regime_tributario})")
                            await self.enviar_mensagem_regime_tributario(codigo, nome, regime_anterior, regime_tributario)
                        elif regime_tributario != regime_anterior and not regime_anterior:
                            # Primeira detecção de regime (sem notificação, apenas log)
                            logger.info(f"📝 Primeiro regime tributário registrado: {codigo} - {nome} (Regime: {regime_tributario})")
                    else:
                        # Nova empresa detectada
                        print(f"\n📝 Nova empresa detectada na linha {idx}:")
                        print(f"   Empresa: {codigo} - {nome}")
                        print(f"   Status inicial: {status}")
                        print(f"   Regime tributário: {regime_tributario}")
                        logger.info(f"📝 Nova empresa detectada na linha {idx}: {codigo} - {nome} (Status: {status}, Regime: {regime_tributario})")
                        await self.enviar_mensagem_nova_empresa(codigo, nome, status, regime_tributario)

                # Atualiza dados salvos
                self.sheet_data = novos_dados
                self.salvar_estado(novos_dados)

            except Exception as e:
                print(f"❌ Erro ao monitorar planilha: {e}")
                logger.error(f"❌ Erro ao monitorar planilha: {e}")

            await asyncio.sleep(30)


    # === Funções auxiliares ===
    def carregar_estado(self):
        caminho = "estado_empresas.json"
        if os.path.exists(caminho):
            try:
                with open(caminho, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                    ultima_verificacao = dados.get("ultima_verificacao", "Nunca")
                    registros = dados.get("registros", {})
                    print(f"🟢 Estado carregado ({len(registros)} registros).")
                    print(f"📅 Última verificação: {ultima_verificacao}")
                    return registros
            except Exception as e:
                print(f"⚠️ Erro ao carregar estado: {e}")
        print("🔹 Nenhum estado salvo encontrado. Criando novo...")
        return {}

    def salvar_estado(self, dados):
        caminho = "estado_empresas.json"
        try:
            estado_completo = {
                "ultima_verificacao": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                "registros": dados
            }
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(estado_completo, f, indent=4, ensure_ascii=False)
            
            # Backup automático
            backup_dir = "backups"
            os.makedirs(backup_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"estado_empresas_backup_{timestamp}.json")
            shutil.copy(caminho, backup_path)
            
            print(f"💾 Estado salvo com sucesso em {estado_completo['ultima_verificacao']}")
            logger.info(f"💾 Estado salvo com sucesso. Backup: {backup_path}")
        except Exception as e:
            print(f"⚠️ Erro ao salvar estado: {e}")
            logger.error(f"⚠️ Erro ao salvar estado: {e}")

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
            title="⚠️ Alteração de Status - Empresa",
            description=f"**{codigo}** - {nome}",
            color=cores.get(status, 0x2196F3)
        )
        embed.add_field(name="Novo Status", value=f"**{status}**", inline=False)
        embed.add_field(name="Data/Hora", value=self.ultima_verificacao, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # Campo vazio para padronizar
        embed.set_footer(text="CANELLA & SANTOS CONTABILIDADE EIRELI")
        
        await canal.send("@everyone", embed=embed)
        logger.info(f"📨 Mensagem enviada: {codigo} - {nome} → {status}")
        print(f"📨 Mensagem enviada: {codigo} - {nome} → {status}")

    async def enviar_mensagem_nova_empresa(self, codigo, nome, status, regime_tributario=""):
        canal = self.get_channel(DISCORD_CHANNEL_GENERAL)
        status_display = "ATIVA" if status.upper() not in STATUS_MONITORADOS else status
        
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
        
        await canal.send(embed=embed)
        logger.info(f"📨 Mensagem de nova empresa enviada: {codigo} - {nome}")
        print(f"📨 Mensagem de nova empresa enviada: {codigo} - {nome} ({status_display})")

    async def enviar_mensagem_regime_tributario(self, codigo, nome, regime_anterior, regime_novo):
        """Envia notificação quando há mudança de regime tributário."""
        canal = self.get_channel(DISCORD_CHANNEL_ID)
        
        # Mapeamento de regimes para descrição e cores
        regimes_map = {
            "SN": ("Simples Nacional", 0x4CAF50),        # Verde
            "LP": ("Lucro Presumido", 0x2196F3),         # Azul
            "IGREJA": ("Organização Religiosa", 0x9C27B0), # Roxo
            "MEI": ("Microempreendedor Individual", 0xFF9800), # Laranja
            "ISENTO": ("Regime Isento", 0xFFC107)        # Amarelo
        }
        
        regime_novo_nome, cor = regimes_map.get(regime_novo, (regime_novo, 0x2196F3))
        regime_anterior_nome = regimes_map.get(regime_anterior, (regime_anterior, 0x2196F3))[0]
        
        embed = discord.Embed(
            title="📋 Alteração de Regime Tributário",
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
            name="⚠️ Ação Necessária",
            value="Revisar documentação e conformidade legal.",
            inline=False
        )
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # Campo vazio para padronizar
        embed.set_footer(text="CANELLA & SANTOS CONTABILIDADE EIRELI")
        
        await canal.send("@everyone", embed=embed)
        logger.info(f"📨 Notificação de regime tributário enviada: {codigo} - {nome} ({regime_anterior} → {regime_novo})")
        print(f"📨 Notificação de regime tributário: {codigo} - {nome} ({regime_anterior} → {regime_novo})")


# === COMANDOS MANUAIS ===
bot = MyBot()

@bot.tree.command(name="ping", description="Responde com Pong!")
async def ping(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latência: {bot.latency * 1000:.2f}ms",
        color=0x00FF00
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="status", description="Status do bot e informações de monitoramento")
async def status(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📊 Status do Bot",
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
        value="**✅ Online**",
        inline=True
    )
    embed.set_footer(text="CANELLA & SANTOS CONTABILIDADE EIRELI")
    
    await interaction.response.send_message(embed=embed)
    logger.info(f"Comando /status executado por {interaction.user}")

bot.run(DISCORD_TOKEN)