"""Jerarquía de excepciones del motor.

Todo error del dominio deriva de `BlockCADError`, de modo que una interfaz
pueda capturar cualquier fallo del motor con un único `except`.

Los errores que históricamente eran `ValueError` o `KeyError` heredan también
de esas clases. Así el código que ya los capturaba sigue funcionando y, al
mismo tiempo, quedan dentro de la jerarquía del motor.
"""


class BlockCADError(Exception):
    """Error base del motor."""


class PartNotFoundError(BlockCADError):
    """La definición de pieza solicitada no existe."""


class DuplicateInstanceError(BlockCADError):
    """Ya existe una instancia con el mismo identificador."""


class InvalidPlacementError(BlockCADError):
    """La posición o transformación solicitada no es válida."""


class CollisionError(InvalidPlacementError):
    """La pieza ocuparía el mismo volumen que otra pieza."""


class CommandError(BlockCADError):
    """Un comando se ejecutó o se deshizo fuera de orden."""


class TransactionError(BlockCADError):
    """Una transacción se utilizó de forma incorrecta."""


class InstanceNotFoundError(BlockCADError, KeyError):
    """No existe la instancia solicitada."""

    def __str__(self) -> str:
        # KeyError añade comillas al mensaje; el texto debe llegar limpio a la
        # interfaz.
        return str(self.args[0]) if self.args else ""


class InvalidGeometryError(BlockCADError, ValueError):
    """Una coordenada, dimensión o rotación no es válida."""


class InvalidColorError(BlockCADError, ValueError):
    """El color no utiliza el formato #RRGGBB."""


class InvalidPartError(BlockCADError, ValueError):
    """La definición de pieza está incompleta o es incoherente."""


class DuplicatePartError(BlockCADError, ValueError):
    """Ya existe una definición de pieza con el mismo identificador."""


class InvalidFormatError(BlockCADError, ValueError):
    """El archivo no es un modelo BlockCAD válido."""


class DslError(BlockCADError, ValueError):
    """El código BlockCAD tiene un fallo, indicando la línea."""

    def __init__(self, line: int, message: str) -> None:
        self.line = line
        self.message = message
        super().__init__(f"Línea {line}: {message}")
