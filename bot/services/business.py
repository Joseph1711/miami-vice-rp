"""Motor economico y de datos del sistema de empleos publicos y empresas privadas.

REGLA INNEGOCIABLE DEL MODULO
-----------------------------
Ninguna funcion de este archivo crea dinero. Todo movimiento se escribe como un
intercambio entre dos cuentas que ya existen:

    Cliente paga  ->  cliente.cash -X      empresa.funds +X
    Nomina        ->  empresa.funds -X     empleado.bank  +X
    Retiro       ->  empresa.funds -X     dueno.cash    +X
    Inversion    ->  inversor.cash -X     empresa.funds +X
    Venta empresa->  comprador.cash -X    vendedor.cash  +X   (el importe entra a la empresa)
    Accion nueva ->  comprador.cash -X    empresa.funds +X
    Dividendo    ->  empresa.funds -X     accionista.bank +X

Cada operacion se ejecuta dentro de UNA transaccion (`aexecute_atomic`) con
guardas `WHERE saldo >= importe`: si una sola parte falla, no se escribe nada.
Los saldos de empresa NUNCA pueden quedar negativos.
"""

import asyncio
import datetime
import logging

from bot.db import aexecute, aexecute_atomic
from bot.helpers import (EMOJI_FALLBACK, generate_id, async_get_or_create_user,
                         async_get_or_create_guild_config, safe_emoji)
from bot.services.catalogs import CITY_OWNER_ID, DEFAULT_JOBS, CITY_COMPANIES

logger = logging.getLogger("bot.business")

# ---------------------------------------------------------------------------
# Estados financieros de una empresa
# ---------------------------------------------------------------------------
COMPANY_STATUS = {
    "active": {"emoji": "\U0001F7E2", "label": "Activa", "color": 0x57F287},
    "difficulty": {"emoji": "\U0001F7E1", "label": "En dificultades", "color": 0xFEE75C},
    "bankrupt": {"emoji": "\U0001F534", "label": "En quiebra", "color": 0xED4245},
    "closed": {"emoji": "⚫", "label": "Cerrada", "color": 0x6D6875},
    "for_sale": {"emoji": "\U0001F3F7️", "label": "En venta", "color": 0x00E5FF},
}

# Un estado que no permite operar sobre el negocio.
BLOCKED_STATUSES = ("closed", "bankrupt")

# ---------------------------------------------------------------------------
# Jerarquia de permisos
# ---------------------------------------------------------------------------
PERMISSIONS = {
    "hire": {
        "label": "Contratar / despedir",
        "desc": "Dar de alta y de baja empleados de la empresa.",
    },
    "positions": {
        "label": "Gestionar puestos",
        "desc": "Crear, editar y eliminar puestos (y sus roles de Discord).",
    },
    "menu": {
        "label": "Gestionar menú",
        "desc": "Crear y editar productos, servicios y precios.",
    },
    "payroll": {
        "label": "Pagar nómina",
        "desc": "Ejecutar el pago de salarios a los empleados.",
    },
    "finance": {
        "label": "Ver finanzas",
        "desc": "Consultar fondos e historial financiero completo.",
    },
    "withdraw": {
        "label": "Retirar fondos",
        "desc": "Retirar capital de la caja de la empresa.",
    },
    "shares": {
        "label": "Acciones y dividendos",
        "desc": "Gestionar las acciones de la sociedad y repartir dividendos.",
    },
    "config": {
        "label": "Configurar empresa",
        "desc": "Cambiar categoria, ubicacion, fiscalidad y ajustes.",
    },
}

# Tipos de movimiento del libro mayor empresarial.
LEDGER = {
    "sale": ("Venta", "\U0001F372"),
    "service": ("Servicio", "✂️"),
    "payroll": ("Nómina", "\U0001F4B0"),
    "deposit": ("Aportación", "\U0001F4E6"),
    "investment": ("Inversión", "\U0001F4C8"),
    "withdrawal": ("Retiro del propietario", "\U0001F4B8"),
    "expense": ("Gasto", "\U0001F6D2"),
    "shares": ("Acciones", "\U0001F4C5"),
    "dividend": ("Dividendo", "\U0001F4B0"),
    "company_sale": ("Venta de la empresa", "\U0001F3E2"),
    "tax": ("Impuestos", "\U0001F4E6"),
    "adjustment": ("Ajuste", "⚖️"),
    "inactivation": ("Inicialización", "\U0001F4E3"),
    "closure": ("Cierre del negocio", "\U0001F6D1"),
}

# Tipos de transaccion registrados en la cartera personal del ciudadano.
# La clave es la que se guarda en `transactions.type` (compatible con el resto del
# bot) y el valor es la etiqueta legible que ve el ciudadano.
TX = {
    "company_purchase": "Compra en empresa",
    "company_service": "Contratacion de servicio",
    "company_salary": "Salario de empresa",
    "company_deposit": "Aportacion a empresa",
    "company_withdrawal": "Retiro de la empresa",
    "company_buy": "Compra de empresa",
    "company_sale_income": "Venta de empresa",
    "company_shares": "Compra de acciones",
    "company_dividend": "Dividendo de empresa",
    "company_expense": "Pago de empresa",
    "company_closure": "Cierre de empresa",
}
TX_LABELS = {label: key for key, label in TX.items()}

# ---------------------------------------------------------------------------
# Utilidades numericas
# ---------------------------------------------------------------------------


def money(value, default: int = 0) -> int:
    """NUMERIC llega como float (SQLite) o Decimal (psycopg): a entero limpio."""
    if value is None:
        return default
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _clean_perms(raw) -> set:
    if not raw:
        return set()
    if isinstance(raw, (list, set, tuple)):
        return {str(item).strip() for item in raw if str(item).strip() in PERMISSIONS}
    return {part.strip() for part in str(raw).split(",") if part.strip() in PERMISSIONS}


def encode_perms(perms) -> str:
    if not perms:
        return ""
    if isinstance(perms, str):
        items = _clean_perms(perms)
    else:
        items = {str(p).strip() for p in perms if str(p).strip() in PERMISSIONS}
    return ",".join(sorted(items))


class BusinessError(Exception):
    """Error de negocio con mensaje listo para mostrar al usuario."""

    def __init__(self, message: str, embed=None):
        super().__init__(message)
        self.message = message
        self.embed = embed


class InsufficientFunds(BusinessError):
    """La empresa no puede cubrir la operacion. Nunca genera el dinero faltante."""

    def __init__(self, message, available=0, required=0, detail=None):
        super().__init__(message)
        self.available = available
        self.required = required
        self.deficit = max(0, required - available)
        self.detail = detail or []


# ---------------------------------------------------------------------------
# Anti-duplicado: dos clics rapidos no pueden ejecutar dos veces la misma compra
# ---------------------------------------------------------------------------
_ACTION_LOCKS: dict = {}
_ACTION_LOCKS_GUARD = asyncio.Lock()


class ActionInProgress(BusinessError):
    pass


async def claim_action(key: str, seconds: float = 2.5) -> None:
    """Reserva `key` durante `seconds`. Lanza si ya hay una accion en vuelo."""
    async with _ACTION_LOCKS_GUARD:
        now = datetime.datetime.utcnow().timestamp()
        busy = [k for k, until in _ACTION_LOCKS.items() if until <= now]
        for k in busy:
            _ACTION_LOCKS.pop(k, None)
        if _ACTION_LOCKS.get(key, 0) > now:
            raise ActionInProgress("⏳ Ya hay una operacion en curso. Espera un momento.")
        _ACTION_LOCKS[key] = now + seconds


def release_action(key: str) -> None:
    _ACTION_LOCKS.pop(key, None)


# ---------------------------------------------------------------------------
# LECTURAS
# ---------------------------------------------------------------------------


async def get_company(company_id: str, guild_id: str):
    return await aexecute(
        "SELECT * FROM companies WHERE id=$1 AND guild_id=$2",
        (company_id, guild_id),
        fetch="one",
    )


async def find_company(guild_id: str, name: str):
    """Busqueda exacta (sin distinguir mayusculas) antes que parcial."""
    exact = await aexecute(
        "SELECT * FROM companies WHERE guild_id=$1 AND name ILIKE $2 LIMIT 1",
        (guild_id, name),
        fetch="one",
    )
    if exact:
        return exact
    return await aexecute(
        "SELECT * FROM companies WHERE guild_id=$1 AND name ILIKE $2 LIMIT 1",
        (guild_id, f"%{name}%"),
        fetch="one",
    )


async def get_owned_company(guild_id: str, user_id: str):
    return await aexecute(
        "SELECT * FROM companies WHERE guild_id=$1 AND owner_id=$2 LIMIT 1",
        (guild_id, user_id),
        fetch="one",
    )


async def get_managed_company(guild_id: str, user_id: str):
    """Empresa propia o, si no se es dueno, la primera que se gestiona.

    Un gerente puede tener varias empresas; sin nombre solo se resuelve la
    primera para que `/empresa nomina` siga siendo usable sin argumentos.
    """
    owned = await get_owned_company(guild_id, user_id)
    if owned:
        return owned
    return await aexecute(
        """SELECT c.* FROM companies c
           JOIN company_members cm ON cm.company_id = c.id
           WHERE c.guild_id=$1 AND cm.discord_id=$2 AND cm.member_status='active'
             AND (cm.is_manager = TRUE OR cm.permissions IS NOT NULL AND cm.permissions <> '')
           ORDER BY cm.is_manager DESC, cm.joined_at LIMIT 1""",
        (guild_id, user_id),
        fetch="one",
    )


async def get_member(company_id: str, user_id: str):
    """Fila de un empleado, con los permisos que lerega su puesto."""
    return await aexecute(
        """SELECT cm.*, p.permissions as position_permissions
           FROM company_members cm
           LEFT JOIN company_positions p ON p.id = cm.position_id
           WHERE cm.company_id=$1 AND cm.discord_id=$2""",
        (company_id, user_id),
        fetch="one",
    )


async def company_employees(company_id: str, only_active: bool = True):
    """Plantilla de la empresa.

    La fila del dueno (rol 'Propietario' en el sistema nuevo, 'Dueño' en el
    heredado) queda fuera: su poder viene de `companies.owner_id` y no cobra
    nomina. El resto son empleados con derecho a salario.
    """
    rows = await aexecute(
        """SELECT cm.*, p.name as position_name, p.permissions as position_permissions
           FROM company_members cm
           LEFT JOIN company_positions p ON p.id = cm.position_id
           WHERE cm.company_id=$1
           ORDER BY cm.salary DESC, cm.joined_at""",
        (company_id,),
        fetch="all",
    ) or []
    rows = [r for r in rows if (r.get("role") or "") not in ("Propietario", "Dueño")]
    if only_active:
        rows = [r for r in rows if (r.get("member_status") or "active") == "active"]
    return rows


async def company_positions(company_id: str, only_active: bool = True):
    rows = await aexecute(
        "SELECT * FROM company_positions WHERE company_id=$1 ORDER BY sort_order, created_at",
        (company_id,),
        fetch="all",
    ) or []
    if only_active:
        rows = [r for r in rows if r.get("is_active", True)]
    return rows


