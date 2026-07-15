import json
import re
import tempfile
import unittest
from pathlib import Path

import blockcad_web
from blockcad_engine import GridPosition, Orientation, load_model, parse_model
from blockcad_engine.geometry import LADRILLO, PLACA, STUD
from blockcad_web.server import (
    EJEMPLO,
    compile_json,
    compile_source,
    import_json,
    model_to_scene,
)

_WEB = Path(blockcad_web.__file__).parent


class SceneTests(unittest.TestCase):
    """El navegador no conoce el catálogo: la escena debe llegar resuelta."""

    def test_dimensions_come_resolved(self) -> None:
        scene = model_to_scene(parse_model("ladrillo 2x4 en 0,0,0"))
        pieza = scene["piezas"][0]
        self.assertEqual(
            (pieza["ancho"], pieza["fondo"], pieza["alto"]),
            (2 * STUD, 4 * STUD, LADRILLO),
        )

    def test_rotation_swaps_width_and_depth_in_the_scene(self) -> None:
        scene = model_to_scene(parse_model("ladrillo 2x4 en 0,0,0 rot 90"))
        pieza = scene["piezas"][0]
        self.assertEqual((pieza["ancho"], pieza["fondo"]), (4 * STUD, 2 * STUD))

    def test_plate_and_tile_are_one_unit_tall(self) -> None:
        scene = model_to_scene(
            parse_model("placa 2x4 en 0,0,0\nbaldosa 1x2 en 0,0,1")
        )
        self.assertEqual([p["alto"] for p in scene["piezas"]], [PLACA, PLACA])

    def test_tile_has_no_studs(self) -> None:
        scene = model_to_scene(
            parse_model("ladrillo 1x1 en 0,0,0\nbaldosa 1x2 en 3,0,0")
        )
        self.assertEqual([p["studs"] for p in scene["piezas"]], [True, False])

    def test_position_is_the_minimum_corner(self) -> None:
        scene = model_to_scene(parse_model("ladrillo 2x4 en 3,4,6"))
        pieza = scene["piezas"][0]
        self.assertEqual(
            (pieza["x"], pieza["y"], pieza["z"]),
            (3 * STUD, 4 * STUD, 6 * PLACA),
        )

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


class ExportTests(unittest.TestCase):
    """Lo exportado debe ser exactamente lo que el motor sabe volver a leer."""

    def test_exported_json_can_be_loaded_back(self) -> None:
        fuente = (
            'modelo "Ida y vuelta"\n'
            "ladrillo 2x4 en 1,2,3 rot 90 color azul grupo 2 paso 5\n"
            "baldosa 1x2 en 0,0,0 color #00AAFF transparente"
        )
        resultado = compile_json(fuente)
        self.assertTrue(resultado["ok"], resultado.get("mensaje"))

        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "modelo.blockcad.json"
            ruta.write_text(resultado["json"], encoding="utf-8")
            recuperado = load_model(ruta)

        self.assertEqual(recuperado.name, "Ida y vuelta")
        self.assertEqual(len(recuperado.instances), 2)

        ladrillo = next(
            i for i in recuperado.instances if i.part_id == "brick_2x4"
        )
        self.assertEqual(ladrillo.position, GridPosition(1 * STUD, 2 * STUD, 3 * PLACA))
        self.assertEqual(ladrillo.orientation, Orientation.z(90))
        self.assertEqual(ladrillo.color, "#457B9D")
        self.assertEqual(ladrillo.group, 2)
        self.assertEqual(ladrillo.step, 5)

        baldosa = next(i for i in recuperado.instances if i.part_id == "tile_1x2")
        self.assertTrue(baldosa.transparent)

    def test_exported_json_uses_the_engine_format(self) -> None:
        datos = json.loads(compile_json("ladrillo 1x1 en 0,0,0")["json"])
        self.assertEqual(datos["format"], "blockcad-remake")
        self.assertEqual(datos["version"], 3)

    def test_export_reports_errors_instead_of_raising(self) -> None:
        resultado = compile_json("ladrillo 2x4 en 0,0,0\nladrillo 1x1 en 1,1,0")
        self.assertFalse(resultado["ok"])
        self.assertEqual(resultado["linea"], 2)

    def test_exported_name_travels(self) -> None:
        resultado = compile_json('modelo "Torre"\nladrillo 1x1 en 0,0,0')
        self.assertEqual(resultado["nombre"], "Torre")
        self.assertEqual(json.loads(resultado["json"])["name"], "Torre")

    def test_example_exports_cleanly(self) -> None:
        resultado = compile_json(EJEMPLO)
        self.assertTrue(resultado["ok"])
        self.assertEqual(len(json.loads(resultado["json"])["parts"]), 21)


