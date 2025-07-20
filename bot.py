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
    PAYMENT_DETAILS = {
        199.0: {
            "upi": {
                "link": "upi://pay?pa=kanhaiyalal-49@ptaxis&pn=Kanhaiya&am=199&cu=INR",
                "qr_code": "https://i.postimg.cc/rp5M3SWC/IMG-20250717-022522-587.webp" # Placeholder QR for 199 UPI
            }
        },
        399.0: {
            "upi": {
                "link": "upi://pay?pa=kanhaiyalal-49@ptaxis&pn=Kanhaiya&am=399&cu=INR",
                "qr_code": "https://i.postimg.cc/rp5M3SWC/IMG-20250717-022522-587.webp" # Placeholder QR for 399 UPI
            }
        }
    }

    # ID of the Telegram Group where UPI SMS notifications are forwarded
    TXN_GROUP_ID = -1002685844988 # REPLACE WITH YOUR ACTUAL UPI SMS FORWARDING GROUP CHAT ID (e.g., -100xxxxxxxxxx)

    # Verification Link for the 199/- plan
    VERIFICATION_LINK = "https://example.com/your_verification_link_here" # REPLACE WITH YOUR ACTUAL VERIFICATION LINK

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
    """Sends a welcome message and offers subscription plans."""
    user = update.effective_user
    # Nyraa: "Heyyy! ✨ Premium chahiye kya, cutie? 😉💖"
    await update.message.reply_text("Heyyy! ✨ Premium chahiye kya, cutie? 😉💖")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles various user messages based on keywords and context."""
    user_text = update.message.text.lower().strip()
    user = update.effective_user
    user_id = user.id
    username = user.username if user.username else user.first_name

    # --- Affirmative Responses (Leading to Plan Options) ---
    affirmative_keywords = [
        "ha", "h", "han", "hanji", "haan", "yes", "y", "yup", "sure", "bilkul",
        "theek hai", "ok", "okay", "hmm", "acha", "ji", "batao", "bolo", "chahiye",
        "yes please", "interested", "mujhe lena hai", "buy karna hai", "kahan se milega"
    ]
    if any(keyword in user_text for keyword in affirmative_keywords):
        # Nyraa: "Aww, cool! 🥳 So, 199/- monthly ya 399/- for 3 months? Kon sa pasand aaya? 🤔💖"
        keyboard = [
            [InlineKeyboardButton("₹199 Monthly", callback_data="plan_199")],
            [InlineKeyboardButton("₹399 for 3 Months", callback_data="plan_399")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Aww, cool! 🥳 So, 199/- monthly ya 399/- for 3 months? Kon sa pasand aaya? 🤔💖",
            reply_markup=reply_markup
        )
        return

    # --- User Inquires about Premium/Plans (Before Choosing) ---
    # If the User Asks "Kya Hai Premium?" or "Benefits?"
    premium_info_keywords = ["kya hai premium", "benefits", "what's included", "why premium", "premium mein kya hai", "features"]
    if any(keyword in user_text for keyword in premium_info_keywords):
        # Nyraa: "Premium mein na, bohot saare exclusive perks milenge! 🤩 Jaise, early access, no ads, special content, aur bhi bohot kuch! Interested ho kya? 😉💖"
        await update.message.reply_text("Premium mein na, bohot saare exclusive perks milenge! 🤩 Jaise, early access, no ads, special content, aur bhi bohot kuch! Interested ho kya? 😉💖")
        return

    # If the User Asks About the Process/How to Subscribe
    process_inquiry_keywords = ["kaise lein", "how to subscribe", "process kya hai", "buy karna hai", "mujhe lena hai", "kahan se milega", "kya karna padega"]
    if any(keyword in user_text for keyword in process_inquiry_keywords):
        # Nyraa: "Aww, awesome! 🤩 Toh, pehle batao na, 199/- monthly ya 399/- for 3 months? Kon sa chahiye? Uske baad main tumhe payment details bhejungi! 😉✨"
        keyboard = [
            [InlineKeyboardButton("₹199 Monthly", callback_data="plan_199")],
            [InlineKeyboardButton("₹399 for 3 Months", callback_data="plan_399")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Aww, awesome! 🤩 Toh, pehle batao na, 199/- monthly ya 399/- for 3 months? Kon sa chahiye? Uske baad main tumhe payment details bhejungi! 😉✨",
            reply_markup=reply_markup
        )
        return

    # If the User Asks About Offers/Discounts
    offer_inquiry_keywords = ["offer hai", "discount", "sasta nahi hoga", "kuch kam hoga", "price kam hoga"]
    if any(keyword in user_text for keyword in offer_inquiry_keywords):
        # Nyraa: "Abhi toh yahi best offers hain, cutie! 🥰 Par trust me, value for money hai! Toh, 199/- monthly ya 399/- for 3 months? Choose kar lo na! 😉💖"
        keyboard = [
            [InlineKeyboardButton("₹199 Monthly", callback_data="plan_199")],
            [InlineKeyboardButton("₹399 for 3 Months", callback_data="plan_399")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Abhi toh yahi best offers hain, cutie! 🥰 Par trust me, value for money hai! Toh, 199/- monthly ya 399/- for 3 months? Choose kar lo na! 😉💖",
            reply_markup=reply_markup
        )
        return

    # If the User Asks for a Free Trial
    free_trial_keywords = ["free trial", "try for free", "demo", "muft mein milega"]
    if any(keyword in user_text for keyword in free_trial_keywords):
        # Nyraa: "Aww, sorry, cutie! 🥺 Abhi koi free trial nahi hai. Par premium ke benefits itne mast hain ki tumko bilkul regret nahi hoga! 😉 Toh, 199/- monthly ya 399/- for 3 months? Choose kar lo na! ✨💖"
        keyboard = [
            [InlineKeyboardButton("₹199 Monthly", callback_data="plan_199")],
            [InlineKeyboardButton("₹399 for 3 Months", callback_data="plan_399")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Aww, sorry, cutie! 🥺 Abhi koi free trial nahi hai. Par premium ke benefits itne mast hain ki tumko bilkul regret nahi hoga! 😉 Toh, 199/- monthly ya 399/- for 3 months? Choose kar lo na! ✨💖",
            reply_markup=reply_markup
        )
        return

    # --- After Plan Selection (What Happens Next) ---
    # If the User Chooses 199/- Monthly (With Verification)
    # This part is handled by the callback_query_handler after button press.
    # The message handler will only catch if they type it out.
    if any(keyword in user_text for keyword in ["199", "monthly", "pehla wala", "first one", "single month", "ek mahina", "1 month"]):
        context.user_data['selected_plan_amount'] = 199.0
        # Nyraa: "Okay, 199/- monthly! ✅ Par wait, ek chhota sa step hai! 🤫 Pehle verify kar lo ki tum human ho, okay? Is link pe click karo: [Your Verification Link Here] ✨ Jaise hi complete hoga, main aage ki details bhejungi, promise! 😉💖"
        await update.message.reply_text(f"Okay, 199/- monthly! ✅ Par wait, ek chhota sa step hai! 🤫 Pehle verify kar lo ki tum human ho, okay? Is link pe click karo: {config.VERIFICATION_LINK} ✨ Jaise hi complete hoga, main aage ki details bhejungi, promise! 😉💖")
        # For demonstration, directly ask for payment method after this.
        # In a real bot, you'd wait for a signal from your verification system.
        payment_options_keyboard = [
            [InlineKeyboardButton("💳 UPI", callback_data=f"paymethod_{199.0}_upi")],
        ]
        reply_markup = InlineKeyboardMarkup(payment_options_keyboard)
        await update.message.reply_text(
            "Yayyy! Verification done! 🎉 Ab batao, payment kisse karoge? QR ya UPI ID? 😉💖",
            reply_markup=reply_markup
        )
        return

    # If the User Chooses 399/- for 3 Months
    if any(keyword in user_text for keyword in ["399", "3 months", "teen mahine", "doosra wala", "second one", "long term", "3 mahine wala"]):
        context.user_data['selected_plan_amount'] = 399.0
        # Nyraa: "Smart choice, cutie! 399/- for 3 months it is! 🥳 Ab main tumhe payment link send kar rahi hoon. Jaise hi payment ho jaayegi na, tumhara premium access unlock ho jaayega! Let's go! 🚀💖"
        # Offer payment options directly for 399 plan
        payment_options_keyboard = [
            [InlineKeyboardButton("💳 UPI", callback_data=f"paymethod_{399.0}_upi")],
        ]
        reply_markup = InlineKeyboardMarkup(payment_options_keyboard)
        await update.message.reply_text(
            f"Smart choice, cutie! 399/- for 3 months it is! 🥳 Ab main tumhe payment details bhejungi. Please choose your preferred payment method:",
            reply_markup=reply_markup
        )
        return

    # If the User Asks for More Payment Options (After Verification) - This context is hard to determine from just text.
    # This response is better placed within the `button_callback_handler` after a plan is selected and payment method is asked.
    # For now, if they type it generally:
    payment_options_keywords = ["aur options hai", "binance", "crypto", "card", "net banking", "wallet"]
    if any(keyword in user_text for keyword in payment_options_keywords):
        # Nyraa: "Aww, filhal toh itne hi options available hain, cutie! 😅 Ek baar support bot mein poochh kar dekho na, kya pata wahaan admin aur options de de! 😉💖"
        await update.message.reply_text("Aww, filhal toh itne hi options available hain, cutie! 😅 Ek baar support bot mein poochh kar dekho na, kya pata wahaan admin aur options de de! 😉💖")
        return

    # If the User Asks About the Verification Link Specifically
    verification_link_keywords = ["ye link kya hai", "why verification", "is it safe", "link pe kya karna hai", "ye kaisa step hai"]
    if any(keyword in user_text for keyword in verification_link_keywords):
        # Nyraa: "Aww, don't worry, it's totally safe! 😊 Ye bas ek chhota sa human verification step hai, taaki hum confirm kar sakein ki tum bot nahi ho! 😉 Link pe click karke simple instructions follow karo, bas! Easy peasy! ✨💖"
        await update.message.reply_text("Aww, don't worry, it's totally safe! 😊 Ye bas ek chhota sa human verification step hai, taaki hum confirm kar sakein ki tum bot nahi ho! 😉 Link pe click karke simple instructions follow karo, bas! Easy peasy! ✨💖")
        return

    # If the User is Unclear After Plan Selection
    unclear_plan_keywords = ["kya karu", "kaise", "batao", "idk", "which one", "you tell"]
    if any(keyword in user_text for keyword in unclear_plan_keywords):
        # Nyraa: "Aww, confusion ho rahi hai? 😅 Koi nahi, sweetheart! Bas type kar do '199' monthly ke liye, ya '399' 3 months ke liye. Easy peasy! 😉💖"
        await update.message.reply_text("Aww, confusion ho rahi hai? 😅 Koi nahi, sweetheart! Bas type kar do '199' monthly ke liye, ya '399' 3 months ke liye. Easy peasy! 😉💖")
        return

    # If the User Asks About Payment Methods (After Initial Plan Selection, before verification)
    payment_method_inquiry_keywords = ["kaise pay karu", "payment options", "UPI hai", "card se hoga", "net banking"]
    if any(keyword in user_text for keyword in payment_method_inquiry_keywords):
        # Nyraa: "Payment ke liye hum saare popular options support karte hain, jaise UPI, Net Banking, aur Cards! 💳 Don't worry, main tumhe secure payment link bhejungi jisme saare options honge! It's super easy! 😉💖"
        # Adjusted response since only UPI is available now
        await update.message.reply_text("Payment ke liye hum sirf UPI support karte hain! 💳 Don't worry, main tumhe secure UPI QR aur ID bhejungi! It's super easy! 😉💖")
        return

    # --- Other Scenarios ---
    # If the User Says "No" or "Nahi"
    negative_keywords = ["no", "nahi", "na", "not now", "rehne do", "abhi nahi"]
    if any(keyword in user_text for keyword in negative_keywords):
        # Nyraa: "Aww, koi baat nahi, cutie! 🥺 Jab mann kare, tab aa jaana! Main yahin milungi! 🤗💖"
        await update.message.reply_text("Aww, koi baat nahi, cutie! 🥺 Jab mann kare, tab aa jaana! Main yahin milungi! 🤗💖")
        return

    # If the User Asks for More Information or Help (General)
    general_help_keywords = ["help", "info", "details", "kya chal raha hai"]
    if any(keyword in user_text for keyword in general_help_keywords):
        # Nyraa: "Heyyy, thoda aur clear karoge? 🧐 Kya jaanna chahte ho, sweetheart? Main yahi hoon help karne ke liye! 😊💖"
        await update.message.reply_text("Heyyy, thoda aur clear karoge? 🧐 Kya jaanna chahte ho, sweetheart? Main yahi hoon help karne ke liye! 😊💖")
        return

    # If the User Asks About Cancellation/Refunds
    cancel_refund_keywords = ["cancel kaise karein", "refund milega", "subscription kaise band karein", "paise wapas milenge"]
    if any(keyword in user_text for keyword in cancel_refund_keywords):
        # Nyraa: "Subscription cancel karne ke liye ya refund related queries ke liye, please hamari support team se contact karo na. Wo tumhari puri help karenge! 😊💖"
        await update.message.reply_text("Subscription cancel karne ke liye ya refund related queries ke liye, please hamari support team se contact karo na. Wo tumhari puri help karenge! 😊💖")
        return

    # If the User Reports a Technical Issue
    technical_issue_keywords = ["error aa raha hai", "not working", "problem ho rahi hai", "issue hai"]
    if any(keyword in user_text for keyword in technical_issue_keywords):
        # Nyraa: "Oh nooo! 😟 Kya problem ho rahi hai, cutie? Thoda aur detail mein bataoge? Main help karne ki puri koshish karungi, ya phir tumhe support team ke paas guide karungi! 🛠️💖"
        await update.message.reply_text("Oh nooo! 😟 Kya problem ho rahi hai, cutie? Thoda aur detail mein bataoge? Main help karne ki puri koshish karungi, ya phir tumhe support team ke paas guide karungi! 🛠️💖")
        return

    # If the User Expresses General Confusion or Frustration
    confusion_frustration_keywords = ["mujhe samajh nahi aa raha", "bahut confusing hai", "ugh", "pata nahi kya karu"]
    if any(keyword in user_text for keyword in confusion_frustration_keywords):
        # Nyraa: "Hey, relax, cutie! 😌 Koi baat nahi, main yahi hoon. Kya cheez samajh nahi aa rahi? Main phir se explain kar sakti hoon na! Bas poochho! 🤗💖"
        await update.message.reply_text("Hey, relax, cutie! 😌 Koi baat nahi, main yahi hoon. Kya cheez samajh nahi aa rahi? Main phir se explain kar sakti hoon na! Bas poochho! 🤗💖")
        return

    # If the User Sends a General Greeting (not /start) or Chit-chat
    general_greeting_keywords = ["hi", "hello", "how are you", "what's up", "kya haal hai"]
    if any(keyword in user_text for keyword in general_greeting_keywords):
        # Nyraa: "Hiii there! 👋 Main theek hoon, tum kaise ho, cutie? Kuch help chahiye ya bas hi-hello? 😉💖"
        await update.message.reply_text("Hiii there! 👋 Main theek hoon, tum kaise ho, cutie? Kuch help chahiye ya bas hi-hello? 😉💖")
        return

    # If the User Replies with Double Meaning / Dark Dank Jokes / Naughty Way
    naughty_keywords = ["naughty", "sexy", "hot", "double meaning", "joke"]
    if any(keyword in user_text for keyword in naughty_keywords) or \
       (len(user_text.split()) > 1 and not any(keyword in user_text for keyword in affirmative_keywords + premium_info_keywords + process_inquiry_keywords + offer_inquiry_keywords + free_trial_keywords + negative_keywords + general_help_keywords + cancel_refund_keywords + technical_issue_keywords + confusion_frustration_keywords + general_greeting_keywords)):
        # Nyraa: "Haha, lagta hai aap masti ke mood mein ho! 😉 Par main toh yahaan aapko premium ke perks batane aayi hoon, na? Toh, plan choose karoge ya kuch aur jaanna hai, sweetheart? 😉💖"
        await update.message.reply_text("Haha, lagta hai aap masti ke mood mein ho! 😉 Par main toh yahaan aapko premium ke perks batane aayi hoon, na? Toh, plan choose karoge ya kuch aur jaanna hai, sweetheart? 😉💖")
        return

    # Fallback for any other unhandled text, or if the user types a TXN ID
    if user_text.startswith("txn id"):
        await handle_txn_id(update, context)
    else:
        # If none of the above specific handlers match, it's an off-topic or unrecognized message.
        await update.message.reply_text("Heyyy, thoda aur clear karoge? 🧐 Kya jaanna chahte ho, sweetheart? Main yahi hoon help karne ke liye! 😊💖")


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

        # Store the selected amount in user_data for later use
        context.user_data['selected_plan_amount'] = selected_amount
        logger.info(f"User {user_id} selected plan for amount: {selected_amount}")

        if selected_amount == 199.0:
            # Nyraa: "Okay, 199/- monthly! ✅ Par wait, ek chhota sa step hai! 🤫 Pehle verify kar lo ki tum human ho, okay? Is link pe click karo: [Your Verification Link Here] ✨ Jaise hi complete hoga, main aage ki details bhejungi, promise! 😉💖"
            await query.edit_message_text(f"Okay, 199/- monthly! ✅ Par wait, ek chhota sa step hai! 🤫 Pehle verify kar lo ki tum human ho, okay? Is link pe click karo: {config.VERIFICATION_LINK} ✨ Jaise hi complete hoga, main aage ki details bhejungi, promise! 😉💖")
            
            # For demonstration, directly ask for payment method after this.
            # In a real bot, you'd wait for a signal from your verification system.
            payment_options_keyboard = [
                [InlineKeyboardButton("💳 UPI", callback_data=f"paymethod_{selected_amount}_upi")],
            ]
            reply_markup = InlineKeyboardMarkup(payment_options_keyboard)
            await query.message.reply_text(
                "Yayyy! Verification done! 🎉 Ab batao, payment kisse karoge? QR ya UPI ID? 😉💖",
                reply_markup=reply_markup
            )

        elif selected_amount == 399.0:
            # Nyraa: "Smart choice, cutie! 399/- for 3 months it is! 🥳 Ab main tumhe payment link send kar rahi hoon. Jaise hi payment ho jaayegi na, tumhara premium access unlock ho jaayega! Let's go! 🚀💖"
            # Offer payment options directly for 399 plan
            payment_options_keyboard = [
                [InlineKeyboardButton("💳 UPI", callback_data=f"paymethod_{selected_amount}_upi")],
            ]
            reply_markup = InlineKeyboardMarkup(payment_options_keyboard)
            await query.edit_message_text(
                f"Smart choice, cutie! 399/- for 3 months it is! 🥳 Ab main tumhe payment details bhejungi. Please choose your preferred payment method:",
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

        # Only UPI method is expected now
        if selected_method == "upi":
            payment_info = config.PAYMENT_DETAILS.get(selected_amount, {}).get("upi")

            if not payment_info:
                await query.edit_message_text(f"Payment details for UPI not available for ₹{int(selected_amount)}. Please contact support.")
                logger.error(f"Payment details missing for amount {selected_amount} and method UPI")
                return

            payment_link = payment_info.get("link")
            qr_code_url = payment_info.get("qr_code")

            payment_message = (
                f"You have selected the ₹{int(selected_amount)} plan via UPI.\n\n"
                "Scan the QR or click the UPI ID link below 👇\n\n"
                f"🔗 {payment_link}\n\n"
                "After you have sent the payment, send your TXN ID to confirm.\n"
                "Example: `TXN ID 264861XXXXX`"
            )

            if qr_code_url:
                await query.message.reply_photo(photo=qr_code_url, caption=payment_message, parse_mode="Markdown")
            else:
                await query.edit_message_text(payment_message, parse_mode="Markdown")
        else:
            # This case should ideally not be reached if buttons are correctly set
            await query.edit_message_text("Invalid payment method selected. Please choose UPI.")


async def handle_txn_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles messages containing 'TXN ID' to process payments.
    Now checks against the `confirmed_upi_txns` collection and selected plan amount.
    """
    user = update.effective_user
    user_id = user.id
    username = user.username if user.username else user.first_name
    text = update.message.text.strip()

    # The calling `handle_message` function already checks for "TXN ID" prefix.
    # So, we can directly parse it here.
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
            "Please select a plan first using the /start command or by choosing from the options provided."
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
async def chat_id_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Listens for messages in the configured TXN_GROUP_ID, parses them for UPI TXN IDs and amounts,
    and stores them in the confirmed_upi_txns collection.
    """
    message_text = update.message.text
    logger.info(f"Received message in TXN group {config.TXN_GROUP_ID}: {message_text}")

    # Regex to extract TXN ID and Amount from common UPI SMS formats
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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback_handler)) # Handles plan selection and payment method selection

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