async def company_catalog(company_id: str, kind: str = None, only_active: bool = False):
    query = "SELECT * FROM company_catalog WHERE company_id=$1"
    params = [company_id]
    if kind:
        query += " AND kind=$2"
        params.append(kind)
    query += " ORDER BY is_active DESC, created_at"
    rows = await aexecute(query, tuple(params), fetch="all") or []
    if only_active:
        rows = [r for r in rows if r.get("is_active", True)]
    return rows


async def company_ledger(company_id: str, limit: int = 15, kind: str = None):
    query = "SELECT * FROM company_transactions WHERE company_id=$1"
    params = [company_id]
    if kind:
        query += " AND kind=$2"
        params.append(kind)
    query += " ORDER BY created_at DESC, id DESC LIMIT $3"
    params.append(limit)
    return await aexecute(query, tuple(params), fetch="all") or []


async def company_shares_config(company_id: str):
    return await aexecute(
        "SELECT * FROM company_shares WHERE company_id=$1",
        (company_id,),
        fetch="one",
    )


async def company_shareholders(company_id: str, only_with_shares: bool = True):
    rows = await aexecute(
        "SELECT * FROM company_shareholders WHERE company_id=$1 ORDER BY shares DESC",
        (company_id,),
        fetch="all",
    ) or []
    if only_with_shares:
        rows = [r for r in rows if money(r.get("shares")) > 0]
    return rows


async def pending_payroll(company_id: str):
    """Nómina pendiente: salario acumulado por cada empleado activo."""
    members = await company_employees(company_id)
    lines = []
    total = 0
    for member in members:
        amount = money(member.get("pending_salary"))
        if amount <= 0:
            continue
        lines.append({
            "member": member,
            "amount": amount,
            "position": member.get("position_name") or member.get("role") or "Empleado",
        })
        total += amount
    return total, lines


# ---------------------------------------------------------------------------
# PERMISOS Y NIVELES DE ACCESO
# ---------------------------------------------------------------------------


async def resolve_access(guild_id: str, user_id: str, company_id: str = None):
    """Nivel de acceso del ciudadano sobre una empresa.

    Devuelve {"level", "member", "permissions", "company"} donde `level` es
    owner / manager / employee / customer / none.
    """
    company = None
    if company_id:
        company = await get_company(company_id, guild_id)
    if not company:
        return {"level": "none", "member": None, "permissions": set(), "company": None}

    if str(company.get("owner_id")) == str(user_id):
        return {
            "level": "owner",
            "member": None,
            "permissions": set(PERMISSIONS.keys()),
            "company": company,
        }

    member = await get_member(company_id, user_id)
    if not member or (member.get("member_status") or "active") != "active":
        return {"level": "customer", "member": None, "permissions": set(), "company": company}

    granted = _clean_perms(member.get("permissions")) | _clean_perms(member.get("position_permissions"))
    if member.get("is_manager"):
        granted |= set(PERMISSIONS.keys()) - {"shares", "config", "withdraw"}
        level = "manager"
    elif granted:
        level = "manager"
    else:
        level = "employee"
    return {"level": level, "member": member, "permissions": granted, "company": company}


def can(access, permission: str) -> bool:
    if not access or access.get("level") == "none":
        return False
    if access.get("level") == "owner":
        return True
    return permission in (access.get("permissions") or set())


async def require_access(interaction, company_id: str, permission: str = None, owner_only: bool = False):
    """Valida acceso y responde al ciudadano si no lo tiene.

    Devuelve el diccionario de acceso, o None si ya se le ha contestado con un
    error. `permission=None` solo exige que la empresa exista y sea visible.
    """
    guild_id = str(interaction.guild_id)
    user_id = str(interaction.user.id)
    access = await resolve_access(guild_id, user_id, company_id)
    company = access.get("company")
    name = (company or {}).get("name", "esa empresa")

    if access["level"] == "none":
        await _deny(interaction, "Empresa no encontrada",
                    "No existe esa empresa en este servidor.")
        return None
    if owner_only and access["level"] != "owner":
        await _deny(interaction, "Solo el dueño",
                    f"La gestión de **{name}** la lleva su propietario. "
                    f"Pídeselo directamente a <@{company.get('owner_id')}>.")
        return None
    if permission and not can(access, permission):
        need = PERMISSIONS.get(permission, {}).get("label", permission)
        await _deny(interaction, "Sin permisos",
                    f"Necesitas el permiso **{need}** en **{name}**. "
                    f"Tu rol actual: {access['level']}.")
        return None
    return access


async def _deny(interaction, title: str, message: str):
    """Responde con un error de forma compatible con cualquier tipo de interaccion."""
    from bot.embeds import error_embed

    embed = error_embed(title, message)
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# CIUDADANO: cartera personal
# ---------------------------------------------------------------------------


def _cash_guard(user_id: str, guild_id: str, amount: int, signed: int):
    """Update del efectivo con guarda de saldo (signed = -1 resta, +1 suma)."""
    if signed < 0:
        return (
            "UPDATE users SET cash=cash-$1, updated_at=NOW() "
            "WHERE discord_id=$2 AND guild_id=$3 AND cash >= $4",
            (amount, user_id, guild_id, amount),
            "count",
        )
    return (
        "UPDATE users SET cash=cash+$1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
        (amount, user_id, guild_id),
        "count",
    )


def _bank_credit(user_id: str, guild_id: str, amount: int):
    return (
        "UPDATE users SET bank=bank+$1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
        (amount, user_id, guild_id),
        "count",
    )


def _treasury_credit(guild_id: str, amount: int):
    """Suma un importe a la Tesoreria Municipal creando la fila si no existe.

    Es la contraparte real cuando no hay un ciudadano al que pagar: el dinero
    sale del bolsillo del comprador y entra en las arcas del servidor, sin
    desaparecer ni multiplicarse.
    """
    return (
        """INSERT INTO treasury (id, guild_id, balance, created_at, updated_at)
           VALUES ($1,$2,$3,NOW(),NOW())
           ON CONFLICT (guild_id) DO UPDATE SET balance=treasury.balance+$3, updated_at=NOW()""",
        (generate_id(), guild_id, amount),
        "count",
    )


def _user_tx(user_id: str, guild_id: str, tx_type: str, amount: float, description: str):
    """Asienta un movimiento en la cartera personal del ciudadano.

    `tx_type` admite la clave tecnica ('company_purchase') o su etiqueta legible
    ('Compra en empresa'); en `transactions.type` siempre queda la clave.
    """
    key = TX_LABELS.get(tx_type, tx_type)
    return (
        """INSERT INTO transactions (id, discord_id, guild_id, type, amount, description, created_at)
           VALUES ($1,$2,$3,$4,$5,$6,NOW())""",
        (generate_id(), user_id, guild_id, key, amount, description),
        None,
    )


def _ledger_tx(company, kind: str, amount: int, balance_after: int, description: str,
               actor_id=None, counterparty_id=None, ref_id=None):
    return (
        """INSERT INTO company_transactions
             (id, guild_id, company_id, kind, amount, balance_after, description,
              actor_id, counterparty_id, ref_id, created_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,NOW())""",
        (generate_id(), company["guild_id"], company["id"], kind, amount, balance_after,
         description, actor_id, counterparty_id, ref_id),
        None,
    )


# ---------------------------------------------------------------------------
# EMPRESAS: ciclo de vida
# ---------------------------------------------------------------------------


async def create_company(guild_id: str, owner_id: str, name: str, description: str,
                         category: str, location: str, emoji: str, tax_rate: int):
    config = await async_get_or_create_guild_config(guild_id)
    cost = money(config.get("company_creation_cost"), 5000)

    taken = await aexecute(
        "SELECT id FROM companies WHERE guild_id=$1 AND name ILIKE $2",
        (guild_id, name),
        fetch="one",
    )
    if taken:
        raise BusinessError(f"Ya existe una empresa llamada **{name}** en este servidor.")

    already = await get_owned_company(guild_id, owner_id)
    if already:
        raise BusinessError(
            f"Solo puedes ser dueno de una empresa a la vez. Ya diriges **{already['name']}**."
        )

    await async_get_or_create_user(owner_id, guild_id)
    company_id = generate_id()
    now = datetime.datetime.utcnow()

    batch = [
        # La licencia se cobra del bolsillo del dueno: el dinero sale de la
        # circulacion (tasas de registro), nunca se inventa ni se crea.
        _cash_guard(owner_id, guild_id, cost, -1),
        (
            """INSERT INTO companies
                 (id, guild_id, owner_id, name, description, funds, tax_rate, category,
                  location, emoji, status, status_note, status_changed_at, public_listing,
                  payroll_mode, allow_multiple_jobs, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,0,$6,$7,$8,$9,'active','',$10,FALSE,'manual',TRUE,$10,$10)""",
            (company_id, guild_id, owner_id, name, description, tax_rate, category,
             location, emoji, now),
            None,
        ),
        # El dueno se registra como miembro para que pueda tener rol de Discord,
        # pero su poder viene de `companies.owner_id`, no de esta fila.
        (
            """INSERT INTO company_members
                 (id, company_id, discord_id, guild_id, role, salary, joined_at, position_id,
                  member_status, permissions, pending_salary, is_manager, hired_by, updated_at)
               VALUES ($1,$2,$3,$4,'Propietario',0,$5,NULL,'active','',0,FALSE,$6,$5)""",
            (generate_id(), company_id, owner_id, guild_id, now, owner_id),
            None,
        ),
        (
            """INSERT INTO company_transactions
                 (id, guild_id, company_id, kind, amount, balance_after, description,
                  actor_id, created_at)
               VALUES ($1,$2,$3,'inactivation',0,0,$4,$5,NOW())""",
            (generate_id(), guild_id, company_id, f"Constitucion de la empresa (coste {cost})", owner_id),
            None,
        ),
    ]
    if cost > 0:
        batch.append(_user_tx(owner_id, guild_id, "company_fee", -cost,
                              f"Licencia de constitution de {name}"))
    results = await aexecute_atomic(batch)
    if cost > 0 and not results[0]:
        raise InsufficientFunds(
            f"Constituir una empresa cuesta {cost:,}. No tienes efectivo suficiente.",
            required=cost,
        )
    return company_id, cost


async def set_company_status(guild_id: str, company_id: str, status: str, note: str = "",
                             actor_id: str = None, clear_sale: bool = False):
    if status not in COMPANY_STATUS:
        raise BusinessError("Estado financiero desconocido.")
    company = await get_company(company_id, guild_id)
    if not company:
        raise BusinessError("La empresa ya no existe.")
    label = COMPANY_STATUS[status]["label"]
    description = f"Estado financiero: {label}" + (f" — {note}" if note else "")
    await aexecute_atomic([
        (
            "UPDATE companies SET status=$1, status_note=$2, status_changed_at=NOW(), updated_at=NOW(),"
            " sale_price=$3, public_listing=$4 WHERE id=$5 AND guild_id=$6",
            (status, note, None if clear_sale else company.get("sale_price"),
             False if clear_sale else company.get("public_listing"), company_id, guild_id),
            "count",
        ),
        _ledger_tx(company, "adjustment", 0, money(company.get("funds")), description, actor_id),
    ])
    company["status"] = status
    return company


