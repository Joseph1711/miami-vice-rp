import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging

from bot.db import aexecute
from bot.helpers import (
    generate_id,
    generate_unique_incident_code,
    is_officer_or_admin,
    parse_db_datetime
)
from bot.embeds import success_embed, error_embed, info_embed, COLOR_PRIMARY, COLOR_ERROR, COLOR_WARNING, COLOR_SUCCESS

logger = logging.getLogger("bot.incidents")

INCIDENT_TYPES = {
    "911_emergencia": {"emoji": "🚨", "label": "Llamada de Emergencia 911"},
    "tiroteo": {"emoji": "💥", "label": "Tiroteo / Disparos Reportados (10-71)"},
    "robo": {"emoji": "💰", "label": "Robo / Atraco en Curso (10-90)"},
    "persecucion": {"emoji": "🚔", "label": "Persecución Vehicular (10-80)"},
    "accidente": {"emoji": "🚗", "label": "Accidente de Tránsito / Choque (10-50)"},
    "altercado": {"emoji": "🥊", "label": "Disturbio / Pelea Callejera (10-15)"},
    "patrullaje": {"emoji": "👮", "label": "Control de Tráfico / Parada (10-38)"},
    "medico": {"emoji": "🚑", "label": "Emergencia Médica / RCP / MDFR (10-52)"},
    "incendio": {"emoji": "🚒", "label": "Incendio Estructural / Bomberos (10-70)"},
    "otro": {"emoji": "⚠️", "label": "Incidente General"}
}

PRIORITY_CODES = {
    "codigo_1": {"label": "Código 1 — Rutinario (Sin sirenas)", "emoji": "🟢", "color": 0x2ECC71},
    "codigo_2": {"label": "Código 2 — Urgente (Luces de emergencia)", "emoji": "🟡", "color": 0xF1C40F},
    "codigo_3": {"label": "Código 3 — EMERGENCIA MÁXIMA (Sirenas y luces / 10-99)", "emoji": "🔴", "color": 0xE74C3C}
}

STATUS_MAP = {
    "activo": "🚨 PENDIENTE DE DESPACHO",
    "en_proceso": "🚔 UNIDADES EN CAMINO / ATENDIENDO",
    "atendido": "🟢 EN ESCENA / CONTROLADO",
    "cerrado": "🔒 RESUELTO Y CERRADO"
}


