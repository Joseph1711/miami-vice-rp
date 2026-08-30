import os
import sys
import json
import logging
import threading
import time
import asyncio
import subprocess
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, render_template_string

from bot.db import execute, check_connection, DB_PATH

app = Flask(__name__, static_folder="dist", static_url_path="")
_bot_ref = None
_bot_loop = None
_bot_task = None
_bot_token = None
_bot_factory = None
_bot_configurator = None
_bot_enabled = True
_control_lock = None
logger = logging.getLogger("dashboard")

DIST_DIR = Path(__file__).resolve().parent / "dist"

COMMAND_GROUPS = {
    "Economía": ["/balance", "/diario", "/semanal", "/trabajar", "/pagar", "/tabla", "/donar"],
    "Banco": ["/banco depositar", "/banco retirar", "/banco ahorros", "/banco prestamo", "/invertir iniciar", "/invertir info"],
    "Ciudad": ["/propiedad lista", "/propiedad comprar", "/propiedad vender", "/propiedad rentar", "/propiedad mias", "/empresa crear", "/empresa info"],
    "Mercado": ["/mercado lista", "/mercado vender", "/mercado comprar", "/mercado subasta", "/tienda explorar", "/tienda comprar", "/mercadonegro explorar"],
    "Noche": ["/drogas plantar", "/drogas cosechar", "/lavar dinero", "/misiones lista", "/contrato lista", "/contrato aceptar"],
    "Agencias": ["/departamento lista", "/departamento info", "/departamento unirse", "/flota ver", "/flota sacar", "/flota devolver"],
    "Comunidad": ["/reputacion perfil", "/reputacion dar", "/nivel", "/inventario", "/ticket abrir", "/verificar estado", "/ayuda"],
    "Administración": ["/admin configuracion ver", "/admin recompensas lista", "/adminshop lista", "/tesoro info", "/solicitar lista"],
}


def set_bot(bot, loop=None, token=None, factory=None, configurator=None):
    global _bot_ref, _bot_loop, _bot_token, _bot_factory, _bot_configurator
    _bot_ref = bot
    _bot_loop = loop
    _bot_token = token
    _bot_factory = factory
    _bot_configurator = configurator


def set_bot_task(task):
    global _bot_task
    _bot_task = task


def _log_finished_task(task):
    if not task.cancelled() and task.exception():
        logger.error("El bot se detuvo por un error: %s", task.exception())


async def _start_bot_from_dashboard():
    global _bot_enabled, _control_lock, _bot_ref
    if _control_lock is None:
        _control_lock = asyncio.Lock()
    async with _control_lock:
        _bot_enabled = True
        token = _bot_token or os.environ.get("DISCORD_TOKEN")
        if not token:
            return {"ok": False, "message": "El bot no tiene DISCORD_TOKEN configurado."}
        if _bot_task and not _bot_task.done():
            return {"ok": True, "message": "El bot ya está encendido o conectándose."}
        
        # Siempre crear una instancia nueva y limpia al encender desde el panel
        if _bot_factory:
            _bot_ref = _bot_factory()
            if _bot_configurator:
                try:
                    _bot_configurator(_bot_ref)
                except Exception as conf_err:
                    logger.warning("Configurator warning: %s", conf_err)
        elif _bot_ref is None or getattr(_bot_ref, "is_closed", lambda: False)():
            try:
                from main import MiamiViceBot, configure_bot
                _bot_ref = MiamiViceBot()
                configure_bot(_bot_ref)
            except Exception as e:
                logger.error("Error creating bot instance: %s", e)

        if not _bot_ref:
            return {"ok": False, "message": "No se pudo instanciar el cliente de Discord."}

        task = asyncio.create_task(_bot_ref.start(token))
        task.add_done_callback(_log_finished_task)
        set_bot_task(task)
        logger.info("Bot iniciado manualmente desde el panel de control.")
        return {"ok": True, "message": "Orden de encendido enviada."}


