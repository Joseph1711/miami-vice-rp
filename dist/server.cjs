var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));

// server.ts
var import_express = __toESM(require("express"), 1);
var import_path = __toESM(require("path"), 1);
var import_fs = __toESM(require("fs"), 1);
var import_child_process = require("child_process");
var import_vite = require("vite");
var import_pg = require("pg");
var app = (0, import_express.default)();
var PORT = 3e3;
app.use(import_express.default.json({ limit: "10mb" }));
var botProcess = null;
var botStartTime = null;
var botLogs = [];
var logCounter = 0;
function appendLog(stream, text) {
  const lines = text.split("\n");
  for (const line of lines) {
    if (!line.trim()) continue;
    logCounter++;
    botLogs.push({
      id: logCounter,
      time: (/* @__PURE__ */ new Date()).toLocaleTimeString(),
      stream,
      text: line
    });
    if (botLogs.length > 500) {
      botLogs.shift();
    }
  }
}
appendLog("system", "Miami Vice RP Bot Manager & Control Hub inicializado.");
appendLog("system", "Conexi\xF3n a Supabase PostgreSQL configurada como base de datos \xFAnica y exclusiva.");
function sanitizePgUrl(url) {
  if (!url) return "";
  return url.replace(/:\[([^\]]+)\]@/, ":$1@").replace(/:%5B([^%]+)%5D@/i, ":$1@");
}
var DEFAULT_SUPABASE_URL = "postgresql://postgres.lbsmuouljgdcaxlcsnsb:102093qvweerr@aws-0-us-west-2.pooler.supabase.com:6543/postgres?sslmode=require";
var rawUrl = process.env.SUPABASE_DB_URL || process.env.DATABASE_URL || DEFAULT_SUPABASE_URL;
var SUPABASE_DB_URL = sanitizePgUrl(rawUrl);
var pgPool = new import_pg.Pool({
  connectionString: SUPABASE_DB_URL,
  ssl: { rejectUnauthorized: false },
  max: 10,
  idleTimeoutMillis: 3e4,
  connectionTimeoutMillis: 8e3
});
pgPool.query("SELECT 1 AS ok").then(() => {
  appendLog("system", "\u2705 Conexi\xF3n con Supabase PostgreSQL establecida y verificada.");
}).catch((err) => {
  appendLog("stderr", `\u26A0\uFE0F Error conectando a Supabase PostgreSQL: ${err.message}`);
});
function startBotProcess() {
  if (botProcess && !botProcess.killed) {
    return { success: false, message: "El bot de Discord ya se encuentra en ejecuci\xF3n." };
  }
  const token = process.env.DISCORD_TOKEN;
  if (!token) {
    appendLog("system", "\u26A0\uFE0F ADVERTENCIA: DISCORD_TOKEN no est\xE1 definido en las variables de entorno.");
    appendLog("system", "El bot intentar\xE1 arrancar pero esperar\xE1 la configuraci\xF3n del token.");
  }
  appendLog("system", "Iniciando proceso: python3 main.py con Supabase PostgreSQL...");
  try {
    botProcess = (0, import_child_process.spawn)("python3", ["main.py"], {
      cwd: process.cwd(),
      env: {
        ...process.env,
        SUPABASE_DB_URL,
        DATABASE_URL: SUPABASE_DB_URL,
        DB_BACKEND: "supabase",
        PYTHONUNBUFFERED: "1",
        DISABLE_FLASK_PORT_3000: "1"
      }
    });
    botStartTime = Date.now();
    botProcess.stdout?.on("data", (data) => {
      appendLog("stdout", data.toString());
    });
    botProcess.stderr?.on("data", (data) => {
      appendLog("stderr", data.toString());
    });
    botProcess.on("close", (code) => {
      appendLog("system", `Proceso del bot finalizado con c\xF3digo de salida: ${code}`);
      botProcess = null;
      botStartTime = null;
    });
    botProcess.on("error", (err) => {
      appendLog("stderr", `Error al ejecutar python3 main.py: ${err.message}`);
      botProcess = null;
      botStartTime = null;
    });
    return { success: true, message: "Bot iniciado correctamente con Supabase." };
  } catch (err) {
    appendLog("stderr", `Fallo al arrancar: ${err.message}`);
    return { success: false, message: err.message };
  }
}
function stopBotProcess() {
  if (!botProcess || botProcess.killed) {
    return { success: false, message: "El bot no est\xE1 en ejecuci\xF3n." };
  }
  try {
    botProcess.kill("SIGTERM");
    appendLog("system", "Se\xF1al SIGTERM enviada al bot de Discord.");
    setTimeout(() => {
      if (botProcess && !botProcess.killed) {
        botProcess.kill("SIGKILL");
        appendLog("system", "Se\xF1al SIGKILL forzada.");
        botProcess = null;
        botStartTime = null;
      }
    }, 2e3);
    return { success: true, message: "Proceso detenido." };
  } catch (err) {
    return { success: false, message: err.message };
  }
}
function cleanPycache(dir) {
  try {
    const entries = import_fs.default.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const full = import_path.default.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "__pycache__") {
          try {
            import_fs.default.rmSync(full, { recursive: true, force: true });
          } catch {
          }
        } else if (entry.name !== "node_modules" && entry.name !== ".git" && entry.name !== "dist") {
          cleanPycache(full);
        }
      }
    }
  } catch {
  }
}
app.get("/api/bot/status", (req, res) => {
  const isRunning = Boolean(botProcess && !botProcess.killed);
  const uptimeSeconds = botStartTime && isRunning ? Math.floor((Date.now() - botStartTime) / 1e3) : 0;
  const hasToken = Boolean(process.env.DISCORD_TOKEN && process.env.DISCORD_TOKEN.length > 10);
  const tokenMasked = hasToken ? `${process.env.DISCORD_TOKEN.slice(0, 6)}...${process.env.DISCORD_TOKEN.slice(-4)}` : "No configurado";
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
    "bot.cogs.help"
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
    cogsList
  });
});
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
  appendLog("system", "\u{1F6A8} INICIANDO REINICIO LIMPIO Y SINCRONIZACI\xD3N CON SUPABASE...");
  if (botProcess && !botProcess.killed) {
    try {
      botProcess.kill("SIGKILL");
    } catch {
    }
    botProcess = null;
    botStartTime = null;
  }
  try {
    (0, import_child_process.exec)("pkill -9 -f 'main.py'", () => {
    });
  } catch {
  }
  botLogs.length = 0;
  logCounter = 0;
  cleanPycache(process.cwd());
  appendLog("system", "\u{1F9F9} REINICIO LIMPIO EJECUTADO: Procesos finalizados, cach\xE9 .pyc purgado y logs reseteados.");
  setTimeout(() => {
    const result = startBotProcess();
    res.json({
      success: true,
      message: "Bot reiniciado de forma limpia y conectado a Supabase PostgreSQL.",
      result
    });
  }, 1e3);
});
app.get("/api/bot/logs", (req, res) => {
  const since = parseInt(req.query.since || "0", 10);
  const logs = botLogs.filter((l) => l.id > since);
  res.json({ logs, lastId: logCounter });
});
app.post("/api/bot/logs/clear", (req, res) => {
  botLogs.length = 0;
  logCounter = 0;
  appendLog("system", "Consola de logs limpiada.");
  res.json({ success: true });
});
function getBotFiles(dir, base = "") {
  const results = [];
  try {
    const entries = import_fs.default.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.name.startsWith(".") || entry.name === "__pycache__" || entry.name === "node_modules" || entry.name === "dist") {
        continue;
      }
      const relPath = base ? `${base}/${entry.name}` : entry.name;
      const fullPath = import_path.default.join(dir, entry.name);
      if (entry.isDirectory()) {
        results.push({ path: relPath, name: entry.name, type: "dir" });
        results.push(...getBotFiles(fullPath, relPath));
      } else {
        const stats = import_fs.default.statSync(fullPath);
        results.push({ path: relPath, name: entry.name, type: "file", size: stats.size });
      }
    }
  } catch (err) {
  }
  return results;
}
app.get("/api/bot/files", (req, res) => {
  const botDir = import_path.default.join(process.cwd(), "bot");
  const allBotFiles = getBotFiles(botDir, "bot");
  const rootPyFiles = ["main.py", "keep_alive.py", "requirements.txt", "test_database.py"].map((f) => {
    const full = import_path.default.join(process.cwd(), f);
    const exists = import_fs.default.existsSync(full);
    const size = exists ? import_fs.default.statSync(full).size : 0;
    return { path: f, name: f, type: "file", size };
  });
  res.json({ files: [...rootPyFiles, ...allBotFiles] });
});
app.get("/api/bot/file-content", (req, res) => {
  const targetRel = req.query.path;
  if (!targetRel || targetRel.includes("..")) {
    return res.status(400).json({ error: "Ruta de archivo inv\xE1lida" });
  }
  const fullPath = import_path.default.join(process.cwd(), targetRel);
  if (!import_fs.default.existsSync(fullPath)) {
    return res.status(404).json({ error: "Archivo no encontrado" });
  }
  try {
    const content = import_fs.default.readFileSync(fullPath, "utf-8");
    res.json({ path: targetRel, content });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});
app.post("/api/bot/save-file", (req, res) => {
  const { path: targetRel, content } = req.body;
  if (!targetRel || targetRel.includes("..") || typeof content !== "string") {
    return res.status(400).json({ error: "Datos inv\xE1lidos para guardar archivo" });
  }
  const fullPath = import_path.default.join(process.cwd(), targetRel);
  try {
    import_fs.default.writeFileSync(fullPath, content, "utf-8");
    appendLog("system", `Archivo guardado exitosamente: ${targetRel}`);
    res.json({ success: true, message: `Archivo ${targetRel} guardado.` });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});
var CATEGORY_MAP = {
  users: ["users_config", "Cuentas de ciudadanos, saldos, niveles, XP y reputaci\xF3n"],
  dni_records: ["users_config", "Registros de Documento Nacional de Identidad (DNI) y datos IC"],
  guild_config: ["users_config", "Configuraci\xF3n general del servidor de Discord"],
  verification_config: ["users_config", "Configuraci\xF3n de verificaci\xF3n y roles"],
  verification_logs: ["users_config", "Auditor\xEDa de usuarios verificados"],
  db_state: ["users_config", "Control de versiones y estado del esquema"],
  work_submissions: ["economy_banking", "Evidencias y reportes de trabajo secundario pendientes/aprobados"],
  transactions: ["economy_banking", "Historial de transferencias y transacciones"],
  treasury: ["economy_banking", "Tesorer\xEDa y fondos p\xFAblicos de la ciudad"],
  savings_accounts: ["economy_banking", "Cuentas de ahorros con devengo de intereses"],
  investments: ["economy_banking", "Inversiones activas de jugadores"],
  loans: ["economy_banking", "Pr\xE9stamos bancarios y deudas activas"],
  companies: ["companies_properties", "Empresas comerciales registradas"],
  company_members: ["companies_properties", "Plantilla de empleados por empresa"],
  properties: ["companies_properties", "Bienes inmuebles, casas y almacenes"],
  property_transactions: ["companies_properties", "Historial de compra/venta de propiedades"],
  departments: ["departments_fleet", "Departamentos oficiales y presupuestos"],
  department_members: ["departments_fleet", "Agentes y funcionarios p\xFAblicos"],
  department_audit: ["departments_fleet", "Auditor\xEDa de fondos departamentales"],
  fleet_vehicle_types: ["departments_fleet", "Tipos y modelos de patrullas y veh\xEDculos"],
  fleet_vehicles: ["departments_fleet", "Unidades en servicio por departamento"],
  vehicle_registries: ["departments_fleet", "Registro y matr\xEDculas de veh\xEDculos particulares, trailers y ATVs"],
  weapon_registries: ["crime_drugs", "Registro bal\xEDstico y licencias de armas de fuego"],
  criminal_missions: ["crime_drugs", "Misiones y golpes delictivos"],
  drug_operations: ["crime_drugs", "Laboratorios y cultivos clandestinos"],
  money_laundering: ["crime_drugs", "Operaciones de lavado de dinero"],
  items: ["market_inventory", "Cat\xE1logo maestro de objetos e \xEDtems"],
  user_inventory: ["market_inventory", "Inventarios individuales de usuarios"],
  shop: ["market_inventory", "Art\xEDculos en la tienda general"],
  marketplace_listings: ["market_inventory", "Anuncios del mercado entre jugadores"],
  auctions: ["market_inventory", "Subastas activas de \xEDtems raros"],
  black_market_stock: ["market_inventory", "Stock del mercado clandestino"],
  black_market_transactions: ["market_inventory", "Compras en el mercado negro"],
  tickets: ["tickets_contracts", "Tickets de soporte y atenci\xF3n ciudadana"],
  ticket_config: ["tickets_contracts", "Configuraci\xF3n de canales de tickets"],
  contracts: ["tickets_contracts", "Contratos y recompensas laborales"],
  applications: ["tickets_contracts", "Postulaciones para facciones"],
  application_config: ["tickets_contracts", "Formularios de postulaci\xF3n"],
  jobs: ["tickets_contracts", "Cat\xE1logo de empleos legales"],
  level_rewards: ["tickets_contracts", "Recompensas por nivel alcanzado"],
  auto_roles: ["tickets_contracts", "Asignaci\xF3n autom\xE1tica de roles"],
  temp_roles: ["tickets_contracts", "Roles temporales con vencimiento"],
  bot_updates_config: ["users_config", "Configuraci\xF3n de canales y GitHub para anuncios de actualizaciones"],
  bot_updates_history: ["users_config", "Registro hist\xF3rico de actualizaciones oficiales publicadas"]
};
app.get("/api/database/stats", async (req, res) => {
  try {
    const tablesRes = await pgPool.query(
      "SELECT table_name as name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
    );
    const tables = tablesRes.rows.map((r) => r.name);
    let totalRows = 0;
    const tableStats = [];
    await Promise.all(
      tables.map(async (t) => {
        try {
          const [cntRes, colsRes] = await Promise.all([
            pgPool.query(`SELECT COUNT(*) as c FROM "${t}"`),
            pgPool.query(
              "SELECT column_name FROM information_schema.columns WHERE table_name = $1",
              [t]
            )
          ]);
          const cnt = parseInt(cntRes.rows[0]?.c || "0", 10);
          totalRows += cnt;
          const [cat, desc] = CATEGORY_MAP[t] || ["other", "Tabla del sistema Supabase"];
          tableStats.push({
            name: t,
            count: cnt,
            columnsCount: colsRes.rows.length,
            category: cat,
            description: desc
          });
        } catch {
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
      } catch {
      }
    }
    res.json({
      tables: tableStats,
      totalTables: tableStats.length,
      totalRows,
      userCount,
      totalEconomy: totalCash + totalBank,
      totalCash,
      totalBank
    });
  } catch (err) {
    res.status(500).json({
      error: err.message,
      tables: [],
      totalTables: 0,
      totalRows: 0,
      userCount: 0,
      totalEconomy: 0,
      totalCash: 0,
      totalBank: 0
    });
  }
});
app.get("/api/database/table-schema", async (req, res) => {
  const tableName = req.query.table;
  if (!tableName || !/^[a-zA-Z0-9_]+$/.test(tableName)) {
    return res.status(400).json({ error: "Nombre de tabla inv\xE1lido" });
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
  } catch (err) {
    res.status(500).json({ error: err.message, columns: [], table: tableName });
  }
});
app.get("/api/database/table-data", async (req, res) => {
  const tableName = req.query.table;
  const limit = Math.min(parseInt(req.query.limit || "50", 10), 1e3);
  const page = Math.max(parseInt(req.query.page || "1", 10), 1);
  const offset = (page - 1) * limit;
  const sortBy = req.query.sortBy || "";
  const sortOrder = req.query.sortOrder === "desc" ? "DESC" : "ASC";
  if (!tableName || !/^[a-zA-Z0-9_]+$/.test(tableName)) {
    return res.status(400).json({ error: "Nombre de tabla inv\xE1lido" });
  }
  try {
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
    const cntRes = await pgPool.query(`SELECT COUNT(*) as c FROM "${tableName}"`);
    const totalCount = parseInt(cntRes.rows[0]?.c || "0", 10);
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
      totalPages: Math.max(1, Math.ceil(totalCount / limit))
    });
  } catch (err) {
    res.status(500).json({
      error: err.message,
      table: tableName,
      columns: [],
      rows: [],
      count: 0,
      totalCount: 0,
      page: 1,
      limit,
      totalPages: 1
    });
  }
});
app.post("/api/database/query", async (req, res) => {
  const { sql } = req.body || {};
  if (!sql || typeof sql !== "string") {
    return res.status(400).json({ error: "Consulta SQL no proporcionada" });
  }
  const trimmed = sql.trim();
  const isSelect = /^(SELECT|EXPLAIN|SHOW)\b/i.test(trimmed);
  if (!isSelect) {
    return res.status(403).json({
      error: "Por seguridad, la consola web solo permite consultas de lectura (SELECT, EXPLAIN, SHOW)."
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
      executionTimeMs: elapsedMs
    });
  } catch (err) {
    res.json({
      success: false,
      error: err.message,
      columns: [],
      rows: [],
      rowCount: 0
    });
  }
});
app.post("/api/database/wipe-clean", async (req, res) => {
  try {
    const tablesRes = await pgPool.query(
      "SELECT table_name as name FROM information_schema.tables WHERE table_schema = 'public'"
    );
    const tables = tablesRes.rows.map((r) => r.name);
    for (const t of tables) {
      try {
        await pgPool.query(`TRUNCATE TABLE "${t}" CASCADE`);
      } catch {
        try {
          await pgPool.query(`DELETE FROM "${t}"`);
        } catch {
        }
      }
    }
    appendLog("system", "\u{1F9F9} SUPABASE LIMPIADO: Todas las tablas quedaron 100% vac\xEDas.");
    res.json({
      success: true,
      message: `Todas las ${tables.length} tablas de Supabase han sido limpiadas.`
    });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});
async function startServer() {
  if (process.env.NODE_ENV !== "production") {
    const vite = await (0, import_vite.createServer)({
      server: { middlewareMode: true },
      appType: "spa"
    });
    app.use(vite.middlewares);
  } else {
    const distPath = import_path.default.join(process.cwd(), "dist");
    app.use(import_express.default.static(distPath));
    app.get("*", (req, res) => {
      res.sendFile(import_path.default.join(distPath, "index.html"));
    });
  }
  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Miami Vice RP Bot Manager corriendo en http://0.0.0.0:${PORT}`);
  });
}
startServer();
//# sourceMappingURL=server.cjs.map
