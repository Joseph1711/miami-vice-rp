"""Catalogos oficiales que la administracion puede sembrar en su servidor.

Solo datos: ni SQL ni Discord. `bot.services.business` usa estas listas para
insertar lo que falte y `bot.cogs.jobs` / `bot.cogs.companies` las exponen
mediante comandos de administracion idempotentes.

Todos los valores de aqui son *puntos de partida*. El admin puede cambiar el
sueldo, el precio y el resto con `/empleos sueldo`, `/empleos editar` o
`/empresa negocio estado`, y la siembra nunca pisa una fila ya existente.
"""

# Identificador de la ciudad como duena. No es un ciudadano de Discord: es la
# contraparte que recibe el importe de la venta en las arcas municipales.
CITY_OWNER_ID = "city"

# ---------------------------------------------------------------------------
# EMPLEOS PUBLICOS PREDETERMINADOS
# ---------------------------------------------------------------------------
# `salary` es el sueldo DIARIO que sale de la Tesoreria Municipal. Los puestos
# mas especializados pagan mas porque la ciudad asume mas formacion.
# `max_workers` en 0 significa plazas ilimitadas.
DEFAULT_JOBS = [
    {
        "name": "Postal",
        "salary": 180,
        "emoji": "\U0001F4EB",
        "description": "Reparto de correspondencia y paquetes por la ciudad.",
        "max_workers": 0,
    },
    {
        "name": "Hospital",
        "salary": 420,
        "emoji": "\U0001F3E5",
        "description": "Sanidad, urgencias y mantenimiento de las salas.",
        "max_workers": 0,
    },
    {
        "name": "Granjero",
        "salary": 200,
        "emoji": "\U0001F33E",
        "description": "Cuidado de ganado, cultivos y venta de producto agricola.",
        "max_workers": 0,
    },
    {
        "name": "Gasolinera",
        "salary": 190,
        "emoji": "\U0001F6E2",
        "description": "Repostaje, tienda de servicio y atencion al cliente.",
        "max_workers": 0,
    },
    {
        "name": "Noticias",
        "salary": 260,
        "emoji": "\U0001F4F0",
        "description": "Periodismo de calle, reportajes y cobertura de incidentes.",
        "max_workers": 0,
    },
    {
        "name": "Taxi y Bus",
        "salary": 210,
        "emoji": "\U0001F697",
        "description": "Transporte de ciudadanos por la ciudad y las islas.",
        "max_workers": 0,
    },
    {
        "name": "Recoleccion de Basura",
        "salary": 170,
        "emoji": "\U0001F6D5",
        "description": "Recogida de residuos, limpieza viaria y contenedores.",
        "max_workers": 0,
    },
    {
        "name": "Deposito de Combustible",
        "salary": 220,
        "emoji": "\U0001F6FD",
        "description": "Almacen y distribucion de combustible para las gasolineras.",
        "max_workers": 0,
    },
    {
        "name": "Cine",
        "salary": 160,
        "emoji": "\U0001F3A6",
        "description": "Cartelera, proyeccion y atencion en salas de cine.",
        "max_workers": 0,
    },
    {
        "name": "Gadget Shack",
        "salary": 230,
        "emoji": "\U0001F4F1",
        "description": "Venta y reparacion de electronica, moviles y accesorios.",
        "max_workers": 0,
    },
]

# ---------------------------------------------------------------------------
# EMPRESAS PRIVADAS EN VENTA (PROPIEDAD DE LA CIUDAD)
# ---------------------------------------------------------------------------
# La ciudad las ofrece con este precio. Quien las compra recibe el negocio con
# su nombre, sector y ubicacion; el importe NO entra en la caja del negocio, va
# a las arcas municipales.
CITY_COMPANIES = [
    {
        "name": "Restaurante de Comida Rapida",
        "category": "Restaurante",
        "location": "Little Havana",
        "emoji": "\U0001F35F",
        "price": 18000,
        "description": "Comida rapida para llevar y servicio en mostrador.",
    },
    {
        "name": "Barberia",
        "category": "Servicios",
        "location": "Little Havana",
        "emoji": "\U0001F488",
        "price": 12000,
        "description": "Corte de pelo, barba y cuidados de imagen.",
    },
    {
        "name": "Liberty Cafe",
        "category": "Restaurante",
        "location": "Ocean Drive",
        "emoji": "☕",
        "price": 26000,
        "description": "Cafeteria de especialidad con reposteria propia.",
    },
    {
        "name": "Rick & John's",
        "category": "Restaurante",
        "location": "Vice City Beach",
        "emoji": "\U0001F37A",
        "price": 32000,
        "description": "Taberna con cocina completa y ambiente nocturno.",
    },
    {
        "name": "Pasteleria",
        "category": "Restaurante",
        "location": "Coral Way",
        "emoji": "\U0001F370",
        "price": 14000,
        "description": "Panaderia y pastelería artisan, con reparto a domicilio.",
    },
    {
        "name": "La Mesa",
        "category": "Restaurante",
        "location": "Downtown",
        "emoji": "\U0001F37D",
        "price": 38000,
        "description": "Restaurante de alta cocina con reservas y eventos.",
    },
    {
        "name": "Gadget Shack",
        "category": "Comercio",
        "location": "Downtown",
        "emoji": "\U0001F4F1",
        "price": 21000,
        "description": "Tienda de electronica, moviles y accesorios.",
    },
    {
        "name": "Royal Scoop",
        "category": "Comercio",
        "location": "North Point",
        "emoji": "\U0001F369",
        "price": 9000,
        "description": "Heladeria y productos de temporada, con reparto a domicilio.",
    },
    {
        "name": "Taco Bout",
        "category": "Restaurante",
        "location": "Little Havana",
        "emoji": "\U0001F32E",
        "price": 16000,
        "description": "Puesto de tacos y comida mexicana callejera.",
    },
    {
        "name": "Pancake House",
        "category": "Restaurante",
        "location": "Sunset Harbour",
        "emoji": "\U0001F95E",
        "price": 19000,
        "description": "Desayuno, brunch y una amplia carta de pancakes y tortitas.",
    },
    {
        "name": "Rising Blakes",
        "category": "Comercio",
        "location": "Wynwood",
        "emoji": "\U0001F4F6",
        "price": 15000,
        "description": "Libros, revista y material de segunda mano.",
    },
    {
        "name": "Sub Station",
        "category": "Restaurante",
        "location": "Sunset Harbour",
        "emoji": "\U0001F96A",
        "price": 17000,
        "description": "Sanguches y menu rapido para llevar.",
    },
    {
        "name": "Sammy's Pizzeria",
        "category": "Restaurante",
        "location": "Little Havana",
        "emoji": "\U0001F355",
        "price": 22000,
        "description": "Pizzeria con horno de piedra y reparto a domicilio.",
    },
]
