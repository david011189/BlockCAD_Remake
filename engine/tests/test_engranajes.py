"""Dos ruedas dentadas engranadas se solapan de verdad.

Los dientes de una entran en los huecos de la otra: las cajas se pisan y no
hay macho ni hembra que lo justifique. Es la tercera manera legal de
solaparse, y la condición es geométrica: ejes paralelos separados EXACTAMENTE
por la suma de los radios primitivos, a 1,25 LDU por diente. De ahí salen
todas las parejas del sistema: 8+8 a 20 LDU (un módulo justo), 12+12 a 30,
8+12 a 25.

Las ruedas van colocadas directamente, sin ejes: a la regla solo le importa
la recta del agujero de cada una, y así cada prueba dice una sola cosa.
"""

import unittest

from blockcad_engine import BlockModel, GridPosition, Orientation
from blockcad_engine.catalogos import cargar
from blockcad_engine.errors import CollisionError

#: Con este giro el agujero de la rueda queda a lo largo de y.
DE_LADO = Orientation.around("x", 90)


class MordidaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.modelo = BlockModel(catalog=cargar("wedo"))

    def par(self, a, b, separacion_x):
        """Dos ruedas con los ejes paralelos, separados en x."""
        self.modelo.add(a, GridPosition(0, 0, 40), orientation=DE_LADO)
        primera = self.modelo.instances[-1]
        eje_a = [
            c
            for c in primera.world_connections(self.modelo.catalog.get(a))
            if c.tipo == "agujero_eje"
        ][0]
        # La segunda, con su agujero exactamente a `separacion_x` del primero.
        segunda = BlockModel(catalog=self.modelo.catalog)
        colocada = segunda.add(b, GridPosition(0, 0, 40), orientation=DE_LADO)
        eje_b = [
            c
            for c in colocada.world_connections(self.modelo.catalog.get(b))
            if c.tipo == "agujero_eje"
        ][0]
        destino = (eje_a.punto[0] + separacion_x, eje_a.punto[1], eje_a.punto[2])
        self.modelo.add(
            b,
            GridPosition(*(g + d - p for g, d, p in zip(
                (0, 0, 40), destino, eje_b.punto
            ))),
            orientation=DE_LADO,
        )

    def test_two_eights_bite_at_one_module(self) -> None:
        # 8 + 8: radios 10 y 10. Un módulo justo: la pareja más común.
        self.par("10928", "10928", 20)

    def test_two_twelves_bite_at_thirty(self) -> None:
        # 12 + 12: radios 15 y 15. Módulo y medio: la rejilla de medio módulo
        # existe justo para esto.
        self.par("32270", "32270", 30)

    def test_eight_and_twelve_bite_at_twentyfive(self) -> None:
        self.par("10928", "32270", 25)

    def test_too_close_the_teeth_jam(self) -> None:
        # 12 + 12 a un módulo: los dientes chocan de frente. Si esto pasara,
        # la regla sería «los engranajes no chocan nunca», que es la vía
        # barata con otro nombre.
        with self.assertRaises(CollisionError):
            self.par("32270", "32270", 20)

    def test_crossed_axles_do_not_bite(self) -> None:
        # La misma distancia, pero una rueda girada: ejes perpendiculares.
        # Las cónicas muerden así en la realidad, pero con OTRA geometría;
        # fingir que esta regla las cubre sería mentir.
        self.modelo.add("10928", GridPosition(0, 0, 40), orientation=DE_LADO)
        with self.assertRaises(CollisionError):
            self.modelo.add("10928", GridPosition(15, 2, 40))

    def test_a_gear_does_not_bite_a_bush(self) -> None:
        # El bush tiene agujero de eje y no tiene dientes: solaparse con él
        # sigue siendo un choque.
        self.modelo.add("10928", GridPosition(0, 0, 40), orientation=DE_LADO)
        with self.assertRaises(CollisionError):
            self.modelo.add("42798", GridPosition(10, 0, 40), orientation=DE_LADO)


class LaBocaTests(unittest.TestCase):
    """El modelo que pidió el usuario: engranajes que muerden como una boca."""

    def test_the_mouth_compiles(self) -> None:
        from blockcad_engine import parse_model

        modelo = parse_model(
            'catalogo "wedo"\n'
            "viga 7 en 0,0,3 rot x 90 llamado chasis\n"
            "eje 6 en el agujero 2 de chasis llamado eje1\n"
            "eje 6 en el agujero 3 de chasis llamado eje2\n"
            "10928 en el eje de eje1 desplazado -1.5\n"
            "10928 en el eje de eje2 desplazado -1.5"
        )
        self.assertEqual(len(modelo.instances), 5)
        self.assertFalse(modelo.floating())


class CremalleraTests(unittest.TestCase):
    """La cremallera es una rueda de radio infinito: linea de paso a 12
    LDU de su base (dientes de 9 a 14 en su malla, perfil complementario
    del engranaje). Muerde cuando sus crestas corren paralelas al eje de
    la rueda, sus dientes la MIRAN, y el eje queda al radio primitivo de
    la linea."""

    #: El tren del sinfin entero: caja, gusano dentro, engranaje coronando.
    def setUp(self) -> None:
        self.modelo = BlockModel(catalog=cargar("wedo"))
        self.modelo.add("28698", GridPosition(100, 100, 40))
        self.modelo.add(
            "32905", GridPosition(120, 107, 49), orientation=Orientation.z(90)
        )
        self.modelo.add("24505", GridPosition(108, 110, 70))

    #: Media vuelta sobre x: los dientes miran al suelo.
    VOLTEADA = Orientation.around("x", 180)

    def test_the_rack_rides_the_crowned_gear(self) -> None:
        # Volteada sobre el engranaje que asoma de la caja: su linea de
        # paso (a 12 de la base, ahora hacia abajo) tangente al circulo de
        # radio 30. Eje de la rueda en z=102, cremallera en z=130: 102 =
        # 130 + 2 - 30. Se solapan de verdad y quedan UNIDAS: no flota.
        barra = self.modelo.add(
            "3743", GridPosition(100, 110, 130), orientation=self.VOLTEADA
        )
        unidas = self.modelo.connected_to(barra.instance_id)
        self.assertEqual([p.part_id for p in unidas], ["24505"])
        self.assertFalse(self.modelo.floating())

    def test_one_ldu_closer_the_teeth_crash(self) -> None:
        with self.assertRaises(CollisionError):
            self.modelo.add(
                "3743", GridPosition(100, 110, 129), orientation=self.VOLTEADA
            )

    def test_teeth_must_face_the_wheel(self) -> None:
        # Sin voltear, a la misma altura: los dientes miran al cielo y lo
        # que toca la rueda es la espalda de la barra. Choque.
        with self.assertRaises(CollisionError):
            self.modelo.add("3743", GridPosition(100, 110, 130))

    def test_crossed_ridges_do_not_mesh(self) -> None:
        # Volteada pero girada un cuarto: las crestas cruzan el eje de la
        # rueda en vez de correr paralelas. Asi no muerde nada.
        cruzada = Orientation.around("x", 180).then(Orientation.z(90))
        with self.assertRaises(CollisionError):
            self.modelo.add(
                "3743", GridPosition(110, 100, 130), orientation=cruzada
            )


if __name__ == "__main__":
    unittest.main()
