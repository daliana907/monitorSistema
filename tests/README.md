# Pruebas automáticas

Comprueban lo que se puede comprobar **sin abrir NVDA**: la forma del código, el
manejo de errores, la seguridad, la lógica que transforma datos y los archivos de
idiomas.

## Cómo ejecutarlas

Desde la carpeta del complemento (la que contiene `manifest.ini`):

    python -m unittest discover -s tests

Para ver el nombre de cada prueba mientras corre:

    python -m unittest discover -s tests -v

No hace falta instalar nada: usan solo lo que trae Python.

## Qué NO comprueban

No sustituyen a probar en NVDA. Estas pruebas corren fuera de NVDA, así que **no**
detectan problemas de permisos de Windows, del modelo de eventos, de wxPython ni
de la voz. Un cambio sigue necesitando reiniciar NVDA y probarlo.

## Por qué existe cada prueba

Ninguna es una precaución teórica: cada una detecta un fallo que **ya ocurrió**
en este proyecto.

- **Decoradores de atajos**: al colar una función entre el decorador y su script,
  el atajo de teclado desapareció sin más aviso que una línea en el registro.
- **Función de traducción**: un `for _ in range(8)` dejó sin efecto todas las
  alertas automáticas de otro complemento durante meses.
- **Capturas de error sin tipo**: `except:` a secas atrapa hasta un Control+C.
- **Rutas con nombre de usuario**: nueve rutas escritas a mano que en otro equipo
  no existen.
- **Escapado para PowerShell**: un valor con apóstrofo partía la orden en dos.
- **Orden de arranque**: el editor anterior permitía repetir un dispositivo y
  perder otro, y mandaba ese orden inválido a la BIOS.
- **Archivos de idiomas**: nueve de diez tenían la cabecera pegada a la primera
  entrada, y otro tenía un mensaje definido dos veces.

- **Tabla de procesadores**: la función más enredada del complemento. Las
  pruebas fijan su comportamiento actual para poder reorganizarla sin cambiarlo.
