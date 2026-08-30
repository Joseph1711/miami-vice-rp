import discord
from discord import app_commands
from discord.ext import commands

from bot.embeds import info_embed

HELP_CATEGORIES = {
    "economia": {
        "emoji": "💰",
        "label": "Economía & Trabajos",
        "commands": [
            ("/balance [usuario]", "Ver tu saldo de efectivo y banco"),
            ("/trabajar", "Enviar reporte/evidencia de trabajo secundario para revisión de admins"),
            ("/trabajo mis_trabajos", "Ver el estado de tus evidencias de trabajo enviadas"),
            ("/trabajo pendientes", "Ver reportes de trabajo pendientes de revisión (Admin)"),
            ("/trabajo aprobar id_trabajo monto", "Aprobar y pagar una evidencia de trabajo (Admin)"),
            ("/trabajo rechazar id_trabajo motivo", "Rechazar un reporte de trabajo (Admin)"),
            ("/diario", "Reclamar recompensa diaria"),
            ("/semanal", "Reclamar recompensa semanal"),
            ("/pagar @usuario cantidad", "Pagar a otro jugador"),
            ("/tabla [tipo]", "Tabla de líderes (riqueza/nivel/reputación)"),
            ("/donar jugador/departamento/empresa", "Donar dinero"),
        ]
    },
    "dni": {
        "emoji": "🪪",
        "label": "Documento de Identidad & Multiroles",
        "commands": [
            ("/dni crear", "Tramitar tu DNI IC con foto de perfil de Roblox sincronizada (hasta 5 personajes)"),
            ("/dni mis_personajes", "Ver tus hasta 5 personajes registrados y alternar tu personaje activo"),
            ("/dni ver [usuario] [numero_dni]", "Ver el documento de identidad oficial con avatar de Roblox"),
            ("/dni buscar numero_dni", "Buscar a un ciudadano por su número de DNI único (ej: MIA-123456)"),
            ("/dni revocar @usuario motivo", "Revocar o anular el DNI de un ciudadano (Admin/Policía)"),
        ]
    },
    "policia": {
        "emoji": "👮",
        "label": "Policía & Seguridad Pública",
        "commands": [
            ("/policia arrestar @ciudadano motivo [tiempo] [fianza]", "Arrestar y procesar judicialmente a un infractor"),
            ("/policia multar @ciudadano monto motivo", "Emitir y cobrar una multa/infracción a un ciudadano"),
            ("/policia antecedentes @ciudadano", "Consultar el historial delictivo, multas y arrestos de un usuario"),
            ("/policia mis_multas", "Consultar tus multas pendientes, historial y fianzas fijadas"),
            ("/policia pagar_multa [folio]", "Pagar y liquidar una multa pendiente (efectivo o banco)"),
            ("/policia pagar_fianza [ciudadano]", "Pagar la fianza judicial de un detenido para otorgarle libertad"),
            ("/policia configurar_roles roles", "Configurar roles de Discord autorizados para usar comandos policiales (Admin)"),
        ]
    },
    "armas": {
        "emoji": "🔫",
        "label": "Registro Balístico de Armas",
        "commands": [
            ("/arma registrar", "Registrar un arma con número de serie único y aleatorio"),
            ("/arma mis_armas", "Ver todas las armas y licencias registradas a tu nombre"),
            ("/arma ver numero_serie", "Consultar el registro balístico y titular de un arma"),
            ("/arma transferir numero_serie @usuario", "Transferir la posesión legal de un arma a otro ciudadano"),
            ("/arma incautar numero_serie motivo", "Incautar un arma en operativo policial (Admin/Policía)"),
        ]
    },
    "vehiculos": {
        "emoji": "🚗",
        "label": "Vehículos, Remolques & ATVs",
        "commands": [
            ("/vehiculo registrar tipo [placa] [marca_modelo] [color]", "Matricular vehículo, trailer o cuatrimoto con tu placa personalizada"),
            ("/vehiculo mis_vehiculos [filtro_tipo]", "Consultar tu garage de vehículos, remolques y ATVs registrados"),
            ("/vehiculo ver placa_o_vin", "Ver tarjeta de circulación, titular y estado legal de una unidad"),
            ("/vehiculo buscar @usuario", "Consultar el parque automotor registrado de un ciudadano"),
            ("/vehiculo transferir placa @usuario [precio]", "Transferir legalmente la titularidad de un vehículo a otro ciudadano"),
            ("/vehiculo reportar placa estado", "Reportar vehículo como robado o recuperado ante la policía"),
            ("/vehiculo incautar placa motivo [multa]", "Incautar vehículo al corralón municipal (Admin/Policía)"),
            ("/vehiculo liberar placa", "Pagar multa de corralón y recuperar circulación de la unidad"),
        ]
    },
    "roblox": {
        "emoji": "🎮",
        "label": "Conexión a Roblox",
        "commands": [
            ("/roblox vincular usuario_o_id", "Vincular tu cuenta de Roblox con tu perfil de Discord"),
            ("/roblox perfil [usuario]", "Ver la tarjeta de Roblox con avatar 3D, estadísticas de rol y link oficial"),
            ("/roblox desvincular", "Desconectar tu cuenta de Roblox del servidor"),
        ]
    },
    "departamentos": {
        "emoji": "🏛️",
        "label": "Departamentos Oficiales",
        "commands": [
            ("/departamento lista", "Ver todos los departamentos oficiales activos"),
            ("/departamento info acronimo", "Ver información y presupuesto de un departamento"),
            ("/departamento postular acronimo", "Enviar postulación detallada validando el acrónimo oficial"),
            ("/departamento mis_postulaciones", "Ver el estado de tus solicitudes de ingreso"),
            ("/departamento miembros acronimo", "Ver el roster de oficiales y miembros"),
            ("/departamento contratar @usuario acronimo", "Contratar o ascender a un miembro (Admin/Mandos)"),
            ("/departamento despedir @usuario acronimo", "Dar de baja a un miembro (Admin/Mandos)"),
            ("/flota ver acronimo", "Ver vehículos del departamento"),
            ("/flota solicitar acronimo placa", "Solicitar un vehículo para patrullaje"),
            ("/flota devolver placa", "Devolver vehículo a la base"),
        ]
    },
    "banco": {
        "emoji": "🏦",
        "label": "Banco & Inversiones",
        "commands": [
            ("/banco depositar cantidad", "Depositar efectivo en el banco"),
            ("/banco retirar cantidad", "Retirar dinero del banco"),
            ("/banco info", "Ver información de tu cuenta"),
            ("/banco ahorros", "Abrir cuenta de ahorros (interés diario)"),
            ("/banco prestamo cantidad", "Solicitar préstamo"),
            ("/banco pagar", "Pagar tu préstamo activo"),
            ("/invertir crear tipo cantidad", "Crear una inversión financiera"),
            ("/invertir portafolio", "Ver tus inversiones activas"),
        ]
    },
    "mercado": {
        "emoji": "🛒",
        "label": "Tienda & Mercados",
        "commands": [
            ("/tienda explorar [categoria]", "Ver catálogo de objetos legales"),
            ("/tienda comprar objeto [cantidad]", "Comprar de la tienda"),
            ("/mercadonegro explorar", "Ver stock rotativo del mercado negro"),
            ("/mercadonegro comprar objeto", "Comprar objetos ilegales"),
            ("/mercado lista", "Ver objetos en venta entre jugadores"),
            ("/mercado vender objeto cantidad precio", "Publicar venta"),
            ("/mercado comprar id", "Comprar a otro jugador"),
            ("/inventario [usuario]", "Ver tu inventario de objetos"),
        ]
    },
    "empresas_propiedades": {
        "emoji": "🏢",
        "label": "Empresas & Bienes Raíces",
        "commands": [
            ("/empresa crear nombre [descripcion]", "Crear tu empresa"),
            ("/empresa info nombre", "Ver info de empresa"),
            ("/empresa contratar @usuario [salario]", "Contratar empleado"),
            ("/empresa miembros", "Ver empleados"),
            ("/propiedad lista", "Ver propiedades disponibles"),
            ("/propiedad comprar id", "Comprar propiedad"),
            ("/propiedad rentar id", "Rentar una propiedad"),
            ("/propiedad mias", "Ver tus propiedades"),
        ]
    },
    "crimen": {
        "emoji": "🕶️",
        "label": "Bajos Fondos & Crimen",
        "commands": [
            ("/drogas sembrar tipo", "Iniciar cultivo de droga"),
            ("/drogas cosechar", "Cosechar cultivo listo"),
            ("/drogas info", "Ver tus cultivos activos"),
            ("/lavar dinero metodo cantidad", "Lavar dinero sucio"),
            ("/lavar info", "Ver métodos de lavado"),
            ("/misiones lista", "Ver contratos ilegales disponibles"),
        ]
    },
    "tickets": {
        "emoji": "🎫",
        "label": "Tickets & Verificación",
        "commands": [
            ("/ticket panel [canal] [categoria] [rol]", "Publicar panel interactivo en el canal y categoría seleccionados"),
            ("/ticket abrir", "Abrir un ticket llenando el formulario/modal interactivo obligatorio"),
            ("/ticket cerrar", "Cerrar el ticket actual"),
            ("/verificar panel [canal] [roles_otorgar] [roles_retirar]", "Publicar panel de verificación multi-rol con conexión a Roblox"),
            ("/verificar configurar [roles_otorgar] [roles_retirar]", "Configurar uno o múltiples roles a otorgar y retirar"),
            ("/verificar agregar_rol @rol", "Añadir un rol adicional a la lista de roles otorgados"),
            ("/verificar remover_rol @rol", "Quitar un rol de la lista de verificación"),
            ("/verificar ver_config", "Ver la lista actual de roles y canales de verificación"),
            ("/verificar estado [usuario]", "Consultar estado de verificación y Roblox vinculado"),
        ]
    },
    "actualizaciones": {
        "emoji": "📢",
        "label": "Anuncios de Actualizaciones",
        "commands": [
            ("/update canal #canal", "Configurar canal oficial donde se publicarán los anuncios"),
            ("/update configurar [version] [cambios]", "Configurar versión y lista de cambios reales a anunciar"),
            ("/update preview", "Ver el anuncio con la personalidad sarcástica y auténtica del bot"),
            ("/update publicar [canal] [forzar]", "Publicar el anuncio en el canal configurado"),
            ("/update historial [limite]", "Consultar el historial de actualizaciones publicadas"),
            ("/update github_check [repo] [publicar]", "Detectar commits reales de GitHub y generar anuncio"),
            ("/update github_config activar_auto repo", "Configurar detección automática de GitHub cada 15 min"),
        ]
    },
    "anuncios_embed": {
        "emoji": "🖼️",
        "label": "Anuncios Oficiales Embed",
        "commands": [
            ("/anuncio modal #canal [mencion]", "Abrir editor interactivo para redactar comunicados con formato enriquecido"),
            ("/anuncio crear #canal titulo mensaje [color] [imagen] [pie]", "Crear y publicar un anuncio embed personalizado"),
            ("/anuncio rapido titulo mensaje [#canal]", "Publicar un comunicado embed rápido al instante"),
        ]
    },
    "bolo": {
        "emoji": "🚨",
        "label": "B.O.L.O. (Búsqueda & Captura)",
        "commands": [
            ("/bolo emitir tipo identificador motivo [peligrosidad] [recompensa]", "Emitir orden oficial de captura o búsqueda"),
            ("/bolo lista [estado] [tipo]", "Consultar órdenes BOLO activas o resueltas"),
            ("/bolo ver codigo", "Ver ficha técnica y antecedentes de la orden BOLO"),
            ("/bolo actualizar codigo nuevo_estado [notas]", "Actualizar estado a Capturado o Cancelado (Policía/Admin)"),
            ("/bolo borrar codigo", "Eliminar permanentemente una orden BOLO"),
        ]
    },
    "casos": {
        "emoji": "📁",
        "label": "Expedientes & Casos Judiciales",
        "commands": [
            ("/caso abrir titulo categoria descripcion [prioridad]", "Abrir nuevo expediente penal o judicial"),
            ("/caso lista [estado] [categoria]", "Ver lista de casos abiertos y en investigación"),
            ("/caso ver numero_caso", "Consultar expediente completo con pruebas y sospechosos"),
            ("/caso nota_agregar numero_caso nota", "Añadir avance de investigación al diario del caso"),
            ("/caso sospechoso_vincular numero_caso sospechoso cargos", "Imputar formalmente a un sospechoso"),
            ("/caso evidencia_vincular numero_caso tipo descripcion [serie]", "Anexar arma, vehículo o prueba forense"),
            ("/caso estado numero_caso nuevo_estado [veredicto]", "Actualizar fase procesal o sentencia judicial"),
        ]
    },
    "incidentes": {
        "emoji": "🚔",
        "label": "Central 911 & Incidentes CAD",
        "commands": [
            ("/incidente crear tipo ubicacion descripcion [prioridad]", "Emitir llamada 911 o reporte operativo"),
            ("/incidente lista [estado]", "Ver despachos activos y llamados de emergencia"),
            ("/incidente ver codigo", "Consultar detalles de la alerta de despacho"),
            ("/incidente atender codigo unidades", "Asignar patrullas y responder al llamado (10-76)"),
            ("/incidente cerrar codigo informe_final", "Cerrar y archivar el reporte del incidente"),
        ]
    },
    "admin": {
        "emoji": "⚙️",
        "label": "Administración del Servidor",
        "commands": [
            ("/admin configuracion rol_admin @rol", "Configurar el rol exclusivo para usar comandos admin"),
            ("/admin configuracion canal_trabajos #canal", "Configurar canal para recibir reportes de /trabajar"),
            ("/admin configuracion canal_postulaciones #canal", "Configurar canal para recibir postulaciones de departamentos"),
            ("/admin configuracion ver", "Ver resumen de toda la configuración del servidor"),
            ("/admin economia dar @usuario cantidad [tipo]", "Entregar dinero administrativo"),
            ("/admin economia quitar @usuario cantidad [tipo]", "Retirar dinero administrativo"),
            ("/admin departamento crear nombre acronimo [desc] [presupuesto]", "Crear nuevo departamento oficial"),
            ("/admin propiedad crear nombre tipo precio", "Crear bienes raíces"),
            ("/adminshop predeterminados", "Cargar catálogo de 35 objetos legales"),
            ("/adminshop mercadonegro", "Cargar catálogo de mercado negro"),
        ]
    },
    "server_control": {
        "emoji": "🌴",
        "label": "Control & Estado del Servidor",
        "commands": [
            ("/abrir-servidor [canal] [anuncio]", "Abrir oficialmente Miami Vice Roleplay (MVERP)"),
            ("/cerrar-servidor [canal] [motivo]", "Cerrar oficialmente las operaciones de Roleplay"),
            ("/votacion-servidor [duracion] [canal]", "Crear votación interactiva para abrir el servidor"),
            ("/estado-servidor", "Consultar si el servidor está ABIERTO o CERRADO"),
            ("/finalizar-votacion", "Concluir de inmediato la votación activa (Staff)"),
        ]
    },
}


class HelpCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=data["label"],
                value=key,
                emoji=data["emoji"],
                description=f"Comandos de {data['label'].lower()}"[:100]
            )
            for key, data in HELP_CATEGORIES.items()
        ]
        super().__init__(placeholder="Selecciona una categoría para ver comandos...", options=options)

    async def callback(self, interaction: discord.Interaction):
        category_key = self.values[0]
        cat_data = HELP_CATEGORIES.get(category_key)
        if not cat_data:
            await interaction.response.send_message("Categoría no encontrada", ephemeral=True)
            return

        e = info_embed(
            f"{cat_data['emoji']} Comandos — {cat_data['label']}",
            f"Lista de comandos disponibles en esta sección:"
        )
        for cmd, desc in cat_data["commands"]:
            e.add_field(name=f"`{cmd}`", value=desc, inline=False)

        e.set_footer(text="Miami Vice RP Bot • Usa / para autocompletar")
        await interaction.response.edit_message(embed=e)


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(HelpCategorySelect())


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Centro de ayuda y lista interactiva de comandos del bot")
    @app_commands.describe(categoria="Categoría opcional a consultar")
    @app_commands.choices(categoria=[
        app_commands.Choice(name="💰 Economía & Trabajos", value="economia"),
        app_commands.Choice(name="🪪 Documento de Identidad (DNI)", value="dni"),
        app_commands.Choice(name="🔫 Registro Balístico de Armas", value="armas"),
        app_commands.Choice(name="🚗 Vehículos, Trailers & ATVs", value="vehiculos"),
        app_commands.Choice(name="🚨 B.O.L.O. (Búsqueda & Captura)", value="bolo"),
        app_commands.Choice(name="📁 Casos & Expedientes", value="casos"),
        app_commands.Choice(name="🚔 Central 911 & Incidentes", value="incidentes"),
        app_commands.Choice(name="🖼️ Anuncios Embed", value="anuncios_embed"),
        app_commands.Choice(name="🎮 Conexión a Roblox", value="roblox"),
        app_commands.Choice(name="🏛️ Departamentos Oficiales", value="departamentos"),
        app_commands.Choice(name="🏦 Banco & Inversiones", value="banco"),
        app_commands.Choice(name="🛒 Tienda & Mercados", value="mercado"),
        app_commands.Choice(name="🏢 Empresas & Propiedades", value="empresas_propiedades"),
        app_commands.Choice(name="🕶️ Crimen & Bajos Fondos", value="crimen"),
        app_commands.Choice(name="🎫 Tickets & Soporte", value="tickets"),
        app_commands.Choice(name="📢 Actualizaciones Bot", value="actualizaciones"),
        app_commands.Choice(name="⚙️ Administración", value="admin"),
    ])
    async def help(self, interaction: discord.Interaction, categoria: str = None):
        if categoria and categoria in HELP_CATEGORIES:
            cat_data = HELP_CATEGORIES[categoria]
            e = info_embed(
                f"{cat_data['emoji']} Comandos — {cat_data['label']}",
                f"Lista de comandos disponibles:"
            )
            for cmd, desc in cat_data["commands"]:
                e.add_field(name=f"`{cmd}`", value=desc, inline=False)
            e.set_footer(text="Miami Vice RP Bot")
            await interaction.response.send_message(embed=e, ephemeral=True)
            return

        e = info_embed(
            "🌴 Miami Vice RP — Centro de Comandos",
            "Bienvenido al sistema integral de Roleplay para **Miami Vice**.\n\n"
            "Selecciona una categoría en el menú desplegable inferior para consultar los comandos detallados."
        )
        for key, data in HELP_CATEGORIES.items():
            e.add_field(
                name=f"{data['emoji']} {data['label']}",
                value=f"{len(data['commands'])} comandos disponibles",
                inline=True
            )

        e.set_footer(text="Desarrollado para la comunidad de Miami Vice Roleplay")
        view = HelpView()
        await interaction.response.send_message(embed=e, view=view)


async def setup(bot):
    await bot.add_cog(Help(bot))
