import discord
from discord import app_commands, ui
from discord.ext import commands
import datetime
import random

from bot.db import aexecute
from bot.helpers import (
    async_get_or_create_user,
    async_get_or_create_guild_config,
    format_currency,
    generate_id,
    get_elapsed_seconds,
    check_admin_permission,
)
from bot.embeds import success_embed, error_embed, economy_embed, info_embed, warning_embed
from bot.services.economy import async_add_cash, async_log_transaction, async_transfer, async_remove_cash
from bot.services.levels import add_xp

COOLDOWNS = {}

def check_cooldown(key, seconds):
    now = datetime.datetime.utcnow().timestamp()
    last = COOLDOWNS.get(key, 0)
    remaining = (last + seconds) - now
    if remaining > 0:
        return remaining
    COOLDOWNS[key] = now
    return 0


class WorkSubmissionModal(ui.Modal, title="📋 Reporte de Trabajo Secundario"):
    puesto = ui.TextInput(
        label="Puesto / Trabajo Secundario",
        placeholder="Ej: Mecánico, Repartidor, Conductor de Bus, Minero, Pescador...",
        min_length=3,
        max_length=60,
        required=True
    )
    horas = ui.TextInput(
        label="Tiempo / Turnos dedicados",
        placeholder="Ej: 2 turnos / 1 hora y media",
        min_length=1,
        max_length=40,
        required=True
    )
    descripcion = ui.TextInput(
        label="Descripción de las labores realizadas",
        placeholder="Detalla qué hiciste, rol ejecutado, clientes atendidos...",
        style=discord.TextStyle.paragraph,
        min_length=10,
        max_length=800,
        required=True
    )
    evidencia = ui.TextInput(
        label="Enlace / Link de Evidencia (Foto/Video)",
        placeholder="https://imgur.com/... o captura en Discord/Roblox",
        min_length=5,
        max_length=500,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        sub_id = f"WRK-{random.randint(100000, 999999)}"
        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)

        await async_get_or_create_user(user_id, guild_id, username=interaction.user.name, display_name=interaction.user.display_name)

        await aexecute(
            """INSERT INTO work_submissions (id, guild_id, discord_id, job_type, description, evidence, hours_or_shifts, status, created_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,'pending',NOW())""",
            (sub_id, guild_id, user_id, self.puesto.value, self.descripcion.value, self.evidencia.value, self.horas.value)
        )

        config = await async_get_or_create_guild_config(guild_id)
        channel_id = config.get("work_logs_channel_id") or config.get("log_channel_id")
        target_channel = interaction.guild.get_channel(int(channel_id)) if channel_id else interaction.channel

        review_embed = economy_embed(f"🛠️ Solicitud de Pago de Trabajo • #{sub_id}")
        review_embed.set_thumbnail(url=interaction.user.display_avatar.url)
        review_embed.add_field(name="👤 Trabajador", value=f"{interaction.user.mention} (`{interaction.user.name}`)", inline=True)
        review_embed.add_field(name="💼 Puesto / Oficio", value=f"**{self.puesto.value}**", inline=True)
        review_embed.add_field(name="⏱️ Tiempo / Turnos", value=self.horas.value, inline=True)
        review_embed.add_field(name="📝 Descripción de Labores", value=self.descripcion.value, inline=False)
        review_embed.add_field(name="📸 Evidencia", value=f"[Ver Evidencia / Captura]({self.evidencia.value})", inline=False)
        review_embed.set_footer(text=f"ID: {sub_id} • Pendiente de revisión por un Administrador")

        view = WorkReviewView(sub_id=sub_id, worker_id=user_id, job_title=self.puesto.value)

        if target_channel:
            try:
                await target_channel.send(embed=review_embed, view=view)
            except Exception:
                pass

        await interaction.followup.send(
            embed=success_embed(
                "¡Reporte de Trabajo Enviado!",
                f"Tu reporte **#{sub_id}** ha sido registrado con éxito.\n"
                f"Un administrador revisará tu evidencia y asignará la remuneración correspondiente."
            ),
            ephemeral=True
        )


