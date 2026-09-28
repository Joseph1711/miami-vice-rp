"""Empleos publicos del servidor: tablon, solicitud y administracion.

El sueldo sale siempre de la Tesoreria Municipal (`treasury`), que es una cuenta
real del servidor. Si la Tesoreria esta vacia el sueldo es 0: nunca se inventa
dinero. La administracion de la oferta (crear, editar, cerrar, fixer sueldo) es
parastaff del servidor.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.db import aexecute
from bot.embeds import error_embed, info_embed, success_embed, warning_embed
from bot.helpers import check_admin_permission
from bot.services import business as B
from bot.services import business_ui as UI

logger = logging.getLogger("bot.jobs")

# Segundos que se mantiene vivo un selector de empleo.
SELECT_TIMEOUT = 120.0

# Anti-doble pulsacion al presentarse desde el tablón público.
APPLY_COOLDOWN = 3.0


class PublicJobApplyView(discord.ui.View):
    """Selector de empleo publico con confirmacion en el mismo sitio.

    En modo `public` el tablón se envía a un canal visible para todos y cada
    ciudadano puede usar el selector: la solicitud se registra a su nombre y la
    respuesta le llega en privado. En modo privado el tablón solo es del
    ciudadano que lo pidió.
    """

    def __init__(self, guild_id: str, viewer_id: str, jobs, timeout: float = SELECT_TIMEOUT,
                 public: bool = False):
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.viewer_id = viewer_id
        self.public = public
        options = [
            discord.SelectOption(
                label=(job.get("name") or "Empleo")[:100],
                value=job["id"],
                description=f"{UI.money(job.get('salary'))} diarios"[:100],
                emoji=(job.get("emoji") or "\U0001F9FA")[:2],
            )
            for job in jobs[:25]
        ]
        if not options:
            options = [discord.SelectOption(
                label="No hay empleos disponibles", value="none",
                description="Pide al staff que publique empleo")]
        self.add_item(discord.ui.Select(
            placeholder="Elige el empleo al que quieres presentarte",
            min_values=1, max_values=1, options=options))

    async def select_callback(self, interaction: discord.Interaction):
        if not self.public and str(interaction.user.id) != self.viewer_id:
            await interaction.response.send_message(
                embed=error_embed("Este tablero no es tuyo", "Pide `/empleos` para abrir tu propio tablon."),
                ephemeral=True)
            return
        job_id = self.children[0].values[0]
        if job_id == "none":
            await interaction.response.send_message(
                embed=warning_embed("Sin oferta", "Ahora mismo no hay empleos públicos abiertos."),
                ephemeral=True)
            if not self.public:
                self.stop()
            return
        # En el tablón público la vista no se autodestruye, así que el mismo
        # ciudadano podría seguir pulsando. Se limita igual que los botones.
        if self.public:
            try:
                await B.claim_action(
                    f"empleo:{self.guild_id}:{interaction.user.id}", APPLY_COOLDOWN)
            except B.ActionInProgress as locked:
                await interaction.response.send_message(
                    embed=warning_embed("Espera", str(locked)), ephemeral=True)
                return
            try:
                await apply_to_public_job(interaction, self.guild_id, job_id)
            finally:
                B.release_action(f"empleo:{self.guild_id}:{interaction.user.id}")
            return
        await apply_to_public_job(interaction, self.guild_id, job_id)
        # El tablón privado era de un solo uso; el público sigue en pie
        # para que el siguiente ciudadano pueda presentarse.
        self.stop()


async def apply_to_public_job(interaction: discord.Interaction, guild_id: str, job_id: str):
    """Contratacion en un empleo publico: rol de Discord, perfil y registro."""
    await interaction.response.defer(ephemeral=True)
    user_id = str(interaction.user.id)
    try:
        result = await B.assign_public_job(guild_id, user_id, job_id)
    except B.BusinessError as error:
        await interaction.followup.send(embed=error_embed("No puedes entrar", str(error)), ephemeral=True)
        return
    except B.InsufficientFunds:
        await interaction.followup.send(
            embed=error_embed("No puedes entrar", "Ese puesto exige una cuota que no puedes pagar."),
            ephemeral=True)
        return

    job = result["job"]
    role = None
    if job.get("role_id"):
        role = interaction.guild.get_role(int(job["role_id"]))
        if role and (interaction.user.guild_permissions.manage_roles
                     or role < interaction.user.top_role):
            try:
                await interaction.user.add_roles(role, reason=f"Empleo público: {job.get('name')}")
            except discord.Forbidden:
                role = None

    # El rol del empleo anterior se retira: si no, el ciudadano acumularia
    # roles de trabajos que ya no ocupa.
    for previous in result.get("replaced") or []:
        await _remove_job_roles(interaction.guild, interaction.user, previous)

    embed = success_embed(
        f"Contratado en {job.get('name')}",
        f"<@{user_id}> ya forma parte del personal de **{job.get('name')}**.",
    )
    embed.add_field(name="Sueldo diario", value=UI.money(result["salary"]), inline=True)
    embed.add_field(name="Forma de pago", value="`/sueldo` (sale de la Tesorería Municipal)", inline=True)
    if role:
        embed.add_field(name="Rol de Discord", value=role.mention, inline=True)
    if result.get("replaced"):
        old = result["replaced"][0].get("job_name")
        embed.description = (
            f"Antes ocupabas **{old}**. Este servidor solo permite un empleo público "
            f"activo a la vez, así que el anterior se ha cerrado."
        )
    await interaction.followup.send(embed=embed, ephemeral=True)


async def save_public_job(interaction: discord.Interaction, guild_id: str, job, name: str,
                          salary: int, description: str, role_id, emoji: str, max_workers: int):
    """Alta o edicion de un empleo publico (solo administracion)."""
    if not await check_admin_permission(interaction):
        await interaction.response.send_message(
            embed=error_embed("Sin permisos", "Solo administracion autorizada puede publicar empleos."),
            ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    name = (name or "").strip()
    if len(name) < 2:
        await interaction.followup.send(
            embed=error_embed("Nombre invalido", "El empleo necesita un nombre de 2 caracteres o mas."),
            ephemeral=True)
        return
    salary = max(0, B.money(salary))
    if salary <= 0:
        await interaction.followup.send(
            embed=error_embed("Sueldo invalido", "El sueldo diario debe ser mayor que cero."),
            ephemeral=True)
        return

    try:
        if job:
            result = await B.update_public_job(
                guild_id, job["id"], name, salary, description or "", role_id,
                emoji or "\U0001F9FA", max_workers)
            verb = "actualizado"
        else:
            result = await B.create_public_job(
                guild_id, name, salary, description or "", role_id,
                emoji or "\U0001F9FA", max_workers)
            verb = "publicado"
    except B.BusinessError as error:
        await interaction.followup.send(
            embed=error_embed("No se pudo guardar", str(error)),
            ephemeral=True)
        return
    except Exception as error:
        logger.error("[Empleos] Error guardando empleo: %s", error, exc_info=True)
        await interaction.followup.send(
            embed=error_embed("No se pudo guardar", "Ha ocurrido un error de base de datos."),
            ephemeral=True)
        return

    embed = success_embed(f"Empleo {verb}", f"**{name}** · sueldo {UI.money(salary)} diarios.")
    if role_id:
        embed.add_field(name="Rol de Discord", value=f"<@&{role_id}>", inline=True)
    if max_workers:
        embed.add_field(name="Plazas", value=f"máximo {max_workers}", inline=True)
    if result["created"] is False:
        embed.set_footer(text="El sueldo nuevo se aplicó a toda la plantilla existente")

    channel_id = await _jobs_channel(guild_id)
    if channel_id:
        guild = interaction.guild
        channel = guild.get_channel(int(channel_id)) if channel_id != "auto" else None
        if channel:
            await channel.send(embed=embed)
    await interaction.followup.send(embed=embed, ephemeral=True)


async def _jobs_channel(guild_id: str):
    return await B.get_jobs_channel(guild_id)


class Jobs(commands.Cog):
    """Tablon de empleos publicos y su administracion."""

    def __init__(self, bot):
        self.bot = bot

    employment = app_commands.Group(
        name="empleos",
        description="Empleos publicos del servidor (policia, bomberos, sanidad...)",
    )

    @employment.command(name="listar", description="Ver los empleos publicos disponibles")
    async def listar(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild_id = str(interaction.guild_id)
        jobs = await B.list_public_jobs(guild_id)
        # Tablon publico: el embed va sin datos del invocante y el selector lo
        # puede usar cualquier ciudadano, que recibe la respuesta en privado.
        embed = UI.public_jobs_embed(jobs, None, None)
        if jobs:
            embed.set_footer(text="Usa el selector para entrar en un empleo")
        else:
            embed.set_footer(text="Pide al staff que publique empleos con /empleos predeterminados")
        await interaction.followup.send(embed=embed, view=PublicJobApplyView(
            guild_id, str(interaction.user.id), jobs, public=True))

    @employment.command(name="predeterminados",
                        description="Publicar el catalogo oficial de empleos publicos (administracion)")
    async def predeterminados(self, interaction: discord.Interaction):
        """Siembra los empleos del catalogo oficial que falten en el servidor.

        No duplica ni pisa nada: los empleos ya publicados se dejan como estan,
        con el sueldo y la descripcion que el admin haya configurado.
        """
        if not await check_admin_permission(interaction):
            await interaction.response.send_message(
                embed=error_embed("Sin permisos", "Solo administracion puede publicar empleos."),
                ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        try:
            result = await B.seed_default_jobs(guild_id)
        except Exception as error:
            logger.error("[Empleos] Error sembrando el catalogo: %s", error, exc_info=True)
            await interaction.followup.send(
                embed=error_embed("No se pudo cargar", "Ha ocurrido un error de base de datos."),
                ephemeral=True)
            return

        created, existing = result["created"], result["existing"]
        if created:
            embed = success_embed(
                "Catalogo de empleos publicado",
                f"**{len(created)}** empleos nuevos en el tablon.")
            embed.add_field(
                name="Nuevos",
                value="\n".join(f"• {n}" for n in created)[:1024],
                inline=False,
            )
        else:
            embed = info_embed(
                "Catalogo ya cargado",
                f"Los **{len(existing)}** empleos oficiales ya estaban publicados. "
                "No se ha creado ni modificado nada.")

        if existing:
            embed.add_field(
                name="Ya existentes (intactos)",
                value="\n".join(f"• {n}" for n in existing)[:1024],
                inline=False,
            )
        embed.set_footer(text="Puedes cambiar sueldo y datos con /empleos editar y /empleos sueldo")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @employment.command(name="mios", description="Ver tus empleos publicos activos")
    async def mios(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        jobs = await B.user_public_jobs(guild_id, str(interaction.user.id))
        if not jobs:
            await interaction.followup.send(
                embed=info_embed("Sin empleos", "No ocupas ningun empleo publico. Mira `/empleos listar`."),
                ephemeral=True)
            return
        lines = []
        for job in jobs:
            paid = job.get("last_paid_at")
            lines.append(
                f"{job.get('emoji') or '\U0001F9FA'} **{job.get('job_name')}** — "
                f"{UI.money(job.get('salary'))} diarios\n"
                f"└ contratado: `{job.get('hired_at')}` · ultimo cobro: "
                f"{'sin cobrar' if not paid else f'`{paid}`'}"
            )
        embed = success_embed("Tus empleos publicos", "\n\n".join(lines))
        embed.set_footer(text="Cobra con /sueldo · renuncia con /empleos renunciar")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @employment.command(name="entrar", description="Entrar en un empleo publico por su nombre")
    @app_commands.describe(empleo="Nombre exacto del empleo")
    async def entrar(self, interaction: discord.Interaction, empleo: str):
        guild_id = str(interaction.guild_id)
        job = await B.find_public_job(guild_id, empleo, include_closed=True)
        if not job:
            await interaction.response.send_message(
                embed=error_embed("No existe", f"No hay ningun empleo llamado **{empleo}**."),
                ephemeral=True)
            return
        await apply_to_public_job(interaction, guild_id, job["id"])

    @employment.command(name="renunciar", description="Renunciar a tu empleo publico actual")
    async def renunciar(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        try:
            left = await B.leave_public_job(guild_id, str(interaction.user.id))
        except B.BusinessError as error:
            await interaction.followup.send(embed=error_embed("No puedes renunciar", str(error)),
                                           ephemeral=True)
            return
        await _remove_job_roles(interaction.guild, interaction.user, left)
        await interaction.followup.send(
            embed=success_embed("Renuncia registrada",
                                f"Has dejado de ocupar **{left.get('job_name')}**."),
            ephemeral=True)

    @employment.command(name="crear", description="Publicar un empleo publico (administracion)")
    async def crear(self, interaction: discord.Interaction):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message(
                embed=error_embed("Sin permisos", "Solo administracion puede publicar empleos."),
                ephemeral=True)
            return
        guild_id = str(interaction.guild_id)
        await interaction.response.send_modal(UI.PublicJobModal(guild_id))
        treasury = await B.get_treasury(guild_id)
        await interaction.followup.send(
            content=(f"El sueldo se pagara desde la **Tesorería Municipal** "
                     f"(saldo actual: {UI.money((treasury or {}).get('balance'))})."),
            ephemeral=True,
        )

    @employment.command(name="editar", description="Editar un empleo publico (administracion)")
    @app_commands.describe(empleo="Nombre exacto del empleo")
    async def editar(self, interaction: discord.Interaction, empleo: str):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message(
                embed=error_embed("Sin permisos", "Solo administracion puede editar empleos."),
                ephemeral=True)
            return
        guild_id = str(interaction.guild_id)
        job = await B.find_public_job(guild_id, empleo, include_closed=True)
        if not job:
            await interaction.response.send_message(
                embed=error_embed("No existe", f"No hay ningun empleo llamado **{empleo}**."),
                ephemeral=True)
            return
        await interaction.response.send_modal(UI.PublicJobModal(guild_id, job))

    @employment.command(name="cerrar", description="Cerrar un empleo publico (administracion)")
    @app_commands.describe(empleo="Nombre exacto del empleo")
    async def cerrar(self, interaction: discord.Interaction, empleo: str):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message(
                embed=error_embed("Sin permisos", "Solo administracion puede cerrar empleos."),
                ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        job = await B.find_public_job(guild_id, empleo, include_closed=True)
        if not job:
            await interaction.followup.send(
                embed=error_embed("No existe", f"No hay ningun empleo llamado **{empleo}**."),
                ephemeral=True)
            return
        try:
            await B.set_public_job_status(guild_id, job["id"], False)
        except B.BusinessError as error:
            await interaction.followup.send(
                embed=error_embed("Sin cambios", str(error)), ephemeral=True)
            return
        await interaction.followup.send(
            embed=warning_embed("Empleo cerrado",
                                f"**{job.get('name')}** ya no admite nuevos candidatos"),
            ephemeral=True)

    @employment.command(name="reanudar", description="Reabrir un empleo publico (administracion)")
    @app_commands.describe(empleo="Nombre exacto del empleo")
    async def reanudar(self, interaction: discord.Interaction, empleo: str):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message(
                embed=error_embed("Sin permisos", "Solo administracion puede reabrir empleos."),
                ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        job = await B.find_public_job(guild_id, empleo, include_closed=True)
        if not job:
            await interaction.followup.send(
                embed=error_embed("No existe", f"No hay ningun empleo llamado **{empleo}**."),
                ephemeral=True)
            return
        try:
            await B.set_public_job_status(guild_id, job["id"], True)
        except B.BusinessError as error:
            await interaction.followup.send(
                embed=error_embed("Sin cambios", str(error)), ephemeral=True)
            return
        await interaction.followup.send(
            embed=success_embed("Empleo reabierto", f"**{job.get('name')}** vuelve a admitir personal."),
            ephemeral=True)

    @employment.command(name="sueldo", description="Cambiar el sueldo de un empleo publico (administracion)")
    @app_commands.describe(empleo="Nombre exacto del empleo", sueldo="Nuevo sueldo diario")
    async def sueldo(self, interaction: discord.Interaction, empleo: str, sueldo: int):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message(
                embed=error_embed("Sin permisos", "Solo administracion puede cambiar sueldos."),
                ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        job = await B.find_public_job(guild_id, empleo, include_closed=True)
        if not job:
            await interaction.followup.send(
                embed=error_embed("No existe", f"No hay ningun empleo llamado **{empleo}**."),
                ephemeral=True)
            return
        try:
            job = await B.set_public_job_salary(guild_id, job["id"], sueldo)
        except B.BusinessError as error:
            await interaction.followup.send(
                embed=error_embed("Sueldo invalido", str(error)), ephemeral=True)
            return
        await interaction.followup.send(
            embed=success_embed("Sueldo actualizado",
                                f"**{job.get('name')}** pasa a {UI.money(job.get('salary'))} diarios."),
            ephemeral=True)

    @employment.command(name="empleados", description="Ver quien ocupa un empleo publico (administracion)")
    @app_commands.describe(empleo="Nombre exacto del empleo")
    async def empleados(self, interaction: discord.Interaction, empleo: str):
        if not await check_admin_permission(interaction):
            await interaction.response.send_message(
                embed=error_embed("Sin permisos", "Solo administracion puede ver la plantilla."),
                ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        job = await B.find_public_job(guild_id, empleo, include_closed=True)
        if not job:
            await interaction.followup.send(
                embed=error_embed("No existe", f"No hay ningun empleo llamado **{empleo}**."),
                ephemeral=True)
            return
        rows = await aexecute(
            "SELECT * FROM user_public_jobs WHERE job_id=$1 AND guild_id=$2 AND status='active'",
            (job["id"], guild_id), fetch="all",
        ) or []
        if not rows:
            await interaction.followup.send(
                embed=info_embed("Sin personal", f"**{job.get('name')}** no tiene empleados todavia."),
                ephemeral=True)
            return
        lines = [f"<@{r['discord_id']}> — {UI.money(r.get('salary'))} diarios"
                 f" · desde `{r.get('hired_at')}`" for r in rows]
        embed = info_embed(f"Plantilla · {job.get('name')}", "\n".join(lines)[:3900])
        embed.add_field(name="Total", value=f"{len(rows)} empleados", inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)


async def _remove_job_roles(guild, member, left_job):
    """Quita el rol de Discord del empleo al que se ha renunciado."""
    if not left_job or not left_job.get("role_id"):
        return
    try:
        role = guild.get_role(int(left_job["role_id"]))
    except (TypeError, ValueError):
        return
    if not role:
        return
    try:
        await member.remove_roles(role, reason="Renuncia al empleo publico")
    except discord.Forbidden:
        logger.debug("[Empleos] No se pudo quitar el rol %s a %s", role.id, member.id)


async def setup(bot):
    await bot.add_cog(Jobs(bot))
