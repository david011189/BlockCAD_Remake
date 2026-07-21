from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from functools import lru_cache
from pathlib import Path

from blockcad_engine import (
    BlockCADError,
    BlockModel,
    DslError,
    Orientation,
    parse_model,
    parse_model_con_lineas,
)
from blockcad_engine.catalogos import cargar as cargar_catalogo
from blockcad_engine.dsl import model_to_source
from blockcad_engine.serialization import model_from_dict, model_to_dict

_HTML = Path(__file__).with_name("index.html")
_VENDOR = Path(__file__).with_name("vendor")
_DATOS = Path(__file__).resolve().parents[1] / "blockcad_engine" / "datos"

EJEMPLO = '''modelo "Casa sencilla"

// La base: dos ladrillos que se tocan sin chocar
ladrillo 2x4 en 0,0,0 color rojo
ladrillo 2x4 en 2,0,0 color amarillo

// Las paredes: cuatro alturas de ladrillo
repetir 4 veces desplazando 0,0,3:
    ladrillo 1x2 en 0,0,3 color celeste
    ladrillo 1x2 en 3,0,3 color celeste
    ladrillo 1x2 en 0,2,3 color celeste
    ladrillo 1x2 en 3,2,3 color celeste

// El techo
placa 2x4 en 0,0,15 color verde
placa 2x4 en 2,0,15 color verde

// Un remate liso
baldosa 1x2 en 1,1,16 color blanco
'''


@lru_cache(maxsize=1)
def _archivo_mallas() -> dict:
    """Las mallas. 5 MB, así que se leen una sola vez."""
    archivo = _DATOS / "mallas_45300.json"
    if not archivo.is_file():
        return {"triangulos": {}, "extension": {}}
    return json.loads(archivo.read_text(encoding="utf-8"))


def _reanclar(orientacion: Orientation, medidas) -> list[int]:
    """Lo que hay que desplazar una caja girada para que vuelva al origen.

    Girar la manda fuera de su sitio: lo que quede en negativo es justo lo que
    hay que devolver.
    """
    return [
        -sum(min(0, fila[k] * medidas[k]) for k in range(3))
        for fila in orientacion.filas
    ]


def _transformacion(item, definition) -> dict:
    """La matriz y el origen que colocan la malla de una pieza donde va.

    Se compone aquí y no en el navegador porque hay que dar dos giros con su
    reanclaje cada uno, en orden, y equivocarse es facilísimo:

    1. El giro propio de la malla. LDraw dibuja el lado largo en X y este
       catálogo lo cuenta en Y, así que la malla llega girada respecto a su
       caja. Se reancla con la EXTENSIÓN DE LA MALLA, que no es la de la caja:
       lleva los studs y viene con el ancho y el fondo cambiados.
    2. La orientación que le ha dado quien construye. Se reancla con la caja
       de colisión, porque es la que define dónde está la pieza.

    Componiendo: mundo = Ru·(Rm·p + om) + ou + posición, o sea matriz Ru·Rm y
    origen Ru·om + ou + posición.
    """
    malla = definition.metadata.get("malla", definition.part_id)
    extension = _archivo_mallas()["extension"].get(malla)

    giro_malla = Orientation.z(int(definition.metadata.get("malla_giro", 0)))
    total = item.orientation.then(giro_malla)

    # Sin malla no hay nada que reanclar: el visor dibujará su caja.
    om = _reanclar(giro_malla, extension) if extension else [0, 0, 0]
    ou = _reanclar(
        item.orientation,
        (
            definition.dimensions.width,
            definition.dimensions.depth,
            definition.dimensions.height,
        ),
    )

    girado = item.orientation.apply(*om)
    return {
        "matriz": [list(fila) for fila in total.filas],
        "origen": [
            item.position.x + girado[0] + ou[0],
            item.position.y + girado[1] + ou[1],
            item.position.z + girado[2] + ou[2],
        ],
    }


