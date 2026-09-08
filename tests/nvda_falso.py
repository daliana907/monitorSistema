# -*- coding: utf-8 -*-
"""Sustitutos de los módulos de NVDA, para poder probar sin abrir NVDA.

Los complementos importan módulos que solo existen dentro de NVDA (ui, wx,
addonHandler...). Aquí se registran versiones falsas antes de importar el
código a probar, de modo que las pruebas corren en cualquier Python.

No pretende imitar a NVDA: solo permite que el archivo se importe y anota lo
que el complemento intentó decir o hacer, para poder comprobarlo.
"""
import os
import sys
import types

dichos = []          # todo lo que el complemento intentó que NVDA dijera
portapapeles = []    # todo lo que intentó copiar


def _modulo(nombre, **atributos):
    m = types.ModuleType(nombre)
    for k, v in atributos.items():
        setattr(m, k, v)
    sys.modules[nombre] = m
    return m


class _Cualquiera:
    """Objeto que acepta cualquier atributo y cualquier llamada sin protestar."""

    def __init__(self, *a, **k):
        pass

    def __getattr__(self, nombre):
        return _Cualquiera()

    def __call__(self, *a, **k):
        return _Cualquiera()

    def __or__(self, otro):
        return self

    def __ror__(self, otro):
        return self


def instalar():
    """Registra los módulos falsos. Llamar antes de importar el complemento."""
    dichos.clear()
    portapapeles.clear()

    _modulo("ui", message=lambda texto, *a, **k: dichos.append(texto))
    _modulo("api", copyToClip=lambda texto, **k: portapapeles.append(texto))
    _modulo("addonHandler",
            initTranslation=lambda: None,
            getCodeAddon=lambda: _Cualquiera(),
            getLanguage=lambda: "es")
    _modulo("logHandler", log=_Cualquiera())
    _modulo("globalPluginHandler", GlobalPlugin=type("GlobalPlugin", (), {}))
    _modulo("scriptHandler",
            script=lambda **k: (lambda f: f),
            getLastScriptRepeatCount=lambda: 0)
    _modulo("inputCore", InputGesture=type("InputGesture", (), {}))
    _modulo("gui", mainFrame=_Cualquiera(), messageBox=lambda *a, **k: None,
            settingsDialogs=_Cualquiera(), guiHelper=_Cualquiera(),
            blockAction=_Cualquiera(), nvdaControls=_Cualquiera(),
            NVDASettingsDialog=_Cualquiera)
    _modulo("gui.settingsDialogs", NVDASettingsDialog=_Cualquiera,
            SettingsPanel=type("SettingsPanel", (), {}))
    _modulo("config", conf={})
    _modulo("queueHandler", queueFunction=lambda *a, **k: None, eventQueue=None)
    _modulo("tones", beep=lambda *a, **k: None)
    _modulo("versionInfo", version_year=2026, version_major=2026, version_minor=3)

    wx = _modulo("wx", NOT_FOUND=-1, OK=1, CANCEL=2, ICON_INFORMATION=4,
                 ICON_WARNING=8, ICON_ERROR=16)
    for nombre in ("Dialog", "Panel", "Button", "CheckBox", "StaticText", "TextCtrl",
                   "ListCtrl", "ListBox", "Choice", "SpinCtrl", "BoxSizer", "Colour",
                   "StaticBox", "StaticBoxSizer", "ScrolledWindow", "StdDialogButtonSizer",
                   "CommandEvent", "MessageBox", "CallAfter"):
        setattr(wx, nombre, _Cualquiera)
    for constante in ("VERTICAL", "HORIZONTAL", "EXPAND", "ALL", "LEFT", "RIGHT", "TOP",
                      "BOTTOM", "LB_SINGLE", "LC_REPORT", "LC_SINGLE_SEL", "BORDER_SUNKEN",
                      "TE_PROCESS_ENTER", "VSCROLL", "ALIGN_RIGHT", "ID_OK", "ID_CANCEL",
                      "WXK_UP", "WXK_DOWN", "EVT_BUTTON", "EVT_TEXT", "EVT_KEY_DOWN",
                      "EVT_LIST_ITEM_SELECTED", "DEFAULT_DIALOG_STYLE", "RESIZE_BORDER"):
        setattr(wx, constante, _Cualquiera())


    # Módulos que solo existen en Windows. Ojo: NO se falsea msvcrt, porque
    # subprocess lo usa para saber si está en Windows y luego busca _winapi.
    if os.name != "nt":
        _modulo("winreg", OpenKey=lambda *a, **k: _Cualquiera(),
                QueryValueEx=lambda *a, **k: ("", 0), CloseKey=lambda *a: None,
                HKEY_LOCAL_MACHINE=0, KEY_READ=0)

    _modulo("globalVars", appArgs=_Cualquiera(), appDir="", startTime=0)
    _modulo("core", callLater=lambda ms, f, *a, **k: None,
            triggerAsleep=lambda: None, isMainThread=lambda: True)
    _modulo("winVersion", getWinVer=lambda: _Cualquiera())
    _modulo("winsound", Beep=lambda *a, **k: None, PlaySound=lambda *a, **k: None,
            SND_FILENAME=1, SND_ASYNC=2)
    _modulo("comtypes", client=_Cualquiera(), CoInitialize=lambda: None,
            CoUninitialize=lambda: None, GUID=_Cualquiera, HRESULT=int,
            COMError=Exception)
    _modulo("comtypes.client", CreateObject=lambda *a, **k: _Cualquiera())
    if "psutil" not in sys.modules:
        _modulo("psutil",
                virtual_memory=lambda: _Cualquiera(),
                swap_memory=lambda: _Cualquiera(),
                cpu_percent=lambda **k: 0.0,
                cpu_count=lambda **k: 4,
                sensors_battery=lambda: None,
                boot_time=lambda: 0,
                disk_usage=lambda p: _Cualquiera(),
                disk_partitions=lambda **k: [],
                process_iter=lambda *a, **k: [],
                net_io_counters=lambda **k: _Cualquiera())

    # ctypes en Linux no tiene windll ni las funciones de Windows.
    import ctypes
    if not hasattr(ctypes, "windll"):
        ctypes.windll = _Cualquiera()
        ctypes.WinDLL = _Cualquiera
        ctypes.WINFUNCTYPE = lambda *a, **k: _Cualquiera
        ctypes.GetLastError = lambda: 0
        ctypes.FormatError = lambda *a: ""
        ctypes.WinError = lambda *a, **k: OSError("windows")

    # NVDA instala _() como función global de traducción.
    import builtins
    builtins._ = lambda texto: texto
    builtins.N_ = lambda texto: texto
