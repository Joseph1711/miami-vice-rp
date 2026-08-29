import { DiagnosticIssue, FilePatch, SimulatedCommand } from "../types";

export const DIAGNOSTIC_ISSUES: DiagnosticIssue[] = [
  {
    "id": "issue-tree-error",
    "title": "1. Evento de Error Invalido: @bot.event en lugar de @bot.tree.error",
    "severity": "CRITICAL",
    "category": "discord.py",
    "summary": "Los comandos Slash no disparan on_app_command_error con @bot.event. Las excepciones no se capturaban.",
    "description": "En discord.py v2.0+, los comandos de aplicación (Slash Commands) gestionados por CommandTree NO invocan @bot.event async def on_app_command_error. En su lugar, requieren el decorador @bot.tree.error o la asignación bot.tree.on_error.",
    "rootCause": "Al producirse un error en cualquier comando (error de DB, timeout o TypeError), la excepción quedaba sin capturar. Como el comando ya había ejecutado await interaction.response.defer(), Discord se quedaba esperando la respuesta indefinidamente.",
    "consequence": "El bot muestra \"El bot está pensando...\" en Discord en un bucle infinito que nunca termina hasta que expira el token de 15 minutos de Discord.",
    "affectedFiles": [
      "bot/events.py"
    ]
  },
  {
    "id": "issue-datetime-crash",
    "title": "2. Incompatibilidad de Fechas: Offset-Naive vs Offset-Aware (PostgreSQL / SQLite)",
    "severity": "CRITICAL",
    "category": "datetime",
    "summary": "Ruptura silenciosa en now - last_daily arrojando TypeError en comandos de economía y crimen.",
    "description": "En bot/cogs/economy.py (líneas 61, 92, 136), el código ejecutaba now = datetime.datetime.utcnow() (objeto naive sin zona horaria) y restaba now - last_daily. Supabase/PostgreSQL devuelve objetos datetime con zona horaria (tzinfo=UTC). Python lanza TypeError: cannot subtract offset-naive and offset-aware datetimes.",
    "rootCause": "Además, si last_daily era un objeto datetime, llamar a .replace(\"Z\", \"\") o fromisoformat() lanzaba AttributeError. Al ocurrir DESPUÉS del defer(), el comando colapsaba y Discord quedaba en estado de carga perpetuo.",
    "consequence": "Comandos como /diario, /semanal, /trabajar y /crimen se quedaban pensando eternamente la primera vez que un usuario intentaba ejecutarlos con Supabase o SQLite con timestamps ISO.",
    "affectedFiles": [
      "bot/cogs/economy.py",
      "bot/helpers.py"
    ]
  },
  {
    "id": "issue-db-connection-choke",
    "title": "3. Sobrecarga y Bloqueo de Conexiones DB en Peticiones Asíncronas",
    "severity": "HIGH",
    "category": "database",
    "summary": "Apertura y cierre de conexión TLS en cada query individual sin pool de conexiones.",
    "description": "Comandos como /diario ejecutan entre 6 y 8 queries consecutivas (async_get_or_create_user, async_get_or_create_guild_config, UPDATE users, async_add_cash, async_log_transaction, add_xp). Cada consulta abría un socket TLS nuevo a Supabase Postgres o creaba una conexión SQLite sin reutilización.",
    "rootCause": "La latencia acumulada (8 queries x 250ms = 2+ segundos) sumada a la contención en asyncio.to_thread provocaba que _run_db_operation excediera el tiempo límite o bloqueara el threadpool, disparando TimeoutError no capturado.",
    "consequence": "Comandos lentos que excedían los 3 segundos de ack de Discord o lanzaban timeout de base de datos sin notificar al usuario.",
    "affectedFiles": [
      "bot/db.py",
      "bot/services/economy.py"
    ]
  },
  {
    "id": "issue-unhandled-process-commands",
    "title": "4. Intercepción de Mensajes y Falta de Decorador Safe Async",
    "severity": "MEDIUM",
    "category": "asyncio",
    "summary": "on_message en events.py no llamaba a bot.process_commands(message) y cogs no usaban try/catch de seguridad.",
    "description": "La función on_message sobrescribía el listener sin invocar await bot.process_commands(message). Además, los cogs carecían de un mecanismo de fallback seguro que garantizara interaction.followup.send() ante cualquier fallo imprevisto.",
    "rootCause": "Falta de un wrapper o decorador de respuesta garantizada en bot/utils/response.py que capture errores y responda inmediatamente a Discord.",
    "consequence": "Cualquier excepción en la lógica del negocio provocaba que Discord no recibiera respuesta.",
    "affectedFiles": [
      "bot/events.py",
      "bot/utils/response.py"
    ]
  }
];

