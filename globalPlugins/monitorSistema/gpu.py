# -*- coding: utf-8 -*-
# Resource Monitor for NVDA
# Presents GPU information
# Copyright 2026 Kevin Derome, Joseph Lee, released under GPL

import os
import os.path
import shutil
import subprocess
import time
import ctypes
from ctypes import (
	wintypes,
	byref,
	sizeof,
	Structure,
	Union,
	c_long,
	c_double,
	c_longlong,
	c_char_p,
	c_wchar_p,
	c_byte,
	c_ubyte,
	c_size_t,
	POINTER,
	cast,
	WINFUNCTYPE,
)
from dataclasses import dataclass
try:
	from logHandler import log
except ImportError:
	import logging
	log = logging.getLogger("gpu")


@dataclass
class GpuTelemetry:
	utilization: str
	temperature: str
	memoryUsed: str
	memoryTotal: str


# Prevents a conhost.exe console window from flashing on screen when running
# nvidia-smi/where.exe, and avoids NVDA's UIAHandler logging errors while it
# tries (and fails) to probe a console window that closes almost immediately.
_CREATE_NO_WINDOW = 0x08000000


class BaseGpuProvider:
	def collect(self) -> list[GpuTelemetry] | None:
		raise NotImplementedError


class NvidiaGpuProvider(BaseGpuProvider):
	def __init__(self):
		super().__init__()
		self._nvidiaSmiPath = None
		self._nvidiaSmiPathResolved = False

	def _findNvidiaSmiPath(self) -> str | None:
		for commandName in ("nvidia-smi", "nvidia-smi.exe"):
			found = shutil.which(commandName)
			if found:
				return found
		windowsDir = os.environ.get("WINDIR", r"C:\Windows")
		candidates = [
			os.path.join(windowsDir, "System32", "nvidia-smi.exe"),
			os.path.join(windowsDir, "Sysnative", "nvidia-smi.exe"),
		]
		for envVar in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
			basePath = os.environ.get(envVar)
			if basePath:
				candidates.append(
					os.path.join(basePath, "NVIDIA Corporation", "NVSMI", "nvidia-smi.exe")
				)
		for path in candidates:
			if os.path.isfile(path):
				return path
		return None

	def collect(self) -> list[GpuTelemetry] | None:
		if not self._nvidiaSmiPathResolved:
			self._nvidiaSmiPath = self._findNvidiaSmiPath()
			self._nvidiaSmiPathResolved = True
		if not self._nvidiaSmiPath:
			return None
		try:
			result = subprocess.run(
				[
					self._nvidiaSmiPath,
					"--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total",
					"--format=csv,noheader,nounits",
				],
				capture_output=True,
				text=True,
				timeout=5,
				check=True,
				creationflags=_CREATE_NO_WINDOW,
			)
		except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired) as e:
			log.debug(f"MonitorSistema GPU: nvidia-smi falló o no está disponible: {e}")
			return []
		lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
		if not lines:
			return []
		items: list[GpuTelemetry] = []
		for line in lines:
			gpuData = [part.strip() for part in line.split(",")]
			if len(gpuData) < 4:
				continue
			items.append(
				GpuTelemetry(
					utilization=gpuData[0],
					temperature=gpuData[1],
					# nvidia-smi reports memory.used/memory.total in MiB when "nounits" is requested.
					memoryUsed=gpuData[2],
					memoryTotal=gpuData[3],
				)
			)
		return items


# ── Windows PDH (Performance Data Helper) & DXGI Provider ─────────────────────

HQUERY = wintypes.HANDLE
HCOUNTER = wintypes.HANDLE
PDH_FMT_DOUBLE = 0x00000200
ERROR_SUCCESS = 0


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


class PDH_FMT_COUNTERVALUE_ITEM_W(Structure):
	_fields_ = [
		("szName", wintypes.LPWSTR),
		("FmtValue", PDH_FMT_COUNTERVALUE),
	]


