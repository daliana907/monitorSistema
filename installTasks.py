# -*- coding: utf-8 -*-
# System Monitor (Monitoreo del Sistema) for NVDA - Install Tasks
# Copyright 2026 Daliana, released under the GNU General Public License version 2 (GPLv2).


import config
from logHandler import log


def onInstall():
	"""Se ejecuta al instalar el complemento."""
	log.info("Monitoreo del Sistema: instalacion completada.")
	try:
		conf_obj = getattr(config, "conf", None)
		if conf_obj is not None and "monitorSistema" in conf_obj:
			try:
				old = dict(conf_obj["monitorSistema"])
			except Exception:
				old = {}
			try:
				if "monitoreoSistema" not in conf_obj:
					conf_obj["monitoreoSistema"] = {}
				for _k, _v in old.items():
					try:
						if _k not in conf_obj["monitoreoSistema"]:
							conf_obj["monitoreoSistema"][_k] = _v
					except Exception:
						continue
				del conf_obj["monitorSistema"]
				try:
					if "monitorSistema" in getattr(conf_obj, "spec", {}):
						del conf_obj.spec["monitorSistema"]
				except Exception:
					pass
				if hasattr(conf_obj, "save"):
					conf_obj.save()
				log.info("Monitoreo del Sistema: seccion huerfana [monitorSistema] migrada a [monitoreoSistema].")
			except Exception as _e:
				log.warning("Monitoreo del Sistema: no se pudo migrar [monitorSistema]: {}".format(_e))
	except Exception:
		pass


def onUninstall():
	"""
	Se ejecuta al desinstalar el complemento desde el administrador de complementos de NVDA.
	Migra/borra la seccion vieja [monitorSistema] y elimina [monitoreoSistema].
	"""
	try:
		conf_obj = getattr(config, "conf", None)
		if conf_obj is None:
			return
		modified = False
		# Migrar huérfana vieja a nueva antes de borrar, para no perder umbrales.
		try:
			if "monitorSistema" in conf_obj:
				try:
					_old = dict(conf_obj["monitorSistema"])
				except Exception:
					_old = {}
				if "monitoreoSistema" not in conf_obj:
					try:
						conf_obj["monitoreoSistema"] = {}
					except Exception:
						pass
				for _kk, _vv in _old.items():
					try:
						if "monitoreoSistema" in conf_obj and _kk not in conf_obj["monitoreoSistema"]:
							conf_obj["monitoreoSistema"][_kk] = _vv
					except Exception:
						continue
		except Exception:
			pass
		for sec in ("monitoreoSistema", "monitorSistema"):
			if sec in conf_obj:
				del conf_obj[sec]
				modified = True
			if sec in getattr(conf_obj, "spec", {}):
				del conf_obj.spec[sec]
				modified = True
		if modified and hasattr(conf_obj, "save"):
			conf_obj.save()
		log.info("Monitoreo del Sistema: configuracion y rastros eliminados correctamente de NVDA.")
	except Exception as e:
		log.warning("Monitoreo del Sistema: error al limpiar la configuracion: {}".format(e))
