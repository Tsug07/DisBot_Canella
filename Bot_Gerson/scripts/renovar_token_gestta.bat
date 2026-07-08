@echo off
REM ============================================================
REM  Renova o token do Gestta de forma TOTALMENTE AUTOMATICA.
REM  Sobe um Chrome HEADLESS com o perfil salvo, faz o SSO do
REM  Onvio sozinho (clica "Entrar" -> sessao salva no perfil),
REM  abre o Messenger, le o JWT e FECHA o Chrome.
REM  Nao precisa manter nenhum Chrome aberto.
REM
REM  Agende no DisC0ntrol / Agendador de Tarefas, ex.: a cada 6h.
REM
REM  PRE-REQUISITO (apenas quando a sessao SSO expirar):
REM    Rode scripts\iniciar_chrome_gestta.bat, faca login no
REM    Onvio uma vez e feche. A sessao fica salva no perfil
REM    C:\chrome_gestta e o modo headless reaproveita.
REM ============================================================

cd /d "%~dp0\.."
python atualizar_token_gestta.py --launch --forcar
exit /b %ERRORLEVEL%
