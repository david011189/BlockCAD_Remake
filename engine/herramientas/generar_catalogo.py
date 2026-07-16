"""Genera un catálogo de piezas cruzando un inventario de set con LDraw.

    python herramientas/generar_catalogo.py \\
        --inventario ../.ldraw-cache/Brickset-inventory-45300-1.csv \\
        --biblioteca ../.ldraw-cache/complete.zip \\
        --salida blockcad_engine/datos/catalogo_45300.json

El inventario dice QUÉ piezas hay (columna DesignID de Brickset, que es el
número de molde de LEGO). LDraw dice CÓMO son. Ninguna de las dos fuentes
basta por separado.

Geometría: The LDraw Parts Library, CC BY 4.0 — https://www.ldraw.org
"""

from __future__ import annotations

import argparse
import csv
import re
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ldraw import Biblioteca  # noqa: E402

#: Piezas donde el número de molde de LEGO no coincide con el de LDraw.
#:
#: Solo van aquí las correspondencias verificadas por dos vías. Los conectores
#: de ángulo casan por el número entre corchetes del nombre de LEGO
#: ("ANGLE ELEMENT, 157,5 DEGR. [3]") y además por los grados, que LDraw
#: escribe en el suyo ("Technic Angle Connector #3 (157.5 degree)").
#:
#: Adivinar aquí sería meter geometría falsa sin que salte ningún error, así
#: que lo que no esté verificado se queda fuera y sale en el informe.
EQUIVALENCIAS = {
    # Casan por el número entre corchetes y además por los grados.
    "42127": "32013",   # ANGLE ELEMENT, 0 DEGREES [1]   -> Angle Connector #1
    "42128": "32016",   # ANGLE ELEMENT, 157,5 DEGR. [3] -> Angle Connector #3 (157.5)
    "42156": "32192",   # ANGLE ELEMENT 135 DEG. [4]     -> Angle Connector #4 (135)

    # Identificadas por quien tiene el set delante y comprobadas contra la
    # geometría de LDraw antes de entrar aquí.
    "42136": "32123a",  # 1/2 BUSH -> Bush 1/2 Smooth, Axle Hole Reduced.
                        # Mide 10 LDU de grueso: medio módulo, como su nombre.
    "42798": "3713",    # BUSH FOR CROSS AXLE -> Technic Bush with Two Flanges.
                        # 20 LDU de grueso: un módulo entero.
    "65668": "4185a",   # WEDGE-BELT WHEEL Ø24 -> Wedge Belt Wheel Not Reinforced.
                        # Mide 60 LDU = 24 mm exactos, el Ø24 del nombre de LEGO.
    "28698": "6588",    # WORM GEAR BLOCK, TRANSP. -> Technic Gearbox 2x4x3&1/3.
                        # El "block" es la carcasa transparente, no el tornillo.
    "21712": "44728",   # ANGLE PLATE 1X2/2X2 -> Bracket 1x2 - 2x2 Down.
    "39223": "6143",    # BRICK Ø16 W. CROSS -> Brick 2x2 Round Reinforced.
                        # El "CROSS" es la cruz de refuerzo interna, no un
                        # agujero de eje: es lo único que lo separa del 3941
                        # ("without Reinforcement"). Ø16 mm = 40 LDU = 2 studs.
    "13360": "10238",   # FLAT TILE 1X1 ROUND 'NO. 8' -> alias de 98138p07,
                        # que LDraw llama "Eye Pattern". El nombre del dibujo
                        # difiere, pero una impresión no cambia la forma: la
                        # geometría es la misma baldosa redonda 1x1.
}

#: Piezas que el motor no podrá representar nunca, por mucho catálogo que
#: tenga: no tienen forma fija.
SIN_FORMA_FIJA = {
    "23241": "cuerda: no tiene geometría rígida",
    "39759": "cadena: cada eslabón se mueve",
}


def cargar_inventario(ruta: Path) -> dict[str, dict]:
    """Agrupa el CSV por molde. Una misma pieza sale varias veces, una por color."""
    piezas: dict[str, dict] = {}
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        for fila in csv.DictReader(archivo):
            diseno = fila["DesignID"].strip()
            entrada = piezas.setdefault(
                diseno,
                {
                    "diseno": diseno,
                    "nombre_lego": fila["ElementName"].strip(),
                    "categoria": fila["Category"].strip(),
                    "cantidad": 0,
                    "colores": [],
                },
            )
            entrada["cantidad"] += int(fila["Qty"])
            color = fila["Colour"].strip()
            if color not in entrada["colores"]:
                entrada["colores"].append(color)
    return piezas