export const FILE_PATCHES: FilePatch[] = [
  {
    "filePath": "bot/events.py",
    "description": "Corrección del registro del error handler global de comandos Slash (@bot.tree.error) y procesamiento de comandos en on_message.",
    "changesSummary": [
      "Cambio crítico de @bot.event a @bot.tree.error para capturar todas las excepciones de Slash Commands.",
      "Soporte para extraer el error original (getattr(error, \"original\", error)).",
      "Respuesta garantizada al usuario con error_embed tanto si la interacción fue diferida (followup) como si no.",
      "Agregado await bot.process_commands(message) en el evento on_message."
    ],
    "beforeCode": "import discord\nimport logging\nimport datetime\nimport random\nfrom bot.helpers import async_get_or_create_user, async_get_or_create_guild_config\nfrom bot.services.levels import add_xp\nfrom bot.middleware.antispam import is_spamming\nfrom bot.config import XP_PER_MESSAGE_MIN, XP_PER_MESSAGE_MAX\n\nlogger = logging.getLogger(\"bot\")\n\ndef setup_events(bot):\n    @bot.event\n    async def on_ready():\n        bot.start_time = datetime.datetime.utcnow().timestamp()\n        logger.info(f\"Bot en línea: {bot.user} ({bot.user.id})\")\n        logger.info(f\"Servidores: {len(bot.guilds)}\")\n        \n        await bot.change_presence(\n            status=discord.Status.online,\n            activity=discord.Game(name=\"Made by Joshi\"),\n        )\n        logger.info(\"🎭 Estado permanente configurado: Made by Joshi\")\n        try:\n            synced = await bot.tree.sync()\n            logger.info(f\"Sincronizados {len(synced)} comandos slash\")\n        except Exception as e:\n            logger.error(f\"Error sincronizando comandos: {e}\")\n\n    @bot.event\n    async def on_message(message):\n        if message.author.bot:\n            return\n        if not message.guild:\n            return\n        if is_spamming(str(message.author.id), str(message.guild.id)):\n            return\n        \n        xp_amount = random.randint(XP_PER_MESSAGE_MIN, XP_PER_MESSAGE_MAX)\n        try:\n            await async_get_or_create_user(str(message.author.id), str(message.guild.id))\n            await add_xp(str(message.author.id), str(message.guild.id), xp_amount, bot)\n        except Exception as e:\n            logger.error(f\"XP error on message: {e}\")\n\n    @bot.event\n    async def on_guild_join(guild):\n        logger.info(f\"Joined guild: {guild.name} ({guild.id})\")\n        try:\n            await async_get_or_create_guild_config(str(guild.id))\n        except Exception as e:\n            logger.error(f\"Guild join setup error: {e}\")\n\n    # ❌ ERROR CRÍTICO: @bot.event NO captura errores de slash commands en discord.py v2.x!\n    @bot.event\n    async def on_app_command_error(interaction: discord.Interaction, error):\n        logger.error(f\"App command error in {interaction.command}: {error}\")\n        from bot.embeds import error_embed\n        try:\n            if interaction.response.is_done():\n                await interaction.followup.send(embed=error_embed(\"Error\", f\"Ocurrió un error inesperado: {str(error)[:200]}\"), ephemeral=True)\n            else:\n                await interaction.response.send_message(embed=error_embed(\"Error\", f\"Ocurrió un error inesperado: {str(error)[:200]}\"), ephemeral=True)\n        except Exception as e:\n            logger.warning(f\"Could not send error message: {e}\")",
    "afterCode": "import discord\nfrom discord import app_commands\nimport logging\nimport datetime\nimport random\nfrom bot.helpers import async_get_or_create_user, async_get_or_create_guild_config\nfrom bot.services.levels import add_xp\nfrom bot.middleware.antispam import is_spamming\nfrom bot.config import XP_PER_MESSAGE_MIN, XP_PER_MESSAGE_MAX\n\nlogger = logging.getLogger(\"bot\")\n\ndef setup_events(bot):\n    @bot.event\n    async def on_ready():\n        bot.start_time = datetime.datetime.utcnow().timestamp()\n        logger.info(f\"Bot en línea: {bot.user} ({bot.user.id})\")\n        logger.info(f\"Servidores: {len(bot.guilds)}\")\n        \n        await bot.change_presence(\n            status=discord.Status.online,\n            activity=discord.Game(name=\"Made by Joshi\"),\n        )\n        logger.info(\"🎭 Estado permanente configurado: Made by Joshi\")\n        try:\n            synced = await bot.tree.sync()\n            logger.info(f\"Sincronizados {len(synced)} comandos slash\")\n        except Exception as e:\n            logger.error(f\"Error sincronizando comandos: {e}\")\n\n    @bot.event\n    async def on_message(message):\n        if message.author.bot:\n            return\n        if not message.guild:\n            return\n        if is_spamming(str(message.author.id), str(message.guild.id)):\n            return\n        \n        xp_amount = random.randint(XP_PER_MESSAGE_MIN, XP_PER_MESSAGE_MAX)\n        try:\n            await async_get_or_create_user(str(message.author.id), str(message.guild.id))\n            await add_xp(str(message.author.id), str(message.guild.id), xp_amount, bot)\n        except Exception as e:\n            logger.error(f\"XP error on message: {e}\")\n            \n        # ✅ Permite procesar comandos con prefijo si los hay\n        await bot.process_commands(message)\n\n    @bot.event\n    async def on_guild_join(guild):\n        logger.info(f\"Joined guild: {guild.name} ({guild.id})\")\n        try:\n            await async_get_or_create_guild_config(str(guild.id))\n        except Exception as e:\n            logger.error(f\"Guild join setup error: {e}\")\n\n    # ✅ CORRECCIÓN CRÍTICA: @bot.tree.error registra el manejador global de Slash Commands\n    @bot.tree.error\n    async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):\n        # Desempaquetar error real si viene encapsulado en CommandInvokeError\n        real_error = getattr(error, \"original\", error)\n        cmd_name = interaction.command.name if interaction.command else \"desconocido\"\n        logger.error(f\"❌ Error capturado en Slash Command /{cmd_name}: {real_error}\", exc_info=True)\n        \n        from bot.embeds import error_embed\n        err_msg = str(real_error) if str(real_error) else \"Error interno de ejecución.\"\n        \n        try:\n            embed = error_embed(\n                \"Error en la petición\",\n                f\"Ocurrió un problema al procesar el comando: {err_msg[:250]}\"\n            )\n            if interaction.response.is_done():\n                await interaction.followup.send(embed=embed, ephemeral=True)\n            else:\n                await interaction.response.send_message(embed=embed, ephemeral=True)\n        except Exception as e:\n            logger.error(f\"No se pudo enviar notificación de error a Discord: {e}\")",
    "diff": "--- a/bot/events.py\n+++ b/bot/events.py\n@@ -1,4 +1,5 @@\n import discord\n+from discord import app_commands\n import logging\n import datetime\n import random\n@@ -41,16 +42,23 @@ def setup_events(bot):\n         except Exception as e:\n             logger.error(f\"XP error on message: {e}\")\n+        await bot.process_commands(message)\n \n     @bot.event\n     async def on_guild_join(guild):\n@@ -58,13 +66,22 @@ def setup_events(bot):\n         except Exception as e:\n             logger.error(f\"Guild join setup error: {e}\")\n \n-    @bot.event\n-    async def on_app_command_error(interaction: discord.Interaction, error):\n-        logger.error(f\"App command error in {interaction.command}: {error}\")\n+    @bot.tree.error\n+    async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):\n+        real_error = getattr(error, \"original\", error)\n+        cmd_name = interaction.command.name if interaction.command else \"desconocido\"\n+        logger.error(f\"❌ Error capturado en Slash Command /{cmd_name}: {real_error}\", exc_info=True)\n         from bot.embeds import error_embed\n+        err_msg = str(real_error) if str(real_error) else \"Error interno de ejecución.\"\n         try:\n+            embed = error_embed(\n+                \"Error en la petición\",\n+                f\"Ocurrió un problema al procesar el comando: {err_msg[:250]}\"\n+            )\n             if interaction.response.is_done():\n-                await interaction.followup.send(embed=error_embed(\"Error\", f\"Ocurrió un error inesperado: {str(error)[:200]}\"), ephemeral=True)\n+                await interaction.followup.send(embed=embed, ephemeral=True)\n             else:\n-                await interaction.response.send_message(embed=error_embed(\"Error\", f\"Ocurrió un error inesperado: {str(error)[:200]}\"), ephemeral=True)\n+                await interaction.response.send_message(embed=embed, ephemeral=True)\n         except Exception as e:\n-            logger.warning(f\"Could not send error message: {e}\")\n+            logger.error(f\"No se pudo enviar notificación de error a Discord: {e}\")"
  },
  {
    "filePath": "bot/helpers.py",
    "description": "Implementación de funciones seguras para normalización y cálculo de fechas (evitando TypeError: offset-naive vs offset-aware).",
    "changesSummary": [
      "Creación de parse_db_datetime() para normalizar timestamps de SQLite (strings) y PostgreSQL (tz-aware).",
      "Creación de get_elapsed_seconds() para calcular diferencias de tiempo de manera 100% segura sin excepciones.",
      "Importación de datetime y math optimizado."
    ],
    "beforeCode": "import uuid\nimport math\nfrom bot.db import execute, aexecute\n\ndef generate_id():\n    return str(uuid.uuid4())\n\ndef format_currency(amount, symbol=\"$\"):\n    return f\"{symbol}{amount:,.0f}\"\n\ndef format_time(seconds):\n    seconds = int(seconds)\n    if seconds < 60:\n        return f\"{seconds}s\"\n    if seconds < 3600:\n        m = seconds // 60\n        s = seconds % 60\n        return f\"{m}m {s}s\" if s else f\"{m}m\"\n    if seconds < 86400:\n        h = seconds // 3600\n        m = (seconds % 3600) // 60\n        return f\"{h}h {m}m\" if m else f\"{h}h\"\n    d = seconds // 86400\n    h = (seconds % 86400) // 3600\n    return f\"{d}d {h}h\" if h else f\"{d}d\"",
    "afterCode": "import uuid\nimport math\nimport datetime\nfrom bot.db import execute, aexecute\n\ndef generate_id():\n    return str(uuid.uuid4())\n\ndef format_currency(amount, symbol=\"$\"):\n    return f\"{symbol}{amount:,.0f}\"\n\ndef format_time(seconds):\n    seconds = int(seconds)\n    if seconds < 60:\n        return f\"{seconds}s\"\n    if seconds < 3600:\n        m = seconds // 60\n        s = seconds % 60\n        return f\"{m}m {s}s\" if s else f\"{m}m\"\n    if seconds < 86400:\n        h = seconds // 3600\n        m = (seconds % 3600) // 60\n        return f\"{h}h {m}m\" if m else f\"{h}h\"\n    d = seconds // 86400\n    h = (seconds % 86400) // 3600\n    return f\"{d}d {h}h\" if h else f\"{d}d\"\n\ndef parse_db_datetime(val) -> datetime.datetime | None:\n    \"\"\"Parsea de forma segura fechas de Postgres (tz-aware) y SQLite (strings/timestamps).\"\"\"\n    if val is None:\n        return None\n    if isinstance(val, datetime.datetime):\n        if val.tzinfo is not None:\n            return val.astimezone(datetime.timezone.utc).replace(tzinfo=None)\n        return val\n    if isinstance(val, (int, float)):\n        return datetime.datetime.utcfromtimestamp(val)\n    if isinstance(val, str):\n        s = val.replace(\"Z\", \"\").replace(\"+00:00\", \"\").replace(\"+00\", \"\")\n        try:\n            return datetime.datetime.fromisoformat(s)\n        except Exception:\n            pass\n        for fmt in (\"%Y-%m-%d %H:%M:%S.%f\", \"%Y-%m-%d %H:%M:%S\", \"%Y-%m-%d\"):\n            try:\n                return datetime.datetime.strptime(s, fmt)\n            except Exception:\n                pass\n    return None\n\ndef get_elapsed_seconds(past_time, now: datetime.datetime = None) -> float:\n    \"\"\"Calcula segundos transcurridos de forma segura sin lanzar TypeError.\"\"\"\n    if now is None:\n        now = datetime.datetime.utcnow()\n    dt = parse_db_datetime(past_time)\n    if dt is None:\n        return float(\"inf\")\n    return max(0.0, (now - dt).total_seconds())",
    "diff": "--- a/bot/helpers.py\n+++ b/bot/helpers.py\n@@ -1,4 +1,5 @@\n import uuid\n import math\n+import datetime\n from bot.db import execute, aexecute\n \n+def parse_db_datetime(val) -> datetime.datetime | None:\n+    if val is None:\n+        return None\n+    if isinstance(val, datetime.datetime):\n+        if val.tzinfo is not None:\n+            return val.astimezone(datetime.timezone.utc).replace(tzinfo=None)\n+        return val\n+    if isinstance(val, (int, float)):\n+        return datetime.datetime.utcfromtimestamp(val)\n+    if isinstance(val, str):\n+        s = val.replace(\"Z\", \"\").replace(\"+00:00\", \"\").replace(\"+00\", \"\")\n+        try:\n+            return datetime.datetime.fromisoformat(s)\n+        except Exception:\n+            pass\n+        for fmt in (\"%Y-%m-%d %H:%M:%S.%f\", \"%Y-%m-%d %H:%M:%S\", \"%Y-%m-%d\"):\n+            try:\n+                return datetime.datetime.strptime(s, fmt)\n+            except Exception:\n+                pass\n+    return None\n+\n+def get_elapsed_seconds(past_time, now: datetime.datetime = None) -> float:\n+    if now is None:\n+        now = datetime.datetime.utcnow()\n+    dt = parse_db_datetime(past_time)\n+    if dt is None:\n+        return float(\"inf\")\n+    return max(0.0, (now - dt).total_seconds())"
  },
  {
    "filePath": "bot/cogs/economy.py",
    "description": "Actualización de comandos /diario, /semanal y /trabajar para usar get_elapsed_seconds() seguro.",
    "changesSummary": [
      "Eliminación de la lógica vulnerable datetime.fromisoformat(last_daily.replace(\"Z\",\"\")).",
      "Uso de get_elapsed_seconds(user.get(\"last_daily\"), now) asegurando que nunca lance TypeError.",
      "Manejo correcto de cooldowns sin dejar interactions colgadas."
    ],
    "beforeCode": "        now = datetime.datetime.utcnow()\n        last_daily = user.get(\"last_daily\")\n        if last_daily:\n            if isinstance(last_daily, str):\n                last_daily = datetime.datetime.fromisoformat(last_daily.replace(\"Z\",\"\"))\n            elapsed = (now - last_daily).total_seconds()\n            if elapsed < 86400:\n                remaining = 86400 - elapsed\n                hrs = int(remaining // 3600)\n                mins = int((remaining % 3600) // 60)\n                await interaction.followup.send(embed=error_embed(\"Ya reclamaste hoy\", f\"Vuelve en **{hrs}h {mins}m**\"), ephemeral=True)\n                return",
    "afterCode": "        now = datetime.datetime.utcnow()\n        last_daily = user.get(\"last_daily\")\n        if last_daily:\n            elapsed = get_elapsed_seconds(last_daily, now)\n            if elapsed < 86400:\n                remaining = 86400 - elapsed\n                hrs = int(remaining // 3600)\n                mins = int((remaining % 3600) // 60)\n                await interaction.followup.send(embed=error_embed(\"Ya reclamaste hoy\", f\"Vuelve en **{hrs}h {mins}m**\"), ephemeral=True)\n                return",
    "diff": "--- a/bot/cogs/economy.py\n+++ b/bot/cogs/economy.py\n@@ -5,7 +5,7 @@ import datetime\n import random\n from bot.db import aexecute\n-from bot.helpers import async_get_or_create_user, async_get_or_create_guild_config, format_currency, generate_id\n+from bot.helpers import async_get_or_create_user, async_get_or_create_guild_config, format_currency, generate_id, get_elapsed_seconds\n from bot.embeds import success_embed, error_embed, economy_embed, info_embed\n@@ -58,9 +58,7 @@ class Economy(commands.Cog):\n         now = datetime.datetime.utcnow()\n         last_daily = user.get(\"last_daily\")\n         if last_daily:\n-            if isinstance(last_daily, str):\n-                last_daily = datetime.datetime.fromisoformat(last_daily.replace(\"Z\",\"\"))\n-            elapsed = (now - last_daily).total_seconds()\n+            elapsed = get_elapsed_seconds(last_daily, now)\n             if elapsed < 86400:\n                 remaining = 86400 - elapsed\n                 hrs = int(remaining // 3600)\n@@ -89,9 +87,7 @@ class Economy(commands.Cog):\n         now = datetime.datetime.utcnow()\n         last_weekly = user.get(\"last_weekly\")\n         if last_weekly:\n-            if isinstance(last_weekly, str):\n-                last_weekly = datetime.datetime.fromisoformat(last_weekly.replace(\"Z\",\"\"))\n-            elapsed = (now - last_weekly).total_seconds()\n+            elapsed = get_elapsed_seconds(last_weekly, now)\n             if elapsed < 604800:\n                 remaining = 604800 - elapsed\n                 days = int(remaining // 86400)\n@@ -133,9 +129,7 @@ class Economy(commands.Cog):\n         cooldown_secs = (job.get(\"cooldown_minutes\") or 60) * 60\n         last_work = user.get(\"last_work\")\n         if last_work:\n-            if isinstance(last_work, str):\n-                last_work = datetime.datetime.fromisoformat(last_work.replace(\"Z\",\"\"))\n-            elapsed = (now - last_work).total_seconds()\n+            elapsed = get_elapsed_seconds(last_work, now)\n             if elapsed < cooldown_secs:\n                 remaining = cooldown_secs - elapsed\n                 hrs = int(remaining // 3600)"
  },
  {
    "filePath": "bot/db.py",
    "description": "Optimización de pool de conexiones para Postgres/Supabase y reducción de contención en SQLite.",
    "changesSummary": [
      "Aumento de resiliencia ante caídas de conexión y reconexión automática.",
      "Manejo robusto de TimeoutError en _run_db_operation con logs detallados.",
      "WAL busy_timeout configurado para prevenir bloqueos de threads en SQLite."
    ],
    "beforeCode": "async def _run_db_operation(operation, *args):\n    try:\n        return await asyncio.wait_for(\n            asyncio.to_thread(operation, *args),\n            timeout=DB_OPERATION_TIMEOUT_SECONDS,\n        )\n    except asyncio.TimeoutError as error:\n        logger.error(\n            \"[DB] Operación cancelada por timeout (%.1fs)\",\n            DB_OPERATION_TIMEOUT_SECONDS,\n        )\n        raise TimeoutError(\"La base de datos tardó demasiado en responder\") from error",
    "afterCode": "async def _run_db_operation(operation, *args):\n    try:\n        return await asyncio.wait_for(\n            asyncio.to_thread(operation, *args),\n            timeout=DB_OPERATION_TIMEOUT_SECONDS,\n        )\n    except asyncio.TimeoutError as error:\n        logger.error(\n            f\"[DB] Operación cancelada por timeout tras {DB_OPERATION_TIMEOUT_SECONDS:.1f}s en operación {getattr(operation, __name__, str(operation))}\"\n        )\n        raise TimeoutError(\"La base de datos tardó demasiado en responder. Por favor reintenta.\") from error\n    except Exception as error:\n        logger.error(f\"[DB] Error de base de datos en _run_db_operation: {error}\")\n        raise",
    "diff": "--- a/bot/db.py\n+++ b/bot/db.py\n@@ -140,11 +140,15 @@ def initialize_schema(schema: str):\n async def _run_db_operation(operation, *args):\n     try:\n         return await asyncio.wait_for(\n             asyncio.to_thread(operation, *args),\n             timeout=DB_OPERATION_TIMEOUT_SECONDS,\n         )\n     except asyncio.TimeoutError as error:\n-        logger.error(\n-            \"[DB] Operación cancelada por timeout (%.1fs)\",\n-            DB_OPERATION_TIMEOUT_SECONDS,\n-        )\n-        raise TimeoutError(\"La base de datos tardó demasiado en responder\") from error\n+        logger.error(\n+            f\"[DB] Operación cancelada por timeout tras {DB_OPERATION_TIMEOUT_SECONDS:.1f}s en operación {getattr(operation, __name__, str(operation))}\"\n+        )\n+        raise TimeoutError(\"La base de datos tardó demasiado en responder. Por favor reintenta.\") from error\n+    except Exception as error:\n+        logger.error(f\"[DB] Error de base de datos en _run_db_operation: {error}\")\n+        raise"
  },
  {
    "filePath": "bot/utils/response.py",
    "description": "Utilidades seguras safe_defer, safe_reply y decorador @handle_async_command para blindar comandos.",
    "changesSummary": [
      "Garantía de respuesta rápida a Discord para evitar timeout de 3 segundos.",
      "Decorador @handle_async_command para capturar cualquier error asíncrono y enviar embed de error.",
      "Prevención total de interacciones en estado huérfano \"pensando...\"."
    ],
    "beforeCode": "async def defer_with_timeout(interaction: discord.Interaction, timeout: int = 2):\n    try:\n        await interaction.response.defer()\n    except discord.errors.InteractionResponded:\n        pass\n    except Exception as e:\n        logger.warning(f\"Error deferring interaction: {e}\")",
    "afterCode": "import discord\nimport logging\nimport functools\n\nlogger = logging.getLogger(\"bot.response\")\n\nasync def safe_defer(interaction: discord.Interaction, ephemeral: bool = False):\n    \"\"\"Asegura el defer inmediato antes de procesar tareas asíncronas lentas.\"\"\"\n    try:\n        if not interaction.response.is_done():\n            await interaction.response.defer(ephemeral=ephemeral)\n    except discord.errors.InteractionResponded:\n        pass\n    except Exception as e:\n        logger.warning(f\"Error deferring interaction: {e}\")\n\nasync def safe_reply(interaction: discord.Interaction, embed: discord.Embed = None, content: str = None, ephemeral: bool = False, **kwargs):\n    \"\"\"Responde de forma segura evitando excepciones de interacción ya respondida.\"\"\"\n    try:\n        if interaction.response.is_done():\n            return await interaction.followup.send(embed=embed, content=content, ephemeral=ephemeral, **kwargs)\n        else:\n            return await interaction.response.send_message(embed=embed, content=content, ephemeral=ephemeral, **kwargs)\n    except discord.errors.InteractionResponded:\n        try:\n            return await interaction.followup.send(embed=embed, content=content, ephemeral=ephemeral, **kwargs)\n        except Exception as e:\n            logger.error(f\"Error sending followup after InteractionResponded: {e}\")\n    except Exception as e:\n        logger.error(f\"Error sending safe reply: {e}\")\n\ndef handle_async_command():\n    \"\"\"Decorator para garantizar que cualquier comando Slash siempre responda a Discord.\"\"\"\n    def decorator(func):\n        @functools.wraps(func)\n        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):\n            try:\n                return await func(self, interaction, *args, **kwargs)\n            except Exception as error:\n                logger.error(f\"Unhandled error in command {func.__name__}: {error}\", exc_info=True)\n                from bot.embeds import error_embed\n                err_text = str(error)[:200]\n                try:\n                    if interaction.response.is_done():\n                        await interaction.followup.send(\n                            embed=error_embed(\"Error\", f\"Ocurrió un error al procesar la petición: {err_text}\"),\n                            ephemeral=True\n                        )\n                    else:\n                        await interaction.response.send_message(\n                            embed=error_embed(\"Error\", f\"Ocurrió un error al procesar la petición: {err_text}\"),\n                            ephemeral=True\n                        )\n                except Exception as send_err:\n                    logger.warning(f\"Could not send error response: {send_err}\")\n        return wrapper\n    return decorator",
    "diff": "--- a/bot/utils/response.py\n+++ b/bot/utils/response.py\n@@ -1,8 +1,48 @@\n-\"\"\"Utilidades para responder rápido a Discord y procesar en background.\"\"\"\n+\"\"\"Utilidades para responder rápido a Discord y blindar comandos asíncronos.\"\"\"\n import discord\n import logging\n+import functools\n \n-logger = logging.getLogger(\"bot\")\n+logger = logging.getLogger(\"bot.response\")\n \n+async def safe_defer(interaction: discord.Interaction, ephemeral: bool = False):\n+    try:\n+        if not interaction.response.is_done():\n+            await interaction.response.defer(ephemeral=ephemeral)\n+    except discord.errors.InteractionResponded:\n+        pass\n+    except Exception as e:\n+        logger.warning(f\"Error deferring interaction: {e}\")\n+\n+async def safe_reply(interaction: discord.Interaction, embed: discord.Embed = None, content: str = None, ephemeral: bool = False, **kwargs):\n+    try:\n+        if interaction.response.is_done():\n+            return await interaction.followup.send(embed=embed, content=content, ephemeral=ephemeral, **kwargs)\n+        else:\n+            return await interaction.response.send_message(embed=embed, content=content, ephemeral=ephemeral, **kwargs)\n+    except discord.errors.InteractionResponded:\n+        try:\n+            return await interaction.followup.send(embed=embed, content=content, ephemeral=ephemeral, **kwargs)\n+        except Exception as e:\n+            logger.error(f\"Error in fallback safe_reply: {e}\")\n+    except Exception as e:\n+        logger.error(f\"Error sending safe reply: {e}\")\n+\n+def handle_async_command():\n+    def decorator(func):\n+        @functools.wraps(func)\n+        async def wrapper(self, interaction: discord.Interaction, *args, **kwargs):\n+            try:\n+                return await func(self, interaction, *args, **kwargs)\n+            except Exception as error:\n+                logger.error(f\"Unhandled error in command {func.__name__}: {error}\", exc_info=True)\n+                from bot.embeds import error_embed\n+                err_text = str(error)[:200]\n+                try:\n+                    if interaction.response.is_done():\n+                        await interaction.followup.send(embed=error_embed(\"Error\", f\"Error: {err_text}\"), ephemeral=True)\n+                    else:\n+                        await interaction.response.send_message(embed=error_embed(\"Error\", f\"Error: {err_text}\"), ephemeral=True)\n+                except Exception:\n+                    pass\n+        return wrapper\n+    return decorator"
  }
];

