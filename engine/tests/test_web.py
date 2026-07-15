import re
import unittest
from pathlib import Path

import blockcad_web
from blockcad_engine import parse_model
from blockcad_web.server import EJEMPLO, compile_source, model_to_scene

_WEB = Path(blockcad_web.__file__).parent


class SceneTests(unittest.TestCase):
    """El navegador no conoce el catálogo: la escena debe llegar resuelta."""

    def test_dimensions_come_resolved(self) -> None:
        scene = model_to_scene(parse_model("ladrillo 2x4 en 0,0,0"))
        pieza = scene["piezas"][0]
        self.assertEqual((pieza["ancho"], pieza["fondo"], pieza["alto"]), (2, 4, 3))

    def test_rotation_swaps_width_and_depth_in_the_scene(self) -> None:
        scene = model_to_scene(parse_model("ladrillo 2x4 en 0,0,0 rot 90"))
        pieza = scene["piezas"][0]
        self.assertEqual((pieza["ancho"], pieza["fondo"]), (4, 2))

    def test_plate_and_tile_are_one_unit_tall(self) -> None:
        scene = model_to_scene(
            parse_model("placa 2x4 en 0,0,0\nbaldosa 1x2 en 0,0,1")
        )
        self.assertEqual([p["alto"] for p in scene["piezas"]], [1, 1])

    def test_tile_has_no_studs(self) -> None:
        scene = model_to_scene(
            parse_model("ladrillo 1x1 en 0,0,0\nbaldosa 1x2 en 3,0,0")
        )
        self.assertEqual([p["studs"] for p in scene["piezas"]], [True, False])

    def test_position_is_the_minimum_corner(self) -> None:
        scene = model_to_scene(parse_model("ladrillo 2x4 en 3,4,6"))
        pieza = scene["piezas"][0]
        self.assertEqual((pieza["x"], pieza["y"], pieza["z"]), (3, 4, 6))

    def test_model_name_travels(self) -> None:
        scene = model_to_scene(parse_model('modelo "Torre"\nladrillo 1x1 en 0,0,0'))
        self.assertEqual(scene["nombre"], "Torre")


class CompileTests(unittest.TestCase):
    def test_valid_source_reports_ok(self) -> None:
        resultado = compile_source("ladrillo 2x4 en 0,0,0")
        self.assertTrue(resultado["ok"])
        self.assertEqual(len(resultado["piezas"]), 1)

    def test_error_carries_the_line_number(self) -> None:
        resultado = compile_source("ladrillo 2x4 en 0,0,0\nladrillo 1x1 en 1,1,0")
        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["linea"], 2)
        self.assertIn("línea 1", resultado["mensaje"])

    def test_compile_never_raises_on_bad_input(self) -> None:
        # El servidor debe responder un error, no caerse.
        for basura in ("hola", "ladrillo 1x1 en 0,0,-5", "repetir 2 desplazando 1,0,0:"):
            with self.subTest(basura=basura):
                self.assertFalse(compile_source(basura)["ok"])

    def test_bundled_example_compiles(self) -> None:
        # El editor abre con este código: no puede venir roto.
        resultado = compile_source(EJEMPLO)
        self.assertTrue(resultado["ok"], resultado.get("mensaje"))
        self.assertEqual(len(resultado["piezas"]), 21)


class OfflineTests(unittest.TestCase):
    """El visor debe funcionar sin conexión: nada puede venir de internet."""

    def test_the_page_has_no_external_references(self) -> None:
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        externas = re.findall(r"https?://[^\"'\s>]+", html)
        self.assertEqual(externas, [], f"El visor apunta fuera: {externas}")

    def test_the_3d_library_is_bundled(self) -> None:
        for nombre in ("three.module.js", "OrbitControls.js"):
            with self.subTest(nombre=nombre):
                self.assertTrue((_WEB / "vendor" / nombre).is_file())

    def test_orbitcontrols_only_needs_three(self) -> None:
        # Si importara de 'three/addons/...' el importmap local no bastaría.
        codigo = (_WEB / "vendor" / "OrbitControls.js").read_text(encoding="utf-8")
        origenes = set(re.findall(r"from\s+['\"]([^'\"]+)['\"]", codigo))
        self.assertEqual(origenes, {"three"})

    def test_the_bundled_library_license_is_included(self) -> None:
        licencia = (_WEB / "vendor" / "LICENSE-three.txt").read_text(encoding="utf-8")
        self.assertIn("MIT", licencia)


if __name__ == "__main__":
    unittest.main()
