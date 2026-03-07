import asyncio
import logging
from bot.client import FamilyBot
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

if __name__ == "__main__":
    bot = FamilyBot()
    bot.run()
