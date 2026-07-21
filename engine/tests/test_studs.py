"""Los studs se clavan en quien no tiene cavidades.

La caja de una pieza no cuenta sus studs: sobresalen 4 LDU y se meten en las
cavidades de la pieza de arriba (ver `Dimensions`). Ese trato tiene letra
pequeña, y estas pruebas la defienden: solo vale para quien TIENE cavidades.
Un ladrillo, una placa o una baldosa abrazan el stud con su reverso hueco;
un eje, un pin o un engranaje son plástico macizo por debajo, y apoyarlos a
la altura exacta del tope es clavarles los studs en la malla.

Se vio en la estación de riego: un eje descansaba sobre un ladrillo 1x2 y
los studs le atravesaban la malla. El modelo se arregló rematando el apoyo
con baldosa lisa; aquí se pide que el motor no vuelva a aceptar la
configuración falsa.
"""

import unittest

from blockcad_engine import BlockModel, GridPosition, Orientation
from blockcad_engine.catalogos import cargar
from blockcad_engine.errors import CollisionError

#: El eje 6, tumbado a lo largo de Y como lo endereza el catálogo: 12x119x12.
EJE = "3706"

#: El ladrillo 1x2 del bug: 40x20x24, dos studs en (10,10,24) y (30,10,24).
LADRILLO_1X2 = "3004"


class StudsComoVolumenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.modelo = BlockModel(catalog=cargar("wedo"))

    def test_an_axle_cannot_rest_on_studs(self) -> None:
        # La configuración de la estación de riego, reducida al hueso: el
        # eje acostado sobre el tope del ladrillo, con un stud bajo su
        # planta. Las cajas solo se tocan, pero el stud existe.
        self.modelo.add(LADRILLO_1X2, GridPosition(0, 0, 0))
        with self.assertRaises(CollisionError):
            self.modelo.add(
                EJE,
                GridPosition(4, 0, 24),
                orientation=Orientation.around("z", 90),
            )

    def test_the_order_does_not_matter(self) -> None:
        # El mismo choque si el ladrillo llega después: los studs se clavan
        # igual venga quien venga primero.
        self.modelo.add(
            EJE,
            GridPosition(4, 0, 24),
            orientation=Orientation.around("z", 90),
        )
        with self.assertRaises(CollisionError):
            self.modelo.add(LADRILLO_1X2, GridPosition(0, 0, 0))

    def test_a_smooth_tile_is_a_valid_bed(self) -> None:
        # El arreglo real del modelo: rematar el apoyo con baldosa lisa. La
        # baldosa se asienta sobre los studs del ladrillo —su reverso es
        # hueco— y su techo, sin studs, sí es cama para el eje.
        self.modelo.add(LADRILLO_1X2, GridPosition(0, 0, 0))
        self.modelo.add("3069", GridPosition(0, 0, 24))
        self.modelo.add(
            EJE,
            GridPosition(4, 0, 32),
            orientation=Orientation.around("z", 90),
        )
        self.assertEqual(len(self.modelo.instances), 3)

    def test_bricks_still_stack(self) -> None:
        # Lo primero que hace cualquiera. Un ladrillo tiene cavidades: los
        # studs de abajo entran y no chocan.
        self.modelo.add(LADRILLO_1X2, GridPosition(0, 0, 0))
        self.modelo.add(LADRILLO_1X2, GridPosition(0, 0, 24))
        self.assertEqual(len(self.modelo.instances), 2)

    def test_a_technic_plate_swallows_studs_too(self) -> None:
        # La placa Technic 2x4 no dibuja tubos en LDraw, pero su reverso es
        # de sistema: el nombre la delata y monta sobre studs como cualquiera.
        self.modelo.add("3001", GridPosition(0, 0, 0))
        self.modelo.add("3709", GridPosition(0, 0, 24))
        self.assertEqual(len(self.modelo.instances), 2)

    def test_a_gear_cannot_rest_on_studs(self) -> None:
        # Un engranaje es macizo por debajo: sobre un tope con studs no se
        # apoya, por mucho que las cajas no se invadan.
        self.modelo.add(LADRILLO_1X2, GridPosition(0, 0, 0))
        with self.assertRaises(CollisionError):
            self.modelo.add("10928", GridPosition(0, 0, 24))

    def test_a_brick_on_its_side_offers_no_cavities(self) -> None:
        # Las cavidades están en la base, no en las paredes: un ladrillo
        # tumbado sobre un tope con studs se los clava en el costado.
        self.modelo.add(LADRILLO_1X2, GridPosition(0, 0, 0))
        with self.assertRaises(CollisionError):
            self.modelo.add(
                LADRILLO_1X2,
                GridPosition(0, 0, 24),
                orientation=Orientation.around("x", 90),
            )

    def test_the_whole_stud_is_forbidden_ground(self) -> None:
        # El stud mide 4 LDU: una pieza maciza flotando DENTRO de ese tramo
        # sigue atravesada aunque las cajas ni se rocen. En su punta, ya no.
        self.modelo.add(LADRILLO_1X2, GridPosition(0, 0, 0))
        with self.assertRaises(CollisionError):
            self.modelo.add(
                EJE,
                GridPosition(4, 0, 26),
                orientation=Orientation.around("z", 90),
            )
        self.modelo.add(
            EJE,
            GridPosition(4, 0, 28),
            orientation=Orientation.around("z", 90),
        )

    def test_resting_between_the_studs_is_allowed(self) -> None:
        # El eje cabe tumbado entre las dos filas de studs de una placa
        # ancha: sin stud bajo su planta no hay nada que se clave.
        self.modelo.add(LADRILLO_1X2, GridPosition(0, 0, 0))
        self.modelo.add(
            EJE,
            GridPosition(14, 0, 24),
            orientation=Orientation.around("z", 90),
        )
        self.assertEqual(len(self.modelo.instances), 2)


class BaseHuecaEnElCatalogoTests(unittest.TestCase):
    """Quién declara cavidades y quién no, pieza a pieza del set real."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalogo = cargar("wedo")

    def test_the_system_families_are_hollow_below(self) -> None:
        # Ladrillo, baldosa (sin conexión alguna), placa Technic y bracket:
        # todo el sistema de ladrillos monta sobre studs.
        for pieza in ("3004", "3069", "3709", "21712", "4287"):
            with self.subTest(pieza=pieza):
                self.assertTrue(self.catalogo.get(pieza).has_bottom_cavities)

    def test_the_underside_tubes_count_as_cavities(self) -> None:
        # La cremallera y el hub eléctrico no se llaman Brick ni Plate,
        # pero LDraw les dibuja los tubos del reverso: montan sobre studs.
        for pieza in ("3743", "19071", "21980"):
            with self.subTest(pieza=pieza):
                self.assertTrue(self.catalogo.get(pieza).has_bottom_cavities)

    def test_solid_technic_parts_declare_no_cavities(self) -> None:
        # Eje, engranaje, pin, casquillo, viga: macizos por debajo.
        for pieza in ("3706", "10928", "2780", "42136", "32524"):
            with self.subTest(pieza=pieza):
                self.assertFalse(self.catalogo.get(pieza).has_bottom_cavities)


if __name__ == "__main__":
    unittest.main()
