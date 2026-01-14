<p align="center">
  <img src="https://img.shields.io/badge/Discord-Bot%20Platform-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord Bot Platform"/>
</p>

<h1 align="center">DisBot Canella</h1>

<p align="center">
  <strong>Plataforma modular para gerenciamento de múltiplos bots Discord</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.8+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.8+"/>
  <img src="https://img.shields.io/badge/discord.py-2.0+-5865F2?style=flat-square&logo=discord&logoColor=white" alt="discord.py"/>
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License MIT"/>
  <img src="https://img.shields.io/badge/status-active-success?style=flat-square" alt="Status Active"/>
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey?style=flat-square" alt="Platform"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Google%20Sheets-Integration-34A853?style=flat-square&logo=googlesheets&logoColor=white" alt="Google Sheets"/>
  <img src="https://img.shields.io/badge/Async-Enabled-blue?style=flat-square" alt="Async"/>
</p>

---

## Sobre o Projeto

**DisBot Canella** é uma plataforma modular e escalável para gerenciar múltiplos bots Discord, onde cada bot opera de forma independente com suas próprias configurações, credenciais e arquivos isolados.

### Principais Recursos

| Recurso | Descrição |
|---------|-----------|
| **Isolamento Completo** | Cada bot possui configurações, credenciais e logs independentes |
| **Integração Google Sheets** | Conexão nativa com planilhas Google para gerenciamento de dados |
| **Logs Estruturados** | Sistema de logging robusto com arquivos separados por bot |
| **Backups Automáticos** | Sistema de backup integrado para dados críticos |
| **Fácil Escalabilidade** | Adicione novos bots com um único comando |

---

## Estrutura do Projeto

```
DisBot_Canella/
├── Bot_Gerson/                 # Bot principal
│   ├── config/
│   │   ├── .env                # Configurações sensíveis
│   │   ├── .env.example        # Template de configuração
│   │   └── credentials.json    # Credenciais Google
│   ├── data/
│   │   └── estado_empresas.json
│   ├── logs/
│   │   └── bot_logs.log
│   ├── backups/
│   └── main.py
│
├── Bot_[NovoBot]/              # Estrutura para novos bots
│   ├── config/
│   ├── data/
│   ├── logs/
│   ├── backups/
│   └── main.py
│
├── create_bot.py               # Script de criação de bots
├── .gitignore
└── README.md
```

---

## Instalação

### Pré-requisitos

- Python 3.8 ou superior
- Conta Discord Developer
- Credenciais Google Cloud (para integração com Sheets)

### Dependências

```bash
pip install discord.py python-dotenv gspread google-auth
```

---

## Início Rápido

### 1. Clone o repositório

```bash
git clone https://github.com/seu-usuario/DisBot_Canella.git
cd DisBot_Canella
```

### 2. Configure o bot existente

```bash
cp Bot_Gerson/config/.env.example Bot_Gerson/config/.env
```

Edite o arquivo `.env` com suas credenciais:

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

### 3. Execute o bot

```bash
python Bot_Gerson/main.py
```

---

## Criando Novos Bots

### Método Automatizado (Recomendado)

```bash
python create_bot.py Bot_NomeDoBot
```

O script cria automaticamente:
- Estrutura completa de diretórios
- Arquivos de configuração (`.env` e `.env.example`)
- Template `main.py` configurado
- README específico do bot

### Método Manual

<details>
<summary>Clique para expandir</summary>

#### 1. Criar estrutura de diretórios

```bash
mkdir -p Bot_NomeDoBot/config
mkdir -p Bot_NomeDoBot/data
mkdir -p Bot_NomeDoBot/logs
mkdir -p Bot_NomeDoBot/backups
```

#### 2. Configurar credenciais

```bash
cp Bot_Gerson/config/.env.example Bot_NomeDoBot/config/.env
```

#### 3. Template base do bot

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

# === SEU CÓDIGO AQUI ===
```

</details>

---

## Executando Múltiplos Bots

Execute cada bot em um terminal separado:

**Terminal 1:**
```bash
python Bot_Gerson/main.py
```

**Terminal 2:**
```bash
python Bot_Vendas/main.py
```

---

## Segurança

### Arquivos Protegidos pelo Git

Os seguintes arquivos são automaticamente ignorados:

| Padrão | Descrição |
|--------|-----------|
| `Bot_*/config/.env` | Tokens e credenciais |
| `Bot_*/config/*.json` | Credenciais Google |
| `Bot_*/data/` | Dados persistentes |
| `Bot_*/logs/` | Arquivos de log |
| `Bot_*/backups/` | Backups automáticos |

> **Importante:** Nunca commite arquivos contendo tokens, senhas ou credenciais.

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                    DisBot Canella                       │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │  Bot_Gerson │  │  Bot_Vendas │  │  Bot_[...]  │     │
│  │  ─────────  │  │  ─────────  │  │  ─────────  │     │
│  │  config/    │  │  config/    │  │  config/    │     │
│  │  data/      │  │  data/      │  │  data/      │     │
│  │  logs/      │  │  logs/      │  │  logs/      │     │
│  │  backups/   │  │  backups/   │  │  backups/   │     │
│  │  main.py    │  │  main.py    │  │  main.py    │     │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘     │
│         │                │                │             │
│         └────────────────┼────────────────┘             │
│                          │                              │
│                   ┌──────▼──────┐                       │
│                   │   Discord   │                       │
│                   │     API     │                       │
│                   └─────────────┘                       │
└─────────────────────────────────────────────────────────┘
```

---

## Vantagens

- **Isolamento**: Cada bot opera independentemente, sem conflitos
- **Segurança**: Credenciais isoladas e protegidas pelo `.gitignore`
- **Escalabilidade**: Adicione quantos bots precisar
- **Organização**: Estrutura padronizada e intuitiva
- **Manutenção**: Fácil debugging com logs separados

---

## Contribuindo

Contribuições são bem-vindas! Sinta-se à vontade para:

1. Fazer um fork do projeto
2. Criar uma branch para sua feature (`git checkout -b feature/NovaFeature`)
3. Commit suas mudanças (`git commit -m 'Adiciona NovaFeature'`)
4. Push para a branch (`git push origin feature/NovaFeature`)
5. Abrir um Pull Request

---

## Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo [LICENSE](LICENSE) para detalhes.

---

## Autor

<table>
  <tr>
    <td align="center">
      <strong>Hugo L. Almeida</strong><br>
      <sub>Desenvolvedor</sub>
    </td>
  </tr>
</table>

---

<p align="center">
  Feito com :purple_heart: usando Python e Discord.py
</p>

<p align="center">
  <a href="#disbot-canella">Voltar ao topo</a>
</p>
