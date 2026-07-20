"""Pruebas del visor con la geometría real de LDraw.

Lo importante que comprueban: que la malla de una pieza cae DENTRO de la caja
que el motor dice que ocupa, en cualquier orientación. Si la transformación
estuviera mal, la pieza se vería en otro sitio y ninguna prueba de las otras
se enteraría.
"""

import json
import unittest
from pathlib import Path

import blockcad_engine
from blockcad_web.server import _archivo_mallas, compile_source

_MALLAS = Path(blockcad_engine.__file__).parent / "datos" / "mallas_45300.json"

#: Lo que un stud sobresale de la caja. Es correcto que lo haga: se mete en la
#: pieza de arriba.
ALTO_STUD = 4


class ArchivoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.doc = json.loads(_MALLAS.read_text(encoding="utf-8"))

    def test_it_is_a_versioned_format(self) -> None:
        # La versión 2 agrupa los triángulos por código de color. La 1 los
        # traía en una sola lista y tiraba el color: los ojos del set se
        # veían blanco sobre blanco.
        self.assertEqual(self.doc["formato"], "blockcad-mallas")
        self.assertEqual(self.doc["version"], 2)

    def test_the_source_is_credited(self) -> None:
        # La CC BY 4.0 exige que la atribución viaje con la geometría.
        self.assertIn("LDraw", self.doc["origen"])
        self.assertIn("CC BY", self.doc["origen"])

    def test_every_group_is_whole_triangles(self) -> None:
        for nombre, grupos in self.doc["triangulos"].items():
            with self.subTest(pieza=nombre):
                self.assertIsInstance(grupos, dict)
                self.assertGreater(len(grupos), 0)
                for codigo, triangulos in grupos.items():
                    self.assertEqual(
                        len(triangulos) % 9, 0, f"sobran vértices en {codigo}"
                    )
                    self.assertGreater(len(triangulos), 0)

    def test_the_eyes_have_their_pupils(self) -> None:
        # El molde 16424 son los ojos del set: cuerpo pintable ("16") y la
        # pupila en negro fijo ("0"). Con el formato viejo —una sola lista—
        # esta prueba no puede pasar: no había más que un grupo.
        grupos = self.doc["triangulos"]["16424"]
        self.assertIn("16", grupos)
        self.assertGreater(len(grupos), 1)
        self.assertIn("0", grupos)

    def test_a_plain_brick_has_only_its_paintable_body(self) -> None:
        # Un ladrillo liso no trae dibujos: todo él es del color que se elija.
        self.assertEqual(set(self.doc["triangulos"]["3001"]), {"16"})

    def test_fixed_colors_come_with_their_hex(self) -> None:
        # Cada código fijo que use alguna malla tiene que decir su hex, o el
        # visor no sabría pintarlo. El "16" no: no es un color, es «píntame».
        colores = self.doc["colores_ldraw"]
        usados = {
            codigo
            for grupos in self.doc["triangulos"].values()
            for codigo in grupos
        }
        for codigo in usados - {"16"}:
            with self.subTest(codigo=codigo):
                self.assertRegex(colores[codigo], r"^#[0-9A-Fa-f]{6}$")
        self.assertNotIn("16", colores)

    def test_every_mesh_declares_its_extent(self) -> None:
        # Hace falta para reanclarla al girarla, y no es la de la caja.
        self.assertEqual(
            set(self.doc["triangulos"]), set(self.doc["extension"])
        )

    def test_a_brick_mesh_includes_its_studs(self) -> None:
        # 24 de ladrillo más 4 de stud. La caja de colisión mide 24; la malla
        # los lleva, porque dibujar un ladrillo sin studs sería otra cosa.
        self.assertEqual(self.doc["extension"]["3001"][2], 28)

    def test_the_basic_catalog_has_meshes_too(self) -> None:
        # Sin esto, un modelo de ladrillos se seguiría viendo como cajas.
        from blockcad_engine.parts import PartCatalog

        for definicion in PartCatalog.with_basic_parts().all():
            with self.subTest(pieza=definicion.part_id):
                self.assertIn(definicion.metadata["malla"], self.doc["triangulos"])


