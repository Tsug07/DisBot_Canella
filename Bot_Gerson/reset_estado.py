#!/usr/bin/env python3
"""
Script para resetar o estado do Bot_Gerson mantendo o histórico de alterações.

Uso:
    python reset_estado.py

O que este script faz:
1. Deleta o arquivo de flag de primeiro carregamento (primeiro_carregamento.flag)
2. Deleta o arquivo de estado das empresas (estado_empresas.json)
3. MANTÉM o histórico de alterações (historico_alteracoes.json)

Após executar este script, o bot irá:
- Fazer uma nova carga completa da planilha SEM enviar notificações
- Recriar o estado das empresas do zero
- Preservar todo o histórico de relatórios anteriores
"""

import os
from pathlib import Path
from datetime import datetime

# Define o diretório de dados
BOT_DIR = Path(__file__).parent.resolve()
DATA_DIR = BOT_DIR / "data"

def reset_estado():
    print("=" * 60)
    print("RESET DE ESTADO DO BOT_GERSON")
    print("=" * 60)
    print()

    # Arquivos a serem deletados
    flag_path = DATA_DIR / "primeiro_carregamento.flag"
    estado_path = DATA_DIR / "estado_empresas.json"
    historico_path = DATA_DIR / "historico_alteracoes.json"

    # Verifica se o histórico existe (para informar o usuário)
    if historico_path.exists():
        print(f"✓ Histórico de alterações encontrado: {historico_path}")
        print("  Este arquivo será MANTIDO.")
    else:
        print(f"⚠ Histórico de alterações não encontrado: {historico_path}")

    print()

    # Deleta flag de primeiro carregamento
    if flag_path.exists():
        flag_path.unlink()
        print(f"✓ Flag de primeiro carregamento deletada: {flag_path}")
    else:
        print(f"⚠ Flag não encontrada (já estava resetada): {flag_path}")

    # Faz backup do estado antes de deletar
    if estado_path.exists():
        backup_path = DATA_DIR / f"estado_empresas_backup_reset_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        estado_path.rename(backup_path)
        print(f"✓ Estado das empresas movido para backup: {backup_path}")
    else:
        print(f"⚠ Estado não encontrado (já estava resetado): {estado_path}")

    print()
    print("=" * 60)
    print("RESET CONCLUÍDO COM SUCESSO!")
    print("=" * 60)
    print()
    print("Próximos passos:")
    print("1. Inicie o bot normalmente: python main.py")
    print("2. O bot fará uma carga completa SEM enviar notificações")
    print("3. Após a primeira carga, notificações funcionarão normalmente")
    print()

if __name__ == "__main__":
    reset_estado()
