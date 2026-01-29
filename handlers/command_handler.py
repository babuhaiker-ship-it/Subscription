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
        await callback_query.message.edit_text(
            f"**Premium Access**\n\n"
            f"To get premium access for **@SpicyNyraa_bot**, you need to pay **{config.PREMIUM_PRICE_INR} INR**.\n\n"
            f"Click the button below to generate a UPI payment link.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Pay via UPI", callback_data="pay_via_upi")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_payment")]
            ])
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
