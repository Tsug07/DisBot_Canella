@echo off
chcp 65001 >nul
color 0A
title 🤖 Instalação Automática - Rebecca Bot

echo.
echo ═══════════════════════════════════════════════════
echo    🤖 INSTALAÇÃO AUTOMÁTICA - REBECCA BOT
echo ═══════════════════════════════════════════════════
echo.

:: Detecta o diretório do bot (pasta pai do setup)
set "BOT_DIR=%~dp0.."
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

echo [1/4] 📁 Verificando dependências...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python não encontrado! Instale Python 3.8+ primeiro.
    pause
    exit /b 1
)

echo [2/4] 📦 Instalando dependências do gerenciador...
pip install customtkinter pillow pystray >nul 2>&1
if errorlevel 1 (
    echo ⚠️ Erro ao instalar dependências. Tentando com --user...
    pip install --user customtkinter pillow pystray
)

echo [3/4] 📦 Instalando dependências do bot...
if exist "%BOT_DIR%\requirements_manager.txt" (
    pip install -r "%BOT_DIR%\requirements_manager.txt" >nul 2>&1
)

echo [4/4] 🔗 Criando atalho na inicialização...

:: Cria arquivo BAT na pasta de inicialização
(
echo @echo off
echo cd /d "%BOT_DIR%"
echo start "" pythonw.exe bot_manager.py
) > "%STARTUP_DIR%\RebeccaBot.bat"

if exist "%STARTUP_DIR%\RebeccaBot.bat" (
    echo.
    echo ═══════════════════════════════════════════════════
    echo    ✅ INSTALAÇÃO CONCLUÍDA COM SUCESSO!
    echo ═══════════════════════════════════════════════════
    echo.
    echo 📍 Localização do atalho:
    echo    %STARTUP_DIR%\RebeccaBot.bat
    echo.
    echo ℹ️  O bot agora iniciará automaticamente quando você ligar o PC.
    echo.
    echo 🚀 Iniciando o gerenciador agora...
    timeout /t 3 /nobreak >nul
    cd /d "%BOT_DIR%"
    start "" pythonw.exe bot_manager.py
) else (
    echo.
    echo ❌ Erro ao criar atalho na inicialização!
    echo Tente executar como Administrador.
)

echo.
pause
