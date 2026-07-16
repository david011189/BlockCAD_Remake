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

### El ratón

Pincha una pieza en el visor y se enciende, se marca en azul la línea que la
puso y se te dice cuál es. **Supr borra esa línea**, pasando por la misma
orden `borrar` de la consola: el deshacer sigue valiendo.

Se enciende solo la pieza que pinchas. Pero lo que se borra es la **línea**,
y una línea con `repetir` pone varias piezas: no hay forma de quitar un
ladrillo de un bucle sin reescribirlo. Cuando pasa, se avisa antes —«pone 4
piezas, y Supr borra la línea entera»— en vez de llevarse cuatro por
sorpresa.

Arrastrar gira la cámara y no elige nada: un clic solo cuenta como clic si el
ratón no se ha movido.

El ratón navega el código; no edita un modelo paralelo. Una pieza abierta
desde un `.json` no salió de ningún texto, así que no lleva línea: se dibuja
igual, y al pincharla se te dice que no hay adónde llevarte.

## El lenguaje

Una instrucción por línea. Los errores indican siempre la línea y, cuando dos
piezas chocan, también la línea de la otra pieza.

### Piezas en el aire

Una pieza sin apoyo **se avisa, no se rechaza**: el BlockCAD original permitía
piezas flotantes y aquí también. La barra de estado dice cuántas hay y el
visor las marca con el contorno en ámbar.

Una pieza está sujeta si toca el suelo, si se apoya en otra, o si comparte un
punto de conexión con otra. Lo último hace falta para Technic: dos vigas
pegadas comparten los agujeros de la cara que se tocan, porque un agujero
atraviesa la pieza y sale por los dos lados.

Un ladrillo, en cambio, tiene studs arriba y nada debajo, así que dos
apilados no comparten ningún punto: se sostienen por apoyo. Por eso hacen
falta las dos reglas.

```python
modelo.floating()                  # las que quedan al aire
modelo.is_supported(instance_id)
modelo.resting_on(instance_id)     # las que tiene debajo
modelo.connected_to(instance_id)   # las que comparten un punto con ella
```

### Elegir el catálogo

Sin decir nada se construye con siete piezas idealizadas: ladrillos, placas y
baldosas. Para usar las de verdad, las que trae una caja concreta:

```
catalogo "wedo"
modelo "Mi robot"

viga 7 en 0,0,0 color rojo
eje 6 en 0,8,0
19071 en 0,14,0          // el hub, 6x8 studs
21980 en 8,14,0          // el motor mediano
```

Va en la primera línea, antes de `modelo`. Son las **277 piezas del set
45300**, con sus medidas reales sacadas de LDraw y lo que trae la caja de
cada una.

Ojo: es un set de robótica. **No trae ladrillos 1×1 ni placas 2×4**, así que
un modelo de ladrillos no compila con él. Los dos catálogos conviven.

Una pieza se escribe por su **número de molde** —`19071`, `3001`—, que es el
que sale en cualquier inventario. Las familias regulares tienen además nombre
corto: `ladrillo 2x4`, `placa 1x2`, `baldosa 1x2`, `viga 7`, `eje 6`.

### Colocar una pieza

```
<tipo> <medida> en <x>,<y>,<z> [opciones]
<tipo> <medida> encima [de <nombre>] [desplazado <dx>,<dy>] [opciones]
```

- **tipo**: `ladrillo`, `placa`, `baldosa`, o un identificador del catálogo
  como `brick_2x4`.
- **medida**: `1x1`, `1x2`, `2x2`, `2x4`… según lo que exista en el catálogo.
- **en**: posición de la esquina mínima.

### Apoyar una pieza sobre otra

`encima` evita calcular la altura a mano. La toma de la pieza de abajo, así
que sobre un ladrillo sube 3 y sobre una placa sube 1.

```
ladrillo 2x4 en 0,0,0 color verde
ladrillo 2x4 encima color azul          // sobre la pieza anterior
```

Con `llamado` se le pone nombre a una pieza para volver a ella más tarde,
desde cualquier punto del código:

