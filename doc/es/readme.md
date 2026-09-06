# Monitor del Sistema para NVDA

* Autora: Daliana
* Versión: 2.4
* Compatibilidad con NVDA: 2019.3 en adelante

Este complemento proporciona información accesible en tiempo real sobre el uso de la memoria RAM, la carga del procesador (CPU), la velocidad/frecuencia del procesador, el espacio en disco, la salud de la batería, conexión de red Wi-Fi, velocidad de Internet, la versión de Windows, el tiempo de actividad y el estado de la tarjeta gráfica (GPU y VRAM).

> **Origen y Reconocimiento:** Este complemento es una bifurcación (fork) ampliada que toma como base e inspiración el extraordinario trabajo de **Joseph Lee y los colaboradores del complemento Resource Monitor** para la comunidad de NVDA. Se amplió el diseño original incorporando nuevas capacidades complementarias (monitorización multi-fabricante de GPU/VRAM para AMD, Intel y NVIDIA, salud de discos S.M.A.R.T., batería de dispositivos Bluetooth clásicos y BLE, test de velocidad y un sistema configurable de alertas automáticas en segundo plano) para ofrecer una suite accesible unificada.


## Atajos de teclado

### Monitor Básico
* **NVDA + Shift + E**: Presenta el porcentaje de memoria RAM utilizada y la carga promedio del procesador.
* **NVDA + Shift + 1**: Presenta la carga promedio del procesador y el porcentaje de uso de cada uno de los núcleos.
* **NVDA + Shift + 2**: Presenta la memoria RAM física y virtual utilizada, total y porcentaje.
* **NVDA + Shift + 3**: Presenta el espacio utilizado, total y porcentaje de las unidades de disco fijas, extraíbles y de red.
* **NVDA + Shift + 4**: Presenta el nombre de la red Wi-Fi (SSID), la intensidad de la señal y el tipo de seguridad. Si se pulsa dos veces, copia la información al portapapeles.
* **NVDA + Shift + 5**: Presenta la velocidad y frecuencia actual del procesador (GHz), velocidad base y estado del modo turbo boost.
* **NVDA + Shift + 6**: Presenta la versión de Windows, compilación y arquitectura de la CPU (x86 / AMD64).
* **NVDA + Shift + 7**: Presenta el tiempo de actividad del sistema (días, horas, minutos y segundos).
* **NVDA + Shift + 8**: Presenta la memoria de la tarjeta gráfica utilizada (MB y %) y la carga de GPU.
* **NVDA + Control + Shift + 8**: Presenta el desglose detallado de la memoria de la tarjeta gráfica (VRAM).

### Herramientas Avanzadas
* **NVDA + Shift + Control + 1**: Análisis de salud de disco (S.M.A.R.T), temperatura y desgaste real de tu SSD/HDD.
* **NVDA + Shift + Control + 2**: Detecta y anuncia los programas que más recursos (CPU/RAM) están consumiendo en ese momento.
* **NVDA + Shift + Control + 3**: Test de velocidad y latencia de Internet (Mide latencia de ping en milisegundos y velocidad real de descarga y subida en MB/s contra servidores dedicados).
* **NVDA + Shift + Control + 4**: Estado avanzado de la batería, incluyendo el porcentaje actual, tiempo restante y desgaste real de fábrica (Salud real).
* **NVDA + Shift + Control + 5**: Nivel de batería de los dispositivos Bluetooth conectados al equipo (auriculares, mandos, etc).

*Nota: Al pulsar cualquiera de estos atajos dos veces consecutivas, la información se copiará directamente al portapapeles. En las herramientas avanzadas que realizan pruebas intensivas, la doble pulsación copia al instante el resultado obtenido previamente sin repetir la prueba ni consumir ancho de banda o recursos de forma innecesaria.*

