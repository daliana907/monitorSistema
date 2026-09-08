# -*- coding: utf-8 -*-
"""Comprobaciones de los archivos de idiomas.

Existen porque en este proyecto aparecieron un archivo con la cabecera pegada a
la primera entrada, otro con un mensaje definido dos veces, y textos visibles
que nunca se habían marcado como traducibles.

Ejecutar con:   python -m unittest discover -s tests -v
"""
import ast
import os
import re
import struct
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDIOMAS = os.path.join(RAIZ, "locale")


def leer(ruta):
    with open(ruta, encoding="utf-8-sig") as archivo:
        return archivo.read()


def archivosPo():
    if not os.path.isdir(IDIOMAS):
        return
    for idioma in sorted(os.listdir(IDIOMAS)):
        ruta = os.path.join(IDIOMAS, idioma, "LC_MESSAGES", "nvda.po")
        if os.path.isfile(ruta):
            yield idioma, ruta


def entradasPo(ruta):
    """Devuelve {texto original: traducción} de un archivo .po."""
    entradas = {}
    for bloque in leer(ruta).split("\n\n"):
        if bloque.lstrip().startswith("#~"):
            continue
        original = re.search(r'^msgid ((?:"(?:[^"\\]|\\.)*"\s*)+)', bloque, re.M)
        traducido = re.search(r'^msgstr ((?:"(?:[^"\\]|\\.)*"\s*)+)', bloque, re.M)
        if not original:
            continue
        clave = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', original.group(1)))
        valor = ("".join(re.findall(r'"((?:[^"\\]|\\.)*)"', traducido.group(1)))
                 if traducido else "")
        if clave:
            entradas[clave] = valor
    return entradas


def mensajesMo(ruta):
    """Lee un archivo .mo compilado y devuelve cuántos mensajes contiene."""
    with open(ruta, "rb") as archivo:
        datos = archivo.read()
    magia, = struct.unpack("<I", datos[:4])
    orden = "<" if magia == 0x950412de else ">"
    _revision, cantidad, _o, _t, _h = struct.unpack(orden + "IIIII", datos[4:24])
    return cantidad


class ArchivosDeIdiomas(unittest.TestCase):
    def test_ninguna_cabecera_esta_pegada_a_la_primera_entrada(self):
        for idioma, ruta in archivosPo():
            with self.subTest(idioma=idioma):
                # Se comprueba línea a línea para poder señalar cuál, en vez de
                # volcar el archivo entero en el mensaje de error.
                for numero, linea in enumerate(leer(ruta).splitlines(), start=1):
                    self.assertNotIn(
                        r"\n\nmsgid ", linea,
                        f"{idioma}, línea {numero}: la cabecera y la primera entrada "
                        "quedaron pegadas; las herramientas de traducción rechazan "
                        "el archivo entero")

    def test_ningun_mensaje_esta_definido_dos_veces(self):
        for idioma, ruta in archivosPo():
            with self.subTest(idioma=idioma):
                vistos = set()
                for bloque in leer(ruta).split("\n\n"):
                    if bloque.lstrip().startswith("#~"):
                        continue
                    m = re.search(r'^msgid ((?:"(?:[^"\\]|\\.)*"\s*)+)', bloque, re.M)
                    if not m:
                        continue
                    clave = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)))
                    if not clave:
                        continue
                    self.assertNotIn(clave, vistos,
                                     f"{idioma}: '{clave[:50]}' está definido dos veces")
                    vistos.add(clave)

    def test_el_compilado_acompaña_al_archivo_de_texto(self):
        """El .mo es lo que NVDA lee de verdad; el .po solo es el archivo de trabajo."""
        for idioma, ruta in archivosPo():
            compilado = ruta[:-3] + ".mo"
            with self.subTest(idioma=idioma):
                self.assertTrue(os.path.isfile(compilado),
                                f"{idioma}: falta el archivo compilado nvda.mo")
                traducidos = sum(1 for v in entradasPo(ruta).values() if v)
                # El .mo incluye la cabecera como una entrada más.
                self.assertGreaterEqual(
                    mensajesMo(compilado) + 1, traducidos * 0.9,
                    f"{idioma}: el compilado tiene muchos menos mensajes que el archivo "
                    "de texto; probablemente quedó sin regenerar")


class TextosDelCodigo(unittest.TestCase):
    def test_no_se_marcan_como_traducibles_nombres_tecnicos(self):
        """Marcar 'sunrise' o 'uv_index_max' para traducir es un error de marcado."""
        sospechoso = re.compile(r"^[a-z][a-z0-9_]*$")
        for carpeta, _sub, archivos in os.walk(RAIZ):
            if "__pycache__" in carpeta or os.sep + "tests" in carpeta:
                continue
            for nombre in archivos:
                if not nombre.endswith(".py"):
                    continue
                ruta = os.path.join(carpeta, nombre)
                for nodo in ast.walk(ast.parse(leer(ruta))):
                    if not (isinstance(nodo, ast.Call)
                            and isinstance(nodo.func, ast.Name)
                            and nodo.func.id in ("_", "N_")
                            and nodo.args
                            and isinstance(nodo.args[0], ast.Constant)
                            and isinstance(nodo.args[0].value, str)):
                        continue
                    texto = nodo.args[0].value
                    if "_" in texto and sospechoso.match(texto):
                        self.fail(f"{nombre}:{nodo.lineno} se marcó como traducible "
                                  f"'{texto}', que parece un nombre técnico")


if __name__ == "__main__":
    unittest.main(verbosity=2)
