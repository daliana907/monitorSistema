# -*- coding: utf-8 -*-
# System Monitor (Monitor del Sistema) for NVDA
#
# A system resource and hardware monitoring add-on for NVDA.
# Based on Resource Monitor for NVDA.
#
# Original work Copyright 2013-2026 Joseph Lee, Alex Hall, Beqa Gozalishvili and Resource Monitor contributors.
# Modifications, extensions and new features Copyright 2026 Daliana.
# Released under the GNU General Public License version 2 (GPLv2).


import logging
import functools
import threading
import addonHandler
addonHandler.initTranslation()
log = logging.getLogger(__name__)

import os.path
import time
import winsound
import ctypes
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
import queueHandler
import scriptHandler
import inputCore
import ui
import winVersion
import wx
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
except (OSError, AttributeError):
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
}
config.conf.spec["monitorSistema"] = confspec

# Si los umbrales de temperatura de CPU o GPU quedaron configurados con valores temporales de prueba (< 70 °C), restaurar automáticamente a los valores reales de sobrecalentamiento (85 °C para CPU y 80 °C para GPU)
try:
	cur_cpu_thresh = config.conf.get("monitorSistema", {}).get("alertCpuHotThreshold")
	if cur_cpu_thresh is not None and int(cur_cpu_thresh) < 70:
		config.conf["monitorSistema"]["alertCpuHotThreshold"] = 85
	cur_gpu_thresh = config.conf.get("monitorSistema", {}).get("alertGpuHotThreshold")
	if cur_gpu_thresh is not None and int(cur_gpu_thresh) < 70:
		config.conf["monitorSistema"]["alertGpuHotThreshold"] = 80
except Exception:
	pass


