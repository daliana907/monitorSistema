# -*- coding: utf-8 -*-
"""Comprobaciones sobre la forma del código, sin ejecutarlo.

Cada una de estas pruebas existe porque el fallo que detecta YA OCURRIÓ en este
proyecto. No son precauciones teóricas.

Ejecutar con:   python -m unittest discover -s tests -v
"""
import ast
import os
import re
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def archivosPython():
    for carpeta, _sub, archivos in os.walk(RAIZ):
        if "__pycache__" in carpeta or os.sep + "tests" in carpeta:
            continue
        for nombre in sorted(archivos):
            if nombre.endswith(".py"):
                yield os.path.join(carpeta, nombre)


def leer(ruta):
    with open(ruta, encoding="utf-8-sig") as archivo:
        return archivo.read()


def arbol(ruta):
    return ast.parse(leer(ruta))


def nodosPropios(funcion):
    """Nodos que pertenecen a la función, sin entrar en funciones anidadas.

    Hace falta porque las funciones anidadas y las comprensiones tienen su
    propio ámbito de nombres.
    """
    encontrados = []

    def recorrer(nodo):
        for hijo in ast.iter_child_nodes(nodo):
            if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
                                 ast.ListComp, ast.SetComp, ast.DictComp,
                                 ast.GeneratorExp, ast.ClassDef)):
                continue
            encontrados.append(hijo)
            recorrer(hijo)

    recorrer(funcion)
    return encontrados


class TodoCompila(unittest.TestCase):
    def test_todos_los_archivos_compilan(self):
        for ruta in archivosPython():
            with self.subTest(archivo=os.path.basename(ruta)):
                try:
                    arbol(ruta)
                except SyntaxError as error:
                    self.fail(f"{ruta} no compila: {error}")


class DecoradoresDeAtajos(unittest.TestCase):
    """Un decorador @scriptHandler.script debe quedar pegado a su script_...

    Ocurrió de verdad: al insertar una función auxiliar entre el decorador y su
    función, el atajo de teclado desapareció sin más aviso que una línea en el
    registro de NVDA.
    """

    def test_cada_decorador_esta_sobre_un_script(self):
        for ruta in archivosPython():
            for nodo in ast.walk(arbol(ruta)):
                if not isinstance(nodo, ast.FunctionDef):
                    continue
                for decorador in nodo.decorator_list:
                    objetivo = getattr(decorador, "func", decorador)
                    if getattr(objetivo, "attr", "") == "script":
                        self.assertTrue(
                            nodo.name.startswith("script_"),
                            f"{os.path.basename(ruta)}:{nodo.lineno} el decorador de atajo "
                            f"quedó sobre '{nodo.name}', que no es un script. "
                            "El atajo no se registrará.")


class FuncionDeTraduccion(unittest.TestCase):
    """'_' no puede ser a la vez variable y función de traducción.

    Ocurrió de verdad: un 'for _ in range(8)' dejó sin efecto todas las alertas
    automáticas de otro complemento durante meses.
    """

    def test_no_se_pisa_la_funcion_de_traduccion(self):
        for ruta in archivosPython():
            for nodo in ast.walk(arbol(ruta)):
                if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                propios = nodosPropios(nodo)
                asignaciones = [x for x in propios
                                if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store)
                                and x.id == "_"]
                llamadas = [x for x in propios
                            if isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
                            and x.func.id == "_"]
                self.assertFalse(
                    asignaciones and llamadas,
                    f"{os.path.basename(ruta)}:{nodo.lineno} en '{nodo.name}' se usa '_' "
                    "como variable y además se llama a _() para traducir. Reventará.")

    def test_quien_traduce_prepara_la_traduccion(self):
        """Sin addonHandler.initTranslation(), _() no encuentra los textos del complemento."""
        for ruta in archivosPython():
            texto = leer(ruta)
            if re.search(r"(?<![\w.])_\(", texto) and "initTranslation" not in texto:
                self.fail(f"{os.path.basename(ruta)} usa _() pero nunca llama a "
                          "addonHandler.initTranslation()")

    def test_no_hay_traducciones_envueltas_dos_veces(self):
        for ruta in archivosPython():
            texto = leer(ruta)
            self.assertNotIn("_(_(", texto,
                             f"{os.path.basename(ruta)} tiene una traducción envuelta dos veces")


class ManejoDeErrores(unittest.TestCase):
    def test_no_hay_capturas_sin_tipo(self):
        """'except:' a secas atrapa hasta un Control+C o un fallo de memoria."""
        encontrados = []
        for ruta in archivosPython():
            for nodo in ast.walk(arbol(ruta)):
                if isinstance(nodo, ast.ExceptHandler) and nodo.type is None:
                    encontrados.append(f"{os.path.basename(ruta)}:{nodo.lineno}")
        self.assertFalse(
            encontrados,
            f"{len(encontrados)} capturas 'except:' sin decir qué error esperan:\n  "
            + "\n  ".join(encontrados))


