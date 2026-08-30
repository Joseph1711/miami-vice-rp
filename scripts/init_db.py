"""
 Inicializa todas las tablas de la base de datos para Miami Vice Bot.
Ejecutar una sola vez (o cuando se agreguen tablas nuevas).
"""
import os
import sys
import logging

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if "." not in sys.path:
    sys.path.insert(0, os.path.abspath("."))

logger = logging.getLogger("bot")

SCHEMA = """
-- =====================
-- USERS & GUILD CONFIG
-- =====================
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    discord_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    cash NUMERIC DEFAULT 500,
    bank NUMERIC DEFAULT 0,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    reputation INTEGER DEFAULT 0,
    dirty_money NUMERIC DEFAULT 0,
    is_verified BOOLEAN DEFAULT FALSE,
    last_daily TIMESTAMP,
    last_weekly TIMESTAMP,
    last_work TIMESTAMP,
    username TEXT,
    display_name TEXT,
    profile_note TEXT DEFAULT 'Made By Joshi',
    roblox_username TEXT,
    roblox_id TEXT,
    roblox_profile_url TEXT,
    dni_number TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(discord_id, guild_id)
);

CREATE TABLE IF NOT EXISTS guild_config (
    id TEXT PRIMARY KEY,
    guild_id TEXT UNIQUE NOT NULL,
    daily_amount INTEGER DEFAULT 500,
    weekly_amount INTEGER DEFAULT 2500,
    tax_rate NUMERIC DEFAULT 5,
    xp_multiplier NUMERIC DEFAULT 1.0,
    log_channel_id TEXT,
    admin_role_id TEXT,
    work_logs_channel_id TEXT,
    applications_channel_id TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =====================
-- TRANSACTIONS
-- =====================
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    discord_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    type TEXT NOT NULL,
    amount NUMERIC NOT NULL,
    description TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT NOW()
);

-- =====================
-- JOBS
-- =====================
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    name TEXT NOT NULL,
    min_pay INTEGER DEFAULT 100,
    max_pay INTEGER DEFAULT 500,
    cooldown_minutes INTEGER DEFAULT 60,
    emoji TEXT DEFAULT '💼',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =====================
-- ITEMS & INVENTORY
-- =====================
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    category TEXT DEFAULT 'General',
    rarity TEXT DEFAULT 'common',
    price NUMERIC DEFAULT 0,
    emoji TEXT DEFAULT '📦',
    is_active BOOLEAN DEFAULT TRUE,
    black_market_only BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS user_inventory (
    id TEXT PRIMARY KEY,
    discord_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    quantity INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(discord_id, guild_id, item_id)
);

-- =====================
-- MARKETPLACE & AUCTIONS
-- =====================
CREATE TABLE IF NOT EXISTS marketplace_listings (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    seller_id TEXT NOT NULL,
    item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    quantity INTEGER DEFAULT 1,
    price NUMERIC NOT NULL,
    status TEXT DEFAULT 'active',
    buyer_id TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auctions (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    seller_id TEXT NOT NULL,
    item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    quantity INTEGER DEFAULT 1,
    starting_bid NUMERIC NOT NULL,
    current_bid NUMERIC,
    current_bidder_id TEXT,
    status TEXT DEFAULT 'active',
    ends_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =====================
-- SHOP & BLACK MARKET
-- =====================
CREATE TABLE IF NOT EXISTS shop (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    price NUMERIC NOT NULL,
    stock INTEGER DEFAULT -1,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(guild_id, item_id)
);

CREATE TABLE IF NOT EXISTS black_market_stock (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    price_modifier NUMERIC DEFAULT 1.0,
    quantity INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS black_market_transactions (
    id TEXT PRIMARY KEY,
    discord_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    quantity INTEGER DEFAULT 1,
    price NUMERIC NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- =====================
-- BANKING
-- =====================
CREATE TABLE IF NOT EXISTS savings_accounts (
    id TEXT PRIMARY KEY,
    discord_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    balance NUMERIC DEFAULT 0,
    interest_rate NUMERIC DEFAULT 2,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(discord_id, guild_id)
);

CREATE TABLE IF NOT EXISTS investments (
    id TEXT PRIMARY KEY,
    discord_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    type TEXT NOT NULL,
    amount NUMERIC NOT NULL,
    return_rate NUMERIC NOT NULL,
    matures_at TIMESTAMP NOT NULL,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS loans (
    id TEXT PRIMARY KEY,
    discord_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    amount NUMERIC NOT NULL,
    interest_rate NUMERIC DEFAULT 10,
    total_due NUMERIC NOT NULL,
    due_date TIMESTAMP NOT NULL,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS treasury (
    id TEXT PRIMARY KEY,
    guild_id TEXT UNIQUE NOT NULL,
    balance NUMERIC DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =====================
-- DEPARTMENTS
-- =====================
CREATE TABLE IF NOT EXISTS departments (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    name TEXT NOT NULL,
    acronym TEXT NOT NULL,
    description TEXT DEFAULT '',
    budget NUMERIC DEFAULT 0,
    role_id TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(guild_id, acronym)
);

CREATE TABLE IF NOT EXISTS department_members (
    id TEXT PRIMARY KEY,
    department_id TEXT NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    discord_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    rank TEXT DEFAULT 'Oficial',
    salary NUMERIC DEFAULT 0,
    joined_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(department_id, discord_id)
);

CREATE TABLE IF NOT EXISTS department_audit (
    id TEXT PRIMARY KEY,
    department_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    action TEXT NOT NULL,
    performed_by TEXT NOT NULL,
    target_id TEXT,
    details TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT NOW()
);

-- =====================
-- FLEET
-- =====================
CREATE TABLE IF NOT EXISTS fleet_vehicle_types (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    name TEXT NOT NULL,
    price NUMERIC DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(guild_id, name)
);

CREATE TABLE IF NOT EXISTS fleet_vehicles (
    id TEXT PRIMARY KEY,
    department_id TEXT NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    guild_id TEXT NOT NULL,
    vehicle_type_id TEXT NOT NULL REFERENCES fleet_vehicle_types(id) ON DELETE CASCADE,
    plate TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'active',
    assigned_to TEXT,
    repair_completes_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =====================
-- COMPANIES
-- =====================
CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    funds NUMERIC DEFAULT 0,
    tax_rate NUMERIC DEFAULT 5,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(guild_id, name)
);

CREATE TABLE IF NOT EXISTS company_members (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    discord_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    role TEXT DEFAULT 'Empleado',
    salary NUMERIC DEFAULT 0,
    joined_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(company_id, discord_id)
);

-- =====================
-- PROPERTIES
-- =====================
CREATE TABLE IF NOT EXISTS properties (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT DEFAULT 'house',
    price NUMERIC NOT NULL,
    rent_price NUMERIC,
    status TEXT DEFAULT 'available',
    owner_id TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS property_transactions (
    id TEXT PRIMARY KEY,
    property_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    buyer_id TEXT NOT NULL,
    amount NUMERIC NOT NULL,
    type TEXT DEFAULT 'purchase',
    created_at TIMESTAMP DEFAULT NOW()
);

-- =====================
-- VERIFICATION
-- =====================
CREATE TABLE IF NOT EXISTS verification_config (
    id TEXT PRIMARY KEY,
    guild_id TEXT UNIQUE NOT NULL,
    verified_role_id TEXT,
    log_channel_id TEXT,
    min_account_age_days INTEGER DEFAULT 7,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS verification_logs (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    discord_id TEXT NOT NULL,
    ign TEXT,
    age TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- =====================
-- TICKETS
-- =====================
CREATE TABLE IF NOT EXISTS ticket_config (
    id TEXT PRIMARY KEY,
    guild_id TEXT UNIQUE NOT NULL,
    category_id TEXT,
    support_role_id TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    creator_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    status TEXT DEFAULT 'open',
    closed_by TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =====================
-- APPLICATIONS
-- =====================
CREATE TABLE IF NOT EXISTS application_config (
    id TEXT PRIMARY KEY,
    guild_id TEXT UNIQUE NOT NULL,
    log_channel_id TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    discord_id TEXT NOT NULL,
    type TEXT NOT NULL,
    experience TEXT DEFAULT '',
    motivation TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    reviewed_by TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =====================
-- CONTRACTS
-- =====================
CREATE TABLE IF NOT EXISTS contracts (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    creator_id TEXT NOT NULL,
    assignee_id TEXT,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    reward NUMERIC DEFAULT 0,
    status TEXT DEFAULT 'open',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =====================
-- ROLE AUTOMATION
-- =====================
CREATE TABLE IF NOT EXISTS temp_roles (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    discord_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS level_rewards (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    level INTEGER NOT NULL,
    role_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(guild_id, level)
);

CREATE TABLE IF NOT EXISTS auto_roles (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(guild_id, role_id)
);

-- =====================
-- CRIME SYSTEM
-- =====================
CREATE TABLE IF NOT EXISTS drug_operations (
    id TEXT PRIMARY KEY,
    discord_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    drug_type TEXT NOT NULL,
    cost NUMERIC DEFAULT 0,
    harvest_at TIMESTAMP NOT NULL,
    status TEXT DEFAULT 'growing',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS money_laundering (
    id TEXT PRIMARY KEY,
    discord_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    method TEXT NOT NULL,
    amount_dirty NUMERIC NOT NULL,
    amount_clean NUMERIC NOT NULL,
    fee NUMERIC DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS criminal_missions (
    id TEXT PRIMARY KEY,
    discord_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    mission_name TEXT NOT NULL,
    reward NUMERIC DEFAULT 0,
    completes_at TIMESTAMP NOT NULL,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =====================
-- WORK SUBMISSIONS & EVIDENCE (TRABAJOS SECUNDARIOS)
-- =====================
CREATE TABLE IF NOT EXISTS work_submissions (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    discord_id TEXT NOT NULL,
    job_type TEXT NOT NULL,
    description TEXT NOT NULL,
    evidence TEXT NOT NULL,
    hours_or_shifts TEXT DEFAULT '1',
    status TEXT DEFAULT 'pending',
    reward_amount NUMERIC DEFAULT 0,
    reward_xp INTEGER DEFAULT 0,
    reviewer_id TEXT,
    review_notes TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT NOW(),
    reviewed_at TIMESTAMP
);

-- =====================
-- DNI / IDENTIDAD CIUDADANA & ROBLOX
-- =====================
CREATE TABLE IF NOT EXISTS dni_records (
    id TEXT PRIMARY KEY,
    discord_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    dni_number TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    birth_date TEXT,
    age INTEGER DEFAULT 18,
    gender TEXT DEFAULT 'No especificado',
    nationality TEXT DEFAULT 'Estadounidense',
    occupation TEXT DEFAULT 'Ciudadano',
    roblox_username TEXT,
    roblox_id TEXT,
    roblox_profile_url TEXT,
    blood_type TEXT DEFAULT 'O+',
    avatar_url TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(discord_id, guild_id)
);

-- =====================
-- REGISTRO DE ARMAS & SERIES ÚNICAS
-- =====================
CREATE TABLE IF NOT EXISTS weapon_registries (
    id TEXT PRIMARY KEY,
    discord_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    serial_number TEXT UNIQUE NOT NULL,
    weapon_name TEXT NOT NULL,
    weapon_type TEXT DEFAULT 'Arma de Fuego',
    caliber TEXT DEFAULT '9mm',
    license_type TEXT DEFAULT 'Defensa Personal',
    status TEXT DEFAULT 'registered',
    dni_number TEXT,
    roblox_username TEXT,
    notes TEXT DEFAULT '',
    registered_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =====================
-- BOT UPDATES & ANNOUNCEMENTS
-- =====================
CREATE TABLE IF NOT EXISTS bot_updates_config (
    id TEXT PRIMARY KEY,
    guild_id TEXT UNIQUE NOT NULL,
    channel_id TEXT,
    github_repo TEXT DEFAULT 'Joseph1711/miami-vice-rp',
    auto_github_enabled BOOLEAN DEFAULT TRUE,
    last_commit_sha TEXT,
    draft_version TEXT DEFAULT 'v1.4.0',
    draft_changes TEXT,
    draft_description TEXT,
    draft_date TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bot_updates_history (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    version TEXT NOT NULL,
    title TEXT NOT NULL,
    raw_message TEXT NOT NULL,
    changes TEXT NOT NULL,
    source TEXT DEFAULT 'manual',
    commit_sha TEXT,
    channel_id TEXT,
    message_id TEXT,
    published_by TEXT,
    published_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);

-- =====================
-- VEHICLE & TRAILER & ATV REGISTRIES
-- =====================
CREATE TABLE IF NOT EXISTS vehicle_registries (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    discord_id TEXT NOT NULL,
    dni_id TEXT,
    dni_number TEXT,
    vehicle_type TEXT NOT NULL,
    brand_model TEXT NOT NULL,
    color TEXT NOT NULL,
    plate TEXT UNIQUE NOT NULL,
    vin_number TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'active',
    registration_fee NUMERIC DEFAULT 500,
    insurance_status TEXT DEFAULT 'basic',
    notes TEXT,
    impound_reason TEXT,
    impound_fine NUMERIC DEFAULT 0,
    registered_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =====================
-- POLICE BOLO (BE ON THE LOOKOUT)
-- =====================
CREATE TABLE IF NOT EXISTS police_bolos (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    bolo_code TEXT UNIQUE NOT NULL,
    target_type TEXT NOT NULL,
    target_name TEXT NOT NULL,
    reason TEXT NOT NULL,
    danger_level TEXT DEFAULT 'media',
    reward NUMERIC DEFAULT 0,
    image_url TEXT,
    status TEXT DEFAULT 'active',
    officer_id TEXT NOT NULL,
    officer_name TEXT,
    resolution_notes TEXT,
    resolved_by TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =====================
-- POLICE & JUSTICE CASES (EXPEDIENTES)
-- =====================
CREATE TABLE IF NOT EXISTS police_cases (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    case_number TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    priority TEXT DEFAULT 'media',
    description TEXT NOT NULL,
    lead_detective_id TEXT NOT NULL,
    lead_detective_name TEXT,
    status TEXT DEFAULT 'abierto',
    suspects_json TEXT DEFAULT '[]',
    evidence_json TEXT DEFAULT '[]',
    notes_json TEXT DEFAULT '[]',
    verdict TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =====================
-- POLICE INCIDENTS & 911 DISPATCH (DESPACHO DE EMERGENCIAS)
-- =====================
CREATE TABLE IF NOT EXISTS police_incidents (
    id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    incident_code TEXT UNIQUE NOT NULL,
    incident_type TEXT NOT NULL,
    location TEXT NOT NULL,
    description TEXT NOT NULL,
    priority_code TEXT DEFAULT 'codigo_2',
    caller_id TEXT,
    caller_name TEXT,
    assigned_units TEXT,
    status TEXT DEFAULT 'activo',
    resolution_report TEXT,
    closed_by TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =====================
-- DB INITIALIZATION STATE
-- =====================
CREATE TABLE IF NOT EXISTS db_state (
    id TEXT PRIMARY KEY,
    initialized BOOLEAN DEFAULT TRUE,
    initialized_at TIMESTAMP DEFAULT NOW(),
    table_count INTEGER DEFAULT 0
);

"""

