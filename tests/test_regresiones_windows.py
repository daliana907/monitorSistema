# -*- coding: utf-8 -*-
"""Pruebas del archivo principal (__init__.py) que necesitan poder importarlo.

El archivo principal no se puede importar fuera de Windows porque, al hacerlo,
también importa wlanapi.py, que define estructuras de C incompatibles con Linux
(ver tests/test_logica.py, que por eso extrae funciones sueltas en vez de
importar todo). Aquí se registra, solo para esta prueba, un módulo de wifi de
mentira en el lugar de wlanapi antes de importar, para poder llegar a probar
de verdad los métodos que no dependen de la parte de wifi (los de la consulta
de velocidad de CPU y el propio cierre de la conexión Wi-Fi).

No es magia: es la misma idea que tests/nvda_falso.py, aplicada nada más que
al módulo de wifi, sin tocar ese archivo compartido.
"""
import ctypes
import os
import sys
import types
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nvda_falso                                    # noqa: E402

nvda_falso.instalar()

# La clase base falsa de nvda_falso no tiene un método terminate: el complemento
# real llama a super().terminate() dentro de su propio terminate(), así que hay
# que darle uno (vacío) para poder instanciar y probar el complemento real aquí.
import globalPluginHandler                            # noqa: E402
if not hasattr(globalPluginHandler.GlobalPlugin, "terminate"):
    globalPluginHandler.GlobalPlugin.terminate = lambda self: None

_NVDASettingsDialog = sys.modules["gui.settingsDialogs"].NVDASettingsDialog
if not hasattr(_NVDASettingsDialog, "categoryClasses"):
    _NVDASettingsDialog.categoryClasses = []

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "globalPlugins"))


class _WlanApiDeMentira(types.ModuleType):
    """Doble de wlanapi.py: no define ninguna estructura de C, solo atributos sueltos."""

    class _DummyStruct(ctypes.Structure):
        _fields_ = [("dummy", ctypes.c_int)]

    def __getattr__(self, nombre):
        if "LIST" in nombre or "INFO" in nombre or "GUID" in nombre:
            return self._DummyStruct
        return MagicMock()


class _ConfDeMentira(dict):
    """El config.conf real de NVDA es más que un diccionario: también tiene .spec."""

    def __init__(self):
        super().__init__()
        self.spec = {}


def _importarModuloPrincipal():
    """Registra los módulos de mentira que hacen falta y importa el archivo principal.

    Se hace en una función, y no una sola vez al cargar el archivo, para que cada
    prueba empiece con un módulo recién importado y sin rastros de pruebas anteriores.
    """
    sys.modules.pop("monitoreoSistema", None)
    sys.modules.pop("monitoreoSistema.__init__", None)
    sys.modules["monitoreoSistema.wlanapi"] = _WlanApiDeMentira("monitoreoSistema.wlanapi")
    paquete = types.ModuleType("monitoreoSistema")
    paquete.__path__ = [os.path.join(RAIZ, "globalPlugins", "monitoreoSistema")]
    sys.modules["monitoreoSistema"] = paquete
    import config
    config.conf = _ConfDeMentira()
    import importlib
    return importlib.import_module("monitoreoSistema.__init__")


class CierreDeLaConexionWifi(unittest.TestCase):
    """terminate() tiene que cerrar el manejador de Wi-Fi tal cual, no con byref()."""

    def test_wlan_close_handle_recibe_el_manejador_en_si(self):
        modulo = _importarModuloPrincipal()
        plugin = modulo.GlobalPlugin.__new__(modulo.GlobalPlugin)
        plugin._cpuQuery = None
        plugin._gpuProviders = []
        handleDePrueba = ctypes.wintypes.HANDLE(4321)
        plugin._client_handle = handleDePrueba
        plugin._negotiated_version = 1

        llamadas = []
        wlanFalso = MagicMock()
        wlanFalso.WlanCloseHandle.side_effect = lambda *a, **k: llamadas.append(a[0])
        modulo.wlanapi = wlanFalso

        plugin.terminate()

        self.assertEqual(len(llamadas), 1)
        # Si el arreglo se deshace, esto vuelve a recibir un objeto byref(), no el
        # manejador en sí, y esta comprobación de identidad vuelve a fallar.
        self.assertIs(llamadas[0], handleDePrueba)
        self.assertIsNone(plugin._client_handle)


