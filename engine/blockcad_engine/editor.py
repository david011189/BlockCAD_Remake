from __future__ import annotations

from pathlib import Path
from typing import Iterator

from .commands import (
    AddPartCommand,
    Command,
    MacroCommand,
    MovePartCommand,
    RecolorPartCommand,
    RemovePartCommand,
    RotateClockwiseCommand,
    SetRotationCommand,
    TranslatePartCommand,
)
from .geometry import GridPosition, Rotation
from .history import CommandHistory
from .model import BlockModel, PlacedPart
from .parts import PartCatalog
from .serialization import load_model, save_model


class BlockEditor:
    """Punto de entrada para editar un modelo con deshacer y rehacer.

    Toda operación pasa por un comando registrado en el historial. El modelo
    subyacente sigue siendo accesible en modo lectura y conserva su propia API
    para pruebas o para scripts que no necesiten historial.
    """

    def __init__(
        self,
        model: BlockModel | None = None,
        *,
        catalog: PartCatalog | None = None,
        name: str = "Modelo sin título",
        history_limit: int | None = None,
    ) -> None:
        self.model = model or BlockModel(catalog=catalog, name=name)
        self.history = CommandHistory(self.model, limit=history_limit)

    @classmethod
    def open(
        cls,
        path: str | Path,
        *,
        catalog: PartCatalog | None = None,
        history_limit: int | None = None,
    ) -> "BlockEditor":
        model = load_model(path, catalog=catalog)
        return cls(model, history_limit=history_limit)

    @property
    def name(self) -> str:
        return self.model.name

    @property
    def instances(self) -> tuple[PlacedPart, ...]:
        return self.model.instances

    @property
    def catalog(self) -> PartCatalog:
        return self.model.catalog

    def get(self, instance_id: str) -> PlacedPart:
        return self.model.get(instance_id)

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
    ) -> PlacedPart:
        command = AddPartCommand(
            part_id,
            position,
            rotation=rotation,
            color=color,
            group=group,
            step=step,
            transparent=transparent,
            instance_id=instance_id,
        )
        self.history.execute(command)
        return command.instance

    def remove(self, instance_id: str) -> None:
        self.history.execute(RemovePartCommand(instance_id))

    def move(self, instance_id: str, position: GridPosition) -> PlacedPart:
        self.history.execute(MovePartCommand(instance_id, position))
        return self.model.get(instance_id)

    def translate(
        self,
        instance_id: str,
        dx: int = 0,
        dy: int = 0,
        dz: int = 0,
    ) -> PlacedPart:
        self.history.execute(TranslatePartCommand(instance_id, dx, dy, dz))
        return self.model.get(instance_id)

    def rotate_clockwise(self, instance_id: str) -> PlacedPart:
        self.history.execute(RotateClockwiseCommand(instance_id))
        return self.model.get(instance_id)

    def set_rotation(self, instance_id: str, rotation: Rotation | int) -> PlacedPart:
        self.history.execute(SetRotationCommand(instance_id, rotation))
        return self.model.get(instance_id)

    def recolor(self, instance_id: str, color: str) -> PlacedPart:
        self.history.execute(RecolorPartCommand(instance_id, color))
        return self.model.get(instance_id)

    def execute(self, command: Command) -> Command:
        """Ejecuta un comando personalizado a través del historial."""
        return self.history.execute(command)

    def transaction(self, label: str = "Operación agrupada") -> Iterator[MacroCommand]:
        return self.history.transaction(label)

    @property
    def can_undo(self) -> bool:
        return self.history.can_undo

    @property
    def can_redo(self) -> bool:
        return self.history.can_redo

    def undo(self) -> Command:
        return self.history.undo()

    def redo(self) -> Command:
        return self.history.redo()

    def save(self, path: str | Path) -> Path:
        return save_model(self.model, path)
