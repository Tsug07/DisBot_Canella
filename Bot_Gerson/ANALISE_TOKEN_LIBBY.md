# Análise — Aplicar o modelo de token da Libby no Bot Gerson

Comparação entre a renovação de token do **Bot Gerson** (`atualizar_token_gestta.py`)
e o serviço de token da **Libby** (`canella_libby/server/app/token_service.py`), com
proposta de melhoria para acabar com as falhas intermitentes de sincronização.

---

## 1. Resposta curta

**Sim, o Gerson faz login no Onvio a cada renovação — e é exatamente esse o problema.**

O Gerson **não reaproveita** o token que já tem: a cada 6 horas ele sobe um Chrome
headless e refaz o SSO do zero, mesmo quando o token no disco ainda tem quase um dia
de validade. Se esse login falhar por qualquer motivo passageiro (Chrome não subiu,
2FA demorou, Auth0 desconfiou do headless), a rodada é registrada como **erro** e o
alerta vai para o Discord — ainda que a integração continuasse funcionando
perfeitamente com o token guardado.

A Libby resolveu isso com uma política **cache-first**: só faz login quando o token
realmente está vencendo. É esse comportamento que vale trazer.

---

## 2. Evidência: a falha de hoje (04/09/2026)

Sequência real extraída de `logs/bot_logs.log`:

```
04/09 02:17  [Gestta] Token: Token renovado (validade ~23h).
04/09 07:07  [Gestta] Reconciliação: add=0 fmt=0 remove=0 aplicados=0 erros=0
04/09 08:18  [Gestta] Token: Token renovado (validade ~23h).
04/09 14:19  [Gestta] Token: Falha ao obter token: Nao foi possivel obter o token
             via SSO/login (sessao expirou e/ou login automatico falhou...)
04/09 14:19  Alerta de falha do Gestta enviado no Discord.
```

Estado do arquivo de token no momento da conferência:

| Item | Valor |
|---|---|
| `config/gestta_token.txt` gravado em | 04/09 **08:18** |
| Validade restante | **~17,6 horas** |

O login das 14:19 falhou, **mas o token de 08:18 continuava válido por mais 17 horas**.
Nenhuma sincronização estava em risco. O alerta no Discord foi **ruído**: cobrou uma
ação manual ("faça login no Onvio") que não era necessária.

Note também que às 02:17 e às 08:18 o token foi renovado tendo o anterior ainda ~23h
de validade — dois logins completos, com 2FA, que não precisavam ter acontecido.

---

## 3. Causa raiz no código

### 3.1 O laço força o login sempre

