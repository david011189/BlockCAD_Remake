"""Lenguaje textual de BlockCAD: código a modelo.

El lenguaje describe una construcción línea a línea. El analizador lo traduce
a un `BlockModel` y aprovecha la validación del motor, de modo que una
colisión se comunica indicando la línea que la provocó.

Ejemplo::

    modelo "Casa sencilla"

    ladrillo 2x4 en 0,0,0 color rojo
    ladrillo 2x4 en 2,0,0 color amarillo   // la otra mitad de la base

    repetir 4 veces desplazando 0,0,3:
        ladrillo 2x2 en 1,1,3 color azul
"""

from __future__ import annotations

import re

from .catalogos import cargar as cargar_catalogo
from .errors import BlockCADError, DslError
from .geometry import (
    MODULO_TECHNIC,
    PLACA,
    STUD,
    Connection,
    GridPosition,
    Orientation,
)
from .model import DEFAULT_MODEL_NAME, BlockModel, PlacedPart, _paralelas
from .parts import PartCatalog, validate_color

#: Nombre en el lenguaje -> prefijo del identificador en el catálogo.
PART_PREFIXES = {
    "ladrillo": "brick",
    "placa": "plate",
    "baldosa": "tile",
    "viga": "beam",
    "eje": "axle",
}

#: Colores con nombre, para no escribir hexadecimal.
NAMED_COLORS = {
    "rojo": "#D62828",
    "azul": "#457B9D",
    "celeste": "#A8DADC",
    "amarillo": "#F6BD60",
    "verde": "#2A9D8F",
    "naranja": "#E76F51",
    "blanco": "#F1FAEE",
    "negro": "#1D1D1D",
    "gris": "#8D99AE",
    "marron": "#6D4C41",
    "rosa": "#E5989B",
    "morado": "#7B2CBF",
}

#: Los inversos, para generar código a partir de un modelo.
_PREFIX_NAMES = {prefijo: nombre for nombre, prefijo in PART_PREFIXES.items()}
_COLOR_NAMES = {valor: nombre for nombre, valor in NAMED_COLORS.items()}

# La medida puede ser doble ("2x4") o simple ("7"): una viga se mide con un
# solo número, y sin esto se escribiría "beam_7" en vez de "viga 7".
_PART_ID_RE = re.compile(r"^(?P<prefijo>[a-z]+)_(?P<medida>\d+(?:x\d+)?)$")

_NAME_RE = re.compile(r'^modelo\s+"(?P<nombre>[^"]*)"\s*$')

_CATALOGO_RE = re.compile(r'^catalogo\s+"(?P<nombre>[^"]*)"\s*$')

_REPEAT_RE = re.compile(
    r"^repetir\s+(?P<veces>\d+)(?:\s+veces)?"
    # Sin desplazamiento el bloque se repite en el sitio, que es lo que hace
    # falta al apilar con `encima`.
    r"(?:\s+desplazando\s+(?P<dx>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<dy>-?\d+(?:\.\d+)?)\s*,\s*(?P<dz>-?\d+(?:\.\d+)?))?"
    r"\s*:$"
)

_PIECE_RE = re.compile(
    # El identificador puede empezar por dígito: los moldes de LEGO se llaman
    # 3001 o 32316, y es como vienen en las instrucciones.
    r"^(?P<tipo>[A-Za-z0-9_][A-Za-z0-9_]*)"
    # Un ladrillo se mide con dos números ("2x4") y una viga con uno ("7").
    r"(?:\s+(?P<medida>\d+(?:x\d+)?))?"
    r"\s+(?P<lugar>(?:encima|en)\b.*)$"
)

# Se admiten decimales porque el motor trabaja en LDU y hay posiciones reales
# que no son un número entero de studs: media distancia son 0,5 studs, y una
# viga Technic mide 2,5 placas de alto. El separador decimal es el punto; la
# coma ya separa las coordenadas.
_NUMERO = r"-?\d+(?:\.\d+)?"

_ABSOLUTO_RE = re.compile(
    rf"^en\s+(?P<x>{_NUMERO})\s*,\s*(?P<y>{_NUMERO})\s*,\s*(?P<z>{_NUMERO})"
    r"(?P<opciones>.*)$"
)

