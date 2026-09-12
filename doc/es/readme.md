# Monitor del Sistema para NVDA (System Monitor)

Autora: Daliana (basado en Resource Monitor de Joseph Lee y colaboradores)
Versión: 2.7
Compatibilidad: NVDA 2019.3 en adelante
Licencia: GNU GPL v2

[Read in English below](#english-version)

---

## Versión en Español

Monitor del Sistema reúne en un solo lugar todas las herramientas para conocer el estado y rendimiento de tu equipo, batería, periféricos y conexión a internet mediante atajos de teclado rápidos y accesibles.

### Atajos de teclado básicos (NVDA + Shift + tecla)
- NVDA + Shift + E: Resumen de recursos (porcentaje de memoria RAM en uso y carga de CPU).
- NVDA + Shift + 1: Carga promedio del procesador (CPU) y uso de cada núcleo.
- NVDA + Shift + 2: Memoria RAM física y virtual (usada, libre, total y porcentaje).
- NVDA + Shift + 3: Espacio libre, usado y total en todas las unidades de disco.
- NVDA + Shift + 4: Estado de la red Wi-Fi (nombre de red SSID, intensidad de señal y seguridad).
- NVDA + Shift + 5: Frecuencia y velocidad del procesador (reloj en GHz, velocidad base y turbo).
- NVDA + Shift + 6: Versión, compilación y arquitectura de Windows.
- NVDA + Shift + 7: Tiempo de actividad del sistema (cuánto lleva encendido el ordenador).
- NVDA + Shift + 8: Tarjeta gráfica (GPU): memoria utilizada, total, porcentaje de carga y temperatura.

### Diagnósticos avanzados (NVDA + Shift + Control + número)
Si pulsas el atajo una vez, se anuncia el informe por voz. Si lo pulsas dos veces seguidas rápidamente, el resultado se copia directamente al portapapeles sin tener que repetir el análisis.
- NVDA + Shift + Control + 1: Estado de salud S.M.A.R.T., temperatura y desgaste de discos SSD y mecánicos.
- NVDA + Shift + Control + 2: Procesos con mayor consumo de recursos (programas que más CPU y RAM están gastando).
- NVDA + Shift + Control + 3: Medición de velocidad de internet en tiempo real (latencia/ping, descarga y subida).
- NVDA + Shift + Control + 4: Diagnóstico avanzado de batería del equipo (nivel, tiempo restante, capacidad de diseño y desgaste).
- NVDA + Shift + Control + 5: Nivel de batería de auriculares y dispositivos Bluetooth conectados.

### Alertas automáticas en segundo plano
En el menú de NVDA > Preferencias > Opciones > Monitor del Sistema, puedes activar avisos con sonido o voz para:
- Temperatura elevada de CPU o GPU.
- Nivel bajo o carga completa de la batería de la laptop.
- Batería baja en auriculares y dispositivos Bluetooth conectados.
- Pérdida de conexión o cambios en la señal Wi-Fi.
- Desgaste crítico en discos de estado sólido (SSD).

### Menú en Herramientas de NVDA
Puedes acceder cómodamente desde el menú de NVDA > Herramientas > Monitor del Sistema:
- Configuración...: Abre directamente el panel de opciones y alertas de Monitor del Sistema.
- Documentación: Abre este manual de ayuda en tu navegador.

## Novedades de la versión 2.7 (12 de septiembre de 2026)

### Novedades

- Se añadió un apartado propio en las opciones de NVDA para avisar si la temperatura de un disco sube demasiado, con umbral térmico (30 a 90 °C) e intervalo en minutos personalizables.
- Se retiró el anuncio automático de temperatura del atajo general de discos para que la lectura de unidades y espacio libre sea rápida y no sature de datos.
- La temperatura de los discos se consulta directamente al controlador de hardware sin requerir permisos de administrador ni depender de comandos lentos de PowerShell.

---

## Novedades de la versión 2.6 (12 de septiembre de 2026)

### Mejorado

- Integración completa con el registro nativo de NVDA (`logHandler.log`), permitiendo que cualquier evento o error técnico se consulte de forma limpia y directa en el Visor de Registro de NVDA.
- Al desactivar o recargar complementos, los elementos del menú Herramientas se destruyen adecuadamente liberando recursos de la interfaz.
- Cierre y descarga rigurosos de hilos de supervisión en segundo plano y temporizadores de alerta al detener el complemento.

---

## Novedades de la versión 2.5 (8 de septiembre de 2026)

### Corregido

- Los avisos automáticos de temperatura, batería, discos y Bluetooth no llegaban a saltar nunca. Un fallo interno detenía el vigilante en su primera vuelta.
- Un procesador Intel Core i5-13600K se confundía con un AMD Ryzen 5 3600 y se anunciaba con 4,2 GHz máximos en vez de 5,0.
- La configuración no se abría desde el menú Herramientas.
- El aviso de temperatura del procesador y el de la gráfica podían quedarse con umbrales de prueba sin que nada lo indicara.
- Cuatro fallos que ocurrían en silencio ahora quedan anotados en el registro de NVDA.
- La medición del ping y las consultas al sistema podían quedarse esperando indefinidamente si el programa consultado se colgaba.
- Un mensaje aparecía dos veces en los 34 archivos de idioma, lo que impedía a las herramientas de traducción abrirlos.

### Cambios internos

- La velocidad máxima de cada procesador conocido pasa de 117 condiciones encadenadas a una tabla de datos, más fácil de ampliar.
- El escaneo de dispositivos Bluetooth, que ocupaba 382 líneas seguidas, se repartió en siete piezas con nombre propio.
- El vigilante de avisos, de 239 líneas, se repartió en cinco vigilancias independientes.
- La prueba de velocidad de internet y la consulta de salud de discos separan ahora medir de interpretar.
- La ventana de opciones, la búsqueda de conflictos y las consultas al procesador se agruparon por secciones.
- Se añadieron 30 comprobaciones automáticas que se ejecutan solas en GitHub con cada cambio.

El listado completo de todas las versiones está en el archivo CHANGELOG.md
del repositorio del complemento.

### Créditos y Agradecimientos
- Basado en el excelente complemento Resource Monitor de Joseph Lee y colaboradores.
- Módulo de baterías Bluetooth inspirado en ideas de BlueToothBatteryReport.
- Contiene 35 traducciones comunitarias preservando los créditos de sus traductores originales.
