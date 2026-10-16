# -*- coding: utf-8 -*-
# System Monitor (Monitoreo del Sistema) for NVDA
#
# A system resource and hardware monitoring add-on for NVDA.
# Based on Resource Monitor for NVDA.
#
# Original work Copyright 2013-2026 Joseph Lee, Alex Hall, Beqa Gozalishvili and Resource Monitor contributors.
# Modifications, extensions and new features Copyright 2026 Daliana.
# Released under the GNU General Public License version 2 (GPLv2).


import functools
import threading
import addonHandler
addonHandler.initTranslation()

try:
	from logHandler import log
except ImportError:
	import logging
	log = logging.getLogger(__name__)

import os
import math
import time
import winsound
import ctypes
import tones
import subprocess
import json
import re
import tempfile
import base64
import urllib.request
import ssl
import winreg
from ctypes import (
	addressof,
	byref,
	POINTER,
	wintypes,
	Structure,
	Union,
	c_long,
	c_double,
	c_longlong,
	c_char_p,
	c_wchar_p,
	c_void_p,
)
from datetime import datetime
from typing import Any
import api
import config
import globalPluginHandler
import globalVars
import queueHandler
import scriptHandler
import inputCore
import ui
import winVersion
import wx
import gui
from gui import blockAction, guiHelper, messageBox
from gui.settingsDialogs import NVDASettingsDialog, SettingsPanel
import psutil

try:
	from gui.nvdaControls import SelectOnFocusSpinCtrl as NumberCtrlClass
except ImportError:
	NumberCtrlClass = wx.SpinCtrl

try:
	from . import wlanapi
	wlanapiAvailable = True
except (OSError, AttributeError, ImportError, Exception):
	wlanapiAvailable = False

from .gpu import BaseGpuProvider, getGpuProviders

MODULE_DIR = os.path.dirname(__file__)

confspec = {
	"gpuTempUnit": "string(default=celsius)",
	"alertBatteryFull": "boolean(default=True)",
	"alertBatteryFullThreshold": "integer(default=100, min=70, max=100)",
	"alertBatteryLow": "boolean(default=True)",
	"alertBatteryLowThreshold": "integer(default=15, min=5, max=50)",
	"alertBatteryInterval": "integer(default=1, min=1, max=60)",
	"alertCpuHot": "boolean(default=True)",
	"alertCpuHotThreshold": "integer(default=85, min=40, max=105)",
	"alertCpuHotInterval": "integer(default=1, min=1, max=60)",
	"alertGpuHot": "boolean(default=True)",
	"alertGpuHotThreshold": "integer(default=80, min=40, max=100)",
	"alertGpuHotInterval": "integer(default=1, min=1, max=60)",
	"alertBluetoothLow": "boolean(default=True)",
	"alertBluetoothLowThreshold": "integer(default=15, min=5, max=50)",
	"alertBluetoothLowInterval": "integer(default=2, min=1, max=60)",
	"alertWlan": "boolean(default=True)",
	"alertWlanSignalChange": "boolean(default=False)",
	"alertDiskHealth": "boolean(default=True)",
	"alertDiskWearThreshold": "integer(default=80, min=70, max=95)",
	"alertDiskHealthInterval": "integer(default=240, min=1, max=1440)",
	"alertDiskHot": "boolean(default=True)",
	"alertDiskHotThreshold": "integer(default=70, min=30, max=90)",
	"alertDiskHotInterval": "integer(default=5, min=1, max=1440)",
}
config.conf.spec["monitoreoSistema"] = confspec

# Si los umbrales de temperatura de CPU o GPU quedaron configurados fuera de los rangos válidos, restaurar a los valores seguros por defecto (85 °C para CPU y 80 °C para GPU)
try:
	cur_cpu_thresh = config.conf.get("monitoreoSistema", {}).get("alertCpuHotThreshold")
	if cur_cpu_thresh is not None and (int(cur_cpu_thresh) < 40 or int(cur_cpu_thresh) > 105):
		config.conf["monitoreoSistema"]["alertCpuHotThreshold"] = 85
	cur_gpu_thresh = config.conf.get("monitoreoSistema", {}).get("alertGpuHotThreshold")
	if cur_gpu_thresh is not None and (int(cur_gpu_thresh) < 40 or int(cur_gpu_thresh) > 100):
		config.conf["monitoreoSistema"]["alertGpuHotThreshold"] = 80
except Exception:
	log.error("Monitoreo del Sistema: no se pudieron revisar los umbrales de temperatura.", exc_info=True)


def _beepAsync(freq: int, duration: int) -> None:
	"""Emite un pitido de forma segura desde cualquier hilo vía la cola de NVDA."""
	try:
		queueHandler.queueFunction(queueHandler.eventQueue, tones.beep, freq, duration)
	except Exception:
		pass


def _extraerSsid(dot11Ssid) -> str:
	"""Extrae el SSID recortado por SSIDLength con fallback a red oculta."""
	try:
		try:
			ssid_len = int(getattr(dot11Ssid, "SSIDLength", 0))
		except (ValueError, TypeError, OverflowError):
			ssid_len = 0
		ssid_len = max(0, min(ssid_len, 32))
		raw = getattr(dot11Ssid, "SSID", b"")
		try:
			ssid_bytes = bytes(raw[:ssid_len]) if ssid_len > 0 else b""
		except (TypeError, ValueError):
			ssid_bytes = b""
		nombre = ssid_bytes.decode("utf-8", errors="ignore").strip()
		# Recorta NULs y espacios residuales del búfer fijo de 32 bytes.
		nombre = nombre.split("\x00")[0].strip()
		return nombre or _("Red oculta")
	except Exception:
		return _("Red oculta")


def message(text: str, fileName: str) -> None:
	"""Anuncia un cambio del Wi-Fi y hace sonar el aviso correspondiente.

	Si tienes apagados los avisos de Wi-Fi no dice nada. Para el sonido prueba
	tres caminos, uno detrás de otro: el reproductor de NVDA, el de Windows y,
	si ninguno funciona, dos pitidos generados en el momento. Así el aviso se
	oye aunque falte el archivo de sonido.
	"""
	cfg = config.conf.get("monitoreoSistema", {})
	if not cfg.get("alertWlan", True):
		return
	log.info(f"MonitorSistema: Evento WLAN notificado: '{text}' (sonido: {fileName})")
	ui.message(text)
	path = os.path.join(MODULE_DIR, fileName)
	played = False
	if os.path.exists(path):
		try:
			import nvwave
			nvwave.playWaveFile(path)
			played = True
		except Exception as we:
			log.debug(f"MonitorSistema: Error reproduciendo wave con nvwave: {we}")
	if not played and os.path.exists(path):
		try:
			winsound.PlaySound(path, winsound.SND_ASYNC)
			played = True
		except Exception:
			pass
	if not played:
		if "connect" in fileName:
			_beepAsync(660, 80)
			_beepAsync(880, 100)
		else:
			_beepAsync(440, 100)
			_beepAsync(330, 120)


try:
	SECURITY_TYPE = {
		wlanapi.DOT11_AUTH_ALGO_80211_OPEN: _("Sin autenticación (abierta)"),
		wlanapi.DOT11_AUTH_ALGO_80211_SHARED_KEY: "WEP",
		wlanapi.DOT11_AUTH_ALGO_WPA: "WPA-Enterprise",
		wlanapi.DOT11_AUTH_ALGO_WPA_PSK: "WPA-PSK",
		wlanapi.DOT11_AUTH_ALGO_RSNA: "WPA2-Enterprise",
		wlanapi.DOT11_AUTH_ALGO_RSNA_PSK: "WPA2-PSK",
		wlanapi.DOT11_AUTH_ALGO_WPA3_ENT_192: "WPA3-Enterprise-192bit",
		wlanapi.DOT11_AUTH_ALGO_WPA3_SAE: "WPA3-SAE",
		wlanapi.DOT11_AUTH_ALGO_OWE: "OWE",
		wlanapi.DOT11_AUTH_ALGO_WPA3_ENT: "WPA3-Enterprise",
	}

	_ultimoSsidConocido: str | None = None

	@wlanapi.WLAN_NOTIFICATION_CALLBACK
	def notifyHandler(pData: Any, pCtx: Any):
		"""Recibe los avisos que Windows manda sobre la tarjeta Wi-Fi.

		Windows llama a esta función desde sus propios hilos, no desde NVDA, así
		que aquí no se habla directamente: se deja el mensaje en la cola de NVDA
		para que lo diga cuando le toque. Reconoce cuatro cosas: te conectaste a
		una red, te desconectaste, se encendió la tarjeta Wi-Fi y se apagó.
		"""
		global _ultimoSsidConocido
		try:
			if not pData or not getattr(pData, "contents", None):
				return
			if pData.contents.NotificationSource != wlanapi.WLAN_NOTIFICATION_SOURCE_ACM:
				return
			match pData.contents.NotificationCode:
				case wlanapi.wlan_notification_acm_connection_complete:
					pDataAddr = getattr(pData.contents, "pData", 0)
					dwSize = int(getattr(pData.contents, "dwDataSize", 0) or 0)
					if not pDataAddr or dwSize < ctypes.sizeof(wlanapi.WLAN_CONNECTION_NOTIFICATION_DATA):
						log.warning(f"MonitorSistema: notificación WLAN con dwDataSize sospechoso: {dwSize}")
						return
					try:
						notificationData = wlanapi.WLAN_CONNECTION_NOTIFICATION_DATA.from_address(pDataAddr)
					except (ValueError, OSError, Exception):
						return
					if notificationData.wlanReasonCode != wlanapi.ERROR_SUCCESS:
						return
					nombre_ssid = _extraerSsid(notificationData.dot11Ssid)
					_ultimoSsidConocido = nombre_ssid
					queueHandler.queueFunction(
						queueHandler.eventQueue,
						message,
						_("Conectado a {}").format(nombre_ssid),
						"connect.wav",
					)
				case wlanapi.wlan_notification_acm_disconnected:
					desconectado_de = _ultimoSsidConocido
					_ultimoSsidConocido = None
					ssid_nombre = ""
					pDataAddr = getattr(pData.contents, "pData", 0)
					dwSize = int(getattr(pData.contents, "dwDataSize", 0) or 0)
					if pDataAddr and dwSize >= ctypes.sizeof(wlanapi.WLAN_CONNECTION_NOTIFICATION_DATA):
						try:
							dot11 = wlanapi.WLAN_CONNECTION_NOTIFICATION_DATA.from_address(
								pDataAddr
							).dot11Ssid
							ssid_nombre = _extraerSsid(dot11)
							if ssid_nombre == _("Red oculta"):
								ssid_nombre = ""
						except Exception:
							pass
					red_nombre = ssid_nombre or desconectado_de
					if red_nombre:
						msg_desc = _("Desconectado de {}").format(red_nombre)
					else:
						msg_desc = _("Desconectado de la red inalámbrica")
					queueHandler.queueFunction(
						queueHandler.eventQueue,
						message,
						msg_desc,
						"disconnect.wav",
					)
				case wlanapi.wlan_notification_acm_interface_arrival:
					queueHandler.queueFunction(
						queueHandler.eventQueue, message, _("Se ha habilitado un dispositivo de red inalámbrica"), "connect.wav"
					)
				case wlanapi.wlan_notification_acm_interface_removal:
					queueHandler.queueFunction(
						queueHandler.eventQueue,
						message,
						_("Se ha deshabilitado un dispositivo de red inalámbrica"),
						"disconnect.wav",
					)
				case _:
					pass
		except Exception as e:
			log.error(f"MonitorSistema: Error procesando notificación de WLAN: {e}", exc_info=True)
except (NameError, AttributeError, Exception):
	notifyHandler = None
	# Sin la biblioteca de red inalambrica no hay avisos de wifi. Es normal en
	# equipos sin tarjeta, pero conviene poder comprobarlo en el registro.
	log.debug("Monitoreo del Sistema: no se pudo preparar el aviso de wifi.", exc_info=True)


_CUSTOM_RESIZE_MAX = 64


_ADL_DLL_CACHE = None
_ADL_DLL_NAME = None
_ADL_DLL_LOCK = threading.Lock()


def _getAdlDll():
	"""Devuelve la DLL ADL de AMD cacheada (atiadlxx/atiadlxy), cargándola una sola vez."""
	global _ADL_DLL_CACHE, _ADL_DLL_NAME
	try:
		with _ADL_DLL_LOCK:
			if _ADL_DLL_CACHE is not None:
				return _ADL_DLL_CACHE, _ADL_DLL_NAME
			for _name in ("atiadlxx.dll", "atiadlxy.dll"):
				try:
					_dll = ctypes.WinDLL(_name)
					_ADL_DLL_CACHE = _dll
					_ADL_DLL_NAME = _name
					return _dll, _name
				except Exception:
					continue
			return None, None
	except Exception:
		return None, None


def _freeAdlDll():
	"""Libera la DLL ADL cacheada con FreeLibrary (llamar en terminate)."""
	global _ADL_DLL_CACHE, _ADL_DLL_NAME
	try:
		with _ADL_DLL_LOCK:
			dll = _ADL_DLL_CACHE
			_ADL_DLL_CACHE = None
			_ADL_DLL_NAME = None
		if dll is not None:
			try:
				ctypes.windll.kernel32.FreeLibrary(dll._handle)  # type: ignore[attr-defined]
			except Exception:
				pass
	except Exception:
		pass


def customResize(array: Any, newSize: Any):
	"""Redimensiona una matriz ctypes en memoria a partir de su dirección base.

	La cantidad se limita a 64 elementos: Windows nunca devuelve más redes o
	interfaces que eso en una sola lista, y un valor mayor indica memoria
	corrupta. Devuelve una lista vacía si la entrada no es válida.
	"""
	try:
		n = int(newSize)
	except (ValueError, TypeError, OverflowError):
		log.warning(f"MonitorSistema: customResize con tamaño inválido: {newSize!r}")
		return []
	if n < 0 or n > _CUSTOM_RESIZE_MAX:
		log.warning(f"MonitorSistema: customResize sospechoso: newSize={newSize!r} (cota {_CUSTOM_RESIZE_MAX})")
		n = max(0, min(n, _CUSTOM_RESIZE_MAX))
	if n == 0:
		return []
	if array is None:
		log.warning("MonitorSistema: customResize con array None")
		return []
	array_type = getattr(array, "_type_", None)
	if array_type is None:
		log.warning("MonitorSistema: customResize sin _type_")
		return []
	try:
		base = addressof(array)
	except (ValueError, TypeError, Exception) as e:
		log.warning(f"MonitorSistema: customResize sin dirección base: {e}")
		return []
	try:
		return (array_type * n).from_address(base)
	except (ValueError, TypeError, OverflowError, Exception) as e:
		log.warning(f"MonitorSistema: customResize falló con n={n}: {e}")
		return []


alternative = [
	(1024.0**10.0, " QB"),
	(1024.0**9.0, " RB"),
	(1024.0**8.0, " YB"),
	(1024.0**7.0, " ZB"),
	(1024.0**6.0, " EB"),
	(1024.0**5.0, " PB"),
	(1024.0**4.0, " TB"),
	(1024.0**3.0, " GB"),
	(1024.0**2.0, " MB"),
	(1024.0**1.0, " KB"),
	(1024.0**0.0, (_(" byte"), _(" bytes"))),
]


def size(bytes_val: int | float, system: list[tuple[float, Any]] = alternative) -> str:
	"""Convierte una cantidad de bytes a una cadena legible con sufijo de unidad (KB, MB, GB, etc.)."""
	try:
		b_val = float(bytes_val) if bytes_val is not None else 0.0
		if math.isnan(b_val) or math.isinf(b_val) or b_val < 0.0:
			b_val = 0.0
	except (ValueError, TypeError, OverflowError):
		b_val = 0.0
	factor = 1.0
	suffix = " B"
	for f, s in system:
		if b_val >= float(f) or f == system[-1][0]:
			factor = f
			suffix = s
			break
	amount = float(b_val / factor) if factor != 0 else 0.0
	if isinstance(suffix, tuple):
		singular, multiple = suffix
		suffix = singular if float(amount) == 1.0 else multiple
	return "{:.2f}{}".format(float(amount), suffix)


def tryTrunk(n: float) -> int | float:
	"""Devuelve el número truncado a entero si no tiene parte decimal, o el float original."""
	try:
		if n == int(n):
			return int(n)
		return n
	except (ValueError, TypeError, OverflowError):
		return 0


def formatGpuTemperature(celsiusText: str) -> str:
	"""Formatea la temperatura de la GPU en Celsius o Fahrenheit según la configuración activa."""
	try:
		text_clean = str(celsiusText or "").strip().replace(",", ".")
		celsius = float(text_clean)
		if math.isnan(celsius) or math.isinf(celsius):
			return celsiusText
	except (TypeError, ValueError, OverflowError):
		return celsiusText
	unit = config.conf.get("monitoreoSistema", {}).get("gpuTempUnit", "celsius")
	if unit == "fahrenheit":
		try:
			value = celsius * 9.0 / 5.0 + 32.0
		except OverflowError:
			return celsiusText
		symbol = _("grados Fahrenheit")
	else:
		value = celsius
		symbol = _("grados Celsius")
	try:
		return "{} {}".format(tryTrunk(round(value, 1)), symbol)
	except (ValueError, OverflowError):
		return celsiusText


def formatGpuMemory(usedMibText: str, totalMibText: str) -> str | None:
	"""Convierte la memoria de la tarjeta gráfica en una frase que se entienda.

	Recibe los megabytes usados y los totales tal como los da la tarjeta, en
	texto. Devuelve algo como "1,2 GB de 8 GB utilizados (15%)". Si no se sabe
	el total, solo dice lo usado. Si el dato usado no es un número, devuelve
	None para que quien llame sepa que no hay nada que decir.
	"""
	try:
		clean_used = str(usedMibText or "").strip().replace(",", ".")
		usedMib = float(clean_used)
		if math.isnan(usedMib) or math.isinf(usedMib) or usedMib < 0:
			return None
	except (TypeError, ValueError, OverflowError):
		return None
	try:
		clean_total = str(totalMibText or "").strip().replace(",", ".")
		totalMib = float(clean_total)
		if math.isnan(totalMib) or math.isinf(totalMib) or totalMib < 0:
			totalMib = 0.0
	except (TypeError, ValueError, OverflowError):
		totalMib = 0.0

	try:
		usedBytes = usedMib * 1024.0 * 1024.0
		if totalMib > 0:
			totalBytes = totalMib * 1024.0 * 1024.0
			return _("{used} de {total} utilizados ({percent}%)").format(
				used=size(usedBytes, alternative),
				total=size(totalBytes, alternative),
				percent=tryTrunk(round(usedBytes / totalBytes * 100, 1)),
			)
		else:
			return _("{used} utilizados").format(used=size(usedBytes, alternative))
	except (OverflowError, ValueError):
		return None


# --- temperatura de los discos ---------------------------------------------
# Se le pregunta directamente al controlador del disco. Es el unico camino que
# no exige permisos de administrador: la via habitual de Windows
# (Get-StorageReliabilityCounter) los exige y le responde "acceso denegado" a un
# NVDA normal, asi que no sirve para un aviso automatico.
IOCTL_CONSULTAR_PROPIEDAD_DE_DISCO = 0x2D1400
PROPIEDAD_DE_TEMPERATURA = 52   # StorageDeviceTemperatureProperty
CONSULTA_NORMAL = 0             # PropertyStandardQuery
MAXIMO_DE_DISCOS = 8


class CONSULTA_DE_PROPIEDAD(Structure):
	"""Estructura STORAGE_PROPERTY_QUERY para consultar propiedades de almacenamiento."""
	_fields_ = [
		("PropertyId", wintypes.DWORD),
		("QueryType", wintypes.DWORD),
		("AdditionalParameters", ctypes.c_ubyte * 1),
	]


def _temperaturaDeUnDisco(numero):
	"""Grados a los que esta el disco fisico indicado, o None si no se sabe.

	Abre el disco pidiendo cero permisos de acceso, solo para preguntarle: por
	eso no hace falta elevar. Devuelve None si ese disco no existe, si el
	controlador no sabe dar su temperatura, o si la cifra no tiene sentido.
	"""
	MANEJADOR_INVALIDO = ctypes.c_void_p(-1).value
	COMPARTIR_LECTURA_Y_ESCRITURA = 3
	ABRIR_SI_EXISTE = 3
	try:
		ctypes.windll.kernel32.CreateFileW.restype = wintypes.HANDLE
		ctypes.windll.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
	except (AttributeError, TypeError):
		pass
	try:
		manejador = ctypes.windll.kernel32.CreateFileW(
			f"\\\\.\\PhysicalDrive{numero}", 0, COMPARTIR_LECTURA_Y_ESCRITURA,
			None, ABRIR_SI_EXISTE, 0, None,
		)
	except Exception as e:
		log.debug(f"MonitorSistema: No se pudo abrir el disco {numero}: {e}")
		return None
	if manejador in (MANEJADOR_INVALIDO, -1, 0, None):
		return None
	try:
		consulta = CONSULTA_DE_PROPIEDAD()
		consulta.PropertyId = PROPIEDAD_DE_TEMPERATURA
		consulta.QueryType = CONSULTA_NORMAL
		respuesta = (ctypes.c_ubyte * 512)()
		devueltos = wintypes.DWORD(0)
		ok = ctypes.windll.kernel32.DeviceIoControl(
			manejador,
			IOCTL_CONSULTAR_PROPIEDAD_DE_DISCO,
			byref(consulta), ctypes.sizeof(consulta),
			byref(respuesta), ctypes.sizeof(respuesta),
			byref(devueltos), None,
		)
		# La respuesta empieza con una cabecera de 24 bytes; despues viene una
		# entrada por cada sensor del disco, y la temperatura del primero esta
		# en el byte 26. Esta posicion esta comprobada sobre un disco real.
		if not ok or devueltos.value < 28:
			return None
		grados = ctypes.cast(byref(respuesta, 26), POINTER(ctypes.c_short))[0]
		# Un disco encendido nunca esta a cero grados: si sale eso, es que el
		# controlador no sabe la temperatura y devuelve el hueco vacio.
		if grados <= 0 or grados > 150:
			return None
		return int(grados)
	except Exception as e:
		log.debug(f"MonitorSistema: El disco {numero} no dio su temperatura: {e}")
		return None
	finally:
		try:
			ctypes.windll.kernel32.CloseHandle(manejador)
		except Exception:
			pass


def temperaturasDeDiscos():
	"""Temperatura de cada disco fisico que sepa decirla.

	Devuelve una lista de pares (nombre, grados). Con un solo disco se le llama
	"el disco"; con varios se numeran, que dicho en voz alta se entiende mucho
	mejor que leer el modelo entero. Los discos que no saben decir su
	temperatura simplemente no aparecen.
	"""
	gradosPorDisco = []
	for numero in range(MAXIMO_DE_DISCOS):
		grados = _temperaturaDeUnDisco(numero)
		if grados is not None:
			gradosPorDisco.append(grados)
	if len(gradosPorDisco) == 1:
		return [(_("el disco"), gradosPorDisco[0])]
	return [
		(_("el disco {}").format(posicion + 1), grados)
		for posicion, grados in enumerate(gradosPorDisco)
	]

