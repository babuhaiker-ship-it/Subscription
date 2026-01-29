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
        price = await database.get_price()
        await message.reply(
            f"👋 **Welcome!**\n\n"
            f"To get premium access, you need to pay **₹{price}**.\n\n"
            f"Click the button below to pay via UPI.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔗 Pay via UPI", callback_data="pay_via_upi")
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
