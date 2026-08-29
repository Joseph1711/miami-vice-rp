from bot.db import aexecute
from bot.helpers import calculate_level, xp_for_level

async def add_xp(discord_id, guild_id, amount, bot):
    row = await aexecute(
        "SELECT xp, level FROM users WHERE discord_id=$1 AND guild_id=$2",
        (discord_id, guild_id), fetch="one"
    )
    if not row:
        return
    new_xp = (row["xp"] or 0) + amount
    new_level = calculate_level(new_xp)
    old_level = row["level"] or 1
    await aexecute(
        "UPDATE users SET xp=$1, level=$2, updated_at=NOW() WHERE discord_id=$3 AND guild_id=$4",
        (new_xp, new_level, discord_id, guild_id)
    )
    if new_level > old_level:
        await apply_level_rewards(discord_id, guild_id, new_level, bot)

async def apply_level_rewards(discord_id, guild_id, level, bot):
    rewards = await aexecute(
        "SELECT * FROM level_rewards WHERE guild_id=$1 AND level=$2",
        (guild_id, level), fetch="all"
    ) or []
    guild = bot.get_guild(int(guild_id))
    if not guild:
        return
    member = guild.get_member(int(discord_id))
    if not member:
        return
    for reward in rewards:
        if reward.get("role_id"):
            role = guild.get_role(int(reward["role_id"]))
            if role:
                try:
                    await member.add_roles(role, reason=f"Level {level} reward")
                except Exception:
                    pass
