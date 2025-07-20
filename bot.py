import os
import logging
from datetime import datetime, timedelta
import pytz
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
)
import uuid
import re

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
        199.0: 30,  # ₹199 for 30 days (Monthly)
        399.0: 90   # ₹399 for 90 days (3 Months)
    }

    # Payment details for each plan and method
    # IMPORTANT: Replace these with your actual dynamic links/QR codes for each amount and method
    # For demonstration, placeholders are used for QR codes and links.
    # For Telegram Stars, the 'link' and 'qr_code' are not directly used as send_invoice handles it.
    PAYMENT_DETAILS = {
        199.0: {
            "upi": {
                "link": "upi://pay?pa=kanhaiyalal-49@ptaxis&pn=Kanhaiya&am=199&cu=INR",
                "qr_code": "https://i.postimg.cc/rp5M3SWC/IMG-20250717-022522-587.webp" # Placeholder QR for 199 UPI
            },
            "binance": {
                "link": "https://pay.binance.com/qr/YOUR_BINANCE_PAY_ID?amount=199&currency=INR", # Placeholder Binance link
                "qr_code": "https://i.postimg.cc/rp5M3SWC/IMG-20250717-022522-587.webp" # Placeholder QR for 199 Binance
            },
            "telegram_star": {
                "link": "https://t.me/wallet/star/invoice?amount=199", # Generic link, actual one is dynamic
                "qr_code": "https://i.postimg.cc/rp5M3SWC/IMG-20250717-022522-587.webp" # Placeholder QR for 199 Telegram Stars
            }
        },
        399.0: {
            "upi": {
                "link": "upi://pay?pa=kanhaiyalal-49@ptaxis&pn=Kanhaiya&am=399&cu=INR",
                "qr_code": "https://i.postimg.cc/rp5M3SWC/IMG-20250717-022522-587.webp" # Placeholder QR for 399 UPI
            },
            "binance": {
                "link": "https://pay.binance.com/qr/YOUR_BINANCE_PAY_ID?amount=399&currency=INR", # Placeholder Binance link
                "qr_code": "https://i.postimg.cc/rp5M3SWC/IMG-20250717-022522-587.webp" # Placeholder QR for 399 Binance
            },
            "telegram_star": {
                "link": "https://t.me/wallet/star/invoice?amount=399", # Generic link, actual one is dynamic
                "qr_code": "https://i.postimg.cc/rp5M3SWC/IMG-20250717-022522-587.webp" # Placeholder QR for 399 Telegram Stars
            }
        }
    }

    # ID of the Telegram Group where UPI SMS notifications are forwarded
    # The bot MUST be an admin in this group with 'Read All Messages' permission.
    TXN_GROUP_ID = -1002685844988 # REPLACE WITH YOUR ACTUAL UPI SMS FORWARDING GROUP CHAT ID (e.g., -100xxxxxxxxxx)

    # Human Verification Link (Placeholder)
    VERIFICATION_LINK = "https://example.com/verify_human" # REPLACE WITH YOUR ACTUAL VERIFICATION LINK

