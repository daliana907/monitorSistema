@echo off
title Activar la marca de pruebas en GitHub
cd /d "%~dp0"
echo.
echo ===========================================================
echo   ACTIVAR LA MARCA DE PRUEBAS EN GITHUB
echo ===========================================================
echo.
if not exist "pruebas.yml" (
  echo No encuentro el archivo pruebas.yml en esta carpeta.
  echo Puede que ya lo hayas activado antes.
  echo.
  pause
  exit /b
)
echo Colocando el archivo en su sitio...
if not exist ".github" mkdir ".github"
if not exist ".github\workflows" mkdir ".github\workflows"
move /Y "pruebas.yml" ".github\workflows\pruebas.yml" >nul
echo Hecho.
echo.
echo -----------------------------------------------------------
echo Guardando y subiendo a GitHub...
echo.
git add -A
git commit -m "Ejecutar las pruebas automaticamente en cada subida" -m "GitHub pasa por su cuenta las pruebas del complemento cada vez que se sube algo, y marca el resultado con un tic verde o una cruz roja visible en el repositorio." -m "Las pruebas no necesitan NVDA ni Windows: la carpeta tests trae un NVDA de mentira que imita lo que el complemento le pide."
git push
echo.
echo ===========================================================
if errorlevel 1 (
  echo   NO SE PUDO SUBIR A GITHUB.
  echo   El archivo SI quedo colocado y guardado en tu equipo.
  echo   Lo de arriba dice por que fallo la subida.
) else (
  echo   LISTO. Entra a tu repositorio en GitHub y en la pestana
  echo   Actions veras las pruebas ejecutandose. Tarda un minuto.
)
echo ===========================================================
echo.
pause
