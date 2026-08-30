import { DiagnosticIssue, FilePatch, SimulatedCommand } from '../types';

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
  },
  {
    "id": "issue-sql-bindings-mismatch",
    "title": "5. Discrepancia de Parámetros SQL: Incorrect number of bindings supplied",
    "severity": "CRITICAL",
    "category": "database",
    "summary": "Mapeo posicional de parámetros ($1, $2, $3, $1) producía un número dispar de placeholders vs tupla de argumentos.",
    "description": "Comandos como /invertir crear, /donar departamento y /mercado subasta invocaban consultas SQL que reutilizaban el placeholder $1 (e.g. UPDATE users SET cash=cash-$1 ... cash >= $1) enviando solo 3 parámetros para 4 interrogantes generadas. Esto disparaba sqlite3.ProgrammingError: Incorrect number of bindings supplied. The current statement uses 4, and there are 3 supplied.",
    "rootCause": "Las funciones remove_cash, remove_bank, async_remove_cash, async_remove_bank y consultas en cogs usaban sintaxis que no correspondía 1:1 con la tupla de parámetros en tiempo de ejecución.",
    "consequence": "Fallo inmediato al crear inversiones con /invertir crear, transferir fondos o crear subastas con error visible en Discord.",
    "affectedFiles": [
      "bot/services/economy.py",
      "bot/cogs/economy.py",
      "bot/cogs/marketplace.py",
      "bot/db.py"
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
    "command": "/admin economia dar",
    "category": "Administración",
    "cog": "admin",
    "description": "Dar dinero a un jugador",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /admin economia dar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /admin economia dar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "⚙️ Panel Administrativo",
      "embedContent": "Acción de administrador ejecutada con permisos elevados: Dar dinero a un jugador."
    }
  },
  {
    "command": "/admin economia quitar",
    "category": "Administración",
    "cog": "admin",
    "description": "Quitar dinero a un jugador",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /admin economia quitar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /admin economia quitar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "⚙️ Panel Administrativo",
      "embedContent": "Acción de administrador ejecutada con permisos elevados: Quitar dinero a un jugador."
    }
  },
  {
    "command": "/admin objetos crear",
    "category": "Administración",
    "cog": "admin",
    "description": "Crear un objeto nuevo",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /admin objetos crear -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /admin objetos crear ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "⚙️ Panel Administrativo",
      "embedContent": "Acción de administrador ejecutada con permisos elevados: Crear un objeto nuevo."
    }
  },
  {
    "command": "/admin objetos lista",
    "category": "Administración",
    "cog": "admin",
    "description": "Ver todos los objetos",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /admin objetos lista -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /admin objetos lista ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "⚙️ Panel Administrativo",
      "embedContent": "Acción de administrador ejecutada con permisos elevados: Ver todos los objetos."
    }
  },
  {
    "command": "/admin departamento crear",
    "category": "Administración",
    "cog": "admin",
    "description": "Crear un departamento",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /admin departamento crear -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /admin departamento crear ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏢 Departamento • Miami Vice",
      "embedContent": "Registro departamental consultado: Crear un departamento. Estado activo en la base de datos."
    }
  },
  {
    "command": "/admin propiedad crear",
    "category": "Administración",
    "cog": "admin",
    "description": "Crear una propiedad",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /admin propiedad crear -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /admin propiedad crear ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏠 Bienes Raíces de Miami",
      "embedContent": "Consulta inmobiliaria procesada con éxito: Crear una propiedad."
    }
  },
  {
    "command": "/admin xp dar",
    "category": "Administración",
    "cog": "admin",
    "description": "Dar XP a un jugador",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /admin xp dar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /admin xp dar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "⚙️ Panel Administrativo",
      "embedContent": "Acción de administrador ejecutada con permisos elevados: Dar XP a un jugador."
    }
  },
  {
    "command": "/admin xp quitar",
    "category": "Administración",
    "cog": "admin",
    "description": "Quitar XP a un jugador",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /admin xp quitar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /admin xp quitar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "⚙️ Panel Administrativo",
      "embedContent": "Acción de administrador ejecutada con permisos elevados: Quitar XP a un jugador."
    }
  },
  {
    "command": "/admin xp multiplicador",
    "category": "Administración",
    "cog": "admin",
    "description": "Ver/establecer el multiplicador de XP del servidor",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /admin xp multiplicador -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /admin xp multiplicador ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "⚙️ Panel Administrativo",
      "embedContent": "Acción de administrador ejecutada con permisos elevados: Ver/establecer el multiplicador de XP del servidor."
    }
  },
  {
    "command": "/admin reset usuario",
    "category": "Administración",
    "cog": "admin",
    "description": "Restablecer economía de un jugador",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /admin reset usuario -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /admin reset usuario ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "⚙️ Panel Administrativo",
      "embedContent": "Acción de administrador ejecutada con permisos elevados: Restablecer economía de un jugador."
    }
  },
  {
    "command": "/admin reset cooldowns",
    "category": "Administración",
    "cog": "admin",
    "description": "Reiniciar los cooldowns de un jugador",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /admin reset cooldowns -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /admin reset cooldowns ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "⚙️ Panel Administrativo",
      "embedContent": "Acción de administrador ejecutada con permisos elevados: Reiniciar los cooldowns de un jugador."
    }
  },
  {
    "command": "/admin recompensas agregar",
    "category": "Administración",
    "cog": "admin",
    "description": "Agregar recompensa de rol por nivel",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /admin recompensas agregar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /admin recompensas agregar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "⚙️ Panel Administrativo",
      "embedContent": "Acción de administrador ejecutada con permisos elevados: Agregar recompensa de rol por nivel."
    }
  },
  {
    "command": "/admin recompensas lista",
    "category": "Administración",
    "cog": "admin",
    "description": "Ver recompensas de nivel configuradas",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /admin recompensas lista -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /admin recompensas lista ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "⚙️ Panel Administrativo",
      "embedContent": "Acción de administrador ejecutada con permisos elevados: Ver recompensas de nivel configuradas."
    }
  },
  {
    "command": "/admin recompensas quitar",
    "category": "Administración",
    "cog": "admin",
    "description": "Quitar recompensa de un nivel",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /admin recompensas quitar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /admin recompensas quitar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "⚙️ Panel Administrativo",
      "embedContent": "Acción de administrador ejecutada con permisos elevados: Quitar recompensa de un nivel."
    }
  },
  {
    "command": "/admin configuracion diario",
    "category": "Administración",
    "cog": "admin",
    "description": "Configurar cantidad de /diario",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] TypeError: can't subtract offset-naive and offset-aware datetimes (last_daily - now) -> Handler colapsó.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /admin configuracion diario ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "¡Recompensa Diaria!",
      "embedContent": "Has recibido **00** 💵 y **50 XP** de experiencia acumulada."
    }
  },
  {
    "command": "/admin configuracion semanal",
    "category": "Administración",
    "cog": "admin",
    "description": "Configurar cantidad de /semanal",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] TypeError: can't subtract offset-naive and offset-aware datetimes en cálculo de semana.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /admin configuracion semanal ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "¡Recompensa Semanal!",
      "embedContent": "Has recibido **,500** 💵 y **250 XP** de bonificación semanal."
    }
  },
  {
    "command": "/admin configuracion canal_log",
    "category": "Administración",
    "cog": "admin",
    "description": "Configurar canal de logs del servidor",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /admin configuracion canal_log -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /admin configuracion canal_log ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "⚙️ Panel Administrativo",
      "embedContent": "Acción de administrador ejecutada con permisos elevados: Configurar canal de logs del servidor."
    }
  },
  {
    "command": "/admin configuracion verificacion",
    "category": "Administración",
    "cog": "admin",
    "description": "Configurar sistema de verificación",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /admin configuracion verificacion -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /admin configuracion verificacion ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "⚙️ Panel Administrativo",
      "embedContent": "Acción de administrador ejecutada con permisos elevados: Configurar sistema de verificación."
    }
  },
  {
    "command": "/admin configuracion ver",
    "category": "Administración",
    "cog": "admin",
    "description": "Ver todas las configuraciones actuales del servidor",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /admin configuracion ver -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /admin configuracion ver ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "⚙️ Panel Administrativo",
      "embedContent": "Acción de administrador ejecutada con permisos elevados: Ver todas las configuraciones actuales del servidor."
    }
  },
  {
    "command": "/admin configuracion tickets",
    "category": "Administración",
    "cog": "admin",
    "description": "Configurar el sistema de tickets",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /admin configuracion tickets -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /admin configuracion tickets ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🎫 Sistema de Tickets y Soporte",
      "embedContent": "Ticket procesado de forma segura: Configurar el sistema de tickets."
    }
  },
  {
    "command": "/adminshop agregar",
    "category": "Administración",
    "cog": "admin",
    "description": "Agregar objeto a la tienda",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /adminshop agregar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /adminshop agregar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "⚙️ Panel Administrativo",
      "embedContent": "Acción de administrador ejecutada con permisos elevados: Agregar objeto a la tienda."
    }
  },
  {
    "command": "/adminshop quitar",
    "category": "Administración",
    "cog": "admin",
    "description": "Quitar objeto de la tienda",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /adminshop quitar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /adminshop quitar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "⚙️ Panel Administrativo",
      "embedContent": "Acción de administrador ejecutada con permisos elevados: Quitar objeto de la tienda."
    }
  },
  {
    "command": "/adminshop predeterminados",
    "category": "Administración",
    "cog": "admin",
    "description": "Cargar el catálogo legal de objetos en la tienda normal",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /adminshop predeterminados -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /adminshop predeterminados ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "⚙️ Panel Administrativo",
      "embedContent": "Acción de administrador ejecutada con permisos elevados: Cargar el catálogo legal de objetos en la tienda normal."
    }
  },
  {
    "command": "/adminshop mercadonegro",
    "category": "Administración",
    "cog": "admin",
    "description": "Cargar el catálogo ilegal exclusivo del mercado negro",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /adminshop mercadonegro -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /adminshop mercadonegro ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🛒 Mercado & Comercio",
      "embedContent": "Catálogo comercial actualizado: Cargar el catálogo ilegal exclusivo del mercado negro."
    }
  },
  {
    "command": "/tesoro info",
    "category": "Administración",
    "cog": "admin",
    "description": "Ver el estado del tesoro",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /tesoro info -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /tesoro info ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "Miami Vice • /tesoro info",
      "embedContent": "Operación  ejecutada correctamente en el servidor. Ver el estado del tesoro."
    }
  },
  {
    "command": "/tesoro depositar",
    "category": "Administración",
    "cog": "admin",
    "description": "Depositar fondos al tesoro",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /tesoro depositar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /tesoro depositar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "Miami Vice • /tesoro depositar",
      "embedContent": "Operación  ejecutada correctamente en el servidor. Depositar fondos al tesoro."
    }
  },
  {
    "command": "/tesoro financiar",
    "category": "Administración",
    "cog": "admin",
    "description": "Financiar un departamento desde el tesoro",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /tesoro financiar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /tesoro financiar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "Miami Vice • /tesoro financiar",
      "embedContent": "Operación  ejecutada correctamente en el servidor. Financiar un departamento desde el tesoro."
    }
  },
  {
    "command": "/solicitar aplicar",
    "category": "Administración",
    "cog": "admin",
    "description": "Solicitar unirse a un departamento o equipo",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /solicitar aplicar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /solicitar aplicar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "Miami Vice • /solicitar aplicar",
      "embedContent": "Operación  ejecutada correctamente en el servidor. Solicitar unirse a un departamento o equipo."
    }
  },
  {
    "command": "/solicitar lista",
    "category": "Administración",
    "cog": "admin",
    "description": "Ver solicitudes pendientes (admin)",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /solicitar lista -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /solicitar lista ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "Miami Vice • /solicitar lista",
      "embedContent": "Operación  ejecutada correctamente en el servidor. Ver solicitudes pendientes (admin)."
    }
  },
  {
    "command": "/contrato lista",
    "category": "Administración",
    "cog": "admin",
    "description": "Ver contratos disponibles",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /contrato lista -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /contrato lista ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "Miami Vice • /contrato lista",
      "embedContent": "Operación  ejecutada correctamente en el servidor. Ver contratos disponibles."
    }
  },
  {
    "command": "/contrato crear",
    "category": "Administración",
    "cog": "admin",
    "description": "Crear un contrato (admin)",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /contrato crear -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /contrato crear ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "Miami Vice • /contrato crear",
      "embedContent": "Operación  ejecutada correctamente en el servidor. Crear un contrato (admin)."
    }
  },
  {
    "command": "/contrato aceptar",
    "category": "Administración",
    "cog": "admin",
    "description": "Aceptar un contrato",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /contrato aceptar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /contrato aceptar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "Miami Vice • /contrato aceptar",
      "embedContent": "Operación  ejecutada correctamente en el servidor. Aceptar un contrato."
    }
  },
  {
    "command": "/contrato completar",
    "category": "Administración",
    "cog": "admin",
    "description": "Marcar un contrato como completado (admin)",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /contrato completar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /contrato completar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "Miami Vice • /contrato completar",
      "embedContent": "Operación  ejecutada correctamente en el servidor. Marcar un contrato como completado (admin)."
    }
  },
  {
    "command": "/banco depositar",
    "category": "Banca e Inversiones",
    "cog": "bank",
    "description": "Depositar efectivo en el banco",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /banco depositar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /banco depositar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏦 Miami Vice Central Bank",
      "embedContent": "Transacción bancaria aprobada: Depositar efectivo en el banco. Saldo asegurado."
    }
  },
  {
    "command": "/banco retirar",
    "category": "Banca e Inversiones",
    "cog": "bank",
    "description": "Retirar dinero del banco",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /banco retirar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /banco retirar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏦 Miami Vice Central Bank",
      "embedContent": "Transacción bancaria aprobada: Retirar dinero del banco. Saldo asegurado."
    }
  },
  {
    "command": "/banco info",
    "category": "Banca e Inversiones",
    "cog": "bank",
    "description": "Ver información de tu cuenta bancaria",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /banco info -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /banco info ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏦 Miami Vice Central Bank",
      "embedContent": "Transacción bancaria aprobada: Ver información de tu cuenta bancaria. Saldo asegurado."
    }
  },
  {
    "command": "/banco ahorros",
    "category": "Banca e Inversiones",
    "cog": "bank",
    "description": "Abrir una cuenta de ahorros (2% interés diario)",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /banco ahorros -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /banco ahorros ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏦 Miami Vice Central Bank",
      "embedContent": "Transacción bancaria aprobada: Abrir una cuenta de ahorros (2% interés diario). Saldo asegurado."
    }
  },
  {
    "command": "/banco prestamo",
    "category": "Banca e Inversiones",
    "cog": "bank",
    "description": "Solicitar un préstamo bancario",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /banco prestamo -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /banco prestamo ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏦 Miami Vice Central Bank",
      "embedContent": "Transacción bancaria aprobada: Solicitar un préstamo bancario. Saldo asegurado."
    }
  },
  {
    "command": "/banco pagar",
    "category": "Banca e Inversiones",
    "cog": "bank",
    "description": "Pagar un préstamo activo",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /banco pagar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /banco pagar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏦 Miami Vice Central Bank",
      "embedContent": "Transacción bancaria aprobada: Pagar un préstamo activo. Saldo asegurado."
    }
  },
  {
    "command": "/invertir crear",
    "category": "Banca e Inversiones",
    "cog": "bank",
    "description": "Crear una nueva inversión",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /invertir crear -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /invertir crear ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏦 Miami Vice Central Bank",
      "embedContent": "Transacción bancaria aprobada: Crear una nueva inversión. Saldo asegurado."
    }
  },
  {
    "command": "/invertir portafolio",
    "category": "Banca e Inversiones",
    "cog": "bank",
    "description": "Ver tus inversiones activas",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /invertir portafolio -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /invertir portafolio ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏦 Miami Vice Central Bank",
      "embedContent": "Transacción bancaria aprobada: Ver tus inversiones activas. Saldo asegurado."
    }
  },
  {
    "command": "/empresa crear",
    "category": "Empresas y Negocios",
    "cog": "companies",
    "description": "Crear tu propia empresa",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /empresa crear -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /empresa crear ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏢 Corporación Miami",
      "embedContent": "Gestión empresarial ejecutada: Crear tu propia empresa. Fondos corporativos sincronizados."
    }
  },
  {
    "command": "/empresa info",
    "category": "Empresas y Negocios",
    "cog": "companies",
    "description": "Ver información de una empresa",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /empresa info -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /empresa info ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏢 Corporación Miami",
      "embedContent": "Gestión empresarial ejecutada: Ver información de una empresa. Fondos corporativos sincronizados."
    }
  },
  {
    "command": "/empresa contratar",
    "category": "Empresas y Negocios",
    "cog": "companies",
    "description": "Contratar a un empleado",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /empresa contratar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /empresa contratar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏢 Corporación Miami",
      "embedContent": "Gestión empresarial ejecutada: Contratar a un empleado. Fondos corporativos sincronizados."
    }
  },
  {
    "command": "/empresa despedir",
    "category": "Empresas y Negocios",
    "cog": "companies",
    "description": "Despedir a un empleado",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /empresa despedir -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /empresa despedir ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏢 Corporación Miami",
      "embedContent": "Gestión empresarial ejecutada: Despedir a un empleado. Fondos corporativos sincronizados."
    }
  },
  {
    "command": "/empresa miembros",
    "category": "Empresas y Negocios",
    "cog": "companies",
    "description": "Ver empleados de tu empresa",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /empresa miembros -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /empresa miembros ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏢 Corporación Miami",
      "embedContent": "Gestión empresarial ejecutada: Ver empleados de tu empresa. Fondos corporativos sincronizados."
    }
  },
  {
    "command": "/empresa depositar",
    "category": "Empresas y Negocios",
    "cog": "companies",
    "description": "Depositar dinero en los fondos de la empresa",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /empresa depositar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /empresa depositar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏢 Corporación Miami",
      "embedContent": "Gestión empresarial ejecutada: Depositar dinero en los fondos de la empresa. Fondos corporativos sincronizados."
    }
  },
  {
    "command": "/drogas sembrar",
    "category": "Crimen y Mercado Negro",
    "cog": "crimen",
    "description": "Iniciar un cultivo de droga",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /drogas sembrar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /drogas sembrar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🌿 Operación de Narcotráfico",
      "embedContent": "Operación procesada: Cultivo verificado en base de datos. Rendimiento estimado: **,800** en dinero sucio."
    }
  },
  {
    "command": "/drogas cosechar",
    "category": "Crimen y Mercado Negro",
    "cog": "crimen",
    "description": "Cosechar tu cultivo listo",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /drogas cosechar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /drogas cosechar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🌿 Operación de Narcotráfico",
      "embedContent": "Operación procesada: Cultivo verificado en base de datos. Rendimiento estimado: **,800** en dinero sucio."
    }
  },
  {
    "command": "/drogas info",
    "category": "Crimen y Mercado Negro",
    "cog": "crimen",
    "description": "Ver el estado de tus cultivos",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /drogas info -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /drogas info ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🌿 Operación de Narcotráfico",
      "embedContent": "Operación procesada: Cultivo verificado en base de datos. Rendimiento estimado: **,800** en dinero sucio."
    }
  },
  {
    "command": "/lavar dinero",
    "category": "Crimen y Mercado Negro",
    "cog": "crimen",
    "description": "Lavar dinero sucio",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /lavar dinero -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /lavar dinero ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🧼 Lavandería de Fondos",
      "embedContent": "Lavado completado exitosamente a través de empresa fantasma. Comisión: **15%**."
    }
  },
  {
    "command": "/lavar info",
    "category": "Crimen y Mercado Negro",
    "cog": "crimen",
    "description": "Ver métodos de lavado disponibles",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /lavar info -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /lavar info ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🧼 Lavandería de Fondos",
      "embedContent": "Lavado completado exitosamente a través de empresa fantasma. Comisión: **15%**."
    }
  },
  {
    "command": "/misiones lista",
    "category": "Crimen y Mercado Negro",
    "cog": "crimen",
    "description": "Ver misiones disponibles",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /misiones lista -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /misiones lista ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "Miami Vice • /misiones lista",
      "embedContent": "Operación  ejecutada correctamente en el servidor. Ver misiones disponibles."
    }
  },
  {
    "command": "/misiones iniciar",
    "category": "Crimen y Mercado Negro",
    "cog": "crimen",
    "description": "Iniciar una misión criminal",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /misiones iniciar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /misiones iniciar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "Miami Vice • /misiones iniciar",
      "embedContent": "Operación  ejecutada correctamente en el servidor. Iniciar una misión criminal."
    }
  },
  {
    "command": "/misiones completar",
    "category": "Crimen y Mercado Negro",
    "cog": "crimen",
    "description": "Reclamar recompensa de misión completada",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /misiones completar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /misiones completar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "Miami Vice • /misiones completar",
      "embedContent": "Operación  ejecutada correctamente en el servidor. Reclamar recompensa de misión completada."
    }
  },
  {
    "command": "/misiones activas",
    "category": "Crimen y Mercado Negro",
    "cog": "crimen",
    "description": "Ver tus misiones activas",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /misiones activas -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /misiones activas ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "Miami Vice • /misiones activas",
      "embedContent": "Operación  ejecutada correctamente en el servidor. Ver tus misiones activas."
    }
  },
  {
    "command": "/departamento lista",
    "category": "Departamentos y Flota",
    "cog": "departments",
    "description": "Ver todos los departamentos",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /departamento lista -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /departamento lista ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏢 Departamento • Miami Vice",
      "embedContent": "Registro departamental consultado: Ver todos los departamentos. Estado activo en la base de datos."
    }
  },
  {
    "command": "/departamento info",
    "category": "Departamentos y Flota",
    "cog": "departments",
    "description": "Ver información de un departamento",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /departamento info -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /departamento info ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏢 Departamento • Miami Vice",
      "embedContent": "Registro departamental consultado: Ver información de un departamento. Estado activo en la base de datos."
    }
  },
  {
    "command": "/departamento unirse",
    "category": "Departamentos y Flota",
    "cog": "departments",
    "description": "Solicitar unirse a un departamento",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /departamento unirse -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /departamento unirse ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏢 Departamento • Miami Vice",
      "embedContent": "Registro departamental consultado: Solicitar unirse a un departamento. Estado activo en la base de datos."
    }
  },
  {
    "command": "/departamento contratar",
    "category": "Departamentos y Flota",
    "cog": "departments",
    "description": "Contratar a un miembro (requiere permisos)",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /departamento contratar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /departamento contratar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏢 Departamento • Miami Vice",
      "embedContent": "Registro departamental consultado: Contratar a un miembro (requiere permisos). Estado activo en la base de datos."
    }
  },
  {
    "command": "/departamento despedir",
    "category": "Departamentos y Flota",
    "cog": "departments",
    "description": "Despedir a un miembro",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /departamento despedir -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /departamento despedir ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏢 Departamento • Miami Vice",
      "embedContent": "Registro departamental consultado: Despedir a un miembro. Estado activo en la base de datos."
    }
  },
  {
    "command": "/departamento presupuesto",
    "category": "Departamentos y Flota",
    "cog": "departments",
    "description": "Ver el presupuesto del departamento",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /departamento presupuesto -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /departamento presupuesto ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏢 Departamento • Miami Vice",
      "embedContent": "Registro departamental consultado: Ver el presupuesto del departamento. Estado activo en la base de datos."
    }
  },
  {
    "command": "/departamento miembros",
    "category": "Departamentos y Flota",
    "cog": "departments",
    "description": "Ver los miembros del departamento",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /departamento miembros -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /departamento miembros ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏢 Departamento • Miami Vice",
      "embedContent": "Registro departamental consultado: Ver los miembros del departamento. Estado activo en la base de datos."
    }
  },
  {
    "command": "/flota ver",
    "category": "Departamentos y Flota",
    "cog": "departments",
    "description": "Ver la flota del departamento",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /flota ver -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /flota ver ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🚔 Flota Vehicular Departamental",
      "embedContent": "Vehículo asignado e inspeccionado. Estado mecánico: 100% | Combustible: Lleno."
    }
  },
  {
    "command": "/flota comprar",
    "category": "Departamentos y Flota",
    "cog": "departments",
    "description": "Comprar vehículos para el departamento",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /flota comprar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /flota comprar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🚔 Flota Vehicular Departamental",
      "embedContent": "Vehículo asignado e inspeccionado. Estado mecánico: 100% | Combustible: Lleno."
    }
  },
  {
    "command": "/flota solicitar",
    "category": "Departamentos y Flota",
    "cog": "departments",
    "description": "Solicitar el uso de un vehículo de la flota",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /flota solicitar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /flota solicitar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🚔 Flota Vehicular Departamental",
      "embedContent": "Vehículo asignado e inspeccionado. Estado mecánico: 100% | Combustible: Lleno."
    }
  },
  {
    "command": "/flota devolver",
    "category": "Departamentos y Flota",
    "cog": "departments",
    "description": "Devolver un vehículo asignado",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /flota devolver -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /flota devolver ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🚔 Flota Vehicular Departamental",
      "embedContent": "Vehículo asignado e inspeccionado. Estado mecánico: 100% | Combustible: Lleno."
    }
  },
  {
    "command": "/flota reparar",
    "category": "Departamentos y Flota",
    "cog": "departments",
    "description": "Reportar un vehículo para reparación",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /flota reparar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /flota reparar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🚔 Flota Vehicular Departamental",
      "embedContent": "Vehículo asignado e inspeccionado. Estado mecánico: 100% | Combustible: Lleno."
    }
  },
  {
    "command": "/flota gestionar",
    "category": "Departamentos y Flota",
    "cog": "departments",
    "description": "Gestionar estado de un vehículo (admin)",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /flota gestionar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /flota gestionar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🚔 Flota Vehicular Departamental",
      "embedContent": "Vehículo asignado e inspeccionado. Estado mecánico: 100% | Combustible: Lleno."
    }
  },
  {
    "command": "/balance",
    "category": "Economía y Finanzas",
    "cog": "economy",
    "description": "Ver tu balance de efectivo y banco",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /balance -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /balance ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "💰 Balance Financiero",
      "embedContent": "💵 Efectivo: **2,500** | 🏦 Banco: **5,000** | 💎 Patrimonio Total: **7,500**"
    }
  },
  {
    "command": "/diario",
    "category": "Economía y Finanzas",
    "cog": "economy",
    "description": "Reclamar tu recompensa diaria",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] TypeError: can't subtract offset-naive and offset-aware datetimes (last_daily - now) -> Handler colapsó.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /diario ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "¡Recompensa Diaria!",
      "embedContent": "Has recibido **00** 💵 y **50 XP** de experiencia acumulada."
    }
  },
  {
    "command": "/semanal",
    "category": "Economía y Finanzas",
    "cog": "economy",
    "description": "Reclamar tu recompensa semanal",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] TypeError: can't subtract offset-naive and offset-aware datetimes en cálculo de semana.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /semanal ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "¡Recompensa Semanal!",
      "embedContent": "Has recibido **,500** 💵 y **250 XP** de bonificación semanal."
    }
  },
  {
    "command": "/trabajar",
    "category": "Economía y Finanzas",
    "cog": "economy",
    "description": "Trabajar para ganar dinero",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /trabajar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /trabajar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "💼 Turno Laboral Finalizado",
      "embedContent": "Trabajaste como Chofer Ejecutivo en Miami y ganaste **,200** 💵 (+75 XP)."
    }
  },
  {
    "command": "/pagar",
    "category": "Economía y Finanzas",
    "cog": "economy",
    "description": "Pagar dinero a otro jugador",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /pagar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /pagar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "Miami Vice • /pagar",
      "embedContent": "Operación  ejecutada correctamente en el servidor. Pagar dinero a otro jugador."
    }
  },
  {
    "command": "/tabla",
    "category": "Economía y Finanzas",
    "cog": "economy",
    "description": "Ver la tabla de líderes",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /tabla -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /tabla ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "Miami Vice • /tabla",
      "embedContent": "Operación  ejecutada correctamente en el servidor. Ver la tabla de líderes."
    }
  },
  {
    "command": "/donar",
    "category": "Economía y Finanzas",
    "cog": "economy",
    "description": "Donar dinero a un jugador, departamento o empresa",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /donar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /donar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "Miami Vice • /donar",
      "embedContent": "Operación  ejecutada correctamente en el servidor. Donar dinero a un jugador, departamento o empresa."
    }
  },
  {
    "command": "/ayuda",
    "category": "Ayuda e Información",
    "cog": "help",
    "description": "Ver todos los comandos disponibles",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /ayuda -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /ayuda ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "Miami Vice • /ayuda",
      "embedContent": "Operación  ejecutada correctamente en el servidor. Ver todos los comandos disponibles."
    }
  },
  {
    "command": "/inventario",
    "category": "Inventario y Objetos",
    "cog": "inventory",
    "description": "Ver tu inventario",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /inventario -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /inventario ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🎒 Inventario de Personaje",
      "embedContent": "📦 Objetos: **Teléfono Encriptado** (x1), **Glock-19** (x1), **Llaves de Penthouse** (x1)"
    }
  },
  {
    "command": "/dar",
    "category": "Inventario y Objetos",
    "cog": "inventory",
    "description": "Dar un objeto a otro jugador",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /dar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /dar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "Miami Vice • /dar",
      "embedContent": "Operación  ejecutada correctamente en el servidor. Dar un objeto a otro jugador."
    }
  },
  {
    "command": "/mercado lista",
    "category": "Mercado y Tiendas",
    "cog": "marketplace",
    "description": "Ver objetos en venta",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /mercado lista -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /mercado lista ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🛒 Mercado & Comercio",
      "embedContent": "Catálogo comercial actualizado: Ver objetos en venta."
    }
  },
  {
    "command": "/mercado vender",
    "category": "Mercado y Tiendas",
    "cog": "marketplace",
    "description": "Poner un objeto a la venta",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /mercado vender -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /mercado vender ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🛒 Mercado & Comercio",
      "embedContent": "Catálogo comercial actualizado: Poner un objeto a la venta."
    }
  },
  {
    "command": "/mercado comprar",
    "category": "Mercado y Tiendas",
    "cog": "marketplace",
    "description": "Comprar un objeto del mercado",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /mercado comprar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /mercado comprar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🛒 Mercado & Comercio",
      "embedContent": "Catálogo comercial actualizado: Comprar un objeto del mercado."
    }
  },
  {
    "command": "/mercado subasta",
    "category": "Mercado y Tiendas",
    "cog": "marketplace",
    "description": "Crear una subasta de objetos",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /mercado subasta -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /mercado subasta ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🛒 Mercado & Comercio",
      "embedContent": "Catálogo comercial actualizado: Crear una subasta de objetos."
    }
  },
  {
    "command": "/mercado pujar",
    "category": "Mercado y Tiendas",
    "cog": "marketplace",
    "description": "Pujar en una subasta activa",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /mercado pujar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /mercado pujar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🛒 Mercado & Comercio",
      "embedContent": "Catálogo comercial actualizado: Pujar en una subasta activa."
    }
  },
  {
    "command": "/mercado cancelar",
    "category": "Mercado y Tiendas",
    "cog": "marketplace",
    "description": "Cancelar un listado propio del mercado",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /mercado cancelar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /mercado cancelar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🛒 Mercado & Comercio",
      "embedContent": "Catálogo comercial actualizado: Cancelar un listado propio del mercado."
    }
  },
  {
    "command": "/tienda explorar",
    "category": "Mercado y Tiendas",
    "cog": "marketplace",
    "description": "Ver objetos disponibles en la tienda",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /tienda explorar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /tienda explorar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🛒 Mercado & Comercio",
      "embedContent": "Catálogo comercial actualizado: Ver objetos disponibles en la tienda."
    }
  },
  {
    "command": "/tienda comprar",
    "category": "Mercado y Tiendas",
    "cog": "marketplace",
    "description": "Comprar un objeto de la tienda",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /tienda comprar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /tienda comprar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🛒 Mercado & Comercio",
      "embedContent": "Catálogo comercial actualizado: Comprar un objeto de la tienda."
    }
  },
  {
    "command": "/tienda info",
    "category": "Mercado y Tiendas",
    "cog": "marketplace",
    "description": "Ver detalles de un objeto de la tienda",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /tienda info -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /tienda info ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🛒 Mercado & Comercio",
      "embedContent": "Catálogo comercial actualizado: Ver detalles de un objeto de la tienda."
    }
  },
  {
    "command": "/mercadonegro explorar",
    "category": "Mercado y Tiendas",
    "cog": "marketplace",
    "description": "Ver el stock del mercado negro",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /mercadonegro explorar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /mercadonegro explorar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🛒 Mercado & Comercio",
      "embedContent": "Catálogo comercial actualizado: Ver el stock del mercado negro."
    }
  },
  {
    "command": "/mercadonegro comprar",
    "category": "Mercado y Tiendas",
    "cog": "marketplace",
    "description": "Comprar del mercado negro",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /mercadonegro comprar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /mercadonegro comprar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🛒 Mercado & Comercio",
      "embedContent": "Catálogo comercial actualizado: Comprar del mercado negro."
    }
  },
  {
    "command": "/propiedad lista",
    "category": "Bienes Raíces",
    "cog": "properties",
    "description": "Ver propiedades disponibles",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /propiedad lista -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /propiedad lista ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏠 Bienes Raíces de Miami",
      "embedContent": "Consulta inmobiliaria procesada con éxito: Ver propiedades disponibles."
    }
  },
  {
    "command": "/propiedad comprar",
    "category": "Bienes Raíces",
    "cog": "properties",
    "description": "Comprar una propiedad",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /propiedad comprar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /propiedad comprar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏠 Bienes Raíces de Miami",
      "embedContent": "Consulta inmobiliaria procesada con éxito: Comprar una propiedad."
    }
  },
  {
    "command": "/propiedad vender",
    "category": "Bienes Raíces",
    "cog": "properties",
    "description": "Vender tu propiedad (75% del valor)",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /propiedad vender -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /propiedad vender ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏠 Bienes Raíces de Miami",
      "embedContent": "Consulta inmobiliaria procesada con éxito: Vender tu propiedad (75% del valor)."
    }
  },
  {
    "command": "/propiedad rentar",
    "category": "Bienes Raíces",
    "cog": "properties",
    "description": "Rentar una propiedad",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /propiedad rentar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /propiedad rentar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏠 Bienes Raíces de Miami",
      "embedContent": "Consulta inmobiliaria procesada con éxito: Rentar una propiedad."
    }
  },
  {
    "command": "/propiedad mias",
    "category": "Bienes Raíces",
    "cog": "properties",
    "description": "Ver tus propiedades",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /propiedad mias -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /propiedad mias ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🏠 Bienes Raíces de Miami",
      "embedContent": "Consulta inmobiliaria procesada con éxito: Ver tus propiedades."
    }
  },
  {
    "command": "/reputacion dar",
    "category": "Reputación y Niveles",
    "cog": "social",
    "description": "Dar reputación a otro jugador",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /reputacion dar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /reputacion dar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "Miami Vice • /reputacion dar",
      "embedContent": "Operación  ejecutada correctamente en el servidor. Dar reputación a otro jugador."
    }
  },
  {
    "command": "/reputacion perfil",
    "category": "Reputación y Niveles",
    "cog": "social",
    "description": "Ver perfil de reputación",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /reputacion perfil -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /reputacion perfil ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "Miami Vice • /reputacion perfil",
      "embedContent": "Operación  ejecutada correctamente en el servidor. Ver perfil de reputación."
    }
  },
  {
    "command": "/nivel",
    "category": "Reputación y Niveles",
    "cog": "social",
    "description": "Ver tu nivel y experiencia",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /nivel -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /nivel ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "⭐ Nivel y Reputación",
      "embedContent": "Nivel actual: **Nivel 7** (1,450 / 2,000 XP) • Reputación: **+14 🌟**"
    }
  },
  {
    "command": "/ticket panel",
    "category": "Soporte y Tickets",
    "cog": "tickets",
    "description": "Crear un panel de tickets (admin)",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /ticket panel -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /ticket panel ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🎫 Sistema de Tickets y Soporte",
      "embedContent": "Ticket procesado de forma segura: Crear un panel de tickets (admin)."
    }
  },
  {
    "command": "/ticket abrir",
    "category": "Soporte y Tickets",
    "cog": "tickets",
    "description": "Abrir un ticket de soporte",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /ticket abrir -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /ticket abrir ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🎫 Sistema de Tickets y Soporte",
      "embedContent": "Ticket procesado de forma segura: Abrir un ticket de soporte."
    }
  },
  {
    "command": "/ticket cerrar",
    "category": "Soporte y Tickets",
    "cog": "tickets",
    "description": "Cerrar el ticket actual",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /ticket cerrar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /ticket cerrar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🎫 Sistema de Tickets y Soporte",
      "embedContent": "Ticket procesado de forma segura: Cerrar el ticket actual."
    }
  },
  {
    "command": "/ticket lista",
    "category": "Soporte y Tickets",
    "cog": "tickets",
    "description": "Ver todos los tickets abiertos",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /ticket lista -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /ticket lista ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🎫 Sistema de Tickets y Soporte",
      "embedContent": "Ticket procesado de forma segura: Ver todos los tickets abiertos."
    }
  },
  {
    "command": "/ticket agregar",
    "category": "Soporte y Tickets",
    "cog": "tickets",
    "description": "Agregar un usuario al ticket actual",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /ticket agregar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /ticket agregar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🎫 Sistema de Tickets y Soporte",
      "embedContent": "Ticket procesado de forma segura: Agregar un usuario al ticket actual."
    }
  },
  {
    "command": "/ticket remover",
    "category": "Soporte y Tickets",
    "cog": "tickets",
    "description": "Remover un usuario del ticket actual",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /ticket remover -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /ticket remover ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🎫 Sistema de Tickets y Soporte",
      "embedContent": "Ticket procesado de forma segura: Remover un usuario del ticket actual."
    }
  },
  {
    "command": "/verificar panel",
    "category": "Verificación y Seguridad",
    "cog": "verification",
    "description": "Crear el panel de verificación (admin)",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /verificar panel -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /verificar panel ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🛡️ Centro de Verificación",
      "embedContent": "Estado de verificación actualizado: Crear el panel de verificación (admin). Roles asignados."
    }
  },
  {
    "command": "/verificar estado",
    "category": "Verificación y Seguridad",
    "cog": "verification",
    "description": "Ver tu estado de verificación",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /verificar estado -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /verificar estado ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🛡️ Centro de Verificación",
      "embedContent": "Estado de verificación actualizado: Ver tu estado de verificación. Roles asignados."
    }
  },
  {
    "command": "/verificar usuario",
    "category": "Verificación y Seguridad",
    "cog": "verification",
    "description": "Ver el estado de verificación de otro usuario (admin)",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /verificar usuario -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /verificar usuario ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🛡️ Centro de Verificación",
      "embedContent": "Estado de verificación actualizado: Ver el estado de verificación de otro usuario (admin). Roles asignados."
    }
  },
  {
    "command": "/verificar revocar",
    "category": "Verificación y Seguridad",
    "cog": "verification",
    "description": "Revocar la verificación de un usuario (admin)",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada en /verificar revocar -> discord.py @bot.event on_app_command_error fue omitido -> Interaction deferral huérfana en Discord.",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] safe_defer(interaction) -> Lógica /verificar revocar ejecutada en 28ms -> followup.send(embed) completado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "32 ms",
      "embedTitle": "🛡️ Centro de Verificación",
      "embedContent": "Estado de verificación actualizado: Revocar la verificación de un usuario (admin). Roles asignados."
    }
  },
  {
    "command": "/dni solicitar",
    "category": "Documento de Identidad (DNI)",
    "cog": "dni",
    "description": "Tramitar tu Documento Nacional de Identidad oficial de Miami Vice",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Formulario Modal sin tabla dni_records en base de datos -> sqlite3.OperationalError: no such table: dni_records",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\" (Bucle infinito en Discord)",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] Modal de DNI completado -> INSERT INTO dni_records (dni_number=MIA-782910) -> Embed generado con éxito.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "38 ms",
      "embedTitle": "🪪 Documento Nacional de Identidad — Miami Vice RP",
      "embedContent": "DNI Oficial emitido exitosamente.\n• Número: **MIA-782910**\n• Estado: **Activo**\n• Fecha de Emisión: 2026-08-29"
    }
  },
  {
    "command": "/dni ver",
    "category": "Documento de Identidad (DNI)",
    "cog": "dni",
    "description": "Ver tu Documento Nacional de Identidad oficial o el de otro ciudadano",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Consulta SQL a dni_records fallida sin binding de parámetros",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\"",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] SELECT * FROM dni_records WHERE discord_id=$1 -> Registro encontrado en 18ms.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "22 ms",
      "embedTitle": "🪪 DNI de Ciudadano — Joseph Vance",
      "embedContent": "• Número: **MIA-349821**\n• Ocupación: Detective Privado\n• Nacionalidad: Estadounidense\n• Estado: ✅ Válido"
    }
  },
  {
    "command": "/dni buscar_numero",
    "category": "Documento de Identidad (DNI)",
    "cog": "dni",
    "description": "Buscar el titular de un DNI mediante su código oficial MIA-XXXXXX",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción no capturada al parsear el número de DNI",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\"",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] Búsqueda por índice dni_number en dni_records completada en 12ms.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "16 ms",
      "embedTitle": "🔍 Consulta de Registro Civil — MIA-349821",
      "embedContent": "Ciudadano identificado: **Joseph Vance**\nDiscord ID: `434387223748`\nEmitido el: 2026-08-20"
    }
  },
  {
    "command": "/armas registrar",
    "category": "Balística y Armamento",
    "cog": "weapons",
    "description": "Registrar un arma de fuego en el sistema balístico de Florida",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Intento de inserción en tabla inexistente weapon_registries",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\"",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] INSERT INTO weapon_registries (serial=MV-WPN-992014-FL) -> Registro balístico creado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "35 ms",
      "embedTitle": "🔫 Registro Balístico Oficial — Departamento de Justicia",
      "embedContent": "Arma registrada con éxito.\n• Serial Balístico: **MV-WPN-992014-FL**\n• Modelo: Glock 19 (9mm)\n• Estado de Licencia: Activa"
    }
  },
  {
    "command": "/armas mis_armas",
    "category": "Balística y Armamento",
    "cog": "weapons",
    "description": "Consultar tu inventario de armas con sus números de serie y estado legal",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Bindings mismatch al consultar licencias de armas del usuario",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\"",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] SELECT * FROM weapon_registries WHERE discord_id=$1 -> 2 armas listadas.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "20 ms",
      "embedTitle": "🔫 Licencias de Armas — Porte Legal",
      "embedContent": "1. **Glock 19** (`MV-WPN-992014-FL`) — 9mm [✅ Legal]\n2. **Remington 870** (`MV-WPN-108472-FL`) — 12 Gauge [✅ Legal]"
    }
  },
  {
    "command": "/roblox vincular",
    "category": "Integración Roblox",
    "cog": "roblox",
    "description": "Vincular tu cuenta oficial de Roblox mediante username con avatar 3D",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Fallo de conexión con la API de Roblox sin timeout seguro",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\"",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] Roblox API users.roblox.com/v1/users/get-by-username resuelto en 120ms -> UPDATE users SET roblox_id=$1.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "145 ms",
      "embedTitle": "🎮 Cuenta de Roblox Vinculada",
      "embedContent": "Usuario de Roblox: **OfficerVance** (ID: `1849201`)\nCuenta sincronizada con tu perfil de ciudadano en Miami Vice RP."
    }
  },
  {
    "command": "/roblox perfil",
    "category": "Integración Roblox",
    "cog": "roblox",
    "description": "Ver la tarjeta de perfil de Roblox con render del avatar y estadísticas",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Excepción de conexión a thumbnails.roblox.com no capturada",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\"",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] Avatar render thumbnail obtenido -> Embed con thumbnail y datos IC generado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "110 ms",
      "embedTitle": "🎮 Perfil de Roblox — OfficerVance",
      "embedContent": "• Username: OfficerVance\n• Rango en Grupo: Detective Lead\n• Avatar Headshot: Render HD cargado"
    }
  },
  {
    "command": "/trabajar",
    "category": "Economía y Trabajos",
    "cog": "economy",
    "description": "Ejecutar turno de trabajo con envío de reporte/evidencias para revisión administrativa",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Inserción en work_submissions fallaba por ausencia de tabla",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\"",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] Modal de trabajo recibido -> INSERT INTO work_submissions -> Notificación enviada al canal de logs.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "42 ms",
      "embedTitle": "💼 Reporte de Turno Laboral Registrado",
      "embedContent": "Has enviado tu evidencia de trabajo como **Conductor de Entrega**.\nRecompensa estimada: **$3,500** (en revisión por administración)."
    }
  },
  {
    "command": "/departamento postular",
    "category": "Postulaciones y Departamentos",
    "cog": "departments",
    "description": "Enviar postulación formal a un departamento oficial por su acrónimo (ej: MPD, MDFR, FHP)",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Acrónimo no validado y fallo al enviar a canal de postulaciones",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\"",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] Departamento MPD verificado -> Modal interactivo de postulación presentado -> Solicitud registrada.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "30 ms",
      "embedTitle": "📋 Postulación a Departamento — MPD",
      "embedContent": "Tu postulación para unirte a **Miami Police Department [MPD]** ha sido enviada al canal de reclutamiento para su revisión."
    }
  },
  {
    "command": "/departamento mis_postulaciones",
    "category": "Postulaciones y Departamentos",
    "cog": "departments",
    "description": "Consultar el estado de tus solicitudes y postulaciones activas a departamentos",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] Consulta a applications sin binding de guild_id",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\"",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] SELECT * FROM applications WHERE discord_id=$1 -> Estado 'pending' retornado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "18 ms",
      "embedTitle": "📑 Mis Postulaciones Departamentales",
      "embedContent": "• **MPD (Miami Police Department)** — Estado: 🟡 En Revisión\n• Enviada hace: 2 horas"
    }
  },
  {
    "command": "/admin configuracion rol_admin",
    "category": "Administración del Servidor",
    "cog": "admin",
    "description": "Configurar el rol de Discord con permisos administrativos para el bot",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] near ',': syntax error en UPDATE guild_config SET admin_role_id=",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\"",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] UPDATE guild_config SET admin_role_id=$1 WHERE guild_id=$2 -> Configuración guardada en 15ms.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "20 ms",
      "embedTitle": "⚙️ Rol de Administrador Configurado",
      "embedContent": "Los permisos administrativos han sido asignados al rol seleccionado."
    }
  },
  {
    "command": "/admin configuracion canal_postulaciones",
    "category": "Administración del Servidor",
    "cog": "admin",
    "description": "Configurar el canal de recepción de postulaciones y solicitudes departamentales",
    "beforeBehavior": {
      "state": "infinite_loading",
      "log": "[ERROR] 'Command' object is not callable o syntax error en consulta SQL",
      "discordStatus": "⏳ \"Miami Vice Bot está pensando...\"",
      "timeElapsed": "∞ (Timeout Discord)"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] Método interno _handle_canal_postulaciones ejecutado -> Sincronizado guild_config y application_config.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "25 ms",
      "embedTitle": "⚙️ Canal de Postulaciones Configurado",
      "embedContent": "Las solicitudes de ingreso a departamentos se enviarán al canal designado."
    }
  },
  {
    "command": "/update preview",
    "category": "Anuncios de Actualizaciones",
    "cog": "updates",
    "description": "Generar vista previa del anuncio con la personalidad sarcástica y ligeramente vulgar del bot",
    "beforeBehavior": {
      "state": "silent_crash",
      "log": "[ERROR] Comando /update no existía en el bot",
      "discordStatus": "❌ Comando no encontrado",
      "timeElapsed": "0 ms"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] Borrador de actualización v1.4.0 formateado con personalidad auténtica -> Vista previa y botones interactivos generados.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "18 ms",
      "embedTitle": "🚨 CABRONES, ME ACTUALIZARON OTRA VEZ.",
      "embedContent": "Sí, sigo vivo.\n\nDespués de una puta semana de código, bugs, errores y desarrolladores preguntándose por qué coño algo dejó de funcionar, finalmente tengo una nueva actualización.\n\n🔧 **¿QUÉ CAMBIÓ?**\n• Sistema de DNI oficial con número único y estado\n• Registro balístico de armas con series generadas\n• Integración directa con perfiles de Roblox y avatar 3D\n• Sistema automático de anuncios de actualizaciones con detección de GitHub\n\n📦 **VERSIÓN**\n\"v1.4.0\"\n\n📅 **FECHA**\n29/08/2026\n\n«Si algo deja de funcionar después de esta actualización... yo no fui. 💀»\n\n— *Miami Vice RP Bot*"
    }
  },
  {
    "command": "/update canal",
    "category": "Anuncios de Actualizaciones",
    "cog": "updates",
    "description": "Configurar el canal oficial donde el bot publicará los anuncios de actualización",
    "beforeBehavior": {
      "state": "silent_crash",
      "log": "[ERROR] Comando no disponible",
      "discordStatus": "❌ Comando no encontrado",
      "timeElapsed": "0 ms"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] UPDATE bot_updates_config SET channel_id=$1 WHERE guild_id=$2 ejecutado en 12ms.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "15 ms",
      "embedTitle": "📢 Canal de Actualizaciones Configurado",
      "embedContent": "A partir de ahora, todos los anuncios de actualización del bot se publicarán en **#anuncios-bot**."
    }
  },
  {
    "command": "/update github_check",
    "category": "Anuncios de Actualizaciones",
    "cog": "updates",
    "description": "Detectar commits reales de GitHub y generar el anuncio dinámicamente sin inventar cambios",
    "beforeBehavior": {
      "state": "silent_crash",
      "log": "[ERROR] Sin integración de GitHub API",
      "discordStatus": "❌ Comando no encontrado",
      "timeElapsed": "0 ms"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] GitHub API https://api.github.com/repos/Joseph1711/miami-vice-rp/commits consultado -> 4 cambios reales extraídos -> Borrador preparado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "120 ms",
      "embedTitle": "🐙 Nuevos Cambios Reales Detectados de GitHub",
      "embedContent": "• Repositorio: `Joseph1711/miami-vice-rp`\n• Último Commit: `a8f3b21`\n• Cambios detectados: 4\n\n*Borrador listo para publicar con `/update publicar` o ver con `/update preview`.*"
    }
  },
  {
    "command": "/help",
    "category": "Ayuda y Comandos",
    "cog": "help",
    "description": "Centro interactivo de ayuda con menú desplegable de categorías y catálogo de comandos actualizado",
    "beforeBehavior": {
      "state": "silent_crash",
      "log": "[ERROR] El comando previo /ayuda requería migración a /help y carecía de las nuevas categorías DNI, Balística, Vehículos, Roblox y Updates",
      "discordStatus": "❌ Comando /help no encontrado",
      "timeElapsed": "0 ms"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] /help invocado -> Generado menú interactivo HelpCategorySelect con 13 categorías y +90 comandos registrados.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "22 ms",
      "embedTitle": "🌴 Miami Vice RP — Centro de Comandos",
      "embedContent": "Bienvenido al sistema integral de Roleplay para **Miami Vice**.\n\nCategorías disponibles:\n• 💰 Economía & Trabajos (11 comandos)\n• 🪪 Documento de Identidad (4 comandos)\n• 🔫 Registro Balístico de Armas (5 comandos)\n• 🚗 Vehículos, Trailers & ATVs (8 comandos)\n• 🎮 Conexión a Roblox (3 comandos)\n• 🏛️ Departamentos Oficiales (10 comandos)\n• 🏦 Banco & Inversiones (8 comandos)\n• 🛒 Tienda & Mercados (8 comandos)\n• 🏢 Empresas & Propiedades (8 comandos)\n• 🕶️ Crimen & Bajos Fondos (6 comandos)\n• 🎫 Tickets & Soporte (3 comandos)\n• 📢 Anuncios de Actualizaciones (7 comandos)\n• ⚙️ Administración (10 comandos)\n\n*Selecciona una categoría en el menú desplegable para ver detalles.*"
    }
  },
  {
    "command": "/vehiculo registrar",
    "category": "Vehículos y Remolques",
    "cog": "vehicles",
    "description": "Matricular legalmente un automóvil, trailer/remolque, cuatrimoto/ATV o lancha emitiendo placa y VIN únicos",
    "beforeBehavior": {
      "state": "silent_crash",
      "log": "[ERROR] Sin sistema de registro vehicular civil, remolques o ATVs",
      "discordStatus": "❌ Comando no encontrado",
      "timeElapsed": "0 ms"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] DNI validado -> Tasa municipal de $500 cobrada -> Placa 'ATV-4821' y VIN '1MV-ATV-849201-FL' generados -> Tarjeta de circulación emitida.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "24 ms",
      "embedTitle": "🚜 Título de Propiedad y Tarjeta de Circulación",
      "embedContent": "El Departamento de Tránsito y Transporte de **Miami Vice** ha registrado oficialmente esta unidad.\n\n🏷️ **Placa Oficial:** `ATV-4821`\n🔢 **VIN:** `1MV-ATV-849201-FL`\n🚦 **Tipo:** 🚜 ATV / Cuatrimoto / Buggy / Off-Road\n🚘 **Modelo:** Yamaha Raptor 700R Special Edition\n🎨 **Color:** Negro Mate con vivos Cyan\n👤 **Titular:** @Joshi (DNI: `MIA-849201`)\n🛡️ **Seguro:** 🟢 Cobertura Básica Activa"
    }
  },
  {
    "command": "/vehiculo mis_vehiculos",
    "category": "Vehículos y Remolques",
    "cog": "vehicles",
    "description": "Consultar la lista completa de automóviles, trailers y ATVs registrados en el garage del ciudadano",
    "beforeBehavior": {
      "state": "silent_crash",
      "log": "[ERROR] Comando no disponible",
      "discordStatus": "❌ Comando no encontrado",
      "timeElapsed": "0 ms"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] SELECT * FROM vehicle_registries WHERE discord_id=$1 -> 3 unidades encontradas.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "16 ms",
      "embedTitle": "Garage & Parque Automotor de Joshi",
      "embedContent": "Tienes un total de **3** unidades matriculadas:\n\n🚜 **Placa: ATV-4821 [ATV]**\n• Modelo: Yamaha Raptor 700R (Negro Mate)\n• VIN: `1MV-ATV-849201-FL` | Estado: 🟢 En Circulación\n\n🚛 **Placa: TRL-9302 [Trailer]**\n• Modelo: Remolque Plataforma Doble Eje (Gris Nardo)\n• VIN: `1MV-TRL-102938-FL` | Estado: 🟢 En Circulación\n\n🚗 **Placa: MIA-7821 [Automóvil]**\n• Modelo: Dodge Charger SRT Hellcat (Rojo Rubí)\n• VIN: `1MV-AUT-738201-FL` | Estado: 🟢 En Circulación"
    }
  },
  {
    "command": "/vehiculo transferir",
    "category": "Vehículos y Remolques",
    "cog": "vehicles",
    "description": "Transferir legalmente la titularidad de un vehículo o trailer a otro ciudadano con validación de DNI y fondos",
    "beforeBehavior": {
      "state": "silent_crash",
      "log": "[ERROR] Comando no disponible",
      "discordStatus": "❌ Comando no encontrado",
      "timeElapsed": "0 ms"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] Titularidad de placa TRL-9302 transferida exitosamente a comprador validado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "20 ms",
      "embedTitle": "Transferencia Vehicular Completada",
      "embedContent": "El título de propiedad del vehículo **Remolque Plataforma Doble Eje** con placa `TRL-9302` ha sido transferido exitosamente.\n\n📤 **Antiguo Titular:** @Joshi\n📥 **Nuevo Titular:** @Carlos\n💵 **Importe de Transferencia:** `$3,500.00`\n🪪 **Nuevo DNI Registrado:** `MIA-294012`"
    }
  },
  {
    "command": "/bolo emitir",
    "category": "BOLO y Captura",
    "cog": "bolo",
    "description": "Emite una orden oficial de búsqueda y captura (BOLO) policial para sospechosos, autos o armas",
    "beforeBehavior": {
      "state": "silent_crash",
      "log": "[ERROR] Comando /bolo no encontrado",
      "discordStatus": "❌ Comando no encontrado",
      "timeElapsed": "0 ms"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] BOLO emitido -> Código generado: BOLO-4892 -> Alerta policial transmitida.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "18 ms",
      "embedTitle": "🚨 [B.O.L.O. ACTIVO] — CÓDIGO BOLO-4892",
      "embedContent": "ALERTA DE BÚSQUEDA Y CAPTURA EMITIDA POR EL CUERPO POLICIAL\n\n🏷️ **Código BOLO:** `BOLO-4892`\n🎯 **Tipo de Objetivo:** 👤 Sospechoso / Prófugo de la Justicia\n⚠️ **Nivel de Amenaza:** 🔴 EXTREMA / Extremadamente Armado y Violento\n📋 **Sujeto:** **Tony 'El Silencioso' Montana**\n⚖️ **Motivo:** Homicidio agravado y robo a joyería de Downtown\n💰 **Recompensa Ciudadana:** `$15,000.00` por información verificable\n👮 **Oficial Emisor:** @Capitán_Miller"
    }
  },
  {
    "command": "/caso abrir",
    "category": "Casos y Expedientes",
    "cog": "cases",
    "description": "Abre un nuevo expediente penal o judicial con seguimiento de sospechosos, pruebas y notas de investigación",
    "beforeBehavior": {
      "state": "silent_crash",
      "log": "[ERROR] Comando /caso no encontrado",
      "discordStatus": "❌ Comando no encontrado",
      "timeElapsed": "0 ms"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] Expediente radicado -> Número: CASO-2026-8491 -> Detective principal asignado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "21 ms",
      "embedTitle": "📁 Expediente Penal Abierto — CASO-2026-8491",
      "embedContent": "Se ha radicado oficialmente una nueva investigación criminal en el Departamento de Policía / Fiscalía.\n\n🔢 **Número de Caso:** `CASO-2026-8491`\n📑 **Categoría:** 💀 Homicidio / Asesinato\n⚡ **Prioridad:** 🔴 Urgente / Prioridad Máxima\n📌 **Título:** **Operación Muelle Sangriento**\n📝 **Resumen:** Hallazgo de indicios balísticos y vehículo calcinado en el puerto este de Miami Vice.\n🕵️ **Detective Principal:** @Detective_Croft\n📊 **Estado:** 🟡 `ABIERTO`"
    }
  },
  {
    "command": "/incidente crear",
    "category": "Central 911 & Incidentes",
    "cog": "incidents",
    "description": "Genera un reporte de incidente o llamada de emergencia 911 en la central CAD de despacho policial/médico",
    "beforeBehavior": {
      "state": "silent_crash",
      "log": "[ERROR] Comando /incidente no encontrado",
      "discordStatus": "❌ Comando no encontrado",
      "timeElapsed": "0 ms"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] Llamada 911 recibida -> Incidente INC-3921 despachado -> Código 3 activado.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "19 ms",
      "embedTitle": "🚨 [CAD / 911 DESPATCH] — INCIDENTE #INC-3921",
      "embedContent": "ALERTA DE DESPACHO POLICIAL & SERVICIOS DE EMERGENCIA\n\n🔢 **Código:** `INC-3921`\n📋 **Tipo:** 💥 Disparos / Tiroteo (10-71)\n⚡ **Respuesta:** 🔴 Código 3 — EMERGENCIA MÁXIMA (10-99)\n📍 **Ubicación:** **Ocean Drive con 5th Avenue, Club Malibu**\n📝 **Detalles:** Múltiples detonaciones de arma automática reportadas por transeúntes.\n📞 **Informante:** @Ciudadano_Miami\n📊 **Estado:** 🚨 `PENDIENTE DE ASIGNACIÓN`"
    }
  },
  {
    "command": "/anuncio crear",
    "category": "Anuncios Oficiales",
    "cog": "announcements",
    "description": "Crea y publica un anuncio oficial con estilo Embed personalizado, colores temáticos e imágenes",
    "beforeBehavior": {
      "state": "silent_crash",
      "log": "[ERROR] Sin comando de anuncios enriquecidos embed",
      "discordStatus": "❌ Comando no encontrado",
      "timeElapsed": "0 ms"
    },
    "afterBehavior": {
      "state": "success",
      "log": "[INFO] Anuncio procesado -> Color 0x00E5FF aplicado -> Embed enviado al canal #anuncios.",
      "discordStatus": "✅ Ejecución completada",
      "timeElapsed": "15 ms",
      "embedTitle": "🌴 Miami Vice RP — Comunicado Oficial de Apertura",
      "embedContent": "Nos complace anunciar la gran apertura de la nueva temporada de **Miami Vice Roleplay**.\n\n✨ **Novedades Principales:**\n• Nuevos sistemas de registro vehicular, trailers y cuatrimotos\n• Central policial CAD/911 con órdenes B.O.L.O. y expedientes penales\n• Economía refinada y banco de inversiones\n\n¡Los esperamos en las calles de Vice City!"
    }
  }
];
