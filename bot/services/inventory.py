from bot.db import execute, aexecute
from bot.helpers import generate_id

def add_item(user_id, guild_id, item_id, qty=1):
    row = execute(
        "SELECT id, quantity FROM user_inventory WHERE discord_id=$1 AND guild_id=$2 AND item_id=$3",
        (user_id, guild_id, item_id), fetch="one"
    )
    if row:
        execute(
            "UPDATE user_inventory SET quantity=quantity+$1, updated_at=NOW() WHERE id=$2",
            (qty, row["id"])
        )
    else:
        execute(
            """INSERT INTO user_inventory (id, discord_id, guild_id, item_id, quantity, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,NOW(),NOW())""",
            (generate_id(), user_id, guild_id, item_id, qty)
        )

def remove_item(user_id, guild_id, item_id, qty=1):
    row = execute(
        "SELECT id, quantity FROM user_inventory WHERE discord_id=$1 AND guild_id=$2 AND item_id=$3",
        (user_id, guild_id, item_id), fetch="one"
    )
    if not row or row["quantity"] < qty:
        return False
    if row["quantity"] == qty:
        execute("DELETE FROM user_inventory WHERE id=$1", (row["id"],))
    else:
        execute(
            "UPDATE user_inventory SET quantity=quantity-$1, updated_at=NOW() WHERE id=$2",
            (qty, row["id"])
        )
    return True

def get_user_inventory(user_id, guild_id):
    return execute(
        """SELECT ui.item_id, ui.quantity, i.name, i.description, i.rarity, i.price, i.category, i.emoji
           FROM user_inventory ui
           INNER JOIN items i ON i.id=ui.item_id
           WHERE ui.discord_id=$1 AND ui.guild_id=$2
           ORDER BY i.category, i.name""",
        (user_id, guild_id), fetch="all"
    ) or []

async def async_add_item(user_id, guild_id, item_id, qty=1):
    row = await aexecute(
        "SELECT id, quantity FROM user_inventory WHERE discord_id=$1 AND guild_id=$2 AND item_id=$3",
        (user_id, guild_id, item_id), fetch="one"
    )
    if row:
        await aexecute(
            "UPDATE user_inventory SET quantity=quantity+$1, updated_at=NOW() WHERE id=$2",
            (qty, row["id"])
        )
    else:
        await aexecute(
            """INSERT INTO user_inventory (id, discord_id, guild_id, item_id, quantity, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,NOW(),NOW())""",
            (generate_id(), user_id, guild_id, item_id, qty)
        )

async def async_remove_item(user_id, guild_id, item_id, qty=1):
    row = await aexecute(
        "SELECT id, quantity FROM user_inventory WHERE discord_id=$1 AND guild_id=$2 AND item_id=$3",
        (user_id, guild_id, item_id), fetch="one"
    )
    if not row or row["quantity"] < qty:
        return False
    if row["quantity"] == qty:
        await aexecute("DELETE FROM user_inventory WHERE id=$1", (row["id"],))
    else:
        await aexecute(
            "UPDATE user_inventory SET quantity=quantity-$1, updated_at=NOW() WHERE id=$2",
            (qty, row["id"])
        )
    return True

async def async_get_user_inventory(user_id, guild_id):
    return await aexecute(
        """SELECT ui.item_id, ui.quantity, i.name, i.description, i.rarity, i.price, i.category, i.emoji
           FROM user_inventory ui
           INNER JOIN items i ON i.id=ui.item_id
           WHERE ui.discord_id=$1 AND ui.guild_id=$2
           ORDER BY i.category, i.name""",
        (user_id, guild_id), fetch="all"
    ) or []
