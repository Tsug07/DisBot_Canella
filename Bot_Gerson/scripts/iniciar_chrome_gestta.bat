@echo off
REM ============================================================
REM  Inicia um Chrome dedicado ao Gestta com porta de depuracao.
REM  Deixe este Chrome sempre aberto e LOGADO no Gestta na VM.
REM  O bot le o token (JWT) desse Chrome via porta 9222.
REM ============================================================

set CHROME="C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist %CHROME% set CHROME="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

start "" %CHROME% ^
  --remote-debugging-port=9222 ^
  --user-data-dir="C:\chrome_gestta" ^
  https://app.gestta.com.br

REM Apos abrir, faca login no Gestta uma vez. A sessao fica salva em
REM C:\chrome_gestta e o token e renovado automaticamente enquanto logado.
