import discord
from discord import app_commands
from discord.ext import commands
import datetime
import math

from bot.db import aexecute
from bot.helpers import async_get_or_create_user, xp_for_level, calculate_level
from bot.embeds import success_embed, error_embed, info_embed

COOLDOWNS = {}
REP_COOLDOWNS = {}

def check_cooldown(key, seconds):
    now = datetime.datetime.utcnow().timestamp()
    last = COOLDOWNS.get(key, 0)
    remaining = (last + seconds) - now
    if remaining > 0:
        return remaining
    COOLDOWNS[key] = now
    return 0

def get_rep_rank(rep):
    if rep >= 1000:
        return "🌟 Leyenda"
    if rep >= 500:
        return "⭐ Estrella"
    if rep >= 200:
        return "🥇 Respetado"
    if rep >= 100:
        return "🥈 Conocido"
    if rep >= 50:
        return "🥉 Notable"
    if rep >= 0:
        return "😐 Neutral"
    if rep >= -50:
        return "😒 Sospechoso"
    if rep >= -100:
        return "😡 Temido"
    return "💀 Infame"

class Social(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    reputacion = app_commands.Group(name="reputacion", description="Sistema de reputación")

    @reputacion.command(name="dar", description="Dar reputación a otro jugador")
    @app_commands.describe(usuario="Usuario", tipo="Positivo o negativo")
    @app_commands.choices(tipo=[
        app_commands.Choice(name="👍 Positivo (+1)", value="positive"),
        app_commands.Choice(name="👎 Negativo (-1)", value="negative"),
    ])
    async def dar(self, interaction: discord.Interaction, usuario: discord.Member, tipo: str):
        await interaction.response.defer()
        if usuario.id == interaction.user.id:
            await interaction.followup.send(embed=error_embed("Error", "No puedes darte reputación a ti mismo"), ephemeral=True)
            return
        if usuario.bot:
            await interaction.followup.send(embed=error_embed("Error", "No puedes dar reputación a bots"), ephemeral=True)
            return
        cooldown_key = f"rep:{interaction.user.id}:{usuario.id}:{interaction.guild_id}"
        now = datetime.datetime.utcnow().timestamp()
        last_rep = REP_COOLDOWNS.get(cooldown_key, 0)
        if now - last_rep < 86400:
            remaining = 86400 - (now - last_rep)
            hrs = int(remaining // 3600)
            mins = int((remaining % 3600) // 60)
            await interaction.followup.send(embed=error_embed("Cooldown", f"Ya le diste reputación. Vuelve en **{hrs}h {mins}m**"), ephemeral=True)
            return
        REP_COOLDOWNS[cooldown_key] = now
        change = 1 if tipo == "positive" else -1
        await async_get_or_create_user(str(usuario.id), str(interaction.guild_id))
        await aexecute(
            "UPDATE users SET reputation=reputation+$1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
            (change, str(usuario.id), str(interaction.guild_id))
        )
        arrow = "⬆️" if change > 0 else "⬇️"
        await interaction.followup.send(embed=success_embed(
            f"{arrow} Reputación actualizada",
            f"{usuario.mention} recibió **{'+' if change>0 else ''}{change}** de reputación"
        ))

    @reputacion.command(name="perfil", description="Ver perfil de reputación")
    @app_commands.describe(usuario="Usuario (opcional)")
    async def perfil(self, interaction: discord.Interaction, usuario: discord.Member = None):
        await interaction.response.defer()
        target = usuario or interaction.user
        user = await async_get_or_create_user(str(target.id), str(interaction.guild_id))
        rep = user.get("reputation", 0) or 0
        rank = get_rep_rank(rep)
        e = info_embed(f"⭐ Reputación de {target.display_name}")
        e.set_thumbnail(url=target.display_avatar.url)
        e.add_field(name="Puntos", value=str(rep), inline=True)
        e.add_field(name="Rango", value=rank, inline=True)
        e.add_field(name="Nota", value=user.get("profile_note") or "Made By Joshi", inline=False)
        await interaction.followup.send(embed=e)

    @app_commands.command(name="nivel", description="Ver tu nivel y experiencia")
    @app_commands.describe(usuario="Usuario (opcional)")
    async def nivel(self, interaction: discord.Interaction, usuario: discord.Member = None):
        await interaction.response.defer()
        cd = check_cooldown(f"nivel:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        target = usuario or interaction.user
        user = await async_get_or_create_user(str(target.id), str(interaction.guild_id))
        level = user.get("level", 1) or 1
        xp = user.get("xp", 0) or 0
        current_level_xp = xp_for_level(level)
        next_level_xp = xp_for_level(level + 1)
        xp_in_level = xp - sum(xp_for_level(i) for i in range(1, level))
        xp_needed = next_level_xp - current_level_xp
        progress = min(1.0, xp_in_level / max(1, xp_needed))
        bar_length = 20
        filled = int(bar_length * progress)
        bar = "█" * filled + "░" * (bar_length - filled)
        e = info_embed(f"⭐ Nivel de {target.display_name}")
        e.set_thumbnail(url=target.display_avatar.url)
        e.add_field(name="Nivel", value=str(level), inline=True)
        e.add_field(name="XP Total", value=f"{xp:,}", inline=True)
        e.add_field(name="Progreso", value=f"`{bar}` {int(progress*100)}%", inline=False)
        e.add_field(name="XP para siguiente nivel", value=f"{int(xp_needed - xp_in_level):,} XP", inline=True)
        await interaction.followup.send(embed=e)


async def setup(bot):
    await bot.add_cog(Social(bot))
