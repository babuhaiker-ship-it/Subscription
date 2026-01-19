from pyrogram import Client, filters
from config import config
import database
from utils import parse_sms
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def setup_payment_handlers(app):
    @app.on_message(filters.chat(config.PAYMENT_GROUP_ID) & filters.text)
    async def sms_handler(client, message):
        logger.info(f"Received new message in payment group: {message.text[:50]}...")
        parsed_data = parse_sms(message.text)

        if parsed_data:
            txn_id = parsed_data['txn_id']
            amount = parsed_data['amount']

            if await database.find_payment_by_txn_id(txn_id):
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
            await database.log_payment(payment_doc)
            logger.info(f"Successfully logged new payment: Txn ID {txn_id}, Amount {amount}")
        else:
            logger.warning("Could not parse SMS for payment details.")

    @app.on_message(filters.text & filters.private)
    async def handle_payment_details(client, message):
        user_id = message.from_user.id
        user_state = await database.get_user_state(user_id)
        if user_state != "awaiting_payment_details":
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

        claimed_payment = await database.find_and_claim_payment(txn_id, amount, user_id, valid_time_window)

        if claimed_payment:
            logger.info(f"Successfully claimed transaction {txn_id} for user {user_id}.")
            if await database.add_premium_access(user_id, config.PREMIUM_DURATION_DAYS):
                await wait_msg.edit_text("✅ **Payment Verified!**\n\nYou now have premium access on @SpicyNyraa_bot. Go there and press /start to enjoy!")
                await database.set_user_state(user_id, None)
            else:
                await wait_msg.edit_text("❌ An error occurred while granting access. Please contact support and provide your Transaction ID.")
        else:
            existing_payment = await database.find_payment(txn_id, amount)
            if existing_payment:
                if existing_payment["is_claimed"]:
                    await wait_msg.edit_text("❌ This Transaction ID has already been used. Please contact support if you believe this is an error.")
                elif existing_payment["received_at"] < valid_time_window:
                    await wait_msg.edit_text(f"❌ This transaction is too old. Payments must be claimed within {config.TRANSACTION_VALIDITY_HOURS} hours.")
            else:
                await wait_msg.edit_text("❌ **Transaction Not Found.**\n\nPlease double-check the details and send them again. If you just paid, wait 1-2 minutes for the payment to register in our system.")
