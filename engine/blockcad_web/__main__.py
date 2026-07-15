import argparse

from .server import serve


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="blockcad_web",
        description="Editor de código BlockCAD con vista 3D en vivo.",
    )
    parser.add_argument(
        "--puerto",
        type=int,
        default=8765,
        help="Puerto donde escuchar (8765 por defecto).",
    )
    parser.add_argument(
        "--sin-navegador",
        action="store_true",
        help="No abrir el navegador automáticamente.",
    )
    args = parser.parse_args()
    serve(args.puerto, open_browser=not args.sin_navegador)


if __name__ == "__main__":
    main()
