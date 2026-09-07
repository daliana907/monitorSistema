# System Monitor for NVDA

Author: Daliana (based on Resource Monitor by Joseph Lee and contributors)
Version: 2.4
Compatibility: NVDA 2019.3 or later
License: GNU GPL v2

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