class MonitorSistemaSettingsPanel(SettingsPanel):
	"""Panel de configuración de Monitoreo del Sistema en las Preferencias de NVDA."""
	title = "Monitoreo del Sistema"

	def makeSettings(self, settingsSizer: wx.BoxSizer) -> None:
		"""Monta el panel de opciones que aparece dentro de las preferencias de NVDA.

		Arriba la unidad de temperatura, Celsius o Fahrenheit. Debajo, los avisos
		automáticos agrupados por lo que vigilan: batería, temperaturas, y red y
		discos. Al final el botón para comprobar conflictos con otros complementos.
		Termina escondiendo los ajustes de cada aviso que esté desmarcado, para que
		el panel no se llene de cosas que no usas.
		"""
		self._settingsSizer = settingsSizer
		ayudante = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		gpuTempUnitLabelText = _("&Unidad de temperatura (CPU y GPU):")
		self._gpuTempUnitLabels = ["Celsius", "Fahrenheit"]
		self._gpuTempUnitValues = ["celsius", "fahrenheit"]
		self.gpuTempUnitList = ayudante.addLabeledControl(
			gpuTempUnitLabelText,
			wx.Choice,
			choices=self._gpuTempUnitLabels,
		)
		try:
			currentIndex = self._gpuTempUnitValues.index(
				config.conf.get("monitoreoSistema", {}).get("gpuTempUnit", "celsius")
			)
		except ValueError:
			currentIndex = 0
		self.gpuTempUnitList.SetSelection(currentIndex)

		# Los avisos automaticos, agrupados por lo que vigilan
		self._ajustesDeBateria(ayudante)
		self._ajustesDeTemperatura(ayudante)
		self._ajustesDeRedYDiscos(ayudante)

		# Botón para comprobar conflictos con otros complementos
		checkBtn = wx.Button(self, label=_("&Comprobar conflictos con otros complementos..."))
		checkBtn.Bind(wx.EVT_BUTTON, self.onCheckConflicts)
		ayudante.addItem(checkBtn)

		self._syncAllThresholdsVisibility()

	def _syncAllThresholdsVisibility(self) -> None:
		"""Sincroniza la visibilidad de todos los controles de umbral según sus casillas maestras."""
		self._updateBatteryFullVisibility(self.alertBatteryFullCheckbox.GetValue())
		self._updateBatteryLowVisibility(self.alertBatteryLowCheckbox.GetValue())
		self._updateCpuHotVisibility(self.alertCpuHotCheckbox.GetValue())
		self._updateGpuHotVisibility(self.alertGpuHotCheckbox.GetValue())
		self._updateBluetoothLowVisibility(self.alertBluetoothLowCheckbox.GetValue())
		self._updateDiskHealthVisibility(self.alertDiskHealthCheckbox.GetValue())
		self._updateDiskHotVisibility(self.alertDiskHotCheckbox.GetValue())

	def _ajustesDeBateria(self, ayudante):
		"""Casillas y valores de los avisos de bateria del equipo."""
		self.alertBatteryFullCheckbox = self._casillaDeAviso(
			ayudante, _('Avisar cuando la batería del equipo esté cargada'), "alertBatteryFull", alCambiar=self.onAlertBatteryFullChange)

		self.batteryFullSlider = self._numeroDeAviso(
			ayudante, _('&Porcentaje para la alerta de batería cargada:'), 70, 100, "alertBatteryFullThreshold", 100)

		self.alertBatteryLowCheckbox = self._casillaDeAviso(
			ayudante, _('Avisar cuando la batería del equipo esté baja'), "alertBatteryLow", alCambiar=self.onAlertBatteryLowChange)

		self.batteryLowSlider = self._numeroDeAviso(
			ayudante, _('&Porcentaje para la alerta de batería baja del equipo:'), 5, 50, "alertBatteryLowThreshold", 15)

		self.batteryIntervalEdit = self._numeroDeAviso(
			ayudante, _('&Intervalo de comprobación de la batería (minutos):'), 1, 60, "alertBatteryInterval", 1)

	def _ajustesDeTemperatura(self, ayudante):
		"""Casillas y valores de los avisos de temperatura del procesador y la grafica."""
		self.alertCpuHotCheckbox = self._casillaDeAviso(
			ayudante, _('Avisar si la temperatura del procesador es alta'), "alertCpuHot", alCambiar=self.onAlertCpuHotChange)

		initialCpuThresh = int(config.conf.get("monitoreoSistema", {}).get("alertCpuHotThreshold", 85))
		if initialCpuThresh < 40 or initialCpuThresh > 105:
			initialCpuThresh = 85
			config.conf["monitoreoSistema"]["alertCpuHotThreshold"] = 85

		self.cpuHotSlider = self._numeroDeAviso(
			ayudante, _('&Temperatura para la alerta de sobrecalentamiento del procesador:'), 40, 105, valor=initialCpuThresh)

		self.cpuHotIntervalEdit = self._numeroDeAviso(
			ayudante, _('I&ntervalo de comprobación de temperatura de CPU (minutos):'), 1, 60, "alertCpuHotInterval", 1)

		self.alertGpuHotCheckbox = self._casillaDeAviso(
			ayudante, _('Avisar si la temperatura de la tarjeta gráfica (GPU) es alta'), "alertGpuHot", alCambiar=self.onAlertGpuHotChange)

		initialGpuThresh = int(config.conf.get("monitoreoSistema", {}).get("alertGpuHotThreshold", 80))
		if initialGpuThresh < 40 or initialGpuThresh > 100:
			initialGpuThresh = 80
			config.conf["monitoreoSistema"]["alertGpuHotThreshold"] = 80

		self.gpuHotSlider = self._numeroDeAviso(
			ayudante, _('Temperat&ura para la alerta de sobrecalentamiento de la GPU:'), 40, 100, valor=initialGpuThresh)

		self.gpuHotIntervalEdit = self._numeroDeAviso(
			ayudante, _('Inter&valo de comprobación de temperatura de GPU (minutos):'), 1, 60, "alertGpuHotInterval", 1)

	def _ajustesDeRedYDiscos(self, ayudante):
		"""Casillas y valores de los avisos de Bluetooth, wifi y discos."""
		self.alertBluetoothLowCheckbox = self._casillaDeAviso(
			ayudante, _('Avisar cuando la batería de un dispositivo Bluetooth esté baja'), "alertBluetoothLow", alCambiar=self.onAlertBluetoothLowChange)

		self.bluetoothLowSlider = self._numeroDeAviso(
			ayudante, _('P&orcentaje para la alerta de batería baja en Bluetooth:'), 5, 50, "alertBluetoothLowThreshold", 15)

		self.bluetoothLowIntervalEdit = self._numeroDeAviso(
			ayudante, _('In&tervalo de comprobación de Bluetooth (minutos):'), 1, 60, "alertBluetoothLowInterval", 2)

		self.alertWlanCheckbox = self._casillaDeAviso(
			ayudante, _('Avisar cuando cambie el estado de la red Wi-Fi (conexión o desconexión)'), "alertWlan")

		self.alertWlanSignalChangeCheckbox = self._casillaDeAviso(
			ayudante, _('Avisar cuando cambie la intensidad de la señal Wi-Fi'), "alertWlanSignalChange", porOmision=False)

		self.alertDiskHealthCheckbox = self._casillaDeAviso(
			ayudante, _('Avisar si se detectan problemas de salud o desgaste crítico en discos (SSD / HDD)'), "alertDiskHealth", alCambiar=self.onAlertDiskHealthChange)

		self.diskWearSlider = self._numeroDeAviso(
			ayudante, _('Porcentaje de des&gaste para la alerta de discos SSD:'), 70, 95, "alertDiskWearThreshold", 80)

		self.diskHealthIntervalEdit = self._numeroDeAviso(
			ayudante, _('Intervalo de comprobación de dis&cos (minutos):'), 1, 1440, "alertDiskHealthInterval", 240)

		self.alertDiskHotCheckbox = self._casillaDeAviso(
		ayudante, _('Avisar si la temperatura de un disco es alta'), "alertDiskHot", alCambiar=self.onAlertDiskHotChange)

		self.diskHotSlider = self._numeroDeAviso(
		ayudante, _('Temperatura para la alerta de disco ca&liente:'), 30, 90, "alertDiskHotThreshold", 70)

		self.diskHotIntervalEdit = self._numeroDeAviso(
		ayudante, _('Intervalo de comprobación de temperatura de discos (&minutos):'), 1, 1440, "alertDiskHotInterval", 5)


	def _leerAjuste(self, clave, porOmision):
		"""Valor guardado de una opcion del complemento, o el de fabrica."""
		sec = config.conf.get("monitoreoSistema")
		if not isinstance(sec, dict):
			return porOmision
		return sec.get(clave, porOmision)

	def _casillaDeAviso(self, ayudante, texto, clave, porOmision=True, alCambiar=None):
		"""Casilla de activar o desactivar un aviso, ya marcada segun lo guardado.

		Las ocho casillas de la ventana se creaban con estas mismas tres lineas
		repetidas una y otra vez.
		"""
		casilla = ayudante.addItem(wx.CheckBox(self, label=texto))
		casilla.SetValue(bool(self._leerAjuste(clave, porOmision)))
		if alCambiar is not None:
			casilla.Bind(wx.EVT_CHECKBOX, alCambiar)
		return casilla

	def _numeroDeAviso(self, ayudante, texto, minimo, maximo, clave=None, porOmision=None, valor=None):
		"""Casilla numerica de un aviso: un porcentaje o un intervalo en minutos.

		Se le da la clave guardada, o directamente un valor ya calculado cuando
		hubo que corregirlo antes (es el caso de los umbrales de temperatura).
		"""
		if valor is None:
			valor = self._leerAjuste(clave, porOmision)
		try:
			val_int = int(valor)
		except (ValueError, TypeError):
			val_int = int(porOmision if porOmision is not None else minimo)
		val_int = max(minimo, min(maximo, val_int))
		return ayudante.addLabeledControl(
			texto,
			NumberCtrlClass,
			min=minimo,
			max=maximo,
			initial=val_int,
		)


	def _updateBatteryIntervalVisibility(self) -> None:
		try:
			show = self.alertBatteryFullCheckbox.GetValue() or self.alertBatteryLowCheckbox.GetValue()
			sizer = self.batteryIntervalEdit.GetContainingSizer()
			if sizer and hasattr(self, "_settingsSizer"):
				self._settingsSizer.Show(sizer, show=show, recursive=True)
			self.batteryIntervalEdit.Show(show)
		except Exception as e:
			log.error(f"MonitorSistema: Error actualizando visibilidad de intervalo de batería: {e}", exc_info=True)

	def _mostrarControlesDeAlerta(self, show, controles, descripcion, despuesDeMostrar=None):
		"""Muestra u oculta los controles de una alerta y recalcula la ventana de opciones.

		show: True para mostrarlos, False para ocultarlos.
		controles: lista de controles (barra deslizante, casilla de intervalo, etc.).
		descripcion: texto que aparece en el registro si algo falla.
		despuesDeMostrar: función opcional que se llama justo después de mostrar u ocultar.
		"""
		try:
			for control in controles:
				sizer = control.GetContainingSizer()
				if sizer and hasattr(self, "_settingsSizer"):
					self._settingsSizer.Show(sizer, show=show, recursive=True)
				control.Show(show)
			if despuesDeMostrar is not None:
				despuesDeMostrar()
			if hasattr(self, "_settingsSizer"):
				self._settingsSizer.Layout()
			self.Layout()
			if hasattr(self, "_sendLayoutUpdatedEvent"):
				self._sendLayoutUpdatedEvent()
		except Exception as e:
			log.error(f"MonitorSistema: Error actualizando visibilidad de {descripcion}: {e}", exc_info=True)

	def _updateBatteryFullVisibility(self, show: bool) -> None:
		"""Muestra u oculta los controles de configuración de aviso de batería cargada."""
		self._mostrarControlesDeAlerta(
			show, [self.batteryFullSlider], "barra de batería cargada",
			self._updateBatteryIntervalVisibility,
		)

	def _updateBatteryLowVisibility(self, show: bool) -> None:
		"""Muestra u oculta los controles de configuración de aviso de batería baja."""
		self._mostrarControlesDeAlerta(
			show, [self.batteryLowSlider], "barra de batería baja",
			self._updateBatteryIntervalVisibility,
		)

	def _updateCpuHotVisibility(self, show: bool) -> None:
		"""Muestra u oculta los controles de umbral térmico e intervalo de CPU."""
		self._mostrarControlesDeAlerta(
			show, [self.cpuHotSlider, self.cpuHotIntervalEdit], "temperatura CPU",
		)

	def _updateGpuHotVisibility(self, show: bool) -> None:
		"""Muestra u oculta los controles de umbral térmico e intervalo de GPU."""
		self._mostrarControlesDeAlerta(
			show, [self.gpuHotSlider, self.gpuHotIntervalEdit], "temperatura GPU",
		)

	def _updateBluetoothLowVisibility(self, show: bool) -> None:
		"""Muestra u oculta los controles de umbral de batería baja e intervalo de Bluetooth."""
		self._mostrarControlesDeAlerta(
			show, [self.bluetoothLowSlider, self.bluetoothLowIntervalEdit], "Bluetooth baja",
		)

	def _updateDiskHealthVisibility(self, show: bool) -> None:
		"""Muestra u oculta los controles de porcentaje de desgaste e intervalo de salud de disco."""
		self._mostrarControlesDeAlerta(
			show, [self.diskWearSlider, self.diskHealthIntervalEdit], "desgaste de disco",
		)

	def _updateDiskHotVisibility(self, show: bool) -> None:
		"""Muestra u oculta los controles de temperatura límite e intervalo térmico de disco."""
		self._mostrarControlesDeAlerta(
			show, [self.diskHotSlider, self.diskHotIntervalEdit], "temperatura de disco",
		)

	def onAlertBatteryFullChange(self, evt: wx.CommandEvent) -> None:
		"""Actualiza la visibilidad de los controles de umbral de batería cargada."""
		self._updateBatteryFullVisibility(self.alertBatteryFullCheckbox.GetValue())
		evt.Skip()

	def onAlertBatteryLowChange(self, evt: wx.CommandEvent) -> None:
		"""Actualiza la visibilidad de los controles de umbral de batería baja."""
		self._updateBatteryLowVisibility(self.alertBatteryLowCheckbox.GetValue())
		evt.Skip()

	def onAlertCpuHotChange(self, evt: wx.CommandEvent) -> None:
		"""Actualiza la visibilidad de los controles de umbral de sobrecalentamiento de CPU."""
		self._updateCpuHotVisibility(self.alertCpuHotCheckbox.GetValue())
		evt.Skip()

	def onAlertGpuHotChange(self, evt: wx.CommandEvent) -> None:
		"""Actualiza la visibilidad de los controles de umbral de sobrecalentamiento de GPU."""
		self._updateGpuHotVisibility(self.alertGpuHotCheckbox.GetValue())
		evt.Skip()

	def onAlertBluetoothLowChange(self, evt: wx.CommandEvent) -> None:
		"""Actualiza la visibilidad de los controles de umbral de batería Bluetooth baja."""
		self._updateBluetoothLowVisibility(self.alertBluetoothLowCheckbox.GetValue())
		evt.Skip()

	def onAlertDiskHealthChange(self, evt: wx.CommandEvent) -> None:
		"""Actualiza la visibilidad de los controles de umbral de desgaste de disco."""
		self._updateDiskHealthVisibility(self.alertDiskHealthCheckbox.GetValue())
		evt.Skip()

	def onAlertDiskHotChange(self, evt: wx.CommandEvent) -> None:
		"""Actualiza la visibilidad de los controles de umbral de temperatura de disco."""
		self._updateDiskHotVisibility(self.alertDiskHotCheckbox.GetValue())
		evt.Skip()

	def onPanelActivated(self) -> None:
		"""Sincroniza la visibilidad de los controles condicionales al activar el panel."""
		super().onPanelActivated()
		self._syncAllThresholdsVisibility()

	def onCheckConflicts(self, evt: wx.CommandEvent) -> None:
		"""Botón "Comprobar conflictos": muestra el resultado en un cuadro de mensaje.

		Busca entre los complementos que NVDA tiene cargados el de Monitor, y le
		pide la auditoría. Después presenta dos listas: los atajos de teclado que
		chocan con otro complemento, y las advertencias de compatibilidad. Si no
		hay nada, lo dice también.
		"""
		plugin = None
		for p in getattr(globalPluginHandler, "runningPlugins", set()):
			if p.__class__.__module__.endswith("monitoreoSistema"):
				plugin = p
				break
		if plugin and hasattr(plugin, "auditConflicts"):
			conflicts, warnings = plugin.auditConflicts()
			if not conflicts and not warnings:
				messageBox(
					_("No se han detectado conflictos de atajos de teclado ni complementos incompatibles activos en este sistema."),
					_("Auditoría de conflictos - Monitoreo del Sistema"),
					wx.OK | wx.ICON_INFORMATION,
					parent=self,
				)
			else:
				lines = []
				if conflicts:
					lines.append(_("COLISIONES DIRECTAS DE ATAJOS:"))
					for c in conflicts:
						lines.append(f"• {c}")
				if warnings:
					if lines:
						lines.append("")
					lines.append(_("ADVERTENCIAS DE COMPATIBILIDAD:"))
					for w in warnings:
						lines.append(f"• {w}")
				lines.append("")
				lines.append(_("Nota: Los detalles completos también se han registrado en el archivo de log de NVDA."))
				messageBox(
					"\n".join(lines),
					_("Auditoría de conflictos - Monitoreo del Sistema"),
					wx.OK | wx.ICON_WARNING,
					parent=self,
				)
		else:
			messageBox(
				_("No se pudo obtener la instancia activa de Monitoreo del Sistema."),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
				parent=self,
			)

	def onSave(self) -> None:
		"""Botón Aceptar de las preferencias: guarda todas las opciones del panel.

		Copia a la configuración de NVDA la unidad de temperatura y, de cada aviso,
		si está encendido, a partir de qué valor avisa y cada cuántos minutos. Al
		final le pone al complemento la marca de comprobación inmediata, para que
		los avisos se revisen con los valores nuevos sin esperar a que venza el
		intervalo anterior.
		"""
		try:
			if "monitoreoSistema" not in config.conf or not isinstance(config.conf["monitoreoSistema"], dict):
				config.conf["monitoreoSistema"] = {}
			selection = self.gpuTempUnitList.GetSelection()
			if selection == wx.NOT_FOUND:
				selection = 0
			config.conf["monitoreoSistema"]["gpuTempUnit"] = self._gpuTempUnitValues[selection]
			config.conf["monitoreoSistema"]["alertBatteryFull"] = self.alertBatteryFullCheckbox.GetValue()
			config.conf["monitoreoSistema"]["alertBatteryFullThreshold"] = self.batteryFullSlider.GetValue()
			config.conf["monitoreoSistema"]["alertBatteryLow"] = self.alertBatteryLowCheckbox.GetValue()
			config.conf["monitoreoSistema"]["alertBatteryLowThreshold"] = self.batteryLowSlider.GetValue()
			config.conf["monitoreoSistema"]["alertBatteryInterval"] = self.batteryIntervalEdit.GetValue()
			config.conf["monitoreoSistema"]["alertCpuHot"] = self.alertCpuHotCheckbox.GetValue()
			config.conf["monitoreoSistema"]["alertCpuHotThreshold"] = self.cpuHotSlider.GetValue()
			config.conf["monitoreoSistema"]["alertCpuHotInterval"] = self.cpuHotIntervalEdit.GetValue()
			config.conf["monitoreoSistema"]["alertGpuHot"] = self.alertGpuHotCheckbox.GetValue()
			config.conf["monitoreoSistema"]["alertGpuHotThreshold"] = self.gpuHotSlider.GetValue()
			config.conf["monitoreoSistema"]["alertGpuHotInterval"] = self.gpuHotIntervalEdit.GetValue()
			config.conf["monitoreoSistema"]["alertBluetoothLow"] = self.alertBluetoothLowCheckbox.GetValue()
			config.conf["monitoreoSistema"]["alertBluetoothLowThreshold"] = self.bluetoothLowSlider.GetValue()
			config.conf["monitoreoSistema"]["alertBluetoothLowInterval"] = self.bluetoothLowIntervalEdit.GetValue()
			config.conf["monitoreoSistema"]["alertWlan"] = self.alertWlanCheckbox.GetValue()
			config.conf["monitoreoSistema"]["alertWlanSignalChange"] = self.alertWlanSignalChangeCheckbox.GetValue()
			config.conf["monitoreoSistema"]["alertDiskHealth"] = self.alertDiskHealthCheckbox.GetValue()
			config.conf["monitoreoSistema"]["alertDiskWearThreshold"] = self.diskWearSlider.GetValue()
			config.conf["monitoreoSistema"]["alertDiskHealthInterval"] = self.diskHealthIntervalEdit.GetValue()
			config.conf["monitoreoSistema"]["alertDiskHot"] = self.alertDiskHotCheckbox.GetValue()
			config.conf["monitoreoSistema"]["alertDiskHotThreshold"] = self.diskHotSlider.GetValue()
			config.conf["monitoreoSistema"]["alertDiskHotInterval"] = self.diskHotIntervalEdit.GetValue()
			log.info(
				f"MonitorSistema: Opciones guardadas -> Batería Llena: {self.alertBatteryFullCheckbox.GetValue()} ({self.batteryFullSlider.GetValue()}%), "
				f"Batería Baja: {self.alertBatteryLowCheckbox.GetValue()} ({self.batteryLowSlider.GetValue()}%), "
				f"Intervalo Batería: {self.batteryIntervalEdit.GetValue()} min, "
				f"CPU Caliente: {self.alertCpuHotCheckbox.GetValue()} ({self.cpuHotSlider.GetValue()} °C, cada {self.cpuHotIntervalEdit.GetValue()} min), "
				f"GPU Caliente: {self.alertGpuHotCheckbox.GetValue()} ({self.gpuHotSlider.GetValue()} °C, cada {self.gpuHotIntervalEdit.GetValue()} min), "
				f"Bluetooth Bajo: {self.alertBluetoothLowCheckbox.GetValue()} ({self.bluetoothLowSlider.GetValue()}%, cada {self.bluetoothLowIntervalEdit.GetValue()} min), "
				f"Alerta Wi-Fi: {self.alertWlanCheckbox.GetValue()}, Señal Wi-Fi: {self.alertWlanSignalChangeCheckbox.GetValue()}, "
				f"Salud Discos: {self.alertDiskHealthCheckbox.GetValue()} ({self.diskWearSlider.GetValue()}% desgaste SSD, cada {self.diskHealthIntervalEdit.GetValue()} min), "
				f"Disco Caliente: {self.alertDiskHotCheckbox.GetValue()} ({self.diskHotSlider.GetValue()} °C, cada {self.diskHotIntervalEdit.GetValue()} min)"
			)
			plugin = None
			for p in getattr(globalPluginHandler, "runningPlugins", set()):
				if p.__class__.__module__.endswith("monitoreoSistema"):
					plugin = p
					break
			if plugin:
				plugin._forceAlertsCheck = True
		except Exception as e:
			log.error(f"MonitorSistema: Error guardando opciones en el panel: {e}", exc_info=True)


@functools.lru_cache(maxsize=1)
def getWinVer() -> str:
	"""Devuelve la versión detallada del sistema operativo Windows y su compilación."""
	try:
		currentWinVer = winVersion.getWinVer() if hasattr(winVersion, "getWinVer") else None
	except Exception:
		currentWinVer = None
	if not currentWinVer:
		return _("Versión de Windows no disponible")
	arch = getattr(currentWinVer, "processorArchitecture", "")
	winverName = getattr(currentWinVer, "releaseName", "Windows")
	if getattr(currentWinVer, "productType", "workstation") != "workstation":
		winverName = f"Windows Server {str(winverName).rpartition(' ')[-1]}"
	revision = getattr(currentWinVer, "revision", None)
	if revision is None:
		try:
			with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
				revision = winreg.QueryValueEx(key, "UBR")[0]
		except Exception:
			revision = None
	build = getattr(currentWinVer, "build", "")
	if revision is not None:
		buildRevision = f"{build}.{revision}"
	else:
		buildRevision = str(build)
	return _("{name} ({arch}) compilación {build}").format(name=winverName, arch=arch, build=buildRevision)


class PDH_FMT_COUNTERVALUE(Structure):
	"""Estructura para valores numéricos formateados devueltos por contadores PDH."""
	class _U(Union):
		"""Unión C para valores enteros, coma flotante o cadenas de texto devueltos por PDH."""
		_fields_ = [
			("longValue", c_long),
			("doubleValue", c_double),
			("largeValue", c_longlong),
			("AnsiStringValue", c_char_p),
			("WideStringValue", c_wchar_p),
		]
	_anonymous_ = ("u",)
	_fields_ = [
		("CStatus", wintypes.DWORD),
		("u", _U),
	]


# Velocidad maxima (turbo) que alcanza cada procesador conocido, en gigahercios.
#
# Cuando el nombre encaja con varias entradas gana la mas concreta, es decir
# la mas larga: un "Ryzen 9 7900X3D" encaja con "7900" y con "7900x3d", y se
# queda con la segunda. Por eso el orden de la lista ya no cambia el resultado
# y se puede escribir en el apartado que corresponda.
#
# Para anadir un procesador nuevo basta con escribir una linea mas en su
# apartado, sin tocar nada de codigo.
VELOCIDAD_MAXIMA_CONOCIDA = [
	# AMD Ryzen 9
	(("9950x", "9900x",), 5.70),
	(("7950x3d", "7950x",), 5.70),
	(("7900x3d", "7900x",), 5.60),
	(("7900", "7945hx", "7945h",), 5.40),
	(("7940hs", "7940hx",), 5.20),
	(("5950x",), 4.90),
	(("5900x", "5900hx", "5900hs",), 4.80),
	(("3950x", "3900xt",), 4.70),
	(("3900x",), 4.60),
	# AMD Ryzen 7
	(("9800x3d", "9700x",), 5.50),
	(("7800x3d",), 5.00),
	(("7700x",), 5.40),
	(("7700",), 5.30),
	(("7745hx", "7735hs", "7735u",), 4.75),
	(("6800h", "6800u",), 4.70),
	(("5800x3d",), 4.50),
	(("5800x",), 4.70),
	(("5800h", "5800u", "5850u",), 4.40),
	(("5700x3d", "5700x", "5700g",), 4.60),
	(("5700u",), 4.30),
	(("4800h", "4800u",), 4.20),
	(("4700u", "4750u",), 4.10),
	(("3800x", "3700x",), 4.50),
	# AMD Ryzen 5
	(("9600x",), 5.40),
	(("7600x",), 5.30),
	(("7600",), 5.10),
	(("7640hs", "7535hs", "7535u",), 4.90),
	(("7530u",), 4.50),
	(("6600h", "6600u",), 4.50),
	(("5600x",), 4.60),
	(("5600g", "5600h",), 4.40),
	(("5600u", "5650u",), 4.20),
	(("5500u",), 4.00),
	(("4650u", "4600u", "4600h", "4500u",), 4.00),
	(("3600x", "3600xt",), 4.40),
	(("3600",), 4.20),
	# AMD Ryzen 3
	(("5300u", "4300u",), 3.80),
	(("3300x",), 4.30),
	(("3100",), 3.90),
	# Intel Core 14th / 13th / 12th / 11th / 10th Gen & Core Ultra
	(("14900k", "14900ks",), 6.00),
	(("14900hx", "14700k", "285k",), 5.80),
	(("14700hx", "14600k",), 5.50),
	(("13900k", "13900ks",), 5.80),
	(("13900h", "13900hx", "13700k",), 5.40),
	(("13700h", "13700hx", "13600k",), 5.00),
	(("13500h", "13400",), 4.70),
	(("12900k", "12900h",), 5.20),
	(("12700k", "12700h",), 5.00),
	(("12600k", "12500h",), 4.90),
	(("11900k", "11900h",), 5.30),
	(("11800h", "11700k",), 5.00),
	(("1165g7",), 4.70),
	(("1135g7", "11400h",), 4.50),
	(("10750h", "10700k",), 5.00),
	(("10500h", "10400",), 4.50),
	(("185h", "165h",), 5.10),
	(("155h", "125h",), 4.80),
]

