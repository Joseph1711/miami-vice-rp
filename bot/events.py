import discord
from discord import app_commands
import logging
import datetime
import random

from bot.helpers import async_get_or_create_user, async_get_or_create_guild_config
from bot.services.levels import add_xp
from bot.middleware.antispam import is_spamming
from bot.config import XP_PER_MESSAGE_MIN, XP_PER_MESSAGE_MAX

logger = logging.getLogger("bot")

def setup_events(bot):
    @bot.event
    async def on_ready():
        bot.start_time = datetime.datetime.utcnow().timestamp()
        logger.info(f"Bot en línea: {bot.user} ({bot.user.id})")
        logger.info(f"Servidores: {len(bot.guilds)}")
        
        await bot.change_presence(
            status=discord.Status.online,
            activity=discord.Game(name="Made by Joshi"),
        )
        logger.info("🎭 Estado permanente configurado: Made by Joshi")

        try:
            synced = await bot.tree.sync()
            logger.info(f"Sincronizados {len(synced)} comandos slash")
        except Exception as e:
            logger.error(f"Error sincronizando comandos: {e}")

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
            await async_get_or_create_user(str(message.author.id), str(message.guild.id))
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

