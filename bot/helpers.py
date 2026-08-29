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

def get_or_create_user(discord_id, guild_id):
    row = execute(
        "SELECT * FROM users WHERE discord_id=$1 AND guild_id=$2",
        (discord_id, guild_id), fetch="one"
    )
    if row:
        return dict(row)
    execute(
        """INSERT INTO users (id, discord_id, guild_id, cash, bank, xp, level, reputation, dirty_money,
           is_verified, created_at, updated_at)
           VALUES ($1,$2,$3,500,0,0,1,0,0,false,NOW(),NOW())
           ON CONFLICT DO NOTHING""",
        (generate_id(), discord_id, guild_id)
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

async def async_get_or_create_user(discord_id, guild_id):
    row = await aexecute(
        "SELECT * FROM users WHERE discord_id=$1 AND guild_id=$2",
        (discord_id, guild_id), fetch="one"
    )
    if row:
        return dict(row)
    await aexecute(
        """INSERT INTO users (id, discord_id, guild_id, cash, bank, xp, level, reputation, dirty_money,
           is_verified, created_at, updated_at)
           VALUES ($1,$2,$3,500,0,0,1,0,0,false,NOW(),NOW())
           ON CONFLICT DO NOTHING""",
        (generate_id(), discord_id, guild_id)
    )
    return dict(await aexecute(
        "SELECT * FROM users WHERE discord_id=$1 AND guild_id=$2",
        (discord_id, guild_id), fetch="one"
    ))

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
