# Registro de cambios / Changelog

Todos los cambios importantes de **Monitoreo del Sistema**.
Lo más reciente, arriba. En español primero y en inglés después.

*All notable changes to **System Monitor**. Newest on top. Spanish first, English below.*

---

## 2.9 — 2026-09-13

### Español

- Consulta de temperatura de discos sin elevación de privilegios: implementación de llamadas nativas a DeviceIoControl mediante IOCTL_STORAGE_QUERY_PROPERTY y StorageDeviceTemperatureProperty, permitiendo vigilar unidades SSD y mecánicas desde cuentas de usuario estándar sin requerir ejecutar NVDA como Administrador ni recurrir a PowerShell.
- Filtrado preventivo de ranuras vacías: comprobación inteligente de manejadores para omitir ranuras M.2 o puertos SATA desocupados, aligerando el ciclo de vigilancia térmica automática en segundo plano.
- Cálculo de tiempo encendido blindado con GetTickCount64: sustitución de llamadas dependientes del reloj del sistema por el contador monotónico de 64 bits del kernel de Windows, evitando errores o cifras negativas al sincronizar la hora por internet y formateando el tiempo en lenguaje natural adaptado al idioma de NVDA tanto en singular como en plural.
- Soporte universal de GPU para Windows (DirectX DXGI y contadores PDH): módulo desacoplado gpu.py con soporte para NVIDIA (nvidia-smi), AMD (biblioteca nativa ADL atiadlxx.dll con callbacks LocalAlloc) y adaptadores universales DirectX mediante contadores PDH y enumeración COM DXGI, con liberación garantizada de interfaces mediante Release().
- Monitorización avanzada de batería en periféricos Bluetooth: motor desarrollado y ampliado por Daliana a partir de la referencia inicial de BlueToothBatteryReport (por Cary-rowen y colaboradores), incorporando una matriz ampliada de 4 claves DEVPROPKEY (SetupAPI y bthprops.cpl) para reconocer periféricos que el diseño original no detectaba, compatibilidad con lecturas en texto, sistema autónomo de alertas periódicas de batería baja en segundo plano y ejecución asíncrona sin bloqueos en la interfaz.
- Saneamiento y soporte de redes Wi-Fi ocultas en wlanapi.py: decodificación binaria segura de SSID, filtrado de bytes nulos y liberación garantizada de memoria nativa con WlanFreeMemory en bloques try/finally.
- Blindaje contra divisiones por cero: protecciones matemáticas añadidas en el cálculo de frecuencias dinámicas de CPU con Turbo Boost, porcentajes de memoria física y memoria virtual swap (psutil.swap_memory).
- Medición de velocidad de red en tiempo real más segura: ejecución de pruebas mediante conexiones HTTPS con sockets de cierre garantizado y cálculo ponderado de tasas de transferencia.
- Gestión de hilos daemon y apagado limpio: todos los subprocesos de supervisión en segundo plano operan como hilos daemon con eventos de parada coordinados (threading.Event), garantizando que NVDA reinicie o cierre de inmediato sin bloqueos.

### English

- Unprivileged drive temperature querying: native DeviceIoControl implementation using IOCTL_STORAGE_QUERY_PROPERTY and StorageDeviceTemperatureProperty, enabling SSD and HDD temperature monitoring under standard user accounts without requiring NVDA to run as Administrator or invoking PowerShell.
- Predictive empty slot filtering: intelligent device descriptor checks bypass empty M.2 or SATA drive bays, minimizing latency during background thermal watchdog loops.
- Monotonic uptime calculation via GetTickCount64: switched from system clock deltas to the Windows 64-bit kernel tick counter, preventing negative numbers or glitches during NTP time synchronizations and generating natural language time summaries in both singular and plural.
- Universal Windows GPU support (DirectX DXGI and PDH counters): modular gpu.py engine providing telemetry for NVIDIA (nvidia-smi), AMD (native ADL library atiadlxx.dll with LocalAlloc memory callbacks), and generic DirectX GPUs via PDH counters and COM DXGI enumeration with guaranteed Release() resource reclamation.
- Advanced Bluetooth peripheral battery reporting: engine expanded and improved by Daliana based on the initial reference from BlueToothBatteryReport (by Cary-rowen and contributors), adding an expanded 4-key DEVPROPKEY matrix (SetupAPI and bthprops.cpl) to detect peripherals missed by the original design, text-formatted battery parsing, autonomous background low-battery alerts, and non-blocking asynchronous execution.
- Hidden Wi-Fi network support and sanitization in wlanapi.py: safe binary SSID parsing, null-byte filtering, and guaranteed native memory release via WlanFreeMemory wrapped in try/finally blocks.
- Zero-division defenses: mathematical guards prevent division-by-zero exceptions across dynamic CPU frequency scaling (Turbo Boost), RAM utilization percentages, and swap virtual memory calculations.
- Resilient real-time internet speed testing: network tests utilize secure HTTPS streams with guaranteed socket closure and throughput weighting.
- Daemon thread lifecycle hardening: all background monitoring workers run with daemon=True and coordinated threading.Event stop flags, ensuring NVDA restarts and exits instantaneously without freezing.

---

## 2.9.1 — 2026-09-13

### Español

Mantenimiento y limpieza interna del código. Sin cambios visibles en el funcionamiento del complemento.

Corrección de una doble llamada redundante a la consulta de red Wi-Fi: al pulsar el atajo dos veces seguidas para copiar el resultado al portapapeles, el código consultaba la información de red dos veces en lugar de reutilizar la ya calculada. Se unificó el patrón de anuncio o copia en un método central (`_anunciarOCopiar`) que ocho atajos distintos compartían con código repetido, eliminando la duplicación y el error de doble consulta. Se eliminaron también importaciones de módulos que el código no utilizaba en `gpu.py`.