# Constantes y estructuras de C que Windows exige para enumerar los
# dispositivos Bluetooth. Son declaraciones puras, sin efecto ninguno: estaban
# escritas dentro de la funcion que las usa, que por eso ocupaba 382 lineas.
# Aqui no se carga ninguna biblioteca del sistema; eso sigue haciendose dentro,
# protegido, porque puede fallar en un equipo sin Bluetooth.

CR_SUCCESS = 0

MAX_DEVICE_ID_LEN = 256

_DIGCF_ALLCLASSES = 0x00000004

DIGCF_PRESENT = 0x00000002

_DN_DEVICE_DISCONNECTED = 0x02000000

class GUID(Structure):
	"""Identificador único universal (GUID) para enumeración de dispositivos SetupAPI."""
	_fields_ = [
		("Data1", wintypes.DWORD),
		("Data2", ctypes.c_ushort),
		("Data3", ctypes.c_ushort),
		("Data4", ctypes.c_ubyte * 8)
	]
	def __init__(self, guid_str):
		super().__init__()
		import uuid
		u = uuid.UUID(guid_str)
		self.Data1 = u.time_low
		self.Data2 = u.time_mid
		self.Data3 = u.time_hi_version
		for i, b in enumerate(u.bytes[8:]):
			self.Data4[i] = b

class DEVPROPKEY(Structure):
	"""Clave de propiedad uniforme de dispositivo en la API de configuración de Windows."""
	_fields_ = [("fmtid", GUID), ("pid", wintypes.ULONG)]

class SP_DEVINFO_DATA(Structure):
	"""Estructura de información de instancia de dispositivo devuelta por SetupAPI."""
	_fields_ = [("cbSize", wintypes.DWORD), ("ClassGuid", GUID), ("DevInst", wintypes.DWORD), ("Reserved", POINTER(wintypes.ULONG))]

class BLUETOOTH_ADDRESS(Structure):
	"""Dirección física de 64 bits para adaptadores y dispositivos de radio Bluetooth."""
	_fields_ = [("ullLong", ctypes.c_ulonglong)]

class SYSTEMTIME(Structure):
	"""Estructura de fecha y hora del sistema en la API nativa de Windows."""
	_fields_ = [
		("wYear", wintypes.WORD), ("wMonth", wintypes.WORD), ("wDayOfWeek", wintypes.WORD),
		("wDay", wintypes.WORD), ("wHour", wintypes.WORD), ("wMinute", wintypes.WORD),
		("wSecond", wintypes.WORD), ("wMilliseconds", wintypes.WORD)
	]

class BLUETOOTH_DEVICE_INFO(Structure):
	"""Información detallada y estado de emparejamiento de un dispositivo Bluetooth."""
	_fields_ = [
		("dwSize", wintypes.DWORD),
		("Address", BLUETOOTH_ADDRESS),
		("ulClassofDevice", wintypes.ULONG),
		("fConnected", wintypes.BOOL),
		("fRemembered", wintypes.BOOL),
		("fAuthenticated", wintypes.BOOL),
		("stLastSeen", SYSTEMTIME),
		("stLastUsed", SYSTEMTIME),
		("szName", wintypes.WCHAR * 248),
	]
	def __init__(self):
		super().__init__()
		self.dwSize = ctypes.sizeof(self)

class BLUETOOTH_FIND_RADIO_PARAMS(Structure):
	"""Parámetros de búsqueda de adaptadores de radio Bluetooth en el sistema."""
	_fields_ = [("dwSize", wintypes.DWORD)]
	def __init__(self):
		super().__init__()
		self.dwSize = ctypes.sizeof(self)

class BLUETOOTH_DEVICE_SEARCH_PARAMS(Structure):
	"""Criterios de filtro para la enumeración de dispositivos Bluetooth."""
	_fields_ = [
		("dwSize", wintypes.DWORD),
		("fReturnAuthenticated", wintypes.BOOL),
		("fReturnRemembered", wintypes.BOOL),
		("fReturnUnknown", wintypes.BOOL),
		("fReturnConnected", wintypes.BOOL),
		("fIssueInquiry", wintypes.BOOL),
		("cTimeoutMultiplier", ctypes.c_ubyte),
		("hRadio", wintypes.HANDLE),
	]
	def __init__(self, hRadio):
		super().__init__()
		self.dwSize = ctypes.sizeof(self)
		self.fReturnAuthenticated = True
		self.fReturnRemembered = True
		self.fReturnUnknown = True
		self.fReturnConnected = True
		self.fIssueInquiry = False
		self.cTimeoutMultiplier = 0
		self.hRadio = hRadio

# Claves de propiedades DEVPROPKEY y lógica de consulta de batería Bluetooth.
# Desarrollado y ampliado por Daliana sobre la referencia inicial de BlueToothBatteryReport (por Cary-rowen y colaboradores),
# incorporando matriz de 4 claves (SetupAPI y bthprops.cpl), soporte de texto, alertas periódicas y ejecución asíncrona.
BATTERY_KEYS = [
	("DEVPKEY_Bluetooth_Battery_2", DEVPROPKEY(GUID("{104EA319-6EE2-4701-BD47-8DDBF425BBE5}"), 2)),
	("DEVPKEY_Device_BatteryReport_2", DEVPROPKEY(GUID("{1032A556-D29E-453E-A59E-9A5EE94AC6EA}"), 2)),
	("DEVPKEY_Bluetooth_Battery_1", DEVPROPKEY(GUID("{104EA319-6EE2-4701-BD47-8DDBF425BBE5}"), 1)),
	("DEVPKEY_Device_BatteryReport_1", DEVPROPKEY(GUID("{1032A556-D29E-453E-A59E-9A5EE94AC6EA}"), 1)),
]

DEVPKEY_NAME = DEVPROPKEY(GUID("{B725F130-47EF-101A-A5F1-02608C9EEBAC}"), 10)

DEVPKEY_Device_FriendlyName = DEVPROPKEY(GUID("{A45C254E-DF1C-4EFD-8020-67D146A850E0}"), 14)

DEVPKEY_Device_DeviceDesc = DEVPROPKEY(GUID("{A45C254E-DF1C-4EFD-8020-67D146A850E0}"), 2)

DEVPKEY_Device_DevNodeStatus = DEVPROPKEY(GUID("{4340A6C5-93FA-4706-972C-7B648008A5A7}"), 2)

DEVPKEY_Device_IsConnected = DEVPROPKEY(GUID("{83DA6326-97A6-4088-9453-A1923F573B29}"), 15)

def _cargarApiDeDispositivos():
	"""Carga las bibliotecas de Windows que enumeran los dispositivos.

	Devuelve las siete funciones que hacen falta, siempre en el mismo orden.
	Antes se cargaban en medio del trabajo, mezcladas con el.
	"""
	_cfgmgr32 = ctypes.WinDLL("cfgmgr32.dll")
	CM_Get_Device_ID = _cfgmgr32.CM_Get_Device_IDW
	CM_Get_Device_ID.argtypes = (wintypes.DWORD, ctypes.c_wchar_p, wintypes.ULONG, wintypes.ULONG)
	CM_Get_Device_ID.restype = wintypes.DWORD

	_CM_Get_DevNode_Property = _cfgmgr32.CM_Get_DevNode_PropertyW
	_CM_Get_DevNode_Property.argtypes = (wintypes.DWORD, c_void_p, c_void_p, c_void_p, c_void_p, wintypes.ULONG)
	_CM_Get_DevNode_Property.restype = wintypes.DWORD

	CM_Get_Parent = _cfgmgr32.CM_Get_Parent
	CM_Get_Parent.argtypes = (POINTER(wintypes.DWORD), wintypes.DWORD, wintypes.ULONG)
	CM_Get_Parent.restype = wintypes.DWORD

	_setupapi = ctypes.WinDLL("setupapi.dll")
	SetupDiGetClassDevs = _setupapi.SetupDiGetClassDevsW
	SetupDiGetClassDevs.argtypes = (c_void_p, wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD)
	SetupDiGetClassDevs.restype = wintypes.HANDLE

	SetupDiEnumDeviceInfo = _setupapi.SetupDiEnumDeviceInfo
	SetupDiEnumDeviceInfo.argtypes = (wintypes.HANDLE, wintypes.DWORD, POINTER(SP_DEVINFO_DATA))
	SetupDiEnumDeviceInfo.restype = wintypes.BOOL

	SetupDiDestroyDeviceInfoList = _setupapi.SetupDiDestroyDeviceInfoList
	SetupDiDestroyDeviceInfoList.argtypes = (wintypes.HANDLE,)
	SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

	SetupDiGetDevicePropertyW = _setupapi.SetupDiGetDevicePropertyW
	SetupDiGetDevicePropertyW.argtypes = (wintypes.HANDLE, POINTER(SP_DEVINFO_DATA), POINTER(DEVPROPKEY), POINTER(wintypes.ULONG), c_void_p, wintypes.DWORD, POINTER(wintypes.DWORD), wintypes.DWORD)
	SetupDiGetDevicePropertyW.restype = wintypes.BOOL
	return (CM_Get_Device_ID, _CM_Get_DevNode_Property, CM_Get_Parent,
		SetupDiGetClassDevs, SetupDiEnumDeviceInfo,
		SetupDiDestroyDeviceInfoList, SetupDiGetDevicePropertyW)


