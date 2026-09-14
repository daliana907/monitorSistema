# Monitoreo del Sistema para NVDA (System Monitor)

- Autora: Daliana (basado en Resource Monitor de Joseph Lee y colaboradores)
- Versión: 2.9
- Compatibilidad: NVDA 2023.1 en adelante
- Licencia: GNU GPL v2

[Read in English](../en/readme.md)

---

## Versión en Español

Monitoreo del Sistema reúne en un solo lugar todas las herramientas para conocer el estado y rendimiento de tu equipo, batería, periféricos y conexión a internet mediante atajos de teclado rápidos y accesibles.

### Atajos de teclado básicos (NVDA + Shift + tecla)

- NVDA + Shift + E: Resumen de recursos (porcentaje de memoria RAM en uso y carga de CPU).
- NVDA + Shift + 1: Carga promedio del procesador (CPU) y uso de cada núcleo.
- NVDA + Shift + 2: Memoria RAM física y virtual (usada, libre, total y porcentaje).
- NVDA + Shift + 3: Espacio libre, usado y total en todas las unidades de disco.
- NVDA + Shift + 4: Estado de la red Wi-Fi (nombre de red SSID, intensidad de señal y seguridad).
- NVDA + Shift + 5: Frecuencia y velocidad del procesador (reloj en GHz, velocidad base y turbo).
- NVDA + Shift + 6: Versión, compilación y arquitectura de Windows.
- NVDA + Shift + 7: Tiempo de actividad del sistema (cuánto lleva encendido el ordenador).
- NVDA + Shift + 8: Tarjeta gráfica (GPU): memoria utilizada, total y porcentaje de carga del procesador gráfico.

### Diagnósticos avanzados (NVDA + Shift + Control + número)

Si pulsas el atajo una vez, se anuncia el informe por voz. Si lo pulsas dos veces seguidas rápidamente, el resultado se copia directamente al portapapeles sin tener que repetir el análisis.

- NVDA + Shift + Control + 1: Estado de salud S.M.A.R.T., vida útil y desgaste de discos SSD y mecánicos.
- NVDA + Shift + Control + 2: Procesos con mayor consumo de recursos (programas que más CPU y RAM están gastando).
- NVDA + Shift + Control + 3: Medición de velocidad de internet en tiempo real (latencia/ping, descarga y subida).
- NVDA + Shift + Control + 4: Diagnóstico avanzado de batería del equipo (nivel, tiempo restante, capacidad de diseño y desgaste).
- NVDA + Shift + Control + 5: Nivel de batería de auriculares y dispositivos Bluetooth conectados.

### Alertas automáticas en segundo plano

En el menú de NVDA > Preferencias > Opciones > Monitoreo del Sistema, puedes activar avisos con sonido o voz para:

- Temperatura elevada de CPU o GPU (con umbral térmico personalizable de 30 a 100 °C).
- Alerta de disco caliente (vigilancia de temperatura con umbral e intervalo configurables).
- Nivel bajo o carga completa de la batería de la laptop.
- Batería baja en auriculares y dispositivos Bluetooth conectados.
- Pérdida de conexión o cambios en la señal Wi-Fi.
- Desgaste crítico en discos de estado sólido (SSD).

### Menú en Herramientas de NVDA

Puedes acceder cómodamente desde el menú de NVDA > Herramientas > Monitoreo del Sistema:

- Configuración...: Abre directamente el panel de opciones y alertas de Monitoreo del Sistema.
- Comprobar conflictos con otros complementos...: Diagnostica colisiones de atajos con otros complementos instalados.

---

## Novedades de la versión 2.9.1 (13 de septiembre de 2026)

- Copia al portapapeles más rápida en el atajo de Wi-Fi: al pulsar dos veces seguidas el atajo de estado de red (NVDA + Shift + 4), la copia ahora es instantánea porque reutiliza la información ya leída en lugar de volver a consultar la tarjeta de red una segunda vez, eliminando el retardo innecesario.
- Mejora de estabilidad general: se unificó y reforzó la lógica interna de los 8 atajos de información del sistema (CPU, RAM, frecuencia, discos, Wi-Fi, versión de Windows, tiempo de actividad y GPU) para garantizar un comportamiento más fiable y consistente al anunciar por voz o copiar al portapapeles.
- Limpieza interna y documentación técnica completa de todas las funciones del complemento.

## Novedades de la versión 2.9 (13 de septiembre de 2026)

- Lectura de temperatura de discos sin pedir permisos de administrador: ahora puedes consultar la temperatura de tus discos SSD y discos mecánicos desde cualquier cuenta de usuario estándar, sin necesidad de ejecutar NVDA como Administrador.
- Más rapidez y menor consumo: el sistema ya no pierde tiempo comprobando ranuras o puertos vacíos donde no hay ningún disco conectado, haciendo las comprobaciones automáticas mucho más ágiles.
- Tiempo de encendido del ordenador más exacto: el cálculo de cuánto tiempo lleva encendido el equipo ya no se confunde si la hora de Windows se sincroniza por internet, y anuncia correctamente las horas, minutos y días en singular y plural (por ejemplo: "1 hora y 1 minuto").
- Compatibilidad universal con tarjetas gráficas: ahora detecta y anuncia la memoria y el uso de tarjetas gráficas de todas las marcas (NVIDIA, AMD y gráficos integrados de Intel o DirectX) sin bloqueos ni errores.
- Batería de auriculares y dispositivos Bluetooth: informa con precisión del porcentaje de batería de tus auriculares y dispositivos conectados por Bluetooth mediante un motor avanzado y mejorado por Daliana (basado en la referencia inicial de BlueToothBatteryReport), que amplía la detección a dispositivos que antes no se reconocían, permite avisos automáticos de batería baja en segundo plano y descarta dispositivos apagados para evitar lecturas erróneas.
- Conexión Wi-Fi más robusta: el lector ahora reconoce y lee sin problemas las redes Wi-Fi con nombres especiales u ocultos sin quedarse mudo ni trabarse.
- Mayor estabilidad en cálculos del sistema: se corrigieron errores matemáticos que podían producir fallos al calcular la velocidad turbo del procesador o la memoria virtual cuando el sistema está al límite.
- Medición de velocidad de internet más rápida y segura: el test de velocidad se realiza mediante conexiones seguras protegidas (HTTPS) y ofrece una lectura de descarga y subida más estable.
- Cierre y reinicio de NVDA sin demoras: todas las tareas de vigilancia en segundo plano se detienen de inmediato al apagar o reiniciar NVDA, evitando que el lector tarde en cerrarse.

### Créditos y Agradecimientos

- Basado en el excelente complemento Resource Monitor de Joseph Lee y colaboradores.
- Módulo de baterías Bluetooth: Desarrollado y ampliado sustancialmente por Daliana, tomando como inspiración inicial la referencia de BlueToothBatteryReport (por Cary-rowen y colaboradores). Introduce mejoras clave como una matriz ampliada de 4 claves DEVPROPKEY para detectar periféricos que el diseño original omitía, soporte para valores de batería en formato texto, sistema de alertas automáticas en segundo plano, ejecución en hilos asíncronos para evitar congelamientos en NVDA y copia rápida de resultados al portapapeles con doble pulsación.
- Mejoras de diagnóstico avanzado, GPU, red y adaptaciones por Daliana.