_ENCIMA_RE = re.compile(
    r"^encima(?:\s+de\s+(?P<nombre>[^\W\d]\w*))?"
    rf"(?:\s+desplazado\s+(?P<dx>{_NUMERO})\s*,\s*(?P<dy>{_NUMERO}))?"
    r"(?P<opciones>.*)$"
)

# «en el agujero 2 de marco desplazado 0.5». El desplazamiento es UN número
# —módulos por la recta del agujero—, no dos como en `encima`: dentro de un
# agujero solo se puede resbalar en una dirección.
_AGUJERO_RE = re.compile(
    r"^en\s+(?:el\s+)?agujero\s+(?P<numero>\d+)"
    r"(?:\s+de\s+(?P<nombre>[^\W\d]\w*))?"
    rf"(?:\s+desplazado\s+(?P<d>{_NUMERO}))?"
    r"(?P<opciones>.*)$"
)

# «en el eje de motor1»: el caso espejo. Aquí no hay número porque un eje es
# una sola recta; lo que se elige es cuánto resbalar por ella. `por su
# agujero 2` dice por cuál de los agujeros PROPIOS se cuelga la pieza: a un
# engranaje le sobra (tiene uno), a una viga le hace falta (tiene siete).
_EJE_RE = re.compile(
    r"^en\s+(?:el\s+)?eje"
    r"(?:\s+de\s+(?P<nombre>[^\W\d]\w*))?"
    r"(?:\s+por\s+su\s+agujero\s+(?P<agujero>\d+))?"
    rf"(?:\s+desplazado\s+(?P<d>{_NUMERO}))?"
    r"(?P<opciones>.*)$"
)


def _a_ldu(valor: str, unidad: int, nombre_unidad: str, line: int) -> int:
    """Traduce lo que escribe el usuario a las unidades del motor.

    El lenguaje cuenta en studs y placas, que es como piensa quien construye.
    El motor cuenta en LDU, que es la única unidad donde todo LEGO es entero.
    Aquí se cruza esa frontera, y en un solo sitio.

    Los decimales valen —media distancia es 0,5 studs— pero el resultado
    tiene que caer exacto: redondear en silencio movería la pieza sin avisar.
    """
    exacto = float(valor) * unidad
    entero = round(exacto)
    if abs(exacto - entero) > 1e-6:
        raise DslError(
            line,
            f"{valor} {nombre_unidad} son {exacto:.2f} LDU, y una posición no "
            f"puede caer entre dos. Un {nombre_unidad[:-1]} son {unidad} LDU.",
        )
    return entero


def _strip_comment(line: str) -> str:
    # `#` inicia comentario solo al principio de la línea, porque en cualquier
    # otro sitio es el comienzo de un color. `//` sirve en cualquier posición.
    if line.lstrip().startswith("#"):
        return ""
    index = line.find("//")
    return line if index < 0 else line[:index]


def _resolve_color(value: str, line: int) -> str:
    if value.lower() in NAMED_COLORS:
        return NAMED_COLORS[value.lower()]
    try:
        return validate_color(value)
    except BlockCADError as exc:
        nombres = ", ".join(sorted(NAMED_COLORS))
        raise DslError(
            line,
            f"{exc} También puedes usar un nombre: {nombres}.",
        ) from exc


def _resolve_part_id(tipo: str, medida: str | None, line: int) -> str:
    if tipo in PART_PREFIXES:
        if not medida:
            raise DslError(
                line,
                f"'{tipo}' necesita una medida, por ejemplo '{tipo} 2x4'.",
            )
        return f"{PART_PREFIXES[tipo]}_{medida}"

    if medida:
        raise DslError(
            line,
            f"No se esperaba una medida después de '{tipo}'.",
        )
    return tipo


