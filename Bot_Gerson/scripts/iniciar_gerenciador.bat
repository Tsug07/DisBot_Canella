@echo off
cd /d "%~dp0.."
title Gerson Bot Manager
echo Iniciando Gerson Bot Manager...
python bot_manager.py
if errorlevel 1 (
    echo.
    echo ERRO: Falha ao iniciar o gerenciador!
    echo Verifique se todas as dependencias estao instaladas.
    echo Execute: scripts\instalar.bat
    pause
)
