from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from blockcad_engine import BlockCADError, BlockModel, DslError, parse_model
from blockcad_engine.dsl import model_to_source
from blockcad_engine.serialization import model_from_dict, model_to_dict

_HTML = Path(__file__).with_name("index.html")
_VENDOR = Path(__file__).with_name("vendor")

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


def model_to_scene(model: BlockModel) -> dict:
    """Traduce el modelo a cajas listas para dibujar.

    El navegador no conoce el catálogo, así que aquí se resuelven las
    dimensiones ya rotadas de cada pieza.
    """
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
                # Los studs solo se dibujan si la pieza sigue de pie: en
                # una viga tumbada mirarían de lado, y el visor todavía
                # no sabe girarlos.
                "studs": definition.has_top_studs and item.orientation.keeps_z_up,
                "transparente": item.transparent,
                "nombre": definition.name,
            }
        )
    return {"nombre": model.name, "piezas": piezas}


def compile_source(source: str) -> dict:
    """Compila código BlockCAD y devuelve la escena o el error."""
    try:
        model = parse_model(source)
    except DslError as error:
        return {"ok": False, "linea": error.line, "mensaje": error.message}
    except BlockCADError as error:
        return {"ok": False, "linea": None, "mensaje": str(error)}

    scene = model_to_scene(model)
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
        }
        accion = rutas.get(self.path)
        if accion is None:
            self._send(404, b"No encontrado", "text/plain; charset=utf-8")
            return

        length = int(self.headers.get("Content-Length", 0))
        self._send_json(accion(self.rfile.read(length).decode("utf-8")))


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
