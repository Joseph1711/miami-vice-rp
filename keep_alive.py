import os
import sys
import json
import logging
import threading
import time
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
        if not _bot_ref or not _bot_token:
            return {"ok": False, "message": "El bot no tiene DISCORD_TOKEN configurado."}
        if _bot_task and not _bot_task.done():
            return {"ok": True, "message": "El bot ya está encendido o conectándose."}
        if _bot_factory:
            _bot_ref = _bot_factory()
            if _bot_configurator:
                _bot_configurator(_bot_ref)
        task = asyncio.create_task(_bot_ref.start(_bot_token))
        task.add_done_callback(_log_finished_task)
        set_bot_task(task)
        return {"ok": True, "message": "Orden de encendido enviada."}


async def _stop_bot_from_dashboard():
    global _bot_enabled, _control_lock
    if _control_lock is None:
        _control_lock = asyncio.Lock()
    async with _control_lock:
        _bot_enabled = False
        if _bot_ref and _bot_task and not _bot_task.done():
            await _bot_ref.close()
            return {"ok": True, "message": "Bot desconectado correctamente."}
        return {"ok": True, "message": "El bot ya estaba apagado."}


def _control_bot(action):
    if _bot_loop is None or _bot_loop.is_closed():
        return {"ok": False, "message": "El ciclo de control del bot no está disponible."}
    coroutine = (
        _start_bot_from_dashboard()
        if action == "start"
        else _stop_bot_from_dashboard()
    )
    try:
        return asyncio.run_coroutine_threadsafe(coroutine, _bot_loop).result(timeout=10)
    except Exception as error:
        logger.error("Error controlando el bot desde el panel: %s", error)
        return {"ok": False, "message": "No se pudo ejecutar la orden del bot."}


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
        for t in tables_list:
            try:
                cnt = _safe_count(t)
                table_stats.append({"name": t, "count": cnt})
                total_rows += cnt
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


@app.route("/api/database/table-data")
def api_database_table_data():
    table_name = request.args.get("table", "users")
    limit = min(int(request.args.get("limit", 50)), 100)
    if not table_name.replace("_", "").isalnum():
        return jsonify({"error": "Nombre de tabla inválido"}), 400
    rows = _safe_query(f'SELECT * FROM "{table_name}" LIMIT {limit}')
    return jsonify({"rows": rows, "count": len(rows)})


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
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    # Si existe el archivo estático en dist/ (ej. assets/index.js, css, etc.)
    if path and (DIST_DIR / path).exists():
        return send_from_directory(str(DIST_DIR), path)

    # Si dist/index.html existe, servir la aplicación React moderna
    index_file = DIST_DIR / "index.html"
    if index_file.exists():
        return send_from_directory(str(DIST_DIR), "index.html")

    # Fallback si no está compilado
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
