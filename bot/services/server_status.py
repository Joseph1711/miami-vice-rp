import datetime
import logging
from bot.db import aexecute
from bot.helpers import generate_id

logger = logging.getLogger("bot.services.server_status")

SERVER_CODE = "MVERP"


async def get_server_status(guild_id: str) -> dict:
    """
    Obtiene el estado actual del servidor ('OPEN' o 'CLOSED').
    Si no existe registro para el guild, crea uno inicial como 'CLOSED'.
    """
    row = await aexecute(
        "SELECT * FROM server_status WHERE guild_id = $1",
        (str(guild_id),),
        fetch="one"
    )
    if row:
        return dict(row)

    # Registro por defecto
    await aexecute(
        """INSERT INTO server_status (guild_id, status, server_code, updated_at)
           VALUES ($1, 'CLOSED', $2, NOW())
           ON CONFLICT (guild_id) DO NOTHING""",
        (str(guild_id), SERVER_CODE)
    )
    row = await aexecute(
        "SELECT * FROM server_status WHERE guild_id = $1",
        (str(guild_id),),
        fetch="one"
    )
    return dict(row) if row else {"guild_id": str(guild_id), "status": "CLOSED", "server_code": SERVER_CODE}


async def is_server_open(guild_id: str) -> bool:
    """Verifica de forma rápida y booleana si el servidor está abierto."""
    data = await get_server_status(guild_id)
    return str(data.get("status", "CLOSED")).upper() == "OPEN"


async def set_server_status(guild_id: str, status: str, updated_by: str = None, server_code: str = SERVER_CODE) -> dict:
    """
    Actualiza y persiste el estado del servidor a 'OPEN' o 'CLOSED'.
    """
    norm_status = status.upper()
    if norm_status not in ("OPEN", "CLOSED"):
        norm_status = "CLOSED"

    await aexecute(
        """INSERT INTO server_status (guild_id, status, server_code, updated_by, updated_at)
           VALUES ($1, $2, $3, $4, NOW())
           ON CONFLICT (guild_id) DO UPDATE 
           SET status = EXCLUDED.status,
               server_code = EXCLUDED.server_code,
               updated_by = EXCLUDED.updated_by,
               updated_at = NOW()""",
        (str(guild_id), norm_status, server_code, str(updated_by) if updated_by else None)
    )
    return await get_server_status(guild_id)


async def create_server_vote(
    guild_id: str,
    channel_id: str,
    message_id: str,
    creator_id: str,
    duration_minutes: int = 5
) -> dict:
    """Crea un nuevo registro de votación en la base de datos."""
    vote_id = generate_id()
    ends_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=max(1, duration_minutes))
    
    # Cancelar/cerrar votaciones activas previas en el mismo servidor
    await aexecute(
        "UPDATE server_votes SET status = 'cancelled' WHERE guild_id = $1 AND status = 'active'",
        (str(guild_id),)
    )

    await aexecute(
        """INSERT INTO server_votes (id, guild_id, channel_id, message_id, creator_id, status, duration_minutes, ends_at, created_at)
           VALUES ($1, $2, $3, $4, $5, 'active', $6, $7, NOW())""",
        (vote_id, str(guild_id), str(channel_id), str(message_id), str(creator_id), duration_minutes, ends_at)
    )

    return {
        "id": vote_id,
        "guild_id": str(guild_id),
        "channel_id": str(channel_id),
        "message_id": str(message_id),
        "creator_id": str(creator_id),
        "status": "active",
        "duration_minutes": duration_minutes,
        "ends_at": ends_at
    }


async def get_active_vote_by_message(message_id: str) -> dict:
    """Busca una votación activa por el ID del mensaje de Discord."""
    row = await aexecute(
        "SELECT * FROM server_votes WHERE message_id = $1 AND status = 'active'",
        (str(message_id),),
        fetch="one"
    )
    return dict(row) if row else None


async def get_active_vote_by_guild(guild_id: str) -> dict:
    """Busca la votación activa actual de un servidor."""
    row = await aexecute(
        "SELECT * FROM server_votes WHERE guild_id = $1 AND status = 'active' ORDER BY created_at DESC LIMIT 1",
        (str(guild_id),),
        fetch="one"
    )
    return dict(row) if row else None


async def record_user_vote(vote_id: str, discord_id: str, choice: str):
    """
    Registra o actualiza el voto de un usuario (solo 1 voto por usuario).
    choice: 'yes' o 'no'.
    """
    norm_choice = "yes" if choice.lower() in ("yes", "si", "sí", "🟢", "1") else "no"
    await aexecute(
        """INSERT INTO server_vote_entries (vote_id, discord_id, choice, created_at)
           VALUES ($1, $2, $3, NOW())
           ON CONFLICT (vote_id, discord_id) DO UPDATE 
           SET choice = EXCLUDED.choice,
               created_at = NOW()""",
        (str(vote_id), str(discord_id), norm_choice)
    )


async def remove_user_vote(vote_id: str, discord_id: str):
    """Elimina el voto de un usuario."""
    await aexecute(
        "DELETE FROM server_vote_entries WHERE vote_id = $1 AND discord_id = $2",
        (str(vote_id), str(discord_id))
    )


async def get_vote_results(vote_id: str) -> dict:
    """Calcula el conteo de votos a favor, en contra y el total."""
    rows = await aexecute(
        "SELECT choice, COUNT(*) as count FROM server_vote_entries WHERE vote_id = $1 GROUP BY choice",
        (str(vote_id),),
        fetch="all"
    ) or []
    
    yes_count = 0
    no_count = 0
    for r in rows:
        c = str(r.get("choice", "")).lower()
        cnt = int(r.get("count", 0))
        if c == "yes":
            yes_count += cnt
        elif c == "no":
            no_count += cnt

    total = yes_count + no_count
    return {
        "yes": yes_count,
        "no": no_count,
        "total": total,
        "winner": "yes" if yes_count > no_count else ("no" if no_count > yes_count else "tie")
    }


async def close_server_vote(vote_id: str) -> dict:
    """Marca la votación como cerrada y devuelve los resultados finales."""
    await aexecute(
        "UPDATE server_votes SET status = 'closed' WHERE id = $1",
        (str(vote_id),)
    )
    return await get_vote_results(vote_id)
