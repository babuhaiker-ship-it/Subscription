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

    # Verification Link for 199/- plan
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
    logger.info(f"Using collections: {config.USERS_COLLECTION_NAME}, {config.TOKONS_COLLECTION_NAME}, {config.CONFIRMED_TXN_COLLECTION_NAME}")
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
    context.user_data['current_state'] = "IDLE" # Reset state on /start
    await update.message.reply_text("Heyyy! ✨ Premium chahiye kya, cutie? 😉💖")

async def handle_affirmative_responses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles affirmative responses and leads to plan options."""
    text = update.message.text.lower()
    affirmative_keywords = ["ha", "h", "han", "hanji", "haan", "yes", "y", "yup", "sure", "bilkul", "theek hai", "ok", "okay", "hmm", "acha", "ji", "batao", "bolo", "chahiye", "yes please", "interested", "mujhe lena hai", "buy karna hai", "kahan se milega"]

    if any(keyword in text for keyword in affirmative_keywords):
        keyboard = [
            [InlineKeyboardButton("₹199 Monthly", callback_data="plan_199")],
            [InlineKeyboardButton("₹399 for 3 Months", callback_data="plan_399")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.user_data['current_state'] = "AWAITING_PLAN_SELECTION"
        await update.message.reply_text("Aww, cool! 🥳 So, 199/- monthly ya 399/- for 3 months? Kon sa pasand aaya? 🤔💖", reply_markup=reply_markup)
        return True # Handled
    return False # Not handled

async def handle_premium_inquiry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles inquiries about premium benefits."""
    text = update.message.text.lower()
    inquiry_keywords = ["kya hai premium", "benefits", "what's included", "why premium", "premium mein kya hai", "features"]
    if any(keyword in text for keyword in inquiry_keywords):
        await update.message.reply_text("Premium mein na, bohot saare exclusive perks milenge! 🤩 Jaise, early access, no ads, special content, aur bhi bohot kuch! Interested ho kya? 😉💖")
        return True
    return False

async def handle_how_to_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles inquiries about how to subscribe."""
    text = update.message.text.lower()
    subscribe_keywords = ["kaise lein", "how to subscribe", "process kya hai", "buy karna hai", "mujhe lena hai", "kahan se milega", "kya karna padega"]
    if any(keyword in text for keyword in subscribe_keywords):
        keyboard = [
            [InlineKeyboardButton("₹199 Monthly", callback_data="plan_199")],
            [InlineKeyboardButton("₹399 for 3 Months", callback_data="plan_399")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.user_data['current_state'] = "AWAITING_PLAN_SELECTION"
        await update.message.reply_text("Aww, awesome! 🤩 Toh, pehle batao na, 199/- monthly ya 399/- for 3 months? Kon sa chahiye? Uske baad main tumhe payment details bhejungi! 😉✨", reply_markup=reply_markup)
        return True
    return False

async def handle_offers_discounts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles inquiries about offers/discounts."""
    text = update.message.text.lower()
    offer_keywords = ["offer hai", "discount", "sasta nahi hoga", "kuch kam hoga", "price kam hoga"]
    if any(keyword in text for keyword in offer_keywords):
        await update.message.reply_text("Abhi toh yahi best offers hain, cutie! 🥰 Par trust me, value for money hai! Toh, 199/- monthly ya 399/- for 3 months? Choose kar lo na! 😉💖")
        return True
    return False

async def handle_free_trial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles inquiries about free trials."""
    text = update.message.text.lower()
    trial_keywords = ["free trial", "try for free", "demo", "muft mein milega"]
    if any(keyword in text for keyword in trial_keywords):
        await update.message.reply_text("Aww, sorry, cutie! 🥺 Abhi koi free trial nahi hai. Par premium ke benefits itne mast hain ki tumko bilkul regret nahi hoga! 😉 Toh, 199/- monthly ya 399/- for 3 months? Choose kar lo na! ✨💖")
        return True
    return False

async def handle_verification_link_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles questions about the verification link."""
    text = update.message.text.lower()
    link_query_keywords = ["ye link kya hai", "why verification", "is it safe", "link pe kya karna hai", "ye kaisa step hai"]
    if any(keyword in text for keyword in link_query_keywords):
        await update.message.reply_text("Aww, don't worry, it's totally safe! 😊 Ye bas ek chhota sa human verification step hai, taaki hum confirm kar sakein ki tum bot nahi ho! 😉 Link pe click karke simple instructions follow karo, bas! Easy peasy! ✨💖")
        return True
    return False

