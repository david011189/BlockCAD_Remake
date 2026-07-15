from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .geometry import GridPosition, Rotation
from .model import BlockModel
from .parts import PartCatalog


FORMAT_NAME = "blockcad-remake"
FORMAT_VERSION = 1


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
                "rotation": int(item.rotation),
                "color": item.color,
                "group": item.group,
                "step": item.step,
                "transparent": item.transparent,
            }
            for item in model.instances
        ],
    }


def model_from_dict(
    payload: dict[str, Any],
    *,
    catalog: PartCatalog | None = None,
) -> BlockModel:
    if payload.get("format") != FORMAT_NAME:
        raise ValueError("El archivo no utiliza el formato BlockCAD Remake.")
    if payload.get("version") != FORMAT_VERSION:
        raise ValueError(
            f"Versión de archivo no soportada: {payload.get('version')!r}."
        )

    model = BlockModel(
        catalog=catalog or PartCatalog.with_basic_parts(),
        name=str(payload.get("name", "Modelo sin título")),
    )

    for data in payload.get("parts", []):
        position_data = data["position"]
        model.add(
            part_id=data["part_id"],
            position=GridPosition(
                int(position_data["x"]),
                int(position_data["y"]),
                int(position_data["z"]),
            ),
            rotation=Rotation.normalize(int(data.get("rotation", 0))),
            color=str(data.get("color", "#D62828")),
            group=int(data.get("group", 0)),
            step=int(data.get("step", 0)),
            transparent=bool(data.get("transparent", False)),
            instance_id=str(data["instance_id"]),
            check_collision=True,
        )

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
