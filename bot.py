import asyncio
import logging
from pyrogram import Client
from config import config
from handlers.command_handler import setup_command_handlers
from handlers.payment_handler import setup_payment_handlers
from aiohttp import web

# --- Event Loop Initialization ---
# Required for Pyrogram on Python 3.14+ or some serverless environments
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

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

# --- Health Check Server ---
async def health_check(request):
    return web.Response(text="Bot is running!")

async def start_health_check():
    webapp = web.Application()
    webapp.router.add_get("/", health_check)
    runner = web.AppRunner(webapp)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.PORT)
    await site.start()
    logger.info(f"Health check server started on port {config.PORT}")

async def main():
    logger.info("Starting Robust Payment Receiver Bot...")
    setup_command_handlers(app)
    setup_payment_handlers(app)

    # Start the Pyrogram client
    await app.start()
    logger.info("Pyrogram client started.")

    # Start the health check server
    await start_health_check()

    # Keep the bot running
    # We use idle() to keep the main task alive while Pyrogram handles updates
    from pyrogram import idle
    await idle()

    # Stop the client gracefully on exit
    await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
