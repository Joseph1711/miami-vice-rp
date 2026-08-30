"""
Utilidades para responder rápido a Discord y procesar en background.
Previene el error "The application did not respond" en comandos lentos.
"""
import discord
from discord.ext import commands
import logging

logger = logging.getLogger("bot")


async def defer_with_timeout(interaction: discord.Interaction, timeout: int = 2):
    """
    Intenta defer inmediatamente. Si falla, usa followup.
    Esto previene el timeout de Discord (3 segundos).
    """
    try:
        await interaction.response.defer()
    except discord.errors.InteractionResponded:
        # Ya fue respondida
        pass
    except Exception as e:
        logger.warning(f"Error deferring interaction: {e}")


async def quick_reply(interaction: discord.Interaction, embed: discord.Embed = None, content: str = None, ephemeral: bool = False):
    """
    Responde INMEDIATAMENTE a Discord para evitar timeout.
    Funciona tanto en deferred como en non-deferred interactions.
    """
    try:
        if interaction.response.is_done():
            # Ya fue deferred o respondida, usa followup
            await interaction.followup.send(embed=embed, content=content, ephemeral=ephemeral)
        else:
            # Responde directamente
            await interaction.response.send_message(embed=embed, content=content, ephemeral=ephemeral)
    except discord.errors.InteractionResponded:
        # Ya fue respondida, usa followup
        await interaction.followup.send(embed=embed, content=content, ephemeral=ephemeral)
    except Exception as e:
        logger.error(f"Error sending quick reply: {e}")
        try:
            await interaction.followup.send(content="⚠️ Error enviando respuesta", ephemeral=True)
        except:
            pass
