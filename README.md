# Monitor del Sistema para NVDA (System Monitor)

[![Pruebas](https://github.com/daliana907/monitorSistema/actions/workflows/pruebas.yml/badge.svg)](https://github.com/daliana907/monitorSistema/actions/workflows/pruebas.yml)

Autora: Daliana (basado en Resource Monitor de Joseph Lee y colaboradores)
Versión: 2.7
Compatibilidad: NVDA 2019.3 en adelante
Licencia: GNU GPL v2

[Read in English below](#english-version)

[Registro de cambios](CHANGELOG.md) · [Changelog](CHANGELOG.md)

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

### Créditos y Agradecimientos
- Basado en el excelente complemento Resource Monitor de Joseph Lee y colaboradores.
- Módulo de baterías Bluetooth inspirado en ideas de BlueToothBatteryReport.
- Contiene 35 traducciones comunitarias preservando los créditos de sus traductores originales.

---

## English Version

System Monitor is an accessible all-in-one resource, hardware, and network monitor for NVDA.

### Basic Shortcuts (NVDA + Shift + key)
- NVDA + Shift + E: Resource summary (RAM usage and overall CPU load).
- NVDA + Shift + 1: CPU load average and per-core load.
- NVDA + Shift + 2: Physical and virtual RAM (used, total, and percentage).
- NVDA + Shift + 3: Disk space across all fixed, removable, and network drives.
- NVDA + Shift + 4: Wi-Fi status (SSID name, signal strength, and security cipher).
- NVDA + Shift + 5: CPU clock speed (current GHz, base clock, and turbo status).
- NVDA + Shift + 6: Windows edition, version, and architecture.
- NVDA + Shift + 7: System uptime.
- NVDA + Shift + 8: Dedicated GPU status (memory usage, core load, and temperature).

### Advanced Diagnostics (NVDA + Shift + Control + number)
Press once to hear the report spoken. Press twice quickly to copy the report directly to the clipboard.
- NVDA + Shift + Control + 1: Drive health (S.M.A.R.T.), temperature, and SSD wear percentage.
- NVDA + Shift + Control + 2: Top resource-consuming processes (highest CPU and RAM usage).
- NVDA + Shift + Control + 3: Real-time internet speed test (ping, download, and upload speeds).
- NVDA + Shift + Control + 4: Advanced laptop battery health, runtime, and design capacity wear.
- NVDA + Shift + Control + 5: Connected Bluetooth devices and audio peripheral battery levels.

### Automated Background Alerts
Configurable under NVDA Menu > Preferences > Settings > System Monitor:
- High CPU or GPU temperatures.
- Low laptop battery or battery full notification.
- Low battery alerts for connected Bluetooth audio devices.
- Wi-Fi disconnect and signal strength change notifications.
- Critical wear threshold alerts for SSDs.

### NVDA Tools Menu
You can access the add-on from NVDA > Tools > System Monitor:
- Settings...: Opens the System Monitor configuration panel directly.
- Documentation: Opens this user guide.

### Credits
- Based on Resource Monitor by Joseph Lee and contributors.
- Bluetooth battery logic inspired by BlueToothBatteryReport.
- Preserves 35 community localizations with original translator attributions.
