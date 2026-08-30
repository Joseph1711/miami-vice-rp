import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import logging
import asyncio

from bot.helpers import check_admin_permission
from bot.embeds import COLOR_SUCCESS, COLOR_ERROR, COLOR_INFO, COLOR_WARNING
from bot.services.server_status import (
    SERVER_CODE,
    get_server_status,
    set_server_status,
    create_server_vote,
    get_active_vote_by_message,
    get_active_vote_by_guild,
    record_user_vote,
    remove_user_vote,
    get_vote_results,
    close_server_vote
)

logger = logging.getLogger("bot.cogs.server_control")


class VoteView(discord.ui.View):
    """Botones interactivos de votación para complementar las reacciones."""
    def __init__(self, vote_id: str, bot=None):
        super().__init__(timeout=None)
        self.vote_id = vote_id
        self.bot = bot

    @discord.ui.button(label="Sí — Abrir servidor", style=discord.ButtonStyle.success, emoji="🟢", custom_id="btn_vote_yes")
    async def vote_yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_vote(interaction, "yes")

    @discord.ui.button(label="No — Mantener cerrado", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="btn_vote_no")
    async def vote_no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_vote(interaction, "no")

    async def _handle_vote(self, interaction: discord.Interaction, choice: str):
        uid = str(interaction.user.id)
        # Registrar o actualizar voto (1 voto por usuario)
        await record_user_vote(self.vote_id, uid, choice)
        res = await get_vote_results(self.vote_id)
        
        choice_text = "🟢 **Sí — Abrir servidor**" if choice == "yes" else "🔴 **No — Mantener cerrado**"
        await interaction.response.send_message(
            f"✅ Tu voto por {choice_text} ha sido registrado exitosamente.\n*Conteo actual:* 🟢 {res['yes']} | 🔴 {res['no']} (Total: {res['total']})",
            ephemeral=True
        )


