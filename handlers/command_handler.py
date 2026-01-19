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
            "👋 **Welcome!**\n\n"
            "This bot helps you get premium access for **@SpicyNyraa_bot**.\n\n"
            "Click the button below to get started!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("💎 Get Premium Access", callback_data="buy_premium")
            ]])
        )

    @app.on_callback_query(filters.regex("buy_premium"))
    async def buy_premium_callback(client, callback_query):
        await callback_query.message.delete()

        payment_text = (
            f"**Step 1: Complete Your Payment**\n\n"
            f"Please pay the following amount to our UPI ID. You have **{config.PAYMENT_WINDOW_MINUTES} minutes** to complete the transaction.\n\n"
            f"💰 **Amount:** `{config.PREMIUM_PRICE_INR} INR`\n"
            f"🆔 **UPI ID:** `{config.YOUR_UPI_ID}`\n\n"
            f"🔗 **[Click here to view QR Code]({config.QR_CODE_URL})**\n\n"
            f"After paying, click the button below to submit your payment details.\n\n"
            f"⚠️ *This message will be deleted in {config.PAYMENT_WINDOW_MINUTES} minutes.*"
        )
        payment_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ I have paid, Submit Details", callback_data="submit_details")],
            [InlineKeyboardButton("❌ Cancel Payment", callback_data="cancel_payment")]
        ])

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
            "**Step 2: Submit Your Payment Details**\n\n"
            "Please send me the **Transaction ID** (e.g., UTR, RRN) and the **Amount** you paid, separated by a single space.\n\n"
            "**Example:** `423567890123 199`\n\n"
            "I'll verify your payment and grant you premium access.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data="cancel_payment")
            ]])
        )

    @app.on_callback_query(filters.regex("cancel_payment"))
    async def cancel_payment_callback(client, callback_query):
        user_id = callback_query.from_user.id
        await database.set_user_state(user_id, None)
        await callback_query.message.delete()
        await client.send_message(
            user_id,
            "Your payment has been cancelled. Feel free to start over whenever you're ready by sending /start."
        )