async def refresh_financial_health(guild_id: str, company_id: str):
    """Reevalua 'en dificultades' segun la cobertura de la nomina pendiente.

    No decide a quien despedir ni modifica salarios: solo refleja la realidad
    economica en el estado visible de la empresa.
    """
    company = await get_company(company_id, guild_id)
    if not company:
        return None
    status = company.get("status") or "active"
    if status in BLOCKED_STATUSES or status == "for_sale":
        return company
    funds = money(company.get("funds"))
    payroll, _ = await pending_payroll(company_id)
    new_status = "active" if funds >= payroll else "difficulty"
    if new_status != status:
        await aexecute(
            "UPDATE companies SET status=$1, status_changed_at=NOW(), updated_at=NOW() WHERE id=$2",
            (new_status, company_id),
        )
        company["status"] = new_status
    return company


# ---------------------------------------------------------------------------
# PUESTOS (definidos por el dueno, sin lista fija)
# ---------------------------------------------------------------------------


async def create_position(guild_id: str, company_id: str, name: str, salary: int,
                          description: str = "", role_id: str = None, permissions=None,
                          max_members: int = 0):
    duplicate = await aexecute(
        "SELECT id FROM company_positions WHERE company_id=$1 AND name ILIKE $2",
        (company_id, name),
        fetch="one",
    )
    if duplicate:
        raise BusinessError(f"El puesto **{name}** ya existe en esta empresa.")
    position_id = generate_id()
    await aexecute(
        """INSERT INTO company_positions
             (id, company_id, guild_id, name, salary, description, discord_role_id,
              permissions, max_members, sort_order, is_active, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,TRUE,NOW(),NOW())""",
        (position_id, company_id, guild_id, name, salary, description, role_id,
         encode_perms(permissions), max_members, 0),
    )
    return position_id


async def position_headcount(company_id: str, position_id: str) -> int:
    row = await aexecute(
        "SELECT COUNT(*) AS c FROM company_members WHERE company_id=$1 AND position_id=$2",
        (company_id, position_id),
        fetch="one",
    )
    return money((row or {}).get("c"))


# ---------------------------------------------------------------------------
# CONTRATACION
# ---------------------------------------------------------------------------


async def hire(guild_id: str, company_id: str, employee_id: str, position_id: str,
               salary: int, actor_id: str, role_id: str = None, permissions=None,
               is_manager: bool = False, notes: str = ""):
    company = await get_company(company_id, guild_id)
    if not company:
        raise BusinessError("La empresa no existe.")
    if (company.get("status") or "active") in BLOCKED_STATUSES:
        raise BusinessError(
            f"La empresa esta en estado **{COMPANY_STATUS[company['status']]['label']}** y no admite altas."
        )
    if str(company.get("owner_id")) == str(employee_id):
        raise BusinessError("El dueno de la empresa ya esta registrado como propietario.")

    position = None
    if position_id:
        position = await aexecute(
            "SELECT * FROM company_positions WHERE id=$1 AND company_id=$2",
            (position_id, company_id),
            fetch="one",
        )
        if not position:
            raise BusinessError("El puesto indicado no existe en esta empresa.")
        if money(position.get("max_members")) > 0:
            current = await position_headcount(company_id, position_id)
            if current >= money(position.get("max_members")):
                raise BusinessError(
                    f"El puesto **{position['name']}** ya tiene su limite de "
                    f"{money(position.get('max_members'))} plazas ocupadas."
                )
        if salary is None:
            salary = money(position.get("salary"))

    salary = money(salary)
    if salary < 0:
        raise BusinessError("El salario no puede ser negativo.")

    await async_get_or_create_user(employee_id, guild_id)
    existing = await get_member(company_id, employee_id)

    perms = encode_perms(permissions) if permissions is not None else (
        encode_perms(position.get("permissions")) if position else ""
    )
    position_name = (position or {}).get("name") or "Empleado"
    discord_role = role_id or (position or {}).get("discord_role_id")

    if existing:
        await aexecute(
            """UPDATE company_members
               SET role=$1, salary=$2, position_id=$3, member_status='active',
                   permissions=$4, discord_role_id=$5, is_manager=$6, hired_by=$7,
                   notes=$8, updated_at=NOW()
               WHERE id=$9""",
            (position_name, salary, position_id, perms, discord_role, is_manager,
             actor_id, notes, existing["id"]),
        )
        member_id = existing["id"]
        created = False
    else:
        member_id = generate_id()
        await aexecute(
            """INSERT INTO company_members
                 (id, company_id, discord_id, guild_id, role, salary, joined_at, position_id,
                  member_status, permissions, discord_role_id, pending_salary, is_manager,
                  hired_by, notes, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,NOW(),$7,'active',$8,$9,0,$10,$11,$12,NOW())""",
            (member_id, company_id, employee_id, guild_id, position_name, salary,
             position_id, perms, discord_role, is_manager, actor_id, notes),
        )
        created = True

    return {
        "member_id": member_id,
        "created": created,
        "position": position_name,
        "salary": salary,
        "discord_role_id": discord_role,
    }


async def fire(guild_id: str, company_id: str, employee_id: str):
    company = await get_company(company_id, guild_id)
    member = await get_member(company_id, employee_id)
    if not member:
        raise BusinessError("Ese ciudadano no trabaja en tu empresa.")
    if str(company.get("owner_id")) == str(employee_id):
        raise BusinessError("No puedes despedir al dueno de la empresa.")
    await aexecute(
        "DELETE FROM company_members WHERE id=$1 AND company_id=$2",
        (member["id"], company_id),
    )
    return {
        "discord_role_id": member.get("discord_role_id"),
        "position": member.get("position_name") or member.get("role") or "Empleado",
        "pending": money(member.get("pending_salary")),
    }


async def accrue_salary(company_id: str, days: int = 1):
    """Genera la nomina pendiente de los empleados con salario > 0."""
    members = await company_employees(company_id)
    touched = 0
    for member in members:
        salary = money(member.get("salary"))
        if salary <= 0:
            continue
        await aexecute(
            "UPDATE company_members SET pending_salary=pending_salary+$1, updated_at=NOW() WHERE id=$2",
            (salary * max(1, days), member["id"]),
        )
        touched += 1
    return touched


# ---------------------------------------------------------------------------
# CAJA DE LA EMPRESA: entradas y salidas
# ---------------------------------------------------------------------------


async def owner_deposit(guild_id: str, company_id: str, actor_id: str, amount: int,
                        kind: str = "deposit"):
    """Dinero del dueno -> empresa (aportacion o inversion)."""
    amount = money(amount)
    if amount <= 0:
        raise BusinessError("La cantidad debe ser mayor que cero.")

    company = await get_company(company_id, guild_id)
    if not company:
        raise BusinessError("La empresa no existe.")
    if (company.get("status") or "active") in BLOCKED_STATUSES:
        raise BusinessError(
            f"No se pueden hacer aportes a una empresa **{COMPANY_STATUS[company['status']]['label']}**."
        )
    if str(company.get("owner_id")) != str(actor_id):
        raise BusinessError("Solo el dueno puede aportar capital a la empresa.")

    await async_get_or_create_user(actor_id, guild_id)
    before = money(company.get("funds"))
    label = LEDGER.get(kind, LEDGER["deposit"])
    description = f"{label[0]} del dueno a la caja de la empresa"

    results = await aexecute_atomic([
        _cash_guard(actor_id, guild_id, amount, -1),
        (
            "UPDATE companies SET funds=funds+$1, updated_at=NOW() WHERE id=$2",
            (amount, company_id),
            "count",
        ),
        _user_tx(actor_id, guild_id, TX["company_deposit"], -amount,
                 f"{description} — {company['name']}"),
        _ledger_tx(company, kind, amount, before + amount, description, actor_id),
    ])
    if not results[0]:
        raise InsufficientFunds(
            "No tienes efectivo suficiente para aportar ese capital.",
            required=amount,
        )
    return {"amount": amount, "balance_after": before + amount}


async def owner_withdraw(guild_id: str, company_id: str, actor_id: str, amount: int):
    """Caja de la empresa -> cuenta personal del dueno. Nunca mas del disponible."""
    amount = money(amount)
    if amount <= 0:
        raise BusinessError("La cantidad debe ser mayor que cero.")

    company = await get_company(company_id, guild_id)
    if not company:
        raise BusinessError("La empresa no existe.")
    if str(company.get("owner_id")) != str(actor_id):
        raise BusinessError("Solo el dueno puede retirar capital de la empresa.")
    if (company.get("status") or "active") == "closed":
        raise BusinessError("Una empresa cerrada no admite movimientos de caja.")

    before = money(company.get("funds"))
    if amount > before:
        raise InsufficientFunds(
            "La empresa no tiene capital suficiente para ese retiro.",
            available=before,
            required=amount,
        )

    await async_get_or_create_user(actor_id, guild_id)
    results = await aexecute_atomic([
        (
            "UPDATE companies SET funds=funds-$1, updated_at=NOW() WHERE id=$2 AND funds >= $3",
            (amount, company_id, amount),
            "count",
        ),
        _cash_guard(actor_id, guild_id, amount, +1),
        _user_tx(actor_id, guild_id, TX["company_withdrawal"], amount,
                 f"Retiro de capital de {company['name']}"),
        _ledger_tx(company, "withdrawal", -amount, before - amount,
                   f"Retiro del propietario {actor_id}", actor_id),
    ])
    if not results[0]:
        raise InsufficientFunds(
            "La empresa no tiene capital suficiente para ese retiro.",
            available=before,
            required=amount,
        )
    return {"amount": amount, "balance_after": before - amount}


async def pay_expense(guild_id: str, company_id: str, actor_id: str, amount: int, description: str):
    """Pago de la empresa a un tercero (proveedor, servicios, multas...)."""
    amount = money(amount)
    if amount <= 0:
        raise BusinessError("La cantidad debe ser mayor que cero.")
    description = (description or "").strip()
    if not description:
        raise BusinessError("Indica el concepto del gasto.")

    company = await get_company(company_id, guild_id)
    if not company:
        raise BusinessError("La empresa no existe.")
    if (company.get("status") or "active") in BLOCKED_STATUSES:
        raise BusinessError("La empresa no admite pagos en su estado actual.")

    before = money(company.get("funds"))
    if amount > before:
        raise InsufficientFunds(
            "La empresa no tiene capital suficiente para cubrir ese gasto.",
            available=before,
            required=amount,
        )

    results = await aexecute_atomic([
        (
            "UPDATE companies SET funds=funds-$1, updated_at=NOW() WHERE id=$2 AND funds >= $3",
            (amount, company_id, amount),
            "count",
        ),
        _user_tx(actor_id, guild_id, TX["company_expense"], -amount,
                 f"Gasto de {company['name']}: {description}"),
        _ledger_tx(company, "expense", -amount, before - amount, description, actor_id),
    ])
    if not results[0]:
        raise InsufficientFunds(
            "La empresa no tiene capital suficiente para cubrir ese gasto.",
            available=before,
            required=amount,
        )
    return {"amount": amount, "balance_after": before - amount}


# ---------------------------------------------------------------------------
# NOMINA
# ---------------------------------------------------------------------------


