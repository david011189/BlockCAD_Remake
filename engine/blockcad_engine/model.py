from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import uuid4

from .errors import (
    CollisionError,
    DuplicateInstanceError,
    InstanceNotFoundError,
)
from .geometry import Bounds3D, GridPosition, Orientation
from .parts import PartCatalog, PartDefinition, validate_color

#: Nombre de un modelo al que nadie ha puesto uno.
DEFAULT_MODEL_NAME = "Modelo sin título"


@dataclass(frozen=True, slots=True)
class PlacedPart:
    """Instancia concreta colocada en el modelo."""

    instance_id: str
    part_id: str
    position: GridPosition
    orientation: Orientation = Orientation()
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
        orientation: Orientation = Orientation(),
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
            orientation=orientation,
            color=color,
            group=group,
            step=step,
            transparent=transparent,
        )

    def bounds(self, definition: PartDefinition) -> Bounds3D:
        dimensions = definition.dimensions.rotated(self.orientation)
        return Bounds3D.from_position_and_dimensions(self.position, dimensions)

    def world_connections(
        self, definition: PartDefinition
    ) -> tuple[tuple[str, tuple[int, int, int]], ...]:
        """Dónde caen sus puntos de conexión, ya girados y colocados.

        Girar mueve la caja fuera de su sitio: un ladrillo de 2x4 girado un
        cuarto de vuelta ocupa donde antes no ocupaba. Como el motor guarda la
        esquina mínima DESPUÉS de girar, hay que reanclar la pieza —y con ella
        sus puntos— para que esa esquina vuelva al origen.
        """
        if not definition.connections:
            return ()

        medidas = (
            definition.dimensions.width,
            definition.dimensions.depth,
            definition.dimensions.height,
        )
        # Al girar, cada eje recibe una medida distinta y puede acabar en
        # negativo. Lo que sobresale por debajo de cero es lo que hay que
        # devolver al sitio.
        desplazamiento = tuple(
            -sum(min(0, fila[k] * medidas[k]) for k in range(3))
            for fila in self.orientation.filas
        )

        puntos = []
        for conexion in definition.connections:
            girado = self.orientation.apply(*conexion.punto)
            puntos.append((
                conexion.tipo,
                (
                    self.position.x + girado[0] + desplazamiento[0],
                    self.position.y + girado[1] + desplazamiento[1],
                    self.position.z + girado[2] + desplazamiento[2],
                ),
            ))
        return tuple(puntos)


class BlockModel:
    """Documento principal que contiene todas las piezas colocadas."""

    def __init__(
        self,
        catalog: PartCatalog | None = None,
        *,
        name: str = DEFAULT_MODEL_NAME,
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
        orientation: Orientation = Orientation(),
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
            orientation=orientation,
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

    def set_orientation(
        self,
        instance_id: str,
        orientation: Orientation,
        *,
        check_collision: bool = True,
    ) -> PlacedPart:
        """Fija la orientación absoluta de una pieza."""
        current = self.get(instance_id)
        candidate = replace(current, orientation=orientation)
        self._validate_instance(
            candidate,
            ignore_instance_id=instance_id,
            check_collision=check_collision,
        )
        self._instances[instance_id] = candidate
        return candidate

    def rotate(
        self,
        instance_id: str,
        eje: str,
        grados: int,
        *,
        check_collision: bool = True,
    ) -> PlacedPart:
        """Gira una pieza sobre un eje, encadenando el giro al que ya tenía."""
        current = self.get(instance_id)
        return self.set_orientation(
            instance_id,
            Orientation.around(eje, grados).then(current.orientation),
            check_collision=check_collision,
        )

    def rotate_clockwise(
        self,
        instance_id: str,
        *,
        check_collision: bool = True,
    ) -> PlacedPart:
        """Gira 90 grados sobre el eje vertical: el giro de toda la vida."""
        return self.rotate(instance_id, "z", 90, check_collision=check_collision)

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

    def connected_to(self, instance_id: str) -> tuple[PlacedPart, ...]:
        """Piezas unidas a esta por compartir un punto de conexión.

        Un agujero aparece en las dos caras de la pieza, así que dos vigas
        pegadas comparten los puntos de la cara que se tocan. Es lo que
        permite saber que están unidas sin modelar el pin.
        """
        pieza = self.get(instance_id)
        mios = {
            punto
            for _, punto in pieza.world_connections(self.catalog.get(pieza.part_id))
        }
        if not mios:
            return ()

        unidas = []
        for otra in self._instances.values():
            if otra.instance_id == instance_id:
                continue
            suyos = {
                punto
                for _, punto in otra.world_connections(self.catalog.get(otra.part_id))
            }
            if mios & suyos:
                unidas.append(otra)
        return tuple(unidas)

    def resting_on(self, instance_id: str) -> tuple[PlacedPart, ...]:
        """Piezas sobre las que esta se apoya: las que tiene justo debajo.

        Hace falta además de `connected_to` porque un ladrillo no tiene puntos
        en su base: sus studs están arriba, y el de encima no aporta nada por
        abajo. Entre ladrillos, lo que hay es apoyo, no puntos compartidos.
        """
        pieza = self.get(instance_id)
        caja = pieza.bounds(self.catalog.get(pieza.part_id))

        debajo = []
        for otra in self._instances.values():
            if otra.instance_id == instance_id:
                continue
            suya = otra.bounds(self.catalog.get(otra.part_id))
            if suya.max_z != caja.min_z:
                continue
            # Que se toquen de canto no sostiene nada: las plantas tienen que
            # solaparse de verdad.
            if (
                suya.min_x < caja.max_x
                and suya.max_x > caja.min_x
                and suya.min_y < caja.max_y
                and suya.max_y > caja.min_y
            ):
                debajo.append(otra)
        return tuple(debajo)

    def is_supported(self, instance_id: str) -> bool:
        """Si la pieza se apoya en el suelo, en otra pieza, o va unida a alguna."""
        pieza = self.get(instance_id)
        if pieza.position.z == 0:
            return True
        return bool(self.resting_on(instance_id)) or bool(
            self.connected_to(instance_id)
        )

    def floating(self) -> tuple[PlacedPart, ...]:
        """Las piezas que se quedan en el aire.

        No es un error: el BlockCAD original permitía piezas flotantes y aquí
        también. Es un aviso, para que quien construye sepa lo que hay.
        """
        return tuple(
            pieza
            for pieza in self._instances.values()
            if not self.is_supported(pieza.instance_id)
        )

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