def _propiedadDeTexto(api, hdev, dev_data, pkey):
	"""Lee una propiedad de texto de un dispositivo; None si no la tiene."""
	SetupDiGetDevicePropertyW = api[6]
	try:
		ptype = wintypes.ULONG()
		rsize = wintypes.DWORD()
		SetupDiGetDevicePropertyW(hdev, ctypes.byref(dev_data), ctypes.byref(pkey), ctypes.byref(ptype), None, 0, ctypes.byref(rsize), 0)
		_MAX_PROP_CHARS = 8192
		if not rsize.value or rsize.value > (_MAX_PROP_CHARS * 2):
			if rsize.value > (_MAX_PROP_CHARS * 2):
				log.warning(f"MonitorSistema: propiedad de texto sospechosa ({rsize.value} bytes), se ignora.")
			return None
		bufChars = min(rsize.value // 2 + 1, _MAX_PROP_CHARS)
		buf = ctypes.create_unicode_buffer(bufChars)
		reqSize = min(int(rsize.value), (_MAX_PROP_CHARS - 1) * 2)
		if SetupDiGetDevicePropertyW(hdev, ctypes.byref(dev_data), ctypes.byref(pkey), ctypes.byref(ptype), ctypes.byref(buf), reqSize, ctypes.byref(rsize), 0):
			val = buf.value or ""
			return val[:_MAX_PROP_CHARS] if len(val) > _MAX_PROP_CHARS else val
	except Exception as err:
		log.debug(f"MonitorSistema: Error leyendo una propiedad de texto: {err}")
	return None

def _nombreDeNodo(api, dev_inst):
	"""Nombre legible de un nodo, probando tres propiedades distintas."""
	_CM_Get_DevNode_Property = api[1]
	for pk in (DEVPKEY_Device_FriendlyName, DEVPKEY_NAME, DEVPKEY_Device_DeviceDesc):
		try:
			buf = (ctypes.c_ubyte * 512)()
			sz = wintypes.ULONG(len(buf))
			pt = wintypes.ULONG()
			if _CM_Get_DevNode_Property(dev_inst, ctypes.byref(pk), ctypes.byref(pt), buf, ctypes.byref(sz), 0) == CR_SUCCESS:
				if pt.value == 18:
					val = ctypes.wstring_at(buf)
					if val and val.strip():
						return val.strip()
		except Exception as err:
			log.debug(f"MonitorSistema: Error en _nombreDeNodo(api, {dev_inst}): {err}")
	return None

def _estadoDeNodo(api, dev_inst):
	"""Palabra de estado que Windows guarda de un nodo; None si no se puede leer."""
	_CM_Get_DevNode_Property = api[1]
	try:
		val = wintypes.ULONG()
		sz = wintypes.ULONG(ctypes.sizeof(val))
		ptype = wintypes.ULONG()
		if _CM_Get_DevNode_Property(dev_inst, ctypes.byref(DEVPKEY_Device_DevNodeStatus), ctypes.byref(ptype), ctypes.byref(val), ctypes.byref(sz), 0) == CR_SUCCESS:
			if ptype.value == 7:
				return int(val.value)
	except Exception:
		pass
	return None

def _dispositivosConBateria(api):
	"""Recorre todos los dispositivos y se queda con los que informan de bateria.

	Devuelve la lista de candidatos y dos diccionarios con el nombre y el nodo de
	cada aparato raiz, o None si Windows no deja ni empezar.
	"""
	(CM_Get_Device_ID, _, _,
		SetupDiGetClassDevs, SetupDiEnumDeviceInfo,
		SetupDiDestroyDeviceInfoList, _) = api
	flags = DIGCF_PRESENT | _DIGCF_ALLCLASSES
	hdev = SetupDiGetClassDevs(None, None, None, flags)
	if not hdev or hdev == wintypes.HANDLE(-1).value:
		log.error("MonitorSistema: SetupDiGetClassDevs devolvió un manejador inválido.")
		# None avisa a quien llama de que no se pudo ni empezar; devolver una lista
		# vacia aqui reventaria al repartirla en tres valores.
		return None

	root_names = {}
	root_dev_insts = {}
	candidates = []
	try:
		index = 0
		while True:
			dev_data = SP_DEVINFO_DATA()
			dev_data.cbSize = ctypes.sizeof(dev_data)
			if not SetupDiEnumDeviceInfo(hdev, index, ctypes.byref(dev_data)):
				break
			index += 1

			buf = ctypes.create_unicode_buffer(MAX_DEVICE_ID_LEN + 1)
			if CM_Get_Device_ID(dev_data.DevInst, buf, len(buf), 0) != CR_SUCCESS:
				continue
			inst_id = buf.value
			upper_id = inst_id.upper()

			if not (upper_id.startswith(("BTHENUM\\", "BTHLE\\", "BTHLEDEVICE\\")) or "BTH" in upper_id or "BLUETOOTH" in upper_id):
				continue

			name = (_propiedadDeTexto(api, hdev, dev_data, DEVPKEY_Device_FriendlyName)
					or _propiedadDeTexto(api, hdev, dev_data, DEVPKEY_NAME)
					or _propiedadDeTexto(api, hdev, dev_data, DEVPKEY_Device_DeviceDesc)
					or inst_id)

			addr = _direccionDelDispositivo(upper_id)

			dev_inst = int(dev_data.DevInst)

			if (upper_id.startswith(("BTHENUM\\DEV_", "BTHLE\\DEV_")) or "DEV_" in upper_id) and addr:
				if name and not name.upper().startswith("BTH"):
					root_names[addr] = name
				root_dev_insts[addr] = dev_inst
			elif addr and addr not in root_names and name and not name.upper().startswith("BTH"):
				root_names[addr] = name

			_anotarSiTieneBateria(api, hdev, dev_data, dev_inst, inst_id, name, addr, candidates)
	finally:
		SetupDiDestroyDeviceInfoList(hdev)
	return candidates, root_names, root_dev_insts

def _direccionDelDispositivo(upper_id):
	"""Saca la direccion Bluetooth de doce digitos del identificador de Windows.

	Los identificadores llegan en varios formatos segun el tipo de aparato, asi
	que se prueban cinco maneras en orden, de la mas fiable a la mas generica.
	"""
	m = (re.search(r"DEV_([0-9A-F]{12})", upper_id)
		 or re.search(r"&0&([0-9A-F]{12})_C", upper_id)
		 or re.search(r"&0&([0-9A-F]{12})", upper_id)
		 or re.search(r"_([0-9A-F]{12})\\[^\\]+$", upper_id)
		 or re.search(r"([0-9A-F]{12})", upper_id))
	return m.group(1) if m else None

def _anotarSiTieneBateria(api, hdev, dev_data, dev_inst, inst_id, name, addr, candidates):
	"""Si el aparato informa de su nivel de bateria, lo apunta en 'candidates'.

	Se prueban varias propiedades de Windows porque cada tipo de aparato guarda el
	nivel en un sitio distinto, y el valor puede venir como numero o como texto.
	"""
	(_, _CM_Get_DevNode_Property, CM_Get_Parent, *_) = api
	for _, pkey in BATTERY_KEYS:
		try:
			b_buf = (ctypes.c_ubyte * 64)()
			b_size = wintypes.ULONG(len(b_buf))
			prop_type = wintypes.ULONG()
			res = _CM_Get_DevNode_Property(dev_inst, ctypes.byref(pkey), ctypes.byref(prop_type), b_buf, ctypes.byref(b_size), 0)
			if res == CR_SUCCESS:
				val = None
				if prop_type.value == 3: # BYTE
					val = b_buf[0]
				elif prop_type.value == 7: # UINT32
					val = int.from_bytes(bytes(b_buf[:4]), 'little')
				elif prop_type.value == 18: # STRING
					try:
						s = ctypes.wstring_at(b_buf)
						dig = ''.join(c for c in s if c.isdigit())
						if dig: val = int(dig)
					except Exception:
						pass
				if val is not None and 0 <= val <= 100:
					parent_name = None
					parent_inst = wintypes.DWORD()
					if CM_Get_Parent(ctypes.byref(parent_inst), dev_inst, 0) == CR_SUCCESS:
						parent_name = _nombreDeNodo(api, parent_inst.value)
					candidates.append({
						"name": name,
						"parent_name": parent_name,
						"battery": val,
						"inst_id": inst_id,
						"dev_inst": dev_inst,
						"addr": addr
					})
					# Este hallazgo puede repetirse en cada escaneo aunque el aparato siga
					# desconectado. Es diagnóstico, no un evento para el registro normal.
					log.debug(f"MonitorSistema: Nodo Bluetooth con batería detectado: '{name}' (batería={val}%, addr={addr}, id={inst_id})")
					break
		except Exception as prop_err:
			log.debug(f"MonitorSistema: Error consultando batería en {inst_id}: {prop_err}")



def _soloLosConectados(api, candidates, estados_clasicos, root_names, root_dev_insts):
	"""De los candidatos, deja solo los que estan conectados de verdad.

	Se comprueba por tres vias porque ningun metodo vale para todos los aparatos.
	"""
	_CM_Get_DevNode_Property = api[1]
	results = []
	seen = set()
	for cand in candidates:
		addr = cand["addr"]
		display_name = root_names.get(addr) or cand["parent_name"] or cand["name"]

		# 1. Chequeo primario para Bluetooth clásico: fConnected de bthprops.cpl
		is_connected = None
		if addr and addr in estados_clasicos:
			is_connected = estados_clasicos[addr]
			log.debug(f"MonitorSistema: Dispositivo '{display_name}' ({addr}) estado vía bthprops: conectado={is_connected}")

		# 2. Chequeo secundario: estado de DevNode (DevNodeStatus)
		if is_connected is None:
			check_nodes = []
			if addr and addr in root_dev_insts:
				check_nodes.append(root_dev_insts[addr])
			if cand["dev_inst"] not in check_nodes:
				check_nodes.append(cand["dev_inst"])

			found_status = False
			for d_inst in check_nodes:
				st = _estadoDeNodo(api, d_inst)
				if st is not None:
					found_status = True
					if st & _DN_DEVICE_DISCONNECTED:
						is_connected = False
						break
					else:
						is_connected = True

			# 3. Fallback adicional para BLE: DEVPKEY_Device_IsConnected
			if not found_status:
				try:
					c_buf = (ctypes.c_ubyte * 16)()
					c_sz = wintypes.ULONG(len(c_buf))
					c_pt = wintypes.ULONG()
					if _CM_Get_DevNode_Property(cand["dev_inst"], ctypes.byref(DEVPKEY_Device_IsConnected), ctypes.byref(c_pt), c_buf, ctypes.byref(c_sz), 0) == CR_SUCCESS:
						is_connected = bool(c_buf[0])
				except Exception:
					pass

			log.debug(f"MonitorSistema: Dispositivo '{display_name}' ({addr}) estado vía DevNodeStatus/PnP: conectado={is_connected}")

		if is_connected:
			key = addr or cand["inst_id"]
			if key not in seen:
				seen.add(key)
				if not addr and display_name in seen:
					continue
				seen.add(display_name)
				results.append({"name": display_name, "battery": cand["battery"]})
				log.info(f"MonitorSistema: Dispositivo conectado confirmado con batería: '{display_name}' al {cand['battery']}%")
		else:
			log.debug(f"MonitorSistema: Omitiendo '{display_name}' ({cand['inst_id']}): no conectado.")
	return results

def _estadosDeBluetoothClasico():
	"""Pregunta a Windows que dispositivos Bluetooth clasicos estan conectados.

	Devuelve un diccionario de direccion del aparato a si esta conectado. Si el
	equipo no tiene Bluetooth, o la biblioteca falla, devuelve un diccionario
	vacio y el resto del escaneo sigue por otras vias.
	"""
	estados = {}
	try:
		_bthprops = ctypes.windll["bthprops.cpl"]
		_BluetoothFindFirstRadio = _bthprops.BluetoothFindFirstRadio
		_BluetoothFindFirstRadio.argtypes = (POINTER(BLUETOOTH_FIND_RADIO_PARAMS), POINTER(wintypes.HANDLE))
		_BluetoothFindFirstRadio.restype = c_void_p

		_BluetoothFindNextRadio = _bthprops.BluetoothFindNextRadio
		_BluetoothFindNextRadio.argtypes = (c_void_p, POINTER(wintypes.HANDLE))
		_BluetoothFindNextRadio.restype = wintypes.BOOL

		_BluetoothFindRadioClose = _bthprops.BluetoothFindRadioClose
		_BluetoothFindRadioClose.argtypes = (c_void_p,)
		_BluetoothFindRadioClose.restype = wintypes.BOOL

		_BluetoothFindFirstDevice = _bthprops.BluetoothFindFirstDevice
		_BluetoothFindFirstDevice.argtypes = (POINTER(BLUETOOTH_DEVICE_SEARCH_PARAMS), POINTER(BLUETOOTH_DEVICE_INFO))
		_BluetoothFindFirstDevice.restype = c_void_p

		_BluetoothFindNextDevice = _bthprops.BluetoothFindNextDevice
		_BluetoothFindNextDevice.argtypes = (c_void_p, POINTER(BLUETOOTH_DEVICE_INFO))
		_BluetoothFindNextDevice.restype = wintypes.BOOL

		_BluetoothFindDeviceClose = _bthprops.BluetoothFindDeviceClose
		_BluetoothFindDeviceClose.argtypes = (c_void_p,)
		_BluetoothFindDeviceClose.restype = wintypes.BOOL

		radio_params = BLUETOOTH_FIND_RADIO_PARAMS()
		h_radio = wintypes.HANDLE()
		h_find_radio = _BluetoothFindFirstRadio(ctypes.byref(radio_params), ctypes.byref(h_radio))
		if h_find_radio:
			try:
				while True:
					search_params = BLUETOOTH_DEVICE_SEARCH_PARAMS(h_radio)
					dev_info = BLUETOOTH_DEVICE_INFO()
					h_find_dev = _BluetoothFindFirstDevice(ctypes.byref(search_params), ctypes.byref(dev_info))
					if h_find_dev:
						try:
							while True:
								addr_hex = f"{dev_info.Address.ullLong:012X}"
								estados[addr_hex] = bool(dev_info.fConnected)
								log.debug(f"MonitorSistema: Classic BT dev '{dev_info.szName}' ({addr_hex}) fConnected={bool(dev_info.fConnected)}")
								if not _BluetoothFindNextDevice(h_find_dev, ctypes.byref(dev_info)):
									break
						finally:
							_BluetoothFindDeviceClose(h_find_dev)
					if getattr(h_radio, "value", None):
						ctypes.windll.kernel32.CloseHandle(h_radio)
						h_radio = wintypes.HANDLE()
					if not _BluetoothFindNextRadio(h_find_radio, ctypes.byref(h_radio)):
						break
			finally:
				if getattr(h_radio, "value", None):
					ctypes.windll.kernel32.CloseHandle(h_radio)
				_BluetoothFindRadioClose(h_find_radio)
	except Exception as bth_err:
		log.debug(f"MonitorSistema: Error consultando bthprops.cpl: {bth_err}")
	return estados


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	"""Plugin global de NVDA para supervisión integral de hardware, red, discos y batería."""
	scriptCategory = _("Monitoreo del sistema")

	def __init__(self):
		"""Arranca el complemento en cuanto NVDA lo carga.

		Deja preparados los contadores del procesador y de la tarjeta gráfica,
		añade el panel de opciones a las preferencias de NVDA y el submenú "Monitor
		del Sistema" al menú Herramientas. También pone a cero la memoria de las
		consultas que tardan (discos, procesos, red, batería y Bluetooth), para no
		lanzar dos veces la misma. Al final arranca los dos hilos de fondo: el que
		prepara el sistema y el que vigila los avisos.
		"""
		if getattr(getattr(globalVars, "appArgs", None), "secureMode", False):
			log.warning("Monitoreo del Sistema: NVDA en modo seguro. Se cancela la carga del complemento por seguridad.")
			raise globalPluginHandler.ActionCancelled()
		super().__init__()
		try:
			self._limpiarTemporalesViejos(maxAgeHours=1.0)
		except Exception:
			pass
		log.info("Monitoreo del Sistema: Inicializando complemento (v3.0.0)...")
		self._stateLock = threading.RLock()
		self._opLocks = {
			"diskHealth": threading.Lock(),
			"topProcesses": threading.Lock(),
			"netSpeed": threading.Lock(),
			"advBattery": threading.Lock(),
			"bluetooth": threading.Lock(),
			"diskAlert": threading.Lock(),
		}
		self._bgThreads: list[threading.Thread] = []
		self._cpuQuery = None
		self._cpuCounter = None
		self._client_handle = None
		self._negotiated_version = None
		self._wlanCallback = None
		self._lastWlanOpenAttempt = 0.0
		self._wlanSignalCache = None
		self._wlanSignalCacheTime = 0.0
		self._pendingWlanSignal = None
		self._pendingWlanSignalTime = 0.0
		self._alertCoalescer: list[str] = []
		self._alertCoalescerTime = 0.0
		self._diskAlertRunning = False
		self._gpuProviders: list[BaseGpuProvider] = getGpuProviders()
		NVDASettingsDialog.categoryClasses.append(MonitorSistemaSettingsPanel)

		# Submenú en el menú Herramientas de NVDA
		try:
			self._toolsMenu = gui.mainFrame.sysTrayIcon.toolsMenu
			self._subMenu = wx.Menu()
			self._itemConfig = self._subMenu.Append(
				wx.ID_ANY,
				_("&Configuración..."),
				_("Abre las opciones y alertas de Monitoreo del Sistema")
			)
			gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self._onMenuConfig, self._itemConfig)
			self._subMenuItem = self._toolsMenu.AppendSubMenu(
				self._subMenu,
				_("&Monitoreo del Sistema"),
				_("Opciones y configuración de Monitoreo del Sistema")
			)
			log.info("Monitoreo del Sistema: Submenú registrado en Herramientas exitosamente.")
		except Exception as e:
			log.error(f"Monitoreo del Sistema: No se pudo registrar el submenú en Herramientas: {e}", exc_info=True)
			self._subMenuItem = None
		self._lastDiskHealthResult = None
		self._diskHealthRunning = False
		self._copyDiskHealthOnFinish = False
		self._lastTopProcessesResult = None
		self._topProcessesRunning = False
		self._copyTopProcessesOnFinish = False
		self._lastNetSpeedResult = None
		self._netSpeedRunning = False
		self._copyNetSpeedOnFinish = False
		self._lastAdvBatteryResult = None
		self._advBatteryRunning = False
		self._copyAdvBatteryOnFinish = False
		self._lastBluetoothResult = None
		self._bluetoothRunning = False
		self._copyBluetoothOnFinish = False

		self._stopAlertsEvent = threading.Event()
		_startupThread = threading.Thread(target=self._startupBackgroundWorker, daemon=True)
		_alertsThread = threading.Thread(target=self._runAlertsLoop, daemon=True)
		with self._stateLock:
			self._bgThreads = [_startupThread, _alertsThread]
		_startupThread.start()
		_alertsThread.start()

	def _joinBackgroundThreads(self, timeout: float = 2.0) -> None:
		"""Espera a los hilos de fondo con límite para no bloquear la descarga."""
		try:
			with self._stateLock:
				threads = list(getattr(self, "_bgThreads", []) or [])
		except Exception:
			threads = []
		for t in threads:
			try:
				if t.is_alive():
					t.join(timeout=timeout)
			except Exception:
				pass

	def _tryStartOp(self, opName: str, flagName: str) -> bool:
		"""Single-flight: True si se puede iniciar la operación, False si ya está en curso."""
		try:
			lock = self._opLocks.get(opName)
			if lock is not None:
				with lock:
					if getattr(self, flagName, False):
						return False
					setattr(self, flagName, True)
					return True
			if getattr(self, flagName, False):
				return False
			setattr(self, flagName, True)
			return True
		except Exception:
			return bool(not getattr(self, flagName, False))

	def _finishOp(self, opName: str, flagName: str) -> None:
		"""Marca la operación como terminada (siempre bajo lock)."""
		try:
			lock = self._opLocks.get(opName)
			if lock is not None:
				with lock:
					setattr(self, flagName, False)
			else:
				setattr(self, flagName, False)
		except Exception:
			try:
				setattr(self, flagName, False)
			except Exception:
				pass

	def _startProgressBeeper(self, freq: int = 440, interval: float = 0.6) -> threading.Event:
		"""Inicia un hilo de pitidos periódicos para operaciones en segundo plano y devuelve el stop_event."""
		stop_event = threading.Event()
		def beeper():
			"""Bucle de emisión de tonos de progreso en segundo plano."""
			_beepAsync(freq, 40)
			while not stop_event.wait(interval):
				if hasattr(self, "_stopAlertsEvent") and self._stopAlertsEvent.is_set():
					break
				_beepAsync(freq, 40)
		threading.Thread(target=beeper, daemon=True).start()
		return stop_event

	def _startupBackgroundWorker(self):
		"""Prepara en segundo plano todo lo que tarda, para no frenar el arranque de NVDA.

		Deja listo el contador de velocidad del procesador, el de la tarjeta
		gráfica, y se apunta a los avisos de Windows sobre el Wi-Fi. Después espera
		tres segundos, el tiempo de que NVDA termine de cargar los demás
		complementos, y revisa si alguno choca con este; esa primera revisión solo
		se anota en el registro, sin molestar con ventanas.
		"""
		log.info(f"Monitoreo del Sistema: Iniciando worker de fondo (CPU núcleos físicos={psutil.cpu_count(logical=False)}, hilos lógicos={psutil.cpu_count(logical=True)})...")
		try:
			self._initCpuQuery()
		except Exception as e:
			log.error(f"MonitorSistema: Error inicializando consulta de CPU: {e}", exc_info=True)

		try:
			with self._stateLock:
				providers = list(self._gpuProviders)
			for provider in providers:
				if hasattr(provider, "_initPdh"):
					provider._initPdh()
		except Exception as e:
			log.error(f"MonitorSistema: Error inicializando PDH de GPU: {e}", exc_info=True)

		self._ensureWlanHandle(force=True)

		# Auditoría de conflictos con otros complementos (tras breve espera para asegurar carga completa de NVDA)
		try:
			if hasattr(self, "_stopAlertsEvent") and self._stopAlertsEvent.wait(3.0):
				return
			if not getattr(self, "_stopAlertsEvent", threading.Event()).is_set():
				self._checkAddonConflicts(interactive=False)
		except Exception as e:
			log.error(f"MonitorSistema: Error durante la auditoría de conflictos: {e}", exc_info=True)

	def _ensureWlanHandle(self, force: bool = False) -> bool:
		"""Abre el manejador WLAN con reintento perezoso cada 60 s si es None.

		Retiene el callback en self._wlanCallback para que el GC no lo libere
		mientras Windows lo usa. Devuelve True si hay manejador válido.
		"""
		try:
			with self._stateLock:
				has_handle = self._client_handle is not None
			if has_handle:
				return True
		except Exception:
			pass
		if not wlanapiAvailable or notifyHandler is None:
			return False
		now = time.time()
		try:
			last = float(getattr(self, "_lastWlanOpenAttempt", 0.0) or 0.0)
		except (ValueError, TypeError):
			last = 0.0
		if not force and (now - last) < 60.0:
			return False
		self._lastWlanOpenAttempt = now
		try:
			version = wintypes.DWORD()
			handle = wintypes.HANDLE()
			if wlanapi.WlanOpenHandle(
				wlanapi.CLIENT_VERSION_WINDOWS_VISTA_OR_LATER,
				None,
				byref(version),
				byref(handle),
			) == 0:
				# Retener el callback vivo: si el objeto CFUNCTYPE se libera,
				# Windows llamaría a memoria liberada y NVDA se cerraría.
				self._wlanCallback = notifyHandler
				wlanapi.WlanRegisterNotification(
					handle,
					wlanapi.WLAN_NOTIFICATION_SOURCE_ACM,
					True,
					self._wlanCallback,
					None,
					None,
					None,
				)
				with self._stateLock:
					self._negotiated_version = version
					self._client_handle = handle
				log.info("MonitorSistema: Notificaciones WLAN registradas exitosamente.")
				return True
		except Exception as e:
			log.error(f"MonitorSistema: Error registrando notificaciones WLAN: {e}", exc_info=True)
		return False

	def _initCpuQuery(self):
		"""Prepara la lectura de la velocidad del procesador.

		Del registro de Windows saca la velocidad base y el nombre del procesador,
		y con el nombre averigua su velocidad máxima. Después abre un contador de
		rendimiento de Windows probando cuatro nombres distintos, porque no todos
		existen en todas las versiones, y se queda con el primero que funcione. Si
		ninguno funciona lo anota en el registro y el complemento sigue
		trabajando; simplemente no dirá la velocidad en tiempo real.
		"""
		# Si ya había una consulta abierta de una vez anterior (por ejemplo, al
		# reintentar tras una muestra fallida), hay que cerrarla antes de perder
		# su referencia; si no, esa consulta anterior queda abierta para siempre.
		try:
			with self._stateLock:
				consultaAnterior = getattr(self, "_cpuQuery", None)
				self._cpuQuery = None
				self._cpuCounter = None
		except Exception:
			consultaAnterior = None
		if consultaAnterior:
			try:
				ctypes.windll.pdh.PdhCloseQuery(consultaAnterior)
			except Exception:
				pass
		self._baseGhz = 2.10
		self._maxTurboGhz = 4.00
		self._lastCpuCollectTime = 0
		try:
			procName = ""
			try:
				with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
					mhz, _ = winreg.QueryValueEx(key, "~MHz")
					if mhz and mhz > 300:
						self._baseGhz = round(mhz / 1000.0, 2)
					try:
						procName, _ = winreg.QueryValueEx(key, "ProcessorNameString")
					except Exception:
						pass
			except Exception as e:
				log.debug(f"MonitorSistema: No se pudo leer CentralProcessor del registro: {e}")
				self._baseGhz = 2.10

			self._maxTurboGhz = self._resolveMaxTurbo(procName, self._baseGhz)
			log.info(f"MonitorSistema: CPU detectada='{procName}', Base={self._baseGhz} GHz, Max Turbo={self._maxTurboGhz} GHz")

			pdh = ctypes.windll.pdh
			pdh.PdhOpenQueryW.restype = wintypes.LONG
			pdh.PdhOpenQueryW.argtypes = [wintypes.LPCWSTR, c_void_p, POINTER(wintypes.HANDLE)]

			pdh.PdhAddEnglishCounterW.restype = wintypes.LONG
			pdh.PdhAddEnglishCounterW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, c_void_p, POINTER(wintypes.HANDLE)]

			pdh.PdhCollectQueryData.restype = wintypes.LONG
			pdh.PdhCollectQueryData.argtypes = [wintypes.HANDLE]

			pdh.PdhCloseQuery.restype = wintypes.LONG
			pdh.PdhCloseQuery.argtypes = [wintypes.HANDLE]

			pdh.PdhGetFormattedCounterValue.restype = wintypes.LONG
			pdh.PdhGetFormattedCounterValue.argtypes = [wintypes.HANDLE, wintypes.DWORD, c_void_p, POINTER(PDH_FMT_COUNTERVALUE)]

			hQuery = wintypes.HANDLE()
			if pdh.PdhOpenQueryW(None, None, byref(hQuery)) == 0:
				hCounter = wintypes.HANDLE()
				# Solo variantes de "% Processor Performance": es el único contador que
				# realmente representa la velocidad relativa a la base (puede superar
				# el 100% con Turbo Boost). Antes había un cuarto respaldo con
				# "% Processor Time" (que mide qué tan ocupado está el procesador, no
				# a qué velocidad va) y se le aplicaba la misma cuenta, dando un
				# resultado en GHz equivocado en los pocos equipos donde ese era el
				# único contador disponible. En esos equipos ahora se cae directo al
				# respaldo de psutil.cpu_freq(), que sí mide la velocidad de verdad.
				counterPaths = [
					r"\Processor Information(_Total)\% Processor Performance",
					r"\Processor Information(0,_Total)\% Processor Performance",
					r"\Processor Information(0,0)\% Processor Performance",
				]
				for cp in counterPaths:
					if pdh.PdhAddEnglishCounterW(hQuery, cp, None, byref(hCounter)) == 0:
						with self._stateLock:
							self._cpuQuery = hQuery
							self._cpuCounter = hCounter
						# Sin sleep en init: la primera muestra se descarta y la
						# segunda llegará en la próxima lectura periódica.
						pdh.PdhCollectQueryData(hQuery)
						self._lastCpuCollectTime = time.time()
						log.info(f"MonitorSistema: Contador PDH CPU configurado exitosamente: {cp}")
						break
				if not self._cpuCounter:
					log.warning("MonitorSistema: Ningún contador de rendimiento de procesador pudo ser añadido.")
					# La consulta se abrió con éxito pero ningún contador sirvió: si no la
					# cerramos aquí, se queda abierta para siempre porque no quedó guardada
					# en ningún lado para cerrarla más tarde.
					try:
						pdh.PdhCloseQuery(hQuery)
					except Exception:
						pass
			else:
				log.warning("MonitorSistema: PdhOpenQueryW falló al abrir la consulta.")
		except Exception as e:
			log.error(f"MonitorSistema: Error general en _initCpuQuery: {e}", exc_info=True)
			self._cpuQuery = None

	def _queryDiskHealthSilent(self) -> list:
		"""Pregunta a Windows por el estado de salud de los discos, sin decir nada.

		Lanza PowerShell y le pide, de cada disco, su nombre, si es SSD o disco
		duro, su estado de salud y su desgaste. Es la versión callada, la que usa
		el vigilante de avisos; devuelve los datos en bruto y, si algo falla,
		devuelve una lista vacía en vez de hablar. Tiene un límite de quince
		segundos para que no se quede colgada.
		"""
		try:
			ps_code = (
				"Get-PhysicalDisk | ForEach-Object {"
				"$rel = $_ | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue;"
				"[PSCustomObject]@{"
				"FriendlyName = $_.FriendlyName;"
				"MediaType = $_.MediaType;"
				"HealthStatus = $_.HealthStatus;"
				"OperationalStatus = ($_.OperationalStatus -join ', ');"
				"Wear = if ($rel) { $rel.Wear } else { $null }"
				"}"
				"} | ConvertTo-Json -Compress"
			)
			cmd = ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_code]
			out = subprocess.check_output(cmd, creationflags=0x08000000, timeout=15)
			if not out.strip():
				return []
			data = json.loads(out.decode("utf-8", errors="ignore"))
			if isinstance(data, dict):
				return [data]
			elif isinstance(data, list):
				return data
			return []
		except Exception as e:
			log.error(f"MonitorSistema: Error consultando salud de discos en segundo plano: {e}", exc_info=True)
			return []

	def _getGpuTemperatures(self) -> list[tuple[str, float]]:
		"""Devuelve la temperatura de cada tarjeta gráfica que la informe.

		Prueba los distintos fabricantes por orden y se queda con el primero que dé
		algún dato. Devuelve pares de nombre y grados; si solo hay una tarjeta la
		llama "GPU", y si hay varias las numera. Si ninguna informa temperatura,
		devuelve la lista vacía.
		"""
		gpus = []
		try:
			try:
				with self._stateLock:
					providers = list(self._gpuProviders)
			except Exception:
				providers = list(getattr(self, '_gpuProviders', []) or [])
			for provider in providers:
				telemetry = provider.collect()
				if not telemetry:
					continue
				is_single = len(telemetry) == 1
				for index, item in enumerate(telemetry, start=1):
					if item.temperature:
						try:
							t_val = float(item.temperature)
							if not math.isnan(t_val) and not math.isinf(t_val) and 0 < t_val < 150:
								name = _("GPU") if is_single else _("GPU {}").format(index)
								gpus.append((name, t_val))
						except (ValueError, TypeError, OverflowError):
							pass
				if gpus:
					break
		except Exception as e:
			log.error(f"MonitorSistema: Error consultando temperaturas de GPU: {e}", exc_info=True)
		return gpus

	def _decir(self, text: str):
		"""Dice un texto en voz alta desde un hilo de fondo, sin bloquear NVDA."""
		try:
			if getattr(self, '_coalescingAlerts', False):
				try:
					with self._stateLock:
						self._alertCoalescer.append(str(text))
					return
				except Exception:
					pass
			queueHandler.queueFunction(queueHandler.eventQueue, ui.message, text)
		except Exception:
			try:
				wx.CallAfter(ui.message, text)
			except Exception:
				pass

	def _emitBeep(self, freq: int, duration: int) -> None:
		"""Pitido vía cola de NVDA (seguro desde cualquier hilo)."""
		_beepAsync(freq, duration)

	def _flushAlertCoalescer(self) -> None:
		"""Emite los avisos acumulados como un único mensaje combinado."""
		try:
			with self._stateLock:
				msgs = list(getattr(self, '_alertCoalescer', []) or [])
				self._alertCoalescer = []
		except Exception:
			msgs = []
		if not msgs:
			return
		# Un solo mensaje combinado en vez de N locuciones encadenadas.
		combined = ' '.join(m.strip() for m in msgs if m and str(m).strip())
		if not combined:
			return
		log.info(f"MonitorSistema: Avisos combinados ({len(msgs)}): '{combined[:200]}'")
		try:
			queueHandler.queueFunction(queueHandler.eventQueue, ui.message, combined)
		except Exception:
			try:
				wx.CallAfter(ui.message, combined)
			except Exception:
				pass

	def _avisoDeBateriaDelEquipo(self, cfg, now, recordado):
		"""Avisa cuando la bateria del equipo se llena o se queda baja.

		'recordado' guarda de una vuelta a la siguiente cuando se comprobo por
		ultima vez y con que ajustes, para no repetir el aviso ni el mensaje.
		"""
		# 1. Chequeo de batería del equipo
		check_full = cfg.get("alertBatteryFull", True)
		check_low = cfg.get("alertBatteryLow", True)
		try:
			bat_interval = max(1, int(cfg.get("alertBatteryInterval", 1))) * 60
		except (ValueError, TypeError):
			bat_interval = 60
		if recordado["last_battery_interval"] != bat_interval:
			recordado["last_battery_interval"] = bat_interval
			recordado["last_battery_check_time"] = 0.0

		if (check_full or check_low) and (now - recordado["last_battery_check_time"] >= bat_interval):
			recordado["last_battery_check_time"] = now
			try:
				bat = psutil.sensors_battery()
				if bat and bat.percent is not None:
					try:
						pct = float(bat.percent)
					except (ValueError, TypeError):
						pct = None
					if pct is not None and not math.isnan(pct) and not math.isinf(pct) and 0 <= pct <= 100:
						plugged = bat.power_plugged

						# Alerta de batería cargada (>= bat_full_thresh% y conectada)
						try:
							bat_full_thresh = int(cfg.get("alertBatteryFullThreshold", 100))
						except (ValueError, TypeError):
							bat_full_thresh = 100
						if check_full and plugged is True and pct >= bat_full_thresh:
							if bat_full_thresh >= 100:
								msg = _("Batería completamente cargada al 100 %. Puedes desconectar el cargador.")
							else:
								msg = _("Batería cargada al {} %. Puedes desconectar el cargador.").format(round(pct))
							log.info(f"MonitorSistema: Alerta automática de batería cargada: '{msg}'")
							self._emitBeep(880, 100); self._emitBeep(1175, 150)
							self._decir(msg)

						# Alerta de batería baja (<= bat_thresh% y desconectada)
						try:
							bat_thresh = int(cfg.get("alertBatteryLowThreshold", 15))
						except (ValueError, TypeError):
							bat_thresh = 15
						if check_low and plugged is False and pct <= bat_thresh:
							msg = _("Advertencia: Batería baja al {} %. Conecta el equipo a la corriente.").format(round(pct))
							log.info(f"MonitorSistema: Alerta automática de batería baja: '{msg}'")
							self._emitBeep(440, 120); self._emitBeep(330, 150)
							self._decir(msg)
			except Exception as be:
				log.error(f"MonitorSistema: Error en chequeo de batería para alertas: {be}", exc_info=True)

	def _avisoDeTemperaturaDeCpu(self, cfg, now, recordado):
		"""Avisa cuando el procesador pasa de la temperatura configurada.

		'recordado' guarda de una vuelta a la siguiente cuando se comprobo por
		ultima vez y con que ajustes, para no repetir el aviso ni el mensaje.
		"""
		# 2. Alerta de temperatura alta de CPU (>= cpu_hot_thresh °C)
		check_hot = cfg.get("alertCpuHot", True)
		try:
			cpu_interval = max(1, int(cfg.get("alertCpuHotInterval", 1))) * 60
		except (ValueError, TypeError):
			cpu_interval = 60
		try:
			cpu_hot_thresh = int(cfg.get("alertCpuHotThreshold", 85))
		except (ValueError, TypeError):
			cpu_hot_thresh = 85
		if cpu_hot_thresh < 70:
			cpu_hot_thresh = 85
		if recordado["last_cpu_hot_thresh"] != cpu_hot_thresh or recordado["last_cpu_interval"] != cpu_interval:
			recordado["last_cpu_hot_thresh"] = cpu_hot_thresh
			recordado["last_cpu_interval"] = cpu_interval
			recordado["last_cpu_check_time"] = 0.0
			log.info(f"MonitorSistema: Umbral de alerta por temperatura de CPU: {cpu_hot_thresh} °C (intervalo: {cpu_interval // 60} min)")

		if check_hot and (now - recordado["last_cpu_check_time"] >= cpu_interval):
			recordado["last_cpu_check_time"] = now
			try:
				temp = self._getCpuTemperature()
				if temp is not None:
					try:
						t_num = float(temp)
						is_valid = not math.isnan(t_num) and not math.isinf(t_num) and 0 < t_num < 150
					except (ValueError, TypeError, OverflowError):
						is_valid = False
					if is_valid and t_num >= cpu_hot_thresh:
						msg = _("Alerta: Temperatura del procesador alta ({}).").format(formatGpuTemperature(str(temp)))
						log.warning(f"MonitorSistema: Alerta automática de temperatura activada: '{msg}' (temp={temp}°C, umbral={cpu_hot_thresh}°C)")
						self._emitBeep(1000, 100); self._emitBeep(1000, 100)
						self._decir(msg)
			except Exception as te:
				log.error(f"MonitorSistema: Error en chequeo de temperatura para alertas: {te}", exc_info=True)

	def _avisoDeTemperaturaDeGpu(self, cfg, now, recordado):
		"""Avisa cuando la tarjeta grafica pasa de la temperatura configurada.

		'recordado' guarda de una vuelta a la siguiente cuando se comprobo por
		ultima vez y con que ajustes, para no repetir el aviso ni el mensaje.
		"""
		# 3. Alerta de temperatura alta de GPU (>= gpu_hot_thresh °C)
		check_gpu_hot = cfg.get("alertGpuHot", True)
		try:
			gpu_interval = max(1, int(cfg.get("alertGpuHotInterval", 1))) * 60
		except (ValueError, TypeError):
			gpu_interval = 60
		try:
			gpu_hot_thresh = int(cfg.get("alertGpuHotThreshold", 80))
		except (ValueError, TypeError):
			gpu_hot_thresh = 80
		if gpu_hot_thresh < 70:
			gpu_hot_thresh = 80
		if recordado["last_gpu_hot_thresh"] != gpu_hot_thresh or recordado["last_gpu_interval"] != gpu_interval:
			recordado["last_gpu_hot_thresh"] = gpu_hot_thresh
			recordado["last_gpu_interval"] = gpu_interval
			recordado["last_gpu_check_time"] = 0.0
			log.info(f"MonitorSistema: Umbral de alerta por temperatura de GPU: {gpu_hot_thresh} °C (intervalo: {gpu_interval // 60} min)")

		if check_gpu_hot and (now - recordado["last_gpu_check_time"] >= gpu_interval):
			recordado["last_gpu_check_time"] = now
			try:
				gpu_temps = self._getGpuTemperatures()
				if not gpu_temps or not isinstance(gpu_temps, (list, tuple)):
					return
				for item in gpu_temps:
					if not isinstance(item, (list, tuple)) or len(item) < 2:
						continue
					g_name, g_temp = item[0], item[1]
					try:
						g_num = float(g_temp)
						g_valid = not math.isnan(g_num) and not math.isinf(g_num) and 0 < g_num < 150
					except (ValueError, TypeError, OverflowError):
						g_valid = False
					if g_valid and g_num >= gpu_hot_thresh:
						msg = _("Alerta: Temperatura de {name} alta ({temp}).").format(
							name=g_name,
							temp=formatGpuTemperature(str(g_temp)),
						)
						log.warning(f"MonitorSistema: Alerta automática de temperatura de GPU activada: '{msg}' (temp={g_temp}°C, umbral={gpu_hot_thresh}°C)")
						self._emitBeep(1200, 100); self._emitBeep(1200, 100)
						self._decir(msg)
			except Exception as ge:
				log.error(f"MonitorSistema: Error en chequeo de temperatura de GPU para alertas: {ge}", exc_info=True)

	def _avisoDeBateriaBluetooth(self, cfg, now, recordado):
		"""Avisa cuando un aparato Bluetooth se queda con poca bateria.

		'recordado' guarda de una vuelta a la siguiente cuando se comprobo por
		ultima vez y con que ajustes, para no repetir el aviso ni el mensaje.
		"""
		# 4. Alerta de batería baja en dispositivos Bluetooth (<= bt_thresh%)
		check_bt = cfg.get("alertBluetoothLow", True)
		try:
			bt_thresh = int(cfg.get("alertBluetoothLowThreshold", 15))
		except (ValueError, TypeError):
			bt_thresh = 15
		try:
			bt_interval = max(1, int(cfg.get("alertBluetoothLowInterval", 2))) * 60
		except (ValueError, TypeError):
			bt_interval = 120
		if recordado["last_bt_thresh"] != bt_thresh or recordado["last_bt_interval"] != bt_interval:
			recordado["last_bt_thresh"] = bt_thresh
			recordado["last_bt_interval"] = bt_interval
			recordado["last_bt_check_time"] = 0.0
			log.info(f"MonitorSistema: Umbral de alerta Bluetooth: {bt_thresh} % (intervalo: {bt_interval // 60} min)")

		if check_bt and (now - recordado["last_bt_check_time"] >= bt_interval):
			recordado["last_bt_check_time"] = now
			try:
				bt_devices = self._queryBluetoothBatteries()
				if not bt_devices or not isinstance(bt_devices, (list, tuple)):
					return
				for d in bt_devices:
					if not isinstance(d, dict):
						continue
					d_name = d.get('name', _('Dispositivo Bluetooth'))
					d_bat = d.get('battery')
					if d_bat is not None:
						try:
							b_num = float(d_bat)
							b_valid = not math.isnan(b_num) and not math.isinf(b_num) and 0 <= b_num <= bt_thresh
						except (ValueError, TypeError, OverflowError):
							b_valid = False
						if b_valid:
							msg = _("Advertencia: Batería baja en el dispositivo Bluetooth {} al {} %.").format(d_name, round(b_num))
							log.warning(f"MonitorSistema: Alerta automática Bluetooth: '{msg}'")
							self._emitBeep(550, 100); self._emitBeep(440, 150)
							self._decir(msg)
			except Exception as bte:
				log.error(f"MonitorSistema: Error en chequeo de batería Bluetooth para alertas: {bte}", exc_info=True)

	def _avisoDeSaludDeDiscos(self, cfg, now, recordado):
		"""Avisa de problemas de salud o de desgaste alto en los discos.

		'recordado' guarda de una vuelta a la siguiente cuando se comprobo por
		ultima vez y con que ajustes, para no repetir el aviso ni el mensaje.
		"""
		# 5. Alerta periódica de salud y desgaste de discos (HDD / SSD)
		check_disk = cfg.get("alertDiskHealth", True)
		try:
			wear_thresh = int(cfg.get("alertDiskWearThreshold", 80))
		except (ValueError, TypeError):
			wear_thresh = 80
		try:
			disk_interval = max(1, int(cfg.get("alertDiskHealthInterval", 240))) * 60
		except (ValueError, TypeError):
			disk_interval = 14400
		if recordado["last_disk_interval"] != disk_interval:
			recordado["last_disk_interval"] = disk_interval
			recordado["last_disk_check_time"] = 0.0

		if check_disk and (now - recordado["last_disk_check_time"] >= disk_interval):
			recordado["last_disk_check_time"] = now
			if not self._tryStartOp("diskAlert", "_diskAlertRunning"):
				return
			def _diskWorker():
				"""Revisa la salud de los discos y avisa si alguno está mal.

				Va en un hilo aparte porque preguntar a Windows por los discos tarda varios
				segundos. Avisa por dos motivos distintos: que el disco diga que no está
				sano, y que un SSD haya gastado más vida útil del límite que tengas puesto.
				Cada aviso lleva sus propios pitidos, para poder distinguirlos sin escuchar
				la frase entera.
				"""
				try:
					disks = self._queryDiskHealthSilent()
					if not disks or not isinstance(disks, (list, tuple)):
						return
					for d in disks:
						if not isinstance(d, dict):
							continue
						name = d.get("FriendlyName") or _("Disco")
						hstatus = str(d.get("HealthStatus") or "")
						opstatus = str(d.get("OperationalStatus") or "")
						wear = d.get("Wear")

						# Daño general S.M.A.R.T. o estado no saludable en HDD o SSD
						is_unhealthy = (
							(hstatus and hstatus.lower() not in ("healthy", "ok", "0")) or
							any(bad in opstatus.lower() for bad in ("degraded", "error", "predictive failure", "unhealthy", "lost communication", "stressed"))
						)
						if is_unhealthy:
							msg = _("Advertencia crítica: El disco {} presenta problemas de salud. Realiza una copia de seguridad.").format(name)
							log.warning(f"MonitorSistema: Alerta de salud de disco: '{msg}'")
							self._emitBeep(330, 150); self._emitBeep(220, 200)
							self._decir(msg)

						# Límite de desgaste de vida útil en discos SSD
						if wear is not None:
							try:
								wear_val = int(wear)
								if wear_val >= wear_thresh:
									msg = _("Advertencia: El disco SSD {} ha alcanzado un {} % de desgaste de su vida útil.").format(name, wear_val)
									log.warning(f"MonitorSistema: Alerta de desgaste SSD: '{msg}'")
									self._emitBeep(440, 150); self._emitBeep(330, 200)
									self._decir(msg)
							except (ValueError, TypeError, OverflowError):
								pass
				except Exception as dke:
					log.error(f"MonitorSistema: Error en chequeo de salud de discos: {dke}", exc_info=True)
				finally:
					self._finishOp("diskAlert", "_diskAlertRunning")
			threading.Thread(target=_diskWorker, daemon=True).start()

	def _avisoDeTemperaturaDeDisco(self, cfg, now, recordado):
		"""Avisa cuando un disco pasa de la temperatura configurada.

		La temperatura se le pide al propio disco, no a Windows, porque es la unica
		forma de leerla sin permisos de administrador. Un aviso automatico que
		sacara el cartel de permisos cada pocos minutos no serviria de nada.

		'recordado' guarda de una vuelta a la siguiente cuando se comprobo por
		ultima vez y con que ajustes, para no repetir el aviso ni el mensaje.
		"""
		# 6. Alerta de temperatura alta de disco (>= disk_hot_thresh °C)
		check_disk_hot = cfg.get("alertDiskHot", True)
		try:
			disk_hot_thresh = int(cfg.get("alertDiskHotThreshold", 70))
		except (ValueError, TypeError):
			disk_hot_thresh = 70
		try:
			disk_hot_interval = max(1, int(cfg.get("alertDiskHotInterval", 5))) * 60
		except (ValueError, TypeError):
			disk_hot_interval = 300
		if (
			recordado["last_disk_hot_thresh"] != disk_hot_thresh
			or recordado["last_disk_hot_interval"] != disk_hot_interval
		):
			recordado["last_disk_hot_thresh"] = disk_hot_thresh
			recordado["last_disk_hot_interval"] = disk_hot_interval
			recordado["last_disk_hot_check_time"] = 0.0
			log.info(f"MonitorSistema: Umbral de alerta por temperatura de disco: {disk_hot_thresh} °C (intervalo: {disk_hot_interval // 60} min)")

		if check_disk_hot and (now - recordado["last_disk_hot_check_time"] >= disk_hot_interval):
			recordado["last_disk_hot_check_time"] = now
			try:
				disks = temperaturasDeDiscos()
				if not disks or not isinstance(disks, (list, tuple)):
					return
				for item in disks:
					if not isinstance(item, (list, tuple)) or len(item) < 2:
						continue
					nombre, grados = item[0], item[1]
					try:
						d_num = float(grados)
						d_valid = (0 < d_num < 150)
					except (ValueError, TypeError, OverflowError):
						d_valid = False
					if d_valid and d_num >= disk_hot_thresh:
						msg = _("Alerta: Temperatura de {name} alta ({temp}).").format(
							name=nombre,
							temp=formatGpuTemperature(str(grados)),
						)
						log.warning(f"MonitorSistema: Alerta automática de temperatura de disco activada: '{msg}' (temp={grados}°C, umbral={disk_hot_thresh}°C)")
						self._emitBeep(800, 100); self._emitBeep(800, 100)
						self._decir(msg)
			except Exception as dhe:
				log.error(f"MonitorSistema: Error en chequeo de temperatura de discos para alertas: {dhe}", exc_info=True)

	def _runAlertsLoop(self):
		"""El vigilante: comprueba cada pocos segundos si toca dar algún aviso.

		Se ejecuta en un hilo aparte durante toda la sesión de NVDA. En el
		diccionario "recordado" guarda cuándo se comprobó cada cosa por última vez
		y con qué ajustes, para no repetir avisos antes de tiempo. Espera ocho
		segundos al arrancar, y después revisa en cada vuelta la batería del
		equipo, la temperatura del procesador y de la gráfica, la batería de los
		aparatos Bluetooth y la salud de los discos. Entre vuelta y vuelta, cada
		dos segundos, mira además si cambió la señal del Wi-Fi. Si cambias las
		opciones, la marca de comprobación inmediata pone a cero los relojes y todo
		se revisa al momento.
		"""
		# Lo que hay que recordar de una vuelta a la siguiente: cuando se comprobo
		# cada cosa por ultima vez y con que ajustes se hizo.
		recordado = {
			"last_cpu_hot_thresh": None,
			"last_cpu_interval": None,
			"last_cpu_check_time": 0.0,
			"last_gpu_hot_thresh": None,
			"last_gpu_interval": None,
			"last_gpu_check_time": 0.0,
			"last_bt_thresh": None,
			"last_bt_interval": None,
			"last_bt_check_time": 0.0,
			"last_battery_interval": None,
			"last_battery_check_time": 0.0,
			"last_disk_interval": None,
			"last_disk_check_time": 0.0,
			"last_disk_hot_thresh": None,
			"last_disk_hot_interval": None,
			"last_disk_hot_check_time": 0.0,
		}
		last_wlan_signal = None


		# Esperar 8 segundos tras arrancar NVDA
		if hasattr(self, "_stopAlertsEvent") and self._stopAlertsEvent.wait(8.0):
			return

		while hasattr(self, "_stopAlertsEvent") and not self._stopAlertsEvent.is_set():
			try:
				try:
					with self._stateLock:
						self._alertCoalescer = []
					self._coalescingAlerts = True
				except Exception:
					pass
				if getattr(self, "_forceAlertsCheck", False):
					self._forceAlertsCheck = False
					# Poner a cero la ultima comprobacion hace que todos los avisos se
					# revisen ya, sin esperar a que venza su intervalo.
					for clave in list(recordado):
						if clave.endswith("check_time"):
							recordado[clave] = 0.0
					log.info("MonitorSistema: Comprobación inmediata de alertas forzada tras cambio de opciones")

				cfg = config.conf.get("monitoreoSistema", {})
				now = time.time()

				self._avisoDeBateriaDelEquipo(cfg, now, recordado)
				self._avisoDeTemperaturaDeCpu(cfg, now, recordado)
				self._avisoDeTemperaturaDeGpu(cfg, now, recordado)
				self._avisoDeBateriaBluetooth(cfg, now, recordado)
				self._avisoDeSaludDeDiscos(cfg, now, recordado)
				self._avisoDeTemperaturaDeDisco(cfg, now, recordado)
			except Exception as e:
				log.error(f"MonitorSistema: Error general en bucle de alertas: {e}", exc_info=True)
			finally:
				try:
					with self._stateLock:
						self._coalescingAlerts = False
				except Exception:
					pass
				try:
					self._flushAlertCoalescer()
				except Exception:
					pass

			for sec in range(5):
				if hasattr(self, "_stopAlertsEvent") and self._stopAlertsEvent.is_set():
					break
				if getattr(self, "_forceAlertsCheck", False):
					break
				if sec % 2 == 0:
					try:
						if config.conf.get("monitoreoSistema", {}).get("alertWlanSignalChange", False):
							cur_sig = self._getCurrentWlanSignalCached()
							if cur_sig is not None:
								if last_wlan_signal is not None and cur_sig != last_wlan_signal:
									# Coalescer: guardar el último valor y avisar una sola vez.
									try:
										with self._stateLock:
											self._pendingWlanSignal = cur_sig
											self._pendingWlanSignalTime = time.time()
									except Exception:
										pass
									# Solo anunciar si pasaron >=15 s desde el último aviso de señal.
									last_ann = float(getattr(self, '_lastWlanSignalAnnounce', 0.0) or 0.0)
									if (time.time() - last_ann) >= 15.0:
										self._lastWlanSignalAnnounce = time.time()
										last_wlan_signal = cur_sig
										freq = int(350 + (cur_sig * 8.5))
										_beepAsync(freq, 70)
										msg = _("Señal de Wi-Fi: {} %.").format(cur_sig)
										log.info(f"MonitorSistema: Alerta de cambio de señal Wi-Fi: {cur_sig}%")
										self._decir(msg)
								elif last_wlan_signal is None:
									last_wlan_signal = cur_sig
							else:
								last_wlan_signal = None
						else:
							last_wlan_signal = None
					except Exception as we:
						log.error(f"MonitorSistema: Error comprobando señal Wi-Fi en loop: {we}", exc_info=True)
				if hasattr(self, "_stopAlertsEvent") and self._stopAlertsEvent.wait(1.0):
					break

	def terminate(self):
		"""Deja todo como estaba cuando NVDA descarga el complemento.

		Manda parar al hilo vigilante, quita el submenú del menú Herramientas y el
		panel de las preferencias, cierra el contador del procesador y se da de baja
		de los avisos de Wi-Fi de Windows. Si esto no se hiciera, al recargar los
		complementos quedarían menús repetidos y hilos y contadores sueltos
		consumiendo recursos.
		"""
		log.info("Monitoreo del Sistema: Finalizando complemento...")
		if hasattr(self, "_stopAlertsEvent"):
			try:
				self._stopAlertsEvent.set()
			except Exception:
				pass
		try:
			self._joinBackgroundThreads(timeout=2.0)
		except Exception:
			pass
		try:
			if hasattr(self, "_itemConfig") and self._itemConfig:
				gui.mainFrame.sysTrayIcon.Unbind(wx.EVT_MENU, source=self._itemConfig)
			if hasattr(self, "_subMenuItem") and self._subMenuItem:
				try:
					self._toolsMenu.DestroyItem(self._subMenuItem)
				except Exception:
					self._toolsMenu.Remove(self._subMenuItem)
		except Exception as e:
			log.debug(f"Monitoreo del Sistema: Error retirando submenú en terminate: {e}")
		super().terminate()
		try:
			with self._stateLock:
				providers = list(getattr(self, '_gpuProviders', []) or [])
		except Exception:
			providers = []
		for provider in providers:
			if hasattr(provider, "close"):
				try:
					provider.close()
				except Exception:
					pass
		try:
			with self._stateLock:
				try:
					self._gpuProviders.clear()
				except Exception:
					pass
		except Exception:
			pass
		try:
			if MonitorSistemaSettingsPanel in NVDASettingsDialog.categoryClasses:
				NVDASettingsDialog.categoryClasses.remove(MonitorSistemaSettingsPanel)
		except Exception:
			pass
		try:
			with self._stateLock:
				cpuQ = getattr(self, '_cpuQuery', None)
				self._cpuQuery = None
				self._cpuCounter = None
		except Exception:
			cpuQ = None
		if cpuQ:
			try:
				ctypes.windll.pdh.PdhCloseQuery(cpuQ)
			except Exception:
				log.debug("Monitoreo del Sistema: no se pudo cerrar el contador del procesador.", exc_info=True)
		try:
			with self._stateLock:
				handle = getattr(self, '_client_handle', None)
				self._client_handle = None
				self._negotiated_version = None
		except Exception:
			handle = None
		if handle:
			try:
				# Unregister con callback None (no notifyHandler): pasar el callback
				# original aquí re-registraría en vez de desregistrar.
				try:
					wlanapi.WlanRegisterNotification(
						handle,
						wlanapi.WLAN_NOTIFICATION_SOURCE_NONE,
						True,
						None,
						None,
						None,
						None,
					)
				except Exception:
					pass
				wlanapi.WlanCloseHandle(
					handle,
					None,
				)
			except Exception:
				log.debug("Monitoreo del Sistema: no se pudo cerrar la conexion con la tarjeta de red.", exc_info=True)
		try:
			self._wlanCallback = None
		except Exception:
			pass
		try:
			_freeAdlDll()
		except Exception:
			pass
		try:
			with self._stateLock:
				self._bgThreads = []
		except Exception:
			pass
		log.info("Monitoreo del Sistema: Recursos y manejadores liberados, complemento finalizado limpiamente.")

	def _onMenuConfig(self, event):
		log.info("Monitoreo del Sistema: Abriendo configuración desde el menú Herramientas...")
		# popupSettingsDialog es la forma correcta de abrir el diálogo de opciones de NVDA
		# posicionado en el panel de un complemento. Se llama con CallAfter para que se
		# abra cuando el menú Herramientas ya se cerró.
		wx.CallAfter(gui.mainFrame.popupSettingsDialog, NVDASettingsDialog, MonitorSistemaSettingsPanel)


	@scriptHandler.script(
		description=_("Presenta la memoria RAM utilizada y la carga promedio del procesador."), category=scriptCategory,
		gesture="kb:nvda+shift+e",
		speakOnDemand=True,
	)
	def script_announceResourceSummary(self, gesture: inputCore.InputGesture):
		"""Anuncia la memoria RAM utilizada y el porcentaje de carga del procesador."""
		try:
			info = _("{}% de RAM utilizada, CPU al {}%.").format(
				tryTrunk(psutil.virtual_memory()[2]), tryTrunk(psutil.cpu_percent())
			)
			log.info(f"MonitorSistema: script_announceResourceSummary - Anunciando al usuario: '{info}'")
			ui.message(info)
		except Exception as e:
			log.error(f"MonitorSistema: Error en script_announceResourceSummary: {e}", exc_info=True)
			ui.message(_("Error al obtener el resumen del sistema."))

	def _getCpuTemperature(self) -> float | int | None:
		"""Temperatura del procesador, probando dos vias distintas.

		Devuelve None si ninguna responde, que es lo normal en muchos equipos.
		"""
		# 1. La biblioteca de AMD, que es la que responde en este tipo de equipos
		temperatura = self._temperaturaPorAmdAdl()
		if temperatura is not None:
			return temperatura

		# 2. Los almacenes de datos de Windows
		return self._temperaturaPorWmi()

	def _temperaturaPorAmdAdl(self):
		"""Temperatura del procesador segun la biblioteca de AMD, o None.

		Solo responde en equipos AMD; en los demas falla y se sigue por otra via.
		Usa la DLL cacheada globalmente y siempre destruye el control ADL en finally.
		"""
		adl, dll_name = _getAdlDll()
		if adl is None:
			return None
		created = False
		adl_alloc_cb = None
		try:
			ALLOC_FUNC = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_size_t)
			def adl_alloc(size):
				"""Reserva de memoria para la biblioteca ADL de AMD."""
				return ctypes.windll.kernel32.LocalAlloc(0x0040, size)
			adl_alloc_cb = ALLOC_FUNC(adl_alloc)
			# Mantener referencia viva durante la llamada.
			self._adlAllocCb = adl_alloc_cb
			if adl.ADL_Main_Control_Create(adl_alloc_cb, 1) != 0:
				return None
			created = True
			temp_val = None
			if hasattr(adl, "ADL2_OverdriveN_Temperature_Get"):
				func = adl.ADL2_OverdriveN_Temperature_Get
				func.argtypes = [ctypes.c_void_p, c_long, c_long, POINTER(c_long)]
				func.restype = c_long
				t = c_long(0)
				if func(None, 0, 0, byref(t)) == 0 and t.value > 0:
					c = t.value / 1000.0
					if 0 < c < 125:
						temp_val = round(c)
						log.debug(f"MonitorSistema: Temperatura CPU obtenida via AMD ADL ({dll_name}): {temp_val} C")
			if temp_val is not None:
				return temp_val
			return None
		except Exception:
			return None
		finally:
			if created:
				try:
					adl.ADL_Main_Control_Destroy()
				except Exception:
					pass

	def _temperaturaPorWmi(self):
		"""Temperatura del procesador preguntando a Windows, o None.

		Se consultan varios almacenes de datos porque cada fabricante publica la
		temperatura en un sitio distinto, y muchos equipos no la publican en ninguno.
		"""
		co_init = False
		try:
			import comtypes
			import comtypes.client
			try:
				comtypes.CoInitialize()
				co_init = True
			except Exception:
				pass
			locator = comtypes.client.CreateObject("WbemScripting.SWbemLocator")

			# 2a. ACPI Thermal Zone (root\wmi)
			try:
				services = locator.ConnectServer(".", "root\\wmi")
				results = services.ExecQuery("SELECT CurrentTemperature FROM MSAcpi_ThermalZoneTemperature")
				for item in results:
					kelvin = item.Properties_("CurrentTemperature").Value
					if kelvin and kelvin > 0:
						c = (kelvin / 10.0) - 273.15
						if 0 < c < 125:
							log.debug(f"MonitorSistema: Temperatura CPU obtenida via MSAcpi: {round(c)} C")
							return round(c)
			except Exception:
				pass

			# 2b. Performance counters de zonas térmicas (root\cimv2)
			try:
				services = locator.ConnectServer(".", "root\\cimv2")
				results = services.ExecQuery("SELECT Temperature FROM Win32_PerfFormattedData_Counters_ThermalZoneInformation")
				for item in results:
					kelvin = item.Properties_("Temperature").Value
					if kelvin and kelvin > 0:
						c = kelvin - 273.15
						if 0 < c < 125:
							log.debug(f"MonitorSistema: Temperatura CPU obtenida via ThermalZoneInformation: {round(c)} C")
							return round(c)
			except Exception:
				pass

			# 2c. Sensores de LibreHardwareMonitor / OpenHardwareMonitor
			for ns in ("root\\OpenHardwareMonitor", "root\\LibreHardwareMonitor"):
				try:
					services = locator.ConnectServer(".", ns)
					results = services.ExecQuery("SELECT Value, Name, SensorType FROM Sensor WHERE SensorType='Temperature'")
					for item in results:
						name = str(item.Properties_("Name").Value or "").lower()
						if any(k in name for k in ("cpu", "package", "core")):
							val = item.Properties_("Value").Value
							if val and 0 < val < 125:
								log.debug(f"MonitorSistema: Temperatura CPU obtenida via {ns}: {round(val)} C")
								return round(val)
				except Exception:
					pass
		except Exception as e:
			log.debug(f"MonitorSistema: Error consultando temperatura de CPU: {e}")
		finally:
			if co_init:
				try:
					comtypes.CoUninitialize()
				except Exception:
					pass
		return None


	@scriptHandler.script(
		description=_("Presenta la carga promedio del procesador y la carga de cada núcleo. Si se pulsa dos veces, copia la información al portapapeles."), category=scriptCategory,
		gesture="kb:nvda+shift+1",
		speakOnDemand=True,
	)
	def script_announceProcessorInfo(self, gesture: inputCore.InputGesture):
		"""Atajo de teclado: dice cuánto está trabajando el procesador.

		Si el equipo tiene un solo núcleo dice solo la carga; si tiene varios, dice
		la media y después la de cada núcleo. Pulsando el atajo dos veces seguidas,
		en vez de decirlo lo copia al portapapeles.
		"""
		try:
			averageLoad = psutil.cpu_percent()
			perCpuLoad = psutil.cpu_percent(percpu=True)
			coreLoad = [
				_("Núcleo {}: {}%").format(core, tryTrunk(cpuLoad))
				for core, cpuLoad in enumerate(perCpuLoad, start=1)
			]

			cpu_count = psutil.cpu_count()
			if cpu_count == 1 or not coreLoad:
				info = _("Carga de CPU al {}%.").format(tryTrunk(averageLoad))
			else:
				info = _("Carga media de CPU al {}%, {}.").format(
					tryTrunk(averageLoad), ", ".join(coreLoad)
				)
			self._anunciarOCopiar(info, "script_announceProcessorInfo")
		except Exception as e:
			log.error(f"MonitorSistema: Error en script_announceProcessorInfo: {e}", exc_info=True)
			ui.message(_("Error al obtener la información del procesador."))

	@scriptHandler.script(
		description=_("Presenta el espacio utilizado y total de la memoria RAM física y virtual. Si se pulsa dos veces, copia la información al portapapeles."), category=scriptCategory,
		gesture="kb:nvda+shift+2",
		speakOnDemand=True,
	)
	def script_announceRamInfo(self, gesture: inputCore.InputGesture):
		"""Atajo de teclado: dice cuánta memoria RAM está usando el equipo.

		Da dos datos: la memoria física, que son los módulos de RAM instalados, y
		la virtual, que incluye además lo que Windows ha pasado al disco. De cada
		una dice cuánto se usa, de cuánto total y el porcentaje. Pulsando el atajo
		dos veces seguidas lo copia al portapapeles.
		"""
		try:
			memory = psutil.virtual_memory()
			physicalRamUsed, physicalRamTotal = memory.used, memory.total
			physicalPercent = tryTrunk(round(physicalRamUsed / physicalRamTotal * 100, 1)) if physicalRamTotal > 0 else 0
			info = _("Física: {physicalUsed} de {physicalTotal} utilizada ({physicalPercent}%). ").format(
				physicalUsed=size(physicalRamUsed, alternative),
				physicalTotal=size(physicalRamTotal, alternative),
				physicalPercent=physicalPercent,
			)
			try:
				if hasattr(psutil, "_psutil_windows") and hasattr(psutil._psutil_windows, "virtual_mem"):
					virtualMemory = psutil._psutil_windows.virtual_mem()
					virtualRamUsed, virtualRamTotal = virtualMemory[2] - virtualMemory[3], virtualMemory[2]
				else:
					swap = psutil.swap_memory()
					virtualRamUsed, virtualRamTotal = swap.used, swap.total
			except Exception:
				swap = psutil.swap_memory()
				virtualRamUsed, virtualRamTotal = swap.used, swap.total
			virtualRamUsed = max(0, virtualRamUsed)
			virtualRamTotal = max(0, virtualRamTotal)
			virtualPercent = tryTrunk(round(virtualRamUsed / virtualRamTotal * 100, 1)) if virtualRamTotal > 0 else 0
			info += _("Virtual: {virtualUsed} de {virtualTotal} utilizada ({virtualPercent}%).").format(
				virtualUsed=size(virtualRamUsed, alternative),
				virtualTotal=size(virtualRamTotal, alternative),
				virtualPercent=virtualPercent,
			)
			self._anunciarOCopiar(info, "script_announceRamInfo")
		except Exception as e:
			log.error(f"MonitorSistema: Error en script_announceRamInfo: {e}", exc_info=True)
			ui.message(_("Error al obtener la información de la memoria RAM."))

	def _resolveMaxTurbo(self, procName: str, baseGhz: float) -> float:
		"""Averigua la velocidad máxima del procesador a partir de su nombre.

		Prueba tres caminos por orden. Primero busca el nombre en la tabla de
		modelos conocidos, quedándose con la coincidencia más larga y no con la
		primera: si no fuera así, un Intel i5-13600K encajaría con "3600", que es
		un AMD, y se le atribuiría la velocidad equivocada. Si no está en la tabla,
		busca una cifra "@ 4.20 GHz" dentro del propio nombre. Si tampoco, se lo
		pregunta al sistema. Y como último recurso, calcula una estimación a partir
		de la velocidad base.
		"""
		name_lower = (procName or "").lower()

		# AMD Ryzen 9
		# Gana la coincidencia mas concreta, no la primera de la lista. Antes se
		# devolvia la primera y eso daba un resultado erroneo cuando el nombre de
		# un procesador contenia al de otro: un Intel i5-13600K encajaba con
		# "3600" (un AMD Ryzen 5) y se le atribuia su velocidad, 4,20 en vez de 5.
		mejorModelo, mejorVelocidad = "", None
		for modelos, velocidad in VELOCIDAD_MAXIMA_CONOCIDA:
			for modelo in modelos:
				if modelo in name_lower and len(modelo) > len(mejorModelo):
					mejorModelo, mejorVelocidad = modelo, velocidad
		if mejorVelocidad is not None:
			return mejorVelocidad

		m = re.search(r"@\s*([0-9\.]+)\s*ghz", name_lower)
		if m:
			try:
				nominal = float(m.group(1))
				if nominal > baseGhz:
					return nominal
			except Exception:
				pass

		try:
			freq = psutil.cpu_freq()
			if freq and freq.max > (baseGhz * 1000.0) and (freq.max / 1000.0) < (baseGhz * 2.5):
				return round(freq.max / 1000.0, 2)
		except Exception:
			pass

		return round(max(baseGhz, baseGhz * 1.35 if baseGhz >= 3.5 else baseGhz * 1.6), 2)

	def _getCpuFrequencyInfo(self) -> str:
		"""Frase con la velocidad del procesador y su relacion con la de fabrica."""
		currGhz = self._velocidadActualDelProcesador()
		if currGhz:
			if currGhz > self._maxTurboGhz:
				currGhz = self._maxTurboGhz

			if currGhz > self._baseGhz:
				max_turbo = self._maxTurboGhz if self._maxTurboGhz > 0 else max(currGhz, self._baseGhz)
				pct = tryTrunk(round((currGhz / max_turbo) * 100, 1))
				return _("{curr:.2f} GHz de {maxTurbo:.2f} GHz máximos ({pct}%), turbo activo.").format(
					curr=currGhz, maxTurbo=max_turbo, pct=pct
				)
			else:
				base_ghz = self._baseGhz if self._baseGhz > 0 else 2.10
				pct = tryTrunk(round((currGhz / base_ghz) * 100, 1))
				return _("{curr:.2f} GHz de {base:.2f} GHz velocidad base ({pct}%).").format(
					curr=currGhz, base=base_ghz, pct=pct
				)

		return _("No se pudo obtener la velocidad del procesador en tiempo real.")

	def _velocidadActualDelProcesador(self):
		"""Gigahercios a los que va el procesador ahora mismo, o None.

		Se intenta primero con los contadores de rendimiento de Windows, que son los
		que coinciden con el Administrador de tareas, y si fallan se prueban dos vias
		de respaldo.
		"""
		currGhz = None
		try:
			try:
				with self._stateLock:
					_hasCpu = bool(self._cpuQuery and self._cpuCounter)
			except Exception:
				_hasCpu = bool(getattr(self, '_cpuQuery', None) and getattr(self, '_cpuCounter', None))
			if not _hasCpu:
				self._initCpuQuery()

			with self._stateLock:
				cpuQuery = self._cpuQuery
				cpuCounter = self._cpuCounter
				lastCollect = getattr(self, '_lastCpuCollectTime', 0)
				lastValid = getattr(self, '_lastValidCpuGhz', None)
			if cpuQuery and cpuCounter:
				now = time.time()
				if now - lastCollect < 0.08:
					# Sin sleep en el hilo principal: devolver el último valor válido.
					if lastValid:
						return lastValid

				pdh = ctypes.windll.pdh
				pdh.PdhCollectQueryData(cpuQuery)
				with self._stateLock:
					self._lastCpuCollectTime = time.time()

				val = PDH_FMT_COUNTERVALUE()
				res = pdh.PdhGetFormattedCounterValue(
					cpuCounter, 0x00000200, None, byref(val)
				)
				if res == 0 and val.CStatus == 0 and val.doubleValue > 0:
					pctPerf = val.doubleValue
					currGhz = (pctPerf / 100.0) * self._baseGhz
					log.info(f"MonitorSistema: Muestra PDH CPU: {pctPerf:.1f}%, calculada={currGhz:.2f} GHz (Base={self._baseGhz} GHz, Max Turbo={self._maxTurboGhz} GHz)")
				else:
					# Recuperación automática: recrear query PDH sin bloquear (una muestra).
					self._initCpuQuery()
					with self._stateLock:
						cpuQuery = self._cpuQuery
						cpuCounter = self._cpuCounter
					if cpuQuery and cpuCounter:
						pdh.PdhCollectQueryData(cpuQuery)
						with self._stateLock:
							self._lastCpuCollectTime = time.time()
						val = PDH_FMT_COUNTERVALUE()
						res = pdh.PdhGetFormattedCounterValue(
							cpuCounter, 0x00000200, None, byref(val)
						)
						if res == 0 and val.CStatus == 0 and val.doubleValue > 0:
							currGhz = (val.doubleValue / 100.0) * self._baseGhz
		except Exception as e:
			log.error(f"MonitorSistema: Error calculando frecuencia de CPU con PDH: {e}", exc_info=True)

		# Respaldo 1: psutil.cpu_freq() en caso de fallo temporal de PDH
		if currGhz is None or currGhz <= 0:
			try:
				freq = psutil.cpu_freq()
				if freq and freq.current and freq.current > 100:
					currGhz = round(freq.current / 1000.0, 2)
			except Exception as e:
				log.debug(f"MonitorSistema: Error obteniendo psutil.cpu_freq: {e}")

		# Respaldo 2: última frecuencia válida registrada
		if currGhz is None or currGhz <= 0:
			currGhz = getattr(self, "_lastValidCpuGhz", self._baseGhz)
		else:
			self._lastValidCpuGhz = currGhz
		return currGhz


	@scriptHandler.script(
		description=_("Anuncia la velocidad y frecuencia actual del procesador (GHz), velocidad base y estado del modo turbo boost. Si se pulsa dos veces, copia la información al portapapeles."), category=scriptCategory,
		gesture="kb:nvda+shift+5",
		speakOnDemand=True,
	)
	def script_announceCpuFrequency(self, gesture: inputCore.InputGesture):
		"""Anuncia la frecuencia actual del procesador en GHz y el modo turbo."""
		try:
			info = self._getCpuFrequencyInfo()
			self._anunciarOCopiar(info, "script_announceCpuFrequency")
		except Exception as e:
			log.error(f"MonitorSistema: Error en script_announceCpuFrequency: {e}", exc_info=True)
			ui.message(_("Error al obtener la frecuencia del procesador."))

	@scriptHandler.script(
		description=_("Presenta el espacio utilizado y total de las unidades de disco fijas, extraíbles y de red. Si se pulsa dos veces, copia la información al portapapeles."), category=scriptCategory,
		gesture="kb:nvda+shift+3",
		speakOnDemand=True,
	)
	def script_announceDriveInfo(self, gesture: inputCore.InputGesture):
		"""Atajo de teclado: dice el espacio usado y libre de cada unidad de disco."""
		def _driveWorker():
			try:
				info = []
				try:
					partitions = psutil.disk_partitions(all=True)
				except Exception as pe:
					log.error(f"MonitorSistema: Error listando particiones: {pe}", exc_info=True)
					partitions = []
				localParts = []
				remoteParts = []
				for drive in partitions or []:
					try:
						fstype = getattr(drive, 'fstype', '')
						if not fstype:
							continue
						opts = (getattr(drive, 'opts', None) or '').split(',')
						if 'remote' in opts:
							remoteParts.append(drive)
						else:
							localParts.append(drive)
					except Exception:
						continue
				for drive in localParts:
					try:
						opts = (getattr(drive, 'opts', None) or '').split(',')
						isRemovable = 'removable' in opts
						try:
							driveInfo = psutil.disk_usage(drive[0])
						except (OSError, Exception):
							continue
						if isRemovable:
							driveType = _('extraible')
						else:
							driveType = _('fijo')
						info.append(
							_('{driveName} (disco {driveType}): {usedSpace} de {totalSpace} utilizados ({percent}%).').format(
								driveName=drive[0],
								driveType=driveType,
								usedSpace=size(driveInfo[1], alternative),
								totalSpace=size(driveInfo[0], alternative),
								percent=tryTrunk(driveInfo[3]),
							)
						)
					except Exception:
						continue
				for drive in remoteParts:
					try:
						info.append(_('{} (unidad de red): no disponible.').format(drive[0]))
					except Exception:
						continue
				text = ' '.join(info) if info else _('No se encontraron unidades de disco disponibles.')
				try:
					wx.CallAfter(self._anunciarOCopiar, text, 'script_announceDriveInfo')
				except Exception:
					try:
						queueHandler.queueFunction(queueHandler.eventQueue, self._anunciarOCopiar, text, 'script_announceDriveInfo')
					except Exception:
						pass
			except Exception as e:
				log.error(f"MonitorSistema: Error en script_announceDriveInfo: {e}", exc_info=True)
				try:
					wx.CallAfter(ui.message, _('Error al obtener la informacion de las unidades de disco.'))
				except Exception:
					pass
		threading.Thread(target=_driveWorker, daemon=True).start()

	def _getWlanInfo(self) -> str:
		"""Devuelve, en una frase, a qué red Wi-Fi estás conectada.

		Recorre las tarjetas inalámbricas del equipo, busca la que esté conectada y
		de ella saca el nombre de la red, la intensidad de la señal y el tipo de
		seguridad. Si no hay tarjeta, o ninguna está conectada, lo dice con esas
		mismas palabras. La memoria que pide Windows se devuelve siempre al
		terminar.
		"""
		global _ultimoSsidConocido
		try:
			with self._stateLock:
				hasHandle = self._client_handle is not None
		except Exception:
			hasHandle = bool(getattr(self, '_client_handle', None))
		if not hasHandle:
			self._ensureWlanHandle()
			try:
				with self._stateLock:
					hasHandle = self._client_handle is not None
			except Exception:
				hasHandle = bool(getattr(self, '_client_handle', None))
			if not hasHandle:
				return _("No hay dispositivos de red inalámbrica")

		wlan_ifaces = POINTER(wlanapi.WLAN_INTERFACE_INFO_LIST)()
		try:
			if wlanapi.WlanEnumInterfaces(self._client_handle, None, byref(wlan_ifaces)) != 0:
				return _("No hay dispositivos de red inalámbrica")
		except (OSError, Exception) as e:
			log.warning(f"MonitorSistema: WlanEnumInterfaces falló en _getWlanInfo: {e}")
			return _("No hay dispositivos de red inalámbrica")
		try:
			if not wlan_ifaces or not bool(wlan_ifaces) or getattr(wlan_ifaces, 'contents', None) is None or wlan_ifaces.contents.NumberOfItems == 0:
				return _("No hay dispositivos de red inalámbrica")

			info = _("No hay conexiones de red inalámbrica")
			for i in customResize(wlan_ifaces.contents.InterfaceInfo, wlan_ifaces.contents.NumberOfItems):
				if i.isState != wlanapi.wlan_interface_state_connected:
					continue

				wlan_available_network_list = POINTER(wlanapi.WLAN_AVAILABLE_NETWORK_LIST)()
				ret = None
				try:
					ret = wlanapi.WlanGetAvailableNetworkList(
						self._client_handle, byref(i.InterfaceGuid), 0, None, byref(wlan_available_network_list)
					)
				except (PermissionError, OSError) as e:
					# En Windows 11 (24H2/26H2), las consultas WLAN exigen permisos de ubicación del sistema.
					# Si la ubicación está desactivada, Windows devuelve ERROR_ACCESS_DENIED (WinError 5).
					# En Windows 10 nunca se produce esta restricción de permisos.
					log.warning(f"MonitorSistema: Acceso denegado a WlanGetAvailableNetworkList (requiere permisos de ubicación en Windows 11): {e}")
					netsh_data = self._obtenerInfoWifiNetsh()
					ssid_respaldo = _ultimoSsidConocido or netsh_data.get("ssid") or self._obtenerSsidDeRespaldo()
					if ssid_respaldo:
						_ultimoSsidConocido = ssid_respaldo
						if netsh_data.get("signal") is not None and netsh_data.get("auth"):
							log.info(f"MonitorSistema: WLAN recuperada vía netsh en Windows 11: SSID='{ssid_respaldo}', Señal={netsh_data['signal']}%, Seguridad='{netsh_data['auth']}'")
							return _("Red inalámbrica conectada: {}, intensidad de señal: {}%, tipo de seguridad: {}").format(
								ssid_respaldo,
								netsh_data["signal"],
								netsh_data["auth"],
							)
						return _(
							"Red inalámbrica conectada: {}. Intensidad de señal y seguridad no disponibles (en Windows 11 activa los servicios de ubicación en Configuración > Privacidad y seguridad > Ubicación)."
						).format(ssid_respaldo)
					return _(
						"No se pudo obtener información de la red inalámbrica: en Windows 11 activa los servicios de ubicación en Configuración > Privacidad y seguridad > Ubicación."
					)
				except Exception as e:
					log.error(f"MonitorSistema: Error inesperado en WlanGetAvailableNetworkList: {e}", exc_info=True)
					continue

				if ret == 0:
					try:
						if wlan_available_network_list and bool(wlan_available_network_list) and getattr(wlan_available_network_list, 'contents', None) is not None and wlan_available_network_list.contents.NumberOfItems > 0:
							for n in customResize(
								wlan_available_network_list.contents.Network,
								wlan_available_network_list.contents.NumberOfItems,
							):
								if n.Flags & wlanapi.WLAN_AVAILABLE_NETWORK_CONNECTED:
									ssid_str = _extraerSsid(n.dot11Ssid)
									_ultimoSsidConocido = ssid_str
									sec_str = SECURITY_TYPE.get(n.dot11DefaultAuthAlgorithm, _("Desconocido"))
									log.info(f"MonitorSistema: Conexión WLAN activa detectada: SSID='{ssid_str}', Señal={n.wlanSignalQuality}%, Seguridad='{sec_str}'")
									info = (
										_("Red inalámbrica conectada: {}, intensidad de señal: {}%, tipo de seguridad: {}")
									).format(
										ssid_str,
										n.wlanSignalQuality,
										sec_str,
									)
									break
					finally:
						try:
							if wlan_available_network_list and bool(wlan_available_network_list):
								wlanapi.WlanFreeMemory(wlan_available_network_list)
						except Exception:
							pass
			return info
		finally:
			try:
				if wlan_ifaces and bool(wlan_ifaces):
					wlanapi.WlanFreeMemory(wlan_ifaces)
			except Exception:
				pass

	def _obtenerInfoWifiNetsh(self) -> dict:
		"""Consulta el estado, SSID, señal y seguridad Wi-Fi vía netsh wlan.

		En Windows 11 (24H2+), Native WiFi (WlanGetAvailableNetworkList) exige
		permisos de ubicación del sistema. Si están desactivados, netsh sigue
		teniendo acceso y devuelve SSID, porcentaje de señal y protocolo de seguridad.
		"""
		info = {"ssid": None, "signal": None, "auth": None, "connected": False}
		try:
			creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
			res = subprocess.run(
				["netsh", "wlan", "show", "interfaces"],
				capture_output=True,
				creationflags=creationflags,
				timeout=3,
			)
			if res.returncode != 0 or not res.stdout:
				return info
			text = ""
			for enc in ("oem", "utf-8", "cp1252"):
				try:
					text = res.stdout.decode(enc)
					break
				except Exception:
					pass
			if not text:
				text = res.stdout.decode("latin-1", errors="ignore")
			for line in text.splitlines():
				if ":" not in line:
					continue
				k, v = line.split(":", 1)
				k_clean = k.strip().lower()
				v_clean = v.strip()
				if k_clean == "ssid":
					info["ssid"] = v_clean
				elif any(sub in k_clean for sub in ("se", "signal", "sin", "segn")):
					m = re.search(r"(\d+)\s*%", v_clean)
					if m:
						info["signal"] = int(m.group(1))
				elif any(sub in k_clean for sub in ("auth", "autentic")):
					info["auth"] = v_clean
				elif any(sub in k_clean for sub in ("estado", "state", "status", "stat")):
					info["connected"] = any(c in v_clean.lower() for c in ("con", "verb", "assoc"))
		except Exception as e:
			log.debug(f"MonitorSistema: Error consultando netsh wlan show interfaces: {e}")
		return info

	def _obtenerSsidDeRespaldo(self) -> str | None:
		"""Obtiene el nombre de la red Wi-Fi activa sin depender de Native WiFi.

		En Windows 11, si la ubicación está desactivada, WlanGetAvailableNetworkList
		falla por denegación de permisos. El perfil de conexión del sistema sí conoce
		el SSID de la red conectada.
		"""
		try:
			creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
			res = subprocess.run(
				["powershell", "-NoProfile", "-Command", "(Get-NetConnectionProfile -InterfaceAlias '*Wi-Fi*').Name"],
				capture_output=True,
				text=True,
				creationflags=creationflags,
				timeout=2,
			)
			if res.returncode == 0:
				lineas = res.stdout.strip().splitlines()
				if lineas and lineas[0].strip():
					return lineas[0].strip()
		except Exception as e:
			log.debug(f"MonitorSistema: No se pudo obtener SSID de respaldo: {e}")
		return None

	def _getCurrentWlanSignalCached(self) -> int | None:
		"""Señal Wi-Fi con caché de 15 s para no saturar Native WiFi en el bucle."""
		try:
			now = time.time()
			cached = getattr(self, '_wlanSignalCache', None)
			cachedTime = float(getattr(self, '_wlanSignalCacheTime', 0.0) or 0.0)
			if cached is not None and (now - cachedTime) < 15.0:
				return cached
		except Exception:
			pass
		val = self._getCurrentWlanSignal()
		try:
			with self._stateLock:
				self._wlanSignalCache = val
				self._wlanSignalCacheTime = time.time()
		except Exception:
			pass
		return val

	def _getCurrentWlanSignal(self) -> int | None:
		"""Devuelve solo el número de la intensidad de señal del Wi-Fi, de 0 a 100.

		Es la versión corta y callada de la consulta anterior, la que usa el
		vigilante para notar cuándo cambia la señal. Devuelve None si no hay
		tarjeta, si no hay conexión o si algo falla, y en ningún caso habla.
		"""
		try:
			with self._stateLock:
				hasHandle = self._client_handle is not None
		except Exception:
			hasHandle = bool(getattr(self, '_client_handle', None) is not None)
		if not hasHandle:
			self._ensureWlanHandle()
			try:
				with self._stateLock:
					hasHandle = self._client_handle is not None
			except Exception:
				hasHandle = bool(getattr(self, '_client_handle', None) is not None)
			if not hasHandle:
				return None
		try:
			wlan_ifaces = POINTER(wlanapi.WLAN_INTERFACE_INFO_LIST)()
			try:
				with self._stateLock:
					handle = self._client_handle
			except Exception:
				handle = getattr(self, '_client_handle', None)
			if wlanapi.WlanEnumInterfaces(handle, None, byref(wlan_ifaces)) != 0:
				return None
			try:
				if not wlan_ifaces or not bool(wlan_ifaces) or getattr(wlan_ifaces, 'contents', None) is None or wlan_ifaces.contents.NumberOfItems == 0:
					return None
				signal = None
				for i in customResize(wlan_ifaces.contents.InterfaceInfo, wlan_ifaces.contents.NumberOfItems):
					if i.isState != wlanapi.wlan_interface_state_connected:
						continue
					wlan_available_network_list = POINTER(wlanapi.WLAN_AVAILABLE_NETWORK_LIST)()
					ret = None
					try:
						ret = wlanapi.WlanGetAvailableNetworkList(
							self._client_handle, byref(i.InterfaceGuid), 0, None, byref(wlan_available_network_list)
						)
					except (PermissionError, OSError) as e:
						log.debug(f"MonitorSistema: Señal WLAN no accesible en Native WiFi por permisos de ubicación en Windows 11 ({e}), intentando netsh...")
						sig_respaldo = self._obtenerInfoWifiNetsh().get("signal")
						if sig_respaldo is not None:
							return sig_respaldo
						return None
					except Exception as e:
						log.error(f"MonitorSistema: Error inesperado consultando señal WLAN: {e}")
						return None

					if ret == 0:
						try:
							for n in customResize(
								wlan_available_network_list.contents.Network,
								wlan_available_network_list.contents.NumberOfItems,
							):
								if n.Flags & wlanapi.WLAN_AVAILABLE_NETWORK_CONNECTED:
									signal = int(n.wlanSignalQuality)
									break
						finally:
							try:
								if wlan_available_network_list and bool(wlan_available_network_list):
									wlanapi.WlanFreeMemory(wlan_available_network_list)
							except Exception:
								pass
					if signal is not None:
						break
				return signal
			finally:
				try:
					if wlan_ifaces and bool(wlan_ifaces):
						wlanapi.WlanFreeMemory(wlan_ifaces)
				except Exception:
					pass
		except Exception as e:
			log.error(f"MonitorSistema: Error consultando señal WLAN: {e}", exc_info=True)
			return None

	@scriptHandler.script(
		description=_("Anuncia el nombre de la red inalámbrica (SSID), intensidad de la señal y protocolo de seguridad. Si se pulsa dos veces, copia la información al portapapeles."),
		gesture="kb:nvda+shift+4",
		speakOnDemand=True,
		category=scriptCategory,
	)
	def script_wlanStatusReport(self, gesture: inputCore.InputGesture):
		"""Verbaliza el estado de la conexión Wi-Fi actual y la intensidad de la señal."""
		try:
			info = self._getWlanInfo()
			self._anunciarOCopiar(info, "script_wlanStatusReport")
		except Exception as e:
			log.error(f"MonitorSistema: Error en script_wlanStatusReport: {e}", exc_info=True)
			ui.message(_("Error al obtener el estado de la red inalámbrica."))

	@scriptHandler.script(
		description=_("Anuncia la versión de Windows y arquitectura del sistema. Si se pulsa dos veces, copia la información al portapapeles."),
		gesture="kb:nvda+shift+6",
		speakOnDemand=True,
		category=scriptCategory,
	)
	def script_announceWinVer(self, gesture: inputCore.InputGesture):
		"""Anuncia la versión exacta y edición de Windows instalada en el equipo."""
		try:
			info = getWinVer()
			self._anunciarOCopiar(info, "script_announceWinVer")
		except Exception as e:
			log.error(f"MonitorSistema: Error en script_announceWinVer: {e}", exc_info=True)
			ui.message(_("Error al obtener la versión de Windows."))

	def getUptime(self) -> str:
		"""Calcula y formatea el tiempo transcurrido desde el último inicio del sistema."""
		totalSecs = 0
		# Primario: GetTickCount64 (monotónico, no le afecta el cambio de hora).
		try:
			GetTickCount64 = getattr(ctypes.windll.kernel32, "GetTickCount64", None)
			if GetTickCount64:
				GetTickCount64.restype = ctypes.c_ulonglong
				totalSecs = int(GetTickCount64() // 1000)
		except Exception:
			pass
		# Respaldo: psutil.boot_time() si el contador no está disponible.
		if totalSecs <= 0:
			try:
				bootTimestamp = psutil.boot_time()
				if bootTimestamp and bootTimestamp > 0.0:
					uptime = datetime.now() - datetime.fromtimestamp(bootTimestamp)
					totalSecs = int(uptime.total_seconds())
			except Exception:
				pass
		if totalSecs <= 0:
			# Translators: Mensaje cuando el tiempo de actividad es inferior a un segundo por desfase horario o arranque inmediato.
			return _("menos de un segundo")
		days, remSecs = divmod(totalSecs, 86400)
		hours, remMins = divmod(remSecs, 3600)
		minutes, seconds = divmod(remMins, 60)
		uptimeComponents = []
		if days > 0:
			# Translators: Formato de días de actividad (singular o plural).
			uptimeComponents.append(_("{count} día").format(count=days) if days == 1 else _("{count} días").format(count=days))
		if hours > 0:
			# Translators: Formato de horas de actividad (singular o plural).
			uptimeComponents.append(_("{count} hora").format(count=hours) if hours == 1 else _("{count} horas").format(count=hours))
		if minutes > 0:
			# Translators: Formato de minutos de actividad (singular o plural).
			uptimeComponents.append(_("{count} minuto").format(count=minutes) if minutes == 1 else _("{count} minutos").format(count=minutes))
		# Translators: Formato de segundos de actividad (singular o plural).
		uptimeComponents.append(_("{count} segundo").format(count=seconds) if seconds == 1 else _("{count} segundos").format(count=seconds))
		res = ", ".join(uptimeComponents)
		log.info(f"MonitorSistema: Tiempo de actividad calculado ({totalSecs}s): {res}")
		return res

	@scriptHandler.script(
		description=_("Anuncia el tiempo de actividad del sistema. Si se pulsa dos veces, copia la información al portapapeles."),
		gesture="kb:nvda+shift+7",
		speakOnDemand=True,
		category=scriptCategory,
	)
	def script_announceUptime(self, gesture: inputCore.InputGesture):
		"""Anuncia el tiempo de actividad del sistema o el tiempo total si se pulsa dos veces."""
		try:
			uptime = self.getUptime()
			self._anunciarOCopiar(uptime, "script_announceUptime")
		except Exception as e:
			log.error(f"MonitorSistema: Error en script_announceUptime: {e}", exc_info=True)
			ui.message(_("No se pudo obtener el tiempo de actividad del sistema."))

	def _getGpuInfo(self) -> str:
		"""Devuelve, en una frase, la memoria y la carga de la tarjeta gráfica.

		Prueba los distintos fabricantes por orden y se queda con el primero que dé
		datos; si hay varias tarjetas, las numera. Distingue tres situaciones que
		no son lo mismo y que antes se confundían: que no haya ninguna tarjeta que
		sepa informar, que la haya pero no responda, y que responda sin datos.
		"""
		hasProvider = False
		hasFailure = False
		try:
			with self._stateLock:
				providers = list(getattr(self, '_gpuProviders', []) or [])
		except Exception:
			providers = []
		for provider in providers:
			telemetry = provider.collect()
			if telemetry is None:
				continue
			hasProvider = True
			if not telemetry:
				hasFailure = True
				continue
			gpuInfoParts = []
			is_single = len(telemetry) == 1
			for index, item in enumerate(telemetry, start=1):
				memPart = formatGpuMemory(item.memoryUsed, item.memoryTotal)
				prefix = _("GPU:") if is_single else _("GPU {}:").format(index)

				if memPart:
					msg = _("{prefix} memoria {mem}, carga del procesador gráfico: {util}%.").format(
						prefix=prefix, mem=memPart, util=item.utilization
					)
				else:
					msg = _("{prefix} carga del procesador gráfico: {util}%.").format(
						prefix=prefix, util=item.utilization
					)
				gpuInfoParts.append(msg)
			if gpuInfoParts:
				return " ".join(gpuInfoParts)
			hasFailure = True
		if not hasProvider:
			return _("No hay información de la tarjeta gráfica disponible.")
		if hasFailure:
			return _("No se pudo obtener información de la tarjeta gráfica.")
		return _("No hay datos de la tarjeta gráfica disponibles.")

	@scriptHandler.script(
		description=_("Anuncia la memoria utilizada, total y carga del procesador gráfico (GPU). Si se pulsa dos veces, copia la información al portapapeles."),
		category=scriptCategory,
		gesture="kb:nvda+shift+8",
		speakOnDemand=True,
	)
	@blockAction.when(blockAction.Context.SECURE_MODE)
	def script_announceGpuInfo(self, gesture: inputCore.InputGesture):
		"""Anuncia el uso, temperatura y consumo de memoria de la tarjeta gráfica."""
		try:
			info = self._getGpuInfo()
			self._anunciarOCopiar(info, "script_announceGpuInfo")
		except Exception as e:
			log.error(f"MonitorSistema: Error en script_announceGpuInfo: {e}", exc_info=True)
			ui.message(_("Error al obtener información de la tarjeta gráfica."))

	def _getDiskHealth(self):
		"""Lanza en segundo plano la consulta del estado de los discos."""
		if not self._tryStartOp("diskHealth", "_diskHealthRunning"):
			return
		ui.message(_("Analizando discos, por favor espera..."))
		threading.Thread(target=self._hiloDeSaludDeDiscos, daemon=True).start()

	def _hiloDeSaludDeDiscos(self):
		"""Consulta el estado de los discos y lo anuncia."""
		stop_event = self._startProgressBeeper(440)
		log.info("MonitorSistema: Iniciando escaneo elevado de salud de discos...")
		try:
			output = self._consultarDiscosConPowerShell()
			if output is None:
				return
			if not output:
				log.warning("MonitorSistema: Salida de Get-PhysicalDisk vacía.")
				err_msg = _("No se pudo obtener información de los discos.")
				wx.CallAfter(ui.message, err_msg)
				return
				
			data = json.loads(output)
			if isinstance(data, dict):
				data = [data]
			elif not isinstance(data, list):
				data = []
			log.info(f"MonitorSistema: Discos detectados ({len(data)}): {data}")
			
			result = self._resumenDeDiscos(data)
			self._lastDiskHealthResult = result
			log.info(f"MonitorSistema: Anunciando salud de discos: {result}")
			wx.CallAfter(ui.message, result)
			if getattr(self, "_copyDiskHealthOnFinish", False):
				self._copyDiskHealthOnFinish = False
				wx.CallAfter(self._safeCopyToClip, result)
		except Exception as e:
			log.error(f"MonitorSistema: Error en worker de salud de discos: {e}", exc_info=True)
			wx.CallAfter(ui.message, _("Error al consultar discos."))
		finally:
			self._finishOp("diskHealth", "_diskHealthRunning")
			stop_event.set()

	def _limpiarTemporalesViejos(self, maxAgeHours: float = 1.0) -> None:
		"""Borra nvda_disk_health_*.json de más de 1 h en el temporal."""
		try:
			tmpdir = tempfile.gettempdir()
			now = time.time()
			for _name in os.listdir(tmpdir):
				if not _name.startswith("nvda_disk_health_") or not _name.endswith(".json"):
					continue
				_p = os.path.join(tmpdir, _name)
				try:
					if (now - os.path.getmtime(_p)) > (maxAgeHours * 3600.0):
						try:
							os.remove(_p)
						except Exception:
							pass
				except Exception:
					continue
		except Exception:
			pass

	def _borrarTemporalConReintento(self, path: str, intentos: int = 5) -> None:
		"""Borra un temporal con reintentos (el elevado puede retenerlo brevemente)."""
		for _i in range(max(1, intentos)):
			try:
				if os.path.exists(path):
					os.remove(path)
				return
				return
			except (PermissionError, OSError):
				try:
					if hasattr(self, '_stopAlertsEvent') and self._stopAlertsEvent.is_set():
						return
				except Exception:
					pass
				time.sleep(0.2)
			except Exception:
				return

	def _consultarDiscosConPowerShell(self):
		"""Pide a Windows, con permisos de administrador, el estado de los discos.

		Devuelve el texto que escribio PowerShell, o None si no llego a escribirlo
		(normalmente porque se rechazo el permiso de administrador). En ese caso ya
		ha avisado por voz.
		"""
		try:
			self._limpiarTemporalesViejos(maxAgeHours=1.0)
		except Exception:
			pass
		try:
			_tf = tempfile.NamedTemporaryFile(prefix="nvda_disk_health_", suffix=".json", delete=False)
			tmp_file = _tf.name
			_tf.close()
			# NamedTemporaryFile crea el archivo vacío; lo borramos para que el elevado lo recree.
			try:
				os.remove(tmp_file)
			except Exception:
				pass
		except Exception:
			tmp_file = os.path.join(tempfile.gettempdir(), f"nvda_disk_health_{os.getpid()}_{int(time.time() * 1000)}.json")
		
		tmp_file_esc = tmp_file.replace("'", "''")
		ps_script = f"""
		$ErrorActionPreference = 'SilentlyContinue'
		$disks = Get-PhysicalDisk
		$results = @()
		foreach ($d in $disks) {{
			$rel = $d | Get-StorageReliabilityCounter
			$results += [PSCustomObject]@{{
				Name = $d.FriendlyName
				Type = $d.MediaType
				Health = $d.HealthStatus
				Temp = $rel.Temperature
				Wear = $rel.Wear
			}}
		}}
		$results | ConvertTo-Json -Compress | Out-File -FilePath '{tmp_file_esc}' -Encoding UTF8
		"""
		encoded = base64.b64encode(ps_script.encode('utf-16le')).decode('utf-8')
		log.info("MonitorSistema: Lanzando PowerShell con ShellExecuteW...")
		resultado = ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", f"-NoProfile -WindowStyle Hidden -EncodedCommand {encoded}", None, 0)
		if resultado <= 32:
			log.info("MonitorSistema: ShellExecuteW no inició PowerShell elevado; intentando consulta no elevada de respaldo...")
			try:
				disks_silent = self._queryDiskHealthSilent()
				if disks_silent:
					transformed = []
					for d in disks_silent:
						transformed.append({
							"Name": d.get("FriendlyName"),
							"Type": d.get("MediaType"),
							"Health": d.get("HealthStatus"),
							"Wear": d.get("Wear"),
						})
					return json.dumps(transformed)
			except Exception as se:
				log.debug(f"MonitorSistema: Error en consulta no elevada de respaldo: {se}")
			log.warning(f"MonitorSistema: ShellExecuteW no pudo iniciar PowerShell (código {resultado}).")
			err_msg = _("No se pudo obtener información de los discos o se canceló el permiso de administrador.")
			wx.CallAfter(ui.message, err_msg)
			return None

		timeout = 15
		while timeout > 0:
			if os.path.exists(tmp_file):
				time.sleep(0.5)
				break
			time.sleep(1)
			timeout -= 1

		if not os.path.exists(tmp_file):
			log.info("MonitorSistema: UAC no completado o archivo temporal no encontrado; intentando consulta no elevada de respaldo...")
			try:
				disks_silent = self._queryDiskHealthSilent()
				if disks_silent:
					transformed = []
					for d in disks_silent:
						transformed.append({
							"Name": d.get("FriendlyName"),
							"Type": d.get("MediaType"),
							"Health": d.get("HealthStatus"),
							"Wear": d.get("Wear"),
						})
					return json.dumps(transformed)
			except Exception as se:
				log.debug(f"MonitorSistema: Error en consulta no elevada de respaldo: {se}")
			log.warning("MonitorSistema: Archivo no encontrado, UAC rechazado o expiró el tiempo de espera.")
			err_msg = _("No se pudo obtener información de los discos o se canceló el permiso de administrador.")
			wx.CallAfter(ui.message, err_msg)
			return None

		output = ""
		try:
			for _intento in range(5):
				try:
					with open(tmp_file, 'r', encoding='utf-8-sig', errors='replace') as f:
						output = f.read().strip()
					if output:
						break
				except (PermissionError, OSError):
					time.sleep(0.3)
				except Exception as e:
					log.error(f"MonitorSistema: Error leyendo archivo temporal de discos: {e}", exc_info=True)
					break
		finally:
			try:
				self._borrarTemporalConReintento(tmp_file)
			except Exception:
				pass
		return output

	def _resumenDeDiscos(self, data):
		"""Convierte los datos de los discos en la frase que se lee en voz alta."""
		if not isinstance(data, (list, tuple)):
			return _("No se encontraron discos.")
		parts = []
		for disk in data:
			if not isinstance(disk, dict):
				continue
			name = disk.get("Name") or _("Disco desconocido")
			name = "".join(ch for ch in str(name) if ch.isprintable() or ch in " \t") or _("Disco desconocido")
			dtype_raw = str(disk.get("Type") or "").strip()
			health_raw = str(disk.get("Health") or "").strip()
			if dtype_raw.upper() == "SSD":
				dtype = _("estado sólido (SSD)")
			elif dtype_raw.upper() == "HDD":
				dtype = _("rígido (HDD)")
			else:
				dtype = dtype_raw or _("Desconocido")

			if health_raw.lower() == "healthy":
				health = _("Saludable")
			elif health_raw.lower() == "warning":
				health = _("En riesgo (Advertencia)")
			elif health_raw.lower() == "unhealthy":
				health = _("Dañado (Crítico)")
			else:
				health = health_raw or _("Desconocido")
			
			wear = disk.get("Wear")
			part = _("Disco {}: Tipo {}. Estado general: {}.").format(name, dtype, health)
			if wear is not None and dtype_raw.upper() == "SSD":
				try:
					clean_wear = str(wear).replace("%", "").strip()
					wear_int = int(round(float(clean_wear)))
					wear_int = max(0, min(100, wear_int))
					health_pct = 100 - wear_int
					part += " " + _("Desgaste de vida útil: {} por ciento (Salud: {}%).").format(wear_int, health_pct)
				except (ValueError, TypeError, OverflowError):
					pass
			parts.append(part)
			
		result = " ".join(parts) if parts else _("No se encontraron discos.")
		return result


	@staticmethod
	def _safeCopyToClip(text: str) -> bool:
		"""Copia texto al portapapeles de forma segura, tolerando bloqueos temporales de Windows."""
		if not text:
			return False
		try:
			return bool(api.copyToClip(text, notify=True))
		except Exception as e:
			log.warning(f"MonitorSistema: No se pudo copiar al portapapeles: {e}")
			try:
				ui.message(_("No se pudo copiar al portapapeles."))
			except Exception:
				pass
			return False

	def _anunciarOCopiar(self, texto: str, nombre_script: str = "") -> None:
		"""Anuncia texto por voz o lo copia al portapapeles según las pulsaciones del atajo.

		Primera pulsación: NVDA lee el texto en voz alta.
		Segunda pulsación consecutiva: copia el texto al portapapeles y notifica.

		Este helper centraliza el patrón getLastScriptRepeatCount() == 0 que se
		repetía en ocho scripts distintos, eliminando tanto la duplicación como el
		bug de doble llamada que tenía script_wlanStatusReport (antes llamaba a
		_getWlanInfo() dos veces en la rama else).
		"""
		if scriptHandler.getLastScriptRepeatCount() == 0:
			log.info(f"MonitorSistema: {nombre_script} - Anunciando al usuario: '{texto}'")
			ui.message(texto)
		else:
			log.info(f"MonitorSistema: {nombre_script} - Copiando al portapapeles: '{texto}'")
			self._safeCopyToClip(texto)

	def _atajoDeConsulta(self, nombreEnCurso, nombreUltimoResultado, nombreCopiarAlTerminar, lanzarConsulta, mensajeEnCurso):
		"""Lógica común de los atajos que consultan algo del sistema.

		Pulsado una vez: lanza la consulta (o avisa si ya está en curso).
		Pulsado dos veces seguidas: copia el resultado al portapapeles, y si todavía
		no hay resultado, deja pedido que se copie en cuanto termine.

		Los tres primeros parámetros son los nombres de las variables donde cada
		atajo guarda su estado; se pasan como texto porque cada consulta tiene las
		suyas.
		"""
		if scriptHandler.getLastScriptRepeatCount() > 0:
			if getattr(self, nombreEnCurso, False):
				setattr(self, nombreCopiarAlTerminar, True)
				ui.message(_("Se copiará el resultado al portapapeles."))
				return
			ultimoResultado = getattr(self, nombreUltimoResultado, None)
			if ultimoResultado:
				self._safeCopyToClip(ultimoResultado)
				return
			setattr(self, nombreCopiarAlTerminar, True)
			ui.message(_("Se copiará el resultado al portapapeles."))
			lanzarConsulta()
			return
		if getattr(self, nombreEnCurso, False):
			ui.message(mensajeEnCurso)
			return
		setattr(self, nombreCopiarAlTerminar, False)
		lanzarConsulta()

	@scriptHandler.script(
		description=_("Anuncia el estado de salud (S.M.A.R.T) y la vida útil de los discos físicos. Si se pulsa dos veces, copia la información al portapapeles."),
		category=scriptCategory,
		gesture="kb:nvda+shift+control+1",
		speakOnDemand=True,
	)
	def script_announceDiskHealth(self, gesture: inputCore.InputGesture):
		"""Consulta e informa el estado de salud, desgaste y temperatura de las unidades de disco."""
		self._atajoDeConsulta(
			"_diskHealthRunning", "_lastDiskHealthResult", "_copyDiskHealthOnFinish",
			self._getDiskHealth,
			_("El análisis de discos ya está en curso, por favor espera..."),
		)

	def _getTopProcesses(self):
		"""Atajo de teclado: busca qué programa consume más procesador y cuál más memoria.

		Avisa de que está analizando y hace el trabajo en un hilo aparte, porque
		recorrer todos los programas abiertos tarda algo más de medio segundo y
		NVDA se quedaría trabado.
		"""
		if not self._tryStartOp("topProcesses", "_topProcessesRunning"):
			return
		def worker():
			"""Recorre los programas abiertos y se queda con los dos más grandes.

			La primera pasada solo sirve para que Windows empiece a medir; los datos
			buenos llegan medio segundo después, en la segunda. No cuenta el "System
			Idle Process", que no es un programa sino el hueco que el procesador deja
			sin usar. Al terminar dice el resultado y, si se pidió, lo copia.
			"""
			log.info("MonitorSistema: Iniciando análisis de Top Procesos...")
			try:
				for p in psutil.process_iter(['name', 'cpu_percent']): pass
				time.sleep(0.5)
				max_cpu, max_cpu_p, max_mem, max_mem_p = -1, None, -1, None
				for p in psutil.process_iter(['name', 'cpu_percent', 'memory_info']):
					try:
						info = p.info
						if not isinstance(info, dict):
							continue
						cpu = info.get('cpu_percent')
						minfo = info.get('memory_info')
						mem = getattr(minfo, 'rss', None) if minfo else None
						name = info.get('name')
						if cpu is not None and name != "System Idle Process":
							try:
								cpu_f = float(cpu)
								if not math.isnan(cpu_f) and not math.isinf(cpu_f) and cpu_f > max_cpu:
									max_cpu, max_cpu_p = cpu_f, name
							except (ValueError, TypeError):
								pass
						if mem is not None:
							try:
								mem_f = float(mem)
								if not math.isnan(mem_f) and not math.isinf(mem_f) and mem_f > max_mem:
									max_mem, max_mem_p = mem_f, name
							except (ValueError, TypeError):
								pass
					except (psutil.Error, OSError, AttributeError, KeyError, ValueError, TypeError): pass
				log.info(f"MonitorSistema: Top procesos detectados - Mayor CPU: '{max_cpu_p}' ({round(max_cpu, 1)}%), Mayor RAM: '{max_mem_p}' ({size(max_mem, alternative) if max_mem else '0'})")
				res = []
				if max_cpu_p: res.append(_("Proceso con más CPU: {} ({}%).").format(max_cpu_p, round(max_cpu, 1)))
				if max_mem_p: res.append(_("Proceso con más RAM: {} ({} MB).").format(max_mem_p, round(max_mem / 1024 / 1024)))
				msg = " ".join(res) if res else _("No se pudieron obtener los procesos.")
				self._lastTopProcessesResult = msg
				log.info(f"MonitorSistema: Top Procesos calculados: {msg}")
			except Exception as e:
				log.error(f"MonitorSistema: Error analizando procesos: {e}", exc_info=True)
				msg = _("Error analizando procesos.")
			finally:
				self._finishOp("topProcesses", "_topProcessesRunning")
			wx.CallAfter(ui.message, msg)
			if getattr(self, "_copyTopProcessesOnFinish", False):
				self._copyTopProcessesOnFinish = False
				wx.CallAfter(self._safeCopyToClip, msg)
		ui.message(_("Analizando procesos..."))
		threading.Thread(target=worker, daemon=True).start()

	@scriptHandler.script(
		description=_("Anuncia los procesos que más CPU y RAM consumen actualmente. Si se pulsa dos veces, copia la información al portapapeles."),
		category=scriptCategory,
		gesture="kb:nvda+shift+control+2",
		speakOnDemand=True,
	)
	def script_announceTopProcesses(self, gesture: inputCore.InputGesture):
		"""Identifica y verbaliza los procesos en ejecución con mayor consumo de CPU o memoria."""
		self._atajoDeConsulta(
			"_topProcessesRunning", "_lastTopProcessesResult", "_copyTopProcessesOnFinish",
			self._getTopProcesses,
			_("El análisis de procesos ya está en curso, por favor espera..."),
		)

	def _getNetworkSpeed(self):
		"""Lanza la prueba de velocidad en segundo plano."""
		if not self._tryStartOp("netSpeed", "_netSpeedRunning"):
			return
		ui.message(_("Realizando prueba de precisión (unos 12 segundos), por favor espera..."))
		threading.Thread(target=self._hiloDeVelocidadDeRed, daemon=True).start()

	def _hiloDeVelocidadDeRed(self):
		"""Mide latencia, descarga y subida, y anuncia el resultado."""
		stop_event = self._startProgressBeeper(880)
		log.info("MonitorSistema: Iniciando Speedtest de red...")
		msg = _("Error al medir la velocidad de Internet.")
		try:
			ping_val = self._medirLatencia()
			dl_speed = self._medirVelocidadDeDescarga()
			up_speed = self._medirVelocidadDeSubida()
			clean_dl = max(0.0, dl_speed) if (isinstance(dl_speed, (int, float)) and not math.isnan(dl_speed) and not math.isinf(dl_speed)) else 0.0
			clean_up = max(0.0, up_speed) if (isinstance(up_speed, (int, float)) and not math.isnan(up_speed) and not math.isinf(up_speed)) else 0.0
			if ping_val:
				msg = _("Velocidad de Internet. Latencia: {} milisegundos. Descarga: {} Megabytes por segundo. Subida: {} Megabytes por segundo.").format(ping_val, round(clean_dl, 1), round(clean_up, 1))
			else:
				msg = _("Velocidad de Internet. Descarga: {} Megabytes por segundo. Subida: {} Megabytes por segundo.").format(round(clean_dl, 1), round(clean_up, 1))
			self._lastNetSpeedResult = msg
		except Exception as e: 
			err_str = str(e)
			log.error(f"MonitorSistema: Error en speedtest: {e}", exc_info=True)
			if "429" in err_str:
				msg = _("El servidor bloqueó la prueba por hacerla muchas veces seguidas. Espera unos minutos y vuelve a intentarlo.")
			elif "11001" in err_str or "getaddrinfo" in err_str.lower() or "urlerror" in err_str.lower() or "timed out" in err_str.lower():
				msg = _("No se pudo conectar a Internet para medir la velocidad. Comprueba tu conexión.")
			else:
				msg = _("Error al medir la velocidad de Internet.")
		finally:
			self._finishOp("netSpeed", "_netSpeedRunning")
			stop_event.set()
		log.info(f"MonitorSistema: Anunciando velocidad de Internet: '{msg}'")
		wx.CallAfter(ui.message, msg)
		if getattr(self, "_copyNetSpeedOnFinish", False):
			self._copyNetSpeedOnFinish = False
			wx.CallAfter(self._safeCopyToClip, msg)

	def _medirLatencia(self):
		"""Milisegundos que tarda en ir y volver un paquete, o None si no se pudo."""
		ping_val = None
		try:
			creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
			res_ping = subprocess.run(
				["ping", "-n", "2", "-w", "1000", "1.1.1.1"],
				capture_output=True,
				text=True,
				creationflags=creationflags,
				# Dos intentos de un segundo tardan tres a lo sumo. Sin este limite,
				# un ping que se cuelga deja la prueba de velocidad sin terminar.
				timeout=10,
			)
			stdout_str = res_ping.stdout or ""
			m = (
				re.search(r'Media = (\d+)ms', stdout_str, re.IGNORECASE)
				or re.search(r'Average = (\d+)ms', stdout_str, re.IGNORECASE)
				or re.search(r'tiempo[=<](\d+)ms', stdout_str, re.IGNORECASE)
				or re.search(r'time[=<](\d+)ms', stdout_str, re.IGNORECASE)
			)
			if m:
				ping_val = m.group(1)
				log.info(f"MonitorSistema: Latencia medida: {ping_val} ms")
			else:
				log.warning(f"MonitorSistema: No se pudo extraer la latencia del ping a 1.1.1.1: {stdout_str.strip()}")
		except Exception as ping_err:
			log.warning(f"MonitorSistema: Error midiendo ping: {ping_err}")
		return ping_val

	def _medirVelocidadDeDescarga(self):
		"""Megabytes por segundo bajando un archivo de prueba.

		Descarta el primer segundo, mientras la conexion se pone a tono, para que
		el arranque lento no rebaje el resultado.
		"""
		start_down = time.time()
		dl_bytes = 0
		total_dl_bytes = 0
		measure_start_d = start_down
		warmed_up = False
		
		ssl_ctx = ssl.create_default_context()

		req_d = urllib.request.Request("https://cachefly.cachefly.net/100mb.test", headers={'User-Agent': 'Mozilla/5.0'})
		with urllib.request.urlopen(req_d, timeout=5, context=ssl_ctx) as res_d:
			while True:
				chunk = res_d.read(1024 * 256)
				if not chunk: break
				now = time.time()
				dl_bytes += len(chunk)
				total_dl_bytes += len(chunk)
				if not warmed_up and (now - start_down) >= 1.5:
					warmed_up = True
					measure_start_d = now
					dl_bytes = 0
				if (now - start_down) >= 6.0: break
		
		dl_time = time.time() - measure_start_d
		if dl_time < 1.0:
			dl_time = time.time() - start_down
			dl_bytes = total_dl_bytes
			
		if dl_time <= 0: dl_time = 0.001
		dl_speed = (dl_bytes / dl_time) / 1048576
		log.info(f"MonitorSistema: Descarga finalizada: {round(dl_speed, 2)} MB/s ({total_dl_bytes} bytes en {round(dl_time, 2)}s)")
		return dl_speed

	def _medirVelocidadDeSubida(self):
		"""Megabytes por segundo subiendo datos generados al vuelo."""
		class UploadStream:
			"""Generador de flujo continuo en memoria para medir la tasa de carga de red."""
			def __init__(self):
				self.start = time.time()
				self.measure_start = None
				self.sent = 0
				self.chunk = os.urandom(1024 * 256)
			def __iter__(self): return self
			def __next__(self):
				now = time.time()
				if now - self.start >= 6.0: raise StopIteration
				if now - self.start >= 1.5:
					if self.measure_start is None:
						self.measure_start = now
					else:
						self.sent += len(self.chunk)
				return self.chunk
				
		url_up = "https://speed.cloudflare.com/__up"
		stream = UploadStream()
		req_u = urllib.request.Request(url_up, data=stream, headers={'User-Agent': 'Mozilla/5.0'})
		try:
			ssl_ctx = ssl.create_default_context()
			urllib.request.urlopen(req_u, timeout=5, context=ssl_ctx)
		except Exception as up_err:
			log.debug(f"MonitorSistema: Cierre de stream de subida: {up_err}")
		
		if stream.measure_start is None: stream.measure_start = stream.start
		up_time = time.time() - stream.measure_start
		if up_time <= 0: up_time = 0.001
		up_speed = (stream.sent / up_time) / 1048576
		log.info(f"MonitorSistema: Subida finalizada: {round(up_speed, 2)} MB/s ({stream.sent} bytes en {round(up_time, 2)}s)")
		return up_speed


	@scriptHandler.script(
		description=_("Anuncia la velocidad de descarga y subida de Internet en tiempo real. Si se pulsa dos veces, copia la información al portapapeles."),
		category=scriptCategory,
		gesture="kb:nvda+shift+control+3",
		speakOnDemand=True,
	)
	def script_announceNetSpeed(self, gesture: inputCore.InputGesture):
		"""Mide y anuncia en tiempo real la velocidad de descarga y subida de internet."""
		self._atajoDeConsulta(
			"_netSpeedRunning", "_lastNetSpeedResult", "_copyNetSpeedOnFinish",
			self._getNetworkSpeed,
			_("La prueba de velocidad de Internet ya está en curso, por favor espera..."),
		)

	def _getAdvancedBattery(self):
		"""Atajo de teclado: dice el estado y la salud real de la batería.

		Avisa de que está consultando y hace el trabajo en un hilo aparte, porque
		preguntar por la salud real de la batería tarda unos segundos.
		"""
		if not self._tryStartOp("advBattery", "_advBatteryRunning"):
			return
		ui.message(_("Consultando estado de la batería, por favor espera..."))

		def worker():
			"""Consulta la batería y arma la frase completa.

			Primero el porcentaje y si está enchufada; si no lo está y el sistema sabe
			cuánto aguantará, añade el tiempo restante. Después le pregunta a Windows
			la capacidad que la batería admite hoy comparada con la que tenía de fábrica,
			que es la salud real y explica por qué una batería vieja dura menos aunque
			marque 100%. Esa consulta tiene cinco segundos de límite. Mientras dura
			todo, un pitido repetido indica que sigue trabajando.
			"""
			stop_event = self._startProgressBeeper(660)
			log.info("MonitorSistema: Consultando batería avanzada (porcentaje, tiempo restante, salud WMI)...")
			msg = _("Error consultando la batería.")
			try:
				bat = None
				try:
					bat = psutil.sensors_battery()
				except Exception as e:
					log.error(f"MonitorSistema: Error obteniendo psutil.sensors_battery: {e}", exc_info=True)

				log.info(f"MonitorSistema: Estado psutil.sensors_battery(): {bat}")
				if not bat:
					log.info("MonitorSistema: psutil no detectó batería en este equipo (posible sobremesa o sin sensor ACPI).")
					msg = _("No hay batería o es un equipo de sobremesa.")
				else:
					try:
						pct_val = float(bat.percent)
						if math.isnan(pct_val) or math.isinf(pct_val):
							pct = 0
						else:
							pct = max(0, min(100, int(round(pct_val))))
					except (ValueError, TypeError):
						pct = 0
					plugged = _("conectado") if bat.power_plugged else _("desconectado")
					msg = _("Batería al {} %. Estado: {}.").format(pct, plugged)
					if not bat.power_plugged and bat.secsleft is not None and 0 < bat.secsleft <= 259200:
						try:
							secs = int(bat.secsleft)
							mins = secs // 60
							msg += " " + _("Tiempo restante estimado: {} horas y {} minutos.").format(mins // 60, mins % 60)
						except (ValueError, TypeError, OverflowError):
							pass
					
					# Consulta WMI de salud real vs capacidad de diseño
					health_pct = None
					co_init = False
					try:
						import comtypes
						import comtypes.client
						try:
							comtypes.CoInitialize()
							co_init = True
						except Exception:
							pass
						locator = comtypes.client.CreateObject("WbemScripting.SWbemLocator")
						services = locator.ConnectServer(".", "root\\wmi")
						f_items = services.ExecQuery("SELECT FullChargedCapacity FROM BatteryFullChargedCapacity")
						d_items = services.ExecQuery("SELECT DesignedCapacity FROM BatteryStaticData")
						f_val = next(iter(f_items)).Properties_("FullChargedCapacity").Value
						d_val = next(iter(d_items)).Properties_("DesignedCapacity").Value
						if f_val and d_val and d_val > 0:
							ratio = (float(f_val) / float(d_val)) * 100.0
							if not math.isnan(ratio) and not math.isinf(ratio) and 0 < ratio <= 200:
								health_pct = str(round(ratio))
					except Exception:
						pass
					finally:
						if co_init:
							try:
								comtypes.CoUninitialize()
							except Exception:
								pass

					if not health_pct:
						# Respaldo vía PowerShell con Get-CimInstance / Get-WmiObject
						ps_script = (
							"Try { "
							"$f = (Get-CimInstance -Namespace root\\wmi -ClassName BatteryFullChargedCapacity -EA Stop | Select-Object -First 1).FullChargedCapacity; "
							"$d = (Get-CimInstance -Namespace root\\wmi -ClassName BatteryStaticData -EA Stop | Select-Object -First 1).DesignedCapacity; "
							"if ($d -gt 0) { [math]::Round(($f / $d) * 100) } "
							"} Catch { "
							"Try { "
							"$f = (Get-WmiObject BatteryFullChargedCapacity -Namespace root\\wmi -EA Stop | Select-Object -First 1 -ExpandProperty FullChargedCapacity); "
							"$d = (Get-WmiObject BatteryStaticData -Namespace root\\wmi -EA Stop | Select-Object -First 1 -ExpandProperty DesignedCapacity); "
							"if ($d -gt 0) { [math]::Round(($f / $d) * 100) } "
							"} Catch { } "
							"}"
						)
						try:
							si = subprocess.STARTUPINFO()
							si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
							out = subprocess.check_output(
								["powershell", "-WindowStyle", "Hidden", "-NoProfile", "-Command", ps_script],
								startupinfo=si,
								creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
								text=True,
								timeout=5
							).strip()
							log.info(f"MonitorSistema: Respuesta PowerShell salud batería WMI: '{out}'")
							if out and out.isdigit() and 0 < int(out) <= 200:
								health_pct = out
						except Exception as pe:
							log.debug(f"MonitorSistema: Error en consulta PowerShell de salud de batería: {pe}")

					if health_pct:
						msg += " " + _("Salud real de la batería: {} % de su capacidad original.").format(health_pct)
				self._lastAdvBatteryResult = msg
			except Exception as e:
				log.error(f"MonitorSistema: Error general consultando batería: {e}", exc_info=True)
				msg = _("Error consultando la batería.")
			finally:
				self._finishOp("advBattery", "_advBatteryRunning")
				stop_event.set()

			log.info(f"MonitorSistema: Anunciando estado de batería al usuario: '{msg}'")
			wx.CallAfter(ui.message, msg)
			if getattr(self, "_copyAdvBatteryOnFinish", False):
				self._copyAdvBatteryOnFinish = False
				wx.CallAfter(self._safeCopyToClip, msg)
		threading.Thread(target=worker, daemon=True).start()

	@scriptHandler.script(
		description=_("Anuncia el estado de la batería, tiempo restante y desgaste de salud. Si se pulsa dos veces, copia la información al portapapeles."),
		category=scriptCategory,
		gesture="kb:nvda+shift+control+4",
		speakOnDemand=True,
	)
	def script_announceAdvBattery(self, gesture: inputCore.InputGesture):
		"""Informa sobre el porcentaje de batería, tiempo restante y desgaste de salud."""
		self._atajoDeConsulta(
			"_advBatteryRunning", "_lastAdvBatteryResult", "_copyAdvBatteryOnFinish",
			self._getAdvancedBattery,
			_("La consulta de batería ya está en curso, por favor espera..."),
		)

	@staticmethod
	def _queryBluetoothBatteries():
		"""Aparatos Bluetooth conectados que informan de su nivel de bateria.

		Motor desarrollado y mejorado por Daliana sobre la base de referencia de
		BlueToothBatteryReport (por Cary-rowen y colaboradores), resolviendo la detección
		con matriz de 4 claves DEVPROPKEY y filtrado multinivel de desconexión.
		"""
		log.debug("MonitorSistema: Iniciando enumeración profunda de dispositivos Bluetooth...")
		try:
			try:
				ctypes.windll.setupapi.SetupDiEnumDeviceInfo.argtypes = None
			except Exception:
				pass

			api = _cargarApiDeDispositivos()
			estados_clasicos = _estadosDeBluetoothClasico()
			encontrados = _dispositivosConBateria(api)
			if encontrados is None:
				return []
			candidates, root_names, root_dev_insts = encontrados
			results = _soloLosConectados(api, candidates, estados_clasicos,
				root_names, root_dev_insts)
			if results:
				log.info(f"MonitorSistema: Fin de escaneo Bluetooth. Dispositivos conectados reportados ({len(results)}): {results}")
			else:
				log.debug("MonitorSistema: Fin de escaneo Bluetooth. No hay dispositivos conectados con batería.")
			return results
		except Exception as e:
			log.error(f"MonitorSistema: Error crítico en detección de batería Bluetooth: {e}", exc_info=True)
			return []

	def _getBluetoothBattery(self):
		"""Atajo de teclado: dice la batería de los aparatos Bluetooth conectados.

		Avisa de que está buscando y hace el trabajo en un hilo aparte, porque
		recorrer los aparatos Bluetooth tarda unos segundos.
		"""
		if not self._tryStartOp("bluetooth", "_bluetoothRunning"):
			return
		ui.message(_("Buscando dispositivos Bluetooth, por favor espera..."))

		def worker():
			"""Pregunta a cada aparato Bluetooth por su batería y arma la frase.

			Solo aparecen los que la informan; no todos lo hacen, y el que no la
			informa no es que esté mal. Si no responde ninguno lo dice con esas
			palabras, en lugar de callarse. Mientras dura la búsqueda, un pitido
			repetido indica que sigue trabajando.
			"""
			stop_event = self._startProgressBeeper(550)
			log.info("MonitorSistema: Ejecutando comando de batería Bluetooth...")
			msg = _("Error consultando dispositivos Bluetooth.")
			try:
				data = self._queryBluetoothBatteries()
				if not data:
					msg = _("No se encontraron dispositivos Bluetooth informando su batería.")
					log.info("MonitorSistema: Anunciando al usuario: 'No se encontraron dispositivos Bluetooth informando su batería.'")
				else:
					parts = []
					for d in data:
						if not isinstance(d, dict):
							continue
						raw_name = d.get('name')
						name = str(raw_name).strip() if raw_name else _('Dispositivo')
						name = "".join(ch for ch in name if ch.isprintable() or ch in " \t") or _('Dispositivo')
						bat_val = d.get('battery')
						try:
							bat_num = int(bat_val)
							if 0 <= bat_num <= 100:
								parts.append(_("{}: {} %").format(name, bat_num))
							else:
								parts.append(_("{}: desconocido").format(name))
						except (ValueError, TypeError, OverflowError):
							parts.append(_("{}: desconocido").format(name))
					if parts:
						msg = _("Batería Bluetooth: ") + ", ".join(parts)
					else:
						msg = _("No se encontraron dispositivos Bluetooth informando su batería.")
					log.info(f"MonitorSistema: Anunciando al usuario: '{msg}'")
				self._lastBluetoothResult = msg
			except Exception as e:
				log.error(f"MonitorSistema: Error consultando dispositivos Bluetooth: {e}", exc_info=True)
				msg = _("Error consultando dispositivos Bluetooth.")
			finally:
				self._finishOp("bluetooth", "_bluetoothRunning")
				stop_event.set()

			wx.CallAfter(ui.message, msg)
			if getattr(self, "_copyBluetoothOnFinish", False):
				self._copyBluetoothOnFinish = False
				wx.CallAfter(self._safeCopyToClip, msg)
		threading.Thread(target=worker, daemon=True).start()

	@scriptHandler.script(
		description=_("Anuncia el nivel de batería de los dispositivos Bluetooth conectados. Si se pulsa dos veces, copia la información al portapapeles."),
		category=scriptCategory,
		gesture="kb:nvda+shift+control+5",
		speakOnDemand=True,
	)
	def script_announceBluetooth(self, gesture: inputCore.InputGesture):
		"""Verbaliza el nivel de batería y estado de los dispositivos Bluetooth conectados."""
		self._atajoDeConsulta(
			"_bluetoothRunning", "_lastBluetoothResult", "_copyBluetoothOnFinish",
			self._getBluetoothBattery,
			_("La búsqueda de dispositivos Bluetooth ya está en curso, por favor espera..."),
		)

	def auditConflicts(self):
		"""
		Audita y registra en el registro de NVDA posibles conflictos con otros complementos instalados o activos,
		incluyendo colisiones directas de atajos de teclado (gestos) y complementos duplicados o incompatibles.
		Devuelve una tupla (conflicts, warnings).
		"""
		conflicts = []
		warnings = []

		log.info("MonitorSistema: Iniciando auditoría de compatibilidad y detección de conflictos con otros complementos...")

		# 1. Complementos instalados que hacen lo mismo que este
		self._revisarComplementosSolapados(warnings)

		# 2. Otros complementos activos que usen los mismos atajos
		self._revisarAtajosDeOtrosComplementos(conflicts)

		# 3. Comandos globales nativos de NVDA
		self._revisarComandosNativosDeNVDA(conflicts)


		# Resumen final en el log
		total_issues = len(conflicts) + len(warnings)
		if total_issues == 0:
			log.info("MonitorSistema: Auditoría de conflictos finalizada con éxito. No se detectaron colisiones de atajos ni complementos incompatibles activos.")
		else:
			log.warning(
				f"MonitorSistema: Auditoría de conflictos finalizada. Se detectaron {len(conflicts)} colisión(es) directa(s) de atajos "
				f"y {len(warnings)} advertencia(s) de compatibilidad."
			)

		return conflicts, warnings

	def _atajosPropios(self):
		"""Los atajos de este complemento y para que sirve cada uno.

		Es un metodo y no una constante del archivo porque los textos se traducen,
		y la traduccion no esta lista hasta que NVDA ha arrancado del todo.
		"""
		return {
			"kb:nvda+shift+e": _("Resumen de recursos (RAM y CPU)"),
			"kb:nvda+shift+1": _("Carga y núcleos del procesador"),
			"kb:nvda+shift+2": _("Memoria RAM física y virtual"),
			"kb:nvda+shift+3": _("Espacio en unidades de disco"),
			"kb:nvda+shift+4": _("Estado e información de red Wi-Fi"),
			"kb:nvda+shift+5": _("Frecuencia y velocidad de CPU"),
			"kb:nvda+shift+6": _("Versión y arquitectura de Windows"),
			"kb:nvda+shift+7": _("Tiempo de actividad del sistema (uptime)"),
			"kb:nvda+shift+8": _("Rendimiento y memoria de GPU"),
			"kb:nvda+shift+control+1": _("Salud S.M.A.R.T. y vida útil de discos"),
			"kb:nvda+shift+control+2": _("Procesos con mayor consumo de recursos"),
			"kb:nvda+shift+control+3": _("Velocidad de red en tiempo real"),
			"kb:nvda+shift+control+4": _("Batería avanzada y salud"),
			"kb:nvda+shift+control+5": _("Nivel de batería de dispositivos Bluetooth"),
		}

	def _revisarComplementosSolapados(self, warnings):
		"""Busca complementos instalados que hagan lo mismo que este.

		Apunta en 'warnings' lo que encuentre.
		"""
		known_overlapping = {
			"resourcemonitor": _("Resource Monitor (comparte los mismos atajos NVDA+Shift+1 al 8 y NVDA+Shift+E, causando que se ignoren comandos o se emitan respuestas duplicadas/en inglés)"),
			"topprocess": _("Top Process (superpone atajos o anuncios de consumo de procesos)"),
			"sysinfo": _("SysInfo (superpone atajos de información de hardware y sistema)"),
			"batterystatus": _("Battery Status (superpone atajos de nivel de batería)"),
		}

		try:
			available_addons = list(addonHandler.getAvailableAddons())
			for addon in available_addons:
				addon_name = getattr(addon, "name", "").lower()
				if addon_name in ("monitorsistema", "monitoreosistema"):
					continue

				if getattr(addon, "isDisabled", False):
					continue

				manifest = getattr(addon, "manifest", {}) or {}
				summary = manifest.get("summary", "")

				if addon_name in known_overlapping:
					reason = known_overlapping[addon_name]
					msg = f"Complemento superpuesto activo detectado: '{addon.name}' ({summary}). Motivo: {reason}."
					warnings.append(msg)
					log.warning(f"MonitorSistema ADVERTENCIA DE COMPATIBILIDAD: {msg}")
				elif "resource monitor" in summary.lower() or "monitor de recursos" in summary.lower():
					msg = f"Complemento con funciones similares activo: '{addon.name}' ({summary}). Podría compartir atajos o interceptar comandos."
					warnings.append(msg)
					log.warning(f"MonitorSistema ADVERTENCIA DE COMPATIBILIDAD: {msg}")
		except Exception as e:
			log.debug(f"MonitorSistema: No se pudo verificar la lista de complementos instalados: {e}")

	@staticmethod
	def _normalizarGesto(gesto_str):
		"""Normaliza un gesto eliminando espacios y modificadores redundantes."""
		s = str(gesto_str).strip().lower().replace(" ", "")
		return re.sub(r'\(.*?\)', '', s)

	def _obtenerMapaAtajosPropiosNormalizado(self):
		"""Construye el mapa de atajos propios normalizados con su descripción."""
		default_map = {self._normalizarGesto(k): v for k, v in self._atajosPropios().items()}
		our_gestures_map = {}
		g_map = getattr(self, "_gestureMap", {}) or {}
		if g_map:
			for g_id, script_ref in g_map.items():
				norm_g = self._normalizarGesto(g_id)
				desc = getattr(script_ref, "description", "") or getattr(script_ref, "__doc__", "") or default_map.get(norm_g, getattr(script_ref, "__name__", str(script_ref)))
				our_gestures_map[norm_g] = desc
		else:
			our_gestures_map = default_map
		return our_gestures_map

	def _revisarAtajosDeOtrosComplementos(self, conflicts):
		"""Busca otros complementos activos que usen los mismos atajos.

		Apunta en 'conflicts' lo que encuentre.
		"""
		our_gestures_map = self._obtenerMapaAtajosPropiosNormalizado()
		try:
			running = getattr(globalPluginHandler, "runningPlugins", set())
			for plugin in running:
				if plugin is self:
					continue
				plugin_mod = getattr(plugin, "__module__", str(type(plugin)))
				if any(k in plugin_mod.lower() for k in ("monitorsistema", "monitoreosistema")):
					continue

				# Obtener mapa de gestos del plugin
				g_map = getattr(plugin, "_gestureMap", {}) or {}
				if not g_map:
					g_map = getattr(plugin, "_ScriptableObject__gestures", {}) or {}

				for g_id, script_ref in g_map.items():
					norm_g = self._normalizarGesto(g_id)
					if norm_g in our_gestures_map:
						script_name = getattr(script_ref, "__name__", str(script_ref))
						our_feature = our_gestures_map[norm_g]
						collision_msg = (
							f"Colisión de atajo: '{norm_g}' está asignado simultáneamente a '{our_feature}' (Monitoreo del Sistema) "
							f"y a '{script_name}' en el plugin '{plugin_mod}'."
						)
						conflicts.append(collision_msg)
						log.warning(f"MonitorSistema CONFLICTO DE ATAJO: {collision_msg}")
		except Exception as e:
			log.debug(f"MonitorSistema: Error inspeccionando runningPlugins: {e}")

	def _revisarComandosNativosDeNVDA(self, conflicts):
		"""Comprueba si algún atajo propio colisiona con comandos nativos de NVDA."""
		our_gestures_map = self._obtenerMapaAtajosPropiosNormalizado()

		try:
			import globalCommands
			cmd_obj = getattr(globalCommands, "commands", None)
			if cmd_obj:
				cmd_map = getattr(cmd_obj, "_gestureMap", {}) or {}
				for cmd_g, cmd_script in cmd_map.items():
					norm_cmd = self._normalizarGesto(cmd_g)
					if norm_cmd in our_gestures_map:
						our_feature = our_gestures_map[norm_cmd]
						cmd_desc = getattr(cmd_script, "description", "") or getattr(cmd_script, "__name__", str(cmd_script))
						collision_msg = (
							f"Colisión de atajo: '{norm_cmd}' está asignado simultáneamente a '{our_feature}' (Monitoreo del Sistema) "
							f"y al comando nativo de NVDA '{cmd_desc}'."
						)
						conflicts.append(collision_msg)
						log.warning(f"MonitorSistema CONFLICTO CON NVDA CORE: {collision_msg}")
		except Exception as e:
			log.debug(f"MonitorSistema: No se pudo verificar comandos globales nativos: {e}")

	def _checkAddonConflicts(self, interactive=False):
		conflicts, warnings = self.auditConflicts()
		if interactive:
			total = len(conflicts) + len(warnings)
			if total == 0:
				ui.message(_("Monitoreo del Sistema: No se detectaron conflictos con otros complementos."))
			else:
				ui.message(
					_("Monitoreo del Sistema: Se detectaron {count} posibles conflictos o advertencias. Revise el registro de NVDA para más detalles.").format(count=total)
				)

	@scriptHandler.script(
		description=_("Comprueba si existen conflictos de atajos de teclado o complementos incompatibles con Monitoreo del Sistema."),
		category=scriptCategory,
	)
	def script_checkConflicts(self, gesture: inputCore.InputGesture):
		"""Ejecuta una auditoría interactiva de atajos y complementos concurrentes."""
		wx.CallAfter(self._checkAddonConflicts, interactive=True)
