import asyncio

# Critical: Create and set event loop BEFORE importing Pyrogram
# This is required for Pyrogram's synchronous wrapper initialization on some environments (e.g. Python 3.14)
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

import logging
import os

from pyrogram import Client, idle, filters
from config import config
from handlers.command_handler import setup_command_handlers
from handlers.payment_handler import setup_payment_handlers
from aiohttp import web

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Pyrogram Client ---
app = Client(
    "payment_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    in_memory=True
)

async def health_check(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    server = web.Application()
    server.add_routes([web.get('/', health_check)])
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Web server started on port {port}")

async def main():
    logger.info("Starting Robust Payment Receiver Bot...")

    # Global logger for all incoming messages (for debugging)
    @app.on_message(filters.all)
    async def log_all_messages(client, message):
        logger.info(f"DEBUG: Received message from {message.from_user.id if message.from_user else 'Unknown'}: {message.text or message.caption or '[No text]'}")
        message.continue_propagation()

    setup_command_handlers(app)
    setup_payment_handlers(app)

    # Start the Pyrogram client first to ensure it's up
    await app.start()
    me = await app.get_me()
    logger.info(f"Bot @{me.username} is running!")

    # Start the web server for Render health checks
    await start_web_server()

    # Keep the bot running until interrupted
    await idle()

    # Stop the client gracefully
    await app.stop()

if __name__ == "__main__":
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    finally:
        loop.close()
