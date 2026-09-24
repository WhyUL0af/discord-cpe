import logging
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

INITIAL_EXTENSIONS = [
    "app.bot.events.error_handler",
    "app.bot.commands.setup_cog",
    "app.bot.commands.account_cog",
    "app.bot.commands.problem_cog",
    "app.bot.commands.rank_cog",
    "app.tasks.submission_tracker",
    "app.tasks.daily_problem_task",
    "app.tasks.ranking_updater_task",
]


class CpeBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True

        super().__init__(
            command_prefix="!cpe_",  # Slash commands are primary, prefix fallback
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self) -> None:
        logger.info("Setting up extensions...")
        for extension in INITIAL_EXTENSIONS:
            try:
                await self.load_extension(extension)
                logger.info(f"Loaded extension: {extension}")
            except Exception as e:
                logger.error(f"Failed to load extension {extension}: {e}", exc_info=True)

        # Register persistent views for button interactions across restarts
        from app.bot.views.problem_view import DailyProblemView, PracticeCenterView
        self.add_view(PracticeCenterView())
        self.add_view(DailyProblemView())

        logger.info("Syncing application commands with Discord...")
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} application commands globally.")
        except Exception as e:
            logger.error(f"Failed to sync application commands: {e}", exc_info=True)

    async def on_ready(self) -> None:
        if self.user:
            logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info("CPE Discord Bot is online and ready.")

        # Sync/verify persistent practice center messages for all connected guilds
        from app.bot.commands.setup_cog import deploy_or_sync_practice_center
        for guild in self.guilds:
            try:
                await deploy_or_sync_practice_center(self, guild.id)
            except Exception as e:
                logger.warning(f"Could not auto-sync practice center in guild {guild.id}: {e}")