async def _stop_bot_from_dashboard():
    global _bot_enabled, _control_lock, _bot_ref, _bot_task
    if _control_lock is None:
        _control_lock = asyncio.Lock()
    async with _control_lock:
        _bot_enabled = False
        if _bot_ref and not getattr(_bot_ref, "is_closed", lambda: True)():
            try:
                await _bot_ref.close()
            except Exception as close_err:
                logger.warning("Error closing bot client: %s", close_err)
        if _bot_task and not _bot_task.done():
            _bot_task.cancel()
        _bot_ref = None
        _bot_task = None
        logger.info("Bot detenido manualmente desde el panel de control.")
        return {"ok": True, "message": "Bot desconectado correctamente."}


def _control_bot(action):
    if _bot_loop is None or _bot_loop.is_closed():
        logger.warning("Loop no disponible en _control_bot")
        return {"ok": False, "message": "El ciclo de control del bot no está disponible."}
    coroutine = (
        _start_bot_from_dashboard()
        if action == "start"
        else _stop_bot_from_dashboard()
    )
    try:
        future = asyncio.run_coroutine_threadsafe(coroutine, _bot_loop)
        return future.result(timeout=12)
    except Exception as error:
        logger.error("Error controlando el bot desde el panel: %s", error)
        return {"ok": False, "message": f"Error ejecutando orden: {error}"}


def format_uptime(seconds):
    if seconds is None:
        return "N/A"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60):02d}s"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"
    return f"{int(seconds // 86400)}d {int((seconds % 86400) // 3600)}h"


def _server_data():
    departments = _safe_query(
        "SELECT id, name, acronym, description FROM departments ORDER BY name"
    )
    fleet = _safe_query(
        """SELECT fv.plate, fv.status, fvt.name AS vehicle_name,
                  d.name AS department_name, d.acronym
           FROM fleet_vehicles fv
           JOIN fleet_vehicle_types fvt ON fvt.id=fv.vehicle_type_id
           JOIN departments d ON d.id=fv.department_id
           ORDER BY d.name, fvt.name"""
    )
    agencies = []
    for department in departments:
        agency_fleet = [
            {
                "vehicle": row["vehicle_name"],
                "plate": row["plate"],
                "status": row["status"],
            }
            for row in fleet
            if row["department_name"] == department["name"]
        ]
        agencies.append({
            "name": department["name"],
            "acronym": department["acronym"],
            "description": department.get("description") or "Agencia de la ciudad",
            "fleet": agency_fleet,
        })
    return {
        "commands": COMMAND_GROUPS,
        "agencies": agencies,
        "overview": {
            "agencies": len(agencies),
            "vehicles": len(fleet),
            "active_vehicles": len([row for row in fleet if row["status"] == "active"]),
            "open_tickets": _safe_count("tickets", "status = 'open'"),
            "active_listings": _safe_count("marketplace_listings", "status = 'active'"),
            "available_properties": _safe_count("properties", "status = 'available'"),
            "pending_applications": _safe_count("applications", "status = 'pending'"),
        },
    }


def _safe_query(query, params=None):
    try:
        return execute(query, params=params, fetch="all") or []
    except Exception as error:
        logger.warning("Dashboard query unavailable: %s", error)
        return []


def _safe_count(table, condition="TRUE"):
    rows = _safe_query(f"SELECT COUNT(*) AS total FROM {table} WHERE {condition}")
    return int(rows[0]["total"]) if rows else 0


def _live_data():
    data = _server_data()
    return {"stats": _bot_stats(), "data": data}


def _bot_stats():
    bot = _bot_ref
    ready = bool(bot and bot.is_ready())
    start_time = getattr(bot, "start_time", None)
    connecting = bool(_bot_enabled and _bot_task and not _bot_task.done())
    if ready:
        control_status = "ENCENDIDO"
    elif connecting:
        control_status = "CONECTANDO"
    else:
        control_status = "APAGADO"
    return {
        "online": ready,
        "status": "EN LÍNEA" if ready else "DESCONECTADO",
        "guilds": len(bot.guilds) if ready else 0,
        "ping": round(bot.latency * 1000) if ready else 0,
        "uptime": format_uptime(time.time() - start_time) if start_time else "N/A",
        "control_status": control_status,
        "control_enabled": bool(_bot_loop and _bot_token),
    }