async def handle_unclear_plan_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles vague responses after being asked to choose a plan."""
    text = update.message.text.lower()
    vague_keywords = ["kya karu", "kaise", "batao", "idk", "which one", "you tell"]
    if context.user_data.get('current_state') == "AWAITING_PLAN_SELECTION" and any(keyword in text for keyword in vague_keywords):
        await update.message.reply_text("Aww, confusion ho rahi hai? 😅 Koi nahi, sweetheart! Bas type kar do '199' monthly ke liye, ya '399' 3 months ke liye. Easy peasy! 😉💖")
        return True
    return False

async def handle_payment_options_inquiry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles inquiries about payment methods before payment details are sent."""
    text = update.message.text.lower()
    payment_keywords = ["kaise pay karu", "payment options", "upi hai", "card se hoga", "net banking"]
    if any(keyword in text for keyword in payment_keywords) and context.user_data.get('current_state') not in ["AWAITING_PAYMENT_METHOD_SELECTION", "AWAITING_TXN_ID"]:
        await update.message.reply_text("Payment ke liye hum saare popular options support karte hain, jaise UPI, Net Banking, aur Cards! 💳 Don't worry, main tumhe secure payment link bhejungi jisme saare options honge! It's super easy! 😉💖")
        return True
    return False

async def handle_negative_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles explicit negative responses."""
    text = update.message.text.lower()
    negative_keywords = ["no", "nahi", "na", "not now", "rehne do", "abhi nahi"]
    if any(keyword in text for keyword in negative_keywords):
        await update.message.reply_text("Aww, koi baat nahi, cutie! 🥺 Jab mann kare, tab aa jaana! Main yahin milungi! 🤗💖")
        context.user_data['current_state'] = "IDLE" # Reset state
        return True
    return False

async def handle_general_info_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles general inquiries or help requests."""
    text = update.message.text.lower()
    help_keywords = ["help", "info", "details", "kya chal raha hai"]
    if any(keyword in text for keyword in help_keywords):
        await update.message.reply_text("Heyyy, thoda aur clear karoge? 🧐 Kya jaanna chahte ho, sweetheart? Main yahi hoon help karne ke liye! 😊💖")
        return True
    return False

