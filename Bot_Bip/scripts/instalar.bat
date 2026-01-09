@echo off
cd /d "%~dp0.."
echo ================================================
echo     Instalador - Bip Bot Manager
echo ================================================
echo.

echo [1/4] Verificando Python...
python --version
if errorlevel 1 (
    echo ERRO: Python nao encontrado!
    echo Por favor, instale o Python 3.8 ou superior.
    pause
    exit /b 1
)
echo.

echo [2/4] Instalando dependencias do bot...
pip install -r requirements.txt
if errorlevel 1 (
    echo ERRO: Falha ao instalar dependencias do bot!
    pause
    exit /b 1
)
echo.

echo [3/4] Instalando dependencias do gerenciador...
pip install -r requirements_manager.txt
if errorlevel 1 (
    echo ERRO: Falha ao instalar dependencias do gerenciador!
    pause
    exit /b 1
)
echo.

echo [4/4] Verificando estrutura de diretorios...
if not exist "logs" mkdir logs
if not exist "debug_output" mkdir debug_output
echo.

echo ================================================
echo     Instalacao concluida com sucesso!
echo ================================================
echo.
echo Proximos passos:
echo 1. Configure o arquivo .env com suas credenciais
echo 2. Execute: scripts\iniciar_gerenciador.bat
echo.

pause
