import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging

from bot.helpers import check_admin_permission
from bot.embeds import success_embed, error_embed, info_embed, COLOR_PRIMARY
from bot.services.updates import (
    async_get_or_create_updates_config,
    async_save_updates_config,
    async_save_update_history,
    async_get_updates_history,
    async_is_update_duplicate,
    build_announcement_text,
    build_announcement_embed,
    fetch_github_commits,
    extract_real_changes_from_commits,
    DEFAULT_REPO
)

logger = logging.getLogger("bot.updates")


class ConfigureUpdateModal(discord.ui.Modal):
    def __init__(self, current_version: str = "v1.4.0", current_changes: str = "", current_desc: str = ""):
        super().__init__(title="Configurar Anuncio de Actualización")

        self.version = discord.ui.TextInput(
            label="Versión del Bot (ej. v1.4.0)",
            placeholder="v1.4.0",
            default=current_version or "v1.4.0",
            max_length=30,
            required=True
        )

        self.changes = discord.ui.TextInput(
            label="Lista de Cambios REALES (un cambio por línea)",
            placeholder="• Corrección en la conexión de base de datos\n• Nuevo comando /update\n• Mejoras de rendimiento en economía",
            default=current_changes or "",
            style=discord.TextStyle.paragraph,
            max_length=1500,
            required=True
        )

        self.description = discord.ui.TextInput(
            label="Descripción o Comentario Opcional",
            placeholder="Opcional: contexto adicional para el anuncio...",
            default=current_desc or "",
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=False
        )

        self.add_item(self.version)
        self.add_item(self.changes)
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)

        ver = self.version.value.strip()
        chg = self.changes.value.strip()
        desc = self.description.value.strip() or None
        today_str = datetime.datetime.utcnow().strftime("%d/%m/%Y")

        await async_save_updates_config(
            guild_id=gid,
            draft_version=ver,
            draft_changes=chg,
            draft_description=desc,
            draft_date=today_str
        )

        preview_text = build_announcement_text(ver, chg, today_str, desc)

        embed = success_embed(
            "Borrador de Actualización Guardado",
            f"Se ha guardado la versión `{ver}` con los cambios configurados.\n\n"
            f"💡 **Siguiente paso:** Usa `/update preview` para verificar cómo lo dirá el bot, o `/update publicar` para lanzarlo."
        )
        embed.add_field(name="Vista Rápida del Mensaje", value=f"```{preview_text[:900]}...```" if len(preview_text) > 900 else f"```{preview_text}```", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)


class UpdateActionButtons(discord.ui.View):
    def __init__(self, cog, guild_id: str, version: str, changes: str, date_str: str, desc: str = None):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.version = version
        self.changes = changes
        self.date_str = date_str
        self.desc = desc

    @discord.ui.button(label="📢 Publicar Ahora", style=discord.ButtonStyle.danger, emoji="🚀")
    async def publish_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin Permisos", "Solo el Staff autorizado puede publicar actualizaciones."), ephemeral=True)
            return

        success, result_msg = await self.cog._publish_update_internal(
            guild=interaction.guild,
            author=interaction.user,
            version_override=self.version,
            changes_override=self.changes,
            date_override=self.date_str,
            desc_override=self.desc,
            force=False
        )

        if success:
            button.disabled = True
            await interaction.followup.send(embed=success_embed("¡Actualización Publicada!", result_msg), ephemeral=True)
        else:
            await interaction.followup.send(embed=error_embed("No se pudo publicar", result_msg), ephemeral=True)

    @discord.ui.button(label="✏️ Reconfigurar", style=discord.ButtonStyle.secondary, emoji="⚙️")
    async def edit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ConfigureUpdateModal(
            current_version=self.version,
            current_changes=self.changes,
            current_desc=self.desc or ""
        )
        await interaction.response.send_modal(modal)


