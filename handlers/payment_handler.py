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
    await callback_query.message.edit_text("⏳ Wait, initializing payment session... This may take a minute.")

    try:
        status = await automate_payment_flow(chat_id, client)

        if status == "SUCCESS":
            # Grant premium access
            await database.add_premium_access(user_id, 30) # Default 30 days
            await client.send_message(
                chat_id,
                "🎉 **Payment Successful!**\n\nYour Premium Access has been activated for 30 days. Enjoy!"
            )
            try:
                await callback_query.message.delete()
            except:
                pass
        elif status == "TIMEOUT":
            await client.send_message(
                chat_id,
                "⌛ **Payment Timed Out.**\n\nWe didn't detect your payment within 5 minutes. If you have already paid, please contact the admin."
            )
        elif status == "OTP_FAILED":
            await callback_query.message.edit_text("❌ Failed to receive OTP from admin. Please try again later.")
        elif status == "QR_NOT_FOUND":
            await callback_query.message.edit_text("❌ Failed to generate QR code. The website might be having issues. Please try again.")
        else:
            await callback_query.message.edit_text("❌ An error occurred during the payment process. Please try again later.")

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
