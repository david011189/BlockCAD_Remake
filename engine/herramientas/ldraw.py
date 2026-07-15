"""Lector de la biblioteca de piezas de LDraw.

Esto NO es parte del motor: es una utilidad que se ejecuta a mano para
extraer medidas y conexiones de LDraw y generar un catálogo. El motor solo
consume el catálogo generado, así que no depende de LDraw ni de sus 136 MB.

La biblioteca de piezas de LDraw está bajo licencia CC BY 4.0.
Atribución: The LDraw Parts Library — https://www.ldraw.org

Formato de LDraw, en una línea: cada archivo `.dat` describe una pieza con
líneas numeradas por tipo. Solo interesan dos:

    0 <comentario o metadato>
    1 <color> <x> <y> <z> <a b c d e f g h i> <subarchivo>
    3 <color> <x1 y1 z1> <x2 y2 z2> <x3 y3 z3>          triángulo
    4 <color> <x1 y1 z1> ... <x4 y4 z4>                 cuadrilátero

La línea 1 coloca otro archivo con una matriz de 3x3 y una traslación. Es
recursiva: una viga referencia una subpieza que referencia los agujeros.

Unidades: 1 LDU = 0,4 mm. Un stud son 20 LDU, una placa 8 y un ladrillo 24.
Ojo con los ejes: en LDraw Y es la vertical y apunta hacia ABAJO.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from functools import lru_cache

#: Unidad de LDraw en milímetros.
LDU_MM = 0.4

#: Equivalencias, en LDU.
STUD = 20
PLACA = 8
LADRILLO = 24
MODULO_TECHNIC = 20

#: Primitivas que delatan una conexión.
CONEXIONES = {
    "peghole.dat": "agujero_pin",
    "axlehole.dat": "agujero_eje",
    "axlehol8.dat": "agujero_eje",
    "axlehol9.dat": "agujero_eje",
    "stud.dat": "stud",
    "stud2.dat": "stud",
    "stud2a.dat": "stud",
    "stud3.dat": "stud",
    "stud3a.dat": "stud",
    "stud4.dat": "stud_hueco",
}


@dataclass(frozen=True, slots=True)
class Punto:
    x: float
    y: float
    z: float

    def __add__(self, otro: "Punto") -> "Punto":
        return Punto(self.x + otro.x, self.y + otro.y, self.z + otro.z)


@dataclass(frozen=True, slots=True)
class Matriz:
    """Matriz de 3x3 más traslación, tal como la escribe LDraw."""

    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 0.0
    e: float = 1.0
    f: float = 0.0
    g: float = 0.0
    h: float = 0.0
    i: float = 1.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def aplicar(self, p: Punto) -> Punto:
        return Punto(
            self.a * p.x + self.b * p.y + self.c * p.z + self.x,
            self.d * p.x + self.e * p.y + self.f * p.z + self.y,
            self.g * p.x + self.h * p.y + self.i * p.z + self.z,
        )

    def componer(self, otra: "Matriz") -> "Matriz":
        """Encadena dos transformaciones: primero `otra`, luego esta.

        La traslación de la hija hay que girarla con la matriz de la madre,
        no sumarla tal cual: un agujero a 20 LDU de su subpieza acaba en otro
        sitio si la subpieza viene rotada.
        """
        origen = self.aplicar(Punto(otra.x, otra.y, otra.z))
        return Matriz(
            a=self.a * otra.a + self.b * otra.d + self.c * otra.g,
            b=self.a * otra.b + self.b * otra.e + self.c * otra.h,
            c=self.a * otra.c + self.b * otra.f + self.c * otra.i,
            d=self.d * otra.a + self.e * otra.d + self.f * otra.g,
            e=self.d * otra.b + self.e * otra.e + self.f * otra.h,
            f=self.d * otra.c + self.e * otra.f + self.f * otra.i,
            g=self.g * otra.a + self.h * otra.d + self.i * otra.g,
            h=self.g * otra.b + self.h * otra.e + self.i * otra.h,
            i=self.g * otra.c + self.h * otra.f + self.i * otra.i,
            x=origen.x,
            y=origen.y,
            z=origen.z,
        )


@dataclass
class Conexion:
    tipo: str
    punto: Punto


@dataclass
class Pieza:
    numero: str
    nombre: str
    palabras: list[str] = field(default_factory=list)
    licencia: str = ""
    vertices: list[Punto] = field(default_factory=list)
    conexiones: list[Conexion] = field(default_factory=list)

    def caja(self) -> tuple[Punto, Punto]:
        """Esquinas mínima y máxima, en LDU."""
        if not self.vertices:
            return Punto(0, 0, 0), Punto(0, 0, 0)
        xs = [v.x for v in self.vertices]
        ys = [v.y for v in self.vertices]
        zs = [v.z for v in self.vertices]
        return Punto(min(xs), min(ys), min(zs)), Punto(max(xs), max(ys), max(zs))

    def medidas(self) -> tuple[float, float, float]:
        """Ancho, alto y fondo en LDU. En LDraw la vertical es Y."""
        minimo, maximo = self.caja()
        return (maximo.x - minimo.x, maximo.y - minimo.y, maximo.z - minimo.z)


_NOMBRE_RE = re.compile(r"^0\s+(?!!)(?P<texto>.+)$")
_META_RE = re.compile(r"^0\s+!(?P<clave>[A-Z_]+)\s+(?P<valor>.*)$")


class Biblioteca:
    """Acceso a los `.dat` de LDraw dentro del zip oficial."""

    def __init__(self, ruta_zip: str) -> None:
        self._zip = zipfile.ZipFile(ruta_zip)
        # LDraw busca cada nombre en parts/, p/ y sus subcarpetas. Un índice
        # por nombre en minúsculas evita recorrer 20.000 entradas por consulta.
        self._indice: dict[str, str] = {}
        for entrada in self._zip.namelist():
            if entrada.lower().endswith(".dat"):
                self._indice.setdefault(entrada.split("/")[-1].lower(), entrada)
                # También por ruta relativa, para 's\32316s01.dat'.
                partes = entrada.lower().split("/")
                if len(partes) >= 2:
                    self._indice.setdefault("/".join(partes[-2:]), entrada)

    def existe(self, nombre: str) -> bool:
        return self._clave(nombre) is not None

    def _clave(self, nombre: str) -> str | None:
        limpio = nombre.lower().replace("\\", "/")
        return self._indice.get(limpio) or self._indice.get(limpio.split("/")[-1])

    @lru_cache(maxsize=4096)
    def leer(self, nombre: str) -> list[str]:
        clave = self._clave(nombre)
        if clave is None:
            return []
        return self._zip.read(clave).decode("latin-1").splitlines()

    def piezas(self) -> list[str]:
        return [
            entrada.split("/")[-1]
            for entrada in self._zip.namelist()
            if re.fullmatch(r"ldraw/parts/[^/]+\.dat", entrada.lower())
        ]

    def cabecera(self, nombre: str) -> tuple[str, list[str], str]:
        """Devuelve (nombre legible, palabras clave, licencia) sin recorrerlo entero."""
        titulo, palabras, licencia = "", [], ""
        for linea in self.leer(nombre)[:40]:
            if not titulo:
                encontrado = _NOMBRE_RE.match(linea)
                if encontrado and not linea.startswith("0 Name:"):
                    titulo = encontrado.group("texto").strip()
            meta = _META_RE.match(linea)
            if not meta:
                continue
            if meta.group("clave") == "KEYWORDS":
                palabras += [p.strip() for p in meta.group("valor").split(",")]
            elif meta.group("clave") == "LICENSE":
                licencia = meta.group("valor").strip()
        return titulo, palabras, licencia

    def analizar(self, nombre: str) -> Pieza:
        """Recorre la pieza y todas sus subpiezas hasta el fondo.

        Una viga no referencia sus agujeros: referencia una subpieza que sí lo
        hace. Sin recursión, las conexiones no aparecen.
        """
        titulo, palabras, licencia = self.cabecera(nombre)
        pieza = Pieza(
            numero=nombre.removesuffix(".dat"),
            nombre=titulo,
            palabras=palabras,
            licencia=licencia,
        )
        self._recorrer(nombre, Matriz(), pieza, profundidad=0, visitados=set())
        return pieza

    def _recorrer(
        self,
        nombre: str,
        transformacion: Matriz,
        pieza: Pieza,
        profundidad: int,
        visitados: set[str],
    ) -> None:
        # Los ciclos no deberían existir en LDraw, pero un archivo mal formado
        # no debe colgar la herramienta.
        if profundidad > 30:
            return

        for linea in self.leer(nombre):
            campos = linea.strip().split()
            if not campos:
                continue

            if campos[0] == "1" and len(campos) >= 15:
                valores = [float(v) for v in campos[2:14]]
                hija = Matriz(
                    x=valores[0], y=valores[1], z=valores[2],
                    a=valores[3], b=valores[4], c=valores[5],
                    d=valores[6], e=valores[7], f=valores[8],
                    g=valores[9], h=valores[10], i=valores[11],
                )
                completa = transformacion.componer(hija)
                subarchivo = " ".join(campos[14:]).replace("\\", "/")

                tipo = CONEXIONES.get(subarchivo.split("/")[-1].lower())
                if tipo is not None:
                    pieza.conexiones.append(
                        Conexion(tipo, Punto(completa.x, completa.y, completa.z))
                    )

                if self.existe(subarchivo):
                    self._recorrer(
                        subarchivo, completa, pieza, profundidad + 1, visitados
                    )

            elif campos[0] in ("3", "4") and len(campos) >= 11:
                cuantos = 3 if campos[0] == "3" else 4
                numeros = [float(v) for v in campos[2 : 2 + cuantos * 3]]
                for i in range(cuantos):
                    bruto = Punto(*numeros[i * 3 : i * 3 + 3])
                    pieza.vertices.append(transformacion.aplicar(bruto))