def model_to_scene(model: BlockModel, lineas: dict[str, int] | None = None) -> dict:
    """Traduce el modelo a cajas listas para dibujar.

    El navegador no conoce el catálogo, así que aquí se resuelven las
    dimensiones ya rotadas de cada pieza.

    `lineas` dice qué línea del código creó cada pieza, y viaja con ella para
    que pinchar en el visor lleve al código. Un modelo que no viene de un
    texto —el que se importa de un JSON— no lo tiene, y entonces la pieza no
    lleva línea: se dibuja igual, pero no se puede pinchar.
    """
    lineas = lineas or {}
    # Una pieza en el aire no es un error: se avisa y se deja construir. Se
    # calcula una vez y se marca cada pieza, en vez de preguntarlo por pieza.
    flotantes = {p.instance_id for p in model.floating()}

    # Que piezas estan SUELTAS: sin union, sin apoyarse en otra y sin nadie
    # encima. Solo esas se pueden arrastrar con el raton; mover una pieza
    # enganchada arrancaria medio modelo.
    con_soporte: set[str] = set()
    enganchadas: set[str] = set()
    for item in model.instances:
        if model.connected_to(item.instance_id):
            enganchadas.add(item.instance_id)
        debajo = model.resting_on(item.instance_id)
        if debajo:
            enganchadas.add(item.instance_id)
            con_soporte.update(p.instance_id for p in debajo)
    enganchadas |= con_soporte

    conjuntos = _conjuntos(model)
    cinematica = _cinematica(model)

    piezas = []
    for item in model.instances:
        definition = model.catalog.get(item.part_id)
        dimensions = definition.dimensions.rotated(item.orientation)
        piezas.append(
            {
                "x": item.position.x,
                "y": item.position.y,
                "z": item.position.z,
                "ancho": dimensions.width,
                "fondo": dimensions.depth,
                "alto": dimensions.height,
                "color": item.color,
                "transparente": item.transparent,
                "nombre": definition.name,
                "flotante": item.instance_id in flotantes,
                "suelta": item.instance_id not in enganchadas,
                "rueda": definition.metadata.get("rueda"),
                "molde": item.part_id,
                "conjunto": conjuntos[item.instance_id],
                "grupo": item.group or None,
                **cinematica.get(item.instance_id, {}),
                **_acogida(item, definition),
                **_agarre(item, definition),
                **_machos(item, definition),
                **_engrane(item, definition),
                **_cremallera(item, definition),
                **_bocas(item, definition),
                "linea": lineas.get(item.instance_id),
                # Qué malla dibujar y dónde. Sin malla, el visor cae a la caja.
                "malla": definition.metadata.get("malla", definition.part_id),
                **_transformacion(item, definition),
            }
        )
    return {
        "nombre": model.name,
        "piezas": piezas,
        "flotantes": len(flotantes),
        # Se avisa, no se rechaza: quizá hay dos cajas. Solo cuentan las
        # piezas cuyo catálogo declara cuántas trae el set.
        "agotadas": _sobreuso(model),
        "inventario": _inventario(model),
    }


