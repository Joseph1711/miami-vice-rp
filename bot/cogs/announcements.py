import discord
from discord import app_commands
from discord.ext import commands
import logging

from bot.helpers import check_admin_permission
from bot.embeds import success_embed, error_embed, info_embed

logger = logging.getLogger("bot.announcements")

COLOR_CHOICES = {
    "cyan": {"label": "🌴 Miami Cyan (#00E5FF)", "value": 0x00E5FF},
    "rosa": {"label": "🌸 Miami Vice Pink (#FF2A85)", "value": 0xFF2A85},
    "dorado": {"label": "✨ Oro / VIP (#FFD700)", "value": 0xFFD700},
    "azul_policial": {"label": "🚔 Azul Policial (#1A5276)", "value": 0x1A5276},
    "rojo": {"label": "🚨 Rojo Alerta (#E74C3C)", "value": 0xE74C3C},
    "verde": {"label": "🟢 Verde Éxito (#2ECC71)", "value": 0x2ECC71},
    "purpura": {"label": "🔮 Púrpura Synthwave (#9B59B6)", "value": 0x9B59B6},
    "naranja": {"label": "🔥 Naranja Atardecer (#E67E22)", "value": 0xE67E22},
    "oscuro": {"label": "🖤 Negro Stealth (#1C1C1E)", "value": 0x1C1C1E}
}


