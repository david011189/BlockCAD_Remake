"""Insertar no es chocar.

Technic no se apila: se construye metiendo cosas dentro de otras. Un pin
*ocupa* el agujero y un eje *atraviesa* la viga, así que sus cajas se solapan
de verdad. Para un motor de ladrillos de sistema eso es un choque —y hace bien:
dos ladrillos se apoyan y se tocan, nunca se invaden—, pero aplicado a Technic
convierte cada unión real en un error y hace el set entero imposible de montar.

Lo que estas pruebas defienden es que la excepción sea *estrecha*: legal solo
cuando el macho y el agujero son la MISMA RECTA. Aceptar cualquier solapamiento
entre piezas de las que se insertan sería más fácil y dejaría al motor sin lo
que lo justifica: saber si un modelo se puede construir.

Las posiciones no están escritas a ojo. Salen de preguntarle al motor dónde
caen los puntos: la viga 3701 en el origen tiene agujeros a y=20, 40 y 60,
todos a z=14, con la recta (1,0,0).
"""

import unittest

from blockcad_engine import BlockModel, GridPosition, Orientation
from blockcad_engine.catalogos import cargar
from blockcad_engine.errors import CollisionError

#: El pin 2780 sin girar apunta en (1,0,0), como el agujero: la postura de
#: la viga la manda su nombre, y el pin nace alineado con ella. Puesto aquí,
#: su punto cae en (10, 20, 14): sobre la recta del primer agujero, y
#: centrado a lo ancho de la viga.
PIN_EN_EL_PRIMER_AGUJERO = (-10, 12, 6)
DE_LADO = Orientation.around("z", 90)


class InsercionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalogo = cargar("wedo")
        self.modelo = BlockModel(catalog=self.catalogo)
        self.viga = self.modelo.add("3701", GridPosition(0, 0, 0))

    def poner(self, pieza, posicion, orientacion=Orientation()):
        return self.modelo.add(
            pieza, GridPosition(*posicion), orientation=orientacion
        )

    # --- lo que tiene que entrar ------------------------------------------

    def test_a_pin_goes_into_a_hole(self) -> None:
        """El caso que bloqueaba el set entero: el paso 2 del camión.

        Sin esto no se puede montar ni la primera página de las instrucciones
        de ningún modelo WeDo.
        """
        self.poner("2780", PIN_EN_EL_PRIMER_AGUJERO)

    def test_an_inserted_pin_is_connected(self) -> None:
        # Un pin metido casi nunca cae sobre el punto del agujero: entra por
        # él y se queda a otra profundidad. Lo que comparten es la recta.
        pin = self.poner("2780", PIN_EN_EL_PRIMER_AGUJERO)
        unidas = self.modelo.connected_to(pin.instance_id)
        self.assertEqual([p.part_id for p in unidas], ["3701"])

    def test_the_same_pin_fits_every_hole_of_the_beam(self) -> None:
        # Los agujeros van cada 20 LDU: un módulo Technic.
        for salto in (0, 20, 40):
            with self.subTest(agujero=salto):
                modelo = BlockModel(catalog=self.catalogo)
                modelo.add("3701", GridPosition(0, 0, 0))
                x, y, z = PIN_EN_EL_PRIMER_AGUJERO
                modelo.add("2780", GridPosition(x, y + salto, z))

    def test_an_axle_goes_through_a_beam(self) -> None:
        # Un eje no se mete: atraviesa, y sale por el otro lado. Es como se
        # montan los engranajes, así que sin esto no hay transmisión posible.
        # La viga también se endereza —el nombre manda—, así que sus agujeros
        # cruzan por X, y el eje, que nace en Y, se gira un cuarto de vuelta.
        modelo = BlockModel(catalog=self.catalogo)
        modelo.add("3702", GridPosition(0, 0, 0))  # viga 1x8
        eje = modelo.add("3706", GridPosition(-50, 34, 8), orientation=DE_LADO)
        self.assertEqual(
            [p.part_id for p in modelo.connected_to(eje.instance_id)], ["3702"]
        )

    def test_an_axle_beside_the_hole_collides(self) -> None:
        modelo = BlockModel(catalog=self.catalogo)
        modelo.add("3702", GridPosition(0, 0, 0))
        with self.assertRaises(CollisionError):
            modelo.add("3706", GridPosition(-50, 34, 12), orientation=DE_LADO)

    # --- lo que NO puede entrar -------------------------------------------

    def test_a_pin_beside_the_hole_still_collides(self) -> None:
        """Paralelo al agujero pero 4 LDU más arriba: atraviesa el plástico.

        Esta es la prueba que separa la regla honesta de la fácil. Es el mismo
        pin, en la misma dirección, dentro de la misma viga: lo único que falla
        es que su recta no es la del agujero. Si esto entrara, el motor habría
        dejado de saber si un modelo se puede construir.
        """
        x, y, z = PIN_EN_EL_PRIMER_AGUJERO
        with self.assertRaises(CollisionError):
            self.poner("2780", (x, y, z + 4))

    def test_a_pin_between_two_holes_collides(self) -> None:
        # Los agujeros están cada 20; a mitad de camino no hay nada.
        x, y, z = PIN_EN_EL_PRIMER_AGUJERO
        with self.assertRaises(CollisionError):
            self.poner("2780", (x, y + 5, z))

    def test_a_pin_across_the_beam_collides(self) -> None:
        # Girado un cuarto de vuelta, el pin apunta a lo largo de la viga:
        # la recorre por dentro en vez de entrar por un agujero.
        with self.assertRaises(CollisionError):
            self.poner("2780", (2, 20, 6), DE_LADO)

    def test_two_beams_in_the_same_place_still_collide(self) -> None:
        # Las dos tienen agujeros, y los agujeros hasta coinciden. No sirve:
        # ninguna es el macho de la otra.
        with self.assertRaises(CollisionError):
            self.poner("3701", (0, 0, 0))

    def test_a_brick_inside_the_beam_still_collides(self) -> None:
        with self.assertRaises(CollisionError):
            self.poner("3001", (0, 0, 0))


