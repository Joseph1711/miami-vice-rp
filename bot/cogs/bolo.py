import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging

from bot.db import aexecute
from bot.helpers import (
    generate_id,
    generate_unique_bolo_code,
    is_officer_or_admin,
    parse_db_datetime
)
from bot.embeds import success_embed, error_embed, info_embed, COLOR_PRIMARY, COLOR_ERROR, COLOR_WARNING, COLOR_SUCCESS

logger = logging.getLogger("bot.bolo")

DANGER_META = {
    "baja": {"label": "🟢 Baja / Sin Resistencia Armada Conocida", "color": 0x2ECC71, "emoji": "🟢"},
    "media": {"label": "🟡 Media / Posible Resistencia", "color": 0xF1C40F, "emoji": "🟡"},
    "alta": {"label": "🟠 Alta / Armado y Peligroso", "color": 0xE67E22, "emoji": "🟠"},
    "extrema": {"label": "🔴 EXTREMA / Extremadamente Armado y Violento", "color": 0xE74C3C, "emoji": "🔴"}
}

TARGET_META = {
    "suspect": {"emoji": "👤", "label": "Sospechoso / Prófugo de la Justicia"},
    "vehicle": {"emoji": "🚗", "label": "Vehículo Involucrado en Delito"},
    "weapon": {"emoji": "🔫", "label": "Arma Buscada / Prueba Balística"},
    "other": {"emoji": "⚠️", "label": "Alerta General / Objeto Buscado"}
}


