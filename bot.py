import os
import re
import asyncio
from datetime import datetime, timedelta
import logging

from pyrogram import Client, filters, types
from motor.motor_asyncio import AsyncIOMotorClient
from bson.objectid import ObjectId

# --- Logging Setup ---
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Bot Configuration Class ---
class BotConfig:
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "7673807124:AAETa1Bty4C4CU0De1PuP31FwMXLmgPwQLk")
    API_ID = int(os.environ.get("API_ID", 29800015))
    API_HASH = os.environ.get("API_HASH", "c8f37108be31ab9ea2818bfe533fbb6f")
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://Pyasipriya:00pEcao9sYhNC5VQ@cluster0.2dfenf7.mongodb.net/spicybot?retryWrites=true&w=majority&appName=Cluster0")
    MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "spicybot")
    UPI_LINK = os.environ.get("UPI_LINK", "upi://pay?pa=you@upi&pn=YourName&mc=0000&tid=00000000000000&tr=YourRef&am=1.00")
    QR_CODE_IMAGE_URL = os.environ.get("QR_CODE_IMAGE_URL", "https://placehold.co/300x300/000000/FFFFFF?text=Scan+QR")
    TXN_GROUP_ID = int(os.environ.get("TXN_GROUP_ID", -1002685844988))
    SUBSCRIPTION_PLANS = {
        "weekly": {"amount": 49, "duration_days": 7},
        "monthly": {"amount": 149, "duration_days": 30},
    }
    PAYMENT_MESSAGE_DELETE_DELAY = 600
    ADMIN_IDS = [123456789]

# --- MongoDB Connection ---
mongo_client = AsyncIOMotorClient(BotConfig.MONGO_URI)
db = mongo_client[BotConfig.MONGO_DB_NAME]

users_collection = db.users
tokens_collection = db.tokens
history_collection = db.history
confirmed_upi_txns_collection = db.confirmed_upi_txns

# --- Pyrogram Client ---
app = Client(
    "SubscriptionBot",
    api_id=BotConfig.API_ID,
    api_hash=BotConfig.API_HASH,
    bot_token=BotConfig.BOT_TOKEN
)

# --- Helper Functions ---
async def get_user_stats(user_id: int):
    user_data = await users_collection.find_one({"user_id": user_id})
    user_tokens = await tokens_collection.find_one({"user_id": user_id})
    user_history = await history_collection.find_one({"user_id": user_id})

    is_premium = False
    active_tokens_count = 0
    expires_at = "N/A"

    if user_tokens and user_tokens.get("tokens"):
        now = datetime.utcnow()
        active_tokens = [
            token for token in user_tokens["tokens"]
            if token.get("is_admin_granted") and token.get("expires_at") and token["expires_at"] > now
        ]
        active_tokens_count = len(active_tokens)
        if active_tokens_count > 0:
            is_premium = True
            latest_expiry = max(token["expires_at"] for token in active_tokens)
            expires_at = latest_expiry.strftime("%Y-%m-%d %H:%M UTC")

    referral_count = user_data.get("referral_count", 0) if user_data else 0
    saved_video_count = len(user_data.get("bookmarked_videos", [])) if user_data else 0
    video_views = user_history.get("views", 0) if user_history else 0

    return {
        "is_premium": is_premium,
        "active_tokens_count": active_tokens_count,
        "expires_at": expires_at,
        "referral_count": referral_count,
        "saved_video_count": saved_video_count,
        "video_views": video_views,
    }

async def update_premium_status(user_id: int, duration_days: int):
    expires_at = datetime.utcnow() + timedelta(days=duration_days)
    token_data = {
        "token_id": str(ObjectId()),
        "is_admin_granted": True,
        "granted_at": datetime.utcnow(),
        "expires_at": expires_at,
        "granted_by": "SubscriptionBot",
    }

    await tokens_collection.update_one(
        {"user_id": user_id},
        {"$push": {"tokens": token_data}},
        upsert=True
    )

    await users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"last_premium_check_status": True}},
        upsert=True
    )
    return expires_at

async def schedule_message_deletion(chat_id: int, message_id: int, delay: int):
    await asyncio.sleep(delay)
    try:
        await app.delete_messages(chat_id, message_id)
    except Exception as e:
        logger.error(f"Failed to delete message {message_id}: {e}")

# --- Command Handlers ---
@app.on_message(filters.command("ping") & filters.private)
async def ping_command(client: Client, message: types.Message):
    await message.reply_text("Pong!")

@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: types.Message):
    user_id = message.from_user.id
    logger.info(f"Start command from {user_id}")

    # Ensure user exists
    if not await users_collection.find_one({"user_id": user_id}):
        await users_collection.insert_one({
            "user_id": user_id,
            "first_name": message.from_user.first_name,
            "referral_count": 0,
            "bookmarked_videos": [],
            "created_at": datetime.utcnow()
        })

    user_stats = await get_user_stats(user_id)

    status_text = "Free User"
    if user_stats["is_premium"]:
        status_text = f"Premium User (Expires: {user_stats['expires_at']})"

    response_text = (
        f"👋 Hello {message.from_user.first_name}!\n\n"
        f"📊 **Your Stats:**\n"
        f"  - Status: {status_text}\n"
        f"  - Active Premium Tokens: {user_stats['active_tokens_count']}\n"
        f"  - Referrals: {user_stats['referral_count']}\n"
        f"  - Saved Videos: {user_stats['saved_video_count']}\n"
        f"  - Total Video Views: {user_stats['video_views']}\n\n"
        "✨ **Unlock Premium Access!**\n"
        "Choose a plan below to get started. After payment, reply with your Transaction ID."
    )

    keyboard = types.InlineKeyboardMarkup([
        [
            types.InlineKeyboardButton("🗓️ Weekly (₹49)", callback_data="pay_weekly"),
            types.InlineKeyboardButton("🗓️ Monthly (₹149)", callback_data="pay_monthly")
        ]
    ])

    await message.reply_text(response_text, reply_markup=keyboard, parse_mode="markdown")

