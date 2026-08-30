import os

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN", "")
DISCORD_CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID", "")

KEEP_ALIVE_PORT = 3000

INVESTMENT_TYPES = {
    "conservative": {"label": "Conservador", "rate": 5,  "days": 3, "emoji": "🟢"},
    "moderate":     {"label": "Moderado",    "rate": 12, "days": 5, "emoji": "🟡"},
    "aggressive":   {"label": "Agresivo",    "rate": 25, "days": 7, "emoji": "🔴"},
}

ANTISPAM_MESSAGES = 5
ANTISPAM_WINDOW_SECONDS = 5

XP_PER_MESSAGE_MIN = 5
XP_PER_MESSAGE_MAX = 15

DEFAULT_DAILY_AMOUNT = 500
DEFAULT_WEEKLY_AMOUNT = 2500
DEFAULT_TAX_RATE = 5
DEFAULT_SAVINGS_INTEREST = 2
DEFAULT_LOAN_INTEREST = 10
LOAN_TERM_DAYS = 7
MAX_ACTIVE_LOANS = 3
MAX_LOAN_TOTAL = 100_000
COMPANY_CREATION_COST = 5_000
PROPERTY_SELL_RETURN = 0.75