class RotulaTests(unittest.TestCase):
    """La bola se asienta en su cazoleta: punto compartido, no recta.

    Una rótula no tiene recta —girar hacia cualquier lado es su oficio—,
    así que la regla es distinta a la del pin: el centro de la bola tiene
    que SER el centro de la copa. Es lo que piden los ganchos de remolque
    del camión de reciclaje (pasos 16 a 19).

    Las posiciones salen de preguntarle al motor: la cazoleta del 92013 en
    el origen tiene su copa en (60, 20, 14), y la bola del 57909 girado
    media vuelta cae ahí puesto en (47, 0, 0).
    """

    def setUp(self) -> None:
        self.modelo = BlockModel(catalog=cargar("wedo"))
        self.modelo.add("92013", GridPosition(0, 0, 0))

    MEDIA_VUELTA = Orientation.z(180)

    def test_the_ball_seats_in_the_socket(self) -> None:
        # Los brazos se interpenetran de verdad: sin la regla, esto es choque.
        bola = self.modelo.add(
            "57909", GridPosition(47, 0, 0), orientation=self.MEDIA_VUELTA
        )
        unidas = self.modelo.connected_to(bola.instance_id)
        self.assertEqual([p.part_id for p in unidas], ["92013"])

    def test_a_ball_beside_the_cup_collides(self) -> None:
        # La misma bola, 4 LDU al lado: atraviesa el plástico de la copa.
        with self.assertRaises(CollisionError):
            self.modelo.add(
                "57909", GridPosition(47, 4, 0), orientation=self.MEDIA_VUELTA
            )

    def test_a_pin_does_not_seat_in_the_cup(self) -> None:
        # La recta del pin pasa por el centro de la copa, pero un pin no es
        # una bola: falla por el TIPO, no por la geometría.
        with self.assertRaises(CollisionError):
            self.modelo.add("2780", GridPosition(40, 12, 6))

    def test_a_ball_does_not_enter_a_pin_hole(self) -> None:
        # El caso espejo: el centro de la bola cae en el punto del agujero
        # de una viga, y aun así no entra: una bola no cabe por un agujero.
        modelo = BlockModel(catalog=cargar("wedo"))
        modelo.add("3701", GridPosition(0, 0, 0))
        with self.assertRaises(CollisionError):
            modelo.add("57909", GridPosition(-50, 0, 0))


