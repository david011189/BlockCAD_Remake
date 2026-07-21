# Los bloques de programación de WeDo 2.0

Resumen de estudio de la guía docente oficial (Caja de herramientas, LEGO
Education 2017), para diseñar la programación por bloques de BlockCAD.
Cada bloque se anota con su pseudocódigo, porque esa es la pista de cómo
debería *escribirse* en un lenguaje de texto.

## Conceptos

- **Cadena de programa**: bloques encadenados que se ejecutan en orden.
  Puede haber varias cadenas en el panel; cada una empieza con un bloque
  de inicio.
- **Secuencia lineal**: un bloque tras otro. **Simultaneidad**: varias
  cadenas corriendo a la vez.
- **Función**: un grupo de bloques con nombre que se usa junto (ej. "la
  función parpadear").
- **Condición**: parte del programa que solo corre si algo ocurre (un
  sensor, un mensaje).
- **Pseudocódigo**: descripción en palabras comunes respetando la
  estructura del programa. WeDo lo usa como puente didáctico — y BlockCAD
  puede usarlo como su sintaxis real.
- **Organigramas**: planificación del flujo antes de programar.

## Bloques de flujo

| Bloque | Pseudocódigo | Nota |
|---|---|---|
| Iniciar | `iniciar programa` | Cabeza obligatoria de toda cadena; se pulsa para ejecutar |
| Iniciar al pulsar tecla | `iniciar con la tecla X` | Cadena que arranca desde el teclado |
| Iniciar al recibir mensaje | `iniciar al recibir "abc"` | Espera su mensaje y arranca |
| Enviar mensaje | `enviar "abc"` | Despierta a todas las cadenas que esperan ese mensaje |
| Esperar | `esperar N` / `esperar <sensor>` | Pausa por tiempo o hasta un cambio de sensor |
| Repetir | `repetir para siempre / N veces / hasta <condición>` | El bucle; los bloques van dentro |

## Bloques de motor

| Bloque | Pseudocódigo |
|---|---|
| Motor en un sentido | `iniciar motor en este sentido` |
| Motor en otro sentido | `iniciar motor en otro sentido` |
| Potencia del motor | `potencia del motor a N` (0–10) |
| Motor durante | `activar motor N segundos` |
| Parar motor | `parar motor` |

## Bloques de luz y sonido

| Bloque | Pseudocódigo |
|---|---|
| Luz | `encender LED en color N` (0–10; 0 apaga, 9 rojo) |
| Reproducir sonido | `reproducir sonido N` (0 = grabado propio) |

## Bloques de pantalla

Mostrar imagen de fondo (por número), mostrar texto o número en el área de
visualización, sumar / restar / multiplicar / dividir el número mostrado,
apagar pantalla, y cambiar el tamaño del área (pequeño / mediano /
pantalla completa).

## Entradas (lo que se enchufa a un bloque)

- **Numérica** y **de texto**: valores directos.
- **Aleatoria**: un número al azar.
- **Sensor de movimiento**: valor 0–10, o sus tres modos de cambio
  (cualquier cambio, más cerca, más lejos).
- **Sensor de inclinación**: valor 0, 3, 5, 7 o 9, o sus modos (un
  sentido, otro sentido, arriba, abajo, sin inclinación, agitar).
- **Sensor de sonido** (micrófono del dispositivo): valor 0–10 o cambio
  de nivel.

## Documentación

El cuadro de texto es un comentario en el panel: no se ejecuta.

## Piezas electrónicas implicadas

- **Hub inteligente** (Bluetooth LE): recibe las cadenas y las ejecuta;
  dos puertos para motor/sensores y un LED de color.
- **Motor mediano**: gira en ambos sentidos con potencia regulable.
- **Sensor de inclinación** y **sensor de movimiento** (distancia).

## Mapa hacia BlockCAD

Lo que esto sugiere para el editor:

1. El modelo ya sabe QUÉ está conectado a qué (inserciones, mordidas,
   acogidas): la cadena motor → eje → gusano → corona → piñón → cremallera
   es un grafo que la física ya conoce. Animar es propagar el giro por ese
   grafo con las relaciones de transmisión (dientes, radios).
2. El pseudocódigo de la guía es casi un lenguaje: `iniciar`, `motor en
   este sentido`, `esperar 2`, `repetir 4 veces:` — la misma filosofía del
   DSL de piezas (español, validado, una línea = una cosa).
3. Los sensores pueden simularse con el ratón/teclado (acercar la mano al
   sensor de movimiento = deslizador; inclinar = girar la pieza).
