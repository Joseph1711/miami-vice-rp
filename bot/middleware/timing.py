"""
Middleware para interceptar y medir tiempo de ejecución de comandos.
Detecta comandos lentos y los reporta en los logs.
"""
import discord
from discord import app_commands
from discord.ext import commands
import logging
import time
import functools

logger = logging.getLogger("bot")

# Umbral de tiempo en segundos para reportar como "lento"
SLOW_COMMAND_THRESHOLD = 2.0


def measure_command_time(func):
    """Decorator para medir tiempo de ejecución de comandos."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = await func(*args, **kwargs)
            elapsed = time.time() - start
            if elapsed > SLOW_COMMAND_THRESHOLD:
                logger.warning(f"⚠️ COMANDO LENTO: {func.__name__} tardó {elapsed:.2f}s")
            return result
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"❌ ERROR en {func.__name__} (tardó {elapsed:.2f}s): {e}")
            raise
    return wrapper
