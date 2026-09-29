"""Capa visual del sistema de empresas: embeds, modales, menus y botones.

Este modulo NO mueve dinero: solo pinta y pide datos. Toda la logica economica
vive en `bot.services.business`. Los objetos de Discord se construyen y se pasan
por `custom_id` para que las vistas sobrevivan a un reinicio.

Convenciones de custom_id
-------------------------
    empresa:<cid>:<accion>[:<extra>]
    vista:<tipo>:<cid>:<actor>:<pagina>
"""


import logging

import discord

from bot.embeds import error_embed, success_embed, warning_embed
from bot.helpers import format_currency, safe_emoji
from bot.services import business as B

logger = logging.getLogger("bot.business_ui")

# ---------------------------------------------------------------------------
# Envio de vistas
# ---------------------------------------------------------------------------


def _drop_view_emojis(view) -> bool:
    """Quita todos los emojis de una vista. Devuelve True si habia alguno."""
    found = False
    for item in getattr(view, "children", ()):
        for option in getattr(item, "options", ()):
            if option.emoji is not None:
                option.emoji = None
                found = True
        if getattr(item, "emoji", None) is not None:
            item.emoji = None
            found = True
    return found


async def send_view(send, **kwargs):
    """Envia un mensaje con vista y reintenta sin emojis si Discord los rechaza.

    Discord valida todo el `components` de golpe: un solo `emoji.name` que no
    reconozca tumba la respuesta entera con 400 / 50035 y el usuario se queda
    sin comando. `safe_emoji()` ya evita casi todos los casos, pero si aun
    asi Discord rechaza algo se prefiere perder los emojis que perder el
    tablon, y el valor concreto se deja en el log para poder arreglarlo.
    """
    view = kwargs.get("view")
    try:
        return await send(**kwargs)
    except discord.HTTPException as error:
        if getattr(error, "status", None) != 400 or getattr(error, "code", None) != 50035:
            raise
        if view is None or not _drop_view_emojis(view):
            raise
        logger.warning(
            "[UI] Discord rechazo un emoji del componente (%s); se reintenta sin emojis",
            getattr(error, "text", None) or error,
        )
        return await send(**kwargs)


# ---------------------------------------------------------------------------
# Formateo
# ---------------------------------------------------------------------------


def money(value) -> str:
    return format_currency(B.money(value))


def status_line(company) -> str:
    status = (company or {}).get("status") or "active"
    info = B.COMPANY_STATUS.get(status, B.COMPANY_STATUS["active"])
    note = (company or {}).get("status_note") or ""
    line = f"{info['emoji']} **{info['label']}**"
    return f"{line} — {note}" if note else line


def level_label(access) -> str:
    return {
        "owner": "\U0001F451 Dueño",
        "manager": "\U0001F9D9 Gerencia",
        "employee": "\U0001F464 Empleado",
        "customer": "\U0001F464 Cliente",
        "none": "Sin acceso",
    }.get((access or {}).get("level"), "Sin acceso")


def perm_summary(permissions) -> str:
    permissions = permissions or set()
    if not permissions:
        return "Sin permisos especiales"
    return " · ".join(B.PERMISSIONS.get(p, {}).get("label", p) for p in sorted(permissions))


def job_line(job) -> str:
    emoji = job.get("emoji") or "\U0001F9FA"
    pay = B.money(job.get("salary"))
    return (
        f"{emoji} **{job.get('name')}** — sueldo diario {money(pay)}"
        f" · rol: {job.get('role_id') or 'sin rol'}"
    )


# ---------------------------------------------------------------------------
# Embeds
# ---------------------------------------------------------------------------


