"""Insertar no es chocar.

Technic no se apila: se construye metiendo cosas dentro de otras. Un pin
*ocupa* el agujero y un eje *atraviesa* la viga, así que sus cajas se solapan
de verdad. Para un motor de ladrillos de sistema eso es un choque —y hace bien:
dos ladrillos se apoyan y se tocan, nunca se invaden—, pero aplicado a Technic
convierte cada unión real en un error y hace el set entero imposible de montar.

Lo que estas pruebas defienden es que la excepción sea *estrecha*: legal solo
cuando el macho y el agujero son la MISMA RECTA. Aceptar cualquier solapamiento
entre piezas de las que se insertan sería más fácil y dejaría al motor sin lo
que lo justifica: saber si un modelo se puede construir.

Las posiciones no están escritas a ojo. Salen de preguntarle al motor dónde
caen los puntos: la viga 3701 en el origen tiene agujeros a x=20, 40 y 60,
todos a z=14, con la recta (0,1,0).
"""

import unittest

from blockcad_engine import BlockModel, GridPosition, Orientation
from blockcad_engine.catalogos import cargar
from blockcad_engine.errors import CollisionError

#: El pin 2780 girado un cuarto de vuelta sobre z apunta en (0,1,0), como el
#: agujero. Puesto aquí, su punto cae en (20, -10, 14): sobre la recta del
#: primer agujero, y centrado a lo ancho de la viga.
PIN_EN_EL_PRIMER_AGUJERO = (12, -30, 6)
DE_LADO = Orientation.around("z", 90)


class InsercionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalogo = cargar("wedo")
        self.modelo = BlockModel(catalog=self.catalogo)
        self.viga = self.modelo.add("3701", GridPosition(0, 0, 0))

    def poner(self, pieza, posicion, orientacion=Orientation()):
        return self.modelo.add(
            pieza, GridPosition(*posicion), orientation=orientacion
        )

    # --- lo que tiene que entrar ------------------------------------------

    def test_a_pin_goes_into_a_hole(self) -> None:
        """El caso que bloqueaba el set entero: el paso 2 del camión.

        Sin esto no se puede montar ni la primera página de las instrucciones
        de ningún modelo WeDo.
        """
        self.poner("2780", PIN_EN_EL_PRIMER_AGUJERO, DE_LADO)

    def test_an_inserted_pin_is_connected(self) -> None:
        # Un pin metido casi nunca cae sobre el punto del agujero: entra por
        # él y se queda a otra profundidad. Lo que comparten es la recta.
        pin = self.poner("2780", PIN_EN_EL_PRIMER_AGUJERO, DE_LADO)
        unidas = self.modelo.connected_to(pin.instance_id)
        self.assertEqual([p.part_id for p in unidas], ["3701"])

    def test_the_same_pin_fits_every_hole_of_the_beam(self) -> None:
        # Los agujeros van cada 20 LDU: un módulo Technic.
        for salto in (0, 20, 40):
            with self.subTest(agujero=salto):
                modelo = BlockModel(catalog=self.catalogo)
                modelo.add("3701", GridPosition(0, 0, 0))
                x, y, z = PIN_EN_EL_PRIMER_AGUJERO
                modelo.add("2780", GridPosition(x + salto, y, z), orientation=DE_LADO)

    def test_an_axle_goes_through_a_beam(self) -> None:
        # Un eje no se mete: atraviesa, y sale por el otro lado. Es como se
        # montan los engranajes, así que sin esto no hay transmisión posible.
        modelo = BlockModel(catalog=self.catalogo)
        modelo.add("3702", GridPosition(0, 0, 0))  # viga 1x8
        eje = modelo.add("3706", GridPosition(14, -50, 8), orientation=DE_LADO)
        self.assertEqual(
            [p.part_id for p in modelo.connected_to(eje.instance_id)], ["3702"]
        )

    def test_an_axle_beside_the_hole_collides(self) -> None:
        modelo = BlockModel(catalog=self.catalogo)
        modelo.add("3702", GridPosition(0, 0, 0))
        with self.assertRaises(CollisionError):
            modelo.add("3706", GridPosition(14, -50, 12), orientation=DE_LADO)

    # --- lo que NO puede entrar -------------------------------------------

    def test_a_pin_beside_the_hole_still_collides(self) -> None:
        """Paralelo al agujero pero 4 LDU más arriba: atraviesa el plástico.

        Esta es la prueba que separa la regla honesta de la fácil. Es el mismo
        pin, en la misma dirección, dentro de la misma viga: lo único que falla
        es que su recta no es la del agujero. Si esto entrara, el motor habría
        dejado de saber si un modelo se puede construir.
        """
        x, y, z = PIN_EN_EL_PRIMER_AGUJERO
        with self.assertRaises(CollisionError):
            self.poner("2780", (x, y, z + 4), DE_LADO)

    def test_a_pin_between_two_holes_collides(self) -> None:
        # Los agujeros están cada 20; a mitad de camino no hay nada.
        x, y, z = PIN_EN_EL_PRIMER_AGUJERO
        with self.assertRaises(CollisionError):
            self.poner("2780", (x + 5, y, z), DE_LADO)

    def test_a_pin_across_the_beam_collides(self) -> None:
        # Sin girar, el pin apunta a lo largo de la viga: la recorre por
        # dentro en vez de entrar por un agujero.
        with self.assertRaises(CollisionError):
            self.poner("2780", (20, 2, 6))

    def test_two_beams_in_the_same_place_still_collide(self) -> None:
        # Las dos tienen agujeros, y los agujeros hasta coinciden. No sirve:
        # ninguna es el macho de la otra.
        with self.assertRaises(CollisionError):
            self.poner("3701", (0, 0, 0))

    def test_a_brick_inside_the_beam_still_collides(self) -> None:
        with self.assertRaises(CollisionError):
            self.poner("3001", (0, 0, 0))


class ApilarSigueIgualTests(unittest.TestCase):
    """Lo de siempre no se puede haber roto por el camino."""

    def setUp(self) -> None:
        self.modelo = BlockModel(catalog=cargar("wedo"))

    def test_bricks_still_stack(self) -> None:
        self.modelo.add("3001", GridPosition(0, 0, 0))
        self.modelo.add("3001", GridPosition(0, 0, 24))

    def test_two_bricks_in_the_same_place_still_collide(self) -> None:
        self.modelo.add("3001", GridPosition(0, 0, 0))
        with self.assertRaises(CollisionError):
            self.modelo.add("3001", GridPosition(0, 0, 0))

    def test_bricks_side_by_side_still_fit(self) -> None:
        # Se tocan y no se invaden: 40 LDU es justo el ancho de un 2x4.
        self.modelo.add("3001", GridPosition(0, 0, 0))
        self.modelo.add("3001", GridPosition(80, 0, 0))


if __name__ == "__main__":
    unittest.main()
