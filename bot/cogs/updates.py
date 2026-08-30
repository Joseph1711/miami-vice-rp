import discord
from discord import app_commands
from discord.ext import commands
import datetime
import json
import logging

from bot.db import aexecute
from bot.helpers import check_admin_permission, generate_id
from bot.embeds import success_embed, error_embed, info_embed, warning_embed
from bot.services.updates import (
    get_or_create_update_config,
    build_announcement_text,
    fetch_github_commits,
    is_commit_already_published,
    record_published_update,
    format_changes_list,
    DEFAULT_REPO
)

logger = logging.getLogger("bot.cogs.updates")


class ConfigureUpdateModal(discord.ui.Modal, title="⚙️ Configurar Anuncio de Actualización"):
    version = discord.ui.TextInput(
        label="Versión de la Actualización",
        placeholder="Ej: v1.5.0 o Parche 2026.08",
        min_length=2,
        max_length=50,
        required=True
    )
    changes = discord.ui.TextInput(
        label="Cambios Reales (Un cambio por línea)",
        style=discord.TextStyle.paragraph,
        placeholder="• Corrección en base de datos\n• Nuevo comando /update\n• Reparación del sistema DNI",
        min_length=5,
        max_length=1500,
        required=True
    )
    description = discord.ui.TextInput(
        label="Comentario Adicional (Opcional)",
        style=discord.TextStyle.short,
        placeholder="Ej: Parche de estabilidad y nuevas funciones",
        max_length=200,
        required=False
    )

    def __init__(self, current_version: str = "", current_changes: str = "", current_desc: str = ""):
        super().__init__()
        if current_version:
            self.version.default = current_version
        if current_changes:
            self.changes.default = current_changes
        if current_desc:
            self.description.default = current_desc

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)

        v_val = self.version.value.strip()
        c_val = self.changes.value.strip()
        d_val = self.description.value.strip() if self.description.value else ""

        await aexecute(
            """UPDATE update_config 
               SET draft_version=$1, draft_changes=$2, draft_description=$3, updated_at=NOW()
               WHERE guild_id=$4""",
            (v_val, c_val, d_val, gid)
        )

        preview_data = build_announcement_text(
            version=v_val,
            changes=c_val,
            description=d_val
        )

        resp_embed = success_embed(
            "Borrador de Actualización Guardado",
            f"Se ha guardado el borrador para la versión **{v_val}**.\n\n"
            f"Puedes ver la previsualización con `/update preview` y publicarlo con `/update publicar`."
        )
        resp_embed.add_field(name="👁️ Previsualización del Tono Sarcástico", value=preview_data["title"], inline=False)
        resp_embed.add_field(name="🔧 Cambios Registrados", value="\n".join(preview_data["changes"])[:800], inline=False)

        await interaction.followup.send(embed=resp_embed, ephemeral=True)


