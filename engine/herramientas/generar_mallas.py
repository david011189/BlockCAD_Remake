"""Extrae las mallas de LDraw de las piezas de un catálogo.

    python herramientas/generar_mallas.py \\
        --catalogo blockcad_engine/datos/catalogo_45300.json \\
        --biblioteca ../.ldraw-cache/complete.zip \\
        --salida blockcad_engine/datos/mallas_45300.json

Van en un archivo aparte del catálogo, y no dentro, porque pesan cincuenta
veces más: el catálogo se lee siempre y las mallas solo cuando hay que
dibujar. El servidor manda al navegador únicamente las de las piezas que el
modelo usa.

Geometría: The LDraw Parts Library, CC BY 4.0 — https://www.ldraw.org
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generar_catalogo import ALTO_STUD, _techo  # noqa: E402
from ldraw import Biblioteca  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blockcad_engine.parts import PartCatalog  # noqa: E402


def malla_en_ejes_del_motor(pieza) -> dict[str, list[float]]:
    """Los triángulos de la pieza, en coordenadas del motor y POR COLOR.

    Mismo cambio de ejes que para las conexiones: LDraw mide la vertical en Y
    y hacia ABAJO, el motor en Z y hacia arriba; y el origen pasa a ser la
    esquina mínima de la caja — de la caja de TODA la pieza, no de cada
    grupo: los grupos comparten origen o la pupila se despega del ojo.

    Ojo con una diferencia importante: aquí NO se quitan los studs. La caja de
    colisión los excluye porque se meten en la pieza de arriba, pero dibujar
    un ladrillo sin sus studs sería dibujar otra cosa. Por eso los vértices
    pueden salirse de la caja por arriba, y está bien.
    """
    minimo, maximo = pieza.caja()
    grupos: dict[str, list[float]] = {}
    for codigo, vertices in pieza.grupos.items():
        planos: list[float] = []
        for vertice in vertices:
            planos.append(round(vertice.x - minimo.x, 1))
            planos.append(round(vertice.z - minimo.z, 1))
            planos.append(round(maximo.y - vertice.y, 1))
        grupos[codigo] = planos
    return grupos


def _union(grupos: dict[str, list[float]]) -> list[float]:
    """Todos los triángulos juntos: lo que miden extensión y planta."""
    return [v for planos in grupos.values() for v in planos]


def colores_ldraw(biblioteca_zip: Path, codigos: set[str]) -> dict[str, str]:
    """El hex de cada código fijo usado, sacado del LDConfig oficial.

    Solo viajan los códigos que las mallas usan de verdad: el LDConfig entero
    son quinientos colores y aquí hacen falta media docena. El "16" no entra:
    no es un color, es «píntame», y el visor ya sabe de qué.

    Un código directo (0x2RRGGBB) lleva su hex dentro y no está en LDConfig.
    """
    with zipfile.ZipFile(biblioteca_zip) as zip_:
        nombre = next(
            n for n in zip_.namelist() if n.lower().endswith("ldconfig.ldr")
        )
        texto = zip_.read(nombre).decode("latin-1")

    tabla = {
        codigo: valor
        for codigo, valor in re.findall(
            r"^0 !COLOUR\s+\S+\s+CODE\s+(\d+)\s+VALUE\s+(#[0-9A-Fa-f]{6})",
            texto,
            re.MULTILINE,
        )
    }

    resultado = {}
    for codigo in sorted(codigos):
        if codigo in ("16", "24"):
            continue
        if codigo.lower().startswith("0x2") and len(codigo) == 9:
            resultado[codigo] = "#" + codigo[3:].upper()
        elif codigo in tabla:
            resultado[codigo] = tabla[codigo]
        else:
            print(f"  ojo: el código de color {codigo} no está en LDConfig")
    return resultado


def _extension(triangulos: list[float]) -> tuple[float, float, float]:
    ejes = [triangulos[i::3] for i in range(3)]
    return tuple(round(max(e) - min(e), 1) for e in ejes)


def _planta(triangulos: list[float]) -> tuple[float, float]:
    xs = triangulos[0::3]
    ys = triangulos[1::3]
    return round(max(xs) - min(xs), 1), round(max(ys) - min(ys), 1)


def giro_para_encajar(triangulos: list[float], ancho: float, fondo: float) -> int:
    """Cuánto hay que girar esta malla para que case con su caja, en grados.

    La malla se guarda TAL COMO VIENE de LDraw, sin retocar, y cada pieza dice
    el giro que necesita. Ajustarla al guardarla no se puede: dos catálogos
    comparten la misma malla y la quieren orientada distinto. El básico dice
    que un ladrillo 2x4 mide 2 de ancho por 4 de fondo; LDraw lo dibuja al
    revés, 4 por 2. Ninguno está mal, es un convenio; pero el archivo es uno
    solo y no puede estar girado y sin girar a la vez.
    """
    malla_ancho, malla_fondo = _planta(triangulos)
    if abs(malla_ancho - ancho) < 1 and abs(malla_fondo - fondo) < 1:
        return 0
    if abs(malla_ancho - fondo) < 1 and abs(malla_fondo - ancho) < 1:
        return 90
    # Ni encaja ni encaja girada. Se deja sin girar y se avisa, en vez de
    # deformarla en silencio.
    return 0


def generar(catalogo: Path, biblioteca_zip: Path, salida: Path) -> dict:
    biblioteca = Biblioteca(str(biblioteca_zip))
    documento = json.loads(catalogo.read_text(encoding="utf-8"))

    mallas = {}
    for entrada in documento["piezas"]:
        pieza = biblioteca.analizar(f"{entrada['ldraw']}.dat")
        if not pieza.vertices:
            continue
        # El motor identifica la pieza por su molde, no por su archivo.
        mallas[entrada["diseno"]] = malla_en_ejes_del_motor(pieza)

    # El catálogo básico también dibuja: sus siete piezas idealizadas dicen de
    # qué molde real sale su malla. Sin esto, un modelo de ladrillos se
    # seguiría viendo como cajas.
    for definicion in PartCatalog.with_basic_parts().all():
        diseno = definicion.metadata.get("malla")
        if not diseno or diseno in mallas:
            continue
        pieza = biblioteca.analizar(f"{diseno}.dat")
        if pieza.vertices:
            mallas[diseno] = malla_en_ejes_del_motor(pieza)

    usados = {codigo for grupos in mallas.values() for codigo in grupos}
    resultado = {
        "formato": "blockcad-mallas",
        # La versión 2 agrupa los triángulos por color: {"16": [...], "0":
        # [...]}. La 1 los traía en una sola lista y tiraba el color, y por
        # eso los ojos del set se veían blanco sobre blanco.
        "version": 2,
        "origen": "The LDraw Parts Library (CC BY 4.0) - https://www.ldraw.org",
        # Cada grupo va en una lista plana de x,y,z: es lo que espera una
        # BufferGeometry, y ahorra un tercio del archivo frente a objetos.
        # El grupo "16" es el cuerpo pintable; el resto, colores fijos.
        "triangulos": mallas,
        # Cuánto ocupa cada malla TAL CUAL viene —todos los grupos juntos—,
        # que no es lo mismo que su caja de colisión: la malla lleva los studs
        # y puede venir con el ancho y el fondo cambiados. Hace falta para
        # reanclarla al girarla.
        "extension": {
            nombre: list(_extension(_union(grupos)))
            for nombre, grupos in mallas.items()
        },
        # Qué hex pinta cada código fijo, según el LDConfig oficial. Solo los
        # códigos que estas mallas usan.
        "colores_ldraw": colores_ldraw(biblioteca_zip, usados),
    }

    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")
    return resultado


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalogo", type=Path, required=True)
    parser.add_argument("--biblioteca", type=Path, required=True)
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args()

    resultado = generar(args.catalogo, args.biblioteca, args.salida)
    vertices = sum(
        len(planos) // 3
        for grupos in resultado["triangulos"].values()
        for planos in grupos.values()
    )
    tamano = args.salida.stat().st_size / 1024 / 1024

    print(f"Mallas escritas en {args.salida}")
    print(f"  {len(resultado['triangulos'])} piezas, {vertices:,} vértices, {tamano:.1f} MB")
    print(f"  colores fijos: {resultado['colores_ldraw']}")
    con_colores = {
        nombre: sorted(grupos)
        for nombre, grupos in resultado["triangulos"].items()
        if set(grupos) != {"16"}
    }
    print(f"  piezas con más de un color: {con_colores}")


if __name__ == "__main__":
    main()
