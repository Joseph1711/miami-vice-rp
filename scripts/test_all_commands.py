"""
Comprehensive tester and simulator for all Miami Vice cogs, commands, and SQL queries.
Provides lightweight mocks for discord / discord.ext / etc. so we can execute every command function and every SQL statement directly against SQLite.
"""
import sys
import os
import types
import asyncio
import re

# Insert mock modules for discord
def create_mock_module(name):
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m

discord = create_mock_module("discord")
discord_ext = create_mock_module("discord.ext")
discord_ext_commands = create_mock_module("discord.ext.commands")
discord_ext_tasks = create_mock_module("discord.ext.tasks")
discord_app_commands = create_mock_module("discord.app_commands")

# Mock discord classes
class MockColor:
    @classmethod
    def from_rgb(cls, r, g, b): return cls()
    @classmethod
    def gold(cls): return cls()
    @classmethod
    def green(cls): return cls()
    @classmethod
    def red(cls): return cls()
    @classmethod
    def blue(cls): return cls()
    @classmethod
    def purple(cls): return cls()
    @classmethod
    def blurple(cls): return cls()
    @classmethod
    def dark_embed(cls): return cls()

class MockEmbed:
    def __init__(self, **kwargs):
        self.title = kwargs.get("title", "")
        self.description = kwargs.get("description", "")
        self.color = kwargs.get("color", None)
        self.fields = []
    def add_field(self, name, value, inline=True):
        self.fields.append({"name": name, "value": value, "inline": inline})
    def set_footer(self, text=None, icon_url=None): pass
    def set_thumbnail(self, url=None): pass
    def set_author(self, name=None, icon_url=None): pass

class MockUser:
    def __init__(self, user_id=987654321098765432, name="UserTest"):
        self.id = user_id
        self.name = name
        self.display_name = f"{name}_Display"
        self.mention = f"<@{user_id}>"
        self.bot = False
        self.roles = []
        self.guild_permissions = types.SimpleNamespace(administrator=True, manage_guild=True, manage_channels=True)
    def __str__(self):
        return self.name

class MockInteraction:
    def __init__(self, guild_id=123456789012345678, user_id=987654321098765432):
        self.guild_id = guild_id
        self.guild = types.SimpleNamespace(
            id=guild_id, 
            name="Test City RP", 
            member_count=100, 
            get_member=lambda uid: MockUser(uid, "MemberName"),
            get_role=lambda rid: types.SimpleNamespace(id=rid, name="RoleName", mention=f"<@&{rid}>"),
            get_channel=lambda cid: types.SimpleNamespace(id=cid, name="channel-name", mention=f"<#{cid}>")
        )
        self.user = MockUser(user_id, "UserTest")
        self.channel = types.SimpleNamespace(
            id=11111, 
            name="general", 
            mention="<#11111>",
            send=self._async_noop,
            delete=self._async_noop
        )
        self.response = types.SimpleNamespace(
            defer=self._async_noop,
            send_message=self._async_noop,
            is_done=lambda: True
        )
        self.followup = types.SimpleNamespace(
            send=self._async_noop
        )
    async def _async_noop(self, *args, **kwargs):
        pass

class MockAppCommands:
    @staticmethod
    def describe(**kwargs):
        def dec(f): return f
        return dec
    @staticmethod
    def choices(**kwargs):
        def dec(f): return f
        return dec
    @staticmethod
    def checks():
        m = types.SimpleNamespace()
        m.has_permissions = lambda **kw: lambda f: f
        return m
    class Choice:
        def __init__(self, name, value):
            self.name = name
            self.value = value
    class Group:
        def __init__(self, name="", description=""):
            self.name = name
            self.description = description
            self.commands = []
        def command(self, name="", description=""):
            def dec(f):
                f.__cmd_name__ = name
                f.__cmd_desc__ = description
                f.__cmd_group__ = self.name
                self.commands.append(f)
                return f
            return dec

