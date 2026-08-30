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

    @policia.command(name="arrestar", description="Arrestar y procesar judicialmente a un sospechoso (Solo Policía)")
    @app_commands.describe(
        ciudadano="Sospechoso o ciudadano a arrestar",
        motivo="Cargos penales o motivo del arresto",
        tiempo_minutos="Tiempo de condena o detención en minutos",
        fianza="Monto de fianza en $ (0 si no aplica fianza)"
    )
    async def arrestar(
        self,
        interaction: discord.Interaction,
        ciudadano: discord.Member,
        motivo: str,
        tiempo_minutos: int = 15,
        fianza: int = 0
    ):
        await interaction.response.defer()
        if not await is_police_authorized(interaction):
            await interaction.followup.send(
                embed=error_embed("Acceso Denegado 👮", "No tienes autorización ni los roles requeridos para ejecutar arrestos policiales."),
                ephemeral=True
            )
            return

        gid = str(interaction.guild_id)
        c_uid = str(ciudadano.id)
        o_uid = str(interaction.user.id)

        tiempo_minutos = max(1, min(1440, tiempo_minutos))
        fianza = max(0, fianza)

        # Crear o buscar al usuario
        c_user = await async_get_or_create_user(c_uid, gid, username=ciudadano.name, display_name=ciudadano.display_name)
        
        # Obtener DNI activo del detenido
        dni_rec = await aexecute(
            "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2 ORDER BY created_at DESC LIMIT 1",
            (gid, c_uid), fetch="one"
        )
        dni_num = dni_rec.get("dni_number", "S/D") if dni_rec else "Sin DNI"
        nombre_ic = dni_rec.get("full_name", ciudadano.display_name) if dni_rec else ciudadano.display_name

        # Registrar arresto en criminal_records
        record_id = generate_id()
        await aexecute(
            """INSERT INTO criminal_records (id, guild_id, discord_id, crime_type, description, fine_amount, jail_time_minutes, officer_id, officer_name, status, created_at)
               VALUES ($1, $2, $3, 'Arresto Policial', $4, $5, $6, $7, $8, 'arrested', NOW())""",
            (record_id, gid, c_uid, motivo, fianza, tiempo_minutos, o_uid, interaction.user.name)
        )

        e = discord.Embed(
            title="🚨 INFORME OFICIAL DE ARRESTO & DETENCIÓN",
            description=f"El oficial {interaction.user.mention} ha procesado formalmente la detención del siguiente individuo:",
            color=discord.Color.red(),
            timestamp=datetime.datetime.utcnow()
        )
        if dni_rec and dni_rec.get("avatar_url"):
            e.set_thumbnail(url=dni_rec["avatar_url"])
        else:
            e.set_thumbnail(url=ciudadano.display_avatar.url)

        e.add_field(name="👤 Sospechoso / Detenido", value=f"{ciudadano.mention} (`{ciudadano.name}`)", inline=True)
        e.add_field(name="🪪 Nombre IC / DNI", value=f"**{nombre_ic}**\n`{dni_num}`", inline=True)
        e.add_field(name="👮 Oficial a Cargo", value=f"{interaction.user.mention}", inline=True)
        e.add_field(name="⚖️ Cargos & Motivo", value=f"```\n{motivo}\n```", inline=False)
        e.add_field(name="⏳ Condena / Tiempo", value=f"**{tiempo_minutos} minutos**", inline=True)
        e.add_field(name="💵 Fianza Fijada", value=f"**{format_currency(fianza)}**" if fianza > 0 else "❌ *Sin derecho a fianza*", inline=True)
        e.set_footer(text=f"Expediente #{record_id[:8].upper()} • Departamento de Policía de Miami")

        await interaction.followup.send(content=f"{ciudadano.mention}", embed=e)

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


async def setup(bot):
    await bot.add_cog(Police(bot))
