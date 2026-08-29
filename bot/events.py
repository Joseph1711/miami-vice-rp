import discord
from discord import app_commands
from discord.ext import tasks
import logging
import datetime
import random

from bot.helpers import async_get_or_create_user, async_get_or_create_guild_config
from bot.services.levels import add_xp
from bot.middleware.antispam import is_spamming
from bot.config import XP_PER_MESSAGE_MIN, XP_PER_MESSAGE_MAX

logger = logging.getLogger("bot")

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

        # Sincronización en segundo plano de nombres de usuarios para servidores conocidos
        try:
            from bot.helpers import async_update_user_name
            for guild in bot.guilds:
                for member in guild.members:
                    if not member.bot:
                        await async_update_user_name(
                            str(member.id), 
                            str(guild.id), 
                            username=member.name, 
                            display_name=member.display_name
                        )
        except Exception as e:
            logger.debug(f"User sync notice: {e}")

    @bot.event
    async def on_interaction(interaction: discord.Interaction):
        # Auto-registro y actualización de username en cualquier interacción
        if interaction.user and interaction.guild and not interaction.user.bot:
            try:
                await async_get_or_create_user(
                    str(interaction.user.id),
                    str(interaction.guild.id),
                    username=interaction.user.name,
                    display_name=interaction.user.display_name
                )
            except Exception as e:
                logger.debug(f"Auto-update user on interaction: {e}")

    @bot.event
    async def on_message(message):
        if message.author.bot:
            return
        if not message.guild:
            return
        if is_spamming(str(message.author.id), str(message.guild.id)):
            return
        
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

