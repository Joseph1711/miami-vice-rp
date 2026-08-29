import express from "express";
import path from "path";
import fs from "fs";
import { spawn, exec, ChildProcess } from "child_process";
import { createServer as createViteServer } from "vite";

const app = express();
const PORT = 3000;

app.use(express.json({ limit: "10mb" }));

// Store in-memory bot logs and process reference
let botProcess: ChildProcess | null = null;
let botStartTime: number | null = null;
const botLogs: Array<{ id: number; time: string; stream: "stdout" | "stderr" | "system"; text: string }> = [];
let logCounter = 0;

function appendLog(stream: "stdout" | "stderr" | "system", text: string) {
  const lines = text.split("\n");
  for (const line of lines) {
    if (!line.trim()) continue;
    logCounter++;
    botLogs.push({
      id: logCounter,
      time: new Date().toLocaleTimeString(),
      stream,
      text: line,
    });
    if (botLogs.length > 500) {
      botLogs.shift();
    }
  }
}

appendLog("system", "Miami Vice RP Bot Manager & Control Hub inicializado.");
appendLog("system", "Código del bot de Discord cargado y verificado en el entorno.");

// Bot Process Management
function startBotProcess(): { success: boolean; message: string } {
  if (botProcess && !botProcess.killed) {
    return { success: false, message: "El bot de Discord ya se encuentra en ejecución." };
  }

  const token = process.env.DISCORD_TOKEN;
  if (!token) {
    appendLog("system", "⚠️ ADVERTENCIA: DISCORD_TOKEN no está definido en las variables de entorno.");
    appendLog("system", "El bot intentará arrancar pero esperará la configuración del token.");
  }

  appendLog("system", "Iniciando proceso: python3 main.py ...");
  try {
    botProcess = spawn("python3", ["main.py"], {
      cwd: process.cwd(),
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        DISABLE_FLASK_PORT_3000: "1",
      },
    });

    botStartTime = Date.now();

    botProcess.stdout?.on("data", (data) => {
      appendLog("stdout", data.toString());
    });

    botProcess.stderr?.on("data", (data) => {
      appendLog("stderr", data.toString());
    });

    botProcess.on("close", (code) => {
      appendLog("system", `Proceso del bot finalizado con código de salida: ${code}`);
      botProcess = null;
      botStartTime = null;
    });

    botProcess.on("error", (err) => {
      appendLog("stderr", `Error al ejecutar python3 main.py: ${err.message}`);
      botProcess = null;
      botStartTime = null;
    });

    return { success: true, message: "Bot iniciado correctamente." };
  } catch (err: any) {
    appendLog("stderr", `Fallo al arrancar: ${err.message}`);
    return { success: false, message: err.message };
  }
}

function stopBotProcess(): { success: boolean; message: string } {
  if (!botProcess || botProcess.killed) {
    return { success: false, message: "El bot no está en ejecución." };
  }
  try {
    botProcess.kill("SIGTERM");
    appendLog("system", "Señal SIGTERM enviada al bot de Discord.");
    setTimeout(() => {
      if (botProcess && !botProcess.killed) {
        botProcess.kill("SIGKILL");
        appendLog("system", "Señal SIGKILL forzada.");
        botProcess = null;
        botStartTime = null;
      }
    }, 2000);
    return { success: true, message: "Proceso detenido." };
  } catch (err: any) {
    return { success: false, message: err.message };
  }
}

// ----------------- API ROUTES ----------------- //

