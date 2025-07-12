import os
import logging
from datetime import datetime, timedelta
import pytz
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler, # Import CallbackQueryHandler
    filters,
    ContextTypes,
)
import uuid
import re
import asyncio # Import asyncio for scheduling tasks

# --- Configuration ---
class BotConfig:
    # Your Subscription Bot's Token (from BotFather for this bot)
    BOT_TOKEN = '7673807124:AAETa1Bty4C4CU0De1PuP31FwMXLmgPwQLk' # REPLACE WITH YOUR SUBSCRIPTION BOT'S TOKEN

    # Your MongoDB URI (MUST be the SAME as your File-Sharing Bot's MONGO_URI)
    MONGO_URI = 'mongodb+srv://Pyasipriya:00pEcao9sYhNC5VQ@cluster0.2dfenf7.mongodb.net/spicybot?retryWrites=true&w=majority&appName=Cluster0' # REPLACE WITH YOUR ACTUAL MONGO_URI

    # MongoDB Database and Collection Names (MUST be the SAME as your File-Sharing Bot)
    MONGO_DB_NAME = "spicybot"
    USERS_COLLECTION_NAME = "users"
    TOKENS_COLLECTION_NAME = "tokens"
    CONFIRMED_TXN_COLLECTION_NAME = "confirmed_upi_txns" # New collection to store confirmed UPI transactions

    # UPI Link and QR Code Image URL
    UPI_LINK = "upi://pay?pa=kanhaiyalal-49@ptaxis&pn=Kanhaiya&am=99&cu=INR" # REPLACE with your actual UPI link
    QR_CODE_IMAGE_URL = "https://i.postimg.cc/28W3hCmz/Image.jpg" # REPLACE with your actual QR code image URL

    # ID of the Telegram Group where UPI SMS notifications are forwarded
    # The bot MUST be an admin in this group with 'Read All Messages' permission.
    TXN_GROUP_ID = -1002123456789 # REPLACE WITH YOUR ACTUAL UPI SMS FORWARDING GROUP CHAT ID (e.g., -100xxxxxxxxxx)

    # Define subscription plans and their corresponding durations in days
    SUBSCRIPTION_PLANS = {
        49.0: 7,   # ₹49 for 7 days (Weekly)
        149.0: 30  # ₹149 for 30 days (Monthly)
    }

    FREE_USER_SAVE_LIMIT = 100 # Max saved videos for free users (from your file-sharing bot)

try:
    config = BotConfig()
    if not all([config.BOT_TOKEN, config.MONGO_URI, config.TXN_GROUP_ID]):
        raise ValueError("One or more essential configuration variables are not set. Please check BOT_TOKEN, MONGO_URI, TXN_GROUP_ID.")
except Exception as e:
    raise RuntimeError(f"Failed to load bot configuration: {e}")

# --- Logging Setup ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- MongoDB Setup ---
client = None
db = None
users_collection = None
tokens_collection = None
confirmed_txn_collection = None # New collection instance

try:
    client = MongoClient(config.MONGO_URI)
    db = client[config.MONGO_DB_NAME]
    users_collection = db[config.USERS_COLLECTION_NAME]
    tokens_collection = db[config.TOKENS_COLLECTION_NAME]
    confirmed_txn_collection = db[config.CONFIRMED_TXN_COLLECTION_NAME]
    
    # Create index on txn_id for faster lookups
    confirmed_txn_collection.create_index([("txn_id", 1)], unique=True)
    
    logger.info(f"MongoDB connected successfully to DB: {config.MONGO_DB_NAME}")
    logger.info(f"Using collections: {config.USERS_COLLECTION_NAME}, {config.TOKENS_COLLECTION_NAME}, {config.CONFIRMED_TXN_COLLECTION_NAME}")
except Exception as e:
    logger.critical(f"Error connecting to MongoDB: {e}", exc_info=True)
    client = None # Ensure client is None if connection fails

# --- GLOBAL SET FOR TRACKING ASYNC TASKS ---
active_tasks = set()

def create_tracked_task(coro):
    """
    Creates an asyncio task, adds it to the global active_tasks set,
    and removes it when it finishes (successfully or with an exception).
    """
    task = asyncio.create_task(coro)
    active_tasks.add(task)
    task.add_done_callback(active_tasks.discard)
    logger.debug(f"Task {task.get_name()} created and tracked. Total active tasks: {len(active_tasks)}")
    return task

# --- Helper Functions ---

def get_ist_now():
    """Returns the current time in IST timezone."""
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist)

