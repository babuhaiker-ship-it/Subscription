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
    help_text += "\n/setdatabase - Set image database (reply to forwarded message)"
    help_text += "\n/setupidatabase - Set payment notification group (reply to forwarded message)"
    help_text += "\n/debug - View current bot configuration"
    help_text += "\n/addpayment <txn_id> <amount> - Manually add a payment record"
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

@Client.on_message(filters.command("setdatabase") & filters.private)
async def setdatabase_handler(client, message):
    user_id = message.from_user.id
    if not await is_admin(user_id):
        return

    # Handle forward_from_chat (standard) or forward_origin (privacy enabled)
    forwarded = message.reply_to_message
    if not forwarded or not (forwarded.forward_from_chat or forwarded.forward_origin):
        await message.reply_text("❌ **Invalid Usage!**\n\nPlease **forward a message** from your database channel/group to this chat, then **reply** to that forwarded message with `/setdatabase`.")
        return

    if forwarded.forward_from_chat:
        channel_id = forwarded.forward_from_chat.id
    else:
        # User has hidden forward source, but for channels it's often still available in origin
        origin = forwarded.forward_origin
        if hasattr(origin, "chat"):
            channel_id = origin.chat.id
        else:
            await message.reply_text("❌ **Privacy Error!**\n\nI couldn't detect the source channel ID. Please make sure the message is from a **Channel or Group** and that forward privacy settings allow source detection.")
            return

    try:
        # Test if bot is admin in channel
        try:
            chat = await client.get_chat(channel_id)
            chat_type = str(chat.type).split(".")[-1].lower() # Handle Enum to string

            if chat_type not in ["channel", "group", "supergroup"]:
                await message.reply_text(f"❌ This belongs to a {chat_type}, not a channel or group.")
                return

            member = await chat.get_member(client.me.id)
            member_status = str(member.status).split(".")[-1].lower() # Handle Enum to string

            if member_status not in ["administrator", "owner", "creator"]:
                await message.reply_text(f"❌ I am a {member_status} in that channel. I must be an **administrator**.")
                return

        except Exception as e:
            await message.reply_text(f"❌ Could not access channel: {e}\nMake sure I am added to it first and that it's a channel or group.")
            return

        await set_setting("img_db_channel", channel_id)
        await message.reply_text(f"✅ **Success!**\n\nImage database channel set to `{chat.title}` (`{channel_id}`).\n\nNow you can simply send photos to this bot and assign them to messages.")
    except Exception as e:
        await message.reply_text(f"❌ An error occurred: {e}")

@Client.on_message(filters.command("setupidatabase") & filters.private)
async def setupidatabase_handler(client, message):
    user_id = message.from_user.id
    if not await is_admin(user_id):
        return

    # Handle forward_from_chat (standard) or forward_origin (privacy enabled)
    forwarded = message.reply_to_message
    if not forwarded or not (forwarded.forward_from_chat or forwarded.forward_origin):
        await message.reply_text("❌ **Invalid Usage!**\n\nPlease **forward a message** from your payment notification group to this chat, then **reply** to that message with `/setupidatabase`.")
        return

    if forwarded.forward_from_chat:
        channel_id = forwarded.forward_from_chat.id
    else:
        origin = forwarded.forward_origin
        if hasattr(origin, "chat"):
            channel_id = origin.chat.id
        else:
            await message.reply_text("❌ **Privacy Error!**\n\nI couldn't detect the source chat ID. Please ensure the message is from a **Group or Channel**.")
            return

    try:
        chat = await client.get_chat(channel_id)
        chat_type = str(chat.type).split(".")[-1].lower()

        if chat_type not in ["group", "supergroup", "channel"]:
            await message.reply_text(f"❌ This belongs to a {chat_type}. Please use a group or channel.")
            return

        await set_setting("sms_group_id", channel_id)
        await message.reply_text(f"✅ **Success!**\n\nPayment notification group set to `{chat.title}` (`{channel_id}`).\n\nI will now listen for payments in this group.")
    except Exception as e:
        await message.reply_text(f"❌ Could not access group: {e}")