class Seguridad(unittest.TestCase):
    def test_no_se_ejecuta_codigo_dinamico(self):
        for ruta in archivosPython():
            for nodo in ast.walk(arbol(ruta)):
                if isinstance(nodo, ast.Call) and getattr(nodo.func, "id", "") in ("eval", "exec"):
                    self.fail(f"{os.path.basename(ruta)}:{nodo.lineno} usa {nodo.func.id}()")

    def test_no_se_llama_al_interprete_de_comandos(self):
        for ruta in archivosPython():
            for nodo in ast.walk(arbol(ruta)):
                if not isinstance(nodo, ast.Call):
                    continue
                for clave in nodo.keywords:
                    if clave.arg == "shell" and getattr(clave.value, "value", None) is True:
                        self.fail(f"{os.path.basename(ruta)}:{nodo.lineno} usa shell=True")

    def test_no_hay_rutas_con_nombre_de_usuario(self):
        """Una ruta con un nombre de usuario concreto no existe en otro equipo."""
        patron = re.compile(r"[A-Za-z]:\\+Users\\+(?!<)\w")
        encontrados = []
        for ruta in archivosPython():
            for nodo in ast.walk(arbol(ruta)):
                if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
                    if patron.search(nodo.value):
                        encontrados.append(
                            f"{os.path.basename(ruta)}:{nodo.lineno}  {nodo.value[:52]}")
        self.assertFalse(
            encontrados,
            f"{len(encontrados)} rutas con un nombre de usuario escrito a mano "
            f"(no existen en otro equipo):\n  " + "\n  ".join(encontrados))


class MetodosYDecoradores(unittest.TestCase):
    """Existen porque un generador de codigo automatico se colo, mas de una vez,
    entre un decorador y la funcion a la que adornaba. El decorador acababa
    puesto en la funcion equivocada y la otra se quedaba sin el; NVDA seguia
    cargando el complemento y el fallo solo aparecia al usarlo.
    """

    def test_todo_metodo_recibe_self(self):
        """Dentro de una clase, una funcion sin 'self' solo vale como estatica.

        Si una funcion pierde su '@staticmethod', deja de poder llamarse y el
        error no salta hasta que alguien la usa.
        """
        sueltas = []
        for ruta in archivosPython():
            for clase in ast.walk(arbol(ruta)):
                if not isinstance(clase, ast.ClassDef):
                    continue
                for nodo in clase.body:
                    if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    marcas = {getattr(d, "id", getattr(d, "attr", ""))
                              for d in nodo.decorator_list}
                    if marcas & {"staticmethod", "classmethod"}:
                        continue
                    argumentos = [a.arg for a in nodo.args.args]
                    if not argumentos or argumentos[0] not in ("self", "cls"):
                        sueltas.append(
                            f"{os.path.basename(ruta)}:{nodo.lineno}  "
                            f"{clase.name}.{nodo.name}")
        self.assertFalse(sueltas, "estos metodos no reciben 'self' y tampoco estan "
                         "marcados como estaticos:\n  " + "\n  ".join(sueltas))

    def test_ningun_decorador_esta_despegado_de_su_funcion(self):
        """Una linea en blanco entre el decorador y el 'def' delata una insercion."""
        despegados = []
        for ruta in archivosPython():
            lineas = leer(ruta).splitlines()
            for nodo in ast.walk(arbol(ruta)):
                if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef,
                                         ast.ClassDef)) or not nodo.decorator_list:
                    continue
                ultimo = max(d.end_lineno for d in nodo.decorator_list)
                for numero in range(ultimo + 1, nodo.lineno):
                    if not lineas[numero - 1].strip():
                        despegados.append(
                            f"{os.path.basename(ruta)}:{numero}  antes de {nodo.name}")
                        break
        self.assertFalse(despegados, "hay decoradores separados de su funcion por una "
                         "linea en blanco:\n  " + "\n  ".join(despegados))


class EsperasConLimite(unittest.TestCase):
    """Toda espera a un programa externo debe tener un tiempo maximo.

    Existe porque habia cinco sitios sin limite: si el programa al que se
    llamaba se colgaba, la espera no terminaba nunca. No llega a congelar NVDA,
    pero el aviso de progreso sigue sonando y la operacion no acaba jamas.
    """

    ESPERAS = ("run", "communicate", "urlopen", "wait")

    def test_toda_llamada_a_un_programa_externo_tiene_limite(self):
        sinLimite = []
        for ruta in archivosPython():
            for nodo in ast.walk(arbol(ruta)):
                if not isinstance(nodo, ast.Call):
                    continue
                nombre = getattr(nodo.func, "attr", getattr(nodo.func, "id", ""))
                if nombre not in self.ESPERAS:
                    continue
                if any(clave.arg == "timeout" for clave in nodo.keywords):
                    continue
                # wait() y communicate() admiten el limite como primer argumento
                if nombre in ("wait", "communicate") and nodo.args:
                    continue
                sinLimite.append(f"{os.path.basename(ruta)}:{nodo.lineno}  {nombre}()")
        self.assertFalse(sinLimite, f"{len(sinLimite)} esperas sin tiempo maximo "
                         "(si el programa se cuelga, no terminan nunca):\n  "
                         + "\n  ".join(sinLimite))

    def test_los_hilos_dejan_cerrar_nvda(self):
        """Un hilo que no sea 'daemon' puede impedir que NVDA se cierre."""
        sueltos = []
        for ruta in archivosPython():
            for nodo in ast.walk(arbol(ruta)):
                if not (isinstance(nodo, ast.Call)
                        and getattr(nodo.func, "attr", "") == "Thread"):
                    continue
                esDemonio = any(clave.arg == "daemon"
                                and getattr(clave.value, "value", False) is True
                                for clave in nodo.keywords)
                if not esDemonio:
                    sueltos.append(f"{os.path.basename(ruta)}:{nodo.lineno}")
        self.assertFalse(sueltos, "estos hilos no estan marcados como 'daemon' y "
                         "pueden impedir que NVDA se cierre:\n  " + "\n  ".join(sueltos))


if __name__ == "__main__":
    unittest.main(verbosity=2)
