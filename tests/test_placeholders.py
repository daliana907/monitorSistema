# -*- coding: utf-8 -*-
"""Los marcadores {…} no se traducen: deben ser identicos en original y traduccion.

Existe porque aparecieron traducciones con {prefix} convertido en {prefixo},
{name} en {navn}, {util} en {bikarhener}, etc. El codigo hace
_("... {name} ...").format(name=...): un marcador renombrado provoca
KeyError y rompe el anuncio en ese idioma.

Solo se revisan las entradas activas (las marcadas como fuzzy no llegan al
.mo compilado, igual que hace msgfmt). Se comparan multiconjuntos: tanto los
nombres ({name}) como la cantidad de posicionales ({}) deben coincidir.

Ejecutar con:   python -m unittest discover -s tests -v
"""
import os
import re
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDIOMAS = os.path.join(RAIZ, "locale")

MARCADOR = re.compile(r"\{[^{}]*\}")


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


def entradasActivas(ruta):
    """Devuelve [(original, traduccion)] de entradas no fuzzy con traduccion."""
    pares = []
    for bloque in leer(ruta).split("\n\n"):
        if bloque.lstrip().startswith("#~"):
            continue
        lineas = bloque.splitlines()
        if any(l.strip() == "#, fuzzy" or l.strip().startswith("#, fuzzy")
               for l in lineas):
            continue
        original = re.search(r'^msgid ((?:"(?:[^"\\]|\\.)*"\s*)+)', bloque, re.M)
        traducido = re.search(r'^msgstr ((?:"(?:[^"\\]|\\.)*"\s*)+)', bloque, re.M)
        if not original:
            continue
        clave = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', original.group(1)))
        valor = ("".join(re.findall(r'"((?:[^"\\]|\\.)*)"', traducido.group(1)))
                 if traducido else "")
        if clave and valor:
            pares.append((clave, valor))
    return pares


class MarcadoresDeFormato(unittest.TestCase):
    def test_los_marcadores_son_identicos_en_original_y_traduccion(self):
        for idioma, ruta in archivosPo():
            with self.subTest(idioma=idioma):
                for original, traduccion in entradasActivas(ruta):
                    self.assertEqual(
                        sorted(MARCADOR.findall(original)),
                        sorted(MARCADOR.findall(traduccion),
                               ),
                        f"{idioma}: {original[:80]!r} -> {traduccion[:80]!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
