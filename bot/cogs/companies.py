"""Gestion de empresas privadas: `/empresa ...`.

Este cog es la capa de comandos. Toda la economia vive en
`bot.services.business` y toda la presentacion en `bot.services.business_ui`:
aqui solo se traducen clicks y argumentos a llamadas del motor, y se traducen
sus excepciones a mensajes. Ninguna sentencia economica se escribe aqui.

Jerarquia de poder
------------------
    dueno      -> todo (precios, salarios, nomina, caja, acciones, estado)
    gerente    -> casi todo menos `shares`, `config` y `withdraw`
    permisos   -> hire, positions, menu, payroll, finance, config...
    empleado   -> cobrar (/sueldo no le toca: paga el dueno) y comprar
    cliente    -> comprar y usar el menu

Los precios de productos, servicios y acciones, y los salarios, los define el
dueno. El dinero sale siempre de una cuenta real: si falta, la operacion se
rechaza; nunca se crea.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.db import aexecute
from bot.embeds import error_embed, info_embed, success_embed, warning_embed
from bot.helpers import async_get_or_create_guild_config, async_get_or_create_user
from bot.services import business as B
from bot.services import business_ui as UI

logger = logging.getLogger("bot.companies")

# Bloqueo anti-doble clic por ciudadano y accion (segundos).
ACTION_COOLDOWN = 3.0
VIEW_TIMEOUT = 180.0


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


async def _resolve_company(interaction, name: str, create_if_missing: bool = False):
    """Localiza la empresa por nombre, nombre propio o id."""
    guild_id = str(interaction.guild_id)
    query = (name or "").strip()
    if not query:
        return await B.get_managed_company(guild_id, str(interaction.user.id))
    company = await B.find_company(guild_id, query)
    if company or not create_if_missing:
        return company
    mine = await B.get_owned_company(guild_id, str(interaction.user.id))
    if mine and str(query) == str(mine["id"]):
        return mine
    return None


async def _deny(interaction, title: str, message: str):
    embed = error_embed(title, message)
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def _report(interaction, error: Exception):
    """Convierte una excepcion del motor en un mensaje util."""
    if isinstance(error, B.InsufficientFunds):
        detail = getattr(error, "detail", None)
        if detail:
            await interaction.followup.send(embed=UI.deficit_embed(error), ephemeral=True)
            return
        embed = error_embed(
            "Fondos insuficientes",
            f"{getattr(error, 'message', str(error))}\n"
            f"Necesitas **{UI.money(getattr(error, 'required', 0))}** y hay "
            f"**{UI.money(getattr(error, 'available', 0))}**.",
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return
    if isinstance(error, B.BusinessError):
        await interaction.followup.send(embed=error_embed("Operación imposible", str(error)),
                                         ephemeral=True)
        return
    if isinstance(error, B.ActionInProgress):
        await interaction.followup.send(embed=warning_embed("Un momento", str(error)),
                                         ephemeral=True)
        return
    logger.error("[Empresa] Error no controlado: %s", error, exc_info=True)
    await interaction.followup.send(
        embed=error_embed("Error interno", "Ha ocurrido un error inesperado. Revisa los registros."),
        ephemeral=True,
    )


async def _guard(interaction, action: str):
    """Anti-doble pulsacion: una accion por ciudadano cada pocos segundos."""
    try:
        await B.claim_action(f"empresa:{interaction.guild_id}:{interaction.user.id}:{action}",
                             ACTION_COOLDOWN)
    except B.ActionInProgress as locked:
        await _deny(interaction, "Espera", str(locked))
        return False
    return True


# ---------------------------------------------------------------------------
# Callbacks de los modales de business_ui
# ---------------------------------------------------------------------------


async def create_company_flow(interaction: discord.Interaction, modal, cost: int):
    """Da de alta la empresa y descuenta la licencia en una sola transaccion."""
    await interaction.response.defer(ephemeral=True)
    guild_id = str(interaction.guild_id)
    user_id = str(interaction.user.id)
    name = modal.children[0].value.strip()
    description = modal.children[1].value.strip()
    category = modal.children[2].value.strip() or "Negocio"
    location = modal.children[3].value.strip() or "Sin ubicación"
    tax_rate = max(0, min(100, UI._int_value(modal.children[4].value, 5)))
    # El modal se queda en 5 campos (limite de Discord): el emoji se deduce
    # del sector que ha elegido el dueno.
    emoji = UI.sector_emoji(category)

    await async_get_or_create_user(user_id, guild_id, interaction.user.name, interaction.user.display_name)
    try:
        company_id, cost_paid = await B.create_company(
            guild_id, user_id, name, description, category, location, emoji, tax_rate)
    except Exception as error:
        await _report(interaction, error)
        return

    embed = success_embed(
        f"\U0001F3E2 {name} ya existe",
        f"Has fundado tu empresa. La licencia te ha costado "
        f"**{UI.money(cost_paid)}** de tu efectivo.",
    )
    embed.add_field(name="Sector", value=f"{category} · {location}", inline=True)
    embed.add_field(name="Impuestos", value=f"{tax_rate}%", inline=True)
    embed.add_field(name="Caja inicial", value=UI.money(0), inline=True)
    embed.set_footer(text="Empieza creando tus puestos y tu menú desde /empresa panel")
    await interaction.followup.send(embed=embed, ephemeral=True)


async def run_amount_action(interaction: discord.Interaction, action: str, company_id: str,
                             amount: int, reason: str):
    """Aportar, retirar, pagar un gasto o repartir un dividendo."""
    guild_id = str(interaction.guild_id)
    user_id = str(interaction.user.id)
    await interaction.response.defer(ephemeral=True)
    if not await B.require_access(interaction, company_id, owner_only=True):
        return
    try:
        if action == "deposit":
            result = await B.owner_deposit(guild_id, company_id, user_id, amount, kind="deposit")
            title, balance = "Capital aportado", result["balance_after"]
        elif action == "investment":
            result = await B.owner_deposit(guild_id, company_id, user_id, amount, kind="investment")
            title, balance = "Inversión realizada", result["balance_after"]
        elif action == "withdraw":
            result = await B.owner_withdraw(guild_id, company_id, user_id, amount)
            title, balance = "Retiro realizado", result["balance_after"]
        elif action == "expense":
            await B.pay_expense(guild_id, company_id, user_id, amount, reason or "Gasto")
            company = await B.get_company(company_id, guild_id)
            title, balance = "Gasto registrado", B.money(company.get("funds"))
        elif action == "dividend":
            result = await B.pay_dividends(guild_id, company_id, user_id, amount, reason)
            title, balance = "Dividendo repartido", result["balance_after"]
            lines = "\n".join(
                f"<@{p['discord_id']}> → **{UI.money(p['amount'])}** ({p['percent']:.1f}%)"
                for p in result["payments"]
            )
            embed = success_embed(f"\U0001F4B0 {title}",
                                  f"Repartido **{UI.money(result['paid'])}** desde la caja real.\n\n{lines}")
            embed.add_field(name="Caja restante", value=UI.money(balance), inline=True)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        else:
            await _deny(interaction, "Acción desconocida", action)
            return
    except Exception as error:
        await _report(interaction, error)
        return

    embed = success_embed(f"\U0001F4B0 {title}", f"Importe: **{UI.money(amount)}**")
    embed.add_field(name="Caja de la empresa", value=UI.money(balance), inline=True)
    await interaction.followup.send(embed=embed, ephemeral=True)


async def save_position(interaction: discord.Interaction, company_id: str, position, name: str,
                        salary: int, role_id, max_count: int, perms: str):
    """Alta o edicion de un puesto definido por el dueno."""
    await interaction.response.defer(ephemeral=True)
    if not await B.require_access(interaction, company_id, owner_only=True):
        return
    requested = B._clean_perms(perms)
    unknown = requested - set(B.PERMISSIONS.keys())
    if unknown:
        await _deny(interaction, "Permisos desconocidos",
                    f"No existen estos permisos: {', '.join(sorted(unknown))}. "
                    f"Disponibles: {', '.join(sorted(B.PERMISSIONS.keys()))}.")
        return
    if role_id and interaction.guild.get_role(int(role_id)) is None:
        await _deny(interaction, "Rol inexistente", "Ese rol no existe en este servidor.")
        return
    guild_id = str(interaction.guild_id)
    try:
        if position:
            await aexecute(
                """UPDATE company_positions SET name=$1, salary=$2, discord_role_id=$3,
                   permissions=$4, max_members=$5, updated_at=NOW()
                   WHERE id=$6 AND company_id=$7""",
                (name, salary, role_id, B.encode_perms(requested), max(0, max_count),
                 position["id"], company_id),
            )
            verb = "actualizado"
        else:
            await B.create_position(
                guild_id, company_id, name, salary, role_id=role_id,
                permissions=requested, max_members=max(0, max_count),
            )
            verb = "creado"
    except Exception as error:
        await _report(interaction, error)
        return

    embed = success_embed(f"Puesto {verb}", f"**{name}** · {UI.money(salary)} diarios")
    if role_id:
        embed.add_field(name="Rol", value=f"<@&{role_id}>", inline=True)
    if requested:
        embed.add_field(name="Permisos", value=UI.perm_summary(requested), inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)


async def save_catalog_item(interaction: discord.Interaction, company_id: str, kind: str,
                            item, name: str, price: int, description: str, role_id, emoji: str):
    """Alta o edicion de un producto o servicio del menu."""
    await interaction.response.defer(ephemeral=True)
    if not await B.require_access(interaction, company_id, permission="menu"):
        return
    guild_id = str(interaction.guild_id)
    if role_id and interaction.guild.get_role(int(role_id)) is None:
        await _deny(interaction, "Rol inexistente", "Ese rol no existe en este servidor.")
        return
    try:
        item_id, created = await B.upsert_catalog_item(
            guild_id, company_id, kind, name, price, description or "",
            emoji or ("\U0001F9FE" if kind == "product" else "✂️"),
            item_id=item["id"] if item else None, role_id=role_id)
    except Exception as error:
        await _report(interaction, error)
        return

    embed = success_embed(
        f"{'Artículo creado' if created else 'Artículo actualizado'}",
        f"{(emoji or '🍽️')} **{name}** — {UI.money(price)}")
    if role_id:
        embed.add_field(name="Rol al comprar", value=f"<@&{role_id}>", inline=True)
    await interaction.followup.send(embed=embed, ephemeral=True)


async def save_shares_config(interaction: discord.Interaction, company_id: str,
                              total_shares: int, share_price: int, founder_shares: int):
    """Configuracion del capital social por el dueno."""
    await interaction.response.defer(ephemeral=True)
    if not await B.require_access(interaction, company_id, owner_only=True):
        return
    guild_id = str(interaction.guild_id)
    try:
        result = await B.configure_shares(
            guild_id, company_id, str(interaction.user.id), total_shares,
            share_price, founder_shares=founder_shares)
    except Exception as error:
        await _report(interaction, error)
        return
    embed = success_embed(
        "\U0001F4C5 Capital social emitido",
        f"{result['total_shares']:,} acciones a {UI.money(result['share_price'])} "
        f"(capital {UI.money(result['total_shares'] * result['share_price'])}).",
    )
    if result["founder_shares"]:
        embed.add_field(name="Tu participación fundacional",
                        value=f"{result['founder_shares']:,} acciones", inline=True)
    embed.set_footer(text="El importe de las compras de acciones entra en la caja de la empresa")
    await interaction.followup.send(embed=embed, ephemeral=True)


async def publish_sale(interaction: discord.Interaction, company_id: str, price: int, note: str):
    """El dueno pone su empresa en venta."""
    await interaction.response.defer(ephemeral=True)
    if not await B.require_access(interaction, company_id, owner_only=True):
        return
    try:
        await B.list_company_for_sale(
            str(interaction.guild_id), company_id, str(interaction.user.id), price, note)
    except Exception as error:
        await _report(interaction, error)
        return
    embed = success_embed(
        "\U0001F3E7 Empresa en venta",
        f"Tu empresa esta publicada por **{UI.money(price)}**."
        f"El importe de la venta entrará en la caja del negocio, no en tu bolsillo.",
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


async def finish_hire(interaction: discord.Interaction, company_id: str, employee_id: str,
                      position_id, salary, perms: str, role_id):
    """Contratacion con permisos, puesto y rol de Discord."""
    await interaction.response.defer(ephemeral=True)
    if not await B.require_access(interaction, company_id, permission="hire"):
        return
    requested = B._clean_perms(perms)
    unknown = requested - set(B.PERMISSIONS.keys())
    if unknown:
        await _deny(interaction, "Permisos desconocidos",
                    f"No existen estos permisos: {', '.join(sorted(unknown))}.")
        return
    try:
        result = await B.hire(
            str(interaction.guild_id), company_id, employee_id, position_id, salary,
            str(interaction.user.id), role_id=role_id, permissions=requested or None)
    except Exception as error:
        await _report(interaction, error)
        return

    granted = None
    if result.get("discord_role_id"):
        try:
            granted = interaction.guild.get_role(int(result["discord_role_id"]))
        except (TypeError, ValueError):
            granted = None
    if granted:
        member = interaction.guild.get_member(int(employee_id))
        can_grant = (member
                     and (interaction.user.guild_permissions.manage_roles
                          or granted < interaction.user.top_role))
        if can_grant:
            try:
                await member.add_roles(granted, reason="Contratación en empresa")
            except discord.Forbidden:
                granted = None

    embed = success_embed(
        "Contratación registrada" if result["created"] else "Ficha actualizada",
        f"<@{employee_id}> ahora es **{result['position']}** con "
        f"{UI.money(result['salary'])} diarios.")
    if granted:
        embed.add_field(name="Rol de Discord", value=granted.mention, inline=True)
    if requested:
        embed.add_field(name="Permisos", value=UI.perm_summary(requested), inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Vistas persistentes
# ---------------------------------------------------------------------------


class CompanyPanelView(discord.ui.View):
    """Panel principal: botones que abren modales, todos con control de permisos."""

    def __init__(self, company_id: str, viewer_id: str, timeout: float = VIEW_TIMEOUT):
        super().__init__(timeout=timeout)
        self.company_id = company_id
        self.viewer_id = viewer_id
        self.add_item(discord.ui.Button(label="Aportar capital", emoji="\U0001F4E6",
                                        style=discord.ButtonStyle.success,
                                        custom_id=f"empresa:{company_id}:deposit"))
        self.add_item(discord.ui.Button(label="Retirar", emoji="\U0001F4B8",
                                        style=discord.ButtonStyle.danger,
                                        custom_id=f"empresa:{company_id}:withdraw"))
        self.add_item(discord.ui.Button(label="Gasto", emoji="\U0001F6D2",
                                        style=discord.ButtonStyle.secondary,
                                        custom_id=f"empresa:{company_id}:expense"))
        self.add_item(discord.ui.Button(label="Nómina", emoji="\U0001F4B0",
                                        style=discord.ButtonStyle.primary,
                                        custom_id=f"empresa:{company_id}:payroll"))
        self.add_item(discord.ui.Button(label="Menú", emoji="\U0001F372",
                                        style=discord.ButtonStyle.secondary,
                                        custom_id=f"empresa:{company_id}:menu"))
        self.add_item(discord.ui.Button(label="Puestos", emoji="\U0001F9D9",
                                        style=discord.ButtonStyle.secondary,
                                        custom_id=f"empresa:{company_id}:positions"))
        self.add_item(discord.ui.Button(label="Finanzas", emoji="\U0001F4CA",
                                        style=discord.ButtonStyle.secondary,
                                        custom_id=f"empresa:{company_id}:finance"))
        self.add_item(discord.ui.Button(label="Contratar", emoji="➕",
                                        style=discord.ButtonStyle.success,
                                        custom_id=f"empresa:{company_id}:hire"))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) == self.viewer_id:
            return True
        await interaction.response.send_message(
            embed=error_embed("Panel ajeno", "Usa `/empresa panel` para abrir el tuyo."),
            ephemeral=True)
        return False


class CatalogBuyView(discord.ui.View):
    """Menu de empresa: el cliente pulsa y compra. El precio lo pone el dueno."""

    def __init__(self, company_id: str, viewer_id: str, items, timeout: float = VIEW_TIMEOUT):
        super().__init__(timeout=timeout)
        self.company_id = company_id
        self.viewer_id = viewer_id
        options = []
        for item in items[:25]:
            stock = item.get("stock")
            stock_text = "ilimitado" if stock is None or stock < 0 else f"{stock} disponibles"
            options.append(discord.SelectOption(
                label=f"{item.get('name')}"[:100],
                value=item["id"],
                description=f"{UI.money(item.get('price'))} · {stock_text}"[:100],
                emoji=(item.get("emoji") or "\U0001F9FE")[:2],
            ))
        if options:
            self.add_item(discord.ui.Select(
                placeholder="Elige qué quieres comprar o contratar",
                min_values=1, max_values=1, options=options))

    async def select_callback(self, interaction: discord.Interaction):
        item_id = self.children[0].values[0]
        await interaction.response.defer(ephemeral=True)
        if not await _guard(interaction, f"buy:{item_id}"):
            return
        try:
            result = await B.purchase_item(
                str(interaction.guild_id), self.company_id, item_id, str(interaction.user.id))
        except Exception as error:
            await _report(interaction, error)
            return
        item = result["item"]
        verb = "Contratado" if result["kind"] == "service" else "Comprado"
        embed = success_embed(
            f"{item.get('emoji') or ''} {verb}".strip(),
            f"**{item.get('name')}** en **{item.get('company_name') or 'la empresa'}**.",
        )
        embed.add_field(name="Precio", value=UI.money(result["total"]), inline=True)
        embed.add_field(name="Tu efectivo", value=UI.money(result["buyer_cash_after"]), inline=True)
        embed.add_field(name="Caja de la empresa",
                        value=UI.money(result["company_balance"]), inline=True)
        embed.set_footer(text="El importe ha salido de tu cartera y entrado en la caja del negocio")
        if viewer := interaction.guild.get_member(int(interaction.user.id)):
            embed.set_thumbnail(url=viewer.display_avatar.url)
        await interaction.followup.send(embed=embed, ephemeral=True)


class MarketBuyView(discord.ui.View):
    """Mercado de empresas en venta: el precio lo fija quien vende."""

    def __init__(self, guild_id: str, viewer_id: str, listings, timeout: float = VIEW_TIMEOUT):
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.viewer_id = viewer_id
        options = [
            discord.SelectOption(
                label=f"{l.get('name')}"[:100],
                value=l["id"],
                description=f"{UI.money(l.get('sale_price'))} · caja {UI.money(l.get('funds'))}"[:100],
            )
            for l in listings[:25]
        ]
        if options:
            self.add_item(discord.ui.Select(
                placeholder="Empresa que quieres comprar",
                min_values=1, max_values=1, options=options))

    async def select_callback(self, interaction: discord.Interaction):
        company_id = self.children[0].values[0]
        await interaction.response.defer(ephemeral=True)
        if not await _guard(interaction, f"buyco:{company_id}"):
            return
        try:
            result = await B.buy_company(self.guild_id, company_id, str(interaction.user.id))
        except Exception as error:
            await _report(interaction, error)
            return
        embed = success_embed(
            f"\U0001F3E2 Eres el nuevo dueño de {result['company'].get('name')}",
            f"Has pagado **{UI.money(result['price'])}** a <@{result['seller_id']}>.",
        )
        embed.add_field(name="Caja heredada", value=UI.money(result["company_balance"]), inline=True)
        embed.set_footer(text="El importe entró en la caja del negocio, no a tu bolsillo")
        await interaction.followup.send(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------


class Companies(commands.Cog):
    """Gestion completa de empresas privadas."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        """Los botones del panel sobreviven a reinicios gracias a este router."""
        self.bot.add_view(CompanyPanelRouter())

    empresa = app_commands.Group(
        name="empresa",
        description="Tu negocio: puestos, precios, nomina, caja y acciones",
    )
    # Discord admite 25 subcomandos por grupo, asi que el arbol se reparte en
    # subgrupos tematicos para que todo siga siendo facil de usar.
    plantilla = app_commands.Group(
        name="plantilla", parent=empresa, description="Puestos, contratos y bajas",
    )
    dinero = app_commands.Group(
        name="dinero", parent=empresa, description="Aportaciones, nomina y libro mayor",
    )
    catalogo = app_commands.Group(
        name="catalogo", parent=empresa, description="Productos, servicios y precios",
    )
    sociedad = app_commands.Group(
        name="sociedad", parent=empresa, description="Capital social, acciones y dividendos",
    )
    negocio = app_commands.Group(
        name="negocio", parent=empresa, description="Estado, compra y venta del negocio",
    )

    # -- Atajos: lo mas usado queda en la raiz de /empresa ------------------

    # -- Creacion ----------------------------------------------------------

    @empresa.command(name="crear", description="Fundar tu propia empresa")
    async def crear(self, interaction: discord.Interaction):
        if not await _guard(interaction, "create"):
            return
        config = await async_get_or_create_guild_config(str(interaction.guild_id))
        cost = B.money(config.get("company_creation_cost"), 5000)
        await interaction.response.send_modal(UI.CompanyCreateModal(cost))

    @empresa.command(name="mi_empresa", description="Resumen de la empresa que diriges")
    async def mi_empresa(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        company = await B.get_owned_company(str(interaction.guild_id), str(interaction.user.id))
        if not company:
            await interaction.followup.send(
                embed=error_embed("No tienes empresa", "Crea una con `/empresa crear`."),
                ephemeral=True)
            return
        await send_panel(interaction, company)

    @empresa.command(name="panel", description="Abrir el panel de gestión de una empresa")
    @app_commands.describe(empresa="Nombre de la empresa (si no la indicas, la tuya)")
    async def panel(self, interaction: discord.Interaction, empresa: str = None):
        await interaction.response.defer(ephemeral=True)
        company = await _resolve_company(interaction, empresa)
        if not company:
            await interaction.followup.send(
                embed=error_embed("Empresa no encontrada", "Indica el nombre de una empresa existente."),
                ephemeral=True)
            return
        await send_panel(interaction, company)

    @empresa.command(name="info", description="Ficha publica de una empresa")
    @app_commands.describe(empresa="Nombre de la empresa")
    async def info(self, interaction: discord.Interaction, empresa: str):
        await interaction.response.defer()
        company = await _resolve_company(interaction, empresa)
        if not company:
            await interaction.followup.send(
                embed=error_embed("Empresa no encontrada", "No existe esa empresa aqui."),
                ephemeral=True)
            return
        access = await B.resolve_access(str(interaction.guild_id), str(interaction.user.id), company["id"])
        # Ficha publica: la ve todo el canal.
        await interaction.followup.send(
            embed=await UI.company_dossier(company["id"], access, str(interaction.guild_id),
                                           mostrar_acceso=False))

    # -- Puestos y plantilla ------------------------------------------------

    @plantilla.command(name="puestos", description="Ver los puestos y sus salarios")
    @app_commands.describe(empresa="Nombre de la empresa")
    async def puestos(self, interaction: discord.Interaction, empresa: str = None):
        await interaction.response.defer()
        company = await _resolve_company(interaction, empresa)
        if not company:
            await interaction.followup.send(embed=error_embed("Empresa no encontrada", "Indica el nombre."),
                                           ephemeral=True)
            return
        positions = await B.company_positions(company["id"])
        employees = await B.company_employees(company["id"])
        await interaction.followup.send(embed=UI.positions_embed(positions, employees))

    @plantilla.command(name="crear_puesto", description="Definir un puesto y su salario (dueño)")
    async def crear_puesto(self, interaction: discord.Interaction):
        company = await B.get_owned_company(str(interaction.guild_id), str(interaction.user.id))
        if not company:
            await interaction.response.send_message(
                embed=error_embed("No tienes empresa", "Crea una con `/empresa crear`."), ephemeral=True)
            return
        await interaction.response.send_modal(UI.PositionModal(company["id"]))

    @plantilla.command(name="empleados", description="Ver la plantilla de la empresa")
    @app_commands.describe(empresa="Nombre de la empresa")
    async def empleados(self, interaction: discord.Interaction, empresa: str = None):
        await interaction.response.defer()
        company = await _resolve_company(interaction, empresa)
        if not company:
            await interaction.followup.send(embed=error_embed("Empresa no encontrada", "Indica el nombre."),
                                           ephemeral=True)
            return
        employees = await B.company_employees(company["id"])
        await interaction.followup.send(embed=UI.employees_embed(employees, company))

    @plantilla.command(name="contratar", description="Contratar a un ciudadano")
    @app_commands.describe(usuario="Ciudadano a contratar")
    async def contratar(self, interaction: discord.Interaction, usuario: discord.Member):
        company = await _resolve_company(interaction, None)
        if not company:
            await interaction.response.send_message(
                embed=error_embed("No tienes empresa", "Usa `/empresa panel` sobre una empresa tuya."),
                ephemeral=True)
            return
        if not await B.require_access(interaction, company["id"], permission="hire"):
            return
        if usuario.bot:
            await interaction.response.send_message(
                embed=error_embed("No es posible", "Los bots no se contratan."), ephemeral=True)
            return
        existing = await B.get_member(company["id"], str(usuario.id))
        if existing:
            await interaction.response.send_message(
                embed=warning_embed("Ya trabaja aquí",
                                    f"<@{usuario.id}> ya figura en la plantilla de **{company['name']}**."),
                ephemeral=True)
            return
        await interaction.response.send_modal(UI.HireModal(company["id"], str(usuario.id),
                                                           await B.company_positions(company["id"])))

    @plantilla.command(name="despedir", description="Dar de baja a un empleado")
    @app_commands.describe(usuario="Empleado a despedir")
    async def despedir(self, interaction: discord.Interaction, usuario: discord.Member):
        company = await _resolve_company(interaction, None)
        if not company:
            await interaction.response.send_message(
                embed=error_embed("No tienes empresa", "Indica la empresa con `/empresa panel`."),
                ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if not await B.require_access(interaction, company["id"], permission="hire"):
            return
        try:
            left = await B.fire(str(interaction.guild_id), company["id"], str(usuario.id))
        except Exception as error:
            await _report(interaction, error)
            return
        await _remove_role(interaction.guild, usuario, left)
        pending = B.money(left.get("pending_salary"))
        embed = success_embed("Baja registrada",
                              f"<@{usuario.id}> ya no trabaja en **{company['name']}**.")
        if pending:
            embed.description += (f"\n⚠️Debía **{UI.money(pending)}** de nómina. "
                                  f"Esa deuda queda anotada a nombre de la empresa.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @plantilla.command(name="mis_datos", description="Tu ficha dentro de la empresa")
    async def mis_datos(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        company = await B.get_owned_company(str(interaction.guild_id), str(interaction.user.id))
        if not company:
            company = await _resolve_company(interaction, None)
        if not company:
            await interaction.followup.send(embed=error_embed("Sin empresa", "No diriges ninguna empresa."),
                                           ephemeral=True)
            return
        access = await B.resolve_access(str(interaction.guild_id), str(interaction.user.id), company["id"])
        member = access.get("member") or {}
        embed = info_embed(f"Tu ficha · {company['name']}", UI.level_label(access))
        if member:
            embed.add_field(name="Puesto", value=member.get("position_name") or member.get("role") or "—",
                            inline=True)
            embed.add_field(name="Salario diario", value=UI.money(member.get("salary")), inline=True)
            embed.add_field(name="Nómina pendiente", value=UI.money(member.get("pending_salary")), inline=True)
            embed.add_field(name="Permisos", value=UI.perm_summary(access.get("permissions")), inline=False)
        if company:
            total_due, headcount = await B.pending_payroll(company["id"])
            embed.add_field(
                name="Nómina de la empresa",
                value=(f"{UI.money(total_due)} pendientes para {headcount} empleado(s)"
                       if headcount else "Al día"),
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # -- Dinero ------------------------------------------------------------

    @empresa.command(name="caja", description="Ver la caja de la empresa")
    @app_commands.describe(empresa="Nombre de la empresa")
    async def caja(self, interaction: discord.Interaction, empresa: str = None):
        await interaction.response.defer(ephemeral=True)
        company = await _resolve_company(interaction, empresa)
        if not company:
            await interaction.followup.send(embed=error_embed("Empresa no encontrada", "Indica el nombre."),
                                           ephemeral=True)
            return
        embed = info_embed(f"\U0001F4B0 Caja · {company['name']}", UI.status_line(company))
        total_due, count = await B.pending_payroll(company["id"])
        embed.add_field(name="Fondos", value=UI.money(company.get("funds")), inline=True)
        embed.add_field(name="Nómina pendiente",
                        value=f"{UI.money(total_due)} ({count} empleados)", inline=True)
        embed.add_field(name="Impuestos", value=f"{B.money(company.get('tax_rate'), 5)}%", inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @dinero.command(name="aportar", description="Meter capital de tu bolsillo en la empresa")
    @app_commands.describe(cantidad="Importe a aportar")
    async def aportar(self, interaction: discord.Interaction, cantidad: int):
        company = await B.get_owned_company(str(interaction.guild_id), str(interaction.user.id))
        if not company:
            await interaction.response.send_message(
                embed=error_embed("No tienes empresa", "Solo el dueño aporta capital."), ephemeral=True)
            return
        await interaction.response.send_modal(UI.AmountModal(
            "Aportar capital", "deposit", company["id"], "Importe a aportar"))

    @dinero.command(name="invertir", description="Registrar una inversión en la empresa")
    @app_commands.describe(cantidad="Importe de la inversión")
    async def invertir(self, interaction: discord.Interaction, cantidad: int):
        company = await B.get_owned_company(str(interaction.guild_id), str(interaction.user.id))
        if not company:
            await interaction.response.send_message(
                embed=error_embed("No tienes empresa", "Solo el dueño invierte."), ephemeral=True)
            return
        await interaction.response.send_modal(UI.AmountModal(
            "Inversión", "investment", company["id"], "Importe invertido"))

    @dinero.command(name="retirar", description="Sacar dinero de la caja a tu bolsillo")
    @app_commands.describe(cantidad="Importe a retirar")
    async def retirar(self, interaction: discord.Interaction, cantidad: int):
        company = await B.get_owned_company(str(interaction.guild_id), str(interaction.user.id))
        if not company:
            await interaction.response.send_message(
                embed=error_embed("No tienes empresa", "Solo el dueño retira capital."), ephemeral=True)
            return
        await interaction.response.send_modal(UI.AmountModal(
            "Retiro del dueño", "withdraw", company["id"], "Importe a retirar"))

    @dinero.command(name="gasto", description="Registrar un gasto de la empresa")
    @app_commands.describe(cantidad="Importe del gasto")
    async def gasto(self, interaction: discord.Interaction, cantidad: int):
        company = await _resolve_company(interaction, None)
        if not company:
            await interaction.response.send_message(
                embed=error_embed("No tienes empresa", "Indica la empresa con `/empresa panel`."),
                ephemeral=True)
            return
        if not await B.require_access(interaction, company["id"], owner_only=True):
            return
        await interaction.response.send_modal(UI.AmountModal(
            "Gasto de empresa", "expense", company["id"], "Importe del gasto"))

    @dinero.command(name="finanzas", description="Libro mayor completo de la empresa")
    @app_commands.describe(empresa="Nombre de la empresa")
    async def finanzas(self, interaction: discord.Interaction, empresa: str = None):
        await interaction.response.defer(ephemeral=True)
        company = await _resolve_company(interaction, empresa)
        if not company:
            await interaction.followup.send(embed=error_embed("Empresa no encontrada", "Indica el nombre."),
                                           ephemeral=True)
            return
        if not await B.require_access(interaction, company["id"], permission="finance"):
            return
        entries = await B.company_ledger(company["id"], limit=20)
        await interaction.followup.send(
            embed=UI.ledger_embed(entries, B.money(company.get("funds"))), ephemeral=True)

    @empresa.command(name="nomina", description="Pagar la nómina desde la caja real")
    @app_commands.describe(
        modo="full = todo lo pendiente; partial = reparto proporcional de la caja",
    )
    @app_commands.choices(
        modo=[discord.app_commands.Choice(name="Completa", value="full"),
              discord.app_commands.Choice(name="Parcial (recorte)", value="partial")],
    )
    async def nomina(self, interaction: discord.Interaction, modo: str = "full"):
        await interaction.response.defer(ephemeral=True)
        company = await _resolve_company(interaction, None)
        if not company:
            await interaction.followup.send(
                embed=error_embed("Sin empresa", "Indica la empresa con `/empresa panel`."),
                ephemeral=True)
            return
        if not await B.require_access(interaction, company["id"], permission="payroll"):
            return
        if not await _guard(interaction, f"payroll:{company['id']}"):
            return
        try:
            result = await B.run_payroll(
                str(interaction.guild_id), company["id"], str(interaction.user.id), mode=modo)
        except B.InsufficientFunds as error:
            if getattr(error, "detail", None):
                await interaction.followup.send(embed=UI.deficit_embed(error), ephemeral=True)
                return
            await _report(interaction, error)
            return
        except B.BusinessError as error:
            await _report(interaction, error)
            return
        embed = UI.payroll_result_embed(result, company, modo)
        lines = "\n".join(
            f"<@{p['member']['discord_id']}> ({p['member'].get('position_name') or 'Empleado'}) "
            f"→ **{UI.money(p['amount'])}**" for p in result["payments"]
        )
        embed.add_field(name="Detalle", value=lines[:1000] or "Nadie cobraba", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @dinero.command(name="acumular_nomina", description="Generar un día de nómina pendiente")
    async def acumular_nomina(self, interaction: discord.Interaction):
        company = await _resolve_company(interaction, None)
        if not company:
            await interaction.response.send_message(
                embed=error_embed("Sin empresa", "Indica la empresa con `/empresa panel`."), ephemeral=True)
            return
        if not await B.require_access(interaction, company["id"], owner_only=True):
            return
        await interaction.response.defer(ephemeral=True)
        touched = await B.accrue_salary(company["id"], 1)
        total, _ = await B.pending_payroll(company["id"])
        await interaction.followup.send(
            embed=success_embed("Nómina acumulada",
                                f"Un día de salario pendiente para **{touched}** empleado(s)."),
            ephemeral=True)

    # -- Menu --------------------------------------------------------------

    @empresa.command(name="menu", description="Ver productos y servicios con sus precios")
    @app_commands.describe(empresa="Nombre de la empresa")
    async def menu(self, interaction: discord.Interaction, empresa: str = None):
        await interaction.response.defer()
        company = await _resolve_company(interaction, empresa)
        if not company:
            await interaction.followup.send(embed=error_embed("Empresa no encontrada", "Indica el nombre."),
                                           ephemeral=True)
            return
        items = await B.company_catalog(company["id"], only_active=True)
        if not items:
            await interaction.followup.send(
                embed=info_embed("Menú vacío", f"**{company['name']}** todavia no ofrece nada."))
            return
        await interaction.followup.send(
            embed=UI.catalog_embed(items, company),
            view=CatalogBuyView(company["id"], str(interaction.user.id), items))

    @catalogo.command(name="agregar_producto", description="Añadir un producto al menú (define tú el precio)")
    async def agregar_producto(self, interaction: discord.Interaction):
        company = await _resolve_company(interaction, None)
        if not company:
            await interaction.response.send_message(
                embed=error_embed("Sin empresa", "Indica la empresa con `/empresa panel`."), ephemeral=True)
            return
        if not await B.require_access(interaction, company["id"], permission="menu"):
            return
        await interaction.response.send_modal(UI.CatalogModal(company["id"], "product"))

    @catalogo.command(name="agregar_servicio", description="Añadir un servicio al menú (define tú el precio)")
    async def agregar_servicio(self, interaction: discord.Interaction):
        company = await _resolve_company(interaction, None)
        if not company:
            await interaction.response.send_message(
                embed=error_embed("Sin empresa", "Indica la empresa con `/empresa panel`."), ephemeral=True)
            return
        if not await B.require_access(interaction, company["id"], permission="menu"):
            return
        await interaction.response.send_modal(UI.CatalogModal(company["id"], "service"))

    @catalogo.command(name="comprar", description="Comprar un producto o contratar un servicio")
    @app_commands.describe(empresa="Nombre de la empresa", articulo="Nombre del artículo")
    async def comprar(self, interaction: discord.Interaction, empresa: str, articulo: str):
        await interaction.response.defer(ephemeral=True)
        company = await _resolve_company(interaction, empresa)
        if not company:
            await interaction.followup.send(embed=error_embed("Empresa no encontrada", "Indica el nombre."),
                                           ephemeral=True)
            return
        item = next(
            (i for i in await B.company_catalog(company["id"], only_active=True)
             if str(i.get("name")).lower() == articulo.strip().lower()),
            None,
        )
        if not item:
            await interaction.followup.send(
                embed=error_embed("No en catálogo", f"**{articulo}** no está en el menú de "
                                    f"**{company['name']}**. Mira `/empresa menu`."),
                ephemeral=True)
            return
        if not await _guard(interaction, f"buy:{item['id']}"):
            return
        try:
            result = await B.purchase_item(
                str(interaction.guild_id), company["id"], item["id"], str(interaction.user.id))
        except Exception as error:
            await _report(interaction, error)
            return
        buyer = await async_get_or_create_user(str(interaction.user.id), str(interaction.guild_id))
        embed = success_embed(
            f"{item.get('emoji') or ''} {result['item'].get('name')}".strip(),
            f"Has {'contratado' if result['kind'] == 'service' else 'comprado'} en "
            f"**{company['name']}** por **{UI.money(result['total'])}**.")
        embed.add_field(name="Tu efectivo", value=UI.money(buyer.get("cash")), inline=True)
        embed.add_field(name="Caja de la empresa", value=UI.money(result["company_balance"]), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    # -- Acciones ----------------------------------------------------------

    @sociedad.command(name="acciones", description="Ver el capital social y los accionistas")
    @app_commands.describe(empresa="Nombre de la empresa")
    async def acciones(self, interaction: discord.Interaction, empresa: str = None):
        await interaction.response.defer()
        company = await _resolve_company(interaction, empresa)
        if not company:
            await interaction.followup.send(embed=error_embed("Empresa no encontrada", "Indica el nombre."),
                                           ephemeral=True)
            return
        config = await B.company_shares_config(company["id"])
        holders = await B.company_shareholders(company["id"])
        await interaction.followup.send(embed=UI.shares_embed(config, holders, company))

    @sociedad.command(name="emitir_acciones", description="Definir el capital social (dueño)")
    async def emitir_acciones(self, interaction: discord.Interaction):
        company = await B.get_owned_company(str(interaction.guild_id), str(interaction.user.id))
        if not company:
            await interaction.response.send_message(
                embed=error_embed("No tienes empresa", "Solo el dueño emite capital social."), ephemeral=True)
            return
        await interaction.response.send_modal(
            UI.SharesModal(company["id"], await B.company_shares_config(company["id"])))

    @sociedad.command(name="comprar_acciones", description="Comprar acciones de una empresa")
    @app_commands.describe(empresa="Nombre de la empresa", acciones="Número de acciones")
    async def comprar_acciones(self, interaction: discord.Interaction, empresa: str, acciones: int):
        await interaction.response.defer(ephemeral=True)
        company = await _resolve_company(interaction, empresa)
        if not company:
            await interaction.followup.send(embed=error_embed("Empresa no encontrada", "Indica el nombre."),
                                           ephemeral=True)
            return
        if not await _guard(interaction, f"shares:{company['id']}"):
            return
        try:
            result = await B.buy_primary_shares(
                str(interaction.guild_id), company["id"], str(interaction.user.id), max(1, acciones))
        except Exception as error:
            await _report(interaction, error)
            return
        embed = success_embed(
            "\U0001F4C5 Compra de acciones",
            f"Has comprado **{result['shares']:,}** acciones de **{company['name']}** "
            f"por **{UI.money(result['total'])}**.")
        embed.add_field(name="Precio por acción", value=UI.money(result["price"]), inline=True)
        embed.add_field(name="Caja de la empresa", value=UI.money(result["company_balance"]), inline=True)
        embed.set_footer(text="Tu dinero ha entrado en la caja de la empresa")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @sociedad.command(name="vender_acciones", description="Vender tus acciones a la propia empresa")
    @app_commands.describe(empresa="Nombre de la empresa", acciones="Número de acciones")
    async def vender_acciones(self, interaction: discord.Interaction, empresa: str, acciones: int):
        await interaction.response.defer(ephemeral=True)
        company = await _resolve_company(interaction, empresa)
        if not company:
            await interaction.followup.send(embed=error_embed("Empresa no encontrada", "Indica el nombre."),
                                           ephemeral=True)
            return
        if not await _guard(interaction, f"sharesell:{company['id']}"):
            return
        try:
            result = await B.sell_shares_to_company(
                str(interaction.guild_id), company["id"], str(interaction.user.id), max(1, acciones))
        except Exception as error:
            await _report(interaction, error)
            return
        embed = success_embed(
            "\U0001F4C5 Venta de acciones",
            f"Has vendido **{result['shares']:,}** acciones por **{UI.money(result['total'])}**.")
        embed.add_field(name="Caja de la empresa",
                        value=UI.money(result["company_balance"]), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @sociedad.command(name="dividendo", description="Repartir dividendo entre los accionistas (dueño)")
    @app_commands.describe(cantidad="Importe total a repartir")
    async def dividendo(self, interaction: discord.Interaction, cantidad: int):
        company = await B.get_owned_company(str(interaction.guild_id), str(interaction.user.id))
        if not company:
            await interaction.response.send_message(
                embed=error_embed("No tienes empresa", "Solo el dueño reparte dividendos."), ephemeral=True)
            return
        await interaction.response.send_modal(UI.AmountModal(
            "Dividendo", "dividend", company["id"], "Importe total a repartir"))

    # -- Estado y venta del negocio ----------------------------------------

    @negocio.command(name="estado", description="Cambiar el estado financiero de la empresa (dueño)")
    @app_commands.choices(
        estado=[discord.app_commands.Choice(name="Activa", value="active"),
                discord.app_commands.Choice(name="En dificultades", value="difficulty"),
                discord.app_commands.Choice(name="En quiebra", value="bankrupt"),
                discord.app_commands.Choice(name="Cerrada", value="closed")],
    )
    @app_commands.describe(estado="Nuevo estado", motivo="Motivo del cambio")
    async def estado(self, interaction: discord.Interaction, estado: str, motivo: str = ""):
        await interaction.response.defer()
        company = await B.get_owned_company(str(interaction.guild_id), str(interaction.user.id))
        if not company:
            await interaction.followup.send(
                embed=error_embed("No tienes empresa", "Solo el dueño cambia el estado."), ephemeral=True)
            return
        try:
            await B.set_company_status(str(interaction.guild_id), company["id"], estado,
                                       motivo, str(interaction.user.id))
        except Exception as error:
            await _report(interaction, error)
            return
        info = B.COMPANY_STATUS.get(estado, B.COMPANY_STATUS["active"])
        # El cambio de estado es publico: todo el canal debe verlo.
        await interaction.followup.send(
            embed=success_embed("Estado actualizado", f"{info['emoji']} **{info['label']}**"
                                + (f"\n{motivo}" if motivo else "")))

    @negocio.command(name="vender_empresa", description="Poner tu empresa en venta")
    @app_commands.describe(precio="Precio de venta pedido")
    async def vender_empresa(self, interaction: discord.Interaction, precio: int):
        company = await B.get_owned_company(str(interaction.guild_id), str(interaction.user.id))
        if not company:
            await interaction.response.send_message(
                embed=error_embed("No tienes empresa", "Solo el dueño vende el negocio."), ephemeral=True)
            return
        await interaction.response.send_modal(UI.SalePriceModal(company["id"], B.money(company.get("funds"))))

    @negocio.command(name="retirar_venta", description="Retirar tu empresa del mercado")
    async def retirar_venta(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        company = await B.get_owned_company(str(interaction.guild_id), str(interaction.user.id))
        if not company:
            await interaction.followup.send(
                embed=error_embed("No tienes empresa", "Solo el dueño retira la venta."), ephemeral=True)
            return
        try:
            await B.cancel_company_sale(str(interaction.guild_id), company["id"],
                                        str(interaction.user.id))
        except Exception as error:
            await _report(interaction, error)
            return
        await interaction.followup.send(
            embed=success_embed("Venta retirada", "Tu empresa ya no está en el mercado."), ephemeral=True)

    @negocio.command(name="mercado", description="Comprar empresas en venta")
    async def mercado(self, interaction: discord.Interaction):
        await interaction.response.defer()
        listings = await B.for_sale_market(str(interaction.guild_id))
        if not listings:
            await interaction.followup.send(
                embed=info_embed("Mercado vacío", "No hay empresas en venta ahora mismo."))
            return
        embed = info_embed("\U0001F3E2 Empresas en venta", "El importe pagado entra en la caja del negocio.")
        for listing in listings[:10]:
            embed.add_field(
                name=listing.get("name"),
                value=f"{UI.money(listing.get('sale_price'))} · caja "
                      f"{UI.money(listing.get('funds'))}",
                inline=True,
            )
        await interaction.followup.send(
            embed=embed,
            view=MarketBuyView(str(interaction.guild_id), str(interaction.user.id), listings))

    @negocio.command(name="comprar_empresa", description="Comprar una empresa en venta por su nombre")
    @app_commands.describe(empresa="Nombre de la empresa en venta")
    async def comprar_empresa(self, interaction: discord.Interaction, empresa: str):
        await interaction.response.defer(ephemeral=True)
        company = await _resolve_company(interaction, empresa)
        if not company:
            await interaction.followup.send(embed=error_embed("No existe", "No hay esa empresa aquí."),
                                           ephemeral=True)
            return
        if not await _guard(interaction, f"buyco:{company['id']}"):
            return
        try:
            result = await B.buy_company(
                str(interaction.guild_id), company["id"], str(interaction.user.id))
        except Exception as error:
            await _report(interaction, error)
            return
        await _transfer_ownership_roles(interaction, result)
        embed = success_embed(
            f"\U0001F3E2 Compras {company.get('name')}",
            f"Nuevo dueño: <@{interaction.user.id}> · vendedor: <@{result['seller_id']}>.")
        embed.add_field(name="Precio", value=UI.money(result["price"]), inline=True)
        embed.add_field(name="Caja del negocio", value=UI.money(result["company_balance"]), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Ayuda para los botones del panel
# ---------------------------------------------------------------------------


class CompanyPanelRouter(discord.ui.View):
    """Router permanente de los botones del panel.

    Vive en el bot para que los botones sigan funcionando aunque el panel se
    haya enviado hace horas. El `custom_id` es `empresa:<empresa>:<accion>`.
    """

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Aportar capital", emoji="\U0001F4E6", style=discord.ButtonStyle.success,
        custom_id="empresa_panel:deposit",
    )
    async def btn_deposit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _route(interaction, "deposit")

    @discord.ui.button(
        label="Retirar", emoji="\U0001F4B8", style=discord.ButtonStyle.danger,
        custom_id="empresa_panel:withdraw",
    )
    async def btn_withdraw(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _route(interaction, "withdraw")

    @discord.ui.button(
        label="Gasto", emoji="\U0001F6D2", style=discord.ButtonStyle.secondary,
        custom_id="empresa_panel:expense",
    )
    async def btn_expense(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _route(interaction, "expense")

    @discord.ui.button(
        label="Nómina", emoji="\U0001F4B0", style=discord.ButtonStyle.primary,
        custom_id="empresa_panel:payroll",
    )
    async def btn_payroll(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _route(interaction, "payroll")

    @discord.ui.button(
        label="Menú", emoji="\U0001F372", style=discord.ButtonStyle.secondary,
        custom_id="empresa_panel:menu",
    )
    async def btn_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _route(interaction, "menu")

    @discord.ui.button(
        label="Puestos", emoji="\U0001F9D9", style=discord.ButtonStyle.secondary,
        custom_id="empresa_panel:positions",
    )
    async def btn_positions(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _route(interaction, "positions")

    @discord.ui.button(
        label="Finanzas", emoji="\U0001F4CA", style=discord.ButtonStyle.secondary,
        custom_id="empresa_panel:finance",
    )
    async def btn_finance(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _route(interaction, "finance")

    @discord.ui.button(
        label="Contratar", emoji="➕", style=discord.ButtonStyle.success,
        custom_id="empresa_panel:hire",
    )
    async def btn_hire(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _route(interaction, "hire")


class CompanyContext:
    """Guarda en memoria que ciudadano tiene abierto el panel de cada empresa.

    Los paneles se envian en efimero, asi que basta con recordar el dueno de cada
    empresa para saber quien puede accionar cada boton.
    """
    _last_viewer: dict = {}

    @classmethod
    def remember(cls, company_id: str, viewer_id: str):
        cls._last_viewer[company_id] = viewer_id

    @classmethod
    def viewer_of(cls, company_id: str):
        return cls._last_viewer.get(company_id)


async def _route(interaction: discord.Interaction, action: str):
    """Traduce un boton del router a la accion correspondiente."""
    data = getattr(interaction.message, "components", None) or []
    company_id = None
    for row in data:
        for component in getattr(row, "children", []):
            cid = getattr(component, "custom_id", "") or ""
            if cid.startswith("empresa:"):
                company_id = cid.split(":")[1]
                break
        if company_id:
            break
    if not company_id:
        await _deny(interaction, "Panel caducado", "Usa `/empresa panel` para abrir uno nuevo.")
        return
    await handle_panel_button(interaction.client, interaction, company_id, action)


async def send_panel(interaction, company):
    """Envia el dossier de la empresa con su panel de botones."""
    access = await B.resolve_access(str(interaction.guild_id), str(interaction.user.id), company["id"])
    embed = await UI.company_dossier(company["id"], access, str(interaction.guild_id))
    CompanyContext.remember(company["id"], str(interaction.user.id))
    await interaction.followup.send(
        embed=embed, view=CompanyPanelView(company["id"], str(interaction.user.id)), ephemeral=True)


async def handle_panel_button(bot, interaction: discord.Interaction, company_id: str, action: str):
    """Abre el modal correspondiente a un boton del panel, validando permisos."""
    company = await B.get_company(company_id, str(interaction.guild_id))
    if not company:
        await _deny(interaction, "Empresa no encontrada", "Ya no existe ese negocio.")
        return
    if action in ("deposit", "investment", "withdraw", "dividend", "sell", "expense"):
        if not await B.require_access(interaction, company_id, owner_only=True):
            return
    elif action in ("menu", "positions"):
        permission = "menu" if action == "menu" else "positions"
        if not await B.require_access(interaction, company_id, permission=permission):
            return
    elif action in ("finance", "payroll"):
        permission = "finance" if action == "finance" else "payroll"
        if not await B.require_access(interaction, company_id, permission=permission):
            return
    elif action == "hire":
        if not await B.require_access(interaction, company_id, permission="hire"):
            return
    else:
        await _deny(interaction, "Acción desconocida", action)
        return

    funds = B.money(company.get("funds"))
    modals = {
        "deposit": lambda: UI.AmountModal("Aportar capital", "deposit", company_id, "Importe a aportar"),
        "investment": lambda: UI.AmountModal("Inversión", "investment", company_id, "Importe invertido"),
        "withdraw": lambda: UI.AmountModal("Retiro del dueño", "withdraw", company_id, "Importe a retirar"),
        "expense": lambda: UI.AmountModal("Gasto de empresa", "expense", company_id, "Importe del gasto"),
        "dividend": lambda: UI.AmountModal("Dividendo", "dividend", company_id, "Importe a repartir"),
        "positions": lambda: UI.PositionModal(company_id),
        "menu": lambda: UI.CatalogModal(company_id, "product"),
        "sell": lambda: UI.SalePriceModal(company_id, funds),
    }
    if action in modals:
        await interaction.response.send_modal(modals[action]())
        return
    if action == "payroll":
        await _payroll_from_button(interaction, company)
        return
    if action == "hire":
        await _hire_from_button(interaction, company)
        return
    if action == "finance":
        await _finance_from_button(interaction, company)


async def _payroll_from_button(interaction, company):
    await interaction.response.defer(ephemeral=True)
    total_due, count = await B.pending_payroll(company["id"])
    if not count:
        await interaction.followup.send(
            embed=info_embed("Nómina al día", "No hay salarios pendientes de pago."), ephemeral=True)
        return
    if B.money(company.get("funds")) < total_due:
        await interaction.followup.send(
            embed=error_embed(
                "Faltan fondos",
                f"La caja tiene **{UI.money(company.get('funds'))}** y la nómina debida es "
                f"**{UI.money(total_due)}**. No se ha movido nada.\n\n"
                f"Opciones: aportar capital (`/empresa aportar`), bajar salarios o vender "
                f"parte del negocio."),
            ephemeral=True)
        return
    try:
        result = await B.run_payroll(
            str(interaction.guild_id), company["id"], str(interaction.user.id), mode="full")
    except Exception as error:
        await _report(interaction, error)
        return
    lines = "\n".join(
        f"<@{p['member']['discord_id']}> → **{UI.money(p['amount'])}**" for p in result["payments"]
    )
    embed = UI.payroll_result_embed(result, company, "full")
    embed.add_field(name="Detalle", value=lines[:1000], inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)


async def _hire_from_button(interaction, company):
    members = [m for m in interaction.guild.members
               if not m.bot and str(m.id) not in {str(company.get("owner_id"))}]
    if not members:
        await interaction.response.send_message(
            embed=error_embed("Sin candidatos", "No hay miembros a los que contratar."), ephemeral=True)
        return
    await interaction.response.send_message(
        content=f"Contratando en **{company.get('name')}**…",
        view=UI.HireMemberSelect(company["id"], members),
        ephemeral=True,
    )


async def _finance_from_button(interaction, company):
    await interaction.response.defer(ephemeral=True)
    entries = await B.company_ledger(company["id"], limit=20)
    await interaction.followup.send(
        embed=UI.ledger_embed(entries, B.money(company.get("funds"))), ephemeral=True)


async def _remove_role(guild, member, left_row):
    """Quita el rol de empresa de quien ha dado de baja."""
    if not left_row or not left_row.get("discord_role_id"):
        return
    try:
        role = guild.get_role(int(left_row["discord_role_id"]))
    except (TypeError, ValueError):
        return
    if not role:
        return
    try:
        await member.remove_roles(role, reason="Baja de empresa")
    except discord.Forbidden:
        logger.debug("[Empresa] No se pudo quitar el rol %s a %s", role.id, member.id)


async def _transfer_ownership_roles(interaction, result):
    """Al vender una empresa, el rol del dueño pasa al comprador."""
    seller = interaction.guild.get_member(int(result["seller_id"]))
    company = result["company"]
    employees = await B.company_employees(company["id"])
    for row in employees:
        role = None
        if row.get("discord_role_id"):
            try:
                role = interaction.guild.get_role(int(row["discord_role_id"]))
            except (TypeError, ValueError):
                role = None
        if not role:
            continue
        member = interaction.guild.get_member(int(row["discord_id"]))
        if not member or member == seller:
            continue
        try:
            await member.add_roles(role, reason="Continúa en la empresa comprada")
        except discord.Forbidden:
            logger.debug("[Empresa] No se pudo reasignar el rol %s", role.id)


async def setup(bot):
    await bot.add_cog(Companies(bot))