def mock_command(name="", description=""):
    def dec(f):
        f.__cmd_name__ = name
        f.__cmd_desc__ = description
        f.__cmd_group__ = None
        return f
    return dec

discord.Embed = MockEmbed
discord.Color = MockColor
discord.Interaction = MockInteraction
discord.Member = MockUser
discord.User = MockUser
discord.Role = object
discord.TextChannel = object
discord.VoiceChannel = object
discord.Attachment = object
discord.ButtonStyle = types.SimpleNamespace(primary=1, secondary=2, success=3, danger=4, link=5)
discord.utils = types.SimpleNamespace(
    get=lambda iterable, **attrs: None,
    format_dt=lambda dt, style='f': str(dt) if dt else "N/A",
    utcnow=lambda: datetime.datetime.utcnow()
)
discord.ui = types.SimpleNamespace(
    View=object,
    Button=object,
    Modal=object,
    TextInput=object,
    Select=object,
    button=lambda **kw: lambda f: f
)
discord.app_commands = MockAppCommands
discord.app_commands.command = mock_command
discord.app_commands.describe = MockAppCommands.describe
discord.app_commands.choices = MockAppCommands.choices
discord.app_commands.Choice = MockAppCommands.Choice
discord.app_commands.Group = MockAppCommands.Group
discord.app_commands.checks = MockAppCommands.checks()

class CogBase:
    pass

discord_ext_commands.Cog = CogBase
discord_ext_commands.Bot = object
discord_ext_tasks.loop = lambda **kw: lambda f: f

# Now setup sys.path and test database
sys.path.insert(0, os.path.abspath("."))
from bot.db import DB_PATH, check_connection, execute, aexecute, _prepare_query_and_params
from scripts.init_db import init_db

init_db()

from bot.helpers import *
from bot.services.economy import *
from bot.services.inventory import *
from bot.services.levels import *

import importlib
import inspect

COG_MODULES = [
    "bot.cogs.economy",
    "bot.cogs.bank",
    "bot.cogs.crimen",
    "bot.cogs.inventory",
    "bot.cogs.marketplace",
    "bot.cogs.departments",
    "bot.cogs.companies",
    "bot.cogs.properties",
    "bot.cogs.social",
    "bot.cogs.tickets",
    "bot.cogs.verification",
    "bot.cogs.admin",
    "bot.cogs.help",
]

