"""Motor principal de BlockCAD Remake."""

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
from .editor import BlockEditor
from .errors import (
    BlockCADError,
    CollisionError,
    CommandError,
    DuplicateInstanceError,
    DuplicatePartError,
    InstanceNotFoundError,
    InvalidColorError,
    InvalidFormatError,
    InvalidGeometryError,
    InvalidPartError,
    InvalidPlacementError,
    PartNotFoundError,
    TransactionError,
)
from .geometry import Bounds3D, Dimensions, GridPosition, Rotation
from .history import CommandHistory
from .model import BlockModel, PlacedPart
from .parts import PartCatalog, PartDefinition
from .serialization import load_model, save_model

__all__ = [
    "BlockCADError",
    "CollisionError",
    "CommandError",
    "DuplicateInstanceError",
    "DuplicatePartError",
    "InstanceNotFoundError",
    "InvalidColorError",
    "InvalidFormatError",
    "InvalidGeometryError",
    "InvalidPartError",
    "InvalidPlacementError",
    "PartNotFoundError",
    "TransactionError",
    "Bounds3D",
    "Dimensions",
    "GridPosition",
    "Rotation",
    "BlockModel",
    "PlacedPart",
    "PartCatalog",
    "PartDefinition",
    "load_model",
    "save_model",
    "Command",
    "AddPartCommand",
    "RemovePartCommand",
    "MovePartCommand",
    "TranslatePartCommand",
    "SetRotationCommand",
    "RotateClockwiseCommand",
    "RecolorPartCommand",
    "MacroCommand",
    "CommandHistory",
    "BlockEditor",
]
