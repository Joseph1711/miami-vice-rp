"""
Servicio centralizado de Webhooks para Miami Vice Roleplay.
Maneja el registro, almacenamiento y despacho de webhooks para:
- Multas de tránsito y sanciones económicas
- Arrestos e informes penitenciarios
- Postulaciones y formularios de ingreso a departamentos (con mención @everyone)
"""

import asyncio
import datetime
import json
import logging
import re
import urllib.request
import urllib.error
from typing import Optional, Tuple, Dict, Any, List

from bot.db import aexecute
from bot.helpers import generate_id

logger = logging.getLogger("bot.services.webhooks")

DISCORD_WEBHOOK_REGEX = re.compile(
    r"^https:\/\/(?:ptb\.|canary\.)?discord(?:app)?\.com\/api\/webhooks\/\d+\/[\w-]+(?:\?.*)?$",
    re.IGNORECASE
)


def validate_discord_webhook_url(url: str) -> bool:
    """Verifica si una URL tiene el formato de un webhook válido de Discord."""
    if not url or not isinstance(url, str):
        return False
    clean = url.strip()
    return bool(DISCORD_WEBHOOK_REGEX.match(clean))


def _post_webhook_sync(url: str, payload: dict) -> Tuple[bool, Optional[str]]:
    """Ejecuta una petición HTTP POST síncrona a la URL del webhook de Discord."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url.strip(),
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "MiamiViceRP-WebhookService/1.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            if status in (200, 204):
                return True, None
            return False, f"HTTP status {status}"
    except urllib.error.HTTPError as he:
        body = ""
        try:
            body = he.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        logger.error(f"[Webhook] Error HTTP {he.code}: {body}")
        # Si el webhook no es propiedad de la app, Discord rechaza components con 400 (COMPONENT_NOT_OWNED)
        if he.code == 400 and "components" in payload and ("COMPONENT_NOT_OWNED" in body or "components" in body):
            logger.warning("[Webhook] Webhook manual no soporta componentes directamente. Reenviando payload sin components...")
            retry_payload = dict(payload)
            retry_payload.pop("components", None)
            return _post_webhook_sync(url, retry_payload)
        return False, f"HTTP {he.code}: {body[:150]}"
    except Exception as e:
        logger.error(f"[Webhook] Error de conexión: {e}")
        return False, str(e)


async def send_discord_webhook(
    webhook_url: str,
    content: Optional[str] = None,
    embeds: Optional[List[Any]] = None,
    components: Optional[List[Dict[str, Any]]] = None,
    username: str = "Miami Vice RP • Registro Oficial",
    avatar_url: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Envía de forma asíncrona un mensaje o lista de embeds a una URL de webhook de Discord.
    Soporta tanto discord.Embed como diccionarios, y componentes interactivos (ActionRows/botones).
    """
    if not webhook_url or not validate_discord_webhook_url(webhook_url):
        return False, "URL de webhook inválida"

    serialized_embeds = []
    if embeds:
        for emb in embeds:
            if hasattr(emb, "to_dict"):
                serialized_embeds.append(emb.to_dict())
            elif isinstance(emb, dict):
                serialized_embeds.append(emb)

    payload: Dict[str, Any] = {}
    if content:
        payload["content"] = str(content)
    if serialized_embeds:
        payload["embeds"] = serialized_embeds
    if components:
        payload["components"] = components
    if username:
        payload["username"] = str(username)[:80]
    if avatar_url:
        payload["avatar_url"] = str(avatar_url)

    # Si aiohttp está disponible en tiempo de ejecución, usarlo; de lo contrario asyncio.to_thread
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url.strip(),
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status in (200, 204):
                    return True, None
                body = await resp.text()
                # Reintento sin components si Discord rechaza por ser webhook manual
                if resp.status == 400 and "components" in payload and ("COMPONENT_NOT_OWNED" in body or "components" in body):
                    retry_payload = dict(payload)
                    retry_payload.pop("components", None)
                    async with session.post(
                        webhook_url.strip(),
                        json=retry_payload,
                        headers={"Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as retry_resp:
                        if retry_resp.status in (200, 204):
                            return True, None
                return False, f"HTTP {resp.status}: {body[:150]}"
    except ImportError:
        pass
    except Exception as aio_err:
        logger.warning(f"[Webhook] Fallback urllib tras fallo en aiohttp: {aio_err}")

    # Fallback universal con biblioteca estándar sin bloquear el loop de asyncio
    return await asyncio.to_thread(_post_webhook_sync, webhook_url, payload)


# =============================================================================
# PERSISTENCIA Y CONSULTA EN BASE DE DATOS
# =============================================================================

async def init_webhooks_table():
    """Garantiza que la tabla server_webhooks exista en la base de datos."""
    try:
        await aexecute("""
            CREATE TABLE IF NOT EXISTS server_webhooks (
                id TEXT PRIMARY KEY,
                guild_id TEXT NOT NULL,
                category TEXT NOT NULL,
                target_id TEXT,
                webhook_url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
    except Exception as e:
        logger.error(f"[Webhook] Error inicializando server_webhooks: {e}")


async def get_webhook_url(guild_id: str, category: str, target_id: Optional[str] = None) -> Optional[str]:
    """
    Obtiene la URL configurada de un webhook para un servidor y categoría:
    - 'fines': Registro de multas
    - 'arrests': Registro de arrestos
    - 'department': Postulaciones/notificaciones de un departamento (target_id = acronym)
    """
    await init_webhooks_table()
    gid = str(guild_id)
    cat = str(category).lower().strip()
    tid = str(target_id).upper().strip() if target_id else ""

    # 1. Buscar en server_webhooks
    row = await aexecute(
        """SELECT webhook_url FROM server_webhooks 
           WHERE guild_id = $1 AND category = $2 AND COALESCE(target_id, '') = $3 
           ORDER BY updated_at DESC LIMIT 1""",
        (gid, cat, tid),
        fetch="one"
    )
    if row and row.get("webhook_url"):
        return row["webhook_url"].strip()

    # 2. Fallbacks específicos por tabla
    if cat == "department" and tid:
        dept = await aexecute(
            "SELECT webhook_url FROM departments WHERE guild_id = $1 AND acronym ILIKE $2",
            (gid, tid),
            fetch="one"
        )
        if dept and dept.get("webhook_url"):
            return dept["webhook_url"].strip()

    if cat == "fines":
        cfg = await aexecute(
            "SELECT webhook_fines_url FROM guild_config WHERE guild_id = $1",
            (gid,),
            fetch="one"
        )
        if cfg and cfg.get("webhook_fines_url"):
            return cfg["webhook_fines_url"].strip()

    if cat == "arrests":
        cfg = await aexecute(
            "SELECT webhook_arrests_url FROM guild_config WHERE guild_id = $1",
            (gid,),
            fetch="one"
        )
        if cfg and cfg.get("webhook_arrests_url"):
            return cfg["webhook_arrests_url"].strip()

    return None


async def set_webhook_url(
    guild_id: str,
    category: str,
    webhook_url: str,
    target_id: Optional[str] = None
) -> Tuple[bool, str]:
    """Guarda o actualiza la URL del webhook en la base de datos."""
    await init_webhooks_table()
    url = webhook_url.strip()
    if not validate_discord_webhook_url(url):
        return False, "La URL proporcionada no es un enlace válido de webhook de Discord."

    gid = str(guild_id)
    cat = str(category).lower().strip()
    tid = str(target_id).upper().strip() if target_id else ""

    # Verificar si ya existe fila
    existing = await aexecute(
        "SELECT id FROM server_webhooks WHERE guild_id = $1 AND category = $2 AND COALESCE(target_id, '') = $3",
        (gid, cat, tid),
        fetch="one"
    )
    if existing:
        await aexecute(
            "UPDATE server_webhooks SET webhook_url = $1, updated_at = NOW() WHERE id = $2",
            (url, existing["id"])
        )
    else:
        new_id = generate_id()
        await aexecute(
            """INSERT INTO server_webhooks (id, guild_id, category, target_id, webhook_url, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, NOW(), NOW())""",
            (new_id, gid, cat, tid, url)
        )

    # Sincronizar en tabla departments si aplica
    if cat == "department" and tid:
        try:
            await aexecute(
                "UPDATE departments SET webhook_url = $1 WHERE guild_id = $2 AND acronym ILIKE $3",
                (url, gid, tid)
            )
        except Exception:
            pass

    return True, "Webhook configurado exitosamente."


async def remove_webhook_url(
    guild_id: str,
    category: str,
    target_id: Optional[str] = None
) -> Tuple[bool, str]:
    """Elimina la configuración del webhook."""
    await init_webhooks_table()
    gid = str(guild_id)
    cat = str(category).lower().strip()
    tid = str(target_id).upper().strip() if target_id else ""

    await aexecute(
        "DELETE FROM server_webhooks WHERE guild_id = $1 AND category = $2 AND COALESCE(target_id, '') = $3",
        (gid, cat, tid)
    )

    if cat == "department" and tid:
        try:
            await aexecute(
                "UPDATE departments SET webhook_url = NULL WHERE guild_id = $1 AND acronym ILIKE $2",
                (gid, tid)
            )
        except Exception:
            pass

    return True, "Webhook eliminado correctamente."


async def get_all_server_webhooks(guild_id: str) -> List[Dict[str, Any]]:
    """Devuelve la lista de webhooks configurados en el servidor."""
    await init_webhooks_table()
    rows = await aexecute(
        "SELECT * FROM server_webhooks WHERE guild_id = $1 ORDER BY category, target_id",
        (str(guild_id),),
        fetch="all"
    ) or []
    return [dict(r) for r in rows]


# =============================================================================
# ENVÍOS ESPECÍFICOS DE MÓDULOS
# =============================================================================

async def send_fine_webhook(guild_id: str, fine_embed_dict: dict) -> bool:
    """Envía un registro oficial de multa al webhook configurado."""
    url = await get_webhook_url(guild_id, "fines")
    if not url:
        return False
    ok, err = await send_discord_webhook(
        webhook_url=url,
        embeds=[fine_embed_dict],
        username="Policía Miami Vice • Registro de Multas",
        avatar_url="https://images.unsplash.com/photo-1541872703-74c5e44368f9?w=300&auto=format&fit=crop&q=80"
    )
    if not ok:
        logger.warning(f"[Webhook] Falló envío de multa a {url}: {err}")
    return ok


async def send_arrest_webhook(guild_id: str, arrest_embed_dict: dict) -> bool:
    """Envía un registro oficial de arresto al webhook configurado."""
    url = await get_webhook_url(guild_id, "arrests")
    if not url:
        return False
    ok, err = await send_discord_webhook(
        webhook_url=url,
        embeds=[arrest_embed_dict],
        username="Sistema Penitenciario • Registro de Arrestos",
        avatar_url="https://images.unsplash.com/photo-1589829545856-d10d557cf95f?w=300&auto=format&fit=crop&q=80"
    )
    if not ok:
        logger.warning(f"[Webhook] Falló envío de arresto a {url}: {err}")
    return ok


async def send_department_application_webhook(
    guild_id: str,
    dept: dict,
    app_embed_dict: dict,
    app_id: str = "",
    applicant_id: str = ""
) -> bool:
    """
    Envía una postulación de ingreso de departamento al webhook específico configurado,
    MENCIONANDO EXPLÍCITAMENTE A @everyone y añadiendo los botones de acción:
    - ✅ Aceptar
    - 🔍 En Revisión
    - ❌ Rechazar
    """
    acronym = dept.get("acronym", "").upper().strip()
    url = await get_webhook_url(guild_id, "department", acronym)
    if not url:
        # Fallback a webhook general de departamentos
        url = await get_webhook_url(guild_id, "departments")

    if not url:
        return False

    dept_name = dept.get("name", "Departamento Oficial")
    mention_content = f"@everyone 🚨 **¡Nueva Postulación de Ingreso para {dept_name} [{acronym}]!**"

    dept_id = str(dept.get("id", ""))
    components = []
    if app_id and dept_id:
        components = [
            {
                "type": 1,  # ActionRow
                "components": [
                    {
                        "type": 2,  # Button
                        "style": 3,  # Success / Verde
                        "label": "Aceptar",
                        "emoji": {"name": "✅"},
                        "custom_id": f"btn_dept_act:accept:{app_id}:{dept_id}:{applicant_id}:{guild_id}"
                    },
                    {
                        "type": 2,  # Button
                        "style": 1,  # Primary / Azul
                        "label": "En Revisión",
                        "emoji": {"name": "🔍"},
                        "custom_id": f"btn_dept_act:review:{app_id}:{dept_id}:{applicant_id}:{guild_id}"
                    },
                    {
                        "type": 2,  # Button
                        "style": 4,  # Danger / Rojo
                        "label": "Rechazar",
                        "emoji": {"name": "❌"},
                        "custom_id": f"btn_dept_act:reject:{app_id}:{dept_id}:{applicant_id}:{guild_id}"
                    }
                ]
            }
        ]

    ok, err = await send_discord_webhook(
        webhook_url=url,
        content=mention_content,
        embeds=[app_embed_dict],
        components=components if components else None,
        username=f"Admisiones • {acronym} {dept_name[:30]}",
        avatar_url="https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=300&auto=format&fit=crop&q=80"
    )
    if not ok:
        logger.warning(f"[Webhook] Falló envío de postulación de {acronym} a {url}: {err}")
    return ok
