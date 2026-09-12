# Nota técnica para revisores — Monitor del Sistema

*Versión 2.6 · Complemento para NVDA · Autora: Daliana*

Este documento describe qué toca el complemento en el sistema, qué permisos
pide y por qué. Está pensado para quien revisa el código antes de instalarlo o
publicarlo.

---

## Alcance

Monitor del Sistema anuncia por voz el estado del equipo: procesador, memoria,
discos, tarjeta gráfica, batería, red inalámbrica y aparatos Bluetooth. Además
puede avisar automáticamente cuando algo se sale de los límites que la usuaria
configure (batería baja, procesador caliente, disco desgastado, etc.).

Toda la información se obtiene del propio equipo. Nada se consulta a un
servicio externo, salvo la prueba de velocidad de internet, que se describe más
abajo y que solo se ejecuta cuando la usuaria la pide con su atajo.

## Interfaces del sistema que utiliza

### Registro de Windows — solo lectura

| Clave | Valor | Para qué |
|---|---|---|
| `HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0` | `~MHz` | Velocidad base del procesador |
| `HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0` | `ProcessorNameString` | Modelo del procesador |
| `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion` | `UBR` | Número de revisión de la compilación de Windows |

El complemento **no escribe nunca en el registro**.

### Bibliotecas del sistema

| DLL | Para qué |
|---|---|
| `pdh.dll` | Contadores de rendimiento: velocidad real del procesador y de la GPU |
| `cfgmgr32.dll`, `setupapi.dll` | Enumerar los aparatos Bluetooth y leer su nivel de batería |
| `bthprops.cpl` | Saber si un aparato Bluetooth está realmente conectado en este momento |
| `kernel32.dll` | Cerrar los identificadores abiertos al consultar el Bluetooth |
| `wlanapi.dll` | Avisos de conexión y desconexión del Wi-Fi, e intensidad de señal |
| `dxgi.dll` | Enumerar los adaptadores gráficos |
| `atiadlxx.dll` / `atiadlxy.dll` | Temperatura de CPU y GPU en equipos AMD (solo si están presentes) |

Todas se cargan con `ctypes` y todas son bibliotecas propias de Windows o del
controlador del fabricante. El complemento no incluye ningún binario propio.

### Programas externos

- `nvidia-smi.exe`, si está instalado, para la telemetría de tarjetas NVIDIA.
  Se busca en las rutas habituales; si no está, esa vía simplemente se descarta.
- `ping.exe`, en la prueba de velocidad de internet.
- `powershell.exe`, para dos consultas WMI concretas: la salud de la batería
  (`BatteryFullChargedCapacity` y `BatteryStaticData`, en `root\wmi`) y la salud
  de los discos (`Get-PhysicalDisk` y `Get-StorageReliabilityCounter`).
- `shutdown.exe` no se usa. El complemento no apaga ni reinicia nada.

### Biblioteca de terceros

`psutil`, que NVDA ya incluye, para carga de CPU, memoria, particiones,
batería y lista de procesos.

## Permisos elevados

**El complemento pide permisos de administrador en un solo caso**: el informe
completo de salud de los discos, cuando la usuaria lo solicita con su atajo de
teclado.

El motivo es que `Get-StorageReliabilityCounter` solo devuelve la temperatura y
el desgaste del disco a un proceso con privilegios. Sin elevar, Windows
devuelve esos campos vacíos.

El mecanismo es `ShellExecuteW` con el verbo `runas`, que provoca el aviso de
UAC de Windows. El script escribe su resultado en `%TEMP%\nvda_disk_health.json`,
el complemento lo lee y **lo borra inmediatamente**. Si la usuaria cancela el
aviso de permisos, el complemento lo dice en voz alta y se detiene; espera como
mucho quince segundos.

**La vigilancia automática de discos, la que corre en segundo plano, NO eleva
nunca.** Usa una consulta de PowerShell normal, con quince segundos de límite, y
se conforma con menos datos. Esto es deliberado: un aviso de permisos que
apareciera solo, sin que la usuaria hubiera pedido nada, sería inaceptable.

Ninguna otra función del complemento eleva.

## Red

El complemento **no abre ninguna conexión de red al arrancar ni en segundo
plano**. La única función que usa internet es la prueba de velocidad, que la
usuaria ejecuta con un atajo de teclado y que anuncia lo que está haciendo.

Esa prueba contacta tres destinos:

| Destino | Para qué | Límite |
|---|---|---|
| `1.1.1.1` (ping, 2 paquetes) | Latencia | 10 s |
| `http://cachefly.cachefly.net/100mb.test` | Velocidad de descarga | 5 s |
| `https://speed.cloudflare.com/__up` | Velocidad de subida | 5 s |

Lo que se sube son **bytes aleatorios generados en el momento** con
`os.urandom`, no datos del equipo. No se envía ningún identificador, ninguna
cookie, ningún dato personal. No hay claves de API, ni telemetría, ni
comprobación de actualizaciones.

## Almacenamiento

La configuración se guarda en la configuración propia de NVDA, bajo la sección
`monitorSistema`. El complemento no crea ningún archivo de configuración aparte.

El único archivo que escribe es el informe temporal de discos descrito arriba,
en la carpeta temporal de Windows, que se borra tras leerlo.

## Hilos

Dos hilos `daemon` durante toda la sesión:

- **El preparador**, que se ejecuta una vez al arrancar: deja listos los
  contadores del procesador y de la gráfica, se apunta a los avisos de Wi-Fi de
  Windows, y a los tres segundos revisa si hay conflictos con otros
  complementos. Esa revisión solo se anota en el registro de NVDA.