### Alertas automáticas del sistema
El complemento puede supervisar en segundo plano eventos importantes de tu equipo y avisarte con un tono suave y un mensaje hablado:
* **Batería cargada del equipo**: Te avisa cuando la batería completa su carga o alcanza el porcentaje configurado (por defecto 100%) para que puedas desconectar el cargador si lo deseas.
* **Batería baja del equipo**: Te advierte a tiempo cuando la batería de tu ordenador desciende del porcentaje que hayas elegido (por defecto 15%) y no está conectado a la corriente.
* **Sobrecalentamiento del procesador (CPU)**: Te notifica si la CPU alcanza el límite térmico configurado (por defecto 85 °C).
* **Sobrecalentamiento de la tarjeta gráfica (GPU)**: Te notifica si la GPU alcanza el límite térmico configurado (por defecto 80 °C).
* **Batería baja en dispositivos Bluetooth**: Te avisa con antelación si tus auriculares, mandos o accesorios Bluetooth caen por debajo del porcentaje configurado (por defecto 15%) antes de que se apaguen de golpe.
* **Estado de la red Wi-Fi (conexión y desconexión)**: Te notifica de inmediato con sonido y voz si el equipo se conecta o desconecta de una red inalámbrica.
* **Cambio en la intensidad de la señal Wi-Fi**: Te avisa con un tono sonoro proporcional y la locución del nuevo porcentaje únicamente cuando sube o baja la cobertura, manteniéndose completamente en silencio mientras no cambie.
* **Salud y desgaste crítico en discos (SSD / HDD)**: Supervisa periódicamente en segundo plano el estado S.M.A.R.T. de tus unidades y te advierte de inmediato si algún disco mecánico o sólido entra en estado de degradación o advertencia. En unidades de estado sólido (SSD), también supervisa el límite de desgaste de vida útil que configures (por defecto 80%).
Todas estas alertas pueden configurarse o desactivarse individualmente desde el menú de opciones de NVDA (**NVDA > Preferencias > Opciones > Monitor del Sistema**). Al activar las alertas de batería, temperatura y desgaste de SSD, se muestran barras deslizadoras interactivas para elegir el valor exacto de aviso, las cuales se ocultan si la alerta correspondiente está desmarcada manteniendo su valor predeterminado.

### Auditoría y Detección de Conflictos
El complemento audita automáticamente durante el arranque de NVDA si existen otros complementos en colisión (por ejemplo, atajos de teclado duplicados o complementos superpuestos como *Resource Monitor*).
* Puedes comprobar el estado en cualquier momento desde el menú **NVDA > Preferencias > Opciones > Monitor del Sistema**, pulsando el botón **Comprobar conflictos con otros complementos...**.
* También puedes asignar un atajo directo a esta función desde el diálogo **Gestos de entrada** de NVDA (categoría *Monitor del sistema*).

## Compatibilidad de Tarjetas Gráficas (GPU)
* Compatible de forma nativa y universal con tarjetas gráficas **AMD Radeon**, **Intel (UHD / Iris / Arc)** y **NVIDIA**. Con soporte para lectura de temperatura en GPUs NVIDIA y AMD Radeon mediante sus bibliotecas nativas.

## Créditos y Reconocimientos
* **Joseph Lee y los colaboradores de Resource Monitor**: Por el diseño y la base de código original del monitor de recursos para NVDA que inspiró este proyecto y sirvió como punto de partida.
* **BlueToothBatteryReport** (por Cary-rowen y colaboradores): Por servir de referencia técnica para la consulta de batería en dispositivos Bluetooth.
* **Traductores de Resource Monitor**: Por sus traducciones comunitarias base a más de 35 idiomas.
* **Comunidad de desarrolladores de complementos de NVDA**: Por su continuo esfuerzo en hacer el ecosistema accesible para personas con discapacidad visual en todo el mundo.

## Declaración sobre el uso de inteligencia artificial
He utilizado herramientas de inteligencia artificial como ayuda para escribir y organizar el código de este complemento.
Como autora (**Daliana**), he guiado todo el desarrollo, decidido qué funciones incluir y probado cada una de ellas directamente en mi ordenador para asegurarme de que funcione bien, sea cómoda de usar con NVDA y no cause problemas.

## Uso de servicios y datos de terceros
*En cumplimiento del criterio 1.6 de la Guía de revisión de complementos de NVDA en español:*  
Este complemento no utiliza técnicas de ingeniería inversa, claves API no autorizadas ni accesos ilícitos. Para las métricas del sistema, interactúa exclusivamente con interfaces de programación de aplicaciones (APIs) y subsistemas documentados de Microsoft Windows (`SetupAPI`, `CfgMgr32`, `WLAN API`, `PDH`, `WMI` y `psutil`). Para la lectura de sensores de tarjetas gráficas, utiliza las bibliotecas oficiales de los fabricantes (`nvapi.dll` y `atiadlxx.dll`). Para la prueba de velocidad de Internet, realiza peticiones estándar a puntos de enlace públicos de diagnóstico de red mediante HTTPS sin recopilar datos personales.

