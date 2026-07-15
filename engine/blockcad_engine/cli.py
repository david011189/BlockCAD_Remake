"""Demostración por consola: construye, deshace, guarda y vuelve a leer.

Es el "hola mundo" del motor y lo primero que ejecuta quien llega al
proyecto. Las medidas van con las constantes —`2 * STUD`, `LADRILLO`— y no
con números crudos: `GridPosition(0, 0, 24)` no dice nada, pero
`GridPosition(0, 0, LADRILLO)` dice «encima del ladrillo».
"""

from pathlib import Path

from .editor import BlockEditor
from .geometry import LADRILLO, STUD, GridPosition, Orientation
from .model import BlockModel
from .serialization import load_model


def describir_caja(model: BlockModel, item) -> str:
    """El bulto de una pieza ya girada, que es donde se nota la orientación."""
    definicion = model.catalog.get(item.part_id)
    caja = definicion.dimensions.rotated(item.orientation)
    return f"{caja.width}x{caja.depth}x{caja.height}"


def print_model(model: BlockModel) -> None:
    print(f"\nModelo: {model.name}")
    print(f"Número de piezas: {len(model.instances)}")
    for item in model.instances:
        definition = model.catalog.get(item.part_id)
        print(
            f"- {definition.name:<16} "
            f"pos=({item.position.x:>3}, {item.position.y:>3}, {item.position.z:>3}) "
            f"caja={describir_caja(model, item):<10} "
            f"color={item.color}"
        )
    print("  (las medidas van en LDU: un stud son 20 y un ladrillo 24 de alto)")


def print_history(editor: BlockEditor) -> None:
    print("\nHistorial")
    print(f"  Deshacer: {list(editor.history.undo_labels) or 'vacío'}")
    print(f"  Rehacer:  {list(editor.history.redo_labels) or 'vacío'}")


def construir() -> BlockEditor:
    editor = BlockEditor(name="Casa sencilla")

    # Las dos mitades de la base se tocan sin chocar: un ladrillo 2x4 ocupa
    # 2 studs de ancho, así que el segundo empieza justo donde acaba el
    # primero.
    with editor.transaction("Construir base"):
        editor.add("brick_2x4", GridPosition(0, 0, 0), color="#D62828")
        editor.add("brick_2x4", GridPosition(2 * STUD, 0, 0), color="#F6BD60")

    # Cruzada encima, girada un cuarto de vuelta.
    editor.add(
        "brick_2x4",
        GridPosition(0, 0, LADRILLO),
        orientation=Orientation.z(90),
        color="#457B9D",
    )
    editor.add("tile_1x2", GridPosition(0, 0, 2 * LADRILLO), color="#F1FAEE")
    return editor


def main() -> None:
    editor = construir()
    base = editor.instances[0]
    cruzada = editor.instances[2]

    editor.rotate_clockwise(cruzada.instance_id)
    editor.recolor(base.instance_id, "#00AAFF")

    print_model(editor.model)
    print_history(editor)

    print("\nDeshaciendo el recoloreado y el giro...")
    editor.undo()
    editor.undo()
    print(f"  Color de la base: {editor.get(base.instance_id).color}")
    print(f"  Caja de la cruzada: {describir_caja(editor.model, editor.get(cruzada.instance_id))}")

    print("\nRehaciendo el giro...")
    editor.redo()
    print(f"  Caja de la cruzada: {describir_caja(editor.model, editor.get(cruzada.instance_id))}")
    print("  (al girar 90 grados se intercambian el ancho y el fondo)")

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
    print(f"\nArchivo generado: {output.resolve()}")


if __name__ == "__main__":
    main()
