import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncio

from bot.db import aexecute
from bot.helpers import async_get_or_create_user, format_currency
from bot.embeds import success_embed, error_embed, info_embed


async def fetch_roblox_user(identifier: str):
    """Fetches Roblox user data by username or ID using public Roblox APIs."""
    identifier = identifier.strip()
    user_data = None
    avatar_url = None

    async with aiohttp.ClientSession() as session:
        # Check if identifier is numeric (Roblox user ID)
        if identifier.isdigit():
            try:
                async with session.get(f"https://users.roblox.com/v1/users/{identifier}", timeout=5) as res:
                    if res.status == 200:
                        data = await res.json()
                        user_data = {
                            "id": str(data.get("id")),
                            "name": data.get("name"),
                            "displayName": data.get("displayName")
                        }
            except Exception:
                pass

        # If not found yet, search by username
        if not user_data:
            try:
                payload = {"usernames": [identifier], "excludeBannedUsers": False}
                async with session.post("https://users.roblox.com/v1/usernames/users", json=payload, timeout=5) as res:
                    if res.status == 200:
                        json_data = await res.json()
                        data_list = json_data.get("data", [])
                        if data_list:
                            u = data_list[0]
                            user_data = {
                                "id": str(u.get("id")),
                                "name": u.get("name"),
                                "displayName": u.get("displayName")
                            }
            except Exception:
                pass

        # If user data found, fetch avatar headshot
        if user_data:
            try:
                thumb_url = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_data['id']}&size=420x420&format=Png&isCircular=false"
                async with session.get(thumb_url, timeout=5) as res:
                    if res.status == 200:
                        thumb_json = await res.json()
                        tdata = thumb_json.get("data", [])
                        if tdata:
                            avatar_url = tdata[0].get("imageUrl")
            except Exception:
                pass

    if not user_data:
        # Fallback if Roblox API is unreachable
        clean_name = identifier.replace(" ", "_")
        user_data = {
            "id": None,
            "name": clean_name,
            "displayName": clean_name
        }

    return user_data, avatar_url