def _parse_options(text: str, line: int) -> dict:
    tokens = text.split()
    options: dict = {}
    index = 0

    def _value(keyword: str) -> str:
        nonlocal index
        if index + 1 >= len(tokens):
            raise DslError(line, f"Falta el valor de '{keyword}'.")
        index += 1
        return tokens[index]

    while index < len(tokens):
        token = tokens[index]
        if token in ("rot", "rotado"):
            # `rot 90` es el giro de siempre, sobre el eje vertical, y sigue
            # significando lo mismo. `rot x 90` gira sobre otro eje, y varios
            # `rot` seguidos se encadenan: "rot x 90 rot z 180".
            siguiente = _value(token)
            if siguiente.lower() in ("x", "y", "z"):
                eje = siguiente.lower()
                raw = _value(f"rot {eje}")
            else:
                eje = "z"
                raw = siguiente

            try:
                grados = int(raw)
            except ValueError as exc:
                raise DslError(
                    line, f"El giro espera grados, no {raw!r}."
                ) from exc

            try:
                giro = Orientation.around(eje, grados)
            except BlockCADError as exc:
                raise DslError(line, str(exc)) from exc

            options["orientation"] = giro.then(
                options.get("orientation", Orientation())
            )
        elif token == "color":
            options["color"] = _resolve_color(_value(token), line)
        elif token == "grupo":
            options["group"] = _int_option(_value(token), "grupo", line)
        elif token == "paso":
            options["step"] = _int_option(_value(token), "paso", line)
        elif token == "transparente":
            options["transparent"] = True
        elif token == "llamado":
            options["nombre"] = _value(token)
        else:
            raise DslError(line, f"Opción desconocida: {token!r}.")
        index += 1

    return options


def _int_option(raw: str, keyword: str, line: int) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise DslError(
            line,
            f"'{keyword}' espera un número entero, no {raw!r}.",
        ) from exc


class _Line:
    __slots__ = ("number", "indent", "text")

    def __init__(self, number: int, indent: int, text: str) -> None:
        self.number = number
        self.indent = indent
        self.text = text


def _read_lines(source: str) -> list[_Line]:
    lines: list[_Line] = []
    for number, raw in enumerate(source.splitlines(), start=1):
        expanded = _strip_comment(raw.expandtabs(4)).rstrip()
        if not expanded.strip():
            continue
        lines.append(
            _Line(number, len(expanded) - len(expanded.lstrip()), expanded.strip())
        )
    return lines