class Updates(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    update_group = app_commands.Group(
        name="update",
        description="Sistema de anuncios automáticos y manuales de actualizaciones del bot"
    )

    @update_group.command(name="canal", description="Configura el canal de Discord para publicar anuncios de actualizaciones")
    @app_commands.describe(
        canal="Canal de texto donde se publicarán los anuncios",
        auto_anunciar="Activar detección y publicación automática desde GitHub (True/False)",
        rol_mencion="Rol opcional para mencionar en cada anuncio"
    )
    async def update_canal(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        auto_anunciar: bool = True,
        rol_mencion: discord.Role = None
    ):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message(
                embed=error_embed("Sin Permiso", "Solo los administradores o miembros del Staff autorizados pueden configurar este sistema."),
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        cid = str(canal.id)
        mention_id = str(rol_mencion.id) if rol_mencion else None

        # Ensure row exists
        await get_or_create_update_config(gid)

        await aexecute(
            """UPDATE update_config 
               SET channel_id=$1, auto_announce=$2, mention_role_id=$3, updated_at=NOW()
               WHERE guild_id=$4""",
            (cid, auto_anunciar, mention_id, gid)
        )

        msg = (
            f"Los anuncios de actualizaciones se publicarán en {canal.mention}.\n"
            f"• **Detección Automática GitHub:** {'🟢 Activada' if auto_anunciar else '🔴 Desactivada'}\n"
        )
        if rol_mencion:
            msg += f"• **Mención de Rol:** {rol_mencion.mention}\n"
        else:
            msg += "• **Mención de Rol:** Ninguna (sin pings molestos)\n"

        await interaction.followup.send(embed=success_embed("Canal de Actualizaciones Configurado", msg), ephemeral=True)

    @update_group.command(name="configurar", description="Configura la información y cambios de una nueva actualización")
    @app_commands.describe(
        version="Número o nombre de la versión (ej: v1.5.0)",
        cambios="Lista de cambios separados por coma o punto y coma (o deja vacío para usar el formulario)",
        descripcion="Descripción o nota opcional"
    )
    async def update_configurar(
        self,
        interaction: discord.Interaction,
        version: str = None,
        cambios: str = None,
        descripcion: str = None
    ):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message(
                embed=error_embed("Sin Permiso", "No tienes permisos de administración para configurar actualizaciones."),
                ephemeral=True
            )
            return

        gid = str(interaction.guild_id)
        config = await get_or_create_update_config(gid)

        # If no inline args, open the nice interactive modal
        if not version or not cambios:
            modal = ConfigureUpdateModal(
                current_version=version or config.get("draft_version") or "v1.5.0",
                current_changes=cambios or config.get("draft_changes") or "",
                current_desc=descripcion or config.get("draft_description") or ""
            )
            await interaction.response.send_modal(modal)
            return

        await interaction.response.defer(ephemeral=True)

        # Parse inline changes
        parsed_changes = [c.strip() for c in cambios.replace(";", "\n").replace(",", "\n").split("\n") if c.strip()]
        changes_text = "\n".join(parsed_changes)

        await aexecute(
            """UPDATE update_config 
               SET draft_version=$1, draft_changes=$2, draft_description=$3, updated_at=NOW()
               WHERE guild_id=$4""",
            (version.strip(), changes_text, descripcion.strip() if descripcion else "", gid)
        )

        preview = build_announcement_text(version=version.strip(), changes=parsed_changes, description=descripcion)

        card = success_embed(
            "Actualización Configurada Exitosamente",
            f"Se ha guardado el borrador de la versión **{version}**.\n\n"
            f"**Previsualización del Anuncio con Tono del Bot:**\n\n"
            f"{preview['full_text']}"
        )
        await interaction.followup.send(embed=card, ephemeral=True)

    @update_group.command(name="preview", description="Muestra una previsualización del anuncio con la personalidad del bot")
    @app_commands.describe(version="Versión específica a previsualizar (opcional)")
    async def update_preview(self, interaction: discord.Interaction, version: str = None):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message(
                embed=error_embed("Sin Permiso", "No tienes permisos de administración."),
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        config = await get_or_create_update_config(gid)

        v_val = version or config.get("draft_version")
        changes_val = config.get("draft_changes")
        desc_val = config.get("draft_description")

        if not v_val or not changes_val:
            # Try fetching latest commit as sample
            commits = await fetch_github_commits(repo=config.get("github_repo") or DEFAULT_REPO, limit=3)
            if commits:
                v_val = v_val or f"v1.0 (Commit {commits[0]['short_sha']})"
                changes_val = "\n".join([f"• {c['clean_message']}" for c in commits])
                desc_val = desc_val or "Sincronizado automáticamente desde los últimos commits del repositorio"
            else:
                await interaction.followup.send(
                    embed=warning_embed(
                        "Sin Borrador Configurado",
                        "No hay ninguna actualización guardada en borrador. Usa `/update configurar` o `/update sync_github`."
                    ),
                    ephemeral=True
                )
                return

        preview = build_announcement_text(
            version=v_val,
            changes=changes_val,
            description=desc_val
        )

        info_box = info_embed(
            "👁️ PREVISUALIZACIÓN DE ANUNCIO (BORRADOR)",
            "Así es como se verá el mensaje publicado en el canal oficial de Discord con el lenguaje y sarcasmo del bot:"
        )

        await interaction.followup.send(embed=info_box, ephemeral=True)
        await interaction.followup.send(embed=preview["embed"], ephemeral=True)

    @update_group.command(name="publicar", description="Publica el anuncio de actualización en el canal oficial de Discord")
    @app_commands.describe(
        version="Versión a publicar (omite para usar el borrador actual)",
        canal="Canal alternativo para esta publicación (opcional)",
        mencionar="Mencionar @everyone o rol específico (ej: 'everyone' o 'rol')"
    )
    async def update_publicar(
        self,
        interaction: discord.Interaction,
        version: str = None,
        canal: discord.TextChannel = None,
        mencionar: str = None
    ):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message(
                embed=error_embed("Sin Permiso", "No tienes permisos de administración."),
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        config = await get_or_create_update_config(gid)

        target_channel_id = str(canal.id) if canal else config.get("channel_id")
        if not target_channel_id:
            await interaction.followup.send(
                embed=error_embed(
                    "Canal No Configurado",
                    "Primero debes configurar un canal de anuncios con `/update canal` o seleccionar uno con el parámetro `canal:`."
                ),
                ephemeral=True
            )
            return

        target_channel = canal or self.bot.get_channel(int(target_channel_id))
        if not target_channel:
            try:
                target_channel = await self.bot.fetch_channel(int(target_channel_id))
            except Exception as e:
                await interaction.followup.send(
                    embed=error_embed("Canal Inaccesible", f"No se pudo acceder al canal configurado: `{e}`"),
                    ephemeral=True
                )
                return

        v_val = version or config.get("draft_version")
        changes_val = config.get("draft_changes")
        desc_val = config.get("draft_description")

        if not v_val or not changes_val:
            await interaction.followup.send(
                embed=error_embed(
                    "Faltan Datos de la Actualización",
                    "No hay ningún borrador de versión ni cambios listos. Configúralos con `/update configurar` o `/update sync_github`."
                ),
                ephemeral=True
            )
            return

        # Duplicate check
        if await is_commit_already_published(gid, v_val):
            await interaction.followup.send(
                embed=warning_embed(
                    "Actualización Ya Publicada",
                    f"La versión **{v_val}** ya fue publicada anteriormente en el historial para evitar duplicados."
                ),
                ephemeral=True
            )
            return

        announcement = build_announcement_text(
            version=v_val,
            changes=changes_val,
            description=desc_val
        )

        # Prepare mention content
        content_mention = ""
        if mencionar and mencionar.lower() in ("everyone", "@everyone", "all"):
            content_mention = "@everyone 🚨 **NUEVA ACTUALIZACIÓN DEL BOT**"
        elif config.get("mention_role_id"):
            content_mention = f"<@&{config['mention_role_id']}> 🚨 **NUEVA ACTUALIZACIÓN DEL BOT**"

        try:
            sent_msg = await target_channel.send(
                content=content_mention if content_mention else None,
                embed=announcement["embed"]
            )
        except Exception as e:
            logger.error(f"[Updates] Error al enviar mensaje de actualización: {e}", exc_info=True)
            await interaction.followup.send(
                embed=error_embed("Error al Publicar", f"No se pudo enviar el mensaje al canal {target_channel.mention}: `{e}`"),
                ephemeral=True
            )
            return

        # Record in history
        parsed_changes = format_changes_list(changes_val)
        await record_published_update(
            guild_id=gid,
            version=v_val,
            title=announcement["title"],
            changes=parsed_changes,
            description=desc_val,
            commit_sha=None,
            source="manual",
            published_by=f"@{interaction.user.name}",
            channel_id=str(target_channel.id),
            message_id=str(sent_msg.id)
        )

        # Clear draft
        await aexecute(
            "UPDATE update_config SET draft_version=NULL, draft_changes=NULL, draft_description=NULL, updated_at=NOW() WHERE guild_id=$1",
            (gid,)
        )

        jump_url = sent_msg.jump_url
        card = success_embed(
            "🚀 Actualización Publicada con Éxito",
            f"El anuncio de la versión **{v_val}** ha sido publicado en {target_channel.mention}.\n\n"
            f"🔗 [Ver Mensaje Publicado]({jump_url})"
        )
        await interaction.followup.send(embed=card, ephemeral=True)

    @update_group.command(name="historial", description="Muestra las actualizaciones anteriores publicadas en el servidor")
    @app_commands.describe(limite="Número de actualizaciones a mostrar (1 a 15)")
    async def update_historial(self, interaction: discord.Interaction, limite: int = 5):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message(
                embed=error_embed("Sin Permiso", "No tienes permisos de administración."),
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        safe_limit = max(1, min(15, limite))

        rows = await aexecute(
            """SELECT * FROM bot_updates_history 
               WHERE guild_id=$1 
               ORDER BY published_at DESC 
               LIMIT $2""",
            (gid, safe_limit), fetch="all"
        ) or []

        if not rows:
            await interaction.followup.send(
                embed=info_embed("Historial Vacío", "Aún no se ha registrado ninguna actualización publicada en este servidor."),
                ephemeral=True
            )
            return

        embed = info_embed(
            f"📜 Historial de Actualizaciones — Miami Vice RP",
            f"Mostrando las últimas **{len(rows)}** actualizaciones publicadas:"
        )

        for r in rows:
            try:
                changes = json.loads(r["changes"])
            except Exception:
                changes = [r["changes"]]

            changes_preview = "\n".join(changes[:3])
            if len(changes) > 3:
                changes_preview += f"\n*... y {len(changes) - 3} cambio(s) más*"

            p_date = str(r.get("published_at", ""))[:19]
            source_icon = "🐙 GitHub" if r.get("source") == "github" else "✍️ Manual"
            sha_text = f" • Commit `{r['commit_sha'][:7]}`" if r.get("commit_sha") else ""

            embed.add_field(
                name=f"📦 Versión {r['version']} ({source_icon}{sha_text})",
                value=f"📅 **Fecha:** `{p_date}`\n👤 **Por:** {r.get('published_by', 'Staff')}\n{changes_preview}",
                inline=False
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @update_group.command(name="sync_github", description="Sincroniza y detecta commits reales desde el repositorio de GitHub")
    @app_commands.describe(
        publicar_inmediato="Publicar el anuncio inmediatamente si hay cambios nuevos sin esperar (True/False)",
        limite_commits="Número de commits recientes a consultar (1 a 5)"
    )
    async def update_sync_github(
        self,
        interaction: discord.Interaction,
        publicar_inmediato: bool = False,
        limite_commits: int = 3
    ):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message(
                embed=error_embed("Sin Permiso", "No tienes permisos de administración."),
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        config = await get_or_create_update_config(gid)
        repo_name = config.get("github_repo") or DEFAULT_REPO

        commits = await fetch_github_commits(repo=repo_name, limit=max(1, min(5, limite_commits)))
        if not commits:
            await interaction.followup.send(
                embed=error_embed(
                    "Error al Conectar con GitHub",
                    f"No se pudieron obtener commits del repositorio `{repo_name}`. Verifica la conexión o el nombre del repositorio."
                ),
                ephemeral=True
            )
            return

        latest_commit = commits[0]
        latest_sha = latest_commit["sha"]
        short_sha = latest_commit["short_sha"]

        # Check if already published
        already_pub = await is_commit_already_published(gid, latest_sha) or await is_commit_already_published(gid, short_sha)

        changes_list = [f"• {c['clean_message']}" for c in commits]
        version_name = f"Build {short_sha}"

        announcement = build_announcement_text(
            version=version_name,
            changes=changes_list,
            description=f"Sincronización automática de GitHub ({repo_name})",
            commit_sha=latest_sha
        )

        if publicar_inmediato:
            if already_pub:
                await interaction.followup.send(
                    embed=warning_embed(
                        "Commit Ya Publicado",
                        f"El último commit `{short_sha}` ya fue anunciado previamente. No se enviarán duplicados."
                    ),
                    ephemeral=True
                )
                return

            channel_id = config.get("channel_id")
            if not channel_id:
                await interaction.followup.send(
                    embed=error_embed(
                        "Canal No Configurado",
                        "Para publicar automáticamente debes configurar primero el canal con `/update canal`."
                    ),
                    ephemeral=True
                )
                return

            target_channel = self.bot.get_channel(int(channel_id))
            if not target_channel:
                try:
                    target_channel = await self.bot.fetch_channel(int(channel_id))
                except Exception as e:
                    await interaction.followup.send(
                        embed=error_embed("Canal Inaccesible", f"No se pudo acceder al canal: `{e}`"),
                        ephemeral=True
                    )
                    return

            mention_text = f"<@&{config['mention_role_id']}> 🚨 **NUEVA ACTUALIZACIÓN**" if config.get("mention_role_id") else None

            sent_msg = await target_channel.send(content=mention_text, embed=announcement["embed"])

            await record_published_update(
                guild_id=gid,
                version=version_name,
                title=announcement["title"],
                changes=changes_list,
                description="Sincronización GitHub",
                commit_sha=latest_sha,
                source="github",
                published_by=f"GitHub ({latest_commit['author']})",
                channel_id=str(target_channel.id),
                message_id=str(sent_msg.id)
            )

            await interaction.followup.send(
                embed=success_embed(
                    "🚀 Actualización Publicada desde GitHub",
                    f"Se detectó el commit `{short_sha}` y se publicó en {target_channel.mention}.\n🔗 [Ver Mensaje]({sent_msg.jump_url})"
                ),
                ephemeral=True
            )
        else:
            # Stage as draft
            await aexecute(
                """UPDATE update_config 
                   SET draft_version=$1, draft_changes=$2, draft_description=$3, updated_at=NOW()
                   WHERE guild_id=$4""",
                (version_name, "\n".join(changes_list), f"GitHub Commit {short_sha}", gid)
            )

            status_text = "🟡 Ya publicado anteriormente" if already_pub else "🟢 Nuevo (Listo para publicar)"

            card = info_embed(
                f"🐙 Sincronización con GitHub — {repo_name}",
                f"**Último Commit Detectado:** `{short_sha}`\n"
                f"**Autor:** {latest_commit['author']}\n"
                f"**Estado:** {status_text}\n\n"
                f"**Borrador guardado:** Puedes revisar la previsualización con `/update preview` y enviarlo con `/update publicar`."
            )
            card.add_field(name="🔧 Cambios Detectados Reales", value="\n".join(changes_list[:5]), inline=False)
            await interaction.followup.send(embed=card, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Updates(bot))
    logger.info("Cog 'Updates' cargado exitosamente.")
