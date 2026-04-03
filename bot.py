import asyncio
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
    # Initialize settings in DB
    await init_settings()

    # Start the bot client
    await app.start()
    print("Bot started!")

    # Start health check server
    await start_health_server()

    # Keep the bot running
    await idle()

    # Cleanup
    await app.stop()

if __name__ == "__main__":
    # Ensure event loop is set for Python 3.14+ (if needed)
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.run_until_complete(main())
