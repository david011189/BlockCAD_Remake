import json
import tempfile
import unittest
from pathlib import Path

from blockcad_engine import (
    BlockCADError,
    BlockEditor,
    BlockModel,
    Dimensions,
    DuplicatePartError,
    GridPosition,
    InstanceNotFoundError,
    InvalidColorError,
    InvalidFormatError,
    InvalidGeometryError,
    InvalidPartError,
    PartCatalog,
    PartDefinition,
    Orientation,
    load_model,
)


class PublicApiTests(unittest.TestCase):
    """Lo que se exporta tiene que existir y usarse.

    `Rotation` sobrevivió al cambio a orientaciones: nada del motor lo usaba,
    pero seguía en la API pública y solo lo tocaban dos pruebas, que probaban
    código muerto.
    """

    def test_everything_exported_exists(self) -> None:
        import blockcad_engine

        for nombre in blockcad_engine.__all__:
            with self.subTest(nombre=nombre):
                self.assertTrue(hasattr(blockcad_engine, nombre))

    def test_nothing_is_exported_twice(self) -> None:
        import blockcad_engine

        self.assertEqual(
            len(blockcad_engine.__all__), len(set(blockcad_engine.__all__))
        )


class HierarchyTests(unittest.TestCase):
    """Ningún fallo del dominio debe escapar de BlockCADError.

    Una interfaz que capture BlockCADError tiene que poder mostrar un mensaje
    para cualquiera de estas situaciones en vez de caerse.
    """

    def setUp(self) -> None:
        self.model = BlockModel()

    def test_moving_below_ground_is_a_domain_error(self) -> None:
        part = self.model.add("brick_1x1", GridPosition(0, 0, 0))
        with self.assertRaises(BlockCADError):
            self.model.translate(part.instance_id, dz=-5)

    def test_negative_z_is_a_domain_error(self) -> None:
        with self.assertRaises(BlockCADError):
            GridPosition(0, 0, -1)

    def test_invalid_rotation_is_a_domain_error(self) -> None:
        with self.assertRaises(BlockCADError):
            Orientation.around("z", 45)

    def test_zero_dimension_is_a_domain_error(self) -> None:
        with self.assertRaises(BlockCADError):
            Dimensions(0, 1, 1)

    def test_missing_instance_is_a_domain_error(self) -> None:
        with self.assertRaises(BlockCADError):
            self.model.get("no-existe")

    def test_invalid_color_is_a_domain_error(self) -> None:
        part = self.model.add("brick_1x1", GridPosition(0, 0, 0))
        with self.assertRaises(BlockCADError):
            self.model.recolor(part.instance_id, "#ZZZZZZ")

    def test_duplicate_part_is_a_domain_error(self) -> None:
        catalog = PartCatalog.with_basic_parts()
        with self.assertRaises(BlockCADError):
            catalog.register(
                PartDefinition("brick_1x1", "Repetida", Dimensions(1, 1, 1))
            )

    def test_empty_part_id_is_a_domain_error(self) -> None:
        with self.assertRaises(BlockCADError):
            PartDefinition("  ", "Sin identificador", Dimensions(1, 1, 1))


class BackwardsCompatibilityTests(unittest.TestCase):
    """El código que ya capturaba ValueError o KeyError debe seguir igual."""

    def test_geometry_errors_are_still_value_errors(self) -> None:
        with self.assertRaises(ValueError):
            GridPosition(0, 0, -1)
        with self.assertRaises(ValueError):
            Orientation.around("z", 45)
        with self.assertRaises(ValueError):
            Dimensions(1, 0, 1)

    def test_missing_instance_is_still_a_key_error(self) -> None:
        model = BlockModel()
        with self.assertRaises(KeyError):
            model.get("no-existe")
        with self.assertRaises(KeyError):
            model.remove("no-existe")
        with self.assertRaises(KeyError):
            model.index_of("no-existe")

    def test_not_found_message_has_no_extra_quotes(self) -> None:
        model = BlockModel()
        try:
            model.get("abc")
        except InstanceNotFoundError as error:
            self.assertEqual(str(error), "No existe la instancia 'abc'.")
        else:
            self.fail("Se esperaba InstanceNotFoundError.")


