"""Editor web y visor 3D para el lenguaje BlockCAD.

Este paquete es la capa de presentación: depende del motor, pero el motor no
depende de él. Se ejecuta con `python -m blockcad_web`.
"""

from .server import serve

__all__ = ["serve"]