def _acogida(item, definition) -> dict:
    """Si la pieza es un contenedor, los ASIENTOS de sus huespedes.

    Cada huesped tiene el suyo —el tope de la pieza real—: las bocas de
    su altura declarada, agrupadas por recta, en coordenadas del mundo.
    El iman no debe ofrecer mas que esto, que es lo que el motor acepta.
    """
    acoge = definition.metadata.get("acoge")
    if not acoge:
        return {}
    entradas = [e.split("@") for e in acoge.split() if "@" in e]
    mundos = list(item.world_connections(definition))
    ejes_locales = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}
    from blockcad_engine.model import _espacio_en_mundo

    asientos = {}
    for molde, resto in entradas:
        donde, espacio = resto.split(":")
        altura, letra = int(donde[:-1]), donde[-1]
        eje_local = ejes_locales[letra]
        desde, hasta = (int(v) for v in espacio.split("-"))
        limites = _espacio_en_mundo(item, definition, letra, desde, hasta)
        tramo = list(limites[1:]) if limites else None
        bocas = [
            mundo
            for local, mundo in zip(definition.connections, mundos)
            if mundo.es_hembra
            and local.punto[2] == altura
            and tuple(abs(v) for v in local.eje) == eje_local
        ]
        grupos: list[list] = []
        for c in bocas:
            for g in grupos:
                if _misma_recta(g[0].punto, g[0].eje, c.punto, c.eje):
                    g.append(c)
                    break
            else:
                grupos.append([c])
        asientos[molde] = [
            {
                "centro": [sum(c.punto[k] for c in g) / len(g) for k in range(3)],
                "eje": list(g[0].eje),
                "espacio": tramo,
            }
            for g in grupos
        ]
    return {"acoge": [molde for molde, _ in entradas], "asientos": asientos}


def _agarre(item, definition) -> dict:
    """Donde agarrar la pieza al imantarla: su agujero de eje, si tiene uno.

    El iman de la acogida no puede anclar por el centro de la caja: el
    agujero del sinfin no esta en su centro, y anclarlo mal lo dejaria
    fuera de la recta por la que luego entra el eje. Es el desplazamiento
    del agujero respecto a la esquina de la pieza, ya girada.
    """
    agujeros = [
        c for c in item.world_connections(definition)
        if c.tipo == "agujero_eje"
    ]
    if len(agujeros) != 1:
        return {}
    p = agujeros[0].punto
    return {
        "agarre": [
            p[0] - item.position.x,
            p[1] - item.position.y,
            p[2] - item.position.z,
        ],
        "agarre_eje": list(agujeros[0].eje),
    }


