from pathlib import Path

from .editor import BlockEditor
from .geometry import GridPosition, Rotation
from .model import BlockModel
from .serialization import load_model


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


def print_history(editor: BlockEditor) -> None:
    print("\nHistorial")
    print(f"  Deshacer: {list(editor.history.undo_labels) or 'vacío'}")
    print(f"  Rehacer:  {list(editor.history.redo_labels) or 'vacío'}")


def main() -> None:
    editor = BlockEditor(name="Casa sencilla")

    with editor.transaction("Construir base"):
        base_left = editor.add("brick_2x4", GridPosition(0, 0, 0), color="#D62828")
        editor.add("brick_2x4", GridPosition(2, 0, 0), color="#F6BD60")

    upper = editor.add(
        "brick_2x2",
        GridPosition(1, 1, 3),
        rotation=Rotation.DEG_90,
        color="#457B9D",
    )
    editor.add("tile_1x2", GridPosition(1, 1, 6), color="#F1FAEE")

    editor.rotate_clockwise(upper.instance_id)
    editor.recolor(base_left.instance_id, "#00AAFF")

    print_model(editor.model)
    print_history(editor)

    print("\nDeshaciendo el recoloreado y la rotación...")
    editor.undo()
    editor.undo()
    print(f"  Color de la base:  {editor.get(base_left.instance_id).color}")
    print(f"  Rotación superior: {int(editor.get(upper.instance_id).rotation)}°")

    print("\nRehaciendo la rotación...")
    editor.redo()
    print(f"  Rotación superior: {int(editor.get(upper.instance_id).rotation)}°")

    print("\nDeshaciendo todo (la base entera es una sola entrada)...")
    while editor.can_undo:
        editor.undo()
    print(f"  Piezas restantes: {len(editor.instances)}")

    print("\nRehaciendo todo...")
    while editor.can_redo:
        editor.redo()
    print(f"  Piezas restantes: {len(editor.instances)}")

    output = Path("modelo_demo.blockcad.json")
    editor.save(output)
    restored = load_model(output)

    print_model(restored)
    print_history(editor)
    print(f"\nArchivo generado: {output.resolve()}")


if __name__ == "__main__":
    main()
