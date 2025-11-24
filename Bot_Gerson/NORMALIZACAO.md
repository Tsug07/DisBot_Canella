# Sistema de Normalização de Status e Regimes

## Visão Geral

O bot agora possui um sistema inteligente de **normalização** que reconhece variações e sinônimos de status e regimes tributários, garantindo que todas as variações sejam tratadas corretamente.

---

## 🔄 Como Funciona

Quando o bot lê a planilha, ele:

1. **Lê o valor bruto** da célula
2. **Normaliza** para um valor padrão
3. **Compara** com valores normalizados anteriores
4. **Detecta alterações** corretamente
5. **Registra no log** quando há normalização

---

## 📊 Status Reconhecidos

### Status Padrão

| Valor na Planilha | Normalizado Para | Monitora? |
|-------------------|------------------|-----------|
| ATIVA | ATIVA | ❌ |
| ATIVO | ATIVA | ❌ |
| INATIVA | INATIVA | ✅ |
| INATIVO | INATIVO | ✅ |
| BAIXA | BAIXA | ✅ |
| BAIXADA | BAIXA | ✅ |
| DEVOLVIDA | DEVOLVIDA | ✅ |
| SUSPENSA | SUSPENSA | ✅ |

### Variações de SUSPENSA ⭐ **NOVO**

| Valor na Planilha | Normalizado Para | Monitora? |
|-------------------|------------------|-----------|
| SUSPENSA RFB | SUSPENSA | ✅ |
| SUSPENSA-RFB | SUSPENSA | ✅ |
| SUSPENSA_RFB | SUSPENSA | ✅ |

**Resultado:** Todas as variações de "SUSPENSA" são reconhecidas e notificadas!

---

## 📋 Regimes Tributários Reconhecidos

### Simples Nacional

| Valor na Planilha | Normalizado Para |
|-------------------|------------------|
| SN | SN |
| SIMPLES NACIONAL | SN |
| SIMPLES | SN |

### Simples Nacional - Excedente ⭐ **NOVO**

| Valor na Planilha | Normalizado Para |
|-------------------|------------------|
| SN-EXCEDENTE | SN-EXCEDENTE |
| SN EXCEDENTE | SN-EXCEDENTE |