def message(text: str, fileName: str) -> None:
	cfg = config.conf.get("monitorSistema", {})
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
		try:
			import tones
			if "connect" in fileName:
				tones.beep(660, 80); tones.beep(880, 100)
			else:
				tones.beep(440, 100); tones.beep(330, 120)
		except Exception:
			pass


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

	@wlanapi.WLAN_NOTIFICATION_CALLBACK
	def notifyHandler(pData: Any, pCtx: Any):
		try:
			if pData.contents.NotificationSource != wlanapi.WLAN_NOTIFICATION_SOURCE_ACM:
				return
			match pData.contents.NotificationCode:
				case wlanapi.wlan_notification_acm_connection_complete:
					notificationData = wlanapi.WLAN_CONNECTION_NOTIFICATION_DATA.from_address(pData.contents.pData)
					if notificationData.wlanReasonCode != wlanapi.ERROR_SUCCESS:
						return
					ssid = notificationData.dot11Ssid.SSID
					queueHandler.queueFunction(
						queueHandler.eventQueue,
						message,
						_("Conectado a {}").format(ssid.decode("utf-8", errors="ignore")),
						"connect.wav",
					)
				case wlanapi.wlan_notification_acm_disconnected:
					ssid = wlanapi.WLAN_CONNECTION_NOTIFICATION_DATA.from_address(
						pData.contents.pData
					).dot11Ssid.SSID
					queueHandler.queueFunction(
						queueHandler.eventQueue,
						message,
						_("Desconectado de {}").format(ssid.decode("utf-8", errors="ignore")),
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
except NameError:
	pass


def customResize(array: Any, newSize: Any):
	return (array._type_ * newSize).from_address(addressof(array))


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
	factor = 1.0
	suffix = " B"
	for f, s in system:
		if float(bytes_val) >= float(f):
			factor = f
			suffix = s
			break
	amount = float(bytes_val / factor)
	if isinstance(suffix, tuple):
		singular, multiple = suffix
		suffix = singular if float(amount) == 1.0 else multiple
	return "{:.2f}{}".format(float(amount), suffix)


def tryTrunk(n: float) -> int | float:
	if n == int(n):
		return int(n)
	return n


def formatGpuTemperature(celsiusText: str) -> str:
	try:
		celsius = float(celsiusText)
	except (TypeError, ValueError):
		return celsiusText
	unit = config.conf.get("monitorSistema", {}).get("gpuTempUnit", "celsius")
	if unit == "fahrenheit":
		value = celsius * 9.0 / 5.0 + 32.0
		symbol = _("grados Fahrenheit")
	else:
		value = celsius
		symbol = _("grados Celsius")
	return "{} {}".format(tryTrunk(round(value, 1)), symbol)


def formatGpuMemory(usedMibText: str, totalMibText: str) -> str | None:
	try:
		usedMib = float(usedMibText)
	except (TypeError, ValueError):
		return None
	try:
		totalMib = float(totalMibText)
	except (TypeError, ValueError):
		totalMib = 0.0

	usedBytes = usedMib * 1024.0 * 1024.0
	if totalMib > 0:
		totalBytes = totalMib * 1024.0 * 1024.0
		return "{used} de {total} utilizados ({percent}%)".format(
			used=size(usedBytes, alternative),
			total=size(totalBytes, alternative),
			percent=tryTrunk(round(usedBytes / totalBytes * 100, 1)),
		)
	else:
		return "{used} utilizados".format(used=size(usedBytes, alternative))


class MonitorSistemaSettingsPanel(SettingsPanel):
	title = "Monitor del Sistema"

	def makeSettings(self, settingsSizer: wx.BoxSizer) -> None:
		self._settingsSizer = settingsSizer
		settingsSizerHelper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		gpuTempUnitLabelText = _("&Unidad de temperatura (CPU y GPU):")
		self._gpuTempUnitLabels = ["Celsius", "Fahrenheit"]
		self._gpuTempUnitValues = ["celsius", "fahrenheit"]
		self.gpuTempUnitList = settingsSizerHelper.addLabeledControl(
			gpuTempUnitLabelText,
			wx.Choice,
			choices=self._gpuTempUnitLabels,
		)
		try:
			currentIndex = self._gpuTempUnitValues.index(
				config.conf.get("monitorSistema", {}).get("gpuTempUnit", "celsius")
			)
		except ValueError:
			currentIndex = 0
		self.gpuTempUnitList.SetSelection(currentIndex)

		# Alertas automáticas en segundo plano
		self.alertBatteryFullCheckbox = settingsSizerHelper.addItem(
			wx.CheckBox(self, label=_("Avisar cuando la batería del equipo esté cargada"))
		)
		self.alertBatteryFullCheckbox.SetValue(
			bool(config.conf.get("monitorSistema", {}).get("alertBatteryFull", True))
		)
		self.alertBatteryFullCheckbox.Bind(wx.EVT_CHECKBOX, self.onAlertBatteryFullChange)

		self.batteryFullSlider = settingsSizerHelper.addLabeledControl(
			_("&Porcentaje para la alerta de batería cargada:"),
			NumberCtrlClass,
			min=70,
			max=100,
			initial=int(config.conf.get("monitorSistema", {}).get("alertBatteryFullThreshold", 100)),
		)

		self.alertBatteryLowCheckbox = settingsSizerHelper.addItem(
			wx.CheckBox(self, label=_("Avisar cuando la batería del equipo esté baja"))
		)
		self.alertBatteryLowCheckbox.SetValue(
			bool(config.conf.get("monitorSistema", {}).get("alertBatteryLow", True))
		)
		self.alertBatteryLowCheckbox.Bind(wx.EVT_CHECKBOX, self.onAlertBatteryLowChange)

		self.batteryLowSlider = settingsSizerHelper.addLabeledControl(
			_("&Porcentaje para la alerta de batería baja del equipo:"),
			NumberCtrlClass,
			min=5,
			max=50,
			initial=int(config.conf.get("monitorSistema", {}).get("alertBatteryLowThreshold", 15)),
		)

		self.batteryIntervalEdit = settingsSizerHelper.addLabeledControl(
			_("&Intervalo de comprobación de la batería (minutos):"),
			NumberCtrlClass,
			min=1,
			max=60,
			initial=int(config.conf.get("monitorSistema", {}).get("alertBatteryInterval", 1)),
		)

		self.alertCpuHotCheckbox = settingsSizerHelper.addItem(
			wx.CheckBox(self, label=_("Avisar si la temperatura del procesador es alta"))
		)
		self.alertCpuHotCheckbox.SetValue(
			bool(config.conf.get("monitorSistema", {}).get("alertCpuHot", True))
		)
		self.alertCpuHotCheckbox.Bind(wx.EVT_CHECKBOX, self.onAlertCpuHotChange)

		initialCpuThresh = int(config.conf.get("monitorSistema", {}).get("alertCpuHotThreshold", 85))
		if initialCpuThresh < 70:
			initialCpuThresh = 85
			config.conf["monitorSistema"]["alertCpuHotThreshold"] = 85

		self.cpuHotSlider = settingsSizerHelper.addLabeledControl(
			_("&Temperatura para la alerta de sobrecalentamiento del procesador:"),
			NumberCtrlClass,
			min=40,
			max=105,
			initial=initialCpuThresh,
		)

		self.cpuHotIntervalEdit = settingsSizerHelper.addLabeledControl(
			_("I&ntervalo de comprobación de temperatura de CPU (minutos):"),
			NumberCtrlClass,
			min=1,
			max=60,
			initial=int(config.conf.get("monitorSistema", {}).get("alertCpuHotInterval", 1)),
		)

		self.alertGpuHotCheckbox = settingsSizerHelper.addItem(
			wx.CheckBox(self, label=_("Avisar si la temperatura de la tarjeta gráfica (GPU) es alta"))
		)
		self.alertGpuHotCheckbox.SetValue(
			bool(config.conf.get("monitorSistema", {}).get("alertGpuHot", True))
		)
		self.alertGpuHotCheckbox.Bind(wx.EVT_CHECKBOX, self.onAlertGpuHotChange)

		initialGpuThresh = int(config.conf.get("monitorSistema", {}).get("alertGpuHotThreshold", 80))
		if initialGpuThresh < 70:
			initialGpuThresh = 80
			config.conf["monitorSistema"]["alertGpuHotThreshold"] = 80

		self.gpuHotSlider = settingsSizerHelper.addLabeledControl(
			_("Temperat&ura para la alerta de sobrecalentamiento de la GPU:"),
			NumberCtrlClass,
			min=40,
			max=100,
			initial=initialGpuThresh,
		)

		self.gpuHotIntervalEdit = settingsSizerHelper.addLabeledControl(
			_("Inter&valo de comprobación de temperatura de GPU (minutos):"),
			NumberCtrlClass,
			min=1,
			max=60,
			initial=int(config.conf.get("monitorSistema", {}).get("alertGpuHotInterval", 1)),
		)

		self.alertBluetoothLowCheckbox = settingsSizerHelper.addItem(
			wx.CheckBox(self, label=_("Avisar cuando la batería de un dispositivo Bluetooth esté baja"))
		)
		self.alertBluetoothLowCheckbox.SetValue(
			bool(config.conf.get("monitorSistema", {}).get("alertBluetoothLow", True))
		)
		self.alertBluetoothLowCheckbox.Bind(wx.EVT_CHECKBOX, self.onAlertBluetoothLowChange)

		self.bluetoothLowSlider = settingsSizerHelper.addLabeledControl(
			_("P&orcentaje para la alerta de batería baja en Bluetooth:"),
			NumberCtrlClass,
			min=5,
			max=50,
			initial=int(config.conf.get("monitorSistema", {}).get("alertBluetoothLowThreshold", 15)),
		)

		self.bluetoothLowIntervalEdit = settingsSizerHelper.addLabeledControl(
			_("In&tervalo de comprobación de Bluetooth (minutos):"),
			NumberCtrlClass,
			min=1,
			max=60,
			initial=int(config.conf.get("monitorSistema", {}).get("alertBluetoothLowInterval", 2)),
		)

		self.alertWlanCheckbox = settingsSizerHelper.addItem(
			wx.CheckBox(self, label=_("Avisar cuando cambie el estado de la red Wi-Fi (conexión o desconexión)"))
		)
		self.alertWlanCheckbox.SetValue(
			bool(config.conf.get("monitorSistema", {}).get("alertWlan", True))
		)

		self.alertWlanSignalChangeCheckbox = settingsSizerHelper.addItem(
			wx.CheckBox(self, label=_("Avisar cuando cambie la intensidad de la señal Wi-Fi"))
		)
		self.alertWlanSignalChangeCheckbox.SetValue(
			bool(config.conf.get("monitorSistema", {}).get("alertWlanSignalChange", False))
		)

		self.alertDiskHealthCheckbox = settingsSizerHelper.addItem(
			wx.CheckBox(self, label=_("Avisar si se detectan problemas de salud o desgaste crítico en discos (SSD / HDD)"))
		)
		self.alertDiskHealthCheckbox.SetValue(
			bool(config.conf.get("monitorSistema", {}).get("alertDiskHealth", True))
		)
		self.alertDiskHealthCheckbox.Bind(wx.EVT_CHECKBOX, self.onAlertDiskHealthChange)

		self.diskWearSlider = settingsSizerHelper.addLabeledControl(
			_("Porcentaje de des&gaste para la alerta de discos SSD:"),
			NumberCtrlClass,
			min=70,
			max=95,
			initial=int(config.conf.get("monitorSistema", {}).get("alertDiskWearThreshold", 80)),
		)

		self.diskHealthIntervalEdit = settingsSizerHelper.addLabeledControl(
			_("Intervalo de comprobación de dis&cos (minutos):"),
			NumberCtrlClass,
			min=1,
			max=1440,
			initial=int(config.conf.get("monitorSistema", {}).get("alertDiskHealthInterval", 240)),
		)

		# Botón para comprobar conflictos con otros complementos
		checkBtn = wx.Button(self, label=_("&Comprobar conflictos con otros complementos..."))
		checkBtn.Bind(wx.EVT_BUTTON, self.onCheckConflicts)
		settingsSizerHelper.addItem(checkBtn)

		self._updateBatteryFullVisibility(self.alertBatteryFullCheckbox.GetValue())
		self._updateBatteryLowVisibility(self.alertBatteryLowCheckbox.GetValue())
		self._updateCpuHotVisibility(self.alertCpuHotCheckbox.GetValue())
		self._updateGpuHotVisibility(self.alertGpuHotCheckbox.GetValue())
		self._updateBluetoothLowVisibility(self.alertBluetoothLowCheckbox.GetValue())
		self._updateDiskHealthVisibility(self.alertDiskHealthCheckbox.GetValue())

	def _updateBatteryIntervalVisibility(self) -> None:
		try:
			show = self.alertBatteryFullCheckbox.GetValue() or self.alertBatteryLowCheckbox.GetValue()
			sizer = self.batteryIntervalEdit.GetContainingSizer()
			if sizer and hasattr(self, "_settingsSizer"):
				self._settingsSizer.Show(sizer, show=show, recursive=True)
			self.batteryIntervalEdit.Show(show)
		except Exception as e:
			log.error(f"MonitorSistema: Error actualizando visibilidad de intervalo de batería: {e}", exc_info=True)

	def _updateBatteryFullVisibility(self, show: bool) -> None:
		try:
			sizer = self.batteryFullSlider.GetContainingSizer()
			if sizer and hasattr(self, "_settingsSizer"):
				self._settingsSizer.Show(sizer, show=show, recursive=True)
			self.batteryFullSlider.Show(show)
			self._updateBatteryIntervalVisibility()
			if hasattr(self, "_settingsSizer"):
				self._settingsSizer.Layout()
			self.Layout()
			if hasattr(self, "_sendLayoutUpdatedEvent"):
				self._sendLayoutUpdatedEvent()
		except Exception as e:
			log.error(f"MonitorSistema: Error actualizando visibilidad de barra de batería cargada: {e}", exc_info=True)

	def _updateBatteryLowVisibility(self, show: bool) -> None:
		try:
			sizer = self.batteryLowSlider.GetContainingSizer()
			if sizer and hasattr(self, "_settingsSizer"):
				self._settingsSizer.Show(sizer, show=show, recursive=True)
			self.batteryLowSlider.Show(show)
			self._updateBatteryIntervalVisibility()
			if hasattr(self, "_settingsSizer"):
				self._settingsSizer.Layout()
			self.Layout()
			if hasattr(self, "_sendLayoutUpdatedEvent"):
				self._sendLayoutUpdatedEvent()
		except Exception as e:
			log.error(f"MonitorSistema: Error actualizando visibilidad de barra de batería baja: {e}", exc_info=True)

	def _updateCpuHotVisibility(self, show: bool) -> None:
		try:
			sizer = self.cpuHotSlider.GetContainingSizer()
			if sizer and hasattr(self, "_settingsSizer"):
				self._settingsSizer.Show(sizer, show=show, recursive=True)
			self.cpuHotSlider.Show(show)
			sizerInt = self.cpuHotIntervalEdit.GetContainingSizer()
			if sizerInt and hasattr(self, "_settingsSizer"):
				self._settingsSizer.Show(sizerInt, show=show, recursive=True)
			self.cpuHotIntervalEdit.Show(show)
			if hasattr(self, "_settingsSizer"):
				self._settingsSizer.Layout()
			self.Layout()
			if hasattr(self, "_sendLayoutUpdatedEvent"):
				self._sendLayoutUpdatedEvent()
		except Exception as e:
			log.error(f"MonitorSistema: Error actualizando visibilidad de temperatura CPU: {e}", exc_info=True)

	def _updateGpuHotVisibility(self, show: bool) -> None:
		try:
			sizer = self.gpuHotSlider.GetContainingSizer()
			if sizer and hasattr(self, "_settingsSizer"):
				self._settingsSizer.Show(sizer, show=show, recursive=True)
			self.gpuHotSlider.Show(show)
			sizerInt = self.gpuHotIntervalEdit.GetContainingSizer()
			if sizerInt and hasattr(self, "_settingsSizer"):
				self._settingsSizer.Show(sizerInt, show=show, recursive=True)
			self.gpuHotIntervalEdit.Show(show)
			if hasattr(self, "_settingsSizer"):
				self._settingsSizer.Layout()
			self.Layout()
			if hasattr(self, "_sendLayoutUpdatedEvent"):
				self._sendLayoutUpdatedEvent()
		except Exception as e:
			log.error(f"MonitorSistema: Error actualizando visibilidad de temperatura GPU: {e}", exc_info=True)

	def _updateBluetoothLowVisibility(self, show: bool) -> None:
		try:
			sizer = self.bluetoothLowSlider.GetContainingSizer()
			if sizer and hasattr(self, "_settingsSizer"):
				self._settingsSizer.Show(sizer, show=show, recursive=True)
			self.bluetoothLowSlider.Show(show)
			sizerInt = self.bluetoothLowIntervalEdit.GetContainingSizer()
			if sizerInt and hasattr(self, "_settingsSizer"):
				self._settingsSizer.Show(sizerInt, show=show, recursive=True)
			self.bluetoothLowIntervalEdit.Show(show)
			if hasattr(self, "_settingsSizer"):
				self._settingsSizer.Layout()
			self.Layout()
			if hasattr(self, "_sendLayoutUpdatedEvent"):
				self._sendLayoutUpdatedEvent()
		except Exception as e:
			log.error(f"MonitorSistema: Error actualizando visibilidad de Bluetooth baja: {e}", exc_info=True)

	def _updateDiskHealthVisibility(self, show: bool) -> None:
		try:
			sizer = self.diskWearSlider.GetContainingSizer()
			if sizer and hasattr(self, "_settingsSizer"):
				self._settingsSizer.Show(sizer, show=show, recursive=True)
			self.diskWearSlider.Show(show)
			sizerInt = self.diskHealthIntervalEdit.GetContainingSizer()
			if sizerInt and hasattr(self, "_settingsSizer"):
				self._settingsSizer.Show(sizerInt, show=show, recursive=True)
			self.diskHealthIntervalEdit.Show(show)
			if hasattr(self, "_settingsSizer"):
				self._settingsSizer.Layout()
			self.Layout()
			if hasattr(self, "_sendLayoutUpdatedEvent"):
				self._sendLayoutUpdatedEvent()
		except Exception as e:
			log.error(f"MonitorSistema: Error actualizando visibilidad de desgaste de disco: {e}", exc_info=True)

	def onAlertBatteryFullChange(self, evt: wx.CommandEvent) -> None:
		self._updateBatteryFullVisibility(self.alertBatteryFullCheckbox.GetValue())
		evt.Skip()

	def onAlertBatteryLowChange(self, evt: wx.CommandEvent) -> None:
		self._updateBatteryLowVisibility(self.alertBatteryLowCheckbox.GetValue())
		evt.Skip()

	def onAlertCpuHotChange(self, evt: wx.CommandEvent) -> None:
		self._updateCpuHotVisibility(self.alertCpuHotCheckbox.GetValue())
		evt.Skip()

	def onAlertGpuHotChange(self, evt: wx.CommandEvent) -> None:
		self._updateGpuHotVisibility(self.alertGpuHotCheckbox.GetValue())
		evt.Skip()

	def onAlertBluetoothLowChange(self, evt: wx.CommandEvent) -> None:
		self._updateBluetoothLowVisibility(self.alertBluetoothLowCheckbox.GetValue())
		evt.Skip()

	def onAlertDiskHealthChange(self, evt: wx.CommandEvent) -> None:
		self._updateDiskHealthVisibility(self.alertDiskHealthCheckbox.GetValue())
		evt.Skip()

	def onPanelActivated(self) -> None:
		super().onPanelActivated()
		self._updateBatteryFullVisibility(self.alertBatteryFullCheckbox.GetValue())
		self._updateBatteryLowVisibility(self.alertBatteryLowCheckbox.GetValue())
		self._updateCpuHotVisibility(self.alertCpuHotCheckbox.GetValue())
		self._updateGpuHotVisibility(self.alertGpuHotCheckbox.GetValue())
		self._updateBluetoothLowVisibility(self.alertBluetoothLowCheckbox.GetValue())
		self._updateDiskHealthVisibility(self.alertDiskHealthCheckbox.GetValue())

	def onCheckConflicts(self, evt: wx.CommandEvent) -> None:
		plugin = None
		for p in getattr(globalPluginHandler, "runningPlugins", set()):
			if p.__class__.__module__.endswith("monitorSistema"):
				plugin = p
				break
		if plugin and hasattr(plugin, "auditConflicts"):
			conflicts, warnings = plugin.auditConflicts()
			if not conflicts and not warnings:
				messageBox(
					_("No se han detectado conflictos de atajos de teclado ni complementos incompatibles activos en este sistema."),
					_("Auditoría de conflictos - Monitor del Sistema"),
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
					_("Auditoría de conflictos - Monitor del Sistema"),
					wx.OK | wx.ICON_WARNING,
					parent=self,
				)
		else:
			messageBox(
				_("No se pudo obtener la instancia activa de Monitor del Sistema."),
				_("Error"),
				wx.OK | wx.ICON_ERROR,
				parent=self,
			)

	def onSave(self) -> None:
		try:
			selection = self.gpuTempUnitList.GetSelection()
			if selection == wx.NOT_FOUND:
				selection = 0
			config.conf["monitorSistema"]["gpuTempUnit"] = self._gpuTempUnitValues[selection]
			config.conf["monitorSistema"]["alertBatteryFull"] = self.alertBatteryFullCheckbox.GetValue()
			config.conf["monitorSistema"]["alertBatteryFullThreshold"] = self.batteryFullSlider.GetValue()
			config.conf["monitorSistema"]["alertBatteryLow"] = self.alertBatteryLowCheckbox.GetValue()
			config.conf["monitorSistema"]["alertBatteryLowThreshold"] = self.batteryLowSlider.GetValue()
			config.conf["monitorSistema"]["alertBatteryInterval"] = self.batteryIntervalEdit.GetValue()
			config.conf["monitorSistema"]["alertCpuHot"] = self.alertCpuHotCheckbox.GetValue()
			config.conf["monitorSistema"]["alertCpuHotThreshold"] = self.cpuHotSlider.GetValue()
			config.conf["monitorSistema"]["alertCpuHotInterval"] = self.cpuHotIntervalEdit.GetValue()
			config.conf["monitorSistema"]["alertGpuHot"] = self.alertGpuHotCheckbox.GetValue()
			config.conf["monitorSistema"]["alertGpuHotThreshold"] = self.gpuHotSlider.GetValue()
			config.conf["monitorSistema"]["alertGpuHotInterval"] = self.gpuHotIntervalEdit.GetValue()
			config.conf["monitorSistema"]["alertBluetoothLow"] = self.alertBluetoothLowCheckbox.GetValue()
			config.conf["monitorSistema"]["alertBluetoothLowThreshold"] = self.bluetoothLowSlider.GetValue()
			config.conf["monitorSistema"]["alertBluetoothLowInterval"] = self.bluetoothLowIntervalEdit.GetValue()
			config.conf["monitorSistema"]["alertWlan"] = self.alertWlanCheckbox.GetValue()
			config.conf["monitorSistema"]["alertWlanSignalChange"] = self.alertWlanSignalChangeCheckbox.GetValue()
			config.conf["monitorSistema"]["alertDiskHealth"] = self.alertDiskHealthCheckbox.GetValue()
			config.conf["monitorSistema"]["alertDiskWearThreshold"] = self.diskWearSlider.GetValue()
			config.conf["monitorSistema"]["alertDiskHealthInterval"] = self.diskHealthIntervalEdit.GetValue()
			log.info(
				f"MonitorSistema: Opciones guardadas -> Batería Llena: {self.alertBatteryFullCheckbox.GetValue()} ({self.batteryFullSlider.GetValue()}%), "
				f"Batería Baja: {self.alertBatteryLowCheckbox.GetValue()} ({self.batteryLowSlider.GetValue()}%), "
				f"Intervalo Batería: {self.batteryIntervalEdit.GetValue()} min, "
				f"CPU Caliente: {self.alertCpuHotCheckbox.GetValue()} ({self.cpuHotSlider.GetValue()} °C, cada {self.cpuHotIntervalEdit.GetValue()} min), "
				f"GPU Caliente: {self.alertGpuHotCheckbox.GetValue()} ({self.gpuHotSlider.GetValue()} °C, cada {self.gpuHotIntervalEdit.GetValue()} min), "
				f"Bluetooth Bajo: {self.alertBluetoothLowCheckbox.GetValue()} ({self.bluetoothLowSlider.GetValue()}%, cada {self.bluetoothLowIntervalEdit.GetValue()} min), "
				f"Alerta Wi-Fi: {self.alertWlanCheckbox.GetValue()}, Señal Wi-Fi: {self.alertWlanSignalChangeCheckbox.GetValue()}, "
				f"Salud Discos: {self.alertDiskHealthCheckbox.GetValue()} ({self.diskWearSlider.GetValue()}% desgaste SSD, cada {self.diskHealthIntervalEdit.GetValue()} min)"
			)
			plugin = None
			for p in getattr(globalPluginHandler, "runningPlugins", set()):
				if p.__class__.__module__.endswith("monitorSistema"):
					plugin = p
					break
			if plugin:
				plugin._forceAlertsCheck = True
		except Exception as e:
			log.error(f"MonitorSistema: Error guardando opciones en el panel: {e}", exc_info=True)


@functools.lru_cache(maxsize=1)
def getWinVer() -> str:
	currentWinVer = winVersion.getWinVer()
	arch = currentWinVer.processorArchitecture
	winverName = currentWinVer.releaseName
	if currentWinVer.productType != "workstation":
		winverName = f"Windows Server {winverName.rpartition(' ')[-1]}"
	revision = getattr(currentWinVer, "revision", None)
	if revision is None:
		try:
			import winreg
			with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
				revision = winreg.QueryValueEx(key, "UBR")[0]
		except Exception:
			revision = None
	if revision is not None:
		buildRevision = f"{currentWinVer.build}.{revision}"
	else:
		buildRevision = str(currentWinVer.build)
	return f"{winverName} ({arch}) compilación {buildRevision}"


class PDH_FMT_COUNTERVALUE(Structure):
	class _U(Union):
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


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	scriptCategory = _("Monitor del sistema")

	def __init__(self):
		super().__init__()
		log.info("Monitor del Sistema: Inicializando complemento (v2.3)...")
		self._cpuQuery = None
		self._cpuCounter = None
		self._client_handle = None
		self._negotiated_version = None
		self._gpuProviders: list[BaseGpuProvider] = getGpuProviders()
		NVDASettingsDialog.categoryClasses.append(MonitorSistemaSettingsPanel)

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

		import threading
		self._stopAlertsEvent = threading.Event()
		threading.Thread(target=self._startupBackgroundWorker, daemon=True).start()
		threading.Thread(target=self._runAlertsLoop, daemon=True).start()

	def _startupBackgroundWorker(self):
		log.info(f"Monitor del Sistema: Iniciando worker de fondo (CPU núcleos físicos={psutil.cpu_count(logical=False)}, hilos lógicos={psutil.cpu_count(logical=True)})...")
		try:
			self._initCpuQuery()
		except Exception as e:
			log.error(f"MonitorSistema: Error inicializando consulta de CPU: {e}", exc_info=True)

		try:
			for provider in self._gpuProviders:
				if hasattr(provider, "_initPdh"):
					provider._initPdh()
		except Exception as e:
			log.error(f"MonitorSistema: Error inicializando PDH de GPU: {e}", exc_info=True)

		if wlanapiAvailable:
			try:
				version = wintypes.DWORD()
				handle = wintypes.HANDLE()
				if wlanapi.WlanOpenHandle(
					wlanapi.CLIENT_VERSION_WINDOWS_VISTA_OR_LATER,
					None,
					byref(version),
					byref(handle),
				) == 0:
					self._negotiated_version = version
					self._client_handle = handle
					wlanapi.WlanRegisterNotification(
						self._client_handle,
						wlanapi.WLAN_NOTIFICATION_SOURCE_ACM,
						True,
						notifyHandler,
						None,
						None,
						None,
					)
					log.info("MonitorSistema: Notificaciones WLAN registradas exitosamente.")
			except Exception as e:
				log.error(f"MonitorSistema: Error registrando notificaciones WLAN: {e}", exc_info=True)

		# Auditoría de conflictos con otros complementos (tras breve espera para asegurar carga completa de NVDA)
		try:
			time.sleep(3.0)
			self._checkAddonConflicts(interactive=False)
		except Exception as e:
			log.error(f"MonitorSistema: Error durante la auditoría de conflictos: {e}", exc_info=True)

	def _initCpuQuery(self):
		self._cpuQuery = None
		self._cpuCounter = None
		self._baseGhz = 2.10
		self._maxTurboGhz = 4.00
		self._lastCpuCollectTime = 0
		try:
			import winreg
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
				counterPaths = [
					r"\Processor Information(_Total)\% Processor Performance",
					r"\Processor Information(0,_Total)\% Processor Performance",
					r"\Processor Information(0,0)\% Processor Performance",
					r"\Processor(_Total)\% Processor Time",
				]
				for cp in counterPaths:
					if pdh.PdhAddEnglishCounterW(hQuery, cp, None, byref(hCounter)) == 0:
						self._cpuQuery = hQuery
						self._cpuCounter = hCounter
						pdh.PdhCollectQueryData(self._cpuQuery)
						time.sleep(0.03)
						pdh.PdhCollectQueryData(self._cpuQuery)
						self._lastCpuCollectTime = time.time()
						log.info(f"MonitorSistema: Contador PDH CPU configurado exitosamente: {cp}")
						break
				if not self._cpuCounter:
					log.warning("MonitorSistema: Ningún contador de rendimiento de procesador pudo ser añadido.")
			else:
				log.warning("MonitorSistema: PdhOpenQueryW falló al abrir la consulta.")
		except Exception as e:
			log.error(f"MonitorSistema: Error general en _initCpuQuery: {e}", exc_info=True)
			self._cpuQuery = None

	def _queryDiskHealthSilent(self) -> list:
		try:
			import subprocess, json
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
				data = [data]
			return data
		except Exception as e:
			log.error(f"MonitorSistema: Error consultando salud de discos en segundo plano: {e}", exc_info=True)
			return []

	def _getGpuTemperatures(self) -> list[tuple[str, float]]:
		gpus = []
		try:
			for provider in self._gpuProviders:
				telemetry = provider.collect()
				if not telemetry:
					continue
				is_single = len(telemetry) == 1
				for index, item in enumerate(telemetry, start=1):
					if item.temperature:
						try:
							t_val = float(item.temperature)
							name = _("GPU") if is_single else _("GPU {}").format(index)
							gpus.append((name, t_val))
						except (ValueError, TypeError):
							pass
				if gpus:
					break
		except Exception as e:
			log.error(f"MonitorSistema: Error consultando temperaturas de GPU: {e}", exc_info=True)
		return gpus

	def _runAlertsLoop(self):
		import time, tones
		last_cpu_hot_thresh = None
		last_cpu_interval = None
		last_cpu_check_time = 0.0
		last_gpu_hot_thresh = None
		last_gpu_interval = None
		last_gpu_check_time = 0.0
		last_bt_thresh = None
		last_bt_interval = None
		last_bt_check_time = 0.0
		last_battery_interval = None
		last_battery_check_time = 0.0
		last_disk_interval = None
		last_disk_check_time = 0.0
		last_wlan_signal = None

		def _speak(text: str):
			try:
				queueHandler.queueFunction(queueHandler.eventQueue, ui.message, text)
			except Exception:
				wx.CallAfter(ui.message, text)

		# Esperar 8 segundos tras arrancar NVDA
		for wait_idx in range(8):
			if hasattr(self, "_stopAlertsEvent") and self._stopAlertsEvent.is_set():
				return
			time.sleep(1.0)

		while hasattr(self, "_stopAlertsEvent") and not self._stopAlertsEvent.is_set():
			try:
				if getattr(self, "_forceAlertsCheck", False):
					self._forceAlertsCheck = False
					last_battery_check_time = 0.0
					last_cpu_check_time = 0.0
					last_gpu_check_time = 0.0
					last_bt_check_time = 0.0
					last_disk_check_time = 0.0
					log.info("MonitorSistema: Comprobación inmediata de alertas forzada tras cambio de opciones")

				cfg = config.conf.get("monitorSistema", {})
				now = time.time()

				# 1. Chequeo de batería del equipo
				check_full = cfg.get("alertBatteryFull", True)
				check_low = cfg.get("alertBatteryLow", True)
				bat_interval = max(1, int(cfg.get("alertBatteryInterval", 1))) * 60
				if last_battery_interval != bat_interval:
					last_battery_interval = bat_interval
					last_battery_check_time = 0.0

				if (check_full or check_low) and (now - last_battery_check_time >= bat_interval):
					last_battery_check_time = now
					try:
						bat = psutil.sensors_battery()
						if bat:
							pct = bat.percent
							plugged = bat.power_plugged

							# Alerta de batería cargada (>= bat_full_thresh% y conectada)
							bat_full_thresh = int(cfg.get("alertBatteryFullThreshold", 100))
							if check_full and plugged and pct >= bat_full_thresh:
								if bat_full_thresh >= 100:
									msg = _("Batería completamente cargada al 100 %. Puedes desconectar el cargador.")
								else:
									msg = _("Batería cargada al {} %. Puedes desconectar el cargador.").format(round(pct))
								log.info(f"MonitorSistema: Alerta automática de batería cargada: '{msg}'")
								try: tones.beep(880, 100); tones.beep(1175, 150)
								except Exception: pass
								_speak(msg)

							# Alerta de batería baja (<= bat_thresh% y desconectada)
							bat_thresh = int(cfg.get("alertBatteryLowThreshold", 15))
							if check_low and not plugged and pct <= bat_thresh:
								msg = _("Advertencia: Batería baja al {} %. Conecta el equipo a la corriente.").format(round(pct))
								log.info(f"MonitorSistema: Alerta automática de batería baja: '{msg}'")
								try: tones.beep(440, 120); tones.beep(330, 150)
								except Exception: pass
								_speak(msg)
					except Exception as be:
						log.error(f"MonitorSistema: Error en chequeo de batería para alertas: {be}", exc_info=True)

				# 2. Alerta de temperatura alta de CPU (>= cpu_hot_thresh °C)
				check_hot = cfg.get("alertCpuHot", True)
				cpu_interval = max(1, int(cfg.get("alertCpuHotInterval", 1))) * 60
				cpu_hot_thresh = int(cfg.get("alertCpuHotThreshold", 85))
				if cpu_hot_thresh < 70:
					cpu_hot_thresh = 85
				if last_cpu_hot_thresh != cpu_hot_thresh or last_cpu_interval != cpu_interval:
					last_cpu_hot_thresh = cpu_hot_thresh
					last_cpu_interval = cpu_interval
					last_cpu_check_time = 0.0
					log.info(f"MonitorSistema: Umbral de alerta por temperatura de CPU: {cpu_hot_thresh} °C (intervalo: {cpu_interval // 60} min)")

				if check_hot and (now - last_cpu_check_time >= cpu_interval):
					last_cpu_check_time = now
					try:
						temp = self._getCpuTemperature()
						if temp is not None and temp >= cpu_hot_thresh:
							msg = _("Alerta: Temperatura del procesador alta ({}).").format(formatGpuTemperature(str(temp)))
							log.warning(f"MonitorSistema: Alerta automática de temperatura activada: '{msg}' (temp={temp}°C, umbral={cpu_hot_thresh}°C)")
							try: tones.beep(1000, 100); tones.beep(1000, 100)
							except Exception: pass
							_speak(msg)
					except Exception as te:
						log.error(f"MonitorSistema: Error en chequeo de temperatura para alertas: {te}", exc_info=True)

				# 3. Alerta de temperatura alta de GPU (>= gpu_hot_thresh °C)
				check_gpu_hot = cfg.get("alertGpuHot", True)
				gpu_interval = max(1, int(cfg.get("alertGpuHotInterval", 1))) * 60
				gpu_hot_thresh = int(cfg.get("alertGpuHotThreshold", 80))
				if gpu_hot_thresh < 70:
					gpu_hot_thresh = 80
				if last_gpu_hot_thresh != gpu_hot_thresh or last_gpu_interval != gpu_interval:
					last_gpu_hot_thresh = gpu_hot_thresh
					last_gpu_interval = gpu_interval
					last_gpu_check_time = 0.0
					log.info(f"MonitorSistema: Umbral de alerta por temperatura de GPU: {gpu_hot_thresh} °C (intervalo: {gpu_interval // 60} min)")

				if check_gpu_hot and (now - last_gpu_check_time >= gpu_interval):
					last_gpu_check_time = now
					try:
						gpu_temps = self._getGpuTemperatures()
						for g_name, g_temp in gpu_temps:
							if g_temp >= gpu_hot_thresh:
								msg = _("Alerta: Temperatura de {name} alta ({temp}).").format(
									name=g_name,
									temp=formatGpuTemperature(str(g_temp)),
								)
								log.warning(f"MonitorSistema: Alerta automática de temperatura de GPU activada: '{msg}' (temp={g_temp}°C, umbral={gpu_hot_thresh}°C)")
								try: tones.beep(1200, 100); tones.beep(1200, 100)
								except Exception: pass
								_speak(msg)
					except Exception as ge:
						log.error(f"MonitorSistema: Error en chequeo de temperatura de GPU para alertas: {ge}", exc_info=True)

				# 4. Alerta de batería baja en dispositivos Bluetooth (<= bt_thresh%)
				check_bt = cfg.get("alertBluetoothLow", True)
				bt_thresh = int(cfg.get("alertBluetoothLowThreshold", 15))
				bt_interval = max(1, int(cfg.get("alertBluetoothLowInterval", 2))) * 60
				if last_bt_thresh != bt_thresh or last_bt_interval != bt_interval:
					last_bt_thresh = bt_thresh
					last_bt_interval = bt_interval
					last_bt_check_time = 0.0
					log.info(f"MonitorSistema: Umbral de alerta Bluetooth: {bt_thresh} % (intervalo: {bt_interval // 60} min)")

				if check_bt and (now - last_bt_check_time >= bt_interval):
					last_bt_check_time = now
					try:
						bt_devices = self._queryBluetoothBatteries()
						for d in bt_devices:
							d_name = d.get('name', _('Dispositivo Bluetooth'))
							d_bat = d.get('battery')
							if d_bat is not None and 0 <= d_bat <= bt_thresh:
								msg = _("Advertencia: Batería baja en el dispositivo Bluetooth {} al {} %.").format(d_name, d_bat)
								log.warning(f"MonitorSistema: Alerta automática Bluetooth: '{msg}'")
								try: tones.beep(550, 100); tones.beep(440, 150)
								except Exception: pass
								_speak(msg)
					except Exception as bte:
						log.error(f"MonitorSistema: Error en chequeo de batería Bluetooth para alertas: {bte}", exc_info=True)

				# 5. Alerta periódica de salud y desgaste de discos (HDD / SSD)
				check_disk = cfg.get("alertDiskHealth", True)
				wear_thresh = int(cfg.get("alertDiskWearThreshold", 80))
				disk_interval = max(1, int(cfg.get("alertDiskHealthInterval", 240))) * 60
				if last_disk_interval != disk_interval:
					last_disk_interval = disk_interval
					last_disk_check_time = 0.0

				if check_disk and (now - last_disk_check_time >= disk_interval):
					last_disk_check_time = now
					def _diskWorker():
						try:
							disks = self._queryDiskHealthSilent()
							for d in disks:
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
									try: tones.beep(330, 150); tones.beep(220, 200)
									except Exception: pass
									_speak(msg)

								# Límite de desgaste de vida útil en discos SSD
								if wear is not None:
									try:
										wear_val = int(wear)
										if wear_val >= wear_thresh:
											msg = _("Advertencia: El disco SSD {} ha alcanzado un {} % de desgaste de su vida útil.").format(name, wear_val)
											log.warning(f"MonitorSistema: Alerta de desgaste SSD: '{msg}'")
											try: tones.beep(440, 150); tones.beep(330, 200)
											except Exception: pass
											_speak(msg)
									except (ValueError, TypeError):
										pass
						except Exception as dke:
							log.error(f"MonitorSistema: Error en chequeo de salud de discos: {dke}", exc_info=True)
					threading.Thread(target=_diskWorker, daemon=True).start()
			except Exception as e:
				log.error(f"MonitorSistema: Error general en bucle de alertas: {e}", exc_info=True)

			for sec in range(5):
				if hasattr(self, "_stopAlertsEvent") and self._stopAlertsEvent.is_set():
					break
				if getattr(self, "_forceAlertsCheck", False):
					break
				if sec % 2 == 0:
					try:
						if config.conf.get("monitorSistema", {}).get("alertWlanSignalChange", False):
							cur_sig = self._getCurrentWlanSignal()
							if cur_sig is not None:
								if last_wlan_signal is not None and cur_sig != last_wlan_signal:
									last_wlan_signal = cur_sig
									freq = int(350 + (cur_sig * 8.5))
									try:
										tones.beep(freq, 70)
									except Exception:
										pass
									msg = _("Señal de Wi-Fi: {} %.").format(cur_sig)
									log.info(f"MonitorSistema: Alerta de cambio de señal Wi-Fi: {cur_sig}%")
									_speak(msg)
								elif last_wlan_signal is None:
									last_wlan_signal = cur_sig
							else:
								last_wlan_signal = None
						else:
							last_wlan_signal = None
					except Exception as we:
						log.error(f"MonitorSistema: Error comprobando señal Wi-Fi en loop: {we}", exc_info=True)
				time.sleep(1.0)

	def terminate(self):
		log.info("Monitor del Sistema: Finalizando complemento...")
		if hasattr(self, "_stopAlertsEvent"):
			self._stopAlertsEvent.set()
		super().terminate()
		self._gpuProviders.clear()
		if MonitorSistemaSettingsPanel in NVDASettingsDialog.categoryClasses:
			NVDASettingsDialog.categoryClasses.remove(MonitorSistemaSettingsPanel)
		if self._cpuQuery:
			try:
				ctypes.windll.pdh.PdhCloseQuery(self._cpuQuery)
			except Exception:
				pass
			self._cpuQuery = None
		if self._client_handle:
			self._negotiated_version = None
			try:
				wlanapi.WlanRegisterNotification(
				self._client_handle,
				wlanapi.WLAN_NOTIFICATION_SOURCE_NONE,
				True,
				notifyHandler,
				None,
				None,
				None,
			)
				wlanapi.WlanCloseHandle(
					byref(self._client_handle),
					None,
				)
				self._client_handle = None
			except OSError:
				pass
		log.info("Monitor del Sistema: Recursos y manejadores liberados, complemento finalizado limpiamente.")

	@scriptHandler.script(
		description=_("Presenta la memoria RAM utilizada y la carga promedio del procesador."), category=scriptCategory,
		gesture="kb:nvda+shift+e",
		speakOnDemand=True,
	)
	def script_announceResourceSummary(self, gesture: inputCore.InputGesture):
		try:
			info = "{}% de RAM utilizada, CPU al {}%.".format(
				tryTrunk(psutil.virtual_memory()[2]), tryTrunk(psutil.cpu_percent())
			)
			log.info(f"MonitorSistema: script_announceResourceSummary - Anunciando al usuario: '{info}'")
			ui.message(info)
		except Exception as e:
			log.error(f"MonitorSistema: Error en script_announceResourceSummary: {e}", exc_info=True)
			ui.message(_("Error al obtener el resumen del sistema."))

	def _getCpuTemperature(self) -> float | int | None:
		# 1. AMD ADL (procesadores AMD Ryzen / APUs Radeon)
		for dll_name in ("atiadlxx.dll", "atiadlxy.dll"):
			try:
				adl = ctypes.WinDLL(dll_name)
				ALLOC_FUNC = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_size_t)
				def adl_alloc(size):
					return ctypes.windll.kernel32.LocalAlloc(0x0040, size)
				adl_alloc_cb = ALLOC_FUNC(adl_alloc)
				
				if adl.ADL_Main_Control_Create(adl_alloc_cb, 1) == 0:
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
								log.info(f"MonitorSistema: Temperatura CPU obtenida via AMD ADL ({dll_name}): {temp_val} C")
					adl.ADL_Main_Control_Destroy()
					if temp_val is not None:
						return temp_val
			except Exception:
				pass

		# 2. WMI ACPI & Hardware Monitors
		try:
			import comtypes.client
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
							log.info(f"MonitorSistema: Temperatura CPU obtenida via MSAcpi: {round(c)} C")
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
							log.info(f"MonitorSistema: Temperatura CPU obtenida via ThermalZoneInformation: {round(c)} C")
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
								log.info(f"MonitorSistema: Temperatura CPU obtenida via {ns}: {round(val)} C")
								return round(val)
				except Exception:
					pass
		except Exception as e:
			log.debug(f"MonitorSistema: Error consultando temperatura de CPU: {e}")
		return None

	@scriptHandler.script(
		description=_("Presenta la carga promedio del procesador y la carga de cada núcleo. Si se pulsa dos veces, copia la información al portapapeles."), category=scriptCategory,
		gesture="kb:nvda+shift+1",
		speakOnDemand=True,
	)
	def script_announceProcessorInfo(self, gesture: inputCore.InputGesture):
		try:
			averageLoad = psutil.cpu_percent()
			perCpuLoad = psutil.cpu_percent(percpu=True)
			coreLoad = [
				"Núcleo {}: {}%".format(core, tryTrunk(cpuLoad))
				for core, cpuLoad in enumerate(perCpuLoad, start=1)
			]

			if psutil.cpu_count() == 1:
				info = _("Carga de CPU al {}%.").format(tryTrunk(averageLoad))
			else:
				info = _("Carga media de CPU al {}%, {}.").format(
					tryTrunk(averageLoad), ", ".join(coreLoad)
				)
			if scriptHandler.getLastScriptRepeatCount() == 0:
				log.info(f"MonitorSistema: script_announceProcessorInfo - Anunciando al usuario: '{info}'")
				ui.message(info)
			else:
				log.info(f"MonitorSistema: script_announceProcessorInfo - Copiando al portapapeles: '{info}'")
				api.copyToClip(info, notify=True)
		except Exception as e:
			log.error(f"MonitorSistema: Error en script_announceProcessorInfo: {e}", exc_info=True)
			ui.message(_("Error al obtener la información del procesador."))

	@scriptHandler.script(
		description=_("Presenta el espacio utilizado y total de la memoria RAM física y virtual. Si se pulsa dos veces, copia la información al portapapeles."), category=scriptCategory,
		gesture="kb:nvda+shift+2",
		speakOnDemand=True,
	)
	def script_announceRamInfo(self, gesture: inputCore.InputGesture):
		try:
			memory = psutil.virtual_memory()
			physicalRamUsed, physicalRamTotal = memory.used, memory.total
			info = "Física: {physicalUsed} de {physicalTotal} utilizada ({physicalPercent}%). ".format(
				physicalUsed=size(physicalRamUsed, alternative),
				physicalTotal=size(physicalRamTotal, alternative),
				physicalPercent=tryTrunk(round(physicalRamUsed / physicalRamTotal * 100, 1)),
			)
			virtualMemory = psutil._psutil_windows.virtual_mem()
			virtualRamUsed, virtualRamTotal = virtualMemory[2] - virtualMemory[3], virtualMemory[2]
			info += "Virtual: {virtualUsed} de {virtualTotal} utilizada ({virtualPercent}%).".format(
				virtualUsed=size(virtualRamUsed, alternative),
				virtualTotal=size(virtualRamTotal, alternative),
				virtualPercent=tryTrunk(round(virtualRamUsed / virtualRamTotal * 100, 1)),
			)
			if scriptHandler.getLastScriptRepeatCount() == 0:
				log.info(f"MonitorSistema: script_announceRamInfo - Anunciando al usuario: '{info}'")
				ui.message(info)
			else:
				log.info(f"MonitorSistema: script_announceRamInfo - Copiando al portapapeles: '{info}'")
				api.copyToClip(info, notify=True)
		except Exception as e:
			log.error(f"MonitorSistema: Error en script_announceRamInfo: {e}", exc_info=True)
			ui.message(_("Error al obtener la información de la memoria RAM."))

	def _resolveMaxTurbo(self, procName: str, baseGhz: float) -> float:
		name_lower = (procName or "").lower()

		# AMD Ryzen 9
		if "9950x" in name_lower or "9900x" in name_lower:
			return 5.70
		if "7950x3d" in name_lower or "7950x" in name_lower:
			return 5.70
		if "7900x3d" in name_lower or "7900x" in name_lower:
			return 5.60
		if "7900" in name_lower or "7945hx" in name_lower or "7945h" in name_lower:
			return 5.40
		if "7940hs" in name_lower or "7940hx" in name_lower:
			return 5.20
		if "5950x" in name_lower:
			return 4.90
		if "5900x" in name_lower or "5900hx" in name_lower or "5900hs" in name_lower:
			return 4.80
		if "3950x" in name_lower or "3900xt" in name_lower:
			return 4.70
		if "3900x" in name_lower:
			return 4.60

		# AMD Ryzen 7
		if "9800x3d" in name_lower or "9700x" in name_lower:
			return 5.50
		if "7800x3d" in name_lower:
			return 5.00
		if "7700x" in name_lower:
			return 5.40
		if "7700" in name_lower:
			return 5.30
		if "7745hx" in name_lower or "7735hs" in name_lower or "7735u" in name_lower:
			return 4.75
		if "6800h" in name_lower or "6800u" in name_lower:
			return 4.70
		if "5800x3d" in name_lower:
			return 4.50
		if "5800x" in name_lower:
			return 4.70
		if "5800h" in name_lower or "5800u" in name_lower or "5850u" in name_lower:
			return 4.40
		if "5700x3d" in name_lower or "5700x" in name_lower or "5700g" in name_lower:
			return 4.60
		if "5700u" in name_lower:
			return 4.30
		if "4800h" in name_lower or "4800u" in name_lower:
			return 4.20
		if "4700u" in name_lower or "4750u" in name_lower:
			return 4.10
		if "3800x" in name_lower or "3700x" in name_lower:
			return 4.50

		# AMD Ryzen 5
		if "9600x" in name_lower:
			return 5.40
		if "7600x" in name_lower:
			return 5.30
		if "7600" in name_lower:
			return 5.10
		if "7640hs" in name_lower or "7535hs" in name_lower or "7535u" in name_lower:
			return 4.90
		if "7530u" in name_lower:
			return 4.50
		if "6600h" in name_lower or "6600u" in name_lower:
			return 4.50
		if "5600x" in name_lower:
			return 4.60
		if "5600g" in name_lower or "5600h" in name_lower:
			return 4.40
		if "5600u" in name_lower or "5650u" in name_lower:
			return 4.20
		if "5500u" in name_lower:
			return 4.00
		if "4650u" in name_lower or "4600u" in name_lower or "4600h" in name_lower or "4500u" in name_lower:
			return 4.00
		if "3600x" in name_lower or "3600xt" in name_lower:
			return 4.40
		if "3600" in name_lower:
			return 4.20

		# AMD Ryzen 3
		if "5300u" in name_lower or "4300u" in name_lower:
			return 3.80
		if "3300x" in name_lower:
			return 4.30
		if "3100" in name_lower:
			return 3.90

		# Intel Core 14th / 13th / 12th / 11th / 10th Gen & Core Ultra
		if "14900k" in name_lower or "14900ks" in name_lower:
			return 6.00
		if "14900hx" in name_lower or "14700k" in name_lower or "285k" in name_lower:
			return 5.80
		if "14700hx" in name_lower or "14600k" in name_lower:
			return 5.50
		if "13900k" in name_lower or "13900ks" in name_lower:
			return 5.80
		if "13900h" in name_lower or "13900hx" in name_lower or "13700k" in name_lower:
			return 5.40
		if "13700h" in name_lower or "13700hx" in name_lower or "13600k" in name_lower:
			return 5.00
		if "13500h" in name_lower or "13400" in name_lower:
			return 4.70
		if "12900k" in name_lower or "12900h" in name_lower:
			return 5.20
		if "12700k" in name_lower or "12700h" in name_lower:
			return 5.00
		if "12600k" in name_lower or "12500h" in name_lower:
			return 4.90
		if "11900k" in name_lower or "11900h" in name_lower:
			return 5.30
		if "11800h" in name_lower or "11700k" in name_lower:
			return 5.00
		if "1165g7" in name_lower:
			return 4.70
		if "1135g7" in name_lower or "11400h" in name_lower:
			return 4.50
		if "10750h" in name_lower or "10700k" in name_lower:
			return 5.00
		if "10500h" in name_lower or "10400" in name_lower:
			return 4.50
		if "185h" in name_lower or "165h" in name_lower:
			return 5.10
		if "155h" in name_lower or "125h" in name_lower:
			return 4.80

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
		currGhz = None
		try:
			if not self._cpuQuery or not self._cpuCounter:
				self._initCpuQuery()

			if self._cpuQuery and self._cpuCounter:
				now = time.time()
				if now - self._lastCpuCollectTime < 0.08:
					time.sleep(0.08)

				pdh = ctypes.windll.pdh
				pdh.PdhCollectQueryData(self._cpuQuery)
				self._lastCpuCollectTime = time.time()

				val = PDH_FMT_COUNTERVALUE()
				res = pdh.PdhGetFormattedCounterValue(
					self._cpuCounter, 0x00000200, None, byref(val)
				)
				if res == 0 and val.CStatus == 0 and val.doubleValue > 0:
					pctPerf = val.doubleValue
					currGhz = (pctPerf / 100.0) * self._baseGhz
					log.info(f"MonitorSistema: Muestra PDH CPU: {pctPerf:.1f}%, calculada={currGhz:.2f} GHz (Base={self._baseGhz} GHz, Max Turbo={self._maxTurboGhz} GHz)")
				else:
					# Recuperación automática: recrear query PDH con doble muestra
					self._initCpuQuery()
					if self._cpuQuery and self._cpuCounter:
						time.sleep(0.05)
						pdh.PdhCollectQueryData(self._cpuQuery)
						self._lastCpuCollectTime = time.time()
						val = PDH_FMT_COUNTERVALUE()
						res = pdh.PdhGetFormattedCounterValue(
							self._cpuCounter, 0x00000200, None, byref(val)
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

		if currGhz:
			if currGhz > self._maxTurboGhz:
				currGhz = self._maxTurboGhz

			if currGhz > self._baseGhz:
				pct = tryTrunk(round((currGhz / self._maxTurboGhz) * 100, 1))
				return "{curr:.2f} GHz de {maxTurbo:.2f} GHz máximos ({pct}%), turbo activo.".format(
					curr=currGhz, maxTurbo=self._maxTurboGhz, pct=pct
				)
			else:
				pct = tryTrunk(round((currGhz / self._baseGhz) * 100, 1))
				return "{curr:.2f} GHz de {base:.2f} GHz velocidad base ({pct}%).".format(
					curr=currGhz, base=self._baseGhz, pct=pct
				)

		return "No se pudo obtener la velocidad del procesador en tiempo real."

	@scriptHandler.script(
		description=_("Anuncia la velocidad y frecuencia actual del procesador (GHz), velocidad base y estado del modo turbo boost. Si se pulsa dos veces, copia la información al portapapeles."), category=scriptCategory,
		gesture="kb:nvda+shift+5",
		speakOnDemand=True,
	)
	def script_announceCpuFrequency(self, gesture: inputCore.InputGesture):
		try:
			info = self._getCpuFrequencyInfo()
			if scriptHandler.getLastScriptRepeatCount() == 0:
				log.info(f"MonitorSistema: script_announceCpuFrequency - Anunciando al usuario: '{info}'")
				ui.message(info)
			else:
				log.info(f"MonitorSistema: script_announceCpuFrequency - Copiando al portapapeles: '{info}'")
				api.copyToClip(info, notify=True)
		except Exception as e:
			log.error(f"MonitorSistema: Error en script_announceCpuFrequency: {e}", exc_info=True)
			ui.message(_("Error al obtener la frecuencia del procesador."))

	@scriptHandler.script(
		description=_("Presenta el espacio utilizado y total de las unidades de disco fijas, extraíbles y de red. Si se pulsa dos veces, copia la información al portapapeles."), category=scriptCategory,
		gesture="kb:nvda+shift+3",
		speakOnDemand=True,
	)
	def script_announceDriveInfo(self, gesture: inputCore.InputGesture):
		try:
			info = []
			for drive in psutil.disk_partitions(all=True):
				if not drive.fstype:
					continue
				isNetworkDrive = "remote" in drive.opts.split(",")
				try:
					driveInfo = psutil.disk_usage(drive[0])
				except OSError:
					if isNetworkDrive:
						info.append(_("{} (unidad de red): no disponible.").format(drive[0]))
					continue
				driveType = _("de red") if isNetworkDrive else _("fijo")
				info.append(
					_("{driveName} (disco {driveType}): {usedSpace} de {totalSpace} utilizados ({percent}%).").format(
						driveName=drive[0],
						driveType=driveType,
						usedSpace=size(driveInfo[1], alternative),
						totalSpace=size(driveInfo[0], alternative),
						percent=tryTrunk(driveInfo[3]),
					)
				)
			text = " ".join(info) if info else _("No se encontraron unidades de disco disponibles.")
			if scriptHandler.getLastScriptRepeatCount() == 0:
				log.info(f"MonitorSistema: script_announceDriveInfo - Anunciando al usuario: '{text}'")
				ui.message(text)
			else:
				log.info(f"MonitorSistema: script_announceDriveInfo - Copiando al portapapeles: '{text}'")
				api.copyToClip(text, notify=True)
		except Exception as e:
			log.error(f"MonitorSistema: Error en script_announceDriveInfo: {e}", exc_info=True)
			ui.message(_("Error al obtener la información de las unidades de disco."))

	def _getWlanInfo(self) -> str:
		if not self._client_handle:
			return _("No hay dispositivos de red inalámbrica")

		wlan_ifaces = POINTER(wlanapi.WLAN_INTERFACE_INFO_LIST)()
		wlanapi.WlanEnumInterfaces(self._client_handle, None, byref(wlan_ifaces))

		if wlan_ifaces.contents.NumberOfItems == 0:
			wlanapi.WlanFreeMemory(wlan_ifaces)
			return _("No hay dispositivos de red inalámbrica")

		info = _("No hay conexiones de red inalámbrica")
		for i in customResize(wlan_ifaces.contents.InterfaceInfo, wlan_ifaces.contents.NumberOfItems):
			if i.isState != wlanapi.wlan_interface_state_connected:
				continue

			wlan_available_network_list = POINTER(wlanapi.WLAN_AVAILABLE_NETWORK_LIST)()
			wlanapi.WlanGetAvailableNetworkList(
				self._client_handle, byref(i.InterfaceGuid), 0, None, byref(wlan_available_network_list)
			)
			for n in customResize(
				wlan_available_network_list.contents.Network,
				wlan_available_network_list.contents.NumberOfItems,
			):
				if n.Flags & wlanapi.WLAN_AVAILABLE_NETWORK_CONNECTED:
					ssid_str = n.dot11Ssid.SSID.decode(errors="ignore")
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
			wlanapi.WlanFreeMemory(wlan_available_network_list)
		wlanapi.WlanFreeMemory(wlan_ifaces)
		return info

	def _getCurrentWlanSignal(self) -> int | None:
		if not self._client_handle:
			return None
		try:
			wlan_ifaces = POINTER(wlanapi.WLAN_INTERFACE_INFO_LIST)()
			if wlanapi.WlanEnumInterfaces(self._client_handle, None, byref(wlan_ifaces)) != 0:
				return None
			if wlan_ifaces.contents.NumberOfItems == 0:
				wlanapi.WlanFreeMemory(wlan_ifaces)
				return None
			signal = None
			for i in customResize(wlan_ifaces.contents.InterfaceInfo, wlan_ifaces.contents.NumberOfItems):
				if i.isState != wlanapi.wlan_interface_state_connected:
					continue
				wlan_available_network_list = POINTER(wlanapi.WLAN_AVAILABLE_NETWORK_LIST)()
				if wlanapi.WlanGetAvailableNetworkList(
					self._client_handle, byref(i.InterfaceGuid), 0, None, byref(wlan_available_network_list)
				) == 0:
					for n in customResize(
						wlan_available_network_list.contents.Network,
						wlan_available_network_list.contents.NumberOfItems,
					):
						if n.Flags & wlanapi.WLAN_AVAILABLE_NETWORK_CONNECTED:
							signal = int(n.wlanSignalQuality)
							break
					wlanapi.WlanFreeMemory(wlan_available_network_list)
				if signal is not None:
					break
			wlanapi.WlanFreeMemory(wlan_ifaces)
			return signal
		except Exception as e:
			log.error(f"MonitorSistema: Error consultando señal WLAN: {e}", exc_info=True)
			return None

	@scriptHandler.script(
		description=_("Anuncia el nombre de la red inalámbrica (SSID), intensidad de la señal y protocolo de seguridad. Si se pulsa dos veces, copia la información al portapapeles."),
		gesture="kb:nvda+shift+4",
		speakOnDemand=True,
	)
	def script_wlanStatusReport(self, gesture: inputCore.InputGesture):
		if scriptHandler.getLastScriptRepeatCount() == 0:
			try:
				info = self._getWlanInfo()
				log.info(f"MonitorSistema: script_wlanStatusReport - Anunciando al usuario: '{info}'")
				ui.message(info)
			except Exception as e:
				log.error(f"MonitorSistema: Error en script_wlanStatusReport: {e}", exc_info=True)
				ui.message(_("Error al obtener el estado de la red inalámbrica."))
		else:
			try:
				info = self._getWlanInfo()
				log.info(f"MonitorSistema: script_wlanStatusReport - Copiando al portapapeles: '{info}'")
				api.copyToClip(info, notify=True)
			except Exception as e:
				log.error(f"MonitorSistema: Error en script_wlanStatusReport copia: {e}", exc_info=True)

	@scriptHandler.script(
		description=_("Anuncia la versión de Windows y arquitectura del sistema. Si se pulsa dos veces, copia la información al portapapeles."),
		gesture="kb:nvda+shift+6",
		speakOnDemand=True,
	)
	def script_announceWinVer(self, gesture: inputCore.InputGesture):
		try:
			info = getWinVer()
			if scriptHandler.getLastScriptRepeatCount() == 0:
				log.info(f"MonitorSistema: script_announceWinVer - Anunciando al usuario: '{info}'")
				ui.message(info)
			else:
				log.info(f"MonitorSistema: script_announceWinVer - Copiando al portapapeles: '{info}'")
				api.copyToClip(info, notify=True)
		except Exception as e:
			log.error(f"MonitorSistema: Error en script_announceWinVer: {e}", exc_info=True)
			ui.message(_("Error al obtener la versión de Windows."))

	def getUptime(self) -> str:
		bootTimestamp = psutil.boot_time()
		if bootTimestamp == 0.0:
			raise TypeError
		uptime = datetime.now() - datetime.fromtimestamp(bootTimestamp)
		hours, remainingMinutes = divmod(uptime.seconds, 3600)
		minutes, seconds = divmod(remainingMinutes, 60)
		uptimeComponents = []
		if uptime.days > 0:
			uptimeComponents.append("{} {}".format(uptime.days, "día" if uptime.days == 1 else "días"))
		if hours > 0:
			uptimeComponents.append("{} {}".format(hours, "hora" if hours == 1 else "horas"))
		if minutes > 0:
			uptimeComponents.append("{} {}".format(minutes, "minuto" if minutes == 1 else "minutos"))
		uptimeComponents.append("{} {}".format(seconds, "segundo" if seconds == 1 else "segundos"))
		res = ", ".join(uptimeComponents)
		log.info(f"MonitorSistema: Tiempo de actividad calculado desde arranque ({datetime.fromtimestamp(bootTimestamp).strftime('%Y-%m-%d %H:%M:%S')}): {res}")
		return res

	@scriptHandler.script(
		description=_("Anuncia el tiempo de actividad del sistema. Si se pulsa dos veces, copia la información al portapapeles."),
		gesture="kb:nvda+shift+7",
		speakOnDemand=True,
	)
	def script_announceUptime(self, gesture: inputCore.InputGesture):
		try:
			uptime = self.getUptime()
			if scriptHandler.getLastScriptRepeatCount() == 0:
				log.info(f"MonitorSistema: script_announceUptime - Anunciando al usuario: '{uptime}'")
				ui.message(uptime)
			else:
				log.info(f"MonitorSistema: script_announceUptime - Copiando al portapapeles: '{uptime}'")
				api.copyToClip(uptime, notify=True)
		except Exception as e:
			log.error(f"MonitorSistema: Error en script_announceUptime: {e}", exc_info=True)
			ui.message("No se pudo obtener el tiempo de actividad del sistema.")

	def _getGpuInfo(self) -> str:
		hasProvider = False
		hasFailure = False
		for provider in self._gpuProviders:
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
		gesture="kb:nvda+shift+8",
		speakOnDemand=True,
	)
	@blockAction.when(blockAction.Context.SECURE_MODE)
	def script_announceGpuInfo(self, gesture: inputCore.InputGesture):
		try:
			info = self._getGpuInfo()
			if scriptHandler.getLastScriptRepeatCount() == 0:
				log.info(f"MonitorSistema: script_announceGpuInfo - Anunciando al usuario: '{info}'")
				ui.message(info)
			else:
				log.info(f"MonitorSistema: script_announceGpuInfo - Copiando al portapapeles: '{info}'")
				api.copyToClip(info, notify=True)
		except Exception as e:
			log.error(f"MonitorSistema: Error en script_announceGpuInfo: {e}", exc_info=True)
			ui.message("Error al obtener información de la tarjeta gráfica.")

	def _getDiskHealth(self):
		import subprocess, json, threading, tempfile, os, base64, time, ctypes, tones
		self._diskHealthRunning = True
		def worker():
			stop_event = threading.Event()
			def beeper():
				try: tones.beep(440, 40)
				except Exception: pass
				while not stop_event.wait(0.6):
					try: tones.beep(440, 40)
					except Exception: pass
			threading.Thread(target=beeper, daemon=True).start()
			log.info("MonitorSistema: Iniciando escaneo elevado de salud de discos...")
			try:
				tmp_file = os.path.join(tempfile.gettempdir(), "nvda_disk_health.json")
				if os.path.exists(tmp_file):
					try: os.remove(tmp_file)
					except Exception: pass
				
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
				$results | ConvertTo-Json -Compress | Out-File -FilePath '{tmp_file}' -Encoding UTF8
				"""
				encoded = base64.b64encode(ps_script.encode('utf-16le')).decode('utf-8')
				log.info("MonitorSistema: Lanzando PowerShell con ShellExecuteW...")
				ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", f"-NoProfile -WindowStyle Hidden -EncodedCommand {encoded}", None, 0)
				
				timeout = 15
				while timeout > 0:
					if os.path.exists(tmp_file):
						time.sleep(0.5)
						break
					time.sleep(1)
					timeout -= 1
				
				if not os.path.exists(tmp_file):
					log.warning("MonitorSistema: Archivo no encontrado, UAC rechazado o expiró el tiempo de espera.")
					err_msg = _("No se pudo obtener información de los discos o se canceló el permiso de administrador.")
					wx.CallAfter(ui.message, err_msg)
					return
					
				with open(tmp_file, 'r', encoding='utf-8-sig') as f:
					output = f.read().strip()
				try: os.remove(tmp_file)
				except Exception: pass
				
				if not output:
					log.warning("MonitorSistema: Salida de Get-PhysicalDisk vacía.")
					err_msg = _("No se pudo obtener información de los discos.")
					wx.CallAfter(ui.message, err_msg)
					return
					
				data = json.loads(output)
				if isinstance(data, dict): data = [data]
				log.info(f"MonitorSistema: Discos detectados ({len(data)}): {data}")
				
				parts = []
				for disk in data:
					name = disk.get("Name", _("Disco desconocido"))
					dtype = disk.get("Type", _("Desconocido"))
					health = disk.get("Health", _("Desconocido"))
					temp = disk.get("Temp")
					wear = disk.get("Wear")
					if dtype == "SSD": dtype = _("estado sólido (SSD)")
					elif dtype == "HDD": dtype = _("rígido (HDD)")
					if health == "Healthy": health = _("Saludable")
					elif health == "Warning": health = _("En riesgo (Advertencia)")
					elif health == "Unhealthy": health = _("Dañado (Crítico)")
					
					part = _("Disco {}: Tipo {}. Estado general: {}.").format(name, dtype, health)
					if temp is not None: 
						part += " " + _("Temperatura: {} grados celsius.").format(temp)
					if wear is not None and dtype == _("estado sólido (SSD)"):
						health_pct = 100 - int(wear)
						part += " " + _("Desgaste de vida útil: {} por ciento (Salud: {}%).").format(int(wear), health_pct)
					parts.append(part)
					
				result = " ".join(parts) if parts else _("No se encontraron discos.")
				self._lastDiskHealthResult = result
				log.info(f"MonitorSistema: Anunciando salud de discos: {result}")
				wx.CallAfter(ui.message, result)
				if getattr(self, "_copyDiskHealthOnFinish", False):
					self._copyDiskHealthOnFinish = False
					wx.CallAfter(api.copyToClip, result, notify=True)
			except Exception as e:
				log.error(f"MonitorSistema: Error en worker de salud de discos: {e}", exc_info=True)
				wx.CallAfter(ui.message, _("Error al consultar discos."))
			finally:
				self._diskHealthRunning = False
				stop_event.set()
		ui.message(_("Analizando discos, por favor espera..."))
		threading.Thread(target=worker, daemon=True).start()

	@scriptHandler.script(
		description=_("Anuncia el estado de salud (S.M.A.R.T), temperatura y vida útil de los discos físicos. Si se pulsa dos veces, copia la información al portapapeles."),
		gesture="kb:nvda+shift+control+1",
		speakOnDemand=True,
	)
	def script_announceDiskHealth(self, gesture: inputCore.InputGesture):
		if scriptHandler.getLastScriptRepeatCount() > 0:
			if self._diskHealthRunning:
				self._copyDiskHealthOnFinish = True
				ui.message(_("Se copiará el resultado al portapapeles."))
				return
			if self._lastDiskHealthResult:
				api.copyToClip(self._lastDiskHealthResult, notify=True)
				return
			self._copyDiskHealthOnFinish = True
			ui.message(_("Se copiará el resultado al portapapeles."))
			self._getDiskHealth()
			return
		if self._diskHealthRunning:
			ui.message(_("El análisis de discos ya está en curso, por favor espera..."))
			return
		self._copyDiskHealthOnFinish = False
		self._getDiskHealth()

	def _getTopProcesses(self):
		import psutil, threading, wx, ui, time
		self._topProcessesRunning = True
		def worker():
			log.info("MonitorSistema: Iniciando análisis de Top Procesos...")
			try:
				for p in psutil.process_iter(['name', 'cpu_percent']): pass
				time.sleep(0.5)
				max_cpu, max_cpu_p, max_mem, max_mem_p = -1, None, -1, None
				for p in psutil.process_iter(['name', 'cpu_percent', 'memory_info']):
					try:
						cpu, mem, name = p.info['cpu_percent'], p.info['memory_info'].rss, p.info['name']
						if cpu is not None and cpu > max_cpu and name != "System Idle Process":
							max_cpu, max_cpu_p = cpu, name
						if mem is not None and mem > max_mem:
							max_mem, max_mem_p = mem, name
					except (psutil.NoSuchProcess, psutil.AccessDenied): pass
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
				self._topProcessesRunning = False
			wx.CallAfter(ui.message, msg)
			if getattr(self, "_copyTopProcessesOnFinish", False):
				self._copyTopProcessesOnFinish = False
				wx.CallAfter(api.copyToClip, msg, notify=True)
		ui.message(_("Analizando procesos..."))
		threading.Thread(target=worker, daemon=True).start()

	@scriptHandler.script(
		description=_("Anuncia los procesos que más CPU y RAM consumen actualmente. Si se pulsa dos veces, copia la información al portapapeles."),
		gesture="kb:nvda+shift+control+2",
		speakOnDemand=True,
	)
	def script_announceTopProcesses(self, gesture: inputCore.InputGesture):
		if scriptHandler.getLastScriptRepeatCount() > 0:
			if self._topProcessesRunning:
				self._copyTopProcessesOnFinish = True
				ui.message(_("Se copiará el resultado al portapapeles."))
				return
			if self._lastTopProcessesResult:
				api.copyToClip(self._lastTopProcessesResult, notify=True)
				return
			self._copyTopProcessesOnFinish = True
			ui.message(_("Se copiará el resultado al portapapeles."))
			self._getTopProcesses()
			return
		if self._topProcessesRunning:
			ui.message(_("El análisis de procesos ya está en curso, por favor espera..."))
			return
		self._copyTopProcessesOnFinish = False
		self._getTopProcesses()

	def _getNetworkSpeed(self):
		import threading, wx, ui, time, urllib.request, os, tones, subprocess, re
		self._netSpeedRunning = True
		def worker():
			stop_event = threading.Event()
			def beeper():
				try: tones.beep(880, 40)
				except Exception: pass
				while not stop_event.wait(0.6):
					try: tones.beep(880, 40)
					except Exception: pass
			threading.Thread(target=beeper, daemon=True).start()
			log.info("MonitorSistema: Iniciando Speedtest de red...")
			msg = _("Error al medir la velocidad de Internet.")
			try:
				ping_val = None
				try:
					creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
					res_ping = subprocess.run(
						["ping", "-n", "2", "-w", "1000", "1.1.1.1"],
						capture_output=True,
						text=True,
						creationflags=creationflags,
					)
					m = (
						re.search(r'Media = (\d+)ms', res_ping.stdout, re.IGNORECASE)
						or re.search(r'Average = (\d+)ms', res_ping.stdout, re.IGNORECASE)
						or re.search(r'tiempo[=<](\d+)ms', res_ping.stdout, re.IGNORECASE)
						or re.search(r'time[=<](\d+)ms', res_ping.stdout, re.IGNORECASE)
					)
					if m:
						ping_val = m.group(1)
						log.info(f"MonitorSistema: Latencia medida: {ping_val} ms")
					else:
						log.warning(f"MonitorSistema: No se pudo extraer la latencia del ping a 1.1.1.1: {res_ping.stdout.strip()}")
				except Exception as ping_err:
					log.warning(f"MonitorSistema: Error midiendo ping: {ping_err}")

				start_down = time.time()
				dl_bytes = 0
				total_dl_bytes = 0
				measure_start_d = start_down
				warmed_up = False
				
				req_d = urllib.request.Request("http://cachefly.cachefly.net/100mb.test", headers={'User-Agent': 'Mozilla/5.0'})
				res_d = urllib.request.urlopen(req_d, timeout=5)
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
				
				class UploadStream:
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
					urllib.request.urlopen(req_u, timeout=5)
				except Exception as up_err:
					log.debug(f"MonitorSistema: Cierre de stream de subida: {up_err}")
				
				if stream.measure_start is None: stream.measure_start = stream.start
				up_time = time.time() - stream.measure_start
				if up_time <= 0: up_time = 0.001
				up_speed = (stream.sent / up_time) / 1048576
				log.info(f"MonitorSistema: Subida finalizada: {round(up_speed, 2)} MB/s ({stream.sent} bytes en {round(up_time, 2)}s)")
				
				if ping_val:
					msg = _("Velocidad de Internet. Latencia: {} milisegundos. Descarga: {} Megabytes por segundo. Subida: {} Megabytes por segundo.").format(ping_val, round(dl_speed, 1), round(up_speed, 1))
				else:
					msg = _("Velocidad de Internet. Descarga: {} Megabytes por segundo. Subida: {} Megabytes por segundo.").format(round(dl_speed, 1), round(up_speed, 1))
				self._lastNetSpeedResult = msg
			except Exception as e: 
				err_str = str(e)
				log.error(f"MonitorSistema: Error en speedtest: {e}", exc_info=True)
				if "429" in err_str:
					msg = _("El servidor bloqueó la prueba por hacerla muchas veces seguidas. Espera unos minutos y vuelve a intentarlo.")
				else:
					msg = _("Error al medir la velocidad de Internet.")
			finally:
				self._netSpeedRunning = False
				stop_event.set()
			log.info(f"MonitorSistema: Anunciando velocidad de Internet: '{msg}'")
			wx.CallAfter(ui.message, msg)
			if getattr(self, "_copyNetSpeedOnFinish", False):
				self._copyNetSpeedOnFinish = False
				wx.CallAfter(api.copyToClip, msg, notify=True)
		ui.message(_("Realizando prueba de precisión (unos 12 segundos), por favor espera..."))
		threading.Thread(target=worker, daemon=True).start()

	@scriptHandler.script(
		description=_("Anuncia la velocidad de descarga y subida de Internet en tiempo real. Si se pulsa dos veces, copia la información al portapapeles."),
		gesture="kb:nvda+shift+control+3",
		speakOnDemand=True,
	)
	def script_announceNetSpeed(self, gesture: inputCore.InputGesture):
		if scriptHandler.getLastScriptRepeatCount() > 0:
			if self._netSpeedRunning:
				self._copyNetSpeedOnFinish = True
				ui.message(_("Se copiará el resultado al portapapeles."))
				return
			if self._lastNetSpeedResult:
				api.copyToClip(self._lastNetSpeedResult, notify=True)
				return
			self._copyNetSpeedOnFinish = True
			ui.message(_("Se copiará el resultado al portapapeles."))
			self._getNetworkSpeed()
			return
		if self._netSpeedRunning:
			ui.message(_("La prueba de velocidad de Internet ya está en curso, por favor espera..."))
			return
		self._copyNetSpeedOnFinish = False
		self._getNetworkSpeed()

	def _getAdvancedBattery(self):
		import psutil, threading, wx, subprocess, tones
		ui.message(_("Consultando estado de la batería, por favor espera..."))
		self._advBatteryRunning = True

		def worker():
			stop_event = threading.Event()
			def beeper():
				try: tones.beep(660, 40)
				except Exception: pass
				while not stop_event.wait(0.6):
					try: tones.beep(660, 40)
					except Exception: pass
			threading.Thread(target=beeper, daemon=True).start()

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
					pct = round(bat.percent)
					plugged = _("conectado") if bat.power_plugged else _("desconectado")
					msg = _("Batería al {} %. Estado: {}.").format(pct, plugged)
					if not bat.power_plugged and bat.secsleft != psutil.POWER_TIME_UNKNOWN:
						mins = bat.secsleft // 60
						msg += " " + _("Tiempo restante estimado: {} horas y {} minutos.").format(mins // 60, mins % 60)
					
					# Consulta WMI de salud real vs capacidad de diseño
					ps_script = "Try { $f = (Get-WmiObject BatteryFullChargedCapacity -Namespace root\\wmi -EA Stop | Select-Object -ExpandProperty FullChargedCapacity); $d = (Get-WmiObject BatteryStaticData -Namespace root\\wmi -EA Stop | Select-Object -ExpandProperty DesignedCapacity); if ($d -gt 0) { [math]::Round(($f / $d) * 100) } } Catch { }"
					
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
						if out and out.isdigit():
							msg += " " + _("Salud real de la batería: {} % de su capacidad original.").format(out)
					except Exception as e:
						log.error(f"MonitorSistema: Error en consulta WMI de salud de batería: {e}", exc_info=True)
				self._lastAdvBatteryResult = msg
			except Exception as e:
				log.error(f"MonitorSistema: Error general consultando batería: {e}", exc_info=True)
				msg = _("Error consultando la batería.")
			finally:
				self._advBatteryRunning = False
				stop_event.set()

			log.info(f"MonitorSistema: Anunciando estado de batería al usuario: '{msg}'")
			wx.CallAfter(ui.message, msg)
			if getattr(self, "_copyAdvBatteryOnFinish", False):
				self._copyAdvBatteryOnFinish = False
				wx.CallAfter(api.copyToClip, msg, notify=True)
		threading.Thread(target=worker, daemon=True).start()

	@scriptHandler.script(
		description=_("Anuncia el estado de la batería, tiempo restante y desgaste de salud. Si se pulsa dos veces, copia la información al portapapeles."),
		gesture="kb:nvda+shift+control+4",
		speakOnDemand=True,
	)
	def script_announceAdvBattery(self, gesture: inputCore.InputGesture):
		if scriptHandler.getLastScriptRepeatCount() > 0:
			if self._advBatteryRunning:
				self._copyAdvBatteryOnFinish = True
				ui.message(_("Se copiará el resultado al portapapeles."))
				return
			if self._lastAdvBatteryResult:
				api.copyToClip(self._lastAdvBatteryResult, notify=True)
				return
			self._copyAdvBatteryOnFinish = True
			ui.message(_("Se copiará el resultado al portapapeles."))
			self._getAdvancedBattery()
			return
		if self._advBatteryRunning:
			ui.message(_("La consulta de batería ya está en curso, por favor espera..."))
			return
		self._copyAdvBatteryOnFinish = False
		self._getAdvancedBattery()

	@staticmethod
	def _queryBluetoothBatteries():
		CR_SUCCESS = 0
		MAX_DEVICE_ID_LEN = 256
		_DIGCF_ALLCLASSES = 0x00000004
		DIGCF_PRESENT = 0x00000002
		_DN_DEVICE_DISCONNECTED = 0x02000000

		log.info("MonitorSistema: Iniciando enumeración profunda de dispositivos Bluetooth...")

		try:
			try:
				ctypes.windll.setupapi.SetupDiEnumDeviceInfo.argtypes = None
			except Exception:
				pass

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

			class GUID(Structure):
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
				_fields_ = [("fmtid", GUID), ("pid", wintypes.ULONG)]

			class SP_DEVINFO_DATA(Structure):
				_fields_ = [("cbSize", wintypes.DWORD), ("ClassGuid", GUID), ("DevInst", wintypes.DWORD), ("Reserved", POINTER(wintypes.ULONG))]

			# Estructuras para la API de Bluetooth Clásico (bthprops.cpl)
			class BLUETOOTH_ADDRESS(Structure):
				_fields_ = [("ullLong", ctypes.c_ulonglong)]

			class SYSTEMTIME(Structure):
				_fields_ = [
					("wYear", wintypes.WORD), ("wMonth", wintypes.WORD), ("wDayOfWeek", wintypes.WORD),
					("wDay", wintypes.WORD), ("wHour", wintypes.WORD), ("wMinute", wintypes.WORD),
					("wSecond", wintypes.WORD), ("wMilliseconds", wintypes.WORD)
				]

			class BLUETOOTH_DEVICE_INFO(Structure):
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
				_fields_ = [("dwSize", wintypes.DWORD)]
				def __init__(self):
					super().__init__()
					self.dwSize = ctypes.sizeof(self)

			class BLUETOOTH_DEVICE_SEARCH_PARAMS(Structure):
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

			# Consultar estados de conexión de Bluetooth clásico vía bthprops.cpl
			classic_connection_states = {}
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
										classic_connection_states[addr_hex] = bool(dev_info.fConnected)
										log.debug(f"MonitorSistema: Classic BT dev '{dev_info.szName}' ({addr_hex}) fConnected={bool(dev_info.fConnected)}")
										if not _BluetoothFindNextDevice(h_find_dev, ctypes.byref(dev_info)):
											break
								finally:
									_BluetoothFindDeviceClose(h_find_dev)
							ctypes.windll.kernel32.CloseHandle(h_radio)
							h_radio = wintypes.HANDLE()
							if not _BluetoothFindNextRadio(h_find_radio, ctypes.byref(h_radio)):
								break
					finally:
						if h_radio:
							ctypes.windll.kernel32.CloseHandle(h_radio)
						_BluetoothFindRadioClose(h_find_radio)
			except Exception as bth_err:
				log.debug(f"MonitorSistema: Error consultando bthprops.cpl: {bth_err}")

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

			def get_prop_str(hdev, dev_data, pkey):
				try:
					ptype = wintypes.ULONG()
					rsize = wintypes.DWORD()
					SetupDiGetDevicePropertyW(hdev, ctypes.byref(dev_data), ctypes.byref(pkey), ctypes.byref(ptype), None, 0, ctypes.byref(rsize), 0)
					if rsize.value == 0: return None
					buf = ctypes.create_unicode_buffer(rsize.value // 2 + 1)
					if SetupDiGetDevicePropertyW(hdev, ctypes.byref(dev_data), ctypes.byref(pkey), ctypes.byref(ptype), ctypes.byref(buf), rsize, ctypes.byref(rsize), 0):
						return buf.value
				except Exception as err:
					log.debug(f"MonitorSistema: Error en get_prop_str: {err}")
				return None

			def get_dev_name_by_inst(dev_inst):
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
						log.debug(f"MonitorSistema: Error en get_dev_name_by_inst({dev_inst}): {err}")
				return None

			def get_devnode_status(dev_inst):
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

			flags = DIGCF_PRESENT | _DIGCF_ALLCLASSES
			hdev = SetupDiGetClassDevs(None, None, None, flags)
			if not hdev or hdev == wintypes.HANDLE(-1).value:
				log.error("MonitorSistema: SetupDiGetClassDevs devolvió un manejador inválido.")
				return []

			import re
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

					name = (get_prop_str(hdev, dev_data, DEVPKEY_Device_FriendlyName)
							or get_prop_str(hdev, dev_data, DEVPKEY_NAME)
							or get_prop_str(hdev, dev_data, DEVPKEY_Device_DeviceDesc)
							or inst_id)

					m = (re.search(r"DEV_([0-9A-F]{12})", upper_id)
						 or re.search(r"&0&([0-9A-F]{12})_C", upper_id)
						 or re.search(r"&0&([0-9A-F]{12})", upper_id)
						 or re.search(r"_([0-9A-F]{12})\\[^\\]+$", upper_id)
						 or re.search(r"([0-9A-F]{12})", upper_id))
					addr = m.group(1) if m else None

					dev_inst = int(dev_data.DevInst)

					if (upper_id.startswith(("BTHENUM\\DEV_", "BTHLE\\DEV_")) or "DEV_" in upper_id) and addr:
						if name and not name.upper().startswith("BTH"):
							root_names[addr] = name
						root_dev_insts[addr] = dev_inst
					elif addr and addr not in root_names and name and not name.upper().startswith("BTH"):
						root_names[addr] = name

					# Comprobar si este nodo reporta nivel de batería
					for kname, pkey in BATTERY_KEYS:
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
										parent_name = get_dev_name_by_inst(parent_inst.value)
									candidates.append({
										"name": name,
										"parent_name": parent_name,
										"battery": val,
										"inst_id": inst_id,
										"dev_inst": dev_inst,
										"addr": addr
									})
									log.info(f"MonitorSistema: Nodo Bluetooth con batería detectado: '{name}' (batería={val}%, addr={addr}, id={inst_id})")
									break
						except Exception as prop_err:
							log.debug(f"MonitorSistema: Error consultando batería en {inst_id}: {prop_err}")
			finally:
				SetupDiDestroyDeviceInfoList(hdev)

			# Determinar estado de conexión preciso para cada candidato
			results = []
			seen = set()
			for cand in candidates:
				addr = cand["addr"]
				display_name = root_names.get(addr) or cand["parent_name"] or cand["name"]

				# 1. Chequeo primario para Bluetooth clásico: fConnected de bthprops.cpl
				is_connected = None
				if addr and addr in classic_connection_states:
					is_connected = classic_connection_states[addr]
					log.info(f"MonitorSistema: Dispositivo '{display_name}' ({addr}) estado vía bthprops: conectado={is_connected}")

				# 2. Chequeo secundario: estado de DevNode (DevNodeStatus)
				if is_connected is None:
					check_nodes = []
					if addr and addr in root_dev_insts:
						check_nodes.append(root_dev_insts[addr])
					if cand["dev_inst"] not in check_nodes:
						check_nodes.append(cand["dev_inst"])

					found_status = False
					for d_inst in check_nodes:
						st = get_devnode_status(d_inst)
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

					log.info(f"MonitorSistema: Dispositivo '{display_name}' ({addr}) estado vía DevNodeStatus/PnP: conectado={is_connected}")

				if is_connected:
					key = addr or cand["inst_id"]
					if key not in seen and display_name not in seen:
						seen.add(key)
						seen.add(display_name)
						results.append({"name": display_name, "battery": cand["battery"]})
						log.info(f"MonitorSistema: Dispositivo conectado confirmado con batería: '{display_name}' al {cand['battery']}%")
				else:
					log.info(f"MonitorSistema: Omitiendo '{display_name}' ({cand['inst_id']}): no conectado.")

			log.info(f"MonitorSistema: Fin de escaneo Bluetooth. Dispositivos conectados reportados ({len(results)}): {results}")
			return results
		except Exception as e:
			log.error(f"MonitorSistema: Error crítico en detección de batería Bluetooth: {e}", exc_info=True)
			return []

	def _getBluetoothBattery(self):
		import threading, wx, ui, tones
		ui.message(_("Buscando dispositivos Bluetooth, por favor espera..."))
		self._bluetoothRunning = True

		def worker():
			stop_event = threading.Event()
			def beeper():
				try: tones.beep(550, 40)
				except Exception: pass
				while not stop_event.wait(0.6):
					try: tones.beep(550, 40)
					except Exception: pass
			threading.Thread(target=beeper, daemon=True).start()

			log.info("MonitorSistema: Ejecutando comando de batería Bluetooth...")
			msg = _("Error consultando dispositivos Bluetooth.")
			try:
				data = self._queryBluetoothBatteries()
				if not data:
					msg = _("No se encontraron dispositivos Bluetooth informando su batería.")
					log.info("MonitorSistema: Anunciando al usuario: 'No se encontraron dispositivos Bluetooth informando su batería.'")
				else:
					parts = [_("{}: {} %").format(d.get('name', _('Dispositivo')), d.get('battery')) for d in data]
					msg = _("Batería Bluetooth: ") + ", ".join(parts)
					log.info(f"MonitorSistema: Anunciando al usuario: '{msg}'")
				self._lastBluetoothResult = msg
			except Exception as e:
				log.error(f"MonitorSistema: Error consultando dispositivos Bluetooth: {e}", exc_info=True)
				msg = _("Error consultando dispositivos Bluetooth.")
			finally:
				self._bluetoothRunning = False
				stop_event.set()

			wx.CallAfter(ui.message, msg)
			if getattr(self, "_copyBluetoothOnFinish", False):
				self._copyBluetoothOnFinish = False
				wx.CallAfter(api.copyToClip, msg, notify=True)
		threading.Thread(target=worker, daemon=True).start()

	@scriptHandler.script(
		description=_("Anuncia el nivel de batería de los dispositivos Bluetooth conectados. Si se pulsa dos veces, copia la información al portapapeles."),
		gesture="kb:nvda+shift+control+5",
		speakOnDemand=True,
	)
	def script_announceBluetooth(self, gesture: inputCore.InputGesture):
		if scriptHandler.getLastScriptRepeatCount() > 0:
			if self._bluetoothRunning:
				self._copyBluetoothOnFinish = True
				ui.message(_("Se copiará el resultado al portapapeles."))
				return
			if self._lastBluetoothResult:
				api.copyToClip(self._lastBluetoothResult, notify=True)
				return
			self._copyBluetoothOnFinish = True
			ui.message(_("Se copiará el resultado al portapapeles."))
			self._getBluetoothBattery()
			return
		if self._bluetoothRunning:
			ui.message(_("La búsqueda de dispositivos Bluetooth ya está en curso, por favor espera..."))
			return
		self._copyBluetoothOnFinish = False
		self._getBluetoothBattery()

	def auditConflicts(self):
		"""
		Audita y registra en el registro de NVDA posibles conflictos con otros complementos instalados o activos,
		incluyendo colisiones directas de atajos de teclado (gestos) y complementos duplicados o incompatibles.
		Devuelve una tupla (conflicts, warnings).
		"""
		conflicts = []
		warnings = []

		our_gestures_map = {
			"kb:nvda+shift+e": _("Resumen de recursos (RAM y CPU)"),
			"kb:nvda+shift+1": _("Carga y núcleos del procesador"),
			"kb:nvda+shift+2": _("Memoria RAM física y virtual"),
			"kb:nvda+shift+3": _("Espacio en unidades de disco"),
			"kb:nvda+shift+4": _("Estado e información de red Wi-Fi"),
			"kb:nvda+shift+5": _("Frecuencia y velocidad de CPU"),
			"kb:nvda+shift+6": _("Versión y arquitectura de Windows"),
			"kb:nvda+shift+7": _("Tiempo de actividad del sistema (uptime)"),
			"kb:nvda+shift+8": _("Rendimiento y memoria de GPU"),
			"kb:nvda+shift+control+1": _("Salud S.M.A.R.T. y temperatura de discos"),
			"kb:nvda+shift+control+2": _("Procesos con mayor consumo de recursos"),
			"kb:nvda+shift+control+3": _("Velocidad de red en tiempo real"),
			"kb:nvda+shift+control+4": _("Batería avanzada y salud"),
			"kb:nvda+shift+control+5": _("Nivel de batería de dispositivos Bluetooth"),
		}

		log.info("MonitorSistema: Iniciando auditoría de compatibilidad y detección de conflictos con otros complementos...")

		# 1. Comprobar complementos conocidos con superposición funcional o colisión de diseño
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
				if addon_name == "monitorsistema":
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

		# 2. Comprobar colisiones directas de atajos de teclado con otros plugins globales activos en NVDA
		try:
			running = getattr(globalPluginHandler, "runningPlugins", set())
			for plugin in running:
				if plugin is self:
					continue
				plugin_mod = getattr(plugin, "__module__", str(type(plugin)))
				if "monitorsistema" in plugin_mod.lower():
					continue

				# Obtener mapa de gestos del plugin
				g_map = getattr(plugin, "_gestureMap", {}) or {}
				if not g_map:
					g_map = getattr(plugin, "_ScriptableObject__gestures", {}) or {}

				for g_id, script_ref in g_map.items():
					norm_g = str(g_id).strip().lower().replace(" ", "")
					if norm_g in our_gestures_map:
						script_name = getattr(script_ref, "__name__", str(script_ref))
						our_feature = our_gestures_map[norm_g]
						collision_msg = (
							f"Colisión de atajo: '{norm_g}' está asignado simultáneamente a '{our_feature}' (Monitor del Sistema) "
							f"y a '{script_name}' en el plugin '{plugin_mod}'."
						)
						conflicts.append(collision_msg)
						log.warning(f"MonitorSistema CONFLICTO DE ATAJO: {collision_msg}")
		except Exception as e:
			log.debug(f"MonitorSistema: Error inspeccionando runningPlugins: {e}")

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

	def _checkAddonConflicts(self, interactive=False):
		conflicts, warnings = self.auditConflicts()
		if interactive:
			total = len(conflicts) + len(warnings)
			if total == 0:
				ui.message(_("Monitor del Sistema: No se detectaron conflictos con otros complementos."))
			else:
				ui.message(
					_("Monitor del Sistema: Se detectaron {count} posibles conflictos o advertencias. Revise el registro de NVDA para más detalles.").format(count=total)
				)

	@scriptHandler.script(
		description=_("Comprueba si existen conflictos de atajos de teclado o complementos incompatibles con Monitor del Sistema."),
		category=scriptCategory,
	)
	def script_checkConflicts(self, gesture: inputCore.InputGesture):
		self._checkAddonConflicts(interactive=True)

