@echo off
setlocal
rem Ejecuta las pruebas automaticas del complemento.
rem Basta con pulsar Intro sobre este archivo: no hay que escribir ninguna ruta.

rem Situarse en la carpeta donde esta este archivo.
cd /d "%~dp0"

rem Buscar Python. Primero el lanzador "py", que es el que instala Python en Windows.
set PYTHON=
py -3 --version >nul 2>&1 && set PYTHON=py -3
if not defined PYTHON python --version >nul 2>&1 && set PYTHON=python

if not defined PYTHON (
    echo.
    echo No se ha encontrado Python en este equipo.
    echo.
    echo Las pruebas necesitan Python instalado. Se descarga gratis desde
    echo python.org, y durante la instalacion hay que marcar la casilla
    echo "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

echo Ejecutando las pruebas del complemento...
echo.
%PYTHON% -m unittest discover -s tests -v
set RESULTADO=%ERRORLEVEL%

echo.
if "%RESULTADO%"=="0" (
    echo TODAS LAS PRUEBAS PASARON.
) else (
    echo HAY PRUEBAS QUE FALLAN. El detalle esta mas arriba, en las lineas
    echo que empiezan por FAIL o por ERROR.
)
echo.
echo Pulsa una tecla para cerrar.
pause >nul
exit /b %RESULTADO%
