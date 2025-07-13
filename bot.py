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
    CallbackQueryHandler, # Import CallbackQueryHandler
)
import uuid
import re # Import regex module

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

    # Define subscription plans and their corresponding durations in days
    SUBSCRIPTION_PLANS = {
        69.0: 7,   # ₹69 for 7 days (Weekly Trial)
        199.0: 30  # ₹199 for 30 days (Monthly)
    }

    # UPI Links and QR Code Image URLs for each plan amount
    # IMPORTANT: Replace these with your actual dynamic links/QR codes for each amount
    # For demonstration, placeholders are used for QR codes.
    UPI_LINKS = {
        69.0: "upi://pay?pa=kanhaiyalal-49@ptaxis&pn=Kanhaiya&am=69&cu=INR", # UPI link for 69
        199.0: "upi://pay?pa=kanhaiyalal-49@ptaxis&pn=Kanhaiya&am=199&cu=INR" # UPI link for 199
    }
    QR_CODE_IMAGE_URLS = {
        69.0: "https://i.postimg.cc/28W3hCmz/Image.jpg", # Placeholder QR for 69
        199.0: "https://i.postimg.cc/28W3hCmz/Image.jpg" # Placeholder QR for 199
    }

    # ID of the Telegram Group where UPI SMS notifications are forwarded
    # The bot MUST be an admin in this group with 'Read All Messages' permission.
    TXN_GROUP_ID = -1002685844988 # REPLACE WITH YOUR ACTUAL UPI SMS FORWARDING GROUP CHAT ID (e.g., -100xxxxxxxxxx)

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
    # Exit if MongoDB connection fails, as the bot cannot function without it
    exit(1) 

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

