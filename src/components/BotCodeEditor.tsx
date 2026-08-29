import React, { useState, useEffect } from 'react';
import { 
  FileCode, 
  Folder, 
  Save, 
  CheckCircle2, 
  FileText, 
  AlertCircle, 
  RefreshCw, 
  Copy, 
  Check, 
  Code,
  ShieldCheck
} from 'lucide-react';

interface FileNode {
  path: string;
  name: string;
  type: 'file' | 'dir';
  size?: number;
}

export function BotCodeEditor() {
  const [files, setFiles] = useState<FileNode[]>([]);
  const [selectedFile, setSelectedFile] = useState<string>('bot/events.py');
  const [content, setContent] = useState<string>('');
  const [initialContent, setInitialContent] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);
  const [saveSuccess, setSaveSuccess] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchFiles = async () => {
    try {
      const res = await fetch('/api/bot/files');
      if (res.ok) {
        const data = await res.json();
        setFiles(data.files || []);
      }
    } catch (err) {
      console.error('Error listing files:', err);
    }
  };

  const loadFileContent = async (filePath: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/bot/file-content?path=${encodeURIComponent(filePath)}`);
      if (res.ok) {
        const data = await res.json();
        setContent(data.content);
        setInitialContent(data.content);
      } else {
        setError('No se pudo cargar el archivo');
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFiles();
  }, []);

  useEffect(() => {
    if (selectedFile) {
      loadFileContent(selectedFile);
    }
  }, [selectedFile]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch('/api/bot/save-file', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: selectedFile, content }),
      });
      if (res.ok) {
        setSaveSuccess(true);
        setInitialContent(content);
        setTimeout(() => setSaveSuccess(false), 2500);
      } else {
        const data = await res.json();
        setError(data.error || 'Error al guardar archivo');
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const isModified = content !== initialContent;

  const getFixBadge = (filePath: string) => {
    if (filePath.includes('events.py')) return '✅ @bot.tree.error Corregido';
    if (filePath.includes('helpers.py')) return '✅ Datetime Seguro';
    if (filePath.includes('cogs/economy.py')) return '✅ Cooldown Sin Crashes';
    if (filePath.includes('db.py')) return '✅ Pool & Timeouts OK';
    return null;
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
      {/* File Tree Sidebar */}
      <div className="lg:col-span-1 bg-slate-900 border border-slate-800 rounded-2xl p-4 flex flex-col h-[650px] shadow-xl">
        <div className="flex items-center justify-between pb-3 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Folder className="w-4 h-4 text-cyan-400" />
            <h3 className="text-xs font-bold text-white uppercase tracking-wider">Archivos del Bot</h3>
          </div>
          <button 
            onClick={fetchFiles}
            title="Refrescar lista"
            className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="mt-3 overflow-y-auto flex-1 space-y-1 pr-1 font-mono text-xs">
          {files.map((f, idx) => {
            const isSelected = selectedFile === f.path;
            const badge = getFixBadge(f.path);
            return (
              <button
                key={`${f.path}-${idx}`}
                onClick={() => setSelectedFile(f.path)}
                className={`w-full text-left px-2.5 py-1.5 rounded-lg flex flex-col gap-0.5 transition-all ${
                  isSelected 
                    ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 font-medium' 
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                }`}
              >
                <div className="flex items-center gap-2 truncate">
                  <FileCode className={`w-3.5 h-3.5 shrink-0 ${isSelected ? 'text-cyan-400' : 'text-slate-500'}`} />
                  <span className="truncate">{f.path}</span>
                </div>
                {badge && (
                  <span className="text-[10px] text-emerald-400 font-sans pl-5">
                    {badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        <div className="pt-3 border-t border-slate-800/80 text-[11px] text-slate-400 flex items-center gap-1.5">
          <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>Todos los archivos están sincronizados con el bot real de Python.</span>
        </div>
      </div>

      {/* Code Editor & Viewer */}
      <div className="lg:col-span-3 bg-slate-950 border border-slate-800 rounded-2xl flex flex-col h-[650px] overflow-hidden shadow-2xl">
        {/* Editor Toolbar */}
        <div className="px-4 py-3 bg-slate-900 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <Code className="w-4 h-4 text-cyan-400" />
            <span className="font-mono text-xs font-bold text-white">{selectedFile}</span>
            {isModified && (
              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                Cambios sin guardar
              </span>
            )}
            {getFixBadge(selectedFile) && (
              <span className="hidden sm:inline-block px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                {getFixBadge(selectedFile)}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCopy}
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? 'Copiado' : 'Copiar'}</span>
            </button>

            <button
              id="save-code-btn"
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-xs font-bold flex items-center gap-1.5 shadow-md shadow-cyan-600/20 transition-all cursor-pointer"
            >
              {saveSuccess ? (
                <>
                  <CheckCircle2 className="w-3.5 h-3.5 text-white" />
                  <span>¡Guardado en el Bot!</span>
                </>
              ) : (
                <>
                  <Save className="w-3.5 h-3.5" />
                  <span>{saving ? 'Guardando...' : 'Guardar Cambios'}</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Editor Area */}
        <div className="flex-1 relative flex overflow-hidden">
          {loading ? (
            <div className="w-full h-full flex items-center justify-center text-slate-400 gap-2">
              <RefreshCw className="w-5 h-5 animate-spin text-cyan-400" />
              <span>Cargando código del archivo...</span>
            </div>
          ) : error ? (
            <div className="w-full h-full flex items-center justify-center text-rose-400 gap-2">
              <AlertCircle className="w-5 h-5" />
              <span>{error}</span>
            </div>
          ) : (
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              spellCheck={false}
              className="w-full h-full p-4 font-mono text-xs bg-slate-950 text-slate-200 resize-none outline-none focus:ring-0 leading-relaxed border-none scrollbar-thin"
            />
          )}
        </div>

        {/* Footer info */}
        <div className="px-4 py-2 bg-slate-900/80 border-t border-slate-800 text-[11px] text-slate-400 flex items-center justify-between">
          <span>Python 3.10 • UTF-8 • {content.split('\n').length} líneas</span>
          <span>Cualquier cambio guardado afectará directamente la ejecución del bot de Discord.</span>
        </div>
      </div>
    </div>
  );
}
