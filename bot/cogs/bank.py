import discord
from discord import app_commands
from discord.ext import commands
import datetime

from bot.db import aexecute
from bot.helpers import async_get_or_create_user, format_currency, generate_id
from bot.embeds import success_embed, error_embed, info_embed
from bot.services.economy import async_add_cash, async_remove_cash, async_add_bank, async_remove_bank, async_log_transaction

COOLDOWNS = {}

def check_cooldown(key, seconds):
    now = datetime.datetime.utcnow().timestamp()
    last = COOLDOWNS.get(key, 0)
    remaining = (last + seconds) - now
    if remaining > 0:
        return remaining
    COOLDOWNS[key] = now
    return 0

INVESTMENT_TYPES = {
    "conservative": {"label": "Conservador", "rate": 5, "days": 3, "emoji": "🟢"},
    "moderate":     {"label": "Moderado",    "rate": 12, "days": 5, "emoji": "🟡"},
    "aggressive":   {"label": "Agresivo",    "rate": 25, "days": 7, "emoji": "🔴"},
}

class Bank(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    banco = app_commands.Group(name="banco", description="Gestión bancaria")

    @banco.command(name="depositar", description="Depositar efectivo en el banco")
    @app_commands.describe(cantidad="Cantidad a depositar")
    async def depositar(self, interaction: discord.Interaction, cantidad: int):
        await interaction.response.defer()
        cd = check_cooldown(f"banco:{interaction.user.id}:{interaction.guild_id}", 3)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        if cantidad <= 0:
            await interaction.followup.send(embed=error_embed("Error", "Cantidad inválida"), ephemeral=True)
            return
        await async_get_or_create_user(str(interaction.user.id), str(interaction.guild_id))
        ok = await async_remove_cash(str(interaction.user.id), str(interaction.guild_id), cantidad)
        if not ok:
            await interaction.followup.send(embed=error_embed("Sin fondos", "No tienes suficiente efectivo"), ephemeral=True)
            return
        await async_add_bank(str(interaction.user.id), str(interaction.guild_id), cantidad)
        await async_log_transaction(str(interaction.user.id), str(interaction.guild_id), "deposit", cantidad, "Depósito bancario")
        await interaction.followup.send(embed=success_embed("Depósito exitoso", f"Depositaste **{format_currency(cantidad)}** en el banco"))

    @banco.command(name="retirar", description="Retirar dinero del banco")
    @app_commands.describe(cantidad="Cantidad a retirar")
    async def retirar(self, interaction: discord.Interaction, cantidad: int):
        await interaction.response.defer()
        cd = check_cooldown(f"banco:{interaction.user.id}:{interaction.guild_id}", 3)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        if cantidad <= 0:
            await interaction.followup.send(embed=error_embed("Error", "Cantidad inválida"), ephemeral=True)
            return
        await async_get_or_create_user(str(interaction.user.id), str(interaction.guild_id))
        ok = await async_remove_bank(str(interaction.user.id), str(interaction.guild_id), cantidad)
        if not ok:
            await interaction.followup.send(embed=error_embed("Sin fondos", "No tienes suficiente dinero en el banco"), ephemeral=True)
            return
        await async_add_cash(str(interaction.user.id), str(interaction.guild_id), cantidad)
        await async_log_transaction(str(interaction.user.id), str(interaction.guild_id), "withdraw", cantidad, "Retiro bancario")
        await interaction.followup.send(embed=success_embed("Retiro exitoso", f"Retiraste **{format_currency(cantidad)}** del banco"))

    @banco.command(name="info", description="Ver información de tu cuenta bancaria")
    async def info(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cd = check_cooldown(f"banco:{interaction.user.id}:{interaction.guild_id}", 3)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        user = await async_get_or_create_user(str(interaction.user.id), str(interaction.guild_id))
        loans = await aexecute(
            "SELECT * FROM loans WHERE discord_id=$1 AND guild_id=$2 AND status='active'",
            (str(interaction.user.id), str(interaction.guild_id)), fetch="all"
        ) or []
        savings = await aexecute(
            "SELECT * FROM savings_accounts WHERE discord_id=$1 AND guild_id=$2",
            (str(interaction.user.id), str(interaction.guild_id)), fetch="one"
        )
        e = info_embed(f"🏦 Cuenta Bancaria de {interaction.user.display_name}")
        e.add_field(name="💵 Efectivo", value=format_currency(user.get("cash",0)), inline=True)
        e.add_field(name="🏦 Banco", value=format_currency(user.get("bank",0)), inline=True)
        if savings:
            e.add_field(name="💰 Ahorros", value=f"{format_currency(savings['balance'])} ({savings['interest_rate']}% diario)", inline=True)
        total_debt = sum(float(l["amount"]) for l in loans) if loans else 0
        if total_debt > 0:
            e.add_field(name="💳 Deuda total", value=format_currency(total_debt), inline=True)
            e.add_field(name="📋 Préstamos activos", value=str(len(loans)), inline=True)
        await interaction.followup.send(embed=e)

    @banco.command(name="ahorros", description="Abrir una cuenta de ahorros (2% interés diario)")
    async def ahorros(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cd = check_cooldown(f"banco:{interaction.user.id}:{interaction.guild_id}", 3)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        await async_get_or_create_user(str(interaction.user.id), str(interaction.guild_id))
        existing = await aexecute(
            "SELECT id FROM savings_accounts WHERE discord_id=$1 AND guild_id=$2",
            (str(interaction.user.id), str(interaction.guild_id)), fetch="one"
        )
        if existing:
            await interaction.followup.send(embed=error_embed("Ya tienes cuenta de ahorros", "Solo puedes tener una cuenta de ahorros"), ephemeral=True)
            return
        await aexecute(
            """INSERT INTO savings_accounts (id, discord_id, guild_id, balance, interest_rate, created_at, updated_at)
               VALUES ($1,$2,$3,0,2,NOW(),NOW())""",
            (generate_id(), str(interaction.user.id), str(interaction.guild_id))
        )
        await interaction.followup.send(embed=success_embed("Cuenta de ahorros abierta", "Se aplicará **2% de interés diario** a tu saldo de ahorros"))

    @banco.command(name="prestamo", description="Solicitar un préstamo bancario")
    @app_commands.describe(cantidad="Cantidad a solicitar (max $100,000)")
    async def prestamo(self, interaction: discord.Interaction, cantidad: int):
        await interaction.response.defer()
        cd = check_cooldown(f"banco:{interaction.user.id}:{interaction.guild_id}", 3)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        if cantidad <= 0 or cantidad > 100000:
            await interaction.followup.send(embed=error_embed("Error", "El préstamo debe ser entre $1 y $100,000"), ephemeral=True)
            return
        loans = await aexecute(
            "SELECT id, amount FROM loans WHERE discord_id=$1 AND guild_id=$2 AND status='active'",
            (str(interaction.user.id), str(interaction.guild_id)), fetch="all"
        ) or []
        if len(loans) >= 3:
            await interaction.followup.send(embed=error_embed("Límite alcanzado", "Tienes 3 préstamos activos. Paga alguno primero."), ephemeral=True)
            return
        total_debt = sum(float(l["amount"]) for l in loans)
        if total_debt + cantidad > 100000:
            await interaction.followup.send(embed=error_embed("Límite de deuda", f"No puedes tener más de **{format_currency(100000)}** en préstamos"), ephemeral=True)
            return
        due = datetime.datetime.utcnow() + datetime.timedelta(days=7)
        interest_amount = int(cantidad * 0.10)
        total = cantidad + interest_amount
        await aexecute(
            """INSERT INTO loans (id, discord_id, guild_id, amount, interest_rate, total_due, due_date, status, created_at, updated_at)
               VALUES ($1,$2,$3,$4,10,$5,$6,'active',NOW(),NOW())""",
            (generate_id(), str(interaction.user.id), str(interaction.guild_id), cantidad, total, due)
        )
        await async_add_cash(str(interaction.user.id), str(interaction.guild_id), cantidad)
        await async_log_transaction(str(interaction.user.id), str(interaction.guild_id), "loan_taken", cantidad, "Préstamo bancario")
        e = success_embed("Préstamo aprobado", f"Recibiste **{format_currency(cantidad)}**")
        e.add_field(name="💳 Total a pagar", value=format_currency(total), inline=True)
        e.add_field(name="📅 Vence", value=f"<t:{int(due.timestamp())}:R>", inline=True)
        await interaction.followup.send(embed=e)

    @banco.command(name="pagar", description="Pagar un préstamo activo")
    async def pagar_prestamo(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cd = check_cooldown(f"banco:{interaction.user.id}:{interaction.guild_id}", 3)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        loans = await aexecute(
            "SELECT * FROM loans WHERE discord_id=$1 AND guild_id=$2 AND status='active' ORDER BY created_at ASC LIMIT 1",
            (str(interaction.user.id), str(interaction.guild_id)), fetch="one"
        )
        if not loans:
            await interaction.followup.send(embed=error_embed("Sin préstamos", "No tienes préstamos activos"), ephemeral=True)
            return
        total = float(loans["total_due"])
        ok = await async_remove_cash(str(interaction.user.id), str(interaction.guild_id), total)
        if not ok:
            await interaction.followup.send(embed=error_embed("Sin fondos", f"Necesitas **{format_currency(total)}** en efectivo"), ephemeral=True)
            return
        await aexecute("UPDATE loans SET status='paid', updated_at=NOW() WHERE id=$1", (loans["id"],))
        await async_log_transaction(str(interaction.user.id), str(interaction.guild_id), "loan_repaid", -total, "Pago de préstamo")
        await interaction.followup.send(embed=success_embed("Préstamo pagado", f"Pagaste **{format_currency(total)}** ✅"))

    invertir = app_commands.Group(name="invertir", description="Gestión de inversiones")

    @invertir.command(name="crear", description="Crear una nueva inversión")
    @app_commands.describe(tipo="Tipo de inversión", cantidad="Cantidad a invertir")
    @app_commands.choices(tipo=[
        app_commands.Choice(name="🟢 Conservador (5% / 3 días)", value="conservative"),
        app_commands.Choice(name="🟡 Moderado (12% / 5 días)", value="moderate"),
        app_commands.Choice(name="🔴 Agresivo (25% / 7 días)", value="aggressive"),
    ])
    async def invertir_crear(self, interaction: discord.Interaction, tipo: str, cantidad: int):
        await interaction.response.defer()
        cd = check_cooldown(f"invertir:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        if cantidad < 100:
            await interaction.followup.send(embed=error_embed("Error", "Inversión mínima: **$100**"), ephemeral=True)
            return
        inv_data = INVESTMENT_TYPES.get(tipo)
        if not inv_data:
            await interaction.followup.send(embed=error_embed("Error", "Tipo inválido"), ephemeral=True)
            return
        await async_get_or_create_user(str(interaction.user.id), str(interaction.guild_id))
        ok = await async_remove_bank(str(interaction.user.id), str(interaction.guild_id), cantidad)
        if not ok:
            ok = await async_remove_cash(str(interaction.user.id), str(interaction.guild_id), cantidad)
        if not ok:
            await interaction.followup.send(embed=error_embed("Sin fondos", "No tienes suficiente dinero"), ephemeral=True)
            return
        matures_at = datetime.datetime.utcnow() + datetime.timedelta(days=inv_data["days"])
        await aexecute(
            """INSERT INTO investments (id, discord_id, guild_id, type, amount, return_rate, matures_at, status, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,'active',NOW(),NOW())""",
            (generate_id(), str(interaction.user.id), str(interaction.guild_id), tipo, cantidad, inv_data["rate"], matures_at)
        )
        await async_log_transaction(str(interaction.user.id), str(interaction.guild_id), "investment", -cantidad, f"Inversión {inv_data['label']}")
        returns = int(cantidad * (1 + inv_data["rate"] / 100))
        e = success_embed(f"{inv_data['emoji']} Inversión creada — {inv_data['label']}")
        e.add_field(name="💰 Invertido", value=format_currency(cantidad), inline=True)
        e.add_field(name="📈 Retorno", value=format_currency(returns), inline=True)
        e.add_field(name="⏰ Madura", value=f"<t:{int(matures_at.timestamp())}:R>", inline=True)
        await interaction.followup.send(embed=e)

    @invertir.command(name="portafolio", description="Ver tus inversiones activas")
    async def portafolio(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cd = check_cooldown(f"invertir:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        investments = await aexecute(
            "SELECT * FROM investments WHERE discord_id=$1 AND guild_id=$2 AND status='active' ORDER BY created_at DESC",
            (str(interaction.user.id), str(interaction.guild_id)), fetch="all"
        ) or []
        if not investments:
            await interaction.followup.send(embed=info_embed("📊 Portafolio", "No tienes inversiones activas"), ephemeral=True)
            return
        e = info_embed(f"📊 Portafolio de {interaction.user.display_name}")
        total_invested = 0
        total_returns = 0
        for inv in investments:
            inv_data = INVESTMENT_TYPES.get(inv["type"], {"label":"?","emoji":"📊","rate":0})
            amt = float(inv["amount"])
            ret = int(amt * (1 + float(inv["return_rate"]) / 100))
            total_invested += amt
            total_returns += ret
            matures_at = inv["matures_at"]
            ts = int(matures_at.timestamp()) if hasattr(matures_at, "timestamp") else 0
            e.add_field(
                name=f"{inv_data['emoji']} {inv_data['label']}",
                value=f"Invertido: **{format_currency(amt)}**\nRetorno: **{format_currency(ret)}**\nMadura: <t:{ts}:R>",
                inline=True
            )
        e.add_field(name="Total invertido", value=format_currency(total_invested), inline=False)
        e.add_field(name="Total retorno esperado", value=format_currency(total_returns), inline=True)
        await interaction.followup.send(embed=e)


async def setup(bot):
    await bot.add_cog(Bank(bot))
