@echo off
cd /d "%~dp0.."
title Compilando Rebecca Bot Manager
echo ========================================
echo  Compilando Rebecca Bot Manager para EXE
echo ========================================
echo.

echo [1/3] Instalando dependencias...
pip install -r requirements_manager.txt
echo.

echo [2/3] Criando executavel (isso pode demorar alguns minutos)...
pyinstaller --onefile --windowed --name="RebeccaManager" --icon=NONE --add-data "bot_config.json;." bot_manager.py
echo.

echo [3/3] Limpando arquivos temporarios...
rmdir /s /q build
del RebeccaManager.spec
echo.

echo ========================================
echo  CONCLUIDO!
echo ========================================
echo.
echo O executavel esta em: dist\RebeccaManager.exe
echo.
echo Voce pode mover o arquivo RebeccaManager.exe
echo para a mesma pasta do rebecca_bot.py
echo.
pause
