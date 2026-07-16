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


class EncajeTipadoTests(unittest.TestCase):
    """No todo macho entra en todo agujero.

    Un eje pasa por el agujero redondo (gira libre: así se cuelgan las ruedas)
    y por el de cruz (gira solidario: así se mueven los engranajes). Un pin
    solo cabe en el redondo: la cruz le cierra el paso al cilindro. Sin este
    tipado, el motor aceptaría uniones que en plástico no existen.
    """

    def setUp(self) -> None:
        self.modelo = BlockModel(catalog=cargar("wedo"))

    def test_a_pin_does_not_fit_a_cross_hole(self) -> None:
        # El engranaje 10928 tiene su agujero de cruz en (12,0,12) con recta
        # (0,1,0). El pin girado apunta igual y su recta pasa por ahí: la
        # geometría es la de una inserción perfecta. Falla por el TIPO.
        self.modelo.add("10928", GridPosition(0, 0, 0))
        with self.assertRaises(CollisionError):
            self.modelo.add("2780", GridPosition(4, -8, 4), orientation=DE_LADO)

    def test_an_axle_does_fit_a_cross_hole(self) -> None:
        # La misma recta, el macho que sí cabe.
        self.modelo.add("10928", GridPosition(0, 0, 0))
        self.modelo.add("4519", GridPosition(6, -20, 6), orientation=DE_LADO)


class LenguajeTests(unittest.TestCase):
    """Insertar sin calcular LDU: «en el agujero 2 de marco».

    Quien escribe dice qué unión quiere y el motor resuelve giro y posición,
    igual que `encima` resuelve la altura. Antes de esto, meter un pin exigía
    saber que el agujero cae en z=14 LDU y escribir `2780 en 0.6,-1.5,0.75
    rot z 90`, que no es un lenguaje: es una calculadora.
    """

    def compilar(self, codigo: str) -> BlockModel:
        from blockcad_engine import parse_model

        return parse_model('catalogo "wedo"\n' + codigo)

    def test_the_truck_step_two_compiles_as_written(self) -> None:
        # Las instrucciones reales del camión de reciclaje: el ladrillo
        # naranja, el verde con agujeros encima, y dos pines metidos. Es el
        # paso que descubrió todo esto.
        modelo = self.compilar(
            "3001 en 0,0,0 llamado base\n"
            "3701 encima de base llamado verde\n"
            "2780 en el agujero 1 de verde\n"
            "2780 en el agujero 3 de verde"
        )
        self.assertEqual(len(modelo.instances), 4)

    def test_the_pin_lands_centered_in_the_hole(self) -> None:
        # La viga en el origen tiene su primer agujero en x=20, z=14, cruzando
        # el fondo. El pin (40 de largo) queda centrado: asoma 10 por cada
        # cara, listo para recibir otra viga.
        modelo = self.compilar("3701 en 0,0,0 llamado v\n2780 en el agujero 1 de v")
        pin = modelo.instances[-1]
        definicion = modelo.catalog.get("2780")
        macho = [c for c in pin.world_connections(definicion) if c.es_macho][0]
        self.assertEqual(macho.punto, (20, 10, 14))

    def test_displacement_slides_along_the_line(self) -> None:
        # `desplazado 0.5` son 10 LDU por la recta del agujero, no por x.
        modelo = self.compilar(
            "3701 en 0,0,0 llamado v\n"
            "2780 en el agujero 1 de v desplazado 0.5"
        )
        pin = modelo.instances[-1]
        definicion = modelo.catalog.get("2780")
        macho = [c for c in pin.world_connections(definicion) if c.es_macho][0]
        self.assertEqual(macho.punto, (20, 20, 14))

    def test_holes_are_numbered_by_position(self) -> None:
        # Agujeros 1, 2 y 3 de la viga: x=20, 40, 60. El número se puede
        # contar mirando el visor.
        for numero, x in ((1, 20), (2, 40), (3, 60)):
            with self.subTest(agujero=numero):
                modelo = self.compilar(
                    f"3701 en 0,0,0 llamado v\n2780 en el agujero {numero} de v"
                )
                pin = modelo.instances[-1]
                definicion = modelo.catalog.get("2780")
                macho = [
                    c for c in pin.world_connections(definicion) if c.es_macho
                ][0]
                self.assertEqual(macho.punto[0], x)

    def test_without_a_name_it_uses_the_last_piece(self) -> None:
        self.compilar("3701 en 0,0,0\n2780 en el agujero 2")

    def test_an_axle_goes_through_a_round_hole_too(self) -> None:
        self.compilar("3701 en 0,0,0 llamado v\n4519 en el agujero 2 de v")

    def test_the_errors_teach(self) -> None:
        # Cada error dice qué está mal Y qué hacer. Se comprueba el contenido,
        # no la frase exacta: la redacción puede mejorar sin romper nada.
        from blockcad_engine.errors import DslError

        casos = (
            ("3701 en 0,0,0 llamado v\n2780 en el agujero 9 de v", "3 agujero"),
            ("3701 en 0,0,0 llamado v\n3001 en el agujero 1 de v", "nada que meter"),
            ("10928 en 0,0,0 llamado g\n2780 en el agujero 1 de g", "cruz"),
            ("3701 en 0,0,0 llamado v\n2780 en el agujero 1 de v rot x 90", "giro"),
            ("3001 en 0,0,0 llamado b\n2780 en el agujero 1 de b", "no tiene agujeros"),
        )
        for codigo, pista in casos:
            with self.subTest(pista=pista):
                with self.assertRaises(DslError) as ctx:
                    self.compilar(codigo)
                self.assertIn(pista, str(ctx.exception))

    def test_the_result_survives_the_round_trip(self) -> None:
        # El código generado desde el modelo usa `en x,y,z` con decimales.
        # Tiene que volver a compilar y dejar las piezas donde estaban.
        from blockcad_engine.dsl import model_to_source, parse_model

        modelo = self.compilar(
            "3701 en 0,0,0 llamado v\n2780 en el agujero 1 de v"
        )
        texto = 'catalogo "wedo"\n' + model_to_source(modelo)
        segundo = parse_model(texto)
        self.assertEqual(
            [(p.part_id, p.position) for p in modelo.instances],
            [(p.part_id, p.position) for p in segundo.instances],
        )


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
