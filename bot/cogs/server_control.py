import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import logging
import asyncio

from bot.helpers import check_admin_permission, parse_db_datetime
from bot.embeds import COLOR_SUCCESS, COLOR_ERROR, COLOR_INFO, COLOR_WARNING
from bot.services.server_status import (
    SERVER_CODE,
    get_server_status,
    set_server_status,
    create_server_vote,
    get_vote_by_id,
    get_active_vote_by_message,
    get_active_vote_by_guild,
    get_latest_vote_for_guild,
    get_vote_voters,
    get_vote_removals,
    record_user_vote,
    remove_user_vote,
    record_vote_removal,
    get_vote_results,
    close_server_vote
)

logger = logging.getLogger("bot.cogs.server_control")


def _format_voters_display(uids: list, max_chars: int = 380) -> str:
    """Formatea una lista de IDs de Discord a menciones legibles respetando el límite de caracteres."""
    if not uids:
        return "*Ninguno*"
    mentions = [f"<@{uid}>" for uid in uids]
    items = []
    cur = 0
    for i, m in enumerate(mentions):
        cost = len(m) + (2 if items else 0)
        if cur + cost + 15 > max_chars:
            items.append(f"*(+{len(mentions) - i} más)*")
            break
        items.append(m)
        cur += cost
    return ", ".join(items)


