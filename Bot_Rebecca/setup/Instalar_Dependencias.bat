@echo off
title Instalando Dependencias do Gerenciador
echo ========================================
echo  Instalando Dependencias do Gerenciador
echo ========================================
echo.

pip install customtkinter Pillow pystray

echo.
echo ========================================
echo  Instalacao Concluida!
echo ========================================
echo.
echo Agora voce pode executar:
echo - Iniciar_Gerenciador.bat
echo.
echo Ou gerar um executavel com:
echo - build_exe.bat
echo.
pause
