"""Pruebas del lector de LDraw.

Necesitan la biblioteca de piezas, que son 136 MB y no se versionan. Si no
está descargada, las pruebas se saltan en vez de fallar: quien clone el
repositorio no tiene por qué bajarse la biblioteca para trabajar en el motor.

    curl -L -o .ldraw-cache/complete.zip \\
        https://library.ldraw.org/library/updates/complete.zip
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "herramientas"))

from ldraw import LADRILLO, PLACA, STUD, Biblioteca, Matriz, Punto  # noqa: E402

_ZIP = Path(__file__).resolve().parents[2] / ".ldraw-cache" / "complete.zip"
_HAY_BIBLIOTECA = _ZIP.is_file()


class MatrixTests(unittest.TestCase):
    """La composición no necesita la biblioteca: es aritmética."""

    def test_identity_changes_nothing(self) -> None:
        p = Punto(1, 2, 3)
        self.assertEqual(Matriz().aplicar(p), p)

    def test_translation(self) -> None:
        m = Matriz(x=10, y=20, z=30)
        self.assertEqual(m.aplicar(Punto(1, 2, 3)), Punto(11, 22, 33))

    def test_composing_rotates_the_child_translation(self) -> None:
        # Una subpieza girada 90° con su agujero a 20 de distancia: el agujero
        # tiene que acabar girado también, no sumado tal cual.
        madre = Matriz(a=0, c=1, g=-1, i=0)          # 90° sobre Y
        hija = Matriz(x=20)                          # desplazada en X
        compuesta = madre.componer(hija)
        self.assertAlmostEqual(compuesta.x, 0)
        self.assertAlmostEqual(compuesta.z, -20)

    def test_composing_keeps_the_parent_translation(self) -> None:
        compuesta = Matriz(x=5, y=5, z=5).componer(Matriz(x=1, y=2, z=3))
        self.assertEqual((compuesta.x, compuesta.y, compuesta.z), (6, 7, 8))


@unittest.skipUnless(_HAY_BIBLIOTECA, "falta .ldraw-cache/complete.zip")
class LibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.biblioteca = Biblioteca(str(_ZIP))

    def test_a_tile_measures_exactly_one_plate(self) -> None:
        # Una baldosa no tiene studs, así que su malla sí coincide con la
        # medida oficial: 1x1 studs y 1 placa de alto.
        ancho, alto, fondo = self.biblioteca.analizar("3070b.dat").medidas()
        self.assertAlmostEqual(ancho, STUD, delta=1)
        self.assertAlmostEqual(alto, PLACA, delta=1)
        self.assertAlmostEqual(fondo, STUD, delta=1)

    def test_a_brick_mesh_includes_its_studs(self) -> None:
        # 24 LDU de ladrillo más 4 de stud. Por eso la caja de la malla no
        # sirve como caja de colisión: los studs entran en la pieza de arriba.
        _, alto, _ = self.biblioteca.analizar("3001.dat").medidas()
        self.assertAlmostEqual(alto, LADRILLO + 4, delta=1)

    def test_holes_are_found_through_nested_subparts(self) -> None:
        # La Viga 5 no nombra sus agujeros: los esconde en s/32316s01.dat.
        # Sin recursión aquí saldría 0.
        viga = self.biblioteca.analizar("32316.dat")
        centros = {
            round(c.punto.z, 1)
            for c in viga.conexiones
            if c.tipo == "agujero_pin"
        }
        self.assertEqual(sorted(centros), [-40.0, -20.0, 0.0, 20.0, 40.0])

    def test_holes_sit_on_the_technic_module_grid(self) -> None:
        ladrillo = self.biblioteca.analizar("3894.dat")
        centros = sorted(
            {round(c.punto.x, 1) for c in ladrillo.conexiones if c.tipo == "agujero_pin"}
        )
        separaciones = {
            round(b - a, 1) for a, b in zip(centros, centros[1:])
        }
        self.assertEqual(separaciones, {20.0})

    def test_an_L_beam_has_holes_on_two_axes(self) -> None:
        viga = self.biblioteca.analizar("32526.dat")
        puntos = {
            (round(c.punto.x, 1), round(c.punto.z, 1))
            for c in viga.conexiones
            if c.tipo == "agujero_pin"
        }
        self.assertEqual(len(puntos), 7)
        self.assertGreater(len({x for x, _ in puntos}), 1)
        self.assertGreater(len({z for _, z in puntos}), 1)

    def test_the_wedo_electronics_are_available(self) -> None:
        for numero, esperado in [
            ("19071", "Hub"),
            ("21980", "Medium Motor"),
            ("20841", "Tilt Sensor"),
            ("20844", "IR Distance Sensor"),
        ]:
            with self.subTest(numero=numero):
                nombre, palabras, _ = self.biblioteca.cabecera(f"{numero}.dat")
                self.assertIn(esperado, nombre)
                self.assertTrue(any("WeDo" in p for p in palabras))

    def test_parts_carry_their_license(self) -> None:
        # Hay que atribuir a LDraw, así que la licencia debe viajar con el dato.
        _, _, licencia = self.biblioteca.cabecera("19071.dat")
        self.assertIn("CC BY", licencia)


if __name__ == "__main__":
    unittest.main()