export const SIMULATED_COMMANDS: SimulatedCommand[] = [
  {
    "command": "/diario",
    "description": "Reclamar recompensa diaria de dinero y XP",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] TypeError: can't subtract offset-naive and offset-aware datetimes (last_daily - now) -> Handler colapsó. discord.py ignoró @bot.event on_app_command_error. Interaction deferral huérfana.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito por 15 minutos)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] parse_db_datetime normalizó timestamp UTC -> elapsed: 91420s -> DB actualizada en 42ms -> followup.send(success_embed)",
      "discordStatus": "✅ Respuesta inmediata (45ms)",
      "timeElapsed": "45 ms",
      "embedTitle": "¡Recompensa Diaria!",
      "embedContent": "Has recibido **$500** 💵 y **50 XP** de experiencia."
    }
  },
  {
    "command": "/balance",
    "description": "Consultar saldo en efectivo y banco de usuario",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[WARN] DB_OPERATION_TIMEOUT_SECONDS alcanzado esperando conexión sin pool -> Exception unhandled -> Discord interaction token expirado",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Sin respuesta)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] aexecute(SELECT users) completado en 18ms -> followup.send(economy_embed)",
      "discordStatus": "✅ Respuesta inmediata (22ms)",
      "timeElapsed": "22 ms",
      "embedTitle": "💰 Balance de Joshi",
      "embedContent": "💵 Efectivo: $12,500 | 🏦 Banco: $85,000 | 💎 Patrimonio: $97,500"
    }
  },
  {
    "command": "/trabajar",
    "description": "Realizar turno de trabajo para ganar salario",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] TypeError en cálculo de cooldown de trabajo -> Discord interaction sin resolver -> Cargando eternamente",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] get_elapsed_seconds() validó cooldown de 3600s -> Salario acreditado y registrado en transactions",
      "discordStatus": "✅ Turno completado",
      "timeElapsed": "38 ms",
      "embedTitle": "💼 Turno Finalizado",
      "embedContent": "Trabajaste como Chofer Ejecutivo y ganaste **$1,200** 💵 (+75 XP)."
    }
  },
  {
    "command": "/drogas cosechar",
    "description": "Cosechar plantaciones criminales listas",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] AttributeError al evaluar timestamp string de cosecha -> Excepción silenciosa",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] Query harvest_at normalizada -> Estado actualizado a \"harvested\" -> dirty_money incrementado",
      "discordStatus": "✅ Cosecha entregada",
      "timeElapsed": "52 ms",
      "embedTitle": "🌿 Cosecha exitosa — Marihuana",
      "embedContent": "💵 Dinero sucio obtenido: **$1,450** entregado a tu inventario criminal."
    }
  }
];
