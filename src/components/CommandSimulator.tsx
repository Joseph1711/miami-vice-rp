import React, { useState, useMemo } from 'react';
import { SimulatedCommand } from '../types';
import { 
  Play, 
  RotateCcw, 
  CheckCircle2, 
  XCircle, 
  Loader2, 
  Terminal, 
  MessageSquare, 
  Bot,
  Search,
  Filter,
  Sparkles,
  ChevronRight,
  ShieldCheck,
  Zap,
  Tag
} from 'lucide-react';

interface CommandSimulatorProps {
  commands: SimulatedCommand[];
}

export const CommandSimulator: React.FC<CommandSimulatorProps> = ({ commands }) => {
  const [selectedCategory, setSelectedCategory] = useState<string>('TODAS');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [activeCommand, setActiveCommand] = useState<SimulatedCommand>(commands[0]);
  const [simulationState, setSimulationState] = useState<'idle' | 'running_before' | 'running_after' | 'done_before' | 'done_after'>('idle');
  const [testMode, setTestMode] = useState<'before' | 'after'>('after');
  const [logs, setLogs] = useState<string[]>([]);

  // Extract unique categories
  const categories = useMemo(() => {
    const set = new Set<string>();
    commands.forEach(c => {
      if (c.category) set.add(c.category);
    });
    return ['TODAS', ...Array.from(set).sort()];
  }, [commands]);

  // Filter commands by category and search
  const filteredCommands = useMemo(() => {
    return commands.filter(cmd => {
      const matchCat = selectedCategory === 'TODAS' || cmd.category === selectedCategory;
      const q = searchQuery.toLowerCase().trim();
      const matchSearch = !q || 
        cmd.command.toLowerCase().includes(q) || 
        cmd.description.toLowerCase().includes(q) ||
        (cmd.category && cmd.category.toLowerCase().includes(q));
      return matchCat && matchSearch;
    });
  }, [commands, selectedCategory, searchQuery]);

  const handleRunSimulation = (mode: 'before' | 'after') => {
    setTestMode(mode);
    setLogs([`> Ejecutando comando slash ${activeCommand.command} en Discord...`]);

    if (mode === 'before') {
      setSimulationState('running_before');
      setTimeout(() => {
        setLogs(prev => [
          ...prev,
          `[0.05s] await interaction.response.defer() -> Discord muestra: "${activeCommand.beforeBehavior.discordStatus}"`,
          `[0.12s] Iniciando ejecución de tarea asíncrona en ${activeCommand.command}...`,
          `[0.25s] ${activeCommand.beforeBehavior.log}`,
          `[0.30s] 💥 Excepción no capturada! El listener @bot.event on_app_command_error fue ignorado por discord.py.`,
          `[0.45s] ⚠️ Discord no recibió followup.send(). El socket queda abierto.`,
          `[1.00s] ... interacción colgada en bucle infinito ("pensando...") hasta expiración de token de 15 min.`
        ]);
        setSimulationState('done_before');
      }, 1100);
    } else {
      setSimulationState('running_after');
      setTimeout(() => {
        setLogs(prev => [
          ...prev,
          `[0.01s] await safe_defer(interaction) -> Interacción reconocida inmediatamente en Discord`,
          `[0.03s] ${activeCommand.afterBehavior.log}`,
          `[0.04s] await interaction.followup.send(embed=...) completado exitosamente!`,
          `[${activeCommand.afterBehavior.timeElapsed}] ✨ Comando resuelto y embed renderizado en el canal de Discord.`
        ]);
        setSimulationState('done_after');
      }, 650);
    }
  };

  const handleReset = () => {
    setSimulationState('idle');
    setLogs([]);
  };

  return (
    <div className="space-y-6">
      {/* Header & Stats Banner */}
      <div className="p-5 rounded-2xl bg-gradient-to-r from-slate-900 via-indigo-950/40 to-slate-900 border border-slate-800 flex flex-wrap items-center justify-between gap-4 shadow-lg">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 font-bold">
              <Sparkles className="w-5 h-5" />
            </span>
            <div>
              <h2 className="text-base font-extrabold text-white flex items-center gap-2">
                Simulador Integral de Comandos
                <span className="px-2.5 py-0.5 rounded-full text-xs font-mono bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                  {commands.length} Comandos Disponibles
                </span>
              </h2>
              <p className="text-xs text-slate-400">
                Prueba en vivo la respuesta de cualquier comando Slash del bot y compara el comportamiento antes vs después del blindaje.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            id="btn-simulate-before"
            onClick={() => handleRunSimulation('before')}
            disabled={simulationState === 'running_before' || simulationState === 'running_after'}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-rose-500/10 text-rose-300 border border-rose-500/30 hover:bg-rose-500/20 text-xs font-semibold transition-colors disabled:opacity-50 cursor-pointer"
          >
            <Play className="w-3.5 h-3.5 text-rose-400" />
            <span>Simular Error Original</span>
          </button>
          <button
            id="btn-simulate-after"
            onClick={() => handleRunSimulation('after')}
            disabled={simulationState === 'running_before' || simulationState === 'running_after'}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-400 text-slate-950 font-bold hover:brightness-110 text-xs transition-all shadow-md shadow-emerald-500/20 disabled:opacity-50 cursor-pointer"
          >
            <Play className="w-3.5 h-3.5 text-slate-950 fill-current" />
            <span>Simular Código Reparado (Ahora)</span>
          </button>
          {simulationState !== 'idle' && (
            <button
              onClick={handleReset}
              className="p-2 rounded-xl bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-700 cursor-pointer"
              title="Reiniciar simulador"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="p-4 rounded-2xl bg-slate-900/80 border border-slate-800 space-y-3">
        <div className="flex flex-col sm:flex-row items-center gap-3">
          <div className="relative flex-1 w-full">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Buscar comando (ej: /diario, /banco, /departamento, /admin, /drogas, /empresa)..."
              className="w-full pl-10 pr-4 py-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 text-xs font-bold"
              >
                ✕
              </button>
            )}
          </div>

          <div className="flex items-center gap-2 self-start sm:self-auto text-xs text-slate-400 whitespace-nowrap">
            <Filter className="w-3.5 h-3.5 text-cyan-400" />
            <span>Mostrando: <strong className="text-white font-mono">{filteredCommands.length}</strong> de {commands.length}</span>
          </div>
        </div>

        {/* Category Pill Filters */}
        <div className="flex flex-wrap items-center gap-1.5 pt-1 border-t border-slate-800/60">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mr-1">Categorías:</span>
          {categories.map(cat => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                selectedCategory === cat
                  ? 'bg-cyan-500 text-slate-950 shadow-md shadow-cyan-500/20'
                  : 'bg-slate-800/80 text-slate-400 hover:bg-slate-800 hover:text-slate-200 border border-slate-700/60'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Commands Grid / Quick Carousel */}
        <div className="max-h-[160px] overflow-y-auto p-2 rounded-xl bg-slate-950/70 border border-slate-800/80 flex flex-wrap gap-1.5">
          {filteredCommands.length === 0 ? (
            <div className="w-full text-center py-4 text-xs text-slate-500">
              No se encontraron comandos que coincidan con "{searchQuery}".
            </div>
          ) : (
            filteredCommands.map((cmd) => {
              const isSelected = activeCommand.command === cmd.command;
              return (
                <button
                  key={cmd.command}
                  onClick={() => {
                    setActiveCommand(cmd);
                    handleReset();
                  }}
                  className={`px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-all flex items-center gap-1.5 cursor-pointer ${
                    isSelected
                      ? 'bg-cyan-500 text-slate-950 font-bold shadow-md shadow-cyan-500/20'
                      : 'bg-slate-900 text-slate-300 hover:bg-slate-800 hover:text-white border border-slate-800'
                  }`}
                  title={`${cmd.command}: ${cmd.description}`}
                >
                  <span>{cmd.command}</span>
                  {cmd.category && (
                    <span className={`text-[9px] px-1 py-0.2 rounded font-sans uppercase ${
                      isSelected ? 'bg-slate-900/30 text-slate-950' : 'bg-slate-800 text-slate-400'
                    }`}>
                      {cmd.category.split(' ')[0]}
                    </span>
                  )}
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Selected Command Card & Simulation Comparison */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Discord Client Live Preview */}
        <div className="rounded-2xl border border-slate-800 bg-slate-950 p-5 space-y-4 shadow-xl relative overflow-hidden flex flex-col justify-between">
          <div className="space-y-3">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800 text-xs text-slate-400">
              <div className="flex items-center gap-2">
                <div className="w-2.5 h-2.5 rounded-full bg-indigo-500 animate-pulse" />
                <span className="font-semibold text-slate-200">Simulador de Cliente Discord</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-[10px] text-cyan-400 font-mono">
                  {activeCommand.category || 'General'}
                </span>
                <span className="font-mono text-cyan-400 font-bold">{activeCommand.command}</span>
              </div>
            </div>

            {/* Command Description badge */}
            <div className="p-2.5 rounded-xl bg-slate-900/70 border border-slate-800/80 text-xs text-slate-300 flex items-start gap-2">
              <Tag className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-white">{activeCommand.command}</span>: {activeCommand.description}
              </div>
            </div>

            {/* User message */}
            <div className="flex items-start gap-3 pt-2">
              <div className="w-9 h-9 rounded-full bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center font-bold text-xs text-white shrink-0 shadow-md">
                U
              </div>
              <div className="space-y-1">
                <div className="flex items-baseline gap-2">
                  <span className="text-sm font-bold text-slate-200">Joshi (Usuario)</span>
                  <span className="text-[10px] text-slate-500">Hoy a las 12:48</span>
                </div>
                <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs font-mono text-cyan-300">
                  <span className="text-slate-500">/</span>
                  {activeCommand.command.replace('/', '')}
                </div>
              </div>
            </div>

            {/* Bot Response Zone */}
            <div className="pl-12 pt-1 space-y-3">
              {simulationState === 'idle' && (
                <div className="p-4 rounded-xl border border-dashed border-slate-800 text-center text-xs text-slate-500 space-y-2">
                  <p>Haz clic en los botones superiores para ejecutar este comando:</p>
                  <div className="flex items-center justify-center gap-2">
                    <span className="px-2 py-0.5 rounded bg-rose-500/10 text-rose-400 text-[10px] font-semibold">Error Original (Antes)</span>
                    <span className="text-slate-600">vs</span>
                    <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 text-[10px] font-semibold">Código Blindado (Ahora)</span>
                  </div>
                </div>
              )}

              {simulationState === 'running_before' && (
                <div className="flex items-center gap-2 text-xs text-slate-400 animate-pulse bg-slate-900/60 p-3.5 rounded-xl border border-slate-800">
                  <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
                  <span>Miami Vice Bot está pensando...</span>
                </div>
              )}

              {simulationState === 'done_before' && (
                <div className="p-4 rounded-xl bg-rose-950/30 border border-rose-800/50 space-y-2">
                  <div className="flex items-center justify-between text-rose-400 text-xs font-bold">
                    <div className="flex items-center gap-2">
                      <XCircle className="w-4 h-4" />
                      <span>Bucle Infinito / Timeout</span>
                    </div>
                    <span className="text-[10px] font-mono text-rose-300 bg-rose-900/40 px-2 py-0.5 rounded">
                      Fallo de Captura Async
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-slate-400 italic">
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-500" />
                    <span>"Miami Vice Bot está pensando..." (Permanece así indefinidamente en Discord)</span>
                  </div>
                  <p className="text-[11px] text-slate-400 border-t border-rose-900/30 pt-2 font-mono">
                    Causa: Excepción no capturada en tarea async sin responder a followup.
                  </p>
                </div>
              )}

              {simulationState === 'running_after' && (
                <div className="flex items-center gap-2 text-xs text-emerald-400 bg-slate-900/60 p-3.5 rounded-xl border border-slate-800">
                  <Loader2 className="w-4 h-4 animate-spin text-emerald-400" />
                  <span>Procesando solicitud asíncrona de forma segura...</span>
                </div>
              )}

              {simulationState === 'done_after' && (
                <div className="p-4 rounded-xl bg-slate-900 border-l-4 border-emerald-500 border-y border-r border-slate-800 space-y-2.5 shadow-lg">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Bot className="w-4 h-4 text-emerald-400" />
                      <span className="text-xs font-bold text-slate-200">Miami Vice Bot</span>
                      <span className="px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 text-[10px] font-bold">BOT</span>
                    </div>
                    <span className="text-[10px] text-emerald-400 font-mono font-semibold flex items-center gap-1">
                      <Zap className="w-3 h-3 text-amber-400 fill-amber-400" />
                      {activeCommand.afterBehavior.timeElapsed}
                    </span>
                  </div>

                  <div className="space-y-1">
                    <h4 className="text-sm font-bold text-white flex items-center gap-1.5">
                      {activeCommand.afterBehavior.embedTitle}
                    </h4>
                    <p className="text-xs text-slate-300 leading-relaxed">
                      {activeCommand.afterBehavior.embedContent}
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="pt-4 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-500">
            <span>Servidor: Miami Vice RP Official</span>
            <span className="font-mono text-cyan-400">Canal: #comandos</span>
          </div>
        </div>

        {/* Right: Live Terminal & Execution Trace */}
        <div className="rounded-2xl border border-slate-800 bg-slate-950 p-5 space-y-3 font-mono text-xs shadow-xl flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-slate-800 text-slate-400">
              <div className="flex items-center gap-2">
                <Terminal className="w-4 h-4 text-cyan-400" />
                <span className="font-semibold text-slate-200">Terminal de Logs del Bot</span>
              </div>
              <span className="text-[10px] text-slate-500">asyncio event loop</span>
            </div>

            <div className="mt-3 bg-slate-900/90 p-4 rounded-xl border border-slate-800/80 min-h-[260px] max-h-[300px] overflow-y-auto space-y-1.5 text-slate-300">
              {logs.length === 0 ? (
                <div className="text-slate-500 italic py-6 text-center">
                  Selecciona un comando y haz clic en "Simular" para ver la traza de ejecución en el event loop.
                </div>
              ) : (
                logs.map((log, i) => {
                  const isErr = log.includes('💥') || log.includes('[ERROR]') || log.includes('colapsó');
                  const isSuccess = log.includes('✨') || log.includes('exitosamente');
                  const isWarn = log.includes('⚠️') || log.includes('Timeout');
                  return (
                    <div
                      key={i}
                      className={`leading-relaxed ${
                        isErr
                          ? 'text-rose-400 font-semibold'
                          : isSuccess
                          ? 'text-emerald-300 font-semibold'
                          : isWarn
                          ? 'text-amber-300'
                          : 'text-slate-300'
                      }`}
                    >
                      {log}
                    </div>
                  );
                })
              )}
            </div>
          </div>

          <div className="pt-3 border-t border-slate-800 flex items-center justify-between text-[11px] text-slate-500">
            <span>Runtime: Python 3.11 + discord.py v2.3</span>
            <span className="text-cyan-400 font-semibold flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
              {testMode === 'after' ? 'Blindaje Activo (@bot.tree.error)' : 'Modo Original (@bot.event)'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
