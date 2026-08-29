import discord
from discord import app_commands
from discord.ext import commands
import datetime
import random
import string

from bot.db import aexecute
from bot.helpers import async_get_or_create_user, format_currency, generate_id, check_admin_permission
from bot.embeds import success_embed, error_embed, info_embed, department_embed
from bot.services.economy import async_remove_cash

COOLDOWNS = {}

def check_cooldown(key, seconds):
    now = datetime.datetime.utcnow().timestamp()
    last = COOLDOWNS.get(key, 0)
    remaining = (last + seconds) - now
    if remaining > 0:
        return remaining
    COOLDOWNS[key] = now
    return 0

DEPT_EMOJI = {
    "MPD": "👮",     # Miami Police Department
    "MDFR": "🚒",    # Miami Dade Fire & Rescue
    "FHP": "🚔",     # Florida Highway Patrol
    "FDOT": "🚧",    # Florida Department of Transportation
    "MBPD": "🏖️",   # Miami Beach Police Department
    "FDOJ": "⚖️",    # Florida Department of Justice
    "EMS": "🚑",     # Emergency Medical Services
    "Sheriff": "⭐", # Miami-Dade Sheriff / Police
    "DOJ": "⚖️",
    "CPD": "👮",
    "CFD": "🚒"
}


class ApproveDepartmentAppModal(discord.ui.Modal):
    def __init__(self, app_id: str, dept_id: str, applicant_id: str):
        super().__init__(title="Aprobar Postulación a Departamento")
        self.app_id = app_id
        self.dept_id = dept_id
        self.applicant_id = applicant_id

        self.rank_input = discord.ui.TextInput(
            label="Rango Inicial Asignado",
            placeholder="Ej: Cadete, Oficial I, Bombero Recluta, Agente",
            default="Cadete",
            max_length=50,
            required=True
        )
        self.salary_input = discord.ui.TextInput(
            label="Salario Diario Inicial ($)",
            placeholder="Ej: 500 (0 para salario base)",
            default="500",
            max_length=10,
            required=True
        )
        self.notes_input = discord.ui.TextInput(
            label="Mensaje o Instrucciones de Bienvenida",
            placeholder="Instrucciones para presentarse a la academia...",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=300
        )

        self.add_item(self.rank_input)
        self.add_item(self.salary_input)
        self.add_item(self.notes_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "No tienes autorización para aprobar postulaciones"), ephemeral=True)
            return

        try:
            salary = max(0, int(self.salary_input.value.strip()))
        except ValueError:
            salary = 500

        rank = self.rank_input.value.strip() or "Cadete"

        dept = await aexecute("SELECT * FROM departments WHERE id=$1", (self.dept_id,), fetch="one")
        if not dept:
            await interaction.followup.send(embed=error_embed("Error", "Departamento no encontrado"), ephemeral=True)
            return

        # Check existing member
        existing = await aexecute(
            "SELECT id FROM department_members WHERE department_id=$1 AND discord_id=$2",
            (self.dept_id, self.applicant_id), fetch="one"
        )
        applicant_user = interaction.guild.get_member(int(self.applicant_id))
        user_name = applicant_user.name if applicant_user else "Usuario"

        if existing:
            await aexecute(
                "UPDATE department_members SET rank=$1, salary=$2, username=$3 WHERE id=$4",
                (rank, salary, user_name, existing["id"])
            )
        else:
            await aexecute(
                """INSERT INTO department_members (id, department_id, discord_id, guild_id, rank, salary, joined_at, username)
                   VALUES ($1,$2,$3,$4,$5,$6,NOW(),$7)""",
                (generate_id(), self.dept_id, self.applicant_id, str(interaction.guild_id), rank, salary, user_name)
            )

        await aexecute(
            "UPDATE applications SET status='approved', reviewed_by=$1, updated_at=NOW() WHERE id=$2",
            (str(interaction.user.id), self.app_id)
        )

        if applicant_user and dept.get("role_id"):
            role = interaction.guild.get_role(int(dept["role_id"]))
            if role:
                try:
                    await applicant_user.add_roles(role, reason=f"Postulación aceptada en {dept['name']}")
                except Exception:
                    pass

        await aexecute(
            """INSERT INTO department_audit (id, department_id, guild_id, action, performed_by, target_id, details, created_at)
               VALUES ($1,$2,$3,'application_approved',$4,$5,$6,NOW())""",
            (generate_id(), self.dept_id, str(interaction.guild_id), str(interaction.user.id), self.applicant_id, f"Aprobado con Rango: {rank}, Salario: ${salary}")
        )

        emoji = DEPT_EMOJI.get(dept.get("acronym", ""), "🏢")
        res_emb = success_embed(
            f"✅ Postulación Aprobada — {emoji} {dept['name']}",
            f"**Postulante:** <@{self.applicant_id}>\n"
            f"**Rango asignado:** `{rank}`\n"
            f"**Salario diario:** {format_currency(salary)}\n"
            f"**Revisado por:** {interaction.user.mention}\n"
            f"**Instrucciones:** {self.notes_input.value.strip() or 'Bienvenido al departamento.'}"
        )
        await interaction.followup.send(embed=res_emb)

        # Notify user via DM
        if applicant_user:
            try:
                dm_emb = success_embed(
                    f"🎉 ¡Felicidades! Fuiste aceptado en {dept['name']} [{dept.get('acronym', '')}]",
                    f"Tu solicitud de ingreso fue **Aprobada** por la administración.\n\n"
                    f"🏷️ **Rango:** `{rank}`\n"
                    f"💵 **Salario diario:** {format_currency(salary)}\n"
                    f"💬 **Mensaje:** {self.notes_input.value.strip() or 'Preséntate en la sede correspondiente.'}"
                )
                await applicant_user.send(embed=dm_emb)
            except Exception:
                pass