class AnnouncementModal(discord.ui.Modal):
    def __init__(self, target_channel: discord.TextChannel, ping_type: str = "none"):
        super().__init__(title="🌴 Redactar Anuncio Oficial Embed")
        self.target_channel = target_channel
        self.ping_type = ping_type

        self.title_input = discord.ui.TextInput(
            label="Título del Anuncio",
            placeholder="Ej: 📢 COMUNICADO OFICIAL DE LA ALCALDÍA",
            max_length=100,
            required=True
        )
        self.message_input = discord.ui.TextInput(
            label="Cuerpo del Comunicado (Markdown)",
            placeholder="Escribe el mensaje completo aquí... Puedes usar **negrita**, *cursiva*, listas y emojis.",
            style=discord.TextStyle.paragraph,
            max_length=3500,
            required=True
        )
        self.color_input = discord.ui.TextInput(
            label="Color Hexadecimal (opcional)",
            placeholder="Ej: #00E5FF o #FF2A85 (dejar vacío para cyan por defecto)",
            max_length=10,
            required=False,
            default="#00E5FF"
        )
        self.banner_input = discord.ui.TextInput(
            label="URL de Banner o Imagen (opcional)",
            placeholder="https://i.imgur.com/ejemplo.png",
            max_length=300,
            required=False
        )
        self.footer_input = discord.ui.TextInput(
            label="Pie de Página / Autor (opcional)",
            placeholder="Ej: Miami Vice Roleplay • Administración",
            max_length=100,
            required=False,
            default="🌴 Miami Vice Roleplay • Comunicado Oficial"
        )

        self.add_item(self.title_input)
        self.add_item(self.message_input)
        self.add_item(self.color_input)
        self.add_item(self.banner_input)
        self.add_item(self.footer_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed(
                "Sin Permisos",
                "Solo los administradores y staff autorizados pueden publicar anuncios oficiales."
            ), ephemeral=True)
            return

        # Parse color
        color_val = 0x00E5FF
        raw_hex = self.color_input.value.strip().lstrip("#")
        if raw_hex:
            try:
                color_val = int(raw_hex, 16)
            except ValueError:
                color_val = 0x00E5FF

        embed = discord.Embed(
            title=self.title_input.value.strip(),
            description=self.message_input.value.strip(),
            color=color_val
        )

        banner = self.banner_input.value.strip()
        if banner and (banner.startswith("http://") or banner.startswith("https://")):
            embed.set_image(url=banner)

        footer = self.footer_input.value.strip() or "🌴 Miami Vice Roleplay • Comunicado Oficial"
        embed.set_footer(text=footer)
        embed.timestamp = discord.utils.utcnow()

        # Mención
        content = None
        if self.ping_type == "everyone":
            content = "@everyone"
        elif self.ping_type == "here":
            content = "@here"

        try:
            sent_msg = await self.target_channel.send(content=content, embed=embed)
            await interaction.followup.send(embed=success_embed(
                "Anuncio Publicado con Éxito",
                f"El anuncio ha sido emitido en {self.target_channel.mention}.\n[Ver Mensaje]({sent_msg.jump_url})"
            ), ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(embed=error_embed(
                "Error de Permisos",
                f"El bot no tiene permisos suficientes para enviar mensajes en {self.target_channel.mention}."
            ), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(embed=error_embed("Error", f"No se pudo enviar el anuncio: {e}"), ephemeral=True)


class Announcements(commands.Cog):
    """Sistema de Anuncios y Comunicados Oficiales tipo Embed."""

    announcement_group = app_commands.Group(
        name="anuncio",
        description="Emisión de anuncios y comunicados oficiales con diseño embed personalizado"
    )

    def __init__(self, bot):
        self.bot = bot

    # ==========================================
    # COMANDO 1: /anuncio modal (Editor Interactivo)
    # ==========================================
    @announcement_group.command(name="modal", description="Abre el editor visual de anuncios con soporte para textos largos")
    @app_commands.describe(
        canal="Canal donde se publicará el comunicado",
        mencion="Mención especial para notificar a la comunidad"
    )
    @app_commands.choices(mencion=[
        app_commands.Choice(name="Sin mención", value="none"),
        app_commands.Choice(name="📢 @everyone", value="everyone"),
        app_commands.Choice(name="🔔 @here", value="here")
    ])
    async def anuncio_modal(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        mencion: str = "none"
    ):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message(embed=error_embed(
                "Sin Permisos",
                "Solo administradores y miembros del staff pueden emitir anuncios."
            ), ephemeral=True)
            return

        modal = AnnouncementModal(target_channel=canal, ping_type=mencion)
        await interaction.response.send_modal(modal)

    # ==========================================
    # COMANDO 2: /anuncio crear (Comando directo)
    # ==========================================
    @announcement_group.command(name="crear", description="Crea y publica un anuncio oficial con estilo Embed personalizado")
    @app_commands.describe(
        canal="Canal donde se emitirá el anuncio",
        titulo="Título del comunicado",
        mensaje="Mensaje o contenido del anuncio (Markdown permitido)",
        color="Color temático del borde del embed",
        imagen_url="URL de imagen o banner adjunto (opcional)",
        miniatura_url="URL de logo o miniatura superior (opcional)",
        pie_de_pagina="Texto en el pie de página (opcional)",
        mencion="Notificación comunitaria"
    )
    @app_commands.choices(
        color=[
            app_commands.Choice(name="🌴 Miami Cyan (#00E5FF)", value="cyan"),
            app_commands.Choice(name="🌸 Rosa Miami Vice (#FF2A85)", value="rosa"),
            app_commands.Choice(name="✨ Oro / VIP (#FFD700)", value="dorado"),
            app_commands.Choice(name="🚔 Azul Policial (#1A5276)", value="azul_policial"),
            app_commands.Choice(name="🚨 Rojo Alerta (#E74C3C)", value="rojo"),
            app_commands.Choice(name="🟢 Verde Éxito (#2ECC71)", value="verde"),
            app_commands.Choice(name="🔮 Púrpura Synthwave (#9B59B6)", value="purpura"),
            app_commands.Choice(name="🔥 Naranja Atardecer (#E67E22)", value="naranja"),
            app_commands.Choice(name="🖤 Negro Stealth (#1C1C1E)", value="oscuro")
        ],
        mencion=[
            app_commands.Choice(name="Sin mención", value="none"),
            app_commands.Choice(name="📢 @everyone", value="everyone"),
            app_commands.Choice(name="🔔 @here", value="here")
        ]
    )
    async def anuncio_crear(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
        titulo: str,
        mensaje: str,
        color: str = "cyan",
        imagen_url: str = None,
        miniatura_url: str = None,
        pie_de_pagina: str = None,
        mencion: str = "none"
    ):
        await interaction.response.defer(ephemeral=True)

        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed(
                "Sin Permisos",
                "Solo administradores y miembros del staff pueden emitir anuncios."
            ), ephemeral=True)
            return

        c_info = COLOR_CHOICES.get(color, COLOR_CHOICES["cyan"])
        color_val = c_info["value"]

        # Procesar saltos de línea literales \n si fueron introducidos en un string
        clean_msg = mensaje.replace("\\n", "\n")

        embed = discord.Embed(
            title=titulo.strip(),
            description=clean_msg.strip(),
            color=color_val
        )

        if imagen_url and (imagen_url.startswith("http://") or imagen_url.startswith("https://")):
            embed.set_image(url=imagen_url.strip())

        if miniatura_url and (miniatura_url.startswith("http://") or miniatura_url.startswith("https://")):
            embed.set_thumbnail(url=miniatura_url.strip())

        footer_text = pie_de_pagina.strip() if pie_de_pagina else "🌴 Miami Vice Roleplay • Anuncio Oficial"
        embed.set_footer(text=footer_text)
        embed.timestamp = discord.utils.utcnow()

        content = None
        if mencion == "everyone":
            content = "@everyone"
        elif mencion == "here":
            content = "@here"

        try:
            sent_msg = await canal.send(content=content, embed=embed)
            await interaction.followup.send(embed=success_embed(
                "Anuncio Publicado",
                f"El comunicado se ha emitido correctamente en {canal.mention}.\n[Ver Anuncio Publicado]({sent_msg.jump_url})"
            ), ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(embed=error_embed(
                "Falta de Permisos",
                f"El bot no cuenta con permisos para enviar mensajes en {canal.mention}."
            ), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(embed=error_embed("Error", f"No se pudo enviar el anuncio: {e}"), ephemeral=True)

    # ==========================================
    # COMANDO 3: /anuncio rapido
    # ==========================================
    @announcement_group.command(name="rapido", description="Publica un anuncio rápido en el canal actual o seleccionado")
    @app_commands.describe(
        titulo="Título breve del anuncio",
        mensaje="Mensaje del anuncio",
        canal="Canal destino (opcional, por defecto el canal actual)"
    )
    async def anuncio_rapido(
        self,
        interaction: discord.Interaction,
        titulo: str,
        mensaje: str,
        canal: discord.TextChannel = None
    ):
        target = canal or interaction.channel
        await interaction.response.defer(ephemeral=True)

        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin Permisos", "Solo administradores pueden emitir anuncios."), ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📢 {titulo.strip()}",
            description=mensaje.replace("\\n", "\n").strip(),
            color=0x00E5FF
        )
        embed.set_footer(text=f"Emitido por {interaction.user.display_name} • Miami Vice RP")
        embed.timestamp = discord.utils.utcnow()

        try:
            sent = await target.send(embed=embed)
            await interaction.followup.send(embed=success_embed(
                "Anuncio Rápido Publicado",
                f"Se publicó en {target.mention}: [Ir al mensaje]({sent.jump_url})"
            ), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(embed=error_embed("Error", f"No se pudo publicar: {e}"), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Announcements(bot))
