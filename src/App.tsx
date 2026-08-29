import React, { useState } from 'react';
import { DIAGNOSTIC_ISSUES, FILE_PATCHES, SIMULATED_COMMANDS } from './data/fixesData';
import { DiagnosticOverview } from './components/DiagnosticOverview';
import { DiffViewer } from './components/DiffViewer';
import { CommandSimulator } from './components/CommandSimulator';
import { ArchitectureFlow } from './components/ArchitectureFlow';
import { GitPatchModal } from './components/GitPatchModal';
import { BotManagerView } from './components/BotManagerView';
import { BotCodeEditor } from './components/BotCodeEditor';
import { DatabaseExplorer } from './components/DatabaseExplorer';
import { DiagnosticIssue } from './types';
import { 
  Bot, 
  ShieldCheck, 
  Code2, 
  PlayCircle, 
  GitBranch, 
  GitPullRequest, 
  CheckCircle2, 
  AlertOctagon, 
  Terminal, 
  ExternalLink,
  Zap,
  Flame,
  Layers,
  Database,
  FileCode,
  Activity
} from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState<'bot-manager' | 'code-editor' | 'database' | 'diagnosis' | 'diffs' | 'simulator' | 'flow' | 'patch'>('bot-manager');
  const [selectedIssue, setSelectedIssue] = useState<DiagnosticIssue>(DIAGNOSTIC_ISSUES[0]);
  const [selectedFilePath, setSelectedFilePath] = useState<string>(FILE_PATCHES[0].filePath);

  const handleSelectIssue = (issue: DiagnosticIssue) => {
    setSelectedIssue(issue);
    if (issue.affectedFiles.length > 0) {
      const match = FILE_PATCHES.find(p => p.filePath === issue.affectedFiles[0]);
      if (match) {
        setSelectedFilePath(match.filePath);
      }
    }
    setActiveTab('diffs');
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans flex flex-col selection:bg-cyan-500/20 selection:text-cyan-300">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-gradient-to-tr from-cyan-500 to-indigo-600 shadow-md shadow-cyan-500/20 text-slate-950 font-black">
              <Bot className="w-5 h-5 text-slate-950" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-extrabold text-white tracking-tight">
                  Miami Vice RP
                </h1>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 font-mono">
                  DISCORD BOT & REPAIR HUB
                </span>
              </div>
              <p className="text-xs text-slate-400 flex items-center gap-1.5 font-mono">
                <span>Repo:</span>
                <a 
                  href="https://github.com/Joseph1711/miami-vice-rp" 
                  target="_blank" 
                  rel="noreferrer"
                  className="text-cyan-400 hover:text-cyan-300 underline inline-flex items-center gap-1"
                >
                  Joseph1711/miami-vice-rp
                  <ExternalLink className="w-3 h-3" />
                </a>
              </p>
            </div>
          </div>

          {/* Quick Metrics */}
          <div className="flex items-center gap-3 text-xs">
            <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-300">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>Código Python Corregido</span>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-950/40 border border-emerald-800/60 text-emerald-300 font-semibold">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              <span>Bucle Infinito Solucionado</span>
            </div>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex overflow-x-auto scrollbar-none gap-1 pt-1">
          <button
            id="tab-bot-manager"
            onClick={() => setActiveTab('bot-manager')}
            className={`flex items-center gap-2 px-4 py-2.5 border-b-2 text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
              activeTab === 'bot-manager'
                ? 'border-cyan-400 text-cyan-400 bg-cyan-500/10'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
            }`}
          >
            <Activity className="w-4 h-4 text-emerald-400" />
            <span>Panel del Bot (Live Process & Logs)</span>
          </button>

          <button
            id="tab-code-editor"
            onClick={() => setActiveTab('code-editor')}
            className={`flex items-center gap-2 px-4 py-2.5 border-b-2 text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
              activeTab === 'code-editor'
                ? 'border-cyan-400 text-cyan-400 bg-cyan-500/10'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
            }`}
          >
            <FileCode className="w-4 h-4 text-cyan-400" />
            <span>Editor de Código Python</span>
          </button>

          <button
            id="tab-database"
            onClick={() => setActiveTab('database')}
            className={`flex items-center gap-2 px-4 py-2.5 border-b-2 text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
              activeTab === 'database'
                ? 'border-cyan-400 text-cyan-400 bg-cyan-500/10'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
            }`}
          >
            <Database className="w-4 h-4 text-amber-400" />
            <span>Base de Datos (38 Tablas)</span>
          </button>

          <button
            id="tab-diagnosis"
            onClick={() => setActiveTab('diagnosis')}
            className={`flex items-center gap-2 px-4 py-2.5 border-b-2 text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
              activeTab === 'diagnosis'
                ? 'border-cyan-400 text-cyan-400 bg-cyan-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
            }`}
          >
            <AlertOctagon className="w-4 h-4" />
            <span>Diagnóstico & Causa Raíz</span>
          </button>

          <button
            id="tab-diffs"
            onClick={() => setActiveTab('diffs')}
            className={`flex items-center gap-2 px-4 py-2.5 border-b-2 text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
              activeTab === 'diffs'
                ? 'border-cyan-400 text-cyan-400 bg-cyan-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
            }`}
          >
            <Code2 className="w-4 h-4" />
            <span>Diffs de Código Reparado</span>
          </button>

          <button
            id="tab-simulator"
            onClick={() => setActiveTab('simulator')}
            className={`flex items-center gap-2 px-4 py-2.5 border-b-2 text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
              activeTab === 'simulator'
                ? 'border-cyan-400 text-cyan-400 bg-cyan-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
            }`}
          >
            <PlayCircle className="w-4 h-4" />
            <span>Simulador de Comandos</span>
          </button>

          <button
            id="tab-flow"
            onClick={() => setActiveTab('flow')}
            className={`flex items-center gap-2 px-4 py-2.5 border-b-2 text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
              activeTab === 'flow'
                ? 'border-cyan-400 text-cyan-400 bg-cyan-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
            }`}
          >
            <Layers className="w-4 h-4" />
            <span>Flujo de Ejecución Async</span>
          </button>

          <button
            id="tab-patch"
            onClick={() => setActiveTab('patch')}
            className={`flex items-center gap-2 px-4 py-2.5 border-b-2 text-xs font-semibold whitespace-nowrap transition-all cursor-pointer ${
              activeTab === 'patch'
                ? 'border-cyan-400 text-cyan-400 bg-cyan-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
            }`}
          >
            <GitPullRequest className="w-4 h-4" />
            <span>Parche Git & Exportación</span>
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === 'bot-manager' && (
          <BotManagerView />
        )}

        {activeTab === 'code-editor' && (
          <BotCodeEditor />
        )}

        {activeTab === 'database' && (
          <DatabaseExplorer />
        )}

        {activeTab === 'diagnosis' && (
          <DiagnosticOverview
            issues={DIAGNOSTIC_ISSUES}
            onSelectIssue={handleSelectIssue}
            selectedIssueId={selectedIssue.id}
          />
        )}

        {activeTab === 'diffs' && (
          <DiffViewer
            patches={FILE_PATCHES}
            activeFilePath={selectedFilePath}
            onSelectFile={(path) => setSelectedFilePath(path)}
          />
        )}

        {activeTab === 'simulator' && (
          <CommandSimulator commands={SIMULATED_COMMANDS} />
        )}

        {activeTab === 'flow' && (
          <ArchitectureFlow />
        )}

        {activeTab === 'patch' && (
          <GitPatchModal patches={FILE_PATCHES} />
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 bg-slate-950 py-6 text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Bot className="w-4 h-4 text-cyan-400" />
            <span>Solución y entorno de control completado para <strong>miami-vice-rp</strong> de Discord.</span>
          </div>
          <div className="flex items-center gap-4">
            <span>Python 3.10 / 3.11</span>
            <span>•</span>
            <span>discord.py 2.3+</span>
            <span>•</span>
            <span>SQLite & Supabase Postgres</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

