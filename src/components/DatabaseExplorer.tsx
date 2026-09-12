import React, { useState, useEffect, useMemo } from 'react';
import { 
  Database, 
  Table, 
  Coins, 
  Users, 
  TrendingUp, 
  RefreshCw, 
  Trash2, 
  CheckCircle2, 
  Layers,
  Search,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Download,
  Terminal,
  FileCode2,
  Key,
  ShieldAlert,
  ChevronLeft,
  ChevronRight,
  Eye,
  X,
  Copy,
  Check,
  Building2,
  Briefcase,
  Skull,
  ShoppingBag,
  Ticket,
  SlidersHorizontal,
  Info,
  Server,
  ShieldCheck,
  AlertCircle,
  ExternalLink,
  Code
} from 'lucide-react';
import { TableMeta, DbStats, ColumnMeta, SupabaseInfo } from '../types';

const CATEGORIES = [
  { id: 'all', label: 'Todas las Tablas', icon: Database, color: 'text-cyan-400' },
  { id: 'users_config', label: 'Usuarios, DNI & Config', icon: Users, color: 'text-blue-400' },
  { id: 'economy_banking', label: 'Economía & Trabajos', icon: Coins, color: 'text-emerald-400' },
  { id: 'companies_properties', label: 'Empresas & Bienes', icon: Building2, color: 'text-indigo-400' },
  { id: 'departments_fleet', label: 'Departamentos & Flota', icon: Briefcase, color: 'text-amber-400' },
  { id: 'crime_drugs', label: 'Armas, Crimen & Drogas', icon: Skull, color: 'text-rose-400' },
  { id: 'market_inventory', label: 'Mercado & Tienda', icon: ShoppingBag, color: 'text-purple-400' },
  { id: 'tickets_contracts', label: 'Postulaciones & Soporte', icon: Ticket, color: 'text-pink-400' },
];