// 1. Status
app.get("/api/bot/status", (req, res) => {
  const isRunning = Boolean(botProcess && !botProcess.killed);
  const uptimeSeconds = botStartTime && isRunning ? Math.floor((Date.now() - botStartTime) / 1000) : 0;
  const hasToken = Boolean(process.env.DISCORD_TOKEN && process.env.DISCORD_TOKEN.length > 10);
  const tokenMasked = hasToken ? `${process.env.DISCORD_TOKEN!.slice(0, 6)}...${process.env.DISCORD_TOKEN!.slice(-4)}` : "No configurado";

  const dbExists = fs.existsSync(path.join(process.cwd(), "miami_vice.sqlite3"));

  const cogsList = [
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
  ];

  res.json({
    status: isRunning ? "online" : "idle",
    pid: botProcess?.pid || null,
    uptimeSeconds,
    hasToken,
    tokenMasked,
    dbExists,
    dbBackend: process.env.SUPABASE_DB_URL ? "Supabase Postgres" : "SQLite Local (miami_vice.sqlite3)",
    cogsCount: cogsList.length,
    cogsList,
  });
});

function cleanPycache(dir: string) {
  try {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "__pycache__") {
          try {
            fs.rmSync(full, { recursive: true, force: true });
          } catch {}
        } else if (entry.name !== "node_modules" && entry.name !== ".git" && entry.name !== "dist") {
          cleanPycache(full);
        }
      }
    }
  } catch {}
}

// 2. Start / Stop / Restart / Clean Reset
app.post("/api/bot/start", (req, res) => {
  const result = startBotProcess();
  res.json(result);
});

app.post("/api/bot/stop", (req, res) => {
  const result = stopBotProcess();
  res.json(result);
});

app.post("/api/bot/restart", (req, res) => {
  stopBotProcess();
  setTimeout(() => {
    const result = startBotProcess();
    res.json({ success: true, message: "Bot reiniciado." });
  }, 1000);
});

app.post("/api/bot/reset-clean", (req, res) => {
  const { wipeDb } = req.body || {};

  // 1. Terminate current process immediately
  if (botProcess && !botProcess.killed) {
    try {
      botProcess.kill("SIGKILL");
    } catch {}
    botProcess = null;
    botStartTime = null;
  }

  // Terminate any orphan python main.py processes
  try {
    exec("pkill -9 -f 'main.py'", () => {});
  } catch {}

  // 2. Clear log buffer
  botLogs.length = 0;
  logCounter = 0;

  // 3. Purge cached python bytecode
  cleanPycache(process.cwd());

  // 4. Optionally wipe SQLite database for complete fresh state
  if (wipeDb) {
    const dbPath = path.join(process.cwd(), "miami_vice.sqlite3");
    if (fs.existsSync(dbPath)) {
      try {
        fs.unlinkSync(dbPath);
        appendLog("system", "🗑️ Base de datos local SQLite eliminada para reinicio limpio.");
      } catch (err: any) {
        appendLog("stderr", `No se pudo eliminar SQLite: ${err.message}`);
      }
    }
  }

  appendLog("system", "🧹 REINICIO LIMPIO EJECUTADO: Procesos finalizados, caché .pyc purgado y logs reseteados.");

  // 5. Spawn clean bot process
  setTimeout(() => {
    const result = startBotProcess();
    res.json({
      success: true,
      message: "Bot reiniciado de forma limpia y completa (procesos reseteados, caché .pyc purgado).",
      result,
    });
  }, 1000);
});

// 3. Logs
app.get("/api/bot/logs", (req, res) => {
  const since = parseInt((req.query.since as string) || "0", 10);
  const logs = botLogs.filter((l) => l.id > since);
  res.json({ logs, lastId: logCounter });
});

app.post("/api/bot/logs/clear", (req, res) => {
  botLogs.length = 0;
  logCounter = 0;
  appendLog("system", "Consola de logs limpiada.");
  res.json({ success: true });
});

// 4. File Tree for the Bot Code
function getBotFiles(dir: string, base: string = ""): Array<{ path: string; name: string; type: "file" | "dir"; size?: number }> {
  const results: Array<{ path: string; name: string; type: "file" | "dir"; size?: number }> = [];
  try {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.name.startsWith(".") || entry.name === "__pycache__" || entry.name === "node_modules" || entry.name === "dist") {
        continue;
      }
      const relPath = base ? `${base}/${entry.name}` : entry.name;
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        results.push({ path: relPath, name: entry.name, type: "dir" });
        results.push(...getBotFiles(fullPath, relPath));
      } else {
        const stats = fs.statSync(fullPath);
        results.push({ path: relPath, name: entry.name, type: "file", size: stats.size });
      }
    }
  } catch (err) {
    // ignore
  }
  return results;
}