class _Builder:
    """Construye el modelo y recuerda qué línea creó cada pieza.

    Ese registro es lo que permite decir «choca con la pieza de la línea 4» en
    lugar de mostrar un identificador interno que no significa nada para quien
    escribe el código.
    """

    def __init__(self, model: BlockModel) -> None:
        self.model = model
        self._line_by_id: dict[str, int] = {}
        self._by_name: dict[str, PlacedPart] = {}
        self._last: PlacedPart | None = None

    @property
    def lineas(self) -> dict[str, int]:
        """Qué línea creó cada pieza."""
        return self._line_by_id

    def place(self, line: _Line, offset: tuple[int, int, int]) -> None:
        match = _PIECE_RE.match(line.text)
        if not match:
            raise DslError(
                line.number,
                f"No entiendo esta instrucción: {line.text!r}. "
                "Se esperaba algo como 'ladrillo 2x4 en 0,0,0 color rojo' "
                "o 'ladrillo 2x4 encima color azul'.",
            )

        part_id = _resolve_part_id(
            match.group("tipo"), match.group("medida"), line.number
        )
        # La definición hace falta ANTES de resolver el lugar: para meter la
        # pieza por un agujero hay que saber qué pin o punta de eje tiene.
        try:
            definition = self.model.catalog.get(part_id)
        except BlockCADError as exc:
            raise DslError(line.number, str(exc)) from exc

        position, options = self._locate(
            match.group("lugar"), line, offset, definition
        )

        nombre = options.pop("nombre", None)
        candidate = PlacedPart.create(
            # Se guarda la pieza canónica, no el alias con que se escribió:
            # "brick_2x4" significa cosas distintas en cada catálogo, y en un
            # archivo guardado eso sería una trampa. El molde 3001 es 3001.
            part_id=definition.part_id,
            position=position,
            color=options.pop("color", None) or definition.default_color,
            **options,
        )

        collisions = self.model.collisions_for(candidate)
        if collisions:
            raise DslError(line.number, self._describe(collisions, line.number))

        self.model.add_instance(candidate, check_collision=False)
        self._line_by_id[candidate.instance_id] = line.number
        self._last = candidate

        if nombre is not None:
            anterior = self._by_name.get(nombre)
            if anterior is not None:
                raise DslError(
                    line.number,
                    f"Ya hay una pieza llamada {nombre!r}, "
                    f"en la línea {self._line_by_id[anterior.instance_id]}.",
                )
            self._by_name[nombre] = candidate

    def _locate(
        self,
        lugar: str,
        line: _Line,
        offset: tuple[int, int, int],
        definition,
    ) -> tuple[GridPosition, dict]:
        # `en el agujero` y `en el eje` van antes que `en x,y,z`: los tres
        # empiezan por "en".
        agujero = _AGUJERO_RE.match(lugar)
        if agujero:
            return self._en_agujero(agujero, line, definition)

        eje = _EJE_RE.match(lugar)
        if eje:
            return self._en_eje(eje, line, definition)

        absoluto = _ABSOLUTO_RE.match(lugar)
        if absoluto:
            options = _parse_options(absoluto.group("opciones"), line.number)
            # x e y se cuentan en studs y z en placas; el motor los quiere en
            # LDU. El desplazamiento del `repetir` ya viene traducido.
            try:
                return (
                    GridPosition(
                        _a_ldu(absoluto.group("x"), STUD, "studs", line.number)
                        + offset[0],
                        _a_ldu(absoluto.group("y"), STUD, "studs", line.number)
                        + offset[1],
                        _a_ldu(absoluto.group("z"), PLACA, "placas", line.number)
                        + offset[2],
                    ),
                    options,
                )
            except DslError:
                # Ya sabe su línea: volver a envolverlo la escribiría dos veces.
                raise
            except BlockCADError as exc:
                raise DslError(line.number, str(exc)) from exc

        encima = _ENCIMA_RE.match(lugar)
        if not encima:
            raise DslError(
                line.number,
                f"No entiendo dónde va la pieza: {lugar!r}. Usa 'en 0,0,0', "
                "'encima', 'encima de <nombre>' o 'en el agujero 2 de "
                "<nombre>'.",
            )

        options = _parse_options(encima.group("opciones"), line.number)
        return self._on_top_of(encima, line), options

    def _referencia(self, nombre: str | None, line: _Line, para: str) -> PlacedPart:
        """La pieza a la que se refiere una orden: por nombre, o la última."""
        if nombre:
            referencia = self._by_name.get(nombre)
            if referencia is None:
                conocidas = ", ".join(sorted(self._by_name))
                raise DslError(
                    line.number,
                    f"No hay ninguna pieza llamada {nombre!r}. "
                    + (
                        f"Las que tienen nombre son: {conocidas}."
                        if conocidas
                        else "Ponle nombre antes, con 'llamado base' al final "
                        "de su línea."
                    ),
                )
            return referencia

        referencia = self._last
        if referencia is None:
            raise DslError(
                line.number,
                f"{para} necesita una pieza anterior. "
                "La primera debe decir dónde va, con 'en 0,0,0'.",
            )
        return referencia

    def _on_top_of(self, match: re.Match, line: _Line) -> GridPosition:
        """Calcula la posición justo encima de otra pieza.

        El desplazamiento de un `repetir` no se aplica aquí: `encima` significa
        «sobre esa pieza», y sumarle el del bucle lo convertiría en otra cosa.
        La referencia ya está donde está.
        """
        referencia = self._referencia(match.group("nombre"), line, "'encima'")

        altura = self.model.catalog.get(referencia.part_id).dimensions.height
        try:
            return GridPosition(
                referencia.position.x
                + _a_ldu(match.group("dx") or "0", STUD, "studs", line.number),
                referencia.position.y
                + _a_ldu(match.group("dy") or "0", STUD, "studs", line.number),
                referencia.position.z + altura,
            )
        except DslError:
            raise
        except BlockCADError as exc:
            raise DslError(line.number, str(exc)) from exc

    def _en_agujero(
        self, match: re.Match, line: _Line, definition
    ) -> tuple[GridPosition, dict]:
        """Mete la pieza por un agujero de otra, resolviendo giro y posición.

        Quien escribe dice QUÉ unión quiere —este pin, en ese agujero— y las
        coordenadas las calcula el motor, igual que `encima` calcula la altura.
        La alternativa era lo que había: colocar un pin exigía saber que el
        agujero cae en z=14 LDU y girar la pieza de cabeza.

        El desplazamiento de un `repetir` no se aplica: el agujero está donde
        está.
        """
        options = _parse_options(match.group("opciones"), line.number)
        referencia = self._referencia(
            match.group("nombre"), line, "'en el agujero'"
        )
        definicion_ref = self.model.catalog.get(referencia.part_id)

        # Los agujeros de la referencia. Cada perforación asoma por las dos
        # caras, y eso es UN agujero: se agrupan las que comparten recta.
        grupos: list[list] = []
        for conexion in referencia.world_connections(definicion_ref):
            if not conexion.es_hembra:
                continue
            for grupo in grupos:
                if conexion.misma_recta_que(grupo[0]):
                    grupo.append(conexion)
                    break
            else:
                grupos.append([conexion])

        if not grupos:
            raise DslError(
                line.number,
                f"{definicion_ref.name} no tiene agujeros donde meter nada.",
            )

        # Se numeran por dónde caen: primero x, luego y, luego z. Así el
        # número se puede contar mirando el visor.
        grupos.sort(key=lambda grupo: min(c.punto for c in grupo))
        numero = int(match.group("numero"))
        if not 1 <= numero <= len(grupos):
            raise DslError(
                line.number,
                f"{definicion_ref.name} tiene "
                f"{len(grupos)} agujero{'s' if len(grupos) > 1 else ''}, "
                f"así que no hay agujero {numero}. Se numeran desde 1, "
                "por posición.",
            )
        agujero = grupos[numero - 1]
        tipos_que_aloja = {c.tipo for c in agujero}

        # ¿Qué tiene esta pieza que quepa ahí? El encaje no es simétrico: un
        # eje pasa por el agujero redondo, pero un pin no entra en la cruz.
        indices_macho = [
            i
            for i, c in enumerate(definition.connections)
            if c.tipo in Connection.MACHOS
            and tipos_que_aloja & set(Connection.ENCAJES[c.tipo])
        ]
        if not indices_macho:
            if any(c.tipo in Connection.MACHOS for c in definition.connections):
                raise DslError(
                    line.number,
                    f"Ese agujero es de cruz y el pin de {definition.name} "
                    "no entra: la cruz le cierra el paso al cilindro. "
                    "Un eje sí pasaría.",
                )
            raise DslError(
                line.number,
                f"{definition.name} no tiene pin ni punta de eje: "
                "no hay nada que meter por un agujero.",
            )

        centro = tuple(
            sum(c.punto[k] for c in agujero) / len(agujero) for k in range(3)
        )
        return self._colocar_por_recta(
            definition, indices_macho, agujero[0].eje, centro, match, options, line
        )

    def _en_eje(
        self, match: re.Match, line: _Line, definition
    ) -> tuple[GridPosition, dict]:
        """Encaja la pieza sobre el eje de otra: el caso espejo del agujero.

        Un engranaje no se mete en nada: es él quien recibe el eje. Aquí la
        recta la pone el macho de la referencia y el agujero lo trae la pieza
        que se coloca. La resolución es la misma con los papeles cambiados.
        """
        options = _parse_options(match.group("opciones"), line.number)
        referencia = self._referencia(match.group("nombre"), line, "'en el eje'")
        definicion_ref = self.model.catalog.get(referencia.part_id)

        puntas = [
            c
            for c in referencia.world_connections(definicion_ref)
            if c.tipo == "punta_eje"
        ]
        if not puntas:
            raise DslError(
                line.number,
                f"{definicion_ref.name} no tiene eje sobre el que encajar nada.",
            )
        if any(not c.misma_recta_que(puntas[0]) for c in puntas[1:]):
            raise DslError(
                line.number,
                f"{definicion_ref.name} tiene ejes en varias direcciones y "
                "no sé cuál quieres.",
            )

        # El agujero lo trae la pieza que se coloca, y tiene que ser de los
        # que un eje atraviesa: el redondo o el de cruz.
        indices = [
            i
            for i, c in enumerate(definition.connections)
            if c.tipo in Connection.ENCAJES["punta_eje"]
        ]
        if not indices:
            raise DslError(
                line.number,
                f"{definition.name} no tiene agujero por donde pase un eje.",
            )

        # Si la pieza tiene varios agujeros —una viga tiene siete—, hay que
        # decir por cuál se cuelga. Se agrupan por recta EN LA PIEZA SIN
        # GIRAR y se numeran por posición, igual que los de una referencia:
        # el agujero 1 de una viga es el de su extremo, se mire como se mire.
        propios = PlacedPart.create(
            definition.part_id, GridPosition(0, 0, 0)
        ).world_connections(definition)
        grupos: list[list[int]] = []
        for i in indices:
            for grupo in grupos:
                if propios[i].misma_recta_que(propios[grupo[0]]):
                    grupo.append(i)
                    break
            else:
                grupos.append([i])
        grupos.sort(key=lambda g: min(propios[i].punto for i in g))

        elegido = match.group("agujero")
        if elegido is None:
            if len(grupos) > 1:
                raise DslError(
                    line.number,
                    f"{definition.name} tiene {len(grupos)} agujeros y no sé "
                    "por cuál colgarla. Dilo con 'por su agujero 2'.",
                )
            indices = grupos[0]
        else:
            numero = int(elegido)
            if not 1 <= numero <= len(grupos):
                raise DslError(
                    line.number,
                    f"{definition.name} tiene {len(grupos)} "
                    f"agujero{'s' if len(grupos) > 1 else ''}; no hay "
                    f"agujero {numero}. Se numeran desde 1, por posición.",
                )
            indices = grupos[numero - 1]

        # El centro del eje: el punto medio entre sus puntas. Un eje con tope
        # tiene una sola punta, y entonces el centro es esa punta.
        centro = tuple(
            sum(c.punto[k] for c in puntas) / len(puntas) for k in range(3)
        )
        return self._colocar_por_recta(
            definition, indices, puntas[0].eje, centro, match, options, line
        )

    def _colocar_por_recta(
        self,
        definition,
        indices: list[int],
        eje_objetivo,
        centro,
        match: re.Match,
        options: dict,
        line: _Line,
    ) -> tuple[GridPosition, dict]:
        """Resuelve giro y posición para que unas conexiones caigan en una recta.

        Es el corazón compartido de `en el agujero` y `en el eje`: en ambos
        casos hay una recta objetivo y unas conexiones de la pieza nueva que
        deben acabar sobre ella, centradas en `centro` y corridas lo que diga
        `desplazado`.
        """
        # Sin girar y en el origen: la vara de medir de la propia pieza.
        base = PlacedPart.create(
            definition.part_id, GridPosition(0, 0, 0)
        ).world_connections(definition)
        primera = base[indices[0]]
        if any(not base[i].misma_recta_que(primera) for i in indices[1:]):
            # Las dos puntas de un eje —o las dos caras de un agujero— son la
            # misma recta y pasan por aquí. Varias rectas distintas, no:
            # elegir sería adivinar.
            raise DslError(
                line.number,
                f"{definition.name} tiene varios sitios que encajar y no sé "
                "cuál quieres. De momento esa pieza va con 'en x,y,z'.",
            )

        orientacion = options.get("orientation")
        if orientacion is not None:
            if not _paralelas(orientacion.apply(*primera.eje), eje_objetivo):
                raise DslError(
                    line.number,
                    "Con ese giro la pieza no apunta por donde se encaja. "
                    "Quita el 'rot' y el giro se resuelve solo.",
                )
        else:
            # El primer giro de los 24 que la deja paralela. El orden de
            # `todas()` es fijo, así que el resultado también.
            orientacion = next(
                (
                    o
                    for o in Orientation.todas()
                    if _paralelas(o.apply(*primera.eje), eje_objetivo)
                ),
                None,
            )
            if orientacion is None:
                raise DslError(
                    line.number,
                    "Esa recta no va paralela a ningún eje y no hay giro "
                    "de 90 grados que la alcance.",
                )
            options["orientation"] = orientacion

        # Dónde queda el ancla de la pieza (el centro de sus conexiones) una
        # vez girada, y dónde tiene que acabar: `centro`, más el
        # desplazamiento que pida el usuario, en módulos y por la recta.
        girados = PlacedPart.create(
            definition.part_id, GridPosition(0, 0, 0), orientation=orientacion
        ).world_connections(definition)
        ancla = tuple(
            sum(girados[i].punto[k] for i in indices) / len(indices)
            for k in range(3)
        )
        modulos = _a_ldu(
            match.group("d") or "0", MODULO_TECHNIC, "módulos", line.number
        )
        largo = sum(v * v for v in eje_objetivo) ** 0.5
        valores = [
            centro[k] + modulos * eje_objetivo[k] / largo - ancla[k]
            for k in range(3)
        ]
        enteros = [round(v) for v in valores]
        if any(abs(v - e) > 1e-6 for v, e in zip(valores, enteros)):
            raise DslError(
                line.number,
                "Con ese desplazamiento la pieza cae entre dos posiciones "
                "LDU. Prueba con medios módulos: 0.5, 1, 1.5...",
            )
        try:
            return GridPosition(*enteros), options
        except BlockCADError as exc:
            # El caso típico: una rueda más grande que la altura de su eje
            # acaba por debajo del suelo. El motor lo rechaza; aquí se le pone
            # el número de línea y el remedio.
            raise DslError(
                line.number,
                f"{exc} Ahí la pieza no cabe: prueba a construir más arriba.",
            ) from exc

    def _describe(self, collisions: tuple[PlacedPart, ...], current: int) -> str:
        lines = sorted({self._line_by_id[item.instance_id] for item in collisions})
        if lines == [current]:
            return "Esta pieza choca consigo misma en una repetición anterior."
        detalle = ", ".join(f"la línea {number}" for number in lines)
        return f"Esta pieza choca con {detalle}."


