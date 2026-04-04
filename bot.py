import asyncio

# For Python 3.14+, we must set an event loop before importing Pyrogram
# to avoid RuntimeError during synchronous wrapper initialization.
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client, filters, idle
from aiohttp import web
import os
import sys

# Import config, db and handlers
from config import API_ID, API_HASH, BOT_TOKEN, SMS_GROUP_ID, PORT
from database import init_settings, db
from utils.parser import parse_sms, store_payment

# Import all handlers to register them
import handlers.user
import handlers.payment
import handlers.admin

# Create Pyrogram Client
app = Client(
    "premium_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,
    plugins=dict(root="handlers")
)

# SMS Group Handler - Watch for payments
@app.on_message(filters.chat(SMS_GROUP_ID) & filters.text, group=-1)
async def sms_group_handler(client, message):
    amount, txn_id = parse_sms(message.text)
    if amount and txn_id:
        success, msg = await store_payment(amount, txn_id)
        if success:
            print(f"Stored payment: ₹{amount}, Txn: {txn_id}")
        else:
            print(f"Failed to store payment: {msg}")

# Health Check Server (Aiohttp)
async def health_check(request):
    try:
        # Check DB connection
        await db.command("ping")
        return web.json_response({"status": "running", "db": "connected"})
    except Exception as e:
        return web.json_response({"status": "running", "db": "error", "error": str(e)}, status=500)

async def start_health_server():
    server = web.Application()
    server.add_routes([web.get("/", health_check)])
    runner = web.AppRunner(server)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"Health check server running on port {PORT}")

async def main():
    # Start health check server FIRST to satisfy Render's port check
    await start_health_server()

    if not BOT_TOKEN or not API_ID or not API_HASH:
        print("CRITICAL: BOT_TOKEN, API_ID, or API_HASH is missing!")
        return

    # Initialize settings in DB
    try:
        print("Connecting to MongoDB...")
        await db.command("ping")
        await init_settings()
        print("MongoDB connected and settings initialized.")
    except Exception as e:
        print(f"CRITICAL: Failed to connect to MongoDB: {e}")
        print("Please check your MONGO_URI and ensure your IP is whitelisted in Atlas.")
        # We don't return here so the health check server keeps running

    # Start the bot client
    try:
        await app.start()
        print("Bot started!")
    except Exception as e:
        print(f"CRITICAL: Failed to start Pyrogram client: {e}")

    # Keep the bot running
    await idle()

    # Cleanup
    await app.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
