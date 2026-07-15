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
from .geometry import GridPosition, Rotation
from .model import BlockModel, PlacedPart
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

_NAME_RE = re.compile(r'^modelo\s+"(?P<nombre>[^"]*)"\s*$')

_REPEAT_RE = re.compile(
    r"^repetir\s+(?P<veces>\d+)(?:\s+veces)?\s+desplazando\s+"
    r"(?P<dx>-?\d+)\s*,\s*(?P<dy>-?\d+)\s*,\s*(?P<dz>-?\d+)\s*:$"
)

_PIECE_RE = re.compile(
    r"^(?P<tipo>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\s+(?P<medida>\d+x\d+))?"
    r"\s+en\s+(?P<x>-?\d+)\s*,\s*(?P<y>-?\d+)\s*,\s*(?P<z>-?\d+)"
    r"(?P<opciones>.*)$"
)


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

    def place(self, line: _Line, offset: tuple[int, int, int]) -> None:
        match = _PIECE_RE.match(line.text)
        if not match:
            raise DslError(
                line.number,
                f"No entiendo esta instrucción: {line.text!r}. "
                "Se esperaba algo como 'ladrillo 2x4 en 0,0,0 color rojo'.",
            )

        part_id = _resolve_part_id(
            match.group("tipo"), match.group("medida"), line.number
        )
        options = _parse_options(match.group("opciones"), line.number)

        try:
            position = GridPosition(
                int(match.group("x")) + offset[0],
                int(match.group("y")) + offset[1],
                int(match.group("z")) + offset[2],
            )
            definition = self.model.catalog.get(part_id)
        except BlockCADError as exc:
            raise DslError(line.number, str(exc)) from exc

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
        delta = (
            int(repeat.group("dx")),
            int(repeat.group("dy")),
            int(repeat.group("dz")),
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


def parse_model(source: str, *, catalog: PartCatalog | None = None) -> BlockModel:
    """Traduce código BlockCAD a un modelo validado.

    Lanza `DslError` indicando la línea cuando el código no es válido o
    cuando el motor rechaza una pieza.
    """
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