def is_premium_user(user_id: int) -> bool:
    """Checks if a user is a premium user (has an active admin-granted token)."""
    now = datetime.utcnow()
    doc = tokens_collection.find_one({'user_id': user_id})
    if not doc or 'tokens' not in doc:
        return False
    
    for token in doc['tokens']:
        # Premium status is tied to tokens explicitly granted by an admin
        if token.get('is_admin_granted', False) and token.get('expires_at') and token['expires_at'] > now:
            return True
    return False

def get_user_stats(user_id: int) -> dict:
    """Fetches user statistics from MongoDB."""
    user_data = users_collection.find_one({'user_id': user_id})
    tokens_doc = tokens_collection.find_one({'user_id': user_id})

    tokens_count = 0
    if tokens_doc and 'tokens' in tokens_doc:
        now = datetime.utcnow()
        tokens_count = sum(1 for token in tokens_doc['tokens'] if token.get('expires_at') and token['expires_at'] > now)

    referral_count = user_data.get('referral_count', 0) if user_data else 0
    bookmarked_videos = user_data.get('bookmarked_videos', []) if user_data else []
    
    is_premium = is_premium_user(user_id)
    user_status = "Premium User 💎" if is_premium else "Free User ✨"
    
    if is_premium:
        save_limit_display = f"{len(bookmarked_videos)}/Unlimited"
    else:
        save_limit_display = f"{len(bookmarked_videos)}/{config.FREE_USER_SAVE_LIMIT}"

    # Assuming history_collection exists and stores views
    history_collection = db.get_collection('history') # Get collection dynamically
    views_doc = history_collection.find_one({'user_id': user_id})
    view_count = len(views_doc['history']) if views_doc and 'history' in views_doc else 0

    return {
        "is_premium": is_premium,
        "user_status": user_status,
        "tokens_count": tokens_count,
        "referral_count": referral_count,
        "saved_videos_count": save_limit_display,
        "view_count": view_count
    }

async def update_premium_status(user_id: int, username: str, duration_days: int):
    """
    Updates the user's premium status in MongoDB by adding an admin-granted token
    and updating their last_premium_check_status.
    """
    if not users_collection or not tokens_collection:
        logger.error("MongoDB collections not initialized. Cannot update premium status.")
        return False

    now_utc = datetime.utcnow()
    expires_at_utc = now_utc + timedelta(days=duration_days)

    # 1. Add/Update user document in 'users' collection
    user_doc_update = {
        'username': username,
        'first_name': username, # Assuming username is first_name if no actual username
        'last_premium_check_status': True, # Set to True as they are now premium
        'last_updated_by_sub_bot': get_ist_now().isoformat() # Track updates from this bot
    }
    
    existing_user = users_collection.find_one({'user_id': user_id})
    if not existing_user:
        user_doc_update['joined_date'] = now_utc
        user_doc_update['referral_count'] = 0
        user_doc_update['bookmarked_videos'] = []
        user_doc_update['last_viewed_per_category'] = {}
        user_doc_update['category_history'] = {}

    users_collection.update_one(
        {'user_id': user_id},
        {'$set': user_doc_update},
        upsert=True
    )
    logger.info(f"User document updated/created for {user_id} in 'users' collection.")

    # 2. Add an admin-granted token to the 'tokens' collection
    new_token = {
        'token_id': str(uuid.uuid4()),
        'created_at': now_utc,
        'expires_at': expires_at_utc,
        'is_admin_granted': True # This is the crucial flag for premium access
    }

    tokens_collection.update_one(
        {'user_id': user_id},
        {'$push': {'tokens': new_token}},
        upsert=True
    )
    logger.info(f"Premium token added for user {user_id} in 'tokens' collection, expires at {expires_at_utc} UTC.")

    ist = pytz.timezone('Asia/Kolkata')
    expires_at_ist = expires_at_utc.astimezone(ist)
    
    return expires_at_ist

async def schedule_message_deletion(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int, delay_seconds: int):
    """Schedules a message to be deleted after a specified delay."""
    try:
        await asyncio.sleep(delay_seconds)
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Message {message_id} in chat {chat_id} auto-deleted after {delay_seconds} seconds.")
    except Exception as e:
        logger.warning(f"Failed to auto-delete message {message_id} in chat {chat_id}: {e}")

# --- Telegram Bot Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message, user stats, and payment options."""
    user = update.effective_user
    username = user.username if user.username else user.first_name
    user_id = user.id

    # Fetch user stats
    stats = get_user_stats(user_id)

    message = (
        f"👋 Welcome, {username}! ✨\n\n"
        f"📊 <b>Your Current Stats:</b>\n"
        f"<b>Status:</b> {stats['user_status']}\n"
        f"<b>Tokens:</b> {stats['tokens_count']} 🪙\n"
        f"<b>Video Views:</b> {stats['view_count']} 🎞️\n"
        f"<b>Saved Videos:</b> {stats['saved_videos_count']} ❤️\n\n"
        "To unlock premium access and enjoy unlimited features, choose a plan below:"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗓️ Weekly (₹49)", callback_data="pay_weekly")],
        [InlineKeyboardButton("🗓️ Monthly (₹149)", callback_data="pay_monthly")]
    ])

    await update.message.reply_text(message, reply_markup=keyboard, parse_mode="HTML")
    logger.info(f"User {user_id} received start message with stats and payment options.")

