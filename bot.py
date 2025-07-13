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
    level=logging.DEBUG, # Changed to DEBUG for more detailed logs
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

    # Add an ADMIN_IDS list for debugging and future admin commands
    ADMIN_IDS = [6612030110] # Replace with your actual Telegram User ID (integer)

# --- MongoDB Connection Setup ---
mongo_client = AsyncIOMotorClient(BotConfig.MONGO_URI)
db = mongo_client[BotConfig.MONGO_DB_NAME]

users_collection = db.users
tokens_collection = db.tokens
history_collection = db.history
confirmed_upi_txns_collection = db.confirmed_upi_txns

# --- Pyrogram Client Initialization ---
app = Client(
    "SubscriptionBot",
    api_id=BotConfig.API_ID,
    api_hash=BotConfig.API_HASH,
    bot_token=BotConfig.BOT_TOKEN
)

# --- Helper Functions (unchanged, for brevity) ---
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
        logger.info(f"Deleted message {message_id} in chat {chat_id} after {delay} seconds.")
    except Exception as e:
        logger.error(f"Could not delete message {message_id} in chat {chat_id}: {e}")

# --- Handlers for User Interaction (Private Chat) ---

# NEW: Simple /ping command for testing responsiveness
@app.on_message(filters.command("ping") & filters.private)
async def ping_command(client: Client, message: types.Message):
    """Responds to /ping with 'Pong!' to check bot's responsiveness."""
    logger.info(f"Received /ping command from user {message.from_user.id}")
    await message.reply_text("Pong!")

@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: types.Message):
    user_id = message.from_user.id
    logger.info(f"Received /start command from user {user_id}") # Added logging
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
            types.InlineKeyboardButton(
                "🗓️ Weekly (₹49)", callback_data="pay_weekly"
            ),
            types.InlineKeyboardButton(
                "🗓️ Monthly (₹149)", callback_data="pay_monthly"
            )
        ]
    ])
    await message.reply_text(response_text, reply_markup=keyboard, parse_mode="markdown")

async def send_payment_info(client: Client, message: types.Message, plan_type: str):
    plan_details = BotConfig.SUBSCRIPTION_PLANS.get(plan_type)
    if not plan_details:
        await message.reply_text("Invalid subscription plan selected. Please try again.")
        return

    amount = plan_details["amount"]
    payment_instructions = (
        f"💰 **Payment Instructions for {plan_type.capitalize()} Plan (₹{amount}):**\n\n"
        f"1. Click the UPI link below or scan the QR code (if provided).\n"
        f"2. Pay exactly **₹{amount}**.\n"
        f"3. **IMPORTANT:** After successful payment, reply to *this message* with only your **Transaction ID** (10-20 digits long).\n\n"
        f"🔗 **UPI Link:** `{BotConfig.UPI_LINK}`\n\n"
        "This message will self-destruct in 10 minutes for your privacy."
    )

    sent_message = None
    if BotConfig.QR_CODE_IMAGE_URL and BotConfig.QR_CODE_IMAGE_URL.startswith("http"):
        try:
            sent_message = await client.send_photo(
                chat_id=message.chat.id,
                photo=BotConfig.QR_CODE_IMAGE_URL,
                caption=payment_instructions,
                parse_mode="markdown"
            )
        except Exception as e:
            logger.error(f"Error sending QR code image: {e}. Sending text only.")
            sent_message = await message.reply_text(payment_instructions, parse_mode="markdown")
    else:
        sent_message = await message.reply_text(payment_instructions, parse_mode="markdown")

    if sent_message:
        asyncio.create_task(
            schedule_message_deletion(
                message.chat.id, sent_message.id, BotConfig.PAYMENT_MESSAGE_DELETE_DELAY
            )
        )

@app.on_callback_query(filters.regex("pay_weekly"))
async def pay_weekly_callback(client: Client, callback_query: types.CallbackQuery):
    logger.info(f"Received pay_weekly callback from user {callback_query.from_user.id}") # Added logging
    await callback_query.answer("You selected Weekly Plan. Sending payment details...")
    await send_payment_info(client, callback_query.message, "weekly")

@app.on_callback_query(filters.regex("pay_monthly"))
async def pay_monthly_callback(client: Client, callback_query: types.CallbackQuery):
    logger.info(f"Received pay_monthly callback from user {callback_query.from_user.id}") # Added logging
    await callback_query.answer("You selected Monthly Plan. Sending payment details...")
    await send_payment_info(client, callback_query.message, "monthly")