class Updates(commands.Cog):
    """Sistema de Anuncios y Control de Actualizaciones de Miami Vice RP con personalidad del bot."""

    update_group = app_commands.Group(
        name="update",
        description="Sistema de anuncios automáticos y configuración de actualizaciones del bot"
    )

    def __init__(self, bot):
        self.bot = bot

    async def _publish_update_internal(
        self,
        guild: discord.Guild,
        author: discord.User | discord.Member,
        channel_override: discord.TextChannel = None,
        version_override: str = None,
        changes_override: str = None,
        date_override: str = None,
        desc_override: str = None,
        source: str = "manual",
        commit_sha: str = None,
        force: bool = False
    ) -> tuple[bool, str]:
        """Lógica centralizada y segura de publicación de anuncios en Discord."""
        gid = str(guild.id)
        config = await async_get_or_create_updates_config(gid)

        channel_id = str(channel_override.id) if channel_override else config.get("channel_id")
        if not channel_id:
            return False, "No se ha configurado un canal de anuncios. Usa primero `/update canal #canal`."

        target_channel = guild.get_channel(int(channel_id))
        if not target_channel:
            try:
                target_channel = await self.bot.fetch_channel(int(channel_id))
            except Exception:
                target_channel = None

        if not target_channel:
            return False, f"El canal con ID `{channel_id}` no existe o el bot no tiene acceso a él."

        ver = version_override or config.get("draft_version") or "v1.4.0"
        chg = changes_override or config.get("draft_changes") or "• Optimizaciones y mejoras de estabilidad general"
        date_str = date_override or config.get("draft_date") or datetime.datetime.utcnow().strftime("%d/%m/%Y")
        desc = desc_override if desc_override is not None else config.get("draft_description")

        # Comprobación de duplicados para evitar spam accidental
        if not force:
            is_dup = await async_is_update_duplicate(gid, version=ver, commit_sha=commit_sha)
            if is_dup:
                return False, f"La versión `{ver}` o este commit ya fue publicado anteriormente. Si deseas forzar el reenvío, usa `/update publicar forzar:True`."

        # Construir mensaje con la personalidad auténtica del bot
        full_text = build_announcement_text(ver, chg, date_str, desc)
        embed = build_announcement_embed(ver, chg, date_str, desc)

        try:
            # Publicar mensaje en el canal configurado
            sent_msg = await target_channel.send(content=full_text)
            
            # Registrar en historial persistente
            await async_save_update_history(
                guild_id=gid,
                version=ver,
                title=f"Actualización {ver}",
                raw_message=full_text,
                changes=chg,
                source=source,
                commit_sha=commit_sha,
                channel_id=str(target_channel.id),
                message_id=str(sent_msg.id),
                published_by=str(author.id) if author else "SYSTEM/GITHUB"
            )

            # Si se publicó un commit de github, actualizar last_commit_sha
            if commit_sha:
                await async_save_updates_config(gid, last_commit_sha=commit_sha)

            return True, f"Anuncio de la versión `{ver}` publicado exitosamente en {target_channel.mention}."
        except discord.Forbidden:
            return False, f"El bot no tiene permisos para enviar mensajes en {target_channel.mention}."
        except Exception as e:
            logger.error(f"[Updates] Error al publicar anuncio: {e}", exc_info=True)
            return False, f"Error al enviar el mensaje al canal: `{e}`"

    # ==========================================
    # COMANDO 1: /update canal
    # ==========================================
    @update_group.command(name="canal", description="Configura el canal oficial donde el bot publicará los anuncios de actualización")
    @app_commands.describe(canal="Canal de texto donde se enviarán las actualizaciones")
    async def update_canal(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin Permisos", "Solo los administradores del servidor pueden configurar el canal de actualizaciones."), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        await async_save_updates_config(gid, channel_id=str(canal.id))

        embed = success_embed(
            "Canal de Actualizaciones Configurado",
            f"A partir de ahora, todos los anuncios de actualización del bot se publicarán en {canal.mention}.\n\n"
            f"📋 **Comandos recomendados:**\n"
            f"• `/update configurar`: Redactar los cambios reales.\n"
            f"• `/update preview`: Ver el anuncio con la personalidad del bot.\n"
            f"• `/update publicar`: Enviar el anuncio al canal."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ==========================================
    # COMANDO 2: /update configurar
    # ==========================================
    @update_group.command(name="configurar", description="Configura la versión y los cambios reales para el próximo anuncio")
    @app_commands.describe(
        version="Número o tag de versión (ej: v1.4.0)",
        cambios="Cambios reales realizados (separa con saltos de línea o comas)",
        descripcion="Descripción o contexto adicional opcional",
        fecha="Fecha de la actualización (opcional, por defecto fecha de hoy)"
    )
    async def update_configurar(
        self,
        interaction: discord.Interaction,
        version: str = None,
        cambios: str = None,
        descripcion: str = None,
        fecha: str = None
    ):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message(embed=error_embed("Sin Permisos", "Solo el Staff autorizado puede configurar actualizaciones."), ephemeral=True)
            return

        # Si no se pasan parámetros completos, abrir Modal interactivo
        if not version or not cambios:
            config = await async_get_or_create_updates_config(str(interaction.guild_id))
            modal = ConfigureUpdateModal(
                current_version=version or config.get("draft_version") or "v1.4.0",
                current_changes=cambios or config.get("draft_changes") or "",
                current_desc=descripcion or config.get("draft_description") or ""
            )
            await interaction.response.send_modal(modal)
            return

        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        today_str = fecha or datetime.datetime.utcnow().strftime("%d/%m/%Y")

        await async_save_updates_config(
            guild_id=gid,
            draft_version=version.strip(),
            draft_changes=cambios.strip(),
            draft_description=descripcion.strip() if descripcion else None,
            draft_date=today_str
        )

        preview_text = build_announcement_text(version, cambios, today_str, descripcion)

        embed = success_embed(
            "Borrador Configurado Exitosamente",
            f"Se ha preparado la actualización **{version}** con fecha `{today_str}`.\n\n"
            f"Usa `/update preview` para ver la redacción del bot o `/update publicar` para lanzarlo."
        )
        embed.add_field(
            name="Vista Previa de Texto",
            value=f"```{preview_text[:900]}...```" if len(preview_text) > 900 else f"```{preview_text}```",
            inline=False
        )

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ==========================================
    # COMANDO 3: /update preview
    # ==========================================
    @update_group.command(name="preview", description="Genera una vista previa del anuncio tal como lo dirá el bot con su personalidad")
    async def update_preview(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin Permisos", "Solo administradores pueden previsualizar anuncios."), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        config = await async_get_or_create_updates_config(gid)

        ver = config.get("draft_version") or "v1.4.0"
        chg = config.get("draft_changes") or "• Optimización general del código\n• Corrección de bugs en comandos de rol"
        desc = config.get("draft_description")
        date_str = config.get("draft_date") or datetime.datetime.utcnow().strftime("%d/%m/%Y")
        channel_id = config.get("channel_id")

        channel_mention = f"<#{channel_id}>" if channel_id else "⚠️ *No configurado (usa `/update canal`)*"

        raw_text = build_announcement_text(ver, chg, date_str, desc)

        header_embed = info_embed(
            "🔍 VISTA PREVIA DEL ANUNCIO DE ACTUALIZACIÓN",
            f"**Canal Destino:** {channel_mention}\n"
            f"**Versión:** `{ver}` | **Fecha:** `{date_str}`\n\n"
            f"El mensaje de abajo es exactamente el que publicará el bot cuando ejecutes `/update publicar`:"
        )

        view = UpdateActionButtons(self, gid, ver, chg, date_str, desc)

        await interaction.followup.send(embed=header_embed, ephemeral=True)
        await interaction.followup.send(content=raw_text, view=view, ephemeral=True)

    # ==========================================
    # COMANDO 4: /update publicar
    # ==========================================
    @update_group.command(name="publicar", description="Publica el anuncio de actualización en el canal configurado")
    @app_commands.describe(
        canal="Canal alternativo opcional para enviar este anuncio",
        forzar="Ignorar advertencia de versión duplicada si ya fue publicada"
    )
    async def update_publicar(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel = None,
        forzar: bool = False
    ):
        await interaction.response.defer(ephemeral=True)
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin Permisos", "Solo el Staff autorizado puede publicar actualizaciones."), ephemeral=True)
            return

        success, result_msg = await self._publish_update_internal(
            guild=interaction.guild,
            author=interaction.user,
            channel_override=canal,
            force=forzar
        )

        if success:
            await interaction.followup.send(embed=success_embed("¡Actualización Publicada con Éxito!", result_msg), ephemeral=True)
        else:
            await interaction.followup.send(embed=error_embed("No se pudo publicar la actualización", result_msg), ephemeral=True)

    # ==========================================
    # COMANDO 5: /update historial
    # ==========================================
    @update_group.command(name="historial", description="Muestra el historial de actualizaciones publicadas anteriormente")
    @app_commands.describe(limite="Cantidad de actualizaciones a consultar (1 a 10)")
    async def update_historial(self, interaction: discord.Interaction, limite: int = 5):
        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)

        history = await async_get_updates_history(gid, limit=limite)

        if not history:
            await interaction.followup.send(embed=info_embed(
                "📜 Historial de Actualizaciones",
                "Aún no se ha registrado ninguna actualización publicada en este servidor.\n"
                "Configura y publica una con `/update configurar` y `/update publicar`."
            ), ephemeral=True)
            return

        embed = info_embed(
            "📜 Historial de Actualizaciones Publicadas",
            f"Mostrando las últimas **{len(history)}** actualizaciones oficiales del bot:"
        )

        for item in history:
            v = item.get("version", "N/A")
            pub_date = item.get("published_at")
            date_str = str(pub_date)[:16] if pub_date else "Fecha desconocida"
            source = item.get("source", "manual").upper()
            changes_preview = item.get("changes", "Sin detalle").split("\n")[0][:100]
            author_id = item.get("published_by", "Staff")
            author_tag = f"<@{author_id}>" if author_id.isdigit() else author_id

            embed.add_field(
                name=f"📦 {v} • {date_str} [{source}]",
                value=f"**Publicado por:** {author_tag}\n**Cambios:** {changes_preview}",
                inline=False
            )

        embed.set_footer(text="Miami Vice RP Bot • Registro Oficial")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ==========================================
    # COMANDO 6: /update github_check
    # ==========================================
    @update_group.command(name="github_check", description="Detecta commits reales de GitHub y genera el anuncio sin inventar cambios")
    @app_commands.describe(
        repositorio="Repositorio de GitHub (por defecto Joseph1711/miami-vice-rp)",
        publicar_auto="Si es True, publica el anuncio inmediatamente si detecta cambios nuevos"
    )
    async def update_github_check(
        self,
        interaction: discord.Interaction,
        repositorio: str = None,
        publicar_auto: bool = False
    ):
        await interaction.response.defer(ephemeral=True)
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin Permisos", "Solo administradores pueden consultar el estado de GitHub."), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        config = await async_get_or_create_updates_config(gid)
        repo_name = repositorio or config.get("github_repo") or DEFAULT_REPO

        commits = await fetch_github_commits(repo=repo_name, limit=6)

        if not commits:
            await interaction.followup.send(embed=error_embed(
                "Error al Conectar con GitHub",
                f"No se pudieron obtener commits del repositorio `{repo_name}`. Verifica que el nombre sea correcto y sea público."
            ), ephemeral=True)
            return

        real_changes, latest_sha, commit_date = extract_real_changes_from_commits(commits)
        last_sha = config.get("last_commit_sha")

        short_sha = latest_sha[:7] if latest_sha else "latest"
        auto_version = f"v1.{len(commits)}.{short_sha}"

        if last_sha and last_sha == latest_sha:
            await interaction.followup.send(embed=info_embed(
                "🤖 Bot al Día (Sin Cambios Nuevos)",
                f"El bot ya tiene registrada la última versión de `{repo_name}` (Commit `{short_sha}`).\n\n"
                f"*«Nadie ha tocado una sola línea de código desde la última vez... dejen de molestar y pónganse a rolear. 💀»*"
            ), ephemeral=True)
            return

        # Formatear cambios
        changes_text = "\n".join([f"• {c}" for c in real_changes])
        today_str = commit_date or datetime.datetime.utcnow().strftime("%d/%m/%Y")

        # Guardar en borrador
        await async_save_updates_config(
            guild_id=gid,
            github_repo=repo_name,
            draft_version=auto_version,
            draft_changes=changes_text,
            draft_date=today_str
        )

        if publicar_auto:
            success, msg = await self._publish_update_internal(
                guild=interaction.guild,
                author=interaction.user,
                version_override=auto_version,
                changes_override=changes_text,
                date_override=today_str,
                source="github",
                commit_sha=latest_sha,
                force=False
            )
            if success:
                await interaction.followup.send(embed=success_embed("Actualización GitHub Publicada", msg), ephemeral=True)
            else:
                await interaction.followup.send(embed=error_embed("Error al Publicar", msg), ephemeral=True)
        else:
            raw_preview = build_announcement_text(auto_version, changes_text, today_str)
            embed = success_embed(
                "Nuevos Cambios Reales Detectados de GitHub",
                f"**Repositorio:** `{repo_name}`\n"
                f"**Último Commit:** `{short_sha}` ({today_str})\n"
                f"**Versión Asignada:** `{auto_version}`\n\n"
                f"Se han extraído **{len(real_changes)}** cambios reales del repositorio sin inventar nada."
            )
            embed.add_field(name="🔧 Cambios Detectados", value=changes_text[:1024], inline=False)
            
            view = UpdateActionButtons(self, gid, auto_version, changes_text, today_str)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    # ==========================================
    # COMANDO 7: /update github_config
    # ==========================================
    @update_group.command(name="github_config", description="Configura el monitoreo automático de GitHub para anuncios en tiempo real")
    @app_commands.describe(
        activar_auto="Activar o desactivar la detección automática periódica",
        repositorio="Repositorio oficial a monitorear (ej: Joseph1711/miami-vice-rp)"
    )
    async def update_github_config(
        self,
        interaction: discord.Interaction,
        activar_auto: bool,
        repositorio: str = None
    ):
        await interaction.response.defer(ephemeral=True)
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin Permisos", "Solo administradores pueden cambiar la configuración de GitHub."), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        repo_val = repositorio.strip() if repositorio else DEFAULT_REPO

        await async_save_updates_config(
            guild_id=gid,
            github_repo=repo_val,
            auto_github_enabled=activar_auto
        )

        status_text = "🟢 **ACTIVADO** (El bot verificará automáticamente nuevos commits cada 15 min)" if activar_auto else "🔴 **DESACTIVADO** (Solo mediante comando `/update github_check`)"

        embed = success_embed(
            "Configuración de GitHub Actualizada",
            f"**Monitoreo Automático:** {status_text}\n"
            f"**Repositorio:** `{repo_val}`\n\n"
            f"Asegúrate de tener configurado el canal de anuncios con `/update canal #canal`."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Updates(bot))
