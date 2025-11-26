# 🤖 Rebecca Bot - Guia de Instalação

## 📋 Pré-requisitos

- Python 3.8 ou superior instalado
- Git (opcional, para clonar o repositório)

## 🚀 Instalação Automática (Recomendado)

### Opção 1: Instalação Completa + Inicialização Automática

1. Navegue até a pasta **`Bot_Rebecca/setup/`**
2. Execute o arquivo: **`INSTALACAO_AUTOMATICA.bat`**
   - Instala todas as dependências
   - Cria atalho na pasta de inicialização do Windows
   - Inicia o gerenciador automaticamente

### Opção 2: Instalação Manual

1. Instale as dependências:
   ```bash
   pip install customtkinter pillow pystray discord.py google-generativeai
   ```

2. Execute o gerenciador (da pasta Bot_Rebecca):
   ```bash
   python bot_manager.py
   ```

## 🔧 Configuração de Inicialização Automática

### Método Automático (Mais Fácil)
Execute: **`setup/INSTALACAO_AUTOMATICA.bat`**

### Método Manual
1. Pressione `Win + R`
2. Digite: `shell:startup`
3. Copie o arquivo **`setup/Iniciar_Rebecca_Bot.bat`** para esta pasta

## 🗑️ Remover da Inicialização

Execute: **`setup/DESINSTALAR_INICIALIZACAO.bat`**

## 📂 Estrutura de Arquivos

```
Bot_Rebecca/
├── bot_manager.py              # Gerenciador principal
├── rebecca_bot.py              # Código do bot Discord
├── config.py                   # Configurações (TOKEN, etc)
├── bot_config.json             # Config local (NÃO VERSIONAR)
├── rebecca_bot.pid             # Arquivo PID (NÃO VERSIONAR)
└── setup/                      # Scripts de instalação e gerenciamento
    ├── INSTALACAO_AUTOMATICA.bat
    ├── Iniciar_Rebecca_Bot.bat
    ├── Iniciar_Gerenciador.bat
    ├── DESINSTALAR_INICIALIZACAO.bat
    ├── Instalar_Dependencias.bat
    ├── testar_bot.bat
    ├── build_exe.bat
    ├── COMO_USAR.txt
    └── README_INSTALACAO.md
```

## ⚙️ Configuração do Token

Edite o arquivo **`config.py`** e adicione seu token do Discord:

```python
DISCORD_TOKEN = "seu_token_aqui"
GEMINI_API_KEY = "sua_chave_api_aqui"
```

## 🎯 Como Usar

1. **Iniciar o Bot**: Execute `setup/Iniciar_Rebecca_Bot.bat` ou `python bot_manager.py` (da pasta Bot_Rebecca)
2. **Parar o Bot**: Use o gerenciador ou feche o processo
3. **Ver Logs**: Clique em "📋 Ver Logs" no gerenciador
4. **Testar Bot**: Execute `setup/testar_bot.bat` para ver logs em tempo real

## 🔄 Atualização via Git

O `.gitignore` já está configurado para ignorar arquivos locais:
- `bot_config.json` (configurações do gerenciador)
- `*.pid` (arquivos de processo)

Você pode atualizar o código com segurança usando:
```bash
git pull origin main
```

## ❓ Problemas Comuns

### Bot não inicia automaticamente
- Verifique se o atalho existe em `shell:startup`
- Execute `INSTALACAO_AUTOMATICA.bat` novamente

### Erro de dependências
- Execute: `pip install --upgrade customtkinter pillow pystray`

### Não encontra o Python
- Verifique se o Python está no PATH do sistema
- Reinstale o Python marcando "Add to PATH"

## 📞 Suporte

Para problemas ou dúvidas, verifique:
- Logs do gerenciador (botão "📋 Ver Logs")
- Arquivo de configuração `bot_config.json`
- Token do Discord em `config.py`