async def run_payroll(guild_id: str, company_id: str, actor_id: str, mode: str = "full",
                      member_ids=None, note: str = ""):
    """Paga la nomina pendiente desde los fondos reales de la empresa.

    mode:
      full     -> paga el total pendiente (exige fondos para el 100%)
      partial  -> reparte el capital disponible entre los empleados con deuda,
                  de forma proporcional, y deja el resto anotado como pendiente.
    Si no hay capital para la nomina completa NO se crea dinero: se informa del
    deficit y el dueno decide (vender, reducir, despedir, inyectar capital...).
    """
    company = await get_company(company_id, guild_id)
    if not company:
        raise BusinessError("La empresa no existe.")
    if (company.get("status") or "active") in BLOCKED_STATUSES:
        raise BusinessError(
            f"No se puede pagar nomina en una empresa **{COMPANY_STATUS[company['status']]['label']}**."
        )

    funds = money(company.get("funds"))
    members = await company_employees(company_id)
    due = []
    for member in members:
        if member_ids and member["id"] not in member_ids:
            continue
        amount = money(member.get("pending_salary"))
        if amount > 0:
            due.append((member, amount))
    if not due:
        raise BusinessError("No hay salarios pendientes de pago para estos empleados.")

    total_due = sum(amount for _, amount in due)
    if total_due <= 0:
        raise BusinessError("No hay salarios pendientes de pago.")

    if mode == "full" and funds < total_due:
        detail = [
            f"<@{m['discord_id']}> — {m.get('position_name') or m.get('role') or 'Empleado'}: "
            f"**{money(a):,}** pendiente"
            for m, a in due
        ]
        raise InsufficientFunds(
            "FONDOS INSUFICIENTES para cubrir la nomina completa.",
            available=funds,
            required=total_due,
            detail=detail,
        )

    if mode == "partial":
        if funds <= 0:
            raise InsufficientFunds(
                "FONDOS INSUFICIENTES: la empresa no tiene caja para repartir la nomina.",
                available=funds,
                required=total_due,
                detail=[f"<@{m['discord_id']}>: **{a:,}** pendiente" for m, a in due],
            )
        ratio = funds / total_due
        payments = [(m, min(a, int(a * ratio))) for m, a in due]
        payments = [(m, a) for m, a in payments if a > 0]
        if not payments:
            raise InsufficientFunds(
                "El capital disponible no alcanza para pagar ni un minima parte de la nomina.",
                available=funds,
                required=total_due,
            )
        # El redondeo deja siempre el importe exacto para que no se pierda ni se cree.
        allocated = sum(a for _, a in payments)
        leftover = funds - allocated
        if leftover > 0:
            payments[0] = (payments[0][0], payments[0][1] + leftover)
            allocated += leftover
    else:
        payments = [(m, a) for m, a in due]
        allocated = sum(a for _, a in payments)

    for member, _ in payments:
        await async_get_or_create_user(member["discord_id"], guild_id)

    batch = [
        (
            "UPDATE companies SET funds=funds-$1, updated_at=NOW() WHERE id=$2 AND funds >= $3",
            (allocated, company_id, allocated),
            "count",
        ),
    ]
    for member, amount in payments:
        batch.append((
            "UPDATE company_members SET pending_salary=GREATEST(0, pending_salary-$1),"
            " last_paid_at=NOW(), updated_at=NOW() WHERE id=$2",
            (amount, member["id"]),
            "count",
        ))
        batch.append(_bank_credit(member["discord_id"], guild_id, amount))
        batch.append(_user_tx(
            member["discord_id"], guild_id, TX["company_salary"], amount,
            f"Salario de {company['name']} — {member.get('position_name') or member.get('role') or 'Empleado'}",
        ))

    run_id = generate_id()
    mode_label = "Nomina completa" if mode == "full" else "Nomina parcial (recorte)"
    detail_note = note or (
        f"{len(payments)} empleados liquidados"
        + (f"; {total_due - allocated:,} queda pendiente" if mode == "partial" and allocated < total_due else "")
    )
    batch.append((
        """INSERT INTO company_payroll_runs
             (id, company_id, guild_id, total, employee_count, mode, status, detail, created_by, created_at)
           VALUES ($1,$2,$3,$4,$5,$6,'completed',$7,$8,NOW())""",
        (run_id, company_id, guild_id, allocated, len(payments), mode, detail_note, actor_id),
        None,
    ))
    batch.append(_ledger_tx(
        company, "payroll", -allocated, funds - allocated,
        f"{mode_label} — {len(payments)} empleados", actor_id,
    ))

    results = await aexecute_atomic(batch)
    if not results[0]:
        raise InsufficientFunds(
            "La empresa no tiene capital suficiente para ejecutar la nomina.",
            available=funds,
            required=allocated,
        )

    await refresh_financial_health(guild_id, company_id)
    return {
        "run_id": run_id,
        "paid": allocated,
        "pending_left": max(0, total_due - allocated),
        "payments": [{"member": m, "amount": a} for m, a in payments],
        "paid_count": len(payments),
        "balance_after": funds - allocated,
        "total_due": total_due,
        "mode": mode,
    }


# ---------------------------------------------------------------------------
# CATALOGO Y COMPRAS
# ---------------------------------------------------------------------------


async def upsert_catalog_item(guild_id: str, company_id: str, kind: str, name: str, price: int,
                              description: str = "", emoji: str = "🍽️", item_id: str = None,
                              stock: int = -1, is_active: bool = True, role_id: str = None):
    price = money(price)
    if price < 0:
        raise BusinessError("El precio no puede ser negativo.")
    name = (name or "").strip()
    if len(name) < 2:
        raise BusinessError("El nombre debe tener al menos 2 caracteres.")
    if kind not in ("product", "service"):
        raise BusinessError("Tipo de articulo no valido.")

    duplicate = await aexecute(
        "SELECT id FROM company_catalog WHERE company_id=$1 AND kind=$2 AND name ILIKE $3",
        (company_id, kind, name),
        fetch="one",
    )
    if duplicate and duplicate["id"] != item_id:
        raise BusinessError(f"Ya existe **{name}** en el catalogo de {kind}s de la empresa.")

    if item_id:
        await aexecute(
            """UPDATE company_catalog
               SET name=$1, description=$2, price=$3, emoji=$4, stock=$5, is_active=$6,
                   role_id=$7, updated_at=NOW()
               WHERE id=$8 AND company_id=$9""",
            (name, description, price, emoji, stock, is_active, role_id, item_id, company_id),
        )
        return item_id, False

    item_id = generate_id()
    await aexecute(
        """INSERT INTO company_catalog
             (id, company_id, guild_id, kind, name, description, price, emoji, stock,
              is_active, role_id, sold_count, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,0,NOW(),NOW())""",
        (item_id, company_id, guild_id, kind, name, description, price, emoji, stock,
         is_active, role_id),
    )
    return item_id, True


async def delete_catalog_item(company_id: str, item_id: str):
    await aexecute(
        "DELETE FROM company_catalog WHERE id=$1 AND company_id=$2",
        (item_id, company_id),
    )


async def purchase_item(guild_id: str, company_id: str, item_id: str, buyer_id: str,
                        quantity: int = 1, ref_id: str = None):
    """Cliente compra un producto o contrata un servicio.

    El dinero sale de la cartera del cliente y entra en la caja de la empresa.
    Si algo falla (sin saldo, sin stock, empresa cerrada) no se escribe nada.
    """
    quantity = max(1, int(quantity))
    company = await get_company(company_id, guild_id)
    if not company:
        raise BusinessError("La empresa ya no existe.")
    if (company.get("status") or "active") in ("closed", "bankrupt"):
        raise BusinessError(
            f"**{company['name']}** esta **{COMPANY_STATUS[company['status']]['label']}** y no opera."
        )
    if str(company.get("owner_id")) == str(buyer_id):
        raise BusinessError("El dueno no puede comprar sus propios articulos: el dinero no saldria de la empresa.")

    item = await aexecute(
        "SELECT * FROM company_catalog WHERE id=$1 AND company_id=$2",
        (item_id, company_id),
        fetch="one",
    )
    if not item:
        raise BusinessError("Ese articulo ya no esta en el catalogo.")
    if not item.get("is_active", True):
        raise BusinessError(f"**{item['name']}** esta desactivado temporalmente.")

    unit_price = money(item.get("price"))
    total = unit_price * quantity
    stock = int(item.get("stock") if item.get("stock") is not None else -1)
    if stock >= 0 and stock < quantity:
        raise BusinessError(
            f"Solo quedan **{stock}** unidad(es) de **{item['name']}**."
        )

    await async_get_or_create_user(buyer_id, guild_id)
    funds = money(company.get("funds"))
    is_service = (item.get("kind") or "product") == "service"
    description = f"{item.get('emoji','')} {item['name']}" + (f" x{quantity}" if quantity > 1 else "")
    ledger_kind = "service" if is_service else "sale"

    batch = [
        _cash_guard(buyer_id, guild_id, total, -1),
        (
            "UPDATE companies SET funds=funds+$1, updated_at=NOW() WHERE id=$2",
            (total, company_id),
            "count",
        ),
        (
            "UPDATE company_catalog SET sold_count=sold_count+$1,"
            " stock=CASE WHEN stock < 0 THEN -1 ELSE stock-$1 END, updated_at=NOW() WHERE id=$2",
            (quantity, item_id),
            "count",
        ),
        _user_tx(buyer_id, guild_id,
                 TX["company_service"] if is_service else TX["company_purchase"],
                 -total, f"{description} en {company['name']}"),
        _ledger_tx(company, ledger_kind, total, funds + total,
                   f"Venta a {buyer_id}: {description}", None, buyer_id, ref_id),
    ]
    results = await aexecute_atomic(batch)
    if not results[0]:
        raise InsufficientFunds(
            f"No tienes efectivo suficiente para comprar **{item['name']}**.",
            required=total,
        )
    buyer = await aexecute(
        "SELECT cash FROM users WHERE discord_id=$1 AND guild_id=$2",
        (buyer_id, guild_id),
        fetch="one",
    )
    return {
        "item": item,
        "unit_price": unit_price,
        "quantity": quantity,
        "total": total,
        "company_balance": funds + total,
        "buyer_cash_after": money((buyer or {}).get("cash")),
        "kind": item.get("kind") or "product",
    }


# ---------------------------------------------------------------------------
# VENTA DE LA EMPRESA
# ---------------------------------------------------------------------------


async def list_company_for_sale(guild_id: str, company_id: str, owner_id: str, price: int,
                                note: str = "", public_listing: bool = True):
    price = money(price)
    if price <= 0:
        raise BusinessError("El precio de venta debe ser mayor que cero.")
    company = await get_company(company_id, guild_id)
    if not company:
        raise BusinessError("La empresa no existe.")
    if str(company.get("owner_id")) != str(owner_id):
        raise BusinessError("Solo el dueno puede poner la empresa en venta.")
    if (company.get("status") or "active") in BLOCKED_STATUSES:
        raise BusinessError("Una empresa cerrada o en quiebra no se puede poner en venta.")

    sale_id = generate_id()
    await aexecute(
        "UPDATE company_sales SET status='cancelled' WHERE company_id=$1 AND status='listed'",
        (company_id,),
    )
    await aexecute(
        """INSERT INTO company_sales (id, company_id, guild_id, seller_id, price, status, note, listed_at)
           VALUES ($1,$2,$3,$4,$5,'listed',$6,NOW())""",
        (sale_id, company_id, guild_id, owner_id, price, note),
    )
    await aexecute(
        """UPDATE companies SET status='for_sale', sale_price=$1, public_listing=$2,
           status_note='En venta', status_changed_at=NOW(), updated_at=NOW() WHERE id=$3""",
        (price, public_listing, company_id),
    )
    await aexecute(
        *_ledger_tx(company, "adjustment", 0, money(company.get("funds")),
                    f"Empresa puesta en venta por {price:,}", owner_id)[:2]
    )
    return sale_id, price


