@echo off
cd /d "%~dp0.."
title Testando Rebecca Bot
echo ========================================
echo  Testando Rebecca Bot (Console Aberto)
echo ========================================
echo.
echo Este teste mostra os logs do bot diretamente
echo para diagnosticar problemas.
echo.
echo Pressione Ctrl+C para parar o bot.
echo.
echo ========================================
echo.

python rebecca_bot.py

pause
