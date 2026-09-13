import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging
import re

from bot.db import aexecute
from bot.helpers import async_get_or_create_user, format_currency, generate_id, check_admin_permission
from bot.embeds import success_embed, error_embed, info_embed
from bot.services.economy import async_remove_cash, async_remove_bank, async_add_cash, async_log_transaction
from bot.services.jail_overlay import get_jailed_roblox_avatar

logger = logging.getLogger("bot.cogs.police")


async def is_police_authorized(interaction: discord.Interaction) -> bool:
    """
    Verifica si el usuario tiene un rol policial configurado o permisos de administrador.
    Los roles policiales se configuran con `/policia configurar_roles`.
    """
    if interaction.user.guild_permissions.administrator:
        return True

    gid = str(interaction.guild_id)
    config = await aexecute("SELECT police_role_ids FROM guild_configs WHERE guild_id=$1", (gid,), fetch="one")
    if config and config.get("police_role_ids"):
        allowed_roles = [int(r.strip()) for r in config["police_role_ids"].split(",") if r.strip().isdigit()]
        user_role_ids = [r.id for r in interaction.user.roles]
        if any(rid in user_role_ids for rid in allowed_roles):
            return True

    # También verificar si pertenece a un departamento policial (MPD, FHP, MBPD, CPD, Sheriff, DOJ)
    dept_member = await aexecute(
        """SELECT dm.id FROM department_members dm 
           JOIN departments d ON d.id=dm.department_id 
           WHERE dm.guild_id=$1 AND dm.discord_id=$2 AND d.acronym IN ('MPD', 'FHP', 'MBPD', 'CPD', 'Sheriff', 'DOJ', 'FDOJ')""",
        (gid, str(interaction.user.id)), fetch="one"
    )
    if dept_member:
        return True

    return False


