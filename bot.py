import asyncio
import logging
import uuid
import re
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import MessageIdInvalid
from pymongo import MongoClient, ReturnDocument

# --- Configuration ---
class PaymentConfig:
    BOT_TOKEN = 'YOUR_PAYMENT_RECEIVER_BOT_TOKEN'
    API_ID = 29800015
    API_HASH = 'c8f37108be31ab9ea2818bfe533fbb6f'
    MONGO_URI = 'mongodb+srv://Pyasipriya:00pEcao9sYhNC5VQ@cluster0.2dfenf7.mongodb.net/spicybot?retryWrites=true&w=majority&appName=Cluster0'
    MONGO_DB_NAME = 'spicybot'
    PAYMENT_GROUP_ID = -1001234567890  # Replace with your private SMS forwarding group ID
    PREMIUM_PRICE_INR = 199
    PREMIUM_DURATION_DAYS = 30
    YOUR_UPI_ID = "your-upi-id@oksbi" # Replace with your actual UPI ID
    QR_CODE_URL = "https://i.postimg.cc/YOUR_QR_CODE.png" # Replace with a direct link to your QR code image
    PAYMENT_WINDOW_MINUTES = 10
    TRANSACTION_VALIDITY_HOURS = 24

config = PaymentConfig()

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Pyrogram & MongoDB Client ---
app = Client("payment_bot", api_id=config.API_ID, api_hash=config.API_HASH, bot_token=config.BOT_TOKEN)
mongo_client = MongoClient(config.MONGO_URI)
db = mongo_client[config.MONGO_DB_NAME]
tokens_collection = db['tokens']
incoming_payments_collection = db['incoming_payments']
users_collection = db['users'] # Added for notifying the main bot

# --- State Management ---
user_state = {}

# --- Helper Functions ---

def parse_sms(text: str):
    text = text.lower()
    amount_match = re.search(r'(?:rs|inr)\.?\s*([\d,]+\.?\d*)', text)
    if not amount_match:
        return None
    amount = float(amount_match.group(1).replace(',', ''))

    txn_id_match = re.search(r'(?:txn|transaction|trxn|payment)\s*(?:id|ref no|ref|id is|no):?\s*(\w+)|utr:?\s*(\d+)', text)
    if not txn_id_match:
        return None
    txn_id = next((g for g in txn_id_match.groups() if g is not None), None)

    if amount and txn_id:
        return {"amount": amount, "txn_id": txn_id}
    return None

async def send_and_schedule_deletion(chat_id: int, text: str, markup: InlineKeyboardMarkup, delay_seconds: int):
    try:
        sent_message = await app.send_message(chat_id, text, reply_markup=markup, disable_web_page_preview=True)
        await asyncio.sleep(delay_seconds)
        await sent_message.delete()
        logger.info(f"Auto-deleted payment message {sent_message.id} for user {chat_id}.")
    except MessageIdInvalid:
        logger.warning(f"Message was already deleted by the user or another process.")
    except Exception as e:
        logger.error(f"Error in send_and_schedule_deletion: {e}")

def add_premium_access(user_id: int, duration_days: int):
    now = datetime.utcnow()
    expires_at = now + timedelta(days=duration_days)
    token = {
        'token_id': str(uuid.uuid4()),
        'created_at': now,
        'expires_at': expires_at,
        'is_admin_granted': True
    }
    try:
        tokens_collection.update_one(
            {'user_id': user_id},
            {'$push': {'tokens': token}},
            upsert=True
        )
        users_collection.update_one(
            {'user_id': user_id},
            {'$set': {'last_premium_check_status': True}},
            upsert=True
        )
        logger.info(f"Premium access granted for user {user_id} for {duration_days} days.")
        return True
    except Exception as e:
        logger.error(f"Failed to grant premium access for user {user_id}: {e}")
        return False

# --- Bot Handlers ---

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    user_state.pop(message.from_user.id, None)
    await message.reply(
        "Welcome! Use this bot to get premium access for @SpicyNyraa_bot.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("💰 Buy Premium Access", callback_data="buy_premium")
        ]])
    )

@app.on_callback_query(filters.regex("buy_premium"))
async def buy_premium_callback(client, callback_query):
    await callback_query.message.delete()

    payment_text = (
        f"⚠️ **You have {config.PAYMENT_WINDOW_MINUTES} minutes to complete the payment.**\n"
        f"This message will be deleted automatically.\n\n"
        f"**Amount:** `{config.PREMIUM_PRICE_INR}`\n"
        f"**UPI ID:** `{config.YOUR_UPI_ID}`\n\n"
        f"<a href='{config.QR_CODE_URL}'>📱 Tap here to view QR Code</a>\n\n"
        "After paying, click the button below."
    )
    payment_markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ I have paid, Submit Details", callback_data="submit_details")
    ]])

    asyncio.create_task(
        send_and_schedule_deletion(
            chat_id=callback_query.from_user.id,
            text=payment_text,
            markup=payment_markup,
            delay_seconds=config.PAYMENT_WINDOW_MINUTES * 60
        )
    )