async def send_payment_info(update: Update, context: ContextTypes.DEFAULT_TYPE, plan_type: str) -> None:
    """Sends the QR code and UPI link for the selected plan."""
    user = update.effective_user
    chat_id = update.effective_chat.id

    message_text = (
        f"To get your {plan_type} premium access, please pay:\n\n"
        f"🔗 {config.UPI_LINK}\n\n"
        "Once done, reply with just your **TXN ID number** (e.g., `516314312632`).\n\n"
        "<i>This message will self-delete in 10 minutes for your privacy.</i> ⏳"
    )

    sent_message = None
    if config.QR_CODE_IMAGE_URL:
        sent_message = await context.bot.send_photo(
            chat_id=chat_id,
            photo=config.QR_CODE_IMAGE_URL,
            caption=message_text,
            parse_mode="HTML"
        )
    else:
        sent_message = await context.bot.send_message(
            chat_id=chat_id,
            text=message_text,
            parse_mode="HTML"
        )
    
    if sent_message:
        # Schedule deletion of the payment info message
        create_tracked_task(schedule_message_deletion(context, chat_id, sent_message.message_id, 600)) # 600 seconds = 10 minutes
        logger.info(f"Payment info sent to user {user.id} for {plan_type} plan. Scheduled for deletion.")
    else:
        logger.error(f"Failed to send payment info message to user {user.id}.")
        await context.bot.send_message(chat_id, "❌ Failed to send payment details. Please try again.")

async def pay_weekly_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles 'Weekly' button click."""
    await update.callback_query.answer() # Acknowledge the callback
    await send_payment_info(update, context, "Weekly")
    logger.info(f"User {update.effective_user.id} clicked Weekly plan.")

async def pay_monthly_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles 'Monthly' button click."""
    await update.callback_query.answer() # Acknowledge the callback
    await send_payment_info(update, context, "Monthly")
    logger.info(f"User {update.effective_user.id} clicked Monthly plan.")