async def company_dossier(company_id: str, viewer_access: dict, guild_id: str,
                          mostrar_acceso: bool = True):
    """Panel principal de la empresa para quien la consulta.

    `mostrar_acceso` añade el tramo "Tu acceso", que es personal de quien
    consulta. Las fichas publicas deben pasarlo en False para no delatar los
    permisos de quien mira.
    """
    company = viewer_access.get("company") or await B.get_company(company_id, guild_id)
    embed = discord.Embed(
        title=f"{company.get('emoji') or '\U0001F3E2'} {company.get('name')}",
        description=(company.get("description") or "Sin descripción."),
        color=B.COMPANY_STATUS.get(company.get("status"), B.COMPANY_STATUS["active"])["color"],
    )
    embed.add_field(name="Estado", value=status_line(company), inline=True)
    embed.add_field(name="Caja", value=money(company.get("funds")), inline=True)
    embed.add_field(name="Impuestos", value=f"{B.money(company.get('tax_rate'), 5)}%", inline=True)
    embed.add_field(
        name="Sector",
        value=f"{company.get('category') or '—'} · {company.get('location') or '—'}",
        inline=False,
    )
    total_due, count = await B.pending_payroll(company_id)
    embed.add_field(name="Plantilla", value=f"{count} empleados con cargo", inline=True)
    embed.add_field(
        name="Nómina pendiente",
        value=(f"{money(total_due)} pendientes" if total_due else "Al día"),
        inline=True,
    )
    if mostrar_acceso:
        embed.add_field(
            name="Tu acceso",
            value=f"{level_label(viewer_access)}\n{perm_summary(viewer_access.get('permissions'))}",
            inline=False,
        )
    if company.get("status") == "for_sale" and company.get("sale_price"):
        embed.add_field(
            name="\U0001F3E2 En venta",
            value=f"Precio: **{money(company.get('sale_price'))}**",
            inline=False,
        )
    if mostrar_acceso:
        embed.set_footer(text="Usa los botones para gestionar la empresa")
    return embed


def ledger_embed(entries, funds: int, title: str = "\U0001F4B0 Libro mayor") -> discord.Embed:
    embed = discord.Embed(title=title, color=0xFFD166)
    if not entries:
        embed.description = "Todavía no hay movimientos registrados."
        return embed
    lines = []
    for entry in entries:
        kind = B.LEDGER.get(entry.get("kind"), ("Movimiento", "•"))
        amount = B.money(entry.get("amount"))
        sign = "+" if amount > 0 else ""
        emoji = kind[1] if len(kind) > 1 else "•"
        who = entry.get("counterparty_id") or entry.get("actor_id") or "sistema"
        lines.append(
            f"{emoji} **{sign}{money(amount)}** · {entry.get('description') or kind[0]}\n"
            f"└ `{entry.get('created_at')}` · {who}"
        )
    embed.description = "\n".join(lines)[:3900]
    embed.add_field(name="Caja actual", value=money(funds), inline=True)
    return embed


def positions_embed(positions, employees) -> discord.Embed:
    embed = discord.Embed(title="\U0001F9D9 Puestos de la empresa", color=0x00E5FF)
    if not positions:
        embed.description = "El dueño todavía no ha definido ningún puesto."
        return embed
    lines = []
    for pos in positions:
        role = f" rol <@&{pos['role_id']}>" if pos.get("role_id") else ""
        count = len([m for m in employees if m.get("position_id") == pos.get("id")])
        lines.append(
            f"**{pos.get('name')}**{role}\n"
            f"Salario {money(pos.get('salary'))} · {count} en el puesto · "
            f"cupo {pos.get('max_members') or '∞'}"
        )
    embed.description = "\n".join(lines)[:3900]
    return embed


def employees_embed(employees, company) -> discord.Embed:
    embed = discord.Embed(
        title=f"\U0001F465 Plantilla · {company.get('name')}",
        color=0x57F287,
    )
    if not employees:
        embed.description = "No hay empleados dados de alta todavía."
        return embed
    lines = []
    for member in employees:
        pos = member.get("position_name") or member.get("role") or "Empleado"
        role = f" · rol <@&{member['discord_role_id']}>" if member.get("discord_role_id") else ""
        pending = B.money(member.get("pending_salary"))
        pending_text = f" · debe {money(pending)}" if pending else ""
        lines.append(
            f"<@{member['discord_id']}> — **{pos}**{role}\n"
            f"Salario {money(member.get('salary'))}{pending_text} · "
            f"{'gerente' if member.get('is_manager') else perm_summary(member.get('permissions'))}"
        )
    embed.description = "\n".join(lines)[:3900]
    return embed


