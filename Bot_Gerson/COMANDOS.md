# Comandos do Bot

## 📚 Comandos Disponíveis

### `/help`
Mostra a lista completa de comandos disponíveis.

**Uso:**
```
/help
```

**Retorna:**
- Lista de todos os comandos
- Descrição de cada comando
- Informações sobre notificações automáticas

---

### `/ping`
Testa a latência do bot com o Discord.

**Uso:**
```
/ping
```

**Retorna:**
```
🏓 Pong!
Latência: XX.XXms
```

---

### `/status`
Mostra informações sobre o status atual do bot.

**Uso:**
```
/status
```

**Retorna:**
- **Empresas Monitoradas**: Quantidade total de empresas
- **Última Verificação**: Data/hora da última consulta à planilha
- **Status**: Se o bot está online

**Exemplo:**
```
📊 Status do Bot
Empresas Monitoradas: 150
Última Verificação: 19/11/2025 15:30:00
Status: ✅ Online
```

---

### `/relatorio [mes] [ano]`
Gera relatório mensal detalhado de alterações.

**Uso:**
```
/relatorio                → Mês atual
/relatorio 11 2024        → Novembro de 2024
/relatorio 1 2025         → Janeiro de 2025
```

**O que mostra:**
- 📈 **Estatísticas Gerais**
  - Total de alterações
  - Alterações de status
  - Alterações de regime tributário

- 🏢 **Empresas Alteradas** (até 10 no embed)
  - Código e nome da empresa
  - Quantidade de alterações por empresa

- 📊 Se houver mais de 20 alterações, gera arquivo detalhado

**Exemplo de Relatório:**
```
📊 Relatório Mensal - NOVEMBRO/2024

📈 Estatísticas Gerais
Total de Alterações: 25
Alterações de Status: 18
Alterações de Regime: 7

🏢 Empresas Alteradas (15)
12345 - EMPRESA ABC LTDA (2 alterações)
67890 - EMPRESA XYZ S.A. (1 alteração)
...
```

**Notifica:** @everyone

---

### `/historico`
Mostra visão geral de todas as competências (meses) com alterações registradas.

**Uso:**
```
/historico
```

**O que mostra:**
- Lista dos últimos 12 meses com alterações
- Total de alterações por mês
- Breakdown por tipo (status e regime)
- Ordenado do mais recente para o mais antigo

**Exemplo:**
```
📚 Histórico de Alterações

📅 November/2024
   25 alterações
   └ 18 status
   └ 7 regimes

📅 October/2024
   15 alterações
   └ 12 status
   └ 3 regimes

📅 September/2024
   8 alterações
   └ 5 status
   └ 3 regimes
```

**Não notifica** @everyone (apenas resposta ao usuário)

---

## 🔄 Notificações Automáticas

O bot envia notificações automaticamente nos seguintes casos:

### ⚠️ Status Problemático
Quando empresa muda para status monitorado:
- INATIVO (🟠 Laranja)
- BAIXA (🔴 Vermelho)
- DEVOLVIDA (🟣 Roxo)
- SUSPENSA (🔴 Rosa)

**Notifica:** @everyone

### ✅ Reativação
Quando empresa volta a ficar ATIVA após estar em status problemático.

**Exemplo:**
```
✅ Empresa Reativada
12345 - EMPRESA ABC LTDA

Status Anterior: INATIVA
Novo Status: ATIVA ✅

ℹ️ Empresa voltou ao status ativo após estar inativa.
```

**Notifica:** @everyone

### 📋 Mudança de Regime Tributário
Quando há alteração no regime tributário:
- SN → LP
- LP → SN
- MEI → SN
- etc.

**Exemplo:**
```
📋 Alteração de Regime Tributário
12345 - EMPRESA ABC LTDA

Regime Anterior: Simples Nacional (SN)
Novo Regime: Lucro Presumido (LP)

⚠️ Ação Necessária
Revisar documentação e conformidade legal.
```

