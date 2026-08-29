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
appendLog("system", "C\xF3digo del bot de Discord cargado y verificado en el entorno.");
function startBotProcess() {
  if (botProcess && !botProcess.killed) {
    return { success: false, message: "El bot de Discord ya se encuentra en ejecuci\xF3n." };
  }
  const token = process.env.DISCORD_TOKEN;
  if (!token) {
    appendLog("system", "\u26A0\uFE0F ADVERTENCIA: DISCORD_TOKEN no est\xE1 definido en las variables de entorno.");
    appendLog("system", "El bot intentar\xE1 arrancar pero esperar\xE1 la configuraci\xF3n del token.");
  }
  appendLog("system", "Iniciando proceso: python3 main.py ...");
  try {
    botProcess = (0, import_child_process.spawn)("python3", ["main.py"], {
      cwd: process.cwd(),
      env: {
        ...process.env,
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
    return { success: true, message: "Bot iniciado correctamente." };
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
app.get("/api/bot/status", (req, res) => {
  const isRunning = Boolean(botProcess && !botProcess.killed);
  const uptimeSeconds = botStartTime && isRunning ? Math.floor((Date.now() - botStartTime) / 1e3) : 0;
  const hasToken = Boolean(process.env.DISCORD_TOKEN && process.env.DISCORD_TOKEN.length > 10);
  const tokenMasked = hasToken ? `${process.env.DISCORD_TOKEN.slice(0, 6)}...${process.env.DISCORD_TOKEN.slice(-4)}` : "No configurado";
  const dbExists = import_fs.default.existsSync(import_path.default.join(process.cwd(), "miami_vice.sqlite3"));
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
    "bot.cogs.help"
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
    cogsList
  });
});
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
  }, 1e3);
});
app.post("/api/bot/reset-clean", (req, res) => {
  const { wipeDb } = req.body || {};
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
  if (wipeDb) {
    const dbPath = import_path.default.join(process.cwd(), "miami_vice.sqlite3");
    if (import_fs.default.existsSync(dbPath)) {
      try {
        import_fs.default.unlinkSync(dbPath);
        appendLog("system", "\u{1F5D1}\uFE0F Base de datos local SQLite eliminada para reinicio limpio.");
      } catch (err) {
        appendLog("stderr", `No se pudo eliminar SQLite: ${err.message}`);
      }
    }
  }
  appendLog("system", "\u{1F9F9} REINICIO LIMPIO EJECUTADO: Procesos finalizados, cach\xE9 .pyc purgado y logs reseteados.");
  setTimeout(() => {
    const result = startBotProcess();
    res.json({
      success: true,
      message: "Bot reiniciado de forma limpia y completa (procesos reseteados, cach\xE9 .pyc purgado).",
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
    for t in tables:
        try:
            res = execute(f'SELECT COUNT(*) as c FROM "{t}"', fetch="one")
            cnt = res["c"] if res else 0
            total_rows += cnt
            table_stats.append({"name": t, "count": cnt})
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
  const child = (0, import_child_process.spawn)("python3", ["-c", pyCode], { cwd: process.cwd() });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (d) => stdout += d.toString());
  child.stderr.on("data", (d) => stderr += d.toString());
  child.on("close", (code) => {
    if (!stdout.trim()) {
      return res.status(500).json({ error: stderr || "Error al consultar base de datos" });
    }
    try {
      const data = JSON.parse(stdout);
      res.json(data);
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });
});
app.get("/api/database/table-data", (req, res) => {
  const tableName = req.query.table;
  const limit = Math.min(parseInt(req.query.limit || "50", 10), 100);
  if (!tableName || !/^[a-zA-Z0-9_]+$/.test(tableName)) {
    return res.status(400).json({ error: "Nombre de tabla inv\xE1lido" });
  }
  const pyCode = `
import json
try:
    from bot.db import execute
    rows = execute(f'SELECT * FROM "{tableName}" LIMIT ${limit}', fetch="all") or []
    print(json.dumps({"rows": rows, "count": len(rows)}, default=str))
except Exception as e:
    print(json.dumps({"error": str(e), "rows": [], "count": 0}))
`;
  const child = (0, import_child_process.spawn)("python3", ["-c", pyCode], { cwd: process.cwd() });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (d) => stdout += d.toString());
  child.stderr.on("data", (d) => stderr += d.toString());
  child.on("close", (code) => {
    if (!stdout.trim()) {
      return res.status(500).json({ error: stderr || "Error al leer tabla" });
    }
    try {
      res.json(JSON.parse(stdout));
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });
});
app.post("/api/database/seed-demo-data", (req, res) => {
  const pyCode = `
import sqlite3, uuid, datetime
conn = sqlite3.connect('miami_vice.sqlite3')
cur = conn.cursor()
now = datetime.datetime.utcnow().isoformat()

# Seed demo users with real usernames
demo_users = [
    (str(uuid.uuid4()), "123456789012345678", "999999999999999999", "Joshi_Admin", "Joshi | Fundador", 150000, 450000, 2400, 10, 500, 2000, True, now, now),
    (str(uuid.uuid4()), "234567890123456789", "999999999999999999", "Carlos_M", "Carlos Santana", 25000, 85000, 650, 4, 120, 500, True, now, now),
    (str(uuid.uuid4()), "345678901234567890", "999999999999999999", "Elena_Miami", "Elena R.", 80000, 250000, 1500, 8, 300, 15000, True, now, now)
]
for u in demo_users:
    cur.execute("""
    INSERT OR REPLACE INTO users (id, discord_id, guild_id, username, display_name, cash, bank, xp, level, reputation, dirty_money, is_verified, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, u)

# Seed default departments if none exist
cur.execute("SELECT COUNT(*) FROM departments")
dept_count = cur.fetchone()[0]
if dept_count == 0:
    depts = [
        (str(uuid.uuid4()), "999999999999999999", "Miami Police Department", "MPD", "Seguridad y orden p\xFAblico en la ciudad de Miami", 500000, None, None, now, now),
        (str(uuid.uuid4()), "999999999999999999", "Miami-Dade Fire & Rescue", "MDFR", "Atenci\xF3n m\xE9dica, emergencias y rescates", 350000, None, None, now, now),
        (str(uuid.uuid4()), "999999999999999999", "Florida Highway Patrol", "FHP", "Patrullaje estatal y carreteras de Florida", 300000, None, None, now, now),
        (str(uuid.uuid4()), "999999999999999999", "Florida Department of Transportation", "FDOT", "Mantenimiento e infraestructura vial", 200000, None, None, now, now),
        (str(uuid.uuid4()), "999999999999999999", "Miami Beach Police Department", "MBPD", "Seguridad en la costa y zonas tur\xEDsticas", 300000, None, None, now, now),
        (str(uuid.uuid4()), "999999999999999999", "Florida Department of Justice", "FDOJ", "Cortes, juicios y leyes de Florida", 250000, None, None, now, now)
    ]
    for d in depts:
        cur.execute("""
        INSERT INTO departments (id, guild_id, name, acronym, description, budget, leader_id, role_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, d)

conn.commit()
conn.close()
print("OK")
`;
  const child = (0, import_child_process.spawn)("python3", ["-c", pyCode], { cwd: process.cwd() });
  child.on("close", () => {
    appendLog("system", "Datos de prueba insertados en SQLite miami_vice.sqlite3 (usuarios con usernames y departamentos).");
    res.json({ success: true, message: "Datos demo con usuarios y departamentos cargados." });
  });
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