class ApproveWorkModal(ui.Modal, title="💵 Aprobar y Remunerar Trabajo"):
    monto = ui.TextInput(
        label="Monto de Dinero a Otorgar ($)",
        placeholder="Ej: 3500",
        min_length=1,
        max_length=10,
        required=True
    )
    xp = ui.TextInput(
        label="Puntos de Experiencia (XP)",
        placeholder="Ej: 100",
        default="100",
        min_length=1,
        max_length=6,
        required=False
    )
    nota = ui.TextInput(
        label="Nota / Comentario de Revisión",
        placeholder="Ej: Excelente servicio y evidencia completa.",
        style=discord.TextStyle.short,
        required=False,
        max_length=200
    )

    def __init__(self, sub_id: str, worker_id: str, job_title: str):
        super().__init__()
        self.sub_id = sub_id
        self.worker_id = worker_id
        self.job_title = job_title

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores o roles autorizados pueden aprobar trabajos."), ephemeral=True)
            return

        try:
            amount = int(self.monto.value.replace("$", "").replace(",", "").strip())
            if amount <= 0:
                raise ValueError()
        except ValueError:
            await interaction.followup.send(embed=error_embed("Monto inválido", "Ingresa un número entero positivo válido."), ephemeral=True)
            return

        try:
            xp_reward = int(self.xp.value.strip()) if self.xp.value else 100
        except ValueError:
            xp_reward = 100

        guild_id = str(interaction.guild_id)
        note = self.nota.value or "Aprobado por Administración"

        # Actualizar en BD
        await aexecute(
            """UPDATE work_submissions 
               SET status='approved', reward_amount=$1, reward_xp=$2, reviewer_id=$3, review_notes=$4, reviewed_at=NOW()
               WHERE id=$5 AND guild_id=$6""",
            (amount, xp_reward, str(interaction.user.id), note, self.sub_id, guild_id)
        )

        # Otorgar dinero y XP
        await async_get_or_create_user(self.worker_id, guild_id)
        await async_add_cash(self.worker_id, guild_id, amount)
        await async_log_transaction(self.worker_id, guild_id, "work_approved", amount, f"Remuneración trabajo: {self.job_title} (#{self.sub_id})")
        await add_xp(self.worker_id, guild_id, xp_reward, interaction.client)

        # Actualizar embed original
        approved_embed = success_embed(
            f"✅ Trabajo Aprobado y Pagado • #{self.sub_id}",
            f"**Trabajador:** <@{self.worker_id}>\n"
            f"**Oficio:** {self.job_title}\n"
            f"**Pago Otorgado:** {format_currency(amount)} 💵\n"
            f"**Experiencia:** +{xp_reward} XP\n"
            f"**Revisado por:** {interaction.user.mention}\n"
            f"**Nota:** {note}"
        )
        approved_embed.set_footer(text=f"ID: {self.sub_id} • Aprobado")

        try:
            await interaction.message.edit(embed=approved_embed, view=None)
        except Exception:
            pass

        await interaction.followup.send(
            embed=success_embed(
                "Remuneración Entregada",
                f"Se han entregado **{format_currency(amount)}** y **+{xp_reward} XP** a <@{self.worker_id}> por el trabajo **#{self.sub_id}**."
            )
        )


class RejectWorkModal(ui.Modal, title="❌ Rechazar Reporte de Trabajo"):
    motivo = ui.TextInput(
        label="Motivo del Rechazo",
        placeholder="Ej: Evidencia insuficiente o borrosa, no cumple los requisitos...",
        style=discord.TextStyle.paragraph,
        min_length=5,
        max_length=400,
        required=True
    )

    def __init__(self, sub_id: str, worker_id: str, job_title: str):
        super().__init__()
        self.sub_id = sub_id
        self.worker_id = worker_id
        self.job_title = job_title

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores o roles autorizados pueden rechazar trabajos."), ephemeral=True)
            return

        guild_id = str(interaction.guild_id)
        reason = self.motivo.value

        await aexecute(
            """UPDATE work_submissions 
               SET status='rejected', reviewer_id=$1, review_notes=$2, reviewed_at=NOW()
               WHERE id=$3 AND guild_id=$4""",
            (str(interaction.user.id), reason, self.sub_id, guild_id)
        )

        rejected_embed = error_embed(
            f"❌ Trabajo Rechazado • #{self.sub_id}",
            f"**Trabajador:** <@{self.worker_id}>\n"
            f"**Oficio:** {self.job_title}\n"
            f"**Revisado por:** {interaction.user.mention}\n"
            f"**Motivo:** {reason}"
        )
        rejected_embed.set_footer(text=f"ID: {self.sub_id} • Rechazado")

        try:
            await interaction.message.edit(embed=rejected_embed, view=None)
        except Exception:
            pass

        await interaction.followup.send(
            embed=warning_embed(
                "Trabajo Rechazado",
                f"El reporte **#{self.sub_id}** de <@{self.worker_id}> fue rechazado. Motivo: *{reason}*"
            )
        )


