# Patrones de diseño WeDo 2.0

Cómo se diseñan modelos con el set 45300, destilado de dos fuentes: los
mecanismos ya construidos y verificados con el motor de BlockCAD, y las
instrucciones oficiales de cinco prototipos (compuerta, helicóptero, flor,
rover lunar y brazo robótico).

Cada patrón trae su receta en el lenguaje de BlockCAD. Las recetas de la
primera parte están compiladas y verificadas; las de la segunda se irán
verificando al reproducir cada modelo.

## Las tres reglas del solape

Todo el diseño Technic descansa en que el motor de BlockCAD acepta tres
maneras de que dos piezas se pisen, y solo tres:

1. **Inserción**: un macho (pin, punta de eje) y un agujero son la misma
   recta. Un pin 4 LDU más arriba del agujero choca: ahí hay plástico.
2. **Mordida**: dos ruedas dentadas con ejes paralelos separados por la suma
   de sus radios primitivos, a 1,25 LDU por diente.
3. Nada más. Todo otro solape es un choque, y eso es lo que hace que un
   modelo que compila se pueda montar en plástico.

## Vocabulario mínimo

| Se escribe | Pieza | Para qué |
|---|---|---|
| `viga 7` | 32524, 7 agujeros redondos | estructura; mástil si se pone de pie |
| `eje 6` / `eje 3` | 3706 / 4519 | transmitir giro |
| `31493` | ladrillo 1×2 con agujero de CRUZ | la pieza-palanca: el eje la arrastra |
| `2780` | pin con fricción | unir vigas y ladrillos technic |
| `42136` | medio bush | retén: que nada se salga del eje |
| `10928` | rueda de 8 dientes | pareja 8+8 a un módulo |
| `32270` / `18575` | dobles cónicos de 12 y 20 | pareja 12+20 a dos módulos |
| `21980` | motor mediano | su boca es el agujero 3 (cruz) |
| `19071` | hub 6×8 | la batería y el cerebro |

Regla que gobierna todo: **agujero redondo gira libre (ruedas); agujero de
cruz arrastra (palancas y transmisión)**. Colgar una palanca de un agujero
redondo compila y en plástico resbala: el 31493 existe para eso.

## Patrones verificados con el motor

### El mástil

Una viga de pie es una columna de agujeros horizontales cada módulo, para
colgar ejes a distintas alturas.

```
viga 7 en 0,0,0 rot x 90 color verde llamado mastil
eje 6 en el agujero 3 de mastil llamado eje1
```

### La palanca motriz

Giro → vaivén. El eje arrastra la mordaza de cruz y la mordaza lleva el
brazo pisado en sus studs. El giro que queda libre en el brazo es el grado
de libertad de la bisagra.

```
21980 en 0,0,0 color blanco llamado motor
eje 6 en el agujero 3 de motor desplazado -2 llamado bisagra
42136 en el eje de bisagra desplazado -1 color gris
31493 en el eje de bisagra desplazado -2 color verde llamado mordaza
placa 1x6 encima de mordaza desplazado -4,0 rot 90 color verde llamado brazo
```

### La prensa (pinza de manguera)

La palanca motriz, con yunque debajo del brazo: el par del motor se vuelve
fuerza vertical al llegar en horizontal. El yunque acaba en baldosa lisa
para no pellizcar lo que prensa.

### La boca

Dos ruedas engranadas giran en sentidos contrarios: una mandíbula sube
cuando la otra baja. A un módulo (8+8) no caben los brazos —las mordazas de
24 LDU chocan en ejes a 20—, así que las mandíbulas van a dos módulos con la
pareja 12+20 (15+25 = 40 justos).

```
viga 7 en 0,0,0 rot x 90 color verde llamado mastil
eje 6 en el agujero 3 de mastil llamado abajo
eje 6 en el agujero 5 de mastil desplazado -2 llamado arriba
18575 en el eje de abajo desplazado -1.5 color gris
32270 en el eje de arriba desplazado 0.5 color gris
31493 en el eje de abajo desplazado -2.5 color rojo llamado quijada
31493 en el eje de arriba desplazado -0.5 color blanco llamado craneo
placa 1x6 encima de quijada desplazado -4,0 rot 90 color rojo
placa 1x6 encima de craneo desplazado -4,0 rot 90 color blanco
21980 en el eje de abajo por su agujero 3 desplazado 2 color blanco
```

### La torre

Elevar el motor o el hub: pisos de ladrillos 2×4 en filas alternadas,
`repetir N veces desplazando 0,0,3`.

## Lo que enseñan las instrucciones oficiales

Cinco modelos leídos página a página. Primero qué es cada uno —la idea
mecánica en una frase—, después los patrones que se repiten entre ellos.

### Los cinco modelos, en una frase cada uno

- **Compuerta**: piñón de 8 contra corona de 24 **en ángulo recto** — cambio
  de plano y reducción 1:3 en un solo engrane—; el eje vertical gira en
  cojinetes de placa técnica y una manivela rígida de cruz barre el muro
  como una puerta.
- **Flor**: el motor va **vertical, con la salida hacia arriba**; reducción
  8:24 en un mismo plano y un brazo de conectores angulares que hace
  **orbitar** una abeja sobre la flor. La flor no se mueve: es escenografía.
