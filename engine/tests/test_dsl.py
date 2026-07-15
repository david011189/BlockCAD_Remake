import unittest

from blockcad_engine import DslError, GridPosition, Rotation, parse_model


class SyntaxTests(unittest.TestCase):
    def test_minimal_model(self) -> None:
        model = parse_model("ladrillo 2x4 en 0,0,0")
        self.assertEqual(len(model.instances), 1)
        part = model.instances[0]
        self.assertEqual(part.part_id, "brick_2x4")
        self.assertEqual(part.position, GridPosition(0, 0, 0))

    def test_model_name(self) -> None:
        model = parse_model('modelo "Mi casa"\nladrillo 1x1 en 0,0,0')
        self.assertEqual(model.name, "Mi casa")

    def test_name_is_optional(self) -> None:
        model = parse_model("ladrillo 1x1 en 0,0,0")
        self.assertEqual(model.name, "Modelo sin título")

    def test_all_part_prefixes(self) -> None:
        model = parse_model(
            "ladrillo 2x4 en 0,0,0\n"
            "placa 2x4 en 0,0,3\n"
            "baldosa 1x2 en 0,0,4"
        )
        self.assertEqual(
            [item.part_id for item in model.instances],
            ["brick_2x4", "plate_2x4", "tile_1x2"],
        )

    def test_raw_catalog_id_is_accepted(self) -> None:
        model = parse_model("brick_2x4 en 0,0,0")
        self.assertEqual(model.instances[0].part_id, "brick_2x4")

    def test_options(self) -> None:
        model = parse_model(
            "ladrillo 2x4 en 1,2,3 rot 90 color azul grupo 2 paso 5 transparente"
        )
        part = model.instances[0]
        self.assertEqual(part.position, GridPosition(1, 2, 3))
        self.assertEqual(part.rotation, Rotation.DEG_90)
        self.assertEqual(part.color, "#457B9D")
        self.assertEqual(part.group, 2)
        self.assertEqual(part.step, 5)
        self.assertTrue(part.transparent)

    def test_hex_color_and_named_color(self) -> None:
        model = parse_model(
            "ladrillo 1x1 en 0,0,0 color #00aaff\n"
            "ladrillo 1x1 en 2,0,0 color rojo"
        )
        self.assertEqual(model.instances[0].color, "#00AAFF")
        self.assertEqual(model.instances[1].color, "#D62828")

    def test_default_color_comes_from_catalog(self) -> None:
        model = parse_model("ladrillo 1x1 en 0,0,0")
        self.assertEqual(model.instances[0].color, "#D62828")

    def test_rotado_is_a_synonym_of_rot(self) -> None:
        model = parse_model("ladrillo 2x4 en 0,0,0 rotado 270")
        self.assertEqual(model.instances[0].rotation, Rotation.DEG_270)


class CommentTests(unittest.TestCase):
    def test_hash_comment_at_line_start(self) -> None:
        model = parse_model("# esto es un comentario\nladrillo 1x1 en 0,0,0")
        self.assertEqual(len(model.instances), 1)

    def test_slash_comment_is_inline(self) -> None:
        model = parse_model("ladrillo 1x1 en 0,0,0 color rojo  // la base")
        self.assertEqual(len(model.instances), 1)
        self.assertEqual(model.instances[0].color, "#D62828")

    def test_hash_inside_a_color_is_not_a_comment(self) -> None:
        model = parse_model("ladrillo 1x1 en 0,0,0 color #123456")
        self.assertEqual(model.instances[0].color, "#123456")

    def test_blank_lines_are_ignored(self) -> None:
        model = parse_model("\n\nladrillo 1x1 en 0,0,0\n\n\nladrillo 1x1 en 2,0,0\n")
        self.assertEqual(len(model.instances), 2)


