@echo off
rem ---------------------------------------------------------------
rem  Abre o Sistema Temis a partir do codigo-fonte.
rem
rem  Serve para a maquina onde o Smart App Control bloqueia o
rem  executavel instalado: aqui quem roda e o python.exe, que e
rem  assinado e reconhecido, entao o bloqueio nao se aplica.
rem
rem  Basta dar dois cliques neste arquivo.
rem ---------------------------------------------------------------
title Sistema Temis
cd /d "%~dp0"

rem Caminho direto do interpretador. O comando "python" solto costuma
rem cair no atalho da Microsoft Store, que nao executa nada.
set "PY=%LOCALAPPDATA%\Python\bin\python.exe"
if not exist "%PY%" set "PY=py"

echo Abrindo o Sistema Temis...
echo (esta janela pode ser minimizada, mas nao fechada)
echo.

"%PY%" run_temis.py
set ERRO=%ERRORLEVEL%

if not "%ERRO%"=="0" (
  echo.
  echo ================================================================
  echo  O programa terminou com erro ^(codigo %ERRO%^).
  echo  A mensagem acima diz o motivo.
  echo ================================================================
  echo.
  pause
)
