"""Geometría del motor, medida en LDU.

Por qué LDU y no studs y placas
-------------------------------

El motor medía `x` e `y` en studs y `z` en placas. Con esas unidades una viga
Technic es incolocable: mide 8 mm de alto, o sea 2,5 placas, y las
coordenadas son enteras.

1 LDU = 0,4 mm, la unidad de LDraw, y es la única en la que todo LEGO cae en
números enteros:

    stud .............. 20 LDU  (8 mm)
    placa (alto) ....... 8 LDU  (3,2 mm)
    ladrillo (alto) ... 24 LDU  (9,6 mm)
    módulo Technic .... 20 LDU  (8 mm)
    medio módulo ...... 10 LDU

Medio módulo, y no el módulo entero, es el paso real de la rejilla Technic:
la caja de engranajes 6588 tiene agujeros a media distancia. Comprobado
contra las 97 piezas del set 45300, ninguna lo rompe.

Esto es interior del motor. Quien escribe código BlockCAD sigue contando en
studs y placas; el lenguaje traduce.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import InvalidGeometryError

#: Un LDU en milímetros.
LDU_MM = 0.4

#: Separación entre studs, y también entre agujeros Technic.
STUD = 20
MODULO_TECHNIC = 20

#: Paso real de la rejilla Technic.
MEDIO_MODULO = 10

#: Alturas.
PLACA = 8
LADRILLO = 24


def _is_integer(value: object) -> bool:
    # bool es subclase de int, pero True como coordenada acabaría escrito como
    # `true` en el JSON y no como un número.
    return isinstance(value, int) and not isinstance(value, bool)


#: Las tres matrices de giro de 90° a derechas, con Z hacia arriba.
_GIROS_90 = {
    "x": ((1, 0, 0), (0, 0, -1), (0, 1, 0)),
    "y": ((0, 0, 1), (0, 1, 0), (-1, 0, 0)),
    "z": ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
}


@dataclass(frozen=True, slots=True)
class Orientation:
    """Cómo está girada una pieza: una de las 24 orientaciones de un cubo.

    Se guarda como una matriz de 3x3 de enteros, igual que LDraw. Con ángulos
    sueltos por eje habría que fijar un orden de aplicación y una misma
    orientación tendría varias escrituras; con la matriz cada orientación es
    una y solo una, y componer dos giros es multiplicar.

    Solo se admiten giros de 90°, así que las casillas son -1, 0 o 1 y las
    cuentas salen exactas: nada de coma flotante.
    """

    filas: tuple[tuple[int, int, int], ...] = ((1, 0, 0), (0, 1, 0), (0, 0, 1))

    def __post_init__(self) -> None:
        if len(self.filas) != 3 or any(len(f) != 3 for f in self.filas):
            raise InvalidGeometryError("Una orientación es una matriz de 3x3.")
        if any(v not in (-1, 0, 1) for fila in self.filas for v in fila):
            raise InvalidGeometryError(
                "Una orientación solo admite giros de 90 grados."
            )
        # Una matriz de giro tiene un único valor por fila y por columna, y su
        # determinante es +1. Con -1 sería un espejo, y una pieza reflejada no
        # existe.
        if any(sum(abs(v) for v in fila) != 1 for fila in self.filas):
            raise InvalidGeometryError("La orientación no es un giro válido.")
        if any(
            sum(abs(self.filas[f][c]) for f in range(3)) != 1 for c in range(3)
        ):
            raise InvalidGeometryError("La orientación no es un giro válido.")
        if self._determinante() != 1:
            raise InvalidGeometryError(
                "Esa orientación refleja la pieza en vez de girarla."
            )

    def _determinante(self) -> int:
        (a, b, c), (d, e, f), (g, h, i) = self.filas
        return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)

    @classmethod
    def around(cls, eje: str, grados: int) -> "Orientation":
        """Giro alrededor de un eje, en pasos de 90 grados."""
        clave = eje.lower()
        if clave not in _GIROS_90:
            raise InvalidGeometryError(
                f"El eje debe ser x, y o z, no {eje!r}."
            )
        if grados % 90:
            raise InvalidGeometryError("El giro debe ser múltiplo de 90 grados.")

        vueltas = (grados // 90) % 4
        resultado = cls()
        paso = cls(_GIROS_90[clave])
        for _ in range(vueltas):
            resultado = paso.then(resultado)
        return resultado

    @classmethod
    def z(cls, grados: int) -> "Orientation":
        """Atajo para el giro de siempre, el del eje vertical."""
        return cls.around("z", grados)

    def then(self, otra: "Orientation") -> "Orientation":
        """Aplica primero `otra` y luego esta."""
        return Orientation(
            tuple(
                tuple(
                    sum(self.filas[f][k] * otra.filas[k][c] for k in range(3))
                    for c in range(3)
                )
                for f in range(3)
            )
        )

    def apply(self, x: int, y: int, z: int) -> tuple[int, int, int]:
        return tuple(
            fila[0] * x + fila[1] * y + fila[2] * z for fila in self.filas
        )

    @property
    def is_identity(self) -> bool:
        return self.filas == ((1, 0, 0), (0, 1, 0), (0, 0, 1))

    @property
    def keeps_z_up(self) -> bool:
        """True si la pieza sigue de pie, aunque esté girada sobre sí misma.

        Sirve para saber si sus studs siguen mirando hacia arriba.
        """
        return self.filas[2][2] == 1


@dataclass(frozen=True, slots=True)
class Connection:
    """Un sitio por donde una pieza se une a otra.

    El punto va en LDU y relativo a la esquina mínima de la pieza, así que
    para saber dónde cae de verdad hay que girarlo y sumarle su posición.

    Los tipos vienen de LDraw. Hay hembras —`agujero_pin` es el hueco de un
    pin, `agujero_eje` el de un eje— y machos: `pin` es un pin y `punta_eje`
    la punta de un eje. `stud` es el pivote de siempre. Un agujero aparece en
    las dos caras de la pieza, y eso no es un duplicado: es lo que hace que
    dos vigas pegadas compartan el punto y se sepan conectadas.

    El `eje` es la RECTA por la que se entra o se sale, no una flecha: meter
    un pin por un lado o por el otro es la misma inserción, así que el sentido
    se descarta. Sin la recta, un punto no dice si algo está insertado: un pin
    en un agujero son dos rectas que coinciden.
    """

    tipo: str
    punto: tuple[int, int, int]
    eje: tuple[float, float, float] = (0.0, 0.0, 0.0)

    #: Los tipos que se meten, y los que alojan.
    MACHOS = ("pin", "punta_eje")
    HEMBRAS = ("agujero_pin", "agujero_eje")

    @property
    def es_macho(self) -> bool:
        return self.tipo in self.MACHOS

    @property
    def es_hembra(self) -> bool:
        return self.tipo in self.HEMBRAS


@dataclass(frozen=True, slots=True)
class GridPosition:
    """Posición de la esquina mínima de una pieza, en LDU.

    `x` e `y` son horizontales y `z` es la altura. Ojo si vienes de LDraw:
    allí la vertical es Y y apunta hacia abajo.
    """

    x: int
    y: int
    z: int

    def __post_init__(self) -> None:
        if not all(_is_integer(value) for value in (self.x, self.y, self.z)):
            raise TypeError("Las coordenadas deben ser números enteros.")
        if self.z < 0:
            raise InvalidGeometryError("La coordenada z no puede ser negativa.")

    def translated(self, dx: int = 0, dy: int = 0, dz: int = 0) -> "GridPosition":
        return GridPosition(self.x + dx, self.y + dy, self.z + dz)


@dataclass(frozen=True, slots=True)
class Dimensions:
    """Tamaño de una pieza en LDU: ancho X, fondo Y y altura Z.

    Es la caja que ocupa, no la de su malla: un ladrillo mide 24 de alto, no
    28, porque sus studs sobresalen 4 y se meten dentro de la pieza de
    arriba. Contarlos aquí haría imposible apilar.
    """

    width: int
    depth: int
    height: int

    def __post_init__(self) -> None:
        if not all(
            _is_integer(value)
            for value in (self.width, self.depth, self.height)
        ):
            raise TypeError("Las dimensiones deben ser números enteros.")
        if self.width <= 0 or self.depth <= 0 or self.height <= 0:
            raise InvalidGeometryError(
                "Todas las dimensiones deben ser mayores que cero."
            )

    def rotated(self, orientation: "Orientation") -> "Dimensions":
        """El tamaño de la caja una vez girada.

        Girar permuta las tres medidas; nunca las cambia. Se toma el valor
        absoluto de la matriz porque a una caja le da igual mirar hacia +x o
        hacia -x: ocupa lo mismo.
        """
        medidas = (self.width, self.depth, self.height)
        return Dimensions(
            *(
                sum(abs(fila[k]) * medidas[k] for k in range(3))
                for fila in orientation.filas
            )
        )


@dataclass(frozen=True, slots=True)
class Bounds3D:
    """Caja tridimensional semiabierta: mínimo incluido, máximo excluido."""

    min_x: int
    min_y: int
    min_z: int
    max_x: int
    max_y: int
    max_z: int

    @classmethod
    def from_position_and_dimensions(
        cls,
        position: GridPosition,
        dimensions: Dimensions,
    ) -> "Bounds3D":
        return cls(
            min_x=position.x,
            min_y=position.y,
            min_z=position.z,
            max_x=position.x + dimensions.width,
            max_y=position.y + dimensions.depth,
            max_z=position.z + dimensions.height,
        )

    def intersects(self, other: "Bounds3D") -> bool:
        """Devuelve True solo cuando los volúmenes se solapan."""
        return (
            self.min_x < other.max_x
            and self.max_x > other.min_x
            and self.min_y < other.max_y
            and self.max_y > other.min_y
            and self.min_z < other.max_z
            and self.max_z > other.min_z
        )
