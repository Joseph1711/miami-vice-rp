-- Miami Vice RP - Supabase/Postgres schema
-- Also executed automatically by scripts/init_db.py.
-- =====================
-- USERS & GUILD CONFIG
-- =====================
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    discord_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    username TEXT,
    display_name TEXT,
    cash NUMERIC DEFAULT 500,
    bank NUMERIC DEFAULT 0,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    reputation INTEGER DEFAULT 0,
    dirty_money NUMERIC DEFAULT 0,
    profile_note TEXT DEFAULT 'Made By Joshi',
    is_verified BOOLEAN DEFAULT FALSE,
    last_daily TIMESTAMP,
    last_weekly TIMESTAMP,
    last_work TIMESTAMP,
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

ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_note TEXT DEFAULT 'Made By Joshi';
UPDATE users SET profile_note = 'Made By Joshi' WHERE profile_note IS NULL OR profile_note = 'Made By Joseph';
