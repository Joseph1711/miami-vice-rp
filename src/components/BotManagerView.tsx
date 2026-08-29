import React, { useState, useEffect, useRef } from 'react';
import { 
  Bot, 
  Play, 
  Square, 
  RotateCw, 
  Terminal, 
  CheckCircle2, 
  AlertTriangle, 
  Database, 
  Cpu, 
  Clock, 
  ShieldAlert, 
  Key, 
  Layers, 
  Trash2,
  RefreshCw,
  Server
} from 'lucide-react';

interface BotStatus {
  status: 'online' | 'idle' | 'error';
  pid: number | null;
  uptimeSeconds: number;
  hasToken: boolean;
  tokenMasked: string;
  dbExists: boolean;
  dbBackend: string;
  cogsCount: number;
  cogsList: string[];
}

interface LogEntry {
  id: number;
  time: string;
  stream: 'stdout' | 'stderr' | 'system';
  text: string;
}

export function BotManagerView() {
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [lastLogId, setLastLogId] = useState(0);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [filterStream, setFilterStream] = useState<'all' | 'stdout' | 'stderr' | 'system'>('all');
  const [autoScroll, setAutoScroll] = useState(true);
  const terminalEndRef = useRef<HTMLDivElement>(null);

  const fetchStatus = async () => {
    try {
      const res = await fetch('/api/bot/status');
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
      }
    } catch (err) {
      console.error('Error fetching status:', err);
    }
  };

  const fetchLogs = async (currentLastId: number) => {
    try {
      const res = await fetch(`/api/bot/logs?since=${currentLastId}`);
      if (res.ok) {
        const data = await res.json();
        if (data.logs && data.logs.length > 0) {
          setLogs(prev => [...prev, ...data.logs].slice(-300));
          setLastLogId(data.lastId);
        }
      }
    } catch (err) {
      console.error('Error fetching logs:', err);
    }
  };

  useEffect(() => {
    fetchStatus();
    fetchLogs(0);
    const interval = setInterval(() => {
      fetchStatus();
      setLastLogId(curId => {
        fetchLogs(curId);
        return curId;
      });
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (autoScroll) {
      terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, autoScroll]);

  const handleStart = async () => {
    setLoadingAction('start');
    try {
      await fetch('/api/bot/start', { method: 'POST' });
      await fetchStatus();
    } finally {
      setLoadingAction(null);
    }
  };

  const handleStop = async () => {
    setLoadingAction('stop');
    try {
      await fetch('/api/bot/stop', { method: 'POST' });
      await fetchStatus();
    } finally {
      setLoadingAction(null);
    }
  };

  const handleRestart = async () => {
    setLoadingAction('restart');
    try {
      await fetch('/api/bot/restart', { method: 'POST' });
      await fetchStatus();
    } finally {
      setLoadingAction(null);
    }
  };

  const handleClearLogs = async () => {
    await fetch('/api/bot/logs/clear', { method: 'POST' });
    setLogs([]);
    setLastLogId(0);
  };

  const formatUptime = (seconds: number) => {
    if (!seconds) return '0s';
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    if (hrs > 0) return `${hrs}h ${mins}m ${secs}s`;
    if (mins > 0) return `${mins}m ${secs}s`;
    return `${secs}s`;
  };

  const filteredLogs = logs.filter(l => {
    if (filterStream === 'all') return true;
    return l.stream === filterStream;
  });

  return (
    <div className="space-y-6">
      {/* Bot Runtime Banner */}
      <div className="p-5 rounded-2xl bg-gradient-to-r from-slate-900 via-slate-900/90 to-slate-950 border border-slate-800 shadow-xl">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
          <div className="flex items-start gap-4">
            <div className={`p-3.5 rounded-2xl ${
              status?.status === 'online' 
                ? 'bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 shadow-lg shadow-emerald-500/10' 
                : 'bg-amber-500/10 border border-amber-500/30 text-amber-400 shadow-lg shadow-amber-500/10'
            }`}>
              <Bot className="w-8 h-8" />
            </div>
            <div>
              <div className="flex items-center gap-3">
                <h2 className="text-xl font-bold text-white tracking-tight">
                  Miami Vice RP — Proceso Discord Bot
                </h2>
                <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold flex items-center gap-1.5 ${
                  status?.status === 'online'
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                    : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                }`}>
                  <span className={`w-2 h-2 rounded-full ${status?.status === 'online' ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}`} />
                  {status?.status === 'online' ? 'PROCESO ACTIVO' : 'EN ESPERA (STANDBY)'}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1 max-w-2xl leading-relaxed">
                El backend en Python (<code className="text-cyan-300 font-mono">main.py</code>) está completamente integrado en este entorno de trabajo con todos los Cogs (<code className="text-slate-300 font-mono">bot/cogs/</code>), helpers y base de datos SQLite/Supabase.
              </p>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2.5 flex-wrap">
            <button
              id="start-bot-btn"
              onClick={handleStart}
              disabled={status?.status === 'online' || loadingAction !== null}
              className="px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:pointer-events-none text-white font-medium text-xs flex items-center gap-2 shadow-lg shadow-emerald-600/20 transition-all cursor-pointer"
            >
              <Play className="w-4 h-4 fill-white" />
              <span>{loadingAction === 'start' ? 'Iniciando...' : 'Iniciar Bot (python3)'}</span>
            </button>

            <button
              id="restart-bot-btn"
              onClick={handleRestart}
              disabled={loadingAction !== null}
              className="px-3.5 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium text-xs flex items-center gap-2 border border-slate-700 transition-all cursor-pointer"
            >
              <RotateCw className={`w-4 h-4 ${loadingAction === 'restart' ? 'animate-spin text-cyan-400' : ''}`} />
              <span>Reiniciar</span>
            </button>

            <button
              id="stop-bot-btn"
              onClick={handleStop}
              disabled={status?.status !== 'online' || loadingAction !== null}
              className="px-3.5 py-2.5 rounded-xl bg-rose-950/40 hover:bg-rose-900/60 text-rose-300 font-medium text-xs flex items-center gap-2 border border-rose-800/60 transition-all cursor-pointer disabled:opacity-40 disabled:pointer-events-none"
            >
              <Square className="w-4 h-4" />
              <span>Detener</span>
            </button>
          </div>
        </div>

        {/* Runtime Metrics Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-6 pt-5 border-t border-slate-800/80">
          <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/60">
            <div className="text-[11px] text-slate-400 flex items-center gap-1.5 font-medium">
              <Cpu className="w-3.5 h-3.5 text-cyan-400" />
              <span>PID & Proceso</span>
            </div>
            <div className="text-sm font-mono font-semibold text-slate-200 mt-1">
              {status?.pid ? `PID: ${status.pid}` : 'Inactivo'}
            </div>
          </div>

          <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/60">
            <div className="text-[11px] text-slate-400 flex items-center gap-1.5 font-medium">
              <Clock className="w-3.5 h-3.5 text-indigo-400" />
              <span>Tiempo de Actividad</span>
            </div>
            <div className="text-sm font-mono font-semibold text-slate-200 mt-1">
              {formatUptime(status?.uptimeSeconds || 0)}
            </div>
          </div>

          <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/60">
            <div className="text-[11px] text-slate-400 flex items-center gap-1.5 font-medium">
              <Database className="w-3.5 h-3.5 text-emerald-400" />
              <span>Base de Datos</span>
            </div>
            <div className="text-sm font-semibold text-slate-200 mt-1 truncate">
              {status?.dbBackend || 'SQLite local'}
            </div>
          </div>

          <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/60">
            <div className="text-[11px] text-slate-400 flex items-center gap-1.5 font-medium">
              <Key className="w-3.5 h-3.5 text-amber-400" />
              <span>DISCORD_TOKEN</span>
            </div>
            <div className="text-xs font-mono font-semibold text-slate-200 mt-1 truncate">
              {status?.hasToken ? (
                <span className="text-emerald-400 flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> Configurado
                </span>
              ) : (
                <span className="text-amber-400 flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" /> Pendiente en .env
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Cogs & Modules Loaded */}
      <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 text-xs text-slate-300">
          <Layers className="w-4 h-4 text-cyan-400 shrink-0" />
          <span className="font-semibold text-white">13 Cogs y Módulos de Comandos en el Bot:</span>
          <span className="text-slate-400">economy, bank, crimen, inventory, marketplace, departments, companies, properties, tickets...</span>
        </div>
        <div className="flex items-center gap-2 text-xs font-mono text-cyan-400 bg-cyan-950/40 px-2.5 py-1 rounded-lg border border-cyan-800/40 self-start md:self-auto">
          <span>{status?.cogsCount || 13} Extensiones Listas</span>
        </div>
      </div>

      {/* Live Log Terminal */}
      <div className="rounded-2xl bg-slate-950 border border-slate-800 overflow-hidden shadow-2xl">
        {/* Terminal Header */}
        <div className="px-4 py-3 bg-slate-900 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-full bg-rose-500/80" />
              <div className="w-3 h-3 rounded-full bg-amber-500/80" />
              <div className="w-3 h-3 rounded-full bg-emerald-500/80" />
            </div>
            <div className="h-4 w-[1px] bg-slate-700 mx-1" />
            <Terminal className="w-4 h-4 text-slate-400" />
            <span className="text-xs font-mono font-bold text-slate-200">
              discord-bot@miami-vice:~$ python3 main.py (Live Logs)
            </span>
          </div>

          <div className="flex items-center gap-2">
            {/* Log Stream Filter */}
            <div className="flex rounded-lg bg-slate-950 p-0.5 border border-slate-800 text-[11px] font-mono">
              {(['all', 'stdout', 'stderr', 'system'] as const).map(f => (
                <button
                  key={f}
                  onClick={() => setFilterStream(f)}
                  className={`px-2 py-0.5 rounded capitalize transition-all ${
                    filterStream === f 
                      ? 'bg-cyan-500/20 text-cyan-300 font-bold' 
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>

            <button
              onClick={() => setAutoScroll(!autoScroll)}
              className={`px-2 py-1 rounded text-[11px] font-mono border transition-all ${
                autoScroll 
                  ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30' 
                  : 'bg-slate-800 text-slate-400 border-slate-700'
              }`}
            >
              Auto-scroll: {autoScroll ? 'ON' : 'OFF'}
            </button>

            <button
              onClick={handleClearLogs}
              title="Limpiar logs"
              className="p-1.5 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-all"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Terminal Body */}
        <div className="p-4 font-mono text-xs h-96 overflow-y-auto bg-slate-950 space-y-1.5 select-text">
          {filteredLogs.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-slate-500 space-y-2">
              <Terminal className="w-8 h-8 opacity-40" />
              <p>No hay mensajes en el registro. Inicia el bot para ver la salida en tiempo real.</p>
            </div>
          ) : (
              filteredLogs.map((l, index) => (
                <div key={`${l.id}-${index}`} className="flex items-start gap-2.5 hover:bg-slate-900/40 px-1 py-0.5 rounded transition-colors leading-relaxed">
                <span className="text-slate-600 text-[10px] select-none shrink-0 pt-0.5">{l.time}</span>
                <span className={`text-[10px] px-1 rounded uppercase font-bold select-none shrink-0 ${
                  l.stream === 'stdout' 
                    ? 'bg-cyan-950 text-cyan-400 border border-cyan-800/50' 
                    : l.stream === 'stderr' 
                    ? 'bg-rose-950 text-rose-400 border border-rose-800/50'
                    : 'bg-indigo-950 text-indigo-400 border border-indigo-800/50'
                }`}>
                  {l.stream}
                </span>
                <span className={`break-all ${
                  l.stream === 'stderr' ? 'text-rose-300' : l.stream === 'system' ? 'text-indigo-300' : 'text-slate-200'
                }`}>
                  {l.text}
                </span>
              </div>
            ))
          )}
          <div ref={terminalEndRef} />
        </div>
      </div>
    </div>
  );
}