class RepeatTests(unittest.TestCase):
    def test_repeat_stacks_upwards(self) -> None:
        model = parse_model(
            "repetir 3 veces desplazando 0,0,3:\n    ladrillo 2x2 en 0,0,0"
        )
        self.assertEqual(
            [item.position.z for item in model.instances],
            [0, 3, 6],
        )

    def test_veces_is_optional(self) -> None:
        model = parse_model("repetir 2 desplazando 2,0,0:\n    ladrillo 1x1 en 0,0,0")
        self.assertEqual([item.position.x for item in model.instances], [0, 2])

    def test_repeat_can_hold_several_lines(self) -> None:
        model = parse_model(
            "repetir 2 desplazando 0,0,3:\n"
            "    ladrillo 1x1 en 0,0,0\n"
            "    ladrillo 1x1 en 2,0,0"
        )
        self.assertEqual(len(model.instances), 4)

    def test_nested_repeat_builds_a_grid(self) -> None:
        model = parse_model(
            "repetir 3 desplazando 0,0,3:\n"
            "    repetir 2 desplazando 2,0,0:\n"
            "        ladrillo 1x1 en 0,0,0"
        )
        self.assertEqual(len(model.instances), 6)
        posiciones = {(i.position.x, i.position.z) for i in model.instances}
        self.assertEqual(
            posiciones,
            {(0, 0), (2, 0), (0, 3), (2, 3), (0, 6), (2, 6)},
        )

    def test_lines_after_a_repeat_block_are_not_repeated(self) -> None:
        model = parse_model(
            "repetir 2 desplazando 0,0,3:\n"
            "    ladrillo 1x1 en 0,0,0\n"
            "ladrillo 1x1 en 5,0,0"
        )
        self.assertEqual(len(model.instances), 3)


class ErrorTests(unittest.TestCase):
    def _error(self, source: str) -> DslError:
        with self.assertRaises(DslError) as capturado:
            parse_model(source)
        return capturado.exception

    def test_collision_points_at_the_other_line(self) -> None:
        error = self._error("ladrillo 2x4 en 0,0,0\nladrillo 1x1 en 1,1,0")
        self.assertEqual(error.line, 2)
        self.assertIn("línea 1", error.message)

    def test_collision_inside_a_repeat_says_so(self) -> None:
        error = self._error("repetir 2 desplazando 0,0,1:\n    ladrillo 2x4 en 0,0,0")
        self.assertEqual(error.line, 2)
        self.assertIn("repetición anterior", error.message)

    def test_unknown_part_reports_its_line(self) -> None:
        error = self._error("ladrillo 1x1 en 0,0,0\nladrillo 9x9 en 5,0,0")
        self.assertEqual(error.line, 2)

    def test_missing_size(self) -> None:
        self.assertEqual(self._error("ladrillo en 0,0,0").line, 1)

    def test_unknown_option(self) -> None:
        error = self._error("ladrillo 1x1 en 0,0,0 girado 90")
        self.assertIn("girado", error.message)

    def test_option_without_value(self) -> None:
        self.assertEqual(self._error("ladrillo 1x1 en 0,0,0 color").line, 1)

    def test_invalid_color(self) -> None:
        error = self._error("ladrillo 1x1 en 0,0,0 color chillon")
        self.assertEqual(error.line, 1)

    def test_invalid_rotation(self) -> None:
        self.assertEqual(self._error("ladrillo 1x1 en 0,0,0 rot 45").line, 1)

    def test_negative_z(self) -> None:
        self.assertEqual(self._error("ladrillo 1x1 en 0,0,-1").line, 1)

    def test_garbage_line(self) -> None:
        error = self._error("ladrillo 1x1 en 0,0,0\nhola que tal")
        self.assertEqual(error.line, 2)

    def test_empty_repeat(self) -> None:
        error = self._error("repetir 3 desplazando 1,0,0:")
        self.assertEqual(error.line, 1)

    def test_model_must_be_first(self) -> None:
        error = self._error('ladrillo 1x1 en 0,0,0\nmodelo "Tarde"')
        self.assertEqual(error.line, 2)

    def test_unexpected_indentation(self) -> None:
        error = self._error("ladrillo 1x1 en 0,0,0\n    ladrillo 1x1 en 3,0,0")
        self.assertEqual(error.line, 2)

    def test_error_message_names_the_line(self) -> None:
        error = self._error("ladrillo 1x1 en 0,0,-1")
        self.assertTrue(str(error).startswith("Línea 1:"))


class EmptyTests(unittest.TestCase):
    def test_empty_source_is_an_empty_model(self) -> None:
        model = parse_model("")
        self.assertEqual(len(model.instances), 0)

    def test_only_comments_is_an_empty_model(self) -> None:
        model = parse_model("# nada\n// tampoco")
        self.assertEqual(len(model.instances), 0)


if __name__ == "__main__":
    unittest.main()
