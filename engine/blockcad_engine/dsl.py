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

from .errors import BlockCADError, DslError
from .geometry import PLACA, STUD, GridPosition, Rotation
from .model import DEFAULT_MODEL_NAME, BlockModel, PlacedPart
from .parts import PartCatalog, validate_color

#: Nombre en el lenguaje -> prefijo del identificador en el catálogo.
PART_PREFIXES = {
    "ladrillo": "brick",
    "placa": "plate",
    "baldosa": "tile",
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

_PART_ID_RE = re.compile(r"^(?P<prefijo>[a-z]+)_(?P<medida>\d+x\d+)$")

_NAME_RE = re.compile(r'^modelo\s+"(?P<nombre>[^"]*)"\s*$')

_REPEAT_RE = re.compile(
    r"^repetir\s+(?P<veces>\d+)(?:\s+veces)?"
    # Sin desplazamiento el bloque se repite en el sitio, que es lo que hace
    # falta al apilar con `encima`.
    r"(?:\s+desplazando\s+(?P<dx>-?\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<dy>-?\d+(?:\.\d+)?)\s*,\s*(?P<dz>-?\d+(?:\.\d+)?))?"
    r"\s*:$"
)

_PIECE_RE = re.compile(
    r"^(?P<tipo>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\s+(?P<medida>\d+x\d+))?"
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
            raw = _value(token)
            try:
                options["rotation"] = Rotation.normalize(int(raw))
            except ValueError as exc:
                raise DslError(line, f"Rotación inválida: {raw!r}. {exc}") from exc
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
        position, options = self._locate(match.group("lugar"), line, offset)

        try:
            definition = self.model.catalog.get(part_id)
        except BlockCADError as exc:
            raise DslError(line.number, str(exc)) from exc

        nombre = options.pop("nombre", None)
        candidate = PlacedPart.create(
            part_id=part_id,
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
    ) -> tuple[GridPosition, dict]:
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
                "'encima' o 'encima de <nombre>'.",
            )

        options = _parse_options(encima.group("opciones"), line.number)
        return self._on_top_of(encima, line), options

    def _on_top_of(self, match: re.Match, line: _Line) -> GridPosition:
        """Calcula la posición justo encima de otra pieza.

        El desplazamiento de un `repetir` no se aplica aquí: `encima` significa
        «sobre esa pieza», y sumarle el del bucle lo convertiría en otra cosa.
        La referencia ya está donde está.
        """
        nombre = match.group("nombre")
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
        else:
            referencia = self._last
            if referencia is None:
                raise DslError(
                    line.number,
                    "'encima' necesita una pieza anterior sobre la que "
                    "apoyarse. La primera debe decir dónde va, con 'en 0,0,0'.",
                )

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
        if item.rotation != Rotation.DEG_0:
            partes.append(f"rot {int(item.rotation)}")
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
    if source.lstrip().startswith("{"):
        raise DslError(
            1,
            "Esto parece un modelo guardado en JSON, no código BlockCAD.",
        )

    lines = _read_lines(source)
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

    if lines and lines[0].indent != 0:
        raise DslError(lines[0].number, "La primera instrucción no debe ir indentada.")

    _run_block(lines, _Builder(model), 0, (0, 0, 0))
    return model
