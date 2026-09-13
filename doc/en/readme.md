# System Monitor for NVDA

Author: Daliana (based on Resource Monitor by Joseph Lee and contributors)
Version: 2.9
Compatibility: NVDA 2023.1 or later
License: GNU GPL v2

System Monitor is an accessible all-in-one resource, hardware, and network monitor for NVDA.

### Basic Shortcuts (NVDA + Shift + key)
- NVDA + Shift + E: Resource summary (RAM memory in use and CPU load percentage).
- NVDA + Shift + 1: Average CPU load and per-core utilization.
- NVDA + Shift + 2: Physical and virtual RAM (used, free, total, and percentage).
- NVDA + Shift + 3: Disk space (free, used, and total for all drives).
- NVDA + Shift + 4: Wi-Fi status (SSID, signal strength, and security).
- NVDA + Shift + 5: CPU frequency and clock speed (current GHz, base, and turbo).
- NVDA + Shift + 6: Windows version, build, and architecture.
- NVDA + Shift + 7: System uptime (how long the computer has been running).
- NVDA + Shift + 8: Dedicated GPU memory used, total, and GPU processor load.

### Advanced Diagnostics (NVDA + Shift + Control + number)
Press once to hear the report spoken. Press twice quickly to copy the report directly to the clipboard.
- NVDA + Shift + Control + 1: Drive health (S.M.A.R.T.), remaining lifetime, and SSD wear percentage.
- NVDA + Shift + Control + 2: Top resource-consuming processes (highest CPU and RAM usage).
- NVDA + Shift + Control + 3: Real-time internet speed test (ping, download, and upload speeds).
- NVDA + Shift + Control + 4: Advanced laptop battery health, runtime, and design capacity wear.
- NVDA + Shift + Control + 5: Connected Bluetooth devices and audio peripheral battery levels.

### Automated Background Alerts
Configurable under NVDA Menu > Preferences > Settings > System Monitor:
- High CPU or GPU temperatures (customizable thermal threshold from 30 to 100 °C).
- Hot disk warning (thermal threshold and check interval).
- Low laptop battery or battery full notification.
- Low battery alerts for connected Bluetooth audio devices.
- Wi-Fi disconnect and signal strength change notifications.
- Critical wear threshold alerts for SSDs.

### NVDA Tools Menu
You can access the add-on from NVDA Menu > Tools > System Monitor:
- Settings...: Opens the System Monitor configuration panel directly.
- Check for add-on conflicts...: Checks for shortcut collisions with other installed add-ons.

## What's new in 2.9 (13 September 2026)

- Optimized background drive temperature monitoring to skip querying empty drive slots, making checks faster and lighter.
- System uptime reporting (NVDA+Shift+7) now fully translates into all NVDA languages with accurate singular and plural phrasing.
- Improved resilience of system uptime tracking when Windows automatically synchronizes or adjusts the clock.

---

## What's new in 2.7 (12 September 2026)

### What's New

- Added a dedicated section in NVDA Settings to monitor drive temperatures with customizable thermal thresholds (30 to 90 °C) and check intervals.
- Removed automatic temperature reporting from the general disk summary shortcut, keeping disk space announcements concise and uncluttered.
- Drive temperatures are queried directly from the hardware controller using standard system IOCTL calls without requiring Windows administrator privileges or slow PowerShell commands.

---

## What's new in 2.6 (12 September 2026)

### Improved

- Switched to NVDA's native logging framework (`logHandler.log`) so all diagnostics integrate cleanly with NVDA's Log Viewer.
- Clean teardown of Tools menu items on addon termination/reload, preventing orphaned UI handles.
- Rigorous cleanup of background monitoring threads and alert timers upon addon termination.

---

## What's new in 2.5 (8 September 2026)

### Fixed

- Automatic alerts for temperature, battery, disks and Bluetooth never fired. An internal error stopped the watcher on its first pass.
- An Intel Core i5-13600K was mistaken for an AMD Ryzen 5 3600 and reported 4.2 GHz max instead of 5.0.
- Settings would not open from the Tools menu.
- CPU and GPU temperature alerts could keep test thresholds with nothing indicating it.
- Four failures that happened silently are now recorded in the NVDA log.
- Ping measurement and system queries could wait forever if the program being queried hung.
- One message appeared twice in all 34 language files, which stopped translation tools from opening them.

### Internal changes

- Maximum speed for each known processor moved from 117 chained conditions to a data table that is easier to extend.
- The Bluetooth device scan, 382 lines in a single block, was split into seven named pieces.
- The alert watcher, 239 lines, was split into five independent watches.
- The internet speed test and the disk health query now separate measuring from interpreting.
- The settings window, the conflict check and the processor queries were grouped into sections.
- Added 30 automatic checks that run on their own on GitHub with every change.

The full history of every version is in the CHANGELOG.md file of the
add-on repository.

### Credits
- Based on Resource Monitor by Joseph Lee and contributors.
- Bluetooth battery logic inspired by BlueToothBatteryReport.
- Preserves 35 community localizations with original translator attributions.