```
ladrillo 2x4 en 0,0,0 color verde llamado base
placa 2x4 en 8,0,0 color rojo
ladrillo 2x4 encima de base color azul  // sobre la base, no sobre la placa
ladrillo 1x1 encima de base desplazado 1,2 color rojo
```

Una torre sale de un `repetir` sin desplazamiento, porque cada vuelta se
apoya en la anterior:

```
ladrillo 2x2 en 0,0,0 color rojo
repetir 4 veces:
    ladrillo 2x2 encima color azul
```

El desplazamiento de un `repetir` **no** se aplica a `encima`: esa pieza va
sobre su referencia y punto. El bucle solo mueve las posiciones escritas
con `en`.

Opciones, todas opcionales y en cualquier orden:

| Opción | Ejemplo | Significado |
|---|---|---|
| `color` | `color rojo` o `color #00AAFF` | Color de la pieza. |
| `rot` / `rotado` | `rot 90` | Giro sobre el eje Z: 0, 90, 180 o 270. |
| `grupo` | `grupo 2` | Número de grupo. |
| `paso` | `paso 5` | Número de paso de montaje. |
| `transparente` | `transparente` | Dibuja la pieza translúcida. |
| `llamado` | `llamado base` | Le da nombre, para usarla luego con `encima de`. |

Colores con nombre: `rojo`, `azul`, `celeste`, `amarillo`, `verde`,
`naranja`, `blanco`, `negro`, `gris`, `marron`, `rosa`, `morado`.

### Meter una pieza por un agujero

Technic no se apila: se inserta. `en el agujero N de <nombre>` mete un pin o
un eje por un agujero de otra pieza, y el motor resuelve el giro y la
posición — igual que `encima` resuelve la altura. Sin esto, colocar un pin
exigía saber que el agujero cae en z=14 LDU y escribir la pieza girada de
cabeza.

```
catalogo "wedo"

3001 en 0,0,0 color naranja llamado base
3701 encima de base color verde llamado verde
2780 en el agujero 1 de verde color negro    // un pin, metido
2780 en el agujero 3 de verde color negro
```

Los agujeros se numeran desde 1, **por posición**: primero x, luego y, luego
z. Se pueden contar mirando el visor. Sin `de <nombre>`, se usa la última
pieza, como en `encima`.

La pieza queda **centrada** en el agujero: un pin asoma lo mismo por las dos
caras, listo para recibir otra viga. `desplazado 0.5` la corre medio módulo
(10 LDU) por la recta del agujero — con signo, para elegir el lado.

El encaje respeta el plástico, y no es simétrico:

| | agujero redondo | agujero de cruz |
|---|---|---|
| **pin** | entra | no entra: la cruz cierra el paso |
| **eje** | pasa, gira libre (ruedas) | pasa, gira solidario (engranajes) |

Un `rot` explícito se respeta si deja la pieza apuntando por el agujero; si
no, el error lo dice y basta quitarlo para que el giro se resuelva solo.

### Encajar sobre un eje

El caso espejo: un engranaje no se mete en nada, es él quien recibe el eje.
`en el eje de <nombre>` encaja la pieza sobre el eje de otra; aquí no hay
número porque un eje es una sola recta, y `desplazado` elige el punto.

```
catalogo "wedo"

// La viga por defecto tiene los agujeros en vertical: se tumba con rot x 90
// y se eleva, porque una rueda más grande que su altura tocaría el suelo.
viga 7 en 0,0,2 rot x 90 color verde llamado chasis

eje 6 en el agujero 2 de chasis llamado transmision
32270 en el eje de transmision desplazado -1.5 color rojo     // 12 dientes
32270 en el eje de transmision desplazado 1.5 color amarillo
10928 en el eje de transmision desplazado 2.5 color gris      // 8 dientes
```

Todo lo del eje gira junto: es un solo grado de libertad, que es lo que hace
transmisión a una transmisión.

Un engranaje tiene un solo agujero, pero una viga tiene siete: para colgarla
de un eje hay que decir por cuál, con `por su agujero N` (numerados en la
pieza sin girar, del extremo hacia dentro). Es lo que convierte una viga en
una **palanca**: la puerta de una barrera es una viga colgada de la bisagra
por su agujero 1.

