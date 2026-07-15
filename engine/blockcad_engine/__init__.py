"""Motor principal de BlockCAD Remake."""

from .errors import (
    BlockCADError,
    CollisionError,
    DuplicateInstanceError,
    InvalidPlacementError,
    PartNotFoundError,
)
from .geometry import Bounds3D, Dimensions, GridPosition, Rotation
from .model import BlockModel, PlacedPart
from .parts import PartCatalog, PartDefinition
from .serialization import load_model, save_model

__all__ = [
    "BlockCADError",
    "CollisionError",
    "DuplicateInstanceError",
    "InvalidPlacementError",
    "PartNotFoundError",
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
]