# ================== HEALTH CHECK ================== #
@app.route("/healthz")
@app.route("/ping")
@app.route("/health")
def health_check():
    return jsonify({"status": "ok", "service": "miami-vice-bot", "timestamp": time.time()}), 200


# ================== API ENDPOINTS (FOR REACT SPA) ================== #
@app.route("/api/bot/status")
def api_bot_status():
    bot = _bot_ref
    ready = bool(bot and bot.is_ready())
    start_time = getattr(bot, "start_time", None)
    uptime_seconds = int(time.time() - start_time) if (ready and start_time) else 0
    token = os.environ.get("DISCORD_TOKEN", "")
    has_token = bool(token and len(token) > 10)
    token_masked = f"{token[:6]}...{token[-4:]}" if has_token else "No configurado"
    
    db_conn = check_connection()
    cogs_list = [
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
    return jsonify({
        "status": "online" if ready else "idle",
        "pid": os.getpid(),
        "uptimeSeconds": uptime_seconds,
        "hasToken": has_token,
        "tokenMasked": token_masked,
        "dbExists": db_conn.get("ok", False),
        "dbBackend": "Supabase Postgres" if os.environ.get("SUPABASE_DB_URL") else f"SQLite Local ({DB_PATH.name})",
        "cogsCount": len(cogs_list),
        "cogsList": cogs_list,
    })


@app.route("/api/bot/start", methods=["POST"])
def api_bot_start():
    result = _control_bot("start")
    return jsonify({"success": result.get("ok", False), "message": result.get("message", "")})


@app.route("/api/bot/stop", methods=["POST"])
def api_bot_stop():
    result = _control_bot("stop")
    return jsonify({"success": result.get("ok", False), "message": result.get("message", "")})


@app.route("/api/bot/restart", methods=["POST"])
def api_bot_restart():
    _control_bot("stop")
    time.sleep(1)
    result = _control_bot("start")
    return jsonify({"success": True, "message": "Bot reiniciado."})


@app.route("/api/bot/reset-clean", methods=["POST"])
def api_bot_reset_clean():
    payload = request.get_json(silent=True) or {}
    wipe_db = payload.get("wipeDb", False)
    _control_bot("stop")
    if wipe_db:
        db_file = Path(__file__).resolve().parent / "miami_vice.sqlite3"
        if db_file.exists():
            try:
                db_file.unlink()
            except Exception:
                pass
    time.sleep(1)
    _control_bot("start")
    return jsonify({"success": True, "message": "Reinicio limpio ejecutado."})


@app.route("/api/bot/logs")
def api_bot_logs():
    bot = _bot_ref
    ready = bool(bot and bot.is_ready())
    timestamp_str = time.strftime("%H:%M:%S")
    
    demo_logs = [
        {"id": 1, "time": timestamp_str, "stream": "system", "text": "Miami Vice RP Bot Manager & Control Hub inicializado."},
        {"id": 2, "time": timestamp_str, "stream": "system", "text": f"Estado del bot Discord: {'EN LÍNEA ✅' if ready else 'EN ESPERA ⏳'}"},
        {"id": 3, "time": timestamp_str, "stream": "stdout", "text": f"Base de datos activa: {check_connection().get('masked_url', 'Desconocido')}"},
    ]
    if ready:
        demo_logs.append({"id": 4, "time": timestamp_str, "stream": "stdout", "text": f"[BOT] Conectado con latencia: {round(bot.latency * 1000)}ms en {len(bot.guilds)} servidores."})
    
    return jsonify({"logs": demo_logs, "lastId": len(demo_logs)})


@app.route("/api/bot/logs/clear", methods=["POST"])
def api_bot_logs_clear():
    return jsonify({"success": True})


@app.route("/api/bot/files")
def api_bot_files():
    base_dir = Path(__file__).resolve().parent
    results = []
    
    root_files = ["main.py", "keep_alive.py", "requirements.txt", "test_database.py"]
    for f in root_files:
        p = base_dir / f
        if p.exists():
            results.append({"path": f, "name": f, "type": "file", "size": p.stat().st_size})

    bot_dir = base_dir / "bot"
    if bot_dir.exists():
        for root, dirs, files in os.walk(bot_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            rel_root = os.path.relpath(root, base_dir)
            if rel_root != ".":
                results.append({"path": rel_root.replace("\\", "/"), "name": os.path.basename(root), "type": "dir"})
            for file in sorted(files):
                if file.endswith(".py") or file.endswith(".sql") or file.endswith(".json"):
                    full_p = os.path.join(root, file)
                    rel_p = os.path.relpath(full_p, base_dir).replace("\\", "/")
                    results.append({"path": rel_p, "name": file, "type": "file", "size": os.path.getsize(full_p)})

    return jsonify({"files": results})


@app.route("/api/bot/file-content")
def api_bot_file_content():
    target_rel = request.args.get("path", "")
    if not target_rel or ".." in target_rel:
        return jsonify({"error": "Ruta de archivo inválida"}), 400
    base_dir = Path(__file__).resolve().parent
    target_path = base_dir / target_rel
    if not target_path.exists() or not target_path.is_file():
        return jsonify({"error": "Archivo no encontrado"}), 404
    try:
        content = target_path.read_text(encoding="utf-8")
        return jsonify({"path": target_rel, "content": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/bot/save-file", methods=["POST"])
def api_bot_save_file():
    payload = request.get_json(silent=True) or {}
    target_rel = payload.get("path", "")
    content = payload.get("content", "")
    if not target_rel or ".." in target_rel:
        return jsonify({"error": "Ruta inválida"}), 400
    base_dir = Path(__file__).resolve().parent
    target_path = base_dir / target_rel
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        return jsonify({"success": True, "message": "Archivo guardado exitosamente."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/database/stats")
def api_database_stats():
    try:
        from bot.db import is_postgres, check_connection
        check_connection()
        if is_postgres():
            tables_rows = _safe_query("SELECT table_name as name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name")
        else:
            tables_rows = _safe_query("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")

        tables_list = [r["name"] for r in tables_rows] if tables_rows else []
        table_stats = []
        total_rows = 0

        CATEGORY_MAP = {
            "users": ("users_config", "Cuentas bancarias y perfiles"),
            "transactions": ("economy_banking", "Historial de transferencias"),
            "savings_accounts": ("economy_banking", "Cuentas de ahorro"),
            "investments": ("economy_banking", "Portafolios de inversión"),
            "loans": ("economy_banking", "Créditos bancarios activos"),
            "treasury": ("economy_banking", "Fondos de tesorería municipal"),
            "companies": ("companies_props", "Empresas registradas"),
            "properties": ("companies_props", "Inmuebles y propiedades"),
            "departments": ("departments_fleet", "Agencias gubernamentales"),
            "fleet_vehicles": ("departments_fleet", "Vehículos de flota"),
            "drug_operations": ("crime_night", "Operaciones de sustancias"),
            "criminal_missions": ("crime_night", "Misiones de crimen organizado"),
            "money_laundering": ("crime_night", "Contratos de lavado"),
            "marketplace_listings": ("market_inventory", "Publicaciones activas"),
            "user_inventory": ("market_inventory", "Mochila e ítems de usuarios"),
            "tickets": ("tickets_contracts", "Tickets de soporte y reportes"),
            "contracts": ("tickets_contracts", "Contratos laborales y privados"),
            "applications": ("tickets_contracts", "Postulaciones a agencias"),
        }

        for t in tables_list:
            try:
                cnt = _safe_count(t)
                total_rows += cnt
                if is_postgres():
                    cols_res = _safe_query(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{t}'")
                else:
                    cols_res = _safe_query(f'PRAGMA table_info("{t}")')
                cols_cnt = len(cols_res) if cols_res else 0
                cat, desc = CATEGORY_MAP.get(t, ("other", "Tabla del sistema"))
                table_stats.append({
                    "name": t,
                    "count": cnt,
                    "columnsCount": cols_cnt,
                    "category": cat,
                    "description": desc,
                })
            except Exception:
                pass

        user_count = _safe_count("users") if "users" in tables_list else 0
        total_cash_rows = _safe_query("SELECT COALESCE(SUM(cash), 0) AS total_cash, COALESCE(SUM(bank), 0) AS total_bank FROM users") if "users" in tables_list else []
        total_cash = int(total_cash_rows[0]["total_cash"]) if total_cash_rows else 0
        total_bank = int(total_cash_rows[0]["total_bank"]) if total_cash_rows else 0

        return jsonify({
            "tables": table_stats,
            "totalTables": len(table_stats),
            "totalRows": total_rows,
            "userCount": user_count,
            "totalEconomy": total_cash + total_bank,
            "totalCash": total_cash,
            "totalBank": total_bank,
        })
    except Exception as err:
        logger.error(f"Error calculando estadísticas de BD: {err}")
        return jsonify({
            "tables": [],
            "totalTables": 0,
            "totalRows": 0,
            "userCount": 0,
            "totalEconomy": 0,
            "totalCash": 0,
            "totalBank": 0,
        })


@app.route("/api/database/table-schema")
def api_database_table_schema():
    table_name = request.args.get("table", "users")
    if not table_name.replace("_", "").isalnum():
        return jsonify({"error": "Nombre de tabla inválido"}), 400
    try:
        from bot.db import is_postgres
        if is_postgres():
            rows = _safe_query(f"""
                SELECT column_name as name, data_type as type,
                       (CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END) as notnull,
                       column_default as dflt_value, 0 as pk
                FROM information_schema.columns
                WHERE table_name = '{table_name}'
                ORDER BY ordinal_position
            """)
        else:
            rows = _safe_query(f'PRAGMA table_info("{table_name}")')
        return jsonify({"columns": rows, "table": table_name})
    except Exception as e:
        return jsonify({"error": str(e), "columns": [], "table": table_name})


@app.route("/api/database/table-data")
def api_database_table_data():
    table_name = request.args.get("table", "users")
    limit = min(int(request.args.get("limit", 50)), 1000)
    page = max(int(request.args.get("page", 1)), 1)
    offset = (page - 1) * limit
    sort_by = request.args.get("sortBy", "")
    sort_order = "DESC" if request.args.get("sortOrder", "").lower() == "desc" else "ASC"

    if not table_name.replace("_", "").isalnum():
        return jsonify({"error": "Nombre de tabla inválido"}), 400

    try:
        from bot.db import is_postgres
        if is_postgres():
            cols_meta = _safe_query(f"""
                SELECT column_name as name, data_type as type,
                       (CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END) as notnull,
                       column_default as dflt_value, 0 as pk
                FROM information_schema.columns
                WHERE table_name = '{table_name}'
                ORDER BY ordinal_position
            """)
        else:
            cols_meta = _safe_query(f'PRAGMA table_info("{table_name}")')

        columns = [c["name"] for c in cols_meta] if cols_meta else []
        cnt_res = _safe_query(f'SELECT COUNT(*) as c FROM "{table_name}"')
        total_count = int(cnt_res[0]["c"]) if cnt_res else 0

        order_clause = ""
        if sort_by and sort_by in columns:
            order_clause = f'ORDER BY "{sort_by}" {sort_order}'
        elif "created_at" in columns:
            order_clause = "ORDER BY created_at DESC"
        elif "id" in columns:
            order_clause = "ORDER BY id ASC"

        query = f'SELECT * FROM "{table_name}" {order_clause} LIMIT {limit} OFFSET {offset}'
        rows = _safe_query(query)
        total_pages = max(1, (total_count + limit - 1) // limit) if limit > 0 else 1

        return jsonify({
            "table": table_name,
            "columns": cols_meta,
            "rows": rows,
            "count": len(rows),
            "totalCount": total_count,
            "page": page,
            "limit": limit,
            "totalPages": total_pages,
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "table": table_name,
            "columns": [],
            "rows": [],
            "count": 0,
            "totalCount": 0,
            "page": 1,
            "limit": limit,
            "totalPages": 1,
        })


@app.route("/api/database/query", methods=["POST"])
def api_database_query():
    payload = request.get_json(silent=True) or {}
    sql = payload.get("sql", "").strip()
    if not sql:
        return jsonify({"error": "Consulta SQL no proporcionada"}), 400
    if not sql.upper().startswith(("SELECT", "PRAGMA", "EXPLAIN", "SHOW")):
        return jsonify({"error": "Por seguridad, la consola web solo permite consultas de lectura (SELECT, PRAGMA, EXPLAIN)."}), 403
    try:
        t0 = time.time()
        rows = _safe_query(sql)
        elapsed_ms = round((time.time() - t0) * 1000, 2)
        columns = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []
        return jsonify({
            "success": True,
            "columns": columns,
            "rows": rows,
            "rowCount": len(rows),
            "executionTimeMs": elapsed_ms,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "columns": [], "rows": [], "rowCount": 0})


@app.route("/api/database/wipe-clean", methods=["POST"])
def api_database_wipe_clean():
    try:
        from scripts.init_db import init_db
        tables = [
            'users', 'transactions', 'savings_accounts', 'investments', 'loans', 'treasury',
            'companies', 'company_members', 'properties', 'property_transactions',
            'departments', 'department_members', 'department_audit', 'fleet_vehicle_types', 'fleet_vehicles',
            'drug_operations', 'criminal_missions', 'money_laundering',
            'auctions', 'marketplace_listings', 'user_inventory', 'shop', 'black_market_stock', 'black_market_transactions', 'items', 'jobs',
            'tickets', 'ticket_config', 'contracts', 'applications', 'application_config',
            'level_rewards', 'auto_roles', 'temp_roles',
            'verification_logs', 'verification_config', 'guild_config', 'db_state'
        ]
        for t in tables:
            try:
                execute(f'DELETE FROM "{t}"')
            except Exception:
                pass
        init_db()
        return jsonify({"success": True, "message": "Base de datos restablecida a estado 100% limpio."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/status")
def status():
    return jsonify(_live_data())


@app.route("/bot/control", methods=["POST"])
def bot_control():
    payload = request.get_json(silent=True) or {}
    action = payload.get("action")
    if action not in {"start", "stop"}:
        return jsonify({"ok": False, "message": "Acción inválida. Usa start o stop."}), 400
    result = _control_bot(action)
    return jsonify(result), 200 if result["ok"] else 503


# ================== FRONTEND SERVING (REACT SPA) ================== #
@app.route("/assets/<path:filename>")
def serve_assets(filename):
    assets_dir = DIST_DIR / "assets"
    if assets_dir.exists() and (assets_dir / filename).exists():
        return send_from_directory(str(assets_dir), filename)
    return jsonify({"error": "Asset not found"}), 404


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    if path and (DIST_DIR / path).exists():
        return send_from_directory(str(DIST_DIR), path)

    index_file = DIST_DIR / "index.html"
    if index_file.exists():
        return send_from_directory(str(DIST_DIR), "index.html")

    return jsonify({
        "service": "Miami Vice RP Bot Hub",
        "status": "online",
        "api": "/api/bot/status",
        "health": "/healthz"
    })


def keep_alive():
    if os.environ.get("DISABLE_FLASK") == "1":
        logger.info("[KEEP_ALIVE] Servidor Flask desactivado por configuración.")
        return

    is_render = bool(os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID"))
    default_port = 10000 if is_render else 3000
    try:
        port = int(os.environ.get("PORT", str(default_port)))
    except (ValueError, TypeError):
        port = default_port

    if not is_render and os.environ.get("DISABLE_FLASK_PORT_3000") == "1" and port == 3000:
        logger.info("[KEEP_ALIVE] Servidor web principal gestionado por Express en puerto 3000.")
        return

    def _run_server():
        try:
            werkzeug_logger = logging.getLogger("werkzeug")
            werkzeug_logger.setLevel(logging.WARNING)
            app.run(host="0.0.0.0", port=port, use_reloader=False, threaded=True)
        except Exception as e:
            logger.warning(f"[KEEP_ALIVE] Error en servidor Flask (puerto {port}): {e}")

    try:
        thread = threading.Thread(target=_run_server, daemon=True)
        thread.start()
        logger.info(f"[KEEP_ALIVE] Panel Web & Bot Manager activo en 0.0.0.0:{port} ✅")
    except Exception as e:
        logger.warning(f"[KEEP_ALIVE] No se pudo iniciar hilo del servidor web: {e}")
