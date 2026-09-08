@echo off
title Sacar los archivos de trabajo del repositorio
set BASE=%APPDATA%\nvda\addons
set INFORME=%TEMP%\nvda_git_informe.txt
echo.
echo ===========================================================
echo   SACAR LOS ARCHIVOS DE TRABAJO DEL REPOSITORIO
echo ===========================================================
echo.
pause
(
echo ===== que contiene el archivo que se subio =====
cd /d "%BASE%\monitorSistema"
git show HEAD:resultado_github.txt
echo.
echo ===== quitando los archivos de trabajo del repositorio =====
git rm --cached --ignore-unmatch -q resultado_github.txt
git rm --cached --ignore-unmatch -q 1_limpiar_token.bat
git rm --cached --ignore-unmatch -q 2_subir_todo.bat
git rm --cached --ignore-unmatch -q 3_terminar.bat
git rm --cached --ignore-unmatch -q reintentar_subida.bat
git rm --cached --ignore-unmatch -q limpiar_repo.bat
git commit -m "Sacar del repositorio los archivos de trabajo de un solo uso"
git push
echo.
echo ===== como quedo =====
git status --short --branch
git ls-files ^| findstr /i "resultado_github 1_limpiar 2_subir 3_terminar reintentar limpiar_repo"
echo (si la linea de arriba no muestra nada, ya no queda ninguno^)
) > "%INFORME%" 2>&1
echo Terminado. El informe quedo en:
echo %INFORME%
echo.
pause