async def send_payment_info(client: Client, message: types.Message, plan_type: str):
    plan = BotConfig.SUBSCRIPTION_PLANS.get(plan_type)
    if not plan:
        await message.reply_text("Invalid plan selected.")
        return

    caption = (
        f"💸 **Payment Instructions for {plan_type.capitalize()} Plan (₹{plan['amount']}):**\n\n"
        f"1. Click the UPI link or scan the QR code.\n"
        f"2. Pay exactly ₹{plan['amount']}.\n"
        f"3. Reply to this message with your **Transaction ID**.\n\n"
        f"📎 UPI Link: `{BotConfig.UPI_LINK}`\n\n"
        "⚠️ This message will auto-delete in 10 minutes."
    )

    sent = await client.send_photo(
        chat_id=message.chat.id,
        photo=BotConfig.QR_CODE_IMAGE_URL,
        caption=caption,
        parse_mode="markdown"
    )

    asyncio.create_task(schedule_message_deletion(
        message.chat.id, sent.id, BotConfig.PAYMENT_MESSAGE_DELETE_DELAY
    ))

@app.on_callback_query(filters.regex("pay_weekly"))
async def pay_weekly(client: Client, callback_query: types.CallbackQuery):
    await callback_query.answer("Weekly plan selected.")
    await send_payment_info(client, callback_query.message, "weekly")

@app.on_callback_query(filters.regex("pay_monthly"))
async def pay_monthly(client: Client, callback_query: types.CallbackQuery):
    await callback_query.answer("Monthly plan selected.")
    await send_payment_info(client, callback_query.message, "monthly")

@app.on_message(filters.private & filters.regex(r'^\d{10,20}$'))
async def handle_txn_id(client: Client, message: types.Message):
    user_id = message.from_user.id
    txn_id = message.text.strip()

    now = datetime.utcnow()
    one_day_ago = now - timedelta(days=1)

    txn = await confirmed_upi_txns_collection.find_one({
        "txn_id": txn_id,
        "timestamp": {"$gte": one_day_ago},
        "$or": [{"used_by_user_id": None}, {"used_by_user_id": {"$exists": False}}]
    })

    if not txn:
        await message.reply_text("❌ Transaction not found or already used.")
        return

    matched_plan = next(
        (k for k, v in BotConfig.SUBSCRIPTION_PLANS.items() if v["amount"] == txn["amount"]),
        None
    )

    if not matched_plan:
        await message.reply_text("❌ Amount mismatch with available plans.")
        return

    expires_at = await update_premium_status(user_id, BotConfig.SUBSCRIPTION_PLANS[matched_plan]["duration_days"])
    await confirmed_upi_txns_collection.update_one(
        {"_id": txn["_id"]},
        {"$set": {"used_by_user_id": user_id, "used_at": now, "status": "used"}}
    )

    await message.reply_text(
        f"🎉 Premium Activated!\nPlan: {matched_plan.capitalize()}\nExpires: `{expires_at.strftime('%Y-%m-%d %H:%M UTC')}`"
    )

@app.on_message(filters.chat(BotConfig.TXN_GROUP_ID) & filters.text)
async def process_group_message(client: Client, message: types.Message):
    text = message.text
    txn_id = None
    amount = None

    txn_patterns = [r'\b(?:TxnId|UTR|Ref|Transaction ID)[:\s]*([0-9]{10,20})']
    amount_patterns = [r'(?:₹|INR|Rs)\s?(\d+(?:\.\d{1,2})?)']

    for pattern in txn_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            txn_id = match.group(1)
            break

    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount = float(match.group(1))
            break

    if txn_id and amount:
        existing = await confirmed_upi_txns_collection.find_one({"txn_id": txn_id})
        if not existing:
            await confirmed_upi_txns_collection.insert_one({
                "txn_id": txn_id,
                "amount": amount,
                "timestamp": datetime.utcnow(),
                "original_message": text,
                "used_by_user_id": None,
                "used_at": None,
                "status": "confirmed"
            })

# --- Main ---
async def main_subscription_bot_logic():
    await db.command("ping")
    logger.info("MongoDB connected.")

    db.confirmed_upi_txns.create_index("txn_id", unique=True)
    db.users.create_index("user_id", unique=True)
    db.tokens.create_index("user_id", unique=True)
    db.history.create_index("user_id", unique=True)

    await app.start()
    logger.info("Bot started.")
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        app.run(main_subscription_bot_logic())
    except KeyboardInterrupt:
        logger.info("Bot stopped.")