- **Helicóptero**: el motor **no mueve el rotor** (gira libre sobre una
  plataforma giratoria): mueve un **cabrestante** por correa doble en
  diagonal, que iza carga con un hilo. El engranaje de la otra punta del eje
  no engrana con nada: es tope y pomo manual.
- **Rover (Milo)**: toda la transmisión vive en una **caja trasera
  enchufable** (dos vigas unidas por pines); corona de 24 a 90° y ruedas
  dentadas que hacen de engranaje **y** de rueda todoterreno a la vez.
- **Brazo robótico**: correa **con un cuarto de vuelta** (transmite entre
  ejes perpendiculares y además patina si la garra se atasca: embrague de
  seguridad) y **piñón con cremallera** para convertir giro en subir/bajar.

### Patrones transversales (aparecen en dos o más modelos)

| Patrón | Modelos | ¿El motor de BlockCAD lo expresa hoy? |
|---|---|---|
| Cojinete de ladrillo/placa técnica: el eje gira en el agujero redondo | todos | **sí** — es la inserción |
| Redondo gira libre, cruz arrastra: la alternancia en un mismo eje decide qué gira | todos | **sí** — es el tipado de encajes |
| Bushes, discos y medio-casquillos como topes axiales | todos | **sí** — `en el eje de ... desplazado` |
| Electrónica **enjaulada por compresión**, sin pines: cama de placas + puente encima | helicóptero, rover, brazo | **sí** — apilado normal |
| Caja reductora de **dos vigas unidas por pines** | rover, brazo | **sí** — verificado abajo |
| **Eje compuesto**: eje + empalme + eje, para largos que la caja no trae | helicóptero | **sí** — verificado abajo |
| Corona de 24 **a 90°**: cambio de plano + reducción 1:3 | compuerta, rover | **no**: el 24505 no tiene agujero en LDraw y el engrane en ángulo es otra geometría |
| **Correas** con poleas (rectas o con cuarto de vuelta) | helicóptero, brazo | **no**: una goma no tiene forma fija |
| Rotor/carga sobre **plataforma giratoria** (gira libre, desacopla el par) | helicóptero, brazo | a medias: la pieza existe (61485), el giro libre no se modela |
| Acople por **rótulas** (bola contra cavidad) | flor, brazo | **no**: la unión bola-cavidad no está modelada |
| Piñón + **cremallera** (giro → traslación) | brazo | **no**: la cremallera no declara dientes |
| Construir tumbado y montar de canto (o boca abajo y voltear) | flor, brazo | **sí** — cualquier `rot` vale |
| El **cable como pieza**: enrollado de asa, brida o alivio de tensión | flor, rover, helicóptero | no se modela (sin forma fija), y no hace falta |

### Recetas nuevas verificadas

**La caja de dos vigas y pines** (rover): dos vigas técnicas en paralelo,
unidas por pines de fricción. El pin queda mitad en cada una —`desplazado
0.5` lo centra en la juntura— y el motor confirma que une a las dos. Entre
las paredes van los engranajes, protegidos y con el entreeje clavado a
módulos exactos.

```
3702 en 0,0,0 color verde llamado pared1
3702 en 0,1,0 color verde llamado pared2
2780 en el agujero 1 de pared1 desplazado 0.5 color negro
2780 en el agujero 7 de pared1 desplazado 0.5 color negro
```

**El eje compuesto** (helicóptero): eje de 7, empalme liso, eje de 3 — un
eje de ~11 módulos que la caja no trae. El empalme (59443) tiene dos cruces
en la misma recta, así que todo gira solidario.

```
3702 en 0,0,3 color verde llamado soporte
44294 en el agujero 4 de soporte llamado eje_largo
59443 en el eje de eje_largo desplazado -4 color gris llamado empalme
4519 en el agujero 1 de empalme desplazado -1.5 color negro
```

### Lo que estos modelos le piden al motor (por orden de valor)

1. **La corona a 90°** — dos de cinco modelos cambian de plano con ella; es
   EL patrón WeDo de transmisión. Pide dos cosas: darle su agujero al 24505
   (LDraw no ayuda: habría que medirlo a mano) y una regla de engrane en
   ángulo (ejes perpendiculares que se cruzan a la distancia justa).
2. **El giro libre como hecho del modelo** — la plataforma giratoria y las
   ruedas locas existen como piezas, pero el motor no distingue «unido» de
   «unido y girando libre». Es la semilla de la pregunta «¿el giro del motor
   llega hasta aquí?», que estos cinco modelos convierten en la pregunta
   central de cualquier transmisión.
3. **Cremallera** — un solo modelo, pero es la única conversión giro →
   traslación del set.

## Los límites, para no pelearse con ellos

- El **tornillo sin fin** y las parejas cónicas **en ángulo** aún no muerden
  en el motor: otra geometría.
- La **cuerda** y la **cadena** no se pueden representar: no tienen forma
  fija.
- El engranaje de **24 dientes** no tiene agujero detectable en LDraw.
- El visor **no anima**: un mecanismo se enseña en una postura, y las demás
  se escriben cambiando un giro.