[gerson_bot.py:1163](gerson_bot.py#L1163):

```python
ok, msg = await asyncio.to_thread(_refresh.renovar, launch=True, forcar=True)
```

E `renovar()` só consulta o cache quando **não** está forçado —
[atualizar_token_gestta.py:554-555](atualizar_token_gestta.py#L554-L555):

```python
if not forcar and token_valido(caminho):
    return True, "Token atual ainda valido; nada a fazer."
```

Com `forcar=True` fixo, a guarda de cache **nunca** é consultada. O `token_valido()`
existe, funciona e está escrito — mas é código morto no caminho automático.

### 3.2 Falha de login vira alerta mesmo com token bom

[gerson_bot.py:1166-1168](gerson_bot.py#L1166-L1168) trata qualquer `ok == False`
como incidente, sem antes perguntar "mas o token atual ainda serve?". Daí o alerta
falso das 14:19.

### 3.3 O headless do Gerson não se disfarça

O Gerson sobe o Chrome assim —
[atualizar_token_gestta.py:524](atualizar_token_gestta.py#L524):

```python
flags += ["--headless=new", "--disable-gpu"]
```

A Libby aprendeu (comentário no próprio código dela) que o Auth0 **recusa o login sem
dizer o motivo** quando reconhece automação: o headless anuncia `HeadlessChrome` no
user-agent e liga `navigator.webdriver`. O sintoma é exatamente o que o Gerson
registra — falha silenciosa, "2FA não solicitado", sem erro na tela.

A Libby contorna com user-agent normal, `--disable-blink-features=AutomationControlled`
e um script que apaga `navigator.webdriver` antes de a página carregar
(`_disfarcar()`).

### 3.4 Sem trava de concorrência

O Gerson pode disparar dois logins ao mesmo tempo: o laço de 6h e o `obter_token()`
sob demanda (chamado dentro de `messenger_gestta.py` quando o token está vencido).
Dois Chromes com o **mesmo perfil** (`C:\chrome_gestta`) se atrapalham — o próprio
`atualizar_token_gestta.py` avisa disso no cabeçalho. A Libby serializa com
`threading.Lock`.

### 3.5 Sem validação real do token

O Gerson confia no campo `exp` do JWT. A Libby bate no endpoint real e exige HTTP 200
antes de guardar (`_validar()`), então nunca salva um token que o servidor já rejeita.

---

## 4. O que a Libby faz (`token_service.py`)

| Mecanismo | Efeito |
|---|---|
| **Cache-first** (`ensure()`) | Usa o token guardado enquanto válido; login só no vencimento. |
| **Margem de 1h** (`MARGEM_SEG`) | Considera vencido 1h antes, evitando expirar no meio de uma operação. |
| **Renovação a cada 8h** | Proativa, mas sem descartar cache bom em falha. |
| **Validação HTTP 200** (`_validar`) | Só grava token que o servidor aceitou de fato. |
| **`threading.Lock`** | Um login por vez (perfil único do Chrome). |
| **Trava anti-bloqueio** (`_marcar_recusa`, `LIMITE_RECUSAS=3`) | Após 3 recusas de credencial, para de tentar — insistir **bloqueia a conta** no Auth0. |
| **Anti-detecção** (`_disfarcar`, UA próprio) | Auth0 não recusa o headless. |
| **Dois tokens num login** (`obter_tokens`) | `ngStorage-jwt` (core) + `user-jwt` (messenger) com um único 2FA. |

O trecho central — `canella_libby/server/app/token_service.py`:

```python
def ensure(log=print) -> dict:
    """Cache-first; login ao vivo (fallback) so quando vence/falha."""
    if _valido("gestta") and _valido("messenger"):
        carregar_para_env()
        return {"gestta": True, "messenger": True, "origem": "cache"}
    log("Token: cache vencido/ausente — fazendo login ao vivo (fallback)...")
    r = renovar(log, forcar=False)
    return {..., "origem": "login"}
```

> **Nota sobre `LIMITE_RECUSAS`:** o comentário da Libby registra que em 01/09/2026 a
> conta foi bloqueada após 6 rodadas seguidas de login recusado. O Gerson hoje repete
> o login a cada 6h indefinidamente e usa a **mesma conta Onvio** — está exposto ao
> mesmo risco.

---

## 5. Proposta para o Gerson

Ordenada por relação benefício/esforço. As três primeiras resolvem a queixa relatada.

### Prioridade 1 — Cache-first no laço de renovação (resolve o problema)

Trocar `forcar=True` por `forcar=False` em [gerson_bot.py:1163](gerson_bot.py#L1163),
e aumentar a margem de validade para pegar o vencimento com folga:

```python
# gerson_bot.py — antes
ok, msg = await asyncio.to_thread(_refresh.renovar, launch=True, forcar=True)

# depois: só faz login se o token estiver realmente vencendo
ok, msg = await asyncio.to_thread(_refresh.renovar, launch=True, forcar=False)
```

```python
# atualizar_token_gestta.py — margem maior que o intervalo do laço (6h),
# para o token nunca vencer entre duas verificações.
def token_valido(caminho=TOKEN_FILE, margem_seg=8*3600):
```

Efeito: com token de ~24h, o login cai de **4x/dia para ~1x/dia**. Menos logins =
menos oportunidade de falhar = menos alerta falso — e bem menos desgaste do 2FA.

### Prioridade 2 — Não alertar quando o token atual ainda serve

Em `manter_token_gestta()`, antes de alertar, checar o cache:

```python
if not ok:
    if _refresh.token_valido(margem_seg=3600):
        logger.warning(f"[Gestta] Renovação falhou, mas o token atual ainda é "
                       f"válido; seguindo com ele. Detalhe: {msg}")
    else:
        logger.error(f"[Gestta] Token: {msg}")
        self._agendar_alerta_gestta("token", msg)
```

Efeito: o alerta das 14:19 de hoje não teria sido enviado. O Discord passa a avisar
só quando a integração está **de fato** parada.

### Prioridade 3 — Trava anti-bloqueio de conta

Portar `_marcar_recusa` / `login_travado` / `limpar_recusas` da Libby, persistindo o
contador num arquivo em `data/` (o Gerson não tem banco). Após 3 recusas de
credencial seguidas, para de tentar e alerta pedindo revisão da senha/2FA.

Protege contra o cenário que já bloqueou a conta na Libby.

### Prioridade 4 — Anti-detecção no headless

Adotar as flags e o `_disfarcar()` da Libby em
[atualizar_token_gestta.py:524](atualizar_token_gestta.py#L524):

```python
flags += ["--headless=new", "--disable-gpu", "--window-size=1568,900",
          "--user-agent=" + UA_PADRAO,
          "--disable-blink-features=AutomationControlled"]
```

mais `Page.addScriptToEvaluateOnNewDocument` apagando `navigator.webdriver` logo após
abrir o WebSocket. Ataca a causa provável das falhas que sobrarem.

### Prioridade 5 — `threading.Lock` e validação HTTP

- Um `_lock` global em `atualizar_token_gestta.py` em volta do bloco que sobe o
  Chrome, para o laço de 6h e o `obter_token()` sob demanda nunca colidirem no perfil.
- Um `_validar()` que faz `GET .../company/contact?page=1&limit=1` e exige 200 antes
  de gravar o token.

### O que **não** vale portar

- **`obter_tokens()` (dois tokens)** — a Libby precisa do `ngStorage-jwt` para
  `/core/*`. O Gerson só usa `/messenger-admin/*`, que aceita o `user-jwt` que ele já
  obtém. Portar isso só adicionaria um handoff a mais para falhar.
- **Cópia de sessão do perfil padrão (`_copiar_sessao`)** — a Libby usa para partir
  de uma sessão já viva do usuário. O Gerson roda em VM com perfil dedicado
  (`C:\chrome_gestta`); não se aplica.
- **Porta 9333** — a Libby mudou de porta para não colidir com o 9222. Se as duas
  automações rodarem na mesma máquina, vale conferir; hoje são VMs distintas.

---

## 6. Resumo comparativo

| Aspecto | Gerson (hoje) | Libby | Proposta |
|---|---|---|---|
| Reuso de token | ❌ `forcar=True` ignora o cache | ✅ cache-first | P1 |
| Logins/dia (token 24h) | ~4 | ~1 | P1 |
| Falha com token válido | ❌ alerta no Discord | ✅ segue com o cache | P2 |
| Margem de validade | 1h (não usada) | 1h (usada) | 8h |
| Trava anti-bloqueio | ❌ | ✅ 3 recusas | P3 |
| Anti-detecção Auth0 | ❌ | ✅ UA + disfarce | P4 |
| Login concorrente | ❌ sem trava | ✅ `threading.Lock` | P5 |
| Validação do token | só `exp` | `exp` + HTTP 200 | P5 |

---

## 7. Conclusão

O que a Libby tem e o Gerson não é, essencialmente, **uma linha de decisão**: perguntar
"o token que eu já tenho ainda serve?" antes de refazer o login. O Gerson tem a função
que responde isso (`token_valido()`) — ela só nunca é chamada no caminho automático,
porque o laço passa `forcar=True`.

As prioridades 1 e 2 são mudanças pequenas e localizadas (duas linhas e um `if`) e
sozinhas devem eliminar as falhas intermitentes relatadas, reduzindo os logins em ~75%.
As prioridades 3 a 5 são endurecimento: valem a pena, mas podem vir depois.

---

## 8. Status da implementação (04/09/2026)

**P1 e P2 aplicadas.** P3–P5 seguem pendentes (endurecimento, sem urgência).

| Arquivo | Mudança |
|---|---|
| `atualizar_token_gestta.py` | `MARGEM_PADRAO_SEG` (intervalo do laço + 2h = 8h); `token_valido(margem_seg=None)` passa a usá-la. |
| `gerson_bot.py` | Laço de renovação com `forcar=False`; novo `_tratar_falha_token_gestta()` só alerta se o token atual já não serve. |
| `messenger_gestta.py` | Chamada sob demanda fixada em `margem_seg=3600` (uso imediato — margem larga aqui subiria Chrome à toa). |

Matriz de decisão verificada:

| Validade restante | Refaz login? | Alerta se falhar? |
|---|---|---|
| 23 h (logo após renovar) | não | — |
| **17,6 h (falha de hoje, 14:19)** | **não** | **—** |
| 9 h | não | — |
| 7,5 h (dentro da margem) | sim | não — segue com o cache |
| 0,5 h / vencido | sim | **sim** (correto: integração em risco) |

A falha das 14:19 de hoje **não teria ocorrido**: com 17,6h de validade o laço nem
tentaria o login. Logins caem de ~4/dia para ~1/dia.

### P4 aplicada (04/09/2026) — causa raiz da falha de hoje

Investigação dos logs mostrou que a falha das 14:19 **não foi de credencial**: não há
nenhum `[login]` nem `[login][debug]` antes do erro (com `GESTTA_LOGIN_DEBUG=1` ligado),
ou seja, o fluxo nem chegou à tela de login. E às 08:18, no sucesso, o debug mostrou
`"url":"/staff/"` com `"inputs":[]` — já logado, sem 2FA. A mensagem genérica
"verifique credenciais/2FA" apontava para o lugar errado.

| Arquivo | Mudança |
|---|---|
| `atualizar_token_gestta.py` | `UA_PADRAO` (env `GESTTA_CHROME_UA`); flags `--user-agent`, `--disable-blink-features=AutomationControlled`, `--window-size=1568,900`; `_disfarcar()` via `Page.addScriptToEvaluateOnNewDocument`; `_diagnostico_chrome()` lendo o stderr; erros por etapa. |

Verificado em navegador real (perfil de teste descartável):

| Marca de automação | Antes | Depois |
|---|---|---|
| `navigator.userAgent` | `HeadlessChrome/...` | Chrome comum |
| `navigator.webdriver` | `true` | `undefined` |
| `navigator.languages` | vazio | `["pt-BR","pt","en-US"]` |
| `navigator.plugins.length` | `0` | `5` |
| viewport | sem tamanho | 1552px |

Renovação real forçada: **OK, token válido ~24h, aceito pela API (HTTP 200, 2123
contatos)**. Novo log `[login] SSO silencioso (sessao do perfil ainda viva).`

Erros agora distinguem: Chrome não subiu (com stderr) / credencial recusada / token não
apareceu (com etapa e URL). Só o segundo caso culpa credencial.

### P3 aplicada (04/09/2026) — trava anti-bloqueio de conta

| Arquivo | Mudança |
|---|---|
| `atualizar_token_gestta.py` | Detecção da mensagem de recusa do Auth0 (pt/en); `marcar_recusa` / `login_travado` / `limpar_recusas` persistindo em `data/gestta_recusas_login.json`; trava verificada **antes** de subir o Chrome; flags `--status` e `--destravar`. |
| `gerson_bot.py` | Alerta do Discord distingue credencial recusada (corrigir `.env` + `--destravar`) de sessão caída (relogar no Chrome); login travado **sempre** alerta, mesmo com token válido. |

Diferente de P1/P2, a trava só conta **recusa explícita de credencial** — rede, Chrome
que não sobe e página lenta não contam. Contar falha genérica travaria a integração por
motivo errado, que é pior que o problema original.

Testado:

| Teste | Resultado |
|---|---|
| 3 recusas → trava | liberado, liberado, **TRAVADO** |
| Trava bloqueia login | erro em **1s, sem subir Chrome** (antes: ~25s desperdiçados) |
| Persistência | processo novo lê do disco e vê a trava |
| `--destravar` | libera e descarta o contador |
| **Login real bem-sucedido** | **OK, contador segue limpo — sem falso positivo** |

Também corrigido: com a trava ativa e token ainda válido, a P2 silenciaria o alerta e
ninguém saberia da trava até o token vencer. Agora login travado sempre alerta.

Validação final (P1+P2+P3+P4 juntas): renovação real OK, token ~24h aceito pela API
(HTTP 200, 2123 contatos); segunda chamada retornou `Token atual ainda valido; nada a
fazer.` em 0s sem subir Chrome.

### P5 aplicada (04/09/2026) — concorrência e validação

| Arquivo | Mudança |
|---|---|
| `atualizar_token_gestta.py` | `_LOCK_LOGIN` (`threading.Lock`) serializa os logins; lock de arquivo `data/gestta_login_em_andamento.lock` (TTL 10 min) protege entre processos; `_validar_token()` exige HTTP 200 antes de gravar; recheca o cache após esperar no lock. |

**A colisão era real e foi comprovada:** subindo dois Chromes no mesmo perfil, o
DevTools do segundo **nunca responde** — em produção isso aparece como
"DevTools não respondeu", mais uma fonte de falha intermitente. O Gerson tinha 3
caminhos capazes de disparar renovação em threads distintas (laço de 6h, sync por
evento, reconciliação diária).

Por que dois locks: o `threading.Lock` só vale dentro do processo; o bot e a CLI
(`--launch` avulso) são processos diferentes. O lock de arquivo expira em 10 min para
que um processo morto não bloqueie renovações para sempre.

`_validar_token()` cobre o que o `exp` não vê: um token **revogado** (troca de senha,
sessão encerrada no Onvio) continua com `exp` no futuro e passaria no `token_valido()`.
Sem rede, aceita com base no `exp` — derrubar token bom por instabilidade seria pior.

Testado:

| Teste | Resultado |
|---|---|
| 3 threads simultâneas | **1 login no pico** (era 3), serializado em 6,0s |
| Token rejeitado pela API | não grava, mantém o anterior |
| Lock entre processos | recusa com mensagem clara |
| Lock órfão (20 min) | ignorado corretamente |
| Vazamento de lock | nenhum, inclusive nas saídas por erro |

**Validação final (P1+P2+P3+P4+P5):** renovação real passando pela **tela de login do
Auth0** (não pelo SSO silencioso) — `[login] Tela de login detectada` seguido de
`Token renovado e validado (~23h)`. Token aceito pela API (HTTP 200, 2123 contatos),
trava limpa, nenhum lock vazado, nenhum Chrome sobrando. Cache-first confirmado:
`Token atual ainda valido; nada a fazer.`

Esta foi a rodada mais informativa: ao contrário dos testes anteriores, exercitou o
caminho onde o Auth0 avalia o navegador — exatamente onde a P4 atua.

**Todas as cinco prioridades aplicadas.**
