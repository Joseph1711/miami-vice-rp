"""Database adapter for the Miami Vice bot (Exclusively Supabase PostgreSQL).

Directly connects to Supabase PostgreSQL. Local SQLite fallback has been completely removed.
"""
import asyncio
import logging
import os
import re
import time

logger = logging.getLogger("bot.db")

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    try:
        import psycopg2 as psycopg
        import psycopg2.extras
        dict_row = psycopg2.extras.RealDictCursor
    except ImportError:
        psycopg = None
        dict_row = None

_DOLLAR_RE = re.compile(r"\$(\d+)")

def _sanitize_pg_url(url: str | None) -> str:
    if not url:
        return ""
    # Strip accidental brackets around password (e.g. postgres:[password]@host)
    cleaned = re.sub(r":\[([^\]]+)\]@", r":\1@", url.strip())
    cleaned = re.sub(r":%5B([^%]+)%5D@", r":\1@", cleaned, flags=re.IGNORECASE)
    return cleaned

DEFAULT_DATABASE_URL = "postgresql://postgres:102093qvweerr@db.lbsmuouljgdcaxlcsnsb.supabase.co:5432/postgres"
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

logger.info(f"[DB] Backend: Supabase PostgreSQL Exclusivo | DATABASE_URL: {'✅' if DATABASE_URL else '❌'}")


def _prepare_query_and_params(query: str, params=None):
    """
    Translates Postgres-style numbered parameters ($1, $2, $1, etc.) into driver-compatible format (%s).
    Handles duplicate placeholders safely by duplicating bindings in positional order.
    Guarantees that generated placeholder count matches the parameter tuple length exactly.
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


def _ensure_schema_migrations(conn):
    """Adds missing columns if needed on Supabase PostgreSQL."""
    try:
        with conn.cursor() as cursor:
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name TEXT")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS roblox_username TEXT")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS roblox_id TEXT")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS roblox_profile_url TEXT")
            cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS dni_number TEXT")
            cursor.execute("ALTER TABLE department_members ADD COLUMN IF NOT EXISTS username TEXT")
            cursor.execute("ALTER TABLE company_members ADD COLUMN IF NOT EXISTS username TEXT")
            cursor.execute("ALTER TABLE dni_records ADD COLUMN IF NOT EXISTS occupation TEXT DEFAULT 'Ciudadano'")
            cursor.execute("ALTER TABLE dni_records ADD COLUMN IF NOT EXISTS age INTEGER DEFAULT 18")
            cursor.execute("ALTER TABLE weapon_registries ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()")
        conn.commit()
    except Exception as e:
        logger.debug(f"[DB] Migration check notice: {e}")


def _connect_postgres():
    if psycopg is None:
        raise RuntimeError("Falta psycopg o psycopg2 instalado. Instala las dependencias con pip install psycopg[binary].")
    if not DATABASE_URL:
        raise RuntimeError("SUPABASE_DB_URL no está configurada.")
    
    # psycopg 3 vs psycopg 2 check
    if hasattr(psycopg, "connect") and "row_factory" in getattr(psycopg.connect, "__code__", type("", (), {"co_varnames": ()})).co_varnames:
        conn = psycopg.connect(
            DATABASE_URL,
            connect_timeout=10,
            options=f"-c statement_timeout={DB_STATEMENT_TIMEOUT_MS} -c lock_timeout={min(DB_STATEMENT_TIMEOUT_MS, 3000)}",
            row_factory=dict_row,
        )
    else:
        conn = psycopg.connect(
            DATABASE_URL,
            connect_timeout=10,
            options=f"-c statement_timeout={DB_STATEMENT_TIMEOUT_MS} -c lock_timeout={min(DB_STATEMENT_TIMEOUT_MS, 3000)}",
        )
    _ensure_schema_migrations(conn)
    return conn


def _connect():
    return _connect_postgres()


def is_postgres() -> bool:
    return True


def get_conn():
    return _connect()


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
    return None


def execute(query, params=None, fetch=None):
    conn = _connect()
    raw, safe_params = _prepare_query_and_params(query, params)
    started = time.monotonic()
    try:
        with conn.cursor() as cursor:
            cursor.execute(raw, safe_params or ())
            result = _fetch_result(cursor, fetch)
        conn.commit()
        elapsed_ms = (time.monotonic() - started) * 1000
        if elapsed_ms > SLOW_QUERY_MS:
            logger.warning("[DB][SLOW %.0fms] %s", elapsed_ms, raw[:120])
        return result
    except Exception as error:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.error("[DB] Error en query: %s | Query: %s | Params: %s", error, raw[:200], safe_params)
        raise
    finally:
        conn.close()


def execute_many(queries):
    conn = _connect()
    started = time.monotonic()
    try:
        with conn.cursor() as cursor:
            for query, params in queries:
                raw, safe_params = _prepare_query_and_params(query, params)
                cursor.execute(raw, safe_params or ())
        conn.commit()
        elapsed_ms = (time.monotonic() - started) * 1000
        if elapsed_ms > SLOW_QUERY_MS:
            logger.warning("[DB][SLOW BATCH %.0fms] %s queries", elapsed_ms, len(queries))
    except Exception as error:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.error("[DB] Error en execute_many: %s", error)
        raise
    finally:
        conn.close()


def initialize_schema(schema: str):
    conn = _connect()
    try:
        with conn.cursor() as cursor:
            for statement in schema.split(";"):
                if statement.strip():
                    cursor.execute(statement)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
        conn = _connect_postgres()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 AS ok")
                row = cursor.fetchone()
                result["ok"] = bool(row)
        finally:
            conn.close()
    except Exception as pg_err:
        result["error"] = str(pg_err)
    return result
