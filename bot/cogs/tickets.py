import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging

from bot.db import aexecute
from bot.helpers import generate_id, check_admin_permission
from bot.embeds import success_embed, error_embed, info_embed

logger = logging.getLogger("bot.cogs.tickets")

COOLDOWNS = {}

def check_cooldown(key, seconds):
    now = datetime.datetime.utcnow().timestamp()
    last = COOLDOWNS.get(key, 0)
    remaining = (last + seconds) - now
    if remaining > 0:
        return remaining
    COOLDOWNS[key] = now
    return 0


class TicketReasonModal(discord.ui.Modal, title="Abrir Ticket de Soporte"):
    need_input = discord.ui.TextInput(
        label="¿Qué necesitas?",
        placeholder="Ej: Dudas con mi rol, reporte de usuario, donación, bug...",
        max_length=100,
        required=True
    )
    reason_input = discord.ui.TextInput(
        label="¿Por qué abres este ticket? (Explicación)",
        placeholder="Describe detalladamente el motivo o situación...",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)

        try:
            # Comprobar límite de 3 tickets abiertos
            open_tickets = await aexecute(
                "SELECT id FROM tickets WHERE guild_id=$1 AND creator_id=$2 AND status='open'",
                (gid, uid), fetch="all"
            ) or []

            if len(open_tickets) >= 3:
                await interaction.followup.send(
                    embed=error_embed("Límite de Tickets", "Tienes 3 tickets abiertos actualmente. Por favor cierra uno antes de crear otro."),
                    ephemeral=True
                )
                return

            config = await aexecute("SELECT * FROM ticket_config WHERE guild_id=$1", (gid,), fetch="one") or {}
            category_id = config.get("category_id")
            support_role_id = config.get("support_role_id")

            # Permisos del canal
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True, manage_messages=True)
            }

            if support_role_id and str(support_role_id).isdigit():
                support_role = interaction.guild.get_role(int(support_role_id))
                if support_role:
                    overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True)

            category = None
            if category_id and str(category_id).isdigit():
                category = interaction.guild.get_channel(int(category_id))

            clean_username = "".join(c for c in interaction.user.name if c.isalnum() or c in "-_")[:15] or "ticket"
            channel_name = f"ticket-{clean_username}"

            channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Ticket de {interaction.user.name} ({interaction.user.id}) | Asunto: {self.need_input.value[:50]}",
                reason=f"Ticket de soporte creado por {interaction.user.name}"
            )

            ticket_id = generate_id()
            await aexecute(
                """INSERT INTO tickets (id, guild_id, creator_id, channel_id, category, status, created_at, updated_at)
                   VALUES ($1,$2,$3,$4,$5,'open',NOW(),NOW())""",
                (ticket_id, gid, uid, str(channel.id), self.need_input.value[:50])
            )

            # Enviar mensaje inicial dentro del canal del ticket
            e = info_embed(
                f"🎫 Ticket #{ticket_id[:6].upper()} — Soporte Miami Vice",
                f"Hola {interaction.user.mention}, el equipo de soporte te atenderá en breve.\nPor favor sé paciente y mantén una conducta respetuosa."
            )
            e.set_thumbnail(url=interaction.user.display_avatar.url)
            e.add_field(name="📌 ¿Qué necesita?", value=f"**{self.need_input.value}**", inline=False)
            e.add_field(name="📝 Motivo detallado", value=self.reason_input.value, inline=False)
            if support_role_id and str(support_role_id).isdigit():
                e.add_field(name="👥 Staff Asignado", value=f"<@&{support_role_id}>", inline=True)
            e.set_footer(text="Haz clic en 'Cerrar Ticket' cuando tu consulta esté resuelta.")

            close_view = TicketCloseButton()
            welcome_msg = await channel.send(
                content=f"{interaction.user.mention} {f'<@&{support_role_id}>' if support_role_id else ''}",
                embed=e,
                view=close_view
            )

            await interaction.followup.send(
                embed=success_embed("Ticket Creado", f"Tu ticket fue creado con éxito en {channel.mention}."),
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error al abrir ticket: {e}", exc_info=True)
            await interaction.followup.send(
                embed=error_embed("Error al Crear Ticket", f"Ocurrió un error al crear el canal: `{e}`"),
                ephemeral=True
            )


class TicketOpenButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Abrir Ticket", style=discord.ButtonStyle.primary, emoji="📩", custom_id="ticket_open_persistent")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketReasonModal())


class TicketCloseButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Cerrar Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket_close_persistent")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        gid = str(interaction.guild_id)
        cid = str(interaction.channel_id)

        ticket = await aexecute(
            "SELECT * FROM tickets WHERE channel_id=$1 AND status='open'",
            (cid,), fetch="one"
        )
        if not ticket:
            await interaction.followup.send(embed=error_embed("Error", "No hay un ticket activo registrado en este canal"), ephemeral=True)
            return

        await aexecute(
            "UPDATE tickets SET status='closed', closed_by=$1, updated_at=NOW() WHERE id=$2",
            (str(interaction.user.id), ticket["id"])
        )

        await interaction.followup.send(
            embed=success_embed("Ticket Cerrado", f"Ticket cerrado por {interaction.user.mention}. El canal será archivado/eliminado.")
        )

        try:
            await interaction.channel.edit(name=f"cerrado-{interaction.channel.name[-10:]}")
            # Quitar permisos de escritura al creador
            creator = interaction.guild.get_member(int(ticket["creator_id"]))
            if creator:
                await interaction.channel.set_permissions(creator, send_messages=False, read_messages=True)
        except Exception:
            pass


class Tickets(commands.Cog, name="Tickets"):
    def __init__(self, bot):
        self.bot = bot

    ticket = app_commands.Group(name="ticket", description="Sistema de tickets y soporte con modales interactivos")

    @ticket.command(name="panel", description="Publicar el panel de tickets en el canal que escojas (Admin)")
    @app_commands.describe(
        canal="Canal donde se publicará el panel de tickets (omite para el canal actual)",
        categoria="Categoría de Discord donde se crearán los canales de tickets",
        rol_soporte="Rol encargado de atender los tickets",
        titulo="Título del panel de soporte",
        descripcion="Descripción del panel"
    )
    async def panel(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel = None,
        categoria: discord.CategoryChannel = None,
        rol_soporte: discord.Role = None,
        titulo: str = "🎫 Centro de Atención & Soporte",
        descripcion: str = "Presiona el botón **'Abrir Ticket'** para comunicarte de forma privada con el equipo de Staff de **Miami Vice**.\n\nAl presionar el botón se abrirá un formulario donde deberás indicar qué necesitas y el motivo de tu solicitud."
    ):
        await interaction.response.defer(ephemeral=True)
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Necesitas permisos de administrador"), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        target_channel = canal or interaction.channel

        # Actualizar configuración de tickets
        cat_id = str(categoria.id) if categoria else None
        role_id = str(rol_soporte.id) if rol_soporte else None

        existing = await aexecute("SELECT * FROM ticket_config WHERE guild_id=$1", (gid,), fetch="one")
        if existing:
            new_cat = cat_id or existing.get("category_id")
            new_role = role_id or existing.get("support_role_id")
            await aexecute(
                "UPDATE ticket_config SET category_id=$1, support_role_id=$2, updated_at=NOW() WHERE guild_id=$3",
                (new_cat, new_role, gid)
            )
        else:
            await aexecute(
                """INSERT INTO ticket_config (id, guild_id, category_id, support_role_id, max_open_tickets, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, 3, NOW(), NOW())""",
                (generate_id(), gid, cat_id, role_id)
            )

        e = discord.Embed(
            title=titulo,
            description=descripcion,
            color=discord.Color.gold()
        )
        e.set_image(url="https://images.unsplash.com/photo-1542751371-adc38448a05e?w=1200&auto=format&fit=crop&q=80")
        if rol_soporte:
            e.add_field(name="🛡️ Equipo a Cargo", value=rol_soporte.mention, inline=True)
        if categoria:
            e.add_field(name="📂 Categoría Asignada", value=f"`{categoria.name}`", inline=True)
        e.set_footer(text=f"{interaction.guild.name} • Soporte 24/7", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)

        view = TicketOpenButton()
        await target_channel.send(embed=e, view=view)
        await interaction.followup.send(
            embed=success_embed("Panel de Tickets Publicado", f"El panel de tickets se ha publicado correctamente en {target_channel.mention}."),
            ephemeral=True
        )

    @ticket.command(name="configurar", description="Configurar categoría de tickets y rol de soporte")
    @app_commands.describe(
        categoria="Categoría de Discord donde se abrirán los tickets",
        rol_soporte="Rol de Staff / Soporte"
    )
    async def configurar(
        self,
        interaction: discord.Interaction,
        categoria: discord.CategoryChannel = None,
        rol_soporte: discord.Role = None
    ):
        await interaction.response.defer(ephemeral=True)
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores"), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        existing = await aexecute("SELECT * FROM ticket_config WHERE guild_id=$1", (gid,), fetch="one")

        cat_id = str(categoria.id) if categoria else (existing.get("category_id") if existing else None)
        role_id = str(rol_soporte.id) if rol_soporte else (existing.get("support_role_id") if existing else None)

        if existing:
            await aexecute(
                "UPDATE ticket_config SET category_id=$1, support_role_id=$2, updated_at=NOW() WHERE guild_id=$3",
                (cat_id, role_id, gid)
            )
        else:
            await aexecute(
                """INSERT INTO ticket_config (id, guild_id, category_id, support_role_id, max_open_tickets, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, 3, NOW(), NOW())""",
                (generate_id(), gid, cat_id, role_id)
            )

        e = success_embed("Configuración de Tickets Guardada")
        if cat_id:
            e.add_field(name="📂 Categoría de Apertura", value=f"<#{cat_id}> (`{cat_id}`)", inline=True)
        if role_id:
            e.add_field(name="🛡️ Rol de Soporte", value=f"<@&{role_id}>", inline=True)
        await interaction.followup.send(embed=e, ephemeral=True)

    @ticket.command(name="abrir", description="Abrir un ticket de soporte interactivo")
    async def abrir(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketReasonModal())

    @ticket.command(name="cerrar", description="Cerrar el ticket actual")
    async def cerrar(self, interaction: discord.Interaction):
        await interaction.response.defer()
        ticket = await aexecute(
            "SELECT * FROM tickets WHERE channel_id=$1 AND status='open'",
            (str(interaction.channel_id),), fetch="one"
        )
        if not ticket:
            await interaction.followup.send(embed=error_embed("Error", "Este canal no corresponde a un ticket abierto"), ephemeral=True)
            return

        await aexecute(
            "UPDATE tickets SET status='closed', closed_by=$1, updated_at=NOW() WHERE id=$2",
            (str(interaction.user.id), ticket["id"])
        )
        await interaction.followup.send(embed=success_embed("Ticket Cerrado", f"Cerrado por {interaction.user.mention}"))
        try:
            await interaction.channel.edit(name=f"cerrado-{interaction.channel.name[-10:]}")
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(Tickets(bot))
