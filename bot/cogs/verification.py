import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging
import json

from bot.db import aexecute
from bot.helpers import async_get_or_create_user, generate_id, check_admin_permission
from bot.embeds import success_embed, error_embed, info_embed
from bot.cogs.roblox import fetch_roblox_user

logger = logging.getLogger("bot.cogs.verification")


class VerifyModal(discord.ui.Modal, title="Verificación Oficial"):
    ign = discord.ui.TextInput(
        label="Nombre de Usuario de Roblox",
        placeholder="Ej: JuanPerez_RP (o tu nombre IC si no juegas Roblox)",
        max_length=64,
        required=True
    )
    age = discord.ui.TextInput(
        label="Edad (OOC / Fuera de Rol)",
        placeholder="Ej: 18",
        max_length=3,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)

        try:
            # Validar edad numérica
            try:
                age_val = int(self.age.value.strip())
                if age_val < 13:
                    await interaction.followup.send(
                        embed=error_embed("Edad Mínima Requerida", "Debes tener al menos 13 años para verificarte según las normativas de Discord."),
                        ephemeral=True
                    )
                    return
            except ValueError:
                await interaction.followup.send(
                    embed=error_embed("Edad Inválida", "Por favor ingresa un número válido para tu edad."),
                    ephemeral=True
                )
                return

            user = await async_get_or_create_user(uid, gid, username=interaction.user.name, display_name=interaction.user.display_name)
            
            # Obtener configuración de roles y canales
            config = await aexecute("SELECT * FROM verification_config WHERE guild_id=$1", (gid,), fetch="one") or {}
            
            # Verificar antigüedad mínima de cuenta si está configurada
            min_age_days = config.get("min_account_age_days", 0) or 0
            if min_age_days > 0:
                account_age = (datetime.datetime.utcnow() - interaction.user.created_at.replace(tzinfo=None)).days
                if account_age < min_age_days:
                    await interaction.followup.send(
                        embed=error_embed("Cuenta muy nueva", f"Tu cuenta de Discord debe tener al menos **{min_age_days} días** de antigüedad. La tuya tiene **{account_age} días**."),
                        ephemeral=True
                    )
                    return

            # Conexión automática con la API de Roblox
            roblox_raw = self.ign.value.strip()
            user_data, avatar_url = await fetch_roblox_user(roblox_raw)
            roblox_name = user_data.get("name") if user_data else roblox_raw
            roblox_id = user_data.get("id") if user_data else None

            # Actualizar datos del usuario
            await aexecute(
                """UPDATE users 
                   SET is_verified=true, roblox_username=$1, roblox_id=$2, updated_at=NOW() 
                   WHERE discord_id=$3 AND guild_id=$4""",
                (roblox_name, roblox_id, uid, gid)
            )

            # Si el usuario ya tiene DNIs creados, sincronizar el avatar y usuario de Roblox en ellos
            if avatar_url:
                await aexecute(
                    """UPDATE dni_records 
                       SET avatar_url=$1, roblox_username=$2, roblox_id=$3, updated_at=NOW() 
                       WHERE discord_id=$4 AND guild_id=$5 AND (avatar_url IS NULL OR avatar_url='')""",
                    (avatar_url, roblox_name, roblox_id, uid, gid)
                )

            # Guardar registro en verification_logs
            await aexecute(
                """INSERT INTO verification_logs (id, guild_id, discord_id, ign, age, created_at)
                   VALUES ($1,$2,$3,$4,$5,NOW())""",
                (generate_id(), gid, uid, roblox_name, str(age_val))
            )

            # Gestionar otorgamiento de uno o más roles
            roles_added_mentions = []
            roles_removed_mentions = []

            # 1. Roles a otorgar (roles_to_add y verified_role_id legado)
            add_role_ids = set()
            if config.get("roles_to_add"):
                for rid in config["roles_to_add"].split(","):
                    if rid.strip().isdigit():
                        add_role_ids.add(int(rid.strip()))
            if config.get("verified_role_id") and str(config["verified_role_id"]).isdigit():
                add_role_ids.add(int(config["verified_role_id"]))

            for rid in add_role_ids:
                role = interaction.guild.get_role(rid)
                if role and role not in interaction.user.roles:
                    try:
                        await interaction.user.add_roles(role, reason="Verificación oficial completada")
                        roles_added_mentions.append(role.mention)
                    except Exception as e:
                        logger.warning(f"No se pudo agregar rol {rid} a {interaction.user.id}: {e}")

            # 2. Roles a retirar (roles_to_remove)
            if config.get("roles_to_remove"):
                for rid in config["roles_to_remove"].split(","):
                    if rid.strip().isdigit():
                        role = interaction.guild.get_role(int(rid.strip()))
                        if role and role in interaction.user.roles:
                            try:
                                await interaction.user.remove_roles(role, reason="Retiro de roles tras verificación")
                                roles_removed_mentions.append(role.mention)
                            except Exception as e:
                                logger.warning(f"No se pudo remover rol {rid} a {interaction.user.id}: {e}")

            # Log al canal configurado
            log_channel_id = config.get("log_channel_id")
            if log_channel_id and str(log_channel_id).isdigit():
                log_channel = interaction.guild.get_channel(int(log_channel_id))
                if log_channel:
                    log_e = success_embed(
                        f"🛡️ Nuevo Usuario Verificado: {interaction.user.display_name}",
                        f"• **Discord:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                        f"• **Usuario Roblox:** `{roblox_name}` (ID: `{roblox_id or 'N/A'}`)\n"
                        f"• **Edad OOC:** `{age_val}` años"
                    )
                    if avatar_url:
                        log_e.set_thumbnail(url=avatar_url)
                    else:
                        log_e.set_thumbnail(url=interaction.user.display_avatar.url)
                    
                    if roles_added_mentions:
                        log_e.add_field(name="Roles Otorgados", value=" ".join(roles_added_mentions), inline=False)
                    if roles_removed_mentions:
                        log_e.add_field(name="Roles Retirados", value=" ".join(roles_removed_mentions), inline=False)
                    
                    try:
                        await log_channel.send(embed=log_e)
                    except Exception:
                        pass

            # Embed de respuesta al usuario
            resp_e = success_embed(
                "¡Verificación Exitosa!",
                f"Bienvenido/a a **{interaction.guild.name}**. Tu perfil ha sido autenticado y vinculado con éxito."
            )
            resp_e.add_field(name="🎮 Roblox Vinculado", value=f"**{roblox_name}**", inline=True)
            resp_e.add_field(name="🎂 Edad Declarada", value=f"{age_val} años", inline=True)
            if avatar_url:
                resp_e.set_thumbnail(url=avatar_url)
                resp_e.add_field(name="🖼️ Foto de Perfil Roblox", value="Sincronizada con tu DNI automáticamente", inline=False)
            
            if roles_added_mentions:
                resp_e.add_field(name="✅ Roles Otorgados", value=" ".join(roles_added_mentions), inline=False)
            if roles_removed_mentions:
                resp_e.add_field(name="❌ Roles Retirados", value=" ".join(roles_removed_mentions), inline=False)

            resp_e.set_footer(text="Miami Vice RP • Ya puedes tramitar tu DNI con /dni crear")
            await interaction.followup.send(embed=resp_e, ephemeral=True)

        except Exception as e:
            logger.error(f"Error en verificación: {e}", exc_info=True)
            await interaction.followup.send(
                embed=error_embed("Error de Verificación", f"Ocurrió un inconveniente: `{e}`"),
                ephemeral=True
            )


class VerifyButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verificarme", style=discord.ButtonStyle.success, emoji="✅", custom_id="verify_button_persistent")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(VerifyModal())


class Verification(commands.Cog, name="Verificación"):
    def __init__(self, bot):
        self.bot = bot

    verificar = app_commands.Group(name="verificar", description="Sistema y panel de verificación oficial")

    @verificar.command(name="panel", description="Publicar el panel interactivo de verificación en un canal")
    @app_commands.describe(
        canal="Canal donde se publicará el panel de verificación (omite para el canal actual)",
        titulo="Título del panel",
        descripcion="Descripción o instrucciones del panel"
    )
    async def panel(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel = None,
        titulo: str = "🛡️ Sistema de Verificación Oficial",
        descripcion: str = "¡Bienvenido/a a **Miami Vice RP**!\n\nPara acceder a los canales del servidor y comenzar tu experiencia de rol, presiona el botón **'Verificarme'** a continuación y completa tus datos."
    ):
        await interaction.response.defer(ephemeral=True)
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Necesitas permisos de administrador"), ephemeral=True)
            return

        target_channel = canal or interaction.channel
        
        embed = discord.Embed(
            title=titulo,
            description=descripcion,
            color=discord.Color.blue()
        )
        embed.set_image(url="https://images.unsplash.com/photo-1514565131-fce0801e5785?w=1200&auto=format&fit=crop&q=80")
        embed.set_footer(text=f"{interaction.guild.name} • Seguridad & Verificación", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)

        view = VerifyButton()
        await target_channel.send(embed=embed, view=view)
        await interaction.followup.send(embed=success_embed("Panel Publicado", f"El panel de verificación fue publicado exitosamente en {target_channel.mention}."), ephemeral=True)

    @verificar.command(name="configurar", description="Configurar los roles a otorgar, roles a retirar y canal de logs")
    @app_commands.describe(
        roles_otorgar="Roles a otorgar al verificarse (separados por comas o menciones)",
        roles_retirar="Roles a retirar al verificarse (ej: No Verificado, Invitado)",
        canal_logs="Canal de logs donde se notificarán las verificaciones",
        edad_minima_cuenta_dias="Días mínimos de antigüedad de la cuenta de Discord"
    )
    async def configurar(
        self,
        interaction: discord.Interaction,
        roles_otorgar: str = None,
        roles_retirar: str = None,
        canal_logs: discord.TextChannel = None,
        edad_minima_cuenta_dias: int = None
    ):
        await interaction.response.defer(ephemeral=True)
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Necesitas permisos de administrador"), ephemeral=True)
            return

        gid = str(interaction.guild_id)

        # Extraer IDs de roles a otorgar
        add_ids = []
        if roles_otorgar:
            # Buscar menciones <@&123> o números directos
            import re
            found = re.findall(r"\d+", roles_otorgar)
            for rid in found:
                r = interaction.guild.get_role(int(rid))
                if r:
                    add_ids.append(str(r.id))
        
        # Extraer IDs de roles a retirar
        remove_ids = []
        if roles_retirar:
            import re
            found = re.findall(r"\d+", roles_retirar)
            for rid in found:
                r = interaction.guild.get_role(int(rid))
                if r:
                    remove_ids.append(str(r.id))

        existing = await aexecute("SELECT * FROM verification_config WHERE guild_id=$1", (gid,), fetch="one")
        
        roles_to_add_str = ",".join(add_ids) if add_ids else (existing.get("roles_to_add") if existing else None)
        roles_to_remove_str = ",".join(remove_ids) if remove_ids else (existing.get("roles_to_remove") if existing else None)
        log_chan_str = str(canal_logs.id) if canal_logs else (existing.get("log_channel_id") if existing else None)
        min_age = edad_minima_cuenta_dias if edad_minima_cuenta_dias is not None else (existing.get("min_account_age_days", 0) if existing else 0)

        # Mantener verified_role_id legado apuntando al primer rol de add_ids si existe
        first_role = add_ids[0] if add_ids else (existing.get("verified_role_id") if existing else None)

        if existing:
            await aexecute(
                """UPDATE verification_config 
                   SET roles_to_add=$1, roles_to_remove=$2, log_channel_id=$3, min_account_age_days=$4, verified_role_id=$5, updated_at=NOW()
                   WHERE guild_id=$6""",
                (roles_to_add_str, roles_to_remove_str, log_chan_str, min_age, first_role, gid)
            )
        else:
            await aexecute(
                """INSERT INTO verification_config (id, guild_id, roles_to_add, roles_to_remove, log_channel_id, min_account_age_days, verified_role_id, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW())""",
                (generate_id(), gid, roles_to_add_str, roles_to_remove_str, log_chan_str, min_age, first_role)
            )

        e = success_embed("Configuración de Verificación Guardada", "Los ajustes han sido actualizados exitosamente.")
        
        if roles_to_add_str:
            r_mentions = [f"<@&{r}>" for r in roles_to_add_str.split(",") if r.isdigit()]
            e.add_field(name="Roles a Otorgar", value=" ".join(r_mentions) or "Ninguno", inline=False)
        if roles_to_remove_str:
            r_mentions = [f"<@&{r}>" for r in roles_to_remove_str.split(",") if r.isdigit()]
            e.add_field(name="Roles a Retirar", value=" ".join(r_mentions) or "Ninguno", inline=False)
        if log_chan_str:
            e.add_field(name="Canal de Logs", value=f"<#{log_chan_str}>", inline=True)
        e.add_field(name="Antigüedad Mínima de Cuenta", value=f"{min_age} días", inline=True)

        await interaction.followup.send(embed=e, ephemeral=True)

    @verificar.command(name="estado", description="Ver tu estado de verificación o el de otro ciudadano")
    @app_commands.describe(usuario="Usuario a consultar (omite para ver el tuyo)")
    async def estado(self, interaction: discord.Interaction, usuario: discord.Member = None):
        await interaction.response.defer()
        target = usuario or interaction.user
        gid = str(interaction.guild_id)
        uid = str(target.id)

        user = await async_get_or_create_user(uid, gid, username=target.name, display_name=target.display_name)
        log = await aexecute(
            "SELECT * FROM verification_logs WHERE guild_id=$1 AND discord_id=$2 ORDER BY created_at DESC LIMIT 1",
            (gid, uid), fetch="one"
        )

        if user.get("is_verified"):
            e = success_embed(f"✅ {target.display_name} está Verificado")
            e.set_thumbnail(url=target.display_avatar.url)
            e.add_field(name="🎮 Usuario Roblox", value=user.get("roblox_username") or (log.get("ign") if log else "No registrado"), inline=True)
            if log and log.get("age"):
                e.add_field(name="🎂 Edad Declarada", value=f"{log['age']} años", inline=True)
            e.add_field(name="📅 Fecha de Registro", value=str(user.get("created_at", ""))[:10] or "N/A", inline=True)
        else:
            e = error_embed(f"❌ {target.display_name} no está Verificado", "Usa el panel de verificación del servidor para autenticarte.")

        await interaction.followup.send(embed=e, ephemeral=True)

    @verificar.command(name="revocar", description="Revocar la verificación de un usuario (Admin)")
    @app_commands.describe(usuario="Usuario a revocar", motivo="Motivo de la revocación")
    async def revocar(self, interaction: discord.Interaction, usuario: discord.Member, motivo: str = "Revocación administrativa"):
        await interaction.response.defer()
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        uid = str(usuario.id)

        await aexecute(
            "UPDATE users SET is_verified=false, updated_at=NOW() WHERE discord_id=$1 AND guild_id=$2",
            (uid, gid)
        )

        config = await aexecute("SELECT * FROM verification_config WHERE guild_id=$1", (gid,), fetch="one") or {}
        
        # Retirar roles otorgados
        add_role_ids = set()
        if config.get("roles_to_add"):
            for rid in config["roles_to_add"].split(","):
                if rid.strip().isdigit():
                    add_role_ids.add(int(rid.strip()))
        if config.get("verified_role_id") and str(config["verified_role_id"]).isdigit():
            add_role_ids.add(int(config["verified_role_id"]))

        for rid in add_role_ids:
            role = interaction.guild.get_role(rid)
            if role and role in usuario.roles:
                try:
                    await usuario.remove_roles(role, reason=f"Verificación revocada: {motivo}")
                except Exception:
                    pass

        await interaction.followup.send(
            embed=success_embed("Verificación Revocada", f"La verificación de {usuario.mention} ha sido revocada.\n**Motivo:** {motivo}"),
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Verification(bot))
