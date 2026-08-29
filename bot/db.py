"""Database adapter for the Miami Vice bot.

SQLite remains available for local development. Set SUPABASE_DB_URL (or
DATABASE_URL) and DB_BACKEND=supabase to use Supabase Postgres in production.
"""
import asyncio
import logging
import os
import re
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger("bot.db")

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

_DOLLAR_RE = re.compile(r"\$(\d+)")
_ROOT = Path(__file__).resolve().parent.parent

def _get_usable_sqlite_path() -> Path:
    """Find a writable path for SQLite database."""
    # 1. Explicit BOT_DB_PATH env var
    custom_path = os.environ.get("BOT_DB_PATH")
    if custom_path:
        p = Path(custom_path).expanduser()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
        except Exception as e:
            logger.warning(f"[DB] BOT_DB_PATH '{custom_path}' no es escribible: {e}")

    # 2. Render persistent disk if explicitly configured
    render_disk = os.environ.get("RENDER_DISK_PATH")
    if render_disk:
        try:
            p = Path(render_disk).expanduser()
            p.mkdir(parents=True, exist_ok=True)
            test_file = p / ".perm_check"
            test_file.touch()
            test_file.unlink()
            return p / "miami_vice.sqlite3"
        except Exception as e:
            logger.warning(f"[DB] RENDER_DISK_PATH '{render_disk}' no es accesible: {e}")

    # 3. Project root directory
    try:
        _ROOT.mkdir(parents=True, exist_ok=True)
        test_file = _ROOT / ".perm_check"
        test_file.touch()
        test_file.unlink()
        return _ROOT / "miami_vice.sqlite3"
    except Exception as e:
        logger.warning(f"[DB] Directorio raíz no es escribible: {e}")

    # 4. Universal /tmp fallback
    tmp_path = Path("/tmp/miami_vice.sqlite3")
    tmp_path.parent.mkdir(parents=True, exist_ok=True)
    return tmp_path

