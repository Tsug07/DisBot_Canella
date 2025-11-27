# 🤖 Gerson Bot Manager

Gerenciador completo para o Bot Gerson com interface gráfica moderna, monitoramento em tempo real e execução em segundo plano.

## 📋 Características

- ✅ Interface gráfica moderna (Dark Mode)
- 🔒 Execução em segundo plano
- 📊 Monitoramento de logs em tempo real
- 💻 Inicialização automática com Windows
- 🔄 Reinício automático programável
- 🔔 Ícone na bandeja do sistema
- 📝 Histórico completo de logs

## 🚀 Instalação

### 1. Instalar dependências

```bash
cd Bot_Gerson
pip install -r requirements.txt
```

### 2. Configurar o Bot

Certifique-se de que o arquivo `config/.env` está configurado corretamente com:
- `DISCORD_TOKEN`: Token do bot do Discord
- `DISCORD_CHANNEL_ID`: ID do canal para notificações
- `GOOGLE_SHEET_ID`: ID da planilha do Google Sheets
- `GOOGLE_CREDENTIALS_FILE`: Nome do arquivo de credenciais (dentro da pasta config)

## 📖 Como Usar

### Iniciar o Gerenciador

```bash
python bot_manager.py
```

O gerenciador irá:
1. Iniciar minimizado na bandeja do sistema
2. Iniciar o bot automaticamente
3. Monitorar o bot em segundo plano

### Funcionalidades da Interface

#### Botões Principais
- **▶️ Iniciar**: Inicia o bot
- **⏹️ Parar**: Para o bot
- **🔄 Reiniciar**: Reinicia o bot
- **📋 Ver Logs**: Abre janela com logs em tempo real

#### Configurações

**🔒 Rodar em segundo plano**
- Quando ativado, o bot continua rodando mesmo após fechar a janela do gerenciador
- Acesse o gerenciador pelo ícone na bandeja do sistema

**💻 Iniciar com Windows**
- Configura o bot para iniciar automaticamente com o Windows
- Útil para manter o bot sempre online

**🔄 Reiniciar a cada X horas**
- Reinicia o bot automaticamente no intervalo configurado
- Útil para manter o bot estável e atualizado

### Ícone na Bandeja do Sistema

Quando minimizado, o gerenciador fica na bandeja do sistema com as opções:
- **Mostrar Gerenciador**: Abre a janela principal
- **Parar Bot**: Para o bot em execução
- **Fechar Gerenciador**: Encerra o gerenciador (e o bot)

## 🛠️ Estrutura de Arquivos

```
Bot_Gerson/
├── main.py                    # Script principal do bot
├── bot_manager.py             # Gerenciador do bot
├── requirements.txt           # Dependências
├── config/
│   ├── .env                   # Variáveis de ambiente
│   └── credentials.json       # Credenciais Google Sheets
├── data/
│   ├── estado_empresas.json   # Estado atual das empresas
│   └── historico_alteracoes.json  # Histórico de alterações
├── logs/
│   └── bot_logs.log          # Logs do bot
└── backups/
    └── estado_empresas_backup_*.json  # Backups automáticos
```

## 📊 Logs

Os logs são salvos automaticamente em:
- **Arquivo**: `logs/bot_logs.log`
- **Interface**: Janela "Ver Logs" no gerenciador

Os logs incluem:
- Inicialização do bot
- Detecção de alterações na planilha
- Envio de notificações no Discord
- Erros e avisos

## ⚙️ Arquivos de Configuração

### bot_config.json
Criado automaticamente com as configurações do gerenciador:
```json
{
    "auto_restart": false,
    "restart_interval_hours": 24,
    "run_detached": true
}
```

### gerson_bot.pid
Arquivo temporário que armazena o PID do processo do bot quando em execução.

## 🔧 Solução de Problemas

### Bot não inicia
1. Verifique se todas as dependências estão instaladas
2. Confirme que o arquivo `.env` está configurado corretamente
3. Verifique os logs na janela "Ver Logs"

### Bot para inesperadamente
1. Abra a janela "Ver Logs" para ver a causa
2. Verifique se o token do Discord é válido
3. Confirme que as credenciais do Google Sheets são válidas

### Ícone da bandeja não aparece
1. Reinstale a dependência: `pip install --upgrade pystray`
2. Verifique se o Pillow está instalado: `pip install --upgrade Pillow`

## 📝 Comandos do Bot

O bot possui os seguintes comandos no Discord:

- `/help`: Mostra todos os comandos disponíveis
- `/ping`: Testa a latência do bot
- `/status`: Mostra status do bot e empresas monitoradas
- `/relatorio [mes] [ano]`: Gera relatório mensal
- `/historico`: Mostra competências com alterações

## 🤝 Suporte

Para problemas ou dúvidas, consulte os logs ou entre em contato com o suporte técnico.

---

**CANELLA & SANTOS CONTABILIDADE EIRELI**