export function DatabaseExplorer() {
  const [stats, setStats] = useState<DbStats | null>(null);
  const [supabaseInfo, setSupabaseInfo] = useState<SupabaseInfo | null>(null);
  const [schemaSql, setSchemaSql] = useState<string>('');
  const [copiedSql, setCopiedSql] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [selectedTable, setSelectedTable] = useState<string>('users');
  const [tableSearch, setTableSearch] = useState('');
  
  // Table Data State
  const [columns, setColumns] = useState<ColumnMeta[]>([]);
  const [rows, setRows] = useState<any[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(50);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(false);
  const [sortBy, setSortBy] = useState<string>('');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');
  const [cellSearch, setCellSearch] = useState('');
  
  // View Modes: 'data' | 'schema' | 'sql' | 'sql_file' | 'connection'
  const [viewMode, setViewMode] = useState<'data' | 'schema' | 'sql' | 'sql_file' | 'connection'>('data');

  // SQL Console State
  const [sqlQuery, setSqlQuery] = useState('SELECT * FROM users LIMIT 25;');
  const [sqlResults, setSqlResults] = useState<{ columns: string[]; rows: any[]; rowCount: number; executionTimeMs?: number } | null>(null);
  const [sqlError, setSqlError] = useState<string | null>(null);
  const [sqlLoading, setSqlLoading] = useState(false);

  // Clean / Wipe Modal State
  const [wipeModalOpen, setWipeModalOpen] = useState(false);
  const [wiping, setWiping] = useState(false);
  const [wipeSuccess, setWipeSuccess] = useState<string | null>(null);

  // Row Detail Modal
  const [inspectRow, setInspectRow] = useState<any | null>(null);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const fetchStats = async () => {
    try {
      const res = await fetch('/api/database/stats');
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (err) {
      console.error('Error fetching db stats:', err);
    }
  };

  const fetchSupabaseInfo = async () => {
    try {
      const res = await fetch('/api/database/supabase-info');
      if (res.ok) {
        const data = await res.json();
        setSupabaseInfo(data);
      }
    } catch (err) {
      console.error('Error fetching supabase info:', err);
    }
  };

  const fetchSchemaSql = async () => {
    try {
      const res = await fetch('/api/database/supabase-schema-sql');
      if (res.ok) {
        const data = await res.json();
        setSchemaSql(data.sql || '');
      }
    } catch (err) {
      console.error('Error fetching schema sql:', err);
    }
  };

  const fetchTableData = async (
    tableName: string, 
    currentPage: number = 1, 
    currentLimit: number = 50, 
    currentSort: string = '', 
    currentOrder: 'asc' | 'desc' = 'asc'
  ) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        table: tableName,
        page: currentPage.toString(),
        limit: currentLimit.toString(),
        sortBy: currentSort,
        sortOrder: currentOrder,
      });
      const res = await fetch(`/api/database/table-data?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        setColumns(data.columns || []);
        setRows(data.rows || []);
        setTotalCount(data.totalCount || 0);
        setPage(data.page || 1);
        setLimit(data.limit || 50);
        setTotalPages(data.totalPages || 1);
      }
    } catch (err) {
      console.error('Error fetching table data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
    fetchSupabaseInfo();
    fetchSchemaSql();
    const interval = setInterval(() => {
      fetchStats();
      fetchSupabaseInfo();
    }, 8000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (selectedTable) {
      fetchTableData(selectedTable, 1, limit, sortBy, sortOrder);
    }
  }, [selectedTable, limit, sortBy, sortOrder]);

  const handleSort = (colName: string) => {
    if (sortBy === colName) {
      setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(colName);
      setSortOrder('asc');
    }
  };

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages) {
      setPage(newPage);
      fetchTableData(selectedTable, newPage, limit, sortBy, sortOrder);
    }
  };

  const handleExecuteSql = async () => {
    if (!sqlQuery.trim()) return;
    setSqlLoading(true);
    setSqlError(null);
    try {
      const res = await fetch('/api/database/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sql: sqlQuery }),
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setSqlResults(data);
      } else {
        setSqlError(data.error || 'Error al ejecutar consulta SQL');
        setSqlResults(null);
      }
    } catch (err: any) {
      setSqlError(err.message || 'Error de red al ejecutar SQL');
    } finally {
      setSqlLoading(false);
    }
  };

  const handleWipeClean = async () => {
    setWiping(true);
    try {
      const res = await fetch('/api/database/wipe-clean', { method: 'POST' });
      const data = await res.json();
      if (res.ok && data.success) {
        setWipeSuccess(data.message);
        await fetchStats();
        await fetchTableData(selectedTable, 1, limit);
        setTimeout(() => {
          setWipeSuccess(null);
          setWipeModalOpen(false);
        }, 2000);
      }
    } catch (err) {
      console.error('Error wiping database:', err);
    } finally {
      setWiping(false);
    }
  };

  const filteredTables = useMemo(() => {
    if (!stats?.tables) return [];
    return stats.tables.filter(t => {
      const matchCat = selectedCategory === 'all' || t.category === selectedCategory;
      const matchSearch = !tableSearch || 
        t.name.toLowerCase().includes(tableSearch.toLowerCase()) || 
        t.description.toLowerCase().includes(tableSearch.toLowerCase());
      return matchCat && matchSearch;
    });
  }, [stats?.tables, selectedCategory, tableSearch]);

  const filteredRows = useMemo(() => {
    if (!cellSearch) return rows;
    const term = cellSearch.toLowerCase();
    return rows.filter(row => JSON.stringify(row).toLowerCase().includes(term));
  }, [rows, cellSearch]);

  const exportData = (type: 'csv' | 'json') => {
    if (rows.length === 0) return;
    let blob: Blob;
    let filename = `${selectedTable}_export_${new Date().toISOString().slice(0, 10)}`;

    if (type === 'json') {
      blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' });
      filename += '.json';
    } else {
      const headers = columns.map(c => c.name);
      const csvRows = [
        headers.join(','),
        ...rows.map(row => headers.map(h => {
          const val = row[h];
          if (val === null || val === undefined) return '';
          const str = String(val).replace(/"/g, '""');
          return `"${str}"`;
        }).join(','))
      ];
      blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
      filename += '.csv';
    }

    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
  };

  const copyToClipboard = (text: string, field: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 1500);
  };

  return (
    <div className="space-y-6">
      {/* Supabase Connection Status Card */}
      <div className="p-5 rounded-2xl bg-gradient-to-r from-slate-900 via-slate-900 to-emerald-950/40 border border-emerald-900/40 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-start sm:items-center gap-3.5">
            <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shrink-0 shadow-inner">
              <Database className="w-6 h-6" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-base font-extrabold text-white tracking-tight">
                  Base de Datos Supabase (PostgreSQL)
                </h2>
                <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold border flex items-center gap-1.5 font-mono ${
                  supabaseInfo?.backend === 'supabase'
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                    : 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                }`}>
                  <span className={`w-2 h-2 rounded-full ${supabaseInfo?.connected ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}`}></span>
                  {supabaseInfo?.backend === 'supabase' ? 'Conectado a Supabase' : 'Modo Local (SQLite Fallback)'}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono">
                <span>Host: <strong className="text-slate-200">{supabaseInfo?.host || 'Local Storage'}</strong></span>
                <span>•</span>
                <span>Base: <strong className="text-slate-200">{supabaseInfo?.database || 'postgres'}</strong></span>
                <span>•</span>
                <span>Tablas: <strong className="text-emerald-400">{supabaseInfo?.totalTables || stats?.totalTables || 0}</strong></span>
                <span>•</span>
                <span>Latencia: <strong className="text-cyan-400">{supabaseInfo?.latencyMs ? `${supabaseInfo.latencyMs}ms` : '< 1ms'}</strong></span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 self-start md:self-auto">
            <button
              onClick={() => setViewMode('sql_file')}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
                viewMode === 'sql_file'
                  ? 'bg-emerald-500 text-slate-950 shadow-md shadow-emerald-500/20'
                  : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700'
              }`}
            >
              <Code className="w-3.5 h-3.5" />
              <span>Ver Schema SQL</span>
            </button>
            <button
              onClick={() => setViewMode('connection')}
              className={`px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
                viewMode === 'connection'
                  ? 'bg-emerald-500 text-slate-950 shadow-md shadow-emerald-500/20'
                  : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700'
              }`}
            >
              <Server className="w-3.5 h-3.5" />
              <span>Configuración</span>
            </button>
            <button
              onClick={() => {
                fetchStats();
                fetchSupabaseInfo();
              }}
              className="p-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors cursor-pointer"
              title="Refrescar estado de conexión"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Top Banner: Global Metrics & Clean Controls */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 shadow-md flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-400 flex items-center gap-1.5 font-medium">
              <Users className="w-4 h-4 text-cyan-400" />
              <span>Ciudadanos Registrados</span>
            </div>
            <div className="text-2xl font-bold text-white mt-1">
              {stats?.userCount || 0}
              <span className="text-xs font-normal text-slate-400 ml-1.5 font-sans">
                en tabla `users`
              </span>
            </div>
          </div>
          <div className="w-10 h-10 rounded-xl bg-cyan-950/60 border border-cyan-800/40 flex items-center justify-center text-cyan-400">
            <Users className="w-5 h-5" />
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 shadow-md flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-400 flex items-center gap-1.5 font-medium">
              <Coins className="w-4 h-4 text-emerald-400" />
              <span>Efectivo Circulante</span>
            </div>
            <div className="text-2xl font-bold text-emerald-400 mt-1 font-mono">
              ${(stats?.totalCash || 0).toLocaleString()}
            </div>
          </div>
          <div className="w-10 h-10 rounded-xl bg-emerald-950/60 border border-emerald-800/40 flex items-center justify-center text-emerald-400">
            <Coins className="w-5 h-5" />
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 shadow-md flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-400 flex items-center gap-1.5 font-medium">
              <TrendingUp className="w-4 h-4 text-indigo-400" />
              <span>Fondos en Bancos</span>
            </div>
            <div className="text-2xl font-bold text-indigo-400 mt-1 font-mono">
              ${(stats?.totalBank || 0).toLocaleString()}
            </div>
          </div>
          <div className="w-10 h-10 rounded-xl bg-indigo-950/60 border border-indigo-800/40 flex items-center justify-center text-indigo-400">
            <TrendingUp className="w-5 h-5" />
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 shadow-md flex items-center justify-between">
          <div>
            <div className="text-xs text-slate-400 flex items-center gap-1.5 font-medium">
              <Database className="w-4 h-4 text-amber-400" />
              <span>Tablas Supabase</span>
            </div>
            <div className="text-2xl font-bold text-amber-400 mt-1">
              {stats?.totalTables || 54} <span className="text-xs font-normal text-slate-400 font-sans">({stats?.totalRows || 0} filas)</span>
            </div>
          </div>
          <button
            onClick={() => setWipeModalOpen(true)}
            className="px-2.5 py-1.5 rounded-xl bg-rose-950/80 hover:bg-rose-900 border border-rose-800/80 text-rose-300 text-xs font-semibold flex items-center gap-1.5 transition-all shadow-sm cursor-pointer"
            title="Limpiar completamente todas las tablas"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Reset</span>
          </button>
        </div>
      </div>

      {/* Main Database Studio Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Column: Category Filters & Table Catalog (4 cols) */}
        <div className="lg:col-span-4 bg-slate-900 border border-slate-800 rounded-2xl p-4 flex flex-col h-[650px]">
          
          {/* Header */}
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <Table className="w-4 h-4 text-cyan-400" />
              <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                Catálogo de Tablas ({stats?.totalTables || 38})
              </h3>
            </div>
            <button
              onClick={fetchStats}
              className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
              title="Sincronizar catálogo"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Table Search */}
          <div className="mt-3 relative">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2.5" />
            <input
              type="text"
              placeholder="Buscar tabla o descripción..."
              value={tableSearch}
              onChange={(e) => setTableSearch(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs rounded-xl bg-slate-950 border border-slate-800 text-slate-200 focus:outline-none focus:border-cyan-500"
            />
          </div>

          {/* Category Chips */}
          <div className="flex gap-1 overflow-x-auto py-2 scrollbar-none border-b border-slate-800/80">
            {CATEGORIES.map(cat => {
              const isSelected = selectedCategory === cat.id;
              return (
                <button
                  key={`cat-${cat.id}`}
                  onClick={() => setSelectedCategory(cat.id)}
                  className={`text-[10px] px-2 py-1 rounded-lg font-medium whitespace-nowrap transition-all flex items-center gap-1 cursor-pointer ${
                    isSelected 
                      ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-bold' 
                      : 'bg-slate-950 text-slate-400 hover:text-slate-200 border border-slate-800'
                  }`}
                >
                  <span>{cat.label}</span>
                </button>
              );
            })}
          </div>

          {/* Tables List */}
          <div className="mt-2 overflow-y-auto flex-1 space-y-1.5 pr-1 font-mono text-xs">
            {filteredTables.map((t, idx) => {
              const isSelected = selectedTable === t.name;
              return (
                <button
                  key={`table-btn-${t.name}-${idx}`}
                  onClick={() => setSelectedTable(t.name)}
                  className={`w-full text-left p-2.5 rounded-xl flex items-center justify-between transition-all group cursor-pointer ${
                    isSelected 
                      ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/40 shadow-sm' 
                      : 'bg-slate-950/60 hover:bg-slate-800/70 border border-slate-800/60 text-slate-300'
                  }`}
                >
                  <div className="truncate pr-2">
                    <div className="font-semibold flex items-center gap-1.5">
                      <span className="truncate">{t.name}</span>
                      {t.count > 0 && (
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 inline-block shrink-0" />
                      )}
                    </div>
                    <div className="text-[10px] font-sans text-slate-400 truncate mt-0.5 font-normal">
                      {t.description}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-semibold ${
                      t.count > 0 
                        ? 'bg-emerald-950 text-emerald-300 border border-emerald-800/60' 
                        : 'bg-slate-800 text-slate-400'
                    }`}>
                      {t.count} filas
                    </span>
                    <span className="text-[9px] text-slate-400 font-sans">
                      {t.columnsCount} cols
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right Column: Data Grid, Schema Inspector, or SQL Console (8 cols) */}
        <div className="lg:col-span-8 bg-slate-950 border border-slate-800 rounded-2xl flex flex-col h-[650px] overflow-hidden shadow-xl">
          
          {/* Top Controls Toolbar */}
          <div className="p-3 bg-slate-900 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3">
            
            {/* View Mode Tabs */}
            <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-xl border border-slate-800">
              <button
                onClick={() => setViewMode('data')}
                className={`text-xs px-3 py-1.5 rounded-lg font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
                  viewMode === 'data' 
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30' 
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Table className="w-3.5 h-3.5" />
                <span>Datos ({totalCount})</span>
              </button>
              <button
                onClick={() => setViewMode('schema')}
                className={`text-xs px-3 py-1.5 rounded-lg font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
                  viewMode === 'schema' 
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30' 
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <FileCode2 className="w-3.5 h-3.5" />
                <span>Esquema ({columns.length} columnas)</span>
              </button>
              <button
                onClick={() => setViewMode('sql')}
                className={`text-xs px-3 py-1.5 rounded-lg font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
                  viewMode === 'sql' 
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30' 
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Terminal className="w-3.5 h-3.5" />
                <span>Consola SQL</span>
              </button>
              <button
                onClick={() => setViewMode('sql_file')}
                className={`text-xs px-3 py-1.5 rounded-lg font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
                  viewMode === 'sql_file' 
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' 
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Code className="w-3.5 h-3.5" />
                <span>Esquema SQL</span>
              </button>
              <button
                onClick={() => setViewMode('connection')}
                className={`text-xs px-3 py-1.5 rounded-lg font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
                  viewMode === 'connection' 
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' 
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Server className="w-3.5 h-3.5" />
                <span>Conexión</span>
              </button>
            </div>

            {/* Quick Actions (Export, Search, Refresh) */}
            <div className="flex items-center gap-2">
              {viewMode === 'data' && (
                <>
                  <div className="relative">
                    <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2" />
                    <input
                      type="text"
                      placeholder="Filtrar en tabla..."
                      value={cellSearch}
                      onChange={(e) => setCellSearch(e.target.value)}
                      className="pl-8 pr-3 py-1 text-xs rounded-lg bg-slate-950 border border-slate-800 text-slate-200 focus:outline-none focus:border-cyan-500 w-36 sm:w-44"
                    />
                  </div>

                  <button
                    onClick={() => exportData('csv')}
                    disabled={rows.length === 0}
                    className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-40 transition-colors cursor-pointer"
                    title="Exportar como CSV"
                  >
                    <Download className="w-3.5 h-3.5" />
                  </button>
                </>
              )}

              <button
                onClick={() => fetchTableData(selectedTable, page, limit, sortBy, sortOrder)}
                className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors cursor-pointer"
                title="Refrescar datos"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>

          {/* VIEW MODE 1: DATA GRID */}
          {viewMode === 'data' && (
            <div className="flex-1 flex flex-col overflow-hidden">
              <div className="flex-1 overflow-auto">
                {loading ? (
                  <div className="h-full flex flex-col items-center justify-center text-slate-400 gap-2">
                    <RefreshCw className="w-6 h-6 animate-spin text-cyan-400" />
                    <span className="text-xs font-mono">Cargando registros de `{selectedTable}`...</span>
                  </div>
                ) : (
                  <table className="w-full text-left font-mono text-xs border-collapse">
                    <thead className="bg-slate-900 text-slate-400 sticky top-0 border-b border-slate-800 z-10">
                      <tr>
                        <th className="p-2.5 w-10 text-center text-slate-500">#</th>
                        {columns.map(c => (
                          <th 
                            key={`th-col-${c.name}`} 
                            onClick={() => handleSort(c.name)}
                            className="p-2.5 font-semibold text-slate-300 whitespace-nowrap cursor-pointer hover:bg-slate-800/80 transition-colors select-none"
                          >
                            <div className="flex items-center gap-1.5">
                              <span>{c.name}</span>
                              {c.pk === 1 && (
                                <Key className="w-3 h-3 text-amber-400 shrink-0" title="Primary Key" />
                              )}
                              <span className="text-[10px] text-slate-500 font-normal">
                                ({c.type})
                              </span>
                              {sortBy === c.name ? (
                                sortOrder === 'asc' ? (
                                  <ArrowUp className="w-3 h-3 text-cyan-400 shrink-0" />
                                ) : (
                                  <ArrowDown className="w-3 h-3 text-cyan-400 shrink-0" />
                                )
                              ) : (
                                <ArrowUpDown className="w-2.5 h-2.5 opacity-30 group-hover:opacity-100 shrink-0" />
                              )}
                            </div>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {filteredRows.length === 0 ? (
                        <tr>
                          <td colSpan={Math.max(columns.length + 1, 1)} className="p-12 text-center text-slate-500">
                            <div className="flex flex-col items-center justify-center space-y-3">
                              <CheckCircle2 className="w-10 h-10 text-emerald-400/60" />
                              <div className="space-y-1">
                                <p className="text-sm font-semibold text-slate-300">
                                  Tabla `{selectedTable}` 100% Limpia
                                </p>
                                <p className="text-xs text-slate-400 max-w-md">
                                  No hay usuarios de prueba ni registros simulados. Las {columns.length} columnas están listas para recibir datos reales del bot de Discord.
                                </p>
                              </div>
                            </div>
                          </td>
                        </tr>
                      ) : (
                        filteredRows.map((row, idx) => (
                          <tr 
                            key={`db-row-${idx}`} 
                            onClick={() => setInspectRow(row)}
                            className="hover:bg-slate-900/60 transition-colors cursor-pointer group"
                          >
                            <td className="p-2.5 text-center text-slate-600 group-hover:text-cyan-400">
                              {(page - 1) * limit + idx + 1}
                            </td>
                            {columns.map(c => {
                              const val = row[c.name];
                              const isUserCol = c.name === 'username' || c.name === 'display_name';
                              const isMoneyCol = c.name === 'cash' || c.name === 'bank' || c.name === 'dirty_money' || c.name === 'budget' || c.name === 'price' || c.name === 'amount';
                              
                              return (
                                <td key={`td-${idx}-${c.name}`} className="p-2.5 max-w-xs truncate whitespace-nowrap text-slate-300">
                                  {val === null || val === undefined ? (
                                    <span className="text-slate-600 italic">null</span>
                                  ) : typeof val === 'boolean' || val === 0 || val === 1 && c.type.toUpperCase() === 'BOOLEAN' ? (
                                    <span className={`inline-flex px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                      Boolean(val) && val !== 0 ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/60' : 'bg-rose-950 text-rose-400 border border-rose-800/60'
                                    }`}>
                                      {Boolean(val) && val !== 0 ? 'true' : 'false'}
                                    </span>
                                  ) : isUserCol && val ? (
                                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-cyan-950/80 border border-cyan-800/60 text-cyan-300 font-semibold">
                                      <span>@{String(val)}</span>
                                    </span>
                                  ) : isMoneyCol && !isNaN(Number(val)) ? (
                                    <span className="text-emerald-400 font-semibold font-mono">
                                      ${Number(val).toLocaleString()}
                                    </span>
                                  ) : typeof val === 'object' ? (
                                    <span className="text-purple-300 text-[11px] bg-purple-950/60 px-1.5 py-0.5 rounded border border-purple-800/40">
                                      {JSON.stringify(val).slice(0, 30)}...
                                    </span>
                                  ) : (
                                    String(val)
                                  )}
                                </td>
                              );
                            })}
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                )}
              </div>

              {/* Pagination & Limit Bar */}
              <div className="p-3 bg-slate-900 border-t border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
                <div className="text-slate-400 flex items-center gap-2 font-mono">
                  <span>Mostrando {rows.length} de {totalCount} registros</span>
                  <span className="text-slate-600">|</span>
                  <span>Tabla: <strong className="text-white">{selectedTable}</strong></span>
                </div>

                <div className="flex items-center gap-3">
                  {/* Rows Limit Selector */}
                  <div className="flex items-center gap-1.5">
                    <span className="text-slate-500 text-[11px]">Filas:</span>
                    <select
                      value={limit}
                      onChange={(e) => setLimit(Number(e.target.value))}
                      className="bg-slate-950 border border-slate-800 rounded-lg px-2 py-1 text-slate-300 text-xs focus:outline-none focus:border-cyan-500 cursor-pointer"
                    >
                      <option value={25}>25</option>
                      <option value={50}>50</option>
                      <option value={100}>100</option>
                      <option value={250}>250</option>
                      <option value={500}>500</option>
                    </select>
                  </div>

                  {/* Pagination Buttons */}
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => handlePageChange(page - 1)}
                      disabled={page <= 1}
                      className="p-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-40 transition-colors cursor-pointer"
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </button>
                    <span className="px-2 font-mono text-slate-300">
                      {page} / {totalPages}
                    </span>
                    <button
                      onClick={() => handlePageChange(page + 1)}
                      disabled={page >= totalPages}
                      className="p-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-40 transition-colors cursor-pointer"
                    >
                      <ChevronRight className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* VIEW MODE 2: SCHEMA INSPECTOR */}
          {viewMode === 'schema' && (
            <div className="flex-1 overflow-auto p-4 space-y-4 font-mono text-xs">
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-bold text-white">Estructura SQL de `{selectedTable}`</h4>
                  <p className="text-xs text-slate-400 font-sans mt-0.5">
                    Definición de campos, tipos de datos SQLite/Postgres y restricciones de integridad.
                  </p>
                </div>
                <span className="px-2.5 py-1 rounded-lg bg-cyan-950 text-cyan-300 border border-cyan-800/60 font-bold">
                  {columns.length} Columnas
                </span>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
                <table className="w-full text-left">
                  <thead className="bg-slate-950/80 text-slate-400 border-b border-slate-800">
                    <tr>
                      <th className="p-3">Columna</th>
                      <th className="p-3">Tipo de Dato</th>
                      <th className="p-3">Primary Key</th>
                      <th className="p-3">NOT NULL</th>
                      <th className="p-3">Valor por Defecto</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {columns.map((c, idx) => (
                      <tr key={`col-schema-${c.name}-${idx}`} className="hover:bg-slate-800/40">
                        <td className="p-3 font-bold text-cyan-300 flex items-center gap-1.5">
                          {c.pk === 1 && <Key className="w-3.5 h-3.5 text-amber-400" />}
                          <span>{c.name}</span>
                        </td>
                        <td className="p-3 text-slate-300 font-semibold">
                          <span className="px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-indigo-300">
                            {c.type}
                          </span>
                        </td>
                        <td className="p-3">
                          {c.pk === 1 ? (
                            <span className="px-1.5 py-0.5 rounded bg-amber-950 border border-amber-800/60 text-amber-300 text-[10px] font-bold">
                              PRIMARY KEY
                            </span>
                          ) : (
                            <span className="text-slate-600">-</span>
                          )}
                        </td>
                        <td className="p-3">
                          {c.notnull === 1 ? (
                            <span className="px-1.5 py-0.5 rounded bg-rose-950/80 border border-rose-800/60 text-rose-300 text-[10px]">
                              NOT NULL
                            </span>
                          ) : (
                            <span className="text-slate-500">NULL</span>
                          )}
                        </td>
                        <td className="p-3 text-slate-400">
                          {c.dflt_value !== null ? (
                            <span className="text-emerald-400">{String(c.dflt_value)}</span>
                          ) : (
                            <span className="text-slate-600 italic">none</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* VIEW MODE 3: LIVE SQL CONSOLE */}
          {viewMode === 'sql' && (
            <div className="flex-1 flex flex-col overflow-hidden p-4 space-y-3 font-mono text-xs">
              
              {/* Presets */}
              <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
                <span className="text-[11px] text-slate-500 font-sans shrink-0">Consultas rápidas:</span>
                {[
                  `SELECT * FROM dni_records LIMIT 25;`,
                  `SELECT * FROM weapon_registries LIMIT 25;`,
                  `SELECT * FROM work_submissions LIMIT 25;`,
                  `SELECT * FROM applications LIMIT 25;`,
                  `SELECT * FROM users LIMIT 25;`,
                  `SELECT * FROM departments LIMIT 25;`,
                  `SELECT * FROM items LIMIT 25;`,
                  `PRAGMA table_info(dni_records);`
                ].map((q, qIdx) => (
                  <button
                    key={`q-preset-${qIdx}`}
                    onClick={() => setSqlQuery(q)}
                    className="px-2 py-1 rounded bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 text-[10px] whitespace-nowrap cursor-pointer transition-colors"
                  >
                    {q.slice(0, 34)}...
                  </button>
                ))}
              </div>

              {/* Editor Box */}
              <div className="flex flex-col gap-2">
                <div className="relative">
                  <textarea
                    rows={3}
                    value={sqlQuery}
                    onChange={(e) => setSqlQuery(e.target.value)}
                    placeholder="Escribe tu consulta SQL (ej. SELECT * FROM users)..."
                    className="w-full p-3 rounded-xl bg-slate-900 border border-slate-800 text-cyan-300 focus:outline-none focus:border-cyan-500 font-mono text-xs resize-none"
                  />
                  <button
                    onClick={handleExecuteSql}
                    disabled={sqlLoading || !sqlQuery.trim()}
                    className="absolute right-2.5 bottom-3.5 px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-bold flex items-center gap-1.5 disabled:opacity-50 transition-all cursor-pointer shadow-md"
                  >
                    {sqlLoading ? (
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Terminal className="w-3.5 h-3.5" />
                    )}
                    <span>Ejecutar</span>
                  </button>
                </div>
              </div>

              {/* Output Error / Results */}
              <div className="flex-1 overflow-auto bg-slate-900 border border-slate-800 rounded-xl">
                {sqlError ? (
                  <div className="p-4 text-rose-400 bg-rose-950/40 border border-rose-800/60 rounded-lg m-3 flex items-start gap-2">
                    <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-bold">Error SQL:</p>
                      <p className="mt-0.5">{sqlError}</p>
                    </div>
                  </div>
                ) : sqlResults ? (
                  <div className="overflow-auto h-full">
                    <div className="p-2.5 bg-slate-950/80 border-b border-slate-800 flex items-center justify-between text-[11px] text-slate-400">
                      <span>Resultados: <strong className="text-white">{sqlResults.rowCount}</strong> filas devueltas</span>
                      {sqlResults.executionTimeMs !== undefined && (
                        <span>Tiempo: <strong className="text-emerald-400">{sqlResults.executionTimeMs} ms</strong></span>
                      )}
                    </div>
                    {sqlResults.rows.length === 0 ? (
                      <div className="p-8 text-center text-slate-500">
                        0 filas devueltas por la consulta.
                      </div>
                    ) : (
                      <table className="w-full text-left">
                        <thead className="bg-slate-950 text-slate-400 sticky top-0 border-b border-slate-800">
                          <tr>
                            {sqlResults.columns.map(col => (
                              <th key={`sql-col-${col}`} className="p-2.5 font-semibold text-slate-300 whitespace-nowrap">
                                {col}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60">
                          {sqlResults.rows.map((r, rIdx) => (
                            <tr key={`sql-r-${rIdx}`} className="hover:bg-slate-800/40">
                              {sqlResults.columns.map(col => (
                                <td key={`sql-c-${rIdx}-${col}`} className="p-2.5 whitespace-nowrap max-w-xs truncate text-slate-300">
                                  {r[col] === null ? (
                                    <span className="text-slate-600 italic">null</span>
                                  ) : (
                                    String(r[col])
                                  )}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                ) : (
                  <div className="p-8 text-center text-slate-500 flex flex-col items-center justify-center space-y-2">
                    <Terminal className="w-8 h-8 opacity-30" />
                    <p className="text-xs">Escribe una consulta SQL o haz clic en un preset para ejecutarla en vivo.</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* VIEW MODE 4: SUPABASE SCHEMA SQL */}
          {viewMode === 'sql_file' && (
            <div className="flex-1 flex flex-col overflow-hidden bg-slate-950 p-4 space-y-3">
              <div className="flex items-center justify-between bg-slate-900 px-4 py-2.5 rounded-xl border border-slate-800">
                <div className="flex items-center gap-2 text-xs">
                  <Code className="w-4 h-4 text-emerald-400" />
                  <span className="font-bold text-white font-mono">supabase/schema.sql</span>
                  <span className="text-slate-400 font-sans">(Script DDL oficial para Supabase PostgreSQL)</span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(schemaSql);
                      setCopiedSql(true);
                      setTimeout(() => setCopiedSql(false), 2000);
                    }}
                    className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold text-xs flex items-center gap-1.5 transition-all cursor-pointer shadow-sm"
                  >
                    {copiedSql ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copiedSql ? '¡Copiado!' : 'Copiar Todo el SQL'}</span>
                  </button>
                  <button
                    onClick={() => {
                      const blob = new Blob([schemaSql], { type: 'text/sql' });
                      const link = document.createElement('a');
                      link.href = URL.createObjectURL(blob);
                      link.download = 'supabase_schema.sql';
                      link.click();
                    }}
                    className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs transition-colors cursor-pointer"
                    title="Descargar archivo schema.sql"
                  >
                    <Download className="w-4 h-4" />
                  </button>
                </div>
              </div>

              <div className="flex-1 overflow-auto rounded-xl bg-slate-900 border border-slate-800 p-4 font-mono text-xs text-slate-300">
                <pre className="whitespace-pre-wrap leading-relaxed select-text">
                  {schemaSql || '-- Cargando esquema de Supabase...'}
                </pre>
              </div>
            </div>
          )}

          {/* VIEW MODE 5: SUPABASE CONNECTION GUIDE */}
          {viewMode === 'connection' && (
            <div className="flex-1 flex flex-col overflow-auto bg-slate-950 p-6 space-y-6">
              <div className="p-4 rounded-2xl bg-emerald-950/20 border border-emerald-800/40">
                <div className="flex items-start gap-3">
                  <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <h4 className="text-sm font-bold text-emerald-300">
                      Conexión Activa de Supabase PostgreSQL
                    </h4>
                    <p className="text-xs text-slate-300 leading-relaxed font-sans">
                      El bot de Miami Vice RP utiliza una arquitectura de alta disponibilidad. Si configuras la variable <code className="text-emerald-400 font-mono font-bold bg-slate-900 px-1.5 py-0.5 rounded">SUPABASE_DB_URL</code> o <code className="text-emerald-400 font-mono font-bold bg-slate-900 px-1.5 py-0.5 rounded">DATABASE_URL</code>, el bot se conecta a Supabase PostgreSQL a través de un pool de conexiones con SSL. En caso de no estar configurada o en modo local, conmuta a SQLite sin detener el bot.
                    </p>
                  </div>
                </div>
              </div>

              {/* Technical Details Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs font-mono">
                <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
                  <span className="text-slate-400">Estado de Conexión:</span>
                  <div className="text-white font-bold flex items-center gap-1.5 text-sm">
                    <span className={`w-2 h-2 rounded-full ${supabaseInfo?.connected ? 'bg-emerald-400' : 'bg-amber-400'}`}></span>
                    {supabaseInfo?.connected ? 'Operativo (OK)' : 'Fallback Local'}
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
                  <span className="text-slate-400">Motor Activo:</span>
                  <div className="text-emerald-400 font-bold text-sm">
                    {supabaseInfo?.backend === 'supabase' ? 'PostgreSQL (Supabase Cloud)' : 'SQLite Local (Fallback)'}
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
                  <span className="text-slate-400">Host Supabase:</span>
                  <div className="text-slate-200 break-all font-bold">
                    {supabaseInfo?.host || 'Local Storage'}
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
                  <span className="text-slate-400">Nombre de la Base de Datos:</span>
                  <div className="text-slate-200 font-bold">
                    {supabaseInfo?.database || 'postgres'}
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
                  <span className="text-slate-400">Modo SSL / Cifrado:</span>
                  <div className="text-cyan-400 font-bold">
                    {supabaseInfo?.sslMode || 'require'} (TLS Encrypted)
                  </div>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 space-y-1">
                  <span className="text-slate-400">Versión del Esquema:</span>
                  <div className="text-slate-200 font-bold">
                    {supabaseInfo?.schemaVersion || 'v2.6.0'}
                  </div>
                </div>
              </div>

              {/* Instructions */}
              <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-3 font-sans text-xs">
                <h4 className="font-bold text-white text-sm flex items-center gap-2">
                  <Terminal className="w-4 h-4 text-cyan-400" />
                  <span>Cómo conectar tu proyecto Supabase</span>
                </h4>
                <ol className="list-decimal list-inside space-y-2 text-slate-300">
                  <li>
                    Ingresa a tu proyecto en <strong className="text-emerald-400">supabase.com</strong> &gt; <strong className="text-white">Project Settings</strong> &gt; <strong className="text-white">Database</strong>.
                  </li>
                  <li>
                    Copia la URI de conexión (Connection String).
                  </li>
                  <li>
                    Configura la variable de entorno en tu hosting o archivo <code className="bg-slate-950 px-1 py-0.5 rounded text-cyan-400 font-mono">.env</code>:
                    <div className="p-2.5 mt-1 rounded-lg bg-slate-950 border border-slate-800 font-mono text-[11px] text-emerald-300 select-all overflow-x-auto">
                      SUPABASE_DB_URL="postgresql://postgres:[TU_PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres"
                    </div>
                  </li>
                  <li>
                    Ejecuta el script SQL en el <strong className="text-white">SQL Editor</strong> de Supabase para tener creadas las 54 tablas con sus relaciones.
                  </li>
                </ol>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Row Detail Inspector Modal */}
      {inspectRow && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden shadow-2xl">
            <div className="p-4 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Eye className="w-4 h-4 text-cyan-400" />
                <h3 className="text-sm font-bold text-white font-mono">
                  Registro de `{selectedTable}`
                </h3>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => copyToClipboard(JSON.stringify(inspectRow, null, 2), 'all')}
                  className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-1.5 transition-colors cursor-pointer"
                >
                  {copiedField === 'all' ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copiedField === 'all' ? 'Copiado' : 'Copiar JSON'}</span>
                </button>
                <button
                  onClick={() => setInspectRow(null)}
                  className="p-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-auto p-4 space-y-3 font-mono text-xs">
              {Object.entries(inspectRow).map(([key, val]) => (
                <div key={`inspect-field-${key}`} className="p-2.5 rounded-xl bg-slate-950 border border-slate-800/80 flex items-start justify-between gap-3 group">
                  <div className="truncate">
                    <span className="text-cyan-400 font-semibold">{key}:</span>
                    <div className="mt-1 text-slate-200 break-all font-sans text-xs">
                      {val === null ? (
                        <span className="text-slate-600 italic">null</span>
                      ) : typeof val === 'object' ? (
                        <pre className="p-2 rounded bg-slate-900 text-slate-300 font-mono text-[11px] overflow-auto">
                          {JSON.stringify(val, null, 2)}
                        </pre>
                      ) : (
                        String(val)
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => copyToClipboard(String(val), key)}
                    className="p-1 rounded bg-slate-900 hover:bg-slate-800 text-slate-400 hover:text-slate-200 opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer shrink-0"
                    title="Copiar valor"
                  >
                    {copiedField === key ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Wipe Clean Confirmation Modal */}
      {wipeModalOpen && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-rose-900/60 rounded-2xl w-full max-w-md p-6 space-y-4 shadow-2xl">
            <div className="w-12 h-12 rounded-2xl bg-rose-950 border border-rose-800 flex items-center justify-center text-rose-400 mx-auto">
              <Trash2 className="w-6 h-6" />
            </div>

            <div className="text-center space-y-1.5">
              <h3 className="text-base font-bold text-white">¿Limpiar todas las tablas?</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Esta acción eliminará <strong>todos los usuarios de prueba, transacciones, empresas y registros temporales</strong> en las 38 tablas de la base de datos, dejándolas 100% limpias y listas para producción.
              </p>
            </div>

            {wipeSuccess && (
              <div className="p-3 rounded-xl bg-emerald-950/80 border border-emerald-800/80 text-emerald-300 text-xs font-semibold flex items-center gap-2 justify-center">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>{wipeSuccess}</span>
              </div>
            )}

            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={() => setWipeModalOpen(false)}
                disabled={wiping}
                className="flex-1 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold transition-colors cursor-pointer"
              >
                Cancelar
              </button>
              <button
                onClick={handleWipeClean}
                disabled={wiping}
                className="flex-1 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold transition-all shadow-lg shadow-rose-900/30 flex items-center justify-center gap-1.5 cursor-pointer"
              >
                {wiping ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Limpiando...</span>
                  </>
                ) : (
                  <>
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Confirmar Limpieza</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
