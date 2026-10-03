import discord
from discord import app_commands
from discord.ext import tasks
import asyncio
import logging
import datetime
import random

from bot.db import aexecute_many
from bot.helpers import async_get_or_create_user, async_get_or_create_guild_config
from bot.services.levels import add_xp
from bot.miami_systems import build_catalog_messages, wants_catalog
from bot.middleware.antispam import is_spamming
from bot.config import XP_PER_MESSAGE_MIN, XP_PER_MESSAGE_MAX

logger = logging.getLogger("bot")

# Miembros por lote al sincronizar nombres. Cada lote viaja como una sola
# sentencia contra la base de datos en vez de una por miembro.
USER_SYNC_BATCH = 50


async def _sync_member_names(bot):
    """Actualiza el nombre de los miembros en lotes, sin bloquear el arranque."""
    pending = []
    total = 0
    try:
        for guild in bot.guilds:
            for member in guild.members:
                if member.bot or not member.name:
                    continue
                pending.append((
                    "UPDATE users SET username=$1, display_name=$2, updated_at=NOW() "
                    "WHERE discord_id=$3 AND guild_id=$4",
                    (member.name, member.display_name or member.name,
                     str(member.id), str(guild.id)),
                ))
                if len(pending) < USER_SYNC_BATCH:
                    continue
                await aexecute_many(pending)
                total += len(pending)
                pending = []
                await asyncio.sleep(0)  # cede el control al resto del bot
        if pending:
            await aexecute_many(pending)
            total += len(pending)
    except Exception as error:
        logger.warning("Sincronizacion de nombres interrumpida tras %d miembros: %s", total, error)
        return
    if total:
        logger.info("Nombres de usuario sincronizados: %d", total)

# Tareas en vuelo del auto-registro de usuario. asyncio solo guarda una
# referencia debil al task, asi que sin este set el recolector puede matar la
# tarea a mitad de la consulta y el usuario nunca se llega a registrar.
_USER_SYNC_TASKS: set = set()


def _spawn_user_sync(discord_id: str, guild_id: str, username: str, display_name: str):
    """Lanza el auto-registro de usuario sin bloquear la interaccion."""

    async def _run():
        try:
            await async_get_or_create_user(
                discord_id,
                guild_id,
                username=username,
                display_name=display_name,
            )
        except Exception as error:
            # Solo se avisa: la interaccion ya esta responding y este sync es
            # best-effort, un fallo aqui no debe romperla.
            logger.debug("Auto-update user on interaction: %s", error)

    task = asyncio.create_task(_run())
    _USER_SYNC_TASKS.add(task)
    task.add_done_callback(_USER_SYNC_TASKS.discard)


def set_bot_task(task):
    """Compatibilidad con versiones que importan set_bot_task desde bot.events"""
    try:
        from keep_alive import set_bot_task as _set_bot_task
        _set_bot_task(task)
    except Exception:
        pass

async def publish_command_catalog(bot, message):
    """Publica el catalogo de Miami Systems si el mensaje lo pide.

    Se responde antes que a nada mas: el catalogo es la respuesta principal y la
    XP es secundaria. Un fallo aqui no debe impedir que `/help` siga siendo
    alcanzable, asi que cualquier error se registra y se sigue.
    """
    if bot.user is None:
        return
    if not wants_catalog(message.content, bot.user.id):
        return
    try:
        for embeds in build_catalog_messages():
            await message.channel.send(embed=embeds)
    except discord.HTTPException as error:
        logger.error("No se pudo publicar el catalogo de Miami Systems: %s", error)
    except Exception as error:
        logger.error("Fallo inesperado publicando el catalogo de Miami Systems: %s",
                     error, exc_info=True)

def set_bot(*args, **kwargs):
    """Compatibilidad con versiones que importan set_bot desde bot.events"""
    try:
        from keep_alive import set_bot as _set_bot
        _set_bot(*args, **kwargs)
    except Exception:
        pass


STATUS_ACTIVITIES = [
    (discord.ActivityType.watching, "Viendo la ciudad de Miami 🌴"),
    (discord.ActivityType.watching, "Caminando por las calles de Miami Beach 🏖️"),
    (discord.ActivityType.playing, "Patrullando de Policía en ER:LC 🚓"),
    (discord.ActivityType.watching, "Dirigiendo el tráfico en Ocean Drive 🚔"),
    (discord.ActivityType.watching, "Observando las cámaras de seguridad de Miami 📹"),
    (discord.ActivityType.playing, "patrullando con el MPD 🚨"),
    (discord.ActivityType.watching, "los reportes del 911 de Miami 🚨"),
    (discord.ActivityType.listening, "la radio policial del MPD & FHP 📻"),
    (discord.ActivityType.watching, "Viendo a los ciudadanos de Miami Vice RP 👥"),
    (discord.ActivityType.playing, "ER:LC Miami Vice Roleplay 🎮"),
    (discord.ActivityType.watching, "En operaciones del MDFR & EMS 🚒🚑"),
    (discord.ActivityType.watching, "Viendo patrullas de FHP en la autopista 🛣️"),
    (discord.ActivityType.watching, "Viva la seguridad en Miami Beach (MBPD) 🏖️"),
    (discord.ActivityType.watching, "Llendo a las subastas del Mercado Negro 💼"),
    (discord.ActivityType.watching, "Viendo el atardecer en South Beach 🌅"),
    (discord.ActivityType.watching, "Resolviendo casos de Florida Dept of Justice (FDOJ) ⚖️"),
    (discord.ActivityType.playing, "Made By Joshi | /help ✨"),
]

