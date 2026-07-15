"""Pruebas de las conexiones y del aviso de piezas flotantes.

Decisión de diseño: una pieza sin apoyo se AVISA, no se rechaza. El BlockCAD
original permitía piezas flotantes, y rechazarlas obligaría a que cada pieza
conecte con algo mientras se construye, lo que vuelve el lenguaje tedioso.
"""

import unittest

from blockcad_engine import BlockModel, GridPosition, Orientation, parse_model
from blockcad_engine.catalogos import cargar
from blockcad_engine.geometry import LADRILLO, STUD


class WorldConnectionTests(unittest.TestCase):
    """Los puntos de conexión, ya girados y colocados."""

    def setUp(self) -> None:
        self.model = BlockModel(catalog=cargar("wedo"))

    def _puntos(self, pieza, tipo=None):
        definicion = self.model.catalog.get(pieza.part_id)
        return sorted(
            punto
            for t, punto in pieza.world_connections(definicion)
            if tipo is None or t == tipo
        )

    def test_a_brick_has_its_studs_on_top(self) -> None:
        pieza = self.model.add("3003", GridPosition(0, 0, 0))
        self.assertEqual(
            self._puntos(pieza, "stud"),
            [(10, 10, 24), (10, 30, 24), (30, 10, 24), (30, 30, 24)],
        )

    def test_the_points_travel_with_the_piece(self) -> None:
        pieza = self.model.add("3003", GridPosition(5 * STUD, 0, 0))
        self.assertTrue(all(p[0] >= 100 for p in self._puntos(pieza, "stud")))

    def test_the_points_stay_inside_the_rotated_box(self) -> None:
        # Girar mueve la caja fuera de su sitio y el motor la reancla. Si los
        # puntos no se reanclaran igual, acabarían fuera de la pieza.
        for eje in "xyz":
            with self.subTest(eje=eje):
                modelo = BlockModel(catalog=cargar("wedo"))
                pieza = modelo.add(
                    "32524",
                    GridPosition(0, 0, 0),
                    orientation=Orientation.around(eje, 90),
                )
                definicion = modelo.catalog.get("32524")
                caja = pieza.bounds(definicion)
                for _, punto in pieza.world_connections(definicion):
                    self.assertTrue(caja.min_x <= punto[0] <= caja.max_x)
                    self.assertTrue(caja.min_y <= punto[1] <= caja.max_y)
                    self.assertTrue(caja.min_z <= punto[2] <= caja.max_z)

    def test_a_beam_is_pierced_by_its_holes(self) -> None:
        # Los agujeros salen por las dos caras. Eso no es un duplicado: es lo
        # que hace que dos vigas pegadas compartan el punto.
        pieza = self.model.add("32524", GridPosition(0, 0, 0))
        alturas = {p[2] for p in self._puntos(pieza, "agujero_pin")}
        self.assertEqual(alturas, {0, 20})

    def test_a_piece_without_data_has_no_points(self) -> None:
        # El catálogo básico no trae conexiones.
        modelo = BlockModel()
        pieza = modelo.add("brick_2x4", GridPosition(0, 0, 0))
        self.assertEqual(
            pieza.world_connections(modelo.catalog.get("brick_2x4")), ()
        )


class ConnectionTests(unittest.TestCase):
    def test_two_stacked_beams_are_connected(self) -> None:
        modelo = BlockModel(catalog=cargar("wedo"))
        abajo = modelo.add("32524", GridPosition(0, 0, 0))
        arriba = modelo.add("32524", GridPosition(0, 0, 20))
        self.assertEqual(
            [p.instance_id for p in modelo.connected_to(arriba.instance_id)],
            [abajo.instance_id],
        )

    def test_beams_apart_are_not_connected(self) -> None:
        modelo = BlockModel(catalog=cargar("wedo"))
        modelo.add("32524", GridPosition(0, 0, 0))
        lejos = modelo.add("32524", GridPosition(0, 0, 200))
        self.assertEqual(modelo.connected_to(lejos.instance_id), ())

    def test_bricks_do_not_share_points(self) -> None:
        # Un ladrillo tiene studs arriba y nada abajo, así que dos apilados no
        # comparten ningún punto. Se sostienen por apoyo, no por conexión.
        modelo = BlockModel(catalog=cargar("wedo"))
        modelo.add("3003", GridPosition(0, 0, 0))
        arriba = modelo.add("3003", GridPosition(0, 0, LADRILLO))
        self.assertEqual(modelo.connected_to(arriba.instance_id), ())
        self.assertTrue(modelo.resting_on(arriba.instance_id))


