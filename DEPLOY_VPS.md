# Bots na VPS — deploy

Bip, Rebecca e Gerson rodam na VPS da Libby, em containers próprios
(`docker-compose.yml` desta pasta), separados do compose da Libby.

| Bot | Container | Estado e logs na VPS |
|---|---|---|
| Bip | `disbot_bip` | `_vps/bip/` |
| Rebecca | `disbot_rebecca` | `_vps/rebecca/` |
| Gerson | `disbot_gerson` | `_vps/gerson/` (`config/`, `data/`, `logs/`, `backups/`) |

> **O repositório é público.** Estado (`data/`), `.env`, `credentials.json` e
> tokens nunca entram no git; eles chegam à VPS pelo Web console.

## Gerson e o token da Libby

Na VPS o Gerson **não faz login no Onvio**. Ele lê o token do Messenger que a
Libby já renova a cada 8h (`messenger_token.txt`, no volume `libby_gestta_tokens`,
montado só para leitura). As duas usam a mesma conta Onvio; dois robôs logando
nela por conta própria é o caminho para o Auth0 bloquear a conta.

- Quem liga isso são as variáveis `GESTTA_TOKEN_ORIGEM=libby` e
  `GESTTA_TOKEN_FILE` no `docker-compose.yml`. Sem elas (na VM), o Gerson faz
  o login próprio como sempre.
- Se o token da Libby vencer, o Gerson alerta no Discord apontando para a Libby
  (Configurações → login do Onvio), não para ele mesmo.
- **Ordem obrigatória:** a Libby precisa ser deployada com o volume antes do
  primeiro `up` daqui. Sem ele, o `up` falha com *external volume not found*.

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

## Instalação do Gerson

1. **Libby primeiro** (cria o volume do token):
   ```bash
   cd /root/canella_libby && git pull
   docker compose -f docker-compose.prod.yml up -d --build
   ```
   Esse primeiro deploy faz **um** login no Onvio, porque o volume nasce vazio.
   Daí em diante o token sobrevive aos deploys. Espere um ou dois minutos e confira:
   ```bash
   docker exec canella_libby ls -la /var/lib/libby-tokens
   ```
   Devem aparecer `gestta_token.txt` e `messenger_token.txt`.
2. **Desligue o Gerson na VM** (DisC0ntrol) e tire-o do início automático.
3. **Leve config e estado** da VM para `_vps/gerson/` pelo Web console: o `.env`
   (sem as linhas `GESTTA_ONVIO_*`, que na VPS não servem), o `credentials.json`
   e os arquivos `.json/.txt/.flag` de `data/`. Os PDFs antigos e os 25 mil
   arquivos de `backups/` ficam na VM.
4. **Suba:**
   ```bash
   cd /root/DisBot_Canella && git pull
   docker compose up -d --build
   docker compose logs --tail 60 bot_gerson
   ```
   Procure `[Gestta] Token: Token da Libby valido (~Nh restantes)`.

## Tela Bots na Libby (porteiro `disbot_controle`)

A Libby mostra e liga/desliga os bots pela tela **Bots do Discord** (menu
Acompanhar). O DP e o Fiscal só veem; ligar, desligar e reiniciar é só para admin.

A Libby **não** tem acesso ao Docker. Quem tem é o `disbot_controle`
(`controle/controle.py`), e ele só sabe fazer status, log, ligar, desligar e
reiniciar de três containers fixos. Os dois conversam pela rede `libby_bots`,
que não publica porta, usando um segredo compartilhado.

```
Libby ──(rede libby_bots + segredo)──> disbot_controle ──(docker.sock)──> disbot_bip / _rebecca / _gerson
```

### Instalação (uma vez)

1. **Gerar o segredo e gravá-lo nos dois lados.** O segredo nasce na própria
   VPS, então não precisa sair de lá:
   ```bash
   TOKEN=$(openssl rand -hex 32)
   cd /root/DisBot_Canella
   echo "CONTROLE_TOKEN=$TOKEN" > controle.env && chmod 600 controle.env
   cd /root/canella_libby
   cp .env.production .env.production.bak
   grep -v '^BOTS_CONTROLE_TOKEN=' .env.production.bak > .env.production
   echo "BOTS_CONTROLE_TOKEN=$TOKEN" >> .env.production
   unset TOKEN
   ```
2. **Libby primeiro**, porque ela cria a rede `libby_bots`:
   ```bash
   cd /root/canella_libby && git pull
   docker compose -f docker-compose.prod.yml up -d --build
   ```
3. **Depois os bots** (sobe o `disbot_controle`):
   ```bash
   cd /root/DisBot_Canella && git pull
   docker compose up -d --build
   docker compose logs --tail 5 controle
   ```
   O esperado é `Porteiro dos bots ouvindo na porta 8090; bots: bip, rebecca, gerson`.

### Bom saber

- **Desligar pela tela** dura até alguém ligar de novo, mesmo depois de reiniciar
  a VPS. **Mas um `docker compose up -d` aqui liga todos de novo.** Para atualizar
  só alguns, passe os nomes: `docker compose up -d --build bot_gerson controle`.
- **Quem fez o quê:** `docker compose logs controle` mostra cada ação, com o
  nome de quem clicou.
- **Mensagens na tela:**
  - "não está configurado": falta o `BOTS_CONTROLE_TOKEN` no `.env.production`.
  - "recusou o segredo": os dois arquivos têm segredos diferentes.
  - "Não foi possível falar": o `disbot_controle` está parado.
- **Bot novo** precisa entrar em `BOTS`, nos dois arquivos:
  `controle/controle.py` (o nome do container) e
  `canella_libby/server/app/bots.py` (os textos da tela).

## Atualizar depois de uma mudança no código

No PC: commit e push. Na VPS:

```bash
cd /root/DisBot_Canella
git pull
docker compose up -d --build
```

Isso **religa** qualquer bot que tenha sido desligado pela tela Bots. Se algum
deve continuar desligado, desligue de novo pela tela ou suba só os outros
serviços, passando os nomes deles.

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
| `GESTTA_TOKEN_ORIGEM` (Gerson) | login próprio | `libby`: só lê o token da Libby |
| `GESTTA_TOKEN_FILE` (Gerson) | `config/gestta_token.txt` | `/var/lib/libby-tokens/messenger_token.txt` |
| `GERSON_MAX_BACKUPS` (Gerson) | sem limite | `500` cópias de `estado_empresas.json` |

Os bots Bip e Rebecca guardam estado em `BOT_DATA_DIR`. O Gerson usa as pastas
`config/ data/ logs/ backups/` ao lado do código, e cada uma vira um bind mount.
