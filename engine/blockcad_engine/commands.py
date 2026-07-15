from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import uuid4

from .errors import CommandError
from .geometry import GridPosition, Rotation
from .model import BlockModel, PlacedPart


class Command(ABC):
    """Operación reversible sobre un modelo.

    Un comando se construye con la intención de la operación. Toda la
    información necesaria para deshacer se captura durante `execute`, de modo
    que rehacer y deshacer reproduzcan siempre el mismo resultado.
    """

    label: str = "Operación"

    @abstractmethod
    def execute(self, model: BlockModel) -> None:
        """Aplica la operación al modelo."""

    @abstractmethod
    def undo(self, model: BlockModel) -> None:
        """Devuelve el modelo al estado anterior a `execute`."""

    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self.label}>"


class AddPartCommand(Command):
    """Añade una pieza nueva al modelo."""

    def __init__(
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
    ) -> None:
        self.part_id = part_id
        self.position = position
        self.rotation = rotation
        self.color = color
        self.group = group
        self.step = step
        self.transparent = transparent
        # El identificador se fija al construir el comando: rehacer debe
        # recrear la misma instancia, no una nueva.
        self.instance_id = instance_id or str(uuid4())
        self.label = f"Añadir {part_id}"
        self._instance: PlacedPart | None = None

    @property
    def instance(self) -> PlacedPart:
        if self._instance is None:
            raise CommandError("El comando todavía no se ha ejecutado.")
        return self._instance

    def execute(self, model: BlockModel) -> None:
        if self._instance is None:
            definition = model.catalog.get(self.part_id)
            self._instance = PlacedPart.create(
                part_id=self.part_id,
                position=self.position,
                rotation=self.rotation,
                color=self.color or definition.default_color,
                group=self.group,
                step=self.step,
                transparent=self.transparent,
                instance_id=self.instance_id,
            )
        model.add_instance(self._instance)

    def undo(self, model: BlockModel) -> None:
        model.remove(self.instance_id)


class RemovePartCommand(Command):
    """Elimina una pieza existente."""

    def __init__(self, instance_id: str) -> None:
        self.instance_id = instance_id
        self.label = "Eliminar pieza"
        self._removed: PlacedPart | None = None
        self._index: int | None = None

    def execute(self, model: BlockModel) -> None:
        self._index = model.index_of(self.instance_id)
        self._removed = model.remove(self.instance_id)
        self.label = f"Eliminar {self._removed.part_id}"

    def undo(self, model: BlockModel) -> None:
        if self._removed is None or self._index is None:
            raise CommandError("El comando todavía no se ha ejecutado.")
        model.insert_instance(self._removed, index=self._index)


class MovePartCommand(Command):
    """Mueve una pieza a una posición absoluta."""

    def __init__(self, instance_id: str, position: GridPosition) -> None:
        self.instance_id = instance_id
        self.position = position
        self.label = "Mover pieza"
        self._previous: GridPosition | None = None

    def execute(self, model: BlockModel) -> None:
        self._previous = model.get(self.instance_id).position
        model.move(self.instance_id, self.position)

    def undo(self, model: BlockModel) -> None:
        if self._previous is None:
            raise CommandError("El comando todavía no se ha ejecutado.")
        model.move(self.instance_id, self._previous)


class TranslatePartCommand(MovePartCommand):
    """Mueve una pieza de forma relativa."""

    def __init__(
        self,
        instance_id: str,
        dx: int = 0,
        dy: int = 0,
        dz: int = 0,
    ) -> None:
        self.instance_id = instance_id
        self.delta = (dx, dy, dz)
        self.label = f"Trasladar ({dx}, {dy}, {dz})"
        self._previous: GridPosition | None = None

    def execute(self, model: BlockModel) -> None:
        current = model.get(self.instance_id).position
        self._previous = current
        self.position = current.translated(*self.delta)
        model.move(self.instance_id, self.position)


class SetRotationCommand(Command):
    """Fija la rotación absoluta de una pieza."""

    def __init__(self, instance_id: str, rotation: Rotation | int) -> None:
        self.instance_id = instance_id
        self.rotation = Rotation.normalize(int(rotation))
        self.label = f"Rotar a {int(self.rotation)}°"
        self._previous: Rotation | None = None

    def execute(self, model: BlockModel) -> None:
        self._previous = model.get(self.instance_id).rotation
        model.set_rotation(self.instance_id, self.rotation)

    def undo(self, model: BlockModel) -> None:
        if self._previous is None:
            raise CommandError("El comando todavía no se ha ejecutado.")
        model.set_rotation(self.instance_id, self._previous)


class RotateClockwiseCommand(SetRotationCommand):
    """Rota una pieza 90 grados en sentido horario."""

    def __init__(self, instance_id: str) -> None:
        self.instance_id = instance_id
        self.label = "Rotar 90° horario"
        self._previous: Rotation | None = None

    def execute(self, model: BlockModel) -> None:
        current = model.get(self.instance_id).rotation
        self._previous = current
        self.rotation = current.clockwise()
        model.set_rotation(self.instance_id, self.rotation)


class RecolorPartCommand(Command):
    """Cambia el color de una pieza."""

    def __init__(self, instance_id: str, color: str) -> None:
        self.instance_id = instance_id
        self.color = color
        self.label = f"Recolorear a {color}"
        self._previous: str | None = None

    def execute(self, model: BlockModel) -> None:
        self._previous = model.get(self.instance_id).color
        model.recolor(self.instance_id, self.color)

    def undo(self, model: BlockModel) -> None:
        if self._previous is None:
            raise CommandError("El comando todavía no se ha ejecutado.")
        model.recolor(self.instance_id, self._previous)


class MacroCommand(Command):
    """Agrupa varios comandos en una única unidad de deshacer."""

    def __init__(self, label: str, commands: list[Command] | None = None) -> None:
        self.label = label
        self.commands: list[Command] = list(commands or [])

    def add(self, command: Command) -> None:
        self.commands.append(command)

    def __len__(self) -> int:
        return len(self.commands)

    def execute(self, model: BlockModel) -> None:
        executed: list[Command] = []
        try:
            for command in self.commands:
                command.execute(model)
                executed.append(command)
        except Exception:
            for command in reversed(executed):
                command.undo(model)
            raise

    def undo(self, model: BlockModel) -> None:
        for command in reversed(self.commands):
            command.undo(model)
