import asyncio
import logging
import datetime
import random
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bot.db import aexecute
from bot.helpers import generate_id

logger = logging.getLogger("bot")

def setup_jobs(bot):
    scheduler = AsyncIOScheduler()

    @scheduler.scheduled_job("interval", minutes=10)
    async def process_investments():
        try:
            now = datetime.datetime.utcnow()
            investments = await aexecute(
                "SELECT * FROM investments WHERE status='active' AND matures_at <= $1",
                (now,), fetch="all"
            ) or []
            if not investments:
                return
            for inv in investments:
                returns = float(inv["amount"]) * (1 + float(inv["return_rate"]) / 100)
                await aexecute(
                    "UPDATE users SET bank=bank+$1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
                    (returns, inv["discord_id"], inv["guild_id"])
                )
                await aexecute(
                    "UPDATE investments SET status='completed', updated_at=NOW() WHERE id=$1",
                    (inv["id"],)
                )
                await aexecute(
                    """INSERT INTO transactions (id, discord_id, guild_id, type, amount, description, created_at)
                       VALUES ($1,$2,$3,'investment_return',$4,'Retorno de inversión',NOW())""",
                    (generate_id(), inv["discord_id"], inv["guild_id"], returns)
                )
            logger.info(f"Processed {len(investments)} mature investments")
        except Exception as e:
            logger.error(f"Investment job error: {e}")

    @scheduler.scheduled_job("interval", hours=6)
    async def rotate_blackmarket():
        try:
            items = await aexecute(
                "SELECT id FROM items WHERE is_active=true AND black_market_only=true ORDER BY RANDOM() LIMIT 8",
                fetch="all"
            ) or []
            if not items:
                logger.info("Black market rotation skipped: no black-market-only items found")
                return
            await aexecute("DELETE FROM black_market_stock")
            for item in items:
                await aexecute(
                    """INSERT INTO black_market_stock (id, item_id, price_modifier, quantity, created_at, updated_at)
                       VALUES ($1,$2,$3,$4,NOW(),NOW())
                       ON CONFLICT DO NOTHING""",
                    (generate_id(), item["id"],
                     round(random.uniform(1.0, 2.0), 2),
                     random.randint(1, 8))
                )
            logger.info(f"Black market rotated: {len(items)} illegal items stocked")
        except Exception as e:
            logger.error(f"Black market rotation error: {e}")

    @scheduler.scheduled_job("interval", minutes=5)
    async def remove_temp_roles():
        try:
            now = datetime.datetime.utcnow()
            expired = await aexecute(
                "SELECT * FROM temp_roles WHERE expires_at <= $1",
                (now,), fetch="all"
            ) or []
            if not expired:
                return
            for tr in expired:
                guild = bot.get_guild(int(tr["guild_id"]))
                if guild:
                    member = guild.get_member(int(tr["discord_id"]))
                    if member:
                        role = guild.get_role(int(tr["role_id"]))
                        if role:
                            try:
                                await member.remove_roles(role, reason="Temporary role expired")
                            except Exception:
                                pass
                await aexecute("DELETE FROM temp_roles WHERE id=$1", (tr["id"],))
            logger.info(f"Removed {len(expired)} expired temp roles")
        except Exception as e:
            logger.error(f"Temp roles job error: {e}")

    @scheduler.scheduled_job("interval", minutes=2)
    async def process_auctions():
        try:
            now = datetime.datetime.utcnow()
            auctions = await aexecute(
                "SELECT * FROM auctions WHERE status='active' AND ends_at <= $1",
                (now,), fetch="all"
            ) or []
            if not auctions:
                return
            for auction in auctions:
                if auction.get("current_bidder_id") and auction.get("current_bid"):
                    has_row = await aexecute(
                        "SELECT id FROM user_inventory WHERE discord_id=$1 AND guild_id=$2 AND item_id=$3",
                        (auction["current_bidder_id"], auction["guild_id"], auction["item_id"]), fetch="one"
                    )
                    if has_row:
                        await aexecute(
                            "UPDATE user_inventory SET quantity=quantity+1, updated_at=NOW() WHERE discord_id=$1 AND guild_id=$2 AND item_id=$3",
                            (auction["current_bidder_id"], auction["guild_id"], auction["item_id"])
                        )
                    else:
                        await aexecute(
                            """INSERT INTO user_inventory (id, discord_id, guild_id, item_id, quantity, created_at, updated_at)
                               VALUES ($1,$2,$3,$4,1,NOW(),NOW())""",
                            (generate_id(), auction["current_bidder_id"], auction["guild_id"], auction["item_id"])
                        )
                    await aexecute(
                        "UPDATE users SET cash=cash+$1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
                        (auction["current_bid"], auction["seller_id"], auction["guild_id"])
                    )
                else:
                    await aexecute(
                        """INSERT INTO user_inventory (id, discord_id, guild_id, item_id, quantity, created_at, updated_at)
                           VALUES ($1,$2,$3,$4,1,NOW(),NOW())
                           ON CONFLICT DO NOTHING""",
                        (generate_id(), auction["seller_id"], auction["guild_id"], auction["item_id"])
                    )
                await aexecute(
                    "UPDATE auctions SET status='completed', updated_at=NOW() WHERE id=$1",
                    (auction["id"],)
                )
        except Exception as e:
            logger.error(f"Auction job error: {e}")

    @scheduler.scheduled_job("cron", hour=0, minute=0)
    async def pay_salaries():
        try:
            dept_members = await aexecute(
                """SELECT dm.*, d.budget, d.guild_id FROM department_members dm
                   JOIN departments d ON d.id=dm.department_id
                   WHERE dm.salary > 0 AND d.budget >= dm.salary""",
                fetch="all"
            ) or []
            for m in dept_members:
                await aexecute(
                    "UPDATE departments SET budget=budget-$1, updated_at=NOW() WHERE id=$2",
                    (m["salary"], m["department_id"])
                )
                await aexecute(
                    "UPDATE users SET cash=cash+$1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
                    (m["salary"], m["discord_id"], m["guild_id"])
                )
                await aexecute(
                    """INSERT INTO transactions (id, discord_id, guild_id, type, amount, description, created_at)
                       VALUES ($1,$2,$3,'department_salary',$4,'Salario departamento',NOW())""",
                    (generate_id(), m["discord_id"], m["guild_id"], m["salary"])
                )
            company_members = await aexecute(
                """SELECT cm.*, c.funds, c.guild_id FROM company_members cm
                   JOIN companies c ON c.id=cm.company_id
                   WHERE cm.salary > 0 AND c.funds >= cm.salary""",
                fetch="all"
            ) or []
            for m in company_members:
                await aexecute(
                    "UPDATE companies SET funds=funds-$1, updated_at=NOW() WHERE id=$2",
                    (m["salary"], m["company_id"])
                )
                await aexecute(
                    "UPDATE users SET cash=cash+$1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
                    (m["salary"], m["discord_id"], m["guild_id"])
                )
                await aexecute(
                    """INSERT INTO transactions (id, discord_id, guild_id, type, amount, description, created_at)
                       VALUES ($1,$2,$3,'company_salary',$4,'Salario empresa',NOW())""",
                    (generate_id(), m["discord_id"], m["guild_id"], m["salary"])
                )
            logger.info(f"Paid {len(dept_members)} dept + {len(company_members)} company salaries")
        except Exception as e:
            logger.error(f"Salary job error: {e}")

    @scheduler.scheduled_job("cron", hour=6, minute=0)
    async def apply_savings_interest():
        try:
            accounts = await aexecute(
                "SELECT * FROM savings_accounts WHERE balance > 0",
                fetch="all"
            ) or []
            if not accounts:
                return
            for acct in accounts:
                interest = float(acct["balance"]) * float(acct["interest_rate"]) / 100
                await aexecute(
                    "UPDATE savings_accounts SET balance=balance+$1, updated_at=NOW() WHERE id=$2",
                    (interest, acct["id"])
                )
                await aexecute(
                    "UPDATE users SET bank=bank+$1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
                    (interest, acct["discord_id"], acct["guild_id"])
                )
            logger.info(f"Applied savings interest to {len(accounts)} accounts")
        except Exception as e:
            logger.error(f"Savings interest job error: {e}")

    @scheduler.scheduled_job("cron", minute=0)
    async def process_vehicle_repairs():
        try:
            now = datetime.datetime.utcnow()
            await aexecute(
                "UPDATE fleet_vehicles SET status='active', updated_at=NOW() WHERE status='repairing' AND repair_completes_at <= $1",
                (now,)
            )
        except Exception as e:
            logger.error(f"Vehicle repair job error: {e}")

    scheduler.start()
    logger.info("Cron jobs started")
    return scheduler