class WorkReviewView(ui.View):
    def __init__(self, sub_id: str, worker_id: str, job_title: str):
        super().__init__(timeout=None)
        self.sub_id = sub_id
        self.worker_id = worker_id
        self.job_title = job_title

    @ui.button(label="Aprobar & Pagar", style=discord.ButtonStyle.success, emoji="💵", custom_id="work_btn_approve")
    async def btn_approve(self, interaction: discord.Interaction, button: ui.Button):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message(embed=error_embed("Sin permisos", "Solo administradores pueden revisar reportes de trabajo."), ephemeral=True)
            return
        await interaction.response.send_modal(ApproveWorkModal(self.sub_id, self.worker_id, self.job_title))

    @ui.button(label="Rechazar", style=discord.ButtonStyle.danger, emoji="❌", custom_id="work_btn_reject")
    async def btn_reject(self, interaction: discord.Interaction, button: ui.Button):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message(embed=error_embed("Sin permisos", "Solo administradores pueden revisar reportes de trabajo."), ephemeral=True)
            return
        await interaction.response.send_modal(RejectWorkModal(self.sub_id, self.worker_id, self.job_title))


class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="balance", description="Ver tu balance de efectivo y banco")
    @app_commands.describe(usuario="Usuario a consultar (opcional)")
    async def balance(self, interaction: discord.Interaction, usuario: discord.Member = None):
        await interaction.response.defer()
        cd = check_cooldown(f"balance:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Comando en cooldown. Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        target = usuario or interaction.user
        user = await async_get_or_create_user(str(target.id), str(interaction.guild_id))
        cash = user.get("cash", 0) or 0
        bank = user.get("bank", 0) or 0
        net = cash + bank
        e = economy_embed(f"💰 Balance de {target.display_name}")
        e.set_thumbnail(url=target.display_avatar.url)
        e.add_field(name="💵 Efectivo", value=format_currency(cash), inline=True)
        e.add_field(name="🏦 Banco", value=format_currency(bank), inline=True)
        e.add_field(name="💎 Patrimonio Neto", value=format_currency(net), inline=True)
        await interaction.followup.send(embed=e)

    @app_commands.command(name="diario", description="Reclamar tu recompensa diaria")
    async def diario(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cd = check_cooldown(f"diario_cmd:{interaction.user.id}:{interaction.guild_id}", 3)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        user = await async_get_or_create_user(str(interaction.user.id), str(interaction.guild_id))
        config = await async_get_or_create_guild_config(str(interaction.guild_id))
        now = datetime.datetime.utcnow()
        last_daily = user.get("last_daily")
        if last_daily:
            elapsed = get_elapsed_seconds(last_daily, now)
            if elapsed < 86400:
                remaining = 86400 - elapsed
                hrs = int(remaining // 3600)
                mins = int((remaining % 3600) // 60)
                await interaction.followup.send(embed=error_embed("Ya reclamaste hoy", f"Vuelve en **{hrs}h {mins}m**"), ephemeral=True)
                return
        amount = config.get("daily_amount") or 500
        await aexecute(
            "UPDATE users SET last_daily=$1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
            (now, str(interaction.user.id), str(interaction.guild_id))
        )
        await async_add_cash(str(interaction.user.id), str(interaction.guild_id), amount)
        await async_log_transaction(str(interaction.user.id), str(interaction.guild_id), "daily", amount, "Recompensa diaria")
        await add_xp(str(interaction.user.id), str(interaction.guild_id), 50, self.bot)
        await interaction.followup.send(embed=success_embed("¡Recompensa Diaria!", f"Has recibido **{format_currency(amount)}** 💵"))

    async def _handle_salary_claim(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cd = check_cooldown(f"sueldo_cmd:{interaction.user.id}:{interaction.guild_id}", 3)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return

        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)
        user = await async_get_or_create_user(user_id, guild_id, username=interaction.user.name, display_name=interaction.user.display_name)
        now = datetime.datetime.utcnow()

        # Verificar si ya cobró sueldo en las últimas 24 horas
        last_salary = user.get("last_salary")
        if last_salary:
            elapsed = get_elapsed_seconds(last_salary, now)
            if elapsed < 86400:
                remaining = 86400 - elapsed
                hrs = int(remaining // 3600)
                mins = int((remaining % 3600) // 60)
                secs = int(remaining % 60)
                time_str = f"**{hrs}h {mins}m**" if hrs > 0 else f"**{mins}m {secs}s**"
                e_wait = warning_embed(
                    "⏱️ Nómina Ya Cobrada",
                    f"Hola {interaction.user.mention}, ya has recibido tu sueldo diario en las últimas 24 horas.\n\n"
                    f"🏦 **Próxima nómina disponible en:** {time_str}\n"
                    f"💡 *Recuerda que también puedes cobrar tu `/diario` o hacer reportes con `/trabajar`.*"
                )
                await interaction.followup.send(embed=e_wait, ephemeral=True)
                return

        # 1. Consultar departamentos donde trabaja el usuario
        dept_rows = await aexecute(
            """SELECT dm.rank, dm.salary, d.id as dept_id, d.name as dept_name, d.acronym, d.budget
               FROM department_members dm
               JOIN departments d ON d.id = dm.department_id
               WHERE dm.discord_id = $1 AND dm.guild_id = $2 AND dm.salary > 0""",
            (user_id, guild_id), fetch="all"
        ) or []

        # 2. Consultar empresas donde trabaja el usuario
        comp_rows = await aexecute(
            """SELECT cm.role, cm.salary, c.id as comp_id, c.name as company_name, c.funds
               FROM company_members cm
               JOIN companies c ON c.id = cm.company_id
               WHERE cm.discord_id = $1 AND cm.guild_id = $2 AND cm.salary > 0""",
            (user_id, guild_id), fetch="all"
        ) or []

        total_salary = 0
        breakdown_items = []

        # Procesar sueldos de departamentos
        for d in dept_rows:
            d_salary = int(d.get("salary", 0) or 0)
            if d_salary <= 0:
                continue
            dept_budget = int(d.get("budget", 0) or 0)
            paid_amount = d_salary
            note = ""

            if dept_budget >= d_salary:
                await aexecute(
                    "UPDATE departments SET budget = budget - $1, updated_at = NOW() WHERE id = $2",
                    (d_salary, d["dept_id"])
                )
            else:
                # Si el departamento tiene poco presupuesto, se cubre con presupuesto disponible + subsidio estatal
                if dept_budget > 0:
                    await aexecute("UPDATE departments SET budget = 0, updated_at = NOW() WHERE id = $1", (d["dept_id"],))
                note = " *(Fondos de Tesorería Municipal)*"

            total_salary += paid_amount
            acronym_badge = f"[{d.get('acronym')}]" if d.get('acronym') else ""
            breakdown_items.append(
                f"🏛️ **{d['dept_name']} {acronym_badge}**\n"
                f"└ Rango: `{d.get('rank', 'Oficial')}` • Salario: **{format_currency(paid_amount)}**{note}"
            )

        # Procesar sueldos de empresas privadas
        for c in comp_rows:
            c_salary = int(c.get("salary", 0) or 0)
            if c_salary <= 0:
                continue
            funds = int(c.get("funds", 0) or 0)
            if funds >= c_salary:
                await aexecute(
                    "UPDATE companies SET funds = funds - $1, updated_at = NOW() WHERE id = $2",
                    (c_salary, c["comp_id"])
                )
                total_salary += c_salary
                breakdown_items.append(
                    f"🏢 **{c['company_name']}**\n"
                    f"└ Cargo: `{c.get('role', 'Empleado')}` • Salario: **{format_currency(c_salary)}**"
                )
            elif funds > 0:
                await aexecute("UPDATE companies SET funds = 0, updated_at = NOW() WHERE id = $1", (c["comp_id"],))
                total_salary += funds
                breakdown_items.append(
                    f"🏢 **{c['company_name']}**\n"
                    f"└ Cargo: `{c.get('role', 'Empleado')}` • Salario Parcial: **{format_currency(funds)}** *(Fondos de empresa limitados)*"
                )
            else:
                breakdown_items.append(
                    f"🏢 **{c['company_name']}**\n"
                    f"└ Cargo: `{c.get('role', 'Empleado')}` • ⚠️ **$0** *(Empresa en quiebra sin fondos)*"
                )

        # Si no tiene ningún salario formal en agencias ni empresas, otorgar subsidio básico de empleo ciudadano
        if total_salary <= 0:
            config = await async_get_or_create_guild_config(guild_id)
            base_subsidy = config.get("daily_amount", 500) or 500
            total_salary = base_subsidy
            breakdown_items.append(
                f"🏙️ **Subsidio de Ciudadanía & Empleo Municipal**\n"
                f"└ Remuneración base ciudadana: **{format_currency(base_subsidy)}** 💵\n"
                f"💡 *Tip: Postúlate a un departamento oficial (`/departamento postular`) o ingresa a una empresa (`/empresa`) para ganar sueldos mayores.*"
            )

        # Actualizar último cobro y depositar en cuenta bancaria (Direct Deposit)
        await aexecute(
            "UPDATE users SET last_salary = $1, bank = bank + $2, updated_at = NOW() WHERE discord_id = $3 AND guild_id = $4",
            (now, total_salary, user_id, guild_id)
        )

        # Registrar transacción
        await async_log_transaction(
            user_id, guild_id, "salary", total_salary,
            f"Nómina salarial diaria: {len(dept_rows)} depts, {len(comp_rows)} comps"
        )

        # Otorgar XP de jornada laboral
        xp_awarded = min(250, max(75, int(total_salary // 15)))
        await add_xp(user_id, guild_id, xp_awarded, self.bot)

        # Obtener balance bancario actualizado
        updated_user = await async_get_or_create_user(user_id, guild_id)
        new_bank = updated_user.get("bank", 0) or 0

        # Crear Embed de Nómina
        emb = economy_embed(f"💼 Nómina Salarial Cobrada • {interaction.user.display_name}")
        emb.set_thumbnail(url=interaction.user.display_avatar.url)
        emb.description = (
            f"¡Tu sueldo diario ha sido liquidado y transferido exitosamente a tu **cuenta bancaria**!\n\n"
            + "\n\n".join(breakdown_items)
        )
        emb.add_field(name="💵 Salario Neto Cobrado", value=f"**+{format_currency(total_salary)}**", inline=True)
        emb.add_field(name="🏦 Nuevo Saldo en Banco", value=f"**{format_currency(new_bank)}**", inline=True)
        emb.add_field(name="⭐ Experiencia Obtenida", value=f"**+{xp_awarded} XP**", inline=True)
        emb.set_footer(text="Miami Vice RP • Sueldo cobrado por 24 horas • Vuelve mañana para tu próxima nómina")

        await interaction.followup.send(embed=emb)

    @app_commands.command(name="sueldo", description="Cobrar tu sueldo diario de tu departamento, empresa o empleo público")
    async def sueldo(self, interaction: discord.Interaction):
        """Reclamar la nómina diaria acumulada por tu empleo o puesto oficial."""
        await self._handle_salary_claim(interaction)

    @app_commands.command(name="salario", description="Cobrar tu sueldo diario (alias de /sueldo)")
    async def salario(self, interaction: discord.Interaction):
        """Alias para cobrar la nómina salarial diaria."""
        await self._handle_salary_claim(interaction)

    @app_commands.command(name="semanal", description="Reclamar tu recompensa semanal")
    async def semanal(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cd = check_cooldown(f"semanal_cmd:{interaction.user.id}:{interaction.guild_id}", 3)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        user = await async_get_or_create_user(str(interaction.user.id), str(interaction.guild_id))
        config = await async_get_or_create_guild_config(str(interaction.guild_id))
        now = datetime.datetime.utcnow()
        last_weekly = user.get("last_weekly")
        if last_weekly:
            elapsed = get_elapsed_seconds(last_weekly, now)
            if elapsed < 604800:
                remaining = 604800 - elapsed
                days = int(remaining // 86400)
                hrs = int((remaining % 86400) // 3600)
                await interaction.followup.send(embed=error_embed("Ya reclamaste esta semana", f"Vuelve en **{days}d {hrs}h**"), ephemeral=True)
                return
        amount = config.get("weekly_amount") or 2500
        await aexecute(
            "UPDATE users SET last_weekly=$1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
            (now, str(interaction.user.id), str(interaction.guild_id))
        )
        await async_add_cash(str(interaction.user.id), str(interaction.guild_id), amount)
        await async_log_transaction(str(interaction.user.id), str(interaction.guild_id), "weekly", amount, "Recompensa semanal")
        await add_xp(str(interaction.user.id), str(interaction.guild_id), 150, self.bot)
        await interaction.followup.send(embed=success_embed("¡Recompensa Semanal!", f"Has recibido **{format_currency(amount)}** 💵"))

    @app_commands.command(name="trabajar", description="Enviar reporte de trabajo secundario con evidencia para revisión y pago")
    async def trabajar(self, interaction: discord.Interaction):
        """Abre el formulario interactivo para reportar trabajo secundario y adjuntar evidencias."""
        await interaction.response.send_modal(WorkSubmissionModal())

    trabajo = app_commands.Group(name="trabajo", description="Gestión y reporte de trabajos secundarios")

    @trabajo.command(name="enviar", description="Enviar reporte de trabajo secundario con evidencia")
    async def trabajo_enviar(self, interaction: discord.Interaction):
        await interaction.response.send_modal(WorkSubmissionModal())

    @trabajo.command(name="pendientes", description="Ver reportes de trabajos pendientes de revisión (Administración)")
    async def trabajo_pendientes(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores o roles autorizados pueden ver reportes pendientes."), ephemeral=True)
            return

        rows = await aexecute(
            """SELECT * FROM work_submissions 
               WHERE guild_id=$1 AND status='pending' 
               ORDER BY created_at ASC LIMIT 10""",
            (str(interaction.guild_id),), fetch="all"
        ) or []

        if not rows:
            await interaction.followup.send(embed=info_embed("📋 Sin Trabajos Pendientes", "No hay reportes de trabajo secundarios esperando revisión."))
            return

        e = economy_embed("📋 Trabajos Secundarios Pendientes de Revisión")
        for r in rows:
            e.add_field(
                name=f"🛠️ #{r['id']} • {r['job_type']}",
                value=f"**Trabajador:** <@{r['discord_id']}>\n**Tiempo:** {r.get('hours_or_shifts','1')}\n**Evidencia:** [Ver Enlace]({r['evidence']})\n*Usa `/trabajo aprobar {r['id']} [monto]`*",
                inline=False
            )
        await interaction.followup.send(embed=e)

    @trabajo.command(name="aprobar", description="Aprobar reporte de trabajo y asignar remuneración (Administración)")
    @app_commands.describe(id_reporte="ID del reporte (ej. WRK-123456)", monto="Cantidad de dinero a otorgar ($)", xp="Puntos de experiencia XP", motivo="Nota o comentario")
    async def trabajo_aprobar(self, interaction: discord.Interaction, id_reporte: str, monto: int, xp: int = 100, motivo: str = "Aprobado por comando"):
        await interaction.response.defer()
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores o roles autorizados pueden aprobar trabajos."), ephemeral=True)
            return

        if monto <= 0:
            await interaction.followup.send(embed=error_embed("Monto inválido", "El monto a pagar debe ser mayor a 0."), ephemeral=True)
            return

        guild_id = str(interaction.guild_id)
        row = await aexecute(
            "SELECT * FROM work_submissions WHERE guild_id=$1 AND id=$2",
            (guild_id, id_reporte.strip()), fetch="one"
        )
        if not row:
            await interaction.followup.send(embed=error_embed("No encontrado", f"No existe el reporte de trabajo con ID `{id_reporte}`."), ephemeral=True)
            return

        if row.get("status") == "approved":
            await interaction.followup.send(embed=warning_embed("Ya aprobado", f"Este reporte ya fue aprobado previamente por {format_currency(row.get('reward_amount',0))}."), ephemeral=True)
            return

        worker_id = row["discord_id"]
        job_title = row.get("job_type", "Trabajo")

        await aexecute(
            """UPDATE work_submissions 
               SET status='approved', reward_amount=$1, reward_xp=$2, reviewer_id=$3, review_notes=$4, reviewed_at=NOW()
               WHERE id=$5 AND guild_id=$6""",
            (monto, xp, str(interaction.user.id), motivo, id_reporte.strip(), guild_id)
        )

        await async_get_or_create_user(worker_id, guild_id)
        await async_add_cash(worker_id, guild_id, monto)
        await async_log_transaction(worker_id, guild_id, "work_approved", monto, f"Remuneración trabajo: {job_title} (#{id_reporte})")
        await add_xp(worker_id, guild_id, xp, self.bot)

        await interaction.followup.send(
            embed=success_embed(
                f"✅ Trabajo #{id_reporte} Aprobado",
                f"Se entregaron **{format_currency(monto)}** y **+{xp} XP** a <@{worker_id}> por su labor como **{job_title}**."
            )
        )

    @trabajo.command(name="rechazar", description="Rechazar reporte de trabajo secundario (Administración)")
    @app_commands.describe(id_reporte="ID del reporte (ej. WRK-123456)", motivo="Razón del rechazo")
    async def trabajo_rechazar(self, interaction: discord.Interaction, id_reporte: str, motivo: str):
        await interaction.response.defer()
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores o roles autorizados pueden rechazar trabajos."), ephemeral=True)
            return

        guild_id = str(interaction.guild_id)
        row = await aexecute(
            "SELECT * FROM work_submissions WHERE guild_id=$1 AND id=$2",
            (guild_id, id_reporte.strip()), fetch="one"
        )
        if not row:
            await interaction.followup.send(embed=error_embed("No encontrado", f"No existe el reporte con ID `{id_reporte}`."), ephemeral=True)
            return

        await aexecute(
            """UPDATE work_submissions 
               SET status='rejected', reviewer_id=$1, review_notes=$2, reviewed_at=NOW()
               WHERE id=$3 AND guild_id=$4""",
            (str(interaction.user.id), motivo, id_reporte.strip(), guild_id)
        )

        await interaction.followup.send(
            embed=warning_embed(
                f"❌ Trabajo #{id_reporte} Rechazado",
                f"El reporte de <@{row['discord_id']}> fue rechazado.\n**Motivo:** {motivo}"
            )
        )

    @trabajo.command(name="mis_trabajos", description="Ver tus reportes de trabajos recientes y su estado")
    async def mis_trabajos(self, interaction: discord.Interaction):
        await interaction.response.defer()
        rows = await aexecute(
            """SELECT * FROM work_submissions 
               WHERE guild_id=$1 AND discord_id=$2 
               ORDER BY created_at DESC LIMIT 5""",
            (str(interaction.guild_id), str(interaction.user.id)), fetch="all"
        ) or []

        if not rows:
            await interaction.followup.send(embed=info_embed("Sin Reportes", "No has enviado reportes de trabajo secundarios aún. Usa `/trabajar` para reportar tu labor."), ephemeral=True)
            return

        e = economy_embed(f"🛠️ Historial de Trabajos de {interaction.user.display_name}")
        status_map = {"pending": "⏳ Pendiente", "approved": "✅ Aprobado", "rejected": "❌ Rechazado"}
        for r in rows:
            status_text = status_map.get(r.get("status"), "Desconocido")
            reward_text = f" • **Pago:** {format_currency(r.get('reward_amount',0))}" if r.get("status") == "approved" else ""
            notes_text = f"\n*Nota:* {r.get('review_notes')}" if r.get("review_notes") else ""
            e.add_field(
                name=f"#{r['id']} — {r.get('job_type','Trabajo')} ({status_text})",
                value=f"**Tiempo:** {r.get('hours_or_shifts','1')}{reward_text}{notes_text}\n[Ver Evidencia]({r.get('evidence')})",
                inline=False
            )
        await interaction.followup.send(embed=e)

    @app_commands.command(name="pagar", description="Pagar dinero a otro jugador")
    @app_commands.describe(usuario="Usuario a pagar", cantidad="Cantidad a pagar")
    async def pagar(self, interaction: discord.Interaction, usuario: discord.Member, cantidad: int):
        await interaction.response.defer()
        cd = check_cooldown(f"pagar:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        if usuario.id == interaction.user.id:
            await interaction.followup.send(embed=error_embed("Error", "No puedes pagarte a ti mismo"), ephemeral=True)
            return
        if usuario.bot:
            await interaction.followup.send(embed=error_embed("Error", "No puedes pagar a un bot"), ephemeral=True)
            return
        if cantidad <= 0:
            await interaction.followup.send(embed=error_embed("Error", "La cantidad debe ser positiva"), ephemeral=True)
            return
        await async_get_or_create_user(str(usuario.id), str(interaction.guild_id))
        ok = await async_transfer(str(interaction.user.id), str(usuario.id), str(interaction.guild_id), cantidad, "pay", f"Pago a {usuario.name}")
        if not ok:
            await interaction.followup.send(embed=error_embed("Sin fondos", "No tienes suficiente efectivo"), ephemeral=True)
            return
        await interaction.followup.send(embed=success_embed("Pago exitoso", f"Pagaste **{format_currency(cantidad)}** a {usuario.mention}"))

    @app_commands.command(name="tabla", description="Ver la tabla de líderes")
    @app_commands.describe(tipo="Tipo de clasificación")
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Riqueza", value="wealth"),
        app_commands.Choice(name="Nivel", value="level"),
        app_commands.Choice(name="Reputación", value="reputation"),
    ])
    async def tabla(self, interaction: discord.Interaction, tipo: str = "wealth"):
        await interaction.response.defer()
        cd = check_cooldown(f"tabla:{interaction.user.id}:{interaction.guild_id}", 10)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        if tipo == "wealth":
            rows = await aexecute(
                "SELECT discord_id, cash, bank FROM users WHERE guild_id=$1 ORDER BY (cash+bank) DESC LIMIT 10",
                (str(interaction.guild_id),), fetch="all"
            ) or []
            e = economy_embed("💎 Tabla de Riqueza")
            lines = []
            medals = ["🥇","🥈","🥉"]
            for i, row in enumerate(rows):
                medal = medals[i] if i < 3 else f"`{i+1}.`"
                net = (row["cash"] or 0) + (row["bank"] or 0)
                lines.append(f"{medal} <@{row['discord_id']}> — **{format_currency(net)}**")
            e.description = "\n".join(lines) if lines else "Sin datos"
        elif tipo == "level":
            rows = await aexecute(
                "SELECT discord_id, level, xp FROM users WHERE guild_id=$1 ORDER BY level DESC, xp DESC LIMIT 10",
                (str(interaction.guild_id),), fetch="all"
            ) or []
            e = info_embed("⭐ Tabla de Niveles")
            lines = []
            medals = ["🥇","🥈","🥉"]
            for i, row in enumerate(rows):
                medal = medals[i] if i < 3 else f"`{i+1}.`"
                lines.append(f"{medal} <@{row['discord_id']}> — Nivel **{row['level']}** (`{row['xp']} XP`)")
            e.description = "\n".join(lines) if lines else "Sin datos"
        else:
            rows = await aexecute(
                "SELECT discord_id, reputation FROM users WHERE guild_id=$1 ORDER BY reputation DESC LIMIT 10",
                (str(interaction.guild_id),), fetch="all"
            ) or []
            e = info_embed("⭐ Tabla de Reputación")
            lines = []
            medals = ["🥇","🥈","🥉"]
            for i, row in enumerate(rows):
                medal = medals[i] if i < 3 else f"`{i+1}.`"
                lines.append(f"{medal} <@{row['discord_id']}> — **{row['reputation']} pts**")
            e.description = "\n".join(lines) if lines else "Sin datos"
        await interaction.followup.send(embed=e)

    @app_commands.command(name="donar", description="Donar dinero a un jugador, departamento o empresa")
    @app_commands.describe(
        tipo="A quién donar",
        cantidad="Cantidad a donar",
        objetivo="Nombre/ID del objetivo",
        mensaje="Mensaje opcional"
    )
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Jugador", value="jugador"),
        app_commands.Choice(name="Departamento", value="departamento"),
        app_commands.Choice(name="Empresa", value="empresa"),
    ])
    async def donar(self, interaction: discord.Interaction, tipo: str, cantidad: int, objetivo: str, mensaje: str = ""):
        await interaction.response.defer()
        cd = check_cooldown(f"donar:{interaction.user.id}:{interaction.guild_id}", 10)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        if cantidad <= 0:
            await interaction.followup.send(embed=error_embed("Error", "La cantidad debe ser positiva"), ephemeral=True)
            return
        ok = await async_remove_cash(str(interaction.user.id), str(interaction.guild_id), cantidad)
        if not ok:
            await interaction.followup.send(embed=error_embed("Sin fondos", "No tienes suficiente efectivo"), ephemeral=True)
            return
        if tipo == "jugador":
            member = interaction.guild.get_member_named(objetivo)
            if not member:
                try:
                    member = await interaction.guild.fetch_member(int(objetivo))
                except Exception:
                    pass
            if not member:
                await async_add_cash(str(interaction.user.id), str(interaction.guild_id), cantidad)
                await interaction.followup.send(embed=error_embed("No encontrado", "No se encontró ese jugador"), ephemeral=True)
                return
            await async_get_or_create_user(str(member.id), str(interaction.guild_id))
            await async_add_cash(str(member.id), str(interaction.guild_id), cantidad)
            await async_log_transaction(str(interaction.user.id), str(interaction.guild_id), "donation", -cantidad, f"Donación a {member.name}")
            await async_log_transaction(str(member.id), str(interaction.guild_id), "donation", cantidad, f"Donación de {interaction.user.name}")
            target_name = member.mention
        elif tipo == "departamento":
            dept = await aexecute(
                "SELECT * FROM departments WHERE guild_id=$1 AND (acronym ILIKE $2 OR name ILIKE $3)",
                (str(interaction.guild_id), objetivo, objetivo), fetch="one"
            )
            if not dept:
                await async_add_cash(str(interaction.user.id), str(interaction.guild_id), cantidad)
                await interaction.followup.send(embed=error_embed("No encontrado", "No se encontró ese departamento"), ephemeral=True)
                return
            await aexecute("UPDATE departments SET budget=budget+$1, updated_at=NOW() WHERE id=$2", (cantidad, dept["id"]))
            await async_log_transaction(str(interaction.user.id), str(interaction.guild_id), "donation", -cantidad, f"Donación a {dept['name']}")
            target_name = dept["name"]
        else:
            company = await aexecute(
                "SELECT * FROM companies WHERE guild_id=$1 AND name ILIKE $2",
                (str(interaction.guild_id), f"%{objetivo}%"), fetch="one"
            )
            if not company:
                await async_add_cash(str(interaction.user.id), str(interaction.guild_id), cantidad)
                await interaction.followup.send(embed=error_embed("No encontrado", "No se encontró esa empresa"), ephemeral=True)
                return
            await aexecute("UPDATE companies SET funds=funds+$1, updated_at=NOW() WHERE id=$2", (cantidad, company["id"]))
            await async_log_transaction(str(interaction.user.id), str(interaction.guild_id), "donation", -cantidad, f"Donación a {company['name']}")
            target_name = company["name"]
        e = success_embed("Donación realizada", f"Donaste **{format_currency(cantidad)}** a **{target_name}**")
        if mensaje:
            e.add_field(name="Mensaje", value=mensaje, inline=False)
        await interaction.followup.send(embed=e)


async def setup(bot):
    await bot.add_cog(Economy(bot))