class Police(commands.Cog, name="Policía & Justicia"):
    def __init__(self, bot):
        self.bot = bot

    policia = app_commands.Group(name="policia", description="Comandos oficiales del cuerpo de policía y justicia")

    @policia.command(name="configurar_roles", description="Configurar qué roles pueden usar los comandos policiales (Admin)")
    @app_commands.describe(roles="Menciones o IDs de los roles autorizados (separados por espacios o comas)")
    async def configurar_roles(self, interaction: discord.Interaction, roles: str):
        await interaction.response.defer(ephemeral=True)
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores pueden configurar roles policiales"), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        found_ids = re.findall(r"\d+", roles)
        valid_roles = []
        for rid in found_ids:
            r = interaction.guild.get_role(int(rid))
            if r:
                valid_roles.append(str(r.id))

        if not valid_roles:
            await interaction.followup.send(embed=error_embed("Roles Inválidos", "No se encontraron roles válidos en tu mensaje."), ephemeral=True)
            return

        roles_str = ",".join(valid_roles)
        existing = await aexecute("SELECT id FROM guild_configs WHERE guild_id=$1", (gid,), fetch="one")
        if existing:
            await aexecute("UPDATE guild_configs SET police_role_ids=$1, updated_at=NOW() WHERE guild_id=$2", (roles_str, gid))
        else:
            await aexecute("INSERT INTO guild_configs (id, guild_id, police_role_ids, created_at, updated_at) VALUES ($1,$2,$3,NOW(),NOW())", (generate_id(), gid, roles_str))

        mentions = [f"<@&{r}>" for r in valid_roles]
        e = success_embed(
            "Roles Policiales Configurados",
            f"Los siguientes roles ahora tienen autorización para usar `/policia arrestar`, `/policia multar` y `/policia antecedentes`:\n\n" + " ".join(mentions)
        )
        await interaction.followup.send(embed=e, ephemeral=True)

    @policia.command(name="arrestar", description="Arrestar y procesar judicialmente a un infractor (Solo Policía)")
    @app_commands.describe(
        usuario="Sospechoso o ciudadano a arrestar (obligatorio)",
        motivo="Motivo o cargos penales del arresto (obligatorio)",
        tiempo="Tiempo de condena o detención ej: 15m, 30 minutos (obligatorio)",
        descripcion="Descripción detallada de los hechos u operativo (obligatorio)",
        encontrado="Objetos o pertenencias encontradas durante la revisión (obligatorio)",
        incautado="Armas, sustancias o bienes incautados (obligatorio)",
        derechos="¿Se le leyeron los derechos Miranda al detenido? (obligatorio)",
        estado_fisico="Estado físico de salud del detenido (obligatorio)",
        oficial_nombre="Nombre, rango o placa del oficial a cargo (obligatorio)",
        prueba="Adjunta archivo o captura de prueba del arresto (obligatorio)"
    )
    @app_commands.choices(
        derechos=[
            app_commands.Choice(name="✅ Sí (Se le leyeron los derechos)", value="si"),
            app_commands.Choice(name="❌ No (No se le leyeron los derechos)", value="no"),
        ],
        estado_fisico=[
            app_commands.Choice(name="🟢 Ileso / En buen estado", value="Ileso / En buen estado"),
            app_commands.Choice(name="🟡 Estable / Con golpes leves", value="Estable / Con golpes leves"),
            app_commands.Choice(name="🔴 Herido / Requiere atención médica", value="Herido / Requiere atención médica"),
            app_commands.Choice(name="⚪ Inconsciente / Hospitalizado", value="Inconsciente / Hospitalizado"),
        ]
    )
    async def arrestar(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        motivo: str,
        tiempo: str,
        descripcion: str,
        encontrado: str,
        incautado: str,
        derechos: app_commands.Choice[str],
        estado_fisico: app_commands.Choice[str],
        oficial_nombre: str,
        prueba: discord.Attachment
    ):
        await interaction.response.defer()
        if not await is_police_authorized(interaction):
            await interaction.followup.send(
                embed=error_embed("Acceso Denegado 👮", "No tienes autorización ni los roles requeridos para ejecutar arrestos policiales."),
                ephemeral=True
            )
            return

        gid = str(interaction.guild_id)
        c_uid = str(usuario.id)
        o_uid = str(interaction.user.id)

        # Extraer minutos numéricos para cálculos y persistencia en DB
        digits = re.findall(r"\d+", str(tiempo))
        tiempo_minutos = int(digits[0]) if digits else 15
        tiempo_minutos = max(1, min(1440, tiempo_minutos))

        # Resolución del estado de derechos Miranda (si se le leyeron o no)
        derechos_raw = derechos.value if hasattr(derechos, "value") else str(derechos or "si")
        se_leyeron_derechos = derechos_raw.strip().lower() in ("si", "sí", "true", "1", "yes")
        derechos_display = "✅ **Sí** — Leídos oportunamente conforme a la ley" if se_leyeron_derechos else "❌ **NO** — No se le leyeron los derechos al detenido"

        # Resolución de estado físico
        estado_display = estado_fisico.value if hasattr(estado_fisico, "value") else str(estado_fisico).strip()

        # Oficial a cargo
        oficial_display = oficial_nombre.strip() if oficial_nombre and oficial_nombre.strip() else interaction.user.display_name

        # Strings de revisión y cateo
        encontrado_txt = encontrado.strip() if encontrado and encontrado.strip() else "Ninguno / Pertenencias de rutina"
        incautado_txt = incautado.strip() if incautado and incautado.strip() else "Nada incautado"
        descripcion_txt = descripcion.strip() if descripcion and descripcion.strip() else "Sin observaciones adicionales."
        prueba_url = prueba.url if prueba else None

        # Crear o buscar al usuario
        await async_get_or_create_user(c_uid, gid, username=usuario.name, display_name=usuario.display_name)
        
        # Obtener DNI activo del detenido
        dni_rec = await aexecute(
            "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2 ORDER BY is_active DESC, updated_at DESC, created_at DESC LIMIT 1",
            (gid, c_uid), fetch="one"
        )
        dni_num = dni_rec.get("dni_number", "S/D") if dni_rec else "Sin DNI"
        nombre_ic = dni_rec.get("full_name", usuario.display_name) if dni_rec else usuario.display_name

        # Obtener estrictamente la foto y perfil de Roblox del DNI
        roblox_avatar_url = None
        roblox_id = None
        roblox_username = None

        if dni_rec:
            roblox_avatar_url = dni_rec.get("avatar_url")
            roblox_id = dni_rec.get("roblox_id")
            roblox_username = dni_rec.get("roblox_username")

        if not roblox_username or not roblox_id:
            u_row = await aexecute(
                "SELECT roblox_id, roblox_username FROM users WHERE guild_id=$1 AND discord_id=$2",
                (gid, c_uid),
                fetch="one"
            )
            if u_row:
                roblox_id = roblox_id or u_row.get("roblox_id")
                roblox_username = roblox_username or u_row.get("roblox_username")

        # Generar foto de perfil de Roblox del DNI entre rejas de prisión (NUNCA Discord)
        jailed_file, thumbnail_uri = await get_jailed_roblox_avatar(
            roblox_avatar_url=roblox_avatar_url,
            roblox_identifier=roblox_id or roblox_username
        )

        # Registrar arresto en criminal_records
        record_id = generate_id()
        try:
            await aexecute(
                """INSERT INTO criminal_records (
                       id, guild_id, discord_id, crime_type, description, fine_amount,
                       jail_time_minutes, officer_id, officer_name, status,
                       items_found, items_seized, rights_read, physical_state, evidence_url, roblox_username,
                       created_at
                   )
                   VALUES ($1, $2, $3, 'Arresto Policial', $4, 0, $5, $6, $7, 'arrested', $8, $9, $10, $11, $12, $13, NOW())""",
                (
                    record_id, gid, c_uid, motivo, tiempo_minutos, o_uid, oficial_display,
                    encontrado_txt, incautado_txt, se_leyeron_derechos, estado_display, prueba_url, str(roblox_username or "")
                )
            )
        except Exception as ex:
            logger.warning(f"[Police] Fallback insert criminal_records: {ex}")
            await aexecute(
                """INSERT INTO criminal_records (id, guild_id, discord_id, crime_type, description, fine_amount, jail_time_minutes, officer_id, officer_name, status, created_at)
                   VALUES ($1, $2, $3, 'Arresto Policial', $4, 0, $5, $6, $7, 'arrested', NOW())""",
                (record_id, gid, c_uid, f"{motivo} | {descripcion_txt}", tiempo_minutos, o_uid, oficial_display)
            )

        e = discord.Embed(
            title="🚨 INFORME OFICIAL DE ARRESTO & DETENCIÓN",
            description=f"El oficial **{oficial_display}** ({interaction.user.mention}) ha procesado formalmente la detención y encarcelamiento del siguiente ciudadano:",
            color=discord.Color.dark_red(),
            timestamp=datetime.datetime.utcnow()
        )
        if thumbnail_uri:
            e.set_thumbnail(url=thumbnail_uri)

        e.add_field(name="👤 Sospechoso / Detenido", value=f"{usuario.mention} (`{usuario.name}`)", inline=True)
        e.add_field(name="🪪 Nombre IC / DNI", value=f"**{nombre_ic}**\n`{dni_num}`", inline=True)

        roblox_badge = f"🎮 **{roblox_username}**" if roblox_username else "⚠️ *Sin vincular*"
        if roblox_id:
            roblox_badge += f" (`{roblox_id}`)"
        e.add_field(name="🎮 Roblox Vinculado", value=roblox_badge, inline=True)

        e.add_field(name="👮 Oficial a Cargo", value=f"**{oficial_display}**", inline=True)
        e.add_field(name="⏳ Condena / Tiempo", value=f"**{tiempo}** (`{tiempo_minutos} min`)", inline=True)
        e.add_field(name="🩺 Estado Físico", value=f"**{estado_display}**", inline=True)

        e.add_field(name="📜 Lectura de Derechos Miranda", value=derechos_display, inline=False)
        e.add_field(name="⚖️ Motivo & Cargos Penales", value=f"```\n{motivo}\n```", inline=False)
        e.add_field(name="📋 Descripción de los Hechos", value=f"{descripcion_txt}", inline=False)
        e.add_field(name="🔍 Objetos Encontrados (Cateo)", value=f"```\n{encontrado_txt}\n```", inline=True)
        e.add_field(name="⛔ Bienes / Armas Incautadas", value=f"```\n{incautado_txt}\n```", inline=True)

        if prueba:
            e.set_image(url=prueba.url)
            e.add_field(name="📸 Prueba / Evidencia Adjunta", value=f"[Ver Archivo Adjunto]({prueba.url})", inline=False)

        e.set_footer(text=f"Expediente #{record_id[:8].upper()} • Departamento de Policía & Justicia de Miami Vice RP")

        send_kwargs = {"content": f"{usuario.mention}", "embed": e}
        if jailed_file is not None:
            send_kwargs["file"] = jailed_file

        await interaction.followup.send(**send_kwargs)

    @policia.command(name="multar", description="Emitir y cobrar una multa de tránsito o infracción a un ciudadano (Solo Policía)")
    @app_commands.describe(
        ciudadano="Ciudadano al que se le aplicará la infracción",
        monto="Monto económico de la multa en $",
        motivo="Motivo o código de la infracción cometida"
    )
    async def multar(
        self,
        interaction: discord.Interaction,
        ciudadano: discord.Member,
        monto: int,
        motivo: str
    ):
        await interaction.response.defer()
        if not await is_police_authorized(interaction):
            await interaction.followup.send(
                embed=error_embed("Acceso Denegado 👮", "No tienes autorización ni los roles requeridos para emitir multas policiales."),
                ephemeral=True
            )
            return

        if monto <= 0:
            await interaction.followup.send(embed=error_embed("Monto Inválido", "El monto de la multa debe ser mayor a $0."), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        c_uid = str(ciudadano.id)
        o_uid = str(interaction.user.id)

        target_user = await async_get_or_create_user(c_uid, gid, username=ciudadano.name, display_name=ciudadano.display_name)
        
        # Descontar el dinero (primero efectivo, si no banco)
        cash_balance = target_user.get("cash", 0)
        bank_balance = target_user.get("bank", 0)
        total_balance = cash_balance + bank_balance

        paid_status = ""
        if cash_balance >= monto:
            await async_remove_cash(c_uid, gid, monto)
            paid_status = "🟢 Descontada de su efectivo al instante."
        elif total_balance >= monto:
            rem = monto - cash_balance
            if cash_balance > 0:
                await async_remove_cash(c_uid, gid, cash_balance)
            await async_remove_bank(c_uid, gid, rem)
            paid_status = "🟢 Descontada de su cuenta bancaria al instante."
        else:
            # Descontar todo lo que tenga y registrar deuda
            if cash_balance > 0:
                await async_remove_cash(c_uid, gid, cash_balance)
            if bank_balance > 0:
                await async_remove_bank(c_uid, gid, bank_balance)
            paid_status = "⚠️ El ciudadano no poseía suficientes fondos. Se le incautó el saldo disponible y quedó asentada la falta en su historial."

        # Registrar en criminal_records
        rec_id = generate_id()
        await aexecute(
            """INSERT INTO criminal_records (id, guild_id, discord_id, crime_type, description, fine_amount, jail_time_minutes, officer_id, officer_name, status, created_at)
               VALUES ($1, $2, $3, 'Multa / Infracción', $4, $5, 0, $6, $7, 'fined', NOW())""",
            (rec_id, gid, c_uid, motivo, monto, o_uid, interaction.user.name)
        )

        dni_rec = await aexecute(
            "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2 ORDER BY created_at DESC LIMIT 1",
            (gid, c_uid), fetch="one"
        )
        dni_num = dni_rec.get("dni_number", "S/D") if dni_rec else "Sin DNI"

        e = discord.Embed(
            title="📄 BOLETA OFICIAL DE INFRACCIÓN / MULTA",
            description=f"Se ha extendido una sanción económica oficial a {ciudadano.mention}:",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.utcnow()
        )
        if dni_rec and dni_rec.get("avatar_url"):
            e.set_thumbnail(url=dni_rec["avatar_url"])
        else:
            e.set_thumbnail(url=ciudadano.display_avatar.url)

        e.add_field(name="👤 Infractor", value=f"{ciudadano.mention} (`{ciudadano.name}`)", inline=True)
        e.add_field(name="🪪 DNI", value=f"`{dni_num}`", inline=True)
        e.add_field(name="👮 Oficial Emisor", value=f"{interaction.user.mention}", inline=True)
        e.add_field(name="💵 Monto de la Multa", value=f"**{format_currency(monto)}**", inline=True)
        e.add_field(name="💳 Estado de Cobro", value=paid_status, inline=True)
        e.add_field(name="📝 Infracción / Motivo", value=f"```{motivo}```", inline=False)
        e.set_footer(text=f"Folio #{rec_id[:8].upper()} • Tránsito & Seguridad Pública")

        await interaction.followup.send(content=f"{ciudadano.mention}", embed=e)

    @policia.command(name="antecedentes", description="Consultar el historial penal, arrestos y multas de un ciudadano (Solo Policía)")
    @app_commands.describe(ciudadano="Ciudadano a consultar antecedentes")
    async def antecedentes(self, interaction: discord.Interaction, ciudadano: discord.Member):
        await interaction.response.defer()
        if not await is_police_authorized(interaction):
            await interaction.followup.send(
                embed=error_embed("Acceso Denegado 👮", "No tienes autorización ni los roles requeridos para consultar la base de datos de antecedentes penales."),
                ephemeral=True
            )
            return

        gid = str(interaction.guild_id)
        c_uid = str(ciudadano.id)

        # Consultar DNI
        dni_rec = await aexecute(
            "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2 ORDER BY created_at DESC LIMIT 1",
            (gid, c_uid), fetch="one"
        )
        dni_num = dni_rec.get("dni_number", "Sin DNI") if dni_rec else "Sin DNI"
        nombre_ic = dni_rec.get("full_name", ciudadano.display_name) if dni_rec else ciudadano.display_name

        # Consultar antecedentes
        records = await aexecute(
            "SELECT * FROM criminal_records WHERE guild_id=$1 AND discord_id=$2 ORDER BY created_at DESC LIMIT 10",
            (gid, c_uid), fetch="all"
        ) or []

        e = discord.Embed(
            title=f"📁 EXPEDIENTE POLICIAL & ANTECEDENTES — {ciudadano.display_name}",
            color=discord.Color.dark_blue(),
            timestamp=datetime.datetime.utcnow()
        )
        if dni_rec and dni_rec.get("avatar_url"):
            e.set_thumbnail(url=dni_rec["avatar_url"])
        else:
            e.set_thumbnail(url=ciudadano.display_avatar.url)

        e.add_field(name="👤 Ciudadano IC", value=f"**{nombre_ic}**", inline=True)
        e.add_field(name="🪪 DNI", value=f"`{dni_num}`", inline=True)
        e.add_field(name="🎮 Roblox", value=f"`{dni_rec.get('roblox_username', 'No vinculado') if dni_rec else 'N/A'}`", inline=True)

        if not records:
            e.description = "🟢 **HISTORIAL LIMPIO**: No cuenta con registros penales, arrestos ni multas registradas en la base de datos de Miami."
        else:
            e.description = f"⚠️ Se encontraron **{len(records)} registro(s)** en la base de datos criminal:"
            for idx, r in enumerate(records, 1):
                fecha = str(r.get("created_at", ""))[:10] or "Fecha N/A"
                tipo = r.get("crime_type", "Registro")
                desc = r.get("description", "Sin descripción")
                multa = r.get("fine_amount", 0)
                tiempo = r.get("jail_time_minutes", 0)
                oficial = r.get("officer_name", "Oficial")

                detalles = []
                if multa > 0:
                    detalles.append(f"Multa: {format_currency(multa)}")
                if tiempo > 0:
                    detalles.append(f"Cárcel: {tiempo}m")
                detalles_str = f" ({', '.join(detalles)})" if detalles else ""

                e.add_field(
                    name=f"#{idx} [{fecha}] {tipo}{detalles_str}",
                    value=f"• **Motivo:** {desc}\n• **Oficial:** `{oficial}`",
                    inline=False
                )

        e.set_footer(text=f"Consulta efectuada por {interaction.user.name} • Sistema CAD/MDT Miami Vice")
        await interaction.followup.send(embed=e)

    @policia.command(name="mis_multas", description="Ver tus multas e infracciones pendientes de pago y fianzas")
    async def mis_multas(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)

        records = await aexecute(
            "SELECT * FROM criminal_records WHERE guild_id=$1 AND discord_id=$2 ORDER BY created_at DESC LIMIT 15",
            (gid, uid), fetch="all"
        ) or []

        if not records:
            await interaction.followup.send(
                embed=success_embed("Sin Infracciones", "No tienes multas pendientes ni antecedentes registrados en el sistema."),
                ephemeral=True
            )
            return

        e = info_embed(
            "📄 Tus Infracciones & Expediente Judicial",
            "A continuación se listan tus infracciones y registros legales en Miami Vice RP. Usa `/policia pagar_multa` o `/policia pagar_fianza` para saldar tus obligaciones."
        )

        unpaid_count = 0
        total_debt = 0

        for idx, r in enumerate(records, 1):
            status = r.get("status", "active")
            monto = r.get("fine_amount", 0)
            tipo = r.get("crime_type", "Registro")
            desc = r.get("description", "Sin detalle")
            rec_id = str(r.get("id", ""))[:8].upper()
            fecha = str(r.get("created_at", ""))[:10]

            if status in ("fined", "unpaid", "pending", "active") and monto > 0:
                badge = "🔴 PENDIENTE DE PAGO"
                unpaid_count += 1
                total_debt += monto
            elif status == "paid":
                badge = "🟢 PAGADA"
            elif status == "arrested":
                badge = f"🚨 ARRESTADO (Fianza: {format_currency(monto)})" if monto > 0 else "🚨 ARRESTADO (Sin fianza)"
            elif status == "bailed":
                badge = "🔓 LIBERADO BAJO FIANZA"
            else:
                badge = f"ℹ️ {status.upper()}"

            e.add_field(
                name=f"#{idx} [{badge}] Folio #{rec_id} — {tipo}",
                value=f"• **Monto:** {format_currency(monto)}\n• **Motivo:** {desc}\n• **Fecha:** {fecha}",
                inline=False
            )

        if unpaid_count > 0:
            e.description = f"⚠️ Tienes **{unpaid_count} multa(s) pendientes** por un total de **{format_currency(total_debt)}**.\nPuedes pagarlas usando `/policia pagar_multa`."

        await interaction.followup.send(embed=e, ephemeral=True)

    @policia.command(name="pagar_multa", description="Pagar una multa de tránsito o infracción pendiente")
    @app_commands.describe(folio="Código de Folio de la multa (ej: Folio #A1B2C3D4 o déjalo vacío para pagar la más reciente)")
    async def pagar_multa(self, interaction: discord.Interaction, folio: str = None):
        await interaction.response.defer()
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)

        # Buscar multa pendiente
        if folio:
            clean_folio = folio.replace("#", "").strip().lower()
            record = await aexecute(
                """SELECT * FROM criminal_records 
                   WHERE guild_id=$1 AND discord_id=$2 AND status IN ('fined', 'unpaid', 'pending', 'active') AND id ILIKE $3
                   ORDER BY created_at DESC LIMIT 1""",
                (gid, uid, f"{clean_folio}%"), fetch="one"
            )
        else:
            record = await aexecute(
                """SELECT * FROM criminal_records 
                   WHERE guild_id=$1 AND discord_id=$2 AND status IN ('fined', 'unpaid', 'pending', 'active') AND fine_amount > 0 AND crime_type LIKE '%Multa%'
                   ORDER BY created_at DESC LIMIT 1""",
                (gid, uid), fetch="one"
            )
            if not record:
                # Buscar cualquier registro con deuda pendiente
                record = await aexecute(
                    """SELECT * FROM criminal_records 
                       WHERE guild_id=$1 AND discord_id=$2 AND status IN ('fined', 'unpaid', 'pending', 'active') AND fine_amount > 0
                       ORDER BY created_at DESC LIMIT 1""",
                    (gid, uid), fetch="one"
                )

        if not record or record.get("fine_amount", 0) <= 0:
            await interaction.followup.send(
                embed=error_embed("Sin Multas Pendientes", "No tienes multas pendientes de pago registradas con ese folio. Usa `/policia mis_multas` para verificar tu estado."),
                ephemeral=True
            )
            return

        monto = record.get("fine_amount", 0)
        user_row = await async_get_or_create_user(uid, gid, username=interaction.user.name, display_name=interaction.user.display_name)
        cash_val = user_row.get("cash", 0)
        bank_val = user_row.get("bank", 0)
        total_balance = cash_val + bank_val

        if total_balance < monto:
            await interaction.followup.send(
                embed=error_embed(
                    "Fondos Insuficientes",
                    f"La multa asciende a **{format_currency(monto)}**, pero tu saldo total (efectivo + banco) es de **{format_currency(total_balance)}**."
                ),
                ephemeral=True
            )
            return

        # Cobrar primero en efectivo, luego banco
        metodo = ""
        if cash_val >= monto:
            await async_remove_cash(uid, gid, monto)
            metodo = "Efectivo"
        else:
            rem = monto - cash_val
            if cash_val > 0:
                await async_remove_cash(uid, gid, cash_val)
            await async_remove_bank(uid, gid, rem)
            metodo = "Efectivo y Cuenta Bancaria"

        # Registrar transacción
        await async_log_transaction(uid, gid, "pay", -monto, f"Pago de multa Folio #{record['id'][:8].upper()}: {record.get('description', '')[:30]}")

        # Actualizar registro a pagado
        await aexecute(
            "UPDATE criminal_records SET status='paid' WHERE id=$1",
            (record["id"],)
        )

        dni_rec = await aexecute(
            "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2 ORDER BY created_at DESC LIMIT 1",
            (gid, uid), fetch="one"
        )
        dni_num = dni_rec.get("dni_number", "S/D") if dni_rec else "Sin DNI"

        e = discord.Embed(
            title="🧾 COMPROBANTE OFICIAL DE PAGO DE MULTA",
            description=f"Se ha liquidado satisfactoriamente la infracción asentada en el Departamento de Tránsito.",
            color=discord.Color.green(),
            timestamp=datetime.datetime.utcnow()
        )
        if dni_rec and dni_rec.get("avatar_url"):
            e.set_thumbnail(url=dni_rec["avatar_url"])
        else:
            e.set_thumbnail(url=interaction.user.display_avatar.url)

        e.add_field(name="👤 Ciudadano / Pagador", value=f"{interaction.user.mention} (`{interaction.user.name}`)", inline=True)
        e.add_field(name="🪪 DNI", value=f"`{dni_num}`", inline=True)
        e.add_field(name="💵 Monto Pagado", value=f"**{format_currency(monto)}**", inline=True)
        e.add_field(name="💳 Método de Cobro", value=metodo, inline=True)
        e.add_field(name="📝 Infracción Liquidada", value=f"```{record.get('description', 'Multa de tránsito')}```", inline=False)
        e.set_footer(text=f"Folio #{record['id'][:8].upper()} • Estado: PAGADA 🟢")

        await interaction.followup.send(embed=e)

    @policia.command(name="pagar_fianza", description="Pagar la fianza judicial de un arresto para obtener la libertad inmediata")
    @app_commands.describe(ciudadano="Ciudadano detenido al que deseas pagarle la fianza (omite para pagarte a ti mismo)")
    async def pagar_fianza(self, interaction: discord.Interaction, ciudadano: discord.Member = None):
        await interaction.response.defer()
        target = ciudadano or interaction.user
        gid = str(interaction.guild_id)
        target_uid = str(target.id)
        payer_uid = str(interaction.user.id)

        # Buscar arresto activo con fianza
        arrest_record = await aexecute(
            """SELECT * FROM criminal_records 
               WHERE guild_id=$1 AND discord_id=$2 AND status='arrested'
               ORDER BY created_at DESC LIMIT 1""",
            (gid, target_uid), fetch="one"
        )

        if not arrest_record:
            # Buscar el arresto más reciente si no tenía status='arrested'
            arrest_record = await aexecute(
                """SELECT * FROM criminal_records 
                   WHERE guild_id=$1 AND discord_id=$2 AND crime_type='Arresto Policial' AND status != 'bailed'
                   ORDER BY created_at DESC LIMIT 1""",
                (gid, target_uid), fetch="one"
            )

        if not arrest_record:
            await interaction.followup.send(
                embed=error_embed("Sin Arresto Activo", f"{target.mention} no tiene ningún expediente de arresto activo o pendiente de fianza."),
                ephemeral=True
            )
            return

        fianza_monto = arrest_record.get("fine_amount", 0)
        if fianza_monto <= 0:
            await interaction.followup.send(
                embed=error_embed("Sin Derecho a Fianza ❌", f"El arresto de {target.mention} fue catalogado **SIN DERECHO A FIANZA** debido a la gravedad de los cargos."),
                ephemeral=True
            )
            return

        # Verificar fondos del pagador
        payer_row = await async_get_or_create_user(payer_uid, gid, username=interaction.user.name, display_name=interaction.user.display_name)
        cash_val = payer_row.get("cash", 0)
        bank_val = payer_row.get("bank", 0)
        total_balance = cash_val + bank_val

        if total_balance < fianza_monto:
            await interaction.followup.send(
                embed=error_embed(
                    "Fondos Insuficientes",
                    f"La fianza judicial asciende a **{format_currency(fianza_monto)}**, pero tu saldo total disponible es de **{format_currency(total_balance)}**."
                ),
                ephemeral=True
            )
            return

        # Cobrar fianza al pagador
        metodo = ""
        if cash_val >= fianza_monto:
            await async_remove_cash(payer_uid, gid, fianza_monto)
            metodo = "Efectivo"
        else:
            rem = fianza_monto - cash_val
            if cash_val > 0:
                await async_remove_cash(payer_uid, gid, cash_val)
            await async_remove_bank(payer_uid, gid, rem)
            metodo = "Efectivo y Banco"

        # Registrar transacción
        await async_log_transaction(payer_uid, gid, "pay", -fianza_monto, f"Pago de fianza judicial para {target.name} (Exp. #{arrest_record['id'][:8].upper()})")

        # Marcar registro penal como liberado bajo fianza
        await aexecute(
            "UPDATE criminal_records SET status='bailed' WHERE id=$1",
            (arrest_record["id"],)
        )

        dni_rec = await aexecute(
            "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2 ORDER BY created_at DESC LIMIT 1",
            (gid, target_uid), fetch="one"
        )
        dni_num = dni_rec.get("dni_number", "S/D") if dni_rec else "Sin DNI"
        nombre_ic = dni_rec.get("full_name", target.display_name) if dni_rec else target.display_name

        e = discord.Embed(
            title="⚖️ LIBERTAD BAJO FIANZA JUDICIAL",
            description=f"Se ha efectuado el pago total de la caución penal fijada por el Departamento de Justicia.",
            color=discord.Color.gold(),
            timestamp=datetime.datetime.utcnow()
        )
        if dni_rec and dni_rec.get("avatar_url"):
            e.set_thumbnail(url=dni_rec["avatar_url"])
        else:
            e.set_thumbnail(url=target.display_avatar.url)

        e.add_field(name="👤 Sospechoso Liberado", value=f"{target.mention} (**{nombre_ic}**)", inline=True)
        e.add_field(name="🪪 DNI", value=f"`{dni_num}`", inline=True)
        e.add_field(name="💵 Monto de Fianza Pagado", value=f"**{format_currency(fianza_monto)}**", inline=True)
        e.add_field(name="🤝 Depositante / Fiador", value=f"{interaction.user.mention}", inline=True)
        e.add_field(name="💳 Método", value=metodo, inline=True)
        e.add_field(name="⚖️ Cargos Originales", value=f"```{arrest_record.get('description', 'Cargos penales')}```", inline=False)
        e.set_footer(text=f"Expediente #{arrest_record['id'][:8].upper()} • Estado: LIBERADO BAJO FIANZA 🔓")

        await interaction.followup.send(content=f"{target.mention}", embed=e)


async def setup(bot):
    await bot.add_cog(Police(bot))