```
catalogo "wedo"
modelo "Barrera"

21980 en 0,0,0 color blanco llamado motor
eje 6 en el agujero 3 de motor desplazado -2 llamado bisagra
42136 en el eje de bisagra desplazado -1 color gris
viga 7 en el eje de bisagra por su agujero 1 desplazado -2 rot x 90 color rojo
```

El `rot` de la última línea es el grado de libertad de la bisagra: con
`rot x 90` la puerta está subida, con `rot x 90 rot y 270` bajada. El motor
no se anima —el visor enseña la construcción, no la simula—, pero las dos
posturas son el mismo código con un giro de diferencia, que es exactamente
lo que el motor real haría.

**El límite honesto de hoy: los dientes no muerden.** Dos ruedas de 8 en
agujeros vecinos —la distancia exacta a la que engranan en la realidad—
chocan para el motor, porque al engranar los dientes se entrelazan y las
cajas se solapan sin que haya macho y hembra que lo justifique. Hace falta
una regla nueva (dos ejes paralelos a la suma de sus radios primitivos:
1,25 LDU por diente), y es el siguiente trabajo del motor. El engranaje de
24 dientes además no tiene agujero detectable: LDraw lo dibuja sin
primitiva.

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

En el **lenguaje** cuentas como siempre:

- `x`: izquierda/derecha, en studs.
- `y`: adelante/atrás, en studs.
- `z`: altura, en placas. Una placa es `1`; un ladrillo, `3`.
- Se admiten decimales: `0.5` studs es media distancia.
- Los giros son de `0`, `90`, `180` o `270` grados.

### Girar

`rot 90` gira sobre el eje vertical, como siempre. Para los otros dos ejes se
nombra el eje, y varios giros se encadenan:

```
ladrillo 2x4 en 0,0,0 rot 90          // el giro de toda la vida
ladrillo 2x4 en 3,0,0 rot x 90        // de pie
ladrillo 2x4 en 6,0,0 rot x 90 rot z 90
```

Por dentro una orientación es una **matriz de 3×3 de enteros**, igual que en
LDraw. Con ángulos sueltos por eje habría que fijar un orden de aplicación y
una misma orientación tendría varias escrituras; con la matriz cada una de
las **24 orientaciones de un cubo** es única, y componer giros es multiplicar.
Solo hay 90 grados, así que las cuentas son exactas y sin coma flotante.

El visor dibuja la geometría real de LDraw, no cajas, así que una pieza se ve
con sus studs y sus agujeros mire hacia donde mire. Las mallas viven en
`datos/mallas_45300.json` (4,9 MB, 99 piezas) y el servidor manda solo las que
el modelo usa: la casa de ejemplo gasta 45 KB.

Por dentro, el **motor mide en LDU** (1 LDU = 0,4 mm, la unidad de LDraw):

| | LDU | mm |
|---|---|---|
| Stud | 20 | 8 |
| Placa (alto) | 8 | 3,2 |
| Ladrillo (alto) | 24 | 9,6 |
| Módulo Technic | 20 | 8 |
| Medio módulo | 10 | 4 |

**Por qué.** Con `z` en placas enteras, una viga Technic es incolocable: mide
8 mm de alto, o sea 2,5 placas. En LDU todo LEGO cae en enteros. El paso real
de la rejilla Technic es **medio módulo**, no el módulo: la caja de engranajes
6588 tiene agujeros a media distancia, y ninguna de las 97 piezas del set
45300 rompe el paso de 10.

El lenguaje traduce studs y placas a LDU en un solo sitio. Si una posición no
cae exacta —`0.33` studs son 6,6 LDU— se rechaza en vez de redondear: mover
una pieza en silencio sería peor que el error.

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

El proyecto empezó como un remake de BlockCAD, un editor de ladrillos de
sistema. En julio de 2026 giró hacia **LEGO Technic y WeDo 2.0**, lo que
invalidó los pasos 3 a 7 del plan original y obligó a rehacer el motor.

El editor de ladrillos, completo y coherente, quedó etiquetado en
`sistema-v1`: `git checkout sistema-v1` para volver a él.

