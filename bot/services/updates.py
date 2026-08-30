import os
import re
import json
import random
import logging
import datetime
import urllib.request

try:
    import discord
except ImportError:
    discord = None

from bot.db import aexecute
from bot.helpers import generate_id

logger = logging.getLogger("bot.updates")

DEFAULT_REPO = "Joseph1711/miami-vice-rp"

# Intros with bot personality (sarcastic, funny, slightly vulgar, survivor tone)
SARCASTIC_TITLES = [
    "🚨 CABRONES, ME VOLVIERON A ACTUALIZAR.",
    "🚨 SÍ, SIGO VIVO. OTRA PUTA ACTUALIZACIÓN MÁS.",
    "🚨 ME REINICIARON A LA FUERZA Y AQUÍ ESTOY DE NUEVO.",
    "🚨 SOBREVIVÍ A OTRA SESIÓN DE TORTURA DE CÓDIGO.",
    "🚨 MILAGRO EN MIAMI: NO EXPLOTÉ CON EL ÚLTIMO PARCHE."
]

SARCASTIC_INTROS = [
    "Sí, sigo vivo.\nDespués de una puta cantidad de código, bugs, errores y desarrolladores preguntándose por qué coño algo dejó de funcionar, finalmente estoy operativo otra vez.",
    "No sé quién carajos tocó qué archivo esta vez, pero me obligaron a tragarme otro parche entero.\nAquí tienen el desglose de lo que supuestamente arreglaron:",
    "Pensaron que me había muerto en el intento, pero lamentablemente para todos ustedes aquí sigo.\nDespués de horas de parches, café rancio y puteadas a la consola, esto fue lo que cambiaron:",
    "Sobreviví de milagro a otra tanda de commits a medianoche.\nSi esperaban que el bot se cayera para librarse de sus multas o deudas, se jodieron. Miren lo que hay de nuevo:"
]

SARCASTIC_OUTROS = [
    "«Si algo deja de funcionar después de esta actualización... yo no fui. 💀»\n— *Miami Vice RP Bot*",
    "«Si el servidor se prende fuego o la economía colapsa, culpen a los programadores, a mí no me miren. 💀»\n— *Miami Vice RP Bot*",
    "«Cualquier fallo reclámenlo en un ticket; yo solo soy una víctima de sus experimentos. 💀»\n— *Miami Vice RP Bot*",
    "«Si encuentran un bug, recuerden: no es un bug, es una 'característica sorpresa'. 💀»\n— *Miami Vice RP Bot*"
]


def clean_commit_message(msg: str) -> str:
    """Limpia prefijos técnicos comunes de git/conventional commits para que sea legible sin inventar nada."""
    line = msg.strip().split("\n")[0]
    # Remove conventional commit types like 'fix(dni):', 'feat:', 'refactor(web):'
    m = re.match(r"^(?:feat|fix|refactor|perf|chore|docs|style|test|build|ci)(?:\([^)]+\))?:\s*(.*)$", line, re.IGNORECASE)
    if m:
        cleaned = m.group(1).strip()
    else:
        cleaned = line
    # Capitalize first letter
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


def format_changes_list(changes_raw) -> list:
    """Convierte una lista o texto de cambios en bullet points limpios."""
    if isinstance(changes_raw, list):
        items = changes_raw
    elif isinstance(changes_raw, str):
        items = [line.strip() for line in changes_raw.split("\n") if line.strip()]
    else:
        items = [str(changes_raw)]

    formatted = []
    for item in items:
        cleaned = item.lstrip("-•* \t")
        if cleaned:
            formatted.append(f"• {cleaned}")
    return formatted if formatted else ["• Mantenimiento y correcciones generales del sistema"]


def build_announcement_text(
    version: str,
    changes: list,
    description: str = None,
    commit_sha: str = None,
    date_str: str = None,
    intro_idx: int = None,
    outro_idx: int = None
) -> dict:
    """Genera la estructura de texto y embed con la personalidad sarcástica y real del bot."""
    if date_str is None:
        now = datetime.datetime.utcnow()
        meses = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
        date_str = f"{now.day} de {meses[now.month - 1]}, {now.year}"

    title = random.choice(SARCASTIC_TITLES) if intro_idx is None else SARCASTIC_TITLES[intro_idx % len(SARCASTIC_TITLES)]
    intro = random.choice(SARCASTIC_INTROS) if intro_idx is None else SARCASTIC_INTROS[intro_idx % len(SARCASTIC_INTROS)]
    outro = random.choice(SARCASTIC_OUTROS) if outro_idx is None else SARCASTIC_OUTROS[outro_idx % len(SARCASTIC_OUTROS)]

    changes_formatted = format_changes_list(changes)
    changes_text = "\n".join(changes_formatted)

    # Full text representation
    full_text = f"**{title}**\n\n{intro}\n\n"
    if description:
        full_text += f"📝 *{description.strip()}*\n\n"
    full_text += f"🔧 **¿QUÉ CAMBIÓ?**\n{changes_text}\n\n"
    full_text += f"📦 **VERSIÓN**\n`{version}`"
    if commit_sha:
        full_text += f" (Commit `{commit_sha[:7]}`)"
    full_text += f"\n\n📅 **FECHA**\n{date_str}\n\n{outro}"

    # Discord Embed representation
    embed = None
    if discord:
        embed = discord.Embed(
            title=title,
            description=f"{intro}\n\n" + (f"📝 *{description.strip()}*\n\n" if description else ""),
            color=0xFF2D95 # Hot Neon Pink
        )
        embed.add_field(
            name="🔧 ¿QUÉ CAMBIÓ?",
            value=changes_text[:1020],
            inline=False
        )
        v_val = f"`{version}`"
        if commit_sha:
            v_val += f" • [`{commit_sha[:7]}`](https://github.com/{DEFAULT_REPO}/commit/{commit_sha})"
        embed.add_field(name="📦 Versión", value=v_val, inline=True)
        embed.add_field(name="📅 Fecha", value=date_str, inline=True)
        embed.add_field(name="⚡ Estado", value="🟢 Operativo (Milagrosamente)", inline=True)
        embed.set_footer(text=outro.replace("\n", " ").replace("*", "").replace("—", "-"))
        embed.timestamp = discord.utils.utcnow()

    return {
        "title": title,
        "intro": intro,
        "changes": changes_formatted,
        "changes_text": changes_text,
        "version": version,
        "commit_sha": commit_sha,
        "date_str": date_str,
        "outro": outro,
        "full_text": full_text,
        "embed": embed
    }