class Roblox(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    roblox_group = app_commands.Group(name="roblox", description="Integración y perfil de Roblox")

    @roblox_group.command(name="vincular", description="Vincular tu cuenta de Roblox con tu perfil de Discord")
    @app_commands.describe(usuario_roblox="Tu nombre de usuario o ID de Roblox")
    async def roblox_vincular(self, interaction: discord.Interaction, usuario_roblox: str):
        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)

        user_data, avatar_url = await fetch_roblox_user(usuario_roblox)
        r_name = user_data["name"]
        r_id = user_data.get("id")

        await async_get_or_create_user(uid, gid, username=interaction.user.name, display_name=interaction.user.display_name)

        await aexecute(
            "UPDATE users SET roblox_username=$1, roblox_id=$2, updated_at=NOW() WHERE discord_id=$3 AND guild_id=$4",
            (r_name, r_id, uid, gid)
        )

        # Update DNI record if exists
        await aexecute(
            "UPDATE dni_records SET roblox_username=$1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
            (r_name, uid, gid)
        )

        profile_url = f"https://www.roblox.com/users/{r_id}/profile" if r_id else f"https://www.roblox.com/search/users?keyword={r_name}"

        card = success_embed(
            "🎮 Cuenta de Roblox Vinculada",
            f"Has conectado exitosamente tu cuenta de Roblox con tu perfil de **Miami Vice RP**."
        )
        if avatar_url:
            card.set_thumbnail(url=avatar_url)

        card.add_field(name="🎮 Usuario de Roblox", value=f"[{r_name}]({profile_url})", inline=True)
        card.add_field(name="🏷️ Nombre Visible", value=user_data.get("displayName", r_name), inline=True)
        if r_id:
            card.add_field(name="🔢 ID de Roblox", value=f"`{r_id}`", inline=True)
        card.add_field(name="🔗 Perfil Oficial", value=f"[Abrir Perfil de Roblox]({profile_url})", inline=False)
        card.set_footer(text=f"Vinculado por: @{interaction.user.name}")

        await interaction.followup.send(embed=card, ephemeral=True)

    @roblox_group.command(name="perfil", description="Ver el perfil de Roblox y estadísticas de rol de un jugador")
    @app_commands.describe(usuario="Jugador a consultar (omite para ver el tuyo)")
    async def roblox_perfil(self, interaction: discord.Interaction, usuario: discord.Member = None):
        await interaction.response.defer()
        target = usuario or interaction.user
        gid = str(interaction.guild_id)
        uid = str(target.id)

        user_row = await aexecute(
            "SELECT * FROM users WHERE guild_id=$1 AND discord_id=$2",
            (gid, uid), fetch="one"
        ) or {}

        r_name = user_row.get("roblox_username")
        r_id = user_row.get("roblox_id")

        if not r_name:
            if target.id == interaction.user.id:
                await interaction.followup.send(embed=error_embed(
                    "Sin Cuenta Vinculada",
                    "No has vinculado tu cuenta de Roblox. Usa `/roblox vincular [usuario]` para conectarla."
                ), ephemeral=True)
            else:
                await interaction.followup.send(embed=error_embed(
                    "Sin Cuenta Vinculada",
                    f"{target.mention} no ha vinculado su cuenta de Roblox todavía."
                ), ephemeral=True)
            return

        # Fetch live Roblox info + avatar
        user_data, avatar_url = await fetch_roblox_user(r_id or r_name)

        # Fetch extra RP data
        dni = await aexecute("SELECT dni_number, full_name, status FROM dni_records WHERE guild_id=$1 AND discord_id=$2", (gid, uid), fetch="one")
        dept_m = await aexecute("SELECT dm.rank, d.name, d.acronym FROM department_members dm JOIN departments d ON d.id=dm.department_id WHERE dm.guild_id=$1 AND dm.discord_id=$2 LIMIT 1", (gid, uid), fetch="one")
        wpn_count = await aexecute("SELECT COUNT(*) as c FROM weapon_registries WHERE guild_id=$1 AND discord_id=$2 AND status='registered'", (gid, uid), fetch="one")

        profile_url = f"https://www.roblox.com/users/{r_id}/profile" if r_id else f"https://www.roblox.com/search/users?keyword={r_name}"

        card = info_embed(
            f"🎮 Perfil de Roblox — {r_name}",
            f"**Jugador:** {target.mention}\n**Roblox ID:** `{r_id or 'N/A'}`"
        )
        if avatar_url:
            card.set_thumbnail(url=avatar_url)
        else:
            card.set_thumbnail(url=target.display_avatar.url)

        card.add_field(name="🎮 Usuario", value=f"[{r_name}]({profile_url})", inline=True)
        card.add_field(name="🏷️ Display Name", value=user_data.get("displayName", r_name), inline=True)
        card.add_field(name="💵 Dinero Total", value=format_currency(user_row.get("cash", 0) + user_row.get("bank", 0)), inline=True)

        if dni:
            card.add_field(name="🪪 DNI Ciudadano", value=f"{dni['full_name']}\n`{dni['dni_number']}`", inline=True)
        else:
            card.add_field(name="🪪 DNI Ciudadano", value="*Sin DNI emitido*", inline=True)

        if dept_m:
            card.add_field(name="🏛️ Departamento", value=f"**{dept_m['acronym']}** — {dept_m['rank']}", inline=True)
        else:
            card.add_field(name="🏛️ Ocupación", value="Ciudadano Civil", inline=True)

        weapons_total = wpn_count.get("c", 0) if wpn_count else 0
        card.add_field(name="🔫 Armas Matriculadas", value=f"**{weapons_total}** registradas", inline=True)

        card.add_field(name="🔗 Enlace al Perfil", value=f"[Visitar perfil en Roblox.com]({profile_url})", inline=False)
        card.set_footer(text=f"Nivel {user_row.get('level', 1)} • XP: {user_row.get('xp', 0)}")

        await interaction.followup.send(embed=card)

    @roblox_group.command(name="desvincular", description="Desvincular tu cuenta de Roblox de este servidor")
    async def roblox_desvincular(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)

        await aexecute(
            "UPDATE users SET roblox_username=NULL, roblox_id=NULL, updated_at=NOW() WHERE discord_id=$1 AND guild_id=$2",
            (uid, gid)
        )
        await aexecute(
            "UPDATE dni_records SET roblox_username=NULL, updated_at=NOW() WHERE discord_id=$1 AND guild_id=$2",
            (uid, gid)
        )

        await interaction.followup.send(embed=success_embed(
            "Cuenta Desvinculada",
            "Tu cuenta de Roblox ha sido desvinculada exitosamente de tu usuario de Discord."
        ), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Roblox(bot))
