import discord
from discord import app_commands
from discord.ext import commands
import datetime
import random

from bot.db import aexecute, aexecute_many
from bot.helpers import async_get_or_create_user, async_get_or_create_guild_config, format_currency, generate_id, check_admin_permission
from bot.embeds import success_embed, error_embed, info_embed
from bot.services.economy import async_add_cash, async_add_bank, async_log_transaction

SHOP_ITEMS = [
    {"name":"Radio Policial","category":"Equipamiento","rarity":"uncommon","price":1500,"emoji":"📻"},
    {"name":"Chaleco Antibalas","category":"Equipamiento","rarity":"rare","price":5000,"emoji":"🦺"},
    {"name":"Esposas","category":"Equipamiento","rarity":"common","price":300,"emoji":"⛓️"},
    {"name":"Extintor","category":"Equipamiento","rarity":"common","price":400,"emoji":"🧯"},
    {"name":"Kit Médico","category":"Equipamiento","rarity":"uncommon","price":1200,"emoji":"🩺"},
    {"name":"Linterna Táctica","category":"Equipamiento","rarity":"common","price":350,"emoji":"🔦"},
    {"name":"Casco de Seguridad","category":"Equipamiento","rarity":"common","price":600,"emoji":"⛑️"},
    {"name":"Walkie-Talkie","category":"Equipamiento","rarity":"common","price":800,"emoji":"📡"},
    {"name":"Binoculares","category":"Equipamiento","rarity":"uncommon","price":1800,"emoji":"🔭"},
    {"name":"Desfibrilador","category":"Equipamiento","rarity":"rare","price":7500,"emoji":"⚡"},
    {"name":"Laptop","category":"Tecnología","rarity":"uncommon","price":3000,"emoji":"💻"},
    {"name":"Teléfono","category":"Tecnología","rarity":"common","price":500,"emoji":"📱"},
    {"name":"Dron de Vigilancia","category":"Tecnología","rarity":"rare","price":8000,"emoji":"🚁"},
    {"name":"Cámara","category":"Tecnología","rarity":"common","price":800,"emoji":"📷"},
    {"name":"GPS Profesional","category":"Tecnología","rarity":"common","price":600,"emoji":"🗺️"},
    {"name":"Tablet","category":"Tecnología","rarity":"uncommon","price":1500,"emoji":"📟"},
    {"name":"Escáner Forense","category":"Tecnología","rarity":"rare","price":9000,"emoji":"🔬"},
    {"name":"Cemento","category":"Construcción","rarity":"common","price":200,"emoji":"🧱"},
    {"name":"Madera","category":"Construcción","rarity":"common","price":150,"emoji":"🪵"},
    {"name":"Acero","category":"Construcción","rarity":"uncommon","price":500,"emoji":"⚙️"},
    {"name":"Vidrio","category":"Construcción","rarity":"common","price":300,"emoji":"🪟"},
    {"name":"Cable","category":"Construcción","rarity":"common","price":250,"emoji":"🔌"},
    {"name":"Herramientas","category":"Construcción","rarity":"uncommon","price":750,"emoji":"🔧"},
    {"name":"Pintura","category":"Construcción","rarity":"common","price":180,"emoji":"🪣"},
    {"name":"Licencia de Conducir","category":"Documentos","rarity":"common","price":500,"emoji":"🪪"},
    {"name":"Permiso de Trabajo","category":"Documentos","rarity":"uncommon","price":1000,"emoji":"📄"},
    {"name":"Pase VIP","category":"Documentos","rarity":"rare","price":12000,"emoji":"🎫"},
    {"name":"Credencial de Prensa","category":"Documentos","rarity":"uncommon","price":2000,"emoji":"📰"},
    {"name":"Certificado Médico","category":"Documentos","rarity":"common","price":300,"emoji":"📋"},
    {"name":"Maletín Ejecutivo","category":"Accesorios","rarity":"uncommon","price":1000,"emoji":"💼"},
    {"name":"Reloj de Lujo","category":"Accesorios","rarity":"epic","price":50000,"emoji":"⌚"},
    {"name":"Cadena de Oro","category":"Accesorios","rarity":"rare","price":20000,"emoji":"📿"},
    {"name":"Gafas Oscuras","category":"Accesorios","rarity":"common","price":400,"emoji":"🕶️"},
    {"name":"Mochila Táctica","category":"Accesorios","rarity":"uncommon","price":900,"emoji":"🎒"},
    {"name":"Traje Formal","category":"Accesorios","rarity":"uncommon","price":3500,"emoji":"👔"},
    {"name":"Chaqueta de Cuero","category":"Accesorios","rarity":"uncommon","price":2800,"emoji":"🧥"},
    {"name":"Botas de Combate","category":"Accesorios","rarity":"uncommon","price":1200,"emoji":"👢"},
    {"name":"Comida","category":"Consumibles","rarity":"common","price":100,"emoji":"🍔"},
    {"name":"Agua","category":"Consumibles","rarity":"common","price":50,"emoji":"💧"},
    {"name":"Energizante","category":"Consumibles","rarity":"common","price":200,"emoji":"⚡"},
    {"name":"Café","category":"Consumibles","rarity":"common","price":80,"emoji":"☕"},
    {"name":"Gasolina","category":"Consumibles","rarity":"common","price":150,"emoji":"⛽"},
    {"name":"Botiquín Básico","category":"Consumibles","rarity":"common","price":250,"emoji":"🩹"},
    {"name":"Sandwich","category":"Consumibles","rarity":"common","price":75,"emoji":"🥪"},
    {"name":"Bebida Isotónica","category":"Consumibles","rarity":"common","price":120,"emoji":"🧃"},
    {"name":"Llanta de Repuesto","category":"Vehículos","rarity":"common","price":400,"emoji":"🛞"},
    {"name":"Aceite de Motor","category":"Vehículos","rarity":"common","price":300,"emoji":"🛢️"},
    {"name":"Kit de Herramientas Auto","category":"Vehículos","rarity":"uncommon","price":1500,"emoji":"🔩"},
    {"name":"Extintor Vehicular","category":"Vehículos","rarity":"common","price":350,"emoji":"🧯"},
]