def _run_block(
    lines: list[_Line],
    builder: _Builder,
    indent: int,
    offset: tuple[int, int, int],
) -> None:
    index = 0
    while index < len(lines):
        line = lines[index]

        if line.indent < indent:
            return
        if line.indent > indent:
            raise DslError(line.number, "Indentación inesperada.")

        repeat = _REPEAT_RE.match(line.text)
        if not repeat:
            builder.place(line, offset)
            index += 1
            continue

        body_start = index + 1
        if body_start >= len(lines) or lines[body_start].indent <= indent:
            raise DslError(
                line.number,
                "'repetir' necesita al menos una línea indentada debajo.",
            )

        body_indent = lines[body_start].indent
        body_end = body_start
        while body_end < len(lines) and lines[body_end].indent >= body_indent:
            body_end += 1

        body = lines[body_start:body_end]
        # El desplazamiento también se escribe en studs y placas.
        delta = (
            _a_ldu(repeat.group("dx") or "0", STUD, "studs", line.number),
            _a_ldu(repeat.group("dy") or "0", STUD, "studs", line.number),
            _a_ldu(repeat.group("dz") or "0", PLACA, "placas", line.number),
        )
        for step in range(int(repeat.group("veces"))):
            _run_block(
                body,
                builder,
                body_indent,
                (
                    offset[0] + delta[0] * step,
                    offset[1] + delta[1] * step,
                    offset[2] + delta[2] * step,
                ),
            )

        index = body_end


