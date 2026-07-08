@echo off
REM ============================================================
REM  Inicia um Chrome dedicado ao Onvio/Gestta com porta de
REM  depuracao. Deixe este Chrome SEMPRE ABERTO na VM.
REM  O bot le o token (JWT) do Messenger via porta 9222.
REM ============================================================

set CHROME="C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist %CHROME% set CHROME="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

start "" %CHROME% ^
  --remote-debugging-port=9222 ^
  --remote-allow-origins=* ^
  --user-data-dir="C:\chrome_gestta" ^
  https://onvio.com.br/login/#/

REM PASSOS (uma vez por sessao do Windows, pois o Onvio exige
REM login a cada nova sessao):
REM   1. Faca login no Onvio (Entrar -> credenciais).
REM   2. Em "Minhas Aplicacoes", clique em "Messenger"
REM      (abre app.gestta.com.br em nova aba).
REM   3. DEIXE este Chrome aberto. A renovacao do token
REM      (scripts\renovar_token_gestta.bat) usa essa sessao viva.