async def cancel_company_sale(guild_id: str, company_id: str, owner_id: str):
    company = await get_company(company_id, guild_id)
    if not company:
        raise BusinessError("La empresa no existe.")
    if str(company.get("owner_id")) != str(owner_id):
        raise BusinessError("Solo el dueno puede retirar la empresa de venta.")
    await aexecute(
        "UPDATE company_sales SET status='cancelled' WHERE company_id=$1 AND status='listed'",
        (company_id,),
    )
    await aexecute(
        """UPDATE companies SET status='active', sale_price=NULL, public_listing=FALSE,
           status_note='', status_changed_at=NOW(), updated_at=NOW() WHERE id=$1""",
        (company_id,),
    )


async def for_sale_market(guild_id: str):
    return await aexecute(
        """SELECT c.*, s.id AS sale_id, s.price AS asking_price
           FROM companies c
           JOIN company_sales s ON s.company_id = c.id
           WHERE c.guild_id=$1 AND s.status='listed' AND c.status='for_sale'
           ORDER BY s.price ASC""",
        (guild_id,),
        fetch="all",
    ) or []


async def buy_company(guild_id: str, company_id: str, buyer_id: str):
    """Compra de una empresa en venta.

    comprador -precio | vendedor +precio | empresa entra el importe en su caja.
    Los empleados, el menu, los puestos y la configuracion se conservan; solo
    cambia la propiedad.

    Excepcion documentada: si el vendedor es la ciudad (empresas sembradas por
    administracion), no existe un ciudadano al que pagar. El importe va a la
    Tesoreria Municipal y NO entra en la caja del negocio, porque la ciudad no
    venda un negocio con capital propio: se limita a entregar la propiedad.
    """
    company = await aexecute(
        """SELECT c.*, s.id AS sale_id, s.price AS asking_price
           FROM companies c
           JOIN company_sales s ON s.company_id = c.id
           WHERE c.id=$1 AND c.guild_id=$2 AND s.status='listed'""",
        (company_id, guild_id),
        fetch="one",
    )
    if not company:
        raise BusinessError("Esa empresa ya no esta en venta.")
    seller_id = str(company.get("owner_id"))
    is_city_sale = seller_id == CITY_OWNER_ID
    if not is_city_sale and seller_id == str(buyer_id):
        raise BusinessError("No puedes comprar tu propia empresa.")
    if (company.get("status") or "active") in BLOCKED_STATUSES:
        raise BusinessError("Esa empresa no admite compra en su estado actual.")

    price = money(company.get("asking_price"))
    if price <= 0:
        raise BusinessError("El anuncio de venta no tiene un precio valido.")

    await async_get_or_create_user(buyer_id, guild_id)
    if not is_city_sale:
        await async_get_or_create_user(seller_id, guild_id)
    funds = money(company.get("funds"))
    now = datetime.datetime.utcnow()
    buyer_already = await get_member(company_id, buyer_id)

    batch = [
        _cash_guard(buyer_id, guild_id, price, -1),
    ]
    if is_city_sale:
        # El precio de una empresa de la ciudad es ingreso municipal.
        batch.append(_treasury_credit(guild_id, price))
    else:
        batch.append(_cash_guard(seller_id, guild_id, price, +1))
    batch += [
        (
            """UPDATE companies SET owner_id=$1, status='active', sale_price=NULL,
               public_listing=FALSE, status_note='', status_changed_at=NOW(), updated_at=NOW()
               WHERE id=$2""",
            (buyer_id, company_id),
            "count",
        ),
        # El importe de la venta pertenece al negocio: entra en su caja, no se
        # queda en el bolsillo del comprador. En una venta de la ciudad el
        # dinero va a las arcas, asi que la caja se hereda tal cual.
        (
            "UPDATE companies SET funds=funds+$1, updated_at=NOW() WHERE id=$2",
            (0 if is_city_sale else price, company_id),
            "count",
        ),
        (
            """UPDATE company_sales SET status='sold', buyer_id=$1, sold_at=NOW()
               WHERE id=$2 AND status='listed'""",
            (buyer_id, company["sale_id"]),
            "count",
        ),
    ]
    if not is_city_sale:
        # El dueno anterior deja de ser miembro de su propia empresa.
        batch.append((
            "UPDATE company_members SET member_status='left', role='Ex-Propietario',"
            " discord_role_id=NULL, position_id=NULL, pending_salary=0, updated_at=NOW()"
            " WHERE company_id=$1 AND discord_id=$2",
            (company_id, seller_id),
            "count",
        ))
    # El comprador pasa a ser dueno: se reutiliza su ficha si ya trabajaba
    # aqui, y se crea si nunca estuvo en la plantilla.
    batch.append((
        """UPDATE company_members SET role='Propietario', salary=0, position_id=NULL,
           member_status='active', permissions='', discord_role_id=NULL, pending_salary=0,
           is_manager=FALSE, hired_by=$1, updated_at=NOW()
           WHERE company_id=$2 AND discord_id=$1""",
        (buyer_id, company_id),
        "count",
    ))
    if not buyer_already:
        batch.append((
            """INSERT INTO company_members
                 (id, company_id, discord_id, guild_id, role, salary, joined_at, position_id,
                  member_status, permissions, pending_salary, is_manager, hired_by, updated_at)
               VALUES ($1,$2,$3,$4,'Propietario',0,$5,NULL,'active','',0,FALSE,$3,$5)""",
            (generate_id(), company_id, buyer_id, guild_id, now),
            "count",
        ))
    batch.append(_user_tx(buyer_id, guild_id, TX["company_buy"], -price,
                          f"Compra de la empresa {company['name']}"
                          + ("" if is_city_sale else f" a {seller_id}")))
    if not is_city_sale:
        batch.append(_user_tx(seller_id, guild_id, TX["company_sale_income"], price,
                              f"Venta de la empresa {company['name']} a {buyer_id}"))
    batch.append(_ledger_tx(
        company, "company_sale",
        0 if is_city_sale else price,
        funds if is_city_sale else funds + price,
        (f"Venta de una empresa de la ciudad por {price:,} — el importe va a la Tesoreria"
         if is_city_sale else f"Venta de la empresa por {price:,}") + f" — nuevo dueno {buyer_id}",
        buyer_id, None if is_city_sale else seller_id,
    ))
    results = await aexecute_atomic(batch)
    if not results[0]:
        raise InsufficientFunds(
            "No tienes efectivo suficiente para comprar esa empresa.",
            required=price,
        )
    return {
        "price": price,
        "seller_id": seller_id,
        "is_city_sale": is_city_sale,
        "company": company,
        "company_balance": funds if is_city_sale else funds + price,
    }


# ---------------------------------------------------------------------------
# DISOLUCION: la caja vuelve al dueno y los locales vuelven al mercado
# ---------------------------------------------------------------------------


async def company_properties(guild_id: str, company_id: str):
    """Locales que pertenecen a la empresa (`properties.company_id`)."""
    return await aexecute(
        "SELECT * FROM properties WHERE guild_id=$1 AND company_id=$2 ORDER BY type, price",
        (guild_id, company_id),
        fetch="all",
    ) or []


async def dissolve_company(guild_id: str, company_id: str, actor_id: str):
    """Disuelve la empresa y devuelve su caja al dueno.

    No se borra el historial: la empresa pasa a `closed` y sale de los listados,
    pero conserva menu, catalogo, puestos y configuracion por si algun dia se
    reactiva. Lo que si cambia de estado:

        empresa.funds -X -> dueno.cash +X   (a la Tesoreria si es empresa de la ciudad)
        empleados        -> 'left' (libres, sin nomina pendiente)
        locales          -> 'available', sin dueno y sin empresa (vuelven al mercado)

    La nomina pendiente que no se haya cobrado se pierde con el negocio: por eso
    se devuelve en `pending_paid` para que el dueno lo vea ANTES de confirmar.

    Todo se escribe en una sola transaccion y el UPDATE de la empresa lleva la
    guarda `status NOT IN ('closed','bankrupt') AND funds >= importe`, de modo
    que un doble clic no puede devolver la caja dos veces.
    """
    company = await get_company(company_id, guild_id)
    if not company:
        raise BusinessError("La empresa ya no existe.")
    if str(company.get("owner_id")) != str(actor_id):
        raise BusinessError("Solo el dueno puede disolver la empresa.")
    if (company.get("status") or "active") in BLOCKED_STATUSES:
        raise BusinessError("Esta empresa ya esta cerrada.")

    owner_id = str(company["owner_id"])
    # Excepcion documentada igual que en `buy_company`: si el dueno es la ciudad
    # no hay ciudadano al que pagar y el importe va a las arcas, no desaparece.
    is_city = owner_id == CITY_OWNER_ID
    funds = money(company.get("funds"))
    pending_total, _ = await pending_payroll(company_id)
    if not is_city:
        await async_get_or_create_user(owner_id, guild_id)

    batch = []

    def counted(item):
        """Encola una sentencia y devuelve el indice que ocupara en `results`.

        `aexecute_atomic` solo devuelve los resultados de las sentencias que
        piden `fetch`, asi que el indice es la posicion entre esas, no la del lote.
        """
        batch.append(item)
        return sum(1 for queued in batch if queued[2]) - 1

    i_company = counted((
        """UPDATE companies SET funds=0, status='closed', status_note=$1,
           status_changed_at=NOW(), sale_price=NULL, public_listing=FALSE, updated_at=NOW()
           WHERE id=$2 AND guild_id=$3 AND status NOT IN ('closed','bankrupt') AND funds >= $4""",
        ("Disuelta por su dueno", company_id, guild_id, funds),
        "count",
    ))
    if funds > 0:
        if is_city:
            counted(_treasury_credit(guild_id, funds))
        else:
            counted(_cash_guard(owner_id, guild_id, funds, +1))
        batch.append(_user_tx(
            owner_id, guild_id, TX["company_closure"], funds,
            f"Liquidacion de la caja de {company['name']} al disolver la empresa",
        ))
    i_listing = counted((
        "UPDATE company_sales SET status='cancelled', note='Empresa disuelta' "
        "WHERE company_id=$1 AND status='listed'",
        (company_id,),
        "count",
    ))
    # Los empleados quedan libres pero conservan su ficha, como en la venta de
    # una empresa: si el negocio se reactiva, la plantilla sigue ahi.
    i_members = counted((
        """UPDATE company_members SET member_status='left', position_id=NULL, permissions='',
           is_manager=FALSE, discord_role_id=NULL, pending_salary=0, updated_at=NOW()
           WHERE company_id=$1 AND (member_status IS NULL OR member_status<>'left')""",
        (company_id,),
        "count",
    ))
    i_properties = counted((
        "UPDATE properties SET status='available', owner_id=NULL, company_id=NULL,"
        " updated_at=NOW() WHERE guild_id=$1 AND company_id=$2",
        (guild_id, company_id),
        "count",
    ))
    batch.append(_ledger_tx(
        company, "closure", -funds, 0,
        f"Cierre del negocio: la caja vuelve al dueno {owner_id}"
        + (f" (nomina pendiente sin cobrar: {pending_total:,})" if pending_total else ""),
        actor_id,
    ))

    results = await aexecute_atomic(batch)
    if not results[i_company]:
        raise BusinessError("La empresa ya no existe o ya estaba disuelta.")
    return {
        "funds": funds,
        "owner_id": owner_id,
        "is_city": is_city,
        "employees_released": results[i_members] or 0,
        "properties_released": results[i_properties] or 0,
        "listings_cancelled": results[i_listing] or 0,
        "pending_paid": pending_total,
    }


