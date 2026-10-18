"""Long-running entry point: `python -m studybot`.

Restarting a bot does not invalidate its token. Discord resets a token only when:
  * someone presses "Reset Token" in the developer portal,
  * the token is found published (e.g. committed to a public GitHub repo, which
    Discord scans for automatically), or
  * the bot opens roughly 1000+ gateway sessions in 24 hours, typically a crash loop.
The last one is guarded against here with a small login budget.
"""
import asyncio
import json
import logging
import shutil
import sys
import time

import discord

from . import config
from .bot import StudyBot
from .db import Store

log = logging.getLogger("studybot")
DAY = 24 * 3600


def take_login_slot() -> float:
    """Records this login. Returns seconds to wait first if today's budget is spent."""
    path = config.DATA_DIR / "logins.json"
    now = time.time()
    try:
        stamps = [t for t in json.loads(path.read_text()) if now - t < DAY]
    except (FileNotFoundError, ValueError):
        stamps = []
    wait = 0.0
    if len(stamps) >= config.MAX_LOGINS_PER_DAY:
        wait = stamps[0] + DAY - now
    stamps.append(now + wait)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(stamps[-config.MAX_LOGINS_PER_DAY:]))
    return wait


async def main() -> int:
    if not config.BOT_TOKEN:
        log.error("Set STUDYBOT_TOKEN (or DISCORD_BOT_TOKEN).")
        return 2
    if config.PROVIDER == "codex":
        if not shutil.which(config.CODEX_BIN):
            log.error("STUDYBOT_PROVIDER=codex but %r is not on PATH. Install the Codex CLI and run `codex login`.", config.CODEX_BIN)
            return 2
        log.info("Using %s via Codex CLI%s", config.CODEX_MODEL, "" if config.GEMINI_API_KEY else " (voice answers off: no GEMINI_API_KEY)")
    elif not config.GEMINI_API_KEY:
        log.error("Set GEMINI_API_KEY (or STUDYBOT_PROVIDER=codex).")
        return 2
    wait = take_login_slot()
    if wait > 0:
        log.error(
            "Logged in %d times in the last 24h; something is crash-looping. Waiting %.0f min "
            "before reconnecting so Discord doesn't reset the token.",
            config.MAX_LOGINS_PER_DAY, wait / 60,
        )
        await asyncio.sleep(wait)

    bot = StudyBot(Store(config.DB_PATH))
    try:
        # discord.py reconnects (and resumes sessions) by itself on network drops,
        # so a healthy process should log in once and stay up indefinitely.
        await bot.start(config.BOT_TOKEN)
    except discord.LoginFailure:
        log.error(
            "Discord rejected the token. It was reset (portal, leak detection, or too many logins). "
            "Generate a new one in the developer portal and update the environment. "
            "Sleeping an hour so the supervisor doesn't hammer Discord."
        )
        await asyncio.sleep(3600)
        return 1
    finally:
        if not bot.is_closed():
            await bot.close()
    return 0


if __name__ == "__main__":
    discord.utils.setup_logging(level=logging.INFO)
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        pass