def _cinematica(model: BlockModel) -> dict[str, dict]:
    """Como se mueve cada pieza cuando el motor gira a una vuelta patron.

    El grafo ya lo conocia la fisica; aqui solo se recorre desde el motor:

    - Recta compartida EN CRUZ gira junta (razon 1). Lo redondo resbala,
      como enseño la prueba en plastico: un eje en agujero redondo no
      transmite.
    - Dos ruedas dentadas engranadas: razon -dientes_a/dientes_b.
    - El sinfin reduce a 1/dientes, en angulo recto.
    - La rueda muerde a la cremallera: el giro se hace CARRERA, radio
      primitivo por radian, con el sentido del punto de contacto.
    - El neumatico gira con su llanta (razon 1).

    Devuelve, por instancia: {"giro": {punto, eje, razon}} para las que
    giran o {"carrera": {eje, razon}} para las que corren.
    """
    from blockcad_engine.model import (
        _muerden,
        _muerde_sinfin,
        _muerde_cremallera,
        _calzan,
        _paralelas,
    )

    piezas = list(model.instances)
    defs = {p.instance_id: model.catalog.get(p.part_id) for p in piezas}
    conex = {
        p.instance_id: list(p.world_connections(defs[p.instance_id]))
        for p in piezas
    }

    def cruces(p):
        return [c for c in conex[p.instance_id] if c.tipo == "agujero_eje"]

    def machos(p):
        return [c for c in conex[p.instance_id] if c.es_macho]

    movimiento: dict[str, dict] = {}
    pendientes = []
    for p in piezas:
        if defs[p.instance_id].metadata.get("motor"):
            boca = cruces(p)[0]
            movimiento[p.instance_id] = {"giro": {
                "punto": list(boca.punto), "eje": list(boca.eje), "razon": 1.0,
            }}
            pendientes.append(p)

    while pendientes:
        actual = pendientes.pop()
        mio = movimiento[actual.instance_id].get("giro")
        if not mio:
            continue
        d_act = defs[actual.instance_id]
        for otra in piezas:
            if otra.instance_id in movimiento:
                continue
            d_otra = defs[otra.instance_id]

            # Recta compartida en cruz: mismo giro. Vale macho-a-cruz en
            # los dos sentidos (el eje mueve al gusano; el motor al eje).
            recta = None
            for a, b in ((actual, otra), (otra, actual)):
                for mc in machos(a):
                    for cz in cruces(b):
                        if mc.misma_recta_que(cz):
                            recta = cz if b is otra else mc
                if recta:
                    break
            if recta is None and cruces(otra):
                # El motor no tiene macho: su boca en cruz comparte recta
                # con el eje que agarra.
                for ca in cruces(actual):
                    for cz in cruces(otra):
                        if ca.misma_recta_que(cz):
                            recta = cz
            if recta is not None:
                movimiento[otra.instance_id] = {"giro": {
                    "punto": list(recta.punto),
                    "eje": list(recta.eje),
                    "razon": mio["razon"],
                }}
                pendientes.append(otra)
                continue

            # Mordida entre ruedas paralelas: razon de dientes, contraria.
            da = d_act.metadata.get("dientes")
            db = d_otra.metadata.get("dientes")
            if da and db and _muerden(actual, d_act, otra, d_otra):
                eje_b = cruces(otra)[0]
                movimiento[otra.instance_id] = {"giro": {
                    "punto": list(eje_b.punto),
                    "eje": list(eje_b.eje),
                    "razon": -mio["razon"] * int(da) / int(db),
                }}
                pendientes.append(otra)
                continue

            # El sinfin muerde en angulo recto: una vuelta, un diente.
            if (
                d_act.metadata.get("sinfin")
                and db
                and _muerde_sinfin(actual, d_act, otra, d_otra)
            ):
                eje_b = cruces(otra)[0]
                movimiento[otra.instance_id] = {"giro": {
                    "punto": list(eje_b.punto),
                    "eje": list(eje_b.eje),
                    "razon": mio["razon"] / int(db),
                }}
                pendientes.append(otra)
                continue

            # La rueda muerde a la cremallera: giro hecho carrera.
            if (
                da
                and d_otra.metadata.get("cremallera")
                and _muerde_cremallera(actual, d_act, otra, d_otra)
            ):
                eje_a = cruces(actual)[0]
                radio = int(da) * 1.25
                filas = otra.orientation.filas
                normal = [filas[i][2] for i in range(3)]
                # v = eje x r: del eje de la rueda al punto de contacto.
                v = [
                    mio["eje"][1] * normal[2] - mio["eje"][2] * normal[1],
                    mio["eje"][2] * normal[0] - mio["eje"][0] * normal[2],
                    mio["eje"][0] * normal[1] - mio["eje"][1] * normal[0],
                ]
                movimiento[otra.instance_id] = {"carrera": {
                    "eje": v,
                    "razon": mio["razon"] * radio,
                }}
                continue

            # El neumatico gira con su llanta.
            if _calzan(actual, d_act, otra, d_otra):
                movimiento[otra.instance_id] = {"giro": dict(mio)}
                pendientes.append(otra)
                continue

    # El motor es la FUENTE: su rotor gira por dentro, pero su carcasa se
    # queda quieta. Sirvio para arrancar el recorrido y aqui se despide.
    return {
        clave: mov
        for clave, mov in movimiento.items()
        if not defs[clave].metadata.get("motor")
    }


def _conjuntos(model: BlockModel) -> dict[str, int]:
    """A que conjunto pertenece cada pieza: su componente conectada.

    Dos piezas estan en el mismo conjunto si una cadena de uniones o de
    apoyos las junta. Es lo que el visor necesita para mover o girar un
    bloque entero como una sola cosa: la caja del sinfin y todo su tren
    son UN conjunto, y el muro de al lado es otro.
    """
    vecinos: dict[str, set[str]] = {p.instance_id: set() for p in model.instances}
    for item in model.instances:
        for otra in model.connected_to(item.instance_id):
            vecinos[item.instance_id].add(otra.instance_id)
            vecinos[otra.instance_id].add(item.instance_id)
        for otra in model.resting_on(item.instance_id):
            vecinos[item.instance_id].add(otra.instance_id)
            vecinos[otra.instance_id].add(item.instance_id)
    conjunto: dict[str, int] = {}
    numero = 0
    for item in model.instances:
        if item.instance_id in conjunto:
            continue
        frontera = [item.instance_id]
        while frontera:
            actual = frontera.pop()
            if actual in conjunto:
                continue
            conjunto[actual] = numero
            frontera.extend(vecinos[actual])
        numero += 1
    return conjunto


