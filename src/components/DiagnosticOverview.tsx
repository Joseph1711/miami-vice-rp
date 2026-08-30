import React from 'react';
import { DiagnosticIssue } from '../types';
import { AlertTriangle, CheckCircle2, ShieldAlert, Cpu, Database, Clock, Terminal } from 'lucide-react';

interface DiagnosticOverviewProps {
  issues: DiagnosticIssue[];
  onSelectIssue: (issue: DiagnosticIssue) => void;
  selectedIssueId: string;
}

export const DiagnosticOverview: React.FC<DiagnosticOverviewProps> = ({
  issues,
  onSelectIssue,
  selectedIssueId
}) => {
  const getCategoryIcon = (category: DiagnosticIssue['category']) => {
    switch (category) {
      case 'discord.py':
        return <Terminal className="w-5 h-5 text-indigo-400" />;
      case 'datetime':
        return <Clock className="w-5 h-5 text-amber-400" />;
      case 'database':
        return <Database className="w-5 h-5 text-cyan-400" />;
      case 'asyncio':
        return <Cpu className="w-5 h-5 text-emerald-400" />;
    }
  };

  const getSeverityBadge = (severity: DiagnosticIssue['severity']) => {
    switch (severity) {
      case 'CRITICAL':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-950/80 text-rose-300 border border-rose-800/60">
            <ShieldAlert className="w-3.5 h-3.5" /> CRÍTICO
          </span>
        );
      case 'HIGH':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-950/80 text-amber-300 border border-amber-800/60">
            <AlertTriangle className="w-3.5 h-3.5" /> ALTO
          </span>
        );
      case 'MEDIUM':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-950/80 text-blue-300 border border-blue-800/60">
            MEDIO
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner Alert explaining the root cause summary */}
      <div className="p-6 rounded-2xl bg-gradient-to-r from-rose-950/40 via-slate-900 to-slate-900 border border-rose-900/40 shadow-xl relative overflow-hidden">
        <div className="absolute right-0 top-0 w-96 h-96 bg-rose-500/5 rounded-full blur-3xl pointer-events-none" />
        <div className="flex items-start gap-4">
          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 shrink-0">
            <ShieldAlert className="w-7 h-7" />
          </div>
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-bold text-white tracking-tight">
                Diagnóstico del Error de Bucle Infinito ("Thinking...") en Discord
              </h2>
              <span className="px-2 py-0.5 text-xs font-semibold rounded bg-rose-500/20 text-rose-300 border border-rose-500/30">
                4 Causas Identificadas
              </span>
            </div>
            <p className="text-slate-300 text-sm leading-relaxed max-w-4xl">
              Al procesar comandos asíncronos en <strong>Miami Vice RP</strong>, el bot ejecutaba <code className="text-cyan-300 px-1.5 py-0.5 bg-slate-800 rounded font-mono text-xs">await interaction.response.defer()</code> indicando a Discord que preparara la respuesta. Inmediatamente después, ocurrían excepciones silenciosas (como <code className="text-amber-300 px-1.5 py-0.5 bg-slate-800 rounded font-mono text-xs">TypeError: offset-naive vs offset-aware datetimes</code> o timeouts de base de datos) que no eran capturadas porque el error handler estaba registrado con <code className="text-rose-300 px-1.5 py-0.5 bg-slate-800 rounded font-mono text-xs">@bot.event</code> en vez de <code className="text-emerald-300 px-1.5 py-0.5 bg-slate-800 rounded font-mono text-xs">@bot.tree.error</code>.
            </p>
          </div>
        </div>
      </div>

      {/* Issues Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {issues.map((issue, issueIdx) => {
          const isSelected = selectedIssueId === issue.id;
          return (
            <div
              key={`diag-card-${issue.id}-${issueIdx}`}
              onClick={() => onSelectIssue(issue)}
              className={`p-5 rounded-xl border transition-all cursor-pointer text-left relative overflow-hidden group ${
                isSelected
                  ? 'bg-slate-900 border-cyan-500 shadow-lg shadow-cyan-500/10'
                  : 'bg-slate-900/60 border-slate-800 hover:border-slate-700 hover:bg-slate-900'
              }`}
            >
              <div className="flex items-start justify-between gap-3 mb-3">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 rounded-lg bg-slate-800/80 border border-slate-700/50">
                    {getCategoryIcon(issue.category)}
                  </div>
                  <span className="text-xs font-mono font-medium text-slate-400 uppercase">
                    {issue.category}
                  </span>
                </div>
                {getSeverityBadge(issue.severity)}
              </div>

              <h3 className="font-bold text-slate-100 group-hover:text-cyan-300 transition-colors text-base mb-2">
                {issue.title}
              </h3>

              <p className="text-slate-400 text-sm leading-normal line-clamp-2 mb-4">
                {issue.summary}
              </p>

              <div className="flex items-center justify-between pt-3 border-t border-slate-800/80 text-xs text-slate-400">
                <span className="font-mono text-slate-500">
                  Archivos: {issue.affectedFiles.join(', ')}
                </span>
                <span className={`font-semibold ${isSelected ? 'text-cyan-400' : 'text-slate-400 group-hover:text-slate-200'}`}>
                  Ver detalle →
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