class EncajeTipadoTests(unittest.TestCase):
    """No todo macho entra en todo agujero.

    Un eje pasa por el agujero redondo (gira libre: así se cuelgan las ruedas)
    y por el de cruz (gira solidario: así se mueven los engranajes). Un pin
    solo cabe en el redondo: la cruz le cierra el paso al cilindro. Sin este
    tipado, el motor aceptaría uniones que en plástico no existen.
    """

    def setUp(self) -> None:
        self.modelo = BlockModel(catalog=cargar("wedo"))

    def test_a_pin_does_not_fit_a_cross_hole(self) -> None:
        # El engranaje 10928 tiene su agujero de cruz en (12,0,12) con recta
        # (0,1,0). El pin girado apunta igual y su recta pasa por ahí: la
        # geometría es la de una inserción perfecta. Falla por el TIPO.
        self.modelo.add("10928", GridPosition(0, 0, 0))
        with self.assertRaises(CollisionError):
            self.modelo.add("2780", GridPosition(4, -8, 4), orientation=DE_LADO)

    def test_an_axle_does_fit_a_cross_hole(self) -> None:
        # La misma recta, el macho que sí cabe. El eje ya apunta en (0,1,0)
        # sin girarlo: es la postura de toda pieza lineal.
        self.modelo.add("10928", GridPosition(0, 0, 0))
        self.modelo.add("4519", GridPosition(6, -20, 6))


