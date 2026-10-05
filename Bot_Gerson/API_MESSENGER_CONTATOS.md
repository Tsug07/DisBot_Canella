# API do Messenger (Gestta) — Alteração de Nomes de Contatos

Referência técnica da API usada pelo **Bot Gerson** para ler e alterar o campo `name`
dos contatos de empresa no Messenger do Gestta (acessado via Onvio / Thomson Reuters).

Implementação de referência: [messenger_gestta.py](messenger_gestta.py)
Autenticação/renovação de token: [atualizar_token_gestta.py](atualizar_token_gestta.py)
Documento operacional (rotina, alertas, .env): [README_GESTTA.md](README_GESTTA.md)

> A API do Messenger **não é pública nem documentada pela Thomson Reuters**. Os
> endpoints abaixo foram descobertos por inspeção do tráfego do próprio painel web
> (`app.gestta.com.br`). Podem mudar sem aviso — se a integração quebrar, o primeiro
> passo é reinspecionar as chamadas do painel na aba Network do navegador.

---

## 1. Endereço base e autenticação

| Item | Valor |
|---|---|
| Host | `https://api.gestta.com.br` |
| Recurso | `/messenger-admin/company/contact` |
| Autenticação | Header `Authorization: JWT <token>` |
| Validade do token | ~24 h |
| Content-Type (escrita) | `application/json` |

O token **não** é obtido por endpoint de login. Ele é emitido pelo SSO do Onvio e fica
guardado no `localStorage` do navegador, na chave `user-jwt`. O
[atualizar_token_gestta.py](atualizar_token_gestta.py) sobe um Chrome headless com o
perfil salvo, faz o handoff Onvio → Messenger e lê essa chave.