# ---------------------------------------------------------------------------
# ACCIONES
# ---------------------------------------------------------------------------


async def configure_shares(guild_id: str, company_id: str, actor_id: str, total_shares: int,
                           share_price: int, control_pct: float = 51.0, enabled: bool = True,
                           founder_shares: int = 0):
    """El dueno define cuantos paquetes de capital existen y a que precio.

    `founder_shares` es la participacion que se reserva el dueno al constitute el
    capital; el resto queda disponible para que otros ciudadanos compren acciones
    (y ese importe entra en la caja de la empresa). Aqui solo se registra la
    configuracion: el dinero se mueve cuando alguien compra.
    """
    total_shares = int(total_shares)
    share_price = money(share_price)
    founder_shares = max(0, int(founder_shares))
    if total_shares <= 0:
        raise BusinessError("El numero total de acciones debe ser mayor que cero.")
    if share_price <= 0:
        raise BusinessError("El valor por accion debe ser mayor que cero.")
    if founder_shares > total_shares:
        raise BusinessError(
            f"La participacion inicial ({founder_shares:,}) no puede superar el capital social "
            f"({total_shares:,})."
        )
    control_pct = max(0.0, min(100.0, float(control_pct)))

    company = await get_company(company_id, guild_id)
    if not company:
        raise BusinessError("La empresa no existe.")
    if str(company.get("owner_id")) != str(actor_id):
        raise BusinessError("Solo el dueno puede definir el capital social.")

    existing = await company_shares_config(company_id)
    holders = await company_shareholders(company_id, only_with_shares=False)
    issued = sum(money(h.get("shares")) for h in holders)
    if issued > total_shares:
        raise BusinessError(
            f"Ya hay **{issued:,}** acciones repartidas: no puedes reducir el capital por debajo de eso."
        )

    if existing:
        await aexecute(
            """UPDATE company_shares SET total_shares=$1, share_price=$2, control_pct=$3,
               is_enabled=$4, updated_at=NOW() WHERE id=$5""",
            (total_shares, share_price, control_pct, enabled, existing["id"]),
        )
    else:
        await aexecute(
            """INSERT INTO company_shares
                 (id, company_id, guild_id, total_shares, share_price, control_pct, is_enabled, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,NOW(),NOW())""",
            (generate_id(), company_id, guild_id, total_shares, share_price, control_pct, enabled),
        )

    # El dueno recibe su participacion fundacional; el resto queda por emitir.
    owner_row = next((h for h in holders if str(h.get("discord_id")) == str(actor_id)), None)
    if not owner_row:
        await aexecute(
            """INSERT INTO company_shareholders
                 (id, company_id, guild_id, discord_id, shares, total_invested, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,0,NOW(),NOW())""",
            (generate_id(), company_id, guild_id, actor_id, founder_shares),
        )
    elif not money(owner_row.get("shares")) and founder_shares:
        await aexecute(
            "UPDATE company_shareholders SET shares=$1, updated_at=NOW() WHERE id=$2",
            (founder_shares, owner_row["id"]),
        )
    return {
        "total_shares": total_shares,
        "share_price": share_price,
        "control_pct": control_pct,
        "founder_shares": founder_shares,
    }



async def buy_primary_shares(guild_id: str, company_id: str, buyer_id: str, shares: int):
    """Emision primaria: el comprador paga y el importe entra a la caja."""
    shares = int(shares)
    if shares <= 0:
        raise BusinessError("La cantidad de acciones debe ser mayor que cero.")

    config = await company_shares_config(company_id)
    company = await get_company(company_id, guild_id)
    if not company:
        raise BusinessError("La empresa no existe.")
    if not config or not config.get("is_enabled"):
        raise BusinessError("Esta empresa no ofrece acciones al publico.")
    if (company.get("status") or "active") in BLOCKED_STATUSES:
        raise BusinessError("La empresa no admite operaciones de capital en su estado actual.")

    total_shares = money(config.get("total_shares"))
    holders = await company_shareholders(company_id, only_with_shares=False)
    issued = sum(money(h.get("shares")) for h in holders)
    available = total_shares - issued
    if available <= 0:
        raise BusinessError("La empresa ya emitio todo su capital social.")
    if shares > available:
        raise BusinessError(
            f"Solo quedan **{available:,}** acciones por emitir de un total de {total_shares:,}."
        )

    price = money(config.get("share_price"))
    total = price * shares
    funds = money(company.get("funds"))
    await async_get_or_create_user(buyer_id, guild_id)

    holder = next((h for h in holders if str(h.get("discord_id")) == str(buyer_id)), None)
    if holder:
        holder_update = (
            """UPDATE company_shareholders SET shares=shares+$1, total_invested=total_invested+$2,
               updated_at=NOW() WHERE id=$3""",
            (shares, total, holder["id"]),
            "count",
        )
    else:
        holder_update = (
            """INSERT INTO company_shareholders
                 (id, company_id, guild_id, discord_id, shares, total_invested, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,NOW(),NOW())""",
            (generate_id(), company_id, guild_id, buyer_id, shares, total),
            "count",
        )

    results = await aexecute_atomic([
        _cash_guard(buyer_id, guild_id, total, -1),
        (
            "UPDATE companies SET funds=funds+$1, updated_at=NOW() WHERE id=$2",
            (total, company_id),
            "count",
        ),
        holder_update,
        (
            """INSERT INTO company_share_trades
                 (id, company_id, guild_id, discord_id, trade_type, shares, price, total, created_at)
               VALUES ($1,$2,$3,$4,'buy',$5,$6,$7,NOW())""",
            (generate_id(), company_id, guild_id, buyer_id, shares, price, total),
            None,
        ),
        _user_tx(buyer_id, guild_id, TX["company_shares"], -total,
                 f"Compra de {shares:,} acciones de {company['name']}"),
        _ledger_tx(company, "shares", total, funds + total,
                   f"Emision de acciones: {shares:,} a {buyer_id}", buyer_id),
    ])
    if not results[0]:
        raise InsufficientFunds(
            "No tienes efectivo suficiente para esa compra de acciones.",
            required=total,
        )
    return {"shares": shares, "price": price, "total": total, "company_balance": funds + total}


async def sell_shares_to_company(guild_id: str, company_id: str, seller_id: str, shares: int):
    """Recompra de acciones por la propia empresa (reducir capital).

    El dinero sale de la caja de la empresa, no de la nada.
    """
    shares = int(shares)
    if shares <= 0:
        raise BusinessError("La cantidad de acciones debe ser mayor que cero.")
    company = await get_company(company_id, guild_id)
    config = await company_shares_config(company_id)
    if not company or not config:
        raise BusinessError("Esta empresa no tiene capital social emitido.")

    holder = next(
        (h for h in await company_shareholders(company_id) if str(h.get("discord_id")) == str(seller_id)),
        None,
    )
    if not holder or money(holder.get("shares")) < shares:
        have = money(holder.get("shares")) if holder else 0
        raise BusinessError(f"Tienes **{have:,}** acciones. No puedes vender {shares:,}.")

    price = money(config.get("share_price"))
    total = price * shares
    funds = money(company.get("funds"))
    if funds < total:
        raise InsufficientFunds(
            "La empresa no tiene caja para recomprar esas acciones.",
            available=funds,
            required=total,
        )

    results = await aexecute_atomic([
        (
            "UPDATE companies SET funds=funds-$1, updated_at=NOW() WHERE id=$2 AND funds >= $3",
            (total, company_id, total),
            "count",
        ),
        _cash_guard(seller_id, guild_id, total, +1),
        (
            "UPDATE company_shareholders SET shares=shares-$1, updated_at=NOW() WHERE id=$2",
            (shares, holder["id"]),
            "count",
        ),
        (
            """INSERT INTO company_share_trades
                 (id, company_id, guild_id, discord_id, trade_type, shares, price, total, counterparty_id, created_at)
               VALUES ($1,$2,$3,$4,'sell',$5,$6,$7,$8,NOW())""",
            (generate_id(), company_id, guild_id, seller_id, shares, price, total, company_id),
            None,
        ),
        _user_tx(seller_id, guild_id, TX["company_shares"], total,
                 f"Venta de {shares:,} acciones de {company['name']} a la empresa"),
        _ledger_tx(company, "shares", -total, funds - total,
                   f"Recompra de acciones a {seller_id}", seller_id),
    ])
    if not results[0]:
        raise InsufficientFunds(
            "La empresa no tiene caja para recomprar esas acciones.",
            available=funds,
            required=total,
        )
    return {"shares": shares, "total": total, "company_balance": funds - total}


# ---------------------------------------------------------------------------
# DIVIDENDOS
# ---------------------------------------------------------------------------


