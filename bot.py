import os
import re
import asyncio
from datetime import datetime, timedelta
import logging

from pyrogram import Client, filters, types
from motor.motor_asyncio import AsyncIOMotorClient
from bson.objectid import ObjectId

# --- Logging Setup ---
# Set to DEBUG for detailed logs during debugging. Change to INFO or WARNING for production.
logging.basicConfig(
    level=logging.DEBUG, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Bot Configuration Class ---
class BotConfig:
    # IMPORTANT: Ensure these environment variables are set correctly in your deployment environment.
    # If running locally, you can set them in your shell before running the script, e.g.:
    # export BOT_TOKEN="YOUR_BOT_TOKEN_HERE"
    # export API_ID="YOUR_API_ID_HERE"
    # export API_HASH="YOUR_API_HASH_HERE"
    # export MONGO_URI="YOUR_MONGO_URI_HERE"
    # export TXN_GROUP_ID="-1001234567890" (Replace with your actual group ID)

    BOT_TOKEN = os.environ.get("BOT_TOKEN", "7673807124:AAETa1Bty4C4CU0De1PuP31FwMXLmgPwQLk") # Replace with your actual bot token
    API_ID = int(os.environ.get("API_ID", 29800015)) # Replace with your actual API ID
    API_HASH = os.environ.get("API_HASH", "c8f37108be31ab9ea2818bfe533fbb6f") # Replace with your actual API Hash
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://Pyasipriya:00pEcao9sYhNC5VQ@cluster0.2dfenf7.mongodb.net/spicybot?retryWrites=true&w=majority&appName=Cluster0") # Replace with your MongoDB URI
    MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "spicybot")
    
    # UPI details for different plans - IMPORTANT: Replace with actual details
    # For a real bot, you'd integrate with a payment gateway or use dynamic UPI links
    # that reflect the amount. For this example, we'll simulate different links.
    # Replace 'your_vpa@bank' with your actual UPI Virtual Payment Address.
    UPI_BASE_LINK = "upi://pay?pa=your_vpa@bank&pn=NyraaExclusive&mc=0000&tid=NYRAA{txn_id_placeholder}&tr={ref_id_placeholder}&am={amount}.00"
    
    # Placeholder for a generic QR code image. In a real scenario, you'd generate this dynamically
    # or use a service that provides QR codes for specific UPI links.
    # For demonstration, we'll use a placeholder.
    QR_CODE_IMAGE_URL = "https://placehold.co/300x300/000000/FFFFFF?text=Scan+QR+Code" 
    
    # Telegram Group ID where payment confirmation messages are forwarded
    # IMPORTANT: Replace with your actual TXN_GROUP_ID (must be an integer, e.g., -1001234567890)
    # To get a group ID: Add your bot to the group, send a message, then use a bot like @RawDataBot
    # to get the raw message data, which will contain the chat.id. Group IDs are usually negative.
    TXN_GROUP_ID = int(os.environ.get("TXN_GROUP_ID", -1002685844988)) 

    SUBSCRIPTION_PLANS = {
        "weekly": {"amount": 69, "duration_days": 7},
        "monthly": {"amount": 199, "duration_days": 30},
    }
    PAYMENT_MESSAGE_DELETE_DELAY = 600 # 10 minutes

    # Admin IDs for debugging or future admin commands
    ADMIN_IDS = [6612030110] # Replace with your actual Telegram User ID (integer)

# --- MongoDB Connection Setup ---
logger.info("Attempting to connect to MongoDB...")
try:
    mongo_client = AsyncIOMotorClient(BotConfig.MONGO_URI)
    db = mongo_client[BotConfig.MONGO_DB_NAME]
    logger.info("MongoDB connection client initialized.")
except Exception as e:
    logger.critical(f"Failed to initialize MongoDB client: {e}")
    # Exit or handle gracefully if MongoDB connection is critical for startup
    exit(1) # Exiting if MongoDB connection fails at startup

