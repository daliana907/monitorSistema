# -*- coding: utf-8 -*-
"""Pruebas de la lógica pura de Monitor del Sistema.

Este complemento no se puede importar fuera de Windows: su módulo de Wi-Fi
define estructuras de C que dependen de bibliotecas del sistema. En vez de
imitarlas, se extrae del archivo únicamente la función a probar y se ejecuta
aislada. Sirve para funciones puras: las que solo transforman sus argumentos.
"""
import ast
import os
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRINCIPAL = os.path.join(RAIZ, "globalPlugins", "monitorSistema", "__init__.py")


def extraer(nombreFuncion, ruta=PRINCIPAL):
    """Devuelve la función indicada, sacada del archivo y ejecutada aislada.

    Solo vale para funciones que no dependen del estado del complemento. Se
    les facilitan los módulos corrientes de Python (re, math, time, os). Si la
    función necesita algo del propio complemento, esta técnica no sirve y hay
    que probarla dentro de NVDA.
    """
    with open(ruta, encoding="utf-8-sig") as archivo:
        codigo = archivo.read()
    arbol = ast.parse(codigo)
    objetivo = None
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.FunctionDef) and nodo.name == nombreFuncion:
            objetivo = nodo
            break
    if objetivo is None:
        raise AssertionError(f"No se encontró la función {nombreFuncion} en {ruta}")
    objetivo.decorator_list = []
    # Algunas funciones consultan tablas de datos declaradas fuera de ellas
    # (por ejemplo VELOCIDAD_MAXIMA_CONOCIDA). Se llevan también, o la función
    # extraída fallaría al no encontrarlas.
    nombresUsados = {n.id for n in ast.walk(objetivo) if isinstance(n, ast.Name)}
    tablas = [sentencia for sentencia in arbol.body
              if isinstance(sentencia, ast.Assign)
              and isinstance(sentencia.targets[0], ast.Name)
              and sentencia.targets[0].id.isupper()
              and sentencia.targets[0].id in nombresUsados]
    modulo = ast.Module(body=tablas + [objetivo], type_ignores=[])
    ast.fix_missing_locations(modulo)
    # La función puede usar módulos corrientes de Python; se le dan
    # los habituales para que se ejecute igual que dentro del complemento.
    import re as _re, math as _math, time as _time, os as _os
    entorno = {"_": lambda t: t, "re": _re, "math": _math,
               "time": _time, "os": _os}
    exec(compile(modulo, ruta, "exec"), entorno)   # noqa: S102
    return entorno[nombreFuncion]


def tablaDeModulo(nombre, ruta=PRINCIPAL):
    """Devuelve el valor de una tabla declarada al principio del archivo."""
    with open(ruta, encoding="utf-8-sig") as archivo:
        arbol = ast.parse(archivo.read())
    for sentencia in arbol.body:
        if (isinstance(sentencia, ast.Assign)
                and isinstance(sentencia.targets[0], ast.Name)
                and sentencia.targets[0].id == nombre):
            return ast.literal_eval(sentencia.value)
    return None


class VelocidadMaximaDelProcesador(unittest.TestCase):
    """La tabla de procesadores: nombre del procesador -> velocidad máxima.

    Es la función más enredada del complemento. Estas pruebas fijan su
    comportamiento actual, para poder reorganizarla después sin cambiarlo.
    """

    @classmethod
    def setUpClass(cls):
        cls.resolver = extraer("_resolveMaxTurbo")

    def resolver_para(self, nombre, base=2.0):
        return type(self).resolver(None, nombre, base)

    def test_devuelve_siempre_un_numero(self):
        for nombre in ["AMD Ryzen 5 PRO 4650U with Radeon Graphics",
                       "AMD Ryzen 9 9950X", "Intel Core i7-1185G7",
                       "Procesador Desconocido XYZ", "", "   "]:
            with self.subTest(procesador=nombre):
                self.assertIsInstance(self.resolver_para(nombre), float)

    def test_nombre_vacio_o_ausente_no_revienta(self):
        self.assertIsInstance(self.resolver_para(""), float)
        self.assertIsInstance(self.resolver_para(None), float)

    def test_nunca_devuelve_menos_que_la_velocidad_base(self):
        """Una velocidad máxima por debajo de la base sería un dato absurdo."""
        for nombre in ["AMD Ryzen 5 PRO 4650U", "Intel Core i5-1035G1",
                       "Procesador Desconocido", ""]:
            for base in (1.0, 2.1, 3.6):
                with self.subTest(procesador=nombre, base=base):
                    self.assertGreaterEqual(self.resolver_para(nombre, base), base)

    def test_no_distingue_mayusculas(self):
        self.assertEqual(self.resolver_para("AMD RYZEN 9 9950X"),
                         self.resolver_para("amd ryzen 9 9950x"))

    def test_un_procesador_conocido_da_mas_que_la_base(self):
        self.assertGreater(self.resolver_para("AMD Ryzen 9 9950X", 4.3), 4.3)

    def test_devuelve_valores_plausibles(self):
        """Ningún procesador de sobremesa pasa hoy de 7 GHz."""
        for nombre in ["AMD Ryzen 9 9950X", "Intel Core i9-14900K",
                       "AMD Ryzen 5 PRO 4650U", "Desconocido"]:
            with self.subTest(procesador=nombre):
                valor = self.resolver_para(nombre, 3.0)
                self.assertGreater(valor, 0.5)
                self.assertLess(valor, 7.0)


