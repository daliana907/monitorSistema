# Registro de cambios / Changelog

Todos los cambios importantes de **Monitor del Sistema**.
Lo más reciente, arriba. En español primero y en inglés después.

*All notable changes to **System Monitor**. Newest on top. Spanish first, English below.*

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
