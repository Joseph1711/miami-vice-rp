import asyncio
import json
import logging
import threading
import time
from flask import Flask, jsonify, request

from bot.db import execute

app = Flask(__name__)
_bot_ref = None
_bot_loop = None
_bot_task = None
_bot_token = None
_bot_factory = None
_bot_configurator = None
_bot_enabled = True
_control_lock = None
logger = logging.getLogger("dashboard")

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
    """Read public server information for the dashboard without exposing player data."""
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


PAGE = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Miami Vice • Central</title>
  <style>
    :root { --bg:#09051c; --panel:#121027e8; --cyan:#00e5ff; --pink:#ff2d95; --gold:#ffd166; --muted:#b9b2d6; }
    * { box-sizing:border-box; } body { margin:0; min-height:100vh; color:#f5f3ff; font-family:Inter,system-ui,sans-serif; background:radial-gradient(circle at 80% 5%,#ff2d9533,transparent 27%),linear-gradient(135deg,var(--bg),#17102f 60%,#2b0b35); }
    .shell { width:min(1080px,100%); margin:auto; padding:36px 20px 56px; } .top { display:flex; justify-content:space-between; gap:24px; align-items:flex-start; }
    .eyebrow { color:var(--pink); font-size:.72rem; letter-spacing:.22em; font-weight:800; text-transform:uppercase; } h1 { color:var(--cyan); font-size:clamp(2.5rem,7vw,5rem); line-height:.9; margin:12px 0 15px; text-shadow:0 0 22px #00e5ff66; }
    .intro { color:var(--muted); max-width:650px; line-height:1.6; font-size:1.05rem; margin:0; } .badge { color:var(--cyan); border:1px solid #00e5ff66; border-radius:99px; padding:10px 14px; font-size:.75rem; font-weight:800; white-space:nowrap; }
     .stats { display:grid; grid-template-columns:repeat(6,1fr); gap:12px; margin:30px 0 18px; } .card { background:var(--panel); border:1px solid #00e5ff2e; border-radius:18px; padding:20px; box-shadow:0 12px 40px #0003; }
    .label { color:var(--muted); font-size:.68rem; letter-spacing:.14em; text-transform:uppercase; } .value { font-size:1.65rem; font-weight:850; margin-top:8px; }
    .tabs { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:15px; } button { color:var(--muted); background:#121027cc; border:1px solid #ffffff1c; border-radius:99px; cursor:pointer; padding:10px 14px; font:inherit; font-size:.82rem; } button.active,button:hover { color:var(--bg); background:var(--cyan); border-color:var(--cyan); }
     .panel { display:none; } .panel.active { display:block; } .command-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; } .command-card { background:#12102799; border:1px solid #ff2d9533; border-radius:14px; padding:17px; }
    .command-card h3 { color:var(--gold); font-size:.95rem; margin:0 0 11px; } .command { display:block; color:#f5f3ff; background:#09051c; border-radius:8px; margin:6px 0; padding:8px 10px; font: .78rem ui-monospace,monospace; }
    .agency { margin-bottom:14px; } .agency-head { display:flex; align-items:center; justify-content:space-between; gap:12px; } .agency h3 { color:var(--cyan); margin:0; } .agency p { color:var(--muted); font-size:.86rem; margin:7px 0 14px; } .count { color:var(--pink); font-size:.78rem; font-weight:800; }
    .cars { display:grid; grid-template-columns:repeat(3,1fr); gap:9px; } .car { background:#09051c; border-radius:10px; padding:11px; font-size:.8rem; } .car small { display:block; color:var(--muted); margin-top:4px; }
     .overview-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; } .metric { min-height:108px; } .metric .value { color:var(--cyan); } .live-note { color:var(--muted); font-size:.75rem; margin:0 0 16px; } .live-dot { display:inline-block; width:7px; height:7px; border-radius:50%; background:#42f59b; margin-right:6px; box-shadow:0 0 10px #42f59b; } .updated { color:#42f59b; }
      .bot-control { margin:0 0 16px; } .control-head { display:flex; align-items:center; justify-content:space-between; gap:16px; } .control-head h2 { color:var(--cyan); font-size:1.15rem; margin:7px 0 0; } .control-actions { display:flex; gap:8px; flex-wrap:wrap; } .control-actions button { color:var(--bg); background:var(--cyan); border-color:var(--cyan); font-weight:800; } .control-actions button[data-action="stop"] { color:#f5f3ff; background:#ff2d9530; border-color:#ff2d9570; } .control-actions button:disabled { cursor:not-allowed; opacity:.45; } .bot-control p { color:var(--muted); font-size:.82rem; margin:13px 0 0; }
      .command-tools { display:flex; gap:10px; margin:0 0 15px; } .command-tools input { flex:1; color:#f5f3ff; background:#121027cc; border:1px solid #ffffff1c; border-radius:12px; padding:11px 14px; font:inherit; outline:none; } .command-tools input:focus { border-color:var(--cyan); box-shadow:0 0 0 3px #00e5ff1c; } .copy { float:right; color:var(--cyan); background:transparent; border:0; padding:0; font-size:.7rem; cursor:pointer; } .copy:hover { color:var(--pink); background:transparent; border:0; }
     .empty { color:var(--muted); text-align:center; padding:25px; } footer { color:#8983a8; text-align:center; font-size:.76rem; margin-top:34px; }
     @media (max-width:900px) { .stats { grid-template-columns:repeat(3,1fr); } .command-grid,.overview-grid { grid-template-columns:repeat(2,1fr); } } @media (max-width:700px) { .top { display:block; } .badge { display:inline-block; margin-top:22px; } .stats,.command-grid,.overview-grid,.cars { grid-template-columns:1fr; } .shell { padding:28px 15px 44px; } }
  </style>
</head>
<body>
  <main class="shell">
     <header class="top"><div><div class="eyebrow">South Florida Roleplay • Central</div><h1>🌴 Miami Vice</h1><p class="intro">La ciudad nunca duerme. Consulta los comandos, conoce las agencias y revisa la flota que mantiene vivo el 305.</p></div><div class="badge">MIAMI • 305</div></header>
    <section class="stats">
      <div class="card"><div class="label">Estado</div><div class="value" id="status">—</div></div>
      <div class="card"><div class="label">Servidores</div><div class="value" id="guilds">—</div></div>
      <div class="card"><div class="label">Tiempo activo</div><div class="value" id="uptime">—</div></div>
       <div class="card"><div class="label">Ping</div><div class="value" id="ping">—</div></div>
       <div class="card"><div class="label">Agencias</div><div class="value" id="agency-count">—</div></div>
       <div class="card"><div class="label">Vehículos</div><div class="value" id="vehicle-count">—</div></div>
     </section>
     <section class="card bot-control">
       <div class="control-head"><div><div class="label">Control del bot</div><h2 id="control-status">CARGANDO</h2></div><div class="control-actions"><button id="bot-start" data-action="start">Encender bot</button><button id="bot-stop" data-action="stop">Apagar bot</button></div></div>
       <p id="control-message">Puedes controlar la conexión de Discord desde este panel.</p>
     </section>
      <p class="live-note"><span class="live-dot"></span>Datos en tiempo real · última actualización: <span id="updated" class="updated">—</span></p>
     <nav class="tabs" aria-label="Secciones"><button class="active" data-tab="overview">Resumen</button><button data-tab="commands">Comandos</button><button data-tab="agencies">Agencias y flota</button></nav>
     <section id="overview" class="panel active"><div class="overview-grid" id="overview-grid"></div></section>
     <section id="commands" class="panel"><div class="command-tools"><input id="command-search" type="search" placeholder="Buscar un comando, por ejemplo: banco o propiedad" aria-label="Buscar comandos"></div><div id="command-grid" class="command-grid"></div></section>
    <section id="agencies" class="panel"><div id="agency-list"></div></section>
    <footer>Miami Vice RP • Neon nights on Ocean Drive</footer>
  </main>
  <script>
     let snapshot = {data: __DATA__, stats: __STATS__};
     const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
     function render(next) {
       snapshot = next;
       const {data, stats} = snapshot;
       document.querySelector('#status').textContent = stats.status;
       document.querySelector('#guilds').textContent = stats.guilds;
       document.querySelector('#uptime').textContent = stats.uptime;
       document.querySelector('#ping').textContent = stats.online ? `${stats.ping} ms` : '—';
       document.querySelector('#agency-count').textContent = data.overview.agencies;
       document.querySelector('#vehicle-count').textContent = data.overview.vehicles;
       document.querySelector('#updated').textContent = new Date().toLocaleTimeString('es-CO');
       document.querySelector('#control-status').textContent = stats.control_status || stats.status;
       document.querySelector('#bot-start').disabled = !stats.control_enabled || stats.control_status === 'ENCENDIDO' || stats.control_status === 'CONECTANDO';
       document.querySelector('#bot-stop').disabled = !stats.control_enabled || stats.control_status === 'APAGADO';
       document.querySelector('#overview-grid').innerHTML = [
         ['Vehículos activos', data.overview.active_vehicles, 'En servicio ahora'],
         ['Mercado activo', data.overview.active_listings, 'Publicaciones disponibles'],
         ['Propiedades libres', data.overview.available_properties, 'Disponibles para comprar'],
         ['Tickets abiertos', data.overview.open_tickets, 'Solicitudes de soporte'],
         ['Solicitudes pendientes', data.overview.pending_applications, 'Por revisar'],
         ['Comandos disponibles', Object.values(data.commands).reduce((sum, group) => sum + group.length, 0), 'Guía completa del servidor'],
       ].map(([label, value, hint]) => `<article class="card metric"><div class="label">${label}</div><div class="value">${value}</div><div class="label">${hint}</div></article>`).join('');
       const search = document.querySelector('#command-search').value.toLowerCase().trim();
       document.querySelector('#command-grid').innerHTML = Object.entries(data.commands).map(([group, commands]) => {
         const visible = commands.filter(command => !search || `${group} ${command}`.toLowerCase().includes(search));
         return visible.length ? `<article class="command-card"><h3>${esc(group)}</h3>${visible.map(command => `<span class="command">${esc(command)}<button class="copy" data-command="${esc(command)}" title="Copiar comando">Copiar</button></span>`).join('')}</article>` : '';
       }).join('') || '<div class="card empty">No encontramos comandos con esa búsqueda.</div>';
       const agencyList = document.querySelector('#agency-list');
       agencyList.innerHTML = data.agencies.length ? data.agencies.map(agency => {
         const cars = agency.fleet.length ? agency.fleet.map(car => `<div class="car">🚘 ${esc(car.vehicle)}<small>${esc(car.plate)} • ${esc(car.status)}</small></div>`).join('') : '<div class="empty">Sin vehículos registrados</div>';
         return `<article class="card agency"><div class="agency-head"><h3>${esc(agency.acronym)} • ${esc(agency.name)}</h3><span class="count">${agency.fleet.length} vehículos</span></div><p>${esc(agency.description)}</p><div class="cars">${cars}</div></article>`;
       }).join('') : '<div class="card empty">No hay agencias configuradas todavía.</div>';
     }
     render(snapshot);
     document.querySelector('#command-search').addEventListener('input', () => render(snapshot));
    document.addEventListener('click', async event => {
      const control = event.target.closest('[data-action]');
      if (control) {
        control.disabled = true;
        document.querySelector('#control-message').textContent = 'Enviando orden…';
        try {
          const response = await fetch('/bot/control', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action: control.dataset.action})});
          const result = await response.json();
          document.querySelector('#control-message').textContent = result.message;
          await refresh();
        } catch (error) {
          document.querySelector('#control-message').textContent = 'No se pudo contactar al controlador.';
        }
        return;
      }
       const button = event.target.closest('[data-command]');
       if (!button) return;
       try { await navigator.clipboard.writeText(button.dataset.command); button.textContent = 'Copiado'; setTimeout(() => button.textContent = 'Copiar', 1200); }
       catch (error) { button.textContent = 'Selecciona'; }
     });
     async function refresh() {
       try { const response = await fetch('/status', {cache:'no-store'}); if (response.ok) render(await response.json()); }
       catch (error) { document.querySelector('#updated').textContent = 'sin conexión'; }
     }
     setInterval(refresh, 5000);
    document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => {
      document.querySelectorAll('[data-tab], .panel').forEach(element => element.classList.remove('active'));
      button.classList.add('active'); document.querySelector('#' + button.dataset.tab).classList.add('active');
    }));
  </script>
</body>
</html>"""


@app.route("/healthz")
@app.route("/ping")
@app.route("/health")
def health_check():
    return jsonify({"status": "ok", "service": "miami-vice-bot", "timestamp": time.time()}), 200


@app.route("/")
@app.route("/dashboard")
def dashboard():
    return PAGE.replace("__DATA__", json.dumps(_server_data(), ensure_ascii=False)).replace("__STATS__", json.dumps(_bot_stats(), ensure_ascii=False))


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


def keep_alive():
    import os
    # Si explícitamente se desactiva Flask
    if os.environ.get("DISABLE_FLASK") == "1":
        logger.info("[KEEP_ALIVE] Servidor Flask desactivado por configuración.")
        return

    # Obtener el puerto asignado por Render o entorno (por defecto 10000 en Render Web Services o 3000)
    is_render = bool(os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID"))
    default_port = 10000 if is_render else 3000
    try:
        port = int(os.environ.get("PORT", str(default_port)))
    except (ValueError, TypeError):
        port = default_port

    # En entorno local AI Studio con Node en puerto 3000, evitar colisión si DISABLE_FLASK_PORT_3000 está activo y port es 3000
    if not is_render and os.environ.get("DISABLE_FLASK_PORT_3000") == "1" and port == 3000:
        logger.info("[KEEP_ALIVE] Servidor web principal gestionado por Express en puerto 3000.")
        return

    def _run_server():
        try:
            # Desactivar logs ruidosos de werkzeug en producción
            werkzeug_logger = logging.getLogger("werkzeug")
            werkzeug_logger.setLevel(logging.WARNING)
            app.run(host="0.0.0.0", port=port, use_reloader=False, threaded=True)
        except Exception as e:
            logger.warning(f"[KEEP_ALIVE] Error en servidor Flask (puerto {port}): {e}")

    try:
        thread = threading.Thread(target=_run_server, daemon=True)
        thread.start()
        logger.info(f"[KEEP_ALIVE] Servidor web activo en 0.0.0.0:{port} (Listo para Render & Healthchecks) ✅")
    except Exception as e:
        logger.warning(f"[KEEP_ALIVE] No se pudo iniciar hilo del servidor web: {e}")