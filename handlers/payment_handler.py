from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import config
import database
from utils import PaymentQueue
import logging
import asyncio
import os

logger = logging.getLogger(__name__)

payment_queue = None

async def process_payment_request(user_id, callback_query):
    await callback_query.message.edit_text("⏳ Wait, creating payment link... This may take a minute.")

    # This is where the Playwright automation will be called
    try:
        from automation import generate_payment_link
        payment_link = await generate_payment_link(callback_query.message.chat.id, callback_query.client)

        if payment_link:
            await callback_query.message.edit_text(
                f"✅ **Payment Link Generated!**\n\n"
                f"Please click the link below to complete your payment of **₹{config.PREMIUM_PRICE_INR}** via UPI.\n\n"
                f"🔗 [Pay via UPI]({payment_link})\n\n"
                f"After payment, your premium access will be activated automatically (once I add that logic!).",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("❌ Close", callback_data="cancel_payment")
                ]])
            )
        else:
            await callback_query.message.edit_text("❌ Failed to generate payment link. Please try again later or contact admin.")
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        logger.error(f"Error in process_payment_request: {error_msg}")
        await callback_query.message.edit_text("❌ An error occurred while generating the payment link.")

        # Notify admin about the error
        try:
            await callback_query.client.send_message(
                config.ADMIN_ID,
                f"🚨 **Automation Error!**\n\n"
                f"User ID: `{user_id}`\n"
                f"Error: `{str(e)}`"
            )
            # Optionally send the screenshot if it exists
            if os.path.exists("error.png"):
                await callback_query.client.send_photo(config.ADMIN_ID, "error.png", caption="Error Screenshot")
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

        await payment_queue.add(user_id, callback_query)
