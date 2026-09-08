@echo off
title Reintentar la subida y guardar el resultado
cd /d "%~dp0"
echo.
echo Reintentando la subida y anotando todo lo que dice...
echo.
(
  echo ===== git status =====
  git status
  echo.
  echo ===== git log, los tres ultimos =====
  git log --oneline -3
  echo.
  echo ===== git push =====
  git push
  echo.
  echo ===== codigo de salida: %%errorlevel%% =====
) > resultado_github.txt 2>&1
echo Listo. Todo quedo anotado en el archivo resultado_github.txt
echo que esta en esta misma carpeta.
echo.
type resultado_github.txt
echo.
pause
