import os
import re
import asyncio
from datetime import datetime, timedelta
import logging # Import logging

from pyrogram import Client, filters, types
from motor.motor_asyncio import AsyncIOMotorClient
from bson.objectid import ObjectId # For potential future use with _id if needed

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Bot Configuration Class ---
# This class holds all the essential configuration details for your bot.
# IMPORTANT: Replace placeholder values with your actual credentials and IDs.
class BotConfig:
    # Your Telegram Bot Token obtained from @BotFather
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "7673807124:AAETa1Bty4C4CU0De1PuP31FwMXLmgPwQLk")

    # Your Telegram API ID and API Hash obtained from my.telegram.org
    API_ID = int(os.environ.get("API_ID", 29800015)) # Replace with your API ID
    API_HASH = os.environ.get("API_HASH", "c8f37108be31ab9ea2818bfe533fbb6f")

    # MongoDB Connection String
    # Example: "mongodb://localhost:27017/" or "mongodb+srv://user:pass@cluster.mongodb.net/dbname?retryWrites=true&w=majority"
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://Pyasipriya:00pEcao9sYhNC5VQ@cluster0.2dfenf7.mongodb.net/spicybot?retryWrites=true&w=majority&appName=Cluster0")
    MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "spicybot") # Shared with File-Sharing Bot

    # UPI Payment Details
    # This should ideally be a business UPI link or a payment gateway link for privacy.
    UPI_LINK = os.environ.get("UPI_LINK", "upi://pay?pa=you@upi&pn=YourName&mc=0000&tid=00000000000000&tr=YourRef&am=1.00")
    # Optional: URL to a QR code image. If not provided, only text instructions will be sent.
    QR_CODE_IMAGE_URL = os.environ.get("QR_CODE_IMAGE_URL", "https://placehold.co/300x300/000000/FFFFFF?text=Scan+QR")

    # The ID of the private Telegram group where UPI SMS notifications are forwarded.
    # The bot must be an admin in this group with read message permissions.
    TXN_GROUP_ID = int(os.environ.get("TXN_GROUP_ID", -1001234567890)) # Replace with your actual group ID

    # Subscription Plans: Maps plan type to (amount_in_rupees, duration_in_days)
    SUBSCRIPTION_PLANS = {
        "weekly": {"amount": 49, "duration_days": 7},
        "monthly": {"amount": 149, "duration_days": 30},
    }

    # Message deletion delay in seconds for payment info messages
    PAYMENT_MESSAGE_DELETE_DELAY = 600 # 10 minutes

# --- MongoDB Connection Setup ---
# Initialize the MongoDB client and select the database.
mongo_client = AsyncIOMotorClient(BotConfig.MONGO_URI)
db = mongo_client[BotConfig.MONGO_DB_NAME]

# Collections (shared with File-Sharing Bot and new for this bot)
users_collection = db.users
tokens_collection = db.tokens
history_collection = db.history # For user stats (e.g., video views)
confirmed_upi_txns_collection = db.confirmed_upi_txns # New for this bot

# --- Pyrogram Client Initialization ---
# Create the Pyrogram client instance.
app = Client(
    "SubscriptionBot",
    api_id=BotConfig.API_ID,
    api_hash=BotConfig.API_HASH,
    bot_token=BotConfig.BOT_TOKEN
)

# --- Helper Functions ---

async def get_user_stats(user_id: int):
    """
    Fetches comprehensive statistics for a given user from MongoDB.
    Includes premium status, active tokens, referral count, saved video count, and video views.
    """
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
            # Find the latest expiry date among active tokens
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
    """
    Grants premium access to a user by adding a new token and updating their status.
    This mimics the /addtoken command of the File-Sharing Bot.
    """
    expires_at = datetime.utcnow() + timedelta(days=duration_days)
    token_data = {
        "token_id": str(ObjectId()), # Unique ID for this token
        "is_admin_granted": True,
        "granted_at": datetime.utcnow(),
        "expires_at": expires_at,
        "granted_by": "SubscriptionBot", # Indicate source of the token
    }

    # Atomically update the tokens collection
    await tokens_collection.update_one(
        {"user_id": user_id},
        {"$push": {"tokens": token_data}},
        upsert=True
    )

    # Update user's last_premium_check_status in the users collection
    await users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"last_premium_check_status": True}},
        upsert=True
    )
    return expires_at

