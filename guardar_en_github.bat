@echo off
title Guardar Monitor del Sistema en GitHub
cd /d "%~dp0"
echo.
echo ===========================================================
echo   GUARDAR MONITOR DEL SISTEMA EN GITHUB
echo ===========================================================
echo.
echo Archivos que han cambiado desde la ultima vez que guardaste:
echo.
git status --short
echo.
echo -----------------------------------------------------------
echo Guardando...
git add -A
git commit -m "Refactorizacion profunda de Monitor del Sistema" -m "- Velocidades maximas de procesador en una tabla, en vez de 117 condiciones encadenadas. Corrige que un Intel i5-13600K se confundiera con un Ryzen 5 3600 y se le atribuyera 4,2 GHz en vez de 5,0." -m "- Escaneo Bluetooth: de 382 lineas en un bloque a siete piezas con nombre." -m "- Bucle de alertas: de 239 lineas a cinco vigilancias independientes." -m "- Prueba de velocidad de red y salud de discos: medir e interpretar separados." -m "- Busqueda de conflictos, ventana de ajustes, temperatura y velocidad de CPU repartidas por secciones." -m "- Cuatro errores que se tragaban en silencio ahora dejan constancia en el registro." -m "- Mensaje duplicado eliminado en los 34 archivos de idioma." -m "- Red de pruebas automaticas: 28 comprobaciones de estructura, traducciones y logica."
echo.
echo -----------------------------------------------------------
echo Subiendo a GitHub...
git push
echo.
echo ===========================================================
if errorlevel 1 (
  echo   NO SE PUDO SUBIR A GITHUB.
  echo   El trabajo SI quedo guardado en tu equipo, no se ha perdido nada.
  echo   Lo de arriba dice por que fallo la subida.
) else (
  echo   LISTO. Guardado en tu equipo y subido a GitHub.
)
echo ===========================================================
echo.
pause
