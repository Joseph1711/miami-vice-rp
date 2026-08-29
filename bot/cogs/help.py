import discord
from discord import app_commands
from discord.ext import commands

from bot.embeds import info_embed

HELP_CATEGORIES = {
    "economia": {
        "emoji": "💰",
        "label": "Economía",
        "commands": [
            ("/balance [usuario]", "Ver tu saldo de efectivo y banco"),
            ("/diario", "Reclamar recompensa diaria"),
            ("/semanal", "Reclamar recompensa semanal"),
            ("/trabajar", "Trabajar para ganar dinero"),
            ("/pagar @usuario cantidad", "Pagar a otro jugador"),
            ("/tabla [tipo]", "Tabla de líderes (riqueza/nivel/reputación)"),
            ("/donar jugador/departamento/empresa", "Donar dinero"),
        ]
    },
    "banco": {
        "emoji": "🏦",
        "label": "Banco",
        "commands": [
            ("/banco depositar cantidad", "Depositar efectivo en el banco"),
            ("/banco retirar cantidad", "Retirar dinero del banco"),
            ("/banco info", "Ver información de tu cuenta"),
            ("/banco ahorros", "Abrir cuenta de ahorros (2% interés diario)"),
            ("/banco prestamo cantidad", "Solicitar préstamo (10% interés, 7 días)"),
            ("/banco pagar", "Pagar tu préstamo activo"),
            ("/invertir crear tipo cantidad", "Crear una inversión"),
            ("/invertir portafolio", "Ver tus inversiones activas"),
        ]
    },
    "inventario": {
        "emoji": "🎒",
        "label": "Inventario",
        "commands": [
            ("/inventario [usuario]", "Ver tu inventario de objetos"),
            ("/dar @usuario objeto [cantidad]", "Dar un objeto a otro jugador"),
        ]
    },
    "mercado": {
        "emoji": "🛒",
        "label": "Mercado",
        "commands": [
            ("/mercado lista", "Ver objetos en venta"),
            ("/mercado vender objeto cantidad precio", "Vender un objeto"),
            ("/mercado comprar id", "Comprar un objeto"),
            ("/mercado subasta objeto precio horas", "Crear subasta"),
            ("/mercado pujar id cantidad", "Pujar en una subasta"),
            ("/mercado cancelar id", "Cancelar tu listado"),
            ("/tienda explorar [categoria]", "Ver objetos en la tienda"),
            ("/tienda comprar objeto [cantidad]", "Comprar de la tienda"),
            ("/tienda info objeto", "Ver detalles de objeto"),
            ("/mercadonegro explorar", "Ver stock del mercado negro"),
            ("/mercadonegro comprar objeto [cantidad]", "Comprar del mercado negro"),
        ]
    },
    "departamentos": {
        "emoji": "🏛️",
        "label": "Departamentos",
        "commands": [
            ("/departamento lista", "Ver todos los departamentos"),
            ("/departamento info acronimo", "Info de un departamento"),
            ("/departamento unirse acronimo", "Unirse a un departamento"),
            ("/departamento contratar @usuario acronimo [rango] [salario]", "Contratar miembro"),
            ("/departamento despedir @usuario acronimo", "Despedir miembro"),
            ("/departamento presupuesto acronimo", "Ver presupuesto"),
            ("/departamento miembros acronimo", "Ver miembros"),
            ("/flota ver acronimo", "Ver vehículos del departamento"),
            ("/flota comprar acronimo tipo", "Comprar vehículo"),
        ]
    },
    "empresas": {
        "emoji": "🏢",
        "label": "Empresas",
        "commands": [
            ("/empresa crear nombre [descripcion]", "Crear tu empresa ($5,000)"),
            ("/empresa info nombre", "Ver info de empresa"),
            ("/empresa contratar @usuario [salario]", "Contratar empleado"),
            ("/empresa despedir @usuario", "Despedir empleado"),
            ("/empresa miembros", "Ver empleados"),
            ("/empresa depositar cantidad", "Depositar fondos a la empresa"),
        ]
    },
    "propiedades": {
        "emoji": "🏘️",
        "label": "Propiedades",
        "commands": [
            ("/propiedad lista", "Ver propiedades disponibles"),
            ("/propiedad comprar id", "Comprar propiedad"),
            ("/propiedad vender id", "Vender propiedad (75% del valor)"),
            ("/propiedad rentar id", "Rentar una propiedad"),
            ("/propiedad mias", "Ver tus propiedades"),
        ]
    },
    "social": {
        "emoji": "⭐",
        "label": "Social y Niveles",
        "commands": [
            ("/reputacion dar @usuario tipo", "Dar reputación positiva/negativa"),
            ("/reputacion perfil [usuario]", "Ver perfil de reputación"),
            ("/nivel [usuario]", "Ver nivel y XP"),
        ]
    },
    "crimen": {
        "emoji": "🔫",
        "label": "Crimen",
        "commands": [
            ("/drogas sembrar tipo", "Iniciar cultivo de droga"),
            ("/drogas cosechar", "Cosechar cultivo listo"),
            ("/drogas info", "Ver tus cultivos activos"),
            ("/lavar dinero metodo cantidad", "Lavar dinero sucio"),
            ("/lavar info", "Ver métodos de lavado"),
            ("/misiones lista", "Ver misiones disponibles"),
            ("/misiones iniciar id", "Iniciar una misión"),
            ("/misiones completar", "Reclamar recompensa"),
            ("/misiones activas", "Ver tus misiones activas"),
        ]
    },
    "tickets": {
        "emoji": "🎫",
        "label": "Tickets y Verificación",
        "commands": [
            ("/ticket abrir", "Abrir ticket de soporte"),
            ("/ticket cerrar", "Cerrar ticket actual"),
            ("/ticket lista", "Ver tickets abiertos (mod)"),
            ("/ticket panel", "Crear panel de tickets (admin)"),
            ("/verificar panel", "Crear panel de verificación (admin)"),
            ("/verificar estado", "Ver tu estado de verificación"),
        ]
    },
    "contratos": {
        "emoji": "📜",
        "label": "Contratos",
        "commands": [
            ("/contrato lista", "Ver contratos disponibles"),
            ("/contrato aceptar id", "Aceptar un contrato"),
            ("/contrato crear titulo descripcion recompensa", "Crear contrato (admin)"),
            ("/contrato completar id", "Completar contrato (admin)"),
        ]
    },
    "admin": {
        "emoji": "⚙️",
        "label": "Administración",
        "commands": [
            ("/admin economia dar @usuario cantidad [tipo]", "Dar dinero"),
            ("/admin economia quitar @usuario cantidad [tipo]", "Quitar dinero"),
            ("/admin objetos crear nombre categoria rareza precio", "Crear objeto"),
            ("/admin objetos lista", "Ver todos los objetos"),
            ("/admin departamento crear nombre acronimo [descripcion] [presupuesto]", "Crear departamento"),
            ("/admin propiedad crear nombre tipo precio [renta]", "Crear propiedad"),
            ("/admin configuracion diario cantidad", "Config recompensa diaria"),
            ("/admin configuracion semanal cantidad", "Config recompensa semanal"),
            ("/adminshop agregar objeto precio [stock]", "Añadir a tienda"),
            ("/adminshop quitar objeto", "Quitar de tienda"),
            ("/adminshop predeterminados", "Cargar catálogo de 35 objetos"),
            ("/tesoro info", "Ver tesoro del servidor"),
            ("/tesoro depositar cantidad", "Depositar al tesoro"),
            ("/tesoro financiar acronimo cantidad", "Financiar departamento"),
            ("/solicitar aplicar tipo", "Solicitar ingreso a departamento"),
            ("/solicitar lista", "Ver solicitudes pendientes (admin)"),
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
                description=f"Comandos de {data['label'].lower()}"
            )
            for key, data in HELP_CATEGORIES.items()
        ]
        super().__init__(placeholder="Selecciona una categoría...", options=options)

    async def callback(self, interaction: discord.Interaction):
        key = self.values[0]
        cat = HELP_CATEGORIES[key]
        e = info_embed(f"{cat['emoji']} {cat['label']}")
        lines = [f"`{cmd}` — {desc}" for cmd, desc in cat["commands"]]
        e.description = "\n".join(lines)
        await interaction.response.edit_message(embed=e, view=self.view)

class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(HelpCategorySelect())

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ayuda", description="Ver todos los comandos disponibles")
    @app_commands.describe(categoria="Categoría específica (opcional)")
    @app_commands.choices(categoria=[
        app_commands.Choice(name=f"{data['emoji']} {data['label']}", value=key)
        for key, data in HELP_CATEGORIES.items()
    ])
    async def ayuda(self, interaction: discord.Interaction, categoria: str = None):
        await interaction.response.defer()
        if categoria:
            cat = HELP_CATEGORIES.get(categoria)
            if not cat:
                await interaction.followup.send(embed=info_embed("❌ Categoría no encontrada"), ephemeral=True)
                return
            e = info_embed(f"{cat['emoji']} {cat['label']}")
            lines = [f"`{cmd}` — {desc}" for cmd, desc in cat["commands"]]
            e.description = "\n".join(lines)
            await interaction.followup.send(embed=e, ephemeral=True)
            return
        e = info_embed("📖 Miami Vice — Ayuda", "Selecciona una categoría del menú desplegable para moverte por la ciudad y ver los comandos disponibles.")
        e.add_field(name="Categorías", value="\n".join(f"{data['emoji']} **{data['label']}**" for data in HELP_CATEGORIES.values()), inline=False)
        view = HelpView()
        await interaction.followup.send(embed=e, view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Help(bot))