def _misma_recta(p1, e1, p2, e2) -> bool:
    def paralelos(a, b):
        cruz = (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )
        return all(abs(c) < 1e-6 for c in cruz)

    if not paralelos(e1, e2):
        return False
    entre = tuple(a - b for a, b in zip(p1, p2))
    return not any(entre) or paralelos(entre, e1)


def _machos(item, definition) -> dict:
    """El asa del iman: los machos de la pieza, si forman una sola recta.

    Un eje son dos puntas de la misma recta; su centro es donde el iman lo
    agarra para casarlo con un agujero. Va relativo a la esquina, girado.
    """
    machos = [c for c in item.world_connections(definition) if c.es_macho]
    if not machos:
        return {}
    primero = machos[0]
    if any(
        not _misma_recta(primero.punto, primero.eje, m.punto, m.eje)
        for m in machos[1:]
    ):
        return {}
    centro = [
        sum(m.punto[k] for m in machos) / len(machos) for k in range(3)
    ]
    return {
        "macho_centro": [
            centro[0] - item.position.x,
            centro[1] - item.position.y,
            centro[2] - item.position.z,
        ],
        "macho_eje": list(primero.eje),
    }


def _bocas(item, definition) -> dict:
    """Los agujeros de la pieza, agrupados por recta: centro y direccion.

    Es lo que el iman necesita para dejar caer un eje o un pin DENTRO: la
    recta exacta ya girada y colocada, que ninguna punteria de raton
    acertaria sola.
    """
    grupos: list[list] = []
    for c in item.world_connections(definition):
        if not c.es_hembra:
            continue
        for g in grupos:
            if _misma_recta(g[0].punto, g[0].eje, c.punto, c.eje):
                g.append(c)
                break
        else:
            grupos.append([c])
    if not grupos:
        return {}
    bocas = []
    for g in grupos:
        centro = [sum(c.punto[k] for c in g) / len(g) for k in range(3)]
        bocas.append({"centro": centro, "eje": list(g[0].eje)})
    return {"bocas": bocas}


def _engrane(item, definition) -> dict:
    """Si la pieza es una rueda dentada, su eje en el mundo y su radio.

    Es lo que necesita el iman de la cremallera: la tangente al circulo
    primitivo no se acierta a ojo.
    """
    dientes = definition.metadata.get("dientes")
    if not dientes:
        return {}
    ejes = [
        c for c in item.world_connections(definition)
        if c.tipo == "agujero_eje"
    ]
    if len(ejes) != 1:
        return {}
    return {"engrane": {
        "punto": list(ejes[0].punto),
        "eje": list(ejes[0].eje),
        "radio": int(dientes) * 1.25,
    }}


def _cremallera(item, definition) -> dict:
    """Si la pieza es una cremallera, hacia donde miran sus dientes.

    La normal va girada al mundo; el paso es la altura de su linea de
    paso sobre la base. Con eso el visor sabe hacerla tangente.
    """
    paso = definition.metadata.get("cremallera")
    if not paso:
        return {}
    filas = item.orientation.filas
    return {"cremallera": {
        "normal": [filas[i][2] for i in range(3)],
        "paso": int(paso),
    }}


