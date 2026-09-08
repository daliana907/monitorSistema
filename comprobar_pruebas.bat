@echo off
title Comprobar las pruebas en GitHub
set INFORME=%TEMP%\nvda_pruebas_github.txt
echo.
echo Preguntando a GitHub como fueron las pruebas...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0comprobar_pruebas.ps1" > "%INFORME%" 2>&1
type "%INFORME%"
echo.
echo El informe quedo en:
echo %INFORME%
echo.
pause
