from __future__ import annotations

from dataclasses import dataclass, field

from .errors import (
    DuplicatePartError,
    InvalidColorError,
    InvalidPartError,
    PartNotFoundError,
)
from .geometry import LADRILLO, PLACA, STUD, Dimensions

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def validate_color(color: str) -> str:
    """Comprueba el formato #RRGGBB y devuelve el color en mayúsculas."""
    if (
        not isinstance(color, str)
        or len(color) != 7
        or color[0] != "#"
        or not all(digit in _HEX_DIGITS for digit in color[1:])
    ):
        raise InvalidColorError(
            f"El color {color!r} debe utilizar el formato hexadecimal #RRGGBB."
        )
    return color.upper()


@dataclass(frozen=True, slots=True)
class PartDefinition:
    """Definición reutilizable de una pieza del catálogo."""

    part_id: str
    name: str
    dimensions: Dimensions
    category: str = "brick"
    default_color: str = "#D62828"
    has_top_studs: bool = True
    metadata: dict[str, str] = field(default_factory=dict)
    #: Otros nombres por los que responde. Una pieza real se llama por su
    #: número de molde —3001—, pero nadie quiere escribir eso: el alias
    #: `brick_2x4` deja que el lenguaje siga diciendo "ladrillo 2x4".
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.part_id.strip():
            raise InvalidPartError("part_id no puede estar vacío.")
        if not self.name.strip():
            raise InvalidPartError("name no puede estar vacío.")
        validate_color(self.default_color)


class PartCatalog:
    """Repositorio de definiciones de piezas."""

    def __init__(self) -> None:
        self._parts: dict[str, PartDefinition] = {}
        self._aliases: dict[str, str] = {}

    def register(self, definition: PartDefinition, *, replace: bool = False) -> None:
        if definition.part_id in self._parts and not replace:
            raise DuplicatePartError(
                f"La pieza {definition.part_id!r} ya está registrada."
            )
        self._parts[definition.part_id] = definition

        for alias in definition.aliases:
            anterior = self._aliases.get(alias)
            if anterior is not None and anterior != definition.part_id and not replace:
                raise DuplicatePartError(
                    f"El alias {alias!r} ya lo usa la pieza {anterior!r}."
                )
            self._aliases[alias] = definition.part_id

    def get(self, part_id: str) -> PartDefinition:
        real = self._aliases.get(part_id, part_id)
        try:
            return self._parts[real]
        except KeyError as exc:
            raise PartNotFoundError(
                f"No existe la definición de pieza {part_id!r}."
            ) from exc

    def contains(self, part_id: str) -> bool:
        return part_id in self._parts or part_id in self._aliases

    def all(self) -> tuple[PartDefinition, ...]:
        return tuple(self._parts.values())

    @classmethod
    def with_basic_parts(cls) -> "PartCatalog":
        """Catálogo mínimo, medido en LDU.

        Un ladrillo de N×M studs mide `N*STUD` de ancho por `M*STUD` de fondo
        y `LADRILLO` de alto.
        """
        catalog = cls()
        basic_parts = (
            PartDefinition(
                "brick_1x1", "Ladrillo 1×1", Dimensions(1 * STUD, 1 * STUD, LADRILLO)
            ),
            PartDefinition(
                "brick_1x2", "Ladrillo 1×2", Dimensions(1 * STUD, 2 * STUD, LADRILLO)
            ),
            PartDefinition(
                "brick_2x2", "Ladrillo 2×2", Dimensions(2 * STUD, 2 * STUD, LADRILLO)
            ),
            PartDefinition(
                "brick_2x4", "Ladrillo 2×4", Dimensions(2 * STUD, 4 * STUD, LADRILLO)
            ),
            PartDefinition(
                "plate_1x2",
                "Placa 1×2",
                Dimensions(1 * STUD, 2 * STUD, PLACA),
                category="plate",
            ),
            PartDefinition(
                "plate_2x4",
                "Placa 2×4",
                Dimensions(2 * STUD, 4 * STUD, PLACA),
                category="plate",
            ),
            PartDefinition(
                "tile_1x2",
                "Baldosa 1×2",
                Dimensions(1 * STUD, 2 * STUD, PLACA),
                category="tile",
                has_top_studs=False,
            ),
        )
        for part in basic_parts:
            catalog.register(part)
        return catalog
