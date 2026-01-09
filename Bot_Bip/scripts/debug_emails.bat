@echo off
cd /d "%~dp0.."
title Debug Emails - ECAC

echo ================================================
echo     Debug - Leitura de Emails ECAC
echo ================================================
echo.
echo Este script le os emails da pasta ECAC e salva
echo os arquivos HTML em debug_output/ para analise.
echo.

python debug_email.py

echo.
echo Arquivos salvos em: debug_output\
echo Abra os arquivos .html no navegador para analise.
echo.

pause
