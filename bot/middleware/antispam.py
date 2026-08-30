import datetime
from bot.config import ANTISPAM_MESSAGES, ANTISPAM_WINDOW_SECONDS

_windows: dict[str, list[float]] = {}

def is_spamming(user_id: str, guild_id: str) -> bool:
    key = f"{user_id}:{guild_id}"
    now = datetime.datetime.utcnow().timestamp()
    window = _windows.get(key, [])
    _windows[key] = [t for t in window if now - t < ANTISPAM_WINDOW_SECONDS]
    _windows[key].append(now)
    return len(_windows[key]) > ANTISPAM_MESSAGES

def check_command_cooldown(key: str, seconds: float) -> float:
    from bot.middleware.antispam import _cooldowns
    now = datetime.datetime.utcnow().timestamp()
    last = _cooldowns.get(key, 0.0)
    remaining = (last + seconds) - now
    if remaining > 0:
        return remaining
    _cooldowns[key] = now
    return 0.0

_cooldowns: dict[str, float] = {}