# --- Telegram Bot Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message and offers subscription plans."""
    user = update.effective_user
    username = user.username if user.username else user.first_name

    welcome_message = (
        f"Dear {username}, this is Nyraa Exclusive. Here you can buy tokens. "
        "Please select a plan to continue."
    )

    keyboard = [
        [InlineKeyboardButton("₹69 Weekly Trial", callback_data="plan_69")],
        [InlineKeyboardButton("₹199 Monthly", callback_data="plan_199")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(welcome_message, reply_markup=reply_markup)

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles inline button presses for plan selection."""
    query = update.callback_query
    await query.answer() # Acknowledge the callback query

    user = query.from_user
    user_id = user.id
    username = user.username if user.username else user.first_name
    
    callback_data = query.data

    if callback_data.startswith("plan_"):
        try:
            amount_str = callback_data.split("_")[1]
            selected_amount = float(amount_str)
        except (IndexError, ValueError):
            logger.error(f"Invalid callback data received: {callback_data}")
            await query.edit_message_text("An error occurred. Please try again or contact support.")
            return

        if selected_amount not in config.SUBSCRIPTION_PLANS:
            await query.edit_message_text("Invalid plan selected. Please choose a valid plan.")
            logger.warning(f"User {user_id} selected an invalid plan amount: {selected_amount}")
            return

        # Store the selected amount in user_data for later verification
        context.user_data['selected_plan_amount'] = selected_amount
        logger.info(f"User {user_id} selected plan for amount: {selected_amount}")

        upi_link = config.UPI_LINKS.get(selected_amount)
        qr_code_url = config.QR_CODE_IMAGE_URLS.get(selected_amount)
        
        if not upi_link:
            await query.edit_message_text("Payment link not available for this plan. Please contact support.")
            logger.error(f"UPI link missing for amount: {selected_amount}")
            return

        payment_message = (
            f"You have selected the ₹{int(selected_amount)} plan.\n\n"
            "Scan the QR or click the UPI link below 👇\n\n"
            f"🔗 {upi_link}\n\n"
            "After you have sent the payment, send your TXN ID to confirm.\n"
            "Example: `TXN ID 264861XXXXX`"
        )

        if qr_code_url:
            # Using reply_photo on the original message to send a new message with photo
            await query.message.reply_photo(photo=qr_code_url, caption=payment_message, parse_mode="Markdown")
            # Optionally delete the original message with buttons if desired
            # await query.message.delete() 
        else:
            await query.edit_message_text(payment_message, parse_mode="Markdown")


async def handle_txn_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles messages containing 'TXN ID' to process payments.
    Now checks against the `confirmed_upi_txns` collection and selected plan amount.
    """
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

    # Retrieve the selected plan amount from user_data
    selected_plan_amount = context.user_data.get('selected_plan_amount')
    if selected_plan_amount is None:
        await update.message.reply_text(
            "Please select a plan first using the /start command before sending a TXN ID."
        )
        return

    # No need to check 'if not confirmed_txn_collection:' here.
    # If it's None, the script should have exited during initialization.
    # If there's a problem with the DB connection *after* initialization,
    # the find_one call will raise an error, which the error_handler will catch.
    try:
        confirmed_payment = confirmed_txn_collection.find_one({
            "txn_id": txn_id,
            "timestamp": {"$gt": datetime.utcnow() - timedelta(hours=24)}, # Only consider transactions from last 24 hours
            "status": "confirmed", # Assuming 'confirmed' status is set by the group message handler
            "used_by_user_id": {"$exists": False} # Ensure this TXN ID hasn't been used by another user
        })
    except Exception as e:
        logger.error(f"Error querying confirmed_upi_txns for TXN ID {txn_id}: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Payment verification system is currently experiencing issues. Please try again later or contact support."
        )
        return

    if not confirmed_payment:
        await update.message.reply_text(
            "❌ Invalid TXN ID, not found in our confirmed payments, or already used. Please double-check your TXN ID and try again."
        )
        logger.warning(f"TXN ID {txn_id} not found in confirmed_upi_txns or already used.")
        return

    received_amount = confirmed_payment["amount"]

    # --- Payment Verification Logic ---
    if received_amount < selected_plan_amount:
        remaining_amount = selected_plan_amount - received_amount
        await update.message.reply_text(
            f"You {username} have paid partially. To get full access for the ₹{int(selected_plan_amount)} plan, "
            f"you need to pay ₹{remaining_amount:.2f} more. Please make a *new* payment for the *full* amount "
            f"of ₹{int(selected_plan_amount)} and send the new TXN ID."
        )
        logger.info(f"User {user_id} paid partially. Received {received_amount}, expected {selected_plan_amount}.")
        return
    elif received_amount > selected_plan_amount:
        await update.message.reply_text(
            f"You {username} have paid more than the selected plan amount (₹{int(selected_plan_amount)}). "
            f"Please ensure your payment matches the plan you selected. Contact support for assistance regarding the excess payment."
        )
        logger.warning(f"User {user_id} paid more. Received {received_amount}, expected {selected_plan_amount}.")
        return
    # If received_amount == selected_plan_amount, proceed with full access granting

    duration_days = config.SUBSCRIPTION_PLANS.get(selected_plan_amount)

    if not duration_days:
        await update.message.reply_text(
            "❌ An internal error occurred: Plan duration not found for the selected amount. "
            "Please contact support if you believe this is an error."
        )
        logger.error(f"No duration found for selected plan amount {selected_plan_amount}.")
        return

    # --- Update MongoDB and mark transaction as used ---
    expires_at_ist = await update_premium_status(user_id, username, duration_days)

    if expires_at_ist:
        # Mark the transaction as used in the database
        try:
            confirmed_txn_collection.update_one(
                {"_id": confirmed_payment["_id"]},
                {"$set": {"used_by_user_id": user_id, "used_at": datetime.utcnow()}}
            )
            logger.info(f"TXN ID {txn_id} marked as used by user {user_id}.")
        except Exception as e:
            logger.error(f"Error marking TXN ID {txn_id} as used: {e}", exc_info=True)
            # Even if marking as used fails, we've already granted access, so proceed with success message
            pass 

        await update.message.reply_text(
            f"Dear {username}, 🎉\n\n"
            f"✅ Your payment of ₹{int(selected_plan_amount)} has been confirmed.\n"
            f"🗓️ Premium access granted for {duration_days} days!\n"
            f"Expires on: {expires_at_ist.strftime('%d %B %Y %H:%M %Z')}.\n\n"
            "You can now enjoy premium content with the File-Sharing Bot!"
        )
        logger.info(f"Premium access granted for user {user_id} for {duration_days} days with TXN ID {txn_id}.")
        # Clear the selected plan from user_data after successful payment
        if 'selected_plan_amount' in context.user_data:
            del context.user_data['selected_plan_amount']
    else:
        await update.message.reply_text(
            "An error occurred while updating your premium status. Please try again later or contact support."
        )
        logger.error(f"Failed to update premium status for user {user_id} with TXN ID {txn_id}.")

# --- New Handler: Listen to messages in the UPI TXN Group ---
# This handler is registered directly in main() to ensure it's part of the application.
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
        try:
            if confirmed_txn_collection.find_one({"txn_id": txn_id}):
                logger.info(f"TXN ID {txn_id} already exists in confirmed_upi_txns. Skipping insertion.")
                return
        except Exception as e:
            logger.error(f"Error checking for existing TXN ID {txn_id} in DB: {e}", exc_info=True)
            # Continue trying to insert, as this might be a transient DB issue
            pass

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
    
    # Safely check if update.effective_message exists before trying to reply
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "An unexpected error occurred. Please try again later."
            )
        except Exception as reply_e:
            logger.error(f"Failed to send error reply to user: {reply_e}")
    else:
        logger.warning("Error occurred but no effective_message to reply to.")


def main() -> None:
    """Start the bot."""
    if not config.BOT_TOKEN:
        logger.critical("BOT_TOKEN environment variable not set. Exiting.")
        return

    application = Application.builder().token(config.BOT_TOKEN).build()

    # Register handlers for private chat with the user
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_txn_id))
    application.add_handler(CallbackQueryHandler(button_callback_handler)) # New handler for inline buttons

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