async def handle_cancellation_refunds(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles inquiries about cancellation/refunds."""
    text = update.message.text.lower()
    cancel_keywords = ["cancel kaise karein", "refund milega", "subscription kaise band karein", "paise wapas milenge"]
    if any(keyword in text for keyword in cancel_keywords):
        await update.message.reply_text("Subscription cancel karne ke liye ya refund related queries ke liye, please hamari support team se contact karo na. Wo tumhari puri help karenge! 😊💖")
        return True
    return False

async def handle_technical_issue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles reports of technical issues."""
    text = update.message.text.lower()
    issue_keywords = ["error aa raha hai", "not working", "problem ho rahi hai", "issue hai"]
    if any(keyword in text for keyword in issue_keywords):
        await update.message.reply_text("Oh nooo! 😟 Kya problem ho rahi hai, cutie? Thoda aur detail mein bataoge? Main help karne ki puri koshish karungi, ya phir tumhe support team ke paas guide karungi! 🛠️💖")
        return True
    return False

async def handle_general_confusion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles expressions of general confusion or frustration."""
    text = update.message.text.lower()
    confusion_keywords = ["mujhe samajh nahi aa raha", "bahut confusing hai", "ugh", "pata nahi kya karu"]
    if any(keyword in text for keyword in confusion_keywords):
        await update.message.reply_text("Hey, relax, cutie! 😌 Koi baat nahi, main yahi hoon. Kya cheez samajh nahi aa rahi? Main phir se explain kar sakti hoon na! Bas poochho! 🤗💖")
        return True
    return False

async def handle_general_greeting(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles general greetings or chit-chat."""
    text = update.message.text.lower()
    greeting_keywords = ["hi", "hello", "how are you", "what's up", "kya haal hai"]
    if any(keyword in text for keyword in greeting_keywords):
        await update.message.reply_text("Hiii there! 👋 Main theek hoon, tum kaise ho, cutie? Kuch help chahiye ya bas hi-hello? 😉💖")
        return True
    return False

async def handle_naughty_jokes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles suggestive or inappropriate messages."""
    # This is a placeholder. You might need more sophisticated NLP for this.
    # For now, it's a catch-all for anything not caught by other filters.
    await update.message.reply_text("Haha, lagta hai aap masti ke mood mein ho! 😉 Par main toh yahaan aapko premium ke perks batane aayi hoon, na? Toh, plan choose karoge ya kuch aur jaanna hai, sweetheart? 😉💖")
    return True


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles inline button presses for plan selection and payment method selection."""
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

        context.user_data['selected_plan_amount'] = selected_amount
        logger.info(f"User {user_id} selected plan for amount: {selected_amount}")

        if selected_amount == 199.0:
            # For 199/- plan, initiate human verification
            verification_keyboard = [[InlineKeyboardButton("I'm Verified! ✨", callback_data="verified_human")]]
            reply_markup = InlineKeyboardMarkup(verification_keyboard)
            context.user_data['current_state'] = "AWAITING_VERIFICATION_CONFIRMATION"
            await query.edit_message_text(
                f"Okay, 199/- monthly! ✅ Par wait, ek chhota sa step hai! 🤫 Pehle verify kar lo ki tum human ho, okay? Is link pe click karo: {config.VERIFICATION_LINK} ✨ Jaise hi complete hoga, main aage ki details bhejungi, promise! 😉💖",
                reply_markup=reply_markup
            )
        elif selected_amount == 399.0:
            # For 399/- plan, directly offer payment options
            context.user_data['current_state'] = "AWAITING_PAYMENT_METHOD_SELECTION"
            payment_options_keyboard = [
                [InlineKeyboardButton("💳 UPI", callback_data=f"paymethod_{selected_amount}_upi")],
                [InlineKeyboardButton("💰 Binance", callback_data=f"paymethod_{selected_amount}_binance")],
                [InlineKeyboardButton("⭐ Telegram Stars", callback_data=f"paymethod_{selected_amount}_telegram_star")],
            ]
            reply_markup = InlineKeyboardMarkup(payment_options_keyboard)
            await query.edit_message_text(
                f"Smart choice, cutie! 399/- for 3 months it is! 🥳 Ab batao, payment kisse karoge? 😉💖",
                reply_markup=reply_markup
            )

    elif callback_data == "verified_human":
        if context.user_data.get('current_state') == "AWAITING_VERIFICATION_CONFIRMATION":
            selected_amount = context.user_data.get('selected_plan_amount')
            if selected_amount is None:
                await query.edit_message_text("Oops! Looks like you haven't selected a plan yet. Please start again with /start.")
                context.user_data['current_state'] = "IDLE"
                return

            context.user_data['current_state'] = "AWAITING_PAYMENT_METHOD_SELECTION"
            payment_options_keyboard = [
                [InlineKeyboardButton("💳 UPI", callback_data=f"paymethod_{selected_amount}_upi")],
                [InlineKeyboardButton("💰 Binance", callback_data=f"paymethod_{selected_amount}_binance")],
                [InlineKeyboardButton("⭐ Telegram Stars", callback_data=f"paymethod_{selected_amount}_telegram_star")],
            ]
            reply_markup = InlineKeyboardMarkup(payment_options_keyboard)
            await query.edit_message_text(
                "Yayyy! Verification done! 🎉 Ab batao, payment kisse karoge? QR ya UPI ID? 😉💖",
                reply_markup=reply_markup
            )
        else:
            await query.edit_message_text("Hmm, I wasn't expecting that button now. Please try starting over with /start if you're stuck.")

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

        if context.user_data.get('selected_plan_amount') != selected_amount:
            logger.warning(f"Mismatch in selected plan amount. User data: {context.user_data.get('selected_plan_amount')}, Callback: {selected_amount}")
            await query.edit_message_text("There was a mismatch in your selected plan. Please start again with /start.")
            context.user_data['current_state'] = "IDLE"
            return

        context.user_data['selected_payment_method'] = selected_method
        context.user_data['current_state'] = "AWAITING_TXN_ID" # Set state to await TXN ID

        if selected_method == "telegram_star":
            plan_name = f"₹{int(selected_amount)} Plan"
            plan_description = f"Subscription for {config.SUBSCRIPTION_PLANS.get(selected_amount)} days."
            payload = f"stars_payment_{user_id}_{int(selected_amount)}_{uuid.uuid4()}" 
            stars_amount_in_smallest_unit = int(selected_amount * 100) # Assuming 1 Star = 100 units (e.g., cents/paise equivalent)
            prices = [LabeledPrice(label=plan_name, amount=stars_amount_in_smallest_unit)]

            try:
                await context.bot.send_invoice(
                    chat_id=user_id,
                    title=plan_name,
                    description=plan_description,
                    payload=payload,
                    provider_token="",
                    currency="XTR",
                    prices=prices,
                    start_parameter="stars_purchase",
                )
                await query.edit_message_text(f"Please complete your ₹{int(selected_amount)} payment using Telegram Stars via the invoice sent to you. After payment, I'll automatically confirm it! 😉💖")
                logger.info(f"Sent Telegram Stars invoice to user {user_id} for {selected_amount} INR equivalent.")
            except Exception as e:
                logger.error(f"Failed to send Telegram Stars invoice to user {user_id}: {e}", exc_info=True)
                await query.edit_message_text("❌ Failed to create Telegram Stars invoice. Please try again later or choose another payment method.")
            return

        # For UPI and Binance
        payment_info = config.PAYMENT_DETAILS.get(selected_amount, {}).get(selected_method)

        if not payment_info:
            await query.edit_message_text(f"Payment details for {selected_method} not available for ₹{int(selected_amount)}. Please choose another method or contact support.")
            logger.error(f"Payment details missing for amount {selected_amount} and method {selected_method}")
            return

        payment_link = payment_info.get("link")
        qr_code_url = payment_info.get("qr_code")

        payment_message = (
            f"You have selected the ₹{int(selected_amount)} plan via {selected_method.replace('_', ' ').title()}.\n\n"
            f"Scan the QR or click the link below 👇\n\n"
            f"🔗 `{payment_link}`\n\n" # Use backticks for monospace
            f"Addon: After payment is sent, tap on 'Payment Done' inline button in this message. 😉"
        )
        
        # Add "Payment Done" inline button
        payment_done_keyboard = [[InlineKeyboardButton("Payment Done ✅", callback_data="payment_done")]]
        reply_markup = InlineKeyboardMarkup(payment_done_keyboard)

        if qr_code_url:
            await query.message.reply_photo(photo=qr_code_url, caption=payment_message, parse_mode="Markdown", reply_markup=reply_markup)
        else:
            await query.edit_message_text(payment_message, parse_mode="Markdown", reply_markup=reply_markup)

    elif callback_data == "payment_done":
        if context.user_data.get('current_state') == "AWAITING_TXN_ID":
            await query.edit_message_text("Awesome! Ab apna TXN ID bhejo na, cutie! 😉 Ek baar recheck kar ke bhejna, okay? Example: `TXN ID 264861XXXXX`")
        else:
            await query.edit_message_text("Hmm, looks like you're not in the payment process right now. If you want to subscribe, please use /start.")
            context.user_data['current_state'] = "IDLE" # Reset state
    else:
        await query.edit_message_text("Oops! Something went wrong with that button. Please try again or start over with /start.")


async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    General handler for all text messages not caught by specific commands or callbacks.
    This acts as a router based on the current state.
    """
    user = update.effective_user
    user_id = user.id
    username = user.username if user.username else user.first_name
    text = update.message.text.strip()

    # Priority 1: Check for TXN ID if awaiting it
    if context.user_data.get('current_state') == "AWAITING_TXN_ID" and text.lower().startswith("txn id"):
        await handle_txn_id(update, context)
        return

    # Priority 2: Check for specific keyword-based responses
    if await handle_affirmative_responses(update, context): return
    if await handle_premium_inquiry(update, context): return
    if await handle_how_to_subscribe(update, context): return
    if await handle_offers_discounts(update, context): return
    if await handle_free_trial(update, context): return
    if await handle_verification_link_query(update, context): return
    if await handle_unclear_plan_selection(update, context): return
    if await handle_payment_options_inquiry(update, context): return
    if await handle_negative_response(update, context): return
    if await handle_general_info_help(update, context): return
    if await handle_cancellation_refunds(update, context): return
    if await handle_technical_issue(update, context): return
    if await handle_general_confusion(update, context): return
    if await handle_general_greeting(update, context): return

    # If nothing else matches, it's a general unhandled message or a naughty joke
    await handle_naughty_jokes(update, context)


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
        # This should ideally not be reached if handle_text_messages routes correctly.
        # But as a safeguard:
        await update.message.reply_text("Invalid format. Please send your TXN ID in the format: `TXN ID <your_transaction_id>`", parse_mode="Markdown")
        return

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
            "Oops! Looks like you haven't selected a plan yet. Please start with /start to choose a plan. 😉💖"
        )
        context.user_data['current_state'] = "IDLE"
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
            "❌ Payment verification system is currently experiencing issues. Please try again later or contact support."
        )
        return

    if not confirmed_payment:
        await update.message.reply_text(
            "Invalid TXN ID, cutie! 🥺 Ek baar recheck karo aur bhejo. Ya phir support bot se help le lo. 😉💖"
        )
        logger.warning(f"TXN ID {txn_id} not found in confirmed_upi_txns or already used.")
        return

    received_amount = confirmed_payment["amount"]

    # --- Payment Verification Logic ---
    if received_amount < selected_plan_amount:
        remaining_amount = selected_plan_amount - received_amount
        await update.message.reply_text(
            f"Aww, cutie! 🥺 Aapka ₹{int(received_amount)} aa gaya hai, par aapne ₹{int(selected_plan_amount)} ka plan select kiya tha. "
            f"Agar aapko premium chahiye toh pura ₹{int(selected_plan_amount)} pay karna hoga, ya support bot se refund le lo. "
            f"Baki ₹{remaining_amount:.2f} pay karke, naya TXN ID bhejo na! 😉💖"
        )
        logger.info(f"User {user_id} paid partially. Received {received_amount}, expected {selected_plan_amount}.")
        return
    elif received_amount > selected_plan_amount:
        await update.message.reply_text(
            f"Heyy! Aapne ₹{int(received_amount)} pay kar diya hai, jo aapke ₹{int(selected_plan_amount)} plan se zyada hai. "
            f"Please make sure your payment matches the plan, ya phir support team se contact karo extra payment ke liye. 😉💖"
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
            f"Congratulations, cutie! 🎉 Aapka payment confirm ho gaya hai! "
            f"Ab aapko {duration_days} days ke liye premium access mil gaya hai! "
            f"Enjoy all the exclusive perks! 🚀💖"
            f"\n\nExpires on: {expires_at_ist.strftime('%d %B %Y %H:%M %Z')}"
        )
        logger.info(f"Premium access granted for user {user_id} for {duration_days} days with TXN ID {txn_id}.")
        # Clear the selected plan and state from user_data after successful payment
        if 'selected_plan_amount' in context.user_data:
            del context.user_data['selected_plan_amount']
        context.user_data['current_state'] = "IDLE"
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

    if not payload.startswith("stars_payment_"):
        await query.answer(ok=False, error_message="Invalid payment request payload.")
        logger.warning(f"Invalid payload in pre_checkout_query: {payload}")
        return

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

    try:
        parts = payload.split("_")
        if len(parts) >= 4 and parts[0] == "stars" and parts[1] == "payment":
            original_user_id = int(parts[2])
            paid_amount_inr = float(parts[3])
        else:
            raise ValueError("Unexpected payload format for successful payment")
    except (ValueError, IndexError) as e:
        logger.error(f"Error parsing successful payment payload '{payload}': {e}", exc_info=True)
        await message.reply_text("❌ An error occurred while processing your payment. Please contact support.")
        return

    if original_user_id != user_id:
        logger.warning(f"Mismatch in user ID for successful Stars payment. Expected {original_user_id}, got {user_id}.")
        await message.reply_text("There was an issue verifying your payment. Please contact support with your Telegram Stars payment details.")
        return

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

    expires_at_ist = await update_premium_status(user_id, username, duration_days)

    if expires_at_ist:
        await message.reply_text(
            f"Congratulations, cutie! 🎉 Aapka payment confirm ho gaya hai! "
            f"Ab aapko {duration_days} days ke liye premium access mil gaya hai! "
            f"Enjoy all the exclusive perks! 🚀💖"
            f"\n\nExpires on: {expires_at_ist.strftime('%d %B %Y %H:%M %Z')}"
        )
        logger.info(f"Premium access granted for user {user_id} for {duration_days} days via Telegram Stars.")
        if 'selected_plan_amount' in context.user_data:
            del context.user_data['selected_plan_amount']
        context.user_data['current_state'] = "IDLE"
    else:
        await message.reply_text(
            "An error occurred while updating your premium status. Please try again later or contact support."
        )
        logger.error(f"Failed to update premium status for user {user_id} after Stars payment.")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a message to the user."""
    logger.error(f"Update {update} caused error {context.error}", exc_info=True)
    
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
    application.add_handler(CallbackQueryHandler(button_callback_handler)) # Handles all inline button presses

    # General text message handler - MUST be after CommandHandlers and CallbackQueryHandlers
    # It acts as a router based on conversation state and keywords
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

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
