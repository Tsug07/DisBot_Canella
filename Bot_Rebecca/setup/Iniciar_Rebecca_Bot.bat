@echo off
:: Navega para o diretório do bot (pasta pai do setup)
cd /d "%~dp0.."

:: Inicia o gerenciador do bot sem abrir janela
start "" pythonw.exe bot_manager.py