def catalog_embed(items, company) -> discord.Embed:
    embed = discord.Embed(
        title=f"\U0001F372 Menú · {company.get('name')}",
        color=0x00B8D4,
    )
    if not items:
        embed.description = "El dueño todavía no ha creado productos ni servicios."
        return embed
    lines = []
    for item in items:
        tag = "servicio" if item.get("kind") == "service" else "producto"
        role = f" · rol <@&{item['role_id']}>" if item.get("role_id") else ""
        lines.append(
            f"{item.get('emoji') or '\U0001F9FE'} **{item.get('name')}** — {money(item.get('price'))}"
            f" `{tag}`{role}"
        )
    embed.description = "\n".join(lines)[:3900]
    return embed


def shares_embed(config, holders, company) -> discord.Embed:
    embed = discord.Embed(
        title=f"\U0001F4C5 Capital social · {company.get('name')}",
        color=0xB5651D,
    )
    if not config or not config.get("is_enabled"):
        embed.description = "La sociedad no tiene capital social emitido."
        return embed
    total = B.money(config.get("total_shares"))
    issued = sum(B.money(h.get("shares")) for h in holders)
    embed.add_field(name="Emitidas", value=f"{B.money(issued):,} / {total:,}", inline=True)
    embed.add_field(name="Precio", value=money(config.get("share_price")), inline=True)
    embed.add_field(
        name="Capital social",
        value=money(B.money(config.get("share_price")) * total),
        inline=True,
    )
    if holders:
        lines = [
            f"<@{h['discord_id']}> — {B.money(h.get('shares')):,} acciones"
            f" ({100 * B.money(h.get('shares')) / total:.1f}%)"
            f" · invertido {money(h.get('total_invested'))}"
            for h in holders
        ]
        embed.add_field(name="Accionistas", value="\n".join(lines)[:900], inline=False)
    return embed


def public_jobs_embed(jobs, user_jobs, viewer_id) -> discord.Embed:
    """Tablon de empleos publicos.

    `viewer_id` a None produce un embed neutro, apto para enviar en un canal
    publico: no marca que empleos ocupa quien lo pidio ni revela cuantos tiene.
    """
    embed = discord.Embed(title="\U0001F9FA Empleos públicos del servidor", color=0x00E5FF)
    es_privado = viewer_id is not None
    mine = {str(j.get("job_id")) for j in (user_jobs or [])} if es_privado else set()
    if not jobs:
        embed.description = "El servidor todavía no ha publicado ningún empleo público."
        return embed
    lines = []
    for job in jobs:
        if not es_privado:
            lines.append(f"\U0001F4C5 {job_line(job)}")
            continue
        mark = "\U0001F7E2" if str(job.get("id")) in mine else "\U0001F4C5"
        lines.append(f"{mark} {job_line(job)}")
    embed.description = "\n".join(lines)[:3900]
    if es_privado:
        embed.set_footer(text=f"Tienes {len(mine)} empleo(s) activo(s)")
    return embed


def payroll_result_embed(result, company, mode: str) -> discord.Embed:
    embed = discord.Embed(
        title="\U0001F4B0 Nómina ejecutada",
        color=0x57F287 if not result.get("short") else 0xFEE75C,
    )
    if mode == "partial":
        embed.title = "\U0001F4B0 Nómina parcial (recorte)"
    embed.add_field(
        name="Pagado",
        value=f"{money(result.get('paid'))} a {result.get('paid_count', 0)} empleados",
        inline=True,
    )
    remaining = B.money(result.get("remaining"))
    embed.add_field(
        name="Pendiente",
        value=money(remaining) if remaining else "Nada pendiente",
        inline=True,
    )
    embed.add_field(name="Caja restante", value=money(result.get("balance_after")), inline=True)
    if remaining:
        embed.description = (
            "La empresa no tiene capital para la nomina completa. "
            "El dueño puede aportar capital, reducir salarios o vender el negocio."
        )
    return embed


