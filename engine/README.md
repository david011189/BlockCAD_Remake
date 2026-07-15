# BlockCAD Engine

Núcleo del remake de BlockCAD, más un lenguaje textual para describir
construcciones y un editor web con vista 3D en vivo.

## El editor: escribe código, mira el modelo

```cmd
python -m blockcad_web
```

Abre el navegador con el editor a la izquierda y el modelo 3D a la derecha,
que se actualiza mientras escribes. Se gira arrastrando y se acerca con la
rueda.

```
modelo "Casa sencilla"

// La base
ladrillo 2x4 en 0,0,0 color rojo
ladrillo 2x4 en 2,0,0 color amarillo

// Cuatro alturas de pared
repetir 4 veces desplazando 0,0,3:
    ladrillo 1x2 en 0,0,3 color celeste
    ladrillo 1x2 en 3,0,3 color celeste

placa 2x4 en 0,0,15 color verde
baldosa 1x2 en 1,1,16 color blanco
```

Funciona sin conexión: Three.js va incluido en `blockcad_web/vendor/` bajo
licencia MIT, compatible con la GPL de este proyecto. Ni el motor, ni el
servidor, ni el visor descargan nada de internet.

### Tu trabajo no se pierde

El código se guarda solo en el navegador mientras escribes, también cuando
todavía no compila, y vuelve al recargar. El ejemplo solo aparece la primera
vez; si vacías el editor con **Nuevo**, sigue vacío al volver.

| Botón | Qué hace |
|---|---|
| **Nuevo** | Vacía el editor para empezar de cero. Pregunta antes de borrar. |
| **Abrir** | Carga un `.blockcad` o un `.json` del motor. El JSON se convierte a código. |
| **Guardar** | Descarga el código como `.blockcad`, con el nombre del modelo. |
| **Exportar JSON** | Descarga el modelo en el formato del motor, el mismo que lee `load_model`. |
| **Ejemplo** | Vuelve a cargar la casa de muestra. |
| **Centrar** | Encuadra la cámara sobre el modelo. |

El guardado automático vive en este navegador y en este equipo. Para
conservar algo de verdad, usa **Guardar**.

**Abrir** entiende los dos formatos que escribe el editor. Al abrir un JSON,
el motor lo convierte de vuelta a código con `model_to_source`. Ojo: el JSON
guarda piezas, no bucles, así que un `repetir` vuelve expandido en líneas
sueltas; el modelo es el mismo, el código no.

### La consola

Debajo del código hay una caja para mandar órdenes sueltas. Enter envía;
Mayúsculas+Enter salta de línea para mandar varias piezas de una vez.

| Orden | Qué hace |
|---|---|
| `ladrillo 2x4 en 0,0,0 color rojo` | Añade esa pieza al final del código. |
| `borrar 7` | Borra la línea 7. |
| `borrar ultima` | Borra la última pieza. |
| `deshacer` / `rehacer` | Sobre las órdenes de la consola. |
| `centrar` | Encuadra la cámara. |
| `limpiar` | Vacía el editor; se puede deshacer. |
| `ayuda` | La lista. |

Una orden que no compile —una pieza que choca, por ejemplo— se rechaza y
**no toca el código**: la consola comprueba antes de añadir.

La consola edita el texto, no un modelo aparte. El código sigue siendo el
único origen de la verdad, así que tus `repetir` y tus comentarios
sobreviven a cualquier orden.

## El lenguaje

Una instrucción por línea. Los errores indican siempre la línea y, cuando dos
piezas chocan, también la línea de la otra pieza.

### Colocar una pieza

```
<tipo> <medida> en <x>,<y>,<z> [opciones]
```

- **tipo**: `ladrillo`, `placa`, `baldosa`, o un identificador del catálogo
  como `brick_2x4`.
- **medida**: `1x1`, `1x2`, `2x2`, `2x4`… según lo que exista en el catálogo.
- **en**: posición de la esquina mínima.

Opciones, todas opcionales y en cualquier orden:

