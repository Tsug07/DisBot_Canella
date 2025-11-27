@echo off
cd /d "%~dp0.."
echo ================================================
echo     Instalador - Gerson Bot Manager
echo ================================================
echo.

echo [1/3] Verificando Python...
python --version
if errorlevel 1 (
    echo ERRO: Python nao encontrado!
    echo Por favor, instale o Python 3.8 ou superior.
    pause
    exit /b 1
)
echo.

echo [2/3] Instalando dependencias...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERRO: Falha ao instalar dependencias!
    pause
    exit /b 1
)
echo.

echo [3/3] Verificando estrutura de diretorios...
if not exist "config" mkdir config
if not exist "data" mkdir data
if not exist "logs" mkdir logs
if not exist "backups" mkdir backups
echo.

echo ================================================
echo     Instalacao concluida com sucesso!
echo ================================================
echo.
echo Proximos passos:
echo 1. Configure o arquivo config/.env com suas credenciais
echo 2. Coloque o arquivo credentials.json na pasta config/
echo 3. Execute: python bot_manager.py
echo.

pause
