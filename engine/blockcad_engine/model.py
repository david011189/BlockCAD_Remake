from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import uuid4

from .errors import (
    CollisionError,
    DuplicateInstanceError,
    InstanceNotFoundError,
)
from .geometry import Bounds3D, Connection, GridPosition, Orientation
from .parts import PartCatalog, PartDefinition, validate_color

#: Nombre de un modelo al que nadie ha puesto uno.
DEFAULT_MODEL_NAME = "Modelo sin título"

#: Cuánto puede desviarse una recta girada de otra para considerarlas la misma.
#: Los giros del motor son de cuartos de vuelta con matrices de enteros, así
#: que una recta cae exacta o cae lejos; el margen es para la aritmética con
#: decimales, no para perdonar piezas mal puestas.
_MARGEN_RECTA = 1e-6


@dataclass(frozen=True, slots=True)
class WorldConnection:
    """Un punto de conexión ya girado y puesto en el mundo."""

    tipo: str
    punto: tuple[int, int, int]
    eje: tuple[float, float, float]

    @property
    def es_macho(self) -> bool:
        return self.tipo in Connection.MACHOS

    @property
    def es_hembra(self) -> bool:
        return self.tipo in Connection.HEMBRAS

    def misma_recta_que(self, otra: "WorldConnection") -> bool:
        """¿Son las dos la misma recta en el espacio?

        Dos rectas son la misma si apuntan igual y además pasan por el mismo
        sitio. Lo segundo es lo que se olvida: dos agujeros paralelos de una
        viga apuntan igual y no son el mismo agujero.
        """
        if not _paralelas(self.eje, otra.eje):
            return False
        # Pasan por el mismo sitio si lo que las separa va en su dirección.
        entre = tuple(a - b for a, b in zip(self.punto, otra.punto))
        return _paralelas(entre, self.eje) or not any(entre)


def _hay_insercion(
    unas: tuple[WorldConnection, ...], otras: tuple[WorldConnection, ...]
) -> bool:
    """¿Hay un macho de un lado metido por un agujero del otro?

    Es la misma pregunta que responde si dos piezas están unidas y si su
    solapamiento es legal, así que vive en un solo sitio: si un pin está
    dentro de una viga, las dos cosas son ciertas a la vez.

    Lo que hace la inserción es que el macho y el agujero sean la MISMA RECTA:
    el pin metido por donde se mete. No basta con que las dos piezas sean de
    las que se insertan, ni con que las rectas sean paralelas: si el pin va por
    otro sitio, es un choque como cualquier otro y hay que decirlo.

    La bola es la excepción que confirma la regla: una rótula no tiene recta
    —girar hacia cualquier lado es su oficio—, así que se asienta cuando su
    centro ES el centro de la cazoleta. Punto, no recta.

    Y el macho tiene que CABER en ese agujero: un eje pasa por el agujero
    redondo, pero un pin no entra en el de cruz.
    """
    return any(
        hembra.tipo in Connection.ENCAJES[macho.tipo]
        and (
            macho.punto == hembra.punto
            if macho.tipo == "bola"
            else macho.misma_recta_que(hembra)
        )
        for a, b in ((unas, otras), (otras, unas))
        for macho in a
        if macho.es_macho
        for hembra in b
        if hembra.es_hembra
    )


#: Radio primitivo de una rueda dentada de LEGO, en LDU por diente. Dos de 8
#: dientes muerden a 20 LDU (un módulo justo), 8 y 24 a 40, 12 y 12 a 30:
#: todas las parejas del sistema salen de esta constante.
_LDU_POR_DIENTE = 1.25


