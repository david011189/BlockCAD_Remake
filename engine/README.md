# BlockCAD Engine — Paso 2

Núcleo del remake de BlockCAD con sistema de comandos, deshacer y rehacer.

## Qué incluye

Todo lo del Paso 1:

- Modelo de coordenadas enteras en una cuadrícula.
- Catálogo básico de piezas.
- Piezas colocadas con identificadores únicos.
- Rotación en pasos de 90 grados.
- Movimiento y eliminación.
- Detección de colisiones por volumen.
- Guardado y carga en JSON.
- Pruebas automatizadas.
- Demostración desde consola.
- Sin PySide6 y sin dependencias externas.

Y lo añadido en el Paso 2:

- Patrón Command: cada operación es un objeto reversible.
- Historial con deshacer y rehacer, con límite opcional.
- Transacciones que agrupan varias operaciones en una sola entrada.
- Reversión automática cuando una transacción falla a medias.
- Fachada `BlockEditor` como punto de entrada para la interfaz futura.
- Etiquetas legibles de cada operación para mostrar en un menú.

## Convención de coordenadas

- `x`: izquierda/derecha, medido en studs.
- `y`: adelante/atrás, medido en studs.
- `z`: altura, medida en unidades de placa.
- Una placa tiene altura `1`.
- Un ladrillo normal tiene altura `3`.
- La rotación es `0`, `90`, `180` o `270` grados.

## Uso básico

```python
from blockcad_engine import BlockEditor, GridPosition

editor = BlockEditor(name="Mi construcción")

base = editor.add("brick_2x4", GridPosition(0, 0, 0), color="#D62828")
editor.rotate_clockwise(base.instance_id)

editor.undo()   # deshace la rotación
editor.redo()   # la vuelve a aplicar

editor.save("mi_modelo.blockcad.json")
```

## Transacciones

Un bloque `transaction` se deshace como una sola operación. Si algo falla
dentro del bloque, lo ya ejecutado se revierte y el historial queda intacto.

```python
with editor.transaction("Construir muro"):
    editor.add("brick_2x4", GridPosition(0, 0, 0))
    editor.add("brick_2x4", GridPosition(2, 0, 0))
    editor.add("brick_2x4", GridPosition(4, 0, 0))

editor.undo()   # retira las tres piezas de una vez
```

## Modelo y editor

`BlockModel` conserva su API directa y sigue siendo válida para scripts o
pruebas que no necesiten historial. `BlockEditor` la envuelve y registra cada
cambio. Los cambios hechos directamente sobre el modelo no se registran, así
que la interfaz debe trabajar siempre a través del editor.

## Ejecutar la demostración

Desde la carpeta del proyecto:

```cmd
python -m blockcad_engine.cli
```

Esto genera `modelo_demo.blockcad.json` y muestra el historial en consola.

## Ejecutar las pruebas

```cmd
python -m unittest discover -s tests -v
```

## Instalar en modo editable

No es obligatorio, pero facilita trabajar desde cualquier carpeta:

```cmd
python -m pip install -e .
blockcad-demo
```

## Próximo paso

El Paso 3 añadirá las conexiones entre piezas:

- studs y tubos;
- puntos de anclaje;
- validación de soporte;
- encaje automático a la cuadrícula.
