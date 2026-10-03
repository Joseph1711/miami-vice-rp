"""Catalogo publico de Miami Systems.

Se publica cuando un ciudadano menciona al bot y escribe `comandos` despues de
la mencion. El texto es largo a proposito (es el manual de referencia del
servidor), asi que se reparte en varios embeds en vez de intentar colarlo en
uno solo: Discord limita cada descripcion a 4096 caracteres y cada mensaje a 10
embeds.
"""

import re

import discord

from bot.embeds import COLOR_INFO

# Discord: descripcion <= 4096, titulo <= 256, 10 embeds por mensaje.
EMBED_DESCRIPTION_LIMIT = 3800
EMBEDS_PER_MESSAGE = 10

CATALOG_FOOTER = "Miami Systems • Official Community Management System"
TRIGGER_WORD = r"comandos"

# Cada bloque es (titulo del embed, cuerpo). El primero de cada grupo se usa
# como titulo y el resto se antepone en negrita dentro de la misma descripcion.
CATALOG_SECTIONS = [
    (
        "\U0001F1FA\U0001F1F8 MIAMI SYSTEMS",
        "**Sistema oficial de gesti\u00f3n de la comunidad**\n\n"
        "> \U0001F916 **\u00a1Hola, comunidad!**\n"
        ">\n"
        "> Soy **Miami Systems**, el sistema encargado de gestionar y conectar gran parte "
        "de las funciones de nuestra comunidad.\n"
        ">\n"
        "> A trav\u00e9s de mis comandos podr\u00e1s administrar tu **identidad, personajes, "
        "econom\u00eda, veh\u00edculos, propiedades, empleos, empresas, departamentos, armas, "
        "justicia, emergencias y mucho m\u00e1s**.\n"
        ">\n"
        "> Mi objetivo es hacer que la experiencia de rol sea m\u00e1s organizada, realista y "
        "sencilla para todos.",
    ),
    (
        "\U0001FAAA IDENTIDAD Y PERSONAJES",
        "Puedes crear y administrar tus propios ciudadanos mediante el sistema de DNI.\n\n"
        "`/dni crear` \u2014 Crea un nuevo personaje utilizando tu avatar de Roblox.\n"
        "`/dni solicitar` \u2014 Acceso alternativo para crear tu DNI.\n"
        "`/dni mis_personajes` \u2014 Consulta y administra tus personajes.\n"
        "`/dni ver` \u2014 Consulta una ficha ciudadana.\n"
        "`/dni buscar` \u2014 Busca ciudadanos mediante su n\u00famero de DNI.\n"
        "`/dni revocar` \u2014 Revocaci\u00f3n o suspensi\u00f3n de DNI para personal autorizado.\n\n"
        "\U0001F464 **Puedes tener hasta 5 personajes por usuario.**",
    ),
    (
        "\U0001F3AE CONEXI\u00d3N CON ROBLOX",
        "Tambi\u00e9n puedo conectar tu cuenta de Discord con Roblox.\n\n"
        "`/roblox vincular`\n"
        "`/roblox perfil`\n"
        "`/roblox desvincular`\n\n"
        "Con `/roblox perfil` podr\u00e1s consultar una tarjeta con el **avatar 3D y "
        "estad\u00edsticas** del usuario.",
    ),
    (
        "\U0001F4B5 ECONOM\u00cdA",
        "La econom\u00eda de Miami Systems permite administrar tu dinero de forma completamente "
        "integrada.\n\n"
        "`/balance` \u2014 Consulta tu efectivo y banco.\n"
        "`/sueldo` / `/salario` \u2014 Cobra tu salario.\n"
        "`/pagar` \u2014 Env\u00eda dinero a otro ciudadano.\n"
        "`/donar` \u2014 Realiza donaciones.\n"
        "`/diario` \u2014 Recompensa diaria.\n"
        "`/semanal` \u2014 Recompensa semanal.\n"
        "`/tabla` \u2014 Rankings econ\u00f3micos, de nivel o reputaci\u00f3n.\n"
        "`/nivel` \u2014 Consulta tu nivel.",
    ),
    (
        "\U0001F3E6 BANCO E INVERSIONES",
        "\u00bfQuieres administrar tus finanzas?\n\n"
        "`/banco info`\n"
        "`/banco depositar`\n"
        "`/banco retirar`\n"
        "`/banco ahorros`\n"
        "`/banco prestamo`\n"
        "`/banco pagar`\n\n"
        "Tambi\u00e9n puedes invertir mediante:\n\n"
        "`/invertir crear`\n"
        "`/invertir portafolio`\n\n"
        "\U0001F4B0 **Los ahorros generan un 2% diario.**",
    ),
    (
        "\U0001F6D2 TIENDAS Y MERCADOS",
        "Puedes comprar, vender e intercambiar diferentes objetos.\n\n"
        "**\U0001F3EA Tienda**\n"
        "`/tienda explorar`\n"
        "`/tienda comprar`\n"
        "`/tienda info`\n\n"
        "**\U0001F576\uFE0F Mercado negro**\n"
        "`/mercadonegro explorar`\n"
        "`/mercadonegro comprar`\n\n"
        "**\U0001F6CD\uFE0F Mercado ciudadano**\n"
        "`/mercado lista`\n"
        "`/mercado vender`\n"
        "`/mercado comprar`\n"
        "`/mercado pujar`\n"
        "`/mercado cancelar`\n\n"
        "Tambi\u00e9n puedes administrar tus objetos mediante:\n\n"
        "`/inventario`",
    ),
    (
        "\U0001F52B ARMAS",
        "Miami Systems mantiene un registro individual de las armas.\n\n"
        "`/arma registrar`\n"
        "`/arma mis_armas`\n"
        "`/arma ver`\n"
        "`/arma transferir`\n"
        "`/arma incautar`\n\n"
        "\U0001F50E Cada arma registrada posee una **serie bal\u00edstica \u00fanica**.",
    ),
    (
        "\U0001F697 VEH\u00cdCULOS",
        "Registra y administra tus veh\u00edculos directamente desde Discord.\n\n"
        "`/vehiculo registrar`\n"
        "`/vehiculo mis_vehiculos`\n"
        "`/vehiculo ver`\n"
        "`/vehiculo buscar`\n"
        "`/vehiculo transferir`\n"
        "`/vehiculo reportar`\n"
        "`/vehiculo liberar`\n"
        "`/vehiculo incautar`\n\n"
        "\U0001F698 El sistema admite veh\u00edculos convencionales, **trailers y ATVs**, "
        "incluyendo placas personalizadas.",
    ),
    (
        "\U0001F3DB\uFE0F DEPARTAMENTOS Y FLOTAS",
        "Los departamentos pueden administrar sus miembros, presupuesto y veh\u00edculos "
        "oficiales.\n\n"
        "`/departamento lista`\n"
        "`/departamento info`\n"
        "`/departamento presupuesto`\n"
        "`/departamento miembros`\n"
        "`/departamento unirse`\n"
        "`/departamento mis_postulaciones`\n\n"
        "**\U0001F693 Flota**\n"
        "`/flota ver`\n"
        "`/flota catalogo`\n"
        "`/flota solicitar`\n"
        "`/flota devolver`\n"
        "`/flota reparar`\n\n"
        "Los mandos autorizados tambi\u00e9n cuentan con herramientas para **gestionar personal, "
        "veh\u00edculos y recursos departamentales**.",
    ),
    (
        "\U0001F4BC EMPLEOS P\u00daBLICOS",
        "Consulta y administra tus empleos:\n\n"
        "`/empleos listar`\n"
        "`/empleos mios`\n"
        "`/empleos entrar`\n"
        "`/empleos renunciar`\n\n"
        "Los administradores disponen de herramientas adicionales para crear y administrar "
        "empleos.",
    ),
    (
        "\U0001F3E2 EMPRESAS",
        "\u00bfQuieres tener tu propio negocio?\n\n"
        "Con Miami Systems puedes crear una empresa y administrar pr\u00e1cticamente todos sus "
        "aspectos:\n\n"
        "**Empresa**\n"
        "`/empresa crear`\n"
        "`/empresa mi_empresa`\n"
        "`/empresa panel`\n"
        "`/empresa info`\n"
        "`/empresa disolver`\n\n"
        "**Finanzas**\n"
        "`/empresa caja`\n"
        "`/empresa nomina`\n"
        "`/empresa dinero`\n\n"
        "**Personal**\n"
        "`/empresa plantilla`\n\n"
        "**Productos y servicios**\n"
        "`/empresa menu`\n"
        "`/empresa catalogo`\n\n"
        "**Acciones**\n"
        "`/empresa sociedad`\n\n"
        "**Negocio**\n"
        "`/empresa negocio`\n\n"
        "\U0001F4C8 podr\u00e1s contratar empleados, administrar n\u00f3minas, manejar las "
        "finanzas, vender productos, ofrecer servicios e incluso gestionar acciones de tu "
        "empresa.",
    ),
    (
        "\U0001F3E0 PROPIEDADES",
        "Tambi\u00e9n puedo ayudarte a administrar tus propiedades.\n\n"
        "`/propiedad lista`\n"
        "`/propiedad comprar`\n"
        "`/propiedad rentar`\n"
        "`/propiedad mias`\n"
        "`/propiedad vender`\n\n"
        "\U0001F3E1 Al vender una propiedad recibir\u00e1s el **75% de su valor**.",
    ),
    (
        "\U0001F46E POLIC\u00cdA Y JUSTICIA",
        "Las autoridades cuentan con herramientas especiales para administrar el sistema "
        "policial y judicial.\n\n"
        "`/policia arrestar`\n"
        "`/policia multar`\n"
        "`/policia antecedentes`\n"
        "`/policia mis_multas`\n"
        "`/policia pagar_multa`\n"
        "`/policia pagar_fianza`\n\n"
        "\U0001F510 **Estos comandos est\u00e1n restringidos al personal autorizado.**",
    ),
    (
        "\U0001F6A8 B.O.L.O. Y EXPEDIENTES",
        "La investigaci\u00f3n policial tambi\u00e9n forma parte de Miami Systems.\n\n"
        "**\U0001F50E B.O.L.O.**\n"
        "`/bolo emitir`\n"
        "`/bolo lista`\n"
        "`/bolo ver`\n"
        "`/bolo actualizar`\n"
        "`/bolo borrar`\n\n"
        "**\U0001F4C1 Expedientes**\n"
        "`/caso abrir`\n"
        "`/caso lista`\n"
        "`/caso ver`\n"
        "`/caso nota_agregar`\n"
        "`/caso sospechoso_vincular`\n"
        "`/caso evidencia_vincular`\n"
        "`/caso estado`\n\n"
        "\U0001F510 Las funciones de gesti\u00f3n de expedientes est\u00e1n reservadas para "
        "**STAFF, JUECES y DETECTIVES autorizados**.",
    ),
    (
        "\U0001F4DE CENTRAL 911",
        "\u00bfExiste una emergencia?\n\n"
        "El sistema 911 permite crear y gestionar incidentes:\n\n"
        "`/incidente crear`\n"
        "`/incidente lista`\n"
        "`/incidente ver`\n"
        "`/incidente atender`\n"
        "`/incidente cerrar`\n\n"
        "\U0001F694\U0001F691 **Polic\u00eda y EMS pueden responder a los incidentes "
        "correspondientes.**",
    ),
    (
        "\U0001F575\uFE0F ACTIVIDADES CRIMINALES",
        "Dentro del sistema de rol tambi\u00e9n existen actividades criminales:\n\n"
        "`/drogas sembrar`\n"
        "`/drogas cosechar`\n"
        "`/drogas info`\n"
        "`/lavar dinero`\n"
        "`/lavar info`\n"
        "`/misiones`\n\n"
        "\u26A0\uFE0F **Estas funciones representan exclusivamente actividades dentro del "
        "sistema de rol.**",
    ),
    (
        "\U0001F4BC TRABAJOS SECUNDARIOS",
        "Tambi\u00e9n puedes realizar trabajos adicionales:\n\n"
        "`/trabajar`\n"
        "`/trabajo mis_trabajos`\n\n"
        "El personal autorizado puede gestionar las evidencias mediante:\n\n"
        "`/trabajo pendientes`\n"
        "`/trabajo aprobar`\n"
        "`/trabajo rechazar`",
    ),
    (
        "\u2B50 REPUTACI\u00d3N",
        "Tu comportamiento dentro de la comunidad tambi\u00e9n puede reflejarse en tu "
        "reputaci\u00f3n.\n\n"
        "`/reputacion perfil`\n"
        "`/reputacion dar`",
    ),
    (
        "\U0001F3AB TICKETS Y VERIFICACI\u00d3N",
        "**\U0001F3AB Tickets**\n"
        "`/ticket abrir`\n"
        "`/ticket cerrar`\n\n"
        "El personal administrativo dispone adem\u00e1s del panel y configuraci\u00f3n del "
        "sistema.\n\n"
        "**\u2705 Verificaci\u00f3n**\n"
        "`/verificar estado`\n"
        "`/verificar panel`\n"
        "`/verificar configurar`\n"
        "`/verificar agregar_rol`\n"
        "`/verificar remover_rol`\n"
        "`/verificar ver_config`\n"
        "`/verificar revocar`",
    ),
    (
        "\U0001F4D6 \u00bfNO SABES QU\u00c9 COMANDO UTILIZAR?",
        "No te preocupes.\n\n"
        "Puedes utilizar:\n\n"
        "**`/help`**\n\n"
        "o\n\n"
        "**`/ayuda`**\n\n"
        "\U0001F4DA Encontrar\u00e1s un **manual interactivo organizado por categor\u00edas**, "
        "donde podr\u00e1s consultar los comandos disponibles y aprender c\u00f3mo utilizar cada "
        "sistema.",
    ),
    (
        "\U0001F1FA\U0001F1F8 MIAMI SYSTEMS",
        "> **Un solo sistema. Toda una comunidad.**\n"
        ">\n"
        "> \U0001FAAA Identidad\n"
        "> \U0001F4B5 Econom\u00eda\n"
        "> \U0001F3E6 Banca\n"
        "> \U0001F697 Veh\u00edculos\n"
        "> \U0001F3E0 Propiedades\n"
        "> \U0001F46E Polic\u00eda\n"
        "> \U0001F691 Emergencias\n"
        "> \U0001F3E2 Empresas\n"
        "> \U0001F3DB\uFE0F Departamentos\n"
        "> \u2696\uFE0F Justicia\n"
        "> \u2B50 Reputaci\u00f3n\n"
        "> \U0001F3AB Comunidad\n"
        ">\n"
        "> **Todo administrado desde un mismo lugar.**\n"
        ">\n"
        "> \u2014 **Miami Systems**\n"
        "> *Official Community Management System*",
    ),
]


