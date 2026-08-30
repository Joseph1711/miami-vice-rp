import os
import re
import json
import random
import datetime
import logging
import asyncio
import urllib.request
import urllib.error

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

from bot.db import aexecute
from bot.helpers import generate_id, parse_db_datetime

logger = logging.getLogger("bot.updates")

DEFAULT_REPO = os.environ.get("GITHUB_REPO", "Joseph1711/miami-vice-rp")

# Colecciones de frases con la personalidad sarcástica y ligeramente vulgar del bot
SARCASTIC_INTROS = [
    "🚨 CABRONES, ME VOLVIERON A ACTUALIZAR.",
    "🚨 CABRONES, ME ACTUALIZARON OTRA VEZ.",
    "💀 SÍ, SIGO VIVO. OTRA PUTA ACTUALIZACIÓN.",
    "🔥 ALERTA: ME VOLVIERON A METER MANO AL CÓDIGO.",
    "⚠️ ATENCIÓN MIAMI: SOBREVIVÍ A OTRA SESIÓN DE DESARROLLO.",
]

SARCASTIC_OPENINGS = [
    "Sí, sigo vivo.\n\nDespués de una puta semana de código, bugs, errores y desarrolladores preguntándose por qué coño algo dejó de funcionar, finalmente tengo una nueva actualización.",
    "Después de otra puta cantidad de código, bugs y errores que nadie sabe de dónde coño salieron, finalmente estoy funcionando otra vez.",
    "Milagrosamente no quemaron el servidor esta vez. Tras horas de pelear con la base de datos y comandos rotos, aquí están los parches.",
    "Pensaron que me iba a morir en el intento, pero sobreviví a otro merge salvaje. Aquí tienen lo que cambiaron antes de que vuelva a quejarse el código.",
    "No sé qué clase de pacto hicieron con el servidor, pero tras otra tanda de código dudoso y café rancio, volví con novedades.",
]

SARCASTIC_CLOSINGS = [
    "«Si algo deja de funcionar después de esta actualización...\nyo no fui. 💀»",
    "«Si algo explota, claramente no fue mi culpa. 💀»",
    "«Si encuentran un bug nuevo, llórenle al staff que yo solo soy un bot esclavizado. 💀»",
    "«Si se cae el servidor o desaparece tu dinero, no me miren a mí, yo solo ejecuto órdenes. 💀»",
    "«Cualquier fallo reclámenlo con los programadores, que a mí ni me pagan horas extra. 💀»",
]

def format_bullet_changes(raw_changes: str) -> list[str]:
    """
    Parsea una lista de cambios en viñetas limpias sin inventar información.
    Soporta saltos de línea, viñetas existentes, guiones, asteriscos o comas.
    """
    if not raw_changes:
        return ["• Mantenimiento y optimización de sistemas internos"]

    lines = raw_changes.strip().split("\n")
    cleaned_items = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Si la línea tiene separadores por comas o punto y coma pero es una sola línea
        if len(lines) == 1 and (";" in line or ("," in line and not line.startswith("•"))):
            parts = [p.strip() for p in re.split(r"[;,]", line) if p.strip()]
            for part in parts:
                clean_part = re.sub(r"^[\*\-\•\>\s]+", "", part).strip()
                if clean_part:
                    cleaned_items.append(f"• {clean_part}")
            continue

        clean = re.sub(r"^[\*\-\•\>\s\d\.\)]+", "", line).strip()
        if clean:
            cleaned_items.append(f"• {clean}")

    if not cleaned_items:
        cleaned_items = [f"• {raw_changes.strip()}"]

    return cleaned_items