async def handle_txn_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles messages containing only the TXN ID number to process payments.
    Checks against the `confirmed_upi_txns` collection.
    """
    user = update.effective_user
    user_id = user.id
    username = user.username if user.username else user.first_name
    txn_id = update.message.text.strip() # Directly use the text as TXN ID

    logger.info(f"User {user_id} ({username}) sent TXN ID: {txn_id}")

    # --- Check against confirmed_upi_txns collection ---
    if not confirmed_txn_collection:
        await update.message.reply_text(
            "❌ Payment verification system is currently unavailable. Please try again later or contact support."
        )
        logger.error("Confirmed TXN collection not initialized. Cannot verify payments.")
        return

    confirmed_payment = confirmed_txn_collection.find_one({
        "txn_id": txn_id,
        "timestamp": {"$gt": datetime.utcnow() - timedelta(hours=24)}, # Only consider transactions from last 24 hours
        "status": "confirmed", # Assuming 'confirmed' status is set by the group message handler
        "used_by_user_id": {"$exists": False} # Ensure this TXN ID hasn't been used by another user
    })

    if not confirmed_payment:
        await update.message.reply_text(
            "❌ Invalid TXN ID, not found in our confirmed payments, or already used. Please double-check your TXN ID and try again."
        )
        logger.warning(f"TXN ID {txn_id} not found in confirmed_upi_txns or already used.")
        return

    amount = confirmed_payment["amount"]
    duration_days = config.SUBSCRIPTION_PLANS.get(amount)

    if not duration_days:
        await update.message.reply_text(
            "❌ Payment received, but the amount does not match any subscription plan. "
            "Please contact support if you believe this is an error."
        )
        logger.warning(f"TXN ID {txn_id} found, but amount {amount} does not match any plan.")
        return

    # --- Update MongoDB and mark transaction as used ---
    expires_at_ist = await update_premium_status(user_id, username, duration_days)

    if expires_at_ist:
        # Mark the transaction as used in the database
        confirmed_txn_collection.update_one(
            {"_id": confirmed_payment["_id"]},
            {"$set": {"used_by_user_id": user_id, "used_at": datetime.utcnow()}}
        )
        logger.info(f"TXN ID {txn_id} marked as used by user {user_id}.")

        await update.message.reply_text(
            f"Dear {username}, 🎉\n\n"
            f"✅ Your payment has been confirmed.\n"
            f"🗓️ Premium access granted for {duration_days} days!\n"
            f"Expires on: {expires_at_ist.strftime('%d %B %Y %H:%M %Z')}.\n\n"
            "You can now enjoy premium content with the File-Sharing Bot!"
        )
        logger.info(f"Premium access granted for user {user_id} for {duration_days} days.")
    else:
        await update.message.reply_text(
            "An error occurred while updating your premium status. Please try again later or contact support."
        )
        logger.error(f"Failed to update premium status for user {user_id}.")

# --- Handler: Listen to messages in the UPI TXN Group ---
async def chat_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Listens for messages in the configured TXN_GROUP_ID, parses them for UPI TXN IDs and amounts,
    and stores them in the confirmed_upi_txns collection.
    """
    message_text = update.message.text
    logger.info(f"Received message in TXN group {config.TXN_GROUP_ID}: {message_text}")

    # Regex to extract TXN ID and Amount from common UPI SMS formats
    # This regex is a starting point and might need adjustment based on your exact SMS format.
    # It looks for patterns like "TxnId: <ID>", "Txn ID: <ID>", "UPI Ref No: <ID>"
    # and amounts like "Rs. <AMOUNT>", "INR <AMOUNT>", "Rs<AMOUNT>"
    txn_id_match = re.search(r'(?:TxnId|Txn ID|UPI Ref No|Ref No|UTR|Transaction ID)[:\s]*([a-zA-Z0-9]{10,20})', message_text, re.IGNORECASE)
    amount_match = re.search(r'(?:Rs\.?|INR)\s*([\d,]+\.?\d{0,2})', message_text, re.IGNORECASE)

    if txn_id_match and amount_match:
        txn_id = txn_id_match.group(1).strip()
        amount_str = amount_match.group(1).replace(',', '').strip()
        try:
            amount = float(amount_str)
        except ValueError:
            logger.warning(f"Could not parse amount '{amount_str}' from TXN group message: {message_text}")
            return # Skip if amount is not a valid number

        logger.info(f"Parsed TXN ID: {txn_id}, Amount: {amount} from group message.")

        # Check if the TXN ID already exists to prevent duplicates
        if confirmed_txn_collection.find_one({"txn_id": txn_id}):
            logger.info(f"TXN ID {txn_id} already exists in confirmed_upi_txns. Skipping insertion.")
            return

        # Store the confirmed transaction in MongoDB
        try:
            confirmed_txn_collection.insert_one({
                "txn_id": txn_id,
                "amount": amount,
                "timestamp": datetime.utcnow(),
                "message_text": message_text, # Store original message for debugging
                "status": "confirmed" # Mark as confirmed
            })
            logger.info(f"Stored new confirmed TXN ID: {txn_id} with amount {amount}.")
        except Exception as e:
            logger.error(f"Error inserting confirmed TXN ID {txn_id} into DB: {e}", exc_info=True)
    else:
        logger.debug(f"No TXN ID or Amount found in group message: {message_text}")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a message to the user."""
    logger.error(f"Update {update} caused error {context.error}", exc_info=True)
    if update.effective_message:
        try:
            await update.effective_message.reply_text(
                "An unexpected error occurred. Please try again later."
            )
        except Exception as reply_e:
            logger.error(f"Failed to send error reply to user: {reply_e}")


def main() -> None:
    """Start the bot."""
    if not config.BOT_TOKEN:
        logger.critical("BOT_TOKEN environment variable not set. Exiting.")
        return

    application = Application.builder().token(config.BOT_TOKEN).build()

    # Register handlers for private chat with the user
    application.add_handler(CommandHandler("start", start_command))
    
    # Handler for TXN ID input (now expects only the number)
    # Filters for messages that are purely digits, 10 to 20 characters long
    application.add_handler(MessageHandler(filters.Regex(r'^\d{10,20}$') & filters.PRIVATE, handle_txn_id))

    # Register handlers for inline keyboard callbacks
    application.add_handler(CallbackQueryHandler(pay_weekly_callback, pattern="^pay_weekly$"))
    application.add_handler(CallbackQueryHandler(pay_monthly_callback, pattern="^pay_monthly$"))

    # Register handler for messages coming from the specific TXN group
    application.add_handler(MessageHandler(filters.Chat(config.TXN_GROUP_ID) & filters.TEXT & ~filters.COMMAND, chat_id_handler))

    application.add_error_handler(error_handler)

    logger.info("Bot started polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
    if client:
        client.close()
        logger.info("MongoDB connection closed.")