def _inventario(model: BlockModel) -> dict | None:
    """Cuántas piezas trae la caja y cuántas usa el modelo, si hay caja."""
    total = sum(
        int(d.metadata["cantidad_en_el_set"])
        for d in model.catalog.all()
        if d.metadata.get("cantidad_en_el_set")
    )
    if not total:
        return None
    return {"total": total, "usadas": len(model.instances)}


def _sobreuso(model: BlockModel) -> list[dict]:
    """Qué moldes usa el modelo por encima de lo que trae la caja."""
    usadas: dict[str, int] = {}
    for item in model.instances:
        usadas[item.part_id] = usadas.get(item.part_id, 0) + 1

    agotadas = []
    for part_id, cuantas in sorted(usadas.items()):
        definicion = model.catalog.get(part_id)
        hay = definicion.metadata.get("cantidad_en_el_set")
        if hay and cuantas > int(hay):
            agotadas.append({
                "pieza": part_id,
                "nombre": definicion.name,
                "usadas": cuantas,
                "hay": int(hay),
            })
    return agotadas


def compile_source(source: str) -> dict:
    """Compila código BlockCAD y devuelve la escena o el error."""
    try:
        model, lineas = parse_model_con_lineas(source)
    except DslError as error:
        return {"ok": False, "linea": error.line, "mensaje": error.message}
    except BlockCADError as error:
        return {"ok": False, "linea": None, "mensaje": str(error)}

    scene = model_to_scene(model, lineas)
    scene["ok"] = True
    return scene


def compile_json(source: str) -> dict:
    """Compila el código y devuelve el JSON del motor, listo para descargar.

    El formato lo define `serialization.model_to_dict`, no el navegador: así
    lo que se exporta es exactamente lo que el motor sabe volver a leer.
    """
    try:
        model = parse_model(source)
    except DslError as error:
        return {"ok": False, "linea": error.line, "mensaje": error.message}
    except BlockCADError as error:
        return {"ok": False, "linea": None, "mensaje": str(error)}

    return {
        "ok": True,
        "nombre": model.name,
        "json": json.dumps(model_to_dict(model), indent=2, ensure_ascii=False),
    }


def piezas_para_soltar(texto: str) -> dict:
    """La paleta del editor: qué piezas hay y cómo se escriben.

    Recibe el nombre del catálogo («wedo», o «basico» si el código no dice
    ninguno) y devuelve, por pieza, la frase con que se escribe en el
    lenguaje —soltar una pieza ESCRIBE CÓDIGO, no toca ningún modelo— y su
    caja, para que el visor enseñe un fantasma del tamaño verdadero.
    """
    from blockcad_engine.dsl import _part_phrase
    from blockcad_engine.parts import PartCatalog

    nombre = texto.strip().strip('"') or "basico"
    try:
        catalogo = (
            PartCatalog.with_basic_parts()
            if nombre == "basico"
            else cargar_catalogo(nombre)
        )
    except BlockCADError:
        return {"piezas": []}

    piezas = []
    for definicion in catalogo.all():
        piezas.append({
            "escritura": _part_phrase(
                definicion.aliases[0] if definicion.aliases else definicion.part_id
            ),
            "nombre": definicion.name,
            "categoria": definicion.category,
            "ancho": definicion.dimensions.width,
            "fondo": definicion.dimensions.depth,
            "alto": definicion.dimensions.height,
            "color": definicion.default_color,
            "cantidad": int(definicion.metadata.get("cantidad_en_el_set", 0)),
            "malla": definicion.metadata.get("malla", definicion.part_id),
        })
    piezas.sort(key=lambda p: (p["categoria"], p["escritura"]))
    return {"piezas": piezas}


