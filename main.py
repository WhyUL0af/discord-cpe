import asyncio
import logging
import sys

from app.config import settings
from app.database import init_db
from app.bot.client import CpeBot


def setup_logging() -> None:
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # Mute noisy third-party loggers if not DEBUG
    if log_level > logging.DEBUG:
        logging.getLogger("discord.gateway").setLevel(logging.WARNING)
        logging.getLogger("discord.client").setLevel(logging.INFO)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)


async def main() -> None:
    setup_logging()
    logger = logging.getLogger("cpe_bot")
    logger.info("Starting CPE Discord Bot application...")

    # Initialize database
    try:
        await init_db()
    except Exception as e:
        logger.warning(
            f"Database initialization warning (will retry on operations): {e}"
        )

    if not settings.DISCORD_TOKEN or settings.DISCORD_TOKEN == "your_discord_bot_token_here":
        logger.error(
            "DISCORD_TOKEN is missing or not set in .env! "
            "Please create a .env file based on .env.example and set your DISCORD_TOKEN."
        )
        return

    bot = CpeBot()
    async with bot:
        await bot.start(settings.DISCORD_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.getLogger("cpe_bot").info("Application stopped gracefully.")