class ServerControl(commands.Cog, name="Control de Servidor"):
    """Comandos y módulos de estado, apertura, cierre y votación de Miami Vice Roleplay."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_expired_votes.start()

    def cog_unload(self):
        self.check_expired_votes.cancel()

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
        embed = discord.Embed(
            title="📊 Resultado de la votación",
            description="La votación oficial para la apertura de **Miami Vice Roleplay** ha concluido.",
            color=COLOR_SUCCESS if results["winner"] == "yes" else (COLOR_ERROR if results["winner"] == "no" else COLOR_WARNING)
        )
        embed.add_field(name="🟢 A favor", value=f"**{results['yes']}**", inline=True)
        embed.add_field(name="🔴 En contra", value=f"**{results['no']}**", inline=True)
        embed.add_field(name="Total de votos", value=f"**{results['total']}**", inline=True)

        if results["winner"] == "yes":
            verdict = "🟢 **Resultado Favorable:** La comunidad ha votado a favor de abrir el servidor.\n\n*El servidor puede ser abierto por el Staff cuando lo disponga mediante `/abrir-servidor`.*"
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

    # -------------------------------------------------------------------------
    # Manejo de Reacciones 🟢 y 🔴 para Votaciones
    # -------------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # Ignorar reacciones del bot
        if payload.user_id == self.bot.user.id:
            return

        emoji_name = str(payload.emoji.name)
        if emoji_name not in ("🟢", "🔴"):
            return

        vote = await get_active_vote_by_message(str(payload.message_id))
        if not vote:
            return

        choice = "yes" if emoji_name == "🟢" else "no"
        await record_user_vote(vote["id"], str(payload.user_id), choice)

        # Si el usuario tenía la otra reacción en el mensaje, removerla para que coincida con su voto único
        try:
            guild = self.bot.get_guild(payload.guild_id)
            if guild:
                channel = guild.get_channel(payload.channel_id)
                if channel:
                    msg = await channel.fetch_message(payload.message_id)
                    other_emoji = "🔴" if emoji_name == "🟢" else "🟢"
                    for r in msg.reactions:
                        if str(r.emoji) == other_emoji:
                            user = guild.get_member(payload.user_id)
                            if user:
                                await r.remove(user)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        # Ignorar reacciones del bot
        if payload.user_id == self.bot.user.id:
            return

        emoji_name = str(payload.emoji.name)
        if emoji_name not in ("🟢", "🔴"):
            return

        vote = await get_active_vote_by_message(str(payload.message_id))
        if not vote:
            return

        # Si el usuario removió una reacción y no tiene la otra, remover su voto
        try:
            guild = self.bot.get_guild(payload.guild_id)
            if guild:
                channel = guild.get_channel(payload.channel_id)
                if channel:
                    msg = await channel.fetch_message(payload.message_id)
                    other_emoji = "🔴" if emoji_name == "🟢" else "🟢"
                    has_other = False
                    for r in msg.reactions:
                        if str(r.emoji) == other_emoji:
                            users = [u.id async for u in r.users()]
                            if payload.user_id in users:
                                has_other = True
                                break
                    if not has_other:
                        await remove_user_vote(vote["id"], str(payload.user_id))
        except Exception:
            pass

    # =========================================================================
    # COMANDO 1: /abrir-servidor
    # =========================================================================
    @app_commands.command(
        name="abrir-servidor",
        description="Abrir oficialmente el servidor de Roleplay Miami Vice (MVERP)"
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

        embed.set_image(url="https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=1200&auto=format&fit=crop&q=80")
        embed.set_footer(
            text="Miami Vice Roleplay (MVERP) • Operaciones Iniciadas",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )
        embed.timestamp = discord.utils.utcnow()

        # Publicar anuncio oficial
        await target_channel.send(content="@everyone" if interaction.guild else None, embed=embed)

        await interaction.followup.send(
            f"✅ El servidor **Miami Vice Roleplay** ha sido marcado como **🟢 ABIERTO** con código `{SERVER_CODE}` y anunciado en {target_channel.mention}.",
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

        ends_timestamp = int((datetime.datetime.utcnow() + datetime.timedelta(minutes=dur)).timestamp())

        # Crear Embed con el diseño y formato requerido
        embed = discord.Embed(
            title="🗳️ Votación de Apertura",
            description=(
                "> ¿Deseas que **Miami Vice Roleplay** abra sus operaciones?\n\n"
                "🟢 **Sí — Abrir servidor**\n"
                "🔴 **No — Mantener cerrado**\n\n"
                "> ⚠️ **La reacción del bot no cuenta como voto.**\n\n"
                f"⏱️ **Tiempo restante:** Termina <t:{ends_timestamp}:R> (<t:{ends_timestamp}:T>)"
            ),
            color=0x00E5FF
        )
        embed.set_footer(
            text="Miami Vice RP • Votación Oficial de Apertura",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )
        embed.timestamp = discord.utils.utcnow()

        # Enviar mensaje con botones interactivos y agregar reacciones 🟢 y 🔴
        dummy_vote_id = "pending"
        vote_view = VoteView(vote_id=dummy_vote_id, bot=self.bot)
        
        msg = await target_channel.send(
            content="@everyone" if interaction.guild else None,
            embed=embed,
            view=vote_view
        )

        # Crear registro en la base de datos
        vote_data = await create_server_vote(
            guild_id=gid,
            channel_id=str(target_channel.id),
            message_id=str(msg.id),
            creator_id=str(interaction.user.id),
            duration_minutes=dur
        )

        # Vincular el ID real de la votación con la vista de botones
        vote_view.vote_id = vote_data["id"]

        # Agregar reacciones oficiales iniciales del bot
        try:
            await msg.add_reaction("🟢")
            await msg.add_reaction("🔴")
        except Exception as e:
            logger.warning(f"No se pudieron agregar reacciones automáticamente al mensaje: {e}")

        await interaction.followup.send(
            f"✅ Votación de apertura iniciada en {target_channel.mention} con una duración de **{dur} minutos**.",
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
