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

    def test_a_non_utf8_body_gets_an_answer_not_a_crash(self) -> None:
        """Un cuerpo mal codificado debe responder, no reventar la petición.

        Lo encontró un acento: «Transmisión» enviado en latin-1 tiraba el
        hilo con un UnicodeDecodeError y el navegador se quedaba esperando
        una respuesta que nunca llegaba.
        """
        import io

        from blockcad_web.server import _Handler

        handler = _Handler.__new__(_Handler)
        handler.path = "/api/modelo"
        handler.headers = {"Content-Length": "5"}
        handler.rfile = io.BytesIO("adiós".encode("latin-1"))
        respuestas = []
        handler._send_json = respuestas.append
        handler.do_POST()
        self.assertEqual(len(respuestas), 1)
        self.assertFalse(respuestas[0]["ok"])
        self.assertIn("UTF-8", respuestas[0]["mensaje"])


class PaletaTests(unittest.TestCase):
    """Soltar una pieza escribe código; la paleta solo dice qué hay."""

    def test_the_palette_lists_the_catalog(self) -> None:
        from blockcad_web.server import piezas_para_soltar

        wedo = piezas_para_soltar("wedo")["piezas"]
        self.assertGreater(len(wedo), 90)
        # Cada pieza dice cómo se ESCRIBE, porque soltar es escribir.
        escrituras = {p["escritura"] for p in wedo}
        self.assertIn("ladrillo 2x4", escrituras)
        self.assertIn("viga 7", escrituras)

    def test_without_a_catalog_line_the_basic_one_answers(self) -> None:
        from blockcad_web.server import piezas_para_soltar

        self.assertEqual(len(piezas_para_soltar("")["piezas"]), 7)

    def test_an_unknown_catalog_is_just_empty(self) -> None:
        from blockcad_web.server import piezas_para_soltar

        self.assertEqual(piezas_para_soltar("nada")["piezas"], [])

    def test_dropping_goes_through_the_console(self) -> None:
        # `anadirPiezas` valida antes de tocar el código y registra el
        # deshacer. Un camino aparte sería un segundo sitio donde el texto
        # cambia, que es justo lo que este editor prohíbe.
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        soltar = html.split("if (armada) {")[1].split("return;")[0]
        self.assertIn("anadirPiezas", soltar)

    def test_the_palette_shows_piece_images(self) -> None:
        # Como el BlockCAD original: cada pieza con su imagen, renderizada
        # una vez desde su malla real y cacheada. El servidor dice la malla.
        from blockcad_web.server import piezas_para_soltar

        piezas = piezas_para_soltar("wedo")["piezas"]
        self.assertTrue(all("malla" in p for p in piezas))
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("function miniatura", html)
        self.assertIn("pedirMallas(datos.piezas.map", html)
        self.assertIn("miniaturas.set(nombreMalla", html)

    def test_the_hand_tool_swaps_left_drag_to_pan(self) -> None:
        # La mano no es un modo nuevo del visor: es decirle a OrbitControls
        # que el boton izquierdo desplace en vez de orbitar. Esc la suelta.
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="mano"', html)
        self.assertIn("controles.mouseButtons.LEFT = manoActiva ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE", html)
        self.assertIn("if (manoActiva) alternarMano(false);", html)
        # Y la tecla H la alterna, salvo escribiendo: ahi la h es una letra.
        self.assertIn("evento.key === 'h' || evento.key === 'H'", html)

    def test_the_code_panel_can_hide(self) -> None:
        # Para ver el diseño entero sin distraccion: se esconde el panel,
        # no el texto — que sigue mandando — y el visor recalcula su ancho.
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="codigo-visible"', html)
        self.assertIn("editor.classList.toggle('oculto')", html)
        self.assertIn("dispatchEvent(new Event('resize'))", html)

    def test_the_scene_says_which_pieces_are_loose(self) -> None:
        # Solo una pieza SUELTA se puede arrastrar: sin union, sin apoyarse
        # y sin nadie encima. La de abajo de una torre no esta suelta.
        escena = compile_source(
            "ladrillo 2x4 en 0,0,0\n"
            "ladrillo 2x2 en 0,0,3\n"
            "ladrillo 1x1 en 10,10,0"
        )
        sueltas = {p["nombre"]: p["suelta"] for p in escena["piezas"]}
        self.assertFalse(sueltas["Ladrillo 2×4"])
        self.assertFalse(sueltas["Ladrillo 2×2"])
        self.assertTrue(sueltas["Ladrillo 1×1"])

    def test_dragging_a_loose_piece_moves_it(self) -> None:
        # Apretar sobre la elegida y suelta la agarra; el movimiento arranca
        # tras unos pixeles (un clic quieto sigue siendo un clic) y soltar
        # el boton la deja, por la misma mudanza validada de siempre.
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("cual.suelta && cual.linea != null", html)
        self.assertIn("iniciarMovimiento(arrastrable, 'Movida')", html)
        self.assertIn("controles.enabled = false", html)
        self.assertIn("verboMovimiento", html)

    def test_the_scene_publishes_mouths_and_males(self) -> None:
        # El iman de la insercion casa rectas: la escena publica las BOCAS
        # de cada pieza (agujeros agrupados por recta, centro y direccion)
        # y el asa de sus machos si forman una sola recta. Un eje de 6: dos
        # puntas, un asa en su centro.
        escena = compile_source('catalogo "wedo"\n3701 en 0,0,0\neje 6 en 10,10,0')
        viga, eje = escena["piezas"]
        self.assertEqual(len(viga["bocas"]), 3)
        self.assertEqual(viga["bocas"][0]["eje"], [1.0, 0.0, 0.0])
        self.assertEqual(eje["macho_centro"], [6.0, 60.0, 6.0])
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("moviendo.machoCentro", html)
        self.assertIn("bocaCercana(otra.bocas, moviendo.machoEje)", html)

    def test_the_host_magnet_anchors_hole_on_mouth(self) -> None:
        # La caja declara a sus huespedes en lista y cada huesped trae su
        # agujero CON direccion: el iman lo ancla sobre la boca paralela
        # mas cercana. Asi el gusano cae a la recta baja y el engranaje a
        # la ranura de arriba, sin centros especiales.
        escena = compile_source('catalogo "wedo"\n28698 en 5,5,5\n24505 en 20,20,0')
        caja, engranaje = escena["piezas"]
        self.assertEqual(caja["acoge"], ["32905", "24505"])
        self.assertEqual(engranaje["agarre_eje"], [0.0, 1.0, 0.0])
        # Cada huesped tiene SU asiento (el tope de la pieza real): el
        # gusano una sola recta baja; el engranaje, las tres de arriba.
        self.assertEqual(len(caja["asientos"]["32905"]), 1)
        self.assertEqual(len(caja["asientos"]["24505"]), 3)
        self.assertEqual(caja["asientos"]["32905"][0]["centro"][2], 62.0)
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("otra.acoge.includes(moviendo.molde)", html)
        self.assertIn("otra.asientos[moviendo.molde]", html)
        # Y la silueta no miente: el iman descarta las bocas paralelas
        # donde el huesped no cabe (fuera por un costado o por abajo),
        # que es lo mismo que exigira el motor al soltar.
        self.assertIn("sx + moviendo.caja.ancho > otra.caja.x + otra.caja.ancho", html)
        self.assertIn("if (sz < otra.caja.z) continue;", html)

    def test_pieces_declare_their_connected_set(self) -> None:
        # Cada pieza dice a que CONJUNTO pertenece: su componente conectada
        # (uniones y apoyos, transitivo). Es lo que hace posible mover o
        # girar un bloque entero como una sola cosa desde el menu.
        escena = compile_source(
            'catalogo "wedo"\n'
            '28698 en 5,5,5\n'
            '32905 en 6.9,5.35,6.125 rot 90\n'
            'ladrillo 2x4 en 30,30,0'
        )
        caja, gusano, ladrillo = escena["piezas"]
        self.assertEqual(caja["conjunto"], gusano["conjunto"])
        self.assertNotEqual(caja["conjunto"], ladrillo["conjunto"])
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("opcionMoverGrupo", html)
        self.assertIn("opcionGirarGrupo", html)
        # Mover el grupo reescribe todas sus lineas con el mismo paso y
        # valida UNA vez; girarlo gira las posiciones ((x,y) a (-y,x)) y
        # encadena el rot 90 de cada linea.
        self.assertIn("async function mudarGrupo", html)
        self.assertIn("async function girarGrupo", html)
        self.assertIn("x: -(p.caja.y - minY + p.caja.fondo)", html)
        # El encaje del grupo lo decide su pieza BASE: su esquina cae en
        # la reticula de studs al soltar y al girar, no la caja envolvente
        # — que puede empezar en la punta de un eje que asoma.
        self.assertIn("moviendo.esGrupo && moviendo.referencia", html)
        self.assertIn("referencia: { x: base.caja.x", html)
        self.assertIn("const ajusteX", html)

    def test_shift_click_marks_several_pieces(self) -> None:
        # Shift+clic suma piezas a la seleccion (o las resta); el clic
        # normal la reduce a una. Con varias marcadas, el menu del boton
        # derecho ofrece moverlas y girarlas juntas, por el mismo camino
        # validado de los grupos. Un repetir a medias se niega.
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("evento.shiftKey && pieza", html)
        self.assertIn("function marcar(pieza)", html)
        self.assertIn("esLaElegida(d) || esMarcada(d)", html)
        self.assertIn("opcionMoverMarcadas", html)
        self.assertIn("mover seleccion (${marcadas.length})", html)
        self.assertIn("la seleccion no las lleva todas", html)

    def test_the_camera_button_locks_the_orbit(self) -> None:
        # Mover una pieza congela la orbita: raton para la pieza, flechas
        # para la camara. Y el boton CAMARA la bloquea a voluntad. Toda
        # reapertura de la orbita pasa por la misma puerta (soltarOrbita),
        # que respeta el candado.
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="camara"', html)
        # Bloqueada avisa en ROJO: un candado debe verse de lejos.
        self.assertIn("#camara.armada", html)
        self.assertIn("border-color: #ff6b6b", html)
        # Y la tecla C la alterna, como la H a la mano: solo fuera del
        # texto, y nunca con Ctrl — copiar es copiar.
        self.assertIn("evento.key === 'c' || evento.key === 'C'", html)
        self.assertIn("!evento.ctrlKey && !evento.metaKey && !evento.altKey", html)
        self.assertIn("function soltarOrbita()", html)
        self.assertIn("!camaraBloqueada && !moviendo", html)
        self.assertNotIn("controles.enabled = true", html)

    def test_ctrl_z_undoes_outside_the_text_boxes(self) -> None:
        # Ctrl+Z deshace y Ctrl+Y (o Ctrl+Shift+Z) rehace, por el MISMO
        # historial que las ordenes de la consola. Escribiendo en el
        # codigo o en la consola no se toca: alli manda el deshacer del
        # navegador, que es el de las letras.
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("function deshacer()", html)
        self.assertIn("function rehacer()", html)
        self.assertIn("evento.ctrlKey || evento.metaKey", html)
        self.assertIn("tecla === 'z' && !evento.shiftKey", html)
        self.assertIn("tecla === 'y' || (tecla === 'z' && evento.shiftKey)", html)
        self.assertIn("donde !== areaCodigo && donde !== areaOrden", html)

    def test_grouping_writes_the_grupo_suffix(self) -> None:
        # Agrupar es ESCRIBIR `grupo N` en las lineas marcadas (el
        # lenguaje ya lo sabia decir); desagrupar lo borra. La escena
        # publica el grupo, el visor le da contorno de color, un clic lo
        # elige entero y arrastrarlo lo mueve como una sola pieza.
        escena = compile_source(
            'ladrillo 2x4 en 0,0,0 grupo 2\nladrillo 2x2 en 10,10,0'
        )
        con, sin = escena["piezas"]
        self.assertEqual(con["grupo"], 2)
        self.assertIsNone(sin["grupo"])
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("opcionAgrupar", html)
        self.assertIn("opcionDesagrupar", html)
        self.assertIn("function colorDeGrupo", html)
        self.assertIn("async function escribirGrupo", html)
        self.assertIn("d.grupo ? colorDeGrupo(d.grupo)", html)
        self.assertIn("pieza.grupo && !esLaElegida(pieza)", html)
        self.assertIn("arrastrable.grupo", html)

    def test_the_rack_magnet_is_tangent(self) -> None:
        # Cada rueda dentada publica su engrane (eje mundial y radio
        # primitivo) y la cremallera su normal con su paso: el visor hace
        # la tangente, que a ojo no se acierta. Y voltear existe, porque
        # una cremallera muerde por donde miran sus dientes.
        escena = compile_source('catalogo "wedo"\n24505 en 5,5,0\n3743 en 20,20,0 rot x 180')
        rueda, barra = escena["piezas"]
        self.assertEqual(rueda["engrane"]["radio"], 30.0)
        self.assertEqual(barra["cremallera"], {"normal": [0, 0, -1], "paso": 12})
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("moviendo.cremallera && tocado.object !== suelo", html)
        self.assertIn("otra.engrane.radio + moviendo.cremallera.paso", html)
        self.assertIn("opcionVoltear", html)
        self.assertIn("rot x 180", html)

    def test_escape_disarms(self) -> None:
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        # Esc cancela el soltado, el modo quitar y el menú contextual.
        self.assertIn("if (evento.key === 'Escape') {", html)
        self.assertIn("cerrarMenu();", html)