# Collections
users_collection = db.users
tokens_collection = db.tokens
history_collection = db.history
confirmed_upi_txns_collection = db.confirmed_upi_txns

# --- Pyrogram Client Initialization ---
logger.info("Initializing Pyrogram client...")
app = Client(
    "SubscriptionBot",
    api_id=BotConfig.API_ID,
    api_hash=BotConfig.API_HASH,
    bot_token=BotConfig.BOT_TOKEN,
    # Add a logger to the Pyrogram client for more detailed Pyrogram-specific logs
    # workers=10 # You can adjust workers based on your bot's load
)
logger.info("Pyrogram client initialized. Ready to start connection.")

# --- Helper Functions ---

async def get_user_stats(user_id: int):
    """Fetches and compiles user statistics."""
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
    """Grants premium access to a user for a specified duration."""
    expires_at = datetime.utcnow() + timedelta(days=duration_days)
    token_data = {
        "token_id": str(ObjectId()), # Generate a unique ID for the token
        "is_admin_granted": True, # Mark as granted by bot/admin
        "granted_at": datetime.utcnow(),
        "expires_at": expires_at,
        "granted_by": "SubscriptionBot",
    }

    await tokens_collection.update_one(
        {"user_id": user_id},
        {"$push": {"tokens": token_data}}, # Add the new token to the user's tokens array
        upsert=True # Create the document if it doesn't exist
    )

    await users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"last_premium_check_status": True}}, # Update premium status flag
        upsert=True
    )
    logger.info(f"User {user_id} premium status updated. Expires at: {expires_at}")
    return expires_at

async def schedule_message_deletion(chat_id: int, message_id: int, delay: int):
    """Schedules a message for deletion after a specified delay."""
    await asyncio.sleep(delay)
    try:
        await app.delete_messages(chat_id, message_id)
        logger.info(f"Deleted message {message_id} in chat {chat_id} after {delay} seconds.")
    except Exception as e:
        logger.error(f"Could not delete message {message_id} in chat {chat_id}: {e}")

async def generate_upi_link(amount: int, user_id: int) -> str:
    """Generates a unique UPI payment link for the given amount and user."""
    # In a real scenario, you'd generate a unique transaction ID and reference ID
    # that you can later match with incoming payments.
    # For this example, we'll use a simple timestamp and user ID.
    timestamp_str = datetime.now().strftime("%Y%m%d%H%M%S")
    txn_id_placeholder = f"{timestamp_str}{user_id}"
    ref_id_placeholder = f"NYRAA{user_id}{timestamp_str}"
    
    # Replace placeholders in the base UPI link
    upi_link = BotConfig.UPI_BASE_LINK.format(
        txn_id_placeholder=txn_id_placeholder,
        ref_id_placeholder=ref_id_placeholder,
        amount=amount
    )
    logger.debug(f"Generated UPI link for user {user_id}, amount {amount}: {upi_link}")
    return upi_link

# --- Handlers for User Interaction (Private Chat) ---

# NEW: Simple /ping command for testing responsiveness
@app.on_message(filters.command("ping") & filters.private)
async def ping_command(client: Client, message: types.Message):
    """Responds to /ping with 'Pong!' to check bot's responsiveness."""
    logger.info(f"Received /ping command from user {message.from_user.id}")
    await message.reply_text("Pong!")

@app.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: types.Message):
    """Handles the /start command, sending a welcome message and subscription options."""
    user_id = message.from_user.id
    user_name = message.from_user.first_name if message.from_user.first_name else "there"
    logger.info(f"Received /start command from user {user_id} ({user_name})")

    welcome_message = (
        f"Dear {user_name}, this is Nyraa Exclusive. Here you can buy tokens. "
        "Please select a plan to continue."
    )

    keyboard = types.InlineKeyboardMarkup([
        [
            types.InlineKeyboardButton(
                "🗓️ ₹69 Weekly Trial", callback_data="pay_weekly"
            )
        ],
        [
            types.InlineKeyboardButton(
                "🗓️ ₹199 Monthly", callback_data="pay_monthly"
            )
        ]
    ])
    await message.reply_text(welcome_message, reply_markup=keyboard, parse_mode="markdown")
    logger.debug(f"Sent /start message to user {user_id}")