## Historial de cambios

### Versión 2.3
* **Alertas automáticas configurables en segundo plano**: Sistema integral de supervisión de eventos clave en el panel de opciones de NVDA (**Preferencias > Opciones > Monitor del Sistema**) para estado de red Wi-Fi (conexión/desconexión con sonido en el canal de audio de NVDA), variación en la intensidad de la señal Wi-Fi (tono y locución únicamente al variar la cobertura), salud y desgaste crítico en discos (supervisión periódica de anomalías S.M.A.R.T. en HDD/SSD y límite de desgaste en SSD), alertas de sobrecalentamiento de CPU (por defecto 85 °C) y GPU (por defecto 80 °C), batería cargada (por defecto 100%), batería baja del equipo (por defecto 15%), batería baja en Bluetooth (por defecto 15%) y desgaste límite en SSD (por defecto 80%), todas con controles interactivos y accesibles para elegir el valor exacto de aviso e intervalos de supervisión periódica (desde 1 minuto), con visibilidad dinámica y respuesta inmediata.
* **Copia automática con doble pulsación**: En todos los comandos avanzados (NVDA + Shift + Control + 1 al 5), al pulsar dos veces se programa la copia automática para que al finalizar la prueba se copie de inmediato al portapapeles, o se copia instantáneamente si la medición ya existía, evitando ejecuciones redundantes.
* **Detección precisa y optimizada de GPU**: Se excluye el adaptador virtual por software de Windows (*Microsoft Basic Render Driver*) para evitar reportar GPUs ficticias, y se homogeniza la locución con el prefijo oficial «GPU:» en equipos con una sola GPU física.
* **Detección universal y fiable de batería Bluetooth**: Integración del subsistema nativo de Bluetooth clásico (`bthprops.cpl`) y verificación de estado DevNode/PnP (`DEVPKEY_Device_DevNodeStatus`), asegurando la detección precisa de batería en auriculares, manos libres y altavoces de audio clásicos (como JLab, Sony, JBL, etc.) así como dispositivos BLE, resolviendo falsos descartes por desconexión.

### Versión 2.2
* **Protección contra pruebas duplicadas**: Bloqueo preventivo de ejecuciones simultáneas accidentales en tareas pesadas (velocidad de Internet, salud S.M.A.R.T. y consultas WMI).
* **Sistema de registro (log) detallado y exhaustivo**: Registro explícito en `nvda.log` del lanzamiento de cada atajo de teclado, parámetros recopilados, tiempos de respuesta de subsistemas (PDH, WMI, PowerShell) y transcripción de cada locución enviada al usuario o copiada al portapapeles.
* **Trazas completas de excepciones**: Integración de `exc_info=True` en todos los puntos de captura de errores para un diagnóstico técnico inmediato.

### Versión 2.1
* **Auditoría automática de conflictos**: Detección inteligente de complementos incompatibles o superpuestos (como Resource Monitor) y colisiones directas de atajos de teclado globales.
* **Panel de opciones enriquecido**: Botón interactivo y accesible para comprobar la compatibilidad y conflictos en cualquier momento.
* **Comando en Gestos de entrada**: Nuevo script configurable para auditar conflictos bajo demanda.
* **Pitidos de espera responsivos**: Integración de tonos de progreso periódicos sin bloqueo en consultas lentas (Bluetooth, batería avanzada, salud S.M.A.R.T. de discos y test de velocidad).
* **Corrección de enumeración DXGI**: Resuelta la detección de salidas de vídeo en adaptadores gráficos híbridos.
* **Compatibilidad actualizada**: Verificado y probado para NVDA 2026.2.

### Versión 2.0
* **Detección avanzada de batería Bluetooth**: Nuevo motor nativo ultrarrápido mediante APIs del sistema (`SetupAPI` y `CfgMgr32`) con soporte para auriculares de audio clásicos (perfil manos libres / HFP) y dispositivos de bajo consumo (BLE), resolviendo automáticamente el nombre comercial real de cada dispositivo.
* **Mensaje de inicio y tonos de espera**: Se añadieron pitidos suaves periódicos de progreso y mensaje de inicio al buscar dispositivos Bluetooth.
* **Corrección de bloqueo en PCs de sobremesa**: Detección síncrona instantánea que evita congelamientos de NVDA al pulsar el atajo de batería avanzada en equipos de escritorio.
* **Internacionalización**: Traducción completa al inglés de todos los mensajes, atajos y descripciones.

