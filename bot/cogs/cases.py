import discord
from discord import app_commands
from discord.ext import commands
import json
import datetime
import logging

from bot.db import aexecute
from bot.helpers import (
    generate_id,
    generate_unique_case_number,
    is_officer_or_admin,
    parse_db_datetime
)
from bot.embeds import success_embed, error_embed, info_embed, COLOR_PRIMARY, COLOR_ERROR, COLOR_WARNING, COLOR_SUCCESS

logger = logging.getLogger("bot.cases")

CATEGORY_META = {
    "homicidio": {"emoji": "💀", "label": "Homicidio / Asesinato"},
    "narcotrafico": {"emoji": "💊", "label": "Narcotráfico / Sustancias Ilícitas"},
    "robo": {"emoji": "💰", "label": "Robo / Atraco a Mano Armada"},
    "crimen_organizado": {"emoji": "🕶️", "label": "Crimen Organizado / Mafias / Cartel"},
    "corrupcion": {"emoji": "🏛️", "label": "Corrupción Estatal / Asuntos Internos"},
    "fraude": {"emoji": "💳", "label": "Fraude / Lavado de Dinero"},
    "secuestro": {"emoji": "⛓️", "label": "Secuestro / Extorsión"},
    "transito": {"emoji": "🚗", "label": "Delitos de Tránsito / Persecución Fatal"},
    "general": {"emoji": "📁", "label": "Investigación General"}
}

PRIORITY_META = {
    "baja": {"emoji": "🟢", "label": "Baja", "color": 0x2ECC71},
    "media": {"emoji": "🟡", "label": "Media", "color": 0xF1C40F},
    "alta": {"emoji": "🟠", "label": "Alta", "color": 0xE67E22},
    "urgente": {"emoji": "🔴", "label": "Urgente / Prioridad Máxima", "color": 0xE74C3C}
}

STATUS_META = {
    "abierto": "🟡 ABIERTO — En Fase Inicial",
    "en_investigacion": "🔍 EN INVESTIGACIÓN ACTIVA",
    "en_juicio": "⚖️ EN JUICIO / TRIBUNALES (DOJ)",
    "cerrado": "🔒 CERRADO / SENTENCIA EMITIDA",
    "archivado": "📁 ARCHIVADO"
}