class SupportTests(unittest.TestCase):
    def test_a_piece_on_the_ground_is_supported(self) -> None:
        modelo = BlockModel()
        pieza = modelo.add("brick_2x4", GridPosition(0, 0, 0))
        self.assertTrue(modelo.is_supported(pieza.instance_id))

    def test_a_stacked_piece_is_supported(self) -> None:
        modelo = BlockModel()
        modelo.add("brick_2x4", GridPosition(0, 0, 0))
        arriba = modelo.add("brick_2x4", GridPosition(0, 0, LADRILLO))
        self.assertTrue(modelo.is_supported(arriba.instance_id))

    def test_a_piece_in_the_air_is_not(self) -> None:
        modelo = BlockModel()
        modelo.add("brick_2x4", GridPosition(0, 0, 0))
        volando = modelo.add("brick_2x4", GridPosition(0, 0, 10 * LADRILLO))
        self.assertFalse(modelo.is_supported(volando.instance_id))

    def test_touching_only_at_the_edge_does_not_hold(self) -> None:
        # Dos piezas que solo se rozan de canto no se sostienen: las plantas
        # tienen que solaparse de verdad.
        modelo = BlockModel()
        modelo.add("brick_2x4", GridPosition(0, 0, 0))
        canto = modelo.add("brick_2x4", GridPosition(2 * STUD, 0, LADRILLO))
        self.assertFalse(modelo.is_supported(canto.instance_id))

    def test_stacked_beams_are_both_resting_and_connected(self) -> None:
        """Las dos vías dan lo mismo, y hoy eso pasa siempre.

        Con las piezas de este set, todo lo que está conectado está además
        apoyado: probado contra 72 colocaciones, no hay ni un caso de pieza
        conectada que no se apoye. La regla «si comparten un punto, una
        sostiene a la otra» se mantiene porque es cierta, y hará falta el día
        que un pin una dos vigas de costado; hoy es redundante.
        """
        modelo = BlockModel(catalog=cargar("wedo"))
        modelo.add("32524", GridPosition(0, 0, 0))
        arriba = modelo.add("32524", GridPosition(0, 0, 20))
        self.assertTrue(modelo.resting_on(arriba.instance_id))
        self.assertTrue(modelo.connected_to(arriba.instance_id))
        self.assertTrue(modelo.is_supported(arriba.instance_id))

    def test_floating_lists_what_is_in_the_air(self) -> None:
        modelo = BlockModel()
        modelo.add("brick_2x4", GridPosition(0, 0, 0))
        volando = modelo.add("brick_2x4", GridPosition(0, 0, 10 * LADRILLO))
        self.assertEqual(
            [p.instance_id for p in modelo.floating()], [volando.instance_id]
        )

    def test_a_floating_piece_is_allowed(self) -> None:
        # Se avisa, no se rechaza: es la decisión de diseño.
        modelo = parse_model("ladrillo 2x4 en 0,0,0\nladrillo 2x4 en 0,0,20")
        self.assertEqual(len(modelo.instances), 2)
        self.assertEqual(len(modelo.floating()), 1)

    def test_the_house_has_nothing_in_the_air(self) -> None:
        # Una casa bien construida no debe dar ni un aviso: si lo diera, el
        # detector estaría inventándose problemas.
        codigo = "\n".join([
            'modelo "Casa"',
            "repetir 3 veces desplazando 0,2,0:",
            "    placa 2x4 en 0,0,0 rot 90",
            "    placa 2x4 en 4,0,0 rot 90",
            "repetir 3 veces desplazando 0,0,3:",
            "    ladrillo 1x2 en 0,1,1",
            "    ladrillo 1x2 en 7,1,1",
        ])
        modelo = parse_model(codigo)
        self.assertEqual(modelo.floating(), ())


if __name__ == "__main__":
    unittest.main()
