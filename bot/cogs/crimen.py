import discord
from discord import app_commands
from discord.ext import commands
import datetime
import random

from bot.db import aexecute
from bot.helpers import async_get_or_create_user, format_currency, generate_id
from bot.embeds import criminal_embed, error_embed, success_embed, dirty_embed, info_embed
from bot.services.economy import async_remove_cash, async_add_cash, async_log_transaction

COOLDOWNS = {}

def check_cooldown(key, seconds):
    now = datetime.datetime.utcnow().timestamp()
    last = COOLDOWNS.get(key, 0)
    remaining = (last + seconds) - now
    if remaining > 0:
        return remaining
    COOLDOWNS[key] = now
    return 0

DRUG_TYPES = {
    "marihuana": {"cost": 500,  "time_hours": 2,  "yield_min": 800,  "yield_max": 1500,  "emoji": "🌿"},
    "cocaina":   {"cost": 2000, "time_hours": 6,  "yield_min": 3500, "yield_max": 6000,  "emoji": "🤍"},
    "heroina":   {"cost": 5000, "time_hours": 12, "yield_min": 9000, "yield_max": 15000, "emoji": "💉"},
    "meth":      {"cost": 3000, "time_hours": 8,  "yield_min": 5000, "yield_max": 9000,  "emoji": "🧪"},
}

LAUNDER_METHODS = {
    "lavanderia": {"label": "Lavandería",    "fee_pct": 12, "cooldown_hours": 4,  "emoji": "👕"},
    "fachada":    {"label": "Empresa Fachada","fee_pct": 20, "cooldown_hours": 8,  "emoji": "🏢"},
    "casino":     {"label": "Casino",         "fee_pct": 35, "cooldown_hours": 1,  "emoji": "🎰"},
}

MISSIONS = [
    {"name":"Robo Express",        "reward_min":800,  "reward_max":1500,  "duration_min":15,  "risk":"Bajo",   "emoji":"💼"},
    {"name":"Asalto al Banco",     "reward_min":5000, "reward_max":10000, "duration_min":60,  "risk":"Crítico","emoji":"🏦"},
    {"name":"Tráfico de Armas",    "reward_min":3000, "reward_max":6000,  "duration_min":45,  "risk":"Alto",   "emoji":"🔫"},
    {"name":"Hackeo Corporativo",  "reward_min":2000, "reward_max":4000,  "duration_min":30,  "risk":"Medio",  "emoji":"💻"},
    {"name":"Secuestro VIP",       "reward_min":4000, "reward_max":8000,  "duration_min":90,  "risk":"Alto",   "emoji":"🎯"},
]

