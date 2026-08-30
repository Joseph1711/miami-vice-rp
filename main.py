import asyncio
import logging
import os
import aiohttp
import discord
from discord.ext import commands

from bot.config import get_settings
from bot.events import set_bot_task
from keep_alive import keep_alive

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("bot")

# Configurar intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

# Instancia del bot
bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None,
)

# Extensiones / Cogs a cargar
EXTENSIONS = [
    "bot.cogs.verification",
    "bot.cogs.dni",
    "bot.cogs.economy",
    "bot.cogs.bank",
    "bot.cogs.inventory",
    "bot.cogs.marketplace",
    "bot.cogs.companies",
    "bot.cogs.properties",
    "bot.cogs.vehicles",
    "bot.cogs.weapons",
    "bot.cogs.crimen",
    "bot.cogs.social",
    "bot.cogs.tickets",
    "bot.cogs.updates",
    "bot.cogs.departments",
    "bot.cogs.roblox",
    "bot.cogs.bolo",
    "bot.cogs.cases",
    "bot.cogs.incidents",
    "bot.cogs.announcements",
    "bot.cogs.police",
    "bot.cogs.server_control",
    "bot.cogs.admin",
    "bot.cogs.help",
]


def configure_bot(b: commands.Bot):
    import bot.events as events_mod

    events_mod.setup_events(b)


async def load_extensions(b: commands.Bot):
    for ext in EXTENSIONS:
        try:
            await b.load_extension(ext)
            logger.info("Cog cargado: %s", ext)
        except Exception as e:
            logger.warning("No se pudo cargar %s: %s", ext, e)


async def main():
    settings = get_settings()
    token = settings.discord_token

    # Iniciar servidor web de monitoreo para Render/Uptime
    logger.info(
        "Panel web de Miami Vice RP disponible en el puerto %s",
        settings.port,
    )
    keep_alive()

    if not token:
        logger.error("DISCORD_TOKEN no configurado en las variables de entorno.")
        logger.warning("El panel seguirá disponible; configura DISCORD_TOKEN para encender el bot.")
        await asyncio.Event().wait()
        return

    from bot.db import check_connection
    db_check = check_connection()
    if db_check["ok"]:
        logger.info(f"[DB] Conexión verificada ✅ — URL: {db_check['masked_url']} | SSL: {db_check['ssl']}")
    else:
        logger.error(f"[DB] Conexión fallida ❌ — {db_check['error']}")
        logger.error("[DB] El bot no puede arrancar sin base de datos.")
        logger.warning("El panel seguirá disponible; corrige la conexión de base de datos para encender el bot.")
        await asyncio.Event().wait()
        return

    try:
        from scripts.init_db import init_db
        init_db()
    except Exception as e:
        logger.error(f"[DB] Error inicializando tablas: {e}")
        logger.warning("El panel seguirá disponible; no se pudo inicializar la base de datos.")
        await asyncio.Event().wait()
        return

    try:
        configure_bot(bot)
    except Exception as error:
        logger.exception("No se pudo configurar el bot: %s", error)
        logger.warning("El panel seguirá disponible; corrige la configuración para encender el bot.")
        await asyncio.Event().wait()
        return

    # Loop de conexión con manejo inteligente de Rate Limits (429 Cloudflare / Discord)
    retry_delay = 10
    max_delay = 300  # Máximo 5 minutos de espera exponencial

    while True:
        try:
            logger.info("Iniciando conexión con Discord...")
            bot_task = asyncio.create_task(bot.start(token))
            set_bot_task(bot_task)
            await bot_task
            break
        except discord.LoginFailure:
            logger.critical("❌ Token inválido rechazado por Discord. Verifica DISCORD_TOKEN.")
            await asyncio.Event().wait()
            return
        except discord.HTTPException as http_err:
            if http_err.status == 429:
                logger.warning(
                    f"⚠️ [RATE LIMIT 429] Discord/Cloudflare ha bloqueado temporalmente la IP del servidor de Render. "
                    f"Esperando {retry_delay}s antes de reintentar para no saturar la API..."
                )
            else:
                logger.error(f"Error HTTP de Discord ({http_err.status}): {http_err}. Reintentando en {retry_delay}s...")
            
            # Cerrar sesión limpia de aiohttp si quedó abierta
            try:
                if not bot.is_closed():
                    await bot.close()
            except Exception:
                pass

            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)
        except (discord.ConnectionClosed, OSError, aiohttp.ClientError) as conn_err:
            logger.warning(f"Conexión perdida con Discord ({conn_err}). Reintentando en {retry_delay}s...")
            try:
                if not bot.is_closed():
                    await bot.close()
            except Exception:
                pass
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)
        except Exception as error:
            logger.error(f"Error inesperado durante la ejecución: {error}")
            try:
                if not bot.is_closed():
                    await bot.close()
            except Exception:
                pass
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot detenido manualmente.")