class LenguajeTests(unittest.TestCase):
    """Insertar sin calcular LDU: «en el agujero 2 de marco».

    Quien escribe dice qué unión quiere y el motor resuelve giro y posición,
    igual que `encima` resuelve la altura. Antes de esto, meter un pin exigía
    saber que el agujero cae en z=14 LDU y escribir `2780 en 0.6,-1.5,0.75
    rot z 90`, que no es un lenguaje: es una calculadora.
    """

    def compilar(self, codigo: str) -> BlockModel:
        from blockcad_engine import parse_model

        return parse_model('catalogo "wedo"\n' + codigo)

    def test_the_truck_step_two_compiles_as_written(self) -> None:
        # Las instrucciones reales del camión de reciclaje: el ladrillo
        # naranja, el verde con agujeros encima, y dos pines metidos. Es el
        # paso que descubrió todo esto.
        modelo = self.compilar(
            "3001 en 0,0,0 llamado base\n"
            "3701 encima de base llamado verde\n"
            "2780 en el agujero 1 de verde\n"
            "2780 en el agujero 3 de verde"
        )
        self.assertEqual(len(modelo.instances), 4)

    def test_the_pin_lands_centered_in_the_hole(self) -> None:
        # La viga en el origen tiene su primer agujero en y=20, z=14, cruzando
        # el ancho. El pin (40 de largo) queda centrado: asoma 10 por cada
        # cara, listo para recibir otra viga.
        modelo = self.compilar("3701 en 0,0,0 llamado v\n2780 en el agujero 1 de v")
        pin = modelo.instances[-1]
        definicion = modelo.catalog.get("2780")
        macho = [c for c in pin.world_connections(definicion) if c.es_macho][0]
        self.assertEqual(macho.punto, (10, 20, 14))

    def test_displacement_slides_along_the_line(self) -> None:
        # `desplazado 0.5` son 10 LDU por la recta del agujero, no por x.
        modelo = self.compilar(
            "3701 en 0,0,0 llamado v\n"
            "2780 en el agujero 1 de v desplazado 0.5"
        )
        pin = modelo.instances[-1]
        definicion = modelo.catalog.get("2780")
        macho = [c for c in pin.world_connections(definicion) if c.es_macho][0]
        self.assertEqual(macho.punto, (20, 20, 14))

    def test_holes_are_numbered_by_position(self) -> None:
        # Agujeros 1, 2 y 3 de la viga: y=20, 40, 60. El número se puede
        # contar mirando el visor.
        for numero, y in ((1, 20), (2, 40), (3, 60)):
            with self.subTest(agujero=numero):
                modelo = self.compilar(
                    f"3701 en 0,0,0 llamado v\n2780 en el agujero {numero} de v"
                )
                pin = modelo.instances[-1]
                definicion = modelo.catalog.get("2780")
                macho = [
                    c for c in pin.world_connections(definicion) if c.es_macho
                ][0]
                self.assertEqual(macho.punto[1], y)

    def test_without_a_name_it_uses_the_last_piece(self) -> None:
        self.compilar("3701 en 0,0,0\n2780 en el agujero 2")

    def test_an_axle_goes_through_a_round_hole_too(self) -> None:
        self.compilar("3701 en 0,0,0 llamado v\n4519 en el agujero 2 de v")

    def test_the_errors_teach(self) -> None:
        # Cada error dice qué está mal Y qué hacer. Se comprueba el contenido,
        # no la frase exacta: la redacción puede mejorar sin romper nada.
        from blockcad_engine.errors import DslError

        casos = (
            ("3701 en 0,0,0 llamado v\n2780 en el agujero 9 de v", "3 agujero"),
            ("3701 en 0,0,0 llamado v\n3001 en el agujero 1 de v", "nada que meter"),
            ("10928 en 0,0,0 llamado g\n2780 en el agujero 1 de g", "cruz"),
            # rot 90 saca el pin de la recta del agujero. Ojo: rot x 90 ya no
            # sirve de caso malo, porque girar sobre X conserva la dirección X.
            ("3701 en 0,0,0 llamado v\n2780 en el agujero 1 de v rot 90", "giro"),
            ("3001 en 0,0,0 llamado b\n2780 en el agujero 1 de b", "no tiene agujeros"),
        )
        for codigo, pista in casos:
            with self.subTest(pista=pista):
                with self.assertRaises(DslError) as ctx:
                    self.compilar(codigo)
                self.assertIn(pista, str(ctx.exception))

    def test_a_gear_slides_onto_an_axle(self) -> None:
        """El caso espejo: la hembra que se encaja sobre el macho.

        Un engranaje no se mete en nada —es él quien recibe el eje—, así que
        `en el agujero de` no podía expresarlo: la recta la pone el eje y el
        agujero lo trae la pieza que se coloca.
        """
        modelo = self.compilar(
            "viga 7 en 0,0,2 rot x 90 llamado chasis\n"
            "eje 6 en el agujero 2 de chasis llamado eje1\n"
            "32270 en el eje de eje1 desplazado -1.5"
        )
        rueda = modelo.instances[-1]
        unidas = {p.part_id for p in modelo.connected_to(rueda.instance_id)}
        self.assertIn("3706", unidas)

    def test_the_motor_pattern_of_the_truck(self) -> None:
        # Motor, eje en su boca (el agujero 3: los otros son de pin), y la
        # rueda dentada en la mitad libre del eje. Es el arranque real de
        # cualquier modelo WeDo con transmisión.
        modelo = self.compilar(
            "21980 en 0,0,0 llamado motor\n"
            "4519 en el agujero 3 de motor llamado eje\n"
            "32270 en el eje de eje desplazado -1"
        )
        self.assertEqual(len(modelo.instances), 3)
        self.assertFalse(modelo.floating())

    def test_a_centered_gear_inside_the_motor_is_refused(self) -> None:
        # Sin desplazar, el engranaje cae dentro del cuerpo del motor. Que
        # esto choque es la regla estrecha trabajando: la recta del agujero
        # del engranaje coincide con la del motor, pero el motor no es un
        # macho metido en él.
        from blockcad_engine.errors import DslError

        with self.assertRaises(DslError):
            self.compilar(
                "21980 en 0,0,0 llamado motor\n"
                "4519 en el agujero 3 de motor llamado eje\n"
                "32270 en el eje de eje"
            )

    def test_a_wheel_bigger_than_its_height_names_the_line(self) -> None:
        # La viga por defecto tiene los agujeros en vertical: un eje metido
        # ahí apunta al suelo. El error debe decir la línea y el remedio, no
        # solo «la coordenada z no puede ser negativa» sin dónde.
        from blockcad_engine.errors import DslError

        with self.assertRaises(DslError) as ctx:
            self.compilar(
                "viga 7 en 0,0,3 llamado chasis\n"
                "eje 6 en el agujero 2 de chasis"
            )
        self.assertEqual(ctx.exception.line, 3)
        self.assertIn("más arriba", str(ctx.exception))

    def test_en_el_eje_errors_teach_too(self) -> None:
        from blockcad_engine.errors import DslError

        casos = (
            # Una viga no tiene eje sobre el que encajar.
            ("3701 en 0,0,0 llamado v\n32270 en el eje de v", "no tiene eje"),
            # Un ladrillo no tiene agujero por donde pase un eje.
            (
                "3701 en 0,0,0 llamado v\n4519 en el agujero 2 de v llamado e\n"
                "3001 en el eje de e",
                "por donde pase un eje",
            ),
        )
        for codigo, pista in casos:
            with self.subTest(pista=pista):
                with self.assertRaises(DslError) as ctx:
                    self.compilar(codigo)
                self.assertIn(pista, str(ctx.exception))

    def test_a_beam_hangs_from_an_axle_by_a_chosen_hole(self) -> None:
        """`por su agujero 1`: la puerta de una barrera, colgada de su bisagra.

        Una viga tiene siete agujeros y colgarla exige decir por cuál. Es lo
        que faltaba para que un motor LEVANTE algo: motor, eje en su boca, y
        la palanca colgada del eje.
        """
        modelo = self.compilar(
            "21980 en 0,0,0 llamado motor\n"
            "eje 6 en el agujero 3 de motor desplazado -2 llamado bisagra\n"
            "viga 7 en el eje de bisagra por su agujero 1 desplazado -2 rot x 90"
        )
        puerta = modelo.instances[-1]
        unidas = {p.part_id for p in modelo.connected_to(puerta.instance_id)}
        self.assertIn("3706", unidas)
        self.assertFalse(modelo.floating())

    def test_both_poses_of_the_door_compile(self) -> None:
        # La puerta subida y bajada son el mismo código con un giro más: el
        # grado de libertad que queda libre es justo el de la bisagra.
        for giro in ("rot x 90", "rot x 90 rot y 270"):
            with self.subTest(giro=giro):
                self.compilar(
                    "21980 en 0,0,0 llamado motor\n"
                    "eje 6 en el agujero 3 de motor desplazado -2 llamado b\n"
                    f"viga 7 en el eje de b por su agujero 1 desplazado -2 {giro}"
                )

    def test_a_door_pointing_into_the_floor_is_refused(self) -> None:
        from blockcad_engine.errors import DslError

        with self.assertRaises(DslError) as ctx:
            self.compilar(
                "21980 en 0,0,0 llamado motor\n"
                "eje 6 en el agujero 3 de motor desplazado -2 llamado b\n"
                "viga 7 en el eje de b por su agujero 1 desplazado -2 "
                "rot x 90 rot y 180"
            )
        self.assertIn("más arriba", str(ctx.exception))

    def test_hanging_a_beam_without_choosing_a_hole_teaches(self) -> None:
        from blockcad_engine.errors import DslError

        with self.assertRaises(DslError) as ctx:
            self.compilar(
                "3701 en 0,0,0 llamado v\n"
                "4519 en el agujero 2 de v llamado e\n"
                "viga 7 en el eje de e rot x 90"
            )
        self.assertIn("por su agujero", str(ctx.exception))

    def test_choosing_a_hole_that_does_not_exist_teaches(self) -> None:
        from blockcad_engine.errors import DslError

        with self.assertRaises(DslError) as ctx:
            self.compilar(
                "3701 en 0,0,0 llamado v\n"
                "4519 en el agujero 2 de v llamado e\n"
                "viga 7 en el eje de e por su agujero 9 rot x 90"
            )
        self.assertIn("7 agujeros", str(ctx.exception))

    def test_the_result_survives_the_round_trip(self) -> None:
        # El código generado desde el modelo usa `en x,y,z` con decimales.
        # Tiene que volver a compilar y dejar las piezas donde estaban.
        from blockcad_engine.dsl import model_to_source, parse_model

        modelo = self.compilar(
            "3701 en 0,0,0 llamado v\n2780 en el agujero 1 de v"
        )
        texto = 'catalogo "wedo"\n' + model_to_source(modelo)
        segundo = parse_model(texto)
        self.assertEqual(
            [(p.part_id, p.position) for p in modelo.instances],
            [(p.part_id, p.position) for p in segundo.instances],
        )