| Opción | Ejemplo | Significado |
|---|---|---|
| `color` | `color rojo` o `color #00AAFF` | Color de la pieza. |
| `rot` / `rotado` | `rot 90` | Giro sobre el eje Z: 0, 90, 180 o 270. |
| `grupo` | `grupo 2` | Número de grupo. |
| `paso` | `paso 5` | Número de paso de montaje. |
| `transparente` | `transparente` | Dibuja la pieza translúcida. |

Colores con nombre: `rojo`, `azul`, `celeste`, `amarillo`, `verde`,
`naranja`, `blanco`, `negro`, `gris`, `marron`, `rosa`, `morado`.

### Nombrar el modelo

```
modelo "Mi construcción"
```

Debe ser la primera instrucción.

### Repetir

```
repetir 4 veces desplazando 0,0,3:
    ladrillo 2x2 en 1,1,0
```

Coloca el bloque indentado 4 veces, sumando el desplazamiento en cada vuelta.
`veces` es opcional. Se pueden anidar para construir rejillas.

### Comentarios

`#` al principio de una línea, o `//` en cualquier posición. `#` solo comenta
al principio de la línea porque en cualquier otro sitio empieza un color.

## El motor

- Modelo de coordenadas enteras en una cuadrícula.
- Catálogo de piezas y piezas colocadas con identificador único.
- Rotación en pasos de 90 grados, movimiento y eliminación.
- Detección de colisiones por volumen.
- Guardado y carga en JSON versionado.
- Patrón Command con deshacer, rehacer y transacciones.
- Sin PySide6 y sin dependencias externas.

### Convención de coordenadas

- `x`: izquierda/derecha, medido en studs.
- `y`: adelante/atrás, medido en studs.
- `z`: altura, medida en unidades de placa.
- Una placa tiene altura `1`; un ladrillo normal, `3`.
- La rotación es `0`, `90`, `180` o `270` grados.

El visor respeta la proporción real: un stud mide 8 mm y una placa 3,2 mm de
alto, así que la altura se dibuja a escala 0,4.

### Uso desde Python

```python
from blockcad_engine import BlockEditor, GridPosition, parse_model

editor = BlockEditor(name="Mi construcción")
base = editor.add("brick_2x4", GridPosition(0, 0, 0), color="#D62828")
editor.rotate_clockwise(base.instance_id)
editor.undo()

modelo = parse_model('ladrillo 2x4 en 0,0,0 color rojo')
```

Un bloque `transaction` se deshace como una sola operación, y si algo falla
dentro se revierte lo ya ejecutado:

```python
with editor.transaction("Construir muro"):
    editor.add("brick_2x4", GridPosition(0, 0, 0))
    editor.add("brick_2x4", GridPosition(2, 0, 0))
```

### Errores

Todo fallo del motor deriva de `BlockCADError`, así que una interfaz puede
capturarlo con un solo `except`. Los que históricamente eran `ValueError` o
`KeyError` heredan también de esas clases, de modo que el código antiguo
sigue funcionando.

## Arquitectura

```
blockcad_engine/     motor puro: geometría, catálogo, modelo, comandos, lenguaje
blockcad_web/        editor y visor 3D; depende del motor, el motor no de él
blockcad_web/vendor/ Three.js incluido (MIT), para funcionar sin conexión
```

## Ejecutar

```cmd
python -m blockcad_web              # editor con vista 3D
python -m blockcad_engine.cli       # demostración por consola
python -m unittest discover -s tests -v
```

## Instalar en modo editable

```cmd
python -m pip install -e .
blockcad-web
```

## Hoja de ruta

| Paso | Estado | Contenido |
|---|---|---|
| 1 | Hecho | Núcleo: piezas, coordenadas, colisiones, JSON. |
| 2 | Hecho | Comandos: deshacer, rehacer, transacciones. |
| — | Hecho | Lenguaje textual y editor web con vista 3D. |
| 3 | Siguiente | Conexiones: studs, tubos, anclajes y soporte. |
| 4 | | Catálogo ampliado y piezas paramétricas. |
| 5 | | Importar el formato original y LDraw. |
| 6 | | Renderizado propio y selección. |
| 7 | | Interfaz de escritorio con PySide6. |
