from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import InvalidFormatError
from .geometry import PLACA, STUD, GridPosition, Orientation
from .model import DEFAULT_MODEL_NAME, BlockModel
from .parts import PartCatalog


FORMAT_NAME = "blockcad-remake"

#: Historia del formato, y por qué se siguen leyendo los viejos:
#:
#:   1 - posiciones en studs y placas, giro como un ángulo sobre Z.
#:   2 - posiciones en LDU, giro como un ángulo sobre Z.
#:   3 - orientación como matriz de 3x3: una pieza puede mirar a cualquier
#:       lado, y un ángulo sobre Z ya no basta para decirlo.
#:
#: Un archivo de la 1 o la 2 se traduce al vuelo. Nadie debería perder lo que
#: guardó porque el motor haya crecido.
FORMAT_VERSION = 3

VERSIONES_LEIBLES = (1, 2, 3)


def model_to_dict(model: BlockModel) -> dict[str, Any]:
    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "name": model.name,
        "parts": [
            {
                "instance_id": item.instance_id,
                "part_id": item.part_id,
                "position": {
                    "x": item.position.x,
                    "y": item.position.y,
                    "z": item.position.z,
                },
                # Se guardan las tres filas de la matriz. Es más largo que un
                # ángulo, pero un ángulo no sabe decir "esta viga está de pie".
                "orientation": [list(fila) for fila in item.orientation.filas],
                "color": item.color,
                "group": item.group,
                "step": item.step,
                "transparent": item.transparent,
            }
            for item in model.instances
        ],
    }


def _leer_orientacion(data: dict[str, Any], version: int) -> Orientation:
    """Saca la orientación de una pieza, venga del formato que venga.

    Hasta la versión 2 el giro era un ángulo sobre el eje vertical, que es un
    caso particular de la matriz de ahora.
    """
    if version < 3:
        return Orientation.z(int(data.get("rotation", 0)))

    filas = data.get("orientation")
    if filas is None:
        return Orientation()
    return Orientation(tuple(tuple(int(v) for v in fila) for fila in filas))


def model_from_dict(
    payload: dict[str, Any],
    *,
    catalog: PartCatalog | None = None,
) -> BlockModel:
    if payload.get("format") != FORMAT_NAME:
        raise InvalidFormatError("El archivo no utiliza el formato BlockCAD Remake.")

    version = payload.get("version")
    if version not in VERSIONES_LEIBLES:
        raise InvalidFormatError(f"Versión de archivo no soportada: {version!r}.")

    # La versión 1 medía en studs y placas. Se traduce al vuelo: los archivos
    # que la gente ya tenga guardados deben seguir abriéndose.
    escala = (STUD, STUD, PLACA) if version == 1 else (1, 1, 1)

    model = BlockModel(
        catalog=catalog or PartCatalog.with_basic_parts(),
        name=str(payload.get("name", DEFAULT_MODEL_NAME)),
    )

    for data in payload.get("parts", []):
        # Un archivo con campos ausentes o valores imposibles es un archivo
        # inválido, no un fallo de programación: se traduce al error del
        # dominio antes de tocar el modelo.
        try:
            position_data = data["position"]
            fields = {
                "part_id": data["part_id"],
                "instance_id": str(data["instance_id"]),
                "position": GridPosition(
                    int(position_data["x"]) * escala[0],
                    int(position_data["y"]) * escala[1],
                    int(position_data["z"]) * escala[2],
                ),
                "orientation": _leer_orientacion(data, version),
                "color": str(data.get("color", "#D62828")),
                "group": int(data.get("group", 0)),
                "step": int(data.get("step", 0)),
                "transparent": bool(data.get("transparent", False)),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidFormatError(
                f"El archivo contiene una pieza inválida: {exc}"
            ) from exc

        model.add(check_collision=True, **fields)

    return model


def save_model(model: BlockModel, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(model_to_dict(model), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return destination


def load_model(
    path: str | Path,
    *,
    catalog: PartCatalog | None = None,
) -> BlockModel:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    return model_from_dict(payload, catalog=catalog)
