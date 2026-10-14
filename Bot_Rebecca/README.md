# Bot Rebecca - Monitor de E-mails DEC

Bot Discord que monitora automaticamente a pasta DEC do Gmail e notifica no Discord as
mensagens fiscais pendentes do DEC-SEFAZ/RJ, marcando o responsável de cada empresa.

## Funcionalidades

- Monitora a pasta **DEC** do Gmail a cada 60 segundos
- Busca apenas e-mails **não lidos** com o assunto
  `Aviso de mensagens - Consulta DEC-SEFAZ/RJ`
- Processa somente a seção **"Mensagens não lidas dos últimos 90 dias"**
  (a seção de mensagens já lidas é ignorada)
- Agrupa as notificações por empresa (CNPJ) e envia um embed por empresa
- Identifica o responsável pela empresa na planilha do Google Sheets
  (coluna E = FISCAL), com match por similaridade de 80% no nome
- Menciona `@Legalização` + responsável quando há `Categoria: NOTIFICAÇÃO`
  com `Tipo de Mensagem: CADASTRO`; nos outros casos, apenas o responsável
- Ignora empresas com situação `BAIXA`, `DEVOLVIDA` ou `INATIVA`
- Envia relatório das empresas sem responsável mapeado
- Trata também o **Aviso de Procurações - SEFAZ/RJ**, enviado como PDF anexo
  para o @Legalização, apenas quando o conteúdo muda (ver seção própria abaixo)

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

## Aviso de Procurações (SEFAZ/RJ)

O bot trata um **segundo tipo de e-mail** do mesmo fornecedor, com assunto
`Aviso de procurações - SEFAZ/RJ`, que chega na mesma pasta DEC.

Diferenças em relação ao aviso do DEC:

| | Aviso do DEC | Aviso de Procurações |
|---|---|---|
| Menciona | Responsável fiscal + @Legalização | **Apenas @Legalização** |
| Formato | Um embed por empresa | **PDF anexo** + embed de resumo |
| Frequência | Toda vez que há notificação | **Só quando o conteúdo muda** |

**Por que PDF:** o relatório traz ~150 empresas em 5 seções, o que daria mais de
10 mensagens no Discord. O e-mail **não** traz PDF anexo — o bot gera o arquivo a
partir do HTML, com `reportlab`.

**Seções incluídas** (configuráveis em `SECOES_PROCURACOES`):

- Procurações vencendo nos próximos 30 dias
- Procurações pendentes de aceite
- Procurações vencidas nos últimos 12 meses

As seções *recusadas* e *renunciadas* ficam de fora de propósito: somam ~84
empresas de histórico e seriam mais ruído que ação.

**Só notifica quando muda:** o e-mail chega quase todo dia com o mesmo conteúdo.
O bot guarda uma impressão digital (hash) do último relatório em
`procuracoes_estado.json` e só avisa quando alguma empresa entra ou sai das
seções acompanhadas — o embed mostra o que mudou (ex.: `vencendo: +2 / -1`).

Se a geração do PDF falhar, o bot envia um resumo em texto em vez de ficar em
silêncio.

### Liberar o aviso para reenvio

Como os avisos de procurações ficam na pasta DEC, o `inicializar_processados.py`
também os marca. Para liberar o mais recente e forçar o envio do relatório:

```bash
python liberar_procuracoes.py              # simula
python liberar_procuracoes.py --aplicar    # libera o mais recente
```

## Controle "já processei"

O bot **não usa** a flag de lido/não-lido do Gmail para decidir o que processar.
Antes ele usava, e isso causava perda silenciosa de notificações: se qualquer
pessoa abrisse o e-mail no Gmail (ou no celular) antes do ciclo de 60 segundos,
o e-mail virava "lido" e o bot nunca o via.

Agora o controle é próprio do bot, em duas camadas independentes:

| Camada | O que é | Para que serve |
|---|---|---|
| Label `DEC-processado` | Aplicada no Gmail via `X-GM-LABELS` | Critério da busca: o bot só lê e-mails **sem** esta label |
| `emails_processados.json` | Histórico local de `X-GM-MSGID` | Rede de segurança: se a label falhar ou for removida à mão, impede reenvio |

Garantias do desenho:

- **Ninguém atrapalha o bot:** abrir, ler ou arquivar o e-mail no Gmail não afeta
  o processamento.
- **Nada é perdido:** a marcação acontece **somente após** o envio ao Discord
  concluir. Se o Discord falhar, o e-mail continua sem a label e é reprocessado
  no ciclo seguinte.
- **Nada é duplicado:** as duas camadas são verificadas; basta uma delas conhecer
  o e-mail para ele não ser reenviado.
- **Auto-correção:** se a label for removida mas o histórico local conhecer o
  e-mail, o bot reaplica a label sem reenviar notificação.

O `X-GM-MSGID` é usado em vez do ID de sequência IMAP porque é estável — o ID de
sequência muda conforme e-mails entram e saem da pasta.

### Primeira execução / depois de resetar

Numa pasta que já tem e-mails antigos, rode o script de inicialização **antes** de
subir o bot, senão ele processará todo o acervo de uma vez:

```bash
python inicializar_processados.py                 # simula, não altera nada
python inicializar_processados.py --aplicar       # aplica a label nos antigos
```

Para deixar os N e-mails mais recentes de fora (o bot ainda vai notificá-los):

```bash
python inicializar_processados.py --aplicar --manter-recentes 2
```

O `emails_processados.json` não é versionado (está no `.gitignore`), pois é estado
de runtime de cada instalação.

## Observações Importantes

- Certifique-se de que a pasta **DEC** existe no seu Gmail
- Se a pasta DEC estiver em um caminho diferente (ex: "INBOX/DEC"), ajuste a chamada
  `mail.select("DEC")` em `check_emails()`
- O intervalo de verificação é de 60 segundos (`@tasks.loop(seconds=60)` em `email_monitor`)

### Formato do e-mail do fornecedor (OCF Informática)

O parser tolera as variações de HTML já observadas, porque o fornecedor mudou o
layout sem avisar (o que deixou o bot silenciosamente sem enviar nada entre
ago/2026 e out/2026):

| Elemento | Formato antigo (até jan/2026) | Formato atual |
|---|---|---|
| Bloco da empresa | `<h4>CNPJ: ... \| Cliente: ...` | `<h3>CNPJ: ... \| Cliente: ...` |
| Campos da tabela | `<b>Categoria: </b>AVISO` | `<b>Categoria:</b> AVISO` |

Se as notificações pararem de chegar novamente, o log mostrará
`E-mail DEC-SEFAZ nao contem notificacoes no padrao esperado` — sinal de que o
HTML mudou outra vez. Use `debug_email.py` para capturar o HTML e comparar.

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
