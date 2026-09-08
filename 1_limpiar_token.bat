@echo off
title Sacar la contrasena de los repositorios
set BASE=%APPDATA%\nvda\addons
set INFORME=%BASE%\monitorSistema\resultado_github.txt
echo.
echo ===========================================================
echo   SACAR LA CONTRASENA DE LOS TRES REPOSITORIOS
echo ===========================================================
echo.
echo Esto quita el token que esta escrito en claro dentro de la
echo configuracion de cada repositorio. No borra nada de tu codigo.
echo.
(
echo ===== como guarda Windows las credenciales =====
cd /d "%BASE%\monitorSistema"
git config --get credential.helper
echo.
echo ===== direcciones ANTES =====
cd /d "%BASE%\monitorSistema"
git remote get-url origin
cd /d "%BASE%\climaAccesible"
git remote get-url origin
cd /d "%BASE%\biosManager"
git remote get-url origin
) > "%INFORME%" 2>&1

cd /d "%BASE%\monitorSistema"
git remote set-url origin https://github.com/daliana907/monitorSistema.git
cd /d "%BASE%\climaAccesible"
git remote set-url origin https://github.com/daliana907/climaAccesible.git
cd /d "%BASE%\biosManager"
git remote set-url origin https://github.com/daliana907/biosManager.git

(
echo.
echo ===== direcciones DESPUES =====
cd /d "%BASE%\monitorSistema"
git remote get-url origin
cd /d "%BASE%\climaAccesible"
git remote get-url origin
cd /d "%BASE%\biosManager"
git remote get-url origin
) >> "%INFORME%" 2>&1

echo Hecho. Las tres direcciones estan limpias.
echo El detalle quedo anotado en resultado_github.txt, dentro de
echo la carpeta de Monitor del Sistema.
echo.
echo Ahora ejecuta subir_todo.bat para subirlo. Te pedira usuario
echo y contrasena: el usuario es daliana907 y la contrasena es el
echo token NUEVO que acabas de crear.
echo.
pause