class ImportTests(unittest.TestCase):
    """Abrir debe entender lo que este mismo editor escribe."""

    def test_exported_json_can_be_opened_again(self) -> None:
        # El recorrido que falla sin esto: Exportar JSON -> Nuevo -> Abrir.
        exportado = compile_json(EJEMPLO)["json"]
        importado = import_json(exportado)

        self.assertTrue(importado["ok"], importado.get("mensaje"))
        recuperado = compile_source(importado["codigo"])
        self.assertTrue(recuperado["ok"], recuperado.get("mensaje"))
        self.assertEqual(len(recuperado["piezas"]), 21)

    def test_the_whole_round_trip_preserves_every_piece(self) -> None:
        fuente = (
            'modelo "Todo junto"\n'
            "ladrillo 2x4 en 1,2,3 rot 90 color azul grupo 2 paso 5\n"
            "baldosa 1x2 en 0,0,0 color #123456 transparente\n"
            "placa 2x4 en 5,0,0 rot 180"
        )
        original = model_to_scene(parse_model(fuente))["piezas"]
        vuelta = model_to_scene(
            parse_model(import_json(compile_json(fuente)["json"])["codigo"])
        )["piezas"]
        self.assertEqual(original, vuelta)

    def test_generated_code_keeps_the_model_name(self) -> None:
        codigo = import_json(compile_json('modelo "Torre"\nladrillo 1x1 en 0,0,0')["json"])
        self.assertIn('modelo "Torre"', codigo["codigo"])

    def test_generated_code_uses_readable_names(self) -> None:
        codigo = import_json(compile_json("ladrillo 2x4 en 0,0,0 color rojo")["json"])
        self.assertIn("ladrillo 2x4 en 0,0,0 color rojo", codigo["codigo"])

    def test_broken_json_is_reported_not_raised(self) -> None:
        for basura in ("{esto no es json", "[]", '{"format": "otro"}', ""):
            with self.subTest(basura=basura):
                resultado = import_json(basura)
                self.assertFalse(resultado["ok"])
                self.assertIn("mensaje", resultado)

    def test_pasting_json_as_code_explains_itself(self) -> None:
        resultado = compile_source(compile_json("ladrillo 1x1 en 0,0,0")["json"])
        self.assertFalse(resultado["ok"])
        self.assertIn("JSON", resultado["mensaje"])