| Estado | Contenido |
|---|---|
| Hecho | Núcleo: piezas, coordenadas, colisiones, JSON. (`paso-1`) |
| Hecho | Comandos: deshacer, rehacer, transacciones. (`paso-2`) |
| Hecho | Lenguaje textual y editor web con vista 3D. |
| Hecho | Lector de LDraw y catálogo del set 45300: 277 de 280 piezas. |
| Hecho | El motor mide en LDU, que es lo que hace colocable una viga. |
| Hecho | Rotaciones en tres ejes: una pieza apunta a donde haga falta. |
| Hecho | El catálogo del set, cargado en el motor. |
| Hecho | Conexiones y aviso de piezas en el aire. |
| Hecho | Visor con la geometría real de LDraw. |
| Hecho | Pinchar una pieza lleva a su línea; Supr la borra. |
| Hecho | El catálogo sabe qué se mete y qué aloja. |
| Hecho | Insertar no es chocar: el pin entra en el agujero. |
| Hecho | `en el agujero 2 de marco`: insertar sin calcular LDU. |
| **Siguiente** | El camión de reciclaje, con las instrucciones delante. |
| Luego | El camino de vuelta: mover y girar con el ratón. |

### Insertar no es chocar

Era lo que bloqueaba el set entero, y se descubrió intentando construir el
camión de reciclaje del WeDo 2.0: el motor sabía apilar pero no insertar.
Para él una colisión era que dos cajas se solaparan —exactamente lo correcto
para ladrillos de sistema, que se apoyan y se tocan pero nunca se invaden— y
exactamente lo contrario de Technic, donde un pin *ocupa* el agujero y un eje
*atraviesa* la viga. Cada unión Technic de verdad era un error.

La solución tiene tres capas, cada una con su porqué:

- **Cada conexión lleva su recta, no solo su punto.** Un punto no dice si
  algo está insertado: un pin en un agujero son dos rectas que coinciden. La
  dirección estaba en la matriz de cada primitiva de LDraw y el lector la
  tiraba. No vale deducirla de la caja: en el `44865` el pin sale de lado.
- **El solapamiento es legal solo si un macho y un agujero son la misma
  recta.** La excepción es estrecha a propósito: un pin 4 LDU más arriba del
  agujero —mismo pin, misma dirección, misma viga— choca, porque ahí lo que
  hay es plástico. Sin esa estrechez el motor dejaría de saber si un modelo
  se puede construir.
- **El encaje respeta el tipo.** Un eje pasa por el agujero redondo y por el
  de cruz; un pin solo por el redondo. La geometría del pin ante un agujero
  de cruz es la de una inserción perfecta, y aun así no entra.

**El giro a Technic está terminado.** El motor mide en LDU, gira en tres ejes,
conoce las piezas de la caja y sabe qué se sostiene.

### El editor web es la interfaz

Decidido en julio de 2026. **No habrá aplicación de escritorio**: los pasos 6
y 7 del plan original —renderizado propio y PySide6— quedan descartados.
Rehacer en PySide6 un visor 3D que ya funciona solo llevaría al mismo sitio
por más camino.

Eso sube el listón de `blockcad_web/`. Deja de ser una forma de mirar el
modelo para ser **el producto**, así que lo que hoy se le perdona —dibujar
las cajas en vez de la geometría de LDraw— pasa a ser deuda. Esa ya está
saldada.

Lo que no cambia es el principio de siempre: **el motor no sabe que existen
los gráficos**. `blockcad_web` depende de él, nunca al revés. Esa frontera es
lo que permitió cambiar las unidades, los giros y el catálogo enteros sin
tocar el editor.

### La licencia del BlockCAD original

Cerrada como irrelevante. Importaba para leer su formato, y ese paso murió con
el giro a Technic: la geometría viene de LDraw y el inventario de Brickset.
Este proyecto usa GPL-2.0-or-later por sus propios méritos, no «por coherencia
con el autor anterior» como se dijo al principio — el original es freeware, o
sea propietario, así que no había ninguna coherencia que preservar.
