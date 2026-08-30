import discord
from discord import app_commands
from discord.ext import commands
import datetime

from bot.db import aexecute
from bot.helpers import async_get_or_create_user, format_currency, generate_id
from bot.embeds import success_embed, error_embed, info_embed, blackmarket_embed
from bot.services.economy import async_remove_cash, async_add_cash, async_log_transaction
from bot.services.inventory import async_remove_item, async_add_item

COOLDOWNS = {}

def check_cooldown(key, seconds):
    now = datetime.datetime.utcnow().timestamp()
    last = COOLDOWNS.get(key, 0)
    remaining = (last + seconds) - now
    if remaining > 0:
        return remaining
    COOLDOWNS[key] = now
    return 0

RARITY_COLORS = {"common":"⚪","uncommon":"🟢","rare":"🔵","epic":"🟣","legendary":"🟠"}

class Marketplace(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    mercado = app_commands.Group(name="mercado", description="Mercado de jugadores")

    @mercado.command(name="lista", description="Ver objetos en venta")
    async def lista(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cd = check_cooldown(f"mercado:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        listings = await aexecute(
            """SELECT ml.*, i.name, i.emoji, i.rarity FROM marketplace_listings ml
               JOIN items i ON i.id=ml.item_id
               WHERE ml.guild_id=$1 AND ml.status='active'
               ORDER BY ml.price ASC LIMIT 20""",
            (str(interaction.guild_id),), fetch="all"
        ) or []
        e = info_embed("🛒 Mercado de Jugadores")
        if not listings:
            e.description = "No hay objetos en venta actualmente"
        else:
            for lst in listings:
                emoji = lst.get("emoji") or RARITY_COLORS.get(lst.get("rarity","common"),"⚪")
                e.add_field(
                    name=f"{emoji} {lst['name']} x{lst['quantity']}",
                    value=f"Precio: **{format_currency(lst['price'])}**\nVendedor: <@{lst['seller_id']}>\n`ID: {lst['id'][:8]}`",
                    inline=True
                )
        await interaction.followup.send(embed=e)

    @mercado.command(name="vender", description="Poner un objeto a la venta")
    @app_commands.describe(objeto="Nombre del objeto", cantidad="Cantidad", precio="Precio total")
    async def vender(self, interaction: discord.Interaction, objeto: str, cantidad: int, precio: int):
        await interaction.response.defer()
        cd = check_cooldown(f"mercado:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        if cantidad < 1 or precio < 1:
            await interaction.followup.send(embed=error_embed("Inválido", "Cantidad y precio deben ser positivos"), ephemeral=True)
            return
        item = await aexecute(
            "SELECT * FROM items WHERE name ILIKE $1 AND is_active=true LIMIT 1",
            (f"%{objeto}%",), fetch="one"
        )
        if not item:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Objeto **{objeto}** no existe"), ephemeral=True)
            return
        ok = await async_remove_item(str(interaction.user.id), str(interaction.guild_id), item["id"], cantidad)
        if not ok:
            await interaction.followup.send(embed=error_embed("Sin stock", f"No tienes **{cantidad}x {item['name']}**"), ephemeral=True)
            return
        listing_id = generate_id()
        await aexecute(
            """INSERT INTO marketplace_listings (id, guild_id, seller_id, item_id, quantity, price, status, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,'active',NOW(),NOW())""",
            (listing_id, str(interaction.guild_id), str(interaction.user.id), item["id"], cantidad, precio)
        )
        emoji = item.get("emoji") or RARITY_COLORS.get(item.get("rarity","common"),"⚪")
        await interaction.followup.send(embed=success_embed(
            "Artículo publicado",
            f"{emoji} **{item['name']}** x{cantidad} por **{format_currency(precio)}**\n`ID: {listing_id[:8]}`"
        ))

    @mercado.command(name="comprar", description="Comprar un objeto del mercado")
    @app_commands.describe(id_listado="ID del listado (primeros 8 caracteres)")
    async def comprar(self, interaction: discord.Interaction, id_listado: str):
        await interaction.response.defer()
        cd = check_cooldown(f"mercado:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        listing = await aexecute(
            """SELECT ml.*, i.name, i.emoji, i.rarity FROM marketplace_listings ml
               JOIN items i ON i.id=ml.item_id
               WHERE ml.id LIKE $1 AND ml.guild_id=$2 AND ml.status='active'""",
            (f"{id_listado}%", str(interaction.guild_id)), fetch="one"
        )
        if not listing:
            await interaction.followup.send(embed=error_embed("No encontrado", "Listado no encontrado o ya vendido"), ephemeral=True)
            return
        if listing["seller_id"] == str(interaction.user.id):
            await interaction.followup.send(embed=error_embed("Error", "No puedes comprar tu propio listado"), ephemeral=True)
            return
        await async_get_or_create_user(str(interaction.user.id), str(interaction.guild_id))
        ok = await async_remove_cash(str(interaction.user.id), str(interaction.guild_id), listing["price"])
        if not ok:
            await interaction.followup.send(embed=error_embed("Sin fondos", f"Necesitas **{format_currency(listing['price'])}**"), ephemeral=True)
            return
        await aexecute("UPDATE marketplace_listings SET status='sold', buyer_id=$1, updated_at=NOW() WHERE id=$2", (str(interaction.user.id), listing["id"]))
        await async_add_cash(listing["seller_id"], str(interaction.guild_id), listing["price"])
        await async_add_item(str(interaction.user.id), str(interaction.guild_id), listing["item_id"], listing["quantity"])
        await async_log_transaction(str(interaction.user.id), str(interaction.guild_id), "marketplace_buy", -listing["price"], f"Compra: {listing['name']}")
        emoji = listing.get("emoji") or RARITY_COLORS.get(listing.get("rarity","common"),"⚪")
        await interaction.followup.send(embed=success_embed(
            "Compra exitosa",
            f"Compraste {emoji} **{listing['name']}** x{listing['quantity']} por **{format_currency(listing['price'])}**"
        ))

    @mercado.command(name="subasta", description="Crear una subasta de objetos")
    @app_commands.describe(objeto="Objeto a subastar", cantidad="Cantidad", precio_base="Precio base", horas="Duración en horas (1-72)")
    async def subasta(self, interaction: discord.Interaction, objeto: str, cantidad: int, precio_base: int, horas: int = 24):
        await interaction.response.defer()
        cd = check_cooldown(f"mercado:{interaction.user.id}:{interaction.guild_id}", 10)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        horas = max(1, min(72, horas))
        item = await aexecute("SELECT * FROM items WHERE name ILIKE $1 AND is_active=true LIMIT 1", (f"%{objeto}%",), fetch="one")
        if not item:
            await interaction.followup.send(embed=error_embed("No encontrado", f"Objeto **{objeto}** no existe"), ephemeral=True)
            return
        ok = await async_remove_item(str(interaction.user.id), str(interaction.guild_id), item["id"], cantidad)
        if not ok:
            await interaction.followup.send(embed=error_embed("Sin stock", f"No tienes **{cantidad}x {item['name']}**"), ephemeral=True)
            return
        ends_at = datetime.datetime.utcnow() + datetime.timedelta(hours=horas)
        auction_id = generate_id()
        await aexecute(
            """INSERT INTO auctions (id, guild_id, seller_id, item_id, quantity, starting_bid, current_bid, ends_at, status, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'active',NOW(),NOW())""",
            (auction_id, str(interaction.guild_id), str(interaction.user.id), item["id"], cantidad, precio_base, precio_base, ends_at)
        )
        emoji = item.get("emoji") or "📦"
        e = success_embed("🔨 Subasta creada", f"{emoji} **{item['name']}** x{cantidad}\nPrecio base: **{format_currency(precio_base)}**")
        e.add_field(name="⏰ Termina", value=f"<t:{int(ends_at.timestamp())}:R>", inline=True)
        e.add_field(name="🆔 ID", value=f"`{auction_id[:8]}`", inline=True)
        await interaction.followup.send(embed=e)

    @mercado.command(name="pujar", description="Pujar en una subasta activa")
    @app_commands.describe(id_subasta="ID de la subasta", cantidad="Cantidad a pujar")
    async def pujar(self, interaction: discord.Interaction, id_subasta: str, cantidad: int):
        await interaction.response.defer()
        cd = check_cooldown(f"pujar:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        auction = await aexecute(
            """SELECT a.*, i.name, i.emoji FROM auctions a
               JOIN items i ON i.id=a.item_id
               WHERE a.id LIKE $1 AND a.guild_id=$2 AND a.status='active'""",
            (f"{id_subasta}%", str(interaction.guild_id)), fetch="one"
        )
        if not auction:
            await interaction.followup.send(embed=error_embed("No encontrada", "Subasta no encontrada o cerrada"), ephemeral=True)
            return
        if auction["seller_id"] == str(interaction.user.id):
            await interaction.followup.send(embed=error_embed("Error", "No puedes pujar en tu propia subasta"), ephemeral=True)
            return
        now = datetime.datetime.utcnow()
        ends_at = auction["ends_at"]
        if hasattr(ends_at, "replace"):
            ends_at = ends_at.replace(tzinfo=None)
        if now > ends_at:
            await interaction.followup.send(embed=error_embed("Subasta terminada", "Esta subasta ya cerró"), ephemeral=True)
            return
        min_bid = float(auction.get("current_bid") or auction.get("starting_bid") or auction.get("starting_price") or 0) + 1
        if cantidad < min_bid:
            await interaction.followup.send(embed=error_embed("Puja baja", f"La puja mínima es **{format_currency(min_bid)}**"), ephemeral=True)
            return
        await async_get_or_create_user(str(interaction.user.id), str(interaction.guild_id))
        user = await aexecute("SELECT cash FROM users WHERE discord_id=$1 AND guild_id=$2", (str(interaction.user.id), str(interaction.guild_id)), fetch="one")
        if not user or float(user.get("cash",0)) < cantidad:
            await interaction.followup.send(embed=error_embed("Sin fondos", f"Necesitas **{format_currency(cantidad)}** en efectivo"), ephemeral=True)
            return
        if auction.get("current_bidder_id"):
            await async_add_cash(auction["current_bidder_id"], str(interaction.guild_id), float(auction["current_bid"]))
        await aexecute(
            "UPDATE auctions SET current_bid=$1, current_bidder_id=$2, updated_at=NOW() WHERE id=$3",
            (cantidad, str(interaction.user.id), auction["id"])
        )
        await async_remove_cash(str(interaction.user.id), str(interaction.guild_id), cantidad)
        emoji = auction.get("emoji") or "📦"
        await interaction.followup.send(embed=success_embed(
            "Puja realizada",
            f"Pujaste **{format_currency(cantidad)}** por {emoji} **{auction['name']}** x{auction['quantity']}"
        ))

    @mercado.command(name="cancelar", description="Cancelar un listado propio del mercado")
    @app_commands.describe(id_listado="ID del listado")
    async def cancelar(self, interaction: discord.Interaction, id_listado: str):
        await interaction.response.defer()
        listing = await aexecute(
            "SELECT * FROM marketplace_listings WHERE id LIKE $1 AND guild_id=$2 AND seller_id=$3 AND status='active'",
            (f"{id_listado}%", str(interaction.guild_id), str(interaction.user.id)), fetch="one"
        )
        if not listing:
            await interaction.followup.send(embed=error_embed("No encontrado", "Listado no encontrado o no te pertenece"), ephemeral=True)
            return
        await aexecute("UPDATE marketplace_listings SET status='cancelled', updated_at=NOW() WHERE id=$1", (listing["id"],))
        await async_add_item(str(interaction.user.id), str(interaction.guild_id), listing["item_id"], listing["quantity"])
        await interaction.followup.send(embed=success_embed("Listado cancelado", f"Tu objeto fue devuelto al inventario"))

    tienda = app_commands.Group(name="tienda", description="Tienda oficial del servidor")

    @tienda.command(name="explorar", description="Ver objetos disponibles en la tienda")
    @app_commands.describe(categoria="Filtrar por categoría (opcional)")
    async def tienda_explorar(self, interaction: discord.Interaction, categoria: str = None):
        await interaction.response.defer()
        cd = check_cooldown(f"tienda:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        if categoria:
            items = await aexecute(
                """SELECT s.*, i.name, i.emoji, i.rarity, i.category FROM shop s
                   JOIN items i ON i.id=s.item_id
                   WHERE s.guild_id=$1 AND (s.stock = -1 OR s.stock > 0) AND i.category ILIKE $2
                   ORDER BY i.category, s.price LIMIT 25""",
                (str(interaction.guild_id), f"%{categoria}%"), fetch="all"
            ) or []
        else:
            items = await aexecute(
                """SELECT s.*, i.name, i.emoji, i.rarity, i.category FROM shop s
                   JOIN items i ON i.id=s.item_id
                   WHERE s.guild_id=$1 AND (s.stock = -1 OR s.stock > 0)
                   ORDER BY i.category, s.price LIMIT 25""",
                (str(interaction.guild_id),), fetch="all"
            ) or []
        e = info_embed("🏪 Tienda Oficial")
        if not items:
            e.description = "No hay artículos disponibles en la tienda"
        else:
            cats = {}
            for it in items:
                cats.setdefault(it.get("category","General"), []).append(it)
            for cat, citems in list(cats.items())[:6]:
                lines = []
                for it in citems[:4]:
                    emoji = it.get("emoji") or RARITY_COLORS.get(it.get("rarity","common"),"⚪")
                    stock = "Stock: ∞" if it.get("stock") == -1 else (f"Stock: {it['stock']}" if it.get("stock") else "")
                    lines.append(f"{emoji} **{it['name']}** — {format_currency(it['price'])} {stock}")
                e.add_field(name=f"📦 {cat}", value="\n".join(lines), inline=True)
        await interaction.followup.send(embed=e)

    @tienda.command(name="comprar", description="Comprar un objeto de la tienda")
    @app_commands.describe(objeto="Nombre del objeto", cantidad="Cantidad (por defecto 1)")
    async def tienda_comprar(self, interaction: discord.Interaction, objeto: str, cantidad: int = 1):
        await interaction.response.defer()
        cd = check_cooldown(f"tienda:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        if cantidad < 1:
            await interaction.followup.send(embed=error_embed("Error", "Cantidad mínima: 1"), ephemeral=True)
            return
        shop_item = await aexecute(
            """SELECT s.*, i.name, i.emoji, i.rarity, i.category FROM shop s
               JOIN items i ON i.id=s.item_id
               WHERE s.guild_id=$1 AND i.name ILIKE $2 AND (s.stock = -1 OR s.stock > 0) LIMIT 1""",
            (str(interaction.guild_id), f"%{objeto}%"), fetch="one"
        )
        if not shop_item:
            await interaction.followup.send(embed=error_embed("No disponible", f"**{objeto}** no está disponible en la tienda"), ephemeral=True)
            return
        if shop_item.get("stock") is not None and shop_item["stock"] != -1 and shop_item["stock"] < cantidad:
            await interaction.followup.send(embed=error_embed("Stock insuficiente", f"Solo hay **{shop_item['stock']}** unidades disponibles"), ephemeral=True)
            return
        total = shop_item["price"] * cantidad
        await async_get_or_create_user(str(interaction.user.id), str(interaction.guild_id))
        ok = await async_remove_cash(str(interaction.user.id), str(interaction.guild_id), total)
        if not ok:
            await interaction.followup.send(embed=error_embed("Sin fondos", f"Necesitas **{format_currency(total)}**"), ephemeral=True)
            return
        if shop_item.get("stock", -1) > 0:
            await aexecute("UPDATE shop SET stock=stock-$1, updated_at=NOW() WHERE id=$2", (cantidad, shop_item["id"]))
        await async_add_item(str(interaction.user.id), str(interaction.guild_id), shop_item["item_id"], cantidad)
        await async_log_transaction(str(interaction.user.id), str(interaction.guild_id), "shop_purchase", -total, f"Tienda: {shop_item['name']} x{cantidad}")
        emoji = shop_item.get("emoji") or "📦"
        await interaction.followup.send(embed=success_embed(
            "Compra realizada",
            f"Compraste {emoji} **{shop_item['name']}** x{cantidad} por **{format_currency(total)}**"
        ))

    @tienda.command(name="info", description="Ver detalles de un objeto de la tienda")
    @app_commands.describe(objeto="Nombre del objeto")
    async def tienda_info(self, interaction: discord.Interaction, objeto: str):
        await interaction.response.defer()
        shop_item = await aexecute(
            """SELECT s.*, i.name, i.emoji, i.rarity, i.category, i.description FROM shop s
               JOIN items i ON i.id=s.item_id
               WHERE s.guild_id=$1 AND i.name ILIKE $2 LIMIT 1""",
            (str(interaction.guild_id), f"%{objeto}%"), fetch="one"
        )
        if not shop_item:
            await interaction.followup.send(embed=error_embed("No encontrado", f"**{objeto}** no está en la tienda"), ephemeral=True)
            return
        emoji = shop_item.get("emoji") or "📦"
        rarity_color = RARITY_COLORS.get(shop_item.get("rarity","common"),"⚪")
        e = info_embed(f"{emoji} {shop_item['name']}", shop_item.get("description",""))
        e.add_field(name="💰 Precio", value=format_currency(shop_item["price"]), inline=True)
        stock = shop_item.get("stock")
        stock_display = "∞" if stock is None or stock == -1 else str(stock)
        e.add_field(name="📦 Stock", value=stock_display, inline=True)
        e.add_field(name="✨ Rareza", value=f"{rarity_color} {shop_item.get('rarity','common').title()}", inline=True)
        e.add_field(name="🏷️ Categoría", value=shop_item.get("category","General"), inline=True)
        await interaction.followup.send(embed=e)

    mercadonegro = app_commands.Group(name="mercadonegro", description="Mercado negro del servidor")

    @mercadonegro.command(name="explorar", description="Ver el stock del mercado negro")
    async def bm_explorar(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cd = check_cooldown(f"bm:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        stock = await aexecute(
            """SELECT bms.*, i.name, i.emoji, i.rarity, i.category, i.price as base_price FROM black_market_stock bms
               JOIN items i ON i.id=bms.item_id
               WHERE bms.quantity > 0
               ORDER BY i.category, bms.price_modifier DESC""",
            fetch="all"
        ) or []
        e = blackmarket_embed("🕶️ Mercado Negro")
        if not stock:
            e.description = "El mercado negro está vacío. Vuelve más tarde."
        else:
            for s in stock[:12]:
                emoji = s.get("emoji") or "📦"
                actual_price = int(float(s.get("base_price",0)) * float(s.get("price_modifier",1.0)))
                e.add_field(
                    name=f"{emoji} {s['name']}",
                    value=f"💰 **{format_currency(actual_price)}**\nStock: {s['quantity']}\n`ID: {s['id'][:8]}`",
                    inline=True
                )
        e.set_footer(text="⚠️ Stock rotativo — el mercado cambia cada 6h")
        await interaction.followup.send(embed=e, ephemeral=True)

    @mercadonegro.command(name="comprar", description="Comprar del mercado negro")
    @app_commands.describe(id_stock="ID del item (primeros 8 caracteres)", cantidad="Cantidad (por defecto 1)")
    async def bm_comprar(self, interaction: discord.Interaction, id_stock: str, cantidad: int = 1):
        await interaction.response.defer()
        cd = check_cooldown(f"bm:{interaction.user.id}:{interaction.guild_id}", 5)
        if cd:
            await interaction.followup.send(embed=error_embed("Espera", f"Intenta en `{cd:.1f}s`"), ephemeral=True)
            return
        if cantidad < 1:
            await interaction.followup.send(embed=error_embed("Error", "Cantidad mínima: 1"), ephemeral=True)
            return
        stock = await aexecute(
            """SELECT bms.*, i.name, i.emoji, i.rarity, i.price as base_price FROM black_market_stock bms
               JOIN items i ON i.id=bms.item_id
               WHERE bms.id LIKE $1 AND bms.quantity >= $2""",
            (f"{id_stock}%", cantidad), fetch="one"
        )
        if not stock:
            await interaction.followup.send(embed=error_embed("No disponible", "Item no encontrado o sin stock suficiente"), ephemeral=True)
            return
        actual_price = int(float(stock["base_price"]) * float(stock.get("price_modifier",1.0)))
        total = actual_price * cantidad
        await async_get_or_create_user(str(interaction.user.id), str(interaction.guild_id))
        ok = await async_remove_cash(str(interaction.user.id), str(interaction.guild_id), total)
        if not ok:
            await interaction.followup.send(embed=error_embed("Sin fondos", f"Necesitas **{format_currency(total)}**"), ephemeral=True)
            return
        await aexecute("UPDATE black_market_stock SET quantity=quantity-$1, updated_at=NOW() WHERE id=$2", (cantidad, stock["id"]))
        await async_add_item(str(interaction.user.id), str(interaction.guild_id), stock["item_id"], cantidad)
        await aexecute(
            """INSERT INTO black_market_transactions (id, discord_id, guild_id, item_id, quantity, price, created_at)
               VALUES ($1,$2,$3,$4,$5,$6,NOW())""",
            (generate_id(), str(interaction.user.id), str(interaction.guild_id), stock["item_id"], cantidad, total)
        )
        await async_log_transaction(str(interaction.user.id), str(interaction.guild_id), "blackmarket_purchase", -total, f"Mercado negro: {stock['name']} x{cantidad}")
        emoji = stock.get("emoji") or "📦"
        await interaction.followup.send(embed=blackmarket_embed("🕶️ Compra en el mercado negro", f"Adquiriste {emoji} **{stock['name']}** x{cantidad} por **{format_currency(total)}**"), ephemeral=True)


async def setup(bot):
    await bot.add_cog(Marketplace(bot))
