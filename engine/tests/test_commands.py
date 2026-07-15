import unittest

from blockcad_engine.geometry import LADRILLO, PLACA, STUD
from blockcad_engine import (
    BlockEditor,
    Orientation,
    CollisionError,
    GridPosition,
    MacroCommand,
    TransactionError,
)


class HistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.editor = BlockEditor(name="Pruebas")

    def test_add_can_be_undone_and_redone(self) -> None:
        part = self.editor.add("brick_2x4", GridPosition(0, 0, 0))
        self.assertEqual(len(self.editor.instances), 1)

        self.editor.undo()
        self.assertEqual(len(self.editor.instances), 0)

        self.editor.redo()
        self.assertEqual(len(self.editor.instances), 1)

    def test_redo_restores_the_same_instance_id(self) -> None:
        part = self.editor.add("brick_2x4", GridPosition(0, 0, 0))
        self.editor.undo()
        self.editor.redo()
        self.assertEqual(self.editor.get(part.instance_id).instance_id, part.instance_id)

    def test_undoing_remove_restores_original_order(self) -> None:
        first = self.editor.add("brick_1x1", GridPosition(0, 0, 0))
        second = self.editor.add("brick_1x1", GridPosition(2 * STUD, 0, 0))
        third = self.editor.add("brick_1x1", GridPosition(4 * STUD, 0, 0))

        self.editor.remove(second.instance_id)
        self.editor.undo()

        ids = [item.instance_id for item in self.editor.instances]
        self.assertEqual(
            ids,
            [first.instance_id, second.instance_id, third.instance_id],
        )

    def test_undo_rotation_restores_previous_angle(self) -> None:
        part = self.editor.add(
            "brick_2x4",
            GridPosition(0, 0, 0),
            orientation=Orientation.z(180),
        )
        self.editor.rotate_clockwise(part.instance_id)
        self.assertEqual(
            self.editor.get(part.instance_id).orientation, Orientation.z(270)
        )

        self.editor.undo()
        self.assertEqual(
            self.editor.get(part.instance_id).orientation, Orientation.z(180)
        )

    def test_undo_translate_restores_previous_position(self) -> None:
        part = self.editor.add("brick_2x4", GridPosition(0, 0, 0))
        self.editor.translate(part.instance_id, dx=4 * STUD, dz=LADRILLO)
        self.assertEqual(self.editor.get(part.instance_id).position, GridPosition(4 * STUD, 0, LADRILLO))

        self.editor.undo()
        self.assertEqual(self.editor.get(part.instance_id).position, GridPosition(0, 0, 0))

    def test_undo_recolor_restores_previous_color(self) -> None:
        part = self.editor.add("brick_2x4", GridPosition(0, 0, 0), color="#AA0000")
        self.editor.recolor(part.instance_id, "#00AAFF")
        self.editor.undo()
        self.assertEqual(self.editor.get(part.instance_id).color, "#AA0000")

    def test_new_command_clears_redo_stack(self) -> None:
        self.editor.add("brick_1x1", GridPosition(0, 0, 0))
        self.editor.undo()
        self.assertTrue(self.editor.can_redo)

        self.editor.add("brick_1x1", GridPosition(5 * STUD, 0, 0))
        self.assertFalse(self.editor.can_redo)

    def test_failed_command_is_not_recorded(self) -> None:
        self.editor.add("brick_2x4", GridPosition(0, 0, 0))
        with self.assertRaises(CollisionError):
            self.editor.add("brick_1x1", GridPosition(STUD, STUD, 0))

        self.assertEqual(len(self.editor.instances), 1)
        self.assertEqual(self.editor.history.undo_labels, ("Añadir brick_2x4",))

    def test_undo_without_history_raises(self) -> None:
        with self.assertRaises(IndexError):
            self.editor.undo()

    def test_history_limit_discards_oldest_entries(self) -> None:
        editor = BlockEditor(history_limit=2)
        for index in range(4):
            editor.add("brick_1x1", GridPosition(index * 2 * STUD, 0, 0))

        self.assertEqual(len(editor.history.undo_labels), 2)


class TransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.editor = BlockEditor(name="Transacciones")

    def test_transaction_groups_commands_into_one_undo(self) -> None:
        with self.editor.transaction("Construir muro"):
            self.editor.add("brick_2x4", GridPosition(0, 0, 0))
            self.editor.add("brick_2x4", GridPosition(2 * STUD, 0, 0))
            self.editor.add("brick_2x4", GridPosition(4 * STUD, 0, 0))

        self.assertEqual(len(self.editor.instances), 3)
        self.assertEqual(self.editor.history.undo_labels, ("Construir muro",))

        self.editor.undo()
        self.assertEqual(len(self.editor.instances), 0)

        self.editor.redo()
        self.assertEqual(len(self.editor.instances), 3)

    def test_failed_transaction_rolls_back_completely(self) -> None:
        self.editor.add("brick_2x4", GridPosition(0, 0, 0))

        with self.assertRaises(CollisionError):
            with self.editor.transaction("Construir torre"):
                self.editor.add("brick_2x4", GridPosition(0, 0, LADRILLO))
                self.editor.add("brick_2x4", GridPosition(0, 0, 2 * LADRILLO))
                self.editor.add("brick_1x1", GridPosition(0, 0, 0))

        self.assertEqual(len(self.editor.instances), 1)
        self.assertEqual(self.editor.history.undo_labels, ("Añadir brick_2x4",))

    def test_empty_transaction_is_not_recorded(self) -> None:
        with self.editor.transaction("Nada"):
            pass
        self.assertFalse(self.editor.can_undo)

    def test_nested_transactions_collapse_into_one_entry(self) -> None:
        with self.editor.transaction("Casa"):
            self.editor.add("brick_2x4", GridPosition(0, 0, 0))
            with self.editor.transaction("Techo"):
                self.editor.add("tile_1x2", GridPosition(0, 0, LADRILLO))
                self.editor.add("tile_1x2", GridPosition(0, 2 * STUD, LADRILLO))

        self.assertEqual(self.editor.history.undo_labels, ("Casa",))
        self.editor.undo()
        self.assertEqual(len(self.editor.instances), 0)

    def test_undo_inside_transaction_is_rejected(self) -> None:
        with self.assertRaises(TransactionError):
            with self.editor.transaction("Bloque"):
                self.editor.add("brick_1x1", GridPosition(0, 0, 0))
                self.editor.undo()


class MacroCommandTests(unittest.TestCase):
    def test_macro_rolls_back_when_a_child_fails(self) -> None:
        from blockcad_engine import AddPartCommand, BlockModel

        model = BlockModel()
        model.add("brick_2x4", GridPosition(0, 0, 0))

        macro = MacroCommand(
            "Grupo",
            [
                AddPartCommand("brick_2x4", GridPosition(0, 0, LADRILLO)),
                AddPartCommand("brick_1x1", GridPosition(0, 0, 0)),
            ],
        )

        with self.assertRaises(CollisionError):
            macro.execute(model)

        self.assertEqual(len(model.instances), 1)


if __name__ == "__main__":
    unittest.main()