class VoteView(discord.ui.View):
    """Botones interactivos de votación con conteo en tiempo real de votantes."""
    def __init__(self, vote_id: str = None, bot=None):
        super().__init__(timeout=None)
        self.vote_id = vote_id
        self.bot = bot

    @discord.ui.button(label="Sí — Abrir servidor", style=discord.ButtonStyle.success, emoji="🟢", custom_id="btn_vote_yes")
    async def vote_yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_vote(interaction, "yes")

    @discord.ui.button(label="No — Mantener cerrado", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="btn_vote_no")
    async def vote_no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_vote(interaction, "no")

    @discord.ui.button(label="Ver votantes", style=discord.ButtonStyle.secondary, emoji="👥", custom_id="btn_vote_viewers")
    async def vote_viewers(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show_voters(interaction)

    @discord.ui.button(label="Quitar mi voto", style=discord.ButtonStyle.danger, emoji="🗑️", custom_id="btn_vote_remove")
    async def vote_remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_remove_vote(interaction)

    async def _resolve_vote(self, interaction: discord.Interaction) -> dict:
        """
        Resuelve de forma dinámica e infalible la votación activa:
        1. Por ID directo almacenado en la vista (si existe y no es 'pending').
        2. Por message.id del mensaje que originó la interacción.
        3. Por guild_id del servidor donde se interactuó.
        """
        # 1. Por ID en memoria de la vista
        if self.vote_id and self.vote_id != "pending":
            vote = await get_vote_by_id(self.vote_id)
            if vote and vote.get("status") == "active":
                return vote

        # 2. Por message_id de la interacción
        if interaction.message:
            vote = await get_active_vote_by_message(str(interaction.message.id))
            if vote:
                self.vote_id = vote["id"]
                return vote

        # 3. Fallback: votación activa del servidor actual
        if interaction.guild_id:
            vote = await get_active_vote_by_guild(str(interaction.guild_id))
            if vote:
                self.vote_id = vote["id"]
                return vote

        return None

    async def _handle_vote(self, interaction: discord.Interaction, choice: str):
        uid = str(interaction.user.id)
        await interaction.response.defer(ephemeral=True)

        vote = await self._resolve_vote(interaction)
        if not vote:
            await interaction.followup.send(
                "ℹ️ No se encontró ninguna votación de apertura activa para este mensaje o ya ha finalizado.",
                ephemeral=True
            )
            return

        vote_id = vote["id"]

        # Verificar si la votación ya expiró
        ends_at = parse_db_datetime(vote.get("ends_at"))
        if ends_at and ends_at < datetime.datetime.utcnow():
            await interaction.followup.send(
                "⏳ Esta votación ya ha finalizado. Los resultados serán publicados por el temporizador o Staff.",
                ephemeral=True
            )
            return

        # Registrar o actualizar voto (1 voto por usuario)
        await record_user_vote(vote_id, uid, choice)

        # Consultar conteo actualizado
        res = await get_vote_results(vote_id)

        # Actualizar el embed en el mensaje original en vivo (sin re-instanciar view para no invalidar botones)
        await self._refresh_live_embed(interaction, vote, res)

        choice_text = "🟢 **Sí — Abrir servidor**" if choice == "yes" else "🔴 **No — Mantener cerrado**"
        await interaction.followup.send(
            f"✅ Tu voto por {choice_text} ha sido registrado exitosamente.\n"
            f"*Conteo actual:* 🟢 {res['yes']} | 🔴 {res['no']} (Total: {res['total']})",
            ephemeral=True
        )

    async def _handle_remove_vote(self, interaction: discord.Interaction):
        uid = str(interaction.user.id)
        await interaction.response.defer(ephemeral=True)

        vote = await self._resolve_vote(interaction)
        if not vote:
            await interaction.followup.send(
                "ℹ️ No hay una votación activa registrada para retirar votos.",
                ephemeral=True
            )
            return

        vote_id = vote["id"]
        existing = await get_vote_voters(vote_id)
        had_vote = uid in existing["total_voters"]

        if not had_vote:
            await interaction.followup.send(
                "ℹ️ No tienes un voto registrado que retirar.",
                ephemeral=True
            )
            return

        await remove_user_vote(vote_id, uid)
        await record_vote_removal(vote_id, uid)

        new_res = await get_vote_results(vote_id)
        await self._refresh_live_embed(interaction, vote, new_res)

        await interaction.followup.send(
            f"🗑️ Tu voto ha sido **retirado** correctamente.\n"
            f"*Conteo actualizado:* 🟢 {new_res['yes']} | 🔴 {new_res['no']} (Total: {new_res['total']})",
            ephemeral=True
        )

    async def _show_voters(self, interaction: discord.Interaction):
        """Muestra en tiempo real quiénes han votado y quiénes retiraron su voto."""
        await interaction.response.defer(ephemeral=True)

        vote = await self._resolve_vote(interaction)
        if not vote:
            await interaction.followup.send(
                "ℹ️ Aún no hay una votación activa registrada o ya ha concluido.",
                ephemeral=True
            )
            return

        vote_id = vote["id"]
        voters_info = await get_vote_voters(vote_id)
        removals = await get_vote_removals(vote_id)
        res = await get_vote_results(vote_id)

        embed = discord.Embed(
            title="👥 Votantes en Tiempo Real",
            description=(
                f"Conteo actual de la votación oficial de apertura:\n\n"
                f"🟢 **A favor:** {res['yes']}\n"
                f"🔴 **En contra:** {res['no']}\n"
                f"📊 **Total de votantes activos:** {res['total']}"
            ),
            color=COLOR_INFO
        )

        yes_mentions = _format_voters_display(voters_info["yes_voters"])
        no_mentions = _format_voters_display(voters_info["no_voters"])

        embed.add_field(
            name=f"🟢 A favor ({voters_info['yes_count']})",
            value=yes_mentions or "*Ninguno*",
            inline=False
        )
        embed.add_field(
            name=f"🔴 En contra ({voters_info['no_count']})",
            value=no_mentions or "*Ninguno*",
            inline=False
        )

        if removals:
            removal_lines = []
            for r in removals[:25]:
                when = ""
                removed_at = parse_db_datetime(r.get("removed_at"))
                if removed_at:
                    when = f" — <t:{int(removed_at.timestamp())}:R>"
                removal_lines.append(f"• <@{r['discord_id']}>{when}")
            embed.add_field(
                name=f"🗑️ Retiraron / quitaron su voto ({len(removals)})",
                value="\n".join(removal_lines) + (f"\n*... +{len(removals) - 25} más*" if len(removals) > 25 else ""),
                inline=False
            )
        else:
            embed.add_field(
                name="🗑️ Retiraron su voto",
                value="*Nadie ha retirado su voto hasta ahora.*",
                inline=False
            )

        embed.set_footer(text="Miami Vice RP • Votación Oficial de Apertura")
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def _build_vote_embed(self, vote: dict, results: dict, guild: discord.Guild) -> discord.Embed:
        """Construye el embed de votación mostrando los conteos y votantes en tiempo real."""
        ends_at = parse_db_datetime(vote.get("ends_at")) if vote else None
        ends_display = f"<t:{int(ends_at.timestamp())}:R> (<t:{int(ends_at.timestamp())}:T>)" if ends_at else "En breve"

        voters_info = None
        if vote and vote.get("id") and vote["id"] != "pending":
            try:
                voters_info = await get_vote_voters(vote["id"])
            except Exception:
                voters_info = None

        embed = discord.Embed(
            title="🗳️ Votación de Apertura",
            description=(
                "> ¿Deseas que **Miami Vice Roleplay** abra sus operaciones?\n\n"
                "🟢 **Sí — Abrir servidor**\n"
                "🔴 **No — Mantener cerrado**\n\n"
                "> ✅ **Usa los botones de abajo para votar.**\n\n"
                f"⏱️ **Tiempo restante:** Termina {ends_display}"
            ),
            color=0x00E5FF
        )

        embed.add_field(name="🟢 A favor", value=f"**{results.get('yes', 0)}**", inline=True)
        embed.add_field(name="🔴 En contra", value=f"**{results.get('no', 0)}**", inline=True)
        embed.add_field(name="📊 Total", value=f"**{results.get('total', 0)}**", inline=True)

        if voters_info and voters_info["total"] > 0:
            yes_mentions = _format_voters_display(voters_info["yes_voters"], max_chars=260)
            no_mentions = _format_voters_display(voters_info["no_voters"], max_chars=260)
            embed.add_field(
                name="👥 Votantes en tiempo real",
                value=(
                    f"🟢 **A favor ({voters_info['yes_count']}):**\n{yes_mentions}\n\n"
                    f"🔴 **En contra ({voters_info['no_count']}):**\n{no_mentions}\n\n"
                    f"*Pulsa el botón « 👥 Ver votantes » para ver el detalle completo.*"
                ),
                inline=False
            )

        embed.set_footer(
            text="Miami Vice RP • Votación Oficial de Apertura",
            icon_url=guild.icon.url if guild and guild.icon else None
        )
        embed.timestamp = discord.utils.utcnow()
        return embed

    async def _refresh_live_embed(self, interaction: discord.Interaction, vote: dict, results: dict):
        """
        Actualiza el embed del mensaje de votación con los conteos y votantes en vivo.
        IMPORTANTE: No sustituye la 'view' para no desasociar los event listeners ni fallar en discord.py.
        """
        try:
            guild = getattr(interaction, "guild", None)
            embed = await self._build_vote_embed(vote, results, guild)

            # 1. Intentar editar el mensaje asociado a la interacción
            if interaction.message:
                try:
                    await interaction.message.edit(embed=embed)
                    return
                except Exception as edit_err:
                    logger.debug(f"No se pudo editar interaction.message directamente: {edit_err}")

            # 2. Fallback: buscar el mensaje por canal y message_id
            channel = interaction.channel or (guild.get_channel(int(vote["channel_id"])) if guild and vote.get("channel_id") else None)
            if channel and vote.get("message_id"):
                try:
                    target_msg = await channel.fetch_message(int(vote["message_id"]))
                    if target_msg:
                        await target_msg.edit(embed=embed)
                except Exception as fetch_err:
                    logger.warning(f"Fallback fetch_message falló para mensaje {vote.get('message_id')}: {fetch_err}")
        except Exception as e:
            logger.error(f"Error actualizando embed en vivo de la votación: {e}", exc_info=True)


class ServerControl(commands.Cog, name="Control de Servidor"):
    """Comandos y módulos de estado, apertura, cierre y votación de Miami Vice Roleplay."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._registered_view_messages = set()
        self.check_expired_votes.start()

    async def cog_load(self):
        """Registra la vista global de votación para garantizar que todos los botones funcionen siempre."""
        try:
            self.bot.add_view(VoteView(bot=self.bot))
            logger.info("Vista global persistente de votación registrada exitosamente")
        except Exception as e:
            logger.warning(f"No se pudo registrar la vista global de votación en cog_load: {e}")

    def cog_unload(self):
        self.check_expired_votes.cancel()

    # -------------------------------------------------------------------------
    # Registro de vistas persistentes de votación (sobreviven a reinicios)
    # -------------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        try:
            from bot.db import aexecute
            active_votes = await aexecute(
                "SELECT id, message_id FROM server_votes WHERE status = 'active'",
                (),
                fetch="all"
            ) or []
            for vote in active_votes:
                try:
                    msg_id = int(vote["message_id"])
                    if msg_id in self._registered_view_messages:
                        continue
                    view = VoteView(vote_id=vote["id"], bot=self.bot)
                    self.bot.add_view(view, message_id=msg_id)
                    self._registered_view_messages.add(msg_id)
                except Exception as inner_err:
                    logger.warning(f"Error registrando vista para mensaje {vote.get('message_id')}: {inner_err}")
            if active_votes:
                logger.info(f"Registradas {len(active_votes)} vistas de votación persistentes")
        except Exception as e:
            logger.error(f"Error registrando vistas de votación persistentes: {e}", exc_info=True)

    # -------------------------------------------------------------------------
    # Tarea periódica para finalizar votaciones automáticamente
    # -------------------------------------------------------------------------
    @tasks.loop(seconds=10)
    async def check_expired_votes(self):
        try:
            from bot.db import aexecute
            now = datetime.datetime.utcnow()
            expired_votes = await aexecute(
                "SELECT * FROM server_votes WHERE status = 'active' AND ends_at <= $1",
                (now,),
                fetch="all"
            ) or []

            for vote in expired_votes:
                await self._conclude_vote(vote)
        except Exception as e:
            logger.error(f"Error verificando votaciones expiradas: {e}", exc_info=True)

    @check_expired_votes.before_loop
    async def before_check_expired_votes(self):
        await self.bot.wait_until_ready()

    async def _conclude_vote(self, vote_data: dict):
        """Cierra una votación y publica el resultado final."""
        vote_id = vote_data["id"]
        guild_id = vote_data["guild_id"]
        channel_id = vote_data["channel_id"]
        message_id = vote_data["message_id"]

        results = await close_server_vote(vote_id)
        
        guild = self.bot.get_guild(int(guild_id))
        if not guild:
            return
        
        channel = guild.get_channel(int(channel_id))
        if not channel:
            return

        # Construir Embed de resultados oficiales
        voters_info = await get_vote_voters(vote_id)

        embed = discord.Embed(
            title="📊 Resultado de la votación",
            description="La votación oficial para la apertura de **Miami Vice Roleplay** ha concluido.",
            color=COLOR_SUCCESS if results["winner"] == "yes" else (COLOR_ERROR if results["winner"] == "no" else COLOR_WARNING)
        )
        embed.add_field(name="🟢 A favor", value=f"**{results['yes']}**", inline=True)
        embed.add_field(name="🔴 En contra", value=f"**{results['no']}**", inline=True)
        embed.add_field(name="Total de votos", value=f"**{results['total']}**", inline=True)

        if voters_info and voters_info["total"] > 0:
            yes_list = _format_voters_display(voters_info["yes_voters"])
            no_list = _format_voters_display(voters_info["no_voters"])
            embed.add_field(
                name="👥 Personas que Votaron",
                value=f"🟢 **A favor ({voters_info['yes_count']}):**\n{yes_list}\n\n🔴 **En contra ({voters_info['no_count']}):**\n{no_list}",
                inline=False
            )

        if results["winner"] == "yes":
            verdict = "🟢 **Resultado Favorable:** La comunidad ha votado a favor de abrir el servidor.\n\n*El servidor puede ser abierto por el Staff cuando lo disponga mediante `/abrir servidor`.*"
        elif results["winner"] == "no":
            verdict = "🔴 **Resultado Negativo:** La comunidad ha decidido que el servidor permanezca cerrado.\n\n*El servidor permanecerá cerrado por el momento.*"
        else:
            verdict = "⚖️ **Empate:** La votación finalizó en empate. La decisión final queda a criterio del Staff."

        embed.add_field(name="📋 Veredicto", value=verdict, inline=False)
        embed.set_footer(text="Miami Vice RP • Sistema Oficial de Apertura y Cierre", icon_url=guild.icon.url if guild.icon else None)
        embed.timestamp = discord.utils.utcnow()

        try:
            # Enviar mensaje con el resultado final
            await channel.send(embed=embed)
            
            # Desactivar botones en el mensaje original si aún existe
            try:
                orig_msg = await channel.fetch_message(int(message_id))
                if orig_msg:
                    disabled_view = discord.ui.View()
                    disabled_view.add_item(discord.ui.Button(label=f"Sí ({results['yes']})", style=discord.ButtonStyle.success, emoji="🟢", disabled=True))
                    disabled_view.add_item(discord.ui.Button(label=f"No ({results['no']})", style=discord.ButtonStyle.danger, emoji="🔴", disabled=True))
                    
                    orig_embed = orig_msg.embeds[0] if orig_msg.embeds else None
                    if orig_embed:
                        orig_embed.color = discord.Color.dark_gray()
                        orig_embed.set_footer(text="🗳️ Votación Finalizada")
                        await orig_msg.edit(embed=orig_embed, view=disabled_view)
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error publicando resultado de votación {vote_id}: {e}")

    # =========================================================================
    # COMANDO 1: /abrir-servidor y /abrir servidor
    # =========================================================================
    abrir_group = app_commands.Group(name="abrir", description="Comandos de apertura para Miami Vice RP")

    @abrir_group.command(
        name="servidor",
        description="Abrir oficialmente el servidor de Roleplay Miami Vice (MVERP) mostrando votantes"
    )
    @app_commands.describe(
        canal="Canal donde se publicará el anuncio oficial (opcional, por defecto el canal actual)",
        anuncio_extra="Mensaje o notas adicionales para los jugadores (opcional)"
    )
    async def abrir_servidor_group(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel = None,
        anuncio_extra: str = None
    ):
        await ServerControl.abrir_servidor.callback(self, interaction, canal, anuncio_extra)

    @app_commands.command(
        name="abrir-servidor",
        description="Abrir oficialmente el servidor de Roleplay Miami Vice (MVERP) mostrando votantes"
    )
    @app_commands.describe(
        canal="Canal donde se publicará el anuncio oficial (opcional, por defecto el canal actual)",
        anuncio_extra="Mensaje o notas adicionales para los jugadores (opcional)"
    )
    async def abrir_servidor(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel = None,
        anuncio_extra: str = None
    ):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message("❌ No tienes permisos para utilizar este comando.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        target_channel = canal or interaction.channel

        # Actualizar y persistir el estado a OPEN en la base de datos
        await set_server_status(
            guild_id=gid,
            status="OPEN",
            updated_by=f"{interaction.user.name} ({interaction.user.id})",
            server_code=SERVER_CODE
        )

        # Consultar la votación comunitaria (activa o la más reciente realizada)
        active_vote = await get_active_vote_by_guild(gid)
        target_vote = None
        if active_vote:
            await close_server_vote(active_vote["id"])
            target_vote = active_vote
        else:
            target_vote = await get_latest_vote_for_guild(gid)

        voters_info = None
        if target_vote:
            voters_info = await get_vote_voters(target_vote["id"])

        # Crear Embed con el diseño requerido
        embed = discord.Embed(
            title="🟢 SERVIDOR ABIERTO",
            description=(
                "> **Miami Vice Roleplay está oficialmente abierto.**\n"
                ">\n"
                "> Ya puedes ingresar al servidor de Roleplay.\n"
                ">\n"
                f"> **Código del servidor: `{SERVER_CODE}`**"
            ),
            color=COLOR_SUCCESS
        )

        embed.add_field(name="Estado", value="🟢 **Abierto**", inline=True)
        embed.add_field(name="Código", value=f"`{SERVER_CODE}`", inline=True)
        embed.add_field(name="Autorizado por", value=interaction.user.mention, inline=True)

        if anuncio_extra:
            embed.add_field(name="📢 Información Adicional", value=anuncio_extra, inline=False)

        # Mostrar a las personas que votaron en el comando
        if voters_info and voters_info["total"] > 0:
            yes_mentions = _format_voters_display(voters_info["yes_voters"])
            no_mentions = _format_voters_display(voters_info["no_voters"])

            voters_value = (
                f"🗳️ **Total de votantes registrados:** `{voters_info['total']}`\n\n"
                f"🟢 **A favor ({voters_info['yes_count']}):**\n{yes_mentions}\n\n"
                f"🔴 **En contra ({voters_info['no_count']}):**\n{no_mentions}"
            )
            embed.add_field(
                name="👥 Personas que Votaron para la Apertura",
                value=voters_value,
                inline=False
            )
        else:
            embed.add_field(
                name="👥 Personas que Votaron",
                value="*Apertura directa ejecutada por el Staff (no se registraron votos en una votación previa).* ",
                inline=False
            )

        embed.set_image(url="https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=1200&auto=format&fit=crop&q=80")
        embed.set_footer(
            text="Miami Vice Roleplay (MVERP) • Operaciones Iniciadas",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )
        embed.timestamp = discord.utils.utcnow()

        # Publicar anuncio oficial
        await target_channel.send(content="@everyone" if interaction.guild else None, embed=embed)

        summary_voters = ""
        if voters_info and voters_info["total"] > 0:
            summary_voters = f"\n🗳️ **Votos contabilizados ({voters_info['total']}):** 🟢 {voters_info['yes_count']} a favor | 🔴 {voters_info['no_count']} en contra."

        await interaction.followup.send(
            f"✅ El servidor **Miami Vice Roleplay** ha sido marcado como **🟢 ABIERTO** con código `{SERVER_CODE}` y anunciado en {target_channel.mention}.{summary_voters}",
            ephemeral=True
        )

    # =========================================================================
    # COMANDO 2: /cerrar-servidor
    # =========================================================================
    @app_commands.command(
        name="cerrar-servidor",
        description="Cerrar oficialmente el servidor de Roleplay Miami Vice (MVERP)"
    )
    @app_commands.describe(
        canal="Canal donde se publicará el anuncio de cierre (opcional, por defecto el canal actual)",
        motivo="Motivo del cierre (mantenimiento, finalización de sesión, etc.)"
    )
    async def cerrar_servidor(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel = None,
        motivo: str = None
    ):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message("❌ No tienes permisos para utilizar este comando.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        target_channel = canal or interaction.channel

        # Actualizar y persistir el estado a CLOSED en la base de datos
        await set_server_status(
            guild_id=gid,
            status="CLOSED",
            updated_by=f"{interaction.user.name} ({interaction.user.id})",
            server_code=SERVER_CODE
        )

        # Crear Embed con el diseño requerido
        embed = discord.Embed(
            title="🔴 SERVIDOR CERRADO",
            description=(
                "> **Miami Vice Roleplay ha cerrado operaciones.**\n"
                ">\n"
                "> El servidor de Roleplay se encuentra actualmente cerrado y **no se puede ingresar al servidor**.\n"
                ">\n"
                "> Por favor, espera a la próxima apertura oficial."
            ),
            color=COLOR_ERROR
        )

        embed.add_field(name="Estado", value="🔴 **Cerrado**", inline=True)
        embed.add_field(name="Acceso", value="🚫 **No disponible**", inline=True)
        embed.add_field(name="Cerrado por", value=interaction.user.mention, inline=True)

        if motivo:
            embed.add_field(name="📝 Motivo del Cierre", value=motivo, inline=False)

        embed.set_image(url="https://images.unsplash.com/photo-1514565131-fce0801e5785?w=1200&auto=format&fit=crop&q=80")
        embed.set_footer(
            text="Miami Vice Roleplay (MVERP) • Operaciones Finalizadas",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )
        embed.timestamp = discord.utils.utcnow()

        # Publicar anuncio oficial
        await target_channel.send(content="@everyone" if interaction.guild else None, embed=embed)

        await interaction.followup.send(
            f"✅ El servidor **Miami Vice Roleplay** ha sido marcado como **🔴 CERRADO** y anunciado en {target_channel.mention}.",
            ephemeral=True
        )

    # =========================================================================
    # COMANDO 3: /votacion-servidor
    # =========================================================================
    @app_commands.command(
        name="votacion-servidor",
        description="Iniciar una votación comunitaria para decidir si se abre el servidor de Roleplay"
    )
    @app_commands.describe(
        duracion_minutos="Duración de la votación en minutos (por defecto 5 minutos)",
        canal="Canal donde se publicará la votación (opcional, por defecto el canal actual)"
    )
    async def votacion_servidor(
        self,
        interaction: discord.Interaction,
        duracion_minutos: int = 5,
        canal: discord.TextChannel = None
    ):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message("❌ No tienes permisos para utilizar este comando.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        target_channel = canal or interaction.channel
        dur = max(1, min(1440, duracion_minutos))

        from bot.helpers import generate_id

        ends_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=dur)
        empty_results = {"yes": 0, "no": 0, "total": 0, "winner": "tie"}
        
        # Pre-generar el ID real para evitar cualquier estado 'pending' o desincronización
        real_vote_id = generate_id()
        placeholder_vote = {"id": real_vote_id, "ends_at": ends_at}

        # Enviar mensaje con botones interactivos y ID real asignado de antemano
        vote_view = VoteView(vote_id=real_vote_id, bot=self.bot)

        # Crear Embed con el formato oficial (conteos en tiempo real y botones)
        embed = await vote_view._build_vote_embed(placeholder_vote, empty_results, interaction.guild)

        msg = await target_channel.send(
            content="@everyone" if interaction.guild else None,
            embed=embed,
            view=vote_view
        )

        # Crear registro en la base de datos vinculado al mensaje y al ID ya asignado
        vote_data = await create_server_vote(
            guild_id=gid,
            channel_id=str(target_channel.id),
            message_id=str(msg.id),
            creator_id=str(interaction.user.id),
            duration_minutes=dur,
            vote_id=real_vote_id,
            ends_at=ends_at
        )

        # Registrar la vista como persistente con message_id para sobrevivir a reinicios
        try:
            self.bot.add_view(vote_view, message_id=msg.id)
            self._registered_view_messages.add(msg.id)
        except Exception as e:
            logger.warning(f"No se pudo registrar la vista persistente de la votación: {e}")

        await interaction.followup.send(
            f"✅ Votación de apertura iniciada en {target_channel.mention} con una duración de **{dur} minutos**.\n"
            f"Los votos se registran mediante los **botones** y puedes consultar a los votantes en tiempo real.",
            ephemeral=True
        )

    # =========================================================================
    # COMANDO 4: /estado-servidor (Consulta de Estado)
    # =========================================================================
    @app_commands.command(
        name="estado-servidor",
        description="Consultar el estado operativo actual de Miami Vice Roleplay (MVERP)"
    )
    async def estado_servidor(self, interaction: discord.Interaction):
        await interaction.response.defer()
        gid = str(interaction.guild_id)
        data = await get_server_status(gid)
        status = str(data.get("status", "CLOSED")).upper()
        server_code = data.get("server_code", SERVER_CODE)

        if status == "OPEN":
            embed = discord.Embed(
                title="🟢 ESTADO: SERVIDOR ABIERTO",
                description=(
                    "> **Miami Vice Roleplay está actualmente ABIERTO.**\n"
                    ">\n"
                    f"> **Código oficial:** `{server_code}`\n"
                    "> ¡Puedes ingresar y rolear con la comunidad!"
                ),
                color=COLOR_SUCCESS
            )
            embed.add_field(name="Estado", value="🟢 **Abierto**", inline=True)
            embed.add_field(name="Código", value=f"`{server_code}`", inline=True)
        else:
            embed = discord.Embed(
                title="🔴 ESTADO: SERVIDOR CERRADO",
                description=(
                    "> **Miami Vice Roleplay se encuentra actualmente CERRADO.**\n"
                    ">\n"
                    "> **Acceso:** 🚫 No disponible.\n"
                    "> Por favor, mantente atento a los anuncios oficiales del Staff para la próxima apertura."
                ),
                color=COLOR_ERROR
            )
            embed.add_field(name="Estado", value="🔴 **Cerrado**", inline=True)
            embed.add_field(name="Acceso", value="🚫 **No disponible**", inline=True)

        if data.get("updated_at"):
            embed.add_field(name="Última Actualización", value=f"{str(data['updated_at'])[:19]} UTC", inline=False)

        embed.set_footer(
            text="Miami Vice Roleplay (MVERP)",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )
        embed.timestamp = discord.utils.utcnow()
        await interaction.followup.send(embed=embed)

    # =========================================================================
    # COMANDO 5: /finalizar-votacion (Cierre Manual por Staff)
    # =========================================================================
    @app_commands.command(
        name="finalizar-votacion",
        description="Finalizar manualmente la votación activa de apertura y publicar los resultados"
    )
    async def finalizar_votacion(self, interaction: discord.Interaction):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message("❌ No tienes permisos para utilizar este comando.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        active_vote = await get_active_vote_by_guild(gid)

        if not active_vote:
            await interaction.followup.send(
                "ℹ️ No hay ninguna votación de apertura activa en este servidor.",
                ephemeral=True
            )
            return

        await self._conclude_vote(active_vote)
        await interaction.followup.send(
            "✅ La votación activa ha sido finalizada y los resultados han sido publicados.",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerControl(bot))
