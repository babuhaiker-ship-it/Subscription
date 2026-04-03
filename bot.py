import logging
import asyncio

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client
from config import config
from handlers.command_handler import setup_command_handlers
from handlers.payment_handler import setup_payment_handlers

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Pyrogram Client ---
app = Client("payment_bot", api_id=config.API_ID, api_hash=config.API_HASH, bot_token=config.BOT_TOKEN)

if __name__ == "__main__":
    logger.info("Starting Robust Payment Receiver Bot...")
    setup_command_handlers(app)
    setup_payment_handlers(app)
    app.run()