def mallas_pedidas(texto: str) -> dict:
    """Devuelve solo las mallas que hagan falta, con sus colores.

    El archivo entero son 5 MB y 99 piezas; un modelo usa un puñado. Mandarlo
    todo en cada compilación sería tirar el ancho de banda por gusto.

    Formato 2: cada malla trae sus triángulos agrupados por código de color
    —"16" es el cuerpo pintable, el resto son fijos: la pupila de un ojo es
    negra la pinte quien la pinte—, y `colores_ldraw` dice el hex de cada
    código fijo que aparezca en lo pedido.
    """
    vacio = {"mallas": {}, "colores_ldraw": {}}
    try:
        pedidas = json.loads(texto)
    except json.JSONDecodeError:
        return vacio
    documento = _archivo_mallas()
    disponibles = documento["triangulos"]
    mallas = {
        nombre: disponibles[nombre]
        for nombre in pedidas
        if isinstance(nombre, str) and nombre in disponibles
    }
    usados = {codigo for grupos in mallas.values() for codigo in grupos}
    colores = documento.get("colores_ldraw", {})
    return {
        "mallas": mallas,
        "colores_ldraw": {c: colores[c] for c in sorted(usados) if c in colores},
    }


def import_json(texto: str) -> dict:
    """Convierte un modelo en JSON a código, para poder abrirlo en el editor.

    Sin esto, el JSON que exporta el propio editor no se podría volver a
    abrir con él.
    """
    try:
        payload = json.loads(texto)
    except json.JSONDecodeError as error:
        return {"ok": False, "mensaje": f"El archivo no es JSON válido: {error}"}

    if not isinstance(payload, dict):
        return {"ok": False, "mensaje": "El archivo no es un modelo BlockCAD."}

    try:
        model = model_from_dict(payload)
    except BlockCADError as error:
        return {"ok": False, "mensaje": str(error)}

    return {"ok": True, "codigo": model_to_source(model)}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # noqa: D102 - silencia el ruido
        pass

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict | list) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(200, body, "application/json; charset=utf-8")

    def _send_vendor(self, nombre: str) -> None:
        # El servidor solo escucha en 127.0.0.1, pero un nombre como
        # '../../secreto' no debe salir nunca de la carpeta vendor.
        raiz = _VENDOR.resolve()
        destino = (raiz / nombre).resolve()
        if raiz not in destino.parents or not destino.is_file():
            self._send(404, b"No encontrado", "text/plain; charset=utf-8")
            return

        tipo = (
            "text/javascript; charset=utf-8"
            if destino.suffix == ".js"
            else "text/plain; charset=utf-8"
        )
        self._send(200, destino.read_bytes(), tipo)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send(
                200,
                _HTML.read_bytes(),
                "text/html; charset=utf-8",
            )
        elif self.path.startswith("/vendor/"):
            self._send_vendor(self.path[len("/vendor/"):])
        elif self.path == "/api/ejemplo":
            self._send_json({"codigo": EJEMPLO})
        else:
            self._send(404, b"No encontrado", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        rutas = {
            "/api/modelo": compile_source,
            "/api/json": compile_json,
            "/api/importar": import_json,
            "/api/mallas": mallas_pedidas,
            "/api/piezas": piezas_para_soltar,
        }
        accion = rutas.get(self.path)
        if accion is None:
            self._send(404, b"No encontrado", "text/plain; charset=utf-8")
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            texto = self.rfile.read(length).decode("utf-8")
        except UnicodeDecodeError:
            # Un cuerpo que no es UTF-8 —un archivo guardado con otra
            # codificación, un cliente mal configurado— no puede tirar la
            # petición sin respuesta: eso deja al navegador esperando y al
            # usuario sin saber qué pasó.
            self._send_json({
                "ok": False,
                "linea": None,
                "mensaje": "El texto no llegó en UTF-8. Si es un archivo, "
                "guárdalo con esa codificación y vuelve a abrirlo.",
            })
            return
        self._send_json(accion(texto))


def serve(port: int = 8765, *, open_browser: bool = True) -> None:
    """Arranca el editor en el navegador."""
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    url = f"http://127.0.0.1:{server.server_port}/"

    print(f"Editor BlockCAD en {url}")
    print("Pulsa Ctrl+C para detenerlo.")

    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDetenido.")
    finally:
        server.server_close()
