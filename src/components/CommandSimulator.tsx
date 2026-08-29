import React, { useState } from 'react';
import { SimulatedCommand } from '../types';
import { Play, RotateCcw, CheckCircle2, XCircle, Loader2, Terminal, MessageSquare, Bot } from 'lucide-react';

interface CommandSimulatorProps {
  commands: SimulatedCommand[];
}

export const CommandSimulator: React.FC<CommandSimulatorProps> = ({ commands }) => {
  const [activeCommand, setActiveCommand] = useState<SimulatedCommand>(commands[0]);
  const [simulationState, setSimulationState] = useState<'idle' | 'running_before' | 'running_after' | 'done_before' | 'done_after'>('idle');
  const [testMode, setTestMode] = useState<'before' | 'after'>('after');
  const [logs, setLogs] = useState<string[]>([]);

  const handleRunSimulation = (mode: 'before' | 'after') => {
    setTestMode(mode);
    setLogs([`> Ejecutando comando slash ${activeCommand.command} en Discord...`]);

    if (mode === 'before') {
      setSimulationState('running_before');
      setTimeout(() => {
        setLogs(prev => [
          ...prev,
          `[0.05s] await interaction.response.defer() -> Discord muestra: "${activeCommand.beforeBehavior.discordStatus}"`,
          `[0.12s] Iniciando ejecución de tarea asíncrona...`,
          `[0.25s] ${activeCommand.beforeBehavior.log}`,
          `[0.30s] 💥 Excepción no capturada! El listener @bot.event on_app_command_error fue ignorado por discord.py.`,
          `[0.45s] ⚠️ Discord no recibió followup.send(). El socket queda abierto.`,
          `[1.00s] ... interacción colgada en bucle infinito ("pensando...") hasta expiración de token.`
        ]);
        setSimulationState('done_before');
      }, 1200);
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
      }, 700);
    }
  };

  const handleReset = () => {
    setSimulationState('idle');
    setLogs([]);
  };

  return (
    <div className="space-y-6">
      {/* Selector & Actions */}
      <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Comando a probar:</span>
          {commands.map((cmd) => (
            <button
              key={cmd.command}
              onClick={() => {
                setActiveCommand(cmd);
                handleReset();
              }}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-mono font-bold transition-all ${
                activeCommand.command === cmd.command
                  ? 'bg-cyan-500 text-slate-950 shadow-md shadow-cyan-500/20'
                  : 'bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white'
              }`}
            >
              {cmd.command}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => handleRunSimulation('before')}
            disabled={simulationState === 'running_before' || simulationState === 'running_after'}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-rose-500/10 text-rose-300 border border-rose-500/30 hover:bg-rose-500/20 text-xs font-semibold transition-colors disabled:opacity-50"
          >
            <Play className="w-3.5 h-3.5 text-rose-400" />
            <span>Simular Error Original (Antes)</span>
          </button>
          <button
            onClick={() => handleRunSimulation('after')}
            disabled={simulationState === 'running_before' || simulationState === 'running_after'}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-500 text-slate-950 font-bold hover:bg-emerald-400 text-xs transition-all shadow-md shadow-emerald-500/20 disabled:opacity-50"
          >
            <Play className="w-3.5 h-3.5 text-slate-950 fill-current" />
            <span>Simular Código Reparado (Ahora)</span>
          </button>
          {simulationState !== 'idle' && (
            <button
              onClick={handleReset}
              className="p-2 rounded-lg bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-700"
              title="Reiniciar simulador"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Simulator Two-Column Comparison */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Discord Client Preview */}
        <div className="rounded-2xl border border-slate-800 bg-slate-950 p-5 space-y-4 shadow-xl relative overflow-hidden">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800 text-xs text-slate-400">
            <div className="flex items-center gap-2">
              <div className="w-2.5 h-2.5 rounded-full bg-indigo-500" />
              <span className="font-semibold text-slate-200">Simulador de Cliente Discord</span>
            </div>
            <span className="font-mono text-cyan-400">{activeCommand.command}</span>
          </div>

          {/* User message */}
          <div className="flex items-start gap-3 pt-2">
            <div className="w-9 h-9 rounded-full bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center font-bold text-xs text-white shrink-0">
              U
            </div>
            <div className="space-y-1">
              <div className="flex items-baseline gap-2">
                <span className="text-sm font-bold text-slate-200">Joshi (Usuario)</span>
                <span className="text-[10px] text-slate-500">Hoy a las 12:48</span>
              </div>
              <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-900 border border-slate-800 text-xs font-mono text-cyan-300">
                <span className="text-slate-500">/</span>
                {activeCommand.command.replace('/', '')}
              </div>
            </div>
          </div>

          {/* Bot Response Zone */}
          <div className="pl-12 pt-1 space-y-3">
            {simulationState === 'idle' && (
              <div className="p-4 rounded-xl border border-dashed border-slate-800 text-center text-xs text-slate-500">
                Haz clic en "Simular Error Original" o "Simular Código Reparado" para ver el comportamiento en Discord.
              </div>
            )}

            {simulationState === 'running_before' && (
              <div className="flex items-center gap-2 text-xs text-slate-400 animate-pulse bg-slate-900/60 p-3 rounded-xl border border-slate-800">
                <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
                <span>Miami Vice Bot está pensando...</span>
              </div>
            )}

            {simulationState === 'done_before' && (
              <div className="p-4 rounded-xl bg-rose-950/30 border border-rose-800/50 space-y-2">
                <div className="flex items-center gap-2 text-rose-400 text-xs font-bold">
                  <XCircle className="w-4 h-4" />
                  <span>Bucle Infinito / Timeout</span>
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400 italic">
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-500" />
                  <span>"Miami Vice Bot está pensando..." (Permanece así indefinidamente en Discord)</span>
                </div>
                <p className="text-[11px] text-slate-400 border-t border-rose-900/30 pt-2 font-mono">
                  Razón: Excepción unhandled en evento async sin responder a followup.
                </p>
              </div>
            )}

            {simulationState === 'running_after' && (
              <div className="flex items-center gap-2 text-xs text-emerald-400 bg-slate-900/60 p-3 rounded-xl border border-slate-800">
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
                  <span className="text-[10px] text-emerald-400 font-mono font-semibold">
                    {activeCommand.afterBehavior.timeElapsed}
                  </span>
                </div>

                <div className="space-y-1">
                  <h4 className="text-sm font-bold text-white">
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

        {/* Right: Live Terminal & Execution Trace */}
        <div className="rounded-2xl border border-slate-800 bg-slate-950 p-5 space-y-3 font-mono text-xs shadow-xl flex flex-col justify-between">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800 text-slate-400">
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 text-cyan-400" />
              <span className="font-semibold text-slate-200">Terminal de Logs del Bot</span>
            </div>
            <span className="text-[10px] text-slate-500">asyncio event loop</span>
          </div>

          <div className="bg-slate-900/90 p-4 rounded-xl border border-slate-800/80 min-h-[220px] max-h-[260px] overflow-y-auto space-y-1.5 text-slate-300">
            {logs.length === 0 ? (
              <div className="text-slate-500 italic">Esperando ejecución...</div>
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

          <div className="pt-2 flex items-center justify-between text-[11px] text-slate-500">
            <span>Runtime: Python 3.11 + discord.py v2.3</span>
            <span className="text-cyan-400 font-semibold">
              {testMode === 'after' ? '🛡️ Blindaje Activo' : '⚠️ Modo Original'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