Cabeçalhos usados em todas as chamadas — [messenger_gestta.py:220-221](messenger_gestta.py#L220-L221):

```http
Authorization: JWT eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Accept: application/json
Content-Type: application/json
```

**Ordem de resolução do token** — [messenger_gestta.py:190-217](messenger_gestta.py#L190-L217):

1. Variável de ambiente `GESTTA_JWT` (prioridade máxima; útil para teste manual).
2. Arquivo `config/gestta_token.txt`. Se ausente ou expirado (margem de 1 h), o módulo
   tenta renovar sozinho subindo o Chrome headless.

O prefixo `JWT ` é normalizado automaticamente: pode-se gravar o token com ou sem ele.

---

## 2. `GET` — Listar contatos

```http
GET /messenger-admin/company/contact?page=1&limit=200&sort=name
Authorization: JWT <token>
```

### Parâmetros de query

| Parâmetro | Tipo | Usado pelo bot | Descrição |
|---|---|---|---|
| `page` | int | `1..n` | Página (1-based). |
| `limit` | int | `200` | Itens por página (`PAGE_LIMIT`). |
| `sort` | string | `name` | Campo de ordenação. |

### Resposta (paginada, formato mongoose-paginate)

```json
{
  "docs": [
    {
      "_id": "6512f8ab3c1d4e0012ab34cd",
      "name": "09/55/884 - JOSIAS",
      "phone_number": "5511999998888"
    }
  ],
  "totalDocs": 2143,
  "limit": 200,
  "page": 1,
  "hasNextPage": true,
  "nextPage": 2
}
```

Campos relevantes para a integração: **`_id`** (chave para o `PUT`), **`name`** (alvo da
alteração) e **`phone_number`** (obrigatório reenviar no `PUT` — ver §3).

### Paginação

A implementação itera até `hasNextPage == false`, com **trava de segurança em 100
páginas** (~20.000 contatos) para evitar loop infinito caso a API pare de sinalizar o
fim — [messenger_gestta.py:224-239](messenger_gestta.py#L224-L239):

```python
def listar_contatos(token, session=None):
    s = session or requests.Session()
    page = 1
    while True:
        r = s.get(API_BASE, headers=_headers(token),
                  params={"page": page, "limit": PAGE_LIMIT, "sort": "name"}, timeout=30)
        r.raise_for_status()
        j = r.json()
        for d in j.get("docs", []):
            yield d
        if not j.get("hasNextPage"):
            break
        page += 1
        if page > 100:
            break
```

> Não existe filtro server-side por nome/código. Para atualizar uma única empresa o bot
> ainda lista tudo e filtra em memória (`atualizar_por_codigo`) — o ganho está em
> escrever só nos contatos afetados, não em ler menos.

---

## 3. `PUT` — Alterar o nome de um contato

```http
PUT /messenger-admin/company/contact/6512f8ab3c1d4e0012ab34cd
Authorization: JWT <token>
Content-Type: application/json

{
  "name": "09/55/884 - JOSIAS [SUSPENSA: 9]",
  "phone_number": "5511999998888"
}
```

### Corpo da requisição

| Campo | Tipo | Obrigatório | Observação |
|---|---|---|---|
| `name` | string | Sim | Nome completo já formatado. A API **substitui**, não faz merge. |
| `phone_number` | string | Sim | Reenviar o valor atual, vindo do `GET`. |

⚠️ **`phone_number` deve sempre ser reenviado.** O endpoint trata o corpo como
representação completa do recurso; omitir o telefone o apaga. O bot repassa o valor lido
na listagem e usa `""` como fallback quando o contato não tem telefone —
[messenger_gestta.py:242-248](messenger_gestta.py#L242-L248):

```python
def atualizar_contato(token, contact_id, novo_nome, phone_number, session=None):
    s = session or requests.Session()
    r = s.put(API_BASE + "/" + str(contact_id), headers=_headers(token),
              data=json.dumps({"name": novo_nome, "phone_number": phone_number or ""}),
              timeout=30)
    r.raise_for_status()
    return r.json() if r.content else {}
```

### Resposta

Retorna o documento atualizado em JSON. Corpo vazio também é aceito (o cliente devolve
`{}` nesse caso). Erro HTTP vira exceção via `raise_for_status()`.

### Códigos de status esperados

| Status | Significado | Tratamento no bot |
|---|---|---|
| `200` | Alteração aplicada. | Conta em `aplicados`. |
| `401` / `403` | Token expirado ou inválido. | Erro registrado; alerta no Discord (sessão SSO caiu). |
| `404` | `_id` inexistente (contato removido entre o `GET` e o `PUT`). | Erro registrado; segue para o próximo. |
| `429` / `5xx` | Limite de taxa ou falha do servidor. | Erro registrado; corrigido na varredura diária seguinte. |

Não há retry automático por contato: uma falha isolada é logada e o item é reprocessado
na próxima reconciliação (a operação é idempotente).

### Controle de taxa

Não há limite documentado. O bot aplica **pausa de 150 ms entre escritas** por
gentileza com a API — [messenger_gestta.py:291](messenger_gestta.py#L291). Numa
varredura completa com poucas dezenas de alterações o custo é desprezível.

---

## 4. Regra de formação do `name`

O campo `name` é a única superfície de dados disponível: a API não expõe o código da
empresa em campo próprio, então ele é lido do próprio texto do nome.

### Formato do contato

```
<códigos separados por / ou espaço> - <NOME DA PESSOA> [marcações]
```

### Extração dos códigos — [messenger_gestta.py:106-122](messenger_gestta.py#L106-L122)

1. Corta o nome no primeiro ` - ` seguido de letra (separador entre códigos e nome).
2. Extrai todos os grupos de dígitos do trecho inicial.
3. Normaliza zeros à esquerda: `09` → `9`, `007` → `7`.
4. Remove duplicatas preservando a ordem.

| `name` original | Códigos extraídos |
|---|---|
| `09/55/884 - JOSIAS` | `9`, `55`, `884` |
| `52/278 - ADRIANA #SOC` | `52`, `278` |
| `615 - JOCIMAR [SUSPENSA]` | `615` |

### Sufixo de suspensão

Formato canônico, com os códigos suspensos ordenados numericamente:

```
[SUSPENSA: 854, 948]
```

O reconhecimento de marcações **já existentes** é tolerante: a regex
`\s*\[[^\]]*suspensa[^\]]*\]` (case-insensitive) casa qualquer colchete que contenha a
palavra "suspensa" — [messenger_gestta.py:63](messenger_gestta.py#L63). Isso cobre o
histórico de marcações manuais feitas à mão pelos atendentes:

`[SUSPENSA]`, `[ SUSPENSA]`, `[881 SUSPENSA]`, `[239, 994 SUSPENSA]`, `[SUSPENSA: 46]`.

Todas são reescritas para o formato canônico.

### Decisão de escrita — [messenger_gestta.py:133-163](messenger_gestta.py#L133-L163)

`calcular_novo_nome()` compara o nome atual com o estado das empresas em
`data/estado_empresas.json` (fonte da verdade) e devolve uma das ações:

| Ação | Condição | Faz `PUT`? |
|---|---|---|
| `add` | Há código suspenso e o contato não tinha marcação. | Sim |
| `fmt` | Há código suspenso e a marcação existente está fora do padrão. | Sim |
| `remove` | Nenhum código suspenso, **e** ao menos um código é conhecido pelo Gerson. | Sim |
| `skip_risk` | Tem marcação, mas **nenhum** código é conhecido pelo Gerson. | Não — preserva |
| `none` | Nome já está correto. | Não |

A ação `skip_risk` é a salvaguarda central: se o Gerson não conhece nenhum dos códigos
do contato, ele não tem base para afirmar que a empresa está ativa — então a marcação
manual do atendente é preservada em vez de apagada.

**Idempotência:** rodar a sincronização N vezes seguidas produz o mesmo resultado; a
partir da segunda execução todas as ações são `none`.

---

## 5. Fluxos de uso

### 5.1 Sincronização completa — `sincronizar()`

Percorre todos os contatos e aplica as alterações necessárias.
[messenger_gestta.py:254-300](messenger_gestta.py#L254-L300)

```python
res = messenger_gestta.sincronizar(apply=True)
```

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `apply` | `False` | **Dry-run por padrão.** Só grava com `apply=True`. |
| `token` | `None` | Token explícito; se omitido, resolve via `obter_token()`. |
| `estado_path` | `data/estado_empresas.json` | Fonte da verdade. |
| `limite` | `None` | Interrompe após N alterações (teste gradual). |
| `session` | `None` | `requests.Session` reaproveitada. |

Retorno:

```python
{
  "resumo":     {"total": 2143, "add": 3, "fmt": 1, "remove": 2,
                 "skip_risk": 7, "aplicados": 6, "erros": 0},
  "alteracoes": [{"id": "...", "acao": "add", "antes": "...", "depois": "..."}],
  "riscos":     [{"id": "...", "name": "...", "codigos": ["1200"]}],
  "erros":      [{"id": "...", "erro": "..."}]
}
```

### 5.2 Atualização pontual — `atualizar_por_codigo()`

Reavalia apenas os contatos que citam um código específico. Usado no momento em que o
Gerson detecta mudança de status de uma empresa.
[messenger_gestta.py:306-338](messenger_gestta.py#L306-L338)

```python
res = messenger_gestta.atualizar_por_codigo("46", apply=True)
# {"codigo": "46", "verificados": 3, "aplicados": 3, "alteracoes": [...], "erros": []}
```

Diferenças em relação a `sincronizar()`: `apply` é `True` por padrão e não há pausa entre
escritas (o volume é de poucos contatos).

### 5.3 Gatilhos automáticos no Gerson

| Gatilho | Chamada | Onde |
|---|---|---|
| Empresa vira SUSPENSA | `atualizar_por_codigo(codigo, apply=True)` | [gerson_bot.py:1285](gerson_bot.py#L1285) |
| Empresa volta a ATIVA | `atualizar_por_codigo(codigo, apply=True)` | [gerson_bot.py:1317](gerson_bot.py#L1317) |
| Varredura diária (07:00) | `sincronizar(apply=True)` | [gerson_bot.py:1211](gerson_bot.py#L1211) |
| Renovação de token (6/6 h) | `atualizar_token_gestta.renovar(launch=True)` | [gerson_bot.py:1163](gerson_bot.py#L1163) |

As chamadas de evento rodam em thread separada (`asyncio.to_thread`) e são
**best-effort**: qualquer exceção é logada e dispara alerta no Discord, sem derrubar o
bot — [gerson_bot.py:1078-1099](gerson_bot.py#L1078-L1099).

---

## 6. CLI

Todos os comandos rodam na pasta `Bot_Gerson`.

```cmd
REM Dry-run: mostra o que seria alterado, sem gravar nada
python messenger_gestta.py

REM Aplica em todos os contatos
python messenger_gestta.py --apply

REM Aplica somente nas 5 primeiras alterações (teste gradual)
python messenger_gestta.py --apply --limite 5

REM Atualiza apenas os contatos que citam o código 46
python messenger_gestta.py --codigo 46 --apply

REM Usa um estado alternativo (ex.: um backup)
python messenger_gestta.py --estado backups\estado_empresas_backup_20260302_084553.json
```

| Flag | Descrição |
|---|---|
| `--apply` | Grava as alterações. Sem ela, é dry-run. |
| `--codigo <n>` | Restringe a um código de empresa. |
| `--limite <n>` | Máximo de alterações (só no modo completo). |
| `--estado <path>` | Caminho alternativo do `estado_empresas.json`. |

Sem `--codigo`, a saída é um resumo legível com contagem por ação, 15 exemplos de
alteração e a lista de pulados. Com `--codigo`, a saída é o JSON do resultado.

---

## 7. Teste manual da API (fora do bot)

Útil para validar credenciais ou confirmar que o endpoint continua o mesmo:

```cmd
REM 1) Renova e lê o token
python atualizar_token_gestta.py --launch --forcar
type config\gestta_token.txt
```

```bash
# 2) Lista a primeira página
curl -H "Authorization: JWT <token>" \
     "https://api.gestta.com.br/messenger-admin/company/contact?page=1&limit=5&sort=name"

# 3) Altera um contato (atenção: escreve de verdade)
curl -X PUT \
     -H "Authorization: JWT <token>" \
     -H "Content-Type: application/json" \
     -d '{"name":"09/55/884 - JOSIAS [SUSPENSA: 9]","phone_number":"5511999998888"}' \
     "https://api.gestta.com.br/messenger-admin/company/contact/<_id>"
```

---

## 8. Diagnóstico

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `401`/`403` em toda chamada | Token expirado; sessão SSO do Onvio caiu. | Rodar `scripts\iniciar_chrome_gestta.bat`, logar no Onvio, abrir o Messenger uma vez e fechar. |
| `Token do Gestta nao encontrado` | Sem `GESTTA_JWT`, sem `config/gestta_token.txt` e sem perfil de Chrome logado. | Renovar com `python atualizar_token_gestta.py --launch --forcar`. |
| Contato perdeu o telefone | `PUT` enviado sem `phone_number`. | Sempre reenviar o valor lido no `GET` (§3). |
| Muitos `skip_risk` no resumo | Contatos com códigos que o Gerson não conhece. | Conferir a planilha de origem — os códigos podem estar ausentes ou grafados de outra forma. |
| Alterações não aparecem no painel | Executou em dry-run. | Acrescentar `--apply`. |
| Nenhuma alteração e nenhum erro | O estado já está sincronizado (idempotência). | Nada a fazer. |
| `404` em contatos específicos | Contato removido entre a listagem e a escrita. | Ignorável; a varredura seguinte já não o encontra. |

Logs da integração ficam em `logs/bot_logs.log`, prefixados com `[Gestta]`.

---

## 9. Limitações conhecidas

- **API não oficial.** Sem contrato de estabilidade; qualquer alteração no painel do
  Gestta pode quebrar a integração.
- **Sem filtro server-side.** Toda operação lista a base inteira (~2.000 contatos), mesmo
  para atualizar um único código.
- **Sem escrita em lote.** Um `PUT` por contato.
- **`name` é campo livre.** Código da empresa e marcação de status convivem no mesmo
  texto que os atendentes editam à mão — daí a necessidade da regex tolerante e da
  salvaguarda `skip_risk`.
- **Token de vida curta (~24 h)** e dependente de sessão SSO em perfil de Chrome, que
  eventualmente exige relogin manual.
