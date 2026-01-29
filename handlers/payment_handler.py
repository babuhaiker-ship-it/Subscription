from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import config
import database
from utils import PaymentQueue
import logging
import asyncio
import os
from automation import automate_payment_flow

logger = logging.getLogger(__name__)

payment_queue = None

async def process_payment_request(user_id, client, callback_query):
    chat_id = callback_query.message.chat.id
    await callback_query.message.edit_text("⏳ wait creating payment link")

    try:
        price = await database.get_price()
        result = await automate_payment_flow(chat_id, client)

        if result and ("http" in result or "upi://" in result):
            await client.send_message(
                chat_id,
                f"✅ **Payment Link Generated!**\n\nClick the link below to pay **₹{price}** via UPI:\n\n`{result}`\n\n"
                f"Please complete the payment in the opened app or browser."
            )
            try:
                await callback_query.message.delete()
            except:
                pass
        elif result == "OTP_FAILED":
            await callback_query.message.edit_text("❌ Failed to receive OTP from admin. Please try again later.")
        elif result == "CONFIG_ERROR":
            await callback_query.message.edit_text("❌ Admin has not finished the setup yet. Please contact support.")
        else:
            await callback_query.message.edit_text("❌ An error occurred while creating the payment link. Please try again later.")

    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        logger.error(f"Error in process_payment_request: {error_msg}")
        await callback_query.message.edit_text(f"❌ An error occurred: {str(e)}")

        # Notify admin about the error
        try:
            error_ss = f"error_{chat_id}.png"
            await client.send_message(
                config.ADMIN_ID,
                f"🚨 **Automation Error!**\n\n"
                f"User ID: `{user_id}`\n"
                f"Error: `{str(e)}`"
            )
            # Optionally send the screenshot if it exists
            if os.path.exists(error_ss):
                await client.send_photo(config.ADMIN_ID, error_ss, caption="Error Screenshot")
                os.remove(error_ss)
        except:
            pass

def setup_payment_handlers(app):
    global payment_queue
    payment_queue = PaymentQueue(process_payment_request)

    @app.on_callback_query(filters.regex("pay_via_upi"))
    async def pay_via_upi_callback(client, callback_query):
        user_id = callback_query.from_user.id
        wait_time = payment_queue.get_wait_time()

        if wait_time > 0:
            await callback_query.answer(f"Queue is busy. Estimated wait: {wait_time} minutes.", show_alert=True)

        await payment_queue.add(user_id, client, callback_query)
