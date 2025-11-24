# Estrutura do Projeto - DisBot Canella

## Visão Geral

Este documento descreve a nova estrutura modular do projeto, onde cada bot tem sua própria pasta isolada.

## Estrutura Atual

```
DisBot_Canella/
│
├── Bot_Gerson/                    # Bot principal (Gerson)
│   ├── config/                    # ⚠️ ARQUIVOS SENSÍVEIS (gitignored)
│   │   ├── .env                   # Configurações do bot (tokens, IDs)
│   │   ├── .env.example           # Template de configuração
│   │   └── credentials.json       # Credenciais Google API
│   │
│   ├── data/                      # 📊 DADOS DO BOT (gitignored)
│   │   └── estado_empresas.json   # Estado persistente das empresas
│   │
│   ├── logs/                      # 📝 LOGS (gitignored)
│   │   └── bot_logs.log           # Arquivo de log
│   │
│   ├── backups/                   # 💾 BACKUPS (gitignored)
│   │   └── estado_empresas_backup_*.json
│   │
│   └── main.py                    # 🤖 Código principal do bot
│
├── .gitignore                     # Configuração do Git
├── README.md                      # Documentação principal
├── ESTRUTURA.md                   # Este arquivo
└── create_bot.py                  # Script para criar novos bots

# Arquivos antigos na raiz (serão removidos eventualmente):
├── .env                           # ⚠️ Antigo - use Bot_*/config/.env
├── gen-lang-client-*.json         # ⚠️ Antigo - use Bot_*/config/credentials.json
├── estado_empresas.json           # ⚠️ Antigo - use Bot_*/data/
├── bot_logs.log                   # ⚠️ Antigo - use Bot_*/logs/
└── backups/                       # ⚠️ Antigo - use Bot_*/backups/
```

## Como Funciona

### Isolamento Completo

Cada bot (`Bot_*`) é completamente isolado:

1. **Configurações próprias**: Cada bot tem seu `.env` em `Bot_*/config/`
2. **Credenciais isoladas**: Credenciais Google em `Bot_*/config/credentials.json`
3. **Dados separados**: Estado e cache em `Bot_*/data/`
4. **Logs independentes**: Cada bot gera logs em `Bot_*/logs/`
5. **Backups automáticos**: Backups em `Bot_*/backups/`

### Segurança

O `.gitignore` está configurado para **NUNCA** commitar:
- `Bot_*/config/.env` - Tokens e senhas
- `Bot_*/config/*.json` - Credenciais
- `Bot_*/data/` - Dados do bot
- `Bot_*/logs/` - Logs
- `Bot_*/backups/` - Backups

Apenas o `.env.example` é commitado como template.

### Caminhos no Código

O código de cada bot usa `Path` do Python para resolver caminhos relativos:

```python
from pathlib import Path

# Define diretório base do bot
BOT_DIR = Path(__file__).parent.resolve()
CONFIG_DIR = BOT_DIR / "config"
DATA_DIR = BOT_DIR / "data"
LOGS_DIR = BOT_DIR / "logs"
BACKUPS_DIR = BOT_DIR / "backups"

# Carrega .env da pasta config
load_dotenv(dotenv_path=CONFIG_DIR / ".env")

# Salva dados na pasta data
with open(DATA_DIR / "estado.json", "w") as f:
    ...
```

## Criar Novo Bot

### Automático (Recomendado)

```bash
python create_bot.py Bot_NomeDoBot
```

Isso cria automaticamente:
- ✅ Estrutura de diretórios completa
- ✅ Arquivo `.env` e `.env.example`
- ✅ Template `main.py` com os caminhos corretos
- ✅ README.md específico do bot

### Manual

```bash
# Criar diretórios
mkdir -p Bot_NomeDoBot/{config,data,logs,backups}

# Copiar template de configuração
cp Bot_Gerson/config/.env.example Bot_NomeDoBot/config/.env

# Editar configurações
nano Bot_NomeDoBot/config/.env

# Copiar credenciais (se necessário)
cp credentials.json Bot_NomeDoBot/config/

# Criar main.py (use o template do README.md)
```

## Executar Bots

### Um Bot

```bash
cd Bot_Gerson
python main.py
```

Ou de qualquer lugar:

```bash
python Bot_Gerson/main.py
```

### Múltiplos Bots Simultaneamente

Abra terminais separados:

**Terminal 1:**
```bash
python Bot_Gerson/main.py
```

**Terminal 2:**
```bash
python Bot_Vendas/main.py
```

**Terminal 3:**
```bash
python Bot_Marketing/main.py
```

Cada bot roda independentemente!

## Vantagens desta Estrutura

| Aspecto | Vantagem |
|---------|----------|
| **Segurança** | Credenciais isoladas, nada no Git |
| **Organização** | Tudo relacionado ao bot em uma pasta |
| **Manutenção** | Fácil localizar arquivos específicos |
| **Escalabilidade** | Adicione bots sem afetar os existentes |
| **Desenvolvimento** | Múltiplos desenvolvedores em bots diferentes |
| **Deploy** | Pode deployar bots individualmente |

## Checklist de Migração

Para migrar um bot antigo:

- [ ] Criar estrutura: `Bot_Nome/{config,data,logs,backups}`
- [ ] Mover `.env` para `Bot_Nome/config/.env`
- [ ] Criar `.env.example` em `Bot_Nome/config/`
- [ ] Mover credenciais para `Bot_Nome/config/`
- [ ] Atualizar código para usar `Path`
- [ ] Atualizar `load_dotenv()` para usar `CONFIG_DIR / ".env"`
- [ ] Atualizar caminhos de dados para usar `DATA_DIR`
- [ ] Atualizar caminhos de logs para usar `LOGS_DIR`
- [ ] Atualizar caminhos de backup para usar `BACKUPS_DIR`
- [ ] Testar o bot
- [ ] Remover arquivos antigos da raiz

## Exemplo Completo

Veja o `Bot_Gerson/main.py` para um exemplo completo de:
- ✅ Configuração de caminhos com Path
- ✅ Carregamento de .env da pasta config
- ✅ Logs na pasta logs
- ✅ Dados na pasta data
- ✅ Backups na pasta backups

## Padrão de Nomenclatura

Use `Bot_` como prefixo para todos os bots:

- ✅ `Bot_Gerson`
- ✅ `Bot_Vendas`
- ✅ `Bot_Marketing`
- ✅ `Bot_Atendimento`
- ❌ `gerson_bot`
- ❌ `vendas`

Isso facilita:
- Identificação visual no explorer
- Configuração do .gitignore (`Bot_*/config/.env`)
- Organização alfabética
- Autocomplete no terminal

## Suporte

Dúvidas? Consulte:
- [README.md](README.md) - Documentação principal
- [Bot_Gerson/main.py](Bot_Gerson/main.py) - Exemplo de código
- [create_bot.py](create_bot.py) - Script de criação
