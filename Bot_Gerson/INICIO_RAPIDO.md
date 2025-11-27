# 🚀 Início Rápido - Gerson Bot Manager

## ⚡ Instalação em 3 Passos

### 1️⃣ Instalar Dependências
Execute o instalador automático:
```bash
scripts\instalar.bat
```

Ou manualmente:
```bash
pip install -r requirements.txt
```

### 2️⃣ Configurar Credenciais

#### a) Configurar Discord e Google Sheets
1. Copie o arquivo de exemplo:
   ```bash
   copy config\.env.example config\.env
   ```

2. Edite `config/.env` com suas credenciais:
   - `DISCORD_TOKEN`: Token do bot do Discord
   - `DISCORD_CHANNEL_ID`: ID do canal para notificações
   - `GOOGLE_SHEET_ID`: ID da planilha Google Sheets

#### b) Adicionar Credenciais do Google
Coloque o arquivo `credentials.json` na pasta `config/`

### 3️⃣ Iniciar o Bot
Execute o gerenciador:
```bash
scripts\iniciar_gerenciador.bat
```

Ou manualmente:
```bash
python bot_manager.py
```

## 🎯 Recursos Principais

### Interface do Gerenciador
- **▶️ Iniciar**: Inicia o bot
- **⏹️ Parar**: Para o bot
- **🔄 Reiniciar**: Reinicia o bot
- **📋 Ver Logs**: Visualiza logs em tempo real

### Configurações Disponíveis
- 🔒 **Segundo Plano**: Bot continua rodando ao fechar
- 💻 **Iniciar com Windows**: Inicia automaticamente
- 🔄 **Auto-restart**: Reinicia periodicamente

### Ícone na Bandeja
O gerenciador fica minimizado na bandeja do sistema:
- Clique para abrir o gerenciador
- Acesso rápido às funções principais
- Notificações de status

## 📊 Funcionalidades do Bot

### Monitoramento Automático
✅ Detecta novas empresas na planilha
✅ Monitora mudanças de status
✅ Acompanha alterações de regime tributário
✅ Envia relatórios mensais automaticamente

### Notificações no Discord
- 🆕 Nova empresa cadastrada
- ⚠️ Status problemático (INATIVA, BAIXA, etc.)
- ✅ Reativação de empresa
- 📋 Mudança de regime tributário
- 📊 Relatório mensal (dia configurável)

### Comandos Discord
- `/help` - Lista todos os comandos
- `/ping` - Verifica latência
- `/status` - Status do bot
- `/relatorio [mes] [ano]` - Relatório específico
- `/historico` - Histórico de alterações

## 🔍 Estrutura de Pastas

```
Bot_Gerson/
├── config/           # Configurações (credenciais)
├── data/             # Dados do bot (criado automaticamente)
├── logs/             # Logs (criado automaticamente)
├── backups/          # Backups automáticos (criado automaticamente)
├── scripts/          # Scripts de instalação e inicialização
├── main.py           # Bot principal
├── bot_manager.py    # Gerenciador
└── requirements.txt  # Dependências
```

## ❓ Solução Rápida de Problemas

### Bot não inicia?
1. Verifique se o arquivo `.env` está configurado
2. Confirme que `credentials.json` está na pasta `config/`
3. Veja os logs na janela "Ver Logs"

### Erro de dependências?
```bash
pip install --upgrade -r requirements.txt
```

### Ícone da bandeja não aparece?
```bash
pip install --upgrade pystray Pillow
```

## 📞 Próximos Passos

1. ✅ Configure o arquivo `.env`
2. ✅ Adicione `credentials.json`
3. ✅ Execute `scripts\iniciar_gerenciador.bat`
4. ✅ Configure "Iniciar com Windows" se desejar
5. ✅ Monitore os logs para garantir que tudo está funcionando

---

**Pronto! Seu bot está configurado e rodando em segundo plano! 🎉**

CANELLA & SANTOS CONTABILIDADE EIRELI
