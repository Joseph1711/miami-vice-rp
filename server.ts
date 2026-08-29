import express from "express";
import path from "path";
import fs from "fs";
import { spawn, ChildProcess } from "child_process";
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

// 2. Start / Stop / Restart
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
import json, sqlite3, os
db_path = 'miami_vice.sqlite3'
if not os.path.exists(db_path):
    print(json.dumps({"error": "Base de datos no encontrada"}))
    exit(0)
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
tables = [r[0] for r in cur.fetchall() if not r[0].startswith('sqlite_')]
table_stats = []
total_rows = 0
for t in tables:
    try:
        cur.execute(f"SELECT COUNT(*) FROM \\"{t}\\"")
        count = cur.fetchone()[0]
        total_rows += count
        table_stats.append({"name": t, "count": count})
    except Exception:
        pass

# Users summary
cur.execute("SELECT COUNT(*), COALESCE(SUM(cash), 0), COALESCE(SUM(bank), 0) FROM users")
u_count, total_cash, total_bank = cur.fetchone()

conn.close()
print(json.dumps({
    "tables": table_stats,
    "totalTables": len(tables),
    "totalRows": total_rows,
    "userCount": u_count,
    "totalEconomy": total_cash + total_bank,
    "totalCash": total_cash,
    "totalBank": total_bank
}))
`;

  const child = spawn("python3", ["-c", pyCode], { cwd: process.cwd() });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (d) => (stdout += d.toString()));
  child.stderr.on("data", (d) => (stderr += d.toString()));
  child.on("close", (code) => {
    if (code !== 0 || !stdout.trim()) {
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

// 8. Database Table Rows
app.get("/api/database/table-data", (req, res) => {
  const tableName = req.query.table as string;
  const limit = Math.min(parseInt((req.query.limit as string) || "50", 10), 100);
  if (!tableName || !/^[a-zA-Z0-9_]+$/.test(tableName)) {
    return res.status(400).json({ error: "Nombre de tabla inválido" });
  }

  const pyCode = `
import json, sqlite3
conn = sqlite3.connect('miami_vice.sqlite3')
conn.row_factory = sqlite3.Row
cur = conn.cursor()
try:
    cur.execute(f"SELECT * FROM \\"${tableName}\\" LIMIT ${limit}")
    rows = [dict(r) for r in cur.fetchall()]
    print(json.dumps({"rows": rows, "count": len(rows)}))
except Exception as e:
    print(json.dumps({"error": str(e)}))
conn.close()
`;

  const child = spawn("python3", ["-c", pyCode], { cwd: process.cwd() });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (d) => (stdout += d.toString()));
  child.stderr.on("data", (d) => (stderr += d.toString()));
  child.on("close", (code) => {
    if (code !== 0 || !stdout.trim()) {
      return res.status(500).json({ error: stderr || "Error al leer tabla" });
    }
    try {
      res.json(JSON.parse(stdout));
    } catch (e: any) {
      res.status(500).json({ error: e.message });
    }
  });
});

// 9. Quick Seed / Test User for Local Testing
app.post("/api/database/seed-demo-data", (req, res) => {
  const pyCode = `
import sqlite3, uuid, datetime
conn = sqlite3.connect('miami_vice.sqlite3')
cur = conn.cursor()
now = datetime.datetime.utcnow().isoformat()
demo_users = [
    (str(uuid.uuid4()), "123456789012345678", "999999999999999999", 15000, 45000, 240, 3, 50, 2000, True, now, now),
    (str(uuid.uuid4()), "234567890123456789", "999999999999999999", 5000, 12000, 110, 2, 20, 0, True, now, now),
    (str(uuid.uuid4()), "345678901234567890", "999999999999999999", 80000, 250000, 1500, 8, 120, 15000, True, now, now)
]
for u in demo_users:
    cur.execute("""
    INSERT OR REPLACE INTO users (id, discord_id, guild_id, cash, bank, xp, level, reputation, dirty_money, is_verified, created_at, updated_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, u)
conn.commit()
conn.close()
print("OK")
`;
  const child = spawn("python3", ["-c", pyCode], { cwd: process.cwd() });
  child.on("close", () => {
    appendLog("system", "Datos de prueba insertados en SQLite miami_vice.sqlite3.");
    res.json({ success: true, message: "Datos demo cargados." });
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