#: Lo que un stud sobresale del techo de la pieza.
ALTO_STUD = 4

_MOVIDA_RE = re.compile(r"^~Moved to (\S+)")


def resolver(biblioteca: Biblioteca, numero: str, saltos: int = 0) -> str:
    """Sigue las redirecciones de LDraw hasta la pieza de verdad.

    Cuando un molde se recataloga, LDraw deja un archivo con el número viejo
    cuyo título es "~Moved to 3023b". La geometría se resuelve igual porque
    apunta al destino, pero el nombre que quedaría en el catálogo sería
    "~Moved to 3023b" en vez de "Plate 1 x 2".
    """
    titulo, _, _ = biblioteca.cabecera(f"{numero}.dat")
    movida = _MOVIDA_RE.match(titulo or "")
    if movida and saltos < 5:
        return resolver(biblioteca, movida.group(1), saltos + 1)
    return numero


def caja_de_colision(pieza) -> tuple[float, float, float]:
    """El bulto real de la pieza, en ejes del motor y sin los studs.

    La caja de la malla no sirve para colisionar: los studs sobresalen 4 LDU
    del techo y se meten dentro de la pieza de arriba. Contarlos haría
    imposible apilar dos ladrillos, que es lo primero que hace cualquiera.

    En LDraw la vertical es Y y apunta hacia ABAJO, así que el techo de una
    pieza es su `min_y`. El motor usa Z hacia arriba, y aquí se traduce:
    ancho = ancho en X, fondo = ancho en Z, alto = ancho en Y.
    """
    minimo, maximo = pieza.caja()
    techo = _techo(pieza)
    return (
        round(maximo.x - minimo.x, 2),
        round(maximo.z - minimo.z, 2),
        round(maximo.y - techo, 2),
    )


def _techo(pieza) -> float:
    """La cara superior de la pieza, sin contar los studs que sobresalen.

    En LDraw la vertical es Y y apunta hacia abajo, así que el techo es el
    min_y de la caja.
    """
    minimo, _ = pieza.caja()
    hay_studs = any(
        conexion.tipo == "stud"
        and abs(conexion.punto.y - (minimo.y + ALTO_STUD)) < 0.01
        for conexion in pieza.conexiones
    )
    return minimo.y + (ALTO_STUD if hay_studs else 0)


def conexiones_en_ejes_del_motor(pieza) -> list[dict]:
    """Pasa los puntos de conexión a las coordenadas que usa el motor.

    Hay que cruzar dos convenios a la vez, y es donde es fácil equivocarse:

    - LDraw mide la vertical en Y y hacia ABAJO; el motor, en Z y hacia
      arriba. Por eso la altura sale de restar a `max_y`.
    - El origen de LDraw está donde el autor de la pieza quisiera; el del
      motor es la esquina mínima de la caja de colisión.

    Cada agujero aparece dos veces en LDraw, una por cara, y eso no es ruido:
    es lo que hace que dos vigas pegadas compartan el punto.
    """
    minimo, maximo = pieza.caja()
    techo = _techo(pieza)

    vistos = {}
    for conexion in pieza.conexiones:
        punto = (
            round(conexion.punto.x - minimo.x, 2),
            round(conexion.punto.z - minimo.z, 2),
            round(maximo.y - conexion.punto.y, 2),
        )
        # Un punto por encima del techo es el propio stud sobresaliendo: no
        # es una conexión más, es el mismo sitio visto desde fuera.
        vistos[(conexion.tipo, punto, _eje_en_ejes_del_motor(conexion.eje))] = None

    return [
        {"tipo": tipo, "punto": list(punto), "eje": list(eje)}
        for tipo, punto, eje in sorted(vistos, key=lambda v: (v[0], v[1], v[2]))
    ]


def _eje_en_ejes_del_motor(eje) -> tuple[float, float, float]:
    """La dirección de LDraw pasada a los ejes del motor, y sin sentido.

    El cambio de ejes es el mismo que el de los puntos: LDraw mide la vertical
    en Y hacia abajo y el motor en Z hacia arriba, así que (x, y, z) de LDraw
    es (x, z, -y) aquí.

    El sentido se descarta a propósito: lo que hace falta es la RECTA, no la
    flecha. Un pin es una sola conexión aunque LDraw lo dibuje con dos mitades
    que miran a lados opuestos, y meterlo por un lado o por el otro es la misma
    inserción. Se elige un sentido canónico —el primer componente no nulo,
    positivo— para que las dos mitades se reconozcan como lo que son: una.
    """
    x, y, z = round(eje.x, 4), round(eje.z, 4), round(-eje.y, 4)
    for componente in (x, y, z):
        if abs(componente) > 1e-6:
            if componente < 0:
                x, y, z = -x, -y, -z
            break
    # El `+ 0.0` evita que quede un -0.0, que se imprime distinto y compara igual.
    return (round(x + 0.0, 4), round(y + 0.0, 4), round(z + 0.0, 4))