### English

Internal maintenance and code cleanup. No user-visible changes.

Fixed a redundant double Wi-Fi query when pressing the shortcut twice to copy the result: the add-on was querying the Wi-Fi adapter twice instead of reusing the already-computed information. Unified the announce-or-copy pattern across eight separate scripts into a shared internal helper (`_anunciarOCopiar`), eliminating code duplication and the redundant hardware query. Also removed unused module imports from `gpu.py`.

---

## 2.7 — 2026-09-12

### Español

#### Novedades

- Se añadió en las Opciones de NVDA una sección dedicada para vigilar la temperatura de los discos. Permite activar o desactivar el aviso, elegir la temperatura deseada (de 30 a 90 °C) y el intervalo de comprobación en minutos.
- Se retiró el anuncio automático de temperatura del atajo general de discos para que la lectura de unidades y espacio libre sea rápida y directa.
- La temperatura de los discos físicos se consulta ahora directamente al controlador mediante llamadas estándar del sistema (IOCTL_STORAGE_QUERY_PROPERTY), sin pedir permisos de administrador ni depender de comandos lentos de PowerShell.
- Se incorporaron pruebas automáticas para verificar la lectura de temperaturas y la lógica de alertas térmicas de discos.

### English

#### What's New

- Added a dedicated section in NVDA Settings to monitor drive temperatures, allowing users to enable or disable the alert, set the alert threshold (30 to 90 °C), and configure the check interval in minutes.
- Removed automatic temperature reporting from the general disk summary shortcut, keeping disk space announcements concise and direct.
- Physical drive temperatures are now read directly from the hardware controller via standard system IOCTL calls without requiring administrator privileges or PowerShell commands.
- Added automated test cases covering drive temperature reading and thermal alert logic.

---

## 2.6 — 2026-09-12

### Español

#### Mejorado

- Integración con el sistema oficial de registro de NVDA (`logHandler.log`), permitiendo que cualquier evento o error técnico se consulte de forma limpia y directa en el Visor de Registro de NVDA.
- Al desactivar o recargar complementos, los elementos del menú Herramientas se destruyen adecuadamente liberando recursos de la interfaz.
- Cierre y descarga rigurosos de hilos de supervisión en segundo plano y temporizadores de alerta al detener el complemento.

### English

#### Improved

- Switched to NVDA's native logging framework (`logHandler.log`) so all diagnostics integrate cleanly with NVDA's Log Viewer.
- Clean teardown of Tools menu items on addon termination/reload, preventing orphaned UI handles.
- Rigorous cleanup of background monitoring threads and alert timers upon addon termination.

---

## 2.5 — 2026-09-08

### Español

#### Corregido

- Los avisos automáticos de temperatura, batería, discos y Bluetooth no llegaban a saltar nunca. Un fallo interno detenía el vigilante en su primera vuelta.
- Un procesador Intel Core i5-13600K se confundía con un AMD Ryzen 5 3600 y se anunciaba con 4,2 GHz máximos en vez de 5,0.
- La configuración no se abría desde el menú Herramientas.
- El aviso de temperatura del procesador y el de la gráfica podían quedarse con umbrales de prueba sin que nada lo indicara.
- Cuatro fallos que ocurrían en silencio ahora quedan anotados en el registro de NVDA.
- La medición del ping y las consultas al sistema podían quedarse esperando indefinidamente si el programa consultado se colgaba.
- Un mensaje aparecía dos veces en los 34 archivos de idioma, lo que impedía a las herramientas de traducción abrirlos.

#### Cambios internos

- La velocidad máxima de cada procesador conocido pasa de 117 condiciones encadenadas a una tabla de datos, más fácil de ampliar.
- El escaneo de dispositivos Bluetooth, que ocupaba 382 líneas seguidas, se repartió en siete piezas con nombre propio.
- El vigilante de avisos, de 239 líneas, se repartió en cinco vigilancias independientes.
- La prueba de velocidad de internet y la consulta de salud de discos separan ahora medir de interpretar.
- La ventana de opciones, la búsqueda de conflictos y las consultas al procesador se agruparon por secciones.
- Se añadieron 30 comprobaciones automáticas que se ejecutan solas en GitHub con cada cambio.

### English

#### Fixed

- Automatic alerts for temperature, battery, disks and Bluetooth never fired. An internal error stopped the watcher on its first pass.
- An Intel Core i5-13600K was mistaken for an AMD Ryzen 5 3600 and reported 4.2 GHz max instead of 5.0.
- Settings would not open from the Tools menu.
- CPU and GPU temperature alerts could keep test thresholds with nothing indicating it.
- Four failures that happened silently are now recorded in the NVDA log.
- Ping measurement and system queries could wait forever if the program being queried hung.
- One message appeared twice in all 34 language files, which stopped translation tools from opening them.

#### Internal changes

- Maximum speed for each known processor moved from 117 chained conditions to a data table that is easier to extend.
- The Bluetooth device scan, 382 lines in a single block, was split into seven named pieces.
- The alert watcher, 239 lines, was split into five independent watches.
- The internet speed test and the disk health query now separate measuring from interpreting.
- The settings window, the conflict check and the processor queries were grouped into sections.
- Added 30 automatic checks that run on their own on GitHub with every change.

---

## 2.4 y anteriores / 2.4 and earlier

El historial de estas versiones está en los mensajes de guardado del repositorio,
en la pestaña de confirmaciones de GitHub.

*The history of these versions lives in the repository commit messages, on the
GitHub commits tab.*