@app.on_message(filters.private & filters.regex(r'^\d{10,20}$'))
async def handle_txn_id(client: Client, message: types.Message):
    user_id = message.from_user.id
    txn_id = message.text.strip()
    logger.info(f"User {user_id} sent potential TXN ID: {txn_id}")

    await message.reply_chat_action("typing")

    now = datetime.utcnow()
    one_day_ago = now - timedelta(days=1)

    confirmed_txn = await confirmed_upi_txns_collection.find_one({
        "txn_id": txn_id,
        "timestamp": {"$gte": one_day_ago},
        "$or": [
            {"used_by_user_id": {"$exists": False}},
            {"used_by_user_id": None}
        ]
    })

    if not confirmed_txn:
        await message.reply_text(
            "❌ **Payment not found or already used!**\n\n"
            "Please ensure:\n"
            "1. You have completed the payment.\n"
            "2. You are entering the correct Transaction ID.\n"
            "3. The payment was made recently (within the last 24 hours).\n"
            "If you believe this is an error, please contact support."
        )
        return

    matched_plan = None
    for plan_type, details in BotConfig.SUBSCRIPTION_PLANS.items():
        if confirmed_txn.get("amount") == details["amount"]:
            matched_plan = plan_type
            break

    if not matched_plan:
        await message.reply_text(
            f"❌ **Payment amount mismatch!**\n\n"
            f"The amount detected for TXN ID `{txn_id}` is ₹{confirmed_txn.get('amount', 'N/A')}. "
            f"Please ensure you pay either ₹{BotConfig.SUBSCRIPTION_PLANS['weekly']['amount']} (Weekly) "
            f"or ₹{BotConfig.SUBSCRIPTION_PLANS['monthly']['amount']} (Monthly)."
        )
        await confirmed_upi_txns_collection.update_one(
            {"_id": confirmed_txn["_id"]},
            {"$set": {"status": "amount_mismatch", "checked_at": now}}
        )
        return

    plan_details = BotConfig.SUBSCRIPTION_PLANS[matched_plan]
    expires_at = await update_premium_status(user_id, plan_details["duration_days"])

    await confirmed_upi_txns_collection.update_one(
        {"_id": confirmed_txn["_id"]},
        {"$set": {"used_by_user_id": user_id, "used_at": now, "status": "used"}}
    )

    await message.reply_text(
        f"🎉 **Congratulations! Your premium access has been activated!**\n\n"
        f"Plan: **{matched_plan.capitalize()}**\n"
        f"Duration: **{plan_details['duration_days']} days**\n"
        f"Expires On: `{expires_at.strftime('%Y-%m-%d %H:%M UTC')}`\n\n"
        "Enjoy your premium features!"
    )
    logger.info(f"User {user_id} successfully granted {matched_plan} premium with TXN ID: {txn_id}")


# --- Handler for Payment Confirmation (Group Chat Listener) ---

@app.on_message(filters.chat(BotConfig.TXN_GROUP_ID) & filters.text)
async def process_group_message(client: Client, message: types.Message):
    text = message.text
    logger.info(f"Received message in TXN Group {BotConfig.TXN_GROUP_ID}: {text[:100]}...")

    txn_id = None
    amount = None

    txn_id_patterns = [
        r'(?:TxnId|UPI Ref No|UTR|Ref\. No\.|TrnId|Ref No|Transaction ID|Txn Id)\D*(\d{10,20})',
        r'(\d{10,20})\s+is\s+the\s+UPI\s+transaction\s+ID',
        r'UPI\s+Ref\s+No\.\s*[:\s]*(\d{10,20})',
        r'Transaction\s+ID\s*[:\s]*(\d{10,20})',
        r'UTR\s*[:\s]*(\d{10,20})',
        r'Ref\s*[:\s]*(\d{10,20})',
    ]

    amount_patterns = [
        r'(?:Rs|INR|₹)\s*(\d+(?:\.\d{1,2})?)',
        r'(\d+(?:\.\d{1,2})?)\s*(?:Rs|INR|₹)',
        r'amount\s*[:\s]*(\d+(?:\.\d{1,2})?)',
    ]

    for pattern in txn_id_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            txn_id = match.group(1)
            break

    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                amount = float(match.group(1))
                if amount.is_integer():
                    amount = int(amount)
                break
            except ValueError:
                amount = None

    if txn_id and amount is not None:
        existing_txn = await confirmed_upi_txns_collection.find_one({"txn_id": txn_id})
        if existing_txn:
            logger.info(f"Duplicate TXN ID '{txn_id}' received. Skipping storage.")
            return

        transaction_data = {
            "txn_id": txn_id,
            "amount": amount,
            "timestamp": datetime.utcnow(),
            "original_message": text,
            "used_by_user_id": None,
            "used_at": None,
            "status": "confirmed"
        }
        await confirmed_upi_txns_collection.insert_one(transaction_data)
        logger.info(f"Stored confirmed UPI transaction: TXN ID={txn_id}, Amount={amount}")
    else:
        logger.info(f"Could not parse TXN ID or Amount from message: {text}")

async def main_subscription_bot_logic():
    logger.info("Starting Subscription Bot and ensuring MongoDB indexes...")
    
    try:
        db.users.drop_index("id_1")
        logger.info("Dropped old 'id_1' index on users collection.")
    except Exception as e:
        logger.info(f"Could not drop 'id_1' index (might not exist or different name): {e}")

    db.confirmed_upi_txns.create_index("txn_id", unique=True)
    db.confirmed_upi_txns.create_index("timestamp")
    db.confirmed_upi_txns.create_index("used_by_user_id")
    
    db.users.create_index("user_id", unique=True)
    db.tokens.create_index("user_id", unique=True)
    db.history.create_index("user_id", unique=True)

    logger.info("MongoDB indexes ensured.")

    await app.start()
    logger.info("Subscription Bot has connected to Telegram.")

    # Keep the bot alive indefinitely
    await asyncio.Event().wait()


if __name__ == "__main__":
    logger.info("Script started. Entering main execution block for Subscription Bot.")
    try:
        app.run(main_subscription_bot_logic())
    except KeyboardInterrupt:
        logger.info("Subscription Bot stopped by KeyboardInterrupt (Ctrl+C). Shutting down...")
    except Exception as e:
        logger.critical(f"An unhandled error occurred during bot startup or main execution: {e}", exc_info=True)
    finally:
        logger.info("Subscription Bot application exiting.")

