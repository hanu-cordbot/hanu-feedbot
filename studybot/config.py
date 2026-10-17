"""Runtime configuration for the study bot, read once from the environment."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Falls back to the feed bot's token so one Discord application can serve both.
BOT_TOKEN = os.getenv("STUDYBOT_TOKEN") or os.getenv("DISCORD_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Question writing and grading get the strongest model; it is the whole point.
GENERATION_MODEL = os.getenv("STUDYBOT_GENERATION_MODEL", "gemini-2.5-pro")
# Cheaper model used if the generation model is rate limited or unavailable.
FALLBACK_MODEL = os.getenv("STUDYBOT_FALLBACK_MODEL", "gemini-2.5-flash")

DATA_DIR = Path(os.getenv("STUDYBOT_DATA_DIR", "data/studybot"))
DB_PATH = DATA_DIR / "studybot.sqlite3"

# Optional: sync slash commands to one guild instantly instead of globally (up to 1h).
DEV_GUILD_ID = int(os.getenv("STUDYBOT_GUILD_ID", "0") or 0)

# Discord resets a bot's token after ~1000 gateway logins in 24h. A crash-looping
# container can hit that, so we refuse to log in more than this many times a day.
MAX_LOGINS_PER_DAY = int(os.getenv("STUDYBOT_MAX_LOGINS_PER_DAY", "200"))

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
CHUNK_CHARS = 3500
CHUNK_OVERLAP = 400
