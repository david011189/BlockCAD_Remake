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


class MachoYHembraTests(unittest.TestCase):
    """Lo que se mete y lo que aloja.

    Technic no se apila: se inserta. Un pin entra en un agujero y un eje
    atraviesa una viga. Para que el motor pueda distinguir esa unión de un
    choque hace falta saber cuál de las dos piezas es cuál, y eso se decide
    aquí, en el dato.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.piezas = {
            p["diseno"]: p
            for p in json.loads(_CATALOGO.read_text(encoding="utf-8"))["piezas"]
        }

    def conexiones(self, diseno, tipo):
        return [
            c["punto"] for c in self.piezas[diseno]["conexiones"] if c["tipo"] == tipo
        ]

    def test_an_axle_has_no_holes(self) -> None:
        """Un eje es macizo. Parece obvio y estuvo mal mucho tiempo.

        `axlehol8.dat` se llama «Technic Axle Perimeter»: es el perfil en cruz
        de un eje, y LDraw lo usa igual para el eje macizo que para el hueco
        que lo aloja. Estaba mapeado a `agujero_eje`, así que seis ejes de
        este set salían del catálogo con un agujero que no existe.
        """
        for diseno in ("3706", "3737", "4519", "44294", "87083", "32062"):
            with self.subTest(eje=diseno):
                self.assertEqual(self.conexiones(diseno, "agujero_eje"), [])

    def test_an_axle_is_as_long_as_its_name_says(self) -> None:
        # Las dos puntas de un eje de N módulos están a N x 20 LDU. Es la
        # comprobación que delata si las puntas se detectan donde no son.
        for diseno, modulos in (("4519", 3), ("3706", 6), ("44294", 7), ("3737", 10)):
            with self.subTest(eje=diseno):
                puntas = self.conexiones(diseno, "punta_eje")
                self.assertEqual(len(puntas), 2, "un eje tiene dos puntas")
                largo = max(abs(a - b) for a, b in zip(*puntas))
                self.assertEqual(largo, modulos * MODULO_TECHNIC)

    def test_an_axle_with_a_stop_has_only_one_end(self) -> None:
        # El 87083 lleva tope en un extremo: por ahí no entra en ningún sitio.
        self.assertEqual(len(self.conexiones("87083", "punta_eje")), 1)

    def test_the_gears_have_their_axle_hole(self) -> None:
        """Sin agujero, un engranaje no puede recibir su eje.

        LDraw dibuja el agujero de los engranajes con la familia «Reduced»
        (axl2hole y compañía), que son agujeros igual de reales con menos
        plástico alrededor. No estaban en el mapa y las ruedas dentadas salían
        del catálogo sin ninguna conexión: piezas que no se unían a nada.
        """
        for diseno in ("32270", "32905", "42136", "59443"):
            with self.subTest(pieza=diseno):
                self.assertTrue(self.conexiones(diseno, "agujero_eje"))

    def test_the_24_tooth_gear_still_has_no_hole(self) -> None:
        # El de 24 dientes dibuja su cruz con geometría cruda, sin primitiva:
        # no hay nada que detectar. Documentarlo evita buscar el fallo donde
        # no está; si LDraw lo arregla algún día, esta prueba avisará.
        self.assertEqual(self.conexiones("24505", "agujero_eje"), [])

    def test_the_pins_are_male(self) -> None:
        # Sin esto un pin no se puede unir a nada: no tiene agujeros ni studs
        # que detectar, y el catálogo lo daba como pieza sin conexiones.
        for diseno in ("2780", "6562", "18651"):
            with self.subTest(pin=diseno):
                self.assertTrue(self.conexiones(diseno, "pin"))

    def test_a_beam_is_female_and_keeps_its_holes(self) -> None:
        # La otra mitad no se puede romper al arreglar esta: una viga 1x4
        # tiene 3 agujeros, y cada uno asoma por las dos caras.
        self.assertEqual(len(self.conexiones("3701", "agujero_pin")), 6)
        self.assertEqual(len(self.conexiones("3700", "agujero_pin")), 2)

    def test_a_part_is_not_male_and_female_at_the_same_place(self) -> None:
        # Un mismo punto no puede ser el pin y el agujero donde entra: si sale
        # así, una primitiva se está leyendo por las dos caras.
        for diseno, pieza in self.piezas.items():
            machos = {
                tuple(c["punto"]) for c in pieza["conexiones"]
                if c["tipo"] in ("pin", "punta_eje")
            }
            hembras = {
                tuple(c["punto"]) for c in pieza["conexiones"]
                if c["tipo"] in ("agujero_pin", "agujero_eje")
            }
            with self.subTest(pieza=diseno):
                self.assertEqual(machos & hembras, set())


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
