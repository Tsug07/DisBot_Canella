# Sistema de Relatórios Mensais

## Visão Geral

O Bot_Gerson agora possui um sistema completo de relatórios mensais que registra todas as alterações de status e regime tributário das empresas, organizadas por competência (mês/ano).

## Como Funciona

### 1. Registro Automático de Alterações

Toda vez que uma alteração é detectada, o bot:
- ✅ Registra a alteração no histórico mensal
- ✅ Salva a competência (ano-mês)
- ✅ Armazena detalhes: tipo, empresa, valores anterior/novo, data/hora
- ✅ Atualiza estatísticas do mês

**Tipos de alterações registradas:**
- **Status**: INATIVO, BAIXA, DEVOLVIDA, SUSPENSA, ATIVA (reativação), etc.
- **Regime Tributário**: SN, LP, MEI, IGREJA, ISENTO, etc.

**Notificações enviadas:**
- ⚠️ Quando empresa muda para status problemático (INATIVO, BAIXA, DEVOLVIDA, SUSPENSA)
- ✅ Quando empresa volta a ficar ATIVA (após estar em status problemático)
- 📋 Quando há mudança de regime tributário

### 2. Relatório Automático Mensal

O bot envia automaticamente um relatório:
- **Quando**: Dia 5 de cada mês (configurável no `.env`)
- **Conteúdo**: Alterações do mês anterior
- **Onde**: Canal configurado em `DISCORD_CHANNEL_ID`
- **Notifica**: @everyone

**Exemplo**: No dia 5 de dezembro, envia o relatório de novembro.

### 3. Armazenamento

Os dados são salvos em:
```
Bot_Gerson/
└── data/
    ├── estado_empresas.json        # Estado atual das empresas
    └── historico_alteracoes.json   # Histórico de alterações por mês
```

**Formato do histórico:**
```json
{
  "2025-01": {
    "alteracoes": [
      {
        "tipo": "status",
        "codigo": "12345",
        "nome": "EMPRESA XYZ LTDA",
        "valor_anterior": "ATIVA",
        "valor_novo": "INATIVA",
        "data_hora": "15/01/2025 14:30:45"
      }
    ],
    "estatisticas": {
      "total_alteracoes": 10,
      "alteracoes_status": 7,
      "alteracoes_regime": 3
    }
  }
}
```

## Configuração

### Arquivo `.env`

```env
# Dia do mês para enviar relatório mensal (1-28, padrão: 5)
DIA_RELATORIO_MENSAL=5
```

**Importante**: Use valores entre 1 e 28 para garantir que funcione em todos os meses (inclusive fevereiro).

## Comandos Disponíveis

### `/relatorio [mes] [ano]`

Gera relatório mensal de alterações.

**Exemplos:**
```
/relatorio                  → Relatório do mês anterior
/relatorio 11 2024         → Relatório de novembro/2024
/relatorio 1 2025          → Relatório de janeiro/2025
```

**O que mostra:**
- 📈 Estatísticas gerais (total de alterações)
- 📊 Alterações por tipo (status e regime)
- 🏢 Lista de empresas alteradas
- 📅 Competência do relatório

### `/historico`

Mostra todas as competências com alterações registradas.

**Exemplo de saída:**
```
📚 Histórico de Alterações

📅 Janeiro/2025
   10 alterações
   └ 7 status
   └ 3 regimes

📅 Dezembro/2024
   15 alterações
   └ 12 status
   └ 3 regimes
```

### `/status`

Mostra status geral do bot (já existia, sem alterações).

### `/ping`

Testa latência do bot (já existia, sem alterações).

## Conteúdo do Relatório

O relatório mensal inclui:

### 1. Cabeçalho
```
📊 Relatório Mensal - JANEIRO/2025
Resumo das alterações registradas no período
```

### 2. Estatísticas Gerais
```
📈 Estatísticas Gerais
Total de Alterações: 25
Alterações de Status: 18
Alterações de Regime: 7
```

### 3. Empresas Alteradas
```
🏢 Empresas Alteradas (15)
12345 - EMPRESA ABC LTDA (2 alterações)
67890 - EMPRESA XYZ S.A. (1 alteração)
...
```

### 4. Rodapé
```
CANELLA & SANTOS CONTABILIDADE EIRELI • Competência: 2025-01
```

## Fluxo de Funcionamento