def describir(biblioteca: Biblioteca, numero: str) -> dict | None:
    pieza = biblioteca.analizar(f"{numero}.dat")
    if not pieza.vertices:
        return None

    minimo, maximo = pieza.caja()
    ancho, alto, fondo = pieza.medidas()

    # Cada agujero aparece dos veces, una por cara. Se unifican por posición.
    conexiones = sorted(
        {
            (c.tipo, round(c.punto.x, 2), round(c.punto.y, 2), round(c.punto.z, 2))
            for c in pieza.conexiones
        }
    )

    return {
        "ldraw": numero,
        # El '=' delante marca un alias en LDraw; no forma parte del nombre.
        "nombre_ldraw": pieza.nombre.lstrip("=").strip(),
        "licencia": pieza.licencia,
        # Lo que el motor necesita: el bulto sin studs y los puntos de
        # conexión, todo en sus ejes.
        "caja_motor_ldu": list(caja_de_colision(pieza)),
        "conexiones_motor": conexiones_en_ejes_del_motor(pieza),
        # Ojo: en LDraw la vertical es Y y apunta hacia abajo. La caja incluye
        # los studs, que sobresalen 4 LDU, así que NO es la caja de colisión.
        "caja_ldu": {
            "min": [round(minimo.x, 2), round(minimo.y, 2), round(minimo.z, 2)],
            "max": [round(maximo.x, 2), round(maximo.y, 2), round(maximo.z, 2)],
        },
        "medidas_ldu": [round(ancho, 2), round(alto, 2), round(fondo, 2)],
        "conexiones": [
            {"tipo": t, "punto": [x, y, z]} for t, x, y, z in conexiones
        ],
    }


def generar(inventario: Path, biblioteca_zip: Path, salida: Path) -> dict:
    biblioteca = Biblioteca(str(biblioteca_zip))
    piezas = cargar_inventario(inventario)

    catalogo, sin_forma, sin_geometria, no_encontradas = [], [], [], []

    for diseno, datos in sorted(piezas.items()):
        if diseno in SIN_FORMA_FIJA:
            sin_forma.append({**datos, "motivo": SIN_FORMA_FIJA[diseno]})
            continue

        numero = EQUIVALENCIAS.get(diseno, diseno)
        if not biblioteca.existe(f"{numero}.dat"):
            no_encontradas.append(datos)
            continue

        numero = resolver(biblioteca, numero)

        descripcion = describir(biblioteca, numero)
        if descripcion is None:
            sin_geometria.append(datos)
            continue

        catalogo.append({**datos, **descripcion})

    total = sum(p["cantidad"] for p in piezas.values())
    cubiertas = sum(p["cantidad"] for p in catalogo)

    documento = {
        "formato": "blockcad-catalogo",
        "version": 1,
        "origen": {
            "inventario": inventario.name,
            "geometria": "The LDraw Parts Library (CC BY 4.0) - https://www.ldraw.org",
        },
        "resumen": {
            "moldes_en_el_set": len(piezas),
            "moldes_en_el_catalogo": len(catalogo),
            "piezas_en_el_set": total,
            "piezas_en_el_catalogo": cubiertas,
        },
        "piezas": catalogo,
        "descartadas": {
            "sin_forma_fija": sin_forma,
            "sin_geometria": sin_geometria,
            "no_estan_en_ldraw": no_encontradas,
        },
    }

    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(
        json.dumps(documento, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return documento


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventario", type=Path, required=True)
    parser.add_argument("--biblioteca", type=Path, required=True)
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args()

    documento = generar(args.inventario, args.biblioteca, args.salida)
    resumen = documento["resumen"]

    print(f"Catálogo escrito en {args.salida}")
    print(
        f"  moldes: {resumen['moldes_en_el_catalogo']}/{resumen['moldes_en_el_set']}"
        f"   piezas: {resumen['piezas_en_el_catalogo']}/{resumen['piezas_en_el_set']}"
    )
    for clave, lista in documento["descartadas"].items():
        if lista:
            print(f"\n  {clave.replace('_', ' ')}:")
            for pieza in lista:
                print(
                    f"    {pieza['diseno']:<8} x{pieza['cantidad']:<3} "
                    f"{pieza['nombre_lego'][:38]}"
                )


if __name__ == "__main__":
    main()
