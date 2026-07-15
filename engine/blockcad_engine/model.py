from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import uuid4

from .errors import (
    CollisionError,
    DuplicateInstanceError,
    InstanceNotFoundError,
)
from .geometry import Bounds3D, GridPosition, Rotation
from .parts import PartCatalog, PartDefinition, validate_color


@dataclass(frozen=True, slots=True)
class PlacedPart:
    """Instancia concreta colocada en el modelo."""

    instance_id: str
    part_id: str
    position: GridPosition
    rotation: Rotation = Rotation.DEG_0
    color: str = "#D62828"
    group: int = 0
    step: int = 0
    transparent: bool = False

    @classmethod
    def create(
        cls,
        part_id: str,
        position: GridPosition,
        *,
        rotation: Rotation = Rotation.DEG_0,
        color: str = "#D62828",
        group: int = 0,
        step: int = 0,
        transparent: bool = False,
        instance_id: str | None = None,
    ) -> "PlacedPart":
        return cls(
            instance_id=instance_id or str(uuid4()),
            part_id=part_id,
            position=position,
            rotation=rotation,
            color=color,
            group=group,
            step=step,
            transparent=transparent,
        )

    def bounds(self, definition: PartDefinition) -> Bounds3D:
        dimensions = definition.dimensions.rotated(self.rotation)
        return Bounds3D.from_position_and_dimensions(self.position, dimensions)


class BlockModel:
    """Documento principal que contiene todas las piezas colocadas."""

    def __init__(
        self,
        catalog: PartCatalog | None = None,
        *,
        name: str = "Modelo sin título",
    ) -> None:
        self.catalog = catalog or PartCatalog.with_basic_parts()
        self.name = name
        self._instances: dict[str, PlacedPart] = {}

    @property
    def instances(self) -> tuple[PlacedPart, ...]:
        return tuple(self._instances.values())

    def get(self, instance_id: str) -> PlacedPart:
        try:
            return self._instances[instance_id]
        except KeyError as exc:
            raise InstanceNotFoundError(
                f"No existe la instancia {instance_id!r}."
            ) from exc

    def index_of(self, instance_id: str) -> int:
        """Posición de la instancia dentro del orden de inserción."""
        for index, key in enumerate(self._instances):
            if key == instance_id:
                return index
        raise InstanceNotFoundError(f"No existe la instancia {instance_id!r}.")

    def add(
        self,
        part_id: str,
        position: GridPosition,
        *,
        rotation: Rotation = Rotation.DEG_0,
        color: str | None = None,
        group: int = 0,
        step: int = 0,
        transparent: bool = False,
        instance_id: str | None = None,
        check_collision: bool = True,
    ) -> PlacedPart:
        definition = self.catalog.get(part_id)
        candidate = PlacedPart.create(
            part_id=part_id,
            position=position,
            rotation=rotation,
            color=color or definition.default_color,
            group=group,
            step=step,
            transparent=transparent,
            instance_id=instance_id,
        )
        self.add_instance(candidate, check_collision=check_collision)
        return candidate

    def add_instance(
        self,
        instance: PlacedPart,
        *,
        check_collision: bool = True,
    ) -> None:
        self.insert_instance(instance, check_collision=check_collision)

    def insert_instance(
        self,
        instance: PlacedPart,
        *,
        index: int | None = None,
        check_collision: bool = True,
    ) -> None:
        """Añade una instancia y, opcionalmente, la sitúa en un índice concreto.

        El índice permite que deshacer una eliminación devuelva la pieza a su
        lugar original dentro del orden de inserción.
        """
        if instance.instance_id in self._instances:
            raise DuplicateInstanceError(
                f"La instancia {instance.instance_id!r} ya existe."
            )

        self.catalog.get(instance.part_id)
        self._validate_instance(instance, check_collision=check_collision)

        if index is None or index >= len(self._instances):
            self._instances[instance.instance_id] = instance
            return

        if index < 0:
            raise ValueError("El índice no puede ser negativo.")

        items = list(self._instances.items())
        items.insert(index, (instance.instance_id, instance))
        self._instances = dict(items)

    def remove(self, instance_id: str) -> PlacedPart:
        try:
            return self._instances.pop(instance_id)
        except KeyError as exc:
            raise InstanceNotFoundError(
                f"No existe la instancia {instance_id!r}."
            ) from exc

    def move(
        self,
        instance_id: str,
        new_position: GridPosition,
        *,
        check_collision: bool = True,
    ) -> PlacedPart:
        current = self.get(instance_id)
        candidate = replace(current, position=new_position)
        self._validate_instance(
            candidate,
            ignore_instance_id=instance_id,
            check_collision=check_collision,
        )
        self._instances[instance_id] = candidate
        return candidate

    def translate(
        self,
        instance_id: str,
        dx: int = 0,
        dy: int = 0,
        dz: int = 0,
        *,
        check_collision: bool = True,
    ) -> PlacedPart:
        current = self.get(instance_id)
        return self.move(
            instance_id,
            current.position.translated(dx, dy, dz),
            check_collision=check_collision,
        )

    def set_rotation(
        self,
        instance_id: str,
        rotation: Rotation | int,
        *,
        check_collision: bool = True,
    ) -> PlacedPart:
        current = self.get(instance_id)
        candidate = replace(current, rotation=Rotation.normalize(int(rotation)))
        self._validate_instance(
            candidate,
            ignore_instance_id=instance_id,
            check_collision=check_collision,
        )
        self._instances[instance_id] = candidate
        return candidate

    def rotate_clockwise(
        self,
        instance_id: str,
        *,
        check_collision: bool = True,
    ) -> PlacedPart:
        current = self.get(instance_id)
        return self.set_rotation(
            instance_id,
            current.rotation.clockwise(),
            check_collision=check_collision,
        )

    def recolor(self, instance_id: str, color: str) -> PlacedPart:
        normalized = validate_color(color)
        current = self.get(instance_id)
        updated = replace(current, color=normalized)
        self._instances[instance_id] = updated
        return updated

    def collisions_for(
        self,
        candidate: PlacedPart,
        *,
        ignore_instance_id: str | None = None,
    ) -> tuple[PlacedPart, ...]:
        definition = self.catalog.get(candidate.part_id)
        candidate_bounds = candidate.bounds(definition)
        collisions: list[PlacedPart] = []

        for existing in self._instances.values():
            if existing.instance_id == ignore_instance_id:
                continue
            existing_definition = self.catalog.get(existing.part_id)
            if candidate_bounds.intersects(existing.bounds(existing_definition)):
                collisions.append(existing)

        return tuple(collisions)

    def _validate_instance(
        self,
        candidate: PlacedPart,
        *,
        ignore_instance_id: str | None = None,
        check_collision: bool,
    ) -> None:
        # `GridPosition` ya garantiza z >= 0, así que aquí no hace falta
        # volver a comprobarlo.
        if check_collision:
            collisions = self.collisions_for(
                candidate,
                ignore_instance_id=ignore_instance_id,
            )
            if collisions:
                ids = ", ".join(item.instance_id for item in collisions)
                raise CollisionError(
                    f"La pieza colisiona con las instancias: {ids}."
                )
