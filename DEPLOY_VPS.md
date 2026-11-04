# Bots na VPS — deploy

Bip e Rebecca rodam na VPS da Libby, em containers próprios (`docker-compose.yml`
desta pasta), separados do compose da Libby. O Gerson continua na VM por enquanto.

| Bot | Container | Estado e logs na VPS |
|---|---|---|
| Bip | `disbot_bip` | `_vps/bip/` |
| Rebecca | `disbot_rebecca` | `_vps/rebecca/` |

> **Uma instância por vez.** O mesmo token rodando na VM e na VPS envia as
> mensagens em dobro. Sempre desligue na VM **antes** de ligar na VPS.

---

## Primeira instalação

Tudo pelo **Web console** da Hostinger (`scp`/`ssh` daqui não chegam na VPS).

### 1. Baixar o código

```bash
cd /root
git clone https://github.com/Tsug07/DisBot_Canella.git
cd DisBot_Canella
```

O GitHub pede usuário e **token** (não a senha).

### 2. Criar os `.env`

Os `.env` não vão pelo git. Copie o conteúdo do `.env` de cada bot na VM e cole:

```bash
cat > Bot_Bip/.env <<'FIM'
(colar aqui o conteúdo de Bot_Bip\.env da VM)
FIM

cat > Bot_Rebecca/.env <<'FIM'
(colar aqui o conteúdo de Bot_Rebecca\.env da VM)
FIM

chmod 600 Bot_Bip/.env Bot_Rebecca/.env
```

### 3. Desligar os bots na VM

1. No DisC0ntrol, pare **Bip** e **Rebecca**.
2. Tire os dois do início automático. O DisC0ntrol está com *Iniciar bots ao
   abrir* ligado e descobre sozinho tudo o que está em `DisBot_Canella`, então
   ele religaria os dois na próxima vez que abrir. Remova os cards (✕) ou
   desligue a opção. Confira também a pasta *Inicializar* do Windows
   (`shell:startup`), que o `Bot_Rebecca\setup\INSTALACAO_AUTOMATICA.bat` pode
   ter usado.

### 4. Levar o estado da Rebecca

Faça **depois** de desligar a Rebecca na VM, para copiar a versão final.

O `emails_processados.json` diz quais e-mails ela já avisou, e o
`procuracoes_estado.json` diz qual relatório de procurações já foi enviado.
Sem o primeiro, a label `DEC-processado` do Gmail ainda segura a maioria dos
reenvios. Sem o segundo, o próximo relatório de procurações é avisado de novo
uma vez.

```bash
mkdir -p _vps/rebecca/dados
cat > _vps/rebecca/dados/emails_processados.json <<'FIM'
(colar aqui Bot_Rebecca\emails_processados.json da VM)
FIM

cat > _vps/rebecca/dados/procuracoes_estado.json <<'FIM'
(colar aqui Bot_Rebecca\procuracoes_estado.json da VM)
FIM

python3 -m json.tool _vps/rebecca/dados/emails_processados.json > /dev/null && echo JSON ok
python3 -m json.tool _vps/rebecca/dados/procuracoes_estado.json > /dev/null && echo JSON ok
```

O Bip não guarda estado: ele lê só os e-mails não lidos.

### 5. Subir

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail 50 bot_bip bot_rebecca
```

Nos logs, cada bot deve mostrar o login no Discord, e o bot deve aparecer
online no servidor.

---

## Atualizar depois de uma mudança no código

No PC: commit e push. Na VPS:

```bash
cd /root/DisBot_Canella
git pull
docker compose up -d --build
```

O `_vps/` não é tocado pelo `git pull` nem pelo rebuild.

## Dia a dia

```bash
docker compose logs -f bot_rebecca       # acompanhar ao vivo
docker compose restart bot_bip           # reiniciar um bot
docker compose stop bot_rebecca          # parar (fica parado até um `up`)
docker stats --no-stream disbot_bip disbot_rebecca   # memória/CPU
tail -f _vps/rebecca/logs/rebecca_bot.log            # log completo (DEBUG)
```

Se um bot cair, o Docker o religa sozinho (`restart: unless-stopped`).

Os scripts auxiliares da Rebecca rodam dentro do container e usam o mesmo estado:

```bash
docker compose exec bot_rebecca python inicializar_processados.py
docker compose exec bot_rebecca python liberar_procuracoes.py
```

## Voltar para a VM

`docker compose stop bot_x` na VPS, copie o estado de `_vps/<bot>/dados/` de
volta para a pasta do bot na VM e ligue o bot pelo DisC0ntrol.

## Variáveis que o código entende

| Variável | Padrão (VM) | No container |
|---|---|---|
| `BOT_DATA_DIR` | pasta do bot | `/var/lib/bot/dados` |
| `BOT_LOG_DIR` | `logs` | `/var/lib/bot/logs` |
| `BOT_SEM_LOCK` | desligada | `1`: sem o `.lock`, porque o PID se repete entre reinícios do container e o bot se recusaria a subir |
