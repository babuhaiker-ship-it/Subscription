import asyncio

# For Python 3.14+, we must set an event loop before importing Pyrogram
# to avoid RuntimeError during synchronous wrapper initialization.
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client, filters, idle
from aiohttp import web

# Import config, db and handlers
from config import API_ID, API_HASH, BOT_TOKEN, SMS_GROUP_ID, PORT, MONGO_URI, DB_NAME
from database import init_settings, db
from utils.parser import parse_sms, store_payment

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
@app.on_message(filters.text, group=-1)
async def sms_group_handler(client, message):
    # Fetch allowed group from settings or fallback to config
    from database import get_setting
    allowed_group = await get_setting("sms_group_id") or SMS_GROUP_ID

    print(f"DEBUG: Received message in chat {message.chat.id}. Expected group: {allowed_group}")

    if message.chat.id != allowed_group:
        return

    print(f"DEBUG: Processing message: {message.text[:50]}...")
    amount, txn_ids = parse_sms(message.text)
    if amount and txn_ids:
        success, msg = await store_payment(amount, txn_ids)
        if success:
            print(f"✅ Stored payment: ₹{amount}, IDs: {txn_ids}")
        else:
            print(f"❌ Failed to store payment: {msg}")
    else:
        print(f"⚠️ Could not parse message. Extracted: Amount={amount}, IDs={txn_ids}")

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
        masked_uri = MONGO_URI.split("@")[-1] if MONGO_URI else "None"
        print(f"Connecting to MongoDB: {DB_NAME} (Host: {masked_uri})")
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
