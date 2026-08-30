import React, { useState } from 'react';
import { FilePatch } from '../types';
import { Check, Copy, FileCode, CheckCircle2, SplitSquareVertical, AlignJustify } from 'lucide-react';

interface DiffViewerProps {
  patches: FilePatch[];
  activeFilePath?: string;
  onSelectFile?: (path: string) => void;
}

export const DiffViewer: React.FC<DiffViewerProps> = ({
  patches,
  activeFilePath,
  onSelectFile
}) => {
  const [selectedPath, setSelectedPath] = useState<string>(activeFilePath || patches[0].filePath);
  const [viewMode, setViewMode] = useState<'diff' | 'side-by-side' | 'full-fixed'>('diff');
  const [copiedFile, setCopiedFile] = useState<string | null>(null);

  const currentPatch = patches.find(p => p.filePath === (activeFilePath || selectedPath)) || patches[0];

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedFile(id);
    setTimeout(() => setCopiedFile(null), 2000);
  };

  return (
    <div className="space-y-4">
      {/* File Selector Tabs */}
      <div className="flex flex-wrap gap-2 items-center justify-between border-b border-slate-800 pb-3">
        <div className="flex flex-wrap gap-1.5">
          {patches.map((patch, pIdx) => {
            const isActive = patch.filePath === currentPatch.filePath;
            return (
              <button
                key={`diff-tab-${patch.filePath}-${pIdx}`}
                onClick={() => {
                  setSelectedPath(patch.filePath);
                  if (onSelectFile) onSelectFile(patch.filePath);
                }}
                className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-mono transition-all ${
                  isActive
                    ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/40 font-semibold shadow-sm'
                    : 'bg-slate-900/60 text-slate-400 border border-slate-800 hover:text-slate-200 hover:bg-slate-800'
                }`}
              >
                <FileCode className="w-4 h-4 text-cyan-400" />
                <span>{patch.filePath}</span>
              </button>
            );
          })}
        </div>

        {/* View Mode Toggle */}
        <div className="flex items-center gap-1 bg-slate-900 p-1 rounded-lg border border-slate-800 text-xs">
          <button
            onClick={() => setViewMode('diff')}
            className={`px-3 py-1.5 rounded-md font-medium transition-colors ${
              viewMode === 'diff'
                ? 'bg-cyan-600 text-white font-semibold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Git Diff
          </button>
          <button
            onClick={() => setViewMode('side-by-side')}
            className={`px-3 py-1.5 rounded-md font-medium transition-colors ${
              viewMode === 'side-by-side'
                ? 'bg-cyan-600 text-white font-semibold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Antes / Después
          </button>
          <button
            onClick={() => setViewMode('full-fixed')}
            className={`px-3 py-1.5 rounded-md font-medium transition-colors ${
              viewMode === 'full-fixed'
                ? 'bg-cyan-600 text-white font-semibold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Código Final
          </button>
        </div>
      </div>

      {/* Changes Summary Header */}
      <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800 space-y-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="font-mono text-cyan-400 font-bold text-sm">
              {currentPatch.filePath}
            </span>
            <span className="text-slate-400 text-xs">— {currentPatch.description}</span>
          </div>
          <button
            onClick={() => handleCopy(currentPatch.afterCode, currentPatch.filePath)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/20 text-xs font-semibold transition-colors"
          >
            {copiedFile === currentPatch.filePath ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-400" />
                <span>¡Copiado!</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span>Copiar Archivo Reparado</span>
              </>
            )}
          </button>
        </div>

        <ul className="grid grid-cols-1 md:grid-cols-2 gap-1.5 pt-1 text-xs text-slate-300">
          {currentPatch.changesSummary.map((item, idx) => (
            <li key={`diff-summary-item-${idx}`} className="flex items-start gap-2">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Code Container */}
      <div className="rounded-xl border border-slate-800 bg-slate-950 overflow-hidden font-mono text-xs shadow-inner">
        {viewMode === 'diff' && (
          <div className="p-4 overflow-x-auto max-h-[500px]">
            <pre className="space-y-0.5">
              {currentPatch.diff.split('\n').map((line, i) => {
                const isAdd = line.startsWith('+') && !line.startsWith('+++');
                const isDel = line.startsWith('-') && !line.startsWith('---');
                const isHeader = line.startsWith('@@') || line.startsWith('---') || line.startsWith('+++');

                return (
                  <div
                    key={`diff-code-line-${i}`}
                    className={`px-2 py-0.5 rounded leading-relaxed ${
                      isAdd
                        ? 'bg-emerald-950/60 text-emerald-300 border-l-2 border-emerald-500'
                        : isDel
                        ? 'bg-rose-950/60 text-rose-300 border-l-2 border-rose-500'
                        : isHeader
                        ? 'text-cyan-400 font-bold bg-slate-900/80 my-1'
                        : 'text-slate-400'
                    }`}
                  >
                    {line}
                  </div>
                );
              })}
            </pre>
          </div>
        )}

        {viewMode === 'side-by-side' && (
          <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-slate-800 max-h-[500px] overflow-y-auto">
            {/* Before */}
            <div className="p-4 bg-rose-950/10">
              <div className="text-rose-400 font-bold pb-2 border-b border-rose-900/30 mb-3 flex items-center justify-between">
                <span>❌ Antes (Causaba bucle infinito)</span>
              </div>
              <pre className="text-slate-300 whitespace-pre-wrap leading-relaxed">
                {currentPatch.beforeCode}
              </pre>
            </div>

            {/* After */}
            <div className="p-4 bg-emerald-950/10">
              <div className="text-emerald-400 font-bold pb-2 border-b border-emerald-900/30 mb-3 flex items-center justify-between">
                <span>✅ Después (Reparado y Blindado)</span>
              </div>
              <pre className="text-slate-200 whitespace-pre-wrap leading-relaxed">
                {currentPatch.afterCode}
              </pre>
            </div>
          </div>
        )}

        {viewMode === 'full-fixed' && (
          <div className="p-4 overflow-x-auto max-h-[500px]">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800 mb-3 text-slate-400">
              <span>Archivo Completo Reparado: <strong className="text-cyan-300">{currentPatch.filePath}</strong></span>
              <button
                onClick={() => handleCopy(currentPatch.afterCode, currentPatch.filePath)}
                className="text-cyan-400 hover:text-cyan-300 underline font-sans text-xs"
              >
                Copiar todo
              </button>
            </div>
            <pre className="text-slate-300 whitespace-pre-wrap leading-relaxed">
              {currentPatch.afterCode}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
};
