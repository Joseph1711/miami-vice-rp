import express from "express";
import path from "path";
import fs from "fs";
import { spawn, exec, ChildProcess } from "child_process";
import { createServer as createViteServer } from "vite";
import { Pool } from "pg";

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
appendLog("system", "Conexión a Supabase PostgreSQL configurada como base de datos única y exclusiva.");

// Database setup - PostgreSQL only (No SQLite)
function sanitizePgUrl(url?: string): string {
  if (!url) return "";
  return url
    .replace(/:\[([^\]]+)\]@/, ":$1@")
    .replace(/:%5B([^%]+)%5D@/i, ":$1@");
}

const DEFAULT_SUPABASE_URL = "postgresql://postgres:102093qvweerr@db.lbsmuouljgdcaxlcsnsb.supabase.co:5432/postgres";
const rawUrl = process.env.SUPABASE_DB_URL || process.env.DATABASE_URL || DEFAULT_SUPABASE_URL;
const SUPABASE_DB_URL = sanitizePgUrl(rawUrl);

const pgPool = new Pool({
  connectionString: SUPABASE_DB_URL,
  ssl: { rejectUnauthorized: false },
  max: 10,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 8000,
});

pgPool.query("SELECT 1 AS ok")
  .then(() => {
    appendLog("system", "✅ Conexión con Supabase PostgreSQL establecida y verificada.");
  })
  .catch((err) => {
    appendLog("stderr", `⚠️ Error conectando a Supabase PostgreSQL: ${err.message}`);
  });

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

  appendLog("system", "Iniciando proceso: python3 main.py con Supabase PostgreSQL...");
  try {
    botProcess = spawn("python3", ["main.py"], {
      cwd: process.cwd(),
      env: {
        ...process.env,
        SUPABASE_DB_URL,
        DATABASE_URL: SUPABASE_DB_URL,
        DB_BACKEND: "supabase",
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

    return { success: true, message: "Bot iniciado correctamente con Supabase." };
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

// ----------------- API ROUTES ----------------- //

// 1. Status
app.get("/api/bot/status", (req, res) => {
  const isRunning = Boolean(botProcess && !botProcess.killed);
  const uptimeSeconds = botStartTime && isRunning ? Math.floor((Date.now() - botStartTime) / 1000) : 0;
  const hasToken = Boolean(process.env.DISCORD_TOKEN && process.env.DISCORD_TOKEN.length > 10);
  const tokenMasked = hasToken ? `${process.env.DISCORD_TOKEN!.slice(0, 6)}...${process.env.DISCORD_TOKEN!.slice(-4)}` : "No configurado";

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
    "bot.cogs.dni",
    "bot.cogs.weapons",
    "bot.cogs.roblox",
    "bot.cogs.updates",
    "bot.cogs.vehicles",
    "bot.cogs.admin",
    "bot.cogs.help",
  ];

  res.json({
    status: isRunning ? "online" : "idle",
    pid: botProcess?.pid || null,
    uptimeSeconds,
    hasToken,
    tokenMasked,
    dbExists: true,
    dbBackend: "Supabase PostgreSQL (Exclusivo)",
    cogsCount: cogsList.length,
    cogsList,
  });
});

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
  appendLog("system", "Solicitud de reinicio del bot recibida...");
  stopBotProcess();
  setTimeout(() => {
    const result = startBotProcess();
    res.json({ success: true, message: "Bot reiniciado exitosamente.", result });
  }, 1500);
});

app.post("/api/bot/clean-reset", (req, res) => {
  appendLog("system", "🚨 INICIANDO REINICIO LIMPIO Y SINCRONIZACIÓN CON SUPABASE...");

  // 1. Force kill existing bot process
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

  appendLog("system", "🧹 REINICIO LIMPIO EJECUTADO: Procesos finalizados, caché .pyc purgado y logs reseteados.");

  // 4. Spawn clean bot process
  setTimeout(() => {
    const result = startBotProcess();
    res.json({
      success: true,
      message: "Bot reiniciado de forma limpia y conectado a Supabase PostgreSQL.",
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

// 7. Database Stats & Inspector via direct Supabase PostgreSQL
const CATEGORY_MAP: Record<string, [string, string]> = {
  users: ["users_config", "Cuentas de ciudadanos, saldos, niveles, XP y reputación"],
  dni_records: ["users_config", "Registros de Documento Nacional de Identidad (DNI) y datos IC"],
  guild_config: ["users_config", "Configuración general del servidor de Discord"],
  verification_config: ["users_config", "Configuración de verificación y roles"],
  verification_logs: ["users_config", "Auditoría de usuarios verificados"],
  db_state: ["users_config", "Control de versiones y estado del esquema"],
  work_submissions: ["economy_banking", "Evidencias y reportes de trabajo secundario pendientes/aprobados"],
  transactions: ["economy_banking", "Historial de transferencias y transacciones"],
  treasury: ["economy_banking", "Tesorería y fondos públicos de la ciudad"],
  savings_accounts: ["economy_banking", "Cuentas de ahorros con devengo de intereses"],
  investments: ["economy_banking", "Inversiones activas de jugadores"],
  loans: ["economy_banking", "Préstamos bancarios y deudas activas"],
  companies: ["companies_properties", "Empresas comerciales registradas"],
  company_members: ["companies_properties", "Plantilla de empleados por empresa"],
  properties: ["companies_properties", "Bienes inmuebles, casas y almacenes"],
  property_transactions: ["companies_properties", "Historial de compra/venta de propiedades"],
  departments: ["departments_fleet", "Departamentos oficiales y presupuestos"],
  department_members: ["departments_fleet", "Agentes y funcionarios públicos"],
  department_audit: ["departments_fleet", "Auditoría de fondos departamentales"],
  fleet_vehicle_types: ["departments_fleet", "Tipos y modelos de patrullas y vehículos"],
  fleet_vehicles: ["departments_fleet", "Unidades en servicio por departamento"],
  vehicle_registries: ["departments_fleet", "Registro y matrículas de vehículos particulares, trailers y ATVs"],
  weapon_registries: ["crime_drugs", "Registro balístico y licencias de armas de fuego"],
  criminal_missions: ["crime_drugs", "Misiones y golpes delictivos"],
  drug_operations: ["crime_drugs", "Laboratorios y cultivos clandestinos"],
  money_laundering: ["crime_drugs", "Operaciones de lavado de dinero"],
  items: ["market_inventory", "Catálogo maestro de objetos e ítems"],
  user_inventory: ["market_inventory", "Inventarios individuales de usuarios"],
  shop: ["market_inventory", "Artículos en la tienda general"],
  marketplace_listings: ["market_inventory", "Anuncios del mercado entre jugadores"],
  auctions: ["market_inventory", "Subastas activas de ítems raros"],
  black_market_stock: ["market_inventory", "Stock del mercado clandestino"],
  black_market_transactions: ["market_inventory", "Compras en el mercado negro"],
  tickets: ["tickets_contracts", "Tickets de soporte y atención ciudadana"],
  ticket_config: ["tickets_contracts", "Configuración de canales de tickets"],
  contracts: ["tickets_contracts", "Contratos y recompensas laborales"],
  applications: ["tickets_contracts", "Postulaciones para facciones"],
  application_config: ["tickets_contracts", "Formularios de postulación"],
  jobs: ["tickets_contracts", "Catálogo de empleos legales"],
  level_rewards: ["tickets_contracts", "Recompensas por nivel alcanzado"],
  auto_roles: ["tickets_contracts", "Asignación automática de roles"],
  temp_roles: ["tickets_contracts", "Roles temporales con vencimiento"],
  bot_updates_config: ["users_config", "Configuración de canales y GitHub para anuncios de actualizaciones"],
  bot_updates_history: ["users_config", "Registro histórico de actualizaciones oficiales publicadas"],
};

app.get("/api/database/stats", async (req, res) => {
  try {
    const tablesRes = await pgPool.query<{ name: string }>(
      "SELECT table_name as name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
    );
    const tables = tablesRes.rows.map((r) => r.name);

    let totalRows = 0;
    const tableStats: any[] = [];

    // Parallel count queries for tables
    await Promise.all(
      tables.map(async (t) => {
        try {
          const [cntRes, colsRes] = await Promise.all([
            pgPool.query(`SELECT COUNT(*) as c FROM "${t}"`),
            pgPool.query(
              "SELECT column_name FROM information_schema.columns WHERE table_name = $1",
              [t]
            ),
          ]);
          const cnt = parseInt(cntRes.rows[0]?.c || "0", 10);
          totalRows += cnt;
          const [cat, desc] = CATEGORY_MAP[t] || ["other", "Tabla del sistema Supabase"];
          tableStats.push({
            name: t,
            count: cnt,
            columnsCount: colsRes.rows.length,
            category: cat,
            description: desc,
          });
        } catch {
          // ignore table count error
        }
      })
    );

    tableStats.sort((a, b) => a.name.localeCompare(b.name));

    let userCount = 0;
    let totalCash = 0;
    let totalBank = 0;

    if (tables.includes("users")) {
      try {
        const uRes = await pgPool.query(
          "SELECT COUNT(*) as c, COALESCE(SUM(cash), 0) as total_cash, COALESCE(SUM(bank), 0) as total_bank FROM users"
        );
        userCount = parseInt(uRes.rows[0]?.c || "0", 10);
        totalCash = parseInt(uRes.rows[0]?.total_cash || "0", 10);
        totalBank = parseInt(uRes.rows[0]?.total_bank || "0", 10);
      } catch {}
    }

    res.json({
      tables: tableStats,
      totalTables: tableStats.length,
      totalRows,
      userCount,
      totalEconomy: totalCash + totalBank,
      totalCash,
      totalBank,
    });
  } catch (err: any) {
    res.status(500).json({
      error: err.message,
      tables: [],
      totalTables: 0,
      totalRows: 0,
      userCount: 0,
      totalEconomy: 0,
      totalCash: 0,
      totalBank: 0,
    });
  }
});

// 8. Database Table Schema
app.get("/api/database/table-schema", async (req, res) => {
  const tableName = req.query.table as string;
  if (!tableName || !/^[a-zA-Z0-9_]+$/.test(tableName)) {
    return res.status(400).json({ error: "Nombre de tabla inválido" });
  }

  try {
    const colsRes = await pgPool.query(
      `SELECT column_name as name, data_type as type, 
              (CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END) as notnull,
              column_default as dflt_value,
              0 as pk
       FROM information_schema.columns 
       WHERE table_name = $1
       ORDER BY ordinal_position`,
      [tableName]
    );
    res.json({ columns: colsRes.rows, table: tableName });
  } catch (err: any) {
    res.status(500).json({ error: err.message, columns: [], table: tableName });
  }
});

// 9. Database Table Data with Pagination, Sorting and Search
app.get("/api/database/table-data", async (req, res) => {
  const tableName = req.query.table as string;
  const limit = Math.min(parseInt((req.query.limit as string) || "50", 10), 1000);
  const page = Math.max(parseInt((req.query.page as string) || "1", 10), 1);
  const offset = (page - 1) * limit;
  const sortBy = (req.query.sortBy as string) || "";
  const sortOrder = req.query.sortOrder === "desc" ? "DESC" : "ASC";

  if (!tableName || !/^[a-zA-Z0-9_]+$/.test(tableName)) {
    return res.status(400).json({ error: "Nombre de tabla inválido" });
  }

  try {
    // 1. Column metadata
    const colsMetaRes = await pgPool.query(
      `SELECT column_name as name, data_type as type, 
              (CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END) as notnull,
              column_default as dflt_value, 0 as pk
       FROM information_schema.columns 
       WHERE table_name = $1
       ORDER BY ordinal_position`,
      [tableName]
    );
    const colsMeta = colsMetaRes.rows;
    const columns = colsMeta.map((c) => c.name);

    // 2. Total count
    const cntRes = await pgPool.query(`SELECT COUNT(*) as c FROM "${tableName}"`);
    const totalCount = parseInt(cntRes.rows[0]?.c || "0", 10);

    // 3. Build query with optional sort
    let orderClause = "";
    if (sortBy && columns.includes(sortBy)) {
      orderClause = `ORDER BY "${sortBy}" ${sortOrder}`;
    } else if (columns.includes("created_at")) {
      orderClause = "ORDER BY created_at DESC";
    } else if (columns.includes("id")) {
      orderClause = "ORDER BY id ASC";
    }

    const dataRes = await pgPool.query(
      `SELECT * FROM "${tableName}" ${orderClause} LIMIT $1 OFFSET $2`,
      [limit, offset]
    );

    res.json({
      table: tableName,
      columns: colsMeta,
      rows: dataRes.rows,
      count: dataRes.rows.length,
      totalCount,
      page,
      limit,
      totalPages: Math.max(1, Math.ceil(totalCount / limit)),
    });
  } catch (err: any) {
    res.status(500).json({
      error: err.message,
      table: tableName,
      columns: [],
      rows: [],
      count: 0,
      totalCount: 0,
      page: 1,
      limit,
      totalPages: 1,
    });
  }
});

// 10. Direct SQL Query Console for Live Exploration (Read-Only)
app.post("/api/database/query", async (req, res) => {
  const { sql } = req.body || {};
  if (!sql || typeof sql !== "string") {
    return res.status(400).json({ error: "Consulta SQL no proporcionada" });
  }

  const trimmed = sql.trim();
  const isSelect = /^(SELECT|EXPLAIN|SHOW)\b/i.test(trimmed);
  if (!isSelect) {
    return res.status(403).json({
      error: "Por seguridad, la consola web solo permite consultas de lectura (SELECT, EXPLAIN, SHOW).",
    });
  }

  try {
    const t0 = Date.now();
    const result = await pgPool.query(trimmed);
    const elapsedMs = Date.now() - t0;
    const columns = result.fields?.map((f) => f.name) || [];

    res.json({
      success: true,
      columns,
      rows: result.rows,
      rowCount: result.rows.length,
      executionTimeMs: elapsedMs,
    });
  } catch (err: any) {
    res.json({
      success: false,
      error: err.message,
      columns: [],
      rows: [],
      rowCount: 0,
    });
  }
});

// 11. Complete Clean Wipe for testing if requested
app.post("/api/database/wipe-clean", async (req, res) => {
  try {
    const tablesRes = await pgPool.query<{ name: string }>(
      "SELECT table_name as name FROM information_schema.tables WHERE table_schema = 'public'"
    );
    const tables = tablesRes.rows.map((r) => r.name);

    for (const t of tables) {
      try {
        await pgPool.query(`TRUNCATE TABLE "${t}" CASCADE`);
      } catch {
        try {
          await pgPool.query(`DELETE FROM "${t}"`);
        } catch {}
      }
    }

    appendLog("system", "🧹 SUPABASE LIMPIADO: Todas las tablas quedaron 100% vacías.");
    res.json({
      success: true,
      message: `Todas las ${tables.length} tablas de Supabase han sido limpiadas.`,
    });
  } catch (err: any) {
    res.status(500).json({ error: err.message });
  }
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
