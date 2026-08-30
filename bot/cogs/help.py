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
        "label": "Documento de Identidad (DNI)",
        "commands": [
            ("/dni crear", "Tramitar tu DNI con datos de tu personaje IC y generar ID único"),
            ("/dni ver [usuario]", "Ver el documento de identidad oficial de un ciudadano"),
            ("/dni buscar numero_dni", "Buscar a un ciudadano por su número de DNI único (ej: MIA-123456)"),
            ("/dni revocar @usuario motivo", "Revocar o anular el DNI de un ciudadano (Admin/Policía)"),
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
        "label": "Tickets & Soporte",
        "commands": [
            ("/ticket abrir", "Abrir ticket de soporte privado"),
            ("/ticket cerrar", "Cerrar ticket actual"),
            ("/verificar estado", "Ver tu estado de verificación"),
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
        app_commands.Choice(name="🎮 Conexión a Roblox", value="roblox"),
        app_commands.Choice(name="🏛️ Departamentos Oficiales", value="departamentos"),
        app_commands.Choice(name="🏦 Banco & Inversiones", value="banco"),
        app_commands.Choice(name="🛒 Tienda & Mercados", value="mercado"),
        app_commands.Choice(name="🏢 Empresas & Propiedades", value="empresas_propiedades"),
        app_commands.Choice(name="🕶️ Crimen & Bajos Fondos", value="crimen"),
        app_commands.Choice(name="🎫 Tickets & Soporte", value="tickets"),
        app_commands.Choice(name="📢 Anuncios de Actualizaciones", value="actualizaciones"),
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