def _part_phrase(part_id: str) -> str:
    match = _PART_ID_RE.match(part_id)
    if match and match.group("prefijo") in _PREFIX_NAMES:
        return f"{_PREFIX_NAMES[match.group('prefijo')]} {match.group('medida')}"
    # Una pieza que no siga el patrón se escribe con su identificador tal cual;
    # el lenguaje también los acepta.
    return part_id


def _tabla_de_giros() -> dict[tuple, list[tuple[str, int]]]:
    """Para cada una de las 24 orientaciones, la forma más corta de llegar.

    Generar el código de vuelta necesita el inverso de la matriz: qué `rot`
    hay que escribir para conseguirla. Una búsqueda en anchura desde la
    identidad da la secuencia más corta de cada una, así que el código
    generado nunca dice "rot x 90 rot x 90 rot x 90" pudiendo decir
    "rot x 270".
    """
    tabla: dict[tuple, list[tuple[str, int]]] = {Orientation().filas: []}
    frontera = [Orientation()]
    while frontera:
        actual = frontera.pop(0)
        for eje in ("x", "y", "z"):
            for grados in (90, 180, 270):
                siguiente = Orientation.around(eje, grados).then(actual)
                if siguiente.filas in tabla:
                    continue
                tabla[siguiente.filas] = tabla[actual.filas] + [(eje, grados)]
                frontera.append(siguiente)
    return tabla


