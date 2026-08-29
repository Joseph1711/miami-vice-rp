import discord
from discord import app_commands
from discord.ext import commands
import datetime

from bot.db import aexecute
from bot.helpers import async_get_or_create_user, generate_id
from bot.embeds import success_embed, error_embed, info_embed

class VerifyModal(discord.ui.Modal, title="Verificación de Cuenta"):
    ign = discord.ui.TextInput(label="Nombre en el juego (IGN)", placeholder="Tu nombre de personaje...", max_length=64)
    age = discord.ui.TextInput(label="Edad", placeholder="Tu edad...", max_length=3)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user = await async_get_or_create_user(str(interaction.user.id), str(interaction.guild_id))
        if user.get("is_verified"):
            await interaction.followup.send(embed=error_embed("Ya verificado", "Tu cuenta ya está verificada"), ephemeral=True)
            return
        config = await aexecute("SELECT * FROM verification_config WHERE guild_id=$1", (str(interaction.guild_id),), fetch="one")
        min_age_days = config.get("min_account_age_days", 7) if config else 7
        account_age = (datetime.datetime.utcnow() - interaction.user.created_at.replace(tzinfo=None)).days
        if account_age < min_age_days:
            await interaction.followup.send(
                embed=error_embed("Cuenta muy nueva", f"Tu cuenta de Discord debe tener al menos **{min_age_days} días**. La tuya tiene **{account_age} días**."),
                ephemeral=True
            )
            return
        await aexecute(
            "UPDATE users SET is_verified=true, updated_at=NOW() WHERE discord_id=$1 AND guild_id=$2",
            (str(interaction.user.id), str(interaction.guild_id))
        )
        await aexecute(
            """INSERT INTO verification_logs (id, guild_id, discord_id, ign, age, created_at)
               VALUES ($1,$2,$3,$4,$5,NOW())""",
            (generate_id(), str(interaction.guild_id), str(interaction.user.id), self.ign.value, self.age.value)
        )
        if config and config.get("verified_role_id"):
            role = interaction.guild.get_role(int(config["verified_role_id"]))
            if role:
                try:
                    await interaction.user.add_roles(role, reason="Verificación aprobada")
                except Exception:
                    pass
        if config and config.get("log_channel_id"):
            log_channel = interaction.guild.get_channel(int(config["log_channel_id"]))
            if log_channel:
                log_e = success_embed(f"✅ {interaction.user.display_name} verificado", f"IGN: **{self.ign.value}** | Edad: **{self.age.value}** | Cuenta: **{account_age} días**")
                log_e.set_thumbnail(url=interaction.user.display_avatar.url)
                try:
                    await log_channel.send(embed=log_e)
                except Exception:
                    pass
        await interaction.followup.send(embed=success_embed("¡Verificado!", f"Bienvenido, **{self.ign.value}** 🎉"), ephemeral=True)

class VerifyButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ Verificarme", style=discord.ButtonStyle.success, custom_id="verify_button")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(VerifyModal())

class Verification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    verificar = app_commands.Group(name="verificar", description="Sistema de verificación")

    @verificar.command(name="panel", description="Crear el panel de verificación (admin)")
    @app_commands.describe(titulo="Título del panel", descripcion="Descripción")
    async def panel(self, interaction: discord.Interaction, titulo: str = "✅ Verificación", descripcion: str = "Haz clic para verificar tu cuenta en el servidor"):
        await interaction.response.defer()
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(embed=error_embed("Sin permisos", "Necesitas permisos de administrador"), ephemeral=True)
            return
        e = info_embed(titulo, descripcion)
        view = VerifyButton()
        await interaction.channel.send(embed=e, view=view)
        await interaction.followup.send(embed=success_embed("Panel creado", "El panel de verificación fue publicado"), ephemeral=True)

    @verificar.command(name="estado", description="Ver tu estado de verificación")
    async def estado(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user = await async_get_or_create_user(str(interaction.user.id), str(interaction.guild_id))
        if user.get("is_verified"):
            await interaction.followup.send(embed=success_embed("Verificado ✅", "Tu cuenta está verificada en este servidor"), ephemeral=True)
        else:
            await interaction.followup.send(embed=error_embed("No verificado", "Tu cuenta aún no está verificada. Usa `/verificar panel` o el panel de verificación."), ephemeral=True)

    @verificar.command(name="usuario", description="Ver el estado de verificación de otro usuario (admin)")
    @app_commands.describe(usuario="Usuario a verificar")
    async def usuario_estado(self, interaction: discord.Interaction, usuario: discord.Member):
        await interaction.response.defer()
        if not interaction.user.guild_permissions.manage_roles and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(embed=error_embed("Sin permisos", "Necesitas permisos de gestión de roles"), ephemeral=True)
            return
        user = await async_get_or_create_user(str(usuario.id), str(interaction.guild_id))
        log = await aexecute(
            "SELECT * FROM verification_logs WHERE guild_id=$1 AND discord_id=$2 ORDER BY created_at DESC LIMIT 1",
            (str(interaction.guild_id), str(usuario.id)), fetch="one"
        )
        if user.get("is_verified"):
            e = success_embed(f"✅ {usuario.display_name} está verificado")
            if log:
                e.add_field(name="IGN", value=log.get("ign","N/A"), inline=True)
                e.add_field(name="Edad declarada", value=log.get("age","N/A"), inline=True)
        else:
            e = error_embed(f"❌ {usuario.display_name} no está verificado")
        await interaction.followup.send(embed=e, ephemeral=True)

    @verificar.command(name="revocar", description="Revocar la verificación de un usuario (admin)")
    @app_commands.describe(usuario="Usuario a revocar")
    async def revocar(self, interaction: discord.Interaction, usuario: discord.Member):
        await interaction.response.defer()
        if not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return
        await aexecute(
            "UPDATE users SET is_verified=false, updated_at=NOW() WHERE discord_id=$1 AND guild_id=$2",
            (str(usuario.id), str(interaction.guild_id))
        )
        config = await aexecute("SELECT * FROM verification_config WHERE guild_id=$1", (str(interaction.guild_id),), fetch="one")
        if config and config.get("verified_role_id"):
            role = interaction.guild.get_role(int(config["verified_role_id"]))
            if role:
                try:
                    await usuario.remove_roles(role, reason="Verificación revocada")
                except Exception:
                    pass
        await interaction.followup.send(embed=success_embed("Verificación revocada", f"La verificación de {usuario.mention} fue revocada"), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Verification(bot))
