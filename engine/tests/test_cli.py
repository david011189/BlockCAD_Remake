"""Pruebas de la demostración por consola.

Esta demo estuvo rota varios commits y nadie se enteró: es el comando que el
README y la documentación dicen que ejecutes, pero ninguna prueba lo
ejecutaba. Dos cambios del motor la rompieron sin que saltara nada —el paso
a LDU, porque sus coordenadas iban en studs, y las orientaciones, porque
seguía leyendo `.rotation`— y las dos veces fue el usuario quien lo encontró.

La lección no era arreglar la demo: era ejecutarla.
"""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path

from blockcad_engine import load_model
from blockcad_engine.cli import construir, main


class DemoTests(unittest.TestCase):
    def _correr(self) -> tuple[str, Path]:
        """Ejecuta la demo entera en una carpeta temporal."""
        carpeta = tempfile.mkdtemp()
        anterior = os.getcwd()
        os.chdir(carpeta)
        try:
            salida = io.StringIO()
            with contextlib.redirect_stdout(salida):
                main()
        finally:
            os.chdir(anterior)
        return salida.getvalue(), Path(carpeta) / "modelo_demo.blockcad.json"

    def test_the_demo_runs_at_all(self) -> None:
        # La prueba que faltaba. Sin ella, cualquier cambio del motor puede
        # romper el primer comando que ejecuta quien llega al proyecto.
        texto, _ = self._correr()
        self.assertIn("Casa sencilla", texto)

    def test_it_writes_a_model_that_can_be_read_back(self) -> None:
        _, archivo = self._correr()
        self.assertTrue(archivo.is_file())
        modelo = load_model(archivo)
        self.assertEqual(modelo.name, "Casa sencilla")
        self.assertEqual(len(modelo.instances), 4)

    def test_it_shows_undo_and_redo_working(self) -> None:
        texto, _ = self._correr()
        self.assertIn("Piezas restantes: 0", texto)
        self.assertIn("Piezas restantes: 4", texto)

    def test_it_shows_what_rotating_does(self) -> None:
        # Girar 90 grados intercambia el ancho y el fondo. Si la demo no lo
        # enseñara, no estaría demostrando nada.
        texto, _ = self._correr()
        self.assertIn("80x40x24", texto)
        self.assertIn("40x80x24", texto)


class BuildTests(unittest.TestCase):
    """`construir` se prueba aparte: es la parte sin efectos secundarios."""

    def test_the_pieces_fit_together(self) -> None:
        # Aquí murió la demo con el paso a LDU: sus coordenadas iban en studs,
        # así que las dos mitades de la base se solapaban.
        editor = construir()
        self.assertEqual(len(editor.instances), 4)

    def test_the_base_halves_touch_without_overlapping(self) -> None:
        editor = construir()
        izquierda, derecha = editor.instances[0], editor.instances[1]
        catalogo = editor.model.catalog
        self.assertEqual(
            derecha.position.x,
            izquierda.position.x + catalogo.get(izquierda.part_id).dimensions.width,
        )

    def test_the_base_is_one_undo(self) -> None:
        editor = construir()
        self.assertEqual(editor.history.undo_labels[0], "Construir base")

    def test_everything_can_be_undone(self) -> None:
        editor = construir()
        while editor.can_undo:
            editor.undo()
        self.assertEqual(len(editor.instances), 0)


if __name__ == "__main__":
    unittest.main()