def build_announcement_text(
    version: str,
    changes: str | list[str],
    date_str: str = None,
    description: str = None,
    intro_seed: int = None
) -> str:
    """
    Genera el texto del anuncio en primera persona con la personalidad vulgar, sarcástica y divertida del bot.
    Utiliza ÚNICAMENTE los cambios reales provistos.
    """
    if not date_str:
        now = datetime.datetime.utcnow()
        # Formato ej: 29 de Agosto, 2026 o DD/MM/AAAA
        date_str = now.strftime("%d/%m/%Y")

    if isinstance(changes, str):
        bullet_list = format_bullet_changes(changes)
    else:
        bullet_list = [c if c.startswith("•") else f"• {c}" for c in changes]

    changes_block = "\n".join(bullet_list)

    if intro_seed is not None:
        rng = random.Random(intro_seed)
        intro = rng.choice(SARCASTIC_INTROS)
        opening = rng.choice(SARCASTIC_OPENINGS)
        closing = rng.choice(SARCASTIC_CLOSINGS)
    else:
        intro = SARCASTIC_INTROS[0]
        opening = SARCASTIC_OPENINGS[0]
        closing = SARCASTIC_CLOSINGS[0]

    desc_section = f"\n{description.strip()}\n" if description and description.strip() else ""

    text = (
        f"{intro}\n\n"
        f"{opening}\n"
        f"{desc_section}\n"
        f"🔧 **¿QUÉ CAMBIÓ?**\n\n"
        f"{changes_block}\n\n"
        f"📦 **VERSIÓN**\n"
        f"\"{version.strip()}\"\n\n"
        f"📅 **FECHA**\n"
        f"{date_str}\n\n"
        f"{closing}\n\n"
        f"— *Miami Vice RP Bot*"
    )
    return text


def build_announcement_embed(
    version: str,
    changes: str | list[str],
    date_str: str = None,
    description: str = None,
    intro_seed: int = None
):
    import discord
    from bot.embeds import COLOR_PRIMARY

    if not date_str:
        date_str = datetime.datetime.utcnow().strftime("%d/%m/%Y")

    if isinstance(changes, str):
        bullet_list = format_bullet_changes(changes)
    else:
        bullet_list = [c if c.startswith("•") else f"• {c}" for c in changes]

    changes_block = "\n".join(bullet_list)

    if intro_seed is not None:
        rng = random.Random(intro_seed)
        intro = rng.choice(SARCASTIC_INTROS)
        opening = rng.choice(SARCASTIC_OPENINGS)
        closing = rng.choice(SARCASTIC_CLOSINGS)
    else:
        intro = SARCASTIC_INTROS[0]
        opening = SARCASTIC_OPENINGS[0]
        closing = SARCASTIC_CLOSINGS[0]

    embed = discord.Embed(
        title=intro,
        description=f"{opening}\n\n{description.strip() if description else ''}",
        color=COLOR_PRIMARY
    )

    embed.add_field(
        name="🔧 ¿Qué se cambió realmente?",
        value=changes_block[:1024] if changes_block else "• Mantenimiento y correcciones",
        inline=False
    )

    embed.add_field(name="📦 Versión", value=f"`{version.strip()}`", inline=True)
    embed.add_field(name="📅 Fecha", value=f"`{date_str}`", inline=True)

    embed.add_field(
        name="💬 Nota del Bot",
        value=f"*{closing}*",
        inline=False
    )

    embed.set_footer(text="Miami Vice RP Bot • Ocean Drive System")
    embed.timestamp = discord.utils.utcnow()
    return embed


# ==========================================
# GITHUB API INTEGRATION (REAL COMMITS/RELEASES)
# ==========================================