**Notifica:** @everyone

### 📊 Relatório Mensal Automático
Todo dia **5 de cada mês** (configurável no `.env`), o bot envia automaticamente o relatório do **mês anterior**.

**Exemplo:** No dia 5 de dezembro, envia relatório de novembro.

**Notifica:** @everyone

---

## 📊 Diferença entre `/relatorio` e `/historico`

| Característica | `/relatorio` | `/historico` |
|----------------|--------------|--------------|
| **Objetivo** | Relatório **detalhado** de um mês específico | **Visão geral** de todos os meses |
| **Escopo** | 1 mês por vez | Últimos 12 meses |
| **Detalhes** | Lista empresas com alterações | Apenas estatísticas |
| **Informações** | Nome das empresas, quantidade de alterações por empresa | Total de alterações por tipo |
| **Notificação** | @everyone | Não notifica |
| **Uso típico** | Ver detalhes de um período específico | Ver panorama geral |
| **Quando usar** | "Quais empresas mudaram em novembro?" | "Quais meses tiveram mais alterações?" |

### Exemplo Prático

**Você quer saber:** *"Houve muitas mudanças nos últimos meses?"*
→ Use `/historico`

**Você quer saber:** *"Quais empresas mudaram em outubro?"*
→ Use `/relatorio 10 2024`

**Você quer ver o mês atual:**
→ Use `/relatorio` (sem parâmetros)

---

## ❓ Perguntas Frequentes

### Por que `/relatorio` sem parâmetros mostra o mês atual e não o anterior?

O relatório **automático** (enviado no dia 5) usa o mês **anterior** porque é um resumo mensal fechado.

Já o comando **manual** `/relatorio` sem parâmetros usa o mês **atual** para você acompanhar as alterações em andamento.

**Lógica:**
- **Automático** (dia 5): Mês anterior = período fechado
- **Manual** (qualquer hora): Mês atual = acompanhamento em tempo real

### Como ver o relatório do mês anterior?

```
/relatorio 10 2024    → Outubro de 2024
/relatorio 11 2024    → Novembro de 2024
```

Ou espere até o dia 5 do próximo mês para o relatório automático.

### `/historico` não mostra as empresas?

Correto! O `/historico` é apenas uma **visão geral rápida** das competências com alterações.

Para ver **quais empresas** mudaram, use `/relatorio` com o mês desejado.

### Posso mudar o dia do relatório automático?

Sim! Edite o arquivo `config/.env`:

```env
# Dia do mês para enviar relatório mensal (1-28)
DIA_RELATORIO_MENSAL=5
```

Altere o número para o dia desejado (entre 1 e 28).

### O bot guarda o histórico para sempre?

Sim! Todos os dados ficam salvos em `data/historico_alteracoes.json`.

Para limpar histórico antigo, edite manualmente esse arquivo (remova as competências indesejadas).

---

## 🔧 Para Administradores

### Configurações Importantes

**Arquivo:** `config/.env`

```env
# Canal para notificações de alterações e relatórios
DISCORD_CHANNEL_ID=1435711368438218964

# Canal para boas-vindas e novas empresas
DISCORD_CHANNEL_GENERAL=1422666872947474464

# Dia do relatório automático
DIA_RELATORIO_MENSAL=5
```

### Logs

Todos os comandos são registrados em: `logs/bot_logs.log`

**Exemplo:**
```
2025-11-19 15:30:45 - INFO - Comando /help executado por Usuario#1234
2025-11-19 15:31:20 - INFO - Comando /relatorio executado por Usuario#1234 - Competência: 2024-11
```

### Permissões Necessárias

O bot precisa de:
- ✅ Enviar mensagens
- ✅ Usar comandos de barra
- ✅ Mencionar @everyone
- ✅ Incorporar links (embeds)
- ✅ Adicionar reações

---

**Última atualização:** 19/11/2025
