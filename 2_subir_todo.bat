@echo off
title Subir los tres complementos a GitHub
set BASE=%APPDATA%\nvda\addons
set INFORME=%BASE%\monitorSistema\resultado_github.txt
echo.
echo ===========================================================
echo   SUBIR LOS TRES COMPLEMENTOS
echo ===========================================================
echo.
echo Si te pide usuario y contrasena: el usuario es daliana907
echo y la contrasena es tu token NUEVO (el que tiene marcado
echo el permiso workflow). Solo te lo pedira una vez.
echo.
pause
(
echo ===== monitorSistema =====
cd /d "%BASE%\monitorSistema"
git add -A
git commit -m "Marca de pruebas automaticas en GitHub"
git push
echo.
echo ===== climaAccesible =====
cd /d "%BASE%\climaAccesible"
git add -A
git commit -m "Marca de pruebas automaticas en GitHub"
git push
echo.
echo ===== biosManager =====
cd /d "%BASE%\biosManager"
git add -A
git commit -m "Marca de pruebas automaticas en GitHub"
git push
) > "%INFORME%" 2>&1
echo.
echo Terminado. El resultado de los tres quedo anotado en
echo resultado_github.txt, dentro de la carpeta de Monitor.
echo.
type "%INFORME%"
echo.
pause