async def run_all_tests():
    print("=" * 60)
    print("Starting Automated Discovery and Test of All Bot Commands")
    print("=" * 60)

    guild_id = 123456789012345678
    user_id = 987654321098765432
    target_id = 112233445566778899

    # Seed some standard data
    execute("INSERT OR REPLACE INTO users (id, discord_id, guild_id, username, display_name, cash, bank, xp, level, reputation, dirty_money, is_verified, created_at, updated_at) VALUES ($1,$2,$3,$4,$5,50000,50000,100,5,10,1000,1,NOW(),NOW())",
            ("u_test_1", str(user_id), str(guild_id), "UserTest", "UserTest_Name"))
    execute("INSERT OR REPLACE INTO users (id, discord_id, guild_id, username, display_name, cash, bank, xp, level, reputation, dirty_money, is_verified, created_at, updated_at) VALUES ($1,$2,$3,$4,$5,50000,50000,100,5,10,1000,1,NOW(),NOW())",
            ("u_target_1", str(target_id), str(guild_id), "TargetUser", "TargetUser_Name"))

    # Seed items
    item_1 = "item_phone"
    item_2 = "item_lockpick"
    execute("INSERT OR REPLACE INTO items (id, name, description, price, category, rarity, emoji) VALUES ($1,$2,$3,$4,$5,$6,$7)",
            (item_1, "Teléfono Móvil", "Teléfono para comunicarse", 500, "electronica", "comun", "📱"))
    execute("INSERT OR REPLACE INTO items (id, name, description, price, category, rarity, emoji) VALUES ($1,$2,$3,$4,$5,$6,$7)",
            (item_2, "Ganzúa", "Herramienta para abrir cerraduras", 250, "ilegal", "poco_comun", "🔓"))

    # Seed shop
    execute("INSERT OR REPLACE INTO shop (id, guild_id, item_id, price, stock) VALUES ($1,$2,$3,$4,$5)",
            ("shop_item_1", str(guild_id), item_1, 500, 20))

    # Seed company & department
    execute("INSERT OR REPLACE INTO departments (id, guild_id, name, acronym, description, budget) VALUES ($1,$2,$3,$4,$5,$6)",
            ("dept_1", str(guild_id), "Miami Police Department", "MPD", "Departamento de policía", 100000))
    execute("INSERT OR REPLACE INTO department_members (id, department_id, discord_id, guild_id, rank, salary, joined_at) VALUES ($1,$2,$3,$4,$5,$6,NOW())",
            ("dm_1", "dept_1", str(user_id), str(guild_id), "Chief", 1500))

    execute("INSERT OR REPLACE INTO companies (id, guild_id, owner_id, name, description, funds) VALUES ($1,$2,$3,$4,$5,$6)",
            ("comp_1", str(guild_id), str(user_id), "Vice Logistics", "Empresa de logística", 50000))
    execute("INSERT OR REPLACE INTO company_members (id, company_id, discord_id, guild_id, role, salary, joined_at) VALUES ($1,$2,$3,$4,$5,$6,NOW())",
            ("cm_1", "comp_1", str(user_id), str(guild_id), "Owner", 1000))

    # Seed property
    execute("INSERT OR REPLACE INTO properties (id, guild_id, name, type, price, rent_price, status) VALUES ($1,$2,$3,$4,$5,$6,$7)",
            ("prop_1", str(guild_id), "Apartamento en Ocean Drive", "apartamento", 25000, 500, "available"))

    total_tested = 0
    passed = 0
    errors = []

    for mod_name in COG_MODULES:
        print(f"\n---> Inspecting module: {mod_name}")
        mod = importlib.import_module(mod_name)
        
        # Find cog class
        cog_class = None
        for attr_name in dir(mod):
            attr = getattr(mod, attr_name)
            if inspect.isclass(attr) and issubclass(attr, CogBase) and attr is not CogBase:
                cog_class = attr
                break
        
        if not cog_class:
            print(f"  [WARN] No Cog class found in {mod_name}")
            continue

        mock_bot = types.SimpleNamespace(user=types.SimpleNamespace(id=999, name="MiamiViceBot"), guilds=[types.SimpleNamespace(id=guild_id)])
        cog_instance = cog_class(mock_bot)

        # Inspect all attributes and methods
        for attr_name in dir(cog_instance):
            attr = getattr(cog_instance, attr_name)
            
            # Check if it is a Group
            if isinstance(attr, MockAppCommands.Group):
                group_name = attr.name
                for cmd_fn in attr.commands:
                    cmd_name = getattr(cmd_fn, "__cmd_name__", cmd_fn.__name__)
                    full_name = f"/{group_name} {cmd_name}"
                    total_tested += 1
                    print(f"  Testing command {full_name} ...", end=" ")
                    
                    try:
                        interaction = MockInteraction(guild_id=guild_id, user_id=user_id)
                        sig = inspect.signature(cmd_fn)
                        kwargs = {}
                        for param_name, param in sig.parameters.items():
                            if param_name in ("self", "interaction"):
                                continue
                            # Supply smart default test value
                            if "item" in param_name or "objeto" in param_name:
                                kwargs[param_name] = "Teléfono Móvil"
                            elif "cantidad" in param_name or "amount" in param_name or "qty" in param_name or "precio" in param_name:
                                kwargs[param_name] = 1
                            elif "usuario" in param_name or "user" in param_name or "member" in param_name or "target" in param_name:
                                kwargs[param_name] = types.SimpleNamespace(id=target_id, name="TargetUser", mention=f"<@{target_id}>")
                            elif "canal" in param_name or "channel" in param_name:
                                kwargs[param_name] = types.SimpleNamespace(id=11111, mention="<#11111>", name="general")
                            elif "rol" in param_name or "role" in param_name:
                                kwargs[param_name] = types.SimpleNamespace(id=22222, mention="<@&22222>", name="Ciudadano")
                            elif "categoria" in param_name or "category" in param_name:
                                kwargs[param_name] = "electronica"
                            elif "tipo" in param_name or "type" in param_name:
                                kwargs[param_name] = "police"
                            elif "codigo" in param_name or "code" in param_name or "nombre" in param_name or "name" in param_name:
                                kwargs[param_name] = "test_code"
                            elif "motivo" in param_name or "reason" in param_name or "mensaje" in param_name or "descripcion" in param_name:
                                kwargs[param_name] = "Mensaje de prueba"
                            elif param.default is not inspect.Parameter.empty:
                                kwargs[param_name] = param.default
                            else:
                                kwargs[param_name] = "test"

                        if inspect.iscoroutinefunction(cmd_fn):
                            await cmd_fn(cog_instance, interaction, **kwargs)
                        else:
                            cmd_fn(cog_instance, interaction, **kwargs)
                        print("[OK]")
                        passed += 1
                    except Exception as e:
                        print(f"[FAIL]: {e}")
                        errors.append((full_name, str(e)))

            # Check if it is a standalone slash command method
            elif inspect.iscoroutinefunction(attr) and hasattr(attr, "__cmd_name__"):
                cmd_name = getattr(attr, "__cmd_name__", attr_name)
                full_name = f"/{cmd_name}"
                total_tested += 1
                print(f"  Testing command {full_name} ...", end=" ")
                try:
                    interaction = MockInteraction(guild_id=guild_id, user_id=user_id)
                    sig = inspect.signature(attr)
                    kwargs = {}
                    for param_name, param in sig.parameters.items():
                        if param_name in ("self", "interaction"):
                            continue
                        if "item" in param_name or "objeto" in param_name:
                            kwargs[param_name] = "Teléfono Móvil"
                        elif "cantidad" in param_name or "amount" in param_name or "qty" in param_name or "precio" in param_name:
                            kwargs[param_name] = 1
                        elif "usuario" in param_name or "user" in param_name or "member" in param_name or "target" in param_name:
                            kwargs[param_name] = types.SimpleNamespace(id=target_id, name="TargetUser", mention=f"<@{target_id}>")
                        elif "canal" in param_name or "channel" in param_name:
                            kwargs[param_name] = types.SimpleNamespace(id=11111, mention="<#11111>", name="general")
                        elif "rol" in param_name or "role" in param_name:
                            kwargs[param_name] = types.SimpleNamespace(id=22222, mention="<@&22222>", name="Ciudadano")
                        elif "categoria" in param_name or "category" in param_name:
                            kwargs[param_name] = "electronica"
                        elif "tipo" in param_name or "type" in param_name:
                            kwargs[param_name] = "police"
                        elif "codigo" in param_name or "code" in param_name or "nombre" in param_name or "name" in param_name:
                            kwargs[param_name] = "test_code"
                        elif "motivo" in param_name or "reason" in param_name or "mensaje" in param_name or "descripcion" in param_name:
                            kwargs[param_name] = "Mensaje de prueba"
                        elif param.default is not inspect.Parameter.empty:
                            kwargs[param_name] = param.default
                        else:
                            kwargs[param_name] = "test"

                    await attr(interaction, **kwargs)
                    print("[OK]")
                    passed += 1
                except Exception as e:
                    print(f"[FAIL]: {e}")
                    errors.append((full_name, str(e)))

    print("\n" + "=" * 60)
    print(f"Summary: {passed}/{total_tested} commands executed successfully.")
    if errors:
        print(f"Found {len(errors)} command failures:")
        for name, err in errors:
            print(f"  - {name}: {err}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_all_tests())