class Bolo(commands.Cog):
    """Sistema BOLO (Be On the Lookout) — Órdenes de Búsqueda y Captura de Miami Vice."""

    bolo_group = app_commands.Group(
        name="bolo",
        description="Sistema de Órdenes de Búsqueda y Captura (B.O.L.O.) de las fuerzas de seguridad"
    )

    def __init__(self, bot):
        self.bot = bot

    # ==========================================
    # COMANDO 1: /bolo emitir
    # ==========================================
    @bolo_group.command(name="emitir", description="Emite una orden oficial de búsqueda y captura (BOLO) policial")
    @app_commands.describe(
        tipo="Tipo de objetivo del BOLO",
        identificador="Nombre del sospechoso, modelo/placa del auto o serie del arma",
        motivo="Cargos criminales, delitos imputados o motivo de la alerta",
        peligrosidad="Nivel de amenaza y peligrosidad del objetivo",
        recompensa="Monto de recompensa en dinero ofrecida por información (opcional)",
        imagen_url="Enlace directo a fotografía del sospechoso o vehículo (opcional)"
    )
    @app_commands.choices(
        tipo=[
            app_commands.Choice(name="👤 Sospechoso / Prófugo de la Justicia", value="suspect"),
            app_commands.Choice(name="🚗 Vehículo Sospechoso / En Fuga", value="vehicle"),
            app_commands.Choice(name="🔫 Arma / Elemento de Delito", value="weapon"),
            app_commands.Choice(name="⚠️ Alerta General / Otro", value="other")
        ],
        peligrosidad=[
            app_commands.Choice(name="🟢 Baja — Sin resistencia armada conocida", value="baja"),
            app_commands.Choice(name="🟡 Media — Posible resistencia", value="media"),
            app_commands.Choice(name="🟠 Alta — Armado y peligroso", value="alta"),
            app_commands.Choice(name="🔴 Extrema — Extremadamente violento / Tiroteo", value="extrema")
        ]
    )
    async def bolo_emitir(
        self,
        interaction: discord.Interaction,
        tipo: str,
        identificador: str,
        motivo: str,
        peligrosidad: str = "media",
        recompensa: float = 0.0,
        imagen_url: str = None
    ):
        await interaction.response.defer()
        if not await is_officer_or_admin(interaction):
            await interaction.followup.send(embed=error_embed(
                "Acceso Denegado",
                "Solo oficiales de policía, agentes de justicia o administradores autorizados pueden emitir alertas BOLO."
            ), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)
        bolo_id = generate_id()
        bolo_code = await generate_unique_bolo_code(gid)

        clean_name = identificador.strip()
        clean_reason = motivo.strip()
        clean_reward = max(0.0, float(recompensa))

        await aexecute(
            """INSERT INTO police_bolos 
               (id, guild_id, bolo_code, target_type, target_name, reason, danger_level, reward, image_url, status, officer_id, officer_name, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'active', $10, $11, NOW(), NOW())""",
            (bolo_id, gid, bolo_code, tipo, clean_name, clean_reason, peligrosidad, clean_reward, imagen_url, uid, interaction.user.display_name)
        )

        d_info = DANGER_META.get(peligrosidad, DANGER_META["media"])
        t_info = TARGET_META.get(tipo, TARGET_META["other"])

        embed = discord.Embed(
            title=f"🚨 [B.O.L.O. ACTIVO] — CÓDIGO {bolo_code}",
            description=f"**ALERTA DE BÚSQUEDA Y CAPTURA EMITIDA POR EL CUERPO POLICIAL**\nSe solicita a todas las patrullas en servicio interceptar y reportar la siguiente unidad/sujeto.",
            color=d_info["color"]
        )

        embed.add_field(name="🏷️ Código BOLO", value=f"```fix\n{bolo_code}\n```", inline=True)
        embed.add_field(name="🎯 Tipo de Objetivo", value=f"{t_info['emoji']} {t_info['label']}", inline=True)
        embed.add_field(name="⚠️ Nivel de Amenaza", value=f"{d_info['label']}", inline=False)

        embed.add_field(name="📋 Identificador / Sujeto", value=f"**{clean_name}**", inline=False)
        embed.add_field(name="⚖️ Motivo & Delitos Imputados", value=f"{clean_reason}", inline=False)

        if clean_reward > 0:
            embed.add_field(name="💰 Recompensa Ciudadana", value=f"**${clean_reward:,.2f}** por información verificable", inline=True)

        embed.add_field(name="👮 Oficial Emisor", value=f"{interaction.user.mention} (`{interaction.user.display_name}`)", inline=True)

        if imagen_url and (imagen_url.startswith("http://") or imagen_url.startswith("https://")):
            embed.set_image(url=imagen_url)

        embed.set_footer(text=f"Miami Vice Law Enforcement • Depto. de Investigaciones • ID: {bolo_id[:8]}")
        embed.timestamp = discord.utils.utcnow()

        await interaction.followup.send(embed=embed)

    # ==========================================
    # COMANDO 2: /bolo lista
    # ==========================================
    @bolo_group.command(name="lista", description="Consulta las órdenes BOLO activas o en historial de la ciudad")
    @app_commands.describe(
        estado="Filtrar por estado de la orden",
        tipo="Filtrar por tipo de objetivo"
    )
    @app_commands.choices(
        estado=[
            app_commands.Choice(name="🟢 Solo Activos (En Búsqueda)", value="active"),
            app_commands.Choice(name="🔒 Capturados / Resueltos", value="captured"),
            app_commands.Choice(name="⚪ Cancelados", value="cancelled"),
            app_commands.Choice(name="📋 Todos los BOLO", value="todos")
        ],
        tipo=[
            app_commands.Choice(name="Todos los tipos", value="todos"),
            app_commands.Choice(name="👤 Sospechosos", value="suspect"),
            app_commands.Choice(name="🚗 Vehículos", value="vehicle"),
            app_commands.Choice(name="🔫 Armas", value="weapon")
        ]
    )
    async def bolo_lista(self, interaction: discord.Interaction, estado: str = "active", tipo: str = "todos"):
        await interaction.response.defer()
        gid = str(interaction.guild_id)

        query = "SELECT * FROM police_bolos WHERE guild_id=$1"
        params = [gid]

        if estado != "todos":
            query += f" AND status=${len(params)+1}"
            params.append(estado)

        if tipo != "todos":
            query += f" AND target_type=${len(params)+1}"
            params.append(tipo)

        query += " ORDER BY created_at DESC LIMIT 15"

        rows = await aexecute(query, tuple(params), fetch="all") or []

        if not rows:
            await interaction.followup.send(embed=info_embed(
                "Sin B.O.L.O. Registrados",
                f"No hay órdenes de búsqueda registradas con los filtros seleccionados (Estado: `{estado}`, Tipo: `{tipo}`)."
            ), ephemeral=True)
            return

        embed = info_embed(
            f"Boletín de Órdenes B.O.L.O. — Miami Vice Police",
            f"Se encontraron **{len(rows)}** órdenes de búsqueda y captura en el archivo policial:"
        )

        status_tags = {
            "active": "🚨 ACTIVO (Buscado)",
            "captured": "🔒 CAPTURADO / RESUELTO",
            "cancelled": "⚪ CANCELADO",
            "resolved": "✅ RESUELTO"
        }

        for row in rows:
            b_code = row.get("bolo_code", "BOLO-????")
            b_type = row.get("target_type", "other")
            t_info = TARGET_META.get(b_type, TARGET_META["other"])
            name = row.get("target_name", "Sin Nombre")
            danger = row.get("danger_level", "media")
            d_info = DANGER_META.get(danger, DANGER_META["media"])
            st = row.get("status", "active")
            st_text = status_tags.get(st, st.upper())
            officer = row.get("officer_name") or f"<@{row.get('officer_id')}>"
            reward = float(row.get("reward", 0))

            field_val = (
                f"**Objetivo:** {name}\n"
                f"**Peligrosidad:** {d_info['emoji']} {danger.capitalize()} | **Estado:** `{st_text}`\n"
                f"**Motivo:** {row.get('reason', 'N/A')[:100]}\n"
                f"**Emisor:** {officer}"
            )
            if reward > 0:
                field_val += f" | 💰 Recompensa: `${reward:,.2f}`"

            embed.add_field(
                name=f"{t_info['emoji']} [{b_code}] — {name[:30]}",
                value=field_val,
                inline=False
            )

        embed.set_footer(text="Miami Vice Police Department • Usa /bolo ver [codigo] para ver la ficha completa")
        await interaction.followup.send(embed=embed)

    # ==========================================
    # COMANDO 3: /bolo ver
    # ==========================================
    @bolo_group.command(name="ver", description="Consulta la ficha detallada de una orden BOLO por su código")
    @app_commands.describe(codigo="Código oficial del BOLO (ej: BOLO-4892)")
    async def bolo_ver(self, interaction: discord.Interaction, codigo: str):
        await interaction.response.defer()
        gid = str(interaction.guild_id)
        clean_code = codigo.strip().upper()

        row = await aexecute(
            "SELECT * FROM police_bolos WHERE guild_id=$1 AND UPPER(bolo_code)=$2",
            (gid, clean_code), fetch="one"
        )

        if not row:
            await interaction.followup.send(embed=error_embed(
                "B.O.L.O. No Encontrado",
                f"No se encontró ninguna orden de búsqueda con el código `{clean_code}`. Verifica el número."
            ), ephemeral=True)
            return

        d_info = DANGER_META.get(row.get("danger_level", "media"), DANGER_META["media"])
        t_info = TARGET_META.get(row.get("target_type", "other"), TARGET_META["other"])
        st = row.get("status", "active")

        embed = discord.Embed(
            title=f"🚨 Ficha Policial B.O.L.O. — {row.get('bolo_code')}",
            description=f"Expediente oficial de búsqueda emitido por las autoridades de Miami Vice.",
            color=d_info["color"]
        )

        embed.add_field(name="🏷️ Código de Orden", value=f"```fix\n{row.get('bolo_code')}\n```", inline=True)
        embed.add_field(name="🎯 Tipo de Objetivo", value=f"{t_info['emoji']} {t_info['label']}", inline=True)
        embed.add_field(name="⚠️ Nivel de Peligrosidad", value=f"{d_info['label']}", inline=False)

        embed.add_field(name="📋 Identificador / Sujeto", value=f"**{row.get('target_name')}**", inline=False)
        embed.add_field(name="⚖️ Cargos y Motivo de Búsqueda", value=f"{row.get('reason')}", inline=False)

        status_str = {
            "active": "🚨 ACTIVO — En Búsqueda Inmediata",
            "captured": "🔒 CAPTURADO / BAJO CUSTODIA",
            "cancelled": "⚪ CANCELADO POR OFICIAL A CARGO",
            "resolved": "✅ RESUELTO"
        }.get(st, st.upper())

        embed.add_field(name="📊 Estado Actual", value=f"**{status_str}**", inline=True)

        reward = float(row.get("reward", 0))
        if reward > 0:
            embed.add_field(name="💰 Recompensa", value=f"**${reward:,.2f}**", inline=True)

        embed.add_field(name="👮 Oficial a Cargo", value=f"<@{row.get('officer_id')}> (`{row.get('officer_name')}`)", inline=False)

        if row.get("resolution_notes"):
            embed.add_field(name="📝 Notas de Cierre / Resolución", value=f"*{row.get('resolution_notes')}*", inline=False)

        img = row.get("image_url")
        if img and (img.startswith("http://") or img.startswith("https://")):
            embed.set_image(url=img)

        dt = parse_db_datetime(row.get("created_at"))
        dt_str = dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "Reciente"
        embed.set_footer(text=f"Miami Vice Police • Fecha de Emisión: {dt_str}")
        embed.timestamp = discord.utils.utcnow()

        await interaction.followup.send(embed=embed)

    # ==========================================
    # COMANDO 4: /bolo actualizar
    # ==========================================
    @bolo_group.command(name="actualizar", description="[STAFF/POLICÍA] Actualiza el estado de una orden BOLO (Capturado / Cancelado)")
    @app_commands.describe(
        codigo="Código de la orden BOLO a actualizar",
        nuevo_estado="Nuevo estado de la orden",
        notas="Detalles de la captura, resolución o motivo de cancelación"
    )
    @app_commands.choices(nuevo_estado=[
        app_commands.Choice(name="🔒 CAPTURADO / Sujeto en Custodia", value="captured"),
        app_commands.Choice(name="⚪ CANCELADO / Retirar de Búsqueda", value="cancelled"),
        app_commands.Choice(name="🚨 REACTIVAR / En Búsqueda", value="active")
    ])
    async def bolo_actualizar(
        self,
        interaction: discord.Interaction,
        codigo: str,
        nuevo_estado: str,
        notas: str = "Actualización rutinaria de expediente"
    ):
        await interaction.response.defer()
        if not await is_officer_or_admin(interaction):
            await interaction.followup.send(embed=error_embed(
                "Sin Permisos",
                "Solo oficiales de policía o administradores autorizados pueden actualizar el estado de un BOLO."
            ), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        clean_code = codigo.strip().upper()

        row = await aexecute(
            "SELECT * FROM police_bolos WHERE guild_id=$1 AND UPPER(bolo_code)=$2",
            (gid, clean_code), fetch="one"
        )
        if not row:
            await interaction.followup.send(embed=error_embed(
                "B.O.L.O. No Encontrado",
                f"No se encontró ninguna orden de búsqueda con el código `{clean_code}`."
            ), ephemeral=True)
            return

        await aexecute(
            """UPDATE police_bolos 
               SET status=$1, resolution_notes=$2, resolved_by=$3, updated_at=NOW() 
               WHERE id=$4""",
            (nuevo_estado, notas.strip(), interaction.user.display_name, row["id"])
        )

        status_text = {
            "captured": "🔒 Marcado como CAPTURADO / EN CUSTODIA",
            "cancelled": "⚪ Marcado como CANCELADO",
            "active": "🚨 REACTIVADO / EN BÚSQUEDA"
        }.get(nuevo_estado, nuevo_estado)

        embed = success_embed(
            "Orden B.O.L.O. Actualizada",
            f"La orden **{row.get('bolo_code')}** ({row.get('target_name')}) ha sido actualizada:\n\n"
            f"📊 **Nuevo Estado:** {status_text}\n"
            f"📝 **Notas:** {notas.strip()}\n"
            f"👮 **Agente Responsable:** {interaction.user.mention}"
        )
        embed.set_footer(text="Miami Vice Police Department • Registro Central")

        await interaction.followup.send(embed=embed)

    # ==========================================
    # COMANDO 5: /bolo borrar
    # ==========================================
    @bolo_group.command(name="borrar", description="[ADMIN/COMANDO] Elimina permanentemente una orden BOLO del sistema")
    @app_commands.describe(codigo="Código de la orden BOLO a eliminar")
    async def bolo_borrar(self, interaction: discord.Interaction, codigo: str):
        await interaction.response.defer(ephemeral=True)
        if not await is_officer_or_admin(interaction):
            await interaction.followup.send(embed=error_embed("Sin Permisos", "Solo el alto mando policial o administración puede borrar expedientes."), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        clean_code = codigo.strip().upper()

        res = await aexecute("DELETE FROM police_bolos WHERE guild_id=$1 AND UPPER(bolo_code)=$2", (gid, clean_code), fetch="count")
        if res == 0:
            await interaction.followup.send(embed=error_embed("No Encontrado", f"No existe la orden `{clean_code}`."), ephemeral=True)
            return

        await interaction.followup.send(embed=success_embed(
            "B.O.L.O. Eliminado",
            f"La orden `{clean_code}` ha sido eliminada definitivamente de la base de datos."
        ), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Bolo(bot))