async def schedule_message_deletion(chat_id: int, message_id: int, delay: int):
    """
    Schedules the deletion of a specific message after a given delay.
    Used for sensitive payment information.
    """
    await asyncio.sleep(delay)
    try:
        await app.delete_messages(chat_id, message_id)
        logger.info(f"Deleted message {message_id} in chat {chat_id} after {delay} seconds.")
    except Exception as e:
        logger.error(f"Could not delete message {message_id} in chat {chat_id}: {e}")

# --- Handlers for User Interaction (Private Chat) ---

@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: types.Message):
    """
    Handles the /start command. Displays user stats and subscription options.
    """
    user_id = message.from_user.id
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
    """
    Sends payment instructions to the user, including UPI link and optional QR code.
    Schedules the message for auto-deletion.
    """
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
        # Schedule deletion of the payment message
        asyncio.create_task(
            schedule_message_deletion(
                message.chat.id, sent_message.id, BotConfig.PAYMENT_MESSAGE_DELETE_DELAY
            )
        )

@app.on_callback_query(filters.regex("pay_weekly"))
async def pay_weekly_callback(client: Client, callback_query: types.CallbackQuery):
    """
    Handles the 'pay_weekly' inline keyboard callback.
    """
    await callback_query.answer("You selected Weekly Plan. Sending payment details...")
    await send_payment_info(client, callback_query.message, "weekly")

@app.on_callback_query(filters.regex("pay_monthly"))
async def pay_monthly_callback(client: Client, callback_query: types.CallbackQuery):
    """
    Handles the 'pay_monthly' inline keyboard callback.
    """
    await callback_query.answer("You selected Monthly Plan. Sending payment details...")
    await send_payment_info(client, callback_query.message, "monthly")