- **El vigilante**, que despierta cada cinco segundos para comprobar si toca dar
  algún aviso. Recuerda cuándo comprobó cada cosa por última vez, para no
  repetir avisos antes de que venza su intervalo.

Cada consulta larga que la usuaria pide (procesos, discos, red, batería,
Bluetooth) lanza además su propio hilo `daemon`, para no bloquear NVDA.

Todos se detienen mediante `_stopAlertsEvent` en `terminate()`, que también
cierra el contador del procesador y da de baja los avisos de Wi-Fi.

## Pruebas automáticas

El complemento incluye 30 pruebas que se ejecutan en cada envío a GitHub. Usan
un NVDA simulado y no requieren hardware concreto.

---

# Technical note for reviewers — System Monitor

*Version 2.6 · NVDA add-on · Author: Daliana*

This document describes what the add-on touches on the system, what permissions
it requests and why. It is intended for anyone reviewing the code before
installing or publishing it.

## Scope

System Monitor announces the state of the machine by speech: processor, memory,
drives, graphics card, battery, wireless network and Bluetooth devices. It can
also alert automatically when something crosses the thresholds the user
configures (low battery, hot processor, worn drive, and so on).

All information comes from the machine itself. Nothing is queried from an
external service, except the internet speed test described below, which runs
only when the user asks for it with its shortcut.

## System interfaces used

### Windows registry — read only

| Key | Value | Purpose |
|---|---|---|
| `HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0` | `~MHz` | Processor base speed |
| `HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0` | `ProcessorNameString` | Processor model |
| `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion` | `UBR` | Windows build revision number |

The add-on **never writes to the registry**.

### System libraries

| DLL | Purpose |
|---|---|
| `pdh.dll` | Performance counters: real processor and GPU clock |
| `cfgmgr32.dll`, `setupapi.dll` | Enumerate Bluetooth devices and read their battery level |
| `bthprops.cpl` | Tell whether a Bluetooth device is actually connected right now |
| `kernel32.dll` | Close handles opened while querying Bluetooth |
| `wlanapi.dll` | Wi-Fi connect/disconnect notifications and signal strength |
| `dxgi.dll` | Enumerate graphics adapters |
| `atiadlxx.dll` / `atiadlxy.dll` | CPU and GPU temperature on AMD machines (only if present) |

All are loaded with `ctypes` and all are Windows or vendor-driver libraries. The
add-on ships no binaries of its own.

### External programs

- `nvidia-smi.exe`, if installed, for NVIDIA GPU telemetry. It is looked for in
  the usual paths; if absent, that route is simply skipped.
- `ping.exe`, in the internet speed test.
- `powershell.exe`, for two specific WMI queries: battery health
  (`BatteryFullChargedCapacity` and `BatteryStaticData`, in `root\wmi`) and
  drive health (`Get-PhysicalDisk` and `Get-StorageReliabilityCounter`).
- `shutdown.exe` is not used. The add-on shuts down and reboots nothing.

### Third-party library

`psutil`, already bundled with NVDA, for CPU load, memory, partitions, battery
and process list.

## Elevated privileges

**The add-on requests administrator privileges in exactly one case**: the full
drive health report, when the user asks for it with its keyboard shortcut.

The reason is that `Get-StorageReliabilityCounter` returns drive temperature and
wear only to a privileged process. Without elevation Windows returns those
fields empty.

The mechanism is `ShellExecuteW` with the `runas` verb, which raises the Windows
UAC prompt. The script writes its result to `%TEMP%\nvda_disk_health.json`; the
add-on reads it and **deletes it immediately**. If the user cancels the prompt,
the add-on says so aloud and stops; it waits at most fifteen seconds.

**The automatic background drive check NEVER elevates.** It uses an ordinary
PowerShell query, bounded at fifteen seconds, and settles for less data. This is
deliberate: a permission prompt appearing on its own, with the user having asked
for nothing, would be unacceptable.

No other function of the add-on elevates.

## Network

The add-on **opens no network connection at startup or in the background**. The
only function that uses the internet is the speed test, which the user runs with
a keyboard shortcut and which announces what it is doing.

That test contacts three destinations:

| Destination | Purpose | Timeout |
|---|---|---|
| `1.1.1.1` (ping, 2 packets) | Latency | 10 s |
| `http://cachefly.cachefly.net/100mb.test` | Download speed | 5 s |
| `https://speed.cloudflare.com/__up` | Upload speed | 5 s |

What is uploaded is **random bytes generated on the spot** with `os.urandom`,
not machine data. No identifier, cookie or personal data is sent. There are no
API keys, no telemetry, no update checks.

## Storage

Settings are stored in NVDA's own configuration, under the `monitorSistema`
section. The add-on creates no separate configuration file.

The only file it writes is the temporary drive report described above, in the
Windows temp folder, deleted after being read.

## Threads

Two `daemon` threads for the whole session:

- **The initialiser**, run once at startup: prepares the processor and GPU
  counters, subscribes to Windows' Wi-Fi notifications, and after three seconds
  checks for conflicts with other add-ons. That check is only written to NVDA's
  log.
- **The watcher**, which wakes every five seconds to check whether any alert is
  due. It remembers when each item was last checked, so alerts are not repeated
  before their interval elapses.

Each long query the user requests (processes, drives, network, battery,
Bluetooth) additionally spawns its own `daemon` thread, so NVDA is never
blocked.

All are stopped through `_stopAlertsEvent` in `terminate()`, which also closes
the processor counter and unsubscribes from the Wi-Fi notifications.

## Automated tests

The add-on ships with 30 tests that run on every push to GitHub. They use a
simulated NVDA and require no particular hardware.
