"""Database adapter for the Miami Vice bot (Exclusively Supabase PostgreSQL).

Directly connects to Supabase PostgreSQL with connection pooling, automatic reconnection,
and transaction rollback recovery.
"""
import asyncio
import logging
import os
import re
import threading
import time
from contextlib import contextmanager

logger = logging.getLogger("bot.db")

try:
    import psycopg2
    from psycopg2 import pool, extras, extensions
    dict_cursor = extras.RealDictCursor
except ImportError:
    try:
        import psycopg
        from psycopg.rows import dict_row as dict_cursor
        psycopg2 = None
    except ImportError:
        psycopg2 = None
        psycopg = None
        dict_cursor = None

_DOLLAR_RE = re.compile(r"\$(\d+)")

def _sanitize_pg_url(url: str | None) -> str:
    if not url:
        return ""
    # Strip accidental brackets around password (e.g. postgres:[password]@host)
    cleaned = re.sub(r":\[([^\]]+)\]@", r":\1@", url.strip())
    cleaned = re.sub(r":%5B([^%]+)%5D@", r":\1@", cleaned, flags=re.IGNORECASE)
    if cleaned.startswith("postgres://"):
        cleaned = "postgresql://" + cleaned[len("postgres://"):]
    if "sslmode=" not in cleaned:
        sep = "&" if "?" in cleaned else "?"
        cleaned = f"{cleaned}{sep}sslmode=require"
    return cleaned

DEFAULT_DATABASE_URL = "postgresql://postgres.lbsmuouljgdcaxlcsnsb:102093qvweerr@aws-0-us-west-2.pooler.supabase.com:6543/postgres?sslmode=require"
_raw_url = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL
DATABASE_URL = _sanitize_pg_url(_raw_url)

DB_BACKEND = "supabase"
USE_POSTGRES = True
DB_PATH = None
SLOW_QUERY_MS = 500

try:
    DB_OPERATION_TIMEOUT_SECONDS = max(1.0, float(os.environ.get("DB_OPERATION_TIMEOUT_SECONDS", "10")))
except ValueError:
    DB_OPERATION_TIMEOUT_SECONDS = 10.0
DB_STATEMENT_TIMEOUT_MS = int(DB_OPERATION_TIMEOUT_SECONDS * 1000)

_connection_pool = None
_pool_lock = threading.Lock()

