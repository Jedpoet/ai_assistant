import os
import discord
from discord.ext import commands
from discord import app_commands
from db.database import init_db
from dotenv import load_dotenv

load_dotenv()


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")


class FamilyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="/", intents=intents)

    async def setup_hook(self):
        init_db()
        # 載入所有 Cog
        await self.load_extension("bot.cogs.setup")
        await self.load_extension("bot.cogs.schedule")
        await self.load_extension("bot.cogs.week")
        await self.tree.sync()
        print("✅ Slash commands synced")

    async def on_ready(self):
        print(f"✅ Bot 已上線：{self.user}")

    def run(self):
        super().run(DISCORD_TOKEN)
