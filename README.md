# System Monitor (Monitor del Sistema) for NVDA

* **Author:** Daliana
* **Version:** 2.3
* **Compatibility:** NVDA 2019.3 or later
* **License:** GNU General Public License v2.0 (GPLv2)

[Versión en español más abajo](#versión-en-español)

---

## English

**System Monitor** is an accessible system performance and hardware monitoring add-on for the NVDA screen reader. It provides real-time announcements for RAM usage, CPU load, CPU core metrics, clock frequency/turbo boost, disk space, battery status and health, Wi-Fi connection and signal strength, internet speed, Windows build information, system uptime, and multi-vendor GPU/VRAM performance.

### Origin and Acknowledgements
> **Fork Notice & Attribution:**  
> This project is an extended fork inspired by and built upon the foundational work of **Joseph Lee and the Resource Monitor add-on contributors** for the NVDA community.  
> We have expanded upon that architecture to incorporate multi-vendor GPU monitoring (AMD, Intel, NVIDIA), S.M.A.R.T. disk health analysis, Bluetooth peripheral battery reporting (classic audio & BLE), internet speed testing, and configurable real-time background event alerts, creating a unified all-in-one hardware suite for screen reader users.

### Key Shortcuts

#### Basic Monitor
* **NVDA + Shift + E**: Announces used RAM percentage and overall CPU load.
* **NVDA + Shift + 1**: Announces CPU load and per-core usage.
* **NVDA + Shift + 2**: Announces physical and virtual RAM (used, total, and percentage).
* **NVDA + Shift + 3**: Announces disk space for local, removable, and network drives.
* **NVDA + Shift + 4**: Announces Wi-Fi SSID, signal strength percentage, and security type.
* **NVDA + Shift + 5**: Announces CPU current frequency (GHz), base clock, and turbo status.
* **NVDA + Shift + 6**: Announces Windows version, build number, and CPU architecture.
* **NVDA + Shift + 7**: Announces system uptime (days, hours, minutes, seconds).
* **NVDA + Shift + 8**: Announces GPU load, memory used, and temperature (NVIDIA/AMD/Intel).
* **NVDA + Control + Shift + 8**: Detailed GPU and dedicated VRAM breakdown.

#### Advanced Tools
* **NVDA + Shift + Control + 1**: S.M.A.R.T. disk health diagnostic, drive temperature, and wear level.
* **NVDA + Shift + Control + 2**: Identifies top resource-consuming processes (CPU and RAM).
* **NVDA + Shift + Control + 3**: Internet speed and ping latency test.
* **NVDA + Shift + Control + 4**: Advanced battery metrics (capacity, discharge rate, wear percentage).
* **NVDA + Shift + Control + 5**: Battery levels for connected Bluetooth peripherals (headphones, controllers, BLE devices).

*Note: Pressing any of these shortcuts twice will copy the announced result to the clipboard.*

### Background Alerts & Monitoring
Configurable from **NVDA > Preferences > Settings > System Monitor**:
* Battery full notification (default 100%)
* Low PC battery alert (default 15%)
* CPU thermal alert (default 85 °C)
* GPU thermal alert (default 80 °C)
* Bluetooth accessory low battery alert (default 15%)
* Wi-Fi connection and disconnection chime & speech
* Wi-Fi signal level changes
* S.M.A.R.T. disk failure degradation and SSD wear threshold warning (default 80%)

### Credits & Acknowledgements
* **Joseph Lee and the Resource Monitor contributors**: For developing the original Resource Monitor add-on for NVDA, which provided the foundational codebase and architecture that inspired this project.
* **NVDA Add-on Community**: For making computing accessible and open to everyone.

---

## Versión en Español

**Monitor del Sistema** es un complemento de supervisión de rendimiento y hardware para el lector de pantalla NVDA. Proporciona información accesible en tiempo real sobre el uso de memoria RAM, carga de CPU y por núcleo, frecuencia de reloj, espacio en disco, estado y salud de la batería, conexión e intensidad Wi-Fi, velocidad de Internet, versión de Windows, tiempo de actividad y estado de la tarjeta gráfica (GPU y VRAM).

### Origen y Reconocimiento
> **Bifurcación y Atribución:**  
> Este proyecto es una bifurcación (fork) ampliada que toma como base e inspiración el extraordinario trabajo de **Joseph Lee y los colaboradores del complemento Resource Monitor** para la comunidad de NVDA.  
> Se amplió el diseño original incorporando nuevas capacidades complementarias (monitorización multi-fabricante de GPU/VRAM para AMD, Intel y NVIDIA, salud de discos S.M.A.R.T., batería de dispositivos Bluetooth clásicos y BLE, test de velocidad y un sistema configurable de alertas automáticas en segundo plano) para ofrecer una suite accesible todo-en-uno.

### Créditos y Agradecimientos
* **Joseph Lee y los colaboradores de Resource Monitor**: Por el diseño y la base de código original del monitor de recursos para NVDA que inspiró este proyecto y sirvió como punto de partida.
* **Comunidad de desarrolladores de complementos de NVDA**: Por su continuo esfuerzo en hacer el ecosistema accesible para personas con discapacidad visual en todo el mundo.