class TablaDeProcesadores(unittest.TestCase):
    """La tabla se recorre de arriba abajo y gana la primera coincidencia.

    Por eso el orden es parte del significado: si alguien anota "7900" encima
    de "7900x3d", el procesador largo deja de encontrarse y nadie se entera,
    porque igualmente devuelve un número creíble.
    """

    @classmethod
    def setUpClass(cls):
        cls.tabla = tablaDeModulo("VELOCIDAD_MAXIMA_CONOCIDA")

    def test_gana_siempre_el_modelo_mas_concreto(self):
        """Un nombre puede encajar con dos entradas; debe ganar la mas larga.

        Es un fallo que ya existia: el Intel i5-13600K encajaba con "3600",
        que es un AMD Ryzen 5, y se le atribuia la velocidad de aquel.
        """
        if self.tabla is None:
            self.skipTest("todavía no existe la tabla de procesadores")
        resolver = extraer("_resolveMaxTurbo")
        velocidadPorModelo = {m: v for modelos, v in self.tabla for m in modelos}
        for modelos, velocidad in self.tabla:
            for modelo in modelos:
                # solo se comprueban los modelos que nadie mas contiene ni
                # contienen a otro con distinta velocidad
                with self.subTest(modelo=modelo):
                    obtenida = resolver(None, modelo, 2.0)
                    masLargos = [otro for otro in velocidadPorModelo
                                 if otro != modelo and modelo in otro]
                    if not masLargos:
                        self.assertEqual(obtenida, velocidad)

    def test_el_intel_13600k_no_se_confunde_con_el_ryzen_3600(self):
        if self.tabla is None:
            self.skipTest("todavía no existe la tabla de procesadores")
        resolver = extraer("_resolveMaxTurbo")
        self.assertEqual(resolver(None, "Intel(R) Core(TM) i5-13600K", 2.5), 5.00)
        self.assertEqual(resolver(None, "AMD Ryzen 5 3600 6-Core", 2.5), 4.20)

    def test_las_velocidades_son_creibles(self):
        if self.tabla is None:
            self.skipTest("todavía no existe la tabla de procesadores")
        for modelos, velocidad in self.tabla:
            with self.subTest(modelos=modelos):
                self.assertIsInstance(velocidad, float)
                self.assertGreater(velocidad, 2.0, "velocidad demasiado baja")
                self.assertLess(velocidad, 8.0, "velocidad demasiado alta")

    def test_ningun_modelo_esta_dos_veces(self):
        if self.tabla is None:
            self.skipTest("todavía no existe la tabla de procesadores")
        todos = [m for modelos, _v in self.tabla for m in modelos]
        repetidos = sorted({m for m in todos if todos.count(m) > 1})
        self.assertFalse(repetidos, f"modelos repetidos en la tabla: {repetidos}")


class DireccionDeAparatoBluetooth(unittest.TestCase):
    """El identificador que da Windows trae la direccion en formatos distintos."""

    @classmethod
    def setUpClass(cls):
        cls.direccion = extraer("_direccionDelDispositivo")

    def test_reconoce_los_formatos_conocidos(self):
        casos = {
            # el de unos auriculares reales, con la direccion al final
            r"BTHENUM\{0000111E-0000-1000-8000-00805F9B34FB}_LOCALMFG&0002"
            r"\8&D497958&0&00762526050E_C00000000": "00762526050E",
            r"BTHENUM\DEV_00762526050E\8&D497958&0&00762526050E": "00762526050E",
            r"BTHLE\DEV_AABBCCDDEEFF\9&12345678&0&AABBCCDDEEFF": "AABBCCDDEEFF",
            r"BTHLEDEVICE\{0000180F-0000-1000-8000-00805F9B34FB}_DEV_112233445566":
                "112233445566",
        }
        for identificador, esperada in casos.items():
            with self.subTest(identificador=identificador[:40]):
                self.assertEqual(type(self).direccion(identificador), esperada)

    def test_devuelve_nada_cuando_no_hay_direccion(self):
        for identificador in ("", "SIN NADA QUE PAREZCA UNA DIRECCION", "USB\\VID_046D"):
            with self.subTest(identificador=identificador):
                self.assertIsNone(type(self).direccion(identificador))

    def test_nunca_revienta(self):
        """Windows puede devolver identificadores con cualquier forma."""
        for identificador in ("\\", "&&&", "0" * 200, "DEV_", "DEV_ZZZZZZZZZZZZ"):
            with self.subTest(identificador=identificador[:20]):
                type(self).direccion(identificador)


if __name__ == "__main__":
    unittest.main(verbosity=2)
