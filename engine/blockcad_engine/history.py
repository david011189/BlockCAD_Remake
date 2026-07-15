from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from .commands import Command, MacroCommand
from .errors import TransactionError
from .model import BlockModel


class CommandHistory:
    """Pila de deshacer y rehacer sobre un modelo.

    Los comandos se ejecutan a través del historial para que el registro de
    cambios sea completo. Ejecutar un comando nuevo descarta la pila de
    rehacer, igual que en cualquier editor.
    """

    def __init__(self, model: BlockModel, *, limit: int | None = None) -> None:
        if limit is not None and limit < 1:
            raise ValueError("El límite del historial debe ser mayor que cero.")
        self.model = model
        self.limit = limit
        self._undo_stack: list[Command] = []
        self._redo_stack: list[Command] = []
        self._transactions: list[MacroCommand] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    @property
    def in_transaction(self) -> bool:
        return bool(self._transactions)

    @property
    def undo_labels(self) -> tuple[str, ...]:
        return tuple(command.label for command in self._undo_stack)

    @property
    def redo_labels(self) -> tuple[str, ...]:
        return tuple(command.label for command in self._redo_stack)

    def execute(self, command: Command) -> Command:
        """Ejecuta un comando y lo registra en el historial."""
        command.execute(self.model)

        if self._transactions:
            self._transactions[-1].add(command)
        else:
            self._push(command)

        return command

    def undo(self) -> Command:
        if self._transactions:
            raise TransactionError("No se puede deshacer dentro de una transacción.")
        if not self._undo_stack:
            raise IndexError("No hay nada que deshacer.")

        command = self._undo_stack.pop()
        command.undo(self.model)
        self._redo_stack.append(command)
        return command

    def redo(self) -> Command:
        if self._transactions:
            raise TransactionError("No se puede rehacer dentro de una transacción.")
        if not self._redo_stack:
            raise IndexError("No hay nada que rehacer.")

        command = self._redo_stack.pop()
        command.execute(self.model)
        self._undo_stack.append(command)
        return command

    def clear(self) -> None:
        if self._transactions:
            raise TransactionError(
                "No se puede limpiar el historial dentro de una transacción."
            )
        self._undo_stack.clear()
        self._redo_stack.clear()

    @contextmanager
    def transaction(self, label: str = "Operación agrupada") -> Iterator[MacroCommand]:
        """Agrupa todos los comandos del bloque en una única unidad de deshacer.

        Si el bloque lanza una excepción, los comandos ya ejecutados se
        deshacen en orden inverso y el historial queda intacto.
        """
        macro = MacroCommand(label)
        self._transactions.append(macro)

        try:
            yield macro
        except BaseException:
            self._transactions.pop()
            for command in reversed(macro.commands):
                command.undo(self.model)
            raise

        self._transactions.pop()

        if not macro.commands:
            return

        # Los comandos ya se ejecutaron uno a uno; el macro solo se registra.
        if self._transactions:
            self._transactions[-1].add(macro)
        else:
            self._push(macro)

    def _push(self, command: Command) -> None:
        self._undo_stack.append(command)
        self._redo_stack.clear()
        if self.limit is not None and len(self._undo_stack) > self.limit:
            del self._undo_stack[: len(self._undo_stack) - self.limit]
