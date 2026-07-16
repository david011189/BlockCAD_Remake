"""Pruebas de la carga del catálogo del set en el motor.

No necesitan la biblioteca de LDraw: el catálogo generado se versiona.
"""

import unittest

from blockcad_engine import (
    BlockModel,
    CollisionError,
    DslError,
    GridPosition,
    InvalidFormatError,
    PartCatalog,
    parse_model,
)
from blockcad_engine.catalogos import cargar, cargar_desde_archivo
from blockcad_engine.geometry import LADRILLO, PLACA, STUD


class LoadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalogo = cargar("wedo")

    def test_it_loads_the_whole_set(self) -> None:
        self.assertEqual(len(self.catalogo.all()), 97)

    def test_each_load_is_independent(self) -> None:
        # Devolver un catálogo cacheado daría el mismo objeto a todos, y
        # registrar una pieza en un modelo la metería en los demás.
        uno, otro = cargar("wedo"), cargar("wedo")
        self.assertIsNot(uno, otro)

    def test_an_unknown_catalog_says_which_ones_hay(self) -> None:
        with self.assertRaises(InvalidFormatError) as capturado:
            cargar("marte")
        self.assertIn("wedo", str(capturado.exception))

    def test_a_file_that_is_not_a_catalog_is_rejected(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "otro.json"
            ruta.write_text('{"formato": "otra cosa"}', encoding="utf-8")
            with self.assertRaises(InvalidFormatError):
                cargar_desde_archivo(ruta)


class MeasurementTests(unittest.TestCase):
    """Las medidas tienen que ser las de LEGO, no las de la malla."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalogo = cargar("wedo")

    def test_a_brick_is_a_brick(self) -> None:
        # El nombre manda: "Brick 2 x 4" son 2 studs de ancho en X, aunque
        # LDraw lo dibuje acostado. Igual que brick_2x4 en el catálogo básico.
        ladrillo = self.catalogo.get("3001")
        self.assertEqual(
            (
                ladrillo.dimensions.width,
                ladrillo.dimensions.depth,
                ladrillo.dimensions.height,
            ),
            (2 * STUD, 4 * STUD, LADRILLO),
        )

    def test_the_studs_are_not_counted(self) -> None:
        # La malla de un ladrillo mide 28 de alto porque incluye los studs.
        # Si esa fuera la caja, apilar sería imposible.
        self.assertEqual(self.catalogo.get("3001").dimensions.height, LADRILLO)
        self.assertEqual(self.catalogo.get("3023").dimensions.height, PLACA)

    def test_two_real_bricks_can_be_stacked(self) -> None:
        # La prueba de fondo: si la caja llevara los studs, esto chocaría.
        modelo = BlockModel(catalog=cargar("wedo"))
        modelo.add("3001", GridPosition(0, 0, 0))
        modelo.add("3001", GridPosition(0, 0, LADRILLO))
        self.assertEqual(len(modelo.instances), 2)

    def test_the_wedo_hub_is_the_right_size(self) -> None:
        # El Smart Hub mide 6x8 studs y 3 ladrillos de alto.
        hub = self.catalogo.get("19071")
        self.assertEqual(hub.dimensions.width, 6 * STUD)
        self.assertEqual(hub.dimensions.depth, 8 * STUD)
        self.assertEqual(hub.dimensions.height, 3 * LADRILLO)

    def test_a_beam_is_long_and_thin(self) -> None:
        viga = self.catalogo.get("beam_7")
        self.assertLess(viga.dimensions.width, STUD)
        self.assertGreater(viga.dimensions.depth, 6 * STUD)

    def test_every_part_has_a_real_volume(self) -> None:
        for definicion in self.catalogo.all():
            with self.subTest(pieza=definicion.part_id):
                self.assertGreater(definicion.dimensions.width, 0)
                self.assertGreater(definicion.dimensions.depth, 0)
                self.assertGreater(definicion.dimensions.height, 0)


class ConventionTests(unittest.TestCase):
    """El nombre manda: `brick_2x4` mide lo mismo en cualquier catálogo.

    LDraw dibuja el lado largo en X y el catálogo del set hereda esa
    orientación, así que sin la convención el mismo código colocaría las
    piezas giradas según el catálogo elegido.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.wedo = cargar("wedo")
        cls.basico = PartCatalog.with_basic_parts()

    def test_shared_aliases_measure_the_same(self) -> None:
        compartidas = [
            basica
            for basica in self.basico.all()
            if self.wedo.contains(basica.part_id)
        ]
        # Si el set dejara de traer piezas con nombre corto, esta prueba
        # pasaría sin comprobar nada y nadie se enteraría.
        self.assertGreaterEqual(len(compartidas), 4)
        for basica in compartidas:
            with self.subTest(pieza=basica.part_id):
                real = self.wedo.get(basica.part_id)
                self.assertEqual(real.dimensions, basica.dimensions)

    def test_the_turned_studs_land_on_the_2x4_grid(self) -> None:
        # Girar la caja sin girar las conexiones dejaría los studs fuera de
        # la pieza. Esta es la malla de studs de un 2x4 de verdad.
        ladrillo = self.wedo.get("brick_2x4")
        studs = sorted(
            c.punto for c in ladrillo.connections if c.tipo == "stud"
        )
        self.assertEqual(
            studs,
            [
                (x, y, LADRILLO)
                for x in (10, 30)
                for y in (10, 30, 50, 70)
            ],
        )

    def test_every_named_part_keeps_its_points_inside(self) -> None:
        for definicion in self.wedo.all():
            if definicion.category not in ("brick", "plate", "tile"):
                continue
            caja = definicion.dimensions
            for conexion in definicion.connections:
                with self.subTest(pieza=definicion.part_id, punto=conexion.punto):
                    x, y, z = conexion.punto
                    self.assertTrue(0 <= x <= caja.width)
                    self.assertTrue(0 <= y <= caja.depth)
                    self.assertTrue(0 <= z <= caja.height)

    def test_every_linear_part_lies_along_y(self) -> None:
        # Viga y eje se nombran con UN número: no hay "2x4" que mande, así
        # que la postura hay que decidirla. Una pieza lineal se tumba a lo
        # largo de Y, como ya venía la viga; los ejes llegaban a lo largo
        # de X y se enderezan al cargar.
        lineales = [
            definicion
            for definicion in self.wedo.all()
            if any(
                alias.startswith(("beam_", "axle_"))
                for alias in definicion.aliases
            )
        ]
        self.assertGreaterEqual(len(lineales), 5)
        for definicion in lineales:
            with self.subTest(pieza=definicion.part_id):
                self.assertGreater(
                    definicion.dimensions.depth, definicion.dimensions.width
                )

    def test_technic_bricks_obey_their_name_too(self) -> None:
        # "Technic Brick 1 x 4 with Holes" no gana alias —se escribe por su
        # molde, como en las instrucciones—, pero su postura también la manda
        # el nombre: 1 stud de ancho en X. Sin esto, el paso 1 del camión de
        # reciclaje dejaba el ladrillo de agujeros cruzado sobre la base.
        ladrillo = self.wedo.get("3701")
        self.assertEqual(
            (ladrillo.dimensions.width, ladrillo.dimensions.depth),
            (1 * STUD, 4 * STUD),
        )
        for numero in ("3700", "3701", "3702", "3703", "3895", "31493"):
            with self.subTest(pieza=numero):
                pieza = self.wedo.get(numero)
                self.assertLess(pieza.dimensions.width, pieza.dimensions.depth)

    def test_a_turned_axle_keeps_its_line_along_y(self) -> None:
        # Girar la caja sin girar la recta dejaría el eje atravesado dentro
        # de sí mismo: nada podría insertarse por él.
        eje = self.wedo.get("axle_6")
        for conexion in eje.connections:
            with self.subTest(tipo=conexion.tipo):
                self.assertEqual(conexion.eje, (0.0, 1.0, 0.0))

    def test_the_base_of_the_house_builds_in_both_catalogs(self) -> None:
        # Las dos primeras líneas del ejemplo del editor: dos ladrillos 2x4
        # que se tocan sin chocar. Antes de la convención, en el catálogo
        # wedo chocaban.
        base = "ladrillo 2x4 en 0,0,0\nladrillo 2x4 en 2,0,0"
        for encabezado in ("", 'catalogo "wedo"\n'):
            with self.subTest(catalogo=encabezado.strip() or "basico"):
                modelo = parse_model(encabezado + base)
                self.assertEqual(len(modelo.instances), 2)


class NamingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalogo = cargar("wedo")

    def test_a_part_answers_to_its_mould_number(self) -> None:
        # Es el número que sale en cualquier inventario o instrucción.
        self.assertEqual(self.catalogo.get("3001").name, "Brick 2 x 4")

    def test_and_also_to_a_readable_alias(self) -> None:
        self.assertIs(self.catalogo.get("brick_2x4"), self.catalogo.get("3001"))
        self.assertIs(self.catalogo.get("beam_7"), self.catalogo.get("32524"))

    def test_redirected_names_were_resolved(self) -> None:
        # 3023 es un "~Moved to 3023b" en LDraw: el nombre tenía que seguir
        # la redirección o el catálogo diría "~Moved to 3023b".
        self.assertEqual(self.catalogo.get("3023").name, "Plate 1 x 2")
        self.assertEqual(self.catalogo.get("3023").metadata["ldraw"], "3023b")

    def test_no_name_carries_ldraw_markers(self) -> None:
        for definicion in self.catalogo.all():
            with self.subTest(pieza=definicion.part_id):
                self.assertNotIn("Moved to", definicion.name)
                self.assertFalse(definicion.name.startswith("="))

    def test_the_electronics_are_recognisable(self) -> None:
        for numero in ("19071", "21980", "20841", "20844"):
            with self.subTest(numero=numero):
                self.assertEqual(self.catalogo.get(numero).category, "electronica")

    def test_it_remembers_how_many_are_in_the_box(self) -> None:
        self.assertEqual(self.catalogo.get("3001").metadata["cantidad_en_el_set"], "6")


class LanguageTests(unittest.TestCase):
    """El catálogo se elige desde el propio código."""

    def test_the_default_catalog_is_still_the_basic_one(self) -> None:
        # El código escrito hasta ahora no debe cambiar de significado.
        modelo = parse_model("ladrillo 2x4 en 0,0,0")
        self.assertEqual(modelo.instances[0].part_id, "brick_2x4")

    def test_declaring_the_catalog_changes_the_parts(self) -> None:
        modelo = parse_model('catalogo "wedo"\nladrillo 2x4 en 0,0,0')
        # Ahora es la pieza real del set, no la idealizada.
        self.assertEqual(modelo.instances[0].part_id, "3001")

    def test_a_beam_can_finally_be_written(self) -> None:
        modelo = parse_model('catalogo "wedo"\nviga 7 en 0,0,0')
        self.assertEqual(modelo.instances[0].part_id, "32524")

    def test_an_axle_too(self) -> None:
        modelo = parse_model('catalogo "wedo"\neje 6 en 0,0,0')
        self.assertEqual(modelo.instances[0].part_id, "3706")

    def test_a_part_can_be_written_by_its_number(self) -> None:
        # El hub no tiene nombre corto: se escribe como en la caja.
        modelo = parse_model('catalogo "wedo"\n19071 en 0,0,0')
        self.assertEqual(modelo.instances[0].part_id, "19071")

    def test_the_catalog_goes_before_the_model_name(self) -> None:
        modelo = parse_model('catalogo "wedo"\nmodelo "Robot"\nviga 7 en 0,0,0')
        self.assertEqual(modelo.name, "Robot")
        self.assertEqual(len(modelo.instances), 1)

    def test_a_late_catalog_line_is_rejected(self) -> None:
        with self.assertRaises(DslError) as capturado:
            parse_model('ladrillo 2x4 en 0,0,0\ncatalogo "wedo"')
        self.assertEqual(capturado.exception.line, 2)

    def test_an_unknown_catalog_reports_its_line(self) -> None:
        with self.assertRaises(DslError) as capturado:
            parse_model('catalogo "marte"\nladrillo 2x4 en 0,0,0')
        self.assertEqual(capturado.exception.line, 1)

    def test_a_part_that_is_not_in_the_box_is_reported(self) -> None:
        # El set de WeDo no trae ladrillos 1x1: es un set de robótica.
        with self.assertRaises(DslError) as capturado:
            parse_model('catalogo "wedo"\nladrillo 1x1 en 0,0,0')
        self.assertIn("brick_1x1", capturado.exception.message)

    def test_real_parts_collide_like_any_other(self) -> None:
        with self.assertRaises(DslError) as capturado:
            parse_model('catalogo "wedo"\nviga 7 en 0,0,0\nviga 7 en 0,0,0')
        self.assertEqual(capturado.exception.line, 3)

    def test_the_code_wins_over_python(self) -> None:
        # Si el código declara su catálogo, manda el código: se describe a sí
        # mismo. El `catalog=` de Python es el valor por defecto para cuando
        # el código no dice nada. Ignorar la línea en silencio sería peor.
        modelo = parse_model(
            'catalogo "wedo"\nladrillo 2x4 en 0,0,0',
            catalog=PartCatalog.with_basic_parts(),
        )
        self.assertEqual(modelo.instances[0].part_id, "3001")

    def test_python_decides_when_the_code_says_nothing(self) -> None:
        modelo = parse_model("ladrillo 2x4 en 0,0,0", catalog=cargar("wedo"))
        self.assertEqual(modelo.instances[0].part_id, "3001")


if __name__ == "__main__":
    unittest.main()