class ApilarSigueIgualTests(unittest.TestCase):
    """Lo de siempre no se puede haber roto por el camino."""

    def setUp(self) -> None:
        self.modelo = BlockModel(catalog=cargar("wedo"))

    def test_bricks_still_stack(self) -> None:
        self.modelo.add("3001", GridPosition(0, 0, 0))
        self.modelo.add("3001", GridPosition(0, 0, 24))

    def test_two_bricks_in_the_same_place_still_collide(self) -> None:
        self.modelo.add("3001", GridPosition(0, 0, 0))
        with self.assertRaises(CollisionError):
            self.modelo.add("3001", GridPosition(0, 0, 0))

    def test_bricks_side_by_side_still_fit(self) -> None:
        # Se tocan y no se invaden: 40 LDU es justo el ancho de un 2x4.
        self.modelo.add("3001", GridPosition(0, 0, 0))
        self.modelo.add("3001", GridPosition(80, 0, 0))


class CalzadoTests(unittest.TestCase):
    """El neumatico abraza a su llanta: cuarta manera legal de solaparse."""

    def setUp(self) -> None:
        self.modelo = BlockModel(catalog=cargar("wedo"))
        self.modelo.add("55982", GridPosition(100, 100, 40))

    def test_the_tyre_mounts_and_is_connected(self) -> None:
        # Concentrico en el plano de la rueda y dentro del tambor. Y cuenta
        # como unido: la rueda montada no flota ni esta suelta.
        neumatico = self.modelo.add("92402", GridPosition(83, 101, 23))
        unidas = self.modelo.connected_to(neumatico.instance_id)
        self.assertEqual([p.part_id for p in unidas], ["55982"])
        self.assertFalse(self.modelo.floating())

    def test_off_centre_still_collides(self) -> None:
        with self.assertRaises(CollisionError):
            self.modelo.add("92402", GridPosition(87, 101, 23))

    def test_outside_the_barrel_collides(self) -> None:
        with self.assertRaises(CollisionError):
            self.modelo.add("92402", GridPosition(83, 90, 23))

    def test_a_crossed_tyre_does_not_mount(self) -> None:
        # Centrado pero girado un cuarto de vuelta: el ancho corre por otro
        # eje y no hay calzado que valga.
        with self.assertRaises(CollisionError):
            self.modelo.add(
                "92402", GridPosition(83, 80, 44),
                orientation=Orientation.around("x", 90),
            )