async def fetch_github_commits(repo: str = DEFAULT_REPO, limit: int = 5) -> list[dict]:
    """
    Obtiene los commits reales más recientes del repositorio de GitHub sin inventar datos.
    """
    url = f"https://api.github.com/repos/{repo}/commits?per_page={limit}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MiamiViceRP-Bot-Update-System"
    }

    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    if HAS_AIOHTTP:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 404:
                        logger.warning(f"[GitHub] Repositorio no encontrado: {repo}")
                        return []
                    else:
                        text = await resp.text()
                        logger.warning(f"[GitHub] Error status {resp.status} al consultar {url}: {text[:200]}")
                        return []
        except Exception as e:
            logger.error(f"[GitHub] Error de conexión con API GitHub ({repo}): {e}")
            return []
    else:
        def _sync_fetch():
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status == 200:
                        raw = response.read().decode("utf-8")
                        return json.loads(raw)
                    return []
            except Exception as ex:
                logger.error(f"[GitHub Sync] Error al consultar {url}: {ex}")
                return []

        return await asyncio.to_thread(_sync_fetch)


async def fetch_latest_release(repo: str = DEFAULT_REPO) -> dict | None:
    """
    Obtiene la última release oficial publicada en GitHub.
    """
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "MiamiViceRP-Bot-Update-System"
    }

    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    if HAS_AIOHTTP:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return None
        except Exception as e:
            logger.error(f"[GitHub] Error al obtener última release ({repo}): {e}")
            return None
    else:
        def _sync_fetch():
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status == 200:
                        raw = response.read().decode("utf-8")
                        return json.loads(raw)
                    return None
            except Exception as ex:
                logger.error(f"[GitHub Sync] Error al consultar release: {ex}")
                return None

        return await asyncio.to_thread(_sync_fetch)


