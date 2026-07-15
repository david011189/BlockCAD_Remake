import tempfile
import unittest
from pathlib import Path

from blockcad_engine import (
    BlockModel,
    CollisionError,
    Dimensions,
    GridPosition,
    PartCatalog,
    PartDefinition,
    Rotation,
    load_model,
    save_model,
)


class GeometryTests(unittest.TestCase):
    def test_rotation_swaps_width_and_depth(self) -> None:
        dimensions = Dimensions(2, 4, 3)
        self.assertEqual(
            dimensions.rotated(Rotation.DEG_90),
            Dimensions(4, 2, 3),
        )

    def test_position_cannot_be_below_ground(self) -> None:
        with self.assertRaises(ValueError):
            GridPosition(0, 0, -1)


class ModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = BlockModel()

    def test_add_and_move_part(self) -> None:
        part = self.model.add("brick_2x4", GridPosition(0, 0, 0))
        moved = self.model.move(part.instance_id, GridPosition(5, 2, 0))
        self.assertEqual(moved.position, GridPosition(5, 2, 0))

    def test_collision_is_detected(self) -> None:
        self.model.add("brick_2x4", GridPosition(0, 0, 0))
        with self.assertRaises(CollisionError):
            self.model.add("brick_1x1", GridPosition(1, 1, 0))

    def test_touching_faces_are_not_collision(self) -> None:
        self.model.add("brick_2x4", GridPosition(0, 0, 0))
        self.model.add("brick_2x4", GridPosition(2, 0, 0))
        self.assertEqual(len(self.model.instances), 2)

    def test_stacking_is_allowed(self) -> None:
        self.model.add("brick_2x4", GridPosition(0, 0, 0))
        self.model.add("brick_2x4", GridPosition(0, 0, 3))
        self.assertEqual(len(self.model.instances), 2)

    def test_rotation_can_trigger_collision(self) -> None:
        first = self.model.add("brick_1x2", GridPosition(0, 0, 0))
        self.model.add("brick_1x1", GridPosition(1, 0, 0))
        with self.assertRaises(CollisionError):
            self.model.rotate_clockwise(first.instance_id)


class SerializationTests(unittest.TestCase):
    def test_save_and_load_preserves_model(self) -> None:
        model = BlockModel(name="Prueba")
        part = model.add(
            "plate_2x4",
            GridPosition(3, 4, 1),
            rotation=Rotation.DEG_90,
            color="#112233",
            group=2,
            step=5,
        )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.json"
            save_model(model, path)
            loaded = load_model(path)

        self.assertEqual(loaded.name, "Prueba")
        self.assertEqual(len(loaded.instances), 1)
        restored = loaded.get(part.instance_id)
        self.assertEqual(restored.position, GridPosition(3, 4, 1))
        self.assertEqual(restored.rotation, Rotation.DEG_90)
        self.assertEqual(restored.color, "#112233")
        self.assertEqual(restored.group, 2)
        self.assertEqual(restored.step, 5)


class CatalogTests(unittest.TestCase):
    def test_custom_part_can_be_registered(self) -> None:
        catalog = PartCatalog()
        catalog.register(
            PartDefinition(
                "custom_column",
                "Columna personalizada",
                Dimensions(1, 1, 9),
            )
        )
        self.assertTrue(catalog.contains("custom_column"))


if __name__ == "__main__":
    unittest.main()
