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

El color: el campo que sigue al tipo de línea. El código 16 significa
«hereda del padre»: al bajar por una línea 1, un triángulo con 16 acaba del
color con que se referenció el subarchivo. En el nivel raíz, 16 es «el color
principal de la pieza», el que elige quien construye. El 24 es lo mismo para
las aristas y aquí se trata igual. Cualquier otro código es un color FIJO de
LDraw (0 negro, 15 blanco, 4 rojo...): la pupila de un ojo es negra la pinte
quien la pinte.

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

#: Primitivas que delatan una conexión, con el título que LDraw les pone.
#:
#: El título importa: es lo que distingue un agujero de un eje, y por el
#: nombre solo no se ve. `axlehol8.dat` se llama «Technic Axle Perimeter» y
#: es el perfil en cruz de un eje —el mismo contorno vale para el eje macizo
#: y para el hueco que lo aloja—, así que no dice si hay agujero. Estuvo
#: mapeado a `agujero_eje` y le puso agujeros fantasma a seis ejes: un eje no
#: tiene agujeros, tiene contorno.
#:
#: Por eso aquí solo entran las primitivas cuyo título afirma la pieza, no la
#: forma. Lo que describe aristas, perfiles o superficies se queda fuera.
CONEXIONES = {
    # Hembra: hay un hueco donde meter algo.
    "peghole.dat": "agujero_pin",  # Peg Hole End
    "peghole5.dat": "agujero_pin",  # Peg Hole End Extended Medium
    "axlehole.dat": "agujero_eje",  # Technic Axle Hole Closed
    # Las variantes «Reduced» y compañía son agujeros de eje igual de reales:
    # con menos plástico alrededor, pero el hueco es el mismo. Los engranajes
    # dibujan el suyo con estas, así que sin ellas una rueda dentada no tiene
    # dónde recibir su eje.
    "axl2hole.dat": "agujero_eje",  # Technic Axle Hole Reduced Closed
    "axl3hole.dat": "agujero_eje",  # Technic Axle Hole Semi-Reduced
    "axl4hole.dat": "agujero_eje",  # Technic Axle Hole Two-toothed Sliding
    "axlehol5.dat": "agujero_eje",  # Technic Axle Hole Open Two Opposite Sides
    # La SUPERFICIE del diente también afirma: es el plástico interior del
    # agujero, y un eje macizo no la tiene. Algunas piezas —los conectores
    # angulares, la cazoleta— dibujan su cruz con la familia descompuesta en
    # vez del agujero cerrado, y sin esto quedaban ciegas. El punto cae en la
    # boca del agujero y no en su centro; para insertar da igual: lo que se
    # comparte es la recta.
    "axl2ho10.dat": "agujero_eje",  # Technic Axle Hole Reduced Tooth Surface
    "axl3ho10.dat": "agujero_eje",  # Technic Axle Hole Semi-Reduced Tooth Surface
    # La rueda de 24 dientes (3648b, alias 24505) dibuja su agujero a mano,
    # en octavos de geometría cruda, sin pasar por ninguna primitiva. El
    # título del subarchivo sí lo afirma: «Eighth of Centre Axlehole». Los
    # ocho octavos caen en el mismo punto con la misma recta, así que la
    # deduplicación del generador los deja en un solo agujero. Sin esto, la
    # rueda no podía recibir su eje y el camión de reciclaje se quedaba sin
    # tren de volcado.
    #
    # Ojo: es un subarchivo, no una primitiva, y su agujero corre por su +Z
    # local —la rueda se dibuja plana en el plano XY—, no por el +Y que usan
    # todas las primitivas. Por eso declara su eje.
    "3648s02.dat": ("agujero_eje", (0.0, 0.0, 1.0)),
    # Macho: es lo que se mete.
    "confric4.dat": "pin",  # Technic Friction Pin 1.0 with Base Collar
    "confric5.dat": "pin",  # Technic Friction Pin 1.0 Slotted
    "connect.dat": "pin",  # Technic Pin 1.0 with Base Collar
    "connect8.dat": "pin",  # Technic Pin 1.0 with Base Collar and Blind Hole
    "axleend2.dat": "punta_eje",  # Technic Axle End Beveled
    "axleend20.dat": "punta_eje",  # Technic Axle End 20 LDU
    # La rótula. La bola NO se detecta por la esfera —el sensor de distancia
    # y el separador dibujan esferas de adorno—, sino por el cuello que la
    # afirma: «Technic Axle Truncated to Fit Ball Joint», cuyo origen cae
    # justo en el centro de la bola. La cazoleta es como la rueda de 24: un
    # subarchivo con el título por delante («Ball Socket Half Type 3») y el
    # centro de la copa declarado a mano, porque su origen es el del
    # ladrillo. El 40 no es casual: es el mismo +40 de la bola de su pareja,
    # así que dos ladrillos unidos quedan a rejilla exacta de 4 studs.
    "axlesphe.dat": "bola",  # Technic Axle Truncated to Fit Ball Joint
    "92013s01.dat": ("cazoleta", (0.0, 1.0, 0.0), (40.0, 10.0, 0.0)),
    # Studs: el pivote de siempre.
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


def _eje_de(m: "Matriz", eje_local: tuple = (0.0, 1.0, 0.0)) -> Punto:
    """Hacia dónde mira una primitiva ya colocada.

    Toda primitiva de LDraw se dibuja a lo largo de su +Y local —un agujero es
    un cilindro en Y, un pin también—, así que su eje en el mundo es la segunda
    columna de la matriz: lo que le pasa al vector (0,1,0) al transformarlo.
    Un subarchivo que no siga ese convenio declara su eje local en el mapa.

    Se normaliza porque una matriz de LDraw puede escalar: un agujero más largo
    se dibuja estirando la misma primitiva, y lo que hace falta es la dirección,
    no el tamaño.
    """
    lx, ly, lz = eje_local
    x = m.a * lx + m.b * ly + m.c * lz
    y = m.d * lx + m.e * ly + m.f * lz
    z = m.g * lx + m.h * ly + m.i * lz
    largo = (x * x + y * y + z * z) ** 0.5
    if largo < 1e-9:
        return Punto(0.0, 0.0, 0.0)
    return Punto(round(x / largo, 4), round(y / largo, 4), round(z / largo, 4))


@dataclass
class Conexion:
    """Un sitio por donde se une una pieza, y hacia dónde mira.

    La dirección no es un adorno: un punto no dice si algo está insertado. Un
    pin metido en un agujero son dos rectas que coinciden, no dos puntos que
    coinciden. Sin el eje, el motor no puede distinguir una unión de un choque.

    Y no se puede deducir de la caja de la pieza: en el ladrillo 44865 el pin
    sale de lado y no a lo largo, así que «la dimensión más larga» daría un eje
    falso sin que saltara ningún error. La matriz de LDraw lo dice bien.
    """

    tipo: str
    punto: Punto
    eje: Punto


@dataclass
class Pieza:
    numero: str
    nombre: str
    palabras: list[str] = field(default_factory=list)
    licencia: str = ""
    #: Los triángulos, agrupados por su código de color YA RESUELTO: "16" es
    #: el cuerpo pintable y el resto son colores fijos de LDraw. Una pieza
    #: lisa tiene un solo grupo; los ojos tienen la pupila en el suyo.
    grupos: dict[str, list[Punto]] = field(default_factory=dict)
    conexiones: list[Conexion] = field(default_factory=list)

    @property
    def vertices(self) -> list[Punto]:
        """Todos los vértices, sin distinguir color: lo que miden las cajas."""
        return [v for grupo in self.grupos.values() for v in grupo]

    def caja(self) -> tuple[Punto, Punto]:
        """Esquinas mínima y máxima, en LDU."""
        vertices = self.vertices
        if not vertices:
            return Punto(0, 0, 0), Punto(0, 0, 0)
        xs = [v.x for v in vertices]
        ys = [v.y for v in vertices]
        zs = [v.z for v in vertices]
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
        color: str = "16",
    ) -> None:
        # `color` es el color con que ESTE archivo fue referenciado: es lo que
        # vale un 16 aquí dentro. En la raíz empieza en "16", así que lo que
        # nadie pinta queda en el grupo pintable.
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

                entrada = CONEXIONES.get(subarchivo.split("/")[-1].lower())
                if entrada is not None:
                    if not isinstance(entrada, tuple):
                        entrada = (entrada,)
                    tipo = entrada[0]
                    eje_local = entrada[1] if len(entrada) > 1 else (0.0, 1.0, 0.0)
                    # Las primitivas ponen su conexión en su propio origen.
                    # Un subarchivo puede no hacerlo —el centro de la copa de
                    # una cazoleta no es el origen del ladrillo— y entonces
                    # declara dónde cae, en sus coordenadas locales.
                    local = entrada[2] if len(entrada) > 2 else (0.0, 0.0, 0.0)
                    punto = completa.aplicar(Punto(*local))
                    pieza.conexiones.append(
                        Conexion(tipo, punto, _eje_de(completa, eje_local))
                    )

                if self.existe(subarchivo):
                    # El 16 hereda: el subarchivo se pinta del color con que
                    # se le referencia, y si esa referencia también dice 16,
                    # del que ya traíamos. El 24 (color de arista) hereda
                    # igual; en la práctica no llega a los triángulos.
                    heredado = (
                        color if campos[1] in ("16", "24") else campos[1]
                    )
                    self._recorrer(
                        subarchivo, completa, pieza, profundidad + 1,
                        visitados, heredado,
                    )

            elif campos[0] in ("3", "4") and len(campos) >= 11:
                cuantos = 3 if campos[0] == "3" else 4
                numeros = [float(v) for v in campos[2 : 2 + cuantos * 3]]
                esquinas = [
                    transformacion.aplicar(Punto(*numeros[i * 3 : i * 3 + 3]))
                    for i in range(cuantos)
                ]
                # El grupo del triángulo: su código, con el 16 (y el 24) ya
                # resueltos al color del padre.
                final = color if campos[1] in ("16", "24") else campos[1]
                grupo = pieza.grupos.setdefault(final, [])
                # Un cuadrilátero se parte en dos triángulos. Guardarlo con sus
                # cuatro esquinas bastaba para medir la caja, pero para dibujar
                # no: los vértices se leen de tres en tres, así que un cuarto
                # vértice suelto desplazaría todo lo que venga detrás y la
                # malla saldría hecha trizas.
                if cuantos == 4:
                    grupo += [
                        esquinas[0], esquinas[1], esquinas[2],
                        esquinas[0], esquinas[2], esquinas[3],
                    ]
                else:
                    grupo += esquinas
