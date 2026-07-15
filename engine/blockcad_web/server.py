from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from blockcad_engine import BlockCADError, BlockModel, DslError, parse_model
from blockcad_engine.parts import PartCatalog

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
        dimensions = definition.dimensions.rotated(item.rotation)
        piezas.append(
            {
                "x": item.position.x,
                "y": item.position.y,
                "z": item.position.z,
                "ancho": dimensions.width,
                "fondo": dimensions.depth,
                "alto": dimensions.height,
                "color": item.color,
                "studs": definition.has_top_studs,
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


def catalog_summary() -> list[dict]:
    catalogo = PartCatalog.with_basic_parts()
    return [
        {
            "id": definition.part_id,
            "nombre": definition.name,
            "ancho": definition.dimensions.width,
            "fondo": definition.dimensions.depth,
            "alto": definition.dimensions.height,
        }
        for definition in catalogo.all()
    ]


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
        elif self.path == "/api/catalogo":
            self._send_json(catalog_summary())
        else:
            self._send(404, b"No encontrado", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        if self.path != "/api/modelo":
            self._send(404, b"No encontrado", "text/plain; charset=utf-8")
            return

        length = int(self.headers.get("Content-Length", 0))
        source = self.rfile.read(length).decode("utf-8")
        self._send_json(compile_source(source))


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
