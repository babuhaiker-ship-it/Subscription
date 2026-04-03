import logging
import asyncio
import os

# Set event loop for Python 3.14.3 compatibility as per memory
# Must be done before importing pyrogram.Client
asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client, idle
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
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