@Client.on_message(filters.command("debug") & filters.private)
async def debug_handler(client, message):
    user_id = message.from_user.id
    if not await is_admin(user_id):
        return

    price = await get_setting("price")
    upi = await get_setting("upi_id")
    img_db = await get_setting("img_db_channel")
    sms_group = await get_setting("sms_group_id")

    debug_text = "🔎 **Bot Debug Info:**\n\n"
    debug_text += f"💰 **Price:** ₹{price}\n"
    debug_text += f"💳 **UPI:** `{upi}`\n"
    debug_text += f"🖼 **Image DB:** `{img_db}`\n"
    debug_text += f"📨 **SMS Group:** `{sms_group}`\n"
    debug_text += f"👑 **Owner ID:** `{OWNER_ID}`\n"

    await message.reply_text(debug_text)

@Client.on_message(filters.command("addpayment") & filters.private)
async def add_payment_handler(client, message):
    user_id = message.from_user.id
    if not await is_admin(user_id):
        return

    if len(message.command) < 3:
        await message.reply_text("Usage: `/addpayment <txn_id> <amount>`")
        return

    txn_id = message.command[1]
    try:
        amount = float(message.command[2])
    except ValueError:
        await message.reply_text("❌ Invalid amount.")
        return

    from utils.parser import store_payment
    success, msg = await store_payment(amount, [txn_id])
    if success:
        await message.reply_text(f"✅ Payment record created: ₹{amount}, ID: `{txn_id}`")
    else:
        await message.reply_text(f"❌ Failed: {msg}")

@Client.on_message(filters.private & filters.photo)
async def admin_photo_handler(client, message):
    user_id = message.from_user.id
    if not await is_admin(user_id):
        return

    # Offer to set this photo as one of the bot images
    keyboard = types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton("Welcome Image", callback_data="setimg_welcome")],
        [types.InlineKeyboardButton("Instruction Image", callback_data="setimg_instr")],
        [types.InlineKeyboardButton("Success Image", callback_data="setimg_success")],
        [types.InlineKeyboardButton("QR Code Image", callback_data="setimg_qr")]
    ])

    await message.reply_text(
        "🖼 **Set this image?**\n\nChoose where you want to show this image:",
        reply_markup=keyboard,
        quote=True
    )

@Client.on_callback_query(filters.regex("^setimg_"))
async def setimg_callback_handler(client, callback_query):
    user_id = callback_query.from_user.id
    if not await is_admin(user_id):
        return

    msg_type = callback_query.data.split("_")[-1]

    # Get the image DB channel
    db_channel = await get_setting("img_db_channel")
    if not db_channel:
        await callback_query.answer("❌ Please set an image database channel first using /setdatabase.", show_alert=True)
        return

    # Check if we have the message with photo (it's the message being replied to)
    # The callback_query.message is the "Set this image?" message.
    # The message with photo is the one before it.

    photo_msg = callback_query.message.reply_to_message
    if not photo_msg or not photo_msg.photo:
        await callback_query.answer("❌ Error: Could not find the original image message.", show_alert=True)
        return

    try:
        # Copy photo to database channel
        copied_msg = await photo_msg.copy(db_channel)

        # Save new IDs
        if msg_type == "qr":
            await set_setting("qr_channel_id", db_channel)
            await set_setting("qr_message_id", copied_msg.id)
        else:
            await set_setting(f"{msg_type}_img_channel", db_channel)
            await set_setting(f"{msg_type}_img_id", copied_msg.id)

        await callback_query.edit_message_text(f"✅ Success! This image is now set as the **{msg_type}** image.")
        await callback_query.answer(f"{msg_type} image updated!")
    except Exception as e:
        await callback_query.answer(f"❌ Failed to copy image: {e}", show_alert=True)
