# Bot Rebecca - Monitor de E-mails DEC

Bot Discord que monitora automaticamente a pasta DEC do Gmail e envia notificações quando recebe e-mails específicos sobre operações de ofício.

## Funcionalidades

- Monitora a pasta **DEC** do Gmail a cada 60 segundos
- Busca apenas e-mails **não lidos**
- Filtra e-mails que contêm:
  - `Categoria: NOTIFICAÇÃO`
  - `Tipo de Mensagem: CADASTRO`
  - `Notificação de realização de operação de ofício` no assunto
- Envia notificações formatadas no Discord com embed roxo

## Requisitos

- Python 3.8 ou superior
- Conta Gmail com acesso IMAP habilitado
- Bot Discord criado no Discord Developer Portal
- Senha de aplicativo do Gmail (não use sua senha normal)

## Instalação

### 1. Clone o repositório ou baixe os arquivos

### 2. Instale as dependências

```bash
pip install -r requirements.txt
```

### 3. Configure as variáveis de ambiente

Copie o arquivo `.env.example` para `.env` e preencha com suas credenciais:

```bash
cp .env.example .env
```

Edite o arquivo `.env`:

```env
GMAIL_USER=seu_email@gmail.com
GMAIL_PASS=sua_senha_de_aplicativo_gmail
DISCORD_TOKEN=seu_token_do_bot_discord
CHANNEL_ID=id_do_canal_discord
```

## Como obter as credenciais

### Senha de Aplicativo do Gmail

1. Acesse [myaccount.google.com](https://myaccount.google.com)
2. Vá em **Segurança**
3. Ative **Verificação em duas etapas** (se ainda não estiver ativada)
4. Procure por **Senhas de app**
5. Crie uma nova senha de app para "E-mail"
6. Copie a senha gerada (16 caracteres)

### Token do Bot Discord

1. Acesse [Discord Developer Portal](https://discord.com/developers/applications)
2. Crie uma nova aplicação ou selecione uma existente
3. Vá em **Bot** no menu lateral
4. Copie o **Token** (se não aparecer, clique em "Reset Token")
5. Em **Privileged Gateway Intents**, habilite:
   - Message Content Intent
   - Server Members Intent

### ID do Canal Discord

1. Ative o Modo Desenvolvedor no Discord:
   - Configurações → Avançado → Modo Desenvolvedor
2. Clique com botão direito no canal desejado
3. Selecione **Copiar ID do Canal**

## Uso

Execute o bot:

```bash
python rebecca_bot.py
```

Você verá a mensagem:

```
Rebecca está online 🟣
```

O bot começará a monitorar automaticamente os e-mails.

## Estrutura do Projeto

```
Bot_Rebecca/
├── rebecca_bot.py      # Código principal do bot
├── requirements.txt    # Dependências Python
├── .env               # Variáveis de ambiente (não versionar)
├── .env.example       # Exemplo de configuração
└── README.md          # Este arquivo
```

## Observações Importantes

- O bot marca os e-mails como lidos após processá-los
- Certifique-se de que a pasta **DEC** existe no seu Gmail
- Se a pasta DEC estiver em um caminho diferente (ex: "INBOX/DEC"), ajuste a linha 41 do código
- O intervalo de verificação é de 60 segundos (configurável na linha 76)

## Solução de Problemas

### Erro ao conectar no Gmail

- Verifique se o IMAP está habilitado nas configurações do Gmail
- Use uma senha de aplicativo, não sua senha normal
- Confirme que a verificação em duas etapas está ativada

### Bot não envia mensagens no Discord

- Verifique se o bot tem permissões para enviar mensagens no canal
- Confirme que o CHANNEL_ID está correto
- Verifique se as intents necessárias estão habilitadas

### Pasta DEC não encontrada

Para listar todas as pastas disponíveis, adicione temporariamente no código:

```python
mail.list()
```

Isso mostrará todos os nomes de pastas disponíveis.

## Licença

Este projeto é de uso pessoal/interno.
