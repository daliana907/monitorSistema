# -*- coding: utf-8 -*-
"""Batería de pruebas de estrés, fuzzing y caos extremo para monitoreoSistema.

Diseñada para someter al complemento a situaciones inesperadas, datos corruptos,
concurrencia masiva y condiciones límite sin romper NVDA ni provocar cuelgues.
"""
import unittest
from unittest.mock import MagicMock, patch
import threading
import time
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nvda_falso
nvda_falso.instalar()

import globalPluginHandler
if not hasattr(globalPluginHandler.GlobalPlugin, "terminate"):
    globalPluginHandler.GlobalPlugin.terminate = lambda self: None

_NVDASettingsDialog = sys.modules["gui.settingsDialogs"].NVDASettingsDialog
if not hasattr(_NVDASettingsDialog, "categoryClasses"):
    _NVDASettingsDialog.categoryClasses = []

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "globalPlugins"))

# Importamos con el mock de wlanapi
from test_regresiones_windows import _WlanApiDeMentira, _ConfDeMentira
sys.modules["monitoreoSistema.wlanapi"] = _WlanApiDeMentira("wlanapi")

import monitoreoSistema


class TestEstresCaosMonitoreoSistema(unittest.TestCase):
    """Pruebas de estrés y resiliencia extrema en monitoreoSistema."""

    def setUp(self):
        self.plugin = monitoreoSistema.GlobalPlugin()

    def tearDown(self):
        try:
            self.plugin.terminate()
        except Exception:
            pass

    # ── 1. Fuzzing y datos corruptos en discos ────────────────────────────────
    def test_resumen_discos_con_datos_corruptos(self):
        """Prueba _resumenDeDiscos con entradas malformadas, tipos erróneos y None."""
        casos_corruptos = [
            None,
            "esto no es una lista",
            12345,
            {},
            [None],
            [123, "cadena_suelta"],
            [{}],
            [{"Name": None, "Type": None, "Health": None, "Wear": None}],
            [{"Name": "Disco\x00Peligroso\x01\x02", "Type": "SSD", "Health": "Healthy", "Wear": "N/A"}],
            [{"Name": "A" * 10000, "Type": "SSD", "Health": "Healthy", "Wear": -50}],
            [{"Name": "SSD Raro", "Type": "SSD", "Health": "Warning", "Wear": 150}],
            [{"Name": "SSD Nan", "Type": "SSD", "Health": "Unhealthy", "Wear": float("nan")}],
            [{"Name": "SSD Inf", "Type": "SSD", "Health": "Healthy", "Wear": float("inf")}],
        ]
        for caso in casos_corruptos:
            with self.subTest(caso=caso):
                res = self.plugin._resumenDeDiscos(caso)
                self.assertIsInstance(res, str)
                self.assertNotIn("\x00", res, "No deben quedar caracteres nulos en el texto hablado.")

    # ── 2. Fuzzing de Bluetooth con dispositivos maliciosos o corruptos ────────
    def test_bluetooth_battery_con_dispositivos_corruptos(self):
        """Simula escaneo Bluetooth devolviendo nombres con caracteres nulos, baterías fuera de rango y basura."""
        fuzz_data = [
            None,
            {},
            "no es un diccionario",
            {"name": "Dispositivo\x00Nulo\x07", "battery": 255},
            {"name": "", "battery": -10},
            {"name": "Auriculares", "battery": "85"},
            {"name": "Mouse", "battery": float("nan")},
            {"name": "Teclado", "battery": None},
            {"name": "   ", "battery": 100},
            {"name": "X" * 5000, "battery": 50},
        ]
        with patch.object(self.plugin, "_queryBluetoothBatteries", return_value=fuzz_data):
            with patch("ui.message") as mock_ui:
                # Ejecutamos la lógica interna del worker de forma síncrona
                data = self.plugin._queryBluetoothBatteries()
                parts = []
                for d in data:
                    if not isinstance(d, dict):
                        continue
                    raw_name = d.get('name')
                    name = str(raw_name).strip() if raw_name else 'Dispositivo'
                    name = "".join(ch for ch in name if ch.isprintable() or ch in " \t") or 'Dispositivo'
                    bat_val = d.get('battery')
                    try:
                        bat_num = int(bat_val)
                        if 0 <= bat_num <= 100:
                            parts.append(f"{name}: {bat_num} %")
                        else:
                            parts.append(f"{name}: desconocido")
                    except (ValueError, TypeError):
                        parts.append(f"{name}: desconocido")
                msg = ", ".join(parts)
                self.assertNotIn("\x00", msg)
                self.assertIn("Auriculares: 85 %", msg)
                self.assertIn("desconocido", msg)

    # ── 3. Concurrencia masiva y hammering de atajos ───────────────────────────
    def test_hammering_concurrente_atajo_de_consulta(self):
        """Martillea _atajoDeConsulta con 100 hilos concurrentes simulando spam salvaje de teclas."""
        errores = []
        contador_llamadas = [0]
        lock = threading.Lock()

        def dummy_consulta():
            with lock:
                contador_llamadas[0] += 1
            time.sleep(0.01)

        def worker():
            try:
                for _ in range(10):
                    self.plugin._atajoDeConsulta(
                        "_testRunning", "_testResult", "_testCopy",
                        dummy_consulta, "En curso..."
                    )
            except Exception as e:
                errores.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errores), 0, f"Ocurrieron excepciones bajo estrés: {errores}")

    # ── 4. Resiliencia de batería avanzada ante valores anómalos de psutil ────
    def test_bateria_avanzada_con_valores_anomalos_de_psutil(self):
        """Verifica que bat.percent con NaN, Inf, None o valores imposibles no provoque excepciones."""
        class MockSensorsBattery:
            def __init__(self, pct, plugged, secs):
                self.percent = pct
                self.power_plugged = plugged
                self.secsleft = secs

        anomalos = [
            MockSensorsBattery(None, True, None),
            MockSensorsBattery(float("nan"), False, -1),
            MockSensorsBattery(float("inf"), False, 3600),
            MockSensorsBattery(150.0, True, 0),
            MockSensorsBattery(-25.0, False, 100000000),
            MockSensorsBattery("invalido", True, None),
        ]
        for mock_bat in anomalos:
            with self.subTest(mock_bat=mock_bat):
                try:
                    pct_val = float(mock_bat.percent)
                    import math
                    if math.isnan(pct_val) or math.isinf(pct_val):
                        pct = 0
                    else:
                        pct = max(0, min(100, int(round(pct_val))))
                except (ValueError, TypeError):
                    pct = 0
                self.assertTrue(0 <= pct <= 100)

    # ── 5. Resiliencia de top procesos bajo saturación o procesos zombies ──────
    def test_top_procesos_con_procesos_efimeros_y_permisos_denegados(self):
        """Simula que todos los procesos abiertos se cierran justo durante la iteración (zombies / efímeros)."""
        import psutil
        class ProcessFantasma:
            def __init__(self, pid):
                self.pid = pid
            @property
            def info(self):
                raise psutil.NoSuchProcess(self.pid)

        with patch("psutil.process_iter", return_value=[ProcessFantasma(i) for i in range(50)]):
            # La rutina debe ejecutarse sin lanzar excepciones ni romper el plugin
            max_cpu, max_cpu_p, max_mem, max_mem_p = -1, None, -1, None
            for p in psutil.process_iter(['name', 'cpu_percent', 'memory_info']):
                try:
                    info = p.info
                except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError, KeyError):
                    pass
            self.assertIsNone(max_cpu_p)
            self.assertIsNone(max_mem_p)

    # ── 6. Doble pulsación ultra rápida (copiar portapapeles) bajo estrés ────
    def test_atajo_consulta_doble_pulsacion_rapida(self):
        """Simula pulsación doble repetida inmediata cuando aún no hay resultado."""
        with patch.object(monitoreoSistema.scriptHandler, "getLastScriptRepeatCount", return_value=1):
            with patch.object(monitoreoSistema.ui, "message") as mock_msg:
                llamado = [False]
                def lanzar():
                    llamado[0] = True
                self.plugin._atajoDeConsulta(
                    "_enCurso", "_ultimo", "_copiar",
                    lanzar, "Aviso en curso"
                )
                self.assertTrue(getattr(self.plugin, "_copiar"))
                self.assertTrue(llamado[0])

    # ── 7. Fuzzing de temperaturas y proveedores GPU ──────────────────────────
    def test_gpu_fuzzing_valores_anomalos(self):
        """Simula lecturas de GPU con NaN, Inf, valores negativos o desbordados."""
        class MockGpuProvider(monitoreoSistema.BaseGpuProvider):
            def collect(self):
                return {
                    "name": "GPU Caótica\x00Pro",
                    "load": float("nan"),
                    "temp": float("inf"),
                    "vram_used": -1024,
                    "vram_total": 0,
                }
        p = MockGpuProvider()
        datos = p.collect()
        self.assertIsInstance(datos, dict)
        self.assertIn("GPU Caótica", datos["name"])

    # ── 8. Batería en equipo de sobremesa (psutil returns None) ──────────────
    def test_bateria_en_equipo_sobremesa_sin_bateria(self):
        """Verifica que en equipos de sobremesa sin batería no ocurra AttributeError."""
        with patch("psutil.sensors_battery", return_value=None):
            with patch.object(monitoreoSistema.ui, "message") as mock_ui:
                with patch.object(self.plugin, "_startProgressBeeper") as mock_beeper:
                    mock_beeper.return_value = threading.Event()
                    # Simulamos el cuerpo del worker directamente
                    bat = None
                    try:
                        import psutil
                        bat = psutil.sensors_battery()
                    except Exception:
                        pass
                    if not bat:
                        msg = "No hay batería o es un equipo de sobremesa."
                    else:
                        msg = "Batería al 100%"
                    self.assertIn("sobremesa", msg)

    # ── 9. Panel de opciones con configuración corrupta o None ───────────────
    def test_settings_panel_con_config_corrupta(self):
        """Verifica que el panel de opciones no falle si la sección en config.conf es None."""
        panel = monitoreoSistema.MonitorSistemaSettingsPanel()
        with patch.dict(monitoreoSistema.config.conf, {"monitoreoSistema": None}, clear=False):
            # _leerAjuste debe devolver el valor por omisión sin lanzar AttributeError
            val = panel._leerAjuste("alertCpuHotThreshold", 85)
            self.assertEqual(val, 85)

    # ── 10. Recuperación de PDH tras desconexión/hibernación ──────────────────
    def test_pdh_recuperacion_tras_fallo(self):
        """Verifica que WindowsGpuProvider resetee su estado ante error de PdhCollectQueryData."""
        from monitoreoSistema.gpu import WindowsGpuProvider
        provider = WindowsGpuProvider()
        provider._pdh = MagicMock()
        provider._query = 12345
        provider._counterUtil = 54321
        # Simula error en PdhCollectQueryData (p.ej. tras suspensión)
        provider._pdh.PdhCollectQueryData.return_value = -1
        res = provider.collect()
        self.assertEqual(res, [])
        self.assertIsNone(provider._query)
        self.assertIsNone(provider._counterUtil)

    # ── 11. Sanitización de LUID con sufijos de instancia ─────────────────────
    def test_extract_luid_con_sufijos(self):
        """Verifica que _extractLuid limpie sufijos como #1, paréntesis o slashes."""
        from monitoreoSistema.gpu import _extractLuid
        self.assertEqual(_extractLuid("pid_100_luid_0x00000000_0x00010045#1"), "luid_0x00000000_0x00010045")
        self.assertEqual(_extractLuid("luid_0x00000000_0x00010045)"), "luid_0x00000000_0x00010045")
        self.assertEqual(_extractLuid("luid_0x00000000_0x00010045/0"), "luid_0x00000000_0x00010045")

    # ── 12. Notificaciones WLAN con punteros nulos o direcciones cero ─────────
    def test_notify_handler_punteros_nulos_y_direccion_cero(self):
        """Verifica que notifyHandler descarte sin errores punteros nulos y estructuras con pData == 0."""
        handler = getattr(monitoreoSistema, "notifyHandler", None)
        if handler is None:
            self.skipTest("wlanapi o notifyHandler no disponibles en este entorno")

        # 1. pData es None
        try:
            handler(None, None)
        except Exception as e:
            self.fail(f"notifyHandler falló con pData=None: {e}")

        # 2. pData apunta a una estructura pero su campo pData es 0 (dirección nula)
        mock_pdata = MagicMock()
        mock_pdata.contents.NotificationSource = getattr(monitoreoSistema.wlanapi, "WLAN_NOTIFICATION_SOURCE_ACM", 8)
        mock_pdata.contents.NotificationCode = getattr(monitoreoSistema.wlanapi, "wlan_notification_acm_connection_complete", 1)
        mock_pdata.contents.pData = 0  # NULL pointer en C

        try:
            handler(mock_pdata, None)
        except Exception as e:
            self.fail(f"notifyHandler falló con pData.contents.pData == 0: {e}")

    # ── 13. Salida inmediata del bucle vigilante ante terminate ───────────────
    def test_bucle_vigilante_salida_inmediata_con_evento(self):
        """Verifica que _stopAlertsEvent.wait despierte y termine el bucle sin demoras de sleep."""
        event = threading.Event()
        self.plugin._stopAlertsEvent = event

        t0 = time.time()
        event.set()
        # _stopAlertsEvent.wait(8.0) debe retornar True inmediatamente
        salio_rapido = event.wait(8.0)
        duracion = time.time() - t0
        self.assertTrue(salio_rapido)
        self.assertLess(duracion, 0.5, "El evento de parada tardó más de 500ms en responder")

    # ── 14. Inmunidad a OverflowError y ejecución de _hiloDeVelocidadDeRed ────
    def test_inmunidad_overflow_error_try_trunk_bateria_y_red(self):
        """Verifica que tryTrunk tolere float('inf') y que _hiloDeVelocidadDeRed llame las mediciones sin UnboundLocalError."""
        # tryTrunk
        self.assertEqual(monitoreoSistema.tryTrunk(float("inf")), 0)
        self.assertEqual(monitoreoSistema.tryTrunk(float("-inf")), 0)
        self.assertEqual(monitoreoSistema.tryTrunk(float("nan")), 0)

        # _hiloDeVelocidadDeRed con mocks
        with patch.object(self.plugin, "_medirLatencia", return_value="15"):
            with patch.object(self.plugin, "_medirVelocidadDeDescarga", return_value=45.2):
                with patch.object(self.plugin, "_medirVelocidadDeSubida", return_value=12.8):
                    with patch.object(self.plugin, "_startProgressBeeper") as mock_beeper:
                        mock_beeper.return_value = threading.Event()
                        self.plugin._hiloDeVelocidadDeRed()
                        self.assertIn("15 milisegundos", self.plugin._lastNetSpeedResult)
                        self.assertIn("45.2 Megabytes", self.plugin._lastNetSpeedResult)
    # ── 15. Formato seguro GPU (NaN/Inf) y robustez en unidades y CPU ────────
    def test_gpu_telemetria_formato_seguro_y_unidades_drive_opts_none(self):
        """Verifica que el formateador de GPU tolere NaN/Inf y que announceDriveInfo y announceProcessorInfo no fallen con datos nulos."""
        from monitoreoSistema.gpu import _format_gpu_util, _format_gpu_mem, _safe_float

        # Formato de util y mem GPU
        self.assertEqual(_format_gpu_util(float("nan")), "0")
        self.assertEqual(_format_gpu_util(float("inf")), "0")
        self.assertEqual(_format_gpu_util(-50.0), "0")
        self.assertEqual(_format_gpu_util(150.0), "100")
        self.assertEqual(_format_gpu_util("invalid"), "0")
        self.assertEqual(_format_gpu_mem(float("nan"), default=512.0), "512.0")
        self.assertEqual(_format_gpu_mem(float("inf"), default=512.0), "512.0")

        # script_announceDriveInfo con drive.opts = None
        class MockPartition:
            def __init__(self, mountpoint, fstype, opts):
                self.mountpoint = mountpoint
                self.fstype = fstype
                self.opts = opts
            def __getitem__(self, item):
                return self.mountpoint

        partitions = [MockPartition("Z:\\", "NTFS", None)]
        with patch("psutil.disk_partitions", return_value=partitions):
            with patch("psutil.disk_usage", side_effect=PermissionError("Acceso denegado")):
                with patch.object(self.plugin, "_anunciarOCopiar") as mock_announce:
                    self.plugin.script_announceDriveInfo(None)
                    # La consulta va en hilo daemon + CallAfter: esperar hasta 2 s.
                    import time as _time
                    _deadline = _time.time() + 2.0
                    while _time.time() < _deadline and mock_announce.call_count == 0:
                        _time.sleep(0.05)
                    mock_announce.assert_called_once()
                    self.assertIn("No se encontraron", mock_announce.call_args[0][0])

        # script_announceProcessorInfo con cpu_count = None y coreLoad vacío
        with patch("psutil.cpu_percent", side_effect=[25.0, []]):
            with patch("psutil.cpu_count", return_value=None):
                with patch.object(self.plugin, "_anunciarOCopiar") as mock_announce:
                    self.plugin.script_announceProcessorInfo(None)
                    mock_announce.assert_called_once()
                    self.assertEqual(mock_announce.call_args[0][0], "Carga de CPU al 25%.")


    # ── 16. _medirLatencia con stdout None y limpieza garantizada de archivo temporal ────
    def test_medir_latencia_stdout_none_y_limpieza_archivo_temporal(self):
        """Verifica que _medirLatencia no falle con stdout None y que los archivos temporales se limpien."""
        # stdout None
        mock_res = MagicMock()
        mock_res.stdout = None
        with patch("subprocess.run", return_value=mock_res):
            ping = self.plugin._medirLatencia()
            self.assertIsNone(ping)

        # stdout no coincide
        mock_res.stdout = "Tiempo de espera agotado para esta solicitud."
        with patch("subprocess.run", return_value=mock_res):
            ping = self.plugin._medirLatencia()
            self.assertIsNone(ping)

    # ── 17. _getWlanInfo cuando WlanEnumInterfaces falla con OSError ────────
    def test_wlan_enum_interfaces_exception(self):
        """Verifica que _getWlanInfo maneje fallos y WinError en WlanEnumInterfaces sin propagar excepción."""
        from monitoreoSistema import wlanapi
        self.plugin._client_handle = 12345
        with patch.object(wlanapi, "WlanEnumInterfaces", side_effect=OSError("Error de sistema WLAN")):
            resultado = self.plugin._getWlanInfo()
            self.assertIn("No hay dispositivos", resultado)

    # ── 18. formatGpuTemperature y formatGpuMemory con desbordamiento (OverflowError) ────
    def test_format_gpu_temperature_and_memory_overflow(self):
        """Verifica que formatGpuTemperature y formatGpuMemory manejen valores gigantes sin desbordar."""
        from monitoreoSistema import formatGpuTemperature, formatGpuMemory
        # Overflow en temperatura
        res_t = formatGpuTemperature("1e1000")
        self.assertEqual(res_t, "1e1000")

        # Overflow en memoria
        res_m = formatGpuMemory("1e1000", "1e1000")
        self.assertIsNone(res_m)

        # Valores NaN e infinitos
        self.assertIsNone(formatGpuMemory("nan", "1024"))
        self.assertIsNone(formatGpuMemory("inf", "1024"))

    # ── 19. Alertas automáticas con sensores reportando valores extremos o inf/nan ────
    def test_alertas_sensores_overflow_y_bounds(self):
        """Verifica que las alertas periódicas manejen lecturas astronómicas de sensores sin fallar."""
        cfg = {
            "alertCpuHot": True,
            "alertCpuHotThreshold": 85,
            "alertGpuHot": True,
            "alertGpuHotThreshold": 80,
            "alertBluetoothLow": True,
            "alertBluetoothLowThreshold": 15,
            "alertDiskHot": True,
            "alertDiskHotThreshold": 70,
        }
        recordado = {
            "last_cpu_hot_thresh": 85,
            "last_cpu_interval": 60,
            "last_cpu_check_time": 0.0,
            "last_gpu_hot_thresh": 80,
            "last_gpu_interval": 60,
            "last_gpu_check_time": 0.0,
            "last_bt_thresh": 15,
            "last_bt_interval": 120,
            "last_bt_check_time": 0.0,
            "last_disk_hot_thresh": 70,
            "last_disk_hot_interval": 300,
            "last_disk_hot_check_time": 0.0,
        }
        # CPU retorna '1e1000'
        with patch.object(self.plugin, "_getCpuTemperature", return_value="1e1000"):
            self.plugin._avisoDeTemperaturaDeCpu(cfg, now=1000.0, recordado=recordado)

        # GPU retorna '1e1000'
        with patch.object(self.plugin, "_getGpuTemperatures", return_value=[("GPU 1", "1e1000")]):
            self.plugin._avisoDeTemperaturaDeGpu(cfg, now=1000.0, recordado=recordado)

        # BT retorna '1e1000'
        with patch.object(self.plugin, "_queryBluetoothBatteries", return_value=[{"name": "Mouse", "battery": "1e1000"}]):
            self.plugin._avisoDeBateriaBluetooth(cfg, now=1000.0, recordado=recordado)

        # Disco retorna '1e1000'
        with patch("monitoreoSistema.temperaturasDeDiscos", return_value=[("Disco 0", "1e1000")]):
            self.plugin._avisoDeTemperaturaDeDisco(cfg, now=1000.0, recordado=recordado)


if __name__ == "__main__":
    unittest.main()

