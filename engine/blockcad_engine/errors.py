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
