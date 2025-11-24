#!/usr/bin/env python3
"""
Script para criar rapidamente a estrutura de um novo bot.
Uso: python create_bot.py nome_do_bot
"""

import sys
import os
from pathlib import Path

def create_bot_structure(bot_name):
    """Cria a estrutura completa de diretórios e arquivos para um novo bot."""

    # Diretório base do projeto
    base_dir = Path(__file__).parent / bot_name

    # Verifica se o bot já existe
    if base_dir.exists():
        print(f"❌ Erro: O bot '{bot_name}' já existe!")
        return False

    # Cria diretórios
    directories = {
        'config': base_dir / "config",
        'data': base_dir / "data",
        'logs': base_dir / "logs",
        'backups': base_dir / "backups"
    }

    print(f"📁 Criando estrutura para o bot '{bot_name}'...")

    for name, path in directories.items():
        path.mkdir(parents=True, exist_ok=True)
        print(f"  ✅ Criado: {name}/")

    # Cria arquivo .env.example
    env_example_content = """# Discord Bot Token
DISCORD_TOKEN=your_discord_token_here

# Discord Channel ID
DISCORD_CHANNEL_ID=your_channel_id_here

# Google Sheets
GOOGLE_SHEET_ID=your_google_sheet_id_here

# Google Credentials File (relative to this bot's config folder)
GOOGLE_CREDENTIALS_FILE=credentials.json

# Discord General Channel ID
DISCORD_CHANNEL_GENERAL=your_general_channel_id_here
"""

    env_example_path = directories['config'] / ".env.example"
    with open(env_example_path, 'w', encoding='utf-8') as f:
        f.write(env_example_content)
    print(f"  ✅ Criado: config/.env.example")

    # Cria arquivo .env vazio
    env_path = directories['config'] / ".env"
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write(env_example_content)
    print(f"  ✅ Criado: config/.env (configure este arquivo!)")

    # Cria main.py com template base
    main_py_content = """import discord
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
import logging
from discord import app_commands

# === CONFIGURAÇÃO DE CAMINHOS ===
BOT_DIR = Path(__file__).parent.resolve()
CONFIG_DIR = BOT_DIR / "config"
DATA_DIR = BOT_DIR / "data"
LOGS_DIR = BOT_DIR / "logs"
BACKUPS_DIR = BOT_DIR / "backups"

# Cria diretórios se não existirem
for directory in [CONFIG_DIR, DATA_DIR, LOGS_DIR, BACKUPS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Carrega variáveis de ambiente
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

# === BOT SETUP ===
class MyBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        logger.info("Comandos sincronizados com sucesso!")

    async def on_ready(self):
        logger.info(f"Bot {self.user} está online!")
        print(f"✅ Bot {self.user} está online!")

# === INSTANCIA E COMANDOS ===
bot = MyBot()

@bot.tree.command(name="ping", description="Testa a latência do bot")
async def ping(interaction: discord.Interaction):
    latency = bot.latency * 1000
    await interaction.response.send_message(f"🏓 Pong! Latência: {latency:.2f}ms")
    logger.info(f"Comando /ping executado por {interaction.user}")

# === EXECUÇÃO ===
if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.error("❌ DISCORD_TOKEN não configurado no arquivo .env!")
        print("❌ Configure o arquivo config/.env antes de executar o bot!")
        exit(1)

    bot.run(DISCORD_TOKEN)
"""

    main_py_path = base_dir / "main.py"
    with open(main_py_path, 'w', encoding='utf-8') as f:
        f.write(main_py_content)
    print(f"  ✅ Criado: main.py")

    # Cria README específico do bot
    readme_content = f"""# {bot_name.replace('_', ' ').title()}

## Configuração

1. Configure o arquivo `config/.env` com suas credenciais
2. Adicione o arquivo de credenciais Google em `config/credentials.json` (se necessário)
3. Execute o bot com: `python main.py`

## Estrutura

```
{bot_name}/
├── config/         # Configurações e credenciais (não commitar)
├── data/           # Dados persistentes do bot
├── logs/           # Logs do bot
├── backups/        # Backups automáticos
├── main.py         # Código principal
└── README.md       # Este arquivo
```

## Comandos

- `/ping` - Testa a latência do bot

## Desenvolvimento

Adicione seus comandos e funcionalidades no arquivo `main.py`.
"""

    readme_path = base_dir / "README.md"
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(readme_content)
    print(f"  ✅ Criado: README.md")

    print(f"\n✨ Bot '{bot_name}' criado com sucesso!")
    print(f"\n📋 Próximos passos:")
    print(f"  1. Configure o arquivo: {bot_name}/config/.env")
    print(f"  2. Adicione credenciais Google (se necessário): {bot_name}/config/credentials.json")
    print(f"  3. Execute o bot: python {bot_name}/main.py")

    return True

def main():
    if len(sys.argv) != 2:
        print("Uso: python create_bot.py Bot_NomeDoBot")
        print("\nExemplo: python create_bot.py Bot_Vendas")
        print("\nNota: Use o padrão Bot_ no início do nome para manter a consistência")
        sys.exit(1)

    bot_name = sys.argv[1]

    # Valida o nome do bot
    if not bot_name.replace('_', '').isalnum():
        print("❌ Erro: Nome do bot deve conter apenas letras, números e underscore (_)")
        sys.exit(1)

    # Recomenda usar Bot_ no início
    if not bot_name.startswith('Bot_'):
        print(f"⚠️  Aviso: Recomendamos usar 'Bot_' no início do nome (ex: Bot_{bot_name})")
        resposta = input("Continuar mesmo assim? (s/N): ")
        if resposta.lower() != 's':
            print("Operação cancelada.")
            sys.exit(0)

    if create_bot_structure(bot_name):
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