_GIROS_POR_MATRIZ = _tabla_de_giros()


def _giro_a_texto(orientation: Orientation) -> list[str]:
    pasos = _GIROS_POR_MATRIZ[orientation.filas]
    # Un giro sobre el eje vertical se escribe como siempre, sin nombrar el
    # eje: es el caso habitual y así el código generado se lee igual que antes.
    if len(pasos) == 1 and pasos[0][0] == "z":
        return [f"rot {pasos[0][1]}"]
    return [f"rot {eje} {grados}" for eje, grados in pasos]


def _desde_ldu(ldu: int, unidad: int) -> str:
    """El camino inverso: de LDU a lo que lee una persona.

    Se escribe entero siempre que se pueda, para que el código generado se
    parezca al que escribiría alguien a mano.
    """
    valor = ldu / unidad
    return str(int(valor)) if valor == int(valor) else f"{valor:g}"


def model_to_source(model: BlockModel) -> str:
    """Genera código BlockCAD a partir de un modelo.

    Es el camino de vuelta de `parse_model`, y permite abrir en el editor un
    modelo guardado en JSON. Los identificadores de instancia no se escriben:
    el código es la fuente, y el motor los vuelve a asignar al leerlo.
    """
    lines: list[str] = []

    if model.name and model.name != DEFAULT_MODEL_NAME:
        # El lenguaje no tiene escapes, así que unas comillas dentro del nombre
        # romperían el código generado.
        lines.append(f'modelo "{model.name.replace(chr(34), chr(39))}"')
        lines.append("")

    for item in model.instances:
        partes = [
            _part_phrase(item.part_id),
            "en "
            + ",".join(
                _desde_ldu(valor, unidad)
                for valor, unidad in (
                    (item.position.x, STUD),
                    (item.position.y, STUD),
                    (item.position.z, PLACA),
                )
            ),
        ]
        partes.extend(_giro_a_texto(item.orientation))
        partes.append(f"color {_COLOR_NAMES.get(item.color.upper(), item.color)}")
        if item.group:
            partes.append(f"grupo {item.group}")
        if item.step:
            partes.append(f"paso {item.step}")
        if item.transparent:
            partes.append("transparente")
        lines.append(" ".join(partes))

    return "\n".join(lines) + "\n"


