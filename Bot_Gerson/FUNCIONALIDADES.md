# 🤖 Funcionalidades Completas do Bot

## Visão Geral

O Bot_Gerson é um bot completo de monitoramento e notificações para gestão contábil, com as seguintes capacidades:

---

## 🎯 Funcionalidades Principais

### 1. 👋 Boas-vindas Automáticas

Quando um **novo membro entra no servidor**, o bot automaticamente:

**O que faz:**
- Detecta a entrada do novo membro
- Envia mensagem de boas-vindas personalizada
- Menciona o novo membro
- Envia no canal configurado em `DISCORD_CHANNEL_GENERAL`

**Mensagem enviada:**
```
Seja bem-vindo(a)!

Seja bem-vindo(a), @NovoMembro! 🎉

Sinta-se em casa — confira os canais e as regras.

CANELLA & SANTOS CONTABILIDADE EIRELI
```

**Cor:** Verde (#4CAF50)

**Local:** [Bot_Gerson/main.py:81-98](main.py:81-98)

**Configuração:** Usa o canal definido em `.env` como `DISCORD_CHANNEL_GENERAL`

---

### 2. 📊 Monitoramento de Planilha Google Sheets

O bot **monitora continuamente** a planilha do Google Sheets.

**O que monitora:**
- ✅ Status das empresas (Coluna C)
- ✅ Regime tributário (Coluna D)
- ✅ Novas empresas adicionadas
- ✅ Mudanças em empresas existentes

**Frequência:** Verifica a cada **30 segundos**

**Colunas monitoradas:**
- **Coluna A:** Código da empresa
- **Coluna B:** Nome da empresa
- **Coluna C:** Status (ATIVA, INATIVA, BAIXA, DEVOLVIDA, SUSPENSA)
- **Coluna D:** Regime Tributário (SN, LP, MEI, IGREJA, ISENTO)

**Local:** [Bot_Gerson/main.py:99-207](main.py:99-207)

---

### 3. ⚠️ Notificações de Status Problemático

Quando uma empresa muda para **status monitorado**, o bot notifica imediatamente.

**Status monitorados:**
- 🟠 **INATIVO** (Laranja - #FF9800)
- 🔴 **BAIXA** (Vermelho - #F44336)
- 🟣 **DEVOLVIDA** (Roxo - #9C27B0)
- 🌸 **SUSPENSA** (Rosa - #E91E63)

**Mensagem enviada:**
```
@everyone

⚠️ Alteração de Status - Empresa
12345 - EMPRESA ABC LTDA

Novo Status: INATIVA

Data/Hora: 19/11/2025 15:30:00

CANELLA & SANTOS CONTABILIDADE EIRELI
```

**Notifica:** @everyone

**Local:** [Bot_Gerson/main.py:175-177](main.py:175-177) + [Bot_Gerson/main.py:438-462](main.py:438-462)

---

### 4. ✅ Notificações de Reativação

Quando uma empresa **volta a ficar ATIVA** após estar em status problemático.

**Condições:**
- Status anterior: INATIVO, BAIXA, DEVOLVIDA ou SUSPENSA
- Status novo: ATIVA

**Mensagem enviada:**
```
@everyone

✅ Empresa Reativada
12345 - EMPRESA ABC LTDA

Status Anterior: INATIVA
Novo Status: ATIVA ✅

Data/Hora: 19/11/2025 16:45:00

ℹ️ Informação
Empresa voltou ao status ativo após estar inativa.

CANELLA & SANTOS CONTABILIDADE EIRELI
```

**Cor:** Verde (#4CAF50)

**Notifica:** @everyone

**Local:** [Bot_Gerson/main.py:179-180](main.py:179-180) + [Bot_Gerson/main.py:482-522](main.py:482-522)

---

### 5. 📋 Notificações de Mudança de Regime Tributário

Quando há alteração no **regime tributário** de uma empresa.

**Regimes reconhecidos:**
- **SN:** Simples Nacional (Verde - #4CAF50)
- **LP:** Lucro Presumido (Azul - #2196F3)
- **IGREJA:** Organização Religiosa (Roxo - #9C27B0)
- **MEI:** Microempreendedor Individual (Laranja - #FF9800)
- **ISENTO:** Regime Isento (Amarelo - #FFC107)

**Mensagem enviada:**
```
@everyone

📋 Alteração de Regime Tributário
12345 - EMPRESA ABC LTDA

Regime Anterior: Simples Nacional (SN)
Novo Regime: Lucro Presumido (LP)

Data/Hora: 19/11/2025 15:30:00

⚠️ Ação Necessária
Revisar documentação e conformidade legal.

CANELLA & SANTOS CONTABILIDADE EIRELI
```

**Notifica:** @everyone

**Local:** [Bot_Gerson/main.py:189-198](main.py:189-198) + [Bot_Gerson/main.py:524-565](main.py:524-565)

---

### 6. ✨ Notificações de Nova Empresa

Quando uma **nova empresa é detectada** na planilha.

**Mensagem enviada:**
```
✨ Nova Empresa Cadastrada
12345 - EMPRESA ABC LTDA

Status Inicial: ATIVA
Regime Tributário: SN

Data/Hora: 19/11/2025 15:30:00

CANELLA & SANTOS CONTABILIDADE EIRELI
```

**Cor:** Verde (#4CAF50)

**Notifica:** Não usa @everyone (só envia no canal)

**Local:** [Bot_Gerson/main.py:463-480](main.py:463-480)

---

### 7. 📚 Registro de Histórico

**Todas** as alterações são registradas automaticamente no histórico mensal.

**O que registra:**
- Tipo de alteração (status ou regime)
- Código e nome da empresa
- Valor anterior e novo
- Data e hora exata
- Competência (mês/ano)

**Arquivo:** `data/historico_alteracoes.json`

**Estrutura:**
```json
{
  "2025-11": {
    "alteracoes": [
      {
        "tipo": "status",
        "codigo": "12345",
        "nome": "EMPRESA ABC LTDA",
        "valor_anterior": "ATIVA",
        "valor_novo": "INATIVA",
        "data_hora": "19/11/2025 15:30:00"
      }
    ],
    "estatisticas": {
      "total_alteracoes": 15,
      "alteracoes_status": 12,
      "alteracoes_regime": 3
    }
  }
}
```

**Local:** [Bot_Gerson/main.py:286-321](main.py:286-321)

---

### 8. 📊 Relatório Mensal Automático

Todo **dia 5 de cada mês**, o bot envia automaticamente o relatório do mês anterior.

**Quando:** Dia configurado em `.env` (padrão: dia 5)

**Conteúdo:**
- Estatísticas gerais do mês
- Total de alterações
- Alterações por tipo
- Lista de empresas alteradas

**Horário:** Verifica a cada 1 hora se é o dia de enviar

**Notifica:** @everyone

**Local:** [Bot_Gerson/main.py:323-359](main.py:323-359) + [Bot_Gerson/main.py:361-436](main.py:361-436)

---

### 9. 💾 Sistema de Backup Automático

Todas as alterações de estado são **backupeadas automaticamente**.

**O que é backupeado:**
- Estado atual das empresas
- Timestamp de cada backup

**Onde:** `backups/estado_empresas_backup_YYYYMMDD_HHMMSS.json`

**Frequência:** Cada vez que o estado é salvo (a cada verificação com mudanças)

**Local:** [Bot_Gerson/main.py:247-253](main.py:247-253)

---

### 10. 📝 Sistema de Logs

Todas as ações são registradas em logs detalhados.

**O que é logado:**
- Inicialização do bot
- Cada alteração detectada
- Comandos executados pelos usuários
- Erros e avisos
- Notificações enviadas

**Arquivo:** `logs/bot_logs.log`

**Formato:**
```
2025-11-19 15:30:00 - INFO - ✅ O Bot BotGerson#1234 está online!
2025-11-19 15:30:45 - INFO - 🔄 Alteração detectada na linha 15: 12345 - EMPRESA ABC (ATIVA → INATIVA)
2025-11-19 15:31:20 - INFO - Comando /relatorio executado por Usuario#5678 - Competência: 2025-11
```

**Local:** [Bot_Gerson/main.py:29-38](main.py:29-38)

---

## 🎮 Comandos Slash (Interativos)

### `/help`
Mostra todos os comandos disponíveis e notificações automáticas.

**Parâmetros:** Nenhum

**Local:** [Bot_Gerson/main.py:572-620](main.py:572-620)

---

### `/ping`
Testa a latência do bot.

**Parâmetros:** Nenhum

**Retorna:** Latência em milissegundos

**Local:** [Bot_Gerson/main.py:622-629](main.py:622-629)

---

### `/status`
Mostra status do bot e informações de monitoramento.

**Parâmetros:** Nenhum

**Retorna:**
- Quantidade de empresas monitoradas
- Data/hora da última verificação
- Status online/offline

**Local:** [Bot_Gerson/main.py:631-655](main.py:631-655)

---

### `/relatorio [mes] [ano]`
Gera relatório mensal detalhado.

**Parâmetros:**
- `mes` (opcional): Mês de 1-12
- `ano` (opcional): Ano (ex: 2024)

**Comportamento:**
- Sem parâmetros: Mês atual
- Com parâmetros: Mês/ano especificado

**Notifica:** @everyone

**Agora os parâmetros aparecem automaticamente no Discord!** ✅

**Local:** [Bot_Gerson/main.py:657-700](main.py:657-700)

---

### `/historico`
Mostra visão geral de todas as competências com alterações.

**Parâmetros:** Nenhum

**Retorna:** Lista dos últimos 12 meses com estatísticas

**Não notifica** @everyone (apenas resposta ao usuário)

**Local:** [Bot_Gerson/main.py:702-744](main.py:702-744)

---

## ⚙️ Configurações

### Arquivo `.env`

```env
# Token do bot Discord
DISCORD_TOKEN=...

# Canal para notificações de alterações e relatórios
DISCORD_CHANNEL_ID=...

# Canal para boas-vindas e novas empresas
DISCORD_CHANNEL_GENERAL=...

# ID da planilha Google Sheets
GOOGLE_SHEET_ID=...

# Arquivo de credenciais Google
GOOGLE_CREDENTIALS_FILE=credentials.json

# Dia do mês para enviar relatório automático (1-28)
DIA_RELATORIO_MENSAL=5
```

---

## 📂 Estrutura de Arquivos

```
Bot_Gerson/
├── config/
│   ├── .env                      # Configurações (tokens, IDs)
│   ├── .env.example              # Template
│   └── credentials.json          # Credenciais Google
│
├── data/
│   ├── estado_empresas.json      # Estado atual das empresas
│   └── historico_alteracoes.json # Histórico mensal de alterações
│
├── logs/
│   └── bot_logs.log              # Logs detalhados
│
├── backups/
│   └── estado_empresas_backup_*.json  # Backups automáticos
│
├── main.py                       # Código principal
├── COMANDOS.md                   # Documentação de comandos
├── RELATORIOS.md                 # Documentação de relatórios
└── FUNCIONALIDADES.md            # Este arquivo
```

---

## 🔄 Fluxo de Funcionamento

```
┌─────────────────────────────────────────────┐
│ Bot inicia                                  │
│ ↓                                           │
│ Carrega configurações (.env)                │
│ ↓                                           │
│ Conecta ao Discord                          │
│ ↓                                           │
│ Autentica no Google Sheets                  │
│ ↓                                           │
│ Carrega estado anterior                     │
│ ↓                                           │
│ Carrega histórico de alterações             │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ Loop principal (a cada 30 segundos):        │
│                                             │
│ 1. Consulta planilha Google Sheets          │
│ 2. Compara com estado anterior              │
│ 3. Detecta alterações                       │
│ 4. Registra no histórico                    │
│ 5. Envia notificações                       │
│ 6. Salva novo estado                        │
│ 7. Cria backup                              │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ Verificação de relatório (a cada 1 hora):  │
│                                             │
│ 1. Verifica se é o dia configurado          │
│ 2. Verifica se já enviou hoje               │
│ 3. Gera relatório do mês anterior           │
│ 4. Envia no canal                           │
│ 5. Marca como enviado                       │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│ Eventos Discord:                            │
│                                             │
│ • Novo membro entra → Envia boas-vindas     │
│ • Comando /help → Mostra comandos           │
│ • Comando /status → Mostra status           │
│ • Comando /relatorio → Gera relatório       │
│ • Comando /historico → Mostra histórico     │
│ • Comando /ping → Mostra latência           │
└─────────────────────────────────────────────┘
```

---

## 🎨 Cores Usadas

- 🟢 **Verde (#4CAF50)**: Boas-vindas, reativação, nova empresa
- 🔵 **Azul (#2196F3)**: Relatórios, informações gerais
- 🟠 **Laranja (#FF9800)**: Status INATIVO, MEI
- 🔴 **Vermelho (#F44336)**: Status BAIXA
- 🟣 **Roxo (#9C27B0)**: Status DEVOLVIDA, IGREJA
- 🌸 **Rosa (#E91E63)**: Status SUSPENSA
- 🟡 **Amarelo (#FFC107)**: ISENTO

---

## 📊 Estatísticas e Métricas

O bot acompanha:
- ✅ Total de empresas monitoradas
- ✅ Última verificação da planilha
- ✅ Total de alterações por mês
- ✅ Alterações de status por mês
- ✅ Alterações de regime por mês
- ✅ Empresas com mais alterações
- ✅ Histórico completo desde o início

---

## 🔒 Segurança

- ✅ Credenciais em arquivo `.env` (gitignored)
- ✅ Tokens não expostos no código
- ✅ Credenciais Google em arquivo separado
- ✅ Logs não expõem informações sensíveis
- ✅ Backups automáticos para recuperação

---

## 🚀 Desempenho

- ⚡ Verificação a cada 30 segundos (configurável)
- ⚡ Notificações instantâneas
- ⚡ Comandos respondem em <1 segundo
- ⚡ Histórico persistente (não perde dados)
- ⚡ Backups automáticos

---

**Última atualização:** 19/11/2025