def _muerden(
    a: PlacedPart,
    def_a: PartDefinition,
    b: PlacedPart,
    def_b: PartDefinition,
) -> bool:
    """¿Están estas dos ruedas dentadas engranadas?

    Dos ruedas que muerden se solapan DE VERDAD: los dientes de una entran
    en los huecos de la otra, y las cajas no saben contar eso. Es la tercera
    manera legal de solaparse, junto a la inserción: aquí no hay macho ni
    hembra, hay dos perfiles entrelazados.

    La condición es geométrica y estrecha: ejes paralelos (no la misma
    recta) y separados EXACTAMENTE por la suma de los radios primitivos,
    1,25 LDU por diente. Más cerca los dientes chocan de frente; más lejos
    no se tocan. El tornillo sin fin y las parejas en ángulo quedan fuera:
    muerden con otra geometría, y fingir que esta las cubre sería mentir.
    """
    dientes_a = def_a.metadata.get("dientes")
    dientes_b = def_b.metadata.get("dientes")
    if not dientes_a or not dientes_b:
        return False

    ejes_a = [c for c in a.world_connections(def_a) if c.tipo == "agujero_eje"]
    ejes_b = [c for c in b.world_connections(def_b) if c.tipo == "agujero_eje"]
    if not ejes_a or not ejes_b:
        return False

    eje_a, eje_b = ejes_a[0], ejes_b[0]
    if not _paralelas(eje_a.eje, eje_b.eje) or eje_a.misma_recta_que(eje_b):
        return False

    # Distancia entre las dos rectas paralelas: lo que separa los puntos,
    # quitando la parte que va a lo largo del eje.
    entre = tuple(pa - pb for pa, pb in zip(eje_a.punto, eje_b.punto))
    u = eje_a.eje
    largo_u = sum(v * v for v in u) ** 0.5
    a_lo_largo = sum(e * v for e, v in zip(entre, u)) / largo_u
    distancia = (
        sum(e * e for e in entre) - a_lo_largo * a_lo_largo
    ) ** 0.5

    primitivos = (int(dientes_a) + int(dientes_b)) * _LDU_POR_DIENTE
    return abs(distancia - primitivos) < 1e-6


def _calzan(
    a: PlacedPart,
    def_a: PartDefinition,
    b: PlacedPart,
    def_b: PartDefinition,
) -> bool:
    """¿Es este el neumatico montado en su llanta?

    El neumatico ABRAZA: no tiene conexiones que compartir ni macho que
    meter, y aun asi el montaje real solapa las cajas de verdad. Es la
    cuarta manera legal de solaparse, y la mas estrecha de todas: uno debe
    ser neumatico y el otro llanta, sus centros deben COINCIDIR, y sus
    anchos —la dimension impar de una pieza redonda— deben correr por el
    mismo eje. Un neumatico cruzado no calza aunque este centrado.
    """
    tipos = {def_a.metadata.get("rueda"), def_b.metadata.get("rueda")}
    if tipos != {"neumatico", "llanta"}:
        return False

    eje = _eje_redondo(a, def_a)
    if eje is None or eje != _eje_redondo(b, def_b):
        return False

    ca, cb = a.bounds(def_a), b.bounds(def_b)
    minimos_a = (ca.min_x, ca.min_y, ca.min_z)
    maximos_a = (ca.max_x, ca.max_y, ca.max_z)
    minimos_b = (cb.min_x, cb.min_y, cb.min_z)
    maximos_b = (cb.max_x, cb.max_y, cb.max_z)
    for k in range(3):
        if k == eje:
            # A lo largo del eje de giro basta con que el mas estrecho quede
            # DENTRO del otro: la caja de una llanta es asimetrica (el cubo
            # sobresale) y exigir centros exactos caia en medio LDU.
            dentro = (
                minimos_a[k] >= minimos_b[k] and maximos_a[k] <= maximos_b[k]
            ) or (
                minimos_b[k] >= minimos_a[k] and maximos_b[k] <= maximos_a[k]
            )
            if not dentro:
                return False
        elif minimos_a[k] + maximos_a[k] != minimos_b[k] + maximos_b[k]:
            # En el plano de la rueda, concentricos de verdad.
            return False
    return True


def _eje_redondo(pieza: PlacedPart, definicion: PartDefinition) -> int | None:
    """Por que eje corre el ancho de una pieza redonda: su dimension impar.

    Una rueda mide diametro x diametro x ancho: dos medidas iguales y una
    distinta. La distinta dice hacia donde apunta el eje de giro.
    """
    d = definicion.dimensions.rotated(pieza.orientation)
    medidas = (d.width, d.depth, d.height)
    for i in range(3):
        otras = [medidas[j] for j in range(3) if j != i]
        if otras[0] == otras[1] and medidas[i] != otras[0]:
            return i
    return None


def _recta_canonica(eje: tuple[float, ...]) -> tuple[float, float, float]:
    """La misma recta, siempre escrita igual.

    Una recta no tiene sentido —entrar por un lado o por el otro es la misma
    inserción—, así que (1,0,0) y (-1,0,0) son la misma y deben compararse
    iguales. Se elige el primer componente no nulo positivo.
    """
    valores = [round(float(v), 4) + 0.0 for v in eje]
    for v in valores:
        if abs(v) > _MARGEN_RECTA:
            if v < 0:
                valores = [-x + 0.0 for x in valores]
            break
    return (valores[0], valores[1], valores[2])