def deficit_embed(error) -> discord.Embed:
    embed = discord.Embed(title="\U0001F6A8 Faltan fondos", color=0xED4245)
    embed.add_field(name="Disponible en caja", value=money(error.available), inline=True)
    embed.add_field(name="Nómina debida", value=money(error.required), inline=True)
    embed.add_field(name="Déficit", value=money(error.deficit), inline=True)
    if error.detail:
        embed.add_field(name="Detalle", value="\n".join(error.detail)[:900], inline=False)
    embed.description = (
        "No se ha movido ni un centavo: la nómina no se ha ejecutado. "
        "El dueño decide cómo resolverlo."
    )
    return embed


# ---------------------------------------------------------------------------
# Modales
# ---------------------------------------------------------------------------


def _int_value(value, default=0) -> int:
    """Lee un importe escrito como lo escribiria un ciudadano.

    El bot formatea con punto de miles (`$1.250`), asi que se admite cualquier
    convencion:

    - Con ambos separadores, el ULTIMO es el decimal (`1.250,50` -> 1250).
    - Con un solo separador y 1-2 digitos detras se interpreta como decimal
      (`1250,50` -> 1250, `12,50` -> 12).
    - Con un solo separador y 3 digitos detras es separador de miles
      (`1,250` -> 1250, `1.250` -> 1250).
    """
    raw = (value or "").strip().replace("$", "").replace(" ", "").replace(" ", "")
    if not raw:
        return default
    sign = 1
    if raw.startswith("-"):
        sign, raw = -1, raw[1:]

    decimal = None
    if "," in raw and "." in raw:
        thousands, decimal = (",", ".") if raw.rindex(",") < raw.rindex(".") else (".", ",")
        raw = raw.replace(thousands, "").replace(decimal, ".")
    else:
        separator = "," if "," in raw else ("." if "." in raw else None)
        if separator:
            head, _, tail = raw.rpartition(separator)
            if not head:
                # ".50" o ",50": separador inicial, asi que 0.50.
                raw = f"0.{tail}" if tail.isdigit() else raw.replace(separator, "")
            elif head and tail.isdigit() and len(tail) in (1, 2):
                raw = f"{head.replace(separator, '')}.{tail}"
            else:
                raw = raw.replace(separator, "")
    try:
        return sign * int(float(raw))
    except (TypeError, ValueError):
        return default


class CompanyCreateModal(discord.ui.Modal):
    """Alta de empresa: el dueño define su identidad y su fiscalidad.

    Discord admite 5 campos por modal, asi que el emoji se deduce del sector
    con `sector_emoji()` en lugar de pedirlo.
    """

    def __init__(self, cost: int):
        super().__init__(title="\U0001F3E2 Fundar empresa")
        self.cost = cost
        self.add_item(discord.ui.TextInput(
            label="Nombre de la empresa", placeholder="Sammy's Pizzeria",
            max_length=60, required=True))
        self.add_item(discord.ui.TextInput(
            label="Descripción", placeholder="¿A qué se dedica?",
            style=discord.TextStyle.paragraph, max_length=300, required=False))
        self.add_item(discord.ui.TextInput(
            label="Sector", placeholder="Restaurante, Nightclub, Taller...",
            max_length=40, required=True, default="Negocio"))
        self.add_item(discord.ui.TextInput(
            label="Ubicación", placeholder="Little Havana, Downtown, Miami Beach...",
            max_length=40, required=True))
        self.add_item(discord.ui.TextInput(
            label="Impuestos (%)", placeholder="5", max_length=3, required=True, default="5"))
        self.cost_note = f"Coste de la licencia: {format_currency(cost)} (se cobra de tu efectivo)"

    async def on_submit(self, interaction: discord.Interaction):
        from bot.cogs.companies import create_company_flow
        await create_company_flow(interaction, self, self.cost)


