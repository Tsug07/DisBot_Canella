# Integração Gerson × Messenger (Gestta/Onvio)

Este documento explica como funciona a marcação automática de empresas **suspensas**
nos contatos do **Messenger do Gestta** (acessado via Onvio), integrada ao Bot Gerson.

---

## O que faz

Quando uma empresa fica **SUSPENSA**, o nome dos contatos dela no Messenger recebe o
sufixo padronizado `[SUSPENSA: <código>]`. Quando volta a ficar ativa, o sufixo é
removido. Assim o atendente vê na hora que aquele cliente está bloqueado.

Exemplos:

```
09/55/884 - JOSIAS        ->  09/55/884 - JOSIAS [SUSPENSA: 09]
52/278 - ADRIANA #SOC      ->  52/278 - ADRIANA #SOC [SUSPENSA: 52]
615 - JOCIMAR [SUSPENSA]   ->  615 - JOCIMAR [SUSPENSA: 615]   (padroniza marcação antiga)
1025 - LUCAS ... #INATIVO [SUSPENSA: 1025]  ->  1025 - LUCAS ... #INATIVO   (empresa não está mais suspensa)
```

### Regras

- A **fonte da verdade** é o arquivo `data/estado_empresas.json` (o estado que o Gerson
  já mantém a partir da planilha do Google Sheets). O `.env` **não** decide quem está
  suspenso — só liga/ajusta a integração.
- Os códigos das empresas são lidos do próprio **nome do contato** (o trecho antes do
  ` - NOME`), separados por `/`, com normalização de zeros à esquerda (`09` = `9`).
- Se um contato tem vários códigos, marca **todos os que estão suspensos**:
  `[SUSPENSA: 854, 948]`.
- **Idempotente:** rodar várias vezes produz o mesmo resultado.
- **Segurança:** se um contato tem marcação antiga mas **nenhum** dos seus códigos é
  conhecido pelo Gerson, a marcação é **preservada** (não remove por engano). Esses
  aparecem como `PULADOS (arriscados)` nos relatórios.

---

## Quando roda (gatilhos)

1. **No evento** — assim que o Gerson detecta a empresa virar suspensa (ou voltar a
   ativa), atualiza na hora os contatos daquele código.
2. **Varredura diária** — 1x/dia (padrão 07:00) revisa **todos** os contatos e corrige
   qualquer divergência (mudança fora do horário, marcação manual nova, etc.).
3. **Renovação de token** — a cada 6h o bot renova sozinho o acesso ao Gestta.

Tudo roda **dentro do Gerson**, então é controlado e monitorado pelo card do Gerson no
**DisC0ntrol** (start/stop/restart e logs).

---

## Login e token (como o acesso é obtido)

O Messenger é acessado por **SSO via Onvio** (Thomson Reuters). O login direto no
Messenger não autentica; é preciso passar pelo Onvio. O token (JWT) do Gestta dura ~24h.

A renovação é **automática e headless**: o `atualizar_token_gestta.py --launch` sobe um
Chrome headless com o **perfil salvo** (`C:\chrome_gestta`), clica em "Entrar" (o SSO
resolve sozinho porque a sessão do provedor de identidade fica salva no perfil), abre o
Messenger, lê o token e fecha o Chrome. **Não digita senha.**

> **Importante:** o perfil precisa ter sido logado **uma vez** manualmente. Quando a
> sessão SSO expirar de vez, alguém precisa relogar (veja "Quando a sessão cair").

---

## Parâmetros do `.env`

| Variável | Padrão | Descrição |
|---|---|---|
| `GESTTA_SYNC_ENABLED` | `0` | Liga a integração. Use `1` para ativar. |
| `GESTTA_ALERT_MENTIONS` | (IDs) | Quem marcar no alerta de falha. `<@&ID>` = cargo, `<@ID>` = usuário. |
| `GESTTA_ALERT_THROTTLE_SEG` | `3600` | Intervalo mínimo (s) entre alertas repetidos. |
| `GESTTA_TOKEN_INTERVALO_H` | `6` | De quantas em quantas horas renovar o token. |
| `GESTTA_RECONCILE_HORA` | `7` | Hora do dia (0–23) para a varredura completa. |
| `GESTTA_JWT` | — | (Opcional) token fixo; tem prioridade sobre o arquivo. |
| `GESTTA_CHROME_HOST` / `GESTTA_CHROME_PORT` | `127.0.0.1` / `9222` | Chrome de depuração (modo conexão). |

---

## Arquivos

| Arquivo | Função |
|---|---|
| `messenger_gestta.py` | Lê o estado do Gerson, casa códigos com contatos, aplica/remove `[SUSPENSA]`. |
| `atualizar_token_gestta.py` | Renova o token (headless, SSO automático via perfil). |
| `scripts/iniciar_chrome_gestta.bat` | Abre o Chrome do Onvio para **semear o login** (uma vez). |
| `scripts/renovar_token_gestta.bat` | Renova o token via linha de comando (uso avulso/opcional). |
| `gerson_bot.py` | Dispara o sync no evento + loops de token (6h) e reconciliação (diária). |

---

## Comandos úteis (na pasta `Bot_Gerson`)

```cmd
REM Simular (não grava nada) — mostra o que faria:
python messenger_gestta.py

REM Aplicar de verdade em todos os contatos:
python messenger_gestta.py --apply

REM Aplicar só nas 5 primeiras (teste gradual):
python messenger_gestta.py --apply --limite 5

REM Atualizar só os contatos de uma empresa:
python messenger_gestta.py --codigo 46 --apply

REM Renovar o token manualmente (headless, SSO automático):
python atualizar_token_gestta.py --launch --forcar
```

---

## Como verificar que está funcionando

- No `logs/bot_logs.log`, procure por `[Gestta]`:
  - `[Gestta] Token: Token renovado (validade ~XXh)` — aparece no start e a cada 6h.
  - `[Gestta] Reconciliação: add=.. fmt=.. remove=.. aplicados=..` — aparece 1x/dia.
  - `[Gestta] sync código NNN: X contato(s) atualizado(s)` — no momento de uma mudança.
- A data de modificação de `config/gestta_token.txt` muda a cada renovação.

---

## Quando a sessão cair (login manual)

Se a sessão do Onvio expirar, a renovação falha e o Gerson **avisa no Discord**
(marcando os IDs configurados). Para regularizar:

1. Rode `scripts\iniciar_chrome_gestta.bat`.
2. Faça login no **Onvio** e abra o **Messenger** uma vez (Minhas Aplicações → Messenger).
3. Feche o Chrome. A sessão fica salva no perfil `C:\chrome_gestta` e a renovação
   automática volta a funcionar.

---

## Dependências

Adicionadas ao `requirements.txt`: `requests`, `websocket-client`
(além de `psutil`, já usado pelo projeto). Instale com:

```cmd
pip install -r requirements.txt
```

---

## Observações

- Os avisos `REGRESSÃO: API retornou dados ... (cache antigo)` no log são do
  monitoramento do Google Sheets do próprio Gerson — **não** têm relação com o Gestta.
- Login automático por **e-mail/senha** (sem depender da sessão salva) é possível no
  futuro, desde que a conta **não use verificação em duas etapas (2FA)**.