def _check_tables_exist():
    """Verifica si las tablas ya existen sin intentar crearlas."""
    from bot.db import execute, USE_POSTGRES
    
    try:
        if USE_POSTGRES:
            result = execute(
                """SELECT COUNT(*) as count FROM information_schema.tables 
                   WHERE table_schema = 'public'""",
                fetch="one"
            )
        else:
            result = execute(
                """SELECT COUNT(*) as count FROM sqlite_master 
                   WHERE type='table' AND name NOT LIKE 'sqlite_%'""",
                fetch="one"
            )
        
        count = result.get("count", 0) if result else 0
        return count > 5  # Si hay más de 5 tablas, asumimos que ya está inicializado
    except Exception as e:
        logger.warning(f"Error verificando tablas: {e}")
        return False


def _ensure_profile_note():
    from bot.db import USE_POSTGRES, execute
    try:
        if USE_POSTGRES:
            execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_note TEXT DEFAULT 'Made By Joshi'")
            execute("ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS admin_role_id TEXT")
            execute("ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS work_logs_channel_id TEXT")
            execute("ALTER TABLE guild_config ADD COLUMN IF NOT EXISTS applications_channel_id TEXT")
        else:
            u_cols = execute("PRAGMA table_info(users)", fetch="all") or []
            if not any(column.get("name") == "profile_note" for column in u_cols):
                execute("ALTER TABLE users ADD COLUMN profile_note TEXT DEFAULT 'Made By Joshi'")
            
            g_cols = execute("PRAGMA table_info(guild_config)", fetch="all") or []
            g_names = [col.get("name") for col in g_cols]
            if "admin_role_id" not in g_names:
                execute("ALTER TABLE guild_config ADD COLUMN admin_role_id TEXT")
            if "work_logs_channel_id" not in g_names:
                execute("ALTER TABLE guild_config ADD COLUMN work_logs_channel_id TEXT")
            if "applications_channel_id" not in g_names:
                execute("ALTER TABLE guild_config ADD COLUMN applications_channel_id TEXT")
        
        execute("UPDATE users SET profile_note='Made By Joshi' WHERE profile_note IS NULL OR profile_note='Made By Joseph'")
    except Exception as e:
        logger.warning(f"Error al agregar columnas adicionales: {e}")


def init_db():
    """Inicializa y verifica todas las tablas de la base de datos."""
    from bot.db import check_connection, initialize_schema
    
    result = check_connection()
    if not result["ok"]:
        raise RuntimeError(f"No se puede conectar a la base de datos: {result['error']}")
    
    try:
        logger.info("🔧 Verificando / creando tablas en la base de datos...")
        initialize_schema(SCHEMA)
        _ensure_profile_note()
        logger.info("✅ Base de datos lista y sincronizada (tablas completas disponibles).")
    except Exception as e:
        logger.error(f"❌ Error al verificar/crear tablas: {e}")
        raise

if __name__ == "__main__":
    init_db()