class EditorTests(unittest.TestCase):
    """El editor no debe perder el trabajo del usuario."""

    def setUp(self) -> None:
        self.html = (_WEB / "index.html").read_text(encoding="utf-8")

    def test_the_code_is_saved_in_the_browser(self) -> None:
        self.assertIn("localStorage.setItem", self.html)

    def test_saving_happens_while_typing_not_only_on_success(self) -> None:
        # guardarEnNavegador() debe llamarse desde alEscribir(), que corre en
        # cada pulsación, y no desde compilar(), que solo acaba bien si el
        # código es válido.
        escribir = self.html.split("function alEscribir()")[1].split("}")[0]
        self.assertIn("guardarEnNavegador()", escribir)

    def test_the_editor_restores_instead_of_loading_the_example(self) -> None:
        arrancar = self.html.split("async function arrancar()")[1]
        self.assertIn("localStorage.getItem", arrancar)

    def test_an_emptied_editor_stays_empty_after_reloading(self) -> None:
        # Distinguir null («nunca lo has usado», trae el ejemplo) de cadena
        # vacía («pulsaste Nuevo», sigue en blanco). Comprobar `.trim()` aquí
        # devolvería el ejemplo justo después de vaciar el editor.
        arrancar = self.html.split("async function arrancar()")[1]
        self.assertIn("guardado !== null", arrancar)
        self.assertNotIn("guardado.trim()", arrancar)

    def test_opening_detects_json_and_converts_it(self) -> None:
        manejador = self.html.split("entradaArchivo.addEventListener('change'")[1]
        self.assertIn("startsWith('{')", manejador)
        self.assertIn("/api/importar", manejador)

    def test_the_file_picker_offers_json(self) -> None:
        entrada = self.html.split('id="archivo"')[1].split(">")[0]
        self.assertIn(".json", entrada)

    def test_the_console_validates_before_touching_the_code(self) -> None:
        # Una orden mal escrita no debe ensuciar el editor: primero se
        # comprueba contra el motor y solo entonces se añade.
        anadir = self.html.split("async function anadirPiezas(")[1].split("\n}")[0]
        self.assertLess(
            anadir.index("/api/modelo"),
            anadir.index("aplicar(propuesta)"),
        )

    def test_the_console_edits_the_text_not_a_parallel_model(self) -> None:
        # El texto es el único origen de la verdad. Un modelo aparte en el
        # servidor obligaría a regenerar el código y borraría los repetir y
        # los comentarios del usuario.
        consola = self.html.split("--- Consola de órdenes")[1]
        self.assertIn("areaCodigo.value", consola)
        self.assertNotIn("/api/editor", consola)

    def test_the_help_does_not_align_with_spaces(self) -> None:
        # El CSS colapsa los espacios múltiples, así que alinear columnas con
        # ellos hacía que la orden y su descripción se leyeran como una sola
        # frase, y el usuario intentaba escribirla entera.
        ayuda = self.html.split("const AYUDA = [")[1].split("];")[0]
        self.assertNotIn("   ", ayuda)
        self.assertIn("['ladrillo 2x4 en 0,0,0 color rojo',", ayuda)

    def test_the_help_is_rendered_in_two_columns(self) -> None:
        self.assertIn("#consola-mensaje.ayuda", self.html)
        self.assertIn("grid-template-columns", self.html)

    def test_the_console_forgives_a_leading_verb(self) -> None:
        verbos = self.html.split("const VERBOS = ")[1].split("\n")[0]
        for verbo in ("añade", "agrega", "pon"):
            with self.subTest(verbo=verbo):
                self.assertIn(verbo, verbos)

    def test_pasting_a_whole_model_loads_it_instead_of_appending(self) -> None:
        # Fallo real: al pegar un modelo completo en la consola, se añadía al
        # final del código y la línea `catalogo` acababa en medio. El error
        # decía "debe ir en la primera línea" cuando en lo pegado sí lo
        # estaba, y la caja de 3 filas ni siquiera dejaba verla.
        enviar = self.html.split("async function enviar()")[1].split("\n}")[0]
        self.assertIn("ES_PROGRAMA.test(texto)", enviar)
        self.assertLess(
            enviar.index("ES_PROGRAMA"),
            enviar.index("anadirPiezas"),
            "hay que detectar el programa antes de añadir nada",
        )

    def test_a_whole_model_is_recognised_by_its_directives(self) -> None:
        patron = self.html.split("const ES_PROGRAMA = ")[1].split("\n")[0]
        self.assertIn("catalogo", patron)
        self.assertIn("modelo", patron)

    def test_the_console_box_grows_with_what_you_paste(self) -> None:
        self.assertIn("function ajustarCaja()", self.html)
        self.assertIn("scrollHeight", self.html)

    def test_the_console_undo_keeps_snapshots(self) -> None:
        registrar = self.html.split("function registrar()")[1].split("}")[0]
        self.assertIn("historial.pasado.push(areaCodigo.value)", registrar)

    def test_replacing_the_code_asks_first(self) -> None:
        for boton in ("nuevo", "abrir", "ejemplo"):
            with self.subTest(boton=boton):
                manejador = self.html.split(f"getElementById('{boton}')")[1]
                self.assertIn("puedoReemplazar()", manejador.split("});")[0])


