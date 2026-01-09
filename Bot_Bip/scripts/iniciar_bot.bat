@echo off
cd /d "%~dp0.."
title Bip Bot - ECAC

echo ================================================
echo     Bip Bot - Monitoramento ECAC
echo ================================================
echo.
echo Iniciando bot...
echo Pressione Ctrl+C para encerrar.
echo.

python bip_bot.py

if errorlevel 1 (
    echo.
    echo ERRO: O bot encerrou com erro!
    echo Verifique as configuracoes no arquivo .env
    pause
)