class Cases(commands.Cog):
    """Sistema de Casos y Expedientes Policiales / Judiciales de Miami Vice."""

    case_group = app_commands.Group(
        name="caso",
        description="Gestión integral de casos de investigación, fiscalía y expedientes judiciales"
    )

    def __init__(self, bot):
        self.bot = bot

    # ==========================================
    # COMANDO 1: /caso abrir
    # ==========================================
    @case_group.command(name="abrir", description="Abre un nuevo expediente o caso de investigación policial/judicial")
    @app_commands.describe(
        titulo="Título descriptivo del caso (ej: Operación Bahía Azul)",
        categoria="Categoría penal del caso",
        prioridad="Nivel de prioridad de la investigación",
        descripcion="Detalles de los hechos, fecha, lugar y móvil del suceso"
    )
    @app_commands.choices(
        categoria=[
            app_commands.Choice(name="💀 Homicidio / Asesinato", value="homicidio"),
            app_commands.Choice(name="💊 Narcotráfico / Sustancias Ilícitas", value="narcotrafico"),
            app_commands.Choice(name="💰 Robo a Mano Armada / Atraco", value="robo"),
            app_commands.Choice(name="🕶️ Crimen Organizado / Carteles", value="crimen_organizado"),
            app_commands.Choice(name="🏛️ Corrupción / Asuntos Internos", value="corrupcion"),
            app_commands.Choice(name="💳 Fraude Financiero / Lavado", value="fraude"),
            app_commands.Choice(name="⛓️ Secuestro / Extorsión", value="secuestro"),
            app_commands.Choice(name="🚗 Delitos de Tránsito / Fuga", value="transito"),
            app_commands.Choice(name="📁 Investigación General", value="general")
        ],
        prioridad=[
            app_commands.Choice(name="🟢 Baja", value="baja"),
            app_commands.Choice(name="🟡 Media", value="media"),
            app_commands.Choice(name="🟠 Alta", value="alta"),
            app_commands.Choice(name="🔴 Urgente / Prioridad Máxima", value="urgente")
        ]
    )
    async def caso_abrir(
        self,
        interaction: discord.Interaction,
        titulo: str,
        categoria: str,
        descripcion: str,
        prioridad: str = "media"
    ):
        await interaction.response.defer()
        if not await is_officer_or_admin(interaction):
            await interaction.followup.send(embed=error_embed(
                "Acceso Denegado",
                "Solo oficiales de policía, detectives, fiscales de justicia o administradores pueden abrir expedientes."
            ), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)
        case_id = generate_id()
        case_number = await generate_unique_case_number(gid)

        clean_title = titulo.strip()
        clean_desc = descripcion.strip()

        # Nota inicial
        initial_note = [{
            "author_id": uid,
            "author_name": interaction.user.display_name,
            "date": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
            "text": f"Apertura formal del expediente por el Detective/Oficial {interaction.user.display_name}."
        }]

        await aexecute(
            """INSERT INTO police_cases
               (id, guild_id, case_number, title, category, priority, description, lead_detective_id, lead_detective_name, status, suspects_json, evidence_json, notes_json, created_at, updated_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'abierto', '[]', '[]', $10, NOW(), NOW())""",
            (case_id, gid, case_number, clean_title, categoria, prioridad, clean_desc, uid, interaction.user.display_name, json.dumps(initial_note))
        )

        p_meta = PRIORITY_META.get(prioridad, PRIORITY_META["media"])
        c_meta = CATEGORY_META.get(categoria, CATEGORY_META["general"])

        embed = discord.Embed(
            title=f"📁 Expediente Penal Abierto — {case_number}",
            description=f"Se ha radicado oficialmente una nueva investigación criminal en el Departamento de Policía / Fiscalía.",
            color=p_meta["color"]
        )

        embed.add_field(name="🔢 Número de Caso", value=f"```fix\n{case_number}\n```", inline=True)
        embed.add_field(name="📑 Categoría", value=f"{c_meta['emoji']} {c_meta['label']}", inline=True)
        embed.add_field(name="⚡ Prioridad", value=f"{p_meta['emoji']} {p_meta['label']}", inline=True)

        embed.add_field(name="📌 Carátula / Título", value=f"**{clean_title}**", inline=False)
        embed.add_field(name="📝 Resumen de los Hechos", value=f"{clean_desc}", inline=False)

        embed.add_field(name="🕵️ Detective Principal a Cargo", value=f"{interaction.user.mention} (`{interaction.user.display_name}`)", inline=True)
        embed.add_field(name="📊 Estado", value="🟡 `ABIERTO`", inline=True)

        embed.set_footer(text="Miami Vice Police Department • División de Investigaciones Criminales")
        embed.timestamp = discord.utils.utcnow()

        await interaction.followup.send(embed=embed)

    # ==========================================
    # COMANDO 2: /caso lista
    # ==========================================
    @case_group.command(name="lista", description="Consulta los casos y expedientes criminales radicados")
    @app_commands.describe(
        estado="Filtrar por estado del caso",
        categoria="Filtrar por categoría"
    )
    @app_commands.choices(
        estado=[
            app_commands.Choice(name="Todos los casos", value="todos"),
            app_commands.Choice(name="🟡 Abiertos", value="abierto"),
            app_commands.Choice(name="🔍 En Investigación Activa", value="en_investigacion"),
            app_commands.Choice(name="⚖️ En Juicio / Tribunal", value="en_juicio"),
            app_commands.Choice(name="🔒 Cerrados", value="cerrado")
        ],
        categoria=[
            app_commands.Choice(name="Todas las categorías", value="todos"),
            app_commands.Choice(name="💀 Homicidio", value="homicidio"),
            app_commands.Choice(name="💊 Narcotráfico", value="narcotrafico"),
            app_commands.Choice(name="💰 Robos", value="robo"),
            app_commands.Choice(name="🕶️ Crimen Organizado", value="crimen_organizado"),
            app_commands.Choice(name="🏛️ Corrupción", value="corrupcion"),
            app_commands.Choice(name="📁 General", value="general")
        ]
    )
    async def caso_lista(self, interaction: discord.Interaction, estado: str = "todos", categoria: str = "todos"):
        await interaction.response.defer()
        gid = str(interaction.guild_id)

        query = "SELECT * FROM police_cases WHERE guild_id=$1"
        params = [gid]

        if estado != "todos":
            query += f" AND status=${len(params)+1}"
            params.append(estado)

        if categoria != "todos":
            query += f" AND category=${len(params)+1}"
            params.append(categoria)

        query += " ORDER BY created_at DESC LIMIT 15"

        rows = await aexecute(query, tuple(params), fetch="all") or []

        if not rows:
            await interaction.followup.send(embed=info_embed(
                "Sin Casos Registrados",
                f"No se encontraron expedientes con los filtros seleccionados (Estado: `{estado}`, Categoría: `{categoria}`)."
            ), ephemeral=True)
            return

        embed = info_embed(
            "Archivo Central de Expedientes — Miami Vice",
            f"Mostrando **{len(rows)}** casos policiales y judiciales:"
        )

        for row in rows:
            c_num = row.get("case_number", "CASO-????")
            c_cat = row.get("category", "general")
            cat_info = CATEGORY_META.get(c_cat, CATEGORY_META["general"])
            title = row.get("title", "Sin Título")
            st = row.get("status", "abierto")
            st_label = STATUS_META.get(st, st.upper())
            prio = row.get("priority", "media")
            p_info = PRIORITY_META.get(prio, PRIORITY_META["media"])
            detective = row.get("lead_detective_name") or f"<@{row.get('lead_detective_id')}>"

            embed.add_field(
                name=f"{cat_info['emoji']} [{c_num}] — {title[:35]}",
                value=(
                    f"**Estado:** {st_label}\n"
                    f"**Prioridad:** {p_info['emoji']} {prio.capitalize()} | **Detective:** {detective}\n"
                    f"**Resumen:** {row.get('description', '')[:90]}..."
                ),
                inline=False
            )

        embed.set_footer(text="Usa /caso ver [numero_caso] para ver el expediente completo con evidencias y sospechosos")
        await interaction.followup.send(embed=embed)

    # ==========================================
    # COMANDO 3: /caso ver
    # ==========================================
    @case_group.command(name="ver", description="Consulta el expediente completo de un caso con sospechosos y pruebas")
    @app_commands.describe(numero_caso="Número de expediente (ej: CASO-2026-7491)")
    async def caso_ver(self, interaction: discord.Interaction, numero_caso: str):
        await interaction.response.defer()
        gid = str(interaction.guild_id)
        clean_num = numero_caso.strip().upper()

        row = await aexecute(
            "SELECT * FROM police_cases WHERE guild_id=$1 AND UPPER(case_number)=$2",
            (gid, clean_num), fetch="one"
        )

        if not row:
            await interaction.followup.send(embed=error_embed(
                "Expediente No Encontrado",
                f"No se encontró ningún caso con el número `{clean_num}`."
            ), ephemeral=True)
            return

        c_cat = row.get("category", "general")
        cat_info = CATEGORY_META.get(c_cat, CATEGORY_META["general"])
        prio = row.get("priority", "media")
        p_info = PRIORITY_META.get(prio, PRIORITY_META["media"])
        st = row.get("status", "abierto")
        st_label = STATUS_META.get(st, st.upper())

        embed = discord.Embed(
            title=f"📁 Expediente Oficial — {row.get('case_number')}",
            description=f"**{row.get('title')}**\n{row.get('description')}",
            color=p_info["color"]
        )

        embed.add_field(name="🏷️ Categoría Penal", value=f"{cat_info['emoji']} {cat_info['label']}", inline=True)
        embed.add_field(name="⚡ Prioridad", value=f"{p_info['emoji']} {p_info['label']}", inline=True)
        embed.add_field(name="📊 Estado", value=f"{st_label}", inline=False)

        embed.add_field(name="🕵️ Detective Principal", value=f"<@{row.get('lead_detective_id')}> (`{row.get('lead_detective_name')}`)", inline=True)

        # Sospechosos
        try:
            suspects = json.loads(row.get("suspects_json") or "[]")
        except Exception:
            suspects = []

        if suspects:
            s_text = ""
            for s in suspects:
                s_text += f"• **{s.get('name')}** — *Cargos:* {s.get('charges')} (Estado: `{s.get('status', 'investigado')}`)\n"
            embed.add_field(name=f"👥 Sospechosos Vinculados ({len(suspects)})", value=s_text[:1000], inline=False)
        else:
            embed.add_field(name="👥 Sospechosos Vinculados", value="*Sin sospechosos imputados aún.*", inline=False)

        # Evidencias
        try:
            evidence = json.loads(row.get("evidence_json") or "[]")
        except Exception:
            evidence = []

        if evidence:
            e_text = ""
            for e in evidence:
                e_text += f"• [{e.get('type', 'Prueba').upper()}] **{e.get('description')}** ({e.get('serial_or_detail', 'S/N')})\n"
            embed.add_field(name=f"📦 Pruebas & Evidencias Forenses ({len(evidence)})", value=e_text[:1000], inline=False)
        else:
            embed.add_field(name="📦 Pruebas & Evidencias Forenses", value="*Sin evidencias registradas aún.*", inline=False)

        # Notas de investigación
        try:
            notes = json.loads(row.get("notes_json") or "[]")
        except Exception:
            notes = []

        if notes:
            n_text = ""
            for n in notes[-5:]: # Últimas 5 notas
                n_text += f"🗓️ **{n.get('date')}** | `{n.get('author_name')}`: {n.get('text')}\n"
            embed.add_field(name=f"📝 Diario de Investigación ({len(notes)} notas)", value=n_text[:1000], inline=False)

        if row.get("verdict"):
            embed.add_field(name="⚖️ Veredicto / Resolución Judicial", value=f"```fix\n{row.get('verdict')}\n```", inline=False)

        dt = parse_db_datetime(row.get("created_at"))
        dt_str = dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "Reciente"
        embed.set_footer(text=f"Miami Vice Criminal Investigation Division • Radicado: {dt_str}")

        await interaction.followup.send(embed=embed)

    # ==========================================
    # COMANDO 4: /caso nota_agregar
    # ==========================================
    @case_group.command(name="nota_agregar", description="Agrega una nota o avance de investigación al expediente")
    @app_commands.describe(
        numero_caso="Número de expediente (ej: CASO-2026-7491)",
        nota="Texto del avance de investigación, declaración o informe"
    )
    async def caso_nota_agregar(self, interaction: discord.Interaction, numero_caso: str, nota: str):
        await interaction.response.defer()
        if not await is_officer_or_admin(interaction):
            await interaction.followup.send(embed=error_embed("Sin Permisos", "Solo oficiales o administradores pueden actualizar el diario del caso."), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        clean_num = numero_caso.strip().upper()

        row = await aexecute("SELECT * FROM police_cases WHERE guild_id=$1 AND UPPER(case_number)=$2", (gid, clean_num), fetch="one")
        if not row:
            await interaction.followup.send(embed=error_embed("No Encontrado", f"No se encontró el caso `{clean_num}`."), ephemeral=True)
            return

        try:
            notes = json.loads(row.get("notes_json") or "[]")
        except Exception:
            notes = []

        new_entry = {
            "author_id": str(interaction.user.id),
            "author_name": interaction.user.display_name,
            "date": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
            "text": nota.strip()
        }
        notes.append(new_entry)

        await aexecute(
            "UPDATE police_cases SET notes_json=$1, updated_at=NOW() WHERE id=$2",
            (json.dumps(notes), row["id"])
        )

        embed = success_embed(
            "Nota Registrada en Expediente",
            f"Se ha añadido la nota de investigación al caso **{clean_num}** ({row.get('title')}):\n\n"
            f"📝 *\"{nota.strip()}\"*\n\n"
            f"✍️ **Autor:** {interaction.user.mention} | 🗓️ **Fecha:** `{new_entry['date']} UTC`"
        )
        await interaction.followup.send(embed=embed)

    # ==========================================
    # COMANDO 5: /caso sospechoso_vincular
    # ==========================================
    @case_group.command(name="sospechoso_vincular", description="Vincula un sospechoso o imputado al expediente penal")
    @app_commands.describe(
        numero_caso="Número de expediente",
        sospechoso="Nombre del sospechoso o mención de usuario",
        cargos="Cargos penales o delitos imputados",
        estado_sospechoso="Situación legal actual del imputado"
    )
    @app_commands.choices(estado_sospechoso=[
        app_commands.Choice(name="Bajo Investigación", value="investigado"),
        app_commands.Choice(name="Orden de Captura / Prófugo", value="profugo"),
        app_commands.Choice(name="Detenido / En Custodia", value="detenido"),
        app_commands.Choice(name="Procesado / Imputado", value="procesado"),
        app_commands.Choice(name="Absuelto / Descartado", value="absuelto")
    ])
    async def caso_sospechoso_vincular(
        self,
        interaction: discord.Interaction,
        numero_caso: str,
        sospechoso: str,
        cargos: str,
        estado_sospechoso: str = "investigado"
    ):
        await interaction.response.defer()
        if not await is_officer_or_admin(interaction):
            await interaction.followup.send(embed=error_embed("Sin Permisos", "Solo agentes autorizados pueden vincular sospechosos."), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        clean_num = numero_caso.strip().upper()

        row = await aexecute("SELECT * FROM police_cases WHERE guild_id=$1 AND UPPER(case_number)=$2", (gid, clean_num), fetch="one")
        if not row:
            await interaction.followup.send(embed=error_embed("No Encontrado", f"No se encontró el caso `{clean_num}`."), ephemeral=True)
            return

        try:
            suspects = json.loads(row.get("suspects_json") or "[]")
        except Exception:
            suspects = []

        suspects.append({
            "name": sospechoso.strip(),
            "charges": cargos.strip(),
            "status": estado_sospechoso,
            "added_by": interaction.user.display_name,
            "added_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        })

        await aexecute(
            "UPDATE police_cases SET suspects_json=$1, updated_at=NOW() WHERE id=$2",
            (json.dumps(suspects), row["id"])
        )

        embed = success_embed(
            "Sospechoso Vinculado al Caso",
            f"Se ha imputado formalmente a **{sospechoso.strip()}** en el expediente **{clean_num}**:\n\n"
            f"⚖️ **Cargos:** {cargos.strip()}\n"
            f"📊 **Situación:** `{estado_sospechoso.upper()}`\n"
            f"👮 **Agente:** {interaction.user.mention}"
        )
        await interaction.followup.send(embed=embed)

    # ==========================================
    # COMANDO 6: /caso evidencia_vincular
    # ==========================================
    @case_group.command(name="evidencia_vincular", description="Vincula una prueba material, arma, vehículo o documento al expediente")
    @app_commands.describe(
        numero_caso="Número de expediente",
        tipo="Tipo de evidencia",
        descripcion="Descripción de la prueba o hallazgo en la escena",
        serie_o_detalle="Número de serie de arma, placa de auto, DNI o identificador único"
    )
    @app_commands.choices(tipo=[
        app_commands.Choice(name="🔫 Arma de Fuego / Balística", value="arma"),
        app_commands.Choice(name="🚗 Vehículo Implicado", value="vehiculo"),
        app_commands.Choice(name="💊 Sustancia / Narcótico", value="narcotico"),
        app_commands.Choice(name="💵 Dinero / Bien Incautado", value="dinero"),
        app_commands.Choice(name="📄 Documento / Contrato / Registro", value="documento"),
        app_commands.Choice(name="🔬 Prueba Forense / Huella / ADN", value="forense"),
        app_commands.Choice(name="📦 Otro", value="otro")
    ])
    async def caso_evidencia_vincular(
        self,
        interaction: discord.Interaction,
        numero_caso: str,
        tipo: str,
        descripcion: str,
        serie_o_detalle: str = "N/A"
    ):
        await interaction.response.defer()
        if not await is_officer_or_admin(interaction):
            await interaction.followup.send(embed=error_embed("Sin Permisos", "Solo agentes autorizados pueden anexar evidencias a un caso."), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        clean_num = numero_caso.strip().upper()

        row = await aexecute("SELECT * FROM police_cases WHERE guild_id=$1 AND UPPER(case_number)=$2", (gid, clean_num), fetch="one")
        if not row:
            await interaction.followup.send(embed=error_embed("No Encontrado", f"No se encontró el caso `{clean_num}`."), ephemeral=True)
            return

        try:
            evidence = json.loads(row.get("evidence_json") or "[]")
        except Exception:
            evidence = []

        evidence.append({
            "type": tipo,
            "description": descripcion.strip(),
            "serial_or_detail": serie_o_detalle.strip(),
            "logged_by": interaction.user.display_name,
            "logged_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        })

        await aexecute(
            "UPDATE police_cases SET evidence_json=$1, updated_at=NOW() WHERE id=$2",
            (json.dumps(evidence), row["id"])
        )

        embed = success_embed(
            "Evidencia Anexada a la Cadena de Custodia",
            f"Se ha catalogado la prueba en el expediente **{clean_num}**:\n\n"
            f"📦 **Tipo:** `{tipo.upper()}`\n"
            f"📋 **Descripción:** {descripcion.strip()}\n"
            f"🔢 **Serie / Identificador:** `{serie_o_detalle.strip()}`\n"
            f"👮 **Oficial Custodio:** {interaction.user.mention}"
        )
        await interaction.followup.send(embed=embed)

    # ==========================================
    # COMANDO 7: /caso estado
    # ==========================================
    @case_group.command(name="estado", description="[STAFF/JUEZ/DETECTIVE] Actualiza la fase o veredicto final de un expediente")
    @app_commands.describe(
        numero_caso="Número de expediente",
        nuevo_estado="Fase legal del caso",
        veredicto="Sentencia, resolución judicial o motivos de cierre"
    )
    @app_commands.choices(nuevo_estado=[
        app_commands.Choice(name="🟡 Abierto", value="abierto"),
        app_commands.Choice(name="🔍 En Investigación Activa", value="en_investigacion"),
        app_commands.Choice(name="⚖️ En Juicio / Tribunal de Justicia", value="en_juicio"),
        app_commands.Choice(name="🔒 Cerrado (Sentencia Dictada)", value="cerrado"),
        app_commands.Choice(name="📁 Archivado (Sin resolución / Sobresedimiento)", value="archivado")
    ])
    async def caso_estado(
        self,
        interaction: discord.Interaction,
        numero_caso: str,
        nuevo_estado: str,
        veredicto: str = None
    ):
        await interaction.response.defer()
        if not await is_officer_or_admin(interaction):
            await interaction.followup.send(embed=error_embed("Sin Permisos", "Solo detectives, jueces o administradores pueden modificar el estado del caso."), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        clean_num = numero_caso.strip().upper()

        row = await aexecute("SELECT * FROM police_cases WHERE guild_id=$1 AND UPPER(case_number)=$2", (gid, clean_num), fetch="one")
        if not row:
            await interaction.followup.send(embed=error_embed("No Encontrado", f"No se encontró el caso `{clean_num}`."), ephemeral=True)
            return

        await aexecute(
            """UPDATE police_cases 
               SET status=$1, verdict=$2, updated_at=NOW() 
               WHERE id=$3""",
            (nuevo_estado, veredicto.strip() if veredicto else row.get("verdict"), row["id"])
        )

        st_label = STATUS_META.get(nuevo_estado, nuevo_estado)

        embed = success_embed(
            "Estado del Expediente Actualizado",
            f"El caso **{clean_num}** ({row.get('title')}) ha cambiado a:\n\n"
            f"📊 **Nuevo Estado:** {st_label}\n"
            + (f"⚖️ **Veredicto / Sentencia:** {veredicto.strip()}\n" if veredicto else "")
            + f"👤 **Autoridad a Cargo:** {interaction.user.mention}"
        )
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Cases(bot))