@app.on_message(filters.private & filters.regex(r'^\d{10,20}$'))
async def handle_txn_id(client: Client, message: types.Message):
    """
    Handles messages that are potential UPI Transaction IDs from users.
    Verifies the transaction against confirmed payments and grants premium.
    """
    user_id = message.from_user.id
    txn_id = message.text.strip()
    logger.info(f"User {user_id} sent potential TXN ID: {txn_id}")

    await message.reply_chat_action("typing")

    # Search for the transaction in the confirmed_upi_txns collection
    # - Match txn_id
    # - Ensure it's recent (e.g., within last 24 hours)
    # - Ensure it hasn't been used by another user
    now = datetime.utcnow()
    one_day_ago = now - timedelta(days=1)

    confirmed_txn = await confirmed_upi_txns_collection.find_one({
        "txn_id": txn_id,
        "timestamp": {"$gte": one_day_ago},
        "$or": [
            {"used_by_user_id": {"$exists": False}}, # Not used yet
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

    # Validate the amount against subscription plans
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
        # Optionally, mark this transaction as 'invalid_amount' to prevent future checks
        await confirmed_upi_txns_collection.update_one(
            {"_id": confirmed_txn["_id"]},
            {"$set": {"status": "amount_mismatch", "checked_at": now}}
        )
        return

    # Grant premium access
    plan_details = BotConfig.SUBSCRIPTION_PLANS[matched_plan]
    expires_at = await update_premium_status(user_id, plan_details["duration_days"])

    # Mark the transaction as used
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
    """
    Listens to messages in the configured TXN_GROUP_ID, parses UPI SMS notifications,
    and stores confirmed transactions in MongoDB.
    """
    text = message.text
    logger.info(f"Received message in TXN Group {BotConfig.TXN_GROUP_ID}: {text[:100]}...") # Log first 100 chars

    txn_id = None
    amount = None

    # Regex to extract Transaction ID (TxnId, UPI Ref No, UTR, Ref. No. etc.)
    txn_id_patterns = [
        r'(?:TxnId|UPI Ref No|UTR|Ref\. No\.|TrnId|Ref No|Transaction ID|Txn Id)\D*(\d{10,20})',
        r'(\d{10,20})\s+is\s+the\s+UPI\s+transaction\s+ID', # Common pattern
        r'UPI\s+Ref\s+No\.\s*[:\s]*(\d{10,20})',
        r'Transaction\s+ID\s*[:\s]*(\d{10,20})',
        r'UTR\s*[:\s]*(\d{10,20})',
        r'Ref\s*[:\s]*(\d{10,20})',
    ]

    # Regex to extract Amount (Rs., INR, ₹)
    amount_patterns = [
        r'(?:Rs|INR|₹)\s*(\d+(?:\.\d{1,2})?)', # Matches Rs 100 or Rs 100.50
        r'(\d+(?:\.\d{1,2})?)\s*(?:Rs|INR|₹)',
        r'amount\s*[:\s]*(\d+(?:\.\d{1,2})?)',
    ]

    # Try to find Transaction ID
    for pattern in txn_id_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            txn_id = match.group(1)
            break

    # Try to find Amount
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                amount = float(match.group(1))
                # Convert to integer if it's a whole number, as UPI amounts are often whole.
                # Or keep as float for more precision. For this bot, we expect whole numbers.
                if amount.is_integer():
                    amount = int(amount)
                break
            except ValueError:
                amount = None # Keep amount as None if conversion fails

    if txn_id and amount is not None:
        # Check for duplicate transaction ID to avoid reprocessing same SMS
        existing_txn = await confirmed_upi_txns_collection.find_one({"txn_id": txn_id})
        if existing_txn:
            logger.info(f"Duplicate TXN ID '{txn_id}' received. Skipping storage.")
            return

        # Store the confirmed transaction in MongoDB
        transaction_data = {
            "txn_id": txn_id,
            "amount": amount,
            "timestamp": datetime.utcnow(), # Store in UTC
            "original_message": text,
            "used_by_user_id": None, # Will be filled when a user claims it
            "used_at": None,
            "status": "confirmed" # Initial status
        }
        await confirmed_upi_txns_collection.insert_one(transaction_data)
        logger.info(f"Stored confirmed UPI transaction: TXN ID={txn_id}, Amount={amount}")
    else:
        logger.info(f"Could not parse TXN ID or Amount from message: {text}")

async def main_subscription_bot_logic():
    """
    Main function to start the subscription bot and ensure database indexes.
    This function will be run once by app.run().
    """
    logger.info("Starting Subscription Bot and ensuring MongoDB indexes...")
    
    # Ensure MongoDB indexes for faster lookups
    try:
        # Attempt to drop the old 'id_1' index if it exists from previous runs
        # This is a safe operation within a try-except block
        db.users.drop_index("id_1")
        logger.info("Dropped old 'id_1' index on users collection.")
    except Exception as e:
        logger.info(f"Could not drop 'id_1' index (might not exist or different name): {e}")

    # Index for txn_id for quick lookup
    db.confirmed_upi_txns.create_index("txn_id", unique=True)
    # Index for timestamp to filter recent transactions
    db.confirmed_upi_txns.create_index("timestamp")
    # Index for used_by_user_id to check if a transaction is claimed
    db.confirmed_upi_txns.create_index("used_by_user_id")
    
    # Index for user ID in users and tokens collection (now consistent with main bot)
    db.users.create_index("user_id", unique=True)
    db.tokens.create_index("user_id", unique=True)
    db.history.create_index("user_id", unique=True)

    logger.info("MongoDB indexes ensured.")

    # Start the Pyrogram client
    await app.start()
    logger.info("Subscription Bot has connected to Telegram.")

    # Keep the bot alive indefinitely
    await asyncio.Event().wait()


if __name__ == "__main__":
    logger.info("Script started. Entering main execution block for Subscription Bot.")
    try:
        # Pyrogram's app.run() is a blocking call that starts the bot and
        # runs the provided coroutine (main_subscription_bot_logic) within its own event loop.
        # It then handles long polling internally.
        app.run(main_subscription_bot_logic())
    except KeyboardInterrupt:
        logger.info("Subscription Bot stopped by KeyboardInterrupt (Ctrl+C). Shutting down...")
        # Pyrogram's app.run() usually handles app.stop() on Ctrl+C.
        # Ensure any custom cleanup is performed here if needed outside app.stop().
    except Exception as e:
        logger.critical(f"An unhandled error occurred during bot startup or main execution: {e}", exc_info=True)
    finally:
        logger.info("Subscription Bot application exiting.")