def setup_events(bot):
    @tasks.loop(seconds=35)
    async def rotate_presence():
        if not bot.is_ready():
            return
        idx = getattr(rotate_presence, "current_index", 0)
        act_type, act_name = STATUS_ACTIVITIES[idx % len(STATUS_ACTIVITIES)]
        rotate_presence.current_index = idx + 1
        try:
            activity = discord.Activity(type=act_type, name=act_name)
            await bot.change_presence(
                status=discord.Status.online,
                activity=activity
            )
        except Exception as e:
            logger.debug(f"Error rotando estado: {e}")

    @bot.event
    async def on_ready():
        bot.start_time = datetime.datetime.utcnow().timestamp()
        logger.info(f"Bot en línea: {bot.user} ({bot.user.id})")
        logger.info(f"Servidores: {len(bot.guilds)}")
        
        # Iniciar rotación de presencia dinámica (Viendo / Jugando / Escuchando)
        if not rotate_presence.is_running():
            rotate_presence.start()
        logger.info("🎭 Rotación dinámica de actividades iniciada (Made By Joshi)")

        try:
            synced = await bot.tree.sync()
            logger.info(f"Sincronizados {len(synced)} comandos slash")
        except Exception as e:
            logger.error(f"Error sincronizando comandos: {e}")

        # Sincronización de nombres de usuario en segundo plano y por lotes.
        # Antes se hacia miembro a miembro y en serie dentro de on_ready: con
        # un servidor grande eran cientos de UPDATE seguidos que bloqueaban el
        # arranque y saturaban el pool de conexiones.
        asyncio.create_task(_sync_member_names(bot))

    @bot.listen("on_interaction")
    async def on_interaction(interaction: discord.Interaction):
        # Auto-registro y actualización de username en cualquier interacción.
        # Esto va en segundo plano y NUNCA se espera: `await` aqui metia una
        # ida y vuelta a la base de datos delante del ACK de cada boton, select
        # y modal, y con la base lenta eso se comia los 3 segundos que Discord
        # concede para responder. Se lanza en una tarea aparte para que el evento
        # devuelva el control de inmediato.
        if interaction.user and interaction.guild and not interaction.user.bot:
            _spawn_user_sync(
                str(interaction.user.id),
                str(interaction.guild.id),
                interaction.user.name,
                interaction.user.display_name,
            )

        # Fallback de seguridad: si un botón de empresa llega y no ha sido respondido
        # por su vista (p. ej. tras reinicio del bot o vista caducada),
        # lo despacha directamente para asegurar respuesta inmediata y no superar los 3s.
        if interaction.type == discord.InteractionType.component:
            custom_id = interaction.data.get("custom_id", "")
            if custom_id.startswith("empresa:"):
                parts = custom_id.split(":")
                if len(parts) >= 3:
                    company_id, action = parts[1], parts[2]
                    async def _fallback_empresa():
                        await asyncio.sleep(0.3)
                        if not interaction.response.is_done():
                            try:
                                from bot.cogs.companies import handle_panel_button
                                await handle_panel_button(bot, interaction, company_id, action)
                            except Exception as ex:
                                logger.error("Error en fallback de boton de empresa %s: %s", custom_id, ex)
                    asyncio.create_task(_fallback_empresa())

    @bot.event
    async def on_message(message):
        if message.author.bot:
            return
        if not message.guild:
            return
        if is_spamming(str(message.author.id), str(message.guild.id)):
            return

        await publish_command_catalog(bot, message)
        
        xp_amount = random.randint(XP_PER_MESSAGE_MIN, XP_PER_MESSAGE_MAX)
        try:
            await async_get_or_create_user(
                str(message.author.id), 
                str(message.guild.id),
                username=message.author.name,
                display_name=message.author.display_name
            )
            await add_xp(str(message.author.id), str(message.guild.id), xp_amount, bot)
        except Exception as e:
            logger.error(f"XP error on message: {e}")

        await bot.process_commands(message)

    @bot.event
    async def on_guild_join(guild):
        logger.info(f"Joined guild: {guild.name} ({guild.id})")
        try:
            await async_get_or_create_guild_config(str(guild.id))
        except Exception as e:
            logger.error(f"Guild join setup error: {e}")

    @bot.tree.error
    async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        real_error = getattr(error, "original", error)
        cmd_name = interaction.command.name if interaction.command else "desconocido"
        logger.error(f"❌ Error capturado en Slash Command '/{cmd_name}': {real_error}", exc_info=True)
        from bot.embeds import error_embed
        err_msg = str(real_error) if str(real_error) else "Error interno de ejecución."
        try:
            embed = error_embed(
                "Error en la petición",
                f"Ocurrió un problema al procesar el comando: `{err_msg[:250]}`"
            )
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"No se pudo enviar notificación de error a Discord: {e}")