def _paralelas(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    """¿Van las dos en la misma dirección? El sentido da igual.

    Se compara con el producto vectorial: es cero cuando son paralelas, y no
    obliga a normalizar nada.
    """
    if not any(a) or not any(b):
        return False
    cruz = (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )
    return all(abs(c) < _MARGEN_RECTA for c in cruz)


@dataclass(frozen=True, slots=True)
class PlacedPart:
    """Instancia concreta colocada en el modelo."""

    instance_id: str
    part_id: str
    position: GridPosition
    orientation: Orientation = Orientation()
    color: str = "#D62828"
    group: int = 0
    step: int = 0
    transparent: bool = False

    @classmethod
    def create(
        cls,
        part_id: str,
        position: GridPosition,
        *,
        orientation: Orientation = Orientation(),
        color: str = "#D62828",
        group: int = 0,
        step: int = 0,
        transparent: bool = False,
        instance_id: str | None = None,
    ) -> "PlacedPart":
        return cls(
            instance_id=instance_id or str(uuid4()),
            part_id=part_id,
            position=position,
            orientation=orientation,
            color=color,
            group=group,
            step=step,
            transparent=transparent,
        )

    def bounds(self, definition: PartDefinition) -> Bounds3D:
        dimensions = definition.dimensions.rotated(self.orientation)
        return Bounds3D.from_position_and_dimensions(self.position, dimensions)

    def world_connections(
        self, definition: PartDefinition
    ) -> tuple["WorldConnection", ...]:
        """Dónde caen sus puntos de conexión, ya girados y colocados.

        Girar mueve la caja fuera de su sitio: un ladrillo de 2x4 girado un
        cuarto de vuelta ocupa donde antes no ocupaba. Como el motor guarda la
        esquina mínima DESPUÉS de girar, hay que reanclar la pieza —y con ella
        sus puntos— para que esa esquina vuelva al origen.

        La recta se gira pero NO se reancla ni se mueve: una dirección no está
        en ningún sitio. Sumarle la posición sería el error clásico, y aquí ni
        siquiera saltaría —daría una recta plausible apuntando a cualquier lado.
        """
        if not definition.connections:
            return ()

        medidas = (
            definition.dimensions.width,
            definition.dimensions.depth,
            definition.dimensions.height,
        )
        # Al girar, cada eje recibe una medida distinta y puede acabar en
        # negativo. Lo que sobresale por debajo de cero es lo que hay que
        # devolver al sitio.
        desplazamiento = tuple(
            -sum(min(0, fila[k] * medidas[k]) for k in range(3))
            for fila in self.orientation.filas
        )

        puntos = []
        for conexion in definition.connections:
            girado = self.orientation.apply(*conexion.punto)
            puntos.append(WorldConnection(
                conexion.tipo,
                (
                    self.position.x + girado[0] + desplazamiento[0],
                    self.position.y + girado[1] + desplazamiento[1],
                    self.position.z + girado[2] + desplazamiento[2],
                ),
                _recta_canonica(self.orientation.apply(*conexion.eje)),
            ))
        return tuple(puntos)


class BlockModel:
    """Documento principal que contiene todas las piezas colocadas."""

    def __init__(
        self,
        catalog: PartCatalog | None = None,
        *,
        name: str = DEFAULT_MODEL_NAME,
    ) -> None:
        self.catalog = catalog or PartCatalog.with_basic_parts()
        self.name = name
        self._instances: dict[str, PlacedPart] = {}

    @property
    def instances(self) -> tuple[PlacedPart, ...]:
        return tuple(self._instances.values())

    def get(self, instance_id: str) -> PlacedPart:
        try:
            return self._instances[instance_id]
        except KeyError as exc:
            raise InstanceNotFoundError(
                f"No existe la instancia {instance_id!r}."
            ) from exc

    def index_of(self, instance_id: str) -> int:
        """Posición de la instancia dentro del orden de inserción."""
        for index, key in enumerate(self._instances):
            if key == instance_id:
                return index
        raise InstanceNotFoundError(f"No existe la instancia {instance_id!r}.")

    def add(
        self,
        part_id: str,
        position: GridPosition,
        *,
        orientation: Orientation = Orientation(),
        color: str | None = None,
        group: int = 0,
        step: int = 0,
        transparent: bool = False,
        instance_id: str | None = None,
        check_collision: bool = True,
    ) -> PlacedPart:
        definition = self.catalog.get(part_id)
        candidate = PlacedPart.create(
            part_id=part_id,
            position=position,
            orientation=orientation,
            color=color or definition.default_color,
            group=group,
            step=step,
            transparent=transparent,
            instance_id=instance_id,
        )
        self.add_instance(candidate, check_collision=check_collision)
        return candidate

    def add_instance(
        self,
        instance: PlacedPart,
        *,
        check_collision: bool = True,
    ) -> None:
        self.insert_instance(instance, check_collision=check_collision)

    def insert_instance(
        self,
        instance: PlacedPart,
        *,
        index: int | None = None,
        check_collision: bool = True,
    ) -> None:
        """Añade una instancia y, opcionalmente, la sitúa en un índice concreto.

        El índice permite que deshacer una eliminación devuelva la pieza a su
        lugar original dentro del orden de inserción.
        """
        if instance.instance_id in self._instances:
            raise DuplicateInstanceError(
                f"La instancia {instance.instance_id!r} ya existe."
            )

        self.catalog.get(instance.part_id)
        self._validate_instance(instance, check_collision=check_collision)

        if index is None or index >= len(self._instances):
            self._instances[instance.instance_id] = instance
            return

        if index < 0:
            raise ValueError("El índice no puede ser negativo.")

        items = list(self._instances.items())
        items.insert(index, (instance.instance_id, instance))
        self._instances = dict(items)

    def remove(self, instance_id: str) -> PlacedPart:
        try:
            return self._instances.pop(instance_id)
        except KeyError as exc:
            raise InstanceNotFoundError(
                f"No existe la instancia {instance_id!r}."
            ) from exc

    def move(
        self,
        instance_id: str,
        new_position: GridPosition,
        *,
        check_collision: bool = True,
    ) -> PlacedPart:
        current = self.get(instance_id)
        candidate = replace(current, position=new_position)
        self._validate_instance(
            candidate,
            ignore_instance_id=instance_id,
            check_collision=check_collision,
        )
        self._instances[instance_id] = candidate
        return candidate

    def translate(
        self,
        instance_id: str,
        dx: int = 0,
        dy: int = 0,
        dz: int = 0,
        *,
        check_collision: bool = True,
    ) -> PlacedPart:
        current = self.get(instance_id)
        return self.move(
            instance_id,
            current.position.translated(dx, dy, dz),
            check_collision=check_collision,
        )

    def set_orientation(
        self,
        instance_id: str,
        orientation: Orientation,
        *,
        check_collision: bool = True,
    ) -> PlacedPart:
        """Fija la orientación absoluta de una pieza."""
        current = self.get(instance_id)
        candidate = replace(current, orientation=orientation)
        self._validate_instance(
            candidate,
            ignore_instance_id=instance_id,
            check_collision=check_collision,
        )
        self._instances[instance_id] = candidate
        return candidate

    def rotate(
        self,
        instance_id: str,
        eje: str,
        grados: int,
        *,
        check_collision: bool = True,
    ) -> PlacedPart:
        """Gira una pieza sobre un eje, encadenando el giro al que ya tenía."""
        current = self.get(instance_id)
        return self.set_orientation(
            instance_id,
            Orientation.around(eje, grados).then(current.orientation),
            check_collision=check_collision,
        )

    def rotate_clockwise(
        self,
        instance_id: str,
        *,
        check_collision: bool = True,
    ) -> PlacedPart:
        """Gira 90 grados sobre el eje vertical: el giro de toda la vida."""
        return self.rotate(instance_id, "z", 90, check_collision=check_collision)

    def recolor(self, instance_id: str, color: str) -> PlacedPart:
        normalized = validate_color(color)
        current = self.get(instance_id)
        updated = replace(current, color=normalized)
        self._instances[instance_id] = updated
        return updated

    def collisions_for(
        self,
        candidate: PlacedPart,
        *,
        ignore_instance_id: str | None = None,
    ) -> tuple[PlacedPart, ...]:
        definition = self.catalog.get(candidate.part_id)
        candidate_bounds = candidate.bounds(definition)
        collisions: list[PlacedPart] = []

        for existing in self._instances.values():
            if existing.instance_id == ignore_instance_id:
                continue
            existing_definition = self.catalog.get(existing.part_id)
            if not candidate_bounds.intersects(existing.bounds(existing_definition)):
                continue
            # Que dos cajas se solapen es un choque para ladrillos de sistema,
            # que se apoyan y se tocan pero nunca se invaden. Technic es lo
            # contrario: se construye metiendo cosas dentro de otras, y un pin
            # OCUPA el agujero. Sin esta excepción, cada unión Technic de
            # verdad sería un error y el set entero resultaría imposible.
            if _hay_insercion(
                candidate.world_connections(definition),
                existing.world_connections(existing_definition),
            ):
                continue
            # Dos ruedas dentadas engranadas también se solapan de verdad:
            # los dientes de una entran en los huecos de la otra.
            if _muerden(candidate, definition, existing, existing_definition):
                continue
            # Y el neumatico abraza a su llanta.
            if _calzan(candidate, definition, existing, existing_definition):
                continue
            collisions.append(existing)

        return tuple(collisions)


    def connected_to(self, instance_id: str) -> tuple[PlacedPart, ...]:
        """Piezas unidas a esta.

        Dos piezas se unen de dos maneras distintas, y hacen falta las dos:

        - **Compartiendo un punto.** Un agujero aparece en las dos caras de la
          pieza, así que dos vigas pegadas comparten los puntos de la cara que
          se tocan. Es lo que permite saber que están unidas sin modelar el pin.
        - **Insertándose.** Un pin metido en un agujero casi nunca cae sobre el
          punto del agujero: entra por él y se queda a otra profundidad. Lo que
          comparten es la RECTA, no el punto. Con la regla anterior, un pin
          podía estar dentro de una viga y el motor los daba por desconocidos.
        """
        pieza = self.get(instance_id)
        definicion = self.catalog.get(pieza.part_id)
        mias = pieza.world_connections(definicion)
        if not mias and not definicion.metadata.get('rueda'):
            # Sin conexiones no hay nada que compartir... salvo que la pieza
            # sea neumatico o llanta: esas se unen abrazando.
            return ()

        puntos = {c.punto for c in mias}
        unidas = []
        for otra in self._instances.values():
            if otra.instance_id == instance_id:
                continue
            suyas = otra.world_connections(self.catalog.get(otra.part_id))
            comparten_punto = puntos & {c.punto for c in suyas}
            if (
                comparten_punto
                or _hay_insercion(mias, suyas)
                or _calzan(
                    pieza,
                    self.catalog.get(pieza.part_id),
                    otra,
                    self.catalog.get(otra.part_id),
                )
            ):
                unidas.append(otra)
        return tuple(unidas)

    def resting_on(self, instance_id: str) -> tuple[PlacedPart, ...]:
        """Piezas sobre las que esta se apoya: las que tiene justo debajo.

        Hace falta además de `connected_to` porque un ladrillo no tiene puntos
        en su base: sus studs están arriba, y el de encima no aporta nada por
        abajo. Entre ladrillos, lo que hay es apoyo, no puntos compartidos.
        """
        pieza = self.get(instance_id)
        caja = pieza.bounds(self.catalog.get(pieza.part_id))

        debajo = []
        for otra in self._instances.values():
            if otra.instance_id == instance_id:
                continue
            suya = otra.bounds(self.catalog.get(otra.part_id))
            if suya.max_z != caja.min_z:
                continue
            # Que se toquen de canto no sostiene nada: las plantas tienen que
            # solaparse de verdad.
            if (
                suya.min_x < caja.max_x
                and suya.max_x > caja.min_x
                and suya.min_y < caja.max_y
                and suya.max_y > caja.min_y
            ):
                debajo.append(otra)
        return tuple(debajo)

    def is_supported(self, instance_id: str) -> bool:
        """Si la pieza se apoya en el suelo, en otra pieza, o va unida a alguna."""
        pieza = self.get(instance_id)
        if pieza.position.z == 0:
            return True
        return bool(self.resting_on(instance_id)) or bool(
            self.connected_to(instance_id)
        )

    def floating(self) -> tuple[PlacedPart, ...]:
        """Las piezas que se quedan en el aire.

        No es un error: el BlockCAD original permitía piezas flotantes y aquí
        también. Es un aviso, para que quien construye sepa lo que hay.
        """
        return tuple(
            pieza
            for pieza in self._instances.values()
            if not self.is_supported(pieza.instance_id)
        )

    def _validate_instance(
        self,
        candidate: PlacedPart,
        *,
        ignore_instance_id: str | None = None,
        check_collision: bool,
    ) -> None:
        # `GridPosition` ya garantiza z >= 0, así que aquí no hace falta
        # volver a comprobarlo.
        if check_collision:
            collisions = self.collisions_for(
                candidate,
                ignore_instance_id=ignore_instance_id,
            )
            if collisions:
                ids = ", ".join(item.instance_id for item in collisions)
                raise CollisionError(
                    f"La pieza colisiona con las instancias: {ids}."
                )
