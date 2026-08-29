import discord
from discord import app_commands
from discord.ext import commands
import datetime
import random
import string

from bot.db import aexecute
from bot.helpers import async_get_or_create_user, format_currency, generate_id
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

DEPT_EMOJI = {"CPD":"👮","CFD":"🚒","Sheriff":"⭐","ISP":"🚔","DOT":"🚧","DOJ":"⚖️","EMA":"🏥"}

class Departments(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    departamento = app_commands.Group(name="departamento", description="Gestión de departamentos")

    @departamento.command(name="lista", description="Ver todos los departamentos")
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
        e = department_embed("🏛️ Departamentos")
        if not depts:
            e.description = "No hay departamentos creados"
        else:
            for d in depts:
                emoji = DEPT_EMOJI.get(d.get("acronym",""),"🏢")
                count = await aexecute("SELECT COUNT(*) as c FROM department_members WHERE department_id=$1", (d["id"],), fetch="one")
                members = count["c"] if count else 0
                e.add_field(
                    name=f"{emoji} {d['name']} [{d.get('acronym','')}]",
                    value=f"👥 {members} miembros | 💰 {format_currency(d.get('budget',0))}",
                    inline=True
                )
        await interaction.followup.send(embed=e)

    @departamento.command(name="info", description="Ver información de un departamento")
    @app_commands.describe(acronimo="Acrónimo del departamento (CPD, CFD, etc.)")
    async def info(self, interaction: discord.Interaction, acronimo: str):
        await interaction.response.defer()
        dept = await aexecute(
            "SELECT * FROM departments WHERE guild_id=$1 AND acronym ILIKE $2",
            (str(interaction.guild_id), acronimo), fetch="one"
        )
        if not dept:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Departamento **{acronimo}** no existe"), ephemeral=True)
            return
        emoji = DEPT_EMOJI.get(dept.get("acronym",""),"🏢")
        count = await aexecute("SELECT COUNT(*) as c FROM department_members WHERE department_id=$1", (dept["id"],), fetch="one")
        members = count["c"] if count else 0
        e = department_embed(f"{emoji} {dept['name']}", dept.get("description",""))
        e.add_field(name="💰 Presupuesto", value=format_currency(dept.get("budget",0)), inline=True)
        e.add_field(name="👥 Miembros", value=str(members), inline=True)
        e.add_field(name="🏷️ Acrónimo", value=dept.get("acronym",""), inline=True)
        await interaction.followup.send(embed=e)

    @departamento.command(name="unirse", description="Solicitar unirse a un departamento")
    @app_commands.describe(acronimo="Acrónimo del departamento")
    async def unirse(self, interaction: discord.Interaction, acronimo: str):
        await interaction.response.defer()
        cd = check_cooldown(f"dept:{interaction.user.id}:{interaction.guild_id}", 10)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        dept = await aexecute(
            "SELECT * FROM departments WHERE guild_id=$1 AND acronym ILIKE $2",
            (str(interaction.guild_id), acronimo), fetch="one"
        )
        if not dept:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Departamento **{acronimo}** no existe"), ephemeral=True)
            return
        existing = await aexecute(
            "SELECT id FROM department_members WHERE department_id=$1 AND discord_id=$2",
            (dept["id"], str(interaction.user.id)), fetch="one"
        )
        if existing:
            await interaction.followup.send(embed=error_embed("Ya eres miembro", f"Ya perteneces a **{dept['name']}**"), ephemeral=True)
            return
        await async_get_or_create_user(str(interaction.user.id), str(interaction.guild_id), username=interaction.user.name, display_name=interaction.user.display_name)
        await aexecute(
            """INSERT INTO department_members (id, department_id, discord_id, guild_id, rank, salary, joined_at, username)
               VALUES ($1,$2,$3,$4,'Cadete',0,NOW(),$5)""",
            (generate_id(), dept["id"], str(interaction.user.id), str(interaction.guild_id), interaction.user.name)
        )
        emoji = DEPT_EMOJI.get(dept.get("acronym",""),"🏢")
        await interaction.followup.send(embed=success_embed(f"Bienvenido al {emoji} {dept['name']}", f"Te uniste como **Cadete**"))

    @departamento.command(name="contratar", description="Contratar a un miembro (requiere permisos)")
    @app_commands.describe(usuario="Usuario a contratar", acronimo="Acrónimo del departamento", rango="Rango asignado", salario="Salario diario")
    async def contratar(self, interaction: discord.Interaction, usuario: discord.Member, acronimo: str, rango: str = "Oficial", salario: int = 0):
        await interaction.response.defer()
        if not interaction.user.guild_permissions.manage_roles and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(embed=error_embed("Sin permisos", "Necesitas permisos de administración"), ephemeral=True)
            return
        dept = await aexecute("SELECT * FROM departments WHERE guild_id=$1 AND acronym ILIKE $2", (str(interaction.guild_id), acronimo), fetch="one")
        if not dept:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Departamento **{acronimo}** no existe"), ephemeral=True)
            return
        existing = await aexecute("SELECT id FROM department_members WHERE department_id=$1 AND discord_id=$2", (dept["id"], str(usuario.id)), fetch="one")
        if existing:
            await aexecute("UPDATE department_members SET rank=$1, salary=$2, username=$3 WHERE id=$4", (rango, salario, usuario.name, existing["id"]))
        else:
            await aexecute(
                """INSERT INTO department_members (id, department_id, discord_id, guild_id, rank, salary, joined_at, username)
                   VALUES ($1,$2,$3,$4,$5,$6,NOW(),$7)""",
                (generate_id(), dept["id"], str(usuario.id), str(interaction.guild_id), rango, salario, usuario.name)
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
            (generate_id(), dept["id"], str(interaction.guild_id), str(interaction.user.id), str(usuario.id), f"Rango: {rango}, Salario: {salario}")
        )
        emoji = DEPT_EMOJI.get(dept.get("acronym",""),"🏢")
        await interaction.followup.send(embed=success_embed(f"Contratado — {emoji} {dept['name']}", f"{usuario.mention} contratado como **{rango}**"))

    @departamento.command(name="despedir", description="Despedir a un miembro")
    @app_commands.describe(usuario="Usuario a despedir", acronimo="Acrónimo del departamento")
    async def despedir(self, interaction: discord.Interaction, usuario: discord.Member, acronimo: str):
        await interaction.response.defer()
        if not interaction.user.guild_permissions.manage_roles and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(embed=error_embed("Sin permisos", "Necesitas permisos de administración"), ephemeral=True)
            return
        dept = await aexecute("SELECT * FROM departments WHERE guild_id=$1 AND acronym ILIKE $2", (str(interaction.guild_id), acronimo), fetch="one")
        if not dept:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Departamento **{acronimo}** no existe"), ephemeral=True)
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
               VALUES ($1,$2,$3,'fire',$4,$5,'Despedido',NOW())""",
            (generate_id(), dept["id"], str(interaction.guild_id), str(interaction.user.id), str(usuario.id))
        )
        await interaction.followup.send(embed=success_embed("Despedido", f"{usuario.mention} fue despedido de **{dept['name']}**"))

    @departamento.command(name="presupuesto", description="Ver el presupuesto del departamento")
    @app_commands.describe(acronimo="Acrónimo del departamento")
    async def presupuesto(self, interaction: discord.Interaction, acronimo: str):
        await interaction.response.defer()
        dept = await aexecute("SELECT * FROM departments WHERE guild_id=$1 AND acronym ILIKE $2", (str(interaction.guild_id), acronimo), fetch="one")
        if not dept:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Departamento **{acronimo}** no existe"), ephemeral=True)
            return
        emoji = DEPT_EMOJI.get(dept.get("acronym",""),"🏢")
        e = department_embed(f"{emoji} Presupuesto — {dept['name']}")
        e.add_field(name="💰 Presupuesto actual", value=format_currency(dept.get("budget",0)), inline=True)
        await interaction.followup.send(embed=e)

    @departamento.command(name="miembros", description="Ver los miembros del departamento")
    @app_commands.describe(acronimo="Acrónimo del departamento")
    async def miembros(self, interaction: discord.Interaction, acronimo: str):
        await interaction.response.defer()
        dept = await aexecute("SELECT * FROM departments WHERE guild_id=$1 AND acronym ILIKE $2", (str(interaction.guild_id), acronimo), fetch="one")
        if not dept:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Departamento **{acronimo}** no existe"), ephemeral=True)
            return
        members = await aexecute(
            """SELECT dm.*, u.username as user_name, u.display_name as user_display_name
               FROM department_members dm
               LEFT JOIN users u ON u.discord_id = dm.discord_id AND u.guild_id = dm.guild_id
               WHERE dm.department_id=$1 
               ORDER BY dm.joined_at""",
            (dept["id"],), fetch="all"
        ) or []
        emoji = DEPT_EMOJI.get(dept.get("acronym",""),"🏢")
        e = department_embed(f"{emoji} Miembros — {dept['name']}")
        if not members:
            e.description = "No hay miembros en este departamento"
        else:
            lines = []
            for m in members:
                uname = m.get("username") or m.get("user_name")
                dname = m.get("user_display_name")
                tag = f"**{uname}** (@{dname})" if uname and dname and uname != dname else f"**{uname or 'Usuario'}**"
                lines.append(f"{tag} — `<@{m['discord_id']}>` | **{m.get('rank','Oficial')}** | {format_currency(m.get('salary',0))}/día")
            e.description = "\n".join(lines)
        await interaction.followup.send(embed=e)

    flota = app_commands.Group(name="flota", description="Gestión de flota vehicular")

    @flota.command(name="ver", description="Ver la flota del departamento")
    @app_commands.describe(acronimo="Acrónimo del departamento")
    async def flota_ver(self, interaction: discord.Interaction, acronimo: str):
        await interaction.response.defer()
        dept = await aexecute("SELECT * FROM departments WHERE guild_id=$1 AND acronym ILIKE $2", (str(interaction.guild_id), acronimo), fetch="one")
        if not dept:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Departamento **{acronimo}** no existe"), ephemeral=True)
            return
        vehicles = await aexecute(
            """SELECT fv.*, fvt.name as type_name, fvt.price FROM fleet_vehicles fv
               JOIN fleet_vehicle_types fvt ON fvt.id=fv.vehicle_type_id
               WHERE fv.department_id=$1 ORDER BY fv.status, fvt.name""",
            (dept["id"],), fetch="all"
        ) or []
        emoji = DEPT_EMOJI.get(dept.get("acronym",""),"🏢")
        e = department_embed(f"{emoji} Flota — {dept['name']}")
        if not vehicles:
            e.description = "No hay vehículos en esta flota"
        else:
            status_emoji = {"active":"✅","repairing":"🔧","returned":"📦","damaged":"❌","in_use":"🚗"}
            lines = [f"🚗 **{v['type_name']}** `{v.get('plate','N/A')}` — {status_emoji.get(v.get('status','active'),'❓')} {v.get('status','active').title()}" for v in vehicles]
            e.description = "\n".join(lines)
        await interaction.followup.send(embed=e)

    @flota.command(name="comprar", description="Comprar vehículos para el departamento")
    @app_commands.describe(
        acronimo="Acrónimo del departamento",
        tipo="Tipo o nombre del vehículo (se crea si no existe)",
        cantidad="Cantidad de vehículos",
        valor_unitario="Valor por unidad (obligatorio para tipos nuevos)"
    )
    async def flota_comprar(self, interaction: discord.Interaction, acronimo: str, tipo: str, cantidad: int = 1, valor_unitario: float = None):
        await interaction.response.defer()
        if not interaction.user.guild_permissions.manage_roles and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(embed=error_embed("Sin permisos", "Necesitas permisos de administración"), ephemeral=True)
            return
        if cantidad < 1:
            await interaction.followup.send(embed=error_embed("Error", "La cantidad mínima es 1 vehículo"), ephemeral=True)
            return
        if valor_unitario is not None and valor_unitario <= 0:
            await interaction.followup.send(embed=error_embed("Error", "El valor por unidad debe ser mayor que 0"), ephemeral=True)
            return
        dept = await aexecute("SELECT * FROM departments WHERE guild_id=$1 AND acronym ILIKE $2", (str(interaction.guild_id), acronimo), fetch="one")
        if not dept:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Departamento **{acronimo}** no existe"), ephemeral=True)
            return
        vtype = await aexecute("SELECT * FROM fleet_vehicle_types WHERE guild_id=$1 AND name ILIKE $2 LIMIT 1", (str(interaction.guild_id), f"%{tipo}%"), fetch="one")
        if vtype:
            unit_price = float(valor_unitario if valor_unitario is not None else vtype.get("price", 0))
            vehicle_type_id = vtype["id"]
            vehicle_type_name = vtype["name"]
        else:
            if valor_unitario is None:
                await interaction.followup.send(embed=error_embed("Falta el valor", "Indica el valor por unidad para registrar este tipo de vehículo"), ephemeral=True)
                return
            unit_price = float(valor_unitario)
            vehicle_type_id = generate_id()
            vehicle_type_name = tipo
        if unit_price <= 0:
            await interaction.followup.send(embed=error_embed("Error", "El tipo de vehículo no tiene un precio válido"), ephemeral=True)
            return
        if cantidad > 100:
            discount_percent = 20
        elif cantidad > 75:
            discount_percent = 15
        elif cantidad > 50:
            discount_percent = 10
        elif cantidad > 35:
            discount_percent = 5
        else:
            discount_percent = 0
        subtotal = unit_price * cantidad
        discount = subtotal * discount_percent / 100
        total = round(subtotal - discount, 2)
        if float(dept.get("budget", 0)) < total:
            await interaction.followup.send(embed=error_embed("Sin presupuesto", f"El departamento necesita **{format_currency(total)}**. Presupuesto actual: **{format_currency(dept.get('budget', 0))}**"), ephemeral=True)
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
        emoji = DEPT_EMOJI.get(dept.get("acronym", ""), "🏢")
        plate_info = f"Placa: `{plates[0]}`" if cantidad == 1 else f"Placas generadas: **{cantidad}**"
        discount_info = f"\nDescuento aplicado: **{discount_percent}%**" if discount_percent else ""
        await interaction.followup.send(embed=success_embed(
            f"{emoji} Vehículos adquiridos",
            f"**{vehicle_type_name}** x{cantidad} — {plate_info}\n"
            f"Valor por unidad: **{format_currency(unit_price)}**\n"
            f"Subtotal: **{format_currency(subtotal)}**{discount_info}\n"
            f"Total pagado: **{format_currency(total)}**"
        ))

    @flota.command(name="solicitar", description="Solicitar el uso de un vehículo de la flota")
    @app_commands.describe(acronimo="Acrónimo del departamento", placa="Placa del vehículo")
    async def flota_solicitar(self, interaction: discord.Interaction, acronimo: str, placa: str):
        await interaction.response.defer()
        dept = await aexecute("SELECT * FROM departments WHERE guild_id=$1 AND acronym ILIKE $2", (str(interaction.guild_id), acronimo), fetch="one")
        if not dept:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Departamento **{acronimo}** no existe"), ephemeral=True)
            return
        member_row = await aexecute(
            "SELECT id FROM department_members WHERE department_id=$1 AND discord_id=$2",
            (dept["id"], str(interaction.user.id)), fetch="one"
        )
        if not member_row:
            await interaction.followup.send(embed=error_embed("No eres miembro", f"Debes pertenecer al **{dept['name']}** para solicitar vehículos"), ephemeral=True)
            return
        vehicle = await aexecute(
            "SELECT fv.*, fvt.name as type_name FROM fleet_vehicles fv JOIN fleet_vehicle_types fvt ON fvt.id=fv.vehicle_type_id WHERE fv.department_id=$1 AND fv.plate ILIKE $2 AND fv.status='active'",
            (dept["id"], f"%{placa}%"), fetch="one"
        )
        if not vehicle:
            await interaction.followup.send(embed=error_embed("No disponible", f"Vehículo con placa `{placa}` no encontrado o no disponible"), ephemeral=True)
            return
        await aexecute("UPDATE fleet_vehicles SET status='in_use', assigned_to=$1, updated_at=NOW() WHERE id=$2", (str(interaction.user.id), vehicle["id"]))
        emoji = DEPT_EMOJI.get(dept.get("acronym",""),"🏢")
        await interaction.followup.send(embed=success_embed(f"{emoji} Vehículo asignado", f"**{vehicle['type_name']}** (Placa: `{vehicle['plate']}`) está bajo tu cargo"))

    @flota.command(name="devolver", description="Devolver un vehículo asignado")
    @app_commands.describe(placa="Placa del vehículo a devolver")
    async def flota_devolver(self, interaction: discord.Interaction, placa: str):
        await interaction.response.defer()
        vehicle = await aexecute(
            "SELECT fv.*, fvt.name as type_name, d.name as dept_name, d.acronym FROM fleet_vehicles fv JOIN fleet_vehicle_types fvt ON fvt.id=fv.vehicle_type_id JOIN departments d ON d.id=fv.department_id WHERE fv.guild_id=$1 AND fv.assigned_to=$2 AND fv.plate ILIKE $3",
            (str(interaction.guild_id), str(interaction.user.id), f"%{placa}%"), fetch="one"
        )
        if not vehicle:
            await interaction.followup.send(embed=error_embed("No encontrado", f"No tienes un vehículo con placa `{placa}` asignado"), ephemeral=True)
            return
        await aexecute("UPDATE fleet_vehicles SET status='active', assigned_to=NULL, updated_at=NOW() WHERE id=$1", (vehicle["id"],))
        emoji = DEPT_EMOJI.get(vehicle.get("acronym",""),"🏢")
        await interaction.followup.send(embed=success_embed(f"{emoji} Vehículo devuelto", f"**{vehicle['type_name']}** (Placa: `{vehicle['plate']}`) devuelto al {vehicle['dept_name']}"))

    @flota.command(name="reparar", description="Reportar un vehículo para reparación")
    @app_commands.describe(placa="Placa del vehículo", razon="Razón del reporte")
    async def flota_reparar(self, interaction: discord.Interaction, placa: str, razon: str = "Daños en servicio"):
        await interaction.response.defer()
        vehicle = await aexecute(
            "SELECT fv.*, fvt.name as type_name, d.name as dept_name, d.acronym FROM fleet_vehicles fv JOIN fleet_vehicle_types fvt ON fvt.id=fv.vehicle_type_id JOIN departments d ON d.id=fv.department_id WHERE fv.guild_id=$1 AND fv.plate ILIKE $2",
            (str(interaction.guild_id), f"%{placa}%"), fetch="one"
        )
        if not vehicle:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Vehículo con placa `{placa}` no encontrado"), ephemeral=True)
            return
        if vehicle.get("status") == "repairing":
            await interaction.followup.send(embed=error_embed("Ya en reparación", f"El vehículo `{placa}` ya está siendo reparado"), ephemeral=True)
            return
        await aexecute("UPDATE fleet_vehicles SET status='repairing', assigned_to=NULL, updated_at=NOW() WHERE id=$1", (vehicle["id"],))
        await interaction.followup.send(embed=success_embed("🔧 Vehículo enviado a reparación", f"**{vehicle['type_name']}** (Placa: `{vehicle['plate']}`) — Razón: {razon}"))

    @flota.command(name="gestionar", description="Gestionar estado de un vehículo (admin)")
    @app_commands.describe(placa="Placa del vehículo", estado="Nuevo estado")
    @app_commands.choices(estado=[
        app_commands.Choice(name="✅ Activo", value="active"),
        app_commands.Choice(name="🔧 En reparación", value="repairing"),
        app_commands.Choice(name="❌ Dañado", value="damaged"),
        app_commands.Choice(name="📦 Devuelto/Baja", value="returned"),
    ])
    async def flota_gestionar(self, interaction: discord.Interaction, placa: str, estado: str):
        await interaction.response.defer()
        if not interaction.user.guild_permissions.manage_roles and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(embed=error_embed("Sin permisos", "Necesitas permisos de administración"), ephemeral=True)
            return
        vehicle = await aexecute(
            "SELECT fv.*, fvt.name as type_name FROM fleet_vehicles fv JOIN fleet_vehicle_types fvt ON fvt.id=fv.vehicle_type_id WHERE fv.guild_id=$1 AND fv.plate ILIKE $2",
            (str(interaction.guild_id), f"%{placa}%"), fetch="one"
        )
        if not vehicle:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Vehículo con placa `{placa}` no encontrado"), ephemeral=True)
            return
        await aexecute("UPDATE fleet_vehicles SET status=$1, assigned_to=NULL, updated_at=NOW() WHERE id=$2", (estado, vehicle["id"]))
        status_emoji = {"active":"✅","repairing":"🔧","damaged":"❌","returned":"📦"}.get(estado,"❓")
        await interaction.followup.send(embed=success_embed(f"{status_emoji} Estado actualizado", f"**{vehicle['type_name']}** (Placa: `{vehicle['plate']}`) → **{estado}**"), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Departments(bot))
