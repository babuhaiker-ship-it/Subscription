from pyrogram import Client, filters, types
from database import is_admin, add_admin, get_db_stats, set_setting, get_setting, OWNER_ID
from utils.localization import get_string
from handlers.user import get_user_lang

@Client.on_message(filters.command(["admin", "help_admin"]) & filters.private)
async def admin_help_handler(client, message):
    user_id = message.from_user.id
    if not await is_admin(user_id):
        return

    lang = await get_user_lang(user_id)
    help_text = get_string("admin_help", lang=lang)
    if user_id == OWNER_ID:
        help_text += "\n/addadmin <user_id> - Add a new admin (Owner only)"
    await message.reply_text(help_text)

@Client.on_message(filters.command("stats") & filters.private)
async def stats_handler(client, message):
    user_id = message.from_user.id
    if not await is_admin(user_id):
        return

    total_users, premium_users, revenue = await get_db_stats()
    lang = await get_user_lang(user_id)

    stats_text = get_string("admin_stats", lang=lang,
                            total_users=total_users,
                            premium_users=premium_users,
                            revenue=revenue)
    await message.reply_text(stats_text)

@Client.on_message(filters.command("setprice") & filters.private)
async def setprice_handler(client, message):
    user_id = message.from_user.id
    if not await is_admin(user_id):
        return

    if len(message.command) < 2:
        await message.reply_text("Usage: /setprice <amount>")
        return

    try:
        new_price = int(message.command[1])
        await set_setting("price", new_price)
        await message.reply_text(f"✅ Price updated to ₹{new_price}")
    except ValueError:
        await message.reply_text("❌ Please enter a valid number for price.")

@Client.on_message(filters.command("setupi") & filters.private)
async def setupi_handler(client, message):
    user_id = message.from_user.id
    if not await is_admin(user_id):
        return

    if len(message.command) < 2:
        await message.reply_text("Usage: /setupi <upi_id>")
        return

    new_upi = message.command[1]
    await set_setting("upi_id", new_upi)
    await message.reply_text(f"✅ UPI ID updated to `{new_upi}`")

@Client.on_message(filters.command("setqr") & filters.private)
async def setqr_handler(client, message):
    user_id = message.from_user.id
    if not await is_admin(user_id):
        return

    if len(message.command) < 3:
        await message.reply_text("Usage: /setqr <channel_id> <message_id>")
        return

    try:
        channel_id = int(message.command[1])
        message_id = int(message.command[2])
        await set_setting("qr_channel_id", channel_id)
        await set_setting("qr_message_id", message_id)
        await message.reply_text(f"✅ QR source updated to channel `{channel_id}` message `{message_id}`")
    except ValueError:
        await message.reply_text("❌ Please enter valid numbers for channel_id and message_id.")

@Client.on_message(filters.private & filters.forwarded)
async def get_id_handler(client, message):
    user_id = message.from_user.id
    if not await is_admin(user_id):
        return

    # Extract forwarded info
    if message.forward_from_chat:
        chat_id = message.forward_from_chat.id
        msg_id = message.forward_from_message_id
        chat_name = message.forward_from_chat.title or "Channel"

        text = f"📊 **Message Source Info:**\n\n"
        text += f"📍 **{chat_name} ID:** `{chat_id}`\n"
        text += f"🔢 **Message ID:** `{msg_id}`\n\n"
        text += f"You can use these with `/setimg` or `/setqr` commands."
        await message.reply_text(text)

@Client.on_message(filters.command("addadmin") & filters.private)
async def addadmin_handler(client, message):
    # Only allow the owner to add new admins
    if message.from_user.id != OWNER_ID:
        return

    if len(message.command) < 2:
        # If no args, add self
        target_id = message.from_user.id
    else:
        try:
            target_id = int(message.command[1])
        except ValueError:
            await message.reply_text("❌ Please enter a valid user ID.")
            return

    await add_admin(target_id)
    await message.reply_text(f"✅ User `{target_id}` is now an admin.")

@Client.on_message(filters.command(["setwelcome", "setsuccess", "setinstr"]) & filters.private)
async def set_msg_handler(client, message):
    user_id = message.from_user.id
    if not await is_admin(user_id):
        return

    cmd = message.command[0]
    if len(message.command) < 3:
        await message.reply_text(f"Usage: /{cmd} <en/hi> <message text>")
        return

    lang = message.command[1]
    if lang not in ["en", "hi"]:
        await message.reply_text("❌ Language must be 'en' or 'hi'.")
        return

    text = message.text.split(None, 2)[2]

    key_map = {
        "setwelcome": "welcome_msg",
        "setsuccess": "success_msg",
        "setinstr": "pay_instr"
    }

    db_key = f"{key_map[cmd]}_{lang}"
    await set_setting(db_key, text)
    await message.reply_text(f"✅ {cmd} for {lang} updated!")

@Client.on_message(filters.command("setimg") & filters.private)
async def setimg_handler(client, message):
    user_id = message.from_user.id
    if not await is_admin(user_id):
        return

    if len(message.command) < 4:
        await message.reply_text("Usage: /setimg <welcome|success|instr> <channel_id> <message_id>")
        return

    msg_type = message.command[1]
    if msg_type not in ["welcome", "success", "instr"]:
        await message.reply_text("❌ Type must be 'welcome', 'success', or 'instr'.")
        return

    try:
        channel_id = int(message.command[2])
        message_id = int(message.command[3])
        await set_setting(f"{msg_type}_img_channel", channel_id)
        await set_setting(f"{msg_type}_img_id", message_id)
        await message.reply_text(f"✅ {msg_type} image updated!")
    except ValueError:
        await message.reply_text("❌ Please enter valid numbers for channel_id and message_id.")