**Descrição:** "Simples Nacional - Excedente"
**Cor:** Verde claro (#8BC34A)

### Lucro Presumido / Real

| Valor na Planilha | Normalizado Para |
|-------------------|------------------|
| LP | LP |
| LUCRO PRESUMIDO | LP |
| LR | LP |
| LUCRO REAL | LP |

### Lucro Presumido - Núcleo ⭐ **NOVO**

| Valor na Planilha | Normalizado Para |
|-------------------|------------------|
| LR-NUCLEO | LP-NUCLEO |
| LR NUCLEO | LP-NUCLEO |
| LP-NUCLEO | LP-NUCLEO |
| LP NUCLEO | LP-NUCLEO |

**Descrição:** "Lucro Presumido - Núcleo"
**Cor:** Azul escuro (#1976D2)

### MEI

| Valor na Planilha | Normalizado Para |
|-------------------|------------------|
| MEI | MEI |
| MICROEMPREENDEDOR | MEI |

### Igreja

| Valor na Planilha | Normalizado Para |
|-------------------|------------------|
| IGREJA | IGREJA |
| RELIGIOSO | IGREJA |
| ORGANIZACAO RELIGIOSA | IGREJA |

### Isento

| Valor na Planilha | Normalizado Para |
|-------------------|------------------|
| ISENTO | ISENTO |
| ISENTA | ISENTO |

---

## 🎯 Exemplos Práticos

### Exemplo 1: Suspensa RFB

**Antes da normalização:**
```
Planilha: SUSPENSA RFB
Bot: ❌ Não reconhece como status monitorado
```

**Depois da normalização:**
```
Planilha: SUSPENSA RFB
Bot normaliza: SUSPENSA RFB → SUSPENSA
Bot: ✅ Reconhece e notifica!

[No Discord]
@everyone
⚠️ Alteração de Status - Empresa
12345 - EMPRESA ABC LTDA
Novo Status: SUSPENSA
```

### Exemplo 2: SN-Excedente

**Antes:**
```
Planilha: SN-EXCEDENTE
Bot: ❌ Não mapeia corretamente
```

**Depois:**
```
Planilha: SN-EXCEDENTE
Bot normaliza: SN-EXCEDENTE → SN-EXCEDENTE
Bot: ✅ Reconhece como regime válido!

[No Discord]
@everyone
📋 Alteração de Regime Tributário
12345 - EMPRESA ABC LTDA

Regime Anterior: Simples Nacional (SN)
Novo Regime: Simples Nacional - Excedente (SN-EXCEDENTE)
```

### Exemplo 3: LR-Núcleo

**Antes:**
```
Planilha: LR-NUCLEO
Bot: ❌ Trata como texto desconhecido
```

**Depois:**
```
Planilha: LR-NUCLEO
Bot normaliza: LR-NUCLEO → LP-NUCLEO
Bot: ✅ Reconhece e notifica com cor correta!

[No Discord]
@everyone
📋 Alteração de Regime Tributário
12345 - EMPRESA ABC LTDA

Novo Regime: Lucro Presumido - Núcleo (LP-NUCLEO)
Cor: Azul escuro
```

---

## 📝 Logs de Normalização

Quando o bot normaliza um valor, ele registra no log:

```log
2025-11-19 16:00:00 - INFO - Status normalizado: 'SUSPENSA RFB' → 'SUSPENSA' (12345)
2025-11-19 16:00:05 - INFO - Regime normalizado: 'SN-EXCEDENTE' → 'SN-EXCEDENTE' (12345)
2025-11-19 16:00:10 - INFO - Regime normalizado: 'LR-NUCLEO' → 'LP-NUCLEO' (67890)
```

**Arquivo:** `logs/bot_logs.log`

---

## 🔍 Verificação de Status Monitorado

A função `eh_status_monitorado()` agora verifica:

1. **Status diretamente monitorados:**
   - INATIVO
   - BAIXA
   - DEVOLVIDA
   - SUSPENSA

2. **Variações que contêm palavras-chave:**
   - SUSPENSA RFB → contém "SUSPENSA" → ✅ Monitora
   - BAIXA ESPECIAL → contém "BAIXA" → ✅ Monitora

**Código:**
```python
def eh_status_monitorado(status):
    """Verifica se o status é um dos monitorados (considerando variações)."""
    status_normalizado = normalizar_status(status)

    # Status diretamente monitorados
    if status_normalizado in STATUS_MONITORADOS:
        return True

    # Variações específicas também são monitoradas
    status_problematicos = ["INATIVO", "BAIXA", "DEVOLVIDA", "SUSPENSA"]
    for prob in status_problematicos:
        if prob in status_normalizado:
            return True

    return False
```

---

## 🛠️ Adicionar Novas Variações

Para adicionar uma nova variação, edite o arquivo [main.py](main.py):

### Para Status

```python
MAPEAMENTO_STATUS = {
    # ... existentes ...
    "NOVA_VARIACAO": "STATUS_PADRAO",
    "OUTRA-VARIACAO": "STATUS_PADRAO",
}
```

### Para Regimes

```python
MAPEAMENTO_REGIME = {
    # ... existentes ...
    "NOVA_SIGLA": "SIGLA_PADRAO",
    "VARIACAO": "SIGLA_PADRAO",
}
```

**Exemplo:** Adicionar "CANCELADA" como variação de "BAIXA":

```python
MAPEAMENTO_STATUS = {
    # ... existentes ...
    "CANCELADA": "BAIXA",
    "CANCELADO": "BAIXA",
}
```

---

## ✅ Vantagens do Sistema

1. **Flexibilidade:** Reconhece múltiplas formas de escrever o mesmo status/regime
2. **Consistência:** Todas as variações são tratadas da mesma forma
3. **Rastreabilidade:** Logs registram quando há normalização
4. **Manutenibilidade:** Fácil adicionar novas variações
5. **Robustez:** Não quebra se aparecer uma variação nova (usa o valor original)
6. **Histórico correto:** Comparações funcionam mesmo com variações

---

## 🔄 Fluxo de Normalização

```
┌─────────────────────────────────────────┐
│ 1. Lê célula da planilha                │
│    "SUSPENSA RFB"                       │
└─────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────┐
│ 2. Converte para maiúsculas e remove    │
│    espaços extras                       │
│    "SUSPENSA RFB"                       │
└─────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────┐
│ 3. Busca no mapeamento                  │
│    MAPEAMENTO_STATUS["SUSPENSA RFB"]    │
│    = "SUSPENSA"                         │
└─────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────┐
│ 4. Registra normalização no log         │
│    "Status normalizado: 'SUSPENSA RFB'  │
│     → 'SUSPENSA' (12345)"               │
└─────────────────────────────────────────┘
                ↓
┌─────────────────────────────────────────┐
│ 5. Usa valor normalizado para           │
│    comparações e notificações           │
│    "SUSPENSA"                           │
└─────────────────────────────────────────┘
```

---

## 📊 Tabela Completa de Normalizações

### Status

| Original | Normalizado | Monitora | Notifica |
|----------|-------------|----------|----------|
| ATIVA | ATIVA | ❌ | ❌ |
| ATIVO | ATIVA | ❌ | ❌ |
| INATIVA | INATIVA | ✅ | ⚠️ |
| INATIVO | INATIVO | ✅ | ⚠️ |
| BAIXA | BAIXA | ✅ | ⚠️ |
| BAIXADA | BAIXA | ✅ | ⚠️ |
| DEVOLVIDA | DEVOLVIDA | ✅ | ⚠️ |
| SUSPENSA | SUSPENSA | ✅ | ⚠️ |
| SUSPENSA RFB | SUSPENSA | ✅ | ⚠️ |
| SUSPENSA-RFB | SUSPENSA | ✅ | ⚠️ |
| SUSPENSA_RFB | SUSPENSA | ✅ | ⚠️ |

### Regimes

| Original | Normalizado | Descrição | Cor |
|----------|-------------|-----------|-----|
| SN | SN | Simples Nacional | 🟢 Verde |
| SIMPLES NACIONAL | SN | Simples Nacional | 🟢 Verde |
| SIMPLES | SN | Simples Nacional | 🟢 Verde |
| SN-EXCEDENTE | SN-EXCEDENTE | Simples Nacional - Excedente | 🟢 Verde claro |
| SN EXCEDENTE | SN-EXCEDENTE | Simples Nacional - Excedente | 🟢 Verde claro |
| LP | LP | Lucro Presumido | 🔵 Azul |
| LUCRO PRESUMIDO | LP | Lucro Presumido | 🔵 Azul |
| LR | LP | Lucro Presumido | 🔵 Azul |
| LUCRO REAL | LP | Lucro Presumido | 🔵 Azul |
| LR-NUCLEO | LP-NUCLEO | Lucro Presumido - Núcleo | 🔵 Azul escuro |
| LR NUCLEO | LP-NUCLEO | Lucro Presumido - Núcleo | 🔵 Azul escuro |
| LP-NUCLEO | LP-NUCLEO | Lucro Presumido - Núcleo | 🔵 Azul escuro |
| LP NUCLEO | LP-NUCLEO | Lucro Presumido - Núcleo | 🔵 Azul escuro |
| MEI | MEI | Microempreendedor Individual | 🟠 Laranja |
| MICROEMPREENDEDOR | MEI | Microempreendedor Individual | 🟠 Laranja |
| IGREJA | IGREJA | Organização Religiosa | 🟣 Roxo |
| RELIGIOSO | IGREJA | Organização Religiosa | 🟣 Roxo |
| ORGANIZACAO RELIGIOSA | IGREJA | Organização Religiosa | 🟣 Roxo |
| ISENTO | ISENTO | Regime Isento | 🟡 Amarelo |
| ISENTA | ISENTO | Regime Isento | 🟡 Amarelo |

---

## 🎯 Casos de Uso Resolvidos

### ✅ Problema 1: "SUSPENSA RFB" não era notificada
**Solução:** Agora normaliza para "SUSPENSA" e notifica corretamente

### ✅ Problema 2: "SN-EXCEDENTE" não tinha descrição
**Solução:** Mapeamento específico com descrição "Simples Nacional - Excedente"

### ✅ Problema 3: "LR-NUCLEO" aparecia como texto genérico
**Solução:** Normaliza para "LP-NUCLEO" com cor azul escuro específica

### ✅ Problema 4: Comparações falhavam com variações
**Solução:** Todas as comparações usam valores normalizados

---

**Local do código:** [Bot_Gerson/main.py:51-136](main.py:51-136)

**Última atualização:** 19/11/2025