def _getDxgiAdapters() -> dict[str, dict]:
	"""Enumerates DirectX (DXGI) display adapters and returns their LUID, name and memory."""
	adapters = {}
	try:
		dxgi = ctypes.windll.dxgi

		class LUID(Structure):
			_fields_ = [
				("LowPart", wintypes.DWORD),
				("HighPart", wintypes.LONG),
			]

		class DXGI_ADAPTER_DESC(Structure):
			_fields_ = [
				("Description", wintypes.WCHAR * 128),
				("VendorId", wintypes.UINT),
				("DeviceId", wintypes.UINT),
				("SubSysId", wintypes.UINT),
				("Revision", wintypes.UINT),
				("DedicatedVideoMemory", c_size_t),
				("DedicatedSystemMemory", c_size_t),
				("SharedSystemMemory", c_size_t),
				("AdapterLuid", LUID),
			]

		class IDXGIAdapterVtbl(Structure):
			pass
		class IDXGIAdapter(Structure):
			pass
		IDXGIAdapter._fields_ = [("lpVtbl", POINTER(IDXGIAdapterVtbl))]

		GETDESC_PROTO = WINFUNCTYPE(wintypes.LONG, POINTER(IDXGIAdapter), POINTER(DXGI_ADAPTER_DESC))
		RELEASE_ADAPTER_PROTO = WINFUNCTYPE(wintypes.ULONG, POINTER(IDXGIAdapter))

		IDXGIAdapterVtbl._fields_ = [
			("QueryInterface", ctypes.c_void_p),
			("AddRef", ctypes.c_void_p),
			("Release", RELEASE_ADAPTER_PROTO),
			("SetPrivateData", ctypes.c_void_p),
			("SetPrivateDataInterface", ctypes.c_void_p),
			("GetPrivateData", ctypes.c_void_p),
			("GetParent", ctypes.c_void_p),
			("EnumOutputs", ctypes.c_void_p),
			("GetDesc", GETDESC_PROTO),
		]

		class IDXGIFactoryVtbl(Structure):
			pass
		class IDXGIFactory(Structure):
			pass
		IDXGIFactory._fields_ = [("lpVtbl", POINTER(IDXGIFactoryVtbl))]

		ENUMADAPTERS_PROTO = WINFUNCTYPE(
			wintypes.LONG,
			POINTER(IDXGIFactory),
			wintypes.UINT,
			POINTER(POINTER(IDXGIAdapter))
		)
		RELEASE_FACTORY_PROTO = WINFUNCTYPE(wintypes.ULONG, POINTER(IDXGIFactory))

		IDXGIFactoryVtbl._fields_ = [
			("QueryInterface", ctypes.c_void_p),
			("AddRef", ctypes.c_void_p),
			("Release", RELEASE_FACTORY_PROTO),
			("SetPrivateData", ctypes.c_void_p),
			("SetPrivateDataInterface", ctypes.c_void_p),
			("GetPrivateData", ctypes.c_void_p),
			("GetParent", ctypes.c_void_p),
			("EnumAdapters", ENUMADAPTERS_PROTO),
		]

		class GUID(Structure):
			_fields_ = [
				("Data1", wintypes.DWORD),
				("Data2", wintypes.WORD),
				("Data3", wintypes.WORD),
				("Data4", c_ubyte * 8),
			]

		IID_IDXGIFactory = GUID(
			0x7B7166EC,
			0x21C7,
			0x44AE,
			(c_ubyte * 8)(0xB2, 0x1A, 0xC9, 0xAE, 0x32, 0x1A, 0xE3, 0x69),
		)

		pFactory = POINTER(IDXGIFactory)()
		hr = dxgi.CreateDXGIFactory(byref(IID_IDXGIFactory), byref(pFactory))
		if hr == 0 and pFactory:
			i = 0
			pAdapter = POINTER(IDXGIAdapter)()
			while pFactory.contents.lpVtbl.contents.EnumAdapters(pFactory, i, byref(pAdapter)) == 0:
				desc = DXGI_ADAPTER_DESC()
				if pAdapter.contents.lpVtbl.contents.GetDesc(pAdapter, byref(desc)) == 0:
					low = desc.AdapterLuid.LowPart
					high = desc.AdapterLuid.HighPart
					luid_str = "luid_0x{:08x}_0x{:08x}".format(high, low).lower()
					vram_mb = desc.DedicatedVideoMemory / (1024.0 * 1024.0)
					shared_mb = desc.SharedSystemMemory / (1024.0 * 1024.0)
					total_mb = vram_mb if vram_mb > 0 else (shared_mb if shared_mb > 0 else 512.0)
					adapters[luid_str] = {
						"name": desc.Description,
						"dedicated_mb": vram_mb,
						"shared_mb": shared_mb,
						"total_mb": total_mb,
					}
				pAdapter.contents.lpVtbl.contents.Release(pAdapter)
				i += 1
			pFactory.contents.lpVtbl.contents.Release(pFactory)
	except Exception as e:
		log.error(f"MonitorSistema GPU: Error obteniendo adaptadores DXGI: {e}", exc_info=True)
	return adapters


