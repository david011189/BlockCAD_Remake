from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from .errors import InvalidGeometryError


def _is_integer(value: object) -> bool:
    # bool es subclase de int, pero True como coordenada acabaría escrito como
    # `true` en el JSON y no como un número.
    return isinstance(value, int) and not isinstance(value, bool)


class Rotation(IntEnum):
    """Rotación alrededor del eje Z."""

    DEG_0 = 0
    DEG_90 = 90
    DEG_180 = 180
    DEG_270 = 270

    @classmethod
    def normalize(cls, value: int) -> "Rotation":
        normalized = value % 360
        try:
            return cls(normalized)
        except ValueError as exc:
            raise InvalidGeometryError(
                "La rotación debe ser múltiplo de 90 grados."
            ) from exc

    def clockwise(self) -> "Rotation":
        return Rotation.normalize(int(self) + 90)


@dataclass(frozen=True, slots=True)
class GridPosition:
    """Posición entera en la cuadrícula de construcción."""

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
    """Dimensiones de una pieza: ancho X, fondo Y y altura Z."""

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

    def rotated(self, rotation: Rotation) -> "Dimensions":
        if rotation in (Rotation.DEG_90, Rotation.DEG_270):
            return Dimensions(self.depth, self.width, self.height)
        return self


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