SECTOR_EMOJI = {
    "restaurante": "\U0001F35E", "pizzeria": "\U0001F355", "bar": "\U0001F37A",
    "nightclub": "\U0001F3AB", "club": "\U0001F3AB", "tienda": "\U0001F6D2",
    "gasolinera": "⛽", "taller": "\U0001F527", "concesionario": "\U0001F697",
    "clinica": "\U0001F3E5", "hospital": "\U0001F3E5", "despacho": "\U0001F4BC",
    "estudio": "\U0001F3A8", "agencia": "\U0001F3E1", "hotel": "\U0001F6E8",
    "gimnasio": "\U0001F3CB", "playa": "\U0001F3D6", "farmacia": "💊",
    "lavanderia": "\U0001F9FA", "mecanico": "\U0001F527", "taxi": "\U0001F695",
    "supermercado": "\U0001F96D", "peluqueria": "\U0001F487", "tatuaje": "\U0001F528",
}


def sector_emoji(sector: str) -> str:
    """Emoji por defecto segun el sector declarado por el dueno."""
    key = (sector or "").strip().lower()
    for word, emoji in SECTOR_EMOJI.items():
        if word in key:
            return emoji
    return "\U0001F3E2"


class AmountModal(discord.ui.Modal):
    """Importe generico (aportaciones, retiros, gastos, dividends)."""

    def __init__(self, title: str, action: str, company_id: str, label: str,
                 placeholder: str = "5000", note: str = ""):
        super().__init__(title=title[:45])
        self.action = action
        self.company_id = company_id
        self.note = note
        self.add_item(discord.ui.TextInput(
            label=label[:45], placeholder=placeholder, max_length=12, required=True))
        if action in ("expense", "dividend"):
            self.add_item(discord.ui.TextInput(
                label="Concepto", placeholder="Alquiler, luz, publicidad...",
                max_length=200, required=False))

    async def on_submit(self, interaction: discord.Interaction):
        from bot.cogs.companies import run_amount_action
        amount = _int_value(self.children[0].value)
        reason = self.children[1].value if len(self.children) > 1 else ""
        await run_amount_action(interaction, self.action, self.company_id, amount, reason or self.note)


class PositionModal(discord.ui.Modal):
    """Alta o edicion de un puesto: nombre, salario, rol de Discord y permisos."""

    def __init__(self, company_id: str, position=None):
        editing = bool(position)
        super().__init__(title="Editar puesto" if editing else "Nuevo puesto")
        self.company_id = company_id
        self.position = position
        self.add_item(discord.ui.TextInput(
            label="Nombre del puesto", max_length=50, required=True,
            default=(position or {}).get("name") or "Empleado"))
        self.add_item(discord.ui.TextInput(
            label="Salario diario ($)", max_length=10, required=True,
            default=str(B.money((position or {}).get("salary")) or 1000)))
        self.add_item(discord.ui.TextInput(
            label="Rol de Discord (ID o @mencion)", max_length=24, required=False,
            default=(position or {}).get("role_id") or ""))
        self.add_item(discord.ui.TextInput(
            label="Cupo máximo", max_length=4, required=False,
            default=str((position or {}).get("max_members") or 0)))
        self.add_item(discord.ui.TextInput(
            label="Permisos (separados por comas)",
            placeholder="hire, payroll, finance",
            max_length=200, required=False,
            default=",".join(sorted(_decode_perms((position or {}).get("permissions"))))))

    async def on_submit(self, interaction: discord.Interaction):
        from bot.cogs.companies import save_position
        name = self.children[0].value.strip()
        salary = max(0, _int_value(self.children[1].value))
        role_id = _parse_role_id(self.children[2].value)
        max_count = max(0, _int_value(self.children[3].value))
        perms = self.children[4].value
        await save_position(interaction, self.company_id, self.position, name, salary,
                            role_id, max_count, perms)