class Incidents(commands.Cog):
    """Sistema de Incidentes, Central 911 y Despacho de Emergencias de Miami Vice."""

    incident_group = app_commands.Group(
        name="incidente",
        description="Sistema de despacho de emergencias, llamadas 911 y reportes de incidentes policiales/médicos"
    )

    def __init__(self, bot):
        self.bot = bot

    # ==========================================
    # COMANDO 1: /incidente crear
    # ==========================================
    @incident_group.command(name="crear", description="Genera un reporte de incidente o llamada de emergencia 911")
    @app_commands.describe(
        tipo="Tipo de incidente o delito en curso",
        ubicacion="Dirección, calle, barrio o punto de referencia en Miami",
        descripcion="Detalles de la situación, sospechosos armados o víctimas",
        prioridad="Código de prioridad de respuesta"
    )
    @app_commands.choices(
        tipo=[
            app_commands.Choice(name="🚨 Llamada 911 de Emergencia", value="911_emergencia"),
            app_commands.Choice(name="💥 Disparos / Tiroteo (10-71)", value="tiroteo"),
            app_commands.Choice(name="💰 Robo / Atraco en Curso (10-90)", value="robo"),
            app_commands.Choice(name="🚔 Persecución Vehicular (10-80)", value="persecucion"),
            app_commands.Choice(name="🚗 Accidente de Tránsito (10-50)", value="accidente"),
            app_commands.Choice(name="🥊 Pelea / Altercado Civil (10-15)", value="altercado"),
            app_commands.Choice(name="🚑 Emergencia Médica / EMS (10-52)", value="medico"),
            app_commands.Choice(name="🚒 Incendio / Bomberos MDFR (10-70)", value="incendio"),
            app_commands.Choice(name="⚠️ Otro Incidente", value="otro")
        ],
        prioridad=[
            app_commands.Choice(name="🟢 Código 1 — Rutinario", value="codigo_1"),
            app_commands.Choice(name="🟡 Código 2 — Urgente", value="codigo_2"),
            app_commands.Choice(name="🔴 Código 3 — Emergencia Máxima (10-99)", value="codigo_3")
        ]
    )
    async def incidente_crear(
        self,
        interaction: discord.Interaction,
        tipo: str,
        ubicacion: str,
        descripcion: str,
        prioridad: str = "codigo_2"
    ):
        await interaction.response.defer()
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)
        inc_id = generate_id()
        inc_code = await generate_unique_incident_code(gid)

        clean_loc = ubicacion.strip()
        clean_desc = descripcion.strip()

        await aexecute(
            """INSERT INTO police_incidents
               (id, guild_id, incident_code, incident_type, location, description, priority_code, caller_id, caller_name, status, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'activo', NOW(), NOW())""",
            (inc_id, gid, inc_code, tipo, clean_loc, clean_desc, prioridad, uid, interaction.user.display_name)
        )

        t_info = INCIDENT_TYPES.get(tipo, INCIDENT_TYPES["otro"])
        p_info = PRIORITY_CODES.get(prioridad, PRIORITY_CODES["codigo_2"])

        embed = discord.Embed(
            title=f"🚨 [CAD / 911 DESPATCH] — INCIDENTE #{inc_code}",
            description="**ALERTA DE DESPACHO POLICIAL & SERVICIOS DE EMERGENCIA**\nSe ha emitido un nuevo reporte en la central operativa.",
            color=p_info["color"]
        )

        embed.add_field(name="🔢 Código de Incidente", value=f"```fix\n{inc_code}\n```", inline=True)
        embed.add_field(name="📋 Tipo de Evento", value=f"{t_info['emoji']} {t_info['label']}", inline=True)
        embed.add_field(name="⚡ Prioridad de Respuesta", value=f"{p_info['emoji']} {p_info['label']}", inline=False)

        embed.add_field(name="📍 Ubicación de los Hechos", value=f"**{clean_loc}**", inline=False)
        embed.add_field(name="📝 Detalles / Informe Inicial", value=f"{clean_desc}", inline=False)

        embed.add_field(name="📞 Informante / Despachador", value=f"{interaction.user.mention} (`{interaction.user.display_name}`)", inline=True)
        embed.add_field(name="📊 Estado", value="🚨 `PENDIENTE DE ASIGNACIÓN`", inline=True)

        embed.set_footer(text="Miami Vice 911 Emergency Communications • Todas las unidades disponibles acudan al llamado")
        embed.timestamp = discord.utils.utcnow()

        await interaction.followup.send(embed=embed)

    # ==========================================
    # COMANDO 2: /incidente lista
    # ==========================================
    @incident_group.command(name="lista", description="Consulta la central de incidentes activos o despachos recientes")
    @app_commands.describe(
        estado="Filtrar por estado del incidente",
        tipo="Filtrar por tipo de incidente"
    )
    @app_commands.choices(
        estado=[
            app_commands.Choice(name="🚨 Solo Activos / En Curso", value="activos"),
            app_commands.Choice(name="🔒 Cerrados / Atendidos", value="cerrado"),
            app_commands.Choice(name="📋 Todos los Incidentes", value="todos")
        ]
    )
    async def incidente_lista(self, interaction: discord.Interaction, estado: str = "activos", tipo: str = "todos"):
        await interaction.response.defer()
        gid = str(interaction.guild_id)

        query = "SELECT * FROM police_incidents WHERE guild_id=$1"
        params = [gid]

        if estado == "activos":
            query += " AND status IN ('activo', 'en_proceso', 'atendido')"
        elif estado != "todos":
            query += f" AND status=${len(params)+1}"
            params.append(estado)

        query += " ORDER BY created_at DESC LIMIT 15"

        rows = await aexecute(query, tuple(params), fetch="all") or []

        if not rows:
            await interaction.followup.send(embed=info_embed(
                "Sin Incidentes en Central",
                f"No hay reportes de incidentes con los filtros seleccionados (Estado: `{estado}`)."
            ), ephemeral=True)
            return

        embed = info_embed(
            "Central de Despacho 911 & Incidentes — Miami Vice",
            f"Mostrando **{len(rows)}** reportes de incidentes operativos:"
        )

        for row in rows:
            i_code = row.get("incident_code", "INC-????")
            i_type = row.get("incident_type", "otro")
            t_info = INCIDENT_TYPES.get(i_type, INCIDENT_TYPES["otro"])
            loc = row.get("location", "Ubicación desconocida")
            st = row.get("status", "activo")
            st_text = STATUS_MAP.get(st, st.upper())
            prio = row.get("priority_code", "codigo_2")
            p_info = PRIORITY_CODES.get(prio, PRIORITY_CODES["codigo_2"])
            units = row.get("assigned_units") or "Sin unidades asignadas"

            embed.add_field(
                name=f"{t_info['emoji']} [{i_code}] — {loc[:35]}",
                value=(
                    f"**Evento:** {t_info['label']} | **Prioridad:** {p_info['emoji']}\n"
                    f"**Estado:** `{st_text}`\n"
                    f"**Unidades:** 🚔 {units}\n"
                    f"**Detalles:** {row.get('description', '')[:70]}..."
                ),
                inline=False
            )

        embed.set_footer(text="Usa /incidente ver [codigo] o /incidente atender [codigo] para responder")
        await interaction.followup.send(embed=embed)

    # ==========================================
    # COMANDO 3: /incidente ver
    # ==========================================
    @incident_group.command(name="ver", description="Consulta el reporte detallado de un incidente")
    @app_commands.describe(codigo="Código del incidente (ej: INC-7391)")
    async def incidente_ver(self, interaction: discord.Interaction, codigo: str):
        await interaction.response.defer()
        gid = str(interaction.guild_id)
        clean_code = codigo.strip().upper()

        row = await aexecute(
            "SELECT * FROM police_incidents WHERE guild_id=$1 AND UPPER(incident_code)=$2",
            (gid, clean_code), fetch="one"
        )

        if not row:
            await interaction.followup.send(embed=error_embed(
                "Incidente No Encontrado",
                f"No se encontró ningún reporte con el código `{clean_code}`."
            ), ephemeral=True)
            return

        i_type = row.get("incident_type", "otro")
        t_info = INCIDENT_TYPES.get(i_type, INCIDENT_TYPES["otro"])
        prio = row.get("priority_code", "codigo_2")
        p_info = PRIORITY_CODES.get(prio, PRIORITY_CODES["codigo_2"])
        st = row.get("status", "activo")
        st_text = STATUS_MAP.get(st, st.upper())

        embed = discord.Embed(
            title=f"📋 Reporte de Incidente Operativo — {row.get('incident_code')}",
            description=f"**{t_info['emoji']} {t_info['label']}**",
            color=p_info["color"]
        )

        embed.add_field(name="📍 Ubicación", value=f"**{row.get('location')}**", inline=False)
        embed.add_field(name="⚡ Código de Respuesta", value=f"{p_info['emoji']} {p_info['label']}", inline=True)
        embed.add_field(name="📊 Estado Operativo", value=f"**{st_text}**", inline=True)

        embed.add_field(name="📝 Informe / Descripción", value=f"{row.get('description')}", inline=False)

        units = row.get("assigned_units") or "Ninguna unidad en escena"
        embed.add_field(name="🚔 Unidades en Respuesta", value=f"*{units}*", inline=False)

        embed.add_field(name="📞 Reportado Por", value=f"<@{row.get('caller_id')}> (`{row.get('caller_name')}`)", inline=True)

        if row.get("resolution_report"):
            embed.add_field(name="🔒 Informe de Cierre", value=f"*{row.get('resolution_report')}*", inline=False)

        dt = parse_db_datetime(row.get("created_at"))
        dt_str = dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "Reciente"
        embed.set_footer(text=f"Miami Vice CAD / MDT Dispatch • Hora de Apertura: {dt_str}")

        await interaction.followup.send(embed=embed)

    # ==========================================
    # COMANDO 4: /incidente atender
    # ==========================================
    @incident_group.command(name="atender", description="[POLICÍA/EMS] Asigna patrullas o responde al llamado de emergencia")
    @app_commands.describe(
        codigo="Código del incidente (ej: INC-7391)",
        unidades="Indicativo de las unidades asignadas (ej: Unidad 10-4, Adam-12, MDFR Rescue 3)"
    )
    async def incidente_atender(self, interaction: discord.Interaction, codigo: str, unidades: str):
        await interaction.response.defer()
        if not await is_officer_or_admin(interaction):
            await interaction.followup.send(embed=error_embed("Sin Permisos", "Solo oficiales o socorristas pueden tomar despachos de emergencia."), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        clean_code = codigo.strip().upper()

        row = await aexecute("SELECT * FROM police_incidents WHERE guild_id=$1 AND UPPER(incident_code)=$2", (gid, clean_code), fetch="one")
        if not row:
            await interaction.followup.send(embed=error_embed("No Encontrado", f"No existe el incidente `{clean_code}`."), ephemeral=True)
            return

        current_units = row.get("assigned_units") or ""
        new_units = f"{current_units}, {unidades.strip()}" if current_units else unidades.strip()

        await aexecute(
            "UPDATE police_incidents SET status='en_proceso', assigned_units=$1, updated_at=NOW() WHERE id=$2",
            (new_units, row["id"])
        )

        embed = success_embed(
            "🚔 Unidades en Camino al Incidente",
            f"El incidente **{clean_code}** en **{row.get('location')}** ha sido tomado:\n\n"
            f"🚔 **Unidades Despachadas:** {new_units}\n"
            f"👮 **Oficial al Mando:** {interaction.user.mention} (10-76 En Ruta)"
        )
        await interaction.followup.send(embed=embed)

    # ==========================================
    # COMANDO 5: /incidente cerrar
    # ==========================================
    @incident_group.command(name="cerrar", description="[POLICÍA/STAFF] Cierra y archiva el reporte de incidente tras resolverlo")
    @app_commands.describe(
        codigo="Código del incidente (ej: INC-7391)",
        informe_final="Informe de cierre, resultado del procedimiento o arrestos realizados"
    )
    async def incidente_cerrar(self, interaction: discord.Interaction, codigo: str, informe_final: str):
        await interaction.response.defer()
        if not await is_officer_or_admin(interaction):
            await interaction.followup.send(embed=error_embed("Sin Permisos", "Solo agentes autorizados pueden cerrar incidentes."), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        clean_code = codigo.strip().upper()

        row = await aexecute("SELECT * FROM police_incidents WHERE guild_id=$1 AND UPPER(incident_code)=$2", (gid, clean_code), fetch="one")
        if not row:
            await interaction.followup.send(embed=error_embed("No Encontrado", f"No existe el incidente `{clean_code}`."), ephemeral=True)
            return

        await aexecute(
            """UPDATE police_incidents 
               SET status='cerrado', resolution_report=$1, closed_by=$2, updated_at=NOW() 
               WHERE id=$3""",
            (informe_final.strip(), interaction.user.display_name, row["id"])
        )

        embed = success_embed(
            "Incidente Resuelto y Cerrado (10-99)",
            f"El incidente **{clean_code}** ({row.get('location')}) ha sido cerrado en el sistema central:\n\n"
            f"📝 **Informe Final:** {informe_final.strip()}\n"
            f"👮 **Cerrado Por:** {interaction.user.mention}"
        )
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Incidents(bot))
