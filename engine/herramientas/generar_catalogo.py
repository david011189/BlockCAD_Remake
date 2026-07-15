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
    "42127": "32013",   # ANGLE ELEMENT, 0 DEGREES [1]      -> Angle Connector #1
    "42128": "32016",   # ANGLE ELEMENT, 157,5 DEGR. [3]    -> Angle Connector #3 (157.5)
    "42156": "32192",   # ANGLE ELEMENT 135 DEG. [4]        -> Angle Connector #4 (135)
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
        "nombre_ldraw": pieza.nombre,
        "licencia": pieza.licencia,
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