class CatalogModal(discord.ui.Modal):
    """Alta o edicion de un producto o servicio del menu."""

    def __init__(self, company_id: str, kind: str = "product", item=None):
        editing = bool(item)
        super().__init__(title=f"Editar {kind}" if editing else f"Nuevo {kind}")
        self.company_id = company_id
        self.kind = kind
        self.item = item
        self.add_item(discord.ui.TextInput(
            label="Nombre", max_length=50, required=True,
            default=(item or {}).get("name") or ""))
        self.add_item(discord.ui.TextInput(
            label="Precio ($)", max_length=10, required=True,
            default=str(B.money((item or {}).get("price")) or 100)))
        self.add_item(discord.ui.TextInput(
            label="Descripción", max_length=200, required=False,
            default=(item or {}).get("description") or ""))
        self.add_item(discord.ui.TextInput(
            label="Rol de Discord al comprar (ID o @mencion)", max_length=24, required=False,
            default=(item or {}).get("role_id") or ""))
        self.add_item(discord.ui.TextInput(
            label="Emoji", max_length=4, required=False,
            default=(item or {}).get("emoji") or ("\U0001F9FE" if kind == "product" else "✂️")))

    async def on_submit(self, interaction: discord.Interaction):
        from bot.cogs.companies import save_catalog_item
        await save_catalog_item(
            interaction, self.company_id, self.kind, self.item,
            self.children[0].value.strip(), max(0, _int_value(self.children[1].value)),
            self.children[2].value.strip(), _parse_role_id(self.children[3].value),
            self.children[4].value.strip() or None,
        )


class SharesModal(discord.ui.Modal):
    """Configuracion del capital social por parte del dueno."""

    def __init__(self, company_id: str, config):
        super().__init__(title="Capital social")
        self.company_id = company_id
        self.config = config or {}
        self.add_item(discord.ui.TextInput(
            label="Acciones totales", max_length=9, required=True,
            default=str(B.money(self.config.get("total_shares")) or 1000)))
        self.add_item(discord.ui.TextInput(
            label="Precio por acción ($)", max_length=10, required=True,
            default=str(B.money(self.config.get("share_price")) or 100)))
        self.add_item(discord.ui.TextInput(
            label="Acciones del fundador (0 = ninguna)", max_length=9, required=False,
            default=str(B.money(self.config.get("founder_shares")) or 0)))

    async def on_submit(self, interaction: discord.Interaction):
        from bot.cogs.companies import save_shares_config
        await save_shares_config(
            interaction, self.company_id,
            max(0, _int_value(self.children[0].value)),
            max(0, _int_value(self.children[1].value)),
            max(0, _int_value(self.children[2].value)),
        )


class SalePriceModal(discord.ui.Modal):
    """Poner la empresa en venta con el precio pedido por el dueno."""

    def __init__(self, company_id: str, funds: int):
        super().__init__(title="Poner la empresa en venta")
        self.company_id = company_id
        self.funds = funds
        self.add_item(discord.ui.TextInput(
            label="Precio de venta ($)", max_length=12, required=True,
            placeholder=str(max(1, funds))))
        self.add_item(discord.ui.TextInput(
            label="Motivo de la venta", max_length=200, required=False))

    async def on_submit(self, interaction: discord.Interaction):
        from bot.cogs.companies import publish_sale
        await publish_sale(interaction, self.company_id, max(1, _int_value(self.children[0].value)),
                           self.children[1].value.strip())


