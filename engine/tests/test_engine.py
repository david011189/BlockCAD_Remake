"""Pruebas del núcleo del motor.

Las medidas van en LDU. Se escriben con las constantes —`2 * STUD`, `LADRILLO`—
y no con los números crudos: `GridPosition(0, 0, 24)` no dice nada, pero
`GridPosition(0, 0, LADRILLO)` dice «encima del ladrillo».
"""

import json
import tempfile
import unittest
from pathlib import Path

from blockcad_engine import (
    BlockModel,
    CollisionError,
    Dimensions,
    GridPosition,
    InvalidFormatError,
    PartCatalog,
    PartDefinition,
    Rotation,
    load_model,
    save_model,
)
from blockcad_engine.geometry import LADRILLO, PLACA, STUD


class GeometryTests(unittest.TestCase):
    def test_rotation_swaps_width_and_depth(self) -> None:
        dimensions = Dimensions(2 * STUD, 4 * STUD, LADRILLO)
        self.assertEqual(
            dimensions.rotated(Rotation.DEG_90),
            Dimensions(4 * STUD, 2 * STUD, LADRILLO),
        )

    def test_position_cannot_be_below_ground(self) -> None:
        with self.assertRaises(ValueError):
            GridPosition(0, 0, -1)

    def test_the_units_are_the_real_ones(self) -> None:
        # Si esto cambia, cambia todo el motor: son los números de LEGO.
        self.assertEqual(STUD, 20)      # 8 mm
        self.assertEqual(PLACA, 8)      # 3,2 mm
        self.assertEqual(LADRILLO, 24)  # 9,6 mm = 3 placas
        self.assertEqual(LADRILLO, 3 * PLACA)


class ModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = BlockModel()

    def test_add_and_move_part(self) -> None:
        part = self.model.add("brick_2x4", GridPosition(0, 0, 0))
        destino = GridPosition(5 * STUD, 2 * STUD, 0)
        moved = self.model.move(part.instance_id, destino)
        self.assertEqual(moved.position, destino)

    def test_collision_is_detected(self) -> None:
        self.model.add("brick_2x4", GridPosition(0, 0, 0))
        with self.assertRaises(CollisionError):
            self.model.add("brick_1x1", GridPosition(1 * STUD, 1 * STUD, 0))

    def test_touching_faces_are_not_collision(self) -> None:
        self.model.add("brick_2x4", GridPosition(0, 0, 0))
        self.model.add("brick_2x4", GridPosition(2 * STUD, 0, 0))
        self.assertEqual(len(self.model.instances), 2)

    def test_stacking_is_allowed(self) -> None:
        self.model.add("brick_2x4", GridPosition(0, 0, 0))
        self.model.add("brick_2x4", GridPosition(0, 0, LADRILLO))
        self.assertEqual(len(self.model.instances), 2)

    def test_a_brick_is_exactly_three_plates_tall(self) -> None:
        # Apilar una placa justo encima de un ladrillo no debe chocar, y una
        # placa menos sí: es lo que fija que un ladrillo mida 24 y no 28.
        self.model.add("brick_2x4", GridPosition(0, 0, 0))
        self.model.add("plate_2x4", GridPosition(0, 0, LADRILLO))
        self.assertEqual(len(self.model.instances), 2)

        with self.assertRaises(CollisionError):
            self.model.add("plate_2x4", GridPosition(0, 0, LADRILLO - PLACA))

    def test_rotation_can_trigger_collision(self) -> None:
        first = self.model.add("brick_1x2", GridPosition(0, 0, 0))
        self.model.add("brick_1x1", GridPosition(1 * STUD, 0, 0))
        with self.assertRaises(CollisionError):
            self.model.rotate_clockwise(first.instance_id)

    def test_a_technic_module_is_not_a_whole_number_of_plates(self) -> None:
        # La razón de existir de LDU: 20 LDU de módulo son 2,5 placas, así que
        # con placas enteras una viga Technic sería incolocable.
        self.assertNotEqual(20 % PLACA, 0)
        self.assertEqual(20 / PLACA, 2.5)