class InventarioTests(unittest.TestCase):
    """Usar más copias de un molde que la caja se avisa, no se rechaza."""

    def test_two_motors_overdraw_the_box(self) -> None:
        escena = compile_source('catalogo "wedo"\n21980 en 0,0,0\n21980 en 5,0,0')
        self.assertEqual(
            escena["agotadas"],
            [{"pieza": "21980",
              "nombre": "Electric Power Functions 2.0 Medium Motor",
              "usadas": 2, "hay": 1}],
        )

    def test_within_the_box_nothing_is_said(self) -> None:
        escena = compile_source('catalogo "wedo"\n21980 en 0,0,0')
        self.assertEqual(escena["agotadas"], [])

    def test_the_basic_catalog_has_no_inventory(self) -> None:
        # Las siete piezas idealizadas no vienen de ninguna caja.
        escena = compile_source("ladrillo 2x4 en 0,0,0")
        self.assertEqual(escena["agotadas"], [])

    def test_the_scene_counts_the_inventory(self) -> None:
        escena = compile_source('catalogo "wedo"\n21980 en 0,0,0')
        self.assertEqual(escena["inventario"], {"total": 277, "usadas": 1})

    def test_the_basic_catalog_has_no_box(self) -> None:
        self.assertIsNone(compile_source("ladrillo 2x4 en 0,0,0")["inventario"])

    def test_the_palette_has_no_remove_button(self) -> None:
        # El «quitar pieza…» de la paleta duplicaba lo que ya hacen el clic
        # derecho (desconectar) y Supr; quien lo usa pidió jubilarlo.
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("quitar pieza", html)
        self.assertNotIn("modoQuitar", html)

    def test_right_click_opens_the_menu(self) -> None:
        # Clic derecho quieto abre el menu de la pieza; arrastrar con el
        # derecho sigue desplazando la camara.
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        rama = html.split("if (evento.button === 2) {")[1].split("return;")[0]
        self.assertIn("piezaDelMenu = cual", rama)
        self.assertIn("contextmenu", html)

    def test_the_menu_options_edit_the_code(self) -> None:
        # Girar valida la linea girada ANTES de aplicarla: si choca, el
        # codigo queda intacto.
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        girar = html.split("opcionGirar.addEventListener")[1].split("opcionQuitar.addEventListener")[0]
        self.assertLess(girar.index("fetch('/api/modelo'"), girar.index("aplicar(propuesta)"))

    def test_moving_rewrites_the_line_and_validates_first(self) -> None:
        # La mudanza compartida (desconectar y conectar): reescribe la linea
        # a posicion absoluta, las opciones viajan, valida ANTES de aplicar,
        # nunca borra, y un `repetir` se rehusa explicando.
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        mudar = html.split("async function mudarPieza")[1].split("opcionQuitar.addEventListener")[0]
        self.assertNotIn("borrar(", mudar)
        self.assertIn("' en ' + sx", mudar)
        self.assertIn("color", mudar)
        self.assertIn("no se puede mover una sola", mudar)
        self.assertLess(mudar.index("fetch('/api/modelo'"), mudar.index("aplicar(propuesta)"))

    def test_disconnect_lands_nearby(self) -> None:
        # La pieza separada se queda cerca: anillos de candidatos alrededor
        # de donde estaba, validados en silencio hasta el primero que
        # compila. Lo pidio quien la veia salir volando al borde del modelo.
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        quitar = html.split("opcionQuitar.addEventListener")[1].split("});")[0]
        self.assertIn("candidatos.push([c.x + c.ancho + 20 * k, c.y])", quitar)
        self.assertIn("false,", quitar)

    def test_connect_previews_with_a_silhouette_and_confirms(self) -> None:
        # Conectar arma una silueta que sigue al puntero (la caja de la
        # pieza) y el clic confirma la mudanza. El rayo no choca contra la
        # propia pieza en movimiento: si no, siempre se conectaria a si
        # misma.
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("opcionConectar", html)
        # La silueta vive en iniciarMovimiento, compartida con el arrastre.
        conectar = html.split("opcionConectar.addEventListener")[1].split("});")[0]
        self.assertIn("iniciarMovimiento(cual, 'Conectada')", conectar)
        mover = html.split("function iniciarMovimiento")[1].split("\n}")[0]
        self.assertIn("moviendo = cual", mover)
        self.assertIn("fantasma", mover)
        clic = html.split("if (moviendo) {")[1].split("return;")[0]
        self.assertIn("mudarPieza(moviendo", clic)
        self.assertIn("!(moviendo.piezas && moviendo.piezas.includes(d))", html)

    def test_the_page_has_no_control_characters(self) -> None:
        """Un retroceso invisible (x08) vivio dentro de un regex del visor.

        Era el resto de un backslash-b comido por una capa del shell: el
        regex exigia un caracter de control que ningun texto tiene, y
        desconectar respondia siempre «No he sabido reescribir esa linea».
        Invisible al leer, letal al ejecutar: lo encontro un usuario y lo
        cazo la comparacion byte a byte.
        """
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        raros = {c for c in html if ord(c) < 32 and c not in '\n\r\t'}
        self.assertEqual(raros, set())

    def test_arrows_orbit_only_while_placing(self) -> None:
        # Colocando una pieza el clic esta ocupado confirmando, asi que la
        # camara se orbita con las flechas. Solo en ese modo, y nunca
        # robandole las flechas al texto.
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("if (!armada && !moviendo) return;", html)
        flechas = html.split("const giros = {")[1].split("});")[0]
        self.assertIn("ArrowLeft", flechas)
        self.assertIn("Spherical", flechas)
        antes = html.split("const giros = {")[0]
        self.assertIn("donde === areaCodigo || donde === areaOrden", antes)

    def test_page_keys_zoom_while_placing(self) -> None:
        # Re Pag acerca, Av Pag aleja, con el radio acotado como el propio
        # OrbitControls: ni dentro de la pieza ni en la estratosfera.
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("PageUp: 0.9", html)
        self.assertIn("PageDown: 1 / 0.9", html)
        self.assertIn("esfera.radius = Math.min(400, Math.max(0.5", html)

    def test_mouse_verbs_refuse_on_broken_code(self) -> None:
        """Con el codigo roto, el visor es una foto vieja y los numeros de
        linea no casan con el texto: mover el motor reescribia un comentario
        y respondia «No he sabido reescribir esa linea». Lo encontro un
        usuario con un modelo a medio editar. La consola ya se protegia con
        codigoValido; ahora el raton tambien.
        """
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("function escenaAlDia()", html)
        mudar = html.split("async function mudarPieza")[1].split("const hermanas")[0]
        self.assertIn("escenaAlDia()", mudar)
        girar = html.split("opcionGirar.addEventListener")[1].split("cerrarMenu();\n")[0]
        self.assertIn("escenaAlDia", html.split("opcionGirar.addEventListener")[1][:200])

    def test_a_blocked_move_highlights_the_prerequisite(self) -> None:
        """Si mover choca, la pieza que estorba se resalta en rojo.

        El motor ya nombraba las lineas culpables en su mensaje; el visor
        las convierte en remedio: las pinta de rojo y dice «quita o mueve
        esa primero». Lo pidio quien construye: con muchas piezas
        entrelazadas, saber CUAL estorba es la mitad del trabajo.
        """
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("function resaltarProblema", html)
        self.assertIn("function avisarChoque", html)
        # Desconectar/conectar y girar pasan por el aviso que enseña.
        self.assertIn("avisarChoque(fallo, datos.mensaje)", html)
        self.assertIn("avisarChoque('Girada choca', datos.mensaje)", html)
        # El resaltado se limpia solo: cualquier repintado o el tiempo.
        self.assertIn("setTimeout(pintarSeleccion, 4000)", html)

    def test_the_header_counts_remaining_pieces(self) -> None:
        # La etiqueta fija de la cabecera: «tienes X piezas restantes de
        # 277», roja cuando la caja no alcanza, oculta con el catalogo
        # basico (que no viene de ninguna caja).
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="restantes"', html)
        self.assertIn("piezas restantes de", html)
        self.assertIn("classList.toggle('agotado', quedan < 0)", html)
        self.assertIn("restantes.hidden = true", html)

    def test_the_viewer_has_scrollbars_that_pan(self) -> None:
        # Las barras pasean la vista por la extension del modelo moviendo
        # objetivo Y camara juntos: paneo, no orbita. Centrar las resincroniza.
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="barra-x"', html)
        self.assertIn('id="barra-y"', html)
        pan = html.split("function desplazarVista")[1].split("}")[0]
        self.assertIn("controles.target[eje] += delta", pan)
        self.assertIn("camara.position[eje] += delta", pan)
        self.assertIn("sincronizarBarras();", html.split("function centrar()")[1][:600])

    def test_the_footer_reports_it(self) -> None:
        html = (_WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("datos.agotadas", html)
        self.assertIn("la caja trae", html)


class SeleccionTests(unittest.TestCase):
    """Pinchar una pieza tiene que llevar a su línea de código.

    El código es el origen de la verdad. Si el ratón editara un modelo aparte
    habría dos verdades; así que lo único que hace falta que viaje con cada
    pieza es de qué línea salió.
    """

    def test_every_piece_says_which_line_made_it(self) -> None:
        escena = compile_source("ladrillo 2x4 en 0,0,0\nladrillo 2x4 en 0,0,3")
        self.assertEqual([p["linea"] for p in escena["piezas"]], [1, 2])

    def test_comments_and_blank_lines_do_not_shift_it(self) -> None:
        # El número tiene que ser el del editor, no el de las líneas útiles.
        escena = compile_source("// una casa\n\nladrillo 2x2 en 0,0,0")
        self.assertEqual(escena["piezas"][0]["linea"], 3)

    def test_a_repeated_line_owns_all_its_pieces(self) -> None:
        # `repetir` pone varias piezas desde una sola línea. Por eso lo elegido
        # es la línea y no la pieza: no hay una línea por pieza que devolver.
        escena = compile_source(
            "repetir 3 veces desplazando 0,0,3:\n    ladrillo 2x2 en 0,0,0"
        )
        self.assertEqual([p["linea"] for p in escena["piezas"]], [2, 2, 2])

    def test_an_imported_model_has_no_lines_and_says_so(self) -> None:
        # Un modelo que viene de un JSON no salió de ningún texto. Se dibuja
        # igual, pero no hay código al que llevar, y eso se dice con None en
        # vez de inventar un número.
        escena = model_to_scene(parse_model("ladrillo 2x4 en 0,0,0"))
        self.assertIsNone(escena["piezas"][0]["linea"])

    def test_the_whole_example_is_traceable(self) -> None:
        escena = compile_source(EJEMPLO)
        sin_linea = [p for p in escena["piezas"] if p["linea"] is None]
        self.assertEqual(sin_linea, [])


class RatonTests(unittest.TestCase):
    """Lo que el visor hace con esa línea."""

    def setUp(self) -> None:
        self.html = (_WEB / "index.html").read_text(encoding="utf-8")

    def test_a_click_is_not_a_drag(self) -> None:
        # Orbitar es arrastrar, y arrastrar acaba en un pointerup. Sin medir el
        # movimiento, girar la cámara elegiría la pieza de debajo.
        self.assertIn("if (movido > 5) return;", self.html)

    def test_only_bodies_are_clickable(self) -> None:
        # Los bordes son líneas de un pixel: pinchar uno es pinchar un pelo.
        # Los cuerpos son varios por pieza —uno por grupo de color— y todos
        # cuentan: pinchar la pupila de un ojo es pinchar el ojo.
        self.assertIn(
            "rayo.intersectObjects(dibujadas.flatMap((d) => d.cuerpos)", self.html
        )

    def test_what_lights_up_is_the_piece_you_clicked(self) -> None:
        # Y solo esa. Una línea con `repetir` pone cuatro ladrillos iguales:
        # encender los cuatro al pinchar uno no responde a lo que has tocado.
        self.assertIn(
            "d.linea === seleccion.linea && d.orden === seleccion.orden", self.html
        )

    def test_a_piece_is_told_apart_by_its_place_in_its_line(self) -> None:
        # El número de línea no basta para saber cuál es cuál cuando la línea
        # pone varias; el puesto dentro de la línea sí, y sobrevive a un
        # recompilado, que es cuando se tira todo lo dibujado.
        anotar = self.html.split("function anotar(")[1].split("\n}")[0]
        self.assertIn("dibujadas.filter((d) => d.linea === p.linea).length", anotar)

    def test_the_selection_survives_a_rebuild(self) -> None:
        # Al recompilar se tira todo lo dibujado. Si la pieza sigue estando,
        # sigue elegida; si ya no la pone nadie, deja de estarlo sola.
        pintar = self.html.split("function pintarSeleccion()")[1].split("\n}")[0]
        self.assertIn("seleccion = null", pintar)

    def test_deleting_a_repeated_line_is_announced(self) -> None:
        # Se elige una pieza pero se borra su línea: no hay forma de quitar un
        # ladrillo de un `repetir` sin reescribir el bucle. Llevarse cuatro por
        # sorpresa sería el peor final; se avisa antes.
        self.assertIn("Supr borra la línea entera", self.html)

    def test_delete_does_not_steal_the_keyboard(self) -> None:
        # Escribiendo, Supr borra letras. Solo fuera del texto borra la pieza.
        self.assertIn("if (donde === areaCodigo || donde === areaOrden) return;", self.html)

    def test_delete_goes_through_the_console(self) -> None:
        # `borrar` ya registra el deshacer y recompila. Un camino aparte sería
        # un segundo sitio donde el texto cambia.
        self.assertIn("borrar(String(seleccion.linea))", self.html)

    def test_selecting_does_not_erase_the_error_mark(self) -> None:
        # El gutter se repinta al elegir; la línea rota tiene que seguir roja.
        self.assertIn("pintarGutter(lineaRota)", self.html)


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