class PublicJobModal(discord.ui.Modal):
    """Alta o edicion de un empleo publico (solo administracion del servidor).

    Discord admite 5 campos, asi que el emoji se deduce del nombre con
    `job_emoji()` y las plazas se piden con 0 = sin limite.
    """

    def __init__(self, guild_id: str, job=None):
        editing = bool(job)
        super().__init__(title="Editar empleo" if editing else "Nuevo empleo público")
        self.guild_id = guild_id
        self.job = job
        self.add_item(discord.ui.TextInput(
            label="Nombre", max_length=50, required=True,
            default=(job or {}).get("name") or ""))
        self.add_item(discord.ui.TextInput(
            label="Salario diario ($)", max_length=10, required=True,
            default=str(B.money((job or {}).get("salary")) or 1000)))
        self.add_item(discord.ui.TextInput(
            label="Descripción", max_length=250, required=False,
            default=(job or {}).get("description") or ""))
        self.add_item(discord.ui.TextInput(
            label="Rol de Discord (ID o @mencion)", max_length=24, required=False,
            default=(job or {}).get("role_id") or ""))
        self.add_item(discord.ui.TextInput(
            label="Máximo de empleados (0 = sin límite)", max_length=4, required=False,
            default=str((job or {}).get("max_workers") or 0)))

    async def on_submit(self, interaction: discord.Interaction):
        from bot.cogs.jobs import save_public_job
        name = self.children[0].value.strip()
        await save_public_job(
            interaction, self.guild_id, self.job,
            name, max(0, _int_value(self.children[1].value)),
            self.children[2].value.strip(), _parse_role_id(self.children[3].value),
            job_emoji(name), max(0, _int_value(self.children[4].value)),
        )


JOB_EMOJI = {
    "polic": "\U0001F46E", "policia": "\U0001F46E", "bombero": "\U0001F692",
    "medic": "\U0001FA7A", "sanitari": "\U0001FA7A", "enfermer": "\U0001FA7A",
    "taxi": "\U0001F695", "conductor": "\U0001F69B", "camioner": "\U0001F69B",
    "mecanic": "\U0001F527", "cociner": "\U0001F373", "camarer": "\U0001F37D\uFE0F",
    "jardin": "\U0001F331", "conserj": "\U0001F6E1", "mensaj": "\U0001F4E6",
    "abogad": "\U0001F3DB", "periodist": "\U0001F4F0", "profesor": "\U0001F3EB",
    "traductor": "\U0001F310", "recepcion": "\U0001F6D4", "cajero": "\U0001F3B4",
}


def job_emoji(name: str) -> str:
    """Emoji por defecto para un empleo publico segun su nombre."""
    key = (name or "").strip().lower()
    for word, emoji in JOB_EMOJI.items():
        if word in key:
            return emoji
    return "\U0001F9FA"


class HireModal(discord.ui.Modal):
    """Contratacion eligiendo puesto o salario libre."""

    def __init__(self, company_id: str, member_id: str, positions):
        super().__init__(title="Contratar empleado")
        self.company_id = company_id
        self.member_id = member_id
        options = [discord.SelectOption(label=p.get("name")[:100],
                                        value=p.get("id"),
                                        description=f"{money(p.get('salary'))} diarios")
                   for p in positions[:20]]
        if not options:
            options = [discord.SelectOption(label="Sin puesto definido", value="none")]
        self.add_item(discord.ui.Select(
            placeholder="Puesto del empleado", min_values=1, max_values=1, options=options))
        self.add_item(discord.ui.TextInput(
            label="Salario diario ($) — vacío = el del puesto", max_length=10, required=False))
        self.add_item(discord.ui.TextInput(
            label="Permisos (opcional, separados por comas)", max_length=200, required=False))
        self.add_item(discord.ui.TextInput(
            label="Rol de Discord (ID o @mencion)", max_length=24, required=False))

    async def on_submit(self, interaction: discord.Interaction):
        from bot.cogs.companies import finish_hire
        position_id = self.children[0].values[0]
        salary_raw = self.children[1].value
        perms = self.children[2].value or ""
        role_id = _parse_role_id(self.children[3].value)
        salary = _int_value(salary_raw, -1) if salary_raw.strip() else -1
        await finish_hire(interaction, self.company_id, self.member_id,
                          None if position_id == "none" else position_id,
                          salary if salary >= 0 else None, perms, role_id)


