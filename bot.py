import logging
from pyrogram import Client
from config import config
from handlers.command_handler import setup_command_handlers
from handlers.payment_handler import setup_payment_handlers
from handlers.admin_handler import setup_admin_handlers
from health_check import start_health_check_server
import asyncio

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Pyrogram Client ---
app = Client("payment_bot", api_id=config.API_ID, api_hash=config.API_HASH, bot_token=config.BOT_TOKEN)

async def run_bot():
    logger.info("Starting Robust Payment Receiver Bot...")
    setup_command_handlers(app)
    setup_payment_handlers(app)
    setup_admin_handlers(app)

    # Start the health check server
    await start_health_check_server()

    # Run the Pyrogram client
    await app.start()
    logger.info("Bot started. Waiting for messages...")

    # Keep the bot running using asyncio.Event().wait()
    # This avoids the pyrogram.idle() / asyncio.run() conflict during shutdown
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await app.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(run_bot())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
