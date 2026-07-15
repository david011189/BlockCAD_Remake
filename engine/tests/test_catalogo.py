"""Pruebas del catálogo generado a partir del set 45300 y LDraw.

A diferencia de test_ldraw.py, estas no necesitan la biblioteca: el catálogo
se versiona, así que corren siempre. Comprueban el dato, no la herramienta.
"""

import json
import unittest
from pathlib import Path

_CATALOGO = (
    Path(__file__).resolve().parents[1]
    / "blockcad_engine"
    / "datos"
    / "catalogo_45300.json"
)

#: 1 LDU = 0,4 mm.
STUD = 20
PLACA = 8
LADRILLO = 24
ALTO_STUD = 4
MODULO_TECHNIC = 20
MEDIO_MODULO = 10


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.doc = json.loads(_CATALOGO.read_text(encoding="utf-8"))
        cls.piezas = {p["diseno"]: p for p in cls.doc["piezas"]}

    def test_it_is_a_versioned_format(self) -> None:
        self.assertEqual(self.doc["formato"], "blockcad-catalogo")
        self.assertEqual(self.doc["version"], 1)

    def test_known_measurements_are_right(self) -> None:
        # Un ladrillo mide 24 de alto más 4 de stud, y una placa 8 más 4.
        # Si esto falla, la extracción de LDraw se ha torcido.
        for diseno, esperado in [
            ("3003", [2 * STUD, LADRILLO + ALTO_STUD, 2 * STUD]),   # ladrillo 2x2
            ("3004", [2 * STUD, LADRILLO + ALTO_STUD, 1 * STUD]),   # ladrillo 1x2
            ("4282", [16 * STUD, PLACA + ALTO_STUD, 2 * STUD]),     # placa 2x16
        ]:
            with self.subTest(diseno=diseno):
                self.assertEqual(self.piezas[diseno]["medidas_ldu"], esperado)

    def test_the_wedo_electronics_are_in(self) -> None:
        for diseno, esperado in [
            ("19071", "Hub"),
            ("21980", "Medium Motor"),
            ("20841", "Tilt Sensor"),
            ("20844", "IR Distance Sensor"),
        ]:
            with self.subTest(diseno=diseno):
                self.assertIn(esperado, self.piezas[diseno]["nombre_ldraw"])

    def test_technic_holes_sit_on_a_half_module_grid(self) -> None:
        """Los agujeros de una pieza se separan por múltiplos de MEDIO módulo.

        Dos matices que costó aprender y que el motor tendrá que respetar:

        1. Lo que está en rejilla es la SEPARACIÓN, no la posición. El origen
           de una pieza no tiene por qué caer en un agujero: la baldosa 32530
           los tiene en y=-22 y y=-2, separados por 20 pero sin ser múltiplos.

        2. La rejilla es de medio módulo, no de módulo entero. La caja de
           engranajes 6588 tiene agujeros en x=±30, a media distancia, porque
           es por donde entra el tornillo sinfín. Con 20 LDU esta prueba
           fallaba solo para ella; con 10, ninguna de las 97 la rompe.

        Es decir: la rejilla Technic del motor tiene que ser de 10 LDU.
        """
        for pieza in self.doc["piezas"]:
            pines = [
                c["punto"] for c in pieza["conexiones"] if c["tipo"] == "agujero_pin"
            ]
            if not pines:
                continue
            for eje in range(3):
                valores = sorted({round(p[eje], 2) for p in pines})
                base = valores[0]
                with self.subTest(diseno=pieza["diseno"], eje="xyz"[eje]):
                    for valor in valores:
                        self.assertAlmostEqual((valor - base) % MEDIO_MODULO, 0, places=1)

    def test_every_part_carries_its_ldraw_licence(self) -> None:
        # Hay que atribuir a LDraw: la licencia debe viajar con cada pieza.
        for pieza in self.doc["piezas"]:
            with self.subTest(diseno=pieza["diseno"]):
                self.assertIn("CC BY", pieza["licencia"])

    def test_the_source_is_credited(self) -> None:
        self.assertIn("LDraw", self.doc["origen"]["geometria"])
        self.assertIn("CC BY", self.doc["origen"]["geometria"])

    def test_it_covers_most_of_the_set(self) -> None:
        resumen = self.doc["resumen"]
        self.assertEqual(resumen["piezas_en_el_set"], 280)
        self.assertGreaterEqual(resumen["piezas_en_el_catalogo"], 250)

    def test_what_is_missing_is_written_down(self) -> None:
        # Lo descartado no se calla: se explica, para que nadie crea que el
        # catálogo es la caja entera.
        descartadas = self.doc["descartadas"]
        self.assertTrue(descartadas["sin_forma_fija"])
        for pieza in descartadas["sin_forma_fija"]:
            self.assertIn("motivo", pieza)

    def test_beams_have_a_hole_every_module(self) -> None:
        vigas = [
            p for p in self.doc["piezas"] if "Technic Beam" in p.get("nombre_ldraw", "")
        ]
        self.assertTrue(vigas)
        for viga in vigas:
            zetas = sorted(
                {
                    c["punto"][2]
                    for c in viga["conexiones"]
                    if c["tipo"] == "agujero_pin"
                }
            )
            with self.subTest(viga=viga["nombre_ldraw"]):
                separaciones = {round(b - a, 1) for a, b in zip(zetas, zetas[1:])}
                self.assertEqual(separaciones, {20.0})

    def test_quantities_add_up_across_colours(self) -> None:
        # El catálogo cuenta moldes, no elementos: el ladrillo 2x2 sale en el
        # inventario dos veces, 4 negros y 2 azules, y aquí es uno con 6.
        ladrillo = self.piezas["3003"]
        self.assertEqual(ladrillo["cantidad"], 6)
        self.assertEqual(sorted(ladrillo["colores"]), ["Black", "Medium Azur"])
        self.assertTrue(all(p["cantidad"] >= 1 for p in self.doc["piezas"]))

    def test_the_total_matches_the_box(self) -> None:
        contadas = sum(p["cantidad"] for p in self.doc["piezas"])
        descartadas = sum(
            p["cantidad"]
            for lista in self.doc["descartadas"].values()
            for p in lista
        )
        self.assertEqual(contadas + descartadas, self.doc["resumen"]["piezas_en_el_set"])


if __name__ == "__main__":
    unittest.main()