class HireMemberSelect(discord.ui.View):
    """Paso 1 del alta: elegir a quien contratar."""

    def __init__(self, company_id: str, candidates, timeout: float = 90.0):
        super().__init__(timeout=timeout)
        self.company_id = company_id
        options = [
            discord.SelectOption(label=(m.display_name or m.name)[:100], value=str(m.id))
            for m in candidates[:25]
        ] or [discord.SelectOption(label="No hay miembros que contratar", value="none",
                                   description="Invita gente al servidor")]
        self.add_item(discord.ui.Select(
            placeholder="Elige a quién contratar", min_values=1, max_values=1, options=options))
        self.value = None

    async def select_callback(self, interaction: discord.Interaction):
        member_id = self.children[0].values[0]
        if member_id == "none":
            await interaction.response.send_message(
                embed=error_embed("Sin candidatos", "No hay miembros en el servidor a los que contratar."),
                ephemeral=True)
            return
        self.value = member_id
        positions = await B.company_positions(self.company_id)
        await interaction.response.send_modal(HireModal(self.company_id, member_id, positions))
        self.stop()


class RoleAssignSelect(discord.ui.View):
    """Asigna el rol de Discord de un puesto a un empleado concreto."""

    def __init__(self, company_id: str, company_name: str, positions, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.company_id = company_id
        self.company_name = company_name
        self.positions = [p for p in positions if p.get("role_id")]
        options = [discord.SelectOption(label=p.get("name")[:100], value=p.get("id"),
                                        description="Asignar este rol al empleado")
                   for p in self.positions[:25]]
        if not options:
            options = [discord.SelectOption(label="Ningún puesto tiene rol", value="none")]
        self.add_item(discord.ui.Select(
            placeholder="Rol de empresa que quieres recibir", min_values=1, max_values=1,
            options=options))

    async def select_callback(self, interaction: discord.Interaction):
        position_id = self.children[0].values[0]
        if position_id == "none":
            await interaction.response.send_message(
                embed=warning_embed("Sin roles", "Ningún puesto de esta empresa tiene rol de Discord."),
                ephemeral=True)
            return
        position = next((p for p in self.positions if p.get("id") == position_id), None)
        role = interaction.guild.get_role(int(position.get("role_id")))
        member = interaction.user
        if not role:
            await interaction.response.send_message(
                embed=error_embed("Rol no encontrado", "Ese rol ya no existe en el servidor."),
                ephemeral=True)
            return
        if not member.guild_permissions.manage_roles and role >= member.top_role:
            await interaction.response.send_message(
                embed=error_embed("Sin permisos", "No puedo darte un rol por encima del tuyo."),
                ephemeral=True)
            return
        try:
            await member.add_roles(role, reason=f"Rol de empresa {self.company_name}")
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Permiso denegado", "No me dejan asignar ese rol."),
                ephemeral=True)
            return
        await B.aexecute(
            "UPDATE company_members SET discord_role_id=$1, updated_at=NOW()"
            " WHERE company_id=$2 AND discord_id=$3",
            (str(role.id), self.company_id, str(member.id)),
        )
        await interaction.response.send_message(
            embed=success_embed("Rol asignado", f"Has recibido el rol {role.mention} de **{self.company_name}**."),
            ephemeral=True)
        self.stop()


class PublicJobSelectView(discord.ui.View):
    """Selector de empleo publico con boton de solicitud directa."""

    def __init__(self, guild_id: str, jobs, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        options = [
            discord.SelectOption(
                label=(j.get("name") or "Empleo")[:100],
                value=j.get("id"),
                description=f"{money(j.get('salary'))} diarios"[:100],
                emoji=safe_emoji(j.get("emoji")),
            )
            for j in jobs[:25]
        ]
        if options:
            self.add_item(discord.ui.Select(
                placeholder="Elige el empleo público al que quieres aspirar",
                min_values=1, max_values=1, options=options))


def _decode_perms(raw) -> set:
    return B._clean_perms(raw)


def _parse_role_id(value):
    """Acepta `@rol`, `<@&123>` o `123` y devuelve el ID limpio."""
    raw = (value or "").strip()
    if not raw:
        return None
    raw = raw.replace("<@&", "").replace("&", "").replace(">", "").replace("@", "").strip()
    return raw if raw.isdigit() else None
