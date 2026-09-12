import React from 'react';
import { DatabaseExplorer } from './components/DatabaseExplorer';
import { 
  Database, 
  ExternalLink,
  ShieldCheck,
  Server
} from 'lucide-react';

export default function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans flex flex-col selection:bg-emerald-500/20 selection:text-emerald-300">
      {/* Top Header */}
      <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-gradient-to-tr from-emerald-500 to-cyan-600 shadow-md shadow-emerald-500/20 text-slate-950 font-black">
              <Database className="w-5 h-5 text-slate-950" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-extrabold text-white tracking-tight">
                  Miami Vice RP
                </h1>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-mono">
                  SUPABASE DATABASE
                </span>
              </div>
              <p className="text-xs text-slate-400 flex items-center gap-1.5 font-mono">
                <span>Repositorio:</span>
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

          {/* Quick Metrics / Status */}
          <div className="flex items-center gap-3 text-xs">
            <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-300">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>Esquema SQL Oficial</span>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-950/40 border border-emerald-800/60 text-emerald-300 font-semibold font-mono">
              <Server className="w-4 h-4 text-emerald-400" />
              <span>Supabase PostgreSQL</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Area: Exclusively Supabase Database Manager */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <DatabaseExplorer />
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-800/80 bg-slate-950 py-6 text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-emerald-400" />
            <span>Gestor de Base de Datos Supabase para <strong>Miami Vice RP</strong>.</span>
          </div>
          <div className="flex items-center gap-4 font-mono text-[11px]">
            <span>PostgreSQL 15+</span>
            <span>•</span>
            <span>SSL Encrypted</span>
            <span>•</span>
            <span>54 Tablas</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

