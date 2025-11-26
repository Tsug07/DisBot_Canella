@echo off
cd /d "%~dp0.."

REM Tenta usar pythonw.exe (não abre console)
where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw bot_manager.py
) else (
    REM Se pythonw não existir, usa python normal
    python bot_manager.py
)
