import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging
import re

from bot.db import aexecute
from bot.helpers import async_get_or_create_user, generate_id, check_admin_permission
from bot.embeds import success_embed, error_embed, info_embed
from bot.cogs.roblox import fetch_roblox_user

logger = logging.getLogger("bot.cogs.verification")


def parse_roles_from_string(guild: discord.Guild, input_str: str) -> list[discord.Role]:
    """Extrae roles de Discord a partir de menciones, IDs o nombres separados por comas/espacios."""
    if not input_str:
        return []
    
    roles = []
    # 1. Extraer por IDs o menciones <@&123456789>
    ids = re.findall(r"\d{17,21}", input_str)
    for rid in ids:
        r = guild.get_role(int(rid))
        if r and r not in roles:
            roles.append(r)

    # 2. Extraer por nombre del rol (separado por comas, saltos de línea o punto y coma)
    tokens = [t.strip().lstrip("@") for t in re.split(r"[,;\n]+", input_str) if t.strip()]
    for token in tokens:
        if not token:
            continue
        if any(token.lower() == r.name.lower() for r in roles):
            continue
        for r in guild.roles:
            if r.name.lower() == token.lower() and r not in roles:
                roles.append(r)
                break

    return roles


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

            # GESTIONAR OTORGAMIENTO DE UNO O MÚLTIPLES ROLES
            roles_added_mentions = []
            roles_removed_mentions = []

            # 1. Coleccionar todos los roles a otorgar
            add_role_ids = set()
            if config.get("roles_to_add"):
                for rid in str(config["roles_to_add"]).split(","):
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
                        logger.warning(f"No se pudo agregar rol {role.name} ({rid}) a {interaction.user.id}: {e}")

            # 2. Coleccionar y retirar roles configurados (ej: No Verificado)
            if config.get("roles_to_remove"):
                for rid in str(config["roles_to_remove"]).split(","):
                    if rid.strip().isdigit():
                        role = interaction.guild.get_role(int(rid.strip()))
                        if role and role in interaction.user.roles:
                            try:
                                await interaction.user.remove_roles(role, reason="Retiro de rol por verificación completada")
                                roles_removed_mentions.append(role.mention)
                            except Exception as e:
                                logger.warning(f"No se pudo remover rol {role.name} ({rid}) a {interaction.user.id}: {e}")

            # 3. Notificación al canal de logs si está configurado
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
                    except Exception as err:
                        logger.warning(f"Error al enviar log de verificación: {err}")

            # 4. Respuesta al usuario que se verificó
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
            elif add_role_ids:
                resp_e.add_field(name="ℹ️ Roles Asignados", value="Ya tenías los roles otorgados o fueron procesados.", inline=False)
            
            if roles_removed_mentions:
                resp_e.add_field(name="❌ Roles Retirados", value=" ".join(roles_removed_mentions), inline=False)

            resp_e.set_footer(text="Miami Vice RP • Ya puedes tramitar tu DNI con /dni crear")
            await interaction.followup.send(embed=resp_e, ephemeral=True)

        except Exception as e:
            logger.error(f"Error en verificación: {e}", exc_info=True)
            await interaction.followup.send(
                embed=error_embed("Error de Verificación", f"Ocurrió un inconveniente al procesar tu verificación: `{e}`"),
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

    verificar = app_commands.Group(name="verificar", description="Sistema y panel de verificación oficial multi-rol")

    @verificar.command(name="panel", description="Publicar el panel interactivo de verificación en un canal")
    @app_commands.describe(
        canal="Canal donde se publicará el panel de verificación (omite para el canal actual)",
        roles_otorgar="Uno o más roles a otorgar al verificarse (menciones o nombres separados por coma)",
        roles_retirar="Uno o más roles a retirar al verificarse (ej: @NoVerificado)",
        canal_logs="Canal donde se enviarán los registros de verificación",
        titulo="Título del panel",
        descripcion="Descripción o instrucciones del panel"
    )
    async def panel(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel = None,
        roles_otorgar: str = None,
        roles_retirar: str = None,
        canal_logs: discord.TextChannel = None,
        titulo: str = "🛡️ Sistema de Verificación Oficial",
        descripcion: str = "¡Bienvenido/a a **Miami Vice RP**!\n\nPara acceder a los canales del servidor y comenzar tu experiencia de rol, presiona el botón **'Verificarme'** a continuación y completa tus datos."
    ):
        await interaction.response.defer(ephemeral=True)
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Necesitas permisos de administrador"), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        target_channel = canal or interaction.channel

        # Si se especificaron roles o canal de logs en el comando del panel, actualizar configuración
        if roles_otorgar or roles_retirar or canal_logs:
            existing = await aexecute("SELECT * FROM verification_config WHERE guild_id=$1", (gid,), fetch="one")
            
            add_roles = parse_roles_from_string(interaction.guild, roles_otorgar) if roles_otorgar else []
            remove_roles = parse_roles_from_string(interaction.guild, roles_retirar) if roles_retirar else []

            roles_to_add_str = ",".join(str(r.id) for r in add_roles) if add_roles else (existing.get("roles_to_add") if existing else None)
            roles_to_remove_str = ",".join(str(r.id) for r in remove_roles) if remove_roles else (existing.get("roles_to_remove") if existing else None)
            log_chan_str = str(canal_logs.id) if canal_logs else (existing.get("log_channel_id") if existing else None)
            first_role = str(add_roles[0].id) if add_roles else (existing.get("verified_role_id") if existing else None)

            if existing:
                await aexecute(
                    """UPDATE verification_config 
                       SET roles_to_add=$1, roles_to_remove=$2, log_channel_id=$3, verified_role_id=$4, updated_at=NOW()
                       WHERE guild_id=$5""",
                    (roles_to_add_str, roles_to_remove_str, log_chan_str, first_role, gid)
                )
            else:
                await aexecute(
                    """INSERT INTO verification_config (id, guild_id, roles_to_add, roles_to_remove, log_channel_id, min_account_age_days, verified_role_id, created_at, updated_at)
                       VALUES ($1, $2, $3, $4, $5, 0, $6, NOW(), NOW())""",
                    (generate_id(), gid, roles_to_add_str, roles_to_remove_str, log_chan_str, first_role)
                )

        # Consultar roles configurados para mostrarlos en el embed
        config = await aexecute("SELECT * FROM verification_config WHERE guild_id=$1", (gid,), fetch="one") or {}
        roles_text = []
        if config.get("roles_to_add"):
            for rid in str(config["roles_to_add"]).split(","):
                if rid.strip().isdigit():
                    roles_text.append(f"<@&{rid.strip()}>")

        embed = discord.Embed(
            title=titulo,
            description=descripcion,
            color=discord.Color.blue()
        )
        embed.set_image(url="https://images.unsplash.com/photo-1514565131-fce0801e5785?w=1200&auto=format&fit=crop&q=80")
        if roles_text:
            embed.add_field(name="🎁 Roles que recibirás", value=" ".join(roles_text), inline=False)
        embed.set_footer(text=f"{interaction.guild.name} • Seguridad & Verificación", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)

        view = VerifyButton()
        await target_channel.send(embed=embed, view=view)

        resp = success_embed("Panel de Verificación Publicado", f"El panel fue publicado exitosamente en {target_channel.mention}.")
        if roles_text:
            resp.add_field(name="Roles Asignados", value=" ".join(roles_text), inline=False)
        await interaction.followup.send(embed=resp, ephemeral=True)

    @verificar.command(name="configurar", description="Configurar uno o múltiples roles a otorgar, roles a retirar y canal de logs")
    @app_commands.describe(
        roles_otorgar="Uno o más roles a otorgar (ej: @Ciudadano, @Verificado, @Miembro)",
        roles_retirar="Uno o más roles a retirar tras verificarse (ej: @NoVerificado)",
        canal_logs="Canal de logs donde se notificarán las verificaciones",
        edad_minima_cuenta_dias="Días mínimos de antigüedad de la cuenta de Discord (0 para desactivar)"
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

        # Extraer roles a otorgar
        add_roles = parse_roles_from_string(interaction.guild, roles_otorgar) if roles_otorgar else []
        add_ids = [str(r.id) for r in add_roles]
        
        # Extraer roles a retirar
        remove_roles = parse_roles_from_string(interaction.guild, roles_retirar) if roles_retirar else []
        remove_ids = [str(r.id) for r in remove_roles]

        existing = await aexecute("SELECT * FROM verification_config WHERE guild_id=$1", (gid,), fetch="one")
        
        roles_to_add_str = ",".join(add_ids) if add_ids else (existing.get("roles_to_add") if existing else None)
        roles_to_remove_str = ",".join(remove_ids) if remove_ids else (existing.get("roles_to_remove") if existing else None)
        log_chan_str = str(canal_logs.id) if canal_logs else (existing.get("log_channel_id") if existing else None)
        min_age = edad_minima_cuenta_dias if edad_minima_cuenta_dias is not None else (existing.get("min_account_age_days", 0) if existing else 0)
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

        e = success_embed("Configuración de Verificación Guardada", "Los ajustes multi-rol han sido actualizados exitosamente.")
        
        if roles_to_add_str:
            r_mentions = [f"<@&{r}>" for r in roles_to_add_str.split(",") if r.isdigit()]
            e.add_field(name="✅ Roles a Otorgar", value=" ".join(r_mentions) if r_mentions else "Ninguno", inline=False)
        else:
            e.add_field(name="✅ Roles a Otorgar", value="*Ninguno configurado*", inline=False)

        if roles_to_remove_str:
            r_mentions = [f"<@&{r}>" for r in roles_to_remove_str.split(",") if r.isdigit()]
            e.add_field(name="❌ Roles a Retirar", value=" ".join(r_mentions) if r_mentions else "Ninguno", inline=False)

        if log_chan_str:
            e.add_field(name="📋 Canal de Logs", value=f"<#{log_chan_str}>", inline=True)
        e.add_field(name="⏳ Antigüedad Mínima", value=f"{min_age} días", inline=True)

        await interaction.followup.send(embed=e, ephemeral=True)

    @verificar.command(name="agregar_rol", description="Añadir un rol adicional a la lista de roles otorgados en la verificación")
    @app_commands.describe(rol="Rol de Discord a añadir a la verificación")
    async def agregar_rol(self, interaction: discord.Interaction, rol: discord.Role):
        await interaction.response.defer(ephemeral=True)
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Necesitas permisos de administrador"), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        existing = await aexecute("SELECT * FROM verification_config WHERE guild_id=$1", (gid,), fetch="one")

        current_roles = set()
        if existing and existing.get("roles_to_add"):
            for r in str(existing["roles_to_add"]).split(","):
                if r.strip().isdigit():
                    current_roles.add(r.strip())
        if existing and existing.get("verified_role_id") and str(existing["verified_role_id"]).isdigit():
            current_roles.add(str(existing["verified_role_id"]))

        current_roles.add(str(rol.id))
        new_roles_str = ",".join(current_roles)

        if existing:
            await aexecute("UPDATE verification_config SET roles_to_add=$1, updated_at=NOW() WHERE guild_id=$2", (new_roles_str, gid))
        else:
            await aexecute(
                """INSERT INTO verification_config (id, guild_id, roles_to_add, verified_role_id, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, NOW(), NOW())""",
                (generate_id(), gid, new_roles_str, str(rol.id))
            )

        mentions = [f"<@&{rid}>" for rid in current_roles]
        e = success_embed("Rol Añadido a la Verificación", f"El rol {rol.mention} fue agregado.\n\n**Lista completa de roles a otorgar:**\n" + " ".join(mentions))
        await interaction.followup.send(embed=e, ephemeral=True)

    @verificar.command(name="remover_rol", description="Quitar un rol de la lista de roles otorgados en la verificación")
    @app_commands.describe(rol="Rol de Discord a remover de la lista")
    async def remover_rol(self, interaction: discord.Interaction, rol: discord.Role):
        await interaction.response.defer(ephemeral=True)
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Necesitas permisos de administrador"), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        existing = await aexecute("SELECT * FROM verification_config WHERE guild_id=$1", (gid,), fetch="one")

        if not existing or not existing.get("roles_to_add"):
            await interaction.followup.send(embed=error_embed("Sin Configuración", "No hay roles configurados en este servidor."), ephemeral=True)
            return

        current_roles = set()
        for r in str(existing.get("roles_to_add", "")).split(","):
            if r.strip().isdigit() and r.strip() != str(rol.id):
                current_roles.add(r.strip())

        new_roles_str = ",".join(current_roles)
        await aexecute("UPDATE verification_config SET roles_to_add=$1, updated_at=NOW() WHERE guild_id=$2", (new_roles_str, gid))

        mentions = [f"<@&{rid}>" for rid in current_roles]
        e = success_embed("Rol Removido de la Verificación", f"El rol {rol.mention} ya no se otorgará al verificarse.\n\n**Roles restantes a otorgar:**\n" + (" ".join(mentions) if mentions else "*Ninguno*"))
        await interaction.followup.send(embed=e, ephemeral=True)

    @verificar.command(name="ver_config", description="Ver la configuración actual de roles y canales de verificación")
    async def ver_config(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Necesitas permisos de administrador"), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        config = await aexecute("SELECT * FROM verification_config WHERE guild_id=$1", (gid,), fetch="one") or {}

        e = info_embed("📋 Configuración Actual de Verificación", f"Servidor: **{interaction.guild.name}**")

        # Roles to add
        add_mentions = []
        if config.get("roles_to_add"):
            for rid in str(config["roles_to_add"]).split(","):
                if rid.strip().isdigit():
                    add_mentions.append(f"<@&{rid.strip()}>")
        if config.get("verified_role_id") and str(config["verified_role_id"]).isdigit():
            v_mention = f"<@&{config['verified_role_id']}>"
            if v_mention not in add_mentions:
                add_mentions.append(v_mention)

        e.add_field(name="✅ Roles a Otorgar", value=" ".join(add_mentions) if add_mentions else "*Ninguno configurado*", inline=False)

        # Roles to remove
        remove_mentions = []
        if config.get("roles_to_remove"):
            for rid in str(config["roles_to_remove"]).split(","):
                if rid.strip().isdigit():
                    remove_mentions.append(f"<@&{rid.strip()}>")
        e.add_field(name="❌ Roles a Retirar", value=" ".join(remove_mentions) if remove_mentions else "*Ninguno*", inline=False)

        # Log channel
        log_id = config.get("log_channel_id")
        e.add_field(name="📢 Canal de Logs", value=f"<#{log_id}>" if log_id and str(log_id).isdigit() else "*Sin canal de logs*", inline=True)
        
        # Min account age
        min_age = config.get("min_account_age_days", 0)
        e.add_field(name="⏳ Antigüedad Mínima", value=f"{min_age} días" if min_age else "Desactivada (0 días)", inline=True)

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
        
        # Retirar todos los roles otorgados
        add_role_ids = set()
        if config.get("roles_to_add"):
            for rid in str(config["roles_to_add"]).split(","):
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