try:
    config = BotConfig()
    if not all([config.BOT_TOKEN, config.MONGO_URI, config.TXN_GROUP_ID, config.VERIFICATION_LINK]):
        raise ValueError("One or more essential configuration variables are not set. Please check BOT_TOKEN, MONGO_URI, TXN_GROUP_ID, VERIFICATION_LINK.")
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
    """Handles the /start command with Nyraa's greeting."""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.username}) started the bot.")
    await update.message.reply_text("Heyyy! ✨ Premium chahiye kya, cutie? 😉💖")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles all non-command text messages, implementing Nyraa's conversational logic.
    """
    user = update.effective_user
    user_id = user.id
    username = user.username if user.username else user.first_name
    text = update.message.text.strip().lower()

    logger.info(f"User {user_id} ({username}) sent message: '{text}'")

    # --- State-based handling ---
    # 1. If awaiting TXN ID
    if context.user_data.get('awaiting_txn_id'):
        await process_txn_id_message(update, context)
        return

    # 2. If awaiting human verification completion (for 199 plan)
    if context.user_data.get('awaiting_verification_done'):
        # This is a simulated response. In a real scenario, you'd have a webhook
        # from your verification service updating a database, which this bot would check.
        # For this example, we'll assume any message after sending the link means verification is "done".
        # A more robust solution would involve a unique token in the verification link
        # that the user sends back or is checked by the bot.
        logger.info(f"User {user_id} is assumed to have completed verification.")
        context.user_data['awaiting_verification_done'] = False # Reset state
        
        # Now offer payment options
        selected_amount = context.user_data.get('selected_plan_amount')
        if selected_amount:
            payment_options_keyboard = [
                [InlineKeyboardButton("💳 UPI", callback_data=f"paymethod_{selected_amount}_upi")],
                [InlineKeyboardButton("💰 Binance", callback_data=f"paymethod_{selected_amount}_binance")],
                [InlineKeyboardButton("⭐ Telegram Stars", callback_data=f"paymethod_{selected_amount}_telegram_star")],
            ]
            reply_markup = InlineKeyboardMarkup(payment_options_keyboard)
            await update.message.reply_text("Yayyy! Verification done! 🎉 Ab batao, payment kisse karoge? QR ya UPI ID? 😉💖", reply_markup=reply_markup)
        else:
            await update.message.reply_text("Oops! Something went wrong with your plan selection. Please start again with /start. 🥺")
        return

    # --- General Conversational Flow ---

    # Affirmative Responses
    affirmative_patterns = r"^(ha|h|han|hanji|haan|yes|y|yup|sure|bilkul|theek hai|ok|okay|hmm|acha|ji|batao|bolo|chahiye|yes please|interested|mujhe lena hai|buy karna hai|kahan se milega).*$"
    if re.search(affirmative_patterns, text, re.IGNORECASE):
        await update.message.reply_text("Aww, cool! 🥳 So, 199/- monthly ya 399/- for 3 months? Kon sa pasand aaya? 🤔💖",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("199/- Monthly", callback_data="plan_199")],
                [InlineKeyboardButton("399/- for 3 Months", callback_data="plan_399")]
            ])
        )
        return

    # User Inquires about Premium/Plans (Before Choosing)
    if re.search(r"kya hai premium|benefits|what's included|why premium|premium mein kya hai|features", text, re.IGNORECASE):
        await update.message.reply_text("Premium mein na, bohot saare exclusive perks milenge! 🤩 Jaise, early access, no ads, special content, aur bhi bohot kuch! Interested ho kya? 😉💖")
        return

    # If the User Asks About the Process/How to Subscribe
    if re.search(r"kaise lein|how to subscribe|process kya hai|buy karna hai|mujhe lena hai|kahan se milega|kya karna padega", text, re.IGNORECASE):
        await update.message.reply_text("Aww, awesome! 🤩 Toh, pehle batao na, 199/- monthly ya 399/- for 3 months? Kon sa chahiye? Uske baad main tumhe payment details bhejungi! 😉✨",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("199/- Monthly", callback_data="plan_199")],
                [InlineKeyboardButton("399/- for 3 Months", callback_data="plan_399")]
            ])
        )
        return

    # If the User Asks About Offers/Discounts
    if re.search(r"offer hai|discount|sasta nahi hoga|kuch kam hoga|price kam hoga", text, re.IGNORECASE):
        await update.message.reply_text("Abhi toh yahi best offers hain, cutie! 🥰 Par trust me, value for money hai! Toh, 199/- monthly ya 399/- for 3 months? Choose kar lo na! 😉💖",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("199/- Monthly", callback_data="plan_199")],
                [InlineKeyboardButton("399/- for 3 Months", callback_data="plan_399")]
            ])
        )
        return

    # If the User Asks for a Free Trial
    if re.search(r"free trial|try for free|demo|muft mein milega", text, re.IGNORECASE):
        await update.message.reply_text("Aww, sorry, cutie! 🥺 Abhi koi free trial nahi hai. Par premium ke benefits itne mast hain ki tumko bilkul regret nahi hoga! 😉 Toh, 199/- monthly ya 399/- for 3 months? Choose kar lo na! ✨💖",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("199/- Monthly", callback_data="plan_199")],
                [InlineKeyboardButton("399/- for 3 Months", callback_data="plan_399")]
            ])
        )
        return

    # If the User Chooses 199/- Monthly (via text, not button)
    if re.search(r"199|monthly|pehla wala|first one|single month|ek mahina|1 month", text, re.IGNORECASE):
        context.user_data['selected_plan_amount'] = 199.0
        context.user_data['awaiting_verification_done'] = True # Set state for verification
        await update.message.reply_text(f"Okay, 199/- monthly! ✅ Par wait, ek chhota sa step hai! 🤫 Pehle verify kar lo ki tum human ho, okay? Is link pe click karo: {config.VERIFICATION_LINK} ✨ Jaise hi complete hoga, main aage ki details bhejungi, promise! 😉💖")
        return

    # If the User Chooses 399/- for 3 Months (via text, not button)
    if re.search(r"399|3 months|teen mahine|doosra wala|second one|long term|3 mahine wala", text, re.IGNORECASE):
        context.user_data['selected_plan_amount'] = 399.0
        # Directly provide payment options as per prompt, no verification for 399 plan
        selected_amount = 399.0
        payment_options_keyboard = [
            [InlineKeyboardButton("💳 UPI", callback_data=f"paymethod_{selected_amount}_upi")],
            [InlineKeyboardButton("💰 Binance", callback_data=f"paymethod_{selected_amount}_binance")],
            [InlineKeyboardButton("⭐ Telegram Stars", callback_data=f"paymethod_{selected_amount}_telegram_star")],
        ]
        reply_markup = InlineKeyboardMarkup(payment_options_keyboard)
        await update.message.reply_text("Smart choice, cutie! 399/- for 3 months it is! 🥳 Ab main tumhe payment details bhejungi. Jaise hi payment ho jaayegi na, tumhara premium access unlock ho jaayega! Let's go! 🚀💖", reply_markup=reply_markup)
        return

    # If the User is Unclear After Plan Selection
    if re.search(r"kya karu|kaise|batao|idk|which one|you tell", text, re.IGNORECASE):
        await update.message.reply_text("Aww, confusion ho rahi hai? 😅 Koi nahi, sweetheart! Bas type kar do '199' monthly ke liye, ya '399' 3 months ke liye. Easy peasy! 😉💖")
        return

    # If the User Asks About Payment Methods (Before choosing a plan or after general inquiry)
    if re.search(r"kaise pay karu|payment options|upi hai|card se hoga|net banking", text, re.IGNORECASE):
        await update.message.reply_text("Payment ke liye hum saare popular options support karte hain, jaise UPI, Net Banking, aur Cards! 💳 Don't worry, main tumhe secure payment link bhejungi jisme saare options honge! It's super easy! 😉💖")
        return

    # If the User Says "No" or "Nahi"
    if re.search(r"no|nahi|na|not now|rehne do|abhi nahi", text, re.IGNORECASE):
        await update.message.reply_text("Aww, koi baat nahi, cutie! 🥺 Jab mann kare, tab aa jaana! Main yahin milungi! 🤗💖")
        return

    # If the User Asks for More Information or Help (General)
    if re.search(r"help|info|details|kya chal raha hai", text, re.IGNORECASE):
        await update.message.reply_text("Heyyy, thoda aur clear karoge? 🧐 Kya jaanna chahte ho, sweetheart? Main yahi hoon help karne ke liye! 😊💖")
        return

    # If the User Asks About Cancellation/Refunds
    if re.search(r"cancel kaise karein|refund milega|subscription kaise band karein|paise wapas milenge", text, re.IGNORECASE):
        await update.message.reply_text("Subscription cancel karne ke liye ya refund related queries ke liye, please hamari support team se contact karo na. Wo tumhari puri help karenge! 😊💖")
        return

    # If the User Reports a Technical Issue
    if re.search(r"error aa raha hai|not working|problem ho rahi hai|issue hai", text, re.IGNORECASE):
        await update.message.reply_text("Oh nooo! 😟 Kya problem ho rahi hai, cutie? Thoda aur detail mein bataoge? Main help karne ki puri koshish karungi, ya phir tumhe support team ke paas guide karungi! 🛠️💖")
        return

    # If the User Expresses General Confusion or Frustration
    if re.search(r"mujhe samajh nahi aa raha|bahut confusing hai|ugh|pata nahi kya karu", text, re.IGNORECASE):
        await update.message.reply_text("Hey, relax, cutie! 😌 Koi baat nahi, main yahi hoon. Kya cheez samajh nahi aa rahi? Main phir se explain kar sakti hoon na! Bas poochho! 🤗💖")
        return

    # If the User Sends a General Greeting (not /start) or Chit-chat
    if re.search(r"hi|hello|how are you|what's up|kya haal hai", text, re.IGNORECASE):
        await update.message.reply_text("Hiii there! 👋 Main theek hoon, tum kaise ho, cutie? Kuch help chahiye ya bas hi-hello? 😉💖")
        return

    # If the User Replies with Double Meaning / Dark Dank Jokes / Naughty Way
    naughty_patterns = r"naughty|sex|dirty|joke|chutkule|masti|flirt|gandi baat" # Add more patterns as needed
    if re.search(naughty_patterns, text, re.IGNORECASE):
        await update.message.reply_text("Haha, lagta hai aap masti ke mood mein ho! 😉 Par main toh yahaan aapko premium ke perks batane aayi hoon, na? Toh, plan choose karoge ya kuch aur jaanna hai, sweetheart? 😉💖")
        return

    # Default fallback for unhandled messages
    await update.message.reply_text("Heyyy, thoda aur clear karoge? 🧐 Kya jaanna chahte ho, sweetheart? Main yahi hoon help karne ke liye! 😊💖")


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles inline button presses for plan selection and payment method selection."""
    query = update.callback_query
    await query.answer() # Acknowledge the callback query

    user = query.from_user
    user_id = user.id
    username = user.username if user.username else user.first_name
    
    callback_data = query.data
    logger.info(f"User {user_id} ({username}) tapped button: {callback_data}")

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

        # Store the selected amount in user_data for later use
        context.user_data['selected_plan_amount'] = selected_amount
        logger.info(f"User {user_id} selected plan for amount: {selected_amount}")

        if selected_amount == 199.0:
            context.user_data['awaiting_verification_done'] = True # Set state for verification
            await query.edit_message_text(f"Okay, 199/- monthly! ✅ Par wait, ek chhota sa step hai! 🤫 Pehle verify kar lo ki tum human ho, okay? Is link pe click karo: {config.VERIFICATION_LINK} ✨ Jaise hi complete hoga, main aage ki details bhejungi, promise! 😉💖")
        elif selected_amount == 399.0:
            # Offer payment options directly for 399 plan
            payment_options_keyboard = [
                [InlineKeyboardButton("💳 UPI", callback_data=f"paymethod_{selected_amount}_upi")],
                [InlineKeyboardButton("💰 Binance", callback_data=f"paymethod_{selected_amount}_binance")],
                [InlineKeyboardButton("⭐ Telegram Stars", callback_data=f"paymethod_{selected_amount}_telegram_star")],
            ]
            reply_markup = InlineKeyboardMarkup(payment_options_keyboard)
            await query.edit_message_text(
                f"Smart choice, cutie! 399/- for 3 months it is! 🥳 Ab main tumhe payment details bhejungi. Jaise hi payment ho jaayegi na, tumhara premium access unlock ho jaayega! Let's go! 🚀💖",
                reply_markup=reply_markup
            )

    elif callback_data.startswith("paymethod_"):
        parts = callback_data.split("_")
        if len(parts) < 3:
            logger.error(f"Invalid payment method callback data: {callback_data}")
            await query.edit_message_text("An error occurred. Please try again or contact support.")
            return

        try:
            selected_amount = float(parts[1])
            selected_method = parts[2]
        except (ValueError, IndexError):
            logger.error(f"Error parsing amount or method from callback data: {callback_data}")
            await query.edit_message_text("An error occurred. Please try again or contact support.")
            return

        # Verify the selected amount matches the one stored earlier (optional, but good for consistency)
        if context.user_data.get('selected_plan_amount') != selected_amount:
            logger.warning(f"Mismatch in selected plan amount. User data: {context.user_data.get('selected_plan_amount')}, Callback: {selected_amount}")
            await query.edit_message_text("There was a mismatch in your selected plan. Please start again with /start.")
            return

        if selected_method == "telegram_star":
            # For Telegram Stars, we use send_invoice
            plan_name = f"₹{int(selected_amount)} Plan"
            plan_description = f"Subscription for {config.SUBSCRIPTION_PLANS.get(selected_amount)} days."
            # The payload should be unique for each transaction to identify it later
            payload = f"stars_payment_{user_id}_{int(selected_amount)}_{uuid.uuid4()}" 

            # Telegram Stars amounts are in the smallest unit (e.g., 100 for 1 Star).
            # Assuming 1 Star = 1 INR for simplicity in the code.
            stars_amount_in_smallest_unit = int(selected_amount * 100) 

            prices = [LabeledPrice(label=plan_name, amount=stars_amount_in_smallest_unit)]

            try:
                await context.bot.send_invoice(
                    chat_id=user_id,
                    title=plan_name,
                    description=plan_description,
                    payload=payload,
                    provider_token="", # Leave empty for Telegram Stars
                    currency="XTR", # Telegram Stars currency
                    prices=prices,
                    start_parameter="stars_purchase", # Optional: for deep linking
                )
                await query.edit_message_text(f"Please complete your ₹{int(selected_amount)} payment using Telegram Stars via the invoice sent to you.")
                logger.info(f"Sent Telegram Stars invoice to user {user_id} for {selected_amount} INR equivalent.")
            except Exception as e:
                logger.error(f"Failed to send Telegram Stars invoice to user {user_id}: {e}", exc_info=True)
                await query.edit_message_text("❌ Failed to create Telegram Stars invoice. Please try again later or choose another payment method.")
            return # Exit after handling Stars payment

        # For UPI and Binance, continue with existing logic
        payment_info = config.PAYMENT_DETAILS.get(selected_amount, {}).get(selected_method)

        if not payment_info:
            await query.edit_message_text(f"Payment details for {selected_method} not available for ₹{int(selected_amount)}. Please choose another method or contact support.")
            logger.error(f"Payment details missing for amount {selected_amount} and method {selected_method}")
            return

        payment_link = payment_info.get("link")
        qr_code_url = payment_info.get("qr_code")

        # Add "Payment Done" inline button
        keyboard = [[InlineKeyboardButton("Payment Done ✅", callback_data="payment_done")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        payment_message = (
            f"You have selected the ₹{int(selected_amount)} plan via {selected_method.replace('_', ' ').title()}.\n\n"
            "Scan the QR or click the link below 👇\n\n"
            f"🔗 {payment_link}\n\n"
            "After payment is sent tap on \"Payment Done\" inline button in this message."
        )

        if qr_code_url:
            await query.message.reply_photo(photo=qr_code_url, caption=payment_message, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await query.edit_message_text(payment_message, reply_markup=reply_markup, parse_mode="Markdown")
        
        # Set state to await "Payment Done" tap
        context.user_data['awaiting_payment_done_tap'] = True

    elif callback_data == "payment_done":
        # User tapped "Payment Done"
        context.user_data['awaiting_payment_done_tap'] = False # Reset this state
        context.user_data['awaiting_txn_id'] = True # Set state to await TXN ID
        await query.edit_message_text("Awesome! Ab apna TXN ID bhejo, cutie! 😉 Recheck karke bhejna, okay? Example: `TXN ID 264861XXXXX` 💖", parse_mode="Markdown")


async def process_txn_id_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Processes the TXN ID sent by the user after they tap "Payment Done".
    This function contains the core logic for checking payment amount and TXN ID validity.
    """
    user = update.effective_user
    user_id = user.id
    username = user.username if user.username else user.first_name
    text = update.message.text.strip()

    context.user_data['awaiting_txn_id'] = False # Reset state regardless of outcome

    parts = text.split(" ")
    if len(parts) < 3 or parts[0].lower() != "txn" or parts[1].lower() != "id":
        await update.message.reply_text(
            "Invalid TXN ID format, cutie! 🥺 Ek baar recheck karo aur bhejo na. Example: `TXN ID 264861XXXXX` 😉💖",
            parse_mode="Markdown"
        )
        return

    txn_id = parts[2].strip()
    logger.info(f"User {user_id} ({username}) sent TXN ID for verification: {txn_id}")

    # Retrieve the selected plan amount from user_data
    selected_plan_amount = context.user_data.get('selected_plan_amount')
    if selected_plan_amount is None:
        await update.message.reply_text(
            "Oops! Lagta hai plan select karna bhool gaye. 😅 Please /start karke plan choose karo na pehle. 😉💖"
        )
        return

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
            "❌ Payment verification system mein thodi problem aa rahi hai. 🥺 Please thodi der baad try karna ya support ko contact karo. 😉💖"
        )
        return

    if not confirmed_payment:
        await update.message.reply_text(
            "Invalid TXN ID, cutie! 🥺 Ek baar recheck karo aur bhejo na. 😉💖"
        )
        logger.warning(f"TXN ID {txn_id} not found in confirmed_upi_txns or already used.")
        return

    received_amount = confirmed_payment["amount"]

    # --- Payment Verification Logic ---
    if received_amount < selected_plan_amount:
        remaining_amount = selected_plan_amount - received_amount
        await update.message.reply_text(
            f"Aww, cutie! 🥺 Aapka ₹{int(received_amount)} aa gaya hai, par aapne ₹{int(selected_plan_amount)} ka plan select kiya tha. "
            f"Agar aapko premium chahiye toh pura pay karna hoga ya support bot se refund le lo. "
            f"₹{int(remaining_amount)} aur pay kar do toh unlock ho jaayega! 😉💖"
        )
        logger.info(f"User {user_id} paid partially. Received {received_amount}, expected {selected_plan_amount}.")
        return
    elif received_amount > selected_plan_amount:
        await update.message.reply_text(
            f"Heyy! Aapne thoda zyada pay kar diya hai, cutie! 😅 Aapka plan ₹{int(selected_plan_amount)} ka tha. "
            f"Excess payment ke liye support team se contact karo na. 😉💖"
        )
        logger.warning(f"User {user_id} paid more. Received {received_amount}, expected {selected_plan_amount}.")
        return
    # If received_amount == selected_plan_amount, proceed with full access granting

    duration_days = config.SUBSCRIPTION_PLANS.get(selected_plan_amount)

    if not duration_days:
        await update.message.reply_text(
            "❌ Oops! Internal error ho gaya. 🥺 Plan ki duration nahi mil rahi. Support ko batao na yeh error. 😉💖"
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
            f"Congratulations, cutie! 🎉 Aapka premium access unlock ho gaya hai! 🥳 "
            f"Ab bindass enjoy karo {duration_days} din tak saare exclusive perks! "
            f"Expires on: {expires_at_ist.strftime('%d %B %Y %H:%M %Z')}. Let's go! 🚀💖"
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

async def pre_checkout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles pre-checkout queries from Telegram Stars payments."""
    query = update.pre_checkout_query
    user_id = query.from_user.id
    payload = query.invoice_payload

    logger.info(f"Received pre_checkout_query from {user_id} with payload: {payload}")

    # You can perform final checks here before confirming the payment
    # For example, verify the payload structure, ensure the user is still active, etc.
    if not payload.startswith("stars_payment_"):
        await query.answer(ok=False, error_message="Invalid payment request payload.")
        logger.warning(f"Invalid payload in pre_checkout_query: {payload}")
        return

    # All checks passed, confirm the payment
    await query.answer(ok=True)
    logger.info(f"Pre-checkout query answered successfully for {user_id}.")

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles successful Telegram Stars payments."""
    message = update.message
    successful_payment = message.successful_payment
    user_id = message.from_user.id
    username = message.from_user.username if message.from_user.username else message.from_user.first_name
    payload = successful_payment.invoice_payload

    logger.info(f"Successful payment received from {user_id} for payload: {payload}")
    logger.info(f"Payment details: Total amount: {successful_payment.total_amount}, Currency: {successful_payment.currency}")

    # Parse the payload to get the original amount and user_id
    try:
        # Expected payload format: "stars_payment_<user_id>_<amount_in_inr>_<uuid>"
        parts = payload.split("_")
        if len(parts) >= 4 and parts[0] == "stars" and parts[1] == "payment":
            original_user_id = int(parts[2])
            paid_amount_inr = float(parts[3]) # This is the INR equivalent you expected
        else:
            raise ValueError("Unexpected payload format for successful payment")
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing successful payment payload '{payload}': {e}", exc_info=True)
        await message.reply_text("❌ An error occurred while processing your payment. Please contact support.")
        return

    # Optional: Verify user_id matches and amount is as expected
    if original_user_id != user_id:
        logger.warning(f"Mismatch in user ID for successful Stars payment. Expected {original_user_id}, got {user_id}.")
        # You might want to log this and potentially alert an admin.
        await message.reply_text("There was an issue verifying your payment. Please contact support with your Telegram Stars payment details.")
        return

    # Convert the received total_amount (in Stars, smallest unit) back to your expected INR equivalent
    # If you used `int(selected_amount * 100)` for stars_amount_in_smallest_unit, then:
    expected_stars_amount_in_smallest_unit = int(paid_amount_inr * 100) 
    
    if successful_payment.total_amount < expected_stars_amount_in_smallest_unit:
        await message.reply_text(
            f"❌ Your Telegram Stars payment of {successful_payment.total_amount / 100:.2f} Stars was less than the required amount for the ₹{int(paid_amount_inr)} plan. Please contact support."
        )
        logger.warning(f"Stars payment too low. Received {successful_payment.total_amount}, expected {expected_stars_amount_in_smallest_unit}.")
        return

    duration_days = config.SUBSCRIPTION_PLANS.get(paid_amount_inr)
    if not duration_days:
        logger.error(f"No duration found for paid amount {paid_amount_inr} from Stars payment.")
        await message.reply_text("❌ An internal error occurred after payment. Please contact support.")
        return

    # Update user's premium status
    expires_at_ist = await update_premium_status(user_id, username, duration_days)

    if expires_at_ist:
        # For Stars, there's no "TXN ID" to mark as used in confirmed_upi_txns.
        # You might want a separate collection for Stars transactions if you need to track them.
        # For now, we just grant access.
        
        await message.reply_text(
            f"Congratulations, cutie! 🎉 Aapka premium access unlock ho gaya hai! 🥳 "
            f"Ab bindass enjoy karo {duration_days} din tak saare exclusive perks! "
            f"Expires on: {expires_at_ist.strftime('%d %B %Y %H:%M %Z')}. Let's go! 🚀💖"
        )
        logger.info(f"Premium access granted for user {user_id} for {duration_days} days via Telegram Stars.")
        # Clear the selected plan from user_data after successful payment
        if 'selected_plan_amount' in context.user_data:
            del context.user_data['selected_plan_amount']
    else:
        await message.reply_text(
            "An error occurred while updating your premium status. Please try again later or contact support."
        )
        logger.error(f"Failed to update premium status for user {user_id} after Stars payment.")


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
    # This handler will now manage the general conversation flow
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback_handler)) # Handles plan & payment method selection, and "Payment Done"

    # Handlers for Telegram Stars payments
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

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

