import discord
from discord import app_commands
from discord.ext import commands
import datetime

from bot.db import aexecute
from bot.helpers import async_get_or_create_user, format_currency, generate_id
from bot.embeds import success_embed, error_embed, info_embed
from bot.services.economy import async_remove_cash, async_add_cash, async_log_transaction

COOLDOWNS = {}

PROP_EMOJI = {"house":"🏠","apartment":"🏢","warehouse":"🏭","office":"🏬","land":"🌿","mansion":"🏰","store":"🏪"}

def check_cooldown(key, seconds):
    now = datetime.datetime.utcnow().timestamp()
    last = COOLDOWNS.get(key, 0)
    remaining = (last + seconds) - now
    if remaining > 0:
        return remaining
    COOLDOWNS[key] = now
    return 0

class Properties(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    propiedad = app_commands.Group(name="propiedad", description="Gestión de propiedades")

    @propiedad.command(name="lista", description="Ver propiedades disponibles")
    async def lista(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cd = check_cooldown(f"prop:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        props = await aexecute(
            "SELECT * FROM properties WHERE guild_id=$1 AND status='available' ORDER BY type, price",
            (str(interaction.guild_id),), fetch="all"
        ) or []
        e = info_embed("🏘️ Propiedades disponibles")
        if not props:
            e.description = "No hay propiedades disponibles"
        else:
            for p in props:
                emoji = PROP_EMOJI.get(p.get("type","house"),"🏠")
                rent = f" | Renta: {format_currency(p.get('rent_price',0))}/día" if p.get("rent_price") else ""
                e.add_field(
                    name=f"{emoji} {p['name']}",
                    value=f"Precio: **{format_currency(p['price'])}**{rent}\n`ID: {p['id'][:8]}`",
                    inline=True
                )
        await interaction.followup.send(embed=e)

    @propiedad.command(name="comprar", description="Comprar una propiedad")
    @app_commands.describe(id_propiedad="ID de la propiedad (primeros 8 caracteres)")
    async def comprar(self, interaction: discord.Interaction, id_propiedad: str):
        await interaction.response.defer()
        cd = check_cooldown(f"prop:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        prop = await aexecute(
            "SELECT * FROM properties WHERE guild_id=$1 AND status='available' AND id LIKE $2",
            (str(interaction.guild_id), f"{id_propiedad}%"), fetch="one"
        )
        if not prop:
            await interaction.followup.send(embed=error_embed("No disponible", "Propiedad no encontrada o ya comprada"), ephemeral=True)
            return
        await async_get_or_create_user(str(interaction.user.id), str(interaction.guild_id))
        ok = await async_remove_cash(str(interaction.user.id), str(interaction.guild_id), prop["price"])
        if not ok:
            await interaction.followup.send(embed=error_embed("Sin fondos", f"Necesitas **{format_currency(prop['price'])}**"), ephemeral=True)
            return
        await aexecute(
            "UPDATE properties SET status='owned', owner_id=$1, updated_at=NOW() WHERE id=$2",
            (str(interaction.user.id), prop["id"])
        )
        await aexecute(
            """INSERT INTO property_transactions (id, property_id, guild_id, buyer_id, amount, type, created_at)
               VALUES ($1,$2,$3,$4,$5,'purchase',NOW())""",
            (generate_id(), prop["id"], str(interaction.guild_id), str(interaction.user.id), prop["price"])
        )
        await async_log_transaction(str(interaction.user.id), str(interaction.guild_id), "property_purchase", -prop["price"], f"Compra: {prop['name']}")
        emoji = PROP_EMOJI.get(prop.get("type","house"),"🏠")
        await interaction.followup.send(embed=success_embed(f"{emoji} Propiedad adquirida", f"Compraste **{prop['name']}** por **{format_currency(prop['price'])}**"))

    @propiedad.command(name="vender", description="Vender tu propiedad (75% del valor)")
    @app_commands.describe(id_propiedad="ID de la propiedad")
    async def vender(self, interaction: discord.Interaction, id_propiedad: str):
        await interaction.response.defer()
        cd = check_cooldown(f"prop:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        prop = await aexecute(
            "SELECT * FROM properties WHERE guild_id=$1 AND owner_id=$2 AND id LIKE $3",
            (str(interaction.guild_id), str(interaction.user.id), f"{id_propiedad}%"), fetch="one"
        )
        if not prop:
            await interaction.followup.send(embed=error_embed("No encontrada", "No tienes esa propiedad"), ephemeral=True)
            return
        sale_price = int(float(prop["price"]) * 0.75)
        await aexecute("UPDATE properties SET status='available', owner_id=NULL, updated_at=NOW() WHERE id=$1", (prop["id"],))
        await async_add_cash(str(interaction.user.id), str(interaction.guild_id), sale_price)
        await async_log_transaction(str(interaction.user.id), str(interaction.guild_id), "property_sale", sale_price, f"Venta: {prop['name']}")
        await aexecute(
            """INSERT INTO property_transactions (id, property_id, guild_id, buyer_id, amount, type, created_at)
               VALUES ($1,$2,$3,$4,$5,'sale',NOW())""",
            (generate_id(), prop["id"], str(interaction.guild_id), str(interaction.user.id), sale_price)
        )
        emoji = PROP_EMOJI.get(prop.get("type","house"),"🏠")
        await interaction.followup.send(embed=success_embed(f"{emoji} Propiedad vendida", f"Vendiste **{prop['name']}** por **{format_currency(sale_price)}** (75% del valor)"))

    @propiedad.command(name="rentar", description="Rentar una propiedad")
    @app_commands.describe(id_propiedad="ID de la propiedad")
    async def rentar(self, interaction: discord.Interaction, id_propiedad: str):
        await interaction.response.defer()
        cd = check_cooldown(f"prop:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        prop = await aexecute(
            "SELECT * FROM properties WHERE guild_id=$1 AND status='available' AND rent_price IS NOT NULL AND id LIKE $2",
            (str(interaction.guild_id), f"{id_propiedad}%"), fetch="one"
        )
        if not prop:
            await interaction.followup.send(embed=error_embed("No disponible", "Propiedad no encontrada o no se puede rentar"), ephemeral=True)
            return
        await async_get_or_create_user(str(interaction.user.id), str(interaction.guild_id))
        ok = await async_remove_cash(str(interaction.user.id), str(interaction.guild_id), prop["rent_price"])
        if not ok:
            await interaction.followup.send(embed=error_embed("Sin fondos", f"Necesitas **{format_currency(prop['rent_price'])}/día**"), ephemeral=True)
            return
        await aexecute(
            "UPDATE properties SET status='rented', owner_id=$1, updated_at=NOW() WHERE id=$2",
            (str(interaction.user.id), prop["id"])
        )
        await async_log_transaction(str(interaction.user.id), str(interaction.guild_id), "property_rent", -prop["rent_price"], f"Renta: {prop['name']}")
        emoji = PROP_EMOJI.get(prop.get("type","house"),"🏠")
        await interaction.followup.send(embed=success_embed(f"{emoji} Propiedad rentada", f"Estás rentando **{prop['name']}** por **{format_currency(prop['rent_price'])}/día**"))

    @propiedad.command(name="mias", description="Ver tus propiedades")
    async def mias(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cd = check_cooldown(f"prop:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        props = await aexecute(
            "SELECT * FROM properties WHERE guild_id=$1 AND owner_id=$2",
            (str(interaction.guild_id), str(interaction.user.id)), fetch="all"
        ) or []
        e = info_embed(f"🏘️ Propiedades de {interaction.user.display_name}")
        if not props:
            e.description = "No tienes propiedades"
        else:
            for p in props:
                emoji = PROP_EMOJI.get(p.get("type","house"),"🏠")
                e.add_field(
                    name=f"{emoji} {p['name']}",
                    value=f"Estado: **{p.get('status','owned').title()}** | Valor: {format_currency(p['price'])}",
                    inline=True
                )
        await interaction.followup.send(embed=e)


async def setup(bot):
    await bot.add_cog(Properties(bot))
