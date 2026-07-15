from __future__ import annotations

from dataclasses import dataclass, field

from .errors import PartNotFoundError
from .geometry import Dimensions


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

    def __post_init__(self) -> None:
        if not self.part_id.strip():
            raise ValueError("part_id no puede estar vacío.")
        if not self.name.strip():
            raise ValueError("name no puede estar vacío.")
        if not self.default_color.startswith("#") or len(self.default_color) != 7:
            raise ValueError("El color debe utilizar el formato hexadecimal #RRGGBB.")


class PartCatalog:
    """Repositorio de definiciones de piezas."""

    def __init__(self) -> None:
        self._parts: dict[str, PartDefinition] = {}

    def register(self, definition: PartDefinition, *, replace: bool = False) -> None:
        if definition.part_id in self._parts and not replace:
            raise ValueError(f"La pieza {definition.part_id!r} ya está registrada.")
        self._parts[definition.part_id] = definition

    def get(self, part_id: str) -> PartDefinition:
        try:
            return self._parts[part_id]
        except KeyError as exc:
            raise PartNotFoundError(
                f"No existe la definición de pieza {part_id!r}."
            ) from exc

    def contains(self, part_id: str) -> bool:
        return part_id in self._parts

    def all(self) -> tuple[PartDefinition, ...]:
        return tuple(self._parts.values())

    @classmethod
    def with_basic_parts(cls) -> "PartCatalog":
        catalog = cls()
        basic_parts = (
            PartDefinition("brick_1x1", "Ladrillo 1×1", Dimensions(1, 1, 3)),
            PartDefinition("brick_1x2", "Ladrillo 1×2", Dimensions(1, 2, 3)),
            PartDefinition("brick_2x2", "Ladrillo 2×2", Dimensions(2, 2, 3)),
            PartDefinition("brick_2x4", "Ladrillo 2×4", Dimensions(2, 4, 3)),
            PartDefinition(
                "plate_1x2",
                "Placa 1×2",
                Dimensions(1, 2, 1),
                category="plate",
            ),
            PartDefinition(
                "plate_2x4",
                "Placa 2×4",
                Dimensions(2, 4, 1),
                category="plate",
            ),
            PartDefinition(
                "tile_1x2",
                "Baldosa 1×2",
                Dimensions(1, 2, 1),
                category="tile",
                has_top_studs=False,
            ),
        )
        for part in basic_parts:
            catalog.register(part)
        return catalog
