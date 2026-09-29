import re
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


# ---------------------------------------------------------------------------
# Emoji para componentes de Discord
# ---------------------------------------------------------------------------
#
# Discord rechaza el envio ENTERO (400 / 50035 "Invalid emoji") cuando un solo
# `emoji.name` de un menu o de un boton no es un emoji que su API reconoce. No
# vale "se ve bien": un code point sin asignar (U+1F6FD), un texto, un emoji
# truncado a medias o un selector de variacion U+FE0E / U+FE0F (prohibido en
# componentes) tumban el comando. Por eso aqui no se adivina con rangos
# aproximados: `_EMOJI_RANGES` es el conjunto RGI de emoji 16.0 tal cual lo
# publica unicode.org en Public/emoji/16.0/emoji-test.txt.
#
# El recorte al estilo `emoji[:2]` que se usaba antes era peor que no hacer
# nada: partia las secuencias ZWJ y destrozaba el marcado de los emojis
# personalizados "<:nombre:id>".

EMOJI_FALLBACK = "\U0001F9FA"

# Code points base de un emoji RGI, en pares (inicio, fin) cerrados.
_EMOJI_RANGES = (
    0x00A9, 0x00A9, 0x00AE, 0x00AE, 0x203C, 0x203C, 0x2049, 0x2049, 0x2122, 0x2122, 0x2139, 0x2139,
    0x2194, 0x2199, 0x21A9, 0x21AA, 0x231A, 0x231B, 0x2328, 0x2328, 0x23CF, 0x23CF, 0x23E9, 0x23F3,
    0x23F8, 0x23FA, 0x24C2, 0x24C2, 0x25AA, 0x25AB, 0x25B6, 0x25B6, 0x25C0, 0x25C0, 0x25FB, 0x25FE,
    0x2600, 0x2604, 0x260E, 0x260E, 0x2611, 0x2611, 0x2614, 0x2615, 0x2618, 0x2618, 0x261D, 0x261D,
    0x2620, 0x2620, 0x2622, 0x2623, 0x2626, 0x2626, 0x262A, 0x262A, 0x262E, 0x262F, 0x2638, 0x263A,
    0x2640, 0x2640, 0x2642, 0x2642, 0x2648, 0x2653, 0x265F, 0x2660, 0x2663, 0x2663, 0x2665, 0x2666,
    0x2668, 0x2668, 0x267B, 0x267B, 0x267E, 0x267F, 0x2692, 0x2697, 0x2699, 0x2699, 0x269B, 0x269C,
    0x26A0, 0x26A1, 0x26A7, 0x26A7, 0x26AA, 0x26AB, 0x26B0, 0x26B1, 0x26BD, 0x26BE, 0x26C4, 0x26C5,
    0x26C8, 0x26C8, 0x26CE, 0x26CF, 0x26D1, 0x26D1, 0x26D3, 0x26D4, 0x26E9, 0x26EA, 0x26F0, 0x26F5,
    0x26F7, 0x26FA, 0x26FD, 0x26FD, 0x2702, 0x2702, 0x2705, 0x2705, 0x2708, 0x270D, 0x270F, 0x270F,
    0x2712, 0x2712, 0x2714, 0x2714, 0x2716, 0x2716, 0x271D, 0x271D, 0x2721, 0x2721, 0x2728, 0x2728,
    0x2733, 0x2734, 0x2744, 0x2744, 0x2747, 0x2747, 0x274C, 0x274C, 0x274E, 0x274E, 0x2753, 0x2755,
    0x2757, 0x2757, 0x2763, 0x2764, 0x2795, 0x2797, 0x27A1, 0x27A1, 0x27B0, 0x27B0, 0x27BF, 0x27BF,
    0x2934, 0x2935, 0x2B05, 0x2B07, 0x2B1B, 0x2B1C, 0x2B50, 0x2B50, 0x2B55, 0x2B55, 0x3030, 0x3030,
    0x303D, 0x303D, 0x3297, 0x3297, 0x3299, 0x3299, 0x1F004, 0x1F004, 0x1F0CF, 0x1F0CF, 0x1F170, 0x1F171,
    0x1F17E, 0x1F17F, 0x1F18E, 0x1F18E, 0x1F191, 0x1F19A, 0x1F201, 0x1F202, 0x1F21A, 0x1F21A, 0x1F22F, 0x1F22F,
    0x1F232, 0x1F23A, 0x1F250, 0x1F251, 0x1F300, 0x1F321, 0x1F324, 0x1F393, 0x1F396, 0x1F397, 0x1F399, 0x1F39B,
    0x1F39E, 0x1F3F0, 0x1F3F3, 0x1F3F5, 0x1F3F7, 0x1F3FA, 0x1F400, 0x1F4FD, 0x1F4FF, 0x1F53D, 0x1F549, 0x1F54E,
    0x1F550, 0x1F567, 0x1F56F, 0x1F570, 0x1F573, 0x1F57A, 0x1F587, 0x1F587, 0x1F58A, 0x1F58D, 0x1F590, 0x1F590,
    0x1F595, 0x1F596, 0x1F5A4, 0x1F5A5, 0x1F5A8, 0x1F5A8, 0x1F5B1, 0x1F5B2, 0x1F5BC, 0x1F5BC, 0x1F5C2, 0x1F5C4,
    0x1F5D1, 0x1F5D3, 0x1F5DC, 0x1F5DE, 0x1F5E1, 0x1F5E1, 0x1F5E3, 0x1F5E3, 0x1F5E8, 0x1F5E8, 0x1F5EF, 0x1F5EF,
    0x1F5F3, 0x1F5F3, 0x1F5FA, 0x1F64F, 0x1F680, 0x1F6C5, 0x1F6CB, 0x1F6D2, 0x1F6D5, 0x1F6D7, 0x1F6DC, 0x1F6E5,
    0x1F6E9, 0x1F6E9, 0x1F6EB, 0x1F6EC, 0x1F6F0, 0x1F6F0, 0x1F6F3, 0x1F6FC, 0x1F7E0, 0x1F7EB, 0x1F7F0, 0x1F7F0,
    0x1F90C, 0x1F93A, 0x1F93C, 0x1F945, 0x1F947, 0x1F9AF, 0x1F9B4, 0x1F9FF, 0x1FA70, 0x1FA7C, 0x1FA80, 0x1FA89,
    0x1FA8F, 0x1FAC6, 0x1FACE, 0x1FADC, 0x1FADF, 0x1FAE9, 0x1FAF0, 0x1FAF8,
)