def _extractLuid(name: str) -> str:
	if not name:
		return "default"
	name = name.lower()
	idx = name.find("luid_")
	if idx >= 0:
		parts = name[idx:].split("_")
		if len(parts) >= 3:
			return f"{parts[0]}_{parts[1]}_{parts[2]}"
	return "default"


def _getAmdGpuTemperature() -> str:
	for dll_name in ("atiadlxx.dll", "atiadlxy.dll"):
		try:
			adl = ctypes.WinDLL(dll_name)
			ALLOC_FUNC = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_size_t)
			def adl_alloc(size):
				return ctypes.windll.kernel32.LocalAlloc(0x0040, size)
			adl_alloc_cb = ALLOC_FUNC(adl_alloc)
			if adl.ADL_Main_Control_Create(adl_alloc_cb, 1) == 0:
				temp_str = ""
				if hasattr(adl, "ADL2_OverdriveN_Temperature_Get"):
					func = adl.ADL2_OverdriveN_Temperature_Get
					func.argtypes = [ctypes.c_void_p, c_long, c_long, POINTER(c_long)]
					func.restype = c_long
					t = c_long(0)
					if func(None, 0, 0, byref(t)) == 0 and t.value > 0:
						c = t.value / 1000.0
						if 0 < c < 125:
							temp_str = str(round(c))
				adl.ADL_Main_Control_Destroy()
				if temp_str:
					return temp_str
		except Exception:
			pass
	return ""


