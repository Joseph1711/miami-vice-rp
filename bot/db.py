"""Database adapter for the Miami Vice bot.

SQLite remains available for local development. Set SUPABASE_DB_URL (or
DATABASE_URL) and DB_BACKEND=supabase to use Supabase Postgres in production.
"""
import asyncio
import logging
import os
import re
import sqlite3
import threading
import time
from collections import deque
from contextlib import contextmanager
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


def _env_float(name: str, default: float, minimum: float) -> float:
    try:
        return max(minimum, float(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int, minimum: int) -> int:
    return int(_env_float(name, default, minimum))


# Presupuesto total de una operacion (conexion + query). Antes 8s: en un host
# remoto eso se agotaba solo con el handshake TLS y las migraciones por query.
DB_OPERATION_TIMEOUT_SECONDS = _env_float("DB_OPERATION_TIMEOUT_SECONDS", 15.0, 2.0)
DB_STATEMENT_TIMEOUT_MS = int(DB_OPERATION_TIMEOUT_SECONDS * 1000)
# Un lock que no se libera falla rapido y se reintenta, en vez de quemarse el
# presupuesto completo esperando.
DB_LOCK_TIMEOUT_MS = _env_int("DB_LOCK_TIMEOUT_MS", 4000, 500)
DB_CONNECT_TIMEOUT_SECONDS = _env_int("DB_CONNECT_TIMEOUT_SECONDS", 10, 1)
DB_MIGRATION_TIMEOUT_MS = _env_int("DB_MIGRATION_TIMEOUT_MS", 60000, 5000)
DB_POOL_MAX_SIZE = _env_int("DB_POOL_MAX_SIZE", 8, 1)
DB_POOL_WAIT_SECONDS = _env_float("DB_POOL_WAIT_SECONDS", 10.0, 1.0)
DB_RETRY_ATTEMPTS = _env_int("DB_RETRY_ATTEMPTS", 3, 1)
DB_RETRY_BACKOFF_SECONDS = _env_float("DB_RETRY_BACKOFF_SECONDS", 0.4, 0.0)
DB_RETRY_BUDGET_RATIO = _env_float("DB_RETRY_BUDGET_RATIO", 0.6, 0.05)
# Si la base esta caida, reintentar las migraciones en cada consulta costaria un
# connect_timeout por comando y volveria a reportar un falso timeout.
DB_MIGRATION_RETRY_COOLDOWN = _env_float("DB_MIGRATION_RETRY_COOLDOWN", 60.0, 0.0)
# El panel React consulta /api/bot/status cada 2s: cachear evita castigar la DB.
DB_CHECK_CACHE_SECONDS = _env_float("DB_CHECK_CACHE_SECONDS", 10.0, 0.0)

_MIGRATIONS_DONE = False
_MIGRATIONS_LOCK = threading.Lock()
_MIGRATIONS_ATTEMPT = {"last": 0.0}
_CHECK_CACHE: dict = {}
_POOL: "_ConnectionPool | None" = None
_POOL_LOCK = threading.Lock()

logger.info(f"[DB] Backend seleccionado: {DB_BACKEND} | USE_POSTGRES: {USE_POSTGRES} | DATABASE_URL: {'✅' if DATABASE_URL else '❌'}")


def _prepare_query_and_params(query: str, params=None, is_sqlite: bool = True):
    """
    Translates Postgres-style numbered parameters ($1, $2, $1, etc.) into driver-compatible format.
    Handles duplicate placeholders safely by duplicating bindings in positional order.
    Guarantees that generated placeholder count matches the parameter tuple length exactly.
    """
    if not params:
        raw = _DOLLAR_RE.sub("?" if is_sqlite else "%s", query)
        if is_sqlite:
            raw = raw.replace("NOW()", "CURRENT_TIMESTAMP").replace("GREATEST(", "MAX(").replace("ILIKE", "LIKE")
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

        raw = _DOLLAR_RE.sub("?" if is_sqlite else "%s", query)
        if is_sqlite:
            raw = raw.replace("NOW()", "CURRENT_TIMESTAMP").replace("GREATEST(", "MAX(").replace("ILIKE", "LIKE")
        return raw, tuple(new_params)

    raw = query
    if is_sqlite:
        raw = raw.replace("NOW()", "CURRENT_TIMESTAMP").replace("GREATEST(", "MAX(").replace("ILIKE", "LIKE")
    return raw, tuple(p_seq)


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


def _pg_migration_statements() -> list:
    """Migraciones idempotentes de Postgres (se ejecutan una vez por proceso)."""
    return [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS roblox_username TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS roblox_id TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS roblox_profile_url TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS dni_number TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_salary TIMESTAMP",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_note TEXT DEFAULT 'Made By Joshi'",
        "ALTER TABLE department_members ADD COLUMN IF NOT EXISTS username TEXT",
        "ALTER TABLE company_members ADD COLUMN IF NOT EXISTS username TEXT",
        "ALTER TABLE properties ADD COLUMN IF NOT EXISTS company_id TEXT",
        "CREATE INDEX IF NOT EXISTS idx_properties_company ON properties(company_id, status)",
        "ALTER TABLE dni_records ADD COLUMN IF NOT EXISTS occupation TEXT DEFAULT 'Ciudadano'",
        "ALTER TABLE dni_records ADD COLUMN IF NOT EXISTS age INTEGER DEFAULT 18",
        "ALTER TABLE weapon_registries ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()",
        "ALTER TABLE weapon_registries ADD COLUMN IF NOT EXISTS weapon_type TEXT DEFAULT 'Arma de Fuego'",
        "ALTER TABLE auctions ADD COLUMN IF NOT EXISTS quantity INTEGER DEFAULT 1",
        "ALTER TABLE auctions ADD COLUMN IF NOT EXISTS starting_price NUMERIC DEFAULT 0",
        """CREATE TABLE IF NOT EXISTS criminal_records (
            id TEXT PRIMARY KEY,
            guild_id TEXT NOT NULL,
            discord_id TEXT NOT NULL,
            crime_type TEXT NOT NULL,
            description TEXT NOT NULL,
            fine_amount NUMERIC DEFAULT 0,
            jail_time_minutes INTEGER DEFAULT 0,
            officer_id TEXT NOT NULL,
            officer_name TEXT,
            status TEXT DEFAULT 'arrested',
            paid BOOLEAN DEFAULT FALSE,
            paid_at TIMESTAMP,
            items_found TEXT,
            items_seized TEXT,
            rights_read BOOLEAN DEFAULT TRUE,
            physical_state TEXT DEFAULT 'Ileso',
            evidence_url TEXT,
            roblox_username TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS guild_configs (
            id TEXT PRIMARY KEY,
            guild_id TEXT UNIQUE NOT NULL,
            police_role_ids TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )""",
        "ALTER TABLE criminal_records ADD COLUMN IF NOT EXISTS items_found TEXT",
        "ALTER TABLE criminal_records ADD COLUMN IF NOT EXISTS items_seized TEXT",
        "ALTER TABLE criminal_records ADD COLUMN IF NOT EXISTS rights_read BOOLEAN DEFAULT TRUE",
        "ALTER TABLE criminal_records ADD COLUMN IF NOT EXISTS physical_state TEXT DEFAULT 'Ileso'",
        "ALTER TABLE criminal_records ADD COLUMN IF NOT EXISTS evidence_url TEXT",
        "ALTER TABLE criminal_records ADD COLUMN IF NOT EXISTS roblox_username TEXT",
        """CREATE TABLE IF NOT EXISTS update_config (
            id TEXT PRIMARY KEY,
            guild_id TEXT UNIQUE NOT NULL,
            channel_id TEXT,
            auto_announce BOOLEAN DEFAULT TRUE,
            github_repo TEXT DEFAULT 'Joseph1711/miami-vice-rp',
            last_commit_sha TEXT,
            draft_version TEXT,
            draft_changes TEXT,
            draft_description TEXT,
            mention_role_id TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS bot_updates_history (
            id TEXT PRIMARY KEY,
            guild_id TEXT NOT NULL,
            version TEXT NOT NULL,
            title TEXT NOT NULL,
            changes TEXT NOT NULL,
            description TEXT,
            commit_sha TEXT,
            source TEXT DEFAULT 'manual',
            published_by TEXT,
            channel_id TEXT,
            message_id TEXT,
            published_at TIMESTAMP DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS server_status (
            guild_id TEXT PRIMARY KEY,
            status TEXT DEFAULT 'CLOSED',
            server_code TEXT DEFAULT 'MVERP',
            updated_by TEXT,
            updated_at TIMESTAMP DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS server_votes (
            id TEXT PRIMARY KEY,
            guild_id TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            creator_id TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            duration_minutes INTEGER DEFAULT 5,
            ends_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS server_vote_entries (
            vote_id TEXT NOT NULL REFERENCES server_votes(id) ON DELETE CASCADE,
            discord_id TEXT NOT NULL,
            choice TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (vote_id, discord_id)
        )""",
        """CREATE TABLE IF NOT EXISTS server_vote_removals (
            id TEXT PRIMARY KEY,
            vote_id TEXT NOT NULL,
            discord_id TEXT NOT NULL,
            removed_at TIMESTAMP DEFAULT NOW()
        )""",
        # --- EMPLEOS PUBLICOS (tabla `jobs` heredada + asignaciones) ---
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS role_id TEXT",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS description TEXT DEFAULT ''",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS salary NUMERIC DEFAULT 0",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS requirements TEXT DEFAULT ''",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS is_single BOOLEAN DEFAULT TRUE",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS max_workers INTEGER DEFAULT 0",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0",
        "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'General'",
        """CREATE TABLE IF NOT EXISTS user_public_jobs (
            id TEXT PRIMARY KEY,
            guild_id TEXT NOT NULL,
            discord_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            job_name TEXT NOT NULL,
            salary NUMERIC DEFAULT 0,
            role_id TEXT,
            status TEXT DEFAULT 'active',
            hired_at TIMESTAMP DEFAULT NOW(),
            last_paid_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(discord_id, guild_id, job_id)
        )""",
        "ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS single_public_job BOOLEAN DEFAULT TRUE",
        "ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS public_jobs_channel_id TEXT",
        "ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS company_creation_cost NUMERIC DEFAULT 5000",
        # --- EMPRESAS PRIVADAS: columnas nuevas sobre `companies` ---
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'General'",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS location TEXT DEFAULT ''",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS emoji TEXT DEFAULT '🏢'",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active'",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS status_note TEXT DEFAULT ''",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMP",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS sale_price NUMERIC",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS public_listing BOOLEAN DEFAULT FALSE",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS payroll_mode TEXT DEFAULT 'automatic'",
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS allow_multiple_jobs BOOLEAN DEFAULT TRUE",
        # `company_members` conserva las columnas heredadas (role/salary) que leen
        # /sueldo y el cron; aqui se anaden las del nuevo sistema.
        "ALTER TABLE company_members ADD COLUMN IF NOT EXISTS position_id TEXT",
        "ALTER TABLE company_members ADD COLUMN IF NOT EXISTS member_status TEXT DEFAULT 'active'",
        "ALTER TABLE company_members ADD COLUMN IF NOT EXISTS permissions TEXT DEFAULT ''",
        "ALTER TABLE company_members ADD COLUMN IF NOT EXISTS discord_role_id TEXT",
        "ALTER TABLE company_members ADD COLUMN IF NOT EXISTS pending_salary NUMERIC DEFAULT 0",
        "ALTER TABLE company_members ADD COLUMN IF NOT EXISTS last_paid_at TIMESTAMP",
        "ALTER TABLE company_members ADD COLUMN IF NOT EXISTS is_manager BOOLEAN DEFAULT FALSE",
        "ALTER TABLE company_members ADD COLUMN IF NOT EXISTS hired_by TEXT",
        "ALTER TABLE company_members ADD COLUMN IF NOT EXISTS notes TEXT DEFAULT ''",
        "ALTER TABLE company_members ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP",
        """CREATE TABLE IF NOT EXISTS company_positions (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            guild_id TEXT NOT NULL,
            name TEXT NOT NULL,
            salary NUMERIC DEFAULT 0,
            description TEXT DEFAULT '',
            discord_role_id TEXT,
            permissions TEXT DEFAULT '',
            max_members INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS company_catalog (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            guild_id TEXT NOT NULL,
            kind TEXT DEFAULT 'product',
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            price NUMERIC NOT NULL DEFAULT 0,
            emoji TEXT DEFAULT '🍽️',
            stock INTEGER DEFAULT -1,
            role_id TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            sold_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(company_id, kind, name)
        )""",
        "ALTER TABLE company_catalog ADD COLUMN IF NOT EXISTS role_id TEXT",
        """CREATE TABLE IF NOT EXISTS company_transactions (
            id TEXT PRIMARY KEY,
            guild_id TEXT NOT NULL,
            company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            amount NUMERIC NOT NULL,
            balance_after NUMERIC DEFAULT 0,
            description TEXT DEFAULT '',
            actor_id TEXT,
            counterparty_id TEXT,
            ref_id TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS company_shares (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            guild_id TEXT NOT NULL,
            total_shares INTEGER DEFAULT 0,
            share_price NUMERIC DEFAULT 0,
            control_pct NUMERIC DEFAULT 51,
            is_enabled BOOLEAN DEFAULT FALSE,
            buyback_price NUMERIC DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS company_shareholders (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            guild_id TEXT NOT NULL,
            discord_id TEXT NOT NULL,
            shares INTEGER DEFAULT 0,
            total_invested NUMERIC DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(company_id, discord_id)
        )""",
        """CREATE TABLE IF NOT EXISTS company_share_trades (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            guild_id TEXT NOT NULL,
            discord_id TEXT NOT NULL,
            trade_type TEXT DEFAULT 'buy',
            shares INTEGER NOT NULL,
            price NUMERIC NOT NULL,
            total NUMERIC NOT NULL,
            counterparty_id TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS company_sales (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            guild_id TEXT NOT NULL,
            seller_id TEXT NOT NULL,
            buyer_id TEXT,
            price NUMERIC NOT NULL DEFAULT 0,
            status TEXT DEFAULT 'listed',
            note TEXT DEFAULT '',
            listed_at TIMESTAMP DEFAULT NOW(),
            sold_at TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS company_dividends (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            guild_id TEXT NOT NULL,
            total_amount NUMERIC NOT NULL DEFAULT 0,
            paid_amount NUMERIC DEFAULT 0,
            recipient_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            note TEXT DEFAULT '',
            created_by TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            paid_at TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS company_dividend_payments (
            id TEXT PRIMARY KEY,
            dividend_id TEXT NOT NULL REFERENCES company_dividends(id) ON DELETE CASCADE,
            company_id TEXT NOT NULL,
            guild_id TEXT NOT NULL,
            discord_id TEXT NOT NULL,
            shares INTEGER DEFAULT 0,
            amount NUMERIC DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS company_payroll_runs (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            guild_id TEXT NOT NULL,
            total NUMERIC DEFAULT 0,
            employee_count INTEGER DEFAULT 0,
            mode TEXT DEFAULT 'full',
            status TEXT DEFAULT 'completed',
            detail TEXT DEFAULT '',
            created_by TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        # Indices del modulo empresarial: el historial y el catalogo se leen mucho.
        "CREATE INDEX IF NOT EXISTS idx_company_tx_company ON company_transactions(company_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_company_catalog_company ON company_catalog(company_id, kind)",
        "CREATE INDEX IF NOT EXISTS idx_public_jobs_user ON user_public_jobs(discord_id, guild_id)",
        "CREATE INDEX IF NOT EXISTS idx_company_members_user ON company_members(discord_id, guild_id)",
    ]



def _sqlite_add_missing_columns(conn, table: str, columns) -> None:
    """ALTER TABLE ... ADD COLUMN solo para las columnas que falten.

    Si la tabla no existe todavia (base recien creada que aun no paso por
    `scripts.init_db`), no hay nada que hacer: el CREATE TABLE ya la define
    completa.
    """
    try:
        cursor = conn.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cursor.fetchall()}
    except Exception:
        return
    if not existing:
        return
    for column, column_type in columns:
        if column in existing:
            continue
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
        except Exception as column_error:
            logger.debug("[DB] Columna %s.%s omitida: %s", table, column, column_error)


def _sqlite_business_ddl() -> list:
    """DDL SQLite del modulo de empleos publicos y empresas privadas."""
    return [
        """CREATE TABLE IF NOT EXISTS user_public_jobs (
            id TEXT PRIMARY KEY,
            guild_id TEXT NOT NULL,
            discord_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            job_name TEXT NOT NULL,
            salary NUMERIC DEFAULT 0,
            role_id TEXT,
            status TEXT DEFAULT 'active',
            hired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_paid_at TIMESTAMP,
            updated_at TIMESTAMP,
            UNIQUE(discord_id, guild_id, job_id)
        )""",
        """CREATE TABLE IF NOT EXISTS company_positions (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            guild_id TEXT NOT NULL,
            name TEXT NOT NULL,
            salary NUMERIC DEFAULT 0,
            description TEXT DEFAULT '',
            discord_role_id TEXT,
            permissions TEXT DEFAULT '',
            max_members INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS company_catalog (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            guild_id TEXT NOT NULL,
            kind TEXT DEFAULT 'product',
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            price NUMERIC NOT NULL DEFAULT 0,
            emoji TEXT DEFAULT '🍽️',
            stock INTEGER DEFAULT -1,
            role_id TEXT,
            is_active BOOLEAN DEFAULT 1,
            sold_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS company_transactions (
            id TEXT PRIMARY KEY,
            guild_id TEXT NOT NULL,
            company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            amount NUMERIC NOT NULL,
            balance_after NUMERIC DEFAULT 0,
            description TEXT DEFAULT '',
            actor_id TEXT,
            counterparty_id TEXT,
            ref_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS company_shares (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            guild_id TEXT NOT NULL,
            total_shares INTEGER DEFAULT 0,
            share_price NUMERIC DEFAULT 0,
            control_pct NUMERIC DEFAULT 51,
            is_enabled BOOLEAN DEFAULT 0,
            buyback_price NUMERIC DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS company_shareholders (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            guild_id TEXT NOT NULL,
            discord_id TEXT NOT NULL,
            shares INTEGER DEFAULT 0,
            total_invested NUMERIC DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP,
            UNIQUE(company_id, discord_id)
        )""",
        """CREATE TABLE IF NOT EXISTS company_share_trades (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            guild_id TEXT NOT NULL,
            discord_id TEXT NOT NULL,
            trade_type TEXT DEFAULT 'buy',
            shares INTEGER NOT NULL,
            price NUMERIC NOT NULL,
            total NUMERIC NOT NULL,
            counterparty_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS company_sales (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            guild_id TEXT NOT NULL,
            seller_id TEXT NOT NULL,
            buyer_id TEXT,
            price NUMERIC NOT NULL DEFAULT 0,
            status TEXT DEFAULT 'listed',
            note TEXT DEFAULT '',
            listed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sold_at TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS company_dividends (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            guild_id TEXT NOT NULL,
            total_amount NUMERIC NOT NULL DEFAULT 0,
            paid_amount NUMERIC DEFAULT 0,
            recipient_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            note TEXT DEFAULT '',
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            paid_at TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS company_dividend_payments (
            id TEXT PRIMARY KEY,
            dividend_id TEXT NOT NULL REFERENCES company_dividends(id) ON DELETE CASCADE,
            company_id TEXT NOT NULL,
            guild_id TEXT NOT NULL,
            discord_id TEXT NOT NULL,
            shares INTEGER DEFAULT 0,
            amount NUMERIC DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS company_payroll_runs (
            id TEXT PRIMARY KEY,
            company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            guild_id TEXT NOT NULL,
            total NUMERIC DEFAULT 0,
            employee_count INTEGER DEFAULT 0,
            mode TEXT DEFAULT 'full',
            status TEXT DEFAULT 'completed',
            detail TEXT DEFAULT '',
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_company_tx_company ON company_transactions(company_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_company_catalog_company ON company_catalog(company_id, kind)",
        "CREATE INDEX IF NOT EXISTS idx_public_jobs_user ON user_public_jobs(discord_id, guild_id)",
        "CREATE INDEX IF NOT EXISTS idx_company_members_user ON company_members(discord_id, guild_id)",
    ]


def _ensure_schema_migrations(conn):
    """Adds missing columns like username, display_name, dni_number, etc. if they do not exist yet.

    Cada sentencia se intenta por separado: un ALTER sobre una tabla que aun no
    existe no debe abortar el resto de la migracion.
    """
    try:
        if USE_POSTGRES:
            failed = []
            for statement in _pg_migration_statements():
                try:
                    with conn.cursor() as cursor:
                        cursor.execute(statement)
                except Exception as stmt_error:
                    failed.append((statement.split("\n")[0][:60], str(stmt_error).strip()))
                    if not conn.autocommit:
                        try:
                            conn.rollback()
                        except Exception:
                            pass
            if not conn.autocommit:
                conn.commit()
            if failed:
                logger.warning("[DB] %d migracion(es) omitida(s): %s", len(failed), failed[:3])
        else:
            cursor = conn.execute("PRAGMA table_info(users)")
            existing_cols = {row[1] for row in cursor.fetchall()}
            for col, col_type in [
                ("username", "TEXT"),
                ("display_name", "TEXT"),
                ("roblox_username", "TEXT"),
                ("roblox_id", "TEXT"),
                ("roblox_profile_url", "TEXT"),
                ("dni_number", "TEXT")
            ]:
                if col not in existing_cols and len(existing_cols) > 0:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
            
            # dni_records check
            cursor_dni = conn.execute("PRAGMA table_info(dni_records)")
            existing_dni = {row[1] for row in cursor_dni.fetchall()}
            if len(existing_dni) > 0:
                if "occupation" not in existing_dni:
                    conn.execute("ALTER TABLE dni_records ADD COLUMN occupation TEXT DEFAULT 'Ciudadano'")
                if "age" not in existing_dni:
                    conn.execute("ALTER TABLE dni_records ADD COLUMN age INTEGER DEFAULT 18")

            # weapon_registries check
            cursor_wpn = conn.execute("PRAGMA table_info(weapon_registries)")
            existing_wpn = {row[1] for row in cursor_wpn.fetchall()}
            if len(existing_wpn) > 0:
                if "created_at" not in existing_wpn:
                    conn.execute("ALTER TABLE weapon_registries ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                if "weapon_type" not in existing_wpn:
                    conn.execute("ALTER TABLE weapon_registries ADD COLUMN weapon_type TEXT DEFAULT 'Arma de Fuego'")

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

            # properties check: vinculo con la empresa duena del local
            _sqlite_add_missing_columns(
                conn,
                "properties",
                [
                    ("company_id", "TEXT"),
                ],
            )
            try:
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_properties_company "
                    "ON properties(company_id, status)"
                )
            except sqlite3.Error as index_error:
                logger.debug("[DB] Indice de properties omitido: %s", index_error)

            _sqlite_add_missing_columns(
                conn,
                "jobs",
                [
                    ("role_id", "TEXT"),
                    ("description", "TEXT DEFAULT ''"),
                    ("salary", "NUMERIC DEFAULT 0"),
                    ("requirements", "TEXT DEFAULT ''"),
                    ("is_single", "BOOLEAN DEFAULT 1"),
                    ("max_workers", "INTEGER DEFAULT 0"),
                    ("sort_order", "INTEGER DEFAULT 0"),
                    ("category", "TEXT DEFAULT 'General'"),
                ],
            )
            _sqlite_add_missing_columns(
                conn,
                "guild_config",
                [
                    ("single_public_job", "BOOLEAN DEFAULT 1"),
                    ("public_jobs_channel_id", "TEXT"),
                    ("company_creation_cost", "NUMERIC DEFAULT 5000"),
                ],
            )
            _sqlite_add_missing_columns(
                conn,
                "companies",
                [
                    ("category", "TEXT DEFAULT 'General'"),
                    ("location", "TEXT DEFAULT ''"),
                    ("emoji", "TEXT DEFAULT '🏢'"),
                    ("status", "TEXT DEFAULT 'active'"),
                    ("status_note", "TEXT DEFAULT ''"),
                    ("status_changed_at", "TIMESTAMP"),
                    ("sale_price", "NUMERIC"),
                    ("public_listing", "BOOLEAN DEFAULT 0"),
                    ("payroll_mode", "TEXT DEFAULT 'automatic'"),
                    ("allow_multiple_jobs", "BOOLEAN DEFAULT 1"),
                ],
            )
            _sqlite_add_missing_columns(
                conn,
                "company_members",
                [
                    ("position_id", "TEXT"),
                    ("member_status", "TEXT DEFAULT 'active'"),
                    ("permissions", "TEXT DEFAULT ''"),
                    ("discord_role_id", "TEXT"),
                    ("pending_salary", "NUMERIC DEFAULT 0"),
                    ("last_paid_at", "TIMESTAMP"),
                    ("is_manager", "BOOLEAN DEFAULT 0"),
                    ("hired_by", "TEXT"),
                    ("notes", "TEXT DEFAULT ''"),
                    ("updated_at", "TIMESTAMP"),
                ],
            )
            for ddl in _sqlite_business_ddl():
                conn.execute(ddl)

            # auctions check
            cursor_auc = conn.execute("PRAGMA table_info(auctions)")
            existing_auc = {row[1] for row in cursor_auc.fetchall()}
            if len(existing_auc) > 0:
                if "quantity" not in existing_auc:
                    conn.execute("ALTER TABLE auctions ADD COLUMN quantity INTEGER DEFAULT 1")
                if "starting_price" not in existing_auc:
                    conn.execute("ALTER TABLE auctions ADD COLUMN starting_price NUMERIC DEFAULT 0")

            # criminal_records check
            conn.execute("""
            CREATE TABLE IF NOT EXISTS criminal_records (
                id TEXT PRIMARY KEY,
                guild_id TEXT NOT NULL,
                discord_id TEXT NOT NULL,
                crime_type TEXT NOT NULL,
                description TEXT NOT NULL,
                fine_amount NUMERIC DEFAULT 0,
                jail_time_minutes INTEGER DEFAULT 0,
                officer_id TEXT NOT NULL,
                officer_name TEXT,
                status TEXT DEFAULT 'arrested',
                paid BOOLEAN DEFAULT 0,
                paid_at TIMESTAMP,
                items_found TEXT,
                items_seized TEXT,
                rights_read BOOLEAN DEFAULT 1,
                physical_state TEXT DEFAULT 'Ileso',
                evidence_url TEXT,
                roblox_username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS guild_configs (
                id TEXT PRIMARY KEY,
                guild_id TEXT UNIQUE NOT NULL,
                police_role_ids TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            cursor_cr = conn.execute("PRAGMA table_info(criminal_records)")
            existing_cr = {row[1] for row in cursor_cr.fetchall()}
            if len(existing_cr) > 0:
                for col_name, col_type, default_val in [
                    ("items_found", "TEXT", "''"),
                    ("items_seized", "TEXT", "''"),
                    ("rights_read", "BOOLEAN", "1"),
                    ("physical_state", "TEXT", "'Ileso'"),
                    ("evidence_url", "TEXT", "NULL"),
                    ("roblox_username", "TEXT", "NULL")
                ]:
                    if col_name not in existing_cr:
                        conn.execute(f"ALTER TABLE criminal_records ADD COLUMN {col_name} {col_type} DEFAULT {default_val}")

            # update_config table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS update_config (
                id TEXT PRIMARY KEY,
                guild_id TEXT UNIQUE NOT NULL,
                channel_id TEXT,
                auto_announce BOOLEAN DEFAULT 1,
                github_repo TEXT DEFAULT 'Joseph1711/miami-vice-rp',
                last_commit_sha TEXT,
                draft_version TEXT,
                draft_changes TEXT,
                draft_description TEXT,
                mention_role_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # bot_updates_history table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS bot_updates_history (
                id TEXT PRIMARY KEY,
                guild_id TEXT NOT NULL,
                version TEXT NOT NULL,
                title TEXT NOT NULL,
                changes TEXT NOT NULL,
                description TEXT,
                commit_sha TEXT,
                source TEXT DEFAULT 'manual',
                published_by TEXT,
                channel_id TEXT,
                message_id TEXT,
                published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

            # server_status, server_votes, server_vote_entries
            conn.execute("""
            CREATE TABLE IF NOT EXISTS server_status (
                guild_id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'CLOSED',
                server_code TEXT DEFAULT 'MVERP',
                updated_by TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS server_votes (
                id TEXT PRIMARY KEY,
                guild_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                creator_id TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                duration_minutes INTEGER DEFAULT 5,
                ends_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS server_vote_entries (
                vote_id TEXT NOT NULL REFERENCES server_votes(id) ON DELETE CASCADE,
                discord_id TEXT NOT NULL,
                choice TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (vote_id, discord_id)
            )
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS server_vote_removals (
                id TEXT PRIMARY KEY,
                vote_id TEXT NOT NULL REFERENCES server_votes(id) ON DELETE CASCADE,
                discord_id TEXT NOT NULL,
                removed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
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
    return conn


def _pg_ok_status():
    """Valor de 'conexion sana' segun la version de psycopg (ConnStatus/Status/PqStatus)."""
    pq_module = getattr(psycopg, "pq", None)
    for enum_name in ("ConnStatus", "Status", "PqStatus"):
        enum = getattr(pq_module, enum_name, None)
        if enum is not None and hasattr(enum, "OK"):
            return enum.OK
    return None


_PG_OK_STATUS = _pg_ok_status() if psycopg is not None else None


def _pg_is_alive(conn) -> bool:
    try:
        if conn.closed:
            return False
        if _PG_OK_STATUS is None:
            return True
        return conn.pgconn.status == _PG_OK_STATUS
    except Exception:
        return False


def _pg_connect_kwargs(statement_timeout_ms: int) -> dict:
    # prepare_threshold=None desactiva el cache de sentencias preparadas.
    # psycopg nombra esas sentencias `_pg3_0`, `_pg3_1`... con un contador que
    # vive en el cliente, y al reconectar el contador vuelve a cero. Si por
    # delante hay un pooler en modo transaction (Supabase/pgbouncer, que
    # reutiliza una misma sesion del servidor entre varios clientes), la
    # sentencia ya existe al lado del servidor y Postgres responde
    # `prepared statement "_pg3_0" already exists`. Sin cache no hay nombres que
    # colisionen. El coste es un viaje de red extra por sentencia repetida.
    return dict(
        connect_timeout=DB_CONNECT_TIMEOUT_SECONDS,
        prepare_threshold=None,
        options=(
            f"-c statement_timeout={statement_timeout_ms} "
            f"-c lock_timeout={DB_LOCK_TIMEOUT_MS} "
            "-c idle_in_transaction_session_timeout=0 "
            "-c application_name=miami-vice-bot"
        ),
        row_factory=dict_row,
    )


def _connect_postgres(statement_timeout_ms: int | None = None):
    """Conexion cruda, fuera del pool. El llamante es responsable de cerrarla."""
    if psycopg is None:
        raise RuntimeError("Falta psycopg[binary]. Instala las dependencias del proyecto.")
    if not DATABASE_URL:
        raise RuntimeError("SUPABASE_DB_URL no está configurada.")
    return psycopg.connect(
        DATABASE_URL,
        **_pg_connect_kwargs(statement_timeout_ms or DB_STATEMENT_TIMEOUT_MS),
    )


class _ConnectionPool:
    """Pool minimo de conexiones psycopg.

    Evita un handshake TLS completo por cada consulta. Cada conexion se toma en
    exclusiva (un hilo = una conexion) y vuelve al pool al terminar.
    """

    def __init__(self, max_size: int):
        self._max_size = max_size
        self._idle: deque = deque()
        self._lock = threading.Lock()
        self._slots = threading.Semaphore(max_size)
        self._total_created = 0

    def _new_connection(self):
        conn = _connect_postgres()
        with self._lock:
            self._total_created += 1
            if self._total_created == 1:
                logger.info("[DB] Pool de conexiones Postgres abierto (max=%d)", self._max_size)
        return conn

    @staticmethod
    def _close_quietly(conn) -> None:
        try:
            conn.close()
        except Exception:
            pass

    def acquire(self, timeout: float | None = None) -> "psycopg.Connection":
        wait = DB_POOL_WAIT_SECONDS if timeout is None else timeout
        if not self._slots.acquire(timeout=wait):
            raise TimeoutError(f"El pool de base de datos esta saturado (>{self._max_size} consultas)")
        try:
            while True:
                with self._lock:
                    conn = self._idle.popleft() if self._idle else None
                if conn is None:
                    return self._new_connection()
                if _pg_is_alive(conn):
                    return conn
                # El host remoto cerro la sesion o la conexion murio: descartar.
                self._close_quietly(conn)
                with self._lock:
                    self._total_created = max(0, self._total_created - 1)
        except BaseException:
            self._slots.release()
            raise

    def release(self, conn, discard: bool = False) -> None:
        try:
            if discard or not _pg_is_alive(conn):
                self._close_quietly(conn)
                with self._lock:
                    self._total_created = max(0, self._total_created - 1)
                return
            with self._lock:
                self._idle.append(conn)
        finally:
            self._slots.release()

    def close(self) -> None:
        with self._lock:
            idle, self._idle = list(self._idle), deque()
        for conn in idle:
            self._close_quietly(conn)


@contextmanager
def _pg_connection():
    """Conexion del pool para el camino caliente. Vive una sola consulta."""
    pool = _get_pool()
    conn = pool.acquire()
    discard = False
    try:
        yield conn
    except BaseException:
        discard = True
        raise
    finally:
        pool.release(conn, discard=discard)


def _get_pool() -> "_ConnectionPool":
    global _POOL
    if _POOL is not None:
        return _POOL
    with _POOL_LOCK:
        if _POOL is None:
            if psycopg is None:
                raise RuntimeError("Falta psycopg[binary]. Instala las dependencias del proyecto.")
            if not DATABASE_URL:
                raise RuntimeError("SUPABASE_DB_URL no está configurada.")
            _POOL = _ConnectionPool(DB_POOL_MAX_SIZE)
    return _POOL


def _connect():
    """Conexion nueva y limpia, fuera del pool. El llamante la cierra."""
    if USE_POSTGRES:
        try:
            return _connect_postgres()
        except Exception as pg_err:
            # No se degrada a SQLite en caliente: el bot terminaria escribiendo
            # datos fiscales en un archivo local distinto de la base real.
            logger.error(f"[DB] Conexión a PostgreSQL fallida ({pg_err})")
            raise
    return _connect_sqlite()


def is_postgres() -> bool:
    global USE_POSTGRES, DB_BACKEND
    if USE_POSTGRES:
        if psycopg is None or not DATABASE_URL:
            USE_POSTGRES = False
            DB_BACKEND = "sqlite"
            return False
    return USE_POSTGRES


def get_conn():
    return _connect()


def run_migrations(force: bool = False) -> bool:
    """Aplica las migraciones idempotentes UNA sola vez por proceso.

    Antes se ejecutaban dentro de cada conexion: ~30 DDL por comando, con lock
    ACCESS EXCLUSIVE sobre users/dni_records, que bloqueaban al bot hasta
    agotar el timeout. Ahora corren al arrancar y nunca mas.
    """
    global _MIGRATIONS_DONE
    if _MIGRATIONS_DONE and not force:
        return False
    _MIGRATIONS_ATTEMPT["last"] = time.monotonic()
    with _MIGRATIONS_LOCK:
        if _MIGRATIONS_DONE and not force:
            return False
        started = time.monotonic()
        if USE_POSTGRES and DATABASE_URL and psycopg is not None:
            conn = _connect_postgres(DB_MIGRATION_TIMEOUT_MS)
            # Cada sentencia DDL es independiente: asi una tabla ausente no
            # envenena la transaccion para el resto de migraciones.
            conn.autocommit = True
        else:
            conn = _connect_sqlite()
        try:
            _ensure_schema_migrations(conn)
            if USE_POSTGRES and not conn.autocommit:
                conn.commit()
        finally:
            try:
                conn.close()
            except Exception:
                pass
        _MIGRATIONS_DONE = True
        logger.info(
            "[DB] Migraciones aplicadas en %.0f ms (backend=%s)",
            (time.monotonic() - started) * 1000,
            "postgres" if USE_POSTGRES else "sqlite",
        )
        return True


def _ensure_migrations_done() -> None:
    """Dispara las migraciones una unica vez, sin castigar si la DB no responde."""
    if _MIGRATIONS_DONE:
        return
    if DB_MIGRATION_RETRY_COOLDOWN > 0:
        elapsed = time.monotonic() - _MIGRATIONS_ATTEMPT["last"]
        if _MIGRATIONS_ATTEMPT["last"] and elapsed < DB_MIGRATION_RETRY_COOLDOWN:
            return
    try:
        run_migrations()
    except Exception as error:
        logger.error(f"[DB] Migraciones fallidas: {error}")


def _fetch_result(cursor, fetch):
    if fetch == "one":
        row = cursor.fetchone()
        return dict(row) if row else None
    if fetch == "all":
        return [dict(row) for row in cursor.fetchall()]
    if fetch == "count":
        return cursor.rowcount
    return None


def _run_query(raw: str, safe_params: tuple, fetch, use_postgres: bool):
    """Ejecuta una sentencia sobre una conexion del pool (o SQLite efimera)."""
    if use_postgres:
        with _pg_connection() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(raw, safe_params or ())
                    result = _fetch_result(cursor, fetch)
                conn.commit()
                return result
            except BaseException:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
    conn = _connect_sqlite()
    try:
        cursor = conn.execute(raw, safe_params or ())
        return _fetch_result(cursor, fetch)
    finally:
        conn.close()


# Estados SQL que garantizan que la sentencia NO llego a aplicarse.
_UNCOMMITTED_SQLSTATES = {"57014", "40001", "40P01", "55P03", "53300", "25006"}


def _error_type(owner, name):
    return getattr(owner, name, None)


def _is_uncommitted_error(error: BaseException) -> bool:
    """El servidor asegura que la sentencia fallo: reintentar es seguro."""
    if getattr(error, "sqlstate", None) in _UNCOMMITTED_SQLSTATES:
        return True
    if isinstance(error, sqlite3.OperationalError):
        text = str(error).lower()
        return "locked" in text or "busy" in text
    if psycopg is None:
        return False
    types = tuple(
        t
        for t in (
            _error_type(psycopg.errors, "LockNotAvailable"),
            _error_type(psycopg.errors, "QueryCanceled"),
            _error_type(psycopg.errors, "SerializationFailure"),
            _error_type(psycopg.errors, "DeadlockDetected"),
            # La sentencia no llego a aplicarse: solo falló el PREPARE.
            _error_type(psycopg.errors, "DuplicatePreparedStatement"),
        )
        if t is not None
    )
    return bool(types) and isinstance(error, types)


def _is_connection_error(error: BaseException) -> bool:
    """Fallo a nivel de conexion: el estado en el servidor es desconocido."""
    if isinstance(error, sqlite3.OperationalError):
        text = str(error).lower()
        return "locked" in text or "busy" in text
    if getattr(error, "sqlstate", None) in {"08000", "08001", "08003", "08004", "08006", "08P01"}:
        return True
    if psycopg is None:
        return False
    types = tuple(
        t
        for t in (
            _error_type(psycopg, "OperationalError"),
            _error_type(psycopg, "InterfaceError"),
        )
        if t is not None
    )
    return bool(types) and isinstance(error, types)


def _should_retry(error: BaseException, fetch, attempt: int) -> bool:
    if attempt >= DB_RETRY_ATTEMPTS:
        return False
    # Errores que garantizan que la sentencia no se aplico: seguros incluso
    # para escrituras.
    if _is_uncommitted_error(error):
        return True
    # Conexion caida durante una escritura seria ambiguo (puede haberse
    # aplicado justo antes), asi que solo se reintenta en lecturas.
    return _is_connection_error(error) and fetch in ("one", "all")


def _retry_budget_exhausted(started: float) -> bool:
    """Los reintentos no pueden comerse el presupuesto de _run_db_operation.

    Si lo hicieran, asyncio.wait_for cortaria y el usuario volveria a ver el
    falso "la base de datos tardo demasiado" en vez del error real.
    """
    return (time.monotonic() - started) > DB_OPERATION_TIMEOUT_SECONDS * DB_RETRY_BUDGET_RATIO


def _can_retry(error: BaseException, fetch, attempt: int, started: float, backoff: float) -> bool:
    if not _should_retry(error, fetch, attempt):
        return False
    deadline = started + DB_OPERATION_TIMEOUT_SECONDS * DB_RETRY_BUDGET_RATIO
    return time.monotonic() + backoff < deadline


def execute(query, params=None, fetch=None):
    _ensure_migrations_done()
    raw, safe_params = _prepare_query_and_params(query, params, is_sqlite=not USE_POSTGRES)
    started = time.monotonic()
    attempt = 1
    while True:
        try:
            result = _run_query(raw, safe_params, fetch, USE_POSTGRES)
            elapsed_ms = (time.monotonic() - started) * 1000
            if elapsed_ms > SLOW_QUERY_MS:
                logger.warning("[DB][SLOW %.0fms] %s", elapsed_ms, raw[:120])
            return result
        except Exception as error:
            backoff = DB_RETRY_BACKOFF_SECONDS * attempt
            if _can_retry(error, fetch, attempt, started, backoff):
                attempt += 1
                logger.warning(
                    "[DB] Reintento %d/%d tras error transitorio (%s): %s",
                    attempt,
                    DB_RETRY_ATTEMPTS,
                    type(error).__name__,
                    error,
                )
                if backoff:
                    time.sleep(backoff)
                continue
            logger.error(
                "[DB] Error en query: %s | Query: %s | Params: %s",
                error,
                raw[:200],
                safe_params if USE_POSTGRES else "-",
            )
            raise


def execute_many(queries):
    _ensure_migrations_done()
    started = time.monotonic()
    attempt = 1
    while True:
        try:
            if USE_POSTGRES:
                with _pg_connection() as conn:
                    try:
                        with conn.cursor() as cursor:
                            for query, params in queries:
                                raw, safe_params = _prepare_query_and_params(query, params, is_sqlite=False)
                                cursor.execute(raw, safe_params or ())
                        conn.commit()
                    except BaseException:
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                        raise
            else:
                conn = _connect_sqlite()
                try:
                    for query, params in queries:
                        raw, safe_params = _prepare_query_and_params(query, params, is_sqlite=True)
                        conn.execute(raw, safe_params or ())
                finally:
                    conn.close()
            elapsed_ms = (time.monotonic() - started) * 1000
            if elapsed_ms > SLOW_QUERY_MS:
                logger.warning("[DB][SLOW BATCH %.0fms] %s queries", elapsed_ms, len(queries))
            return None
        except Exception as error:
            backoff = DB_RETRY_BACKOFF_SECONDS * attempt
            if _can_retry(error, None, attempt, started, backoff):
                attempt += 1
                logger.warning("[DB] Reintento %d/%d en lote: %s", attempt, DB_RETRY_ATTEMPTS, error)
                if backoff:
                    time.sleep(backoff)
                continue
            logger.error("[DB] Error en execute_many: %s", error)
            raise


def _run_transaction(queries) -> list:
    """Ejecuta una lista de sentencias DDL/DML como UNA sola transaccion.

    Es la base del modulo empresarial: cualquier movimiento de dinero (compra,
    nomina, venta de empresa, acciones) se aplica completa o no se aplica. Si una
    sentencia falla a mitad, nada queda escrito y el balance no se descuadra.

    `queries` es una lista de tuplas (query, params). Devuelve los resultados de
    las sentencias que pidieron `fetch` (tuplas de 3 elementos: q, params, fetch).
    """
    if not queries:
        return []

    if USE_POSTGRES:
        with _pg_connection() as conn:
            results = []
            try:
                for item in queries:
                    query, params = item[0], item[1]
                    fetch = item[2] if len(item) > 2 else None
                    raw, safe_params = _prepare_query_and_params(query, params, is_sqlite=False)
                    with conn.cursor() as cursor:
                        cursor.execute(raw, safe_params or ())
                        if fetch:
                            results.append(_fetch_result(cursor, fetch))
                conn.commit()
                return results
            except BaseException:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise

    conn = _connect_sqlite()
    results = []
    try:
        # isolation_level=None deja la conexion en autocommit: sin BEGIN explicito
        # cada sentencia se confirmaria por separado y no habria atomicidad.
        conn.execute("BEGIN IMMEDIATE")
        try:
            for item in queries:
                query, params = item[0], item[1]
                fetch = item[2] if len(item) > 2 else None
                raw, safe_params = _prepare_query_and_params(query, params, is_sqlite=True)
                cursor = conn.execute(raw, safe_params or ())
                if fetch:
                    results.append(_fetch_result(cursor, fetch))
            conn.execute("COMMIT")
            return results
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
    finally:
        conn.close()


def execute_atomic(queries):
    """Version sincrona de `_run_transaction`."""
    _ensure_migrations_done()
    started = time.monotonic()
    attempt = 1
    while True:
        try:
            results = _run_transaction(queries)
            elapsed_ms = (time.monotonic() - started) * 1000
            if elapsed_ms > SLOW_QUERY_MS:
                logger.warning("[DB][SLOW TX %.0fms] %d queries", elapsed_ms, len(queries))
            return results
        except Exception as error:
            backoff = DB_RETRY_BACKOFF_SECONDS * attempt
            # Una transacion revertida NO se reintenta a ciegas: el servidor ya
            # garantiza que nada quedo escrito y el error suele ser de logica
            # (saldo insuficiente, clave duplicada), no transitorio.
            if _can_retry(error, None, attempt, started, backoff):
                attempt += 1
                logger.warning(
                    "[DB] Reintento %d/%d en transaccion (%s)",
                    attempt,
                    DB_RETRY_ATTEMPTS,
                    error,
                )
                if backoff:
                    time.sleep(backoff)
                continue
            logger.error(
                "[DB] Error en transaccion: %s | Queries: %d",
                error,
                len(queries),
            )
            raise


async def aexecute_atomic(queries):
    """Version asincrona de `execute_atomic` (el camino de los comandos slash)."""
    return await _run_db_operation(execute_atomic, queries)


# Sentencias del esquema que fallan solo porque una tabla YA existente no tiene
# la columna que su indice usa: `CREATE TABLE IF NOT EXISTS` no repara una tabla
# vieja. Pasaba con `properties(company_id)` al meter empresas en un servidor que
# ya tenia datos. La columna y el indice los pone despues la migracion, asi que
# en el esquema esa sentencia se omite en vez de impedir el arranque.
_MISSING_COLUMN_ERRORS = (
    re.compile(r'column "[^"]+" does not exist', re.IGNORECASE),
    re.compile(r"no such column", re.IGNORECASE),
)


def _is_missing_column_error(error: Exception) -> bool:
    """True si el error es "a esa tabla le falta la columna", no otra cosa."""
    message = str(error)
    return any(pattern.search(message) for pattern in _MISSING_COLUMN_ERRORS)


def initialize_schema(schema: str):
    """Crea el esquema completo. Solo en arranque: usa conexion propia y timeout amplio.

    Cada sentencia DDL va por separado y en autocommit. Antes era una unica
    transaccion: un solo fallo abortaba las 60+ CREATE TABLE que venian
    despues y el bot no arrancaba. Ahora una sentencia que falla por una tabla
    vieja sin esa columna se omite sola (la repara la migracion posterior) y
    cualquier otro error se sigue propagateiendo.
    """
    if USE_POSTGRES:
        conn = _connect_postgres(DB_MIGRATION_TIMEOUT_MS)
    else:
        conn = _connect_sqlite()
    pending = []
    try:
        if USE_POSTGRES:
            conn.autocommit = True
        with conn:
            for statement in schema.split(";"):
                if not statement.strip():
                    continue
                if not USE_POSTGRES:
                    statement = _to_sqlite(statement)
                try:
                    conn.execute(statement)
                except Exception as stmt_error:
                    if not _is_missing_column_error(stmt_error):
                        raise
                    pending.append(statement.strip().split("\n")[0][:60])
    finally:
        try:
            conn.close()
        except Exception:
            pass
    if pending:
        logger.warning(
            "[DB] %d sentencia(s) del esquema pendientes de migracion: %s",
            len(pending), pending[:3],
        )
    # Las migraciones van DESPUES: los ALTER COLUMN necesitan que las tablas
    # del esquema ya existan.
    _ensure_migrations_done()


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


def check_connection(force: bool = False) -> dict:
    """Prueba de vida de la base de datos. Solo `SELECT 1` sobre el pool.

    El panel web la llama cada 2s, asi que NO ejecuta migraciones ni abre
    conexiones nuevas: antes cada sondeo corria ~30 DDL y bloqueaba al bot.
    El resultado se cachea `DB_CHECK_CACHE_SECONDS` segundos.
    """
    now = time.monotonic()
    if not force and DB_CHECK_CACHE_SECONDS > 0:
        cached = _CHECK_CACHE.get("result")
        if cached and (now - cached["at"]) < DB_CHECK_CACHE_SECONDS:
            return dict(cached["data"])

    result = {
        "ok": False,
        "masked_url": _mask_url(DATABASE_URL) if USE_POSTGRES else f"sqlite:///{DB_PATH}",
        "error": None,
        "ssl": "Supabase/Postgres" if USE_POSTGRES else "no aplica",
        "backend": DB_BACKEND,
    }
    if USE_POSTGRES:
        try:
            with _pg_connection() as conn:
                try:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT 1 AS ok")
                        result["ok"] = bool(cursor.fetchone())
                    conn.commit()
                except BaseException:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    raise
        except Exception as pg_err:
            # No se degrada el backend global aqui: un fallo puntual del panel no
            # debe mandar al bot a escribir a la SQLite local.
            logger.warning(f"[DB] Falló la prueba de conexión a Postgres ({pg_err})")
            result["ok"] = False
            result["error"] = f"postgres: {pg_err}"
    else:
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

    if DB_CHECK_CACHE_SECONDS > 0:
        _CHECK_CACHE["result"] = {"at": now, "data": dict(result)}
    return result