class ViewerUnitTests(unittest.TestCase):
    """El visor recibe LDU y dibuja en studs. Esa división tiene que estar."""

    def setUp(self) -> None:
        self.html = (_WEB / "index.html").read_text(encoding="utf-8")

    def test_the_viewer_converts_from_ldu(self) -> None:
        self.assertIn("const LDU = 1 / 20", self.html)

    def test_the_viewer_no_longer_scales_height_apart(self) -> None:
        # Antes la altura iba a escala 0,4 porque z venía en placas. Con todo
        # en LDU esa corrección sobra, y dejarla aplastaría el modelo.
        construir = self.html.split("function construir(")[1].split("\n}")[0]
        self.assertNotIn("PLACA", construir)
        self.assertIn("p.alto * LDU", construir)

    def test_studs_are_counted_not_taken_from_the_size(self) -> None:
        # `ancho` ya no es "2 studs" sino "40 LDU": usarlo como contador
        # dibujaría 40 studs sobre un ladrillo que tiene 2.
        construir = self.html.split("function construir(")[1].split("\n}")[0]
        self.assertIn("p.ancho / 20", construir)
        self.assertIn("p.fondo / 20", construir)


class ContrastTests(unittest.TestCase):
    """Una pieza tiene que verse sea del color que sea.

    Los colores de LEGO van del negro (#1B1B1B) al blanco (#F4F4F4), así que
    NINGÚN fondo contrasta con todos: medido, el peor caso no pasa de 1.58:1
    ni con el gris óptimo. Por eso el fondo es un compromiso y lo que
    garantiza la silueta es el contorno, que se adapta a la pieza.
    """

    def setUp(self) -> None:
        self.html = (_WEB / "index.html").read_text(encoding="utf-8")

    def test_the_outline_adapts_to_the_piece(self) -> None:
        # Un contorno negro sobre una pieza negra no dibuja nada.
        self.assertIn("function esOscura(", self.html)
        construir = self.html.split("function construir(")[1].split("\n}")[0]
        self.assertIn("oscura ? 0xaab3c4 : 0x000000", construir)

    def test_the_background_is_not_almost_black(self) -> None:
        # Con el #0f1116 de antes, una viga negra daba 1.10:1 y desaparecía.
        fondo = re.search(r"escena\.background = new THREE\.Color\((0x[0-9a-f]+)\)", self.html)
        self.assertIsNotNone(fondo)
        valor = int(fondo.group(1), 16)
        canales = ((valor >> 16) & 255, (valor >> 8) & 255, valor & 255)
        self.assertGreater(min(canales), 0x28)

    def test_colours_are_six_digits(self) -> None:
        # `0x39405060` tenía ocho y se salía del rango: la rejilla salía de un
        # tono cualquiera y nadie se enteraba.
        for encontrado in re.findall(r"0x[0-9a-fA-F]{7,}", self.html):
            self.fail(f"{encontrado} no es un color: sobra algún dígito")


class PackagingTests(unittest.TestCase):
    """Lo que no es .py hay que declararlo, o no llega al paquete instalado.

    Se coló dos veces: al incluir Three.js y al generar el catálogo. Nada
    saltaba porque en el repositorio los archivos están; solo faltaban en el
    `pip install`, y ahí el visor se quedaba sin librería.
    """

    def setUp(self) -> None:
        self.pyproject = (
            Path(blockcad_web.__file__).resolve().parents[1] / "pyproject.toml"
        ).read_text(encoding="utf-8")

    def test_the_bundled_library_is_declared(self) -> None:
        self.assertIn("vendor/*", self.pyproject)

    def test_the_catalog_is_declared(self) -> None:
        self.assertIn("datos/*.json", self.pyproject)

    def test_every_runtime_file_lives_where_it_is_declared(self) -> None:
        # Si alguien mueve un archivo, la declaración deja de cubrirlo.
        for relativo in (
            "index.html",
            "vendor/three.module.js",
            "vendor/OrbitControls.js",
            "vendor/LICENSE-three.txt",
        ):
            with self.subTest(archivo=relativo):
                self.assertTrue((_WEB / relativo).is_file())


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
