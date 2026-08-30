import discord
from discord import app_commands
from discord.ext import commands
import datetime

from bot.db import aexecute
from bot.helpers import async_get_or_create_user, format_currency, generate_id
from bot.embeds import success_embed, error_embed, info_embed
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

class Companies(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    empresa = app_commands.Group(name="empresa", description="Gestión de empresas")

    @empresa.command(name="crear", description="Crear tu propia empresa")
    @app_commands.describe(nombre="Nombre de la empresa", descripcion="Descripción")
    async def crear(self, interaction: discord.Interaction, nombre: str, descripcion: str = ""):
        await interaction.response.defer()
        cd = check_cooldown(f"empresa:{interaction.user.id}:{interaction.guild_id}", 10)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        existing = await aexecute(
            "SELECT id FROM companies WHERE owner_id=$1 AND guild_id=$2",
            (str(interaction.user.id), str(interaction.guild_id)), fetch="one"
        )
        if existing:
            await interaction.followup.send(embed=error_embed("Ya tienes empresa", "Solo puedes ser dueño de una empresa"), ephemeral=True)
            return
        name_taken = await aexecute(
            "SELECT id FROM companies WHERE guild_id=$1 AND name ILIKE $2",
            (str(interaction.guild_id), nombre), fetch="one"
        )
        if name_taken:
            await interaction.followup.send(embed=error_embed("Nombre ocupado", f"Ya existe una empresa llamada **{nombre}**"), ephemeral=True)
            return
        cost = 5000
        ok = await async_remove_cash(str(interaction.user.id), str(interaction.guild_id), cost)
        if not ok:
            await interaction.followup.send(embed=error_embed("Sin fondos", f"Crear una empresa cuesta **{format_currency(cost)}**"), ephemeral=True)
            return
        company_id = generate_id()
        await aexecute(
            """INSERT INTO companies (id, guild_id, owner_id, name, description, funds, tax_rate, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,0,5,NOW(),NOW())""",
            (company_id, str(interaction.guild_id), str(interaction.user.id), nombre, descripcion)
        )
        await aexecute(
            """INSERT INTO company_members (id, company_id, discord_id, guild_id, role, salary, joined_at)
               VALUES ($1,$2,$3,$4,'Dueño',0,NOW())""",
            (generate_id(), company_id, str(interaction.user.id), str(interaction.guild_id))
        )
        await interaction.followup.send(embed=success_embed(f"🏢 Empresa creada — {nombre}", f"Invertiste **{format_currency(cost)}** para fundar tu empresa"))

    @empresa.command(name="info", description="Ver información de una empresa")
    @app_commands.describe(nombre="Nombre de la empresa")
    async def info(self, interaction: discord.Interaction, nombre: str):
        await interaction.response.defer()
        company = await aexecute(
            "SELECT * FROM companies WHERE guild_id=$1 AND name ILIKE $2 LIMIT 1",
            (str(interaction.guild_id), f"%{nombre}%"), fetch="one"
        )
        if not company:
            await interaction.followup.send(embed=error_embed("No encontrada", f"Empresa **{nombre}** no existe"), ephemeral=True)
            return
        count = await aexecute("SELECT COUNT(*) as c FROM company_members WHERE company_id=$1", (company["id"],), fetch="one")
        members = count["c"] if count else 0
        e = info_embed(f"🏢 {company['name']}", company.get("description",""))
        e.add_field(name="💰 Fondos", value=format_currency(company.get("funds",0)), inline=True)
        e.add_field(name="👥 Empleados", value=str(members), inline=True)
        e.add_field(name="📊 Tasa fiscal", value=f"{company.get('tax_rate',5)}%", inline=True)
        e.add_field(name="👔 Dueño", value=f"<@{company['owner_id']}>", inline=True)
        await interaction.followup.send(embed=e)

    @empresa.command(name="contratar", description="Contratar a un empleado")
    @app_commands.describe(usuario="Empleado", salario="Salario diario")
    async def contratar(self, interaction: discord.Interaction, usuario: discord.Member, salario: int = 0):
        await interaction.response.defer()
        company = await aexecute(
            "SELECT * FROM companies WHERE guild_id=$1 AND owner_id=$2",
            (str(interaction.guild_id), str(interaction.user.id)), fetch="one"
        )
        if not company:
            await interaction.followup.send(embed=error_embed("Sin empresa", "No eres dueño de ninguna empresa"), ephemeral=True)
            return
        existing = await aexecute(
            "SELECT id FROM company_members WHERE company_id=$1 AND discord_id=$2",
            (company["id"], str(usuario.id)), fetch="one"
        )
        if existing:
            await aexecute("UPDATE company_members SET salary=$1 WHERE id=$2", (salario, existing["id"]))
            await interaction.followup.send(embed=success_embed("Salario actualizado", f"{usuario.mention} — **{format_currency(salario)}/día**"))
            return
        await async_get_or_create_user(str(usuario.id), str(interaction.guild_id))
        await aexecute(
            """INSERT INTO company_members (id, company_id, discord_id, guild_id, role, salary, joined_at)
               VALUES ($1,$2,$3,$4,'Empleado',$5,NOW())""",
            (generate_id(), company["id"], str(usuario.id), str(interaction.guild_id), salario)
        )
        await interaction.followup.send(embed=success_embed(f"Contratado — {company['name']}", f"{usuario.mention} contratado. Salario: **{format_currency(salario)}/día**"))

    @empresa.command(name="despedir", description="Despedir a un empleado")
    @app_commands.describe(usuario="Empleado a despedir")
    async def despedir(self, interaction: discord.Interaction, usuario: discord.Member):
        await interaction.response.defer()
        company = await aexecute(
            "SELECT * FROM companies WHERE guild_id=$1 AND owner_id=$2",
            (str(interaction.guild_id), str(interaction.user.id)), fetch="one"
        )
        if not company:
            await interaction.followup.send(embed=error_embed("Sin empresa", "No eres dueño de ninguna empresa"), ephemeral=True)
            return
        member_row = await aexecute(
            "SELECT id FROM company_members WHERE company_id=$1 AND discord_id=$2",
            (company["id"], str(usuario.id)), fetch="one"
        )
        if not member_row:
            await interaction.followup.send(embed=error_embed("No es empleado", f"{usuario.mention} no trabaja en tu empresa"), ephemeral=True)
            return
        await aexecute("DELETE FROM company_members WHERE id=$1", (member_row["id"],))
        await interaction.followup.send(embed=success_embed("Despedido", f"{usuario.mention} fue despedido de **{company['name']}**"))

    @empresa.command(name="miembros", description="Ver empleados de tu empresa")
    async def miembros(self, interaction: discord.Interaction):
        await interaction.response.defer()
        company = await aexecute(
            "SELECT * FROM companies WHERE guild_id=$1 AND owner_id=$2",
            (str(interaction.guild_id), str(interaction.user.id)), fetch="one"
        )
        if not company:
            company = await aexecute(
                """SELECT c.* FROM companies c JOIN company_members cm ON cm.company_id=c.id
                   WHERE c.guild_id=$1 AND cm.discord_id=$2 LIMIT 1""",
                (str(interaction.guild_id), str(interaction.user.id)), fetch="one"
            )
        if not company:
            await interaction.followup.send(embed=error_embed("Sin empresa", "No perteneces a ninguna empresa"), ephemeral=True)
            return
        members = await aexecute(
            "SELECT * FROM company_members WHERE company_id=$1 ORDER BY joined_at",
            (company["id"],), fetch="all"
        ) or []
        e = info_embed(f"🏢 Empleados — {company['name']}")
        if not members:
            e.description = "No hay empleados"
        else:
            lines = [f"<@{m['discord_id']}> — **{m.get('role','Empleado')}** | {format_currency(m.get('salary',0))}/día" for m in members]
            e.description = "\n".join(lines)
        await interaction.followup.send(embed=e)

    @empresa.command(name="depositar", description="Depositar dinero en los fondos de la empresa")
    @app_commands.describe(cantidad="Cantidad a depositar")
    async def depositar(self, interaction: discord.Interaction, cantidad: int):
        await interaction.response.defer()
        if cantidad <= 0:
            await interaction.followup.send(embed=error_embed("Error", "Cantidad inválida"), ephemeral=True)
            return
        company = await aexecute(
            "SELECT * FROM companies WHERE guild_id=$1 AND owner_id=$2",
            (str(interaction.guild_id), str(interaction.user.id)), fetch="one"
        )
        if not company:
            await interaction.followup.send(embed=error_embed("Sin empresa", "Solo el dueño puede depositar fondos"), ephemeral=True)
            return
        ok = await async_remove_cash(str(interaction.user.id), str(interaction.guild_id), cantidad)
        if not ok:
            await interaction.followup.send(embed=error_embed("Sin fondos", "No tienes suficiente efectivo"), ephemeral=True)
            return
        await aexecute("UPDATE companies SET funds=funds+$1, updated_at=NOW() WHERE id=$2", (cantidad, company["id"]))
        await interaction.followup.send(embed=success_embed("Fondos depositados", f"Depositaste **{format_currency(cantidad)}** en **{company['name']}**"))


async def setup(bot):
    await bot.add_cog(Companies(bot))