DB_PATH = _get_usable_sqlite_path()
DATABASE_URL = os.environ.get("SUPABASE_DB_URL") or os.environ.get("DATABASE_URL")
_IS_RENDER = bool(os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID"))

# En Render, FUERZA el uso de PostgreSQL si está disponible
_requested_backend = os.environ.get("DB_BACKEND", "").strip().lower()
if _IS_RENDER and DATABASE_URL and not _requested_backend:
    DB_BACKEND = "supabase"
else:
    DB_BACKEND = _requested_backend or ("supabase" if DATABASE_URL else "sqlite")

USE_POSTGRES = DB_BACKEND in {"supabase", "postgres", "postgresql"}
SLOW_QUERY_MS = 500

try:
    DB_OPERATION_TIMEOUT_SECONDS = max(1.0, float(os.environ.get("DB_OPERATION_TIMEOUT_SECONDS", "8")))
except ValueError:
    DB_OPERATION_TIMEOUT_SECONDS = 8.0
DB_STATEMENT_TIMEOUT_MS = int(DB_OPERATION_TIMEOUT_SECONDS * 1000)

logger.info(f"[DB] Backend seleccionado: {DB_BACKEND} | USE_POSTGRES: {USE_POSTGRES} | DATABASE_URL: {'✅' if DATABASE_URL else '❌'}")


def _prepare_query_and_params(query: str, params=None, is_sqlite: bool = True):
    """
    Translates Postgres-style numbered parameters ($1, $2, $1, etc.) into driver-compatible format.
    Handles duplicate placeholders safely by duplicating bindings in positional order.
    """
    if not params:
        raw = _DOLLAR_RE.sub("?" if is_sqlite else "%s", query)
        if is_sqlite:
            raw = raw.replace("NOW()", "CURRENT_TIMESTAMP").replace("GREATEST(", "MAX(").replace("ILIKE", "LIKE")
        return raw, ()

    matches = _DOLLAR_RE.findall(query)
    if not matches:
        raw = query
        if is_sqlite:
            raw = raw.replace("NOW()", "CURRENT_TIMESTAMP").replace("GREATEST(", "MAX(").replace("ILIKE", "LIKE")
        return raw, params

    p_seq = list(params) if isinstance(params, (list, tuple)) else [params]
    new_params = []
    for m in matches:
        idx = int(m) - 1
        if 0 <= idx < len(p_seq):
            new_params.append(p_seq[idx])
        else:
            raise IndexError(f"Query placeholder ${m} out of range for params of length {len(p_seq)}")

    raw = _DOLLAR_RE.sub("?" if is_sqlite else "%s", query)
    if is_sqlite:
        raw = raw.replace("NOW()", "CURRENT_TIMESTAMP").replace("GREATEST(", "MAX(").replace("ILIKE", "LIKE")
    return raw, tuple(new_params)


def _to_sqlite(query: str) -> str:
    return (
        _DOLLAR_RE.sub("?", query)
        .replace("NOW()", "CURRENT_TIMESTAMP")
        .replace("GREATEST(", "MAX(")
        .replace("ILIKE", "LIKE")
    )


def _to_postgres(query: str) -> str:
    return _DOLLAR_RE.sub("%s", query)


def _mask_url(url: str | None) -> str:
    if not url:
        return "no configurada"
    return re.sub(r"(://[^:]+:)[^@]+@", r"\1***@", url)


def connection_label() -> str:
    if USE_POSTGRES:
        return f"Supabase Postgres — {_mask_url(DATABASE_URL)}"
    return f"SQLite local — {DB_PATH}"


def _ensure_schema_migrations(conn):
    """Adds missing columns like username, display_name if they do not exist yet."""
    try:
        if USE_POSTGRES:
            with conn.cursor() as cursor:
                cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT")
                cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name TEXT")
                cursor.execute("ALTER TABLE department_members ADD COLUMN IF NOT EXISTS username TEXT")
                cursor.execute("ALTER TABLE company_members ADD COLUMN IF NOT EXISTS username TEXT")
            conn.commit()
        else:
            cursor = conn.execute("PRAGMA table_info(users)")
            existing_cols = {row[1] for row in cursor.fetchall()}
            if "username" not in existing_cols:
                conn.execute("ALTER TABLE users ADD COLUMN username TEXT")
            if "display_name" not in existing_cols:
                conn.execute("ALTER TABLE users ADD COLUMN display_name TEXT")
            
            # department_members check
            cursor_dm = conn.execute("PRAGMA table_info(department_members)")
            existing_dm = {row[1] for row in cursor_dm.fetchall()}
            if "username" not in existing_dm and len(existing_dm) > 0:
                conn.execute("ALTER TABLE department_members ADD COLUMN username TEXT")
                
            # company_members check
            cursor_cm = conn.execute("PRAGMA table_info(company_members)")
            existing_cm = {row[1] for row in cursor_cm.fetchall()}
            if "username" not in existing_cm and len(existing_cm) > 0:
                conn.execute("ALTER TABLE company_members ADD COLUMN username TEXT")
            conn.commit()
    except Exception as e:
        logger.debug(f"[DB] Migration check notice: {e}")


def _connect_sqlite() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        DB_PATH, 
        timeout=DB_OPERATION_TIMEOUT_SECONDS, 
        check_same_thread=False, 
        detect_types=sqlite3.PARSE_DECLTYPES,
        isolation_level=None # autocommit mode with explicit transaction control
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute(f"PRAGMA busy_timeout = {DB_STATEMENT_TIMEOUT_MS}")
    _ensure_schema_migrations(conn)
    return conn


def _connect_postgres():
    if psycopg is None:
        raise RuntimeError("Falta psycopg[binary]. Instala las dependencias del proyecto.")
    if not DATABASE_URL:
        raise RuntimeError("SUPABASE_DB_URL no está configurada.")
    conn = psycopg.connect(
        DATABASE_URL,
        connect_timeout=10,
        options=f"-c statement_timeout={DB_STATEMENT_TIMEOUT_MS} -c lock_timeout={min(DB_STATEMENT_TIMEOUT_MS, 3000)}",
        row_factory=dict_row,
    )
    _ensure_schema_migrations(conn)
    return conn


def _connect():
    global USE_POSTGRES, DB_BACKEND
    if USE_POSTGRES:
        try:
            return _connect_postgres()
        except Exception as pg_err:
            logger.warning(f"[DB] Conexión a PostgreSQL fallida ({pg_err}). Usando fallback a SQLite...")
            USE_POSTGRES = False
            DB_BACKEND = "sqlite"
            return _connect_sqlite()
    return _connect_sqlite()


def is_postgres() -> bool:
    return USE_POSTGRES


def get_conn():
    return _connect()


def _fetch_result(cursor, fetch):
    if fetch == "one":
        row = cursor.fetchone()
        return dict(row) if row else None
    if fetch == "all":
        return [dict(row) for row in cursor.fetchall()]
    if fetch == "count":
        return cursor.rowcount
    return None


def execute(query, params=None, fetch=None):
    conn = _connect()
    raw, safe_params = _prepare_query_and_params(query, params, is_sqlite=not USE_POSTGRES)
    started = time.monotonic()
    try:
        if USE_POSTGRES:
            with conn.cursor() as cursor:
                cursor.execute(raw, safe_params or ())
                result = _fetch_result(cursor, fetch)
            conn.commit()
        else:
            cursor = conn.execute(raw, safe_params or ())
            result = _fetch_result(cursor, fetch)
        elapsed_ms = (time.monotonic() - started) * 1000
        if elapsed_ms > SLOW_QUERY_MS:
            logger.warning("[DB][SLOW %.0fms] %s", elapsed_ms, raw[:120])
        return result
    except Exception as error:
        if USE_POSTGRES:
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
        if USE_POSTGRES:
            with conn.cursor() as cursor:
                for query, params in queries:
                    raw, safe_params = _prepare_query_and_params(query, params, is_sqlite=False)
                    cursor.execute(raw, safe_params or ())
            conn.commit()
        else:
            for query, params in queries:
                raw, safe_params = _prepare_query_and_params(query, params, is_sqlite=True)
                conn.execute(raw, safe_params or ())
        elapsed_ms = (time.monotonic() - started) * 1000
        if elapsed_ms > SLOW_QUERY_MS:
            logger.warning("[DB][SLOW BATCH %.0fms] %s queries", elapsed_ms, len(queries))
    except Exception as error:
        if USE_POSTGRES:
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
        if USE_POSTGRES:
            with conn.cursor() as cursor:
                for statement in schema.split(";"):
                    if statement.strip():
                        cursor.execute(statement)
            conn.commit()
        else:
            with conn:
                conn.executescript(_to_sqlite(schema))
    except Exception:
        if USE_POSTGRES:
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
        raise TimeoutError("La base de datos tardó demasiado en responder") from error


async def aexecute(query, params=None, fetch=None):
    return await _run_db_operation(execute, query, params, fetch)


async def aexecute_many(queries):
    return await _run_db_operation(execute_many, queries)


def check_connection() -> dict:
    global USE_POSTGRES, DB_BACKEND
    result = {
        "ok": False,
        "masked_url": _mask_url(DATABASE_URL) if USE_POSTGRES else f"sqlite:///{DB_PATH}",
        "error": None,
        "ssl": "Supabase/Postgres" if USE_POSTGRES else "no aplica",
        "backend": DB_BACKEND,
    }
    if USE_POSTGRES:
        try:
            conn = _connect_postgres()
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1 AS ok")
                    result["ok"] = bool(cursor.fetchone())
            finally:
                conn.close()
            return result
        except Exception as pg_err:
            logger.warning(f"[DB] Falló conexión a Postgres ({pg_err}). Activando fallback a SQLite local...")
            USE_POSTGRES = False
            DB_BACKEND = "sqlite"

    try:
        conn = _connect_sqlite()
        try:
            result["ok"] = bool(conn.execute("SELECT 1 AS ok").fetchone())
            result["masked_url"] = f"sqlite:///{DB_PATH}"
            result["backend"] = "sqlite"
            result["ssl"] = "no aplica"
            result["error"] = None
        finally:
            conn.close()
    except Exception as error:
        result["error"] = f"sqlite: {error}"
    return result