class AcogidaTests(unittest.TestCase):
    """La caja del sinfin acoge al sinfin: quinta manera legal de solaparse."""

    def setUp(self) -> None:
        self.modelo = BlockModel(catalog=cargar("wedo"))
        self.modelo.add("28698", GridPosition(100, 100, 40))

    GIRADO = Orientation.z(90)

    def test_the_worm_lives_inside_its_box(self) -> None:
        # Girado para alinear su agujero con las bocas bajas, y ENTERO
        # dentro. Queda unido: ni flota ni esta suelto.
        gusano = self.modelo.add(
            "32905", GridPosition(138, 107, 49), orientation=self.GIRADO
        )
        unidas = self.modelo.connected_to(gusano.instance_id)
        self.assertEqual([p.part_id for p in unidas], ["28698"])
        self.assertFalse(self.modelo.floating())

    def test_off_the_line_still_collides(self) -> None:
        # Dentro de la caja pero fuera de la recta de las bocas: por ahi no
        # entraria el eje, y no hay acogida que valga.
        with self.assertRaises(CollisionError):
            self.modelo.add(
                "32905", GridPosition(138, 107, 57), orientation=self.GIRADO
            )

    def test_crossed_the_worm_does_not_fit(self) -> None:
        # Sin girar, su agujero corre perpendicular a las bocas.
        with self.assertRaises(CollisionError):
            self.modelo.add("32905", GridPosition(138, 100, 49))

    def test_the_stop_forbids_the_high_tunnel(self) -> None:
        # La pieza real lleva un TOPE: el gusano solo entra en la camara
        # baja. Girado y entero dentro, pero sobre la recta alta, sigue
        # siendo choque: ese no es su asiento.
        with self.assertRaises(CollisionError):
            self.modelo.add(
                "32905", GridPosition(138, 107, 89), orientation=self.GIRADO
            )

    def test_the_gear_crowns_the_box(self) -> None:
        # El segundo huesped: el engranaje de 24 entra por la ranura de
        # arriba, ASOMA por ella (la boca del contenedor esta abierta al
        # cielo) y muerde al gusano en angulo recto. Queda unido a los dos.
        self.modelo.add(
            "32905", GridPosition(138, 107, 49), orientation=self.GIRADO
        )
        engranaje = self.modelo.add("24505", GridPosition(108, 110, 70))
        unidas = self.modelo.connected_to(engranaje.instance_id)
        self.assertEqual(
            sorted(p.part_id for p in unidas), ["28698", "32905"]
        )
        self.assertFalse(self.modelo.floating())

    def test_through_a_wall_is_still_a_crash(self) -> None:
        # Asomar por arriba es legal; atravesar un costado no. Corrido dos
        # studs, el engranaje sale por la pared y ya no hay recta de boca
        # que lo salve.
        with self.assertRaises(CollisionError):
            self.modelo.add("24505", GridPosition(148, 110, 70))

    def test_the_box_does_not_host_other_pieces(self) -> None:
        # El contenedor declara a QUIEN acoge: un ladrillo dentro de la caja
        # sigue siendo un choque. (Un pin, en cambio, SI puede insertarse en
        # las bocas de la caja: eso es una insercion legitima, no acogida.)
        with self.assertRaises(CollisionError):
            self.modelo.add("3004", GridPosition(120, 110, 50))


