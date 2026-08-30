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
    token = os.environ.get("DISCORD_TOKEN")
    bot = MiamiViceBot()
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

    # Intentar conectar con reintentos y regeneración de instancia limpia
    max_retries = 10
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            logger.info(f"Intento de conexión {retry_count + 1}/{max_retries}...")
            
            # Si bot es None o fue cerrado previamente, instanciar y configurar uno nuevo
            if bot is None or bot.is_closed():
                bot = MiamiViceBot()
                configure_bot(bot)
                set_bot(
                    bot,
                    asyncio.get_running_loop(),
                    token,
                    factory=MiamiViceBot,
                    configurator=configure_bot,
                )
            else:
                try:
                    configure_bot(bot)
                except Exception:
                    pass

            bot_task = asyncio.create_task(bot.start(token))
            set_bot_task(bot_task)
            await bot_task
            break  # Si se conecta exitosamente, salir del loop
        except discord.LoginFailure:
            logger.error("❌ Discord rechazó DISCORD_TOKEN; verifica que sea válido.")
            logger.error("La web continúa disponible en http://localhost:3000")
            raise
        except discord.HTTPException as http_err:
            retry_count += 1
            is_429 = getattr(http_err, 'status', None) == 429 or "429" in str(http_err)
            wait_time = min(30 * retry_count, 180) if is_429 else 10
            
            # Cerrar la sesión y descartar la instancia para que el próximo intento cree una limpia
            try:
                if bot and not bot.is_closed():
                    await bot.close()
            except Exception:
                pass
            bot = None

            if is_429:
                logger.warning(
                    f"⚠️ Discord 429 Rate Limit (Demasiadas peticiones). "
                    f"Esperando {wait_time}s antes de reintentar... ({retry_count}/{max_retries})"
                )
            else:
                logger.warning(f"Error HTTP de Discord ({http_err}). Reintentando en {wait_time}s... ({retry_count}/{max_retries})")
            
            await asyncio.sleep(wait_time)
        except (discord.ConnectionClosed, OSError) as e:
            retry_count += 1
            try:
                if bot and not bot.is_closed():
                    await bot.close()
            except Exception:
                pass
            bot = None
            logger.warning(f"Conexión perdida: {e}. Reintentando en 10s... ({retry_count}/{max_retries})")
            await asyncio.sleep(10)
        except Exception as error:
            logger.error(f"Error inesperado: {error}")
            retry_count += 1
            try:
                if bot and not bot.is_closed():
                    await bot.close()
            except Exception:
                pass
            bot = None
            if retry_count >= max_retries:
                logger.warning("Alcanzado límite de intentos. Manteniendo el panel web activo.")
                await asyncio.Event().wait()
                return
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
