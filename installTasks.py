# -*- coding: utf-8 -*-
# System Monitor (Monitor del Sistema) for NVDA - Install Tasks
# Copyright 2026 Daliana, released under the GNU General Public License version 2 (GPLv2).


import config
from logHandler import log


def onInstall():
	"""Se ejecuta al instalar el complemento."""
	log.info("Monitor del Sistema: instalación completada.")


def onUninstall():
	"""
	Se ejecuta al desinstalar el complemento desde el administrador de complementos de NVDA.
	Elimina completamente la sección [monitorSistema] de nvda.ini y limpia cualquier rastro.
	"""
	try:
		modified = False
		if "monitorSistema" in config.conf:
			del config.conf["monitorSistema"]
			modified = True
		if "monitorSistema" in config.conf.spec:
			del config.conf.spec["monitorSistema"]
			modified = True
		if modified:
			config.conf.save()
		log.info("Monitor del Sistema: configuración y rastros eliminados correctamente de NVDA.")
	except Exception as e:
		log.warning("Monitor del Sistema: error al limpiar la configuración: {}".format(e))