class MordidaSinfinTests(unittest.TestCase):
    """El tornillo sin fin muerde en angulo recto: su propia geometria."""

    def setUp(self) -> None:
        self.modelo = BlockModel(catalog=cargar("wedo"))
        self.modelo.add("32905", GridPosition(0, 0, 0))

    def test_perpendicular_at_the_sum_of_radii_bites(self) -> None:
        # Ejes cruzados a 90 grados, separados 40 LDU: el radio primitivo
        # de la rueda de 24 (30) mas el del sinfin (medio stud). Las cajas
        # se solapan de verdad y aun asi es legal — y cuenta como union.
        rueda = self.modelo.add(
            "24505", GridPosition(3, 0, 21), orientation=Orientation.z(90)
        )
        unidas = self.modelo.connected_to(rueda.instance_id)
        self.assertEqual([p.part_id for p in unidas], ["32905"])
        self.assertFalse(self.modelo.floating())

    def test_too_close_the_teeth_crash(self) -> None:
        # Dos LDU mas cerca los dientes chocan de frente.
        with self.assertRaises(CollisionError):
            self.modelo.add(
                "24505", GridPosition(3, 0, 19), orientation=Orientation.z(90)
            )

    def test_parallel_axes_are_not_a_worm_bite(self) -> None:
        # Sin girar, los ejes corren paralelos: asi muerden dos ruedas,
        # no un sinfin. Y como el sinfin no cuenta dientes, no hay mordida
        # que valga: es choque.
        with self.assertRaises(CollisionError):
            self.modelo.add("24505", GridPosition(3, 0, 21))


if __name__ == "__main__":
    unittest.main()
