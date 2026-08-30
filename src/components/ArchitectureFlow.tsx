import React from 'react';
import { ArrowRight, CheckCircle2, XCircle, ShieldAlert, Zap, Server, MessageSquare, Database } from 'lucide-react';

export const ArchitectureFlow: React.FC = () => {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* BEFORE FLOW */}
        <div className="p-6 rounded-2xl bg-slate-950 border border-rose-900/50 space-y-4 shadow-xl relative overflow-hidden">
          <div className="flex items-center justify-between pb-3 border-b border-rose-900/30">
            <div className="flex items-center gap-2 text-rose-400 font-bold text-sm">
              <XCircle className="w-5 h-5" />
              <span>Flujo ROTO (Antes de la corrección)</span>
            </div>
            <span className="text-xs px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 font-mono">Bucle Infinito</span>
          </div>

          <div className="space-y-3 font-mono text-xs">
            {/* Step 1 */}
            <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
              <div className="text-slate-400 font-semibold flex items-center justify-between">
                <span>1. Usuario envía /diario</span>
                <span className="text-slate-500 text-[10px]">Discord API</span>
              </div>
              <p className="text-slate-300 font-sans text-xs">
                El bot ejecuta <code className="text-cyan-300">await interaction.response.defer()</code>. Discord muestra "Pensando...".
              </p>
            </div>

            <div className="flex justify-center text-slate-600">
              <ArrowRight className="w-4 h-4 rotate-90" />
            </div>

            {/* Step 2 */}
            <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
              <div className="text-slate-400 font-semibold flex items-center justify-between">
                <span>2. Operaciones asíncronas</span>
                <span className="text-slate-500 text-[10px]">asyncio loop</span>
              </div>
              <p className="text-slate-300 font-sans text-xs">
                Se ejecutan consultas DB y cálculo de cooldown con fechas tz-aware vs naive.
              </p>
            </div>

            <div className="flex justify-center text-rose-500">
              <ArrowRight className="w-4 h-4 rotate-90" />
            </div>

            {/* Step 3 - Crash */}
            <div className="p-3 rounded-xl bg-rose-950/40 border border-rose-800/80 space-y-1">
              <div className="text-rose-300 font-bold flex items-center justify-between">
                <span>💥 Excepción Silenciosa</span>
                <span className="text-rose-400 text-[10px]">TypeError / Timeout</span>
              </div>
              <p className="text-rose-200 font-sans text-xs">
                Fallo en resta de fechas o timeout. El bot salta a <code className="text-rose-300">@bot.event on_app_command_error</code>, ¡pero discord.py NO lo invoca para slash commands!
              </p>
            </div>

            <div className="flex justify-center text-rose-500">
              <ArrowRight className="w-4 h-4 rotate-90" />
            </div>

            {/* Step 4 - Result */}
            <div className="p-3 rounded-xl bg-rose-950/60 border border-rose-700 text-rose-200 font-sans space-y-1">
              <span className="font-bold block text-xs">❌ Resultado Final:</span>
              <p className="text-xs">
                Nunca se ejecuta <code className="text-rose-300 font-mono">interaction.followup.send()</code>. Discord queda mostrando "Pensando..." en bucle infinito durante 15 minutos.
              </p>
            </div>
          </div>
        </div>

        {/* AFTER FLOW */}
        <div className="p-6 rounded-2xl bg-slate-950 border border-emerald-900/50 space-y-4 shadow-xl relative overflow-hidden">
          <div className="flex items-center justify-between pb-3 border-b border-emerald-900/30">
            <div className="flex items-center gap-2 text-emerald-400 font-bold text-sm">
              <CheckCircle2 className="w-5 h-5" />
              <span>Flujo BLINDADO (Con la solución aplicada)</span>
            </div>
            <span className="text-xs px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-mono">100% Estable</span>
          </div>

          <div className="space-y-3 font-mono text-xs">
            {/* Step 1 */}
            <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
              <div className="text-slate-400 font-semibold flex items-center justify-between">
                <span>1. Usuario envía /diario</span>
                <span className="text-slate-500 text-[10px]">Discord API</span>
              </div>
              <p className="text-slate-300 font-sans text-xs">
                <code className="text-emerald-300">safe_defer(interaction)</code> envía el ack en &lt;50ms previniendo el timeout de 3s.
              </p>
            </div>

            <div className="flex justify-center text-slate-600">
              <ArrowRight className="w-4 h-4 rotate-90" />
            </div>

            {/* Step 2 */}
            <div className="p-3 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
              <div className="text-slate-400 font-semibold flex items-center justify-between">
                <span>2. Normalización de Fechas & DB</span>
                <span className="text-slate-500 text-[10px]">bot.helpers</span>
              </div>
              <p className="text-slate-300 font-sans text-xs">
                <code className="text-emerald-300">get_elapsed_seconds()</code> normaliza SQLite y Postgres sin ningún TypeError.
              </p>
            </div>

            <div className="flex justify-center text-emerald-500">
              <ArrowRight className="w-4 h-4 rotate-90" />
            </div>

            {/* Step 3 - Protection */}
            <div className="p-3 rounded-xl bg-emerald-950/40 border border-emerald-800/80 space-y-1">
              <div className="text-emerald-300 font-bold flex items-center justify-between">
                <span>🛡️ Manejador Global @bot.tree.error</span>
                <span className="text-emerald-400 text-[10px]">discord.py v2.x</span>
              </div>
              <p className="text-emerald-200 font-sans text-xs">
                Cualquier error inesperado es interceptado de inmediato y respondido con un mensaje de error legible al usuario.
              </p>
            </div>

            <div className="flex justify-center text-emerald-500">
              <ArrowRight className="w-4 h-4 rotate-90" />
            </div>

            {/* Step 4 - Result */}
            <div className="p-3 rounded-xl bg-emerald-950/60 border border-emerald-700 text-emerald-200 font-sans space-y-1">
              <span className="font-bold block text-xs">✅ Resultado Final:</span>
              <p className="text-xs">
                Respuesta entregada en menos de 50ms. Nunca más un comando queda colgado en bucle infinito.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