async def pay_dividends(guild_id: str, company_id: str, actor_id: str, total_amount: int,
                        note: str = ""):
    """Reparte un dividendo desde los fondos reales, segun participacion.

    El sobrante por redondeo va al accionista con mas participacion: el total
    repartido es exactamente el solicitado, ni un centimetro mas.
    """
    total_amount = money(total_amount)
    if total_amount <= 0:
        raise BusinessError("El importe del dividendo debe ser mayor que cero.")

    company = await get_company(company_id, guild_id)
    if not company:
        raise BusinessError("La empresa no existe.")
    if (company.get("status") or "active") in BLOCKED_STATUSES:
        raise BusinessError("La empresa no puede repartir dividendos en su estado actual.")

    holders = await company_shareholders(company_id)
    if not holders:
        raise BusinessError("Esta empresa no tiene accionistas con participacion.")
    total_shares = sum(money(h.get("shares")) for h in holders)
    if total_shares <= 0:
        raise BusinessError("Ningun accionista tiene acciones: no hay base para repartir.")

    funds = money(company.get("funds"))
    if funds < total_amount:
        raise InsufficientFunds(
            "La caja de la empresa no alcanza para ese dividendo.",
            available=funds,
            required=total_amount,
        )

    raw = [(h, money(h.get("shares")) / total_shares * total_amount) for h in holders]
    payments = [(h, int(value)) for h, value in raw]
    leftover = total_amount - sum(amount for _, amount in payments)
    if leftover:
        biggest = max(payments, key=lambda pair: pair[0].get("shares") or 0)
        payments = [(h, amount + (leftover if h["id"] == biggest[0]["id"] else 0)) for h, amount in payments]
    payments = [(h, amount) for h, amount in payments if amount > 0]
    if not payments:
        raise BusinessError("El dividendo es demasiado pequeno para repartirse.")

    for holder, _ in payments:
        await async_get_or_create_user(holder["discord_id"], guild_id)

    dividend_id = generate_id()
    batch = [
        (
            "UPDATE companies SET funds=funds-$1, updated_at=NOW() WHERE id=$2 AND funds >= $3",
            (total_amount, company_id, total_amount),
            "count",
        ),
        (
            """INSERT INTO company_dividends
                 (id, company_id, guild_id, total_amount, paid_amount, recipient_count,
                  status, note, created_by, created_at, paid_at)
               VALUES ($1,$2,$3,$4,$5,$6,'paid',$7,$8,NOW(),NOW())""",
            (dividend_id, company_id, guild_id, total_amount, total_amount,
             len(payments), note, actor_id),
            None,
        ),
    ]
    for holder, amount in payments:
        batch.append((
            """INSERT INTO company_dividend_payments
                 (id, dividend_id, company_id, guild_id, discord_id, shares, amount, status, created_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,'paid',NOW())""",
            (generate_id(), dividend_id, company_id, guild_id, holder["discord_id"],
             money(holder.get("shares")), amount),
            None,
        ))
        batch.append(_bank_credit(holder["discord_id"], guild_id, amount))
        batch.append(_user_tx(
            holder["discord_id"], guild_id, TX["company_dividend"], amount,
            f"Dividendo de {company['name']} ({money(holder.get('shares')):,} acciones)",
        ))

    batch.append(_ledger_tx(company, "dividend", -total_amount, funds - total_amount,
                            f"Dividendo a {len(payments)} accionistas", actor_id))
    results = await aexecute_atomic(batch)
    if not results[0]:
        raise InsufficientFunds(
            "La caja de la empresa no alcanza para ese dividendo.",
            available=funds,
            required=total_amount,
        )
    return {
        "dividend_id": dividend_id,
        "total": total_amount,
        "recipients": len(payments),
        "balance_after": funds - total_amount,
        "top": max(payments, key=lambda pair: pair[1]),
    }


# ---------------------------------------------------------------------------
# EMPLEOS PUBLICOS
# ---------------------------------------------------------------------------


async def list_public_jobs(guild_id: str, only_active: bool = True):
    query = "SELECT * FROM jobs WHERE guild_id=$1"
    if only_active:
        query += " AND is_active=TRUE"
    query += " ORDER BY sort_order, created_at"
    return await aexecute(query, (guild_id,), fetch="all") or []


async def create_public_job(guild_id: str, name: str, salary: int, description: str = "",
                            role_id: str = None, emoji: str = "\U0001F9FA", max_workers: int = 0):
    """Publica un empleo publico. Devuelve {"job", "created"}.

    El nombre es unico por servidor: un puesto de policia no puede duplicarse
    cambiando solo las mayusculas.
    """
    name = (name or "").strip()
    if len(name) < 3:
        raise BusinessError("El nombre del empleo debe tener al menos 3 caracteres.")
    salary = money(salary)
    if salary <= 0:
        raise BusinessError("El sueldo diario debe ser mayor que cero.")
    duplicate = await aexecute(
        "SELECT id FROM jobs WHERE guild_id=$1 AND name ILIKE $2",
        (guild_id, name),
        fetch="one",
    )
    if duplicate:
        raise BusinessError(f"El empleo **{name}** ya existe en este servidor.")

    job_id = generate_id()
    await aexecute(
        """INSERT INTO jobs
             (id, guild_id, name, salary, description, role_id, emoji, is_active,
              is_single, max_workers, sort_order, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,TRUE,TRUE,$8,0,NOW(),NOW())""",
        (job_id, guild_id, name, salary, description or "", role_id,
         emoji or "\U0001F9FA", max(0, int(max_workers or 0))),
    )
    return {"job": await get_public_job(guild_id, job_id), "created": True}


async def update_public_job(guild_id: str, job_id: str, name: str, salary: int,
                            description: str = "", role_id: str = None,
                            emoji: str = "\U0001F9FA", max_workers: int = 0):
    """Edita un empleo publico ya existente y devuelve la fila actualizada."""
    name = (name or "").strip()
    if len(name) < 3:
        raise BusinessError("El nombre del empleo debe tener al menos 3 caracteres.")
    salary = money(salary)
    if salary <= 0:
        raise BusinessError("El sueldo diario debe ser mayor que cero.")
    duplicate = await aexecute(
        "SELECT id FROM jobs WHERE guild_id=$1 AND name ILIKE $2 AND id <> $3",
        (guild_id, name, job_id),
        fetch="one",
    )
    if duplicate:
        raise BusinessError(f"Ya existe otro empleo llamado **{name}**.")

    await aexecute(
        """UPDATE jobs SET name=$1, salary=$2, description=$3, role_id=$4,
           emoji=$5, max_workers=$6, updated_at=NOW()
           WHERE id=$7 AND guild_id=$8""",
        (name, salary, description or "", role_id, emoji or "\U0001F9FA",
         max(0, int(max_workers or 0)), job_id, guild_id),
    )
    # Quien ya trabaja no puede cobrar mas de lo pactado tras la revision.
    await aexecute(
        "UPDATE user_public_jobs SET salary=$1, updated_at=NOW() WHERE job_id=$2 AND guild_id=$3",
        (salary, job_id, guild_id),
    )
    return {"job": await get_public_job(guild_id, job_id), "created": False}


async def set_public_job_status(guild_id: str, job_id: str, active: bool):
    """Abre o cierra un empleo publico.

    Cerrar no borra a nadie: la plantilla sigue cobrando, simplemente el puesto
    deja de admitir candidatos nuevos.
    """
    job = await get_public_job(guild_id, job_id)
    if not job:
        raise BusinessError("Ese empleo publico no existe.")
    if bool(job.get("is_active", True)) == bool(active):
        raise BusinessError(
            f"**{job.get('name')}** ya esta "
            f"{'abierto' if active else 'cerrado'}."
        )
    await aexecute(
        "UPDATE jobs SET is_active=$1, updated_at=NOW() WHERE id=$2 AND guild_id=$3",
        (bool(active), job_id, guild_id),
    )
    return await get_public_job(guild_id, job_id)


async def set_public_job_salary(guild_id: str, job_id: str, salary: int):
    """Revisa el sueldo de un empleo y lo sincroniza con su plantilla."""
    salary = money(salary)
    if salary <= 0:
        raise BusinessError("El sueldo debe ser mayor que cero.")
    job = await get_public_job(guild_id, job_id)
    if not job:
        raise BusinessError("Ese empleo publico no existe.")
    await aexecute_atomic([
        ("UPDATE jobs SET salary=$1, updated_at=NOW() WHERE id=$2 AND guild_id=$3",
         (salary, job_id, guild_id), "count"),
        ("UPDATE user_public_jobs SET salary=$1, updated_at=NOW() WHERE job_id=$2 AND guild_id=$3",
         (salary, job_id, guild_id), "count"),
    ])
    return await get_public_job(guild_id, job_id)


async def get_public_job(guild_id: str, job_id: str):
    return await aexecute(
        "SELECT * FROM jobs WHERE id=$1 AND guild_id=$2",
        (job_id, guild_id),
        fetch="one",
    )


async def find_public_job(guild_id: str, name: str, include_closed: bool = False):
    """Busca un empleo publico por nombre (sin distinguir mayusculas).

    Los ciudadanos solo ven los activos; administracion puede pasar
    `include_closed=True` para reabrir o editar uno cerrado.
    """
    if not (name or "").strip():
        return None
    query = "SELECT * FROM jobs WHERE guild_id=$1 AND name ILIKE $2"
    if not include_closed:
        query += " AND is_active=TRUE"
    return await aexecute(
        query + " ORDER BY sort_order, created_at LIMIT 1",
        (guild_id, name.strip()),
        fetch="one",
    )


async def get_treasury(guild_id: str):
    return await aexecute(
        "SELECT * FROM treasury WHERE guild_id=$1",
        (guild_id,),
        fetch="one",
    )


async def get_jobs_channel(guild_id: str):
    config = await async_get_or_create_guild_config(guild_id)
    return config.get("public_jobs_channel_id")


async def user_public_jobs(guild_id: str, user_id: str, only_active: bool = True):
    query = "SELECT * FROM user_public_jobs WHERE discord_id=$1 AND guild_id=$2"
    if only_active:
        query += " AND status='active'"
    query += " ORDER BY hired_at"
    return await aexecute(query, (user_id, guild_id), fetch="all") or []


async def assign_public_job(guild_id: str, user_id: str, job_id: str):
    """Contratacion en un empleo publico.

    El rol de Discord, el registro en el perfil y (si el servidor lo permite) la
    retirada del empleo publico anterior ocurren en la misma transaccion.
    """
    job = await get_public_job(guild_id, job_id)
    if not job:
        raise BusinessError("Ese empleo publico no existe.")
    if not job.get("is_active", True):
        raise BusinessError("Ese empleo publico esta cerrado.")

    config = await async_get_or_create_guild_config(guild_id)
    single = bool(config.get("single_public_job", True))
    salary = money(job.get("salary")) or money(job.get("min_pay"))
    await async_get_or_create_user(user_id, guild_id)

    current = await user_public_jobs(guild_id, user_id)
    already = next((row for row in current if str(row.get("job_id")) == str(job_id)), None)
    replaced = []
    if single:
        replaced = [row for row in current if str(row.get("job_id")) != str(job_id)]

    # Limite de plazas declarado por el dueno del empleo publico.
    max_workers = int(job.get("max_workers") or 0)
    if max_workers > 0 and not already:
        taken = await aexecute(
            "SELECT COUNT(*) AS n FROM user_public_jobs"
            " WHERE job_id=$1 AND guild_id=$2 AND status='active'",
            (job_id, guild_id),
            fetch="one",
        )
        if int((taken or {}).get("n") or 0) >= max_workers:
            raise BusinessError(
                f"**{job.get('name')}** ha llenado sus {max_workers} plazas."
            )

    batch = [
        (
            """INSERT INTO user_public_jobs
                 (id, guild_id, discord_id, job_id, job_name, salary, role_id, status,
                  hired_at, last_paid_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,'active',NOW(),NULL,NOW())
               ON CONFLICT DO NOTHING""",
            (generate_id(), guild_id, user_id, job_id, job.get("name", "Empleo publico"),
             salary, job.get("role_id")),
            None,
        ),
        (
            """UPDATE user_public_jobs SET salary=$1, role_id=$2, status='active', updated_at=NOW()
               WHERE discord_id=$3 AND guild_id=$4 AND job_id=$5""",
            (salary, job.get("role_id"), user_id, guild_id, job_id),
            "count",
        ),
    ]
    if replaced:
        batch.append((
            "UPDATE user_public_jobs SET status='left', updated_at=NOW()"
            " WHERE discord_id=$1 AND guild_id=$2 AND job_id=$3",
            (user_id, guild_id, replaced[0]["job_id"]),
            "count",
        ))
    await aexecute_atomic(batch)

    # La ocupacion del DNI refleja el empleo publico vigente.
    try:
        await aexecute(
            "UPDATE dni_records SET occupation=$1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
            (job.get("name", "Ciudadano"), user_id, guild_id),
        )
    except Exception as dni_error:
        logger.debug("[Business] DNI occupation no actualizada: %s", dni_error)

    return {
        "job": job,
        "salary": salary,
        "replaced": replaced,
        "already": bool(already),
    }