async def send_payment_info(client: Client, message: types.Message, plan_type: str):
    """Sends payment instructions, UPI link, and QR code (if available) to the user."""
    user_id = message.from_user.id
    plan_details = BotConfig.SUBSCRIPTION_PLANS.get(plan_type)
    if not plan_details:
        logger.warning(f"Invalid plan type '{plan_type}' requested by user {user_id}")
        await message.reply_text("Invalid subscription plan selected. Please try again.")
        return

    amount = plan_details["amount"]
    upi_link = await generate_upi_link(amount, user_id) # Generate dynamic UPI link

    payment_instructions = (
        f"💰 **Payment Instructions for {plan_type.capitalize()} Plan (₹{amount}):**\n\n"
        f"1. Click the UPI link below or scan the QR code.\n"
        f"2. Pay exactly **₹{amount}**.\n"
        f"3. **IMPORTANT:** After successful payment, reply to *this message* with only your **Transaction ID** (10-20 digits long).\n\n"
        f"🔗 **UPI Link:** `{upi_link}`\n\n"
        "This message will self-destruct in 10 minutes for your privacy."
    )

    sent_message = None
    # Attempt to send QR code image if URL is configured
    if BotConfig.QR_CODE_IMAGE_URL and BotConfig.QR_CODE_IMAGE_URL.startswith("http"):
        try:
            sent_message = await client.send_photo(
                chat_id=message.chat.id,
                photo=BotConfig.QR_CODE_IMAGE_URL,
                caption=payment_instructions,
                parse_mode="markdown"
            )
            logger.debug(f"Sent QR code and payment instructions to user {user_id}")
        except Exception as e:
            logger.error(f"Error sending QR code image to user {user_id}: {e}. Sending text only.")
            sent_message = await message.reply_text(payment_instructions, parse_mode="markdown")
    else:
        sent_message = await message.reply_text(payment_instructions, parse_mode="markdown")
        logger.debug(f"Sent payment instructions (text only) to user {user_id}")

    if sent_message:
        # Schedule the payment message for deletion for privacy
        asyncio.create_task(
            schedule_message_deletion(
                message.chat.id, sent_message.id, BotConfig.PAYMENT_MESSAGE_DELETE_DELAY
            )
        )

@app.on_callback_query(filters.regex("pay_weekly"))
async def pay_weekly_callback(client: Client, callback_query: types.CallbackQuery):
    """Handles callback for weekly plan selection."""
    logger.info(f"Received pay_weekly callback from user {callback_query.from_user.id}")
    await callback_query.answer("You selected Weekly Trial Plan. Sending payment details...")
    await send_payment_info(client, callback_query.message, "weekly")

@app.on_callback_query(filters.regex("pay_monthly"))
async def pay_monthly_callback(client: Client, callback_query: types.CallbackQuery):
    """Handles callback for monthly plan selection."""
    logger.info(f"Received pay_monthly callback from user {callback_query.from_user.id}")
    await callback_query.answer("You selected Monthly Plan. Sending payment details...")
    await send_payment_info(client, callback_query.message, "monthly")