def parse_model(source: str, *, catalog: PartCatalog | None = None) -> BlockModel:
    """Traduce código BlockCAD a un modelo validado.

    Lanza `DslError` indicando la línea cuando el código no es válido o
    cuando el motor rechaza una pieza.
    """
    return parse_model_con_lineas(source, catalog=catalog)[0]


def parse_model_con_lineas(
    source: str, *, catalog: PartCatalog | None = None
) -> tuple[BlockModel, dict[str, int]]:
    """Igual, pero dice además qué línea creó cada pieza.

    El constructor ya lo sabía —lo usa para avisar de que una pieza «choca con
    la línea 2»— pero lo tiraba al terminar. Hace falta para que pinchar una
    pieza en el visor lleve a su línea: el código es el origen de la verdad, y
    el 3D es una forma de navegarlo.
    """
    if source.lstrip().startswith("{"):
        raise DslError(
            1,
            "Esto parece un modelo guardado en JSON, no código BlockCAD.",
        )

    lines = _read_lines(source)

    # `catalogo "wedo"` elige con qué piezas se construye. Sin él se usan las
    # básicas, que es lo que espera el código escrito hasta ahora.
    #
    # Si el código lo declara, manda el código: se describe a sí mismo, y el
    # `catalog=` de Python es el valor por defecto para cuando no dice nada.
    # Ignorar la línea en silencio sería peor: alguien pediría "wedo" y
    # construiría con otra cosa.
    if lines:
        eleccion = _CATALOGO_RE.match(lines[0].text)
        if eleccion:
            try:
                catalog = cargar_catalogo(eleccion.group("nombre"))
            except BlockCADError as exc:
                raise DslError(lines[0].number, str(exc)) from exc
            lines = lines[1:]

    model = BlockModel(catalog=catalog)

    if lines:
        name = _NAME_RE.match(lines[0].text)
        if name:
            model.name = name.group("nombre")
            lines = lines[1:]

    for line in lines:
        if _NAME_RE.match(line.text):
            raise DslError(
                line.number,
                "'modelo' debe ser la primera instrucción del código.",
            )
        if _CATALOGO_RE.match(line.text):
            raise DslError(
                line.number,
                "'catalogo' debe ir en la primera línea, antes que 'modelo'.",
            )

    if lines and lines[0].indent != 0:
        raise DslError(lines[0].number, "La primera instrucción no debe ir indentada.")

    constructor = _Builder(model)
    _run_block(lines, constructor, 0, (0, 0, 0))
    return model, dict(constructor.lineas)
