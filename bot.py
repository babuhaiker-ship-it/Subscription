import asyncio

# --- Event Loop Initialization ---
# This MUST be at the absolute top before any Pyrogram imports to satisfy
# its synchronous wrapper initialization on Python 3.14+.
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

import logging
from pyrogram import Client, idle
from config import config
from handlers.command_handler import setup_command_handlers
from handlers.payment_handler import setup_payment_handlers
from aiohttp import web
from database import mongo_client

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
    try:
        # Basic check to see if database is reachable
        await mongo_client.admin.command('ping')
        return web.json_response({"status": "ok", "bot_running": app.is_connected, "database": "connected"})
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

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

    # 1. Start the Pyrogram client (as per Render best practices)
    await app.start()
    logger.info("Pyrogram client started.")

    # 2. Check Database connection
    try:
        await mongo_client.admin.command('ping')
        logger.info("Database connection established.")
    except Exception as e:
        logger.critical(f"Failed to connect to MongoDB: {e}")
        # We continue anyway, the health check will reflect the failure

    # 3. Setup handlers
    setup_command_handlers(app)
    setup_payment_handlers(app)

    # 4. Start the health check server
    await start_health_check()

    # 5. Keep the bot running
    await idle()

    # Stop the client gracefully on exit
    await app.stop()

if __name__ == "__main__":
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