class EncajeTests(unittest.TestCase):
    """La malla tiene que caer donde el motor dice que está la pieza."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.triangulos = _archivo_mallas()["triangulos"]

    def _vertices_fuera(self, codigo: str) -> int:
        escena = compile_source(codigo)
        self.assertTrue(escena["ok"], escena.get("mensaje"))

        fuera = 0
        for pieza in escena["piezas"]:
            grupos = self.triangulos.get(pieza["malla"])
            self.assertIsNotNone(grupos, f"sin malla: {pieza['malla']}")
            matriz, origen = pieza["matriz"], pieza["origen"]
            caja = (
                (pieza["x"], pieza["x"] + pieza["ancho"]),
                (pieza["y"], pieza["y"] + pieza["fondo"]),
                (pieza["z"], pieza["z"] + pieza["alto"]),
            )
            # TODOS los grupos de color: la pupila tiene que caer dentro de
            # la caja igual que el cuerpo.
            for malla in grupos.values():
                for i in range(0, len(malla), 3):
                    punto = malla[i], malla[i + 1], malla[i + 2]
                    for eje in range(3):
                        valor = (
                            sum(matriz[eje][k] * punto[k] for k in range(3))
                            + origen[eje]
                        )
                        bajo, alto = caja[eje]
                        if not (
                            bajo - ALTO_STUD - 0.5
                            <= valor
                            <= alto + ALTO_STUD + 0.5
                        ):
                            fuera += 1
                            break
        return fuera

    def test_a_piece_without_turning(self) -> None:
        self.assertEqual(self._vertices_fuera("ladrillo 2x4 en 0,0,0"), 0)

    def test_every_turn_around_z(self) -> None:
        for grados in (90, 180, 270):
            with self.subTest(grados=grados):
                self.assertEqual(
                    self._vertices_fuera(f"ladrillo 2x4 en 0,0,0 rot {grados}"), 0
                )

    def test_every_axis(self) -> None:
        for eje in "xyz":
            with self.subTest(eje=eje):
                self.assertEqual(
                    self._vertices_fuera(f"ladrillo 2x4 en 0,0,0 rot {eje} 90"), 0
                )

    def test_two_turns_and_moved(self) -> None:
        self.assertEqual(
            self._vertices_fuera("ladrillo 2x4 en 5,3,2 rot x 90 rot z 90"), 0
        )

    def test_the_flat_pieces(self) -> None:
        for codigo in ("placa 2x4 en 0,0,0 rot 90", "baldosa 1x2 en 0,0,0 rot 270"):
            with self.subTest(codigo=codigo):
                self.assertEqual(self._vertices_fuera(codigo), 0)

    def test_the_real_parts_of_the_set(self) -> None:
        for codigo in (
            'catalogo "wedo"\nviga 7 en 0,0,0',
            'catalogo "wedo"\nviga 7 en 0,0,0 rot x 90',
            'catalogo "wedo"\n19071 en 0,0,0 rot z 180',
            # Piezas enderezadas al cargar: su malla lleva un giro propio que
            # se compone con el del constructor, y ahí es donde se falla.
            'catalogo "wedo"\nladrillo 2x4 en 0,0,0',
            'catalogo "wedo"\nladrillo 2x4 en 0,0,0 rot 90',
            'catalogo "wedo"\nplaca 1x6 en 0,0,0 rot x 90',
            'catalogo "wedo"\neje 6 en 0,0,0',
            'catalogo "wedo"\neje 6 en 0,0,0 rot 90',
        ):
            with self.subTest(codigo=codigo.splitlines()[-1]):
                self.assertEqual(self._vertices_fuera(codigo), 0)

    def test_the_whole_house(self) -> None:
        from blockcad_web.server import EJEMPLO

        self.assertEqual(self._vertices_fuera(EJEMPLO), 0)


class ServidorTests(unittest.TestCase):
    def test_it_only_sends_what_is_asked(self) -> None:
        # El archivo son 5 MB y 99 piezas; un modelo usa un puñado.
        from blockcad_web.server import mallas_pedidas

        recibido = mallas_pedidas(json.dumps(["3001"]))
        self.assertEqual(list(recibido["mallas"]), ["3001"])

    def test_the_colors_travel_with_their_meshes(self) -> None:
        # Los ojos usan negro fijo: su hex tiene que venir en la respuesta,
        # o el visor no sabría de qué pintar la pupila.
        from blockcad_web.server import mallas_pedidas

        recibido = mallas_pedidas(json.dumps(["16424"]))
        self.assertIn("0", recibido["mallas"]["16424"])
        self.assertRegex(recibido["colores_ldraw"]["0"], r"^#[0-9A-Fa-f]{6}$")
        # Y solo los códigos que lo pedido usa, no la tabla entera.
        usados = {c for g in recibido["mallas"].values() for c in g}
        self.assertEqual(set(recibido["colores_ldraw"]), usados - {"16"})

    def test_an_unknown_mesh_is_just_missing(self) -> None:
        from blockcad_web.server import mallas_pedidas

        recibido = mallas_pedidas(json.dumps(["no_existe"]))
        self.assertEqual(recibido, {"mallas": {}, "colores_ldraw": {}})

    def test_rubbish_does_not_break_it(self) -> None:
        from blockcad_web.server import mallas_pedidas

        self.assertEqual(
            mallas_pedidas("{no es json"), {"mallas": {}, "colores_ldraw": {}}
        )

    def test_the_scene_says_which_mesh_to_draw(self) -> None:
        escena = compile_source("ladrillo 2x4 en 0,0,0")
        self.assertEqual(escena["piezas"][0]["malla"], "3001")


class VisorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = (
            Path(blockcad_engine.__file__).resolve().parents[1]
            / "blockcad_web"
            / "index.html"
        ).read_text(encoding="utf-8")

    def test_opened_as_a_file_the_page_explains_itself(self) -> None:
        """Abierta con doble clic (file://), la página debe decir qué le falta.

        Lo que importa es DÓNDE vive el aviso: fuera del módulo principal.
        Con file:// el navegador ni siquiera carga el módulo —Three.js llega
        por el servidor—, así que un aviso dentro de él no se ejecutaría nunca
        y la página se quedaría en «Cargando…» para siempre, que no explica
        nada. Lo encontró un usuario, no una prueba.
        """
        antes_del_modulo = self.html.split('<script type="module">')[0]
        self.assertIn("location.protocol === 'file:'", antes_del_modulo)
        self.assertIn("python -m blockcad_web", antes_del_modulo)

    def test_the_axes_are_turned_not_mirrored(self) -> None:
        # Intercambiar Y y Z es un reflejo, no un giro: a una caja simétrica le
        # da igual, pero a una malla le invierte las normales.
        self.assertIn("modelo.rotation.x = -Math.PI / 2", self.html)

    def test_shared_meshes_are_not_disposed(self) -> None:
        # Liberarlas al limpiar dejaría la escena sin geometría al siguiente
        # dibujado: se comparten entre todas las copias de una pieza.
        limpiar = self.html.split("function limpiar(")[1].split("\n}")[0]
        self.assertIn("userData.compartida", limpiar)

    def test_the_pieces_have_edges(self) -> None:
        """Sin bordes, una pared de ladrillos se ve como un bloque liso.

        Dos piezas del mismo color pegadas son caras coplanares con la misma
        luz: nada las separa. El sombreado no basta, por muy real que sea la
        malla.
        """
        self.assertIn("new THREE.EdgesGeometry(geometria, 30)", self.html)

    def test_the_edges_are_computed_once_per_part(self) -> None:
        # Un hub tiene 6.348 triángulos: calcular sus aristas por cada copia
        # sería tirar el tiempo. Van con la malla, que ya se cachea.
        pedir = self.html.split("async function pedirMallas(")[1].split("\n}")[0]
        self.assertIn("EdgesGeometry", pedir)

    def test_the_edges_adapt_to_the_piece(self) -> None:
        # Un borde negro sobre una pieza negra no dibuja nada.
        self.assertIn("oscura ? 0xaab3c4", self.html)

    def test_both_faces_are_drawn(self) -> None:
        """Sin esto las piezas se ven huecas, como tubos rotos.

        LDraw dice hacia dónde mira cada triángulo con instrucciones BFC, y el
        lector no las interpreta: para medir una caja daba igual. Al dibujar,
        la mitad de los triángulos quedan del revés y se descartan.
        """
        self.assertIn("side: THREE.DoubleSide", self.html)

    def test_the_mesh_is_not_indexed(self) -> None:
        # De eso depende lo anterior: sin índice, cada triángulo lleva su
        # propia normal y Three.js la voltea sola en las caras traseras. Con
        # índice, las normales se promediarían entre caras de sentido opuesto
        # y se anularían.
        self.assertNotIn("setIndex", self.html)

    def test_meshes_are_asked_for_before_drawing(self) -> None:
        compilar = self.html.split("async function compilar()")[1]
        self.assertLess(
            compilar.index("pedirMallas"), compilar.index("construir(datos.piezas)")
        )


if __name__ == "__main__":
    unittest.main()