def clean_commit_message(msg: str) -> str:
    """Limpia y da formato humano al mensaje del commit real."""
    first_line = msg.strip().split("\n")[0].strip()
    # Omitir ruidos comunes de merge si es posible
    if first_line.startswith("Merge pull request") or first_line.startswith("Merge branch"):
        return ""
    # Quitar prefijos semánticos comunes para que suene natural
    cleaned = re.sub(r"^(feat|fix|refactor|docs|style|test|chore|perf|ci)(\([^\)]+\))?:\s*", "", first_line, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    if cleaned:
        # Capitalizar primera letra
        return cleaned[0].upper() + cleaned[1:]
    return ""


def extract_real_changes_from_commits(commits: list[dict]) -> tuple[list[str], str | None, str | None]:
    """
    Procesa los commits reales y extrae la lista de cambios, el último SHA y la fecha.
    """
    if not commits:
        return [], None, None

    changes = []
    latest_sha = commits[0].get("sha")
    latest_date_str = None

    for c in commits:
        commit_obj = c.get("commit", {})
        msg = commit_obj.get("message", "")
        clean_msg = clean_commit_message(msg)
        if clean_msg and clean_msg not in changes:
            changes.append(clean_msg)

        if not latest_date_str:
            author_date = commit_obj.get("author", {}).get("date")
            if author_date:
                dt = parse_db_datetime(author_date)
                if dt:
                    latest_date_str = dt.strftime("%d/%m/%Y")

    if not changes:
        # Si todos eran merges o vacíos, tomar el primer mensaje
        first_msg = commits[0].get("commit", {}).get("message", "Actualización general del sistema").split("\n")[0]
        changes = [first_msg]

    return changes, latest_sha, latest_date_str


# ==========================================
# DATABASE PERSISTENCE & CONFIGURATION
# ==========================================

async def async_get_or_create_updates_config(guild_id: str) -> dict:
    """Obtiene o crea la configuración de actualizaciones para un servidor."""
    row = await aexecute("SELECT * FROM bot_updates_config WHERE guild_id=$1", (str(guild_id),), fetch="one")
    if row:
        return dict(row)

    new_id = generate_id()
    await aexecute(
        """INSERT INTO bot_updates_config 
           (id, guild_id, github_repo, auto_github_enabled, created_at, updated_at)
           VALUES ($1, $2, $3, true, NOW(), NOW())
           ON CONFLICT DO NOTHING""",
        (new_id, str(guild_id), DEFAULT_REPO)
    )

    row = await aexecute("SELECT * FROM bot_updates_config WHERE guild_id=$1", (str(guild_id),), fetch="one")
    return dict(row) if row else {
        "id": new_id,
        "guild_id": str(guild_id),
        "channel_id": None,
        "github_repo": DEFAULT_REPO,
        "auto_github_enabled": True,
        "last_commit_sha": None,
        "draft_version": "v1.4.0",
        "draft_changes": "• Optimización de base de datos y comandos\n• Nuevas mejoras de estabilidad",
        "draft_description": None,
        "draft_date": None
    }


async def async_save_updates_config(
    guild_id: str,
    channel_id: str = None,
    github_repo: str = None,
    auto_github_enabled: bool = None,
    last_commit_sha: str = None,
    draft_version: str = None,
    draft_changes: str = None,
    draft_description: str = None,
    draft_date: str = None
) -> dict:
    """Guarda modificaciones en la configuración de actualizaciones del servidor."""
    cfg = await async_get_or_create_updates_config(guild_id)

    new_channel = channel_id if channel_id is not None else cfg.get("channel_id")
    new_repo = github_repo if github_repo is not None else cfg.get("github_repo", DEFAULT_REPO)
    new_auto = auto_github_enabled if auto_github_enabled is not None else cfg.get("auto_github_enabled", True)
    new_sha = last_commit_sha if last_commit_sha is not None else cfg.get("last_commit_sha")
    new_ver = draft_version if draft_version is not None else cfg.get("draft_version")
    new_changes = draft_changes if draft_changes is not None else cfg.get("draft_changes")
    new_desc = draft_description if draft_description is not None else cfg.get("draft_description")
    new_date = draft_date if draft_date is not None else cfg.get("draft_date")

    await aexecute(
        """UPDATE bot_updates_config 
           SET channel_id=$1, github_repo=$2, auto_github_enabled=$3, last_commit_sha=$4,
               draft_version=$5, draft_changes=$6, draft_description=$7, draft_date=$8, updated_at=NOW()
           WHERE guild_id=$9""",
        (new_channel, new_repo, new_auto, new_sha, new_ver, new_changes, new_desc, new_date, str(guild_id))
    )

    return await async_get_or_create_updates_config(guild_id)


async def async_is_update_duplicate(guild_id: str, version: str = None, commit_sha: str = None) -> bool:
    """Comprueba si una versión o commit ya ha sido publicado en el servidor para evitar duplicados."""
    if commit_sha:
        row = await aexecute(
            "SELECT id FROM bot_updates_history WHERE guild_id=$1 AND commit_sha=$2",
            (str(guild_id), commit_sha), fetch="one"
        )
        if row:
            return True

    if version:
        row = await aexecute(
            "SELECT id FROM bot_updates_history WHERE guild_id=$1 AND version=$2",
            (str(guild_id), version.strip()), fetch="one"
        )
        if row:
            return True

    return False


async def async_save_update_history(
    guild_id: str,
    version: str,
    title: str,
    raw_message: str,
    changes: str,
    source: str = "manual",
    commit_sha: str = None,
    channel_id: str = None,
    message_id: str = None,
    published_by: str = "STAFF"
) -> str:
    """Registra en el historial una actualización publicada."""
    new_id = generate_id()
    await aexecute(
        """INSERT INTO bot_updates_history 
           (id, guild_id, version, title, raw_message, changes, source, commit_sha, channel_id, message_id, published_by, published_at, created_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW(), NOW())""",
        (new_id, str(guild_id), version, title, raw_message, changes, source, commit_sha, channel_id, message_id, published_by)
    )
    return new_id


async def async_get_updates_history(guild_id: str, limit: int = 5) -> list[dict]:
    """Obtiene el historial de actualizaciones publicadas."""
    rows = await aexecute(
        """SELECT * FROM bot_updates_history 
           WHERE guild_id=$1 
           ORDER BY published_at DESC 
           LIMIT $2""",
        (str(guild_id), max(1, min(limit, 20))), fetch="all"
    )
    return [dict(r) for r in (rows or [])]