class Crimen(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    drogas = app_commands.Group(name="drogas", description="Operaciones de narcotráfico")

    @drogas.command(name="sembrar", description="Iniciar un cultivo de droga")
    @app_commands.describe(tipo="Tipo de droga")
    @app_commands.choices(tipo=[
        app_commands.Choice(name="🌿 Marihuana ($500 / 2h)", value="marihuana"),
        app_commands.Choice(name="🤍 Cocaína ($2,000 / 6h)", value="cocaina"),
        app_commands.Choice(name="💉 Heroína ($5,000 / 12h)", value="heroina"),
        app_commands.Choice(name="🧪 Meth ($3,000 / 8h)", value="meth"),
    ])
    async def sembrar(self, interaction: discord.Interaction, tipo: str):
        await interaction.response.defer()
        cd = check_cooldown(f"drogas:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        await async_get_or_create_user(str(interaction.user.id), str(interaction.guild_id))
        active = await aexecute(
            "SELECT COUNT(*) as c FROM drug_operations WHERE discord_id=$1 AND guild_id=$2 AND status='growing'",
            (str(interaction.user.id), str(interaction.guild_id)), fetch="one"
        )
        if active and active["c"] >= 3:
            await interaction.followup.send(embed=error_embed("Límite alcanzado", "Tienes 3 cultivos activos. Cosecha primero."), ephemeral=True)
            return
        drug = DRUG_TYPES[tipo]
        ok = await async_remove_cash(str(interaction.user.id), str(interaction.guild_id), drug["cost"])
        if not ok:
            await interaction.followup.send(embed=error_embed("Sin fondos", f"Necesitas **{format_currency(drug['cost'])}**"), ephemeral=True)
            return
        harvest_at = datetime.datetime.utcnow() + datetime.timedelta(hours=drug["time_hours"])
        await aexecute(
            """INSERT INTO drug_operations (id, discord_id, guild_id, drug_type, cost, harvest_at, status, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,'growing',NOW(),NOW())""",
            (generate_id(), str(interaction.user.id), str(interaction.guild_id), tipo, drug["cost"], harvest_at)
        )
        e = criminal_embed(f"{drug['emoji']} Cultivo iniciado — {tipo.title()}")
        e.add_field(name="💰 Inversión", value=format_currency(drug["cost"]), inline=True)
        e.add_field(name="⏰ Lista", value=f"<t:{int(harvest_at.timestamp())}:R>", inline=True)
        e.add_field(name="📈 Ganancia estimada", value=f"{format_currency(drug['yield_min'])} — {format_currency(drug['yield_max'])}", inline=True)
        await interaction.followup.send(embed=e, ephemeral=True)

    @drogas.command(name="cosechar", description="Cosechar tu cultivo listo")
    async def cosechar(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cd = check_cooldown(f"drogas:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        now = datetime.datetime.utcnow()
        ready = await aexecute(
            "SELECT * FROM drug_operations WHERE discord_id=$1 AND guild_id=$2 AND status='growing' AND harvest_at <= $3 LIMIT 1",
            (str(interaction.user.id), str(interaction.guild_id), now), fetch="one"
        )
        if not ready:
            pending = await aexecute(
                "SELECT harvest_at FROM drug_operations WHERE discord_id=$1 AND guild_id=$2 AND status='growing' ORDER BY harvest_at LIMIT 1",
                (str(interaction.user.id), str(interaction.guild_id)), fetch="one"
            )
            if pending:
                ts = int(pending["harvest_at"].timestamp()) if hasattr(pending["harvest_at"],"timestamp") else 0
                await interaction.followup.send(embed=error_embed("Aún no está lista", f"Tu cultivo estará listo <t:{ts}:R>"), ephemeral=True)
            else:
                await interaction.followup.send(embed=error_embed("Sin cultivos", "No tienes cultivos activos"), ephemeral=True)
            return
        drug = DRUG_TYPES.get(ready["drug_type"], DRUG_TYPES["marihuana"])
        earned = random.randint(drug["yield_min"], drug["yield_max"])
        await aexecute("UPDATE drug_operations SET status='harvested', updated_at=NOW() WHERE id=$1", (ready["id"],))
        await aexecute(
            "UPDATE users SET dirty_money=COALESCE(dirty_money,0)+$1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
            (earned, str(interaction.user.id), str(interaction.guild_id))
        )
        e = dirty_embed(f"{drug['emoji']} Cosecha exitosa — {ready['drug_type'].title()}")
        e.add_field(name="💵 Dinero sucio obtenido", value=format_currency(earned), inline=True)
        await interaction.followup.send(embed=e, ephemeral=True)

    @drogas.command(name="info", description="Ver el estado de tus cultivos")
    async def drogas_info(self, interaction: discord.Interaction):
        await interaction.response.defer()
        ops = await aexecute(
            "SELECT * FROM drug_operations WHERE discord_id=$1 AND guild_id=$2 AND status='growing' ORDER BY harvest_at",
            (str(interaction.user.id), str(interaction.guild_id)), fetch="all"
        ) or []
        e = criminal_embed("🌿 Tus cultivos activos")
        if not ops:
            e.description = "No tienes cultivos activos"
        else:
            for op in ops:
                drug = DRUG_TYPES.get(op["drug_type"], DRUG_TYPES["marihuana"])
                ts = int(op["harvest_at"].timestamp()) if hasattr(op["harvest_at"],"timestamp") else 0
                e.add_field(
                    name=f"{drug['emoji']} {op['drug_type'].title()}",
                    value=f"Lista: <t:{ts}:R>\nGanancia: {format_currency(drug['yield_min'])}–{format_currency(drug['yield_max'])}",
                    inline=True
                )
        await interaction.followup.send(embed=e, ephemeral=True)

    lavar = app_commands.Group(name="lavar", description="Lavado de dinero")

    @lavar.command(name="dinero", description="Lavar dinero sucio")
    @app_commands.describe(metodo="Método de lavado", cantidad="Cantidad a lavar")
    @app_commands.choices(metodo=[
        app_commands.Choice(name="👕 Lavandería (12% comisión, 4h CD)", value="lavanderia"),
        app_commands.Choice(name="🏢 Empresa Fachada (20% comisión, 8h CD)", value="fachada"),
        app_commands.Choice(name="🎰 Casino (35% comisión, 1h CD)", value="casino"),
    ])
    async def lavar_dinero(self, interaction: discord.Interaction, metodo: str, cantidad: int):
        await interaction.response.defer()
        cd_key = f"lavar:{interaction.user.id}:{interaction.guild_id}:{metodo}"
        method = LAUNDER_METHODS[metodo]
        cd = check_cooldown(cd_key, method["cooldown_hours"] * 3600)
        if cd:
            hrs = int(cd // 3600)
            mins = int((cd % 3600) // 60)
            await interaction.followup.send(embed=error_embed("Cooldown", f"**{method['label']}** disponible en **{hrs}h {mins}m**"), ephemeral=True)
            return
        if cantidad < 100:
            await interaction.followup.send(embed=error_embed("Error", "Mínimo a lavar: **$100**"), ephemeral=True)
            return
        user = await async_get_or_create_user(str(interaction.user.id), str(interaction.guild_id))
        dirty = user.get("dirty_money", 0) or 0
        if dirty < cantidad:
            await interaction.followup.send(embed=error_embed("Sin dinero sucio", f"Solo tienes **{format_currency(dirty)}** de dinero sucio"), ephemeral=True)
            return
        fee = int(cantidad * method["fee_pct"] / 100)
        clean = cantidad - fee
        await aexecute(
            "UPDATE users SET dirty_money=dirty_money-$1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
            (cantidad, str(interaction.user.id), str(interaction.guild_id))
        )
        await async_add_cash(str(interaction.user.id), str(interaction.guild_id), clean)
        await async_log_transaction(str(interaction.user.id), str(interaction.guild_id), "money_laundering", clean, f"Lavado vía {method['label']}")
        await aexecute(
            """INSERT INTO money_laundering (id, discord_id, guild_id, method, amount_dirty, amount_clean, fee, created_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,NOW())""",
            (generate_id(), str(interaction.user.id), str(interaction.guild_id), metodo, cantidad, clean, fee)
        )
        e = dirty_embed(f"{method['emoji']} Lavado exitoso — {method['label']}")
        e.add_field(name="💵 Sucio lavado", value=format_currency(cantidad), inline=True)
        e.add_field(name="💸 Comisión", value=format_currency(fee), inline=True)
        e.add_field(name="✅ Dinero limpio", value=format_currency(clean), inline=True)
        await interaction.followup.send(embed=e, ephemeral=True)

    @lavar.command(name="info", description="Ver métodos de lavado disponibles")
    async def lavar_info(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user = await async_get_or_create_user(str(interaction.user.id), str(interaction.guild_id))
        dirty = user.get("dirty_money", 0) or 0
        e = dirty_embed("🧹 Centro de Limpieza", f"Dinero sucio disponible: **{format_currency(dirty)}**")
        for key, m in LAUNDER_METHODS.items():
            e.add_field(
                name=f"{m['emoji']} {m['label']}",
                value=f"Comisión: **{m['fee_pct']}%**\nCooldown: **{m['cooldown_hours']}h**",
                inline=True
            )
        await interaction.followup.send(embed=e, ephemeral=True)

    misiones = app_commands.Group(name="misiones", description="Misiones criminales")

    @misiones.command(name="lista", description="Ver misiones disponibles")
    async def lista(self, interaction: discord.Interaction):
        await interaction.response.defer()
        e = criminal_embed("🎯 Misiones Criminales")
        for i, m in enumerate(MISSIONS):
            e.add_field(
                name=f"{m['emoji']} {m['name']}",
                value=f"Recompensa: {format_currency(m['reward_min'])}–{format_currency(m['reward_max'])}\nDuración: {m['duration_min']}min | Riesgo: **{m['risk']}**\n`ID: {i}`",
                inline=True
            )
        await interaction.followup.send(embed=e, ephemeral=True)

    @misiones.command(name="iniciar", description="Iniciar una misión criminal")
    @app_commands.describe(id_mision="ID de la misión (0-4)")
    async def iniciar(self, interaction: discord.Interaction, id_mision: int):
        await interaction.response.defer()
        if id_mision < 0 or id_mision >= len(MISSIONS):
            await interaction.followup.send(embed=error_embed("Inválido", "ID de misión inválido"), ephemeral=True)
            return
        active = await aexecute(
            "SELECT id FROM criminal_missions WHERE discord_id=$1 AND guild_id=$2 AND status='active'",
            (str(interaction.user.id), str(interaction.guild_id)), fetch="one"
        )
        if active:
            await interaction.followup.send(embed=error_embed("Misión activa", "Completa tu misión actual primero"), ephemeral=True)
            return
        mission = MISSIONS[id_mision]
        completes_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=mission["duration_min"])
        reward = random.randint(mission["reward_min"], mission["reward_max"])
        await aexecute(
            """INSERT INTO criminal_missions (id, discord_id, guild_id, mission_name, reward, completes_at, status, created_at)
               VALUES ($1,$2,$3,$4,$5,$6,'active',NOW())""",
            (generate_id(), str(interaction.user.id), str(interaction.guild_id), mission["name"], reward, completes_at)
        )
        e = criminal_embed(f"{mission['emoji']} Misión iniciada — {mission['name']}")
        e.add_field(name="💰 Recompensa", value=format_currency(reward), inline=True)
        e.add_field(name="⏰ Completa", value=f"<t:{int(completes_at.timestamp())}:R>", inline=True)
        e.add_field(name="⚠️ Riesgo", value=mission["risk"], inline=True)
        await interaction.followup.send(embed=e, ephemeral=True)

    @misiones.command(name="completar", description="Reclamar recompensa de misión completada")
    async def completar(self, interaction: discord.Interaction):
        await interaction.response.defer()
        now = datetime.datetime.utcnow()
        mission = await aexecute(
            "SELECT * FROM criminal_missions WHERE discord_id=$1 AND guild_id=$2 AND status='active' AND completes_at <= $3",
            (str(interaction.user.id), str(interaction.guild_id), now), fetch="one"
        )
        if not mission:
            pending = await aexecute(
                "SELECT completes_at FROM criminal_missions WHERE discord_id=$1 AND guild_id=$2 AND status='active'",
                (str(interaction.user.id), str(interaction.guild_id)), fetch="one"
            )
            if pending:
                ts = int(pending["completes_at"].timestamp()) if hasattr(pending["completes_at"],"timestamp") else 0
                await interaction.followup.send(embed=error_embed("Aún en progreso", f"Misión lista <t:{ts}:R>"), ephemeral=True)
            else:
                await interaction.followup.send(embed=error_embed("Sin misión", "No tienes misiones activas"), ephemeral=True)
            return
        await aexecute("UPDATE criminal_missions SET status='completed', updated_at=NOW() WHERE id=$1", (mission["id"],))
        await aexecute(
            "UPDATE users SET dirty_money=COALESCE(dirty_money,0)+$1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
            (mission["reward"], str(interaction.user.id), str(interaction.guild_id))
        )
        e = dirty_embed(f"🎯 ¡Misión completada! — {mission['mission_name']}")
        e.add_field(name="💵 Dinero sucio obtenido", value=format_currency(mission["reward"]), inline=True)
        await interaction.followup.send(embed=e, ephemeral=True)

    @misiones.command(name="activas", description="Ver tus misiones activas")
    async def activas(self, interaction: discord.Interaction):
        await interaction.response.defer()
        missions = await aexecute(
            "SELECT * FROM criminal_missions WHERE discord_id=$1 AND guild_id=$2 AND status='active'",
            (str(interaction.user.id), str(interaction.guild_id)), fetch="all"
        ) or []
        e = criminal_embed("🎯 Tus misiones activas")
        if not missions:
            e.description = "No tienes misiones activas"
        else:
            for m in missions:
                ts = int(m["completes_at"].timestamp()) if hasattr(m["completes_at"],"timestamp") else 0
                e.add_field(
                    name=f"📋 {m['mission_name']}",
                    value=f"Recompensa: **{format_currency(m['reward'])}**\nCompleta: <t:{ts}:R>",
                    inline=True
                )
        await interaction.followup.send(embed=e, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Crimen(bot))
