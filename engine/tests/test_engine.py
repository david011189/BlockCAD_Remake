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
    InvalidGeometryError,
    Orientation,
    load_model,
    save_model,
)
from blockcad_engine.geometry import LADRILLO, PLACA, STUD


class GeometryTests(unittest.TestCase):
    def test_rotation_swaps_width_and_depth(self) -> None:
        dimensions = Dimensions(2 * STUD, 4 * STUD, LADRILLO)
        self.assertEqual(
            dimensions.rotated(Orientation.z(90)),
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


class OrientationTests(unittest.TestCase):
    """Las 24 orientaciones de un cubo, como matrices de enteros."""

    def test_there_are_exactly_twenty_four(self) -> None:
        # El grupo de rotaciones del cubo tiene 24 elementos. Si salieran más
        # es que se cuela un espejo; si menos, que falta algún giro.
        vistas = set()
        pendientes = [Orientation()]
        while pendientes:
            actual = pendientes.pop()
            if actual.filas in vistas:
                continue
            vistas.add(actual.filas)
            for eje in "xyz":
                pendientes.append(Orientation.around(eje, 90).then(actual))
        self.assertEqual(len(vistas), 24)

    def test_four_quarter_turns_come_back(self) -> None:
        for eje in "xyz":
            with self.subTest(eje=eje):
                actual = Orientation()
                for _ in range(4):
                    actual = Orientation.around(eje, 90).then(actual)
                self.assertTrue(actual.is_identity)

    def test_rotating_z_still_swaps_width_and_depth(self) -> None:
        # Compatible con lo de siempre: el giro de toda la vida no cambia.
        pieza = Dimensions(2 * STUD, 4 * STUD, LADRILLO)
        self.assertEqual(
            pieza.rotated(Orientation.z(90)),
            Dimensions(4 * STUD, 2 * STUD, LADRILLO),
        )
        self.assertEqual(pieza.rotated(Orientation.z(180)), pieza)

    def test_a_beam_can_stand_up(self) -> None:
        # Lo que era imposible: una pieza larga apuntando hacia arriba.
        viga = Dimensions(STUD, 5 * STUD, STUD)
        self.assertEqual(
            viga.rotated(Orientation.around("x", 90)),
            Dimensions(STUD, STUD, 5 * STUD),
        )

    def test_rotating_never_changes_the_volume(self) -> None:
        pieza = Dimensions(2 * STUD, 4 * STUD, LADRILLO)
        volumen = pieza.width * pieza.depth * pieza.height
        for filas in _todas_las_orientaciones():
            girada = pieza.rotated(Orientation(filas))
            with self.subTest(filas=filas):
                self.assertEqual(
                    girada.width * girada.depth * girada.height, volumen
                )

    def test_a_mirror_is_not_an_orientation(self) -> None:
        # Determinante -1: reflejaría la pieza, y una pieza reflejada no
        # existe. Es el error clásico de las matrices de giro.
        with self.assertRaises(InvalidGeometryError):
            Orientation(((-1, 0, 0), (0, 1, 0), (0, 0, 1)))

    def test_nonsense_matrices_are_rejected(self) -> None:
        for filas in (
            ((1, 1, 0), (0, 1, 0), (0, 0, 1)),   # dos valores en una fila
            ((1, 0, 0), (1, 0, 0), (0, 0, 1)),   # dos filas iguales
            ((2, 0, 0), (0, 1, 0), (0, 0, 1)),   # no es un giro de 90°
            ((1, 0, 0), (0, 1, 0)),              # le falta una fila
        ):
            with self.subTest(filas=filas):
                with self.assertRaises(InvalidGeometryError):
                    Orientation(filas)

    def test_only_right_angles(self) -> None:
        with self.assertRaises(InvalidGeometryError):
            Orientation.around("z", 45)

    def test_the_axis_must_exist(self) -> None:
        with self.assertRaises(InvalidGeometryError):
            Orientation.around("w", 90)

    def test_it_knows_when_a_piece_is_still_upright(self) -> None:
        # De esto depende que el visor dibuje los studs o no.
        self.assertTrue(Orientation().keeps_z_up)
        self.assertTrue(Orientation.z(180).keeps_z_up)
        self.assertFalse(Orientation.around("x", 90).keeps_z_up)


def _todas_las_orientaciones() -> set:
    vistas = set()
    pendientes = [Orientation()]
    while pendientes:
        actual = pendientes.pop()
        if actual.filas in vistas:
            continue
        vistas.add(actual.filas)
        for eje in "xyz":
            pendientes.append(Orientation.around(eje, 90).then(actual))
    return vistas


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
            orientation=Orientation.z(90),
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
        self.assertEqual(restored.orientation, Orientation.z(90))
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
        self.assertEqual(pieza.orientation, Orientation.z(90))

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

    def test_a_version_2_file_still_opens(self) -> None:
        # La 2 ya medía en LDU, pero el giro era un ángulo sobre Z. Un ángulo
        # es un caso particular de la matriz de ahora.
        viejo = {
            "format": "blockcad-remake",
            "version": 2,
            "name": "Con angulo",
            "parts": [
                {
                    "instance_id": "a",
                    "part_id": "brick_2x4",
                    "position": {"x": 0, "y": 0, "z": 0},
                    "rotation": 90,
                    "color": "#D62828",
                    "group": 0,
                    "step": 0,
                    "transparent": False,
                }
            ],
        }
        modelo = load_model(self._guardar(viejo))
        self.assertEqual(modelo.instances[0].orientation, Orientation.z(90))

    def test_the_new_format_stores_the_whole_matrix(self) -> None:
        modelo = BlockModel(name="De pie")
        modelo.add(
            "brick_2x4",
            GridPosition(0, 0, 0),
            orientation=Orientation.around("x", 90),
        )
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "m.json"
            save_model(modelo, ruta)
            datos = json.loads(ruta.read_text(encoding="utf-8"))
            recuperado = load_model(ruta)

        self.assertEqual(len(datos["parts"][0]["orientation"]), 3)
        self.assertEqual(
            recuperado.instances[0].orientation, Orientation.around("x", 90)
        )

    def test_an_upright_piece_survives_a_round_trip(self) -> None:
        # Un ángulo sobre Z no sabe decir "de pie": si el formato perdiera la
        # matriz, la pieza volvería tumbada y nadie se enteraría.
        modelo = BlockModel()
        pieza = modelo.add(
            "brick_2x4",
            GridPosition(0, 0, 0),
            orientation=Orientation.around("y", 90),
        )
        caja_antes = pieza.bounds(modelo.catalog.get("brick_2x4"))

        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "m.json"
            save_model(modelo, ruta)
            recuperado = load_model(ruta)

        vuelta = recuperado.instances[0]
        self.assertEqual(
            vuelta.bounds(recuperado.catalog.get("brick_2x4")), caja_antes
        )

    def test_what_gets_written_is_the_new_version(self) -> None:
        modelo = BlockModel(name="Nuevo")
        modelo.add("brick_2x4", GridPosition(0, 0, 0))
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "m.json"
            save_model(modelo, ruta)
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        self.assertEqual(datos["version"], 3)

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
