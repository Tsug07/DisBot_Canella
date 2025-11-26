@echo off
chcp 65001 >nul
color 0C
title 🗑️ Desinstalar Inicialização - Rebecca Bot

echo.
echo ═══════════════════════════════════════════════════
echo    🗑️ DESINSTALAR INICIALIZAÇÃO - REBECCA BOT
echo ═══════════════════════════════════════════════════
echo.

set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

if exist "%STARTUP_DIR%\RebeccaBot.bat" (
    del "%STARTUP_DIR%\RebeccaBot.bat"
    echo ✅ Atalho removido da inicialização com sucesso!
    echo.
    echo ℹ️  O bot não iniciará mais automaticamente ao ligar o PC.
) else (
    echo ⚠️ Nenhum atalho encontrado na inicialização.
)

echo.
pause
