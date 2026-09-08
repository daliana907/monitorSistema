@echo off
title Crear los paquetes instalables
set INFORME=%TEMP%\nvda_paquetes.txt
echo.
echo ===========================================================
echo   CREAR LOS PAQUETES INSTALABLES (.nvda-addon)
echo ===========================================================
echo.
echo Los tres paquetes quedaran en tu Escritorio.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0empaquetar.ps1" > "%INFORME%" 2>&1
type "%INFORME%"
echo.
echo El detalle quedo tambien en:
echo %INFORME%
echo.
pause