```
┌─────────────────────────────────────────────────┐
│ 1. Bot detecta alteração na planilha            │
│    ↓                                             │
│ 2. Registra no histórico (competência atual)    │
│    ↓                                             │
│ 3. Salva em historico_alteracoes.json           │
│    ↓                                             │
│ 4. Envia notificação imediata (como antes)      │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│ No dia 5 de cada mês:                           │
│    ↓                                             │
│ 1. Bot verifica se é dia de relatório           │
│    ↓                                             │
│ 2. Gera relatório do mês anterior               │
│    ↓                                             │
│ 3. Envia no canal configurado                   │
│    ↓                                             │
│ 4. Marca como enviado (não repete)              │
└─────────────────────────────────────────────────┘
```

## Exemplo de Uso Prático

### Cenário 1: Empresa ficou Inativa
```
[15/01/2025 10:30]
🔄 Alteração detectada
   Empresa: 12345 - EMPRESA ABC LTDA
   Status: ATIVA → INATIVA

✅ Alteração registrada no histórico (Competência: 2025-01)
📨 Notificação enviada ao canal

[No Discord]
@everyone
⚠️ Alteração de Status - Empresa
12345 - EMPRESA ABC LTDA
Novo Status: INATIVA
```

### Cenário 1b: Empresa foi Reativada
```
[20/01/2025 15:45]
🔄 Alteração detectada
   Empresa: 12345 - EMPRESA ABC LTDA
   Status: INATIVA → ATIVA

✅ Alteração registrada no histórico (Competência: 2025-01)
📨 Notificação de reativação enviada ao canal

[No Discord]
@everyone
✅ Empresa Reativada
12345 - EMPRESA ABC LTDA
Status Anterior: INATIVA
Novo Status: ATIVA ✅
ℹ️ Empresa voltou ao status ativo após estar inativa.
```

### Cenário 2: Relatório Automático
```
[05/02/2025 00:01]
📊 Gerando relatório mensal...
📅 Competência: 2025-01 (Janeiro)

[No Discord]
@everyone
📊 Relatório Mensal - JANEIRO/2025
📈 Total: 25 alterações
🏢 15 empresas alteradas
```

### Cenário 3: Relatório Manual
```
Usuário: /relatorio 12 2024

Bot:
✅ Relatório da competência 2024-12 enviado com sucesso!

[No canal]
📊 Relatório Mensal - DEZEMBRO/2024
...
```

## Vantagens

✅ **Histórico completo**: Todas as alterações ficam registradas por mês
✅ **Rastreabilidade**: Data/hora exata de cada alteração
✅ **Estatísticas**: Visão geral por competência
✅ **Automático**: Relatório mensal sem intervenção
✅ **Manual**: Gere relatórios sob demanda quando necessário
✅ **Organizado**: Dados estruturados por mês/ano
✅ **Backup**: Histórico preservado em JSON

## Manutenção

### Limpeza de Histórico Antigo

Para remover competências antigas (opcional):

1. Acesse: `Bot_Gerson/data/historico_alteracoes.json`
2. Remova as competências desejadas
3. Salve o arquivo

**Exemplo**: Remover dados de 2023:
```json
{
  "2023-01": { ... },  ← Deletar
  "2023-02": { ... },  ← Deletar
  ...
  "2024-01": { ... },  ← Manter
  "2025-01": { ... }   ← Manter
}
```

### Backup Manual

Os arquivos são salvos em:
- `Bot_Gerson/data/historico_alteracoes.json`
- `Bot_Gerson/backups/` (backups automáticos do estado)

**Recomendação**: Faça backup mensal do arquivo `historico_alteracoes.json`.

## Troubleshooting

### Relatório não foi enviado automaticamente

**Possíveis causas:**
1. Bot estava offline no dia configurado
2. Nenhuma alteração foi registrada no mês anterior
3. Data configurada incorreta no `.env`

**Solução**: Use `/relatorio` manualmente

### Histórico vazio

**Causas:**
- Bot foi reiniciado e o histórico não existia
- Arquivo `historico_alteracoes.json` foi deletado

**Solução**: O histórico começará a acumular a partir da próxima alteração

### Erro ao gerar relatório

**Verificar:**
1. Arquivo `historico_alteracoes.json` não está corrompido
2. Canal do Discord está configurado corretamente
3. Bot tem permissões para enviar mensagens

## Atualizações Futuras

Melhorias planejadas:
- 📄 Exportar relatório em PDF/Excel
- 📧 Enviar relatório por e-mail
- 📊 Gráficos e visualizações
- 🔍 Filtros por tipo de alteração
- 📈 Comparação entre meses

---

**Dúvidas?** Consulte o código em [Bot_Gerson/main.py](main.py) ou os logs em [Bot_Gerson/logs/bot_logs.log](logs/bot_logs.log)
