import unittest
from dataclasses import replace

from blockcad_engine import DslError, GridPosition, Orientation, parse_model
from blockcad_engine.geometry import LADRILLO, PLACA, STUD


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
        self.assertEqual(part.position, GridPosition(1 * STUD, 2 * STUD, 3 * PLACA))
        self.assertEqual(part.orientation, Orientation.z(90))
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
        self.assertEqual(model.instances[0].orientation, Orientation.z(270))


class RelativeTests(unittest.TestCase):
    """Apoyar una pieza sobre otra sin calcular la altura a mano."""

    def test_encima_stacks_on_the_previous_piece(self) -> None:
        model = parse_model(
            "ladrillo 2x4 en 0,0,0 color verde\nladrillo 2x4 encima color azul"
        )
        self.assertEqual(model.instances[1].position, GridPosition(0, 0, LADRILLO))

    def test_the_height_comes_from_the_piece_below(self) -> None:
        # Una placa mide 1 y un ladrillo 3: la altura no puede estar fija.
        model = parse_model("placa 2x4 en 0,0,0\nladrillo 2x4 encima")
        self.assertEqual(model.instances[1].position.z, PLACA)

        model = parse_model("ladrillo 2x4 en 0,0,0\nplaca 2x4 encima")
        self.assertEqual(model.instances[1].position.z, LADRILLO)

    def test_encima_de_a_named_piece(self) -> None:
        model = parse_model(
            "ladrillo 2x4 en 0,0,0 llamado base\n"
            "placa 2x4 en 8,0,0\n"
            "ladrillo 2x4 encima de base color azul"
        )
        # Se apoya en la base, no en la pieza de la línea anterior.
        self.assertEqual(model.instances[2].position, GridPosition(0, 0, LADRILLO))

    def test_desplazado_moves_it_sideways(self) -> None:
        model = parse_model(
            "ladrillo 2x4 en 0,0,0 llamado base\n"
            "ladrillo 1x1 encima de base desplazado 1,2"
        )
        self.assertEqual(model.instances[1].position, GridPosition(1 * STUD, 2 * STUD, LADRILLO))

    def test_repeat_without_desplazando_stacks_a_tower(self) -> None:
        model = parse_model(
            "ladrillo 2x2 en 0,0,0\nrepetir 4 veces:\n    ladrillo 2x2 encima"
        )
        self.assertEqual(
            [item.position.z for item in model.instances],
            [z * LADRILLO for z in (0, 1, 2, 3, 4)],
        )

    def test_repeat_offset_does_not_apply_to_encima(self) -> None:
        # `encima` significa «sobre esa pieza»: sumarle el desplazamiento del
        # bucle lo convertiría en otra cosa y dejaría huecos.
        model = parse_model(
            "ladrillo 2x2 en 0,0,0\n"
            "repetir 2 desplazando 0,0,99:\n"
            "    ladrillo 2x2 encima"
        )
        self.assertEqual([i.position.z for i in model.instances], [0, LADRILLO, 2 * LADRILLO])

    def test_a_name_can_be_used_before_it_is_shadowed(self) -> None:
        model = parse_model(
            "ladrillo 2x4 en 0,0,0 llamado base\n"
            "ladrillo 2x4 encima de base llamado piso\n"
            "ladrillo 1x1 encima de piso"
        )
        self.assertEqual(model.instances[2].position, GridPosition(0, 0, 2 * LADRILLO))

    def test_encima_without_a_previous_piece_explains_itself(self) -> None:
        with self.assertRaises(DslError) as capturado:
            parse_model("ladrillo 2x4 encima")
        self.assertIn("en 0,0,0", capturado.exception.message)

    def test_unknown_name_lists_the_known_ones(self) -> None:
        with self.assertRaises(DslError) as capturado:
            parse_model("ladrillo 2x4 en 0,0,0 llamado base\nladrillo 1x1 encima de pepe")
        self.assertIn("base", capturado.exception.message)

    def test_repeated_name_is_rejected(self) -> None:
        with self.assertRaises(DslError) as capturado:
            parse_model(
                "ladrillo 2x4 en 0,0,0 llamado base\n"
                "ladrillo 1x1 en 5,0,0 llamado base"
            )
        self.assertEqual(capturado.exception.line, 2)

    def test_stacking_never_collides_with_its_support(self) -> None:
        # Si la altura estuviera mal, la pieza se solaparía con la de abajo.
        model = parse_model(
            "ladrillo 2x4 en 0,0,0\n" + "ladrillo 2x4 encima\n" * 10
        )
        self.assertEqual(len(model.instances), 11)


