import discord

COLOR_SUCCESS = 0x57F287
COLOR_ERROR = 0xED4245
COLOR_WARNING = 0xFEE75C
# Miami Vice palette: neon cyan, hot pink, sunset gold, and midnight navy.
COLOR_INFO = 0x00E5FF
COLOR_ECONOMY = 0xFFD166
COLOR_DEPARTMENT = 0x00B8D4
COLOR_BLACKMARKET = 0x17152B
COLOR_CRIMINAL = 0xFF3D81
COLOR_DIRTY = 0xB5651D
COLOR_PRIMARY = 0xFF2D95

def success_embed(title, description=None):
    e = discord.Embed(title=f"✅ {title}", description=description, color=COLOR_SUCCESS)
    e.set_footer(text="Miami Vice RP • Ocean Drive")
    e.timestamp = discord.utils.utcnow()
    return e

def error_embed(title, description=None):
    e = discord.Embed(title=f"❌ {title}", description=description, color=COLOR_ERROR)
    e.set_footer(text="Miami Vice RP • Ocean Drive")
    e.timestamp = discord.utils.utcnow()
    return e

def warning_embed(title, description=None):
    e = discord.Embed(title=f"⚠️ {title}", description=description, color=COLOR_WARNING)
    e.set_footer(text="Miami Vice RP • Ocean Drive")
    e.timestamp = discord.utils.utcnow()
    return e

def info_embed(title, description=None):
    e = discord.Embed(title=title, description=description, color=COLOR_INFO)
    e.set_footer(text="Miami Vice RP • Ocean Drive")
    e.timestamp = discord.utils.utcnow()
    return e

def economy_embed(title, description=None):
    e = discord.Embed(title=title, description=description, color=COLOR_ECONOMY)
    e.set_footer(text="Miami Vice RP • Ocean Drive")
    e.timestamp = discord.utils.utcnow()
    return e

def department_embed(title, description=None):
    e = discord.Embed(title=title, description=description, color=COLOR_DEPARTMENT)
    e.set_footer(text="Miami Vice RP • Ocean Drive")
    e.timestamp = discord.utils.utcnow()
    return e

def blackmarket_embed(title, description=None):
    e = discord.Embed(title=title, description=description, color=COLOR_BLACKMARKET)
    e.set_footer(text="Miami Vice RP • Ocean Drive")
    e.timestamp = discord.utils.utcnow()
    return e

def criminal_embed(title, description=None):
    e = discord.Embed(title=title, description=description, color=COLOR_CRIMINAL)
    e.set_footer(text="Miami Vice RP • Ocean Drive")
    e.timestamp = discord.utils.utcnow()
    return e

def dirty_embed(title, description=None):
    e = discord.Embed(title=title, description=description, color=COLOR_DIRTY)
    e.set_footer(text="Miami Vice RP • Ocean Drive")
    e.timestamp = discord.utils.utcnow()
    return e