async def leave_public_job(guild_id: str, user_id: str, job_id: str = None):
    current = await user_public_jobs(guild_id, user_id)
    if not current:
        raise BusinessError("No tienes ningun empleo publico activo.")
    target = None
    if job_id:
        target = next((row for row in current if str(row.get("job_id")) == str(job_id)), None)
        if not target:
            raise BusinessError("No ocupas ese empleo publico.")
    else:
        target = current[-1]

    await aexecute(
        "UPDATE user_public_jobs SET status='left', updated_at=NOW() WHERE id=$1",
        (target["id"],),
    )
    remaining = [row for row in current if row["id"] != target["id"]]
    if remaining:
        try:
            await aexecute(
                "UPDATE dni_records SET occupation=$1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
                (remaining[-1].get("job_name", "Ciudadano"), user_id, guild_id),
            )
        except Exception:
            pass
    else:
        try:
            await aexecute(
                "UPDATE dni_records SET occupation='Ciudadano', updated_at=NOW()"
                " WHERE discord_id=$1 AND guild_id=$2",
                (user_id, guild_id),
            )
        except Exception:
            pass
    return target


async def pay_public_salary_from_treasury(guild_id: str, user_id: str):
    """Liquida el sueldo del empleo publico desde la Tesoreria del servidor.

    La Tesoreria es la contraparte real: si no tiene fondos, el sueldo sale a
    cero y se informa. Nunca se inventa dinero.
    """
    jobs = await user_public_jobs(guild_id, user_id)
    jobs = [j for j in jobs if money(j.get("salary")) > 0]
    if not jobs:
        return {"paid": 0, "lines": [], "short": 0}

    treasury = await aexecute(
        "SELECT * FROM treasury WHERE guild_id=$1",
        (guild_id,),
        fetch="one",
    )
    balance = money((treasury or {}).get("balance"))
    total = sum(money(j.get("salary")) for j in jobs)
    payable = min(balance, total)

    if payable <= 0:
        return {
            "paid": 0,
            "lines": [
                {"job": j.get("job_name"), "amount": 0, "due": money(j.get("salary"))}
                for j in jobs
            ],
            "short": total,
            "treasury": balance,
        }

    lines = []
    remaining = payable
    for job in jobs:
        due = money(job.get("salary"))
        amount = min(due, remaining)
        remaining -= amount
        lines.append({"job": job.get("job_name"), "amount": amount, "due": due, "id": job["id"]})

    # Reparto proporcional cuando la tesoreria no cubre la nomina completa.
    if remaining > 0:
        ratio = payable / total if total else 0
        recalculated = []
        for line in lines:
            recalculated.append({
                "job": line["job"],
                "amount": int(line["due"] * ratio),
                "due": line["due"],
                "id": line["id"],
            })
        leftover = payable - sum(l["amount"] for l in recalculated)
        if leftover and recalculated:
            recalculated[0]["amount"] += leftover
        lines = recalculated

    # Todo el pago es una sola transaccion: o entra el sueldo entero en la cuenta
    # del ciudadano y sale de la Tesoreria, o no pasa nada.
    batch = [
        (
            "UPDATE treasury SET balance=balance-$1, updated_at=NOW() WHERE guild_id=$2 AND balance >= $3",
            (payable, guild_id, payable),
            "count",
        ),
        (
            "UPDATE users SET bank=bank+$1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
            (payable, user_id, guild_id),
            "count",
        ),
        (
            """INSERT INTO transactions (id, discord_id, guild_id, type, amount, description, created_at)
               VALUES ($1,$2,$3,'public_job_salary',$4,$5,NOW())""",
            (generate_id(), user_id, guild_id, payable,
             "Nomina de empleo publico (Tesoreria Municipal)"),
            None,
        ),
    ]
    for line in lines:
        if line["amount"] > 0:
            batch.append((
                "UPDATE user_public_jobs SET last_paid_at=NOW(), updated_at=NOW() WHERE id=$1",
                (line["id"],),
                "count",
            ))
    results = await aexecute_atomic(batch)
    if not results[0]:
        # La Tesoreria se quedo sin fondos entre la lectura y el cobro.
        return {
            "paid": 0,
            "lines": [
                {"job": j.get("job_name"), "amount": 0, "due": money(j.get("salary"))}
                for j in jobs
            ],
            "short": total,
            "treasury": 0,
        }
    for line in lines:
        line.pop("id", None)
    return {
        "paid": payable,
        "lines": lines,
        "short": max(0, total - payable),
        "treasury": balance - payable,
    }


# ---------------------------------------------------------------------------
# CATALOGOS PREDETERMINADOS (siembra por administracion)
# ---------------------------------------------------------------------------


async def seed_default_jobs(guild_id: str):
    """Publica los empleos del catalogo oficial que falten en el servidor.

    Idempotente: solo inserta los que no existen (comparacion sin distinguir
    mayusculas, igual que al crear a mano). Los que ya estan no se tocan, de
    forma que un sueldo o una descripcion editados por el admin se respetan.
    La unica excepcion es el emoji: si el guardado no es utilizable por
    Discord se restituye, porque un emoji roto hacia fallar `/empleos listar`
    entero. Al final se barren todos los empleos del servidor, no solo los del
    catalogo, para no dejar ninguno sin arreglar.
    """
    from bot.services.business_ui import job_emoji as emoji_por_nombre

    created, existing, repaired = [], [], []
    catalog = {job["name"]: job.get("emoji", EMOJI_FALLBACK) for job in DEFAULT_JOBS}
    for job in DEFAULT_JOBS:
        name = job["name"]
        catalog_emoji = catalog[name]
        found = await aexecute(
            "SELECT id FROM jobs WHERE guild_id=$1 AND name ILIKE $2",
            (guild_id, name),
            fetch="one",
        )
        if found:
            existing.append(name)
            continue
        job_id = generate_id()
        try:
            await aexecute(
                """INSERT INTO jobs
                     (id, guild_id, name, salary, description, role_id, emoji, is_active,
                      is_single, max_workers, sort_order, created_at, updated_at)
                   VALUES ($1,$2,$3,$4,$5,NULL,$6,TRUE,TRUE,$7,$8,NOW(),NOW())""",
                (job_id, guild_id, name, money(job["salary"]), job.get("description", ""),
                 catalog_emoji, max(0, int(job.get("max_workers") or 0)),
                 len(DEFAULT_JOBS)),
            )
        except Exception as error:
            # Carrera con otra siembra simultanea: la fila ya existe y se trata
            # como "ya estaba", nunca como fallo del comando.
            logger.warning("[Empleos] No se pudo sembrar '%s': %s", name, error)
            existing.append(name)
            continue
        created.append(name)

    # Barrido final sobre TODOS los empleos del servidor, tambien los que el
    # admin creo a mano: cualquier emoji que Discord vaya a rechazar se
    # sustituye aqui, porque un solo valor sucio tumba `/empleos listar` entero.
    roto = await aexecute(
        "SELECT id, name, emoji FROM jobs WHERE guild_id=$1", (guild_id,), fetch="all",
    ) or []
    for job in roto:
        if safe_emoji(job.get("emoji"), None) is not None:
            continue
        name = job.get("name") or ""
        nuevo = catalog.get(name) or emoji_por_nombre(name)
        try:
            await aexecute(
                "UPDATE jobs SET emoji=$1, updated_at=NOW() WHERE id=$2 AND guild_id=$3",
                (nuevo, job["id"], guild_id),
            )
        except Exception as error:
            logger.warning("[Empleos] No se pudo reparar el emoji de '%s': %s",
                           name, error)
            continue
        logger.warning("[Empleos] Emoji reparado en '%s': %r -> %r",
                       name, job.get("emoji"), nuevo)
        if name and name not in existing:
            existing.append(name)
        if name and name not in repaired:
            repaired.append(name)
    return {"created": created, "existing": existing, "repaired": repaired}


async def seed_city_companies(guild_id: str):
    """Pone a la venta las empresas privadas del catalogo oficial de la ciudad.

    Idempotente y no destructiva:

    * si el nombre ya existe en el servidor, no se toca la empresa;
    * si la ciudad sigue siendo la duena y no esta en venta, se vuelve a
      anunciar con su precio de catalogo (por ejemplo tras un reinicio);
    * si ya fue vendida a un ciudadano, se respeta al nuevo dueno.

    Las empresas se crean con caja a cero y sin plantilla: la ciudad entrega
    el negocio, no capital ni empleados.
    """
    listed, already, sold, failed = [], [], [], []
    for item in CITY_COMPANIES:
        name = item["name"]
        price = money(item.get("price"))
        if price <= 0:
            failed.append(name)
            continue
        company = await aexecute(
            "SELECT id, owner_id, status FROM companies WHERE guild_id=$1 AND name ILIKE $2",
            (guild_id, name),
            fetch="one",
        )
        if company:
            if str(company.get("owner_id")) != CITY_OWNER_ID:
                sold.append(name)
                continue
            company_id = company["id"]
            sale = await aexecute(
                "SELECT id FROM company_sales WHERE company_id=$1 AND status='listed'",
                (company_id,),
                fetch="one",
            )
            if sale:
                already.append(name)
                continue
            # Era de la ciudad pero se quedo sin anuncio: se vuelve a vender.
            await aexecute(
                """UPDATE companies SET status='for_sale', sale_price=$1, public_listing=TRUE,
                   status_note='En venta', status_changed_at=NOW(), updated_at=NOW() WHERE id=$2""",
                (price, company_id),
            )
        else:
            company_id = generate_id()
            try:
                await aexecute(
                    """INSERT INTO companies
                         (id, guild_id, owner_id, name, description, funds, tax_rate, category,
                          location, emoji, status, status_note, status_changed_at, public_listing,
                          payroll_mode, allow_multiple_jobs, sale_price, created_at, updated_at)
                       VALUES ($1,$2,$3,$4,$5,0,5,$6,$7,$8,'for_sale','En venta',NOW(),TRUE,
                               'manual',TRUE,$9,NOW(),NOW())""",
                    (company_id, guild_id, CITY_OWNER_ID, name, item.get("description", ""),
                     item.get("category", "General"), item.get("location", ""),
                     item.get("emoji", "\U0001F3E2"), price),
                )
            except Exception as error:
                logger.warning("[Empresas] No se pudo sembrar '%s': %s", name, error)
                failed.append(name)
                continue
        try:
            await aexecute(
                """INSERT INTO company_sales
                     (id, company_id, guild_id, seller_id, price, status, note, listed_at)
                   VALUES ($1,$2,$3,$4,$5,'listed',$6,NOW())""",
                (generate_id(), company_id, guild_id, CITY_OWNER_ID, price,
                 "Propiedad de la ciudad"),
            )
        except Exception as error:
            logger.warning("[Empresas] No se pudo anunciar '%s': %s", name, error)
            failed.append(name)
            continue
        listed.append(name)
    return {"listed": listed, "already": already, "sold": sold, "failed": failed}