def _ensure_schema_migrations(conn):
    """Verifica y añade columnas faltantes si es necesario en Supabase PostgreSQL."""
    try:
        cursor_cls = dict_cursor if dict_cursor else None
        with conn.cursor(cursor_factory=cursor_cls) if cursor_cls else conn.cursor() as cursor:
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name TEXT")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS roblox_username TEXT")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS roblox_id TEXT")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS roblox_profile_url TEXT")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS dni_number TEXT")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS criminal_records (
                    id TEXT PRIMARY KEY,
                    guild_id TEXT NOT NULL,
                    discord_id TEXT NOT NULL,
                    crime_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    fine_amount BIGINT DEFAULT 0,
                    jail_time_minutes INTEGER DEFAULT 0,
                    officer_id TEXT NOT NULL,
                    officer_name TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS guild_configs (
                    id TEXT PRIMARY KEY,
                    guild_id TEXT UNIQUE NOT NULL,
                    police_role_ids TEXT,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
            cursor.execute("ALTER TABLE ticket_config ADD COLUMN IF NOT EXISTS max_open_tickets INTEGER DEFAULT 3")
            cursor.execute("ALTER TABLE ticket_config ADD COLUMN IF NOT EXISTS category_id TEXT")
            cursor.execute("ALTER TABLE ticket_config ADD COLUMN IF NOT EXISTS support_role_id TEXT")
            cursor.execute("ALTER TABLE ticket_config ADD COLUMN IF NOT EXISTS log_channel_id TEXT")
            cursor.execute("ALTER TABLE ticket_config ADD COLUMN IF NOT EXISTS panel_channel_id TEXT")
            cursor.execute("ALTER TABLE ticket_config ADD COLUMN IF NOT EXISTS transcripts_channel_id TEXT")
            cursor.execute("ALTER TABLE verification_config ADD COLUMN IF NOT EXISTS roles_to_add TEXT")
            cursor.execute("ALTER TABLE verification_config ADD COLUMN IF NOT EXISTS roles_to_remove TEXT")
            cursor.execute("ALTER TABLE verification_config ADD COLUMN IF NOT EXISTS verified_role_id TEXT")
            cursor.execute("ALTER TABLE verification_config ADD COLUMN IF NOT EXISTS log_channel_id TEXT")
            cursor.execute("ALTER TABLE verification_config ADD COLUMN IF NOT EXISTS min_account_age_days INTEGER DEFAULT 0")
            cursor.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS category TEXT")
            cursor.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS channel_id TEXT")
            cursor.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS creator_id TEXT")
            cursor.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS reason TEXT")
            cursor.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS subject TEXT")
            cursor.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'open'")
            cursor.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS claimed_by TEXT")
            cursor.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS closed_by TEXT")
    except Exception as e:
        logger.debug(f"[DB] Migration check notice: {e}")

def get_connection_pool(force_reconnect: bool = False):
    global _connection_pool
    with _pool_lock:
        if force_reconnect and _connection_pool is not None:
            try:
                _connection_pool.closeall()
            except Exception:
                pass
            _connection_pool = None

        if _connection_pool is None or (hasattr(_connection_pool, "closed") and _connection_pool.closed):
            if psycopg2 is None:
                return None
            
            last_err = None
            for attempt in range(1, 4):
                try:
                    _connection_pool = pool.ThreadedConnectionPool(
                        minconn=1,
                        maxconn=15,
                        dsn=DATABASE_URL,
                        connect_timeout=10,
                        options=f"-c statement_timeout={DB_STATEMENT_TIMEOUT_MS} -c lock_timeout={min(DB_STATEMENT_TIMEOUT_MS, 3000)}",
                        keepalives=1,
                        keepalives_idle=30,
                        keepalives_interval=10,
                        keepalives_count=5
                    )
                    logger.info("[DB] Supabase PostgreSQL Connection Pool inicializado correctamente.")
                    # Ejecutar comprobación de migraciones inicial
                    try:
                        init_conn = _connection_pool.getconn()
                        _ensure_schema_migrations(init_conn)
                        _connection_pool.putconn(init_conn)
                    except Exception:
                        pass
                    break
                except Exception as e:
                    last_err = e
                    logger.warning(f"[DB] Reintentando inicializar pool ({attempt}/3): {e}")
                    time.sleep(1.0 * attempt)
            
            if _connection_pool is None:
                logger.error(f"[DB] No se pudo inicializar el Connection Pool: {last_err}")
                raise RuntimeError(f"Fallo al conectar a Supabase: {last_err}")

        return _connection_pool


def _prepare_query_and_params(query: str, params=None):
    """
    Translates Postgres-style numbered parameters ($1, $2, $1, etc.) into driver-compatible format (%s).
    Handles duplicate placeholders safely by duplicating bindings in positional order.
    """
    if not params:
        raw = _DOLLAR_RE.sub("%s", query)
        return raw, ()

    matches = _DOLLAR_RE.findall(query)
    p_seq = list(params) if isinstance(params, (list, tuple)) else [params]

    if matches:
        new_params = []
        for m in matches:
            idx = int(m) - 1
            if 0 <= idx < len(p_seq):
                new_params.append(p_seq[idx])
            else:
                new_params.append(p_seq[-1] if p_seq else None)

        raw = _DOLLAR_RE.sub("%s", query)
        return raw, tuple(new_params)

    raw = query
    return raw, tuple(p_seq)


def _mask_url(url: str | None) -> str:
    if not url:
        return "no configurada"
    return re.sub(r"(://[^:]+:)[^@]+@", r"\1***@", url)


def connection_label() -> str:
    return f"Supabase Postgres — {_mask_url(DATABASE_URL)}"


@contextmanager
def get_db_connection():
    """Context manager para obtener y devolver una conexión limpia y recuperable."""
    c_pool = get_connection_pool()
    conn = None
    if c_pool is not None:
        try:
            conn = c_pool.getconn()
        except Exception as e:
            logger.warning(f"[DB] Error al obtener del pool: {e}. Forzando reconexión del pool...")
            c_pool = get_connection_pool(force_reconnect=True)
            conn = c_pool.getconn()

        try:
            if conn.closed != 0:
                raise psycopg2.OperationalError("Conexión en pool ya cerrada")
            conn.autocommit = True
        except Exception:
            try:
                c_pool.putconn(conn, close=True)
            except Exception:
                pass
            c_pool = get_connection_pool(force_reconnect=True)
            conn = c_pool.getconn()
            conn.autocommit = True
    else:
        # Fallback sin pool
        conn = psycopg2.connect(DATABASE_URL) if psycopg2 else psycopg.connect(DATABASE_URL)
        conn.autocommit = True

    try:
        yield conn
    except Exception as e:
        if conn is not None:
            try:
                if conn.closed == 0:
                    conn.rollback()
            except Exception:
                pass
        raise e
    finally:
        if conn is not None:
            if c_pool is not None:
                try:
                    if conn.closed != 0:
                        c_pool.putconn(conn, close=True)
                    else:
                        # Limpiar estado si hubo abort previo
                        try:
                            if hasattr(conn, "get_transaction_status"):
                                if conn.get_transaction_status() == extensions.TRANSACTION_STATUS_ERROR:
                                    conn.rollback()
                        except Exception:
                            pass
                        conn.autocommit = True
                        c_pool.putconn(conn)
                except Exception as e:
                    logger.debug(f"[DB] Error devolviendo conexion al pool: {e}")
            else:
                try:
                    conn.close()
                except Exception:
                    pass


def _fetch_result(cursor, fetch):
    if fetch == "one":
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row) if not isinstance(row, dict) else row
    if fetch == "all":
        rows = cursor.fetchall()
        return [dict(r) if not isinstance(r, dict) else r for r in rows]
    if fetch == "count":
        return cursor.rowcount
    if fetch is None and cursor.description:
        rows = cursor.fetchall()
        return [dict(r) if not isinstance(r, dict) else r for r in rows]
    return cursor.rowcount if cursor.rowcount >= 0 else None


