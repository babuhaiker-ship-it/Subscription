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
    filters,
    ContextTypes,
)
import uuid # For generating token IDs

# --- Configuration ---
# Set your bot token and MongoDB URI as environment variables for security.
# Example:
# export BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
# export MONGO_URI="mongodb+srv://user:password@cluster.mongodb.net/dbname?retryWrites=true&w=majority"

BOT_TOKEN = os.environ.get("7673807124:AAETa1Bty4C4CU0De1PuP31FwMXLmgPwQLk")
# IMPORTANT: Use the exact MONGO_URI from your file-sharing bot's config.py
# Example from your file-sharing bot: 'mongodb+srv://Pyasipriya:00pEcao9sYhNC5VQ@cluster0.2dfenf7.mongodb.net/spicybot?retryWrites=true&w=majority&appName=Cluster0'
MONGO_URI = os.environ.get("MONGO_URI")
MONGO_DB_NAME = "spicybot"  # This MUST match your file-sharing bot's MONGO_DB_NAME
USERS_COLLECTION_NAME = "users" # This MUST match your file-sharing bot's users collection name
TOKENS_COLLECTION_NAME = "tokens" # This MUST match your file-sharing bot's tokens collection name

# UPI Link and QR Code (placeholders)
UPI_LINK = "kanhaiyalal-49@ptaxis"
QR_CODE_IMAGE_URL = "https://i.postimg.cc/28W3hCmz/Image.jpg" # Placeholder

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- MongoDB Setup ---
client = None
db = None
users_collection = None
tokens_collection = None

try:
    if MONGO_URI:
        client = MongoClient(MONGO_URI)
        db = client[MONGO_DB_NAME]
        users_collection = db[USERS_COLLECTION_NAME]
        tokens_collection = db[TOKENS_COLLECTION_NAME]
        logger.info(f"MongoDB connected successfully to DB: {MONGO_DB_NAME}, using collections: {USERS_COLLECTION_NAME}, {TOKENS_COLLECTION_NAME}")
    else:
        logger.error("MONGO_URI environment variable not set. MongoDB will not be used.")
except Exception as e:
    logger.critical(f"Error connecting to MongoDB: {e}", exc_info=True)
    client = None # Ensure client is None if connection fails

# --- Mock Payment Data (For Simulation) ---
# In a real scenario, this data would come from your UPI SMS forwarding system
# (e.g., parsed from SMS messages forwarded to a private Telegram group or a database).
MOCK_PAYMENTS = {
    "26486100001": {"amount": 49.0, "status": "paid"}, # 7 days
    "26486100002": {"amount": 149.0, "status": "paid"}, # 30 days
    "26486100003": {"amount": 49.0, "status": "paid"},
    "26486100004": {"amount": 149.0, "status": "paid"},
    # Add more mock TXN IDs as needed for testing
}

# --- Helper Functions ---

def get_ist_now():
    """Returns the current time in IST timezone."""
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist)

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
    # This ensures the user exists and their username/first_name is up-to-date
    user_doc_update = {
        'username': username,
        'first_name': username, # Assuming username is first_name if no actual username
        'last_premium_check_status': True, # Set to True as they are now premium
        'last_updated_by_sub_bot': get_ist_now().isoformat() # Track updates from this bot
    }
    
    # If user doesn't exist, set joined_date. If exists, just update.
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
    # This replicates the logic of your file-sharing bot's add_token for premium
    new_token = {
        'token_id': str(uuid.uuid4()),
        'created_at': now_utc,
        'expires_at': expires_at_utc,
        'is_admin_granted': True # This is the crucial flag for premium access
    }

    # Use $push to add the new token to the 'tokens' array, upserting if the document doesn't exist
    tokens_collection.update_one(
        {'user_id': user_id},
        {'$push': {'tokens': new_token}},
        upsert=True
    )
    logger.info(f"Premium token added for user {user_id} in 'tokens' collection, expires at {expires_at_utc} UTC.")

    # Convert UTC expiry to IST for display
    ist = pytz.timezone('Asia/Kolkata')
    expires_at_ist = expires_at_utc.astimezone(ist)
    
    return expires_at_ist

# --- Telegram Bot Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message and payment instructions."""
    user = update.effective_user
    username = user.username if user.username else user.first_name

    message = (
        f"Dear {username}, to unlock premium access please pay:\n\n"
        "📌 7 days: ₹49\n"
        "📌 1 month: ₹149\n\n"
        "Scan the QR or click the UPI link below 👇\n\n"
        f"🔗 {UPI_LINK}\n\n"
        "Once done, reply with: `TXN ID <your_transaction_id>`\n"
        "Example: `TXN ID 264861XXXXX`"
    )

    # Send QR code image (optional)
    if QR_CODE_IMAGE_URL:
        await update.message.reply_photo(photo=QR_CODE_IMAGE_URL, caption=message, parse_mode="Markdown")
    else:
        await update.message.reply_text(message, parse_mode="Markdown")

async def handle_txn_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles messages containing 'TXN ID' to process payments."""
    user = update.effective_user
    user_id = user.id
    username = user.username if user.username else user.first_name
    text = update.message.text.strip()

    if not text.lower().startswith("txn id"):
        return # Not a TXN ID message, ignore

    parts = text.split(" ")
    if len(parts) < 3:
        await update.message.reply_text(
            "Please provide the TXN ID in the format: `TXN ID <your_transaction_id>`",
            parse_mode="Markdown"
        )
        return

    txn_id = parts[2].strip()
    logger.info(f"User {user_id} ({username}) sent TXN ID: {txn_id}")

    # --- Simulate Payment Confirmation ---
    # In a real system, you would query your SMS forwarding database or API here.
    # For this example, we check against MOCK_PAYMENTS.
    payment_info = MOCK_PAYMENTS.get(txn_id)

    if not payment_info or payment_info["status"] != "paid":
        await update.message.reply_text(
            "❌ Invalid amount or TXN ID not found. Please double-check your TXN ID and try again."
        )
        logger.warning(f"TXN ID {txn_id} not found or not paid in mock data.")
        return

    amount = payment_info["amount"]
    duration_days = 0

    if amount == 49.0:
        duration_days = 7
    elif amount == 149.0:
        duration_days = 30
    else:
        await update.message.reply_text(
            "❌ Payment received, but the amount does not match any subscription plan. "
            "Please contact support if you believe this is an error."
        )
        logger.warning(f"TXN ID {txn_id} found, but amount {amount} is invalid.")
        return

    # --- Update MongoDB ---
    expires_at_ist = await update_premium_status(user_id, username, duration_days)

    if expires_at_ist:
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

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a message to the user."""
    logger.error(f"Update {update} caused error {context.error}")
    if update.effective_message:
        await update.effective_message.reply_text(
            "An unexpected error occurred. Please try again later."
        )

def main() -> None:
    """Start the bot."""
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN environment variable not set. Exiting.")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_txn_id))
    application.add_error_handler(error_handler)

    logger.info("Bot started polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
    # Close MongoDB connection when the application stops
    if client:
        client.close()
        logger.info("MongoDB connection closed.")