class RejectDepartmentAppModal(discord.ui.Modal):
    def __init__(self, app_id: str, dept_name: str, applicant_id: str):
        super().__init__(title="Rechazar Postulación")
        self.app_id = app_id
        self.dept_name = dept_name
        self.applicant_id = applicant_id

        self.reason_input = discord.ui.TextInput(
            label="Motivo del Rechazo",
            placeholder="Explica detalladamente por qué no cumple los requisitos...",
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=True
        )
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "No tienes autorización para rechazar postulaciones"), ephemeral=True)
            return

        reason = self.reason_input.value.strip()
        await aexecute(
            "UPDATE applications SET status='denied', reviewed_by=$1, updated_at=NOW() WHERE id=$2",
            (str(interaction.user.id), self.app_id)
        )

        res_emb = error_embed(
            f"❌ Postulación Rechazada — {self.dept_name}",
            f"**Postulante:** <@{self.applicant_id}>\n"
            f"**Revisado por:** {interaction.user.mention}\n"
            f"**Motivo:** {reason}"
        )
        await interaction.followup.send(embed=res_emb)

        applicant_user = interaction.guild.get_member(int(self.applicant_id))
        if applicant_user:
            try:
                dm_emb = error_embed(
                    f"❌ Postulación a {self.dept_name}",
                    f"Lamentamos informarte que tu postulación fue rechazada.\n\n"
                    f"**Motivo oficial:** {reason}\n\n"
                    f"Puedes volver a postularte cuando cumplas los requisitos."
                )
                await applicant_user.send(embed=dm_emb)
            except Exception:
                pass


