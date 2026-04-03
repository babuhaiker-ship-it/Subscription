from pyrogram import Client, filters, types
from database import is_admin, add_admin, get_db_stats, set_setting, get_setting
from utils.localization import get_string
from handlers.user import get_user_lang

@Client.on_message(filters.command("admin") & filters.private)
async def admin_help_handler(client, message):
    user_id = message.from_user.id
    if not await is_admin(user_id):
        return

    lang = await get_user_lang(user_id)
    help_text = get_string("admin_help", lang=lang)
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

@Client.on_message(filters.command("addadmin") & filters.private)
async def addadmin_handler(client, message):
    # Only allow existing admins or the first user (if no admins exist)
    # This is a bit simplified for security; usually, one super-admin is hardcoded.
    # We'll allow the first person who calls this command to become admin if the list is empty.
    from database import admins_col
    admin_count = await admins_col.count_documents({})

    if admin_count > 0 and not await is_admin(message.from_user.id):
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
