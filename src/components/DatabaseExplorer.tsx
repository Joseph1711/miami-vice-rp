import React, { useState, useEffect } from 'react';
import { 
  Database, 
  Table, 
  Coins, 
  Users, 
  TrendingUp, 
  RefreshCw, 
  Sparkles, 
  CheckCircle2, 
  Layers,
  Search
} from 'lucide-react';

interface DbStats {
  tables: Array<{ name: string; count: number }>;
  totalTables: number;
  totalRows: number;
  userCount: number;
  totalEconomy: number;
  totalCash: number;
  totalBank: number;
}

export function DatabaseExplorer() {
  const [stats, setStats] = useState<DbStats | null>(null);
  const [selectedTable, setSelectedTable] = useState<string>('users');
  const [tableData, setTableData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [seedSuccess, setSeedSuccess] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

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

  const fetchTableData = async (tableName: string) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/database/table-data?table=${tableName}&limit=50`);
      if (res.ok) {
        const data = await res.json();
        setTableData(data.rows || []);
      }
    } catch (err) {
      console.error('Error fetching table data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
    // Auto-refresh stats every 5 seconds for real-time synchronization with Discord bot
    const interval = setInterval(() => {
      fetchStats();
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (selectedTable) {
      fetchTableData(selectedTable);
      // Auto-refresh active table data every 5 seconds
      const interval = setInterval(() => {
        fetchTableData(selectedTable);
      }, 5000);
      return () => clearInterval(interval);
    }
  }, [selectedTable]);

  const handleSeedDemo = async () => {
    setSeeding(true);
    try {
      const res = await fetch('/api/database/seed-demo-data', { method: 'POST' });
      if (res.ok) {
        setSeedSuccess(true);
        await fetchStats();
        await fetchTableData(selectedTable);
        setTimeout(() => setSeedSuccess(false), 3000);
      }
    } finally {
      setSeeding(false);
    }
  };

  const filteredRows = tableData.filter(row => {
    if (!searchTerm) return true;
    return JSON.stringify(row).toLowerCase().includes(searchTerm.toLowerCase());
  });

  const columns = tableData.length > 0 ? Object.keys(tableData[0]) : [];

  return (
    <div className="space-y-6">
      {/* Economy Overview Banner */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 shadow-md">
          <div className="text-xs text-slate-400 flex items-center gap-1.5 font-medium">
            <Users className="w-4 h-4 text-cyan-400" />
            <span>Usuarios Registrados</span>
          </div>
          <div className="text-2xl font-bold text-white mt-1">
            {stats?.userCount || 0}
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 shadow-md">
          <div className="text-xs text-slate-400 flex items-center gap-1.5 font-medium">
            <Coins className="w-4 h-4 text-emerald-400" />
            <span>Efectivo Total en Servidor</span>
          </div>
          <div className="text-2xl font-bold text-emerald-400 mt-1 font-mono">
            ${(stats?.totalCash || 0).toLocaleString()}
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 shadow-md">
          <div className="text-xs text-slate-400 flex items-center gap-1.5 font-medium">
            <TrendingUp className="w-4 h-4 text-indigo-400" />
            <span>Fondos en Banco</span>
          </div>
          <div className="text-2xl font-bold text-indigo-400 mt-1 font-mono">
            ${(stats?.totalBank || 0).toLocaleString()}
          </div>
        </div>

        <div className="p-4 rounded-2xl bg-slate-900 border border-slate-800 shadow-md">
          <div className="text-xs text-slate-400 flex items-center gap-1.5 font-medium">
            <Database className="w-4 h-4 text-amber-400" />
            <span>Tablas / Registros</span>
          </div>
          <div className="text-2xl font-bold text-amber-400 mt-1">
            {stats?.totalTables || 38} <span className="text-xs font-normal text-slate-400 font-sans">({stats?.totalRows || 0} filas)</span>
          </div>
        </div>
      </div>

      {/* Main Database Table Explorer */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Table Selector */}
        <div className="lg:col-span-1 bg-slate-900 border border-slate-800 rounded-2xl p-4 flex flex-col h-[550px]">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <Table className="w-4 h-4 text-cyan-400" />
              <h3 className="text-xs font-bold text-white uppercase tracking-wider">Tablas SQLite</h3>
            </div>
            <button
              onClick={handleSeedDemo}
              disabled={seeding}
              className="text-[10px] px-2 py-1 rounded bg-indigo-950 hover:bg-indigo-900 text-indigo-300 border border-indigo-800/60 font-semibold flex items-center gap-1 transition-colors cursor-pointer"
            >
              <Sparkles className="w-3 h-3" />
              <span>{seedSuccess ? 'Demo OK' : '+ Demo'}</span>
            </button>
          </div>

          <div className="mt-3 overflow-y-auto flex-1 space-y-1 pr-1 font-mono text-xs">
            {stats?.tables.map((t, tIdx) => {
              const isSelected = selectedTable === t.name;
              return (
                <button
                  key={`table-name-${t.name}-${tIdx}`}
                  onClick={() => setSelectedTable(t.name)}
                  className={`w-full text-left px-3 py-2 rounded-lg flex items-center justify-between transition-all ${
                    isSelected 
                      ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 font-medium' 
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                  }`}
                >
                  <span className="truncate">{t.name}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 shrink-0">
                    {t.count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Table Data Viewer */}
        <div className="lg:col-span-3 bg-slate-950 border border-slate-800 rounded-2xl flex flex-col h-[550px] overflow-hidden shadow-xl">
          <div className="px-4 py-3 bg-slate-900 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-bold text-white">SELECT * FROM {selectedTable}</span>
              <span className="text-xs text-slate-400">({filteredRows.length} registros cargados)</span>
            </div>

            <div className="flex items-center gap-2">
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2" />
                <input
                  type="text"
                  placeholder="Buscar en tabla..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-8 pr-3 py-1 text-xs rounded-lg bg-slate-950 border border-slate-800 text-slate-200 focus:outline-none focus:border-cyan-500 w-44"
                />
              </div>

              <button
                onClick={() => fetchTableData(selectedTable)}
                className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors"
                title="Refrescar tabla"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-auto">
            {loading ? (
              <div className="h-full flex items-center justify-center text-slate-400 gap-2">
                <RefreshCw className="w-5 h-5 animate-spin text-cyan-400" />
                <span>Cargando datos de {selectedTable}...</span>
              </div>
            ) : filteredRows.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-slate-500 space-y-2">
                <Table className="w-8 h-8 opacity-40" />
                <p className="text-xs">No hay filas en la tabla o no coinciden con la búsqueda.</p>
              </div>
            ) : (
              <table className="w-full text-left font-mono text-xs border-collapse">
                <thead className="bg-slate-900/90 text-slate-400 sticky top-0 border-b border-slate-800 z-10">
                  <tr>
                    {columns.map(c => (
                      <th key={`th-col-${c}`} className="p-2.5 font-semibold text-slate-300 whitespace-nowrap">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {filteredRows.map((row, idx) => (
                    <tr key={`db-row-${idx}-${row.id || idx}`} className="hover:bg-slate-900/40 transition-colors">
                      {columns.map(c => {
                        const isUserNameCol = c === 'username' || c === 'display_name';
                        return (
                          <td key={`td-${idx}-${c}`} className={`p-2.5 max-w-xs truncate whitespace-nowrap ${isUserNameCol ? 'text-cyan-300 font-semibold' : 'text-slate-300'}`}>
                            {row[c] === null ? (
                              <span className="text-slate-600 italic">null</span>
                            ) : typeof row[c] === 'boolean' ? (
                              <span className={row[c] ? 'text-emerald-400' : 'text-rose-400'}>
                                {row[c] ? 'true' : 'false'}
                              </span>
                            ) : isUserNameCol && row[c] ? (
                              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-cyan-950/80 border border-cyan-800/60 text-cyan-300">
                                <span>@{String(row[c])}</span>
                              </span>
                            ) : (
                              String(row[c])
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
