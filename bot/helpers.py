import uuid
import math
import datetime
from bot.db import execute, aexecute

def generate_id():
    return str(uuid.uuid4())

def format_currency(amount, symbol="$"):
    return f"{symbol}{amount:,.0f}"

def format_time(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        m = seconds // 60
        s = seconds % 60
        return f"{m}m {s}s" if s else f"{m}m"
    if seconds < 86400:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m" if m else f"{h}h"
    d = seconds // 86400
    h = (seconds % 86400) // 3600
    return f"{d}d {h}h" if h else f"{d}d"

def parse_db_datetime(val):
    """Parsea de forma segura fechas de Postgres (tz-aware) y SQLite (strings/timestamps)."""
    if val is None:
        return None
    if isinstance(val, datetime.datetime):
        if val.tzinfo is not None:
            return val.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return val
    if isinstance(val, (int, float)):
        return datetime.datetime.utcfromtimestamp(val)
    if isinstance(val, str):
        s = val.replace("Z", "").replace("+00:00", "").replace("+00", "")
        try:
            return datetime.datetime.fromisoformat(s)
        except Exception:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.datetime.strptime(s, fmt)
            except Exception:
                pass
    return None

def get_elapsed_seconds(past_time, now=None) -> float:
    """Calcula segundos transcurridos de forma segura sin lanzar TypeError."""
    if now is None:
        now = datetime.datetime.utcnow()
    dt = parse_db_datetime(past_time)
    if dt is None:
        return float("inf")
    return max(0.0, (now - dt).total_seconds())


def format_time_ms(ms):
    return format_time(ms / 1000)

def xp_for_level(level):
    return math.floor(100 * (1.5 ** (level - 1)))

def calculate_level(xp):
    level = 1
    while xp >= xp_for_level(level + 1):
        level += 1
    return level

def clamp(value, min_val, max_val):
    return max(min_val, min(max_val, value))

def random_between(a, b):
    import random
    return random.randint(a, b)

def chunk_array(arr, size):
    return [arr[i:i+size] for i in range(0, len(arr), size)]

def get_or_create_user(discord_id, guild_id, username=None, display_name=None):
    row = execute(
        "SELECT * FROM users WHERE discord_id=$1 AND guild_id=$2",
        (discord_id, guild_id), fetch="one"
    )
    if row:
        if username and (row.get("username") != username or (display_name and row.get("display_name") != display_name)):
            execute(
                "UPDATE users SET username=$1, display_name=$2, updated_at=NOW() WHERE discord_id=$3 AND guild_id=$4",
                (username, display_name or username, discord_id, guild_id)
            )
            row["username"] = username
            if display_name:
                row["display_name"] = display_name
        return dict(row)
    execute(
        """INSERT INTO users (id, discord_id, guild_id, username, display_name, cash, bank, xp, level, reputation, dirty_money,
           is_verified, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,500,0,0,1,0,0,false,NOW(),NOW())
           ON CONFLICT DO NOTHING""",
        (generate_id(), discord_id, guild_id, username, display_name or username)
    )
    return dict(execute(
        "SELECT * FROM users WHERE discord_id=$1 AND guild_id=$2",
        (discord_id, guild_id), fetch="one"
    ))

def get_or_create_guild_config(guild_id):
    row = execute("SELECT * FROM guild_config WHERE guild_id=$1", (guild_id,), fetch="one")
    if row:
        return dict(row)
    execute(
        """INSERT INTO guild_config (id, guild_id, daily_amount, weekly_amount, tax_rate,
           created_at, updated_at)
           VALUES ($1,$2,500,2500,5,NOW(),NOW()) ON CONFLICT DO NOTHING""",
        (generate_id(), guild_id)
    )
    return dict(execute("SELECT * FROM guild_config WHERE guild_id=$1", (guild_id,), fetch="one"))

async def async_get_or_create_user(discord_id, guild_id, username=None, display_name=None):
    row = await aexecute(
        "SELECT * FROM users WHERE discord_id=$1 AND guild_id=$2",
        (discord_id, guild_id), fetch="one"
    )
    if row:
        if username and (row.get("username") != username or (display_name and row.get("display_name") != display_name)):
            await aexecute(
                "UPDATE users SET username=$1, display_name=$2, updated_at=NOW() WHERE discord_id=$3 AND guild_id=$4",
                (username, display_name or username, discord_id, guild_id)
            )
            row["username"] = username
            if display_name:
                row["display_name"] = display_name
        return dict(row)
    await aexecute(
        """INSERT INTO users (id, discord_id, guild_id, username, display_name, cash, bank, xp, level, reputation, dirty_money,
           is_verified, created_at, updated_at)
           VALUES ($1,$2,$3,$4,$5,500,0,0,1,0,0,false,NOW(),NOW())
           ON CONFLICT DO NOTHING""",
        (generate_id(), discord_id, guild_id, username, display_name or username)
    )
    return dict(await aexecute(
        "SELECT * FROM users WHERE discord_id=$1 AND guild_id=$2",
        (discord_id, guild_id), fetch="one"
    ))

async def async_update_user_name(discord_id, guild_id, username, display_name=None):
    if not username:
        return
    await aexecute(
        "UPDATE users SET username=$1, display_name=$2, updated_at=NOW() WHERE discord_id=$3 AND guild_id=$4",
        (username, display_name or username, str(discord_id), str(guild_id))
    )

async def async_get_or_create_guild_config(guild_id):
    row = await aexecute("SELECT * FROM guild_config WHERE guild_id=$1", (guild_id,), fetch="one")
    if row:
        return dict(row)
    await aexecute(
        """INSERT INTO guild_config (id, guild_id, daily_amount, weekly_amount, tax_rate,
           created_at, updated_at)
           VALUES ($1,$2,500,2500,5,NOW(),NOW()) ON CONFLICT DO NOTHING""",
        (generate_id(), guild_id)
    )
    return dict(await aexecute(
        "SELECT * FROM guild_config WHERE guild_id=$1", (guild_id,), fetch="one"
    ))

async def check_admin_permission(interaction) -> bool:
    """
    Verifica si el usuario tiene permisos de administración:
    1. Administrador del servidor nativo en Discord
    2. Posee el rol configurado en guild_config.admin_role_id
    """
    if not interaction.guild or not interaction.user:
        return False
    
    # 1. Permiso de Administrador en Discord
    if getattr(interaction.user, "guild_permissions", None) and interaction.user.guild_permissions.administrator:
        return True
    
    # 2. Rol de Admin configurado
    try:
        config = await async_get_or_create_guild_config(str(interaction.guild.id))
        admin_role_id = config.get("admin_role_id")
        if admin_role_id:
            target_role_id = int(admin_role_id)
            user_roles = getattr(interaction.user, "roles", [])
            if any(role.id == target_role_id for role in user_roles):
                return True
    except Exception:
        pass
    
    return False

def check_admin_permission_sync(member, guild_id: str) -> bool:
    """Versión sincrónica de comprobación de permisos de admin."""
    if getattr(member, "guild_permissions", None) and member.guild_permissions.administrator:
        return True
    try:
        config = get_or_create_guild_config(str(guild_id))
        admin_role_id = config.get("admin_role_id")
        if admin_role_id:
            target_role_id = int(admin_role_id)
            user_roles = getattr(member, "roles", [])
            if any(role.id == target_role_id for role in user_roles):
                return True
    except Exception:
        pass
    return False

async def generate_unique_dni(guild_id: str) -> str:
    """Genera un número de DNI único y aleatorio (ej. MIA-849201)."""
    import random
    for _ in range(20):
        num = random.randint(100000, 999999)
        dni = f"MIA-{num}"
        existing = await aexecute("SELECT id FROM dni_records WHERE dni_number=$1", (dni,), fetch="one")
        if not existing:
            return dni
    return f"MIA-{uuid.uuid4().hex[:6].upper()}"

async def generate_unique_weapon_serial(guild_id: str) -> str:
    """Genera un número de serie único y aleatorio para armas (ej. MV-WPN-73921-FL)."""
    import random
    import string
    for _ in range(20):
        num = random.randint(10000, 99999)
        letters = "".join(random.choices(string.ascii_uppercase, k=2))
        serial = f"MV-WPN-{num}-{letters}"
        existing = await aexecute("SELECT id FROM weapon_registries WHERE serial_number=$1", (serial,), fetch="one")
        if not existing:
            return serial
    return f"MV-WPN-{uuid.uuid4().hex[:8].upper()}"

async def generate_unique_vehicle_plate(guild_id: str, vehicle_type: str = "auto") -> str:
    """Genera una placa de circulación única y estilizada según el tipo de vehículo."""
    import random
    import string
    
    prefix = "MIA"
    if vehicle_type in ("trailer", "remolque"):
        prefix = "TRL"
    elif vehicle_type in ("atv", "cuatrimoto", "quad", "buggy"):
        prefix = "ATV"
    elif vehicle_type in ("moto", "motocicleta", "scooter"):
        prefix = "MOT"
    elif vehicle_type in ("lancha", "bote", "jet_ski"):
        prefix = "SEA"
    elif vehicle_type in ("camion", "comercial"):
        prefix = "TRK"

    for _ in range(30):
        num = random.randint(1000, 9999)
        plate = f"{prefix}-{num}"
        existing = await aexecute("SELECT id FROM vehicle_registries WHERE plate=$1", (plate,), fetch="one")
        if not existing:
            return plate
            
    # Fallback con letra
    letter = random.choice(string.ascii_uppercase)
    return f"{prefix}-{random.randint(100, 999)}{letter}"

async def generate_unique_vin(guild_id: str, vehicle_type: str = "auto") -> str:
    """Genera un número de serie / VIN de chasis único para el vehículo registrado."""
    import random
    import string

    code_map = {
        "auto": "AUT",
        "suv": "SUV",
        "moto": "MOT",
        "atv": "ATV",
        "trailer": "TRL",
        "camion": "TRK",
        "lancha": "BOT",
        "otro": "VEH"
    }
    code = code_map.get(vehicle_type, "VEH")
    
    for _ in range(30):
        digits = "".join([str(random.randint(0, 9)) for _ in range(6)])
        letters = "".join(random.choices(string.ascii_uppercase, k=2))
        vin = f"1MV-{code}-{digits}-{letters}"
        existing = await aexecute("SELECT id FROM vehicle_registries WHERE vin_number=$1", (vin,), fetch="one")
        if not existing:
            return vin

    return f"1MV-{code}-{uuid.uuid4().hex[:8].upper()}"

async def is_officer_or_admin(interaction) -> bool:
    """Verifica si el usuario es Administrador o miembro activo de un Departamento de Seguridad/Justicia."""
    if await check_admin_permission(interaction):
        return True
    if not interaction.guild or not interaction.user:
        return False
    gid = str(interaction.guild_id)
    uid = str(interaction.user.id)
    dept_member = await aexecute(
        """SELECT dm.id FROM department_members dm
           JOIN departments d ON dm.department_id = d.id
           WHERE dm.guild_id=$1 AND dm.discord_id=$2 
           AND LOWER(d.type) IN ('police', 'sheriff', 'highway_patrol', 'justice', 'fbi', 'dea', 'swat', 'seguridad', 'legal', 'mdfr', 'mpd', 'fhp', 'mbpd', 'fdoj')""",
        (gid, uid), fetch="one"
    )
    return bool(dept_member)

async def generate_unique_bolo_code(guild_id: str) -> str:
    """Genera un código BOLO único (ej. BOLO-8492)."""
    import random
    for _ in range(30):
        num = random.randint(1000, 9999)
        code = f"BOLO-{num}"
        existing = await aexecute("SELECT id FROM police_bolos WHERE bolo_code=$1 AND guild_id=$2", (code, guild_id), fetch="one")
        if not existing:
            return code
    return f"BOLO-{uuid.uuid4().hex[:6].upper()}"

async def generate_unique_case_number(guild_id: str) -> str:
    """Genera un número de expediente penal / caso policial único (ej. CASO-2026-7491)."""
    import random
    year = datetime.datetime.utcnow().year
    for _ in range(30):
        num = random.randint(1000, 9999)
        code = f"CASO-{year}-{num}"
        existing = await aexecute("SELECT id FROM police_cases WHERE case_number=$1 AND guild_id=$2", (code, guild_id), fetch="one")
        if not existing:
            return code
    return f"CASO-{year}-{uuid.uuid4().hex[:6].upper()}"

async def generate_unique_incident_code(guild_id: str) -> str:
    """Genera un código de incidente de despacho / 911 único (ej. INC-9302)."""
    import random
    for _ in range(30):
        num = random.randint(1000, 9999)
        code = f"INC-{num}"
        existing = await aexecute("SELECT id FROM police_incidents WHERE incident_code=$1 AND guild_id=$2", (code, guild_id), fetch="one")
        if not existing:
            return code
    return f"INC-{uuid.uuid4().hex[:6].upper()}"



