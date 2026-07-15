from pathlib import Path

from .geometry import GridPosition, Rotation
from .model import BlockModel
from .serialization import load_model, save_model


def print_model(model: BlockModel) -> None:
    print(f"\nModelo: {model.name}")
    print(f"Número de piezas: {len(model.instances)}")
    for item in model.instances:
        definition = model.catalog.get(item.part_id)
        print(
            f"- {definition.name:<16} "
            f"pos=({item.position.x}, {item.position.y}, {item.position.z}) "
            f"rot={int(item.rotation):>3}° color={item.color}"
        )


def main() -> None:
    model = BlockModel(name="Casa sencilla")

    base_left = model.add(
        "brick_2x4",
        GridPosition(0, 0, 0),
        color="#D62828",
    )
    model.add(
        "brick_2x4",
        GridPosition(2, 0, 0),
        color="#F6BD60",
    )
    upper = model.add(
        "brick_2x2",
        GridPosition(1, 1, 3),
        rotation=Rotation.DEG_90,
        color="#457B9D",
    )
    model.add(
        "tile_1x2",
        GridPosition(1, 1, 6),
        color="#F1FAEE",
    )

    model.translate(base_left.instance_id, dx=0, dy=1)
    model.translate(base_left.instance_id, dx=0, dy=-1)
    model.rotate_clockwise(upper.instance_id)

    output = Path("modelo_demo.blockcad.json")
    save_model(model, output)
    restored = load_model(output)

    print_model(restored)
    print(f"\nArchivo generado: {output.resolve()}")


if __name__ == "__main__":
    main()