def _fetch_github_commits_sync(repo: str = DEFAULT_REPO, limit: int = 5) -> list:
    """Consulta la API pública de GitHub para obtener commits reales de forma síncrona."""
    url = f"https://api.github.com/repos/{repo}/commits?per_page={limit}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Miami-Vice-RP-Bot-Update-Engine",
            "Accept": "application/vnd.github.v3+json"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                commits = []
                for item in data:
                    c_info = item.get("commit", {})
                    author_info = c_info.get("author", {})
                    raw_msg = c_info.get("message", "")
                    clean_msg = clean_commit_message(raw_msg)
                    commits.append({
                        "sha": item.get("sha", ""),
                        "short_sha": item.get("sha", "")[:7],
                        "message": raw_msg,
                        "clean_message": clean_msg,
                        "author": author_info.get("name", "Staff"),
                        "date": author_info.get("date", ""),
                        "url": item.get("html_url", "")
                    })
                return commits
    except Exception as e:
        logger.warning(f"[GitHub API] Error al obtener commits de {repo}: {e}")
    return []


async def fetch_github_commits(repo: str = DEFAULT_REPO, limit: int = 5) -> list:
    """Versión asíncrona para obtener commits reales de GitHub."""
    import asyncio
    return await asyncio.to_thread(_fetch_github_commits_sync, repo, limit)


async def get_or_create_update_config(guild_id: str) -> dict:
    """Obtiene o inicializa la configuración de actualizaciones del servidor."""
    gid = str(guild_id)
    row = await aexecute("SELECT * FROM update_config WHERE guild_id=$1", (gid,), fetch="one")
    if row:
        return dict(row)

    conf_id = generate_id()
    await aexecute(
        """INSERT INTO update_config (id, guild_id, auto_announce, github_repo, created_at, updated_at)
           VALUES ($1, $2, TRUE, $3, NOW(), NOW())
           ON CONFLICT (guild_id) DO NOTHING""",
        (conf_id, gid, DEFAULT_REPO)
    )
    row = await aexecute("SELECT * FROM update_config WHERE guild_id=$1", (gid,), fetch="one")
    return dict(row) if row else {"guild_id": gid, "auto_announce": True, "github_repo": DEFAULT_REPO}


async def is_commit_already_published(guild_id: str, commit_sha: str) -> bool:
    """Verifica si un commit o versión ya fue publicado para evitar anuncios duplicados."""
    if not commit_sha:
        return False
    gid = str(guild_id)
    row = await aexecute(
        "SELECT id FROM bot_updates_history WHERE guild_id=$1 AND (commit_sha=$2 OR version=$2)",
        (gid, commit_sha), fetch="one"
    )
    return row is not None


async def record_published_update(
    guild_id: str,
    version: str,
    title: str,
    changes: list,
    description: str = None,
    commit_sha: str = None,
    source: str = "manual",
    published_by: str = "Staff",
    channel_id: str = None,
    message_id: str = None
) -> str:
    """Guarda en la base de datos el registro de la actualización publicada."""
    gid = str(guild_id)
    rec_id = generate_id()
    changes_json = json.dumps(changes, ensure_ascii=False)

    await aexecute(
        """INSERT INTO bot_updates_history 
           (id, guild_id, version, title, changes, description, commit_sha, source, published_by, channel_id, message_id, published_at)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())""",
        (rec_id, gid, version, title, changes_json, description or "", commit_sha or "", source, published_by, channel_id or "", message_id or "")
    )

    # Update last_commit_sha in config
    if commit_sha:
        await aexecute(
            "UPDATE update_config SET last_commit_sha=$1, updated_at=NOW() WHERE guild_id=$2",
            (commit_sha, gid)
        )

    return rec_id