class DepartmentApplicationReviewView(discord.ui.View):
    def __init__(self, app_id: str, dept_id: str, applicant_id: str, dept_name: str):
        super().__init__(timeout=None)
        self.app_id = app_id
        self.dept_id = dept_id
        self.applicant_id = applicant_id
        self.dept_name = dept_name

    @discord.ui.button(label="Aprobar Solicitud", style=discord.ButtonStyle.success, emoji="✅", custom_id="btn_app_approve")
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message(embed=error_embed("Sin permisos", "Solo administradores autorizados"), ephemeral=True)
            return
        modal = ApproveDepartmentAppModal(self.app_id, self.dept_id, self.applicant_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Rechazar Solicitud", style=discord.ButtonStyle.danger, emoji="❌", custom_id="btn_app_reject")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message(embed=error_embed("Sin permisos", "Solo administradores autorizados"), ephemeral=True)
            return
        modal = RejectDepartmentAppModal(self.app_id, self.dept_name, self.applicant_id)
        await interaction.response.send_modal(modal)


class DepartmentApplicationModal(discord.ui.Modal):
    def __init__(self, dept: dict):
        acronym = dept.get("acronym", "").upper()
        super().__init__(title=f"Postulación a {acronym} — {dept['name'][:25]}")
        self.dept = dept

        self.age_avail = discord.ui.TextInput(
            label="Edad IC / OOC y Disponibilidad Horaria",
            placeholder="Ej: IC: 28 años | OOC: 20 años | Disp: 3-4 horas diarias tardes/noches",
            style=discord.TextStyle.short,
            max_length=150,
            required=True
        )
        self.experience = discord.ui.TextInput(
            label="Experiencia Previa en Roleplay y Servicios",
            placeholder="Detalla tu experiencia previa en servidores RP, rangos ejercidos y conocimientos de radio/códigos...",
            style=discord.TextStyle.paragraph,
            max_length=600,
            required=True
        )
        self.lore_motivation = discord.ui.TextInput(
            label="Historia y Motivación de tu Personaje",
            placeholder="¿Por qué tu personaje desea ingresar a esta institución? ¿Cuáles son sus metas y antecedentes?",
            style=discord.TextStyle.paragraph,
            max_length=600,
            required=True
        )
        self.scenario = discord.ui.TextInput(
            label="Caso Práctico / Actuación en Emergencia",
            placeholder="Describe cómo actuarías ante una situación de alto riesgo, conflicto o emergencia bajo presión...",
            style=discord.TextStyle.paragraph,
            max_length=600,
            required=True
        )

        self.add_item(self.age_avail)
        self.add_item(self.experience)
        self.add_item(self.lore_motivation)
        self.add_item(self.scenario)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        app_id = generate_id()
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)
        acronym = self.dept.get("acronym", "").upper()

        combined_exp = f"[Edad/Disponibilidad]: {self.age_avail.value}\n\n[Experiencia]: {self.experience.value}"
        combined_mot = f"[Motivación/Lore]: {self.lore_motivation.value}\n\n[Caso Práctico]: {self.scenario.value}"

        await aexecute(
            """INSERT INTO applications (id, guild_id, discord_id, type, experience, motivation, status, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,'pending',NOW(),NOW())""",
            (app_id, gid, uid, acronym, combined_exp, combined_mot)
        )

        # Notify review channel
        cfg = await aexecute("SELECT * FROM guild_config WHERE guild_id=$1", (gid,), fetch="one")
        app_channel_id = None
        if cfg:
            app_channel_id = cfg.get("applications_channel_id") or cfg.get("log_channel_id")

        if not app_channel_id:
            # Check application_config fallback
            app_cfg = await aexecute("SELECT log_channel_id FROM application_config WHERE guild_id=$1", (gid,), fetch="one")
            if app_cfg:
                app_channel_id = app_cfg.get("log_channel_id")

        channel = None
        if app_channel_id:
            channel = interaction.guild.get_channel(int(app_channel_id))

        emoji = DEPT_EMOJI.get(acronym, "🏛️")
        rev_emb = info_embed(
            f"📋 Nueva Solicitud Oficial de Ingreso — {emoji} {self.dept['name']} [{acronym}]",
            f"**Postulante:** {interaction.user.mention} (`{interaction.user.name}`)\n"
            f"**ID de Discord:** `{interaction.user.id}`\n"
            f"**ID de Postulación:** `{app_id[:8]}`"
        )
        rev_emb.add_field(name="🕒 Edad & Disponibilidad Horaria", value=self.age_avail.value[:300], inline=False)
        rev_emb.add_field(name="🎖️ Experiencia Previa en Rol", value=self.experience.value[:600], inline=False)
        rev_emb.add_field(name="📖 Historia y Motivación", value=self.lore_motivation.value[:600], inline=False)
        rev_emb.add_field(name="🚨 Caso Práctico / Actuación", value=self.scenario.value[:600], inline=False)
        rev_emb.set_footer(text=f"Fecha: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')} • ID: {app_id}")

        view = DepartmentApplicationReviewView(app_id, self.dept["id"], uid, self.dept["name"])

        if channel:
            try:
                await channel.send(embed=rev_emb, view=view)
            except Exception:
                pass

        await interaction.followup.send(embed=success_embed(
            "📬 Postulación Enviada con Éxito",
            f"Tu solicitud para unirte al **{emoji} {self.dept['name']} [{acronym}]** ha sido registrada correctamente.\n\n"
            f"Los altos mandos y administradores revisarán tus respuestas y recibirás una notificación cuando sea evaluada.\n"
            f"**ID de Solicitud:** `{app_id[:8]}`"
        ), ephemeral=True)


