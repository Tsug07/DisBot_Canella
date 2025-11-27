@echo off
cd /d "%~dp0.."

REM Tenta usar pythonw.exe (não abre console)
where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw bot_manager.py
) else (
    REM Se pythonw não existir, usa python normal
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
)
