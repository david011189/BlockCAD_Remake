# BlockCAD Engine — Paso 1

Primer núcleo funcional del remake de BlockCAD.

## Qué incluye

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

## Convención de coordenadas

- `x`: izquierda/derecha, medido en studs.
- `y`: adelante/atrás, medido en studs.
- `z`: altura, medida en unidades de placa.
- Una placa tiene altura `1`.
- Un ladrillo normal tiene altura `3`.
- La rotación es `0`, `90`, `180` o `270` grados.

## Ejecutar la demostración

Desde la carpeta del proyecto:

```cmd
python -m blockcad_engine.cli
```

Esto genera `modelo_demo.blockcad.json`.

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

El Paso 2 añadirá el patrón Command para:

- deshacer;
- rehacer;
- transacciones;
- agrupación de varias operaciones;
- registro limpio de cambios.