@app.on_message(filters.private & filters.regex(r'^\d{10,20}$'))
async def handle_txn_id(client: Client, message: types.Message):
    """Handles messages containing a potential transaction ID from users."""
    user_id = message.from_user.id
    user_name = message.from_user.first_name if message.from_user.first_name else "User"
    txn_id = message.text.strip()
    logger.info(f"User {user_id} ({user_name}) sent potential TXN ID: {txn_id}")

    await message.reply_chat_action("typing")

    now = datetime.utcnow()
    # Look for transactions confirmed within the last 24 hours that haven't been used
    one_day_ago = now - timedelta(days=1) 

    confirmed_txn = await confirmed_upi_txns_collection.find_one({
        "txn_id": txn_id,
        "timestamp": {"$gte": one_day_ago}, # Transaction must be recent
        "$or": [
            {"used_by_user_id": {"$exists": False}}, # Not used by any user
            {"used_by_user_id": None} # Explicitly not used
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
        logger.warning(f"TXN ID {txn_id} from user {user_id}: Not found or already used.")
        return

    # Determine which plan the payment corresponds to
    matched_plan = None
    for plan_type, details in BotConfig.SUBSCRIPTION_PLANS.items():
        if confirmed_txn.get("amount") == details["amount"]:
            matched_plan = plan_type
            break

    if not matched_plan:
        # If the amount doesn't match any known plan
        await message.reply_text(
            f"❌ **Payment amount mismatch!**\n\n"
            f"The amount detected for TXN ID `{txn_id}` is ₹{confirmed_txn.get('amount', 'N/A')}. "
            f"Please ensure you pay either ₹{BotConfig.SUBSCRIPTION_PLANS['weekly']['amount']} (Weekly) "
            f"or ₹{BotConfig.SUBSCRIPTION_PLANS['monthly']['amount']} (Monthly)."
        )
        # Mark the transaction as having an amount mismatch
        await confirmed_upi_txns_collection.update_one(
            {"_id": confirmed_txn["_id"]},
            {"$set": {"status": "amount_mismatch", "checked_at": now}}
        )
        logger.warning(f"TXN ID {txn_id} from user {user_id}: Amount mismatch. Detected: {confirmed_txn.get('amount')}")
        return

    plan_details = BotConfig.SUBSCRIPTION_PLANS[matched_plan]
    
    # Check for partial payment logic
    # This assumes `confirmed_txn.get("amount")` is the amount received.
    # If the user paid less than the full amount for the chosen plan.
    if confirmed_txn.get("amount") < plan_details["amount"]:
        remaining_amount = plan_details["amount"] - confirmed_txn.get("amount")
        await message.reply_text(
            f"You {user_name} have paid partially. To get full access, send ₹{remaining_amount:.2f} more. "
            f"Please send the TXN ID for the remaining payment once done."
        )
        # Optionally, you could store the partial payment and link it to the user
        # to track outstanding amounts. For simplicity, we'll just inform the user.
        logger.info(f"User {user_id} made partial payment for {matched_plan} plan. Remaining: {remaining_amount}")
        return

    # If payment is complete and valid, grant access
    expires_at = await update_premium_status(user_id, plan_details["duration_days"])

    # Mark the transaction as used by this user
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
    Listens for messages in the designated transaction confirmation group.
    Parses TXN ID and amount from messages and stores them in MongoDB.
    """
    text = message.text
    logger.info(f"Received message in TXN Group {BotConfig.TXN_GROUP_ID}: {text[:200]}...") # Log first 200 chars

    txn_id = None
    amount = None

    # Regex patterns to extract Transaction ID
    txn_id_patterns = [
        r'(?:TxnId|UPI Ref No|UTR|Ref\. No\.|TrnId|Ref No|Transaction ID|Txn Id|Transaction ID)\D*(\d{10,20})',
        r'(\d{10,20})\s+is\s+the\s+UPI\s+transaction\s+ID',
        r'UPI\s+Ref\s+No\.\s*[:\s]*(\d{10,20})',
        r'Transaction\s+ID\s*[:\s]*(\d{10,20})',
        r'UTR\s*[:\s]*(\d{10,20})',
        r'Ref\s*[:\s]*(\d{10,20})',
        r'(\d{12})\s+is\s+the\s+UPI\s+Ref\s+No', # Specific for 12-digit UPI Ref No.
    ]

    # Regex patterns to extract Amount
    amount_patterns = [
        r'(?:Rs|INR|₹)\s*(\d+(?:\.\d{1,2})?)',
        r'(\d+(?:\.\d{1,2})?)\s*(?:Rs|INR|₹)',
        r'amount\s*[:\s]*(\d+(?:\.\d{1,2})?)',
        r'paid\s*(\d+(?:\.\d{1,2})?)',
    ]

    # Try to find TXN ID
    for pattern in txn_id_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            txn_id = match.group(1)
            break

    # Try to find Amount
    for pattern in amount_patterns:
        match = re.search(pattern, re.sub(r',', '', text), re.IGNORECASE) # Remove commas from numbers
        if match:
            try:
                amount = float(match.group(1))
                if amount.is_integer(): # Store as int if it's a whole number
                    amount = int(amount)
                break
            except ValueError:
                amount = None # If conversion fails, amount is not valid

    if txn_id and amount is not None:
        # Check if this transaction ID already exists to prevent duplicates
        existing_txn = await confirmed_upi_txns_collection.find_one({"txn_id": txn_id})
        if existing_txn:
            logger.info(f"Duplicate TXN ID '{txn_id}' received in group. Skipping storage.")
            return

        transaction_data = {
            "txn_id": txn_id,
            "amount": amount,
            "timestamp": datetime.utcnow(),
            "original_message": text,
            "used_by_user_id": None, # Initially not used by any user
            "used_at": None,
            "status": "confirmed" # Initial status
        }
        await confirmed_upi_txns_collection.insert_one(transaction_data)
        logger.info(f"Stored confirmed UPI transaction: TXN ID={txn_id}, Amount={amount}")
    else:
        logger.info(f"Could not parse TXN ID or Amount from message in group: {text}")

async def main_subscription_bot_logic():
    """Main function to start the bot and ensure MongoDB indexes."""
    logger.info("Starting Subscription Bot and ensuring MongoDB indexes...")
    
    # Ensure indexes for efficient database operations
    try:
        # Attempt to drop old 'id_1' index if it exists (from previous versions)
        # This is a cleanup step, not critical for new deployments
        await db.users.drop_index("id_1")
        logger.info("Dropped old 'id_1' index on users collection.")
    except Exception as e:
        logger.info(f"Could not drop 'id_1' index on users collection (might not exist or different name): {e}")

    # Create unique and non-unique indexes
    try:
        await db.confirmed_upi_txns.create_index("txn_id", unique=True)
        await db.confirmed_upi_txns.create_index("timestamp")
        await db.confirmed_upi_txns.create_index("used_by_user_id")
        
        await db.users.create_index("user_id", unique=True)
        await db.tokens.create_index("user_id", unique=True)
        await db.history.create_index("user_id", unique=True)
        logger.info("MongoDB indexes ensured.")
    except Exception as e:
        logger.critical(f"Failed to ensure MongoDB indexes: {e}")
        # This might not be a fatal error, but could impact performance.
        # Decide whether to exit or continue based on criticality.

    # Start the Pyrogram client
    logger.info("Attempting to connect to Telegram...")
    try:
        await app.start()
        logger.info("Subscription Bot has successfully connected to Telegram.")
    except Exception as e:
        logger.critical(f"Failed to connect to Telegram: {e}. Please check your BOT_TOKEN, API_ID, and API_HASH.")
        # If bot can't connect to Telegram, it cannot function. Exit.
        exit(1)

    # Keep the bot alive indefinitely
    logger.info("Bot is now running and listening for messages.")
    await asyncio.Event().wait()


if __name__ == "__main__":
    logger.info("Script started. Entering main execution block for Subscription Bot.")
    try:
        # Run the main bot logic
        app.run(main_subscription_bot_logic())
    except KeyboardInterrupt:
        logger.info("Subscription Bot stopped by KeyboardInterrupt (Ctrl+C). Shutting down...")
    except Exception as e:
        logger.critical(f"An unhandled error occurred during bot startup or main execution: {e}", exc_info=True)
    finally:
        logger.info("Subscription Bot application exiting.")


