# -*- coding: utf-8 -*-
"""Pruebas de gpu.py.

A diferencia del archivo principal del complemento, gpu.py sí se puede
importar fuera de Windows (no define estructuras de C incompatibles), así
que aquí se prueba el módulo real importado, no una copia de su lógica.
"""
import ctypes
import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nvda_falso                                    # noqa: E402

nvda_falso.instalar()

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "globalPlugins", "monitoreoSistema"))

import gpu  # noqa: E402


class ContadoresPdhDeGpuQueFallan(unittest.TestCase):
    """Si Windows no puede darle al complemento alguno de los contadores de GPU,
    el complemento tiene que darse cuenta y no tratarlo como si fuera un dato real.
    """

    def setUp(self):
        # _getDxgiAdapters hace llamadas a DirectX que no tienen sentido fuera
        # de Windows; se reemplaza para no depender de eso en esta prueba.
        self._original_get_adapters = gpu._getDxgiAdapters
        gpu._getDxgiAdapters = lambda: {}

    def tearDown(self):
        gpu._getDxgiAdapters = self._original_get_adapters

    def test_contador_que_falla_queda_en_none_no_en_cero_falso(self):
        pdhFalso = MagicMock()
        pdhFalso.PdhOpenQueryW.return_value = 0
        # Utilización: éxito. Memoria dedicada: éxito. Memoria compartida: falla.
        pdhFalso.PdhAddEnglishCounterW.side_effect = [0, 0, 1]
        ctypes.windll.pdh = pdhFalso

        proveedor = gpu.WindowsGpuProvider()
        proveedor._initPdh()

        self.assertIsNotNone(proveedor._counterUtil)
        self.assertIsNotNone(proveedor._counterDedicated)
        self.assertIsNone(proveedor._counterShared)

    def test_los_tres_contadores_funcionan(self):
        pdhFalso = MagicMock()
        pdhFalso.PdhOpenQueryW.return_value = 0
        pdhFalso.PdhAddEnglishCounterW.side_effect = [0, 0, 0]
        ctypes.windll.pdh = pdhFalso

        proveedor = gpu.WindowsGpuProvider()
        proveedor._initPdh()

        self.assertIsNotNone(proveedor._counterUtil)
        self.assertIsNotNone(proveedor._counterDedicated)
        self.assertIsNotNone(proveedor._counterShared)


if __name__ == "__main__":
    unittest.main(verbosity=2)
