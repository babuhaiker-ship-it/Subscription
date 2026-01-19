from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import config
import database
from utils import send_and_schedule_deletion
import asyncio

def setup_command_handlers(app):
    @app.on_message(filters.command("start") & filters.private)
    async def start_cmd(client, message):
        await database.set_user_state(message.from_user.id, None)
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
                app=client,
                chat_id=callback_query.from_user.id,
                text=payment_text,
                markup=payment_markup,
                delay_seconds=config.PAYMENT_WINDOW_MINUTES * 60
            )
        )

    @app.on_callback_query(filters.regex("submit_details"))
    async def submit_details_callback(client, callback_query):
        user_id = callback_query.from_user.id
        await database.set_user_state(user_id, "awaiting_payment_details")
        await callback_query.message.edit_text(
            "Please send me the **Transaction ID** (e.g., UTR) and the **Amount** you paid, separated by a space.\n\n"
            "**Example:** `423567890123 199`"
        )