@app.on_callback_query(filters.regex("submit_details"))
async def submit_details_callback(client, callback_query):
    user_id = callback_query.from_user.id
    user_state[user_id] = "awaiting_payment_details"
    await callback_query.message.edit_text(
        "Please send me the **Transaction ID** (e.g., UTR) and the **Amount** you paid, separated by a space.\n\n"
        "**Example:** `423567890123 199`"
    )

@app.on_message(filters.chat(config.PAYMENT_GROUP_ID) & filters.text)
async def sms_handler(client, message):
    logger.info(f"Received new message in payment group: {message.text[:50]}...")
    parsed_data = parse_sms(message.text)

    if parsed_data:
        txn_id = parsed_data['txn_id']
        amount = parsed_data['amount']

        if incoming_payments_collection.find_one({"txn_id": txn_id}):
            logger.warning(f"Duplicate transaction ID {txn_id} detected. Ignoring.")
            return

        payment_doc = {
            "txn_id": txn_id,
            "amount": amount,
            "received_at": datetime.utcnow(),
            "is_claimed": False,
            "claimed_by_user_id": None,
            "claimed_at": None,
            "raw_sms": message.text
        }
        incoming_payments_collection.insert_one(payment_doc)
        logger.info(f"Successfully logged new payment: Txn ID {txn_id}, Amount {amount}")
    else:
        logger.warning("Could not parse SMS for payment details.")

@app.on_message(filters.text & filters.private)
async def handle_payment_details(client, message):
    user_id = message.from_user.id
    if user_state.get(user_id) != "awaiting_payment_details":
        return

    try:
        parts = message.text.strip().split()
        if len(parts) != 2:
            await message.reply("❌ Invalid format. Please send the Transaction ID and Amount separated by a single space.\n\n**Example:** `423567890123 199`")
            return

        txn_id, amount_str = parts
        amount = float(amount_str)
    except (ValueError, IndexError):
        await message.reply("❌ Invalid format. Please ensure the amount is a valid number.\n\n**Example:** `423567890123 199`")
        return

    logger.info(f"User {user_id} submitted details: Txn ID {txn_id}, Amount {amount}")

    if amount != config.PREMIUM_PRICE_INR:
        await message.reply(f"⚠️ The amount you entered (₹{amount}) does not match the required amount (₹{config.PREMIUM_PRICE_INR}). Please check and try again.")
        return

    wait_msg = await message.reply("⏳ Verifying your payment... This may take a moment.")

    valid_time_window = datetime.utcnow() - timedelta(hours=config.TRANSACTION_VALIDITY_HOURS)

    claimed_payment = incoming_payments_collection.find_one_and_update(
        {
            "txn_id": txn_id,
            "amount": amount,
            "is_claimed": False,
            "received_at": {"$gte": valid_time_window}
        },
        {
            "$set": {
                "is_claimed": True,
                "claimed_by_user_id": user_id,
                "claimed_at": datetime.utcnow()
            }
        },
        return_document=ReturnDocument.AFTER
    )

    if claimed_payment:
        logger.info(f"Successfully claimed transaction {txn_id} for user {user_id}.")
        if add_premium_access(user_id, config.PREMIUM_DURATION_DAYS):
            await wait_msg.edit_text("✅ **Payment Verified!**\n\nYou now have premium access on @SpicyNyraa_bot. Go there and press /start to enjoy!")
            user_state.pop(user_id, None)
        else:
            await wait_msg.edit_text("❌ An error occurred while granting access. Please contact support and provide your Transaction ID.")
    else:
        existing_payment = incoming_payments_collection.find_one({"txn_id": txn_id, "amount": amount})
        if existing_payment:
            if existing_payment["is_claimed"]:
                await wait_msg.edit_text("❌ This Transaction ID has already been used. Please contact support if you believe this is an error.")
            elif existing_payment["received_at"] < valid_time_window:
                await wait_msg.edit_text(f"❌ This transaction is too old. Payments must be claimed within {config.TRANSACTION_VALIDITY_HOURS} hours.")
        else:
            await wait_msg.edit_text("❌ **Transaction Not Found.**\n\nPlease double-check the details and send them again. If you just paid, wait 1-2 minutes for the payment to register in our system.")

if __name__ == "__main__":
    logger.info("Starting Robust Payment Receiver Bot...")
    app.run()
