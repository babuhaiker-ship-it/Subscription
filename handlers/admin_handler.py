from pyrogram import Client, filters
from pyrogram.types import Message
from config import config
import database
import logging
import asyncio
from events import otp_events, otp_values

logger = logging.getLogger(__name__)

def setup_admin_handlers(app: Client):
    @app.on_message(filters.command("login") & filters.user(config.ADMIN_ID) & filters.private)
    async def login_cmd(client, message):
        await database.set_user_state(message.from_user.id, "awaiting_woohoo_mobile")
        await message.reply("Please send your Woohoo Mobile Number or Email.")

    @app.on_message(filters.command("setup") & filters.user(config.ADMIN_ID) & filters.private)
    async def setup_cmd(client, message):
        await database.set_user_state(message.from_user.id, "awaiting_receiver_name")
        await message.reply("Please send the Receiver's Name for the Gift Voucher.")

    @app.on_message(filters.private & filters.user(config.ADMIN_ID) & ~filters.command(["start", "login", "setup"]))
    async def admin_conversation(client, message):
        user_id = message.from_user.id
        state = await database.get_user_state(user_id)
        if not state:
            return

        if state == "awaiting_woohoo_mobile":
            await database.set_woohoo_config({"mobile": message.text})
            await database.set_user_state(user_id, "awaiting_woohoo_password")
            await message.reply("Got it. Now please send your Woohoo Password.")

        elif state == "awaiting_woohoo_password":
            woohoo_config = await database.get_woohoo_config()
            woohoo_config["password"] = message.text
            await database.set_woohoo_config(woohoo_config)
            await database.set_user_state(user_id, None)
            await message.reply("✅ Woohoo login credentials saved!")

        elif state == "awaiting_receiver_name":
            await database.set_gifting_details({"name": message.text})
            await database.set_user_state(user_id, "awaiting_receiver_email")
            await message.reply("Now please send the Receiver's Email.")

        elif state == "awaiting_receiver_email":
            details = await database.get_gifting_details()
            details["email"] = message.text
            await database.set_gifting_details(details)
            await database.set_user_state(user_id, "awaiting_receiver_mobile")
            await message.reply("Now please send the Receiver's Mobile Number.")

        elif state == "awaiting_receiver_mobile":
            details = await database.get_gifting_details()
            details["mobile"] = message.text
            await database.set_gifting_details(details)
            await database.set_user_state(user_id, "awaiting_receiver_message")
            await message.reply("Finally, please send the Message for the receiver.")

        elif state == "awaiting_receiver_message":
            details = await database.get_gifting_details()
            details["message"] = message.text
            await database.set_gifting_details(details)
            await database.set_user_state(user_id, None)
            await message.reply("✅ Gifting details saved!")

        elif state == "awaiting_otp":
            otp_values[user_id] = message.text
            if user_id in otp_events:
                otp_events[user_id].set()
            await message.reply("OTP received, continuing automation...")
