# DisBot Canella - Multi-Bot Discord Platform

Plataforma modular para gerenciar múltiplos bots Discord, cada um com suas próprias configurações e arquivos isolados.

## Estrutura do Projeto

```
DisBot_Canella/
├── Bot_Gerson/
│   ├── config/
│   │   ├── .env              # Configurações sensíveis (NÃO commitar)
│   │   ├── .env.example      # Exemplo de configurações
│   │   └── credentials.json  # Credenciais Google (NÃO commitar)
│   ├── data/
│   │   └── estado_empresas.json  # Estado do bot
│   ├── logs/
│   │   └── bot_logs.log      # Logs do bot
│   ├── backups/
│   │   └── [backups automáticos]
│   └── main.py               # Código principal do bot
│
├── Bot_[NomeDoNovoBot]/      # Adicione novos bots aqui
│   ├── config/
│   ├── data/
│   ├── logs/
│   ├── backups/
│   └── main.py
│
├── .gitignore
├── create_bot.py             # Script para criar novos bots
└── README.md
```

## Como Adicionar um Novo Bot

### Método 1: Usando o Script Automático (Recomendado)

```bash
python create_bot.py Bot_NomeDoBot
```

O script irá:
1. Criar toda a estrutura de diretórios
2. Criar arquivos de configuração (.env e .env.example)
3. Criar um main.py com template base
4. Criar README.md específico do bot

### Método 2: Manualmente

#### 1. Criar Estrutura de Diretórios

```bash
mkdir -p Bot_NomeDoBot/config
mkdir -p Bot_NomeDoBot/data
mkdir -p Bot_NomeDoBot/logs
mkdir -p Bot_NomeDoBot/backups
```

#### 2. Criar Arquivo de Configuração

Copie o exemplo e configure:

```bash
cp Bot_Gerson/config/.env.example Bot_NomeDoBot/config/.env
```

Edite `Bot_NomeDoBot/config/.env` com suas credenciais:

```env
# Discord Bot Token
DISCORD_TOKEN=seu_token_aqui

# Discord Channel ID
DISCORD_CHANNEL_ID=id_do_canal

# Google Sheets
GOOGLE_SHEET_ID=id_da_planilha

# Google Credentials File
GOOGLE_CREDENTIALS_FILE=credentials.json

# Discord General Channel ID
DISCORD_CHANNEL_GENERAL=id_do_canal_geral
```

#### 3. Adicionar Credenciais Google

Coloque o arquivo de credenciais JSON do Google em:
```
Bot_NomeDoBot/config/credentials.json
```

#### 4. Criar o Código do Bot

Use este template base no arquivo `Bot_NomeDoBot/main.py`:

```python
import discord
import os
from pathlib import Path
from dotenv import load_dotenv
import logging

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
# ... suas outras configurações

# === SEU CÓDIGO AQUI ===
```

## Executando um Bot

Para executar um bot específico:

```bash
cd Bot_Gerson
python main.py
```

Ou execute de qualquer lugar:

```bash
python Bot_Gerson/main.py
```

## Vantagens desta Estrutura

### Isolamento Completo
- Cada bot tem suas próprias configurações (.env)
- Credenciais isoladas por bot
- Logs separados para cada bot
- Dados e backups independentes

### Segurança
- Arquivos sensíveis não são commitados (protegidos pelo .gitignore)
- Cada bot só tem acesso às suas próprias credenciais
- Sem conflito de variáveis de ambiente

### Escalabilidade
- Fácil adicionar novos bots
- Estrutura padronizada
- Gerenciamento independente de cada bot

### Organização
- Código limpo e modular
- Fácil localizar arquivos de cada bot
- Manutenção simplificada

## Arquivos Sensíveis (NÃO COMMITAR)

Os seguintes arquivos são automaticamente ignorados pelo Git:

- `Bot_*/config/.env` - Configurações com tokens e IDs
- `Bot_*/config/*.json` - Credenciais Google
- `Bot_*/data/` - Dados e estado dos bots
- `Bot_*/logs/` - Logs dos bots
- `Bot_*/backups/` - Backups automáticos

## Estrutura de cada Bot

Cada bot segue este padrão:

```
Bot_Nome/
├── config/           # Configurações sensíveis (gitignored)
│   ├── .env         # Tokens, IDs, credenciais
│   ├── .env.example # Template de configuração
│   └── credentials.json  # Credenciais Google
├── data/            # Dados persistentes (gitignored)
│   └── *.json      # Estados, cache, etc
├── logs/            # Logs do bot (gitignored)
│   └── bot_logs.log
├── backups/         # Backups automáticos (gitignored)
└── main.py          # Código principal
```

## Migração do Bot Existente

O bot original (Bot_Gerson) foi migrado para a nova estrutura:

- ✅ Código movido para [Bot_Gerson/main.py](Bot_Gerson/main.py)
- ✅ Configurações em [Bot_Gerson/config/.env](Bot_Gerson/config/.env)
- ✅ Credenciais em [Bot_Gerson/config/credentials.json](Bot_Gerson/config/credentials.json)
- ✅ Caminhos atualizados no código

## Dependências

Certifique-se de ter instalado:

```bash
pip install discord.py python-dotenv gspread google-auth
```

## Exemplos de Uso

### Criar um novo bot de vendas
```bash
python create_bot.py Bot_Vendas
cd Bot_Vendas
# Configure o arquivo config/.env
python main.py
```

### Executar múltiplos bots simultaneamente
Abra terminais separados para cada bot:

Terminal 1:
```bash
python Bot_Gerson/main.py
```

Terminal 2:
```bash
python Bot_Vendas/main.py
```

## Suporte

Para problemas ou dúvidas, consulte a documentação de cada bot ou entre em contato com o desenvolvedor.