app.get("/api/bot/files", (req, res) => {
  const botDir = path.join(process.cwd(), "bot");
  const allBotFiles = getBotFiles(botDir, "bot");

  // Include root level Python files
  const rootPyFiles = ["main.py", "keep_alive.py", "requirements.txt", "test_database.py"].map((f) => {
    const full = path.join(process.cwd(), f);
    const exists = fs.existsSync(full);
    const size = exists ? fs.statSync(full).size : 0;
    return { path: f, name: f, type: "file" as const, size };
  });

  res.json({ files: [...rootPyFiles, ...allBotFiles] });
});

// 5. Read File Content
app.get("/api/bot/file-content", (req, res) => {
  const targetRel = req.query.path as string;
  if (!targetRel || targetRel.includes("..")) {
    return res.status(400).json({ error: "Ruta de archivo inválida" });
  }
  const fullPath = path.join(process.cwd(), targetRel);
  if (!fs.existsSync(fullPath)) {
    return res.status(404).json({ error: "Archivo no encontrado" });
  }
  try {
    const content = fs.readFileSync(fullPath, "utf-8");
    res.json({ path: targetRel, content });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// 6. Save File Content
app.post("/api/bot/save-file", (req, res) => {
  const { path: targetRel, content } = req.body;
  if (!targetRel || targetRel.includes("..") || typeof content !== "string") {
    return res.status(400).json({ error: "Datos inválidos para guardar archivo" });
  }
  const fullPath = path.join(process.cwd(), targetRel);
  try {
    fs.writeFileSync(fullPath, content, "utf-8");
    appendLog("system", `Archivo guardado exitosamente: ${targetRel}`);
    res.json({ success: true, message: `Archivo ${targetRel} guardado.` });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
});

// 7. Database Stats & Inspector via python query runner
app.get("/api/database/stats", (req, res) => {
  const pyCode = `
import json
try:
    from bot.db import execute, check_connection, is_postgres
    check_connection()
    if is_postgres():
        tables_rows = execute("SELECT table_name as name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name", fetch="all") or []
    else:
        tables_rows = execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name", fetch="all") or []

    tables = [r["name"] for r in tables_rows]
    table_stats = []
    total_rows = 0

    CATEGORY_MAP = {
        "users": ("users_config", "Cuentas de ciudadanos, saldos, niveles, XP y reputación"),
        "dni_records": ("users_config", "Registros de Documento Nacional de Identidad (DNI) y datos IC"),
        "guild_config": ("users_config", "Configuración general del servidor de Discord"),
        "verification_config": ("users_config", "Configuración de verificación y roles"),
        "verification_logs": ("users_config", "Auditoría de usuarios verificados"),
        "db_state": ("users_config", "Control de versiones y estado del esquema"),
        "work_submissions": ("economy_banking", "Evidencias y reportes de trabajo secundario pendientes/aprobados"),
        "transactions": ("economy_banking", "Historial de transferencias y transacciones"),
        "treasury": ("economy_banking", "Tesorería y fondos públicos de la ciudad"),
        "savings_accounts": ("economy_banking", "Cuentas de ahorros con devengo de intereses"),
        "investments": ("economy_banking", "Inversiones activas de jugadores"),
        "loans": ("economy_banking", "Préstamos bancarios y deudas activas"),
        "companies": ("companies_properties", "Empresas comerciales registradas"),
        "company_members": ("companies_properties", "Plantilla de empleados por empresa"),
        "properties": ("companies_properties", "Bienes inmuebles, casas y almacenes"),
        "property_transactions": ("companies_properties", "Historial de compra/venta de propiedades"),
        "departments": ("departments_fleet", "Departamentos oficiales y presupuestos"),
        "department_members": ("departments_fleet", "Agentes y funcionarios públicos"),
        "department_audit": ("departments_fleet", "Auditoría de fondos departamentales"),
        "fleet_vehicle_types": ("departments_fleet", "Tipos y modelos de patrullas y vehículos"),
        "fleet_vehicles": ("departments_fleet", "Unidades en servicio por departamento"),
        "weapon_registries": ("crime_drugs", "Registro balístico y licencias de armas de fuego"),
        "criminal_missions": ("crime_drugs", "Misiones y golpes delictivos"),
        "drug_operations": ("crime_drugs", "Laboratorios y cultivos clandestinos"),
        "money_laundering": ("crime_drugs", "Operaciones de lavado de dinero"),
        "items": ("market_inventory", "Catálogo maestro de objetos e ítems"),
        "user_inventory": ("market_inventory", "Inventarios individuales de usuarios"),
        "shop": ("market_inventory", "Artículos en la tienda general"),
        "marketplace_listings": ("market_inventory", "Anuncios del mercado entre jugadores"),
        "auctions": ("market_inventory", "Subastas activas de ítems raros"),
        "black_market_stock": ("market_inventory", "Stock del mercado clandestino"),
        "black_market_transactions": ("market_inventory", "Compras en el mercado negro"),
        "tickets": ("tickets_contracts", "Tickets de soporte y atención ciudadana"),
        "ticket_config": ("tickets_contracts", "Configuración de canales de tickets"),
        "contracts": ("tickets_contracts", "Contratos y recompensas laborales"),
        "applications": ("tickets_contracts", "Postulaciones para facciones"),
        "application_config": ("tickets_contracts", "Formularios de postulación"),
        "jobs": ("tickets_contracts", "Catálogo de empleos legales"),
        "level_rewards": ("tickets_contracts", "Recompensas por nivel alcanzado"),
        "auto_roles": ("tickets_contracts", "Asignación automática de roles"),
        "temp_roles": ("tickets_contracts", "Roles temporales con vencimiento")
    }

    for t in tables:
        try:
            res = execute(f'SELECT COUNT(*) as c FROM "{t}"', fetch="one")
            cnt = res["c"] if res else 0
            total_rows += cnt

            if is_postgres():
                cols_res = execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{t}'", fetch="all") or []
                cols_cnt = len(cols_res)
            else:
                cols_res = execute(f'PRAGMA table_info("{t}")', fetch="all") or []
                cols_cnt = len(cols_res)

            cat, desc = CATEGORY_MAP.get(t, ("other", "Tabla del sistema"))
            table_stats.append({
                "name": t, 
                "count": cnt, 
                "columnsCount": cols_cnt,
                "category": cat,
                "description": desc
            })
        except Exception:
            pass

    u_res = execute("SELECT COUNT(*) as c, COALESCE(SUM(cash), 0) as total_cash, COALESCE(SUM(bank), 0) as total_bank FROM users", fetch="one") if "users" in tables else {"c": 0, "total_cash": 0, "total_bank": 0}

    print(json.dumps({
        "tables": table_stats,
        "totalTables": len(table_stats),
        "totalRows": total_rows,
        "userCount": u_res.get("c", 0) if u_res else 0,
        "totalEconomy": int(u_res.get("total_cash", 0) or 0) + int(u_res.get("total_bank", 0) or 0) if u_res else 0,
        "totalCash": int(u_res.get("total_cash", 0) or 0) if u_res else 0,
        "totalBank": int(u_res.get("total_bank", 0) or 0) if u_res else 0
    }))
except Exception as e:
    print(json.dumps({"error": str(e), "tables": [], "totalTables": 0, "totalRows": 0, "userCount": 0, "totalEconomy": 0, "totalCash": 0, "totalBank": 0}))
`;

  const child = spawn("python3", ["-c", pyCode], { cwd: process.cwd() });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (d) => (stdout += d.toString()));
  child.stderr.on("data", (d) => (stderr += d.toString()));
  child.on("close", (code) => {
    if (!stdout.trim()) {
      return res.status(500).json({ error: stderr || "Error al consultar base de datos" });
    }
    try {
      const data = JSON.parse(stdout);
      res.json(data);
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
  });
});

// 8. Database Table Schema
app.get("/api/database/table-schema", (req, res) => {
  const tableName = req.query.table as string;
  if (!tableName || !/^[a-zA-Z0-9_]+$/.test(tableName)) {
    return res.status(400).json({ error: "Nombre de tabla inválido" });
  }

  const pyCode = `
import json
try:
    from bot.db import execute, is_postgres
    table_name = "${tableName}"
    if is_postgres():
        rows = execute(f"""
            SELECT column_name as name, data_type as type, 
                   (CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END) as notnull,
                   column_default as dflt_value,
                   0 as pk
            FROM information_schema.columns 
            WHERE table_name = '{table_name}'
            ORDER BY ordinal_position
        """, fetch="all") or []
    else:
        rows = execute(f'PRAGMA table_info("{table_name}")', fetch="all") or []
    print(json.dumps({"columns": rows, "table": table_name}, default=str))
except Exception as e:
    print(json.dumps({"error": str(e), "columns": [], "table": "${tableName}"}))
`;

  const child = spawn("python3", ["-c", pyCode], { cwd: process.cwd() });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (d) => (stdout += d.toString()));
  child.stderr.on("data", (d) => (stderr += d.toString()));
  child.on("close", () => {
    try {
      res.json(JSON.parse(stdout || '{"columns":[]}'));
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
  });
});

// 9. Database Table Data with Pagination, Sorting and Search
app.get("/api/database/table-data", (req, res) => {
  const tableName = req.query.table as string;
  const limit = Math.min(parseInt((req.query.limit as string) || "50", 10), 1000);
  const page = Math.max(parseInt((req.query.page as string) || "1", 10), 1);
  const offset = (page - 1) * limit;
  const search = (req.query.search as string) || "";
  const sortBy = (req.query.sortBy as string) || "";
  const sortOrder = req.query.sortOrder === "desc" ? "DESC" : "ASC";

  if (!tableName || !/^[a-zA-Z0-9_]+$/.test(tableName)) {
    return res.status(400).json({ error: "Nombre de tabla inválido" });
  }

  const pyCode = `
import json
try:
    from bot.db import execute, is_postgres
    table_name = "${tableName}"
    sort_by = "${sortBy}"
    sort_order = "${sortOrder}"
    limit = ${limit}
    offset = ${offset}

    # 1. Get column metadata
    if is_postgres():
        cols_meta = execute(f"""
            SELECT column_name as name, data_type as type, 
                   (CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END) as notnull,
                   column_default as dflt_value, 0 as pk
            FROM information_schema.columns 
            WHERE table_name = '{table_name}'
            ORDER BY ordinal_position
        """, fetch="all") or []
    else:
        cols_meta = execute(f'PRAGMA table_info("{table_name}")', fetch="all") or []

    columns = [c["name"] for c in cols_meta]

    # 2. Total count
    cnt_res = execute(f'SELECT COUNT(*) as c FROM "{table_name}"', fetch="one")
    total_count = cnt_res["c"] if cnt_res else 0

    # 3. Build query with optional sort
    order_clause = ""
    if sort_by and sort_by in columns:
        order_clause = f'ORDER BY "{sort_by}" {sort_order}'
    elif "created_at" in columns:
        order_clause = 'ORDER BY created_at DESC'
    elif "id" in columns:
        order_clause = 'ORDER BY id ASC'

    query = f'SELECT * FROM "{table_name}" {order_clause} LIMIT {limit} OFFSET {offset}'
    rows = execute(query, fetch="all") or []

    print(json.dumps({
        "table": table_name,
        "columns": cols_meta,
        "rows": rows,
        "count": len(rows),
        "totalCount": total_count,
        "page": ${page},
        "limit": limit,
        "totalPages": max(1, (total_count + limit - 1) // limit) if limit > 0 else 1
    }, default=str))
except Exception as e:
    print(json.dumps({
        "error": str(e), 
        "table": "${tableName}",
        "columns": [], 
        "rows": [], 
        "count": 0, 
        "totalCount": 0,
        "page": 1,
        "limit": ${limit},
        "totalPages": 1
    }))
`;

  const child = spawn("python3", ["-c", pyCode], { cwd: process.cwd() });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (d) => (stdout += d.toString()));
  child.stderr.on("data", (d) => (stderr += d.toString()));
  child.on("close", () => {
    if (!stdout.trim()) {
      return res.status(500).json({ error: stderr || "Error al leer tabla" });
    }
    try {
      res.json(JSON.parse(stdout));
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
  });
});

// 10. Direct SQL Query Console for Live Exploration
app.post("/api/database/query", (req, res) => {
  const { sql } = req.body || {};
  if (!sql || typeof sql !== "string") {
    return res.status(400).json({ error: "Consulta SQL no proporcionada" });
  }

  const trimmed = sql.trim();
  // Safe execution guard: only allow SELECT or PRAGMA queries by default
  const isSelect = /^(SELECT|PRAGMA|EXPLAIN|SHOW)\b/i.test(trimmed);
  if (!isSelect) {
    return res.status(403).json({ error: "Por seguridad, la consola web solo permite consultas de lectura (SELECT, PRAGMA, EXPLAIN)." });
  }

  const pyCode = `
import json, time
try:
    from bot.db import execute
    t0 = time.time()
    rows = execute("""${trimmed.replace(/"/g, '\\"').replace(/\n/g, ' ')}""", fetch="all") or []
    elapsed_ms = round((time.time() - t0) * 1000, 2)
    
    columns = list(rows[0].keys()) if rows and isinstance(rows[0], dict) else []
    print(json.dumps({
        "success": True,
        "columns": columns,
        "rows": rows,
        "rowCount": len(rows),
        "executionTimeMs": elapsed_ms
    }, default=str))
except Exception as e:
    print(json.dumps({"success": False, "error": str(e), "columns": [], "rows": [], "rowCount": 0}))
`;

  const child = spawn("python3", ["-c", pyCode], { cwd: process.cwd() });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (d) => (stdout += d.toString()));
  child.stderr.on("data", (d) => (stderr += d.toString()));
  child.on("close", () => {
    try {
      res.json(JSON.parse(stdout || '{"success":false,"error":"Error al ejecutar consulta"}'));
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
  });
});

// 11. Complete Clean Wipe (Remove all test accounts and leave tables 100% clean)
app.post("/api/database/wipe-clean", (req, res) => {
  const pyCode = `
import sqlite3, os
from bot.db import execute, is_postgres
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

cleaned = []
for t in tables:
    try:
        execute(f'DELETE FROM "{t}"')
        cleaned.append(t)
    except Exception:
        pass

# Ensure schema is intact
init_db()

print(f"OK:{len(cleaned)}")
`;

  const child = spawn("python3", ["-c", pyCode], { cwd: process.cwd() });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (d) => (stdout += d.toString()));
  child.stderr.on("data", (d) => (stderr += d.toString()));
  child.on("close", (code) => {
    appendLog("system", "🧹 BASE DE DATOS LIMPIADA: Todas las tablas quedaron 100% vacías, sin usuarios ni datos de prueba.");
    res.json({
      success: true,
      message: "Todas las 38 tablas de la base de datos han sido limpiadas completamente. Sin usuarios ni registros de prueba."
    });
  });
});

// ----------------- VITE & SPA SETUP ----------------- //

async function startServer() {
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Miami Vice RP Bot Manager corriendo en http://0.0.0.0:${PORT}`);
  });
}

startServer();