class WindowsGpuProvider(BaseGpuProvider):
	"""Universal Windows GPU telemetry provider using Performance Data Helper (PDH) and DXGI."""

	def __init__(self):
		super().__init__()
		self._pdh = None
		self._query = None
		self._counterUtil = None
		self._counterDedicated = None
		self._counterShared = None
		self._adapters = {}
		self._lastCollectTime = 0

	def _initPdh(self):
		try:
			self._pdh = ctypes.windll.pdh
			hQuery = HQUERY()
			status = self._pdh.PdhOpenQueryW(None, 0, byref(hQuery))
			if status != ERROR_SUCCESS:
				self._pdh = None
				return
			self._query = hQuery

			hCounterUtil = HCOUNTER()
			self._pdh.PdhAddEnglishCounterW(
				self._query,
				r"\GPU Engine(*)\Utilization Percentage",
				0,
				byref(hCounterUtil),
			)
			self._counterUtil = hCounterUtil

			hCounterDedicated = HCOUNTER()
			self._pdh.PdhAddEnglishCounterW(
				self._query,
				r"\GPU Adapter Memory(*)\Dedicated Usage",
				0,
				byref(hCounterDedicated),
			)
			self._counterDedicated = hCounterDedicated

			hCounterShared = HCOUNTER()
			self._pdh.PdhAddEnglishCounterW(
				self._query,
				r"\GPU Adapter Memory(*)\Shared Usage",
				0,
				byref(hCounterShared),
			)
			self._counterShared = hCounterShared

			self._adapters = _getDxgiAdapters()
			self._pdh.PdhCollectQueryData(self._query)
			self._lastCollectTime = time.time()
		except Exception as e:
			log.error(f"MonitorSistema GPU: Error inicializando PDH en WindowsGpuProvider: {e}", exc_info=True)
			self._pdh = None

	def collect(self) -> list[GpuTelemetry] | None:
		if not self._pdh or not self._query:
			self._initPdh()
		if not self._pdh or not self._query:
			return None
		try:
			now = time.time()
			# Rate counters require at least ~100ms between data collections
			if now - self._lastCollectTime < 0.1:
				time.sleep(0.1)

			status = self._pdh.PdhCollectQueryData(self._query)
			self._lastCollectTime = time.time()
			if status != ERROR_SUCCESS:
				return []

			luidUtilization: dict[str, float] = {}
			if self._counterUtil:
				bufSize = wintypes.DWORD(0)
				itemCount = wintypes.DWORD(0)
				self._pdh.PdhGetFormattedCounterArrayW(
					self._counterUtil,
					PDH_FMT_DOUBLE,
					byref(bufSize),
					byref(itemCount),
					None,
				)
				if bufSize.value > 0:
					buf = (c_byte * bufSize.value)()
					res = self._pdh.PdhGetFormattedCounterArrayW(
						self._counterUtil,
						PDH_FMT_DOUBLE,
						byref(bufSize),
						byref(itemCount),
						byref(buf),
					)
					if res == ERROR_SUCCESS:
						items = cast(buf, POINTER(PDH_FMT_COUNTERVALUE_ITEM_W))
						for i in range(itemCount.value):
							item = items[i]
							val = item.FmtValue.doubleValue
							if item.szName:
								luid = _extractLuid(item.szName)
								if val > 0.0001:
									luidUtilization[luid] = luidUtilization.get(luid, 0.0) + val
								elif luid not in luidUtilization:
									luidUtilization[luid] = 0.0

			luidMemUsed: dict[str, float] = {}
			for counter in (self._counterDedicated, self._counterShared):
				if not counter:
					continue
				bufSize = wintypes.DWORD(0)
				itemCount = wintypes.DWORD(0)
				self._pdh.PdhGetFormattedCounterArrayW(
					counter,
					PDH_FMT_DOUBLE,
					byref(bufSize),
					byref(itemCount),
					None,
				)
				if bufSize.value > 0:
					buf = (c_byte * bufSize.value)()
					res = self._pdh.PdhGetFormattedCounterArrayW(
						counter,
						PDH_FMT_DOUBLE,
						byref(bufSize),
						byref(itemCount),
						byref(buf),
					)
					if res == ERROR_SUCCESS:
						items = cast(buf, POINTER(PDH_FMT_COUNTERVALUE_ITEM_W))
						for i in range(itemCount.value):
							item = items[i]
							val = item.FmtValue.doubleValue
							if item.szName:
								luid = _extractLuid(item.szName)
								if val > 0:
									luidMemUsed[luid] = luidMemUsed.get(luid, 0.0) + (val / (1024.0 * 1024.0))

			if not self._adapters:
				self._adapters = _getDxgiAdapters()

			amdTemp = _getAmdGpuTemperature()
			telemetryList: list[GpuTelemetry] = []
			if self._adapters:
				has_hardware_gpu = any(
					"basic render" not in a.get("name", "").lower()
					and "software" not in a.get("name", "").lower()
					for a in self._adapters.values()
				)
				for luid, info in self._adapters.items():
					adapter_name = info.get("name", "").lower()
					if has_hardware_gpu and ("basic render" in adapter_name or "software" in adapter_name):
						continue
					util = min(100.0, luidUtilization.get(luid, 0.0))
					if util == 0.0 and "default" in luidUtilization:
						util = min(100.0, luidUtilization["default"])
					memUsed = luidMemUsed.get(luid, 0.0)
					if memUsed == 0.0 and "default" in luidMemUsed:
						memUsed = luidMemUsed["default"]
					memTotal = info.get("total_mb", 512.0)
					is_amd = "amd" in info.get("name", "").lower() or "radeon" in info.get("name", "").lower()
					t_val = amdTemp if is_amd else ""
					telemetryList.append(
						GpuTelemetry(
							utilization=str(round(util, 1) if util != int(util) else int(util)),
							temperature=t_val,
							memoryUsed=str(round(memUsed, 1)),
							memoryTotal=str(round(memTotal, 1)),
						)
					)

			if not telemetryList:
				totalUtil = sum(luidUtilization.values())
				totalMem = sum(luidMemUsed.values())
				telemetryList.append(
					GpuTelemetry(
						utilization=str(round(min(100.0, totalUtil), 1) if totalUtil != int(totalUtil) else int(totalUtil)),
						temperature=amdTemp,
						memoryUsed=str(round(totalMem, 1)),
						memoryTotal=str(round(max(512.0, totalMem), 1)),
					)
				)

			return telemetryList
		except Exception as e:
			log.error(f"MonitorSistema GPU: Error en WindowsGpuProvider.collect: {e}", exc_info=True)
			return []

	def __del__(self):
		if self._pdh and self._query:
			try:
				self._pdh.PdhCloseQuery(self._query)
			except Exception:
				pass


def getGpuProviders() -> list[BaseGpuProvider]:
	return [NvidiaGpuProvider(), WindowsGpuProvider()]