BLACK_MARKET_ITEMS = [
    {"name":"Arma Corta","category":"Armas","rarity":"rare","price":10000,"emoji":"🔫"},
    {"name":"Rifle de Asalto","category":"Armas","rarity":"epic","price":28000,"emoji":"🎯"},
    {"name":"Cuchillo de Combate","category":"Armas","rarity":"uncommon","price":2500,"emoji":"🗡️"},
    {"name":"Granada","category":"Armas","rarity":"epic","price":18000,"emoji":"💣"},
    {"name":"Munición Especial","category":"Armas","rarity":"uncommon","price":500,"emoji":"🔹"},
    {"name":"Silenciador","category":"Armas","rarity":"rare","price":6000,"emoji":"🔧"},
    {"name":"Escopeta","category":"Armas","rarity":"rare","price":15000,"emoji":"🔫"},
    {"name":"Francotirador","category":"Armas","rarity":"legendary","price":60000,"emoji":"🎯"},
    {"name":"Chaleco Militar","category":"Armas","rarity":"epic","price":20000,"emoji":"🥋"},
    {"name":"Hierba","category":"Drogas","rarity":"common","price":200,"emoji":"🌿"},
    {"name":"Polvo Blanco","category":"Drogas","rarity":"rare","price":5000,"emoji":"🤍"},
    {"name":"Pastillas","category":"Drogas","rarity":"uncommon","price":800,"emoji":"💊"},
    {"name":"Metanfetamina","category":"Drogas","rarity":"rare","price":4500,"emoji":"💎"},
    {"name":"Opiáceos","category":"Drogas","rarity":"epic","price":9000,"emoji":"🔴"},
    {"name":"Solvente Tóxico","category":"Drogas","rarity":"uncommon","price":1200,"emoji":"🧪"},
    {"name":"Pasaporte Falso","category":"Documentos Falsos","rarity":"epic","price":35000,"emoji":"📕"},
    {"name":"Placa Policial Falsa","category":"Documentos Falsos","rarity":"epic","price":30000,"emoji":"🪪"},
    {"name":"Identificación Robada","category":"Documentos Falsos","rarity":"rare","price":12000,"emoji":"🆔"},
    {"name":"Licencia Falsificada","category":"Documentos Falsos","rarity":"rare","price":8000,"emoji":"📃"},
    {"name":"Placas Vehiculares Robadas","category":"Documentos Falsos","rarity":"uncommon","price":3000,"emoji":"🔲"},
    {"name":"Llave Maestra","category":"Equipo Especial","rarity":"legendary","price":100000,"emoji":"🗝️"},
    {"name":"Explosivo C4","category":"Equipo Especial","rarity":"legendary","price":80000,"emoji":"💥"},
    {"name":"Cámara Espía","category":"Equipo Especial","rarity":"rare","price":15000,"emoji":"👁️"},
    {"name":"Escáner de Frecuencias","category":"Equipo Especial","rarity":"epic","price":25000,"emoji":"📡"},
    {"name":"Bloqueador de Señal","category":"Equipo Especial","rarity":"rare","price":18000,"emoji":"📵"},
    {"name":"Kit de Hackeo","category":"Equipo Especial","rarity":"epic","price":40000,"emoji":"💻"},
    {"name":"Cigarrillos de Contrabando","category":"Contrabando","rarity":"common","price":600,"emoji":"🚬"},
    {"name":"Alcohol Ilegal","category":"Contrabando","rarity":"uncommon","price":1500,"emoji":"🥃"},
    {"name":"Diamantes Robados","category":"Contrabando","rarity":"legendary","price":75000,"emoji":"💎"},
    {"name":"Arte Falsificado","category":"Contrabando","rarity":"epic","price":45000,"emoji":"🖼️"},
    {"name":"Electrónicos Robados","category":"Contrabando","rarity":"rare","price":8000,"emoji":"📦"},
    {"name":"Vehículo Chop Shop","category":"Contrabando","rarity":"rare","price":20000,"emoji":"🚗"},
]

