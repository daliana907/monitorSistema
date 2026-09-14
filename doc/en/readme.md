# System Monitor for NVDA

- Author: Daliana (based on Resource Monitor by Joseph Lee and contributors)
- Version: 2.9
- Compatibility: NVDA 2023.1 and later
- License: GNU GPL v2

[Leer en español](../es/readme.md)

---

## English Version

System Monitor provides a complete set of accessible diagnostic tools to check the status and performance of your computer, battery, peripherals, and internet connection using fast keyboard shortcuts.

### Basic Shortcuts (NVDA + Shift + key)

- NVDA + Shift + E: Resource summary (RAM memory in use and CPU load percentage).
- NVDA + Shift + 1: Average processor load (CPU) and individual core usage.
- NVDA + Shift + 2: Physical and virtual RAM memory (used, free, total, and percentage).
- NVDA + Shift + 3: Free, used, and total space on all disk drives.
- NVDA + Shift + 4: Wi-Fi network status (SSID network name, signal strength, and security).
- NVDA + Shift + 5: Processor frequency and speed (current clock in GHz, base speed, and turbo).
- NVDA + Shift + 6: Windows version, build number, and architecture.
- NVDA + Shift + 7: System uptime (how long the computer has been running).
- NVDA + Shift + 8: Graphics card (GPU): memory in use, total memory, and processor utilization.

### Advanced Diagnostics (NVDA + Shift + Control + number)

Press once to hear the report spoken. Press twice quickly to copy the result directly to your clipboard without repeating the measurement.

- NVDA + Shift + Control + 1: Drive health (S.M.A.R.T.), remaining lifetime, and wear level for SSDs and hard disks.
- NVDA + Shift + Control + 2: Top resource-consuming processes (programs using the most CPU and RAM).
- NVDA + Shift + Control + 3: Real-time internet speed test (ping/latency, download, and upload speeds).
- NVDA + Shift + Control + 4: Advanced laptop battery diagnostics (charge level, remaining runtime, design capacity, and wear).
- NVDA + Shift + Control + 5: Battery level for connected Bluetooth headphones and devices.

### Automatic Background Alerts

Configurable under NVDA Menu > Preferences > Settings > System Monitor:

- High CPU or GPU temperatures (customizable thermal threshold from 30 to 100 °C).
- Hot disk drive alert (drive temperature monitoring with custom threshold and check intervals).
- Low battery and full charge notifications for laptops.
- Low battery alerts for connected Bluetooth headphones.
- Wi-Fi network disconnection and signal changes.
- Critical solid-state drive (SSD) wear alerts.

### Tools Menu

You can access the add-on from NVDA Menu > Tools > System Monitor:

- Settings...: Opens the System Monitor configuration panel directly.
- Check shortcut conflicts with other add-ons...: Scans for overlapping shortcuts with other installed add-ons.

---

## What's new in 2.9.1 (13 September 2026)

- Faster clipboard copy for Wi-Fi status: pressing the network status shortcut (NVDA + Shift + 4) twice quickly now copies instantly by reusing the data already read, instead of querying the wireless adapter a second time, eliminating the unnecessary delay.
- General stability improvement: unified and reinforced the internal logic of all 8 system information shortcuts (CPU, RAM, frequency, drives, Wi-Fi, Windows version, uptime, and GPU) for more reliable and consistent behavior when announcing by speech or copying to clipboard.
- Internal cleanup and complete technical documentation of all add-on functions.

## What's new in 2.9 (13 September 2026)

- Disk temperature checks without administrator permissions: you can now check the temperature of your SSDs and hard drives from any standard user account without running NVDA as Administrator.
- Faster checks and lower resource usage: the add-on skips empty drive slots and unused ports, making automatic background temperature checks faster and lighter.
- More accurate computer uptime reporting: uptime calculation no longer gets confused when Windows syncs its clock over the internet, and reports days, hours, and minutes with natural phrasing (such as "1 hour and 1 minute").
- Universal graphics card support: detects and announces memory and GPU usage across all major graphics cards (NVIDIA, AMD, and Intel/DirectX integrated graphics) smoothly without freezing.
- Bluetooth headphone and device battery: accurately checks the battery percentage of your connected Bluetooth headphones and devices using an advanced engine expanded by Daliana (inspired by the initial reference of BlueToothBatteryReport), featuring broader device recognition, autonomous low-battery background alerts, and smart filtering of disconnected hardware.
- More reliable Wi-Fi connection handling: the add-on reliably reads Wi-Fi networks with hidden names or special characters without speech interruptions.
- Improved calculation stability: fixed calculation issues that could produce errors when measuring dynamic processor Turbo Boost speeds or swap memory under heavy system loads.
- Faster and safer internet speed testing: network speed tests now run over encrypted connections (HTTPS) with improved connection handling for reliable download and upload results.
- Instant NVDA exit and restart: all background monitoring tasks terminate cleanly the moment NVDA closes or restarts, preventing delays during shutdown.

### Credits

- Based on Resource Monitor by Joseph Lee and contributors.
- Bluetooth battery module: Substantially improved and expanded by Daliana, inspired by the initial reference from BlueToothBatteryReport (by Cary-rowen and contributors). Features significant improvements: an expanded 4-key DEVPROPKEY matrix to detect peripherals missed by the original design, support for text-formatted battery readings, automatic background alerts with customizable thresholds, non-blocking asynchronous execution to keep NVDA fully responsive, and quick clipboard copying via double-press.
- Advanced diagnostics, GPU, network monitoring, and enhancements by Daliana.