class SpecificErrorTests(unittest.TestCase):
    """Cada situación lanza la clase concreta que le corresponde."""

    def test_error_classes_are_specific(self) -> None:
        model = BlockModel()
        part = model.add("brick_1x1", GridPosition(0, 0, 0))

        with self.assertRaises(InvalidGeometryError):
            GridPosition(0, 0, -1)
        with self.assertRaises(InstanceNotFoundError):
            model.get("no-existe")
        with self.assertRaises(InvalidColorError):
            model.recolor(part.instance_id, "#12345")
        with self.assertRaises(InvalidPartError):
            PartDefinition("x", "   ", Dimensions(1, 1, 1))
        with self.assertRaises(DuplicatePartError):
            catalog = PartCatalog.with_basic_parts()
            catalog.register(PartDefinition("tile_1x2", "Otra", Dimensions(1, 1, 1)))


class ColorValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = BlockModel()
        self.part = self.model.add("brick_1x1", GridPosition(0, 0, 0))

    def test_non_hexadecimal_color_is_rejected(self) -> None:
        for color in ("#ZZZZZZ", "#12345", "#1234567", "D62828", "", "#GGHHII"):
            with self.subTest(color=color):
                with self.assertRaises(InvalidColorError):
                    self.model.recolor(self.part.instance_id, color)

    def test_valid_color_is_normalized_to_uppercase(self) -> None:
        updated = self.model.recolor(self.part.instance_id, "#00aaff")
        self.assertEqual(updated.color, "#00AAFF")


class BooleanCoordinateTests(unittest.TestCase):
    def test_booleans_are_rejected_as_coordinates(self) -> None:
        with self.assertRaises(TypeError):
            GridPosition(True, 0, 0)

    def test_booleans_are_rejected_as_dimensions(self) -> None:
        with self.assertRaises(TypeError):
            Dimensions(True, 1, 1)


class CorruptFileTests(unittest.TestCase):
    def _write(self, payload: dict) -> Path:
        directory = tempfile.mkdtemp()
        path = Path(directory) / "roto.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_unknown_format_is_a_domain_error(self) -> None:
        path = self._write({"format": "otro", "version": 1, "parts": []})
        with self.assertRaises(InvalidFormatError):
            load_model(path)

    def test_missing_field_is_a_domain_error(self) -> None:
        path = self._write(
            {
                "format": "blockcad-remake",
                "version": 1,
                "name": "Roto",
                "parts": [{"instance_id": "a", "part_id": "brick_1x1"}],
            }
        )
        with self.assertRaises(InvalidFormatError):
            load_model(path)

    def test_impossible_value_is_a_domain_error(self) -> None:
        path = self._write(
            {
                "format": "blockcad-remake",
                "version": 1,
                "name": "Roto",
                "parts": [
                    {
                        "instance_id": "a",
                        "part_id": "brick_1x1",
                        "position": {"x": 0, "y": 0, "z": -3},
                    }
                ],
            }
        )
        with self.assertRaises(InvalidFormatError):
            load_model(path)


class EditorErrorTests(unittest.TestCase):
    def test_failed_editor_operation_is_catchable_as_domain_error(self) -> None:
        editor = BlockEditor()
        part = editor.add("brick_1x1", GridPosition(0, 0, 0))

        with self.assertRaises(BlockCADError):
            editor.translate(part.instance_id, dz=-1)

        # El comando falló, así que no debe quedar registrado.
        self.assertEqual(len(editor.history.undo_labels), 1)
        self.assertEqual(editor.get(part.instance_id).position, GridPosition(0, 0, 0))


if __name__ == "__main__":
    unittest.main()