class SerializationTests(unittest.TestCase):
    def test_save_and_load_preserves_model(self) -> None:
        model = BlockModel(name="Prueba")
        posicion = GridPosition(3 * STUD, 4 * STUD, 1 * PLACA)
        part = model.add(
            "plate_2x4",
            posicion,
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
        self.assertEqual(restored.position, posicion)
        self.assertEqual(restored.rotation, Rotation.DEG_90)
        self.assertEqual(restored.color, "#112233")
        self.assertEqual(restored.group, 2)
        self.assertEqual(restored.step, 5)


class MigrationTests(unittest.TestCase):
    """Los archivos de la versión 1 medían en studs y placas.

    Hay gente con modelos guardados: tienen que seguir abriéndose. La regla
    la escribió el propio proyecto en su guía de extensión —«la carga deberá
    conservar migradores para versiones anteriores»— y aquí se cumple.
    """

    def _guardar(self, payload: dict) -> Path:
        carpeta = tempfile.mkdtemp()
        ruta = Path(carpeta) / "viejo.json"
        ruta.write_text(json.dumps(payload), encoding="utf-8")
        return ruta

    def test_a_version_1_file_still_opens(self) -> None:
        # Un ladrillo en (2, 0, 3) de la versión 1 son 2 studs y 3 placas, o
        # sea la altura justa de un ladrillo.
        viejo = {
            "format": "blockcad-remake",
            "version": 1,
            "name": "De antes",
            "parts": [
                {
                    "instance_id": "a",
                    "part_id": "brick_2x4",
                    "position": {"x": 2, "y": 0, "z": 3},
                    "rotation": 90,
                    "color": "#D62828",
                    "group": 0,
                    "step": 0,
                    "transparent": False,
                }
            ],
        }
        modelo = load_model(self._guardar(viejo))
        self.assertEqual(modelo.name, "De antes")
        pieza = modelo.instances[0]
        self.assertEqual(pieza.position, GridPosition(2 * STUD, 0, LADRILLO))
        self.assertEqual(pieza.rotation, Rotation.DEG_90)

    def test_a_version_1_model_keeps_its_shape(self) -> None:
        # Dos ladrillos apilados en la versión 1 siguen apilados y sin chocar.
        viejo = {
            "format": "blockcad-remake",
            "version": 1,
            "name": "Torre vieja",
            "parts": [
                {
                    "instance_id": str(i),
                    "part_id": "brick_2x4",
                    "position": {"x": 0, "y": 0, "z": 3 * i},
                    "rotation": 0,
                    "color": "#D62828",
                    "group": 0,
                    "step": 0,
                    "transparent": False,
                }
                for i in range(3)
            ],
        }
        modelo = load_model(self._guardar(viejo))
        self.assertEqual(
            [p.position.z for p in modelo.instances],
            [0, LADRILLO, 2 * LADRILLO],
        )

    def test_what_gets_written_is_the_new_version(self) -> None:
        modelo = BlockModel(name="Nuevo")
        modelo.add("brick_2x4", GridPosition(0, 0, 0))
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "m.json"
            save_model(modelo, ruta)
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        self.assertEqual(datos["version"], 2)

    def test_an_unknown_version_is_still_rejected(self) -> None:
        futuro = {"format": "blockcad-remake", "version": 99, "parts": []}
        with self.assertRaises(InvalidFormatError):
            load_model(self._guardar(futuro))


class CatalogTests(unittest.TestCase):
    def test_custom_part_can_be_registered(self) -> None:
        catalog = PartCatalog()
        catalog.register(
            PartDefinition(
                "custom_column",
                "Columna personalizada",
                Dimensions(1 * STUD, 1 * STUD, 3 * LADRILLO),
            )
        )
        self.assertTrue(catalog.contains("custom_column"))

    def test_the_basic_catalog_is_measured_in_ldu(self) -> None:
        catalogo = PartCatalog.with_basic_parts()
        self.assertEqual(
            catalogo.get("brick_2x4").dimensions,
            Dimensions(2 * STUD, 4 * STUD, LADRILLO),
        )
        self.assertEqual(
            catalogo.get("plate_2x4").dimensions,
            Dimensions(2 * STUD, 4 * STUD, PLACA),
        )


if __name__ == "__main__":
    unittest.main()