class FugasDeLaConsultaDeVelocidadDeCpu(unittest.TestCase):
    """_initCpuQuery() no debe dejar consultas PDH abiertas sin cerrar."""

    def setUp(self):
        self.modulo = _importarModuloPrincipal()

    def test_cierra_la_consulta_si_ningun_contador_de_cpu_funciona(self):
        plugin = self.modulo.GlobalPlugin.__new__(self.modulo.GlobalPlugin)
        pdhFalso = MagicMock()
        pdhFalso.PdhOpenQueryW.return_value = 0
        pdhFalso.PdhAddEnglishCounterW.return_value = 1  # los 4 nombres de contador fallan
        ctypes.windll.pdh = pdhFalso

        plugin._initCpuQuery()

        pdhFalso.PdhCloseQuery.assert_called_once()

    def test_no_acepta_el_contador_de_tiempo_ocupado_como_si_fuera_velocidad(self):
        # "% Processor Time" mide qué tan ocupado está el procesador, no a qué
        # velocidad va: si _initCpuQuery lo aceptara como si fuera un contador
        # de velocidad válido, el cálculo posterior de GHz daría un número
        # equivocado en vez de caer al respaldo correcto (psutil.cpu_freq()).
        plugin = self.modulo.GlobalPlugin.__new__(self.modulo.GlobalPlugin)
        pdhFalso = MagicMock()
        pdhFalso.PdhOpenQueryW.return_value = 0

        def agregar_contador(query, nombre, reservado, phCounter):
            # Solo el contador de "tiempo ocupado" (el viejo respaldo) está disponible.
            return 0 if "Processor Time" in nombre else 1
        pdhFalso.PdhAddEnglishCounterW.side_effect = agregar_contador
        ctypes.windll.pdh = pdhFalso

        plugin._initCpuQuery()

        self.assertIsNone(plugin._cpuCounter)

    def test_cierra_la_consulta_anterior_antes_de_reintentar(self):
        plugin = self.modulo.GlobalPlugin.__new__(self.modulo.GlobalPlugin)
        pdhFalso = MagicMock()
        pdhFalso.PdhOpenQueryW.return_value = 0
        pdhFalso.PdhAddEnglishCounterW.return_value = 0  # el primer nombre de contador funciona
        ctypes.windll.pdh = pdhFalso

        plugin._initCpuQuery()
        primeraConsulta = plugin._cpuQuery
        self.assertIsNotNone(primeraConsulta)

        # Simula lo que hace _velocidadActualDelProcesador cuando una muestra falla:
        # vuelve a llamar a _initCpuQuery() para reintentar.
        plugin._initCpuQuery()

        cerrados = [llamada.args[0] for llamada in pdhFalso.PdhCloseQuery.call_args_list]
        self.assertIn(primeraConsulta, cerrados)


class ResilienciaDeAtajos(unittest.TestCase):
    """_atajoDeConsulta con doble pulsación no debe lanzar AttributeError al arrancar."""

    def setUp(self):
        self.modulo = _importarModuloPrincipal()

    def test_doble_pulsacion_con_resultado_none_no_lanza_error(self):
        import scriptHandler
        scriptHandler.getLastScriptRepeatCount = lambda: 1
        plugin = self.modulo.GlobalPlugin.__new__(self.modulo.GlobalPlugin)
        plugin._diskHealthRunning = False
        plugin._lastDiskHealthResult = None
        plugin._copyDiskHealthOnFinish = False

        consultas = []
        plugin._atajoDeConsulta(
            "_diskHealthRunning", "_lastDiskHealthResult", "_copyDiskHealthOnFinish",
            lambda: consultas.append(True), "espera"
        )
        self.assertEqual(len(consultas), 1)
        self.assertTrue(plugin._copyDiskHealthOnFinish)


class ResilienciaWlanApi(unittest.TestCase):
    """_getWlanInfo debe manejar fallos de WlanEnumInterfaces sin acceder a memoria nula."""

    def setUp(self):
        self.modulo = _importarModuloPrincipal()

    def test_wlan_enum_interfaces_con_error_no_lanza_null_pointer_access(self):
        plugin = self.modulo.GlobalPlugin.__new__(self.modulo.GlobalPlugin)
        plugin._client_handle = ctypes.wintypes.HANDLE(1234)
        self.modulo.wlanapi.WlanEnumInterfaces = MagicMock(return_value=1)

        res = plugin._getWlanInfo()
        self.assertIn("No hay dispositivos", res)


if __name__ == "__main__":
    unittest.main(verbosity=2)