def execute(query, params=None, fetch=None):
    raw, safe_params = _prepare_query_and_params(query, params)
    last_err = None
    
    for attempt in range(1, 4):
        started = time.monotonic()
        try:
            with get_db_connection() as conn:
                cursor_cls = dict_cursor if dict_cursor else None
                with conn.cursor(cursor_factory=cursor_cls) as cursor:
                    cursor.execute(raw, safe_params or ())
                    result = _fetch_result(cursor, fetch)
                    
                elapsed_ms = (time.monotonic() - started) * 1000
                if elapsed_ms > SLOW_QUERY_MS:
                    logger.warning("[DB][SLOW %.0fms] %s", elapsed_ms, raw[:120])
                return result
        except (psycopg2.OperationalError, psycopg2.InterfaceError) if psycopg2 else Exception as e:
            last_err = e
            logger.warning(f"[DB] Reintento de consulta tras error transitorio ({attempt}/3): {e}")
            if attempt == 2:
                get_connection_pool(force_reconnect=True)
            time.sleep(0.4 * attempt)
        except Exception as error:
            logger.error("[DB] Error en query: %s | Query: %s | Params: %s", error, raw[:200], safe_params)
            raise error

    if last_err:
        logger.error("[DB] Error final en query tras reintentos: %s | Query: %s", last_err, raw[:200])
        raise last_err


def execute_many(queries):
    started = time.monotonic()
    try:
        with get_db_connection() as conn:
            cursor_cls = dict_cursor if dict_cursor else None
            with conn.cursor(cursor_factory=cursor_cls) as cursor:
                for query, params in queries:
                    raw, safe_params = _prepare_query_and_params(query, params)
                    cursor.execute(raw, safe_params or ())
                    
            elapsed_ms = (time.monotonic() - started) * 1000
            if elapsed_ms > SLOW_QUERY_MS:
                logger.warning("[DB][SLOW BATCH %.0fms] %s queries", elapsed_ms, len(queries))
            return len(queries)
    except Exception as error:
        logger.error("[DB] Error en execute_many: %s", error)
        raise


def initialize_schema(schema: str):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            for statement in schema.split(";"):
                if statement.strip():
                    cursor.execute(statement)


async def _run_db_operation(operation, *args):
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(operation, *args),
            timeout=DB_OPERATION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as error:
        logger.error(
            "[DB] Operación cancelada por timeout (%.1fs)",
            DB_OPERATION_TIMEOUT_SECONDS,
        )
        raise TimeoutError("La base de datos Supabase tardó demasiado en responder") from error


async def aexecute(query, params=None, fetch=None):
    return await _run_db_operation(execute, query, params, fetch)


async def aexecute_many(queries):
    return await _run_db_operation(execute_many, queries)


def check_connection() -> dict:
    result = {
        "ok": False,
        "masked_url": _mask_url(DATABASE_URL),
        "error": None,
        "ssl": "Supabase SSL/TLS",
        "backend": "supabase",
    }
    try:
        rows = execute("SELECT 1 AS ok", fetch="one")
        if rows and rows.get("ok") == 1:
            result["ok"] = True
        else:
            result["error"] = "No se recibió confirmación de consulta"
    except Exception as pg_err:
        result["error"] = str(pg_err)
    return result

