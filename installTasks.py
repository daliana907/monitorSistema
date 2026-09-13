# -*- coding: utf-8 -*-
# System Monitor (Monitoreo del Sistema) for NVDA - Install Tasks
# Copyright 2026 Daliana, released under the GNU General Public License version 2 (GPLv2).


import config
from logHandler import log


def onInstall():
	"""Se ejecuta al instalar el complemento."""
	log.info("Monitoreo del Sistema: instalación completada.")


def onUninstall():
	"""
	Se ejecuta al desinstalar el complemento desde el administrador de complementos de NVDA.
	Elimina completamente la sección [monitoreoSistema] de nvda.ini y limpia cualquier rastro.
	"""
	try:
		modified = False
		for sec in ("monitoreoSistema", "monitorSistema"):
			if sec in config.conf:
				del config.conf[sec]
				modified = True
			if sec in getattr(config.conf, "spec", {}):
				del config.conf.spec[sec]
				modified = True
		if modified:
			config.conf.save()
		log.info("Monitoreo del Sistema: configuración y rastros eliminados correctamente de NVDA.")
	except Exception as e:
		log.warning("Monitoreo del Sistema: error al limpiar la configuración: {}".format(e))
