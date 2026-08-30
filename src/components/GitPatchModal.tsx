import React, { useState } from 'react';
import { FilePatch } from '../types';
import { Copy, Check, Terminal, GitCommit, Download, ExternalLink } from 'lucide-react';

interface GitPatchModalProps {
  patches: FilePatch[];
}

export const GitPatchModal: React.FC<GitPatchModalProps> = ({ patches }) => {
  const [copied, setCopied] = useState<string | null>(null);

  const fullGitPatch = patches.map(p => p.diff).join('\n\n');

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(null), 2000);
  };

  const handleDownloadPatch = () => {
    const blob = new Blob([fullGitPatch], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'discord_async_fix.patch';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="space-y-6">
      {/* Header Info */}
      <div className="p-6 rounded-2xl bg-gradient-to-br from-cyan-950/30 via-slate-900 to-slate-900 border border-cyan-900/40 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-3 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
              <GitCommit className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white">
                Parche Unificado para el Repositorio GitHub
              </h3>
              <p className="text-xs text-slate-400 font-mono">
                Joseph1711 / miami-vice-rp
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleDownloadPatch}
              className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700 text-xs font-semibold transition-colors"
            >
              <Download className="w-4 h-4 text-cyan-400" />
              <span>Descargar .patch</span>
            </button>
            <button
              onClick={() => copyToClipboard(fullGitPatch, 'full-patch')}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-slate-950 text-xs font-bold transition-all shadow-md shadow-cyan-500/20"
            >
              {copied === 'full-patch' ? (
                <>
                  <Check className="w-4 h-4 text-slate-950" />
                  <span>¡Parche Copiado!</span>
                </>
              ) : (
                <>
                  <Copy className="w-4 h-4" />
                  <span>Copiar Parche Git</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* 3 Simple CLI steps */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2 text-xs">
          <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
            <span className="text-[10px] font-bold text-cyan-400 uppercase tracking-wider">Paso 1</span>
            <p className="text-slate-300 font-semibold">Guardar el parche</p>
            <code className="block font-mono text-slate-400 text-[11px] bg-slate-900 px-2 py-1 rounded">
              fix.patch
            </code>
          </div>
          <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
            <span className="text-[10px] font-bold text-cyan-400 uppercase tracking-wider">Paso 2</span>
            <p className="text-slate-300 font-semibold">Aplicar cambios</p>
            <code className="block font-mono text-slate-400 text-[11px] bg-slate-900 px-2 py-1 rounded">
              git apply fix.patch
            </code>
          </div>
          <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 space-y-1">
            <span className="text-[10px] font-bold text-cyan-400 uppercase tracking-wider">Paso 3</span>
            <p className="text-slate-300 font-semibold">Commit & Push</p>
            <code className="block font-mono text-slate-400 text-[11px] bg-slate-900 px-2 py-1 rounded">
              git commit -am "fix: async commands loop"
            </code>
          </div>
        </div>
      </div>

      {/* Raw Patch Viewer */}
      <div className="rounded-2xl border border-slate-800 bg-slate-950 overflow-hidden font-mono text-xs shadow-xl">
        <div className="flex items-center justify-between p-3.5 bg-slate-900 border-b border-slate-800 text-slate-400">
          <div className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-cyan-400" />
            <span className="font-semibold text-slate-200">diff --git a/bot/events.py b/bot/events.py ...</span>
          </div>
          <button
            onClick={() => copyToClipboard(fullGitPatch, 'full-patch')}
            className="text-cyan-400 hover:text-cyan-300 text-xs flex items-center gap-1 font-sans"
          >
            <Copy className="w-3.5 h-3.5" />
            <span>Copiar todo</span>
          </button>
        </div>

        <div className="p-4 max-h-[400px] overflow-y-auto bg-slate-950/80">
          <pre className="text-slate-300 whitespace-pre leading-relaxed">
            {fullGitPatch}
          </pre>
        </div>
      </div>
    </div>
  );
};
