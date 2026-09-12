export interface TableMeta {
  name: string;
  count: number;
  columnsCount: number;
  category: string;
  description: string;
}

export interface DbStats {
  tables: TableMeta[];
  totalTables: number;
  totalRows: number;
  userCount: number;
  totalEconomy: number;
  totalCash: number;
  totalBank: number;
}

export interface ColumnMeta {
  cid?: number;
  name: string;
  type: string;
  notnull: number;
  dflt_value: any;
  pk: number;
}

export interface SupabaseInfo {
  connected: boolean;
  backend: 'supabase' | 'sqlite';
  urlConfigured: boolean;
  maskedUrl?: string;
  host?: string;
  database?: string;
  port?: number;
  sslMode?: string;
  latencyMs?: number;
  totalTables: number;
  schemaVersion: string;
}