async def admin_check(interaction: discord.Interaction) -> bool:
    return await check_admin_permission(interaction)

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    admin = app_commands.Group(name="admin", description="Comandos de administración")

    admin_eco = app_commands.Group(name="economia", description="Gestión de economía", parent=admin)

    @admin_eco.command(name="dar", description="Dar dinero a un jugador")
    @app_commands.describe(usuario="Jugador", cantidad="Cantidad", tipo="Efectivo o banco")
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Efectivo", value="cash"),
        app_commands.Choice(name="Banco", value="bank"),
    ])
    async def eco_dar(self, interaction: discord.Interaction, usuario: discord.Member, cantidad: int, tipo: str = "cash"):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        await async_get_or_create_user(str(usuario.id), str(interaction.guild_id))
        if tipo == "cash":
            await async_add_cash(str(usuario.id), str(interaction.guild_id), cantidad)
        else:
            await async_add_bank(str(usuario.id), str(interaction.guild_id), cantidad)
        await interaction.followup.send(embed=success_embed("Dinero entregado", f"Se entregaron **{format_currency(cantidad)}** ({tipo}) a {usuario.mention}"), ephemeral=True)

    @admin_eco.command(name="quitar", description="Quitar dinero a un jugador")
    @app_commands.describe(usuario="Jugador", cantidad="Cantidad", tipo="Efectivo o banco")
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Efectivo", value="cash"),
        app_commands.Choice(name="Banco", value="bank"),
    ])
    async def eco_quitar(self, interaction: discord.Interaction, usuario: discord.Member, cantidad: int, tipo: str = "cash"):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        if tipo == "cash":
            await aexecute("UPDATE users SET cash=GREATEST(0,cash-$1), updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3", (cantidad, str(usuario.id), str(interaction.guild_id)))
        else:
            await aexecute("UPDATE users SET bank=GREATEST(0,bank-$1), updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3", (cantidad, str(usuario.id), str(interaction.guild_id)))
        await interaction.followup.send(embed=success_embed("Dinero quitado", f"Se quitaron **{format_currency(cantidad)}** ({tipo}) a {usuario.mention}"), ephemeral=True)

    admin_items = app_commands.Group(name="objetos", description="Gestión de objetos", parent=admin)

    @admin_items.command(name="crear", description="Crear un objeto nuevo")
    @app_commands.describe(nombre="Nombre", categoria="Categoría", rareza="Rareza", precio="Precio", emoji="Emoji")
    @app_commands.choices(rareza=[
        app_commands.Choice(name="Common", value="common"),
        app_commands.Choice(name="Uncommon", value="uncommon"),
        app_commands.Choice(name="Rare", value="rare"),
        app_commands.Choice(name="Epic", value="epic"),
        app_commands.Choice(name="Legendary", value="legendary"),
    ])
    async def items_crear(self, interaction: discord.Interaction, nombre: str, categoria: str, rareza: str, precio: int, emoji: str = "📦"):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        item_id = generate_id()
        await aexecute(
            """INSERT INTO items (id, name, category, rarity, price, emoji, is_active, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,true,NOW(),NOW())""",
            (item_id, nombre, categoria, rareza, precio, emoji)
        )
        await interaction.followup.send(embed=success_embed("Objeto creado", f"{emoji} **{nombre}** — {rareza} — {format_currency(precio)}"), ephemeral=True)

    @admin_items.command(name="lista", description="Ver todos los objetos")
    async def items_lista(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        items = await aexecute("SELECT * FROM items ORDER BY category, name LIMIT 25", fetch="all") or []
        e = info_embed("📦 Objetos del servidor")
        if not items:
            e.description = "No hay objetos creados"
        else:
            cats = {}
            for it in items:
                cats.setdefault(it.get("category","General"), []).append(it)
            for cat, citems in cats.items():
                lines = [f"{it.get('emoji','📦')} **{it['name']}** — {format_currency(it['price'])} ({it.get('rarity','common')})" for it in citems[:5]]
                e.add_field(name=cat, value="\n".join(lines), inline=True)
        await interaction.followup.send(embed=e, ephemeral=True)

    admin_dept = app_commands.Group(name="departamento", description="Gestión de departamentos", parent=admin)

    @admin_dept.command(name="crear", description="Crear un departamento")
    @app_commands.describe(nombre="Nombre completo", acronimo="Acrónimo (MPD, MDFR, FHP, FDOT, MBPD, FDOJ)", descripcion="Descripción", presupuesto="Presupuesto inicial")
    async def dept_crear(self, interaction: discord.Interaction, nombre: str, acronimo: str, descripcion: str = "", presupuesto: int = 10000):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        existing = await aexecute("SELECT id FROM departments WHERE guild_id=$1 AND acronym ILIKE $2", (str(interaction.guild_id), acronimo), fetch="one")
        if existing:
            await interaction.followup.send(embed=error_embed("Ya existe", f"Ya hay un departamento con acrónimo **{acronimo}**"), ephemeral=True)
            return
        await aexecute(
            """INSERT INTO departments (id, guild_id, name, acronym, description, budget, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,NOW(),NOW())""",
            (generate_id(), str(interaction.guild_id), nombre, acronimo.upper(), descripcion, presupuesto)
        )
        await interaction.followup.send(embed=success_embed(f"Departamento creado — {acronimo.upper()}", f"**{nombre}** con presupuesto inicial de {format_currency(presupuesto)}"), ephemeral=True)

    admin_prop = app_commands.Group(name="propiedad", description="Gestión de propiedades", parent=admin)

    @admin_prop.command(name="crear", description="Crear una propiedad")
    @app_commands.describe(nombre="Nombre", tipo="Tipo", precio="Precio de compra", precio_renta="Precio de renta diario (0=no rentable)")
    @app_commands.choices(tipo=[
        app_commands.Choice(name="🏠 Casa", value="house"),
        app_commands.Choice(name="🏢 Apartamento", value="apartment"),
        app_commands.Choice(name="🏭 Bodega", value="warehouse"),
        app_commands.Choice(name="🏬 Oficina", value="office"),
        app_commands.Choice(name="🌿 Terreno", value="land"),
        app_commands.Choice(name="🏰 Mansión", value="mansion"),
        app_commands.Choice(name="🏪 Tienda", value="store"),
    ])
    async def prop_crear(self, interaction: discord.Interaction, nombre: str, tipo: str, precio: int, precio_renta: int = 0):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        await aexecute(
            """INSERT INTO properties (id, guild_id, name, type, price, rent_price, status, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,'available',NOW(),NOW())""",
            (generate_id(), str(interaction.guild_id), nombre, tipo, precio, precio_renta if precio_renta > 0 else None)
        )
        await interaction.followup.send(embed=success_embed("Propiedad creada", f"**{nombre}** — {format_currency(precio)} de compra"), ephemeral=True)

    admin_xp = app_commands.Group(name="xp", description="Gestión de XP", parent=admin)

    @admin_xp.command(name="dar", description="Dar XP a un jugador")
    @app_commands.describe(usuario="Jugador", cantidad="Cantidad de XP")
    async def xp_dar(self, interaction: discord.Interaction, usuario: discord.Member, cantidad: int):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        await async_get_or_create_user(str(usuario.id), str(interaction.guild_id))
        await aexecute("UPDATE users SET xp=xp+$1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3", (cantidad, str(usuario.id), str(interaction.guild_id)))
        await interaction.followup.send(embed=success_embed("XP otorgado", f"Se dieron **{cantidad} XP** a {usuario.mention}"), ephemeral=True)

    @admin_xp.command(name="quitar", description="Quitar XP a un jugador")
    @app_commands.describe(usuario="Jugador", cantidad="Cantidad de XP")
    async def xp_quitar(self, interaction: discord.Interaction, usuario: discord.Member, cantidad: int):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        await aexecute("UPDATE users SET xp=GREATEST(0,xp-$1), updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3", (cantidad, str(usuario.id), str(interaction.guild_id)))
        await interaction.followup.send(embed=success_embed("XP quitado", f"Se quitaron **{cantidad} XP** a {usuario.mention}"), ephemeral=True)

    @admin_xp.command(name="multiplicador", description="Ver/establecer el multiplicador de XP del servidor")
    @app_commands.describe(valor="Multiplicador (ej: 1.5 = +50% XP). Omite para ver el actual.")
    async def xp_multiplicador(self, interaction: discord.Interaction, valor: float = None):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        await async_get_or_create_guild_config(str(interaction.guild_id))
        if valor is None:
            cfg = await aexecute("SELECT xp_multiplier FROM guild_config WHERE guild_id=$1", (str(interaction.guild_id),), fetch="one")
            mult = cfg.get("xp_multiplier", 1.0) if cfg else 1.0
            await interaction.followup.send(embed=info_embed("Multiplicador de XP", f"Actual: **{mult}x**"), ephemeral=True)
        else:
            await aexecute("UPDATE guild_config SET xp_multiplier=$1, updated_at=NOW() WHERE guild_id=$2", (max(0.1, min(valor, 10.0)), str(interaction.guild_id)))
            await interaction.followup.send(embed=success_embed("Multiplicador actualizado", f"XP multiplicado por **{valor}x**"), ephemeral=True)

    admin_reset = app_commands.Group(name="reset", description="Restablecer datos de jugadores", parent=admin)

    @admin_reset.command(name="usuario", description="Restablecer economía de un jugador")
    @app_commands.describe(usuario="Jugador a restablecer")
    async def reset_usuario(self, interaction: discord.Interaction, usuario: discord.Member):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        await aexecute(
            "UPDATE users SET cash=0, bank=0, xp=0, level=1, reputation=0, dirty_money=0, updated_at=NOW() WHERE discord_id=$1 AND guild_id=$2",
            (str(usuario.id), str(interaction.guild_id))
        )
        await interaction.followup.send(embed=success_embed("Usuario restablecido", f"Economía y estadísticas de {usuario.mention} fueron reiniciadas"), ephemeral=True)

    @admin_reset.command(name="cooldowns", description="Reiniciar los cooldowns de un jugador")
    @app_commands.describe(usuario="Jugador")
    async def reset_cooldowns(self, interaction: discord.Interaction, usuario: discord.Member):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        await aexecute(
            "UPDATE users SET last_daily=NULL, last_weekly=NULL, last_work=NULL, updated_at=NOW() WHERE discord_id=$1 AND guild_id=$2",
            (str(usuario.id), str(interaction.guild_id))
        )
        await interaction.followup.send(embed=success_embed("Cooldowns reiniciados", f"Cooldowns de {usuario.mention} fueron reiniciados"), ephemeral=True)

    admin_rewards = app_commands.Group(name="recompensas", description="Recompensas de nivel", parent=admin)

    @admin_rewards.command(name="agregar", description="Agregar recompensa de rol por nivel")
    @app_commands.describe(nivel="Nivel requerido", rol="Rol a otorgar")
    async def rewards_agregar(self, interaction: discord.Interaction, nivel: int, rol: discord.Role):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        existing = await aexecute("SELECT id FROM level_rewards WHERE guild_id=$1 AND level=$2", (str(interaction.guild_id), nivel), fetch="one")
        if existing:
            await aexecute("UPDATE level_rewards SET role_id=$1, updated_at=NOW() WHERE id=$2", (str(rol.id), existing["id"]))
        else:
            await aexecute(
                "INSERT INTO level_rewards (id, guild_id, level, role_id, created_at, updated_at) VALUES ($1,$2,$3,$4,NOW(),NOW())",
                (generate_id(), str(interaction.guild_id), nivel, str(rol.id))
            )
        await interaction.followup.send(embed=success_embed("Recompensa agregada", f"Nivel **{nivel}** → {rol.mention}"), ephemeral=True)

    @admin_rewards.command(name="lista", description="Ver recompensas de nivel configuradas")
    async def rewards_lista(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        rewards = await aexecute(
            "SELECT * FROM level_rewards WHERE guild_id=$1 ORDER BY level",
            (str(interaction.guild_id),), fetch="all"
        ) or []
        e = info_embed("🎖️ Recompensas de Nivel")
        if not rewards:
            e.description = "No hay recompensas de nivel configuradas"
        else:
            lines = [f"Nivel **{r['level']}** → <@&{r['role_id']}>" for r in rewards]
            e.description = "\n".join(lines)
        await interaction.followup.send(embed=e, ephemeral=True)

    @admin_rewards.command(name="quitar", description="Quitar recompensa de un nivel")
    @app_commands.describe(nivel="Nivel")
    async def rewards_quitar(self, interaction: discord.Interaction, nivel: int):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        await aexecute("DELETE FROM level_rewards WHERE guild_id=$1 AND level=$2", (str(interaction.guild_id), nivel))
        await interaction.followup.send(embed=success_embed("Recompensa eliminada", f"Recompensa de nivel **{nivel}** eliminada"), ephemeral=True)

    admin_cfg = app_commands.Group(name="configuracion", description="Configuración del servidor", parent=admin)

    @admin_cfg.command(name="rol_admin", description="Configurar el rol de administrador para comandos admin")
    @app_commands.describe(rol="Rol que tendrá permisos de administrador")
    async def cfg_rol_admin(self, interaction: discord.Interaction, rol: discord.Role):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores autorizados"), ephemeral=True)
            return
        await async_get_or_create_guild_config(str(interaction.guild_id))
        await aexecute("UPDATE guild_config SET admin_role_id=$1, updated_at=NOW() WHERE guild_id=$2", (str(rol.id), str(interaction.guild_id)))
        await interaction.followup.send(embed=success_embed("Rol Admin Configurado", f"Los comandos administrativos ahora pueden ser usados por el rol {rol.mention}"), ephemeral=True)

    @admin_cfg.command(name="canal_trabajos", description="Configurar canal de revisiones para evidencias de trabajo")
    @app_commands.describe(canal="Canal donde se enviarán las evidencias de trabajo para revisión")
    async def cfg_canal_trabajos(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores autorizados"), ephemeral=True)
            return
        await async_get_or_create_guild_config(str(interaction.guild_id))
        await aexecute("UPDATE guild_config SET work_logs_channel_id=$1, updated_at=NOW() WHERE guild_id=$2", (str(canal.id), str(interaction.guild_id)))
        await interaction.followup.send(embed=success_embed("Canal de Trabajos Configurado", f"Las evidencias de trabajo se enviarán a {canal.mention}"), ephemeral=True)

    @admin_cfg.command(name="canal_postulaciones", description="Configurar canal para postulaciones a departamentos")
    @app_commands.describe(canal="Canal donde se enviarán las solicitudes a departamentos")
    async def cfg_canal_postulaciones(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores autorizados"), ephemeral=True)
            return
        gid = str(interaction.guild_id)
        cid = str(canal.id)
        await async_get_or_create_guild_config(gid)
        await aexecute("UPDATE guild_config SET applications_channel_id=$1, updated_at=NOW() WHERE guild_id=$2", (cid, gid))
        
        # Sync with application_config table as well
        existing_app_cfg = await aexecute("SELECT id FROM application_config WHERE guild_id=$1", (gid,), fetch="one")
        if existing_app_cfg:
            await aexecute("UPDATE application_config SET log_channel_id=$1, updated_at=NOW() WHERE guild_id=$2", (cid, gid))
        else:
            await aexecute("INSERT INTO application_config (id, guild_id, log_channel_id, created_at, updated_at) VALUES ($1,$2,$3,NOW(),NOW())", (generate_id(), gid, cid))

        await interaction.followup.send(embed=success_embed("Canal de Postulaciones Configurado", f"Las solicitudes de departamentos se enviarán a {canal.mention}"), ephemeral=True)

    @admin_cfg.command(name="solicitud", description="Alias: Configurar canal para postulaciones y solicitudes")
    @app_commands.describe(canal="Canal donde se enviarán las postulaciones")
    async def cfg_solicitud(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await self.cfg_canal_postulaciones(interaction, canal)

    @admin_cfg.command(name="canal_solicitudes", description="Alias: Configurar canal para postulaciones a departamentos")
    @app_commands.describe(canal="Canal donde se enviarán las solicitudes")
    async def cfg_canal_solicitudes(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await self.cfg_canal_postulaciones(interaction, canal)


    @admin_cfg.command(name="diario", description="Configurar cantidad de /diario")
    @app_commands.describe(cantidad="Cantidad nueva")
    async def cfg_diario(self, interaction: discord.Interaction, cantidad: int):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        await async_get_or_create_guild_config(str(interaction.guild_id))
        await aexecute("UPDATE guild_config SET daily_amount=$1, updated_at=NOW() WHERE guild_id=$2", (cantidad, str(interaction.guild_id)))
        await interaction.followup.send(embed=success_embed("Configurado", f"Recompensa diaria actualizada a **{format_currency(cantidad)}**"), ephemeral=True)

    @admin_cfg.command(name="semanal", description="Configurar cantidad de /semanal")
    @app_commands.describe(cantidad="Cantidad nueva")
    async def cfg_semanal(self, interaction: discord.Interaction, cantidad: int):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        await async_get_or_create_guild_config(str(interaction.guild_id))
        await aexecute("UPDATE guild_config SET weekly_amount=$1, updated_at=NOW() WHERE guild_id=$2", (cantidad, str(interaction.guild_id)))
        await interaction.followup.send(embed=success_embed("Configurado", f"Recompensa semanal actualizada a **{format_currency(cantidad)}**"), ephemeral=True)

    @admin_cfg.command(name="canal_log", description="Configurar canal de logs del servidor")
    @app_commands.describe(canal="Canal de texto para logs")
    async def cfg_canal_log(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        await async_get_or_create_guild_config(str(interaction.guild_id))
        await aexecute("UPDATE guild_config SET log_channel_id=$1, updated_at=NOW() WHERE guild_id=$2", (str(canal.id), str(interaction.guild_id)))
        await interaction.followup.send(embed=success_embed("Canal configurado", f"Canal de logs: {canal.mention}"), ephemeral=True)

    @admin_cfg.command(name="verificacion", description="Configurar sistema de verificación")
    @app_commands.describe(rol="Rol de verificado", canal_log="Canal de logs", edad_minima="Edad mínima de cuenta en días")
    async def cfg_verificacion(self, interaction: discord.Interaction, rol: discord.Role = None, canal_log: discord.TextChannel = None, edad_minima: int = None):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        existing = await aexecute("SELECT id FROM verification_config WHERE guild_id=$1", (str(interaction.guild_id),), fetch="one")
        if existing:
            if rol:
                await aexecute("UPDATE verification_config SET verified_role_id=$1, updated_at=NOW() WHERE guild_id=$2", (str(rol.id), str(interaction.guild_id)))
            if canal_log:
                await aexecute("UPDATE verification_config SET log_channel_id=$1, updated_at=NOW() WHERE guild_id=$2", (str(canal_log.id), str(interaction.guild_id)))
            if edad_minima is not None:
                await aexecute("UPDATE verification_config SET min_account_age_days=$1, updated_at=NOW() WHERE guild_id=$2", (edad_minima, str(interaction.guild_id)))
        else:
            await aexecute(
                "INSERT INTO verification_config (id, guild_id, verified_role_id, log_channel_id, min_account_age_days, created_at, updated_at) VALUES ($1,$2,$3,$4,$5,NOW(),NOW())",
                (generate_id(), str(interaction.guild_id), str(rol.id) if rol else None, str(canal_log.id) if canal_log else None, edad_minima or 7)
            )
        changes = []
        if rol: changes.append(f"Rol: {rol.mention}")
        if canal_log: changes.append(f"Log: {canal_log.mention}")
        if edad_minima is not None: changes.append(f"Edad mínima: {edad_minima} días")
        await interaction.followup.send(embed=success_embed("Verificación configurada", "\n".join(changes) or "Sin cambios"), ephemeral=True)

    @admin_cfg.command(name="ver", description="Ver todas las configuraciones actuales del servidor")
    async def cfg_ver(self, interaction: discord.Interaction):
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        import asyncio
        (cfg, ver_cfg, tick_cfg, app_cfg, treasury,
         dept_count_row, company_count_row, prop_count_row,
         player_count_row, shop_count_row, bm_count_row, reward_count_row) = await asyncio.gather(
            aexecute("SELECT * FROM guild_config WHERE guild_id=$1", (gid,), fetch="one"),
            aexecute("SELECT * FROM verification_config WHERE guild_id=$1", (gid,), fetch="one"),
            aexecute("SELECT * FROM ticket_config WHERE guild_id=$1", (gid,), fetch="one"),
            aexecute("SELECT * FROM application_config WHERE guild_id=$1", (gid,), fetch="one"),
            aexecute("SELECT balance FROM treasury WHERE guild_id=$1", (gid,), fetch="one"),
            aexecute("SELECT COUNT(*) as c FROM departments WHERE guild_id=$1", (gid,), fetch="one"),
            aexecute("SELECT COUNT(*) as c FROM companies WHERE guild_id=$1", (gid,), fetch="one"),
            aexecute("SELECT COUNT(*) as c FROM properties WHERE guild_id=$1", (gid,), fetch="one"),
            aexecute("SELECT COUNT(*) as c FROM users WHERE guild_id=$1", (gid,), fetch="one"),
            aexecute("SELECT COUNT(*) as c FROM shop WHERE guild_id=$1", (gid,), fetch="one"),
            aexecute("SELECT COUNT(*) as c FROM black_market_stock WHERE quantity > 0", fetch="one"),
            aexecute("SELECT COUNT(*) as c FROM level_rewards WHERE guild_id=$1", (gid,), fetch="one"),
        )
        cfg = cfg or {}
        ver_cfg = ver_cfg or {}
        tick_cfg = tick_cfg or {}
        app_cfg = app_cfg or {}
        treasury = treasury or {}
        dept_count = (dept_count_row or {}).get("c", 0)
        company_count = (company_count_row or {}).get("c", 0)
        prop_count = (prop_count_row or {}).get("c", 0)
        player_count = (player_count_row or {}).get("c", 0)
        shop_count = (shop_count_row or {}).get("c", 0)
        bm_count = (bm_count_row or {}).get("c", 0)
        reward_count = (reward_count_row or {}).get("c", 0)

        e = info_embed(f"⚙️ Configuración de {interaction.guild.name}", "Resumen completo del servidor para administradores")
        log_ch = f"<#{cfg.get('log_channel_id')}>" if cfg.get("log_channel_id") else "No configurado"
        e.add_field(name="💰 Economía", value=(
            f"Diario: **{format_currency(cfg.get('daily_amount', 500))}**\n"
            f"Semanal: **{format_currency(cfg.get('weekly_amount', 2500))}**\n"
            f"Impuesto: **{cfg.get('tax_rate', 5)}%**\n"
            f"Mult. XP: **{cfg.get('xp_multiplier', 1.0)}x**\n"
            f"Canal log: {log_ch}"
        ), inline=True)
        treas_bal = format_currency(treasury.get("balance", 0)) if treasury else "**$0** (sin inicializar)"
        e.add_field(name="🏛️ Tesoro & Stats", value=(
            f"Tesoro: **{treas_bal}**\n"
            f"Jugadores: **{player_count}**\n"
            f"Departamentos: **{dept_count}**\n"
            f"Empresas: **{company_count}**\n"
            f"Propiedades: **{prop_count}**"
        ), inline=True)
        ver_role = f"<@&{ver_cfg.get('verified_role_id')}>" if ver_cfg.get("verified_role_id") else "No config."
        ver_log = f"<#{ver_cfg.get('log_channel_id')}>" if ver_cfg.get("log_channel_id") else "No config."
        e.add_field(name="✅ Verificación", value=(
            f"Rol verificado: {ver_role}\n"
            f"Canal log: {ver_log}\n"
            f"Edad mínima: **{ver_cfg.get('min_account_age_days', 7)} días**"
        ) if ver_cfg else "❌ Sin configurar — usa `/admin configuracion verificacion`", inline=True)
        tick_cat = f"**{tick_cfg.get('category_id', 'N/A')}**" if tick_cfg.get("category_id") else "No config."
        tick_rol = f"<@&{tick_cfg.get('support_role_id')}>" if tick_cfg.get("support_role_id") else "No config."
        e.add_field(name="🎫 Tickets", value=(
            f"Categoría ID: {tick_cat}\n"
            f"Rol soporte: {tick_rol}"
        ) if tick_cfg else "❌ Sin configurar — usa `/admin configuracion tickets`", inline=True)
        app_log = f"<#{app_cfg.get('log_channel_id')}>" if app_cfg.get("log_channel_id") else "No config."
        e.add_field(name="📋 Solicitudes", value=(f"Canal log: {app_log}") if app_cfg else "❌ Sin configurar", inline=True)
        e.add_field(name="🛍️ Tienda & Mercado", value=(
            f"Objetos en tienda: **{shop_count}**\n"
            f"Stock mercado negro: **{bm_count}** items activos\n"
            f"Recompensas de nivel: **{reward_count}**"
        ), inline=True)
        e.set_footer(text=f"ID del servidor: {gid}")
        await interaction.followup.send(embed=e, ephemeral=True)

    @admin_cfg.command(name="tickets", description="Configurar el sistema de tickets")
    @app_commands.describe(categoria="Categoría de Discord para tickets", rol_soporte="Rol de soporte")
    async def cfg_tickets(self, interaction: discord.Interaction, categoria: discord.CategoryChannel = None, rol_soporte: discord.Role = None):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        existing = await aexecute("SELECT id FROM ticket_config WHERE guild_id=$1", (str(interaction.guild_id),), fetch="one")
        if existing:
            if categoria:
                await aexecute("UPDATE ticket_config SET category_id=$1, updated_at=NOW() WHERE guild_id=$2", (str(categoria.id), str(interaction.guild_id)))
            if rol_soporte:
                await aexecute("UPDATE ticket_config SET support_role_id=$1, updated_at=NOW() WHERE guild_id=$2", (str(rol_soporte.id), str(interaction.guild_id)))
        else:
            await aexecute(
                "INSERT INTO ticket_config (id, guild_id, category_id, support_role_id, created_at, updated_at) VALUES ($1,$2,$3,$4,NOW(),NOW())",
                (generate_id(), str(interaction.guild_id), str(categoria.id) if categoria else None, str(rol_soporte.id) if rol_soporte else None)
            )
        changes = []
        if categoria: changes.append(f"Categoría: **{categoria.name}**")
        if rol_soporte: changes.append(f"Soporte: {rol_soporte.mention}")
        await interaction.followup.send(embed=success_embed("Tickets configurados", "\n".join(changes) or "Sin cambios"), ephemeral=True)

    adminshop = app_commands.Group(name="adminshop", description="Gestión de la tienda")

    @adminshop.command(name="agregar", description="Agregar objeto a la tienda")
    @app_commands.describe(objeto="Nombre del objeto", precio="Precio de venta", stock="Stock (-1 = infinito)")
    async def shop_agregar(self, interaction: discord.Interaction, objeto: str, precio: int, stock: int = -1):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        item = await aexecute("SELECT * FROM items WHERE name ILIKE $1 AND is_active=true LIMIT 1", (f"%{objeto}%",), fetch="one")
        if not item:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Objeto **{objeto}** no existe. Créalo primero con `/admin objetos crear`"), ephemeral=True)
            return
        existing = await aexecute("SELECT id FROM shop WHERE guild_id=$1 AND item_id=$2", (str(interaction.guild_id), item["id"]), fetch="one")
        if existing:
            await aexecute("UPDATE shop SET price=$1, stock=$2, updated_at=NOW() WHERE id=$3", (precio, stock, existing["id"]))
            await interaction.followup.send(embed=success_embed("Tienda actualizada", f"**{item['name']}** — {format_currency(precio)} (stock: {'∞' if stock==-1 else stock})"), ephemeral=True)
            return
        await aexecute(
            """INSERT INTO shop (id, guild_id, item_id, price, stock, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,NOW(),NOW())""",
            (generate_id(), str(interaction.guild_id), item["id"], precio, stock)
        )
        await interaction.followup.send(embed=success_embed("Objeto añadido a tienda", f"**{item['name']}** — {format_currency(precio)}"), ephemeral=True)

    @adminshop.command(name="quitar", description="Quitar objeto de la tienda")
    @app_commands.describe(objeto="Nombre del objeto")
    async def shop_quitar(self, interaction: discord.Interaction, objeto: str):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        item = await aexecute("SELECT * FROM items WHERE name ILIKE $1 LIMIT 1", (f"%{objeto}%",), fetch="one")
        if not item:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Objeto **{objeto}** no existe"), ephemeral=True)
            return
        await aexecute("DELETE FROM shop WHERE guild_id=$1 AND item_id=$2", (str(interaction.guild_id), item["id"]))
        await interaction.followup.send(embed=success_embed("Objeto quitado", f"**{item['name']}** eliminado de la tienda"), ephemeral=True)

    @adminshop.command(name="predeterminados", description="Cargar el catálogo legal de objetos en la tienda normal")
    async def shop_defaults(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return

        names = [it["name"] for it in SHOP_ITEMS]
        placeholders = ", ".join(f"${i+1}" for i in range(len(names)))
        existing_rows = await aexecute(
            f"SELECT id, name FROM items WHERE name IN ({placeholders}) AND is_active=true",
            tuple(names), fetch="all"
        ) or []
        existing_map = {r["name"]: r["id"] for r in existing_rows}

        new_items = [it for it in SHOP_ITEMS if it["name"] not in existing_map]
        new_ids = {it["name"]: generate_id() for it in new_items}

        if new_items:
            insert_queries = [
                (
                    """INSERT INTO items (id, name, category, rarity, price, emoji, is_active, black_market_only, created_at, updated_at)
                       VALUES ($1,$2,$3,$4,$5,$6,true,false,NOW(),NOW()) ON CONFLICT DO NOTHING""",
                    (new_ids[it["name"]], it["name"], it["category"], it["rarity"], it["price"], it["emoji"])
                )
                for it in new_items
            ]
            await aexecute_many(insert_queries)

        if existing_map:
            update_queries = [
                ("UPDATE items SET black_market_only=false, updated_at=NOW() WHERE id=$1", (iid,))
                for iid in existing_map.values()
            ]
            await aexecute_many(update_queries)

        all_ids = {**existing_map, **new_ids}
        all_item_ids = list(all_ids.values())
        placeholders2 = ", ".join(f"${i+2}" for i in range(len(all_item_ids)))
        shop_rows = await aexecute(
            f"SELECT item_id FROM shop WHERE guild_id=$1 AND item_id IN ({placeholders2})",
            tuple([str(interaction.guild_id)] + all_item_ids), fetch="all"
        ) or []
        shop_existing = {r["item_id"] for r in shop_rows}

        shop_inserts = [
            (
                """INSERT INTO shop (id, guild_id, item_id, price, stock, created_at, updated_at)
                   VALUES ($1,$2,$3,$4,-1,NOW(),NOW()) ON CONFLICT DO NOTHING""",
                (generate_id(), str(interaction.guild_id), iid, next(it["price"] for it in SHOP_ITEMS if all_ids[it["name"]] == iid))
            )
            for name, iid in all_ids.items()
            if iid not in shop_existing
        ]
        if shop_inserts:
            await aexecute_many(shop_inserts)

        await interaction.followup.send(embed=success_embed(
            "🛍️ Tienda cargada",
            f"**{len(new_items)}** objetos nuevos creados\n**{len(shop_inserts)}** añadidos a la tienda\n\nTotal catálogo: **{len(SHOP_ITEMS)} objetos legales**"
        ), ephemeral=True)

    @adminshop.command(name="mercadonegro", description="Cargar el catálogo ilegal exclusivo del mercado negro")
    async def shop_blackmarket_defaults(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return

        names = [it["name"] for it in BLACK_MARKET_ITEMS]
        placeholders = ", ".join(f"${i+1}" for i in range(len(names)))
        existing_rows = await aexecute(
            f"SELECT id, name FROM items WHERE name IN ({placeholders}) AND is_active=true",
            tuple(names), fetch="all"
        ) or []
        existing_map = {r["name"]: r["id"] for r in existing_rows}

        new_items = [it for it in BLACK_MARKET_ITEMS if it["name"] not in existing_map]
        new_ids = {it["name"]: generate_id() for it in new_items}

        if new_items:
            insert_queries = [
                (
                    """INSERT INTO items (id, name, category, rarity, price, emoji, is_active, black_market_only, created_at, updated_at)
                       VALUES ($1,$2,$3,$4,$5,$6,true,true,NOW(),NOW()) ON CONFLICT DO NOTHING""",
                    (new_ids[it["name"]], it["name"], it["category"], it["rarity"], it["price"], it["emoji"])
                )
                for it in new_items
            ]
            await aexecute_many(insert_queries)

        if existing_map:
            update_queries = [
                ("UPDATE items SET black_market_only=true, updated_at=NOW() WHERE id=$1", (iid,))
                for iid in existing_map.values()
            ]
            await aexecute_many(update_queries)

        all_ids = {**existing_map, **new_ids}
        all_item_ids = list(all_ids.values())
        placeholders2 = ", ".join(f"${i+1}" for i in range(len(all_item_ids)))
        bm_rows = await aexecute(
            f"SELECT item_id FROM black_market_stock WHERE item_id IN ({placeholders2})",
            tuple(all_item_ids), fetch="all"
        ) or []
        bm_existing = {r["item_id"] for r in bm_rows}

        bm_inserts = [
            (
                """INSERT INTO black_market_stock (id, item_id, price_modifier, quantity, created_at, updated_at)
                   VALUES ($1,$2,$3,$4,NOW(),NOW()) ON CONFLICT DO NOTHING""",
                (generate_id(), iid, round(random.uniform(1.0, 1.8), 2), random.randint(1, 8))
            )
            for iid in all_ids.values()
            if iid not in bm_existing
        ]
        if bm_inserts:
            await aexecute_many(bm_inserts)

        await interaction.followup.send(embed=success_embed(
            "🕶️ Mercado Negro cargado",
            f"**{len(new_items)}** objetos ilegales creados\n**{len(bm_inserts)}** añadidos al stock del mercado negro\n\nTotal catálogo: **{len(BLACK_MARKET_ITEMS)} objetos ilegales**\n\nEl stock se rota automáticamente cada 6 horas."
        ), ephemeral=True)

    tesoro_group = app_commands.Group(name="tesoro", description="Gestión del tesoro")

    @tesoro_group.command(name="info", description="Ver el estado del tesoro")
    async def tesoro_info(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        treasury = await aexecute("SELECT * FROM treasury WHERE guild_id=$1", (str(interaction.guild_id),), fetch="one")
        e = info_embed("🏛️ Tesoro del Servidor")
        if not treasury:
            e.description = "No hay tesoro configurado. Úsalo para gestionar fondos de gobierno."
            e.add_field(name="💰 Fondos", value="$0", inline=True)
        else:
            e.add_field(name="💰 Fondos", value=format_currency(treasury.get("balance",0)), inline=True)
        await interaction.followup.send(embed=e, ephemeral=True)

    @tesoro_group.command(name="depositar", description="Depositar fondos al tesoro")
    @app_commands.describe(cantidad="Cantidad")
    async def tesoro_depositar(self, interaction: discord.Interaction, cantidad: int):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        treasury = await aexecute("SELECT * FROM treasury WHERE guild_id=$1", (str(interaction.guild_id),), fetch="one")
        if treasury:
            await aexecute("UPDATE treasury SET balance=balance+$1, updated_at=NOW() WHERE guild_id=$2", (cantidad, str(interaction.guild_id)))
        else:
            await aexecute(
                "INSERT INTO treasury (id, guild_id, balance, created_at, updated_at) VALUES ($1,$2,$3,NOW(),NOW())",
                (generate_id(), str(interaction.guild_id), cantidad)
            )
        await interaction.followup.send(embed=success_embed("Fondos depositados", f"Se depositaron **{format_currency(cantidad)}** al tesoro"), ephemeral=True)

    @tesoro_group.command(name="financiar", description="Financiar un departamento desde el tesoro")
    @app_commands.describe(acronimo="Acrónimo del departamento", cantidad="Cantidad")
    async def tesoro_financiar(self, interaction: discord.Interaction, acronimo: str, cantidad: int):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        treasury = await aexecute("SELECT * FROM treasury WHERE guild_id=$1", (str(interaction.guild_id),), fetch="one")
        if not treasury or (treasury.get("balance",0) or 0) < cantidad:
            await interaction.followup.send(embed=error_embed("Sin fondos", "El tesoro no tiene fondos suficientes"), ephemeral=True)
            return
        dept = await aexecute("SELECT * FROM departments WHERE guild_id=$1 AND acronym ILIKE $2", (str(interaction.guild_id), acronimo), fetch="one")
        if not dept:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Departamento **{acronimo}** no existe"), ephemeral=True)
            return
        await aexecute("UPDATE treasury SET balance=balance-$1, updated_at=NOW() WHERE guild_id=$2", (cantidad, str(interaction.guild_id)))
        await aexecute("UPDATE departments SET budget=budget+$1, updated_at=NOW() WHERE id=$2", (cantidad, dept["id"]))
        await interaction.followup.send(embed=success_embed("Departamento financiado", f"**{format_currency(cantidad)}** transferidos al **{dept['name']}**"), ephemeral=True)

    solicitar_group = app_commands.Group(name="solicitar", description="Sistema de solicitudes")

    @solicitar_group.command(name="aplicar", description="Solicitar unirse a un departamento o equipo")
    @app_commands.describe(tipo="Tipo de solicitud")
    @app_commands.choices(tipo=[
        app_commands.Choice(name="👮 MPD (Miami Police Dept)", value="MPD"),
        app_commands.Choice(name="🚒 MDFR (Miami-Dade Fire & Rescue)", value="MDFR"),
        app_commands.Choice(name="🚔 FHP (Florida Highway Patrol)", value="FHP"),
        app_commands.Choice(name="🚧 FDOT (Florida Dept of Transportation)", value="FDOT"),
        app_commands.Choice(name="🏖️ MBPD (Miami Beach Police)", value="MBPD"),
        app_commands.Choice(name="⚖️ FDOJ (Florida Dept of Justice)", value="FDOJ"),
        app_commands.Choice(name="⭐ Sheriff (Miami-Dade)", value="Sheriff"),
        app_commands.Choice(name="🛠️ Staff", value="Staff"),
    ])
    async def solicitar_aplicar(self, interaction: discord.Interaction, tipo: str):
        modal = ApplicationModal(tipo)
        await interaction.response.send_modal(modal)

    @solicitar_group.command(name="lista", description="Ver solicitudes pendientes (admin)")
    async def solicitar_lista(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        apps = await aexecute(
            "SELECT * FROM applications WHERE guild_id=$1 AND status='pending' ORDER BY created_at DESC LIMIT 10",
            (str(interaction.guild_id),), fetch="all"
        ) or []
        e = info_embed("📋 Solicitudes pendientes")
        if not apps:
            e.description = "No hay solicitudes pendientes"
        else:
            lines = [f"<@{a['discord_id']}> — **{a.get('type','?')}** (`{a['id'][:8]}`) — <t:{int(a['created_at'].timestamp()) if hasattr(a['created_at'],'timestamp') else 0}:R>" for a in apps]
            e.description = "\n".join(lines)
        await interaction.followup.send(embed=e, ephemeral=True)

    contrato_group = app_commands.Group(name="contrato", description="Sistema de contratos")

    @contrato_group.command(name="lista", description="Ver contratos disponibles")
    async def contrato_lista(self, interaction: discord.Interaction):
        await interaction.response.defer()
        contracts = await aexecute(
            "SELECT * FROM contracts WHERE guild_id=$1 AND status='open' ORDER BY reward DESC LIMIT 10",
            (str(interaction.guild_id),), fetch="all"
        ) or []
        e = info_embed("📜 Contratos disponibles")
        if not contracts:
            e.description = "No hay contratos disponibles"
        else:
            for c in contracts:
                e.add_field(
                    name=f"📋 {c.get('title','Contrato')}",
                    value=f"Recompensa: **{format_currency(c.get('reward',0))}**\n{c.get('description','')[:80]}\n`ID: {c['id'][:8]}`",
                    inline=True
                )
        await interaction.followup.send(embed=e)

    @contrato_group.command(name="crear", description="Crear un contrato (admin)")
    @app_commands.describe(titulo="Título", descripcion="Descripción", recompensa="Recompensa en cash")
    async def contrato_crear(self, interaction: discord.Interaction, titulo: str, descripcion: str, recompensa: int):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        await aexecute(
            """INSERT INTO contracts (id, guild_id, creator_id, title, description, reward, status, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,'open',NOW(),NOW())""",
            (generate_id(), str(interaction.guild_id), str(interaction.user.id), titulo, descripcion, recompensa)
        )
        await interaction.followup.send(embed=success_embed(f"📜 Contrato creado — {titulo}", f"Recompensa: **{format_currency(recompensa)}**"), ephemeral=True)

    @contrato_group.command(name="aceptar", description="Aceptar un contrato")
    @app_commands.describe(id_contrato="ID del contrato")
    async def contrato_aceptar(self, interaction: discord.Interaction, id_contrato: str):
        await interaction.response.defer()
        contract = await aexecute(
            "SELECT * FROM contracts WHERE guild_id=$1 AND status='open' AND id LIKE $2",
            (str(interaction.guild_id), f"{id_contrato}%"), fetch="one"
        )
        if not contract:
            await interaction.followup.send(embed=error_embed("No encontrado", "Contrato no encontrado o no disponible"), ephemeral=True)
            return
        await aexecute(
            "UPDATE contracts SET status='active', assignee_id=$1, updated_at=NOW() WHERE id=$2",
            (str(interaction.user.id), contract["id"])
        )
        await interaction.followup.send(embed=success_embed(f"📜 Contrato aceptado — {contract['title']}", f"Complétalo para ganar **{format_currency(contract['reward'])}**"))

    @contrato_group.command(name="completar", description="Marcar un contrato como completado (admin)")
    @app_commands.describe(id_contrato="ID del contrato")
    async def contrato_completar(self, interaction: discord.Interaction, id_contrato: str):
        await interaction.response.defer()
        if not await admin_check(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        contract = await aexecute(
            "SELECT * FROM contracts WHERE guild_id=$1 AND status='active' AND id LIKE $2",
            (str(interaction.guild_id), f"{id_contrato}%"), fetch="one"
        )
        if not contract:
            await interaction.followup.send(embed=error_embed("No encontrado", "Contrato activo no encontrado"), ephemeral=True)
            return
        await aexecute("UPDATE contracts SET status='completed', updated_at=NOW() WHERE id=$1", (contract["id"],))
        if contract.get("assignee_id"):
            await async_add_cash(contract["assignee_id"], str(interaction.guild_id), contract["reward"])
            await async_log_transaction(contract["assignee_id"], str(interaction.guild_id), "contract_reward", contract["reward"], f"Contrato: {contract['title']}")
        await interaction.followup.send(embed=success_embed("Contrato completado", f"**{contract['title']}** — Recompensa de **{format_currency(contract['reward'])}** entregada"))


class ApplicationModal(discord.ui.Modal):
    def __init__(self, dept_type: str):
        super().__init__(title=f"Solicitud — {dept_type}")
        self.dept_type = dept_type
        self.experience = discord.ui.TextInput(
            label="Experiencia relevante",
            placeholder="Describe tu experiencia...",
            style=discord.TextStyle.paragraph,
            max_length=500
        )
        self.motivation = discord.ui.TextInput(
            label="Motivación",
            placeholder="¿Por qué quieres unirte?",
            style=discord.TextStyle.paragraph,
            max_length=300
        )
        self.add_item(self.experience)
        self.add_item(self.motivation)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        app_id = generate_id()
        await aexecute(
            """INSERT INTO applications (id, guild_id, discord_id, type, experience, motivation, status, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,'pending',NOW(),NOW())""",
            (app_id, str(interaction.guild_id), str(interaction.user.id), self.dept_type, self.experience.value, self.motivation.value)
        )
        config = await aexecute("SELECT * FROM application_config WHERE guild_id=$1", (str(interaction.guild_id),), fetch="one")
        if config and config.get("log_channel_id"):
            channel = interaction.guild.get_channel(int(config["log_channel_id"]))
            if channel:
                e = info_embed(f"📋 Nueva solicitud — {self.dept_type}", f"Solicitante: {interaction.user.mention}")
                e.add_field(name="Experiencia", value=self.experience.value[:500], inline=False)
                e.add_field(name="Motivación", value=self.motivation.value[:300], inline=False)
                e.set_footer(text=f"ID: {app_id[:8]}")
                view = ApplicationReviewView(app_id)
                try:
                    await channel.send(embed=e, view=view)
                except Exception:
                    pass
        await interaction.followup.send(embed=success_embed("Solicitud enviada", f"Tu solicitud para **{self.dept_type}** fue enviada. Espera respuesta."), ephemeral=True)


class ApplicationReviewView(discord.ui.View):
    def __init__(self, app_id: str):
        super().__init__(timeout=None)
        self.app_id = app_id

    @discord.ui.button(label="✅ Aprobar", style=discord.ButtonStyle.success, custom_id="app_approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Sin permisos"), ephemeral=True)
            return
        await aexecute("UPDATE applications SET status='approved', reviewed_by=$1, updated_at=NOW() WHERE id=$2", (str(interaction.user.id), self.app_id))
        await interaction.followup.send(embed=success_embed("Solicitud aprobada", f"ID: `{self.app_id[:8]}`"), ephemeral=True)

    @discord.ui.button(label="❌ Rechazar", style=discord.ButtonStyle.danger, custom_id="app_deny")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Sin permisos"), ephemeral=True)
            return
        await aexecute("UPDATE applications SET status='denied', reviewed_by=$1, updated_at=NOW() WHERE id=$2", (str(interaction.user.id), self.app_id))
        await interaction.followup.send(embed=success_embed("Solicitud rechazada", f"ID: `{self.app_id[:8]}`"), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Admin(bot))