def mention_pattern(bot_user_id: int) -> re.Pattern:
    """Encuentra la mencion al bot admitiendo `<@id>` y `<@!id>` (el nick legacy)."""
    return re.compile(rf"<@!?{bot_user_id}>")


def wants_catalog(content: str, bot_user_id: int) -> bool:
    """True si el mensaje menciona al bot y despues de la mencion dice `comandos`.

    Exige el orden menciona -> "comandos": un "comandos" suelto antes del ping no
    cuenta, para no responder a cualquier frase que Mention la palabra.
    """
    mention = mention_pattern(bot_user_id).search(content)
    if not mention:
        return False
    after = content[mention.end():]
    return re.search(rf"\b{TRIGGER_WORD}\b", after, re.IGNORECASE) is not None


def _group_sections() -> list[list[tuple[str, str]]]:
    """Agrupa bloques mientras quepan en la descripcion de un embed."""
    groups: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    budget = 0

    for title, body in CATALOG_SECTIONS:
        # +8 del separador y del encabezado en negrita de los bloques siguientes.
        cost = len(title) + len(body) + 8
        if current and budget + cost > EMBED_DESCRIPTION_LIMIT:
            groups.append(current)
            current = []
            budget = 0
        current.append((title, body))
        budget += cost

    if current:
        groups.append(current)
    return groups


def build_catalog_embeds() -> list[discord.Embed]:
    """Un embed por grupo de secciones, respetando los limites de Discord."""
    groups = _group_sections()
    total = len(groups)
    embeds = []
    for index, group in enumerate(groups, 1):
        title, body = group[0]
        description = body
        for extra_title, extra_body in group[1:]:
            description += f"\n\n**{extra_title}**\n{extra_body}"

        # El contenido no cabe en un solo embed, asi que se numera para que se
        # lea como una serie y no como dos mensajes sin relacion.
        if total > 1:
            title = f"{title}  ({index}/{total})"

        embed = discord.Embed(
            title=title,
            description=description[:EMBED_DESCRIPTION_LIMIT],
            color=COLOR_INFO,
        )
        embed.set_footer(text=CATALOG_FOOTER)
        embeds.append(embed)
    return embeds


def build_catalog_messages() -> list[list[discord.Embed]]:
    """Los embeds partidos en los mensajes queDiscord permitira enviar."""
    embeds = build_catalog_embeds()
    return [embeds[i:i + EMBEDS_PER_MESSAGE]
            for i in range(0, len(embeds), EMBEDS_PER_MESSAGE)]