import sys
try:
    import audioop
except ModuleNotFoundError:
    try:
        import audioop_lts as audioop
        sys.modules["audioop"] = audioop
    except ImportError:
        pass

import os
import asyncio
import logging
import discord
from discord.ext import commands

from keep_alive import keep_alive, set_bot, set_bot_task

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("bot")


def _log_startup_diagnostics():
    logger.info("=" * 50)
    logger.info("  MIAMI VICE — DIAGNÓSTICO DE ARRANQUE")
    logger.info("=" * 50)

    discord_token = os.environ.get("DISCORD_TOKEN", "")

    from bot.db import connection_label
    logger.info(f"[ENV] BASE DE DATOS   : {connection_label()}")

    if discord_token:
        logger.info(f"[ENV] DISCORD_TOKEN  : ✅ detectado ({len(discord_token)} chars)")
    else:
        logger.error("[ENV] DISCORD_TOKEN  : ❌ NO CONFIGURADO")

    logger.info(f"[ENV] Variables cargadas por proceso: {len(os.environ)} vars de entorno visibles")
    logger.info("=" * 50)

COGS = [
    "bot.cogs.economy",
    "bot.cogs.bank",
    "bot.cogs.inventory",
    "bot.cogs.marketplace",
    "bot.cogs.departments",
    "bot.cogs.companies",
    "bot.cogs.properties",
    "bot.cogs.social",
    "bot.cogs.tickets",
    "bot.cogs.verification",
    "bot.cogs.crimen",
    "bot.cogs.dni",
    "bot.cogs.weapons",
    "bot.cogs.roblox",
    "bot.cogs.updates",
    "bot.cogs.vehicles",
    "bot.cogs.admin",
    "bot.cogs.help",
]

class MiamiViceBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )
        self.start_time = None

    async def setup_hook(self):
        for cog in COGS:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded cog: {cog}")
            except Exception as e:
                logger.error(f"Failed to load cog {cog}: {e}")


def configure_bot(bot):
    from bot.events import setup_events
    from bot.jobs.cron import setup_jobs
    setup_events(bot)
    setup_jobs(bot)


async def main():
    _log_startup_diagnostics()
    bot = MiamiViceBot()
    token = os.environ.get("DISCORD_TOKEN")
    set_bot(
        bot,
        asyncio.get_running_loop(),
        token,
        factory=MiamiViceBot,
        configurator=configure_bot,
    )
    keep_alive()

    if not token:
        logger.error("DISCORD_TOKEN not set in environment")
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

    # Intentar conectar con reintentos
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            logger.info(f"Intento de conexión {retry_count + 1}/{max_retries}...")
            bot_task = asyncio.create_task(bot.start(token))
            set_bot_task(bot_task)
            await bot_task
            break  # Si se conecta exitosamente, salir del loop
        except discord.LoginFailure:
            logger.error("❌ Discord rechazó DISCORD_TOKEN; verifica que sea válido.")
            logger.error("La web continúa disponible en http://localhost:3000")
            raise
        except (discord.ConnectionClosed, OSError) as e:
            retry_count += 1
            logger.warning(f"Conexión perdida: {e}. Reintentando en 5s... ({retry_count}/{max_retries})")
            if retry_count >= max_retries:
                logger.error("No se pudo conectar después de múltiples intentos.")
                raise RuntimeError("Discord no está disponible después de múltiples intentos") from e
            await asyncio.sleep(5)  # Esperar antes de reintentar
        except Exception as error:
            logger.error(f"Error inesperado: {error}")
            retry_count += 1
            if retry_count >= max_retries:
                await asyncio.Event().wait()
                return
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