_CUSTOM_EMOJI_RE = re.compile(
    r"\A<(?P<animated>a)?:(?P<name>[A-Za-z0-9_]{2,32}):(?P<id>\d{15,25})>\Z"
)
_STRIP_VARIATIONS = {0xFE0E: None, 0xFE0F: None}
_ZWJ = "\u200d"
_REGIONAL = range(0x1F1E6, 0x1F200)
_SKIN = range(0x1F3FB, 0x1F400)
_TAG = range(0xE0020, 0xE0080)
_KEYCAP = "\u20e3"


def _is_emoji_base(char: str) -> bool:
    """True si `char` es la base de un emoji que la API de Discord acepta."""
    point = ord(char)
    return any(lo <= point <= hi
               for lo, hi in zip(_EMOJI_RANGES[::2], _EMOJI_RANGES[1::2]))


def _skip_modifiers(text: str, index: int) -> int:
    """Avanza los modificadores que pueden seguir a la base de un emoji."""
    while index < len(text):
        char = text[index]
        if char == _KEYCAP or ord(char) in _SKIN or ord(char) in _TAG:
            index += 1
        else:
            break
    return index


def _emoji_cluster(text: str) -> str:
    """Primer cluster de emoji completo de `text`, o "" si no hay ninguno."""
    if not text:
        return ""
    first = text[0]
    if ord(first) in _REGIONAL:  # bandera: dos indicadores regionales
        if len(text) > 1 and ord(text[1]) in _REGIONAL:
            return text[:2]
        return ""
    if not _is_emoji_base(first):
        return ""
    end = _skip_modifiers(text, 1)
    while text[end:end + 1] == _ZWJ:  # secuencia ZWJ: bombero, professions...
        nxt = end + 1
        if nxt >= len(text) or not _is_emoji_base(text[nxt]):
            break
        end = _skip_modifiers(text, nxt + 1)
    return text[:end]


def safe_emoji(value, fallback: str = EMOJI_FALLBACK) -> str:
    """Normaliza un emoji para usarlo en un menu o boton de Discord.

    Nunca lanza y siempre devuelve algo que Discord acepta: un emoji
    personalizado se respeta tal cual, a un emoji unicode se le quitan los
    selectores de variacion y se le conserva el primer cluster entero, y si no
    queda nada utilizable se cae a `fallback` (None deja la opcion sin emoji).
    Asi un valor sucio en la base de datos no puede romper un comando entero.
    """
    if value is None:
        return fallback
    text = str(value).strip()
    if _CUSTOM_EMOJI_RE.match(text):
        return text
    return _emoji_cluster(text.translate(_STRIP_VARIATIONS)) or fallback


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