class UnitTests(unittest.TestCase):
    """El lenguaje cuenta en studs y placas; el motor, en LDU.

    Esa frontera es lo que permitió cambiar el motor entero a LDU sin que
    nadie tenga que reescribir su código.
    """

    def test_the_language_still_speaks_studs_and_plates(self) -> None:
        # "en 1,2,3" = 1 stud, 2 studs, 3 placas. Es lo mismo que significaba
        # antes del cambio a LDU: el código de un usuario no se toca.
        model = parse_model("ladrillo 2x4 en 1,2,3")
        self.assertEqual(
            model.instances[0].position,
            GridPosition(1 * STUD, 2 * STUD, 3 * PLACA),
        )

    def test_half_a_stud_is_allowed(self) -> None:
        # Media distancia son 10 LDU: el paso real de la rejilla Technic, y
        # justo lo que era imposible con coordenadas en studs enteros.
        model = parse_model("ladrillo 1x1 en 0.5,0,0")
        self.assertEqual(model.instances[0].position.x, STUD // 2)

    def test_a_technic_module_is_two_and_a_half_plates(self) -> None:
        # La razón de existir de todo este cambio.
        model = parse_model("ladrillo 1x1 en 0,0,2.5")
        self.assertEqual(model.instances[0].position.z, 20)

    def test_decimals_work_in_repeat(self) -> None:
        # Ojo con el desplazamiento: medio stud es 10 LDU y un ladrillo 1x1
        # mide 20 de ancho, así que a media distancia chocaría consigo mismo.
        # 1,5 studs lo separan sin solaparlo.
        model = parse_model("repetir 2 desplazando 1.5,0,0:\n    ladrillo 1x1 en 0,0,0")
        self.assertEqual(
            [i.position.x for i in model.instances], [0, 30]
        )

    def test_half_a_stud_off_is_a_collision_for_a_1x1(self) -> None:
        # No es un fallo: un ladrillo mide un stud entero, así que a media
        # distancia se pisa con el de al lado. El motor lo dice con su línea.
        with self.assertRaises(DslError) as capturado:
            parse_model("ladrillo 1x1 en 0,0,0\nladrillo 1x1 en 0.5,0,0")
        self.assertEqual(capturado.exception.line, 2)

    def test_a_position_between_two_ldu_is_rejected(self) -> None:
        # Redondear en silencio movería la pieza sin avisar.
        with self.assertRaises(DslError) as capturado:
            parse_model("ladrillo 1x1 en 0.33,0,0")
        self.assertIn("LDU", capturado.exception.message)
        self.assertEqual(capturado.exception.line, 1)

    def test_the_error_says_where_it_lands(self) -> None:
        with self.assertRaises(DslError) as capturado:
            parse_model("ladrillo 1x1 en 0,0,0.1")
        self.assertIn("0.80", capturado.exception.message)

    def test_generated_code_comes_back_in_studs(self) -> None:
        # El camino inverso: nadie quiere leer "en 40,0,24".
        from blockcad_engine.dsl import model_to_source

        codigo = model_to_source(parse_model("ladrillo 2x4 en 2,0,3"))
        self.assertIn("en 2,0,3", codigo)

    def test_generated_code_keeps_halves(self) -> None:
        from blockcad_engine.dsl import model_to_source

        codigo = model_to_source(parse_model("ladrillo 1x1 en 0.5,0,0"))
        self.assertIn("en 0.5,0,0", codigo)


class RotationSyntaxTests(unittest.TestCase):
    """`rot 90` significa lo de siempre; los otros ejes son lo nuevo."""

    def _caja(self, codigo: str):
        model = parse_model(codigo)
        pieza = model.instances[0]
        return model.catalog.get(pieza.part_id).dimensions.rotated(pieza.orientation)

    def test_rot_alone_is_still_the_vertical_axis(self) -> None:
        # Compatibilidad: el código escrito antes de los tres ejes vale igual.
        model = parse_model("ladrillo 2x4 en 0,0,0 rot 90")
        self.assertEqual(model.instances[0].orientation, Orientation.z(90))

    def test_a_brick_can_be_stood_on_its_end(self) -> None:
        caja = self._caja("ladrillo 2x4 en 0,0,0 rot x 90")
        self.assertEqual((caja.width, caja.depth, caja.height), (40, 24, 80))

    def test_each_axis_turns_a_different_way(self) -> None:
        cajas = {
            self._caja(f"ladrillo 2x4 en 0,0,0 rot {eje} 90") for eje in "xyz"
        }
        # Un 2x4 girado sobre cada eje da tres cajas distintas. Si dos
        # coincidieran, dos ejes estarían haciendo lo mismo.
        self.assertEqual(len(cajas), 3)

    def test_rotations_chain(self) -> None:
        model = parse_model("ladrillo 2x4 en 0,0,0 rot x 90 rot z 90")
        esperado = Orientation.z(90).then(Orientation.around("x", 90))
        self.assertEqual(model.instances[0].orientation, esperado)

    def test_the_axis_is_case_insensitive(self) -> None:
        self.assertEqual(
            parse_model("ladrillo 1x1 en 0,0,0 rot X 90").instances[0].orientation,
            Orientation.around("x", 90),
        )

    def test_a_bad_axis_is_reported(self) -> None:
        with self.assertRaises(DslError) as capturado:
            parse_model("ladrillo 1x1 en 0,0,0 rot w 90")
        self.assertEqual(capturado.exception.line, 1)

    def test_a_bad_angle_is_reported(self) -> None:
        with self.assertRaises(DslError):
            parse_model("ladrillo 1x1 en 0,0,0 rot x 45")

    def test_every_orientation_survives_the_round_trip(self) -> None:
        # Generar el código de vuelta tiene que reproducir la orientación
        # exacta, o abrir un JSON giraría las piezas.
        from blockcad_engine.dsl import _GIROS_POR_MATRIZ, model_to_source

        self.assertEqual(len(_GIROS_POR_MATRIZ), 24)
        for filas in _GIROS_POR_MATRIZ:
            with self.subTest(filas=filas):
                original = parse_model("ladrillo 2x4 en 0,0,0")
                pieza = original.instances[0]
                original._instances[pieza.instance_id] = replace(
                    pieza, orientation=Orientation(filas)
                )
                vuelta = parse_model(model_to_source(original))
                self.assertEqual(vuelta.instances[0].orientation.filas, filas)

    def test_generated_code_says_rot_90_for_the_usual_turn(self) -> None:
        from blockcad_engine.dsl import model_to_source

        codigo = model_to_source(parse_model("ladrillo 2x4 en 0,0,0 rot 90"))
        self.assertIn("rot 90", codigo)
        self.assertNotIn("rot z 90", codigo)

    def test_generated_code_never_repeats_a_turn(self) -> None:
        # "rot x 270" y no "rot x 90 rot x 90 rot x 90".
        from blockcad_engine.dsl import model_to_source

        codigo = model_to_source(parse_model("ladrillo 2x4 en 0,0,0 rot x 270"))
        self.assertEqual(codigo.count("rot"), 1)


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
            [0, LADRILLO, 2 * LADRILLO],
        )

    def test_veces_is_optional(self) -> None:
        model = parse_model("repetir 2 desplazando 2,0,0:\n    ladrillo 1x1 en 0,0,0")
        self.assertEqual([i.position.x for i in model.instances], [0, 2 * STUD])

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
            {(0, 0), (2 * STUD, 0), (0, LADRILLO), (2 * STUD, LADRILLO),
             (0, 2 * LADRILLO), (2 * STUD, 2 * LADRILLO)},
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
