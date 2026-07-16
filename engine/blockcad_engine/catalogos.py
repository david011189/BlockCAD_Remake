"""Catálogos de piezas reales, sacados de LDraw.

`PartCatalog.with_basic_parts()` da siete piezas idealizadas, escritas a mano,
que valen para probar y para construir con ladrillos. Aquí se cargan las de
verdad: las que trae una caja concreta, con sus medidas y sus conexiones.

El dato lo genera `herramientas/generar_catalogo.py` cruzando el inventario
del set con la biblioteca de LDraw. Este módulo solo lo lee, así que el motor
no depende de LDraw ni de sus 136 MB.

Geometría: The LDraw Parts Library, CC BY 4.0 — https://www.ldraw.org
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .errors import InvalidFormatError
from .geometry import STUD, Connection, Dimensions
from .parts import PartCatalog, PartDefinition

_DATOS = Path(__file__).parent / "datos"

#: Los catálogos disponibles, por nombre corto.
CATALOGOS = {
    "wedo": "catalogo_45300.json",
}

#: De qué familia es cada pieza, según cómo la llama LDraw. Decide el nombre
#: corto con el que se la puede escribir y su categoría.
_FAMILIAS = (
    (re.compile(r"^Brick (\d+) x (\d+)$"), "brick_{0}x{1}", "brick"),
    (re.compile(r"^Plate (\d+) x (\d+)$"), "plate_{0}x{1}", "plate"),
    (re.compile(r"^Tile (\d+) x (\d+)(?: with Groove)?$"), "tile_{0}x{1}", "tile"),
    (re.compile(r"^Technic Beam +(\d+)$"), "beam_{0}", "technic"),
    (re.compile(r"^Technic Axle +(\d+)$"), "axle_{0}", "technic"),
)

#: Colores de LEGO que aparecen en los inventarios. Solo los del set; el resto
#: cae en el gris de por defecto, que es visible y no engaña.
_COLORES = {
    "Black": "#1B1B1B",
    "White": "#F4F4F4",
    "Bright Red": "#C91A09",
    "Red": "#C91A09",
    "Bright Blue": "#0055BF",
    "Blue": "#0055BF",
    "Bright Yellow": "#F2CD37",
    "Yellow": "#F2CD37",
    "Dark Green": "#237841",
    "Green": "#237841",
    "Bright Green": "#4B9F4A",
    "Medium Azur": "#36AEBF",
    "Medium Azure": "#36AEBF",
    "Medium Stone Grey": "#9BA19D",
    "Light Bluish Gray": "#9BA19D",
    "Dark Stone Grey": "#6C6E68",
    "Dark Bluish Gray": "#6C6E68",
    "Reddish Brown": "#582A12",
    "Orange": "#FE8A18",
    "Bright Orange": "#FE8A18",
    "Lime": "#BBE90B",
    "Transparent": "#FCFCFC",
}
_GRIS_POR_DEFECTO = "#9BA19D"


def _alias_y_categoria(
    nombre_ldraw: str,
) -> tuple[list[str], str, tuple[int, ...]]:
    limpio = re.sub(r"\s+", " ", nombre_ldraw).strip()
    for patron, plantilla, categoria in _FAMILIAS:
        encontrado = patron.match(limpio)
        if encontrado:
            medidas = tuple(int(g) for g in encontrado.groups())
            return [plantilla.format(*encontrado.groups())], categoria, medidas
    if limpio.startswith("Technic"):
        return [], "technic", ()
    if limpio.startswith("Electric Power Functions"):
        return [], "electronica", ()
    return [], "otros", ()


def _viene_acostada(
    medidas: tuple[int, ...], ancho: float, fondo: float
) -> bool:
    """True si la caja llega tumbada hacia el lado que no le toca.

    LDraw dibuja las piezas como quiere, y cada familia hereda otra postura:
    el "Brick 2 x 4" llega con los 4 studs en X, la viga a lo largo de Y y
    los ejes a lo largo de X. Aquí se decide una sola postura por nombre:

    - Dos números ("2x4"): el nombre manda. El 2 es el ancho en X, igual
      que en el catálogo básico. Si no, el mismo código colocaría las
      piezas giradas según el catálogo elegido.
    - Un número (viga 7, eje 6): la pieza es una línea y se tumba a lo
      largo de Y, que es como ya venía la viga.
    """
    if len(medidas) == 2:
        n, m = medidas
        return n != m and (ancho, fondo) == (m * STUD, n * STUD)
    if len(medidas) == 1:
        return ancho > fondo
    return False


def _giradas_90(conexiones, fondo: float) -> list[dict]:
    """Las conexiones tras girar su pieza 90° sobre Z y reanclarla.

    El mismo giro y el mismo reanclaje que hace el motor al girar una pieza
    colocada: el punto (x, y) pasa a (fondo - y, x). La recta solo se gira;
    una dirección no está en ningún sitio, así que no se reancla.
    """
    giradas = []
    for c in conexiones:
        x, y, z = c["punto"]
        ax, ay, az = c.get("eje", (0.0, 0.0, 0.0))
        girada = dict(c)
        girada["punto"] = [fondo - y, x, z]
        girada["eje"] = [-ay, ax, az]
        giradas.append(girada)
    return giradas


_DIENTES_RE = re.compile(r"Gear (\d+) Tooth")


def _dientes(nombre_ldraw: str) -> dict[str, str]:
    """Cuántos dientes tiene la pieza, si es una rueda dentada.

    Sale del nombre de LDraw, que lo declara siempre («Gear 8 Tooth»). Los
    dientes son lo que decide a qué distancia muerde: el radio primitivo de
    LEGO es 1,25 LDU por diente, y dos ruedas engranan cuando sus ejes están
    a la suma de sus radios. El tornillo sin fin no dice dientes y queda
    fuera a propósito: muerde con otra geometría.
    """
    # LDraw alinea números con espacios dobles («Gear  8 Tooth»): se
    # normaliza antes de buscar, igual que hace el nombre de la pieza.
    encontrado = _DIENTES_RE.search(re.sub(r"\s+", " ", nombre_ldraw))
    return {"dientes": encontrado.group(1)} if encontrado else {}


def _color(colores: list[str]) -> str:
    for nombre in colores:
        if nombre in _COLORES:
            return _COLORES[nombre]
    return _GRIS_POR_DEFECTO


def _definicion(pieza: dict) -> PartDefinition:
    ancho, fondo, alto = pieza["caja_motor_ldu"]
    aliases, categoria, medidas = _alias_y_categoria(pieza["nombre_ldraw"])
    conexiones = pieza.get("conexiones_motor", ())

    # El nombre manda. Una pieza que LDraw dibuja acostada se endereza al
    # cargarla —caja y conexiones a la vez, o los studs quedarían fuera— y se
    # apunta el giro para que el visor gire su malla igual. El JSON no se
    # toca: es LDraw tal cual, y quien lo regenere no tiene que saber esto.
    malla_giro = {}
    if _viene_acostada(medidas, ancho, fondo):
        conexiones = _giradas_90(conexiones, fondo)
        ancho, fondo = fondo, ancho
        malla_giro = {"malla_giro": "90"}

    return PartDefinition(
        # El identificador es el número de molde de LEGO, que es el que sale
        # en cualquier inventario o instrucción.
        part_id=pieza["diseno"],
        name=re.sub(r"\s+", " ", pieza["nombre_ldraw"]).strip(),
        # La caja ya viene sin los studs: si los contara, apilar sería
        # imposible.
        dimensions=Dimensions(round(ancho), round(fondo), round(alto)),
        category=categoria,
        default_color=_color(pieza.get("colores", [])),
        has_top_studs=any(
            c["tipo"] == "stud" for c in pieza.get("conexiones", [])
        ),
        metadata={
            "ldraw": pieza["ldraw"],
            "nombre_lego": pieza.get("nombre_lego", ""),
            "cantidad_en_el_set": str(pieza.get("cantidad", 0)),
            **malla_giro,
            **_dientes(pieza["nombre_ldraw"]),
        },
        aliases=tuple(aliases),
        connections=tuple(
            Connection(
                c["tipo"],
                tuple(round(v) for v in c["punto"]),
                tuple(float(v) for v in c.get("eje", (0.0, 0.0, 0.0))),
            )
            for c in conexiones
        ),
    )


@lru_cache(maxsize=4)
def _leer(ruta: str) -> tuple[dict, ...]:
    """Lee el archivo una vez. Se cachea el dato, nunca el catálogo.

    Devolver un `PartCatalog` cacheado daría el mismo objeto a todo el mundo,
    y registrar una pieza en un modelo la metería en todos los demás. El JSON
    es lo caro; construir el catálogo son microsegundos.
    """
    documento = json.loads(Path(ruta).read_text(encoding="utf-8"))
    if documento.get("formato") != "blockcad-catalogo":
        raise InvalidFormatError("Ese archivo no es un catálogo de BlockCAD.")
    return tuple(documento["piezas"])


def cargar_desde_archivo(ruta: Path | str) -> PartCatalog:
    catalogo = PartCatalog()
    for pieza in _leer(str(ruta)):
        ancho, fondo, alto = pieza["caja_motor_ldu"]
        # Una pieza sin bulto no se puede colocar ni colisionar. Que exista en
        # LDraw no la hace utilizable aquí.
        if min(ancho, fondo, alto) <= 0:
            continue
        catalogo.register(_definicion(pieza))
    return catalogo


def cargar(nombre: str) -> PartCatalog:
    """Carga un catálogo por su nombre corto: `cargar("wedo")`."""
    archivo = CATALOGOS.get(nombre.lower())
    if archivo is None:
        conocidos = ", ".join(sorted(CATALOGOS))
        raise InvalidFormatError(
            f"No hay ningún catálogo llamado {nombre!r}. Hay: {conocidos}."
        )
    return cargar_desde_archivo(_DATOS / archivo)