class Departments(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    departamento = app_commands.Group(name="departamento", description="Gestión de departamentos oficiales")

    @departamento.command(name="lista", description="Ver todos los departamentos oficiales del servidor")
    async def lista(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cd = check_cooldown(f"dept:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        depts = await aexecute(
            "SELECT * FROM departments WHERE guild_id=$1 ORDER BY name",
            (str(interaction.guild_id),), fetch="all"
        ) or []
        e = department_embed("🏛️ Departamentos Oficiales de Miami")
        if not depts:
            e.description = "No hay departamentos creados actualmente en el servidor."
        else:
            for d in depts:
                emoji = DEPT_EMOJI.get(d.get("acronym", "").upper(), "🏢")
                count = await aexecute("SELECT COUNT(*) as c FROM department_members WHERE department_id=$1", (d["id"],), fetch="one")
                members = count["c"] if count else 0
                e.add_field(
                    name=f"{emoji} {d['name']} [{d.get('acronym','')}]",
                    value=f"🏷️ **Acrónimo:** `{d.get('acronym','')}`\n👥 **Miembros:** {members}\n💰 **Presupuesto:** {format_currency(d.get('budget',0))}",
                    inline=True
                )
        e.set_footer(text="Para postularte a uno usa: /departamento postular [acronimo]")
        await interaction.followup.send(embed=e)

    @departamento.command(name="info", description="Ver información detallada de un departamento")
    @app_commands.describe(acronimo="Acrónimo del departamento (ej: MPD, MDFR, FHP, FDOT, MBPD, FDOJ)")
    async def info(self, interaction: discord.Interaction, acronimo: str):
        await interaction.response.defer()
        dept = await aexecute(
            "SELECT * FROM departments WHERE guild_id=$1 AND acronym ILIKE $2",
            (str(interaction.guild_id), acronimo.strip()), fetch="one"
        )
        if not dept:
            await interaction.followup.send(embed=error_embed("No encontrado", f"No existe un departamento con acrónimo **{acronimo.upper()}**"), ephemeral=True)
            return
        emoji = DEPT_EMOJI.get(dept.get("acronym", "").upper(), "🏢")
        count = await aexecute("SELECT COUNT(*) as c FROM department_members WHERE department_id=$1", (dept["id"],), fetch="one")
        members = count["c"] if count else 0
        e = department_embed(f"{emoji} {dept['name']} [{dept.get('acronym','')}]", dept.get("description", "Sin descripción oficial"))
        e.add_field(name="💰 Presupuesto", value=format_currency(dept.get("budget", 0)), inline=True)
        e.add_field(name="👥 Miembros Activos", value=str(members), inline=True)
        e.add_field(name="🏷️ Acrónimo Oficial", value=f"`{dept.get('acronym','')}`", inline=True)
        await interaction.followup.send(embed=e)

    @departamento.command(name="postular", description="Enviar solicitud de ingreso a un departamento mediante su acrónimo")
    @app_commands.describe(acronimo="Acrónimo oficial del departamento al que deseas postular (ej: MPD, MDFR, FHP)")
    async def postular(self, interaction: discord.Interaction, acronimo: str):
        cd = check_cooldown(f"dept_postular:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.response.send_message(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return

        cleaned_acronym = acronimo.strip()
        dept = await aexecute(
            "SELECT * FROM departments WHERE guild_id=$1 AND acronym ILIKE $2",
            (str(interaction.guild_id), cleaned_acronym), fetch="one"
        )

        if not dept:
            await interaction.response.send_message(embed=error_embed(
                "Acrónimo Inválido",
                f"❌ Ningún departamento oficial tiene el acrónimo **{cleaned_acronym.upper()}**.\n\n"
                f"Por favor revisa la lista de departamentos activos con `/departamento lista` e introduce el acrónimo correcto."
            ), ephemeral=True)
            return

        # Check if user is already a member
        existing_member = await aexecute(
            "SELECT id FROM department_members WHERE department_id=$1 AND discord_id=$2",
            (dept["id"], str(interaction.user.id)), fetch="one"
        )
        if existing_member:
            await interaction.response.send_message(embed=error_embed(
                "Ya eres miembro",
                f"Ya perteneces actualmente al departamento **{dept['name']}**."
            ), ephemeral=True)
            return

        # Check pending application
        existing_app = await aexecute(
            "SELECT id FROM applications WHERE guild_id=$1 AND discord_id=$2 AND type=$3 AND status='pending'",
            (str(interaction.guild_id), str(interaction.user.id), dept.get("acronym", "").upper()), fetch="one"
        )
        if existing_app:
            await interaction.response.send_message(embed=error_embed(
                "Postulación Pendiente",
                f"Ya tienes una postulación en revisión para **{dept['name']}**. Espera a que sea evaluada por los mandos."
            ), ephemeral=True)
            return

        modal = DepartmentApplicationModal(dept)
        await interaction.response.send_modal(modal)

    @departamento.command(name="unirse", description="Alias de postular: Enviar solicitud con acrónimo")
    @app_commands.describe(acronimo="Acrónimo del departamento")
    async def unirse(self, interaction: discord.Interaction, acronimo: str):
        # Redirect to postular logic
        await self.postular(interaction, acronimo)

    @departamento.command(name="mis_postulaciones", description="Ver el historial y estado de tus postulaciones a departamentos")
    async def mis_postulaciones(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        apps = await aexecute(
            "SELECT * FROM applications WHERE guild_id=$1 AND discord_id=$2 ORDER BY created_at DESC LIMIT 10",
            (str(interaction.guild_id), str(interaction.user.id)), fetch="all"
        ) or []

        e = info_embed("📋 Tus Postulaciones a Departamentos")
        if not apps:
            e.description = "No has enviado ninguna postulación a departamentos aún."
        else:
            status_emojis = {"pending": "⏳ Pendiente", "approved": "✅ Aprobada", "denied": "❌ Rechazada"}
            lines = []
            for a in apps:
                status_txt = status_emojis.get(a.get("status"), a.get("status"))
                dept_code = a.get("type", "Departamento")
                date_txt = str(a.get("created_at", ""))[:16]
                lines.append(f"• **{dept_code}** — {status_txt} (`{a['id'][:8]}`) • *{date_txt}*")
            e.description = "\n".join(lines)

        await interaction.followup.send(embed=e, ephemeral=True)

    @departamento.command(name="contratar", description="Contratar o ascender a un miembro directamente (Admin/Mandos)")
    @app_commands.describe(usuario="Usuario", acronimo="Acrónimo del departamento", rango="Rango asignado", salario="Salario diario")
    async def contratar(self, interaction: discord.Interaction, usuario: discord.Member, acronimo: str, rango: str = "Oficial", salario: int = 500):
        await interaction.response.defer()
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Necesitas permisos de administración autorizados"), ephemeral=True)
            return

        dept = await aexecute("SELECT * FROM departments WHERE guild_id=$1 AND acronym ILIKE $2", (str(interaction.guild_id), acronimo.strip()), fetch="one")
        if not dept:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Departamento con acrónimo **{acronimo.upper()}** no existe"), ephemeral=True)
            return

        existing = await aexecute("SELECT id FROM department_members WHERE department_id=$1 AND discord_id=$2", (dept["id"], str(usuario.id)), fetch="one")
        if existing:
            await aexecute("UPDATE department_members SET rank=$1, salary=$2, username=$3 WHERE id=$4", (rango, max(0, salario), usuario.name, existing["id"]))
        else:
            await aexecute(
                """INSERT INTO department_members (id, department_id, discord_id, guild_id, rank, salary, joined_at, username)
                   VALUES ($1,$2,$3,$4,$5,$6,NOW(),$7)""",
                (generate_id(), dept["id"], str(usuario.id), str(interaction.guild_id), rango, max(0, salario), usuario.name)
            )

        await async_get_or_create_user(str(usuario.id), str(interaction.guild_id), username=usuario.name, display_name=usuario.display_name)
        if dept.get("role_id"):
            role = interaction.guild.get_role(int(dept["role_id"]))
            if role:
                try:
                    await usuario.add_roles(role, reason=f"Contratado en {dept['name']}")
                except Exception:
                    pass

        await aexecute(
            """INSERT INTO department_audit (id, department_id, guild_id, action, performed_by, target_id, details, created_at)
               VALUES ($1,$2,$3,'hire',$4,$5,$6,NOW())""",
            (generate_id(), dept["id"], str(interaction.guild_id), str(interaction.user.id), str(usuario.id), f"Rango: {rango}, Salario: ${salario}")
        )
        emoji = DEPT_EMOJI.get(dept.get("acronym", "").upper(), "🏢")
        await interaction.followup.send(embed=success_embed(f"Contratado — {emoji} {dept['name']}", f"{usuario.mention} asignado como **{rango}** con salario diario de {format_currency(salario)}"))

    @departamento.command(name="despedir", description="Dar de baja a un miembro de un departamento (Admin/Mandos)")
    @app_commands.describe(usuario="Usuario a dar de baja", acronimo="Acrónimo del departamento")
    async def despedir(self, interaction: discord.Interaction, usuario: discord.Member, acronimo: str):
        await interaction.response.defer()
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Necesitas permisos de administración autorizados"), ephemeral=True)
            return

        dept = await aexecute("SELECT * FROM departments WHERE guild_id=$1 AND acronym ILIKE $2", (str(interaction.guild_id), acronimo.strip()), fetch="one")
        if not dept:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Departamento con acrónimo **{acronimo.upper()}** no existe"), ephemeral=True)
            return

        member_row = await aexecute("SELECT id FROM department_members WHERE department_id=$1 AND discord_id=$2", (dept["id"], str(usuario.id)), fetch="one")
        if not member_row:
            await interaction.followup.send(embed=error_embed("No es miembro", f"{usuario.mention} no pertenece a **{dept['name']}**"), ephemeral=True)
            return

        await aexecute("DELETE FROM department_members WHERE id=$1", (member_row["id"],))
        if dept.get("role_id"):
            role = interaction.guild.get_role(int(dept["role_id"]))
            if role:
                try:
                    await usuario.remove_roles(role, reason=f"Despedido de {dept['name']}")
                except Exception:
                    pass

        await aexecute(
            """INSERT INTO department_audit (id, department_id, guild_id, action, performed_by, target_id, details, created_at)
               VALUES ($1,$2,$3,'fire',$4,$5,'Baja administrativa',NOW())""",
            (generate_id(), dept["id"], str(interaction.guild_id), str(interaction.user.id), str(usuario.id))
        )
        await interaction.followup.send(embed=success_embed("Baja Completada", f"{usuario.mention} fue dado de baja de **{dept['name']}**"))

    @departamento.command(name="presupuesto", description="Consultar el presupuesto de un departamento")
    @app_commands.describe(acronimo="Acrónimo del departamento")
    async def presupuesto(self, interaction: discord.Interaction, acronimo: str):
        await interaction.response.defer()
        dept = await aexecute("SELECT * FROM departments WHERE guild_id=$1 AND acronym ILIKE $2", (str(interaction.guild_id), acronimo.strip()), fetch="one")
        if not dept:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Departamento con acrónimo **{acronimo.upper()}** no existe"), ephemeral=True)
            return
        emoji = DEPT_EMOJI.get(dept.get("acronym", "").upper(), "🏢")
        e = department_embed(f"{emoji} Presupuesto — {dept['name']}")
        e.add_field(name="💰 Fondos Asignados", value=format_currency(dept.get("budget", 0)), inline=True)
        await interaction.followup.send(embed=e)

    @departamento.command(name="miembros", description="Ver el roster o lista de oficiales/miembros del departamento")
    @app_commands.describe(acronimo="Acrónimo del departamento")
    async def miembros(self, interaction: discord.Interaction, acronimo: str):
        await interaction.response.defer()
        dept = await aexecute("SELECT * FROM departments WHERE guild_id=$1 AND acronym ILIKE $2", (str(interaction.guild_id), acronimo.strip()), fetch="one")
        if not dept:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Departamento con acrónimo **{acronimo.upper()}** no existe"), ephemeral=True)
            return

        members = await aexecute(
            """SELECT dm.*, u.username as user_name, u.display_name as user_display_name
               FROM department_members dm
               LEFT JOIN users u ON u.discord_id = dm.discord_id AND u.guild_id = dm.guild_id
               WHERE dm.department_id=$1 
               ORDER BY dm.joined_at""",
            (dept["id"],), fetch="all"
        ) or []

        emoji = DEPT_EMOJI.get(dept.get("acronym", "").upper(), "🏢")
        e = department_embed(f"{emoji} Roster de Miembros — {dept['name']}")
        if not members:
            e.description = "No hay miembros registrados en este departamento."
        else:
            lines = []
            for m in members:
                uname = m.get("username") or m.get("user_name")
                dname = m.get("user_display_name")
                tag = f"**{uname}** (@{dname})" if uname and dname and uname != dname else f"**{uname or 'Usuario'}**"
                lines.append(f"{tag} — `<@{m['discord_id']}>` | **{m.get('rank','Oficial')}** | {format_currency(m.get('salary',0))}/día")
            e.description = "\n".join(lines)
        await interaction.followup.send(embed=e)

    flota = app_commands.Group(name="flota", description="Gestión de flota vehicular departamental")

    @flota.command(name="ver", description="Ver la flota de vehículos del departamento")
    @app_commands.describe(acronimo="Acrónimo del departamento")
    async def flota_ver(self, interaction: discord.Interaction, acronimo: str):
        await interaction.response.defer()
        dept = await aexecute("SELECT * FROM departments WHERE guild_id=$1 AND acronym ILIKE $2", (str(interaction.guild_id), acronimo.strip()), fetch="one")
        if not dept:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Departamento con acrónimo **{acronimo.upper()}** no existe"), ephemeral=True)
            return

        vehicles = await aexecute(
            """SELECT fv.*, fvt.name as type_name, fvt.price FROM fleet_vehicles fv
               JOIN fleet_vehicle_types fvt ON fvt.id=fv.vehicle_type_id
               WHERE fv.department_id=$1 ORDER BY fv.status, fvt.name""",
            (dept["id"],), fetch="all"
        ) or []

        emoji = DEPT_EMOJI.get(dept.get("acronym", "").upper(), "🏢")
        e = department_embed(f"{emoji} Flota de Vehículos — {dept['name']}")
        if not vehicles:
            e.description = "No hay vehículos asignados a esta flota actualmente."
        else:
            status_emoji = {"active": "✅", "repairing": "🔧", "returned": "📦", "damaged": "❌", "in_use": "🚗"}
            lines = [f"🚗 **{v['type_name']}** `{v.get('plate','N/A')}` — {status_emoji.get(v.get('status','active'),'❓')} {v.get('status','active').title()}" for v in vehicles]
            e.description = "\n".join(lines)
        await interaction.followup.send(embed=e)

    @flota.command(name="comprar", description="Comprar vehículos para la flota del departamento (Admin/Mandos)")
    @app_commands.describe(
        acronimo="Acrónimo del departamento",
        tipo="Tipo o modelo del vehículo",
        cantidad="Cantidad de vehículos",
        valor_unitario="Valor por unidad"
    )
    async def flota_comprar(self, interaction: discord.Interaction, acronimo: str, tipo: str, cantidad: int = 1, valor_unitario: float = None):
        await interaction.response.defer()
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Necesitas permisos de administración autorizados"), ephemeral=True)
            return

        if cantidad < 1:
            await interaction.followup.send(embed=error_embed("Error", "La cantidad mínima es 1 vehículo"), ephemeral=True)
            return

        dept = await aexecute("SELECT * FROM departments WHERE guild_id=$1 AND acronym ILIKE $2", (str(interaction.guild_id), acronimo.strip()), fetch="one")
        if not dept:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Departamento con acrónimo **{acronimo.upper()}** no existe"), ephemeral=True)
            return

        vtype = await aexecute("SELECT * FROM fleet_vehicle_types WHERE guild_id=$1 AND name ILIKE $2 LIMIT 1", (str(interaction.guild_id), f"%{tipo}%"), fetch="one")
        if vtype:
            unit_price = float(valor_unitario if valor_unitario is not None else vtype.get("price", 0))
            vehicle_type_id = vtype["id"]
            vehicle_type_name = vtype["name"]
        else:
            if valor_unitario is None:
                await interaction.followup.send(embed=error_embed("Falta el valor", "Indica el valor por unidad para registrar este modelo"), ephemeral=True)
                return
            unit_price = float(valor_unitario)
            vehicle_type_id = generate_id()
            vehicle_type_name = tipo

        total = round(unit_price * cantidad, 2)
        if float(dept.get("budget", 0)) < total:
            await interaction.followup.send(embed=error_embed("Presupuesto insuficiente", f"El departamento requiere {format_currency(total)} pero solo tiene {format_currency(dept.get('budget',0))}"), ephemeral=True)
            return

        if not vtype:
            await aexecute(
                """INSERT INTO fleet_vehicle_types (id, guild_id, name, price, created_at, updated_at)
                   VALUES ($1,$2,$3,$4,NOW(),NOW())""",
                (vehicle_type_id, str(interaction.guild_id), vehicle_type_name, unit_price)
            )

        await aexecute("UPDATE departments SET budget=budget-$1, updated_at=NOW() WHERE id=$2", (total, dept["id"]))
        plates = []
        for _ in range(cantidad):
            plate = "".join(random.choices(string.ascii_uppercase + string.digits, k=7))
            plates.append(plate)
            await aexecute(
                """INSERT INTO fleet_vehicles (id, department_id, guild_id, vehicle_type_id, plate, status, created_at, updated_at)
                   VALUES ($1,$2,$3,$4,$5,'active',NOW(),NOW())""",
                (generate_id(), dept["id"], str(interaction.guild_id), vehicle_type_id, plate)
            )

        emoji = DEPT_EMOJI.get(dept.get("acronym", "").upper(), "🏢")
        await interaction.followup.send(embed=success_embed(
            f"{emoji} Flota Adquirida",
            f"**{vehicle_type_name}** x{cantidad}\n"
            f"**Placas:** {', '.join(f'`{p}`' for p in plates[:5])}{'...' if len(plates) > 5 else ''}\n"
            f"**Total abonado del presupuesto:** {format_currency(total)}"
        ))

    @flota.command(name="solicitar", description="Solicitar un vehículo de la flota para patrullaje/servicio")
    @app_commands.describe(acronimo="Acrónimo del departamento", placa="Placa del vehículo")
    async def flota_solicitar(self, interaction: discord.Interaction, acronimo: str, placa: str):
        await interaction.response.defer()
        dept = await aexecute("SELECT * FROM departments WHERE guild_id=$1 AND acronym ILIKE $2", (str(interaction.guild_id), acronimo.strip()), fetch="one")
        if not dept:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Departamento con acrónimo **{acronimo.upper()}** no existe"), ephemeral=True)
            return

        member_row = await aexecute(
            "SELECT id FROM department_members WHERE department_id=$1 AND discord_id=$2",
            (dept["id"], str(interaction.user.id)), fetch="one"
        )
        if not member_row:
            await interaction.followup.send(embed=error_embed("No eres miembro", f"Debes pertenecer a **{dept['name']}** para patrullar en sus vehículos"), ephemeral=True)
            return

        vehicle = await aexecute(
            "SELECT fv.*, fvt.name as type_name FROM fleet_vehicles fv JOIN fleet_vehicle_types fvt ON fvt.id=fv.vehicle_type_id WHERE fv.department_id=$1 AND fv.plate ILIKE $2 AND fv.status='active'",
            (dept["id"], f"%{placa.strip()}%"), fetch="one"
        )
        if not vehicle:
            await interaction.followup.send(embed=error_embed("No disponible", f"Vehículo con placa `{placa}` no encontrado o no disponible"), ephemeral=True)
            return

        await aexecute("UPDATE fleet_vehicles SET status='in_use', assigned_to=$1, updated_at=NOW() WHERE id=$2", (str(interaction.user.id), vehicle["id"]))
        emoji = DEPT_EMOJI.get(dept.get("acronym", "").upper(), "🏢")
        await interaction.followup.send(embed=success_embed(f"{emoji} Unidad Asignada", f"**{vehicle['type_name']}** (Placa: `{vehicle['plate']}`) está ahora en tu posesión."))

    @flota.command(name="devolver", description="Devolver el vehículo asignado a la base")
    @app_commands.describe(placa="Placa del vehículo")
    async def flota_devolver(self, interaction: discord.Interaction, placa: str):
        await interaction.response.defer()
        vehicle = await aexecute(
            "SELECT fv.*, fvt.name as type_name, d.name as dept_name, d.acronym FROM fleet_vehicles fv JOIN fleet_vehicle_types fvt ON fvt.id=fv.vehicle_type_id JOIN departments d ON d.id=fv.department_id WHERE fv.guild_id=$1 AND fv.assigned_to=$2 AND fv.plate ILIKE $3",
            (str(interaction.guild_id), str(interaction.user.id), f"%{placa.strip()}%"), fetch="one"
        )
        if not vehicle:
            await interaction.followup.send(embed=error_embed("No encontrado", f"No tienes ningún vehículo con placa `{placa}` asignado"), ephemeral=True)
            return

        await aexecute("UPDATE fleet_vehicles SET status='active', assigned_to=NULL, updated_at=NOW() WHERE id=$1", (vehicle["id"],))
        await interaction.followup.send(embed=success_embed("Unidad Devuelta", f"**{vehicle['type_name']}** (Placa: `{vehicle['plate']}`) devuelto a la sede de **{vehicle['dept_name']}**."))

    @flota.command(name="reparar", description="Enviar un vehículo al taller mecánico para reparaciones")
    @app_commands.describe(placa="Placa del vehículo", razon="Motivo o reporte de avería")
    async def flota_reparar(self, interaction: discord.Interaction, placa: str, razon: str = "Avería en patrullaje"):
        await interaction.response.defer()
        vehicle = await aexecute(
            "SELECT fv.*, fvt.name as type_name, d.name as dept_name, d.acronym FROM fleet_vehicles fv JOIN fleet_vehicle_types fvt ON fvt.id=fv.vehicle_type_id JOIN departments d ON d.id=fv.department_id WHERE fv.guild_id=$1 AND fv.plate ILIKE $2",
            (str(interaction.guild_id), f"%{placa.strip()}%"), fetch="one"
        )
        if not vehicle:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Vehículo con placa `{placa}` no encontrado"), ephemeral=True)
            return

        await aexecute("UPDATE fleet_vehicles SET status='repairing', assigned_to=NULL, updated_at=NOW() WHERE id=$1", (vehicle["id"],))
        await interaction.followup.send(embed=success_embed("🔧 Unidad en Taller", f"**{vehicle['type_name']}** (Placa: `{vehicle['plate']}`) enviada a reparación.\n**Motivo:** {razon}"))

    @flota.command(name="gestionar", description="Cambiar el estado de un vehículo de la flota (Admin/Mandos)")
    @app_commands.describe(placa="Placa del vehículo", estado="Nuevo estado de la unidad")
    @app_commands.choices(estado=[
        app_commands.Choice(name="✅ Activo (Disponible)", value="active"),
        app_commands.Choice(name="🔧 En Reparación (Taller)", value="repairing"),
        app_commands.Choice(name="❌ Dañado / Fuera de servicio", value="damaged"),
        app_commands.Choice(name="📦 Retirado / Baja de inventario", value="returned"),
    ])
    async def flota_gestionar(self, interaction: discord.Interaction, placa: str, estado: str):
        await interaction.response.defer()
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Necesitas permisos de administración autorizados"), ephemeral=True)
            return

        vehicle = await aexecute(
            "SELECT fv.*, fvt.name as type_name FROM fleet_vehicles fv JOIN fleet_vehicle_types fvt ON fvt.id=fv.vehicle_type_id WHERE fv.guild_id=$1 AND fv.plate ILIKE $2",
            (str(interaction.guild_id), f"%{placa.strip()}%"), fetch="one"
        )
        if not vehicle:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Vehículo con placa `{placa}` no encontrado"), ephemeral=True)
            return

        await aexecute("UPDATE fleet_vehicles SET status=$1, assigned_to=NULL, updated_at=NOW() WHERE id=$2", (estado, vehicle["id"]))
        await interaction.followup.send(embed=success_embed("Estado de Flota Actualizado", f"**{vehicle['type_name']}** (Placa: `{vehicle['plate']}`) cambiado a **{estado}**"))


async def setup(bot):
    await bot.add_cog(Departments(bot))
