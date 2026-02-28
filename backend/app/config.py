import os
from pathlib import Path

# python-dotenv correctly handles quoted values and '#' inside quotes,
# unlike Docker Compose's env_file: which truncates at '#'.
_env_file = Path("/app/.env")
if _env_file.exists():
    from dotenv import dotenv_values
    _env = dotenv_values(_env_file)
else:
    _env = {}

def _get(key: str, default: str = "") -> str:
    # Prefer the dotenv-parsed value; fall back to os.environ (e.g. local dev)
    return _env.get(key) or os.environ.get(key, default)

HIPASS_ID: str = _get("HIPASS_ID")
HIPASS_PW: str = _get("HIPASS_PW")
ECD_NO: str = _get("ECD_NO")

SCREENSHOTS_DIR: Path = Path(_get("SCREENSHOTS_DIR", "/app/screenshots"))
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

RETENTION_DAYS: int = int(_get("RETENTION_DAYS", "14"))
SCHEDULE_HOUR: int = int(_get("SCHEDULE_HOUR", "6"))
