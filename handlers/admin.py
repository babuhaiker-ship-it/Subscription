from pyrogram import Client, filters, types
from database import is_admin, add_admin, get_db_stats, set_setting, get_setting, OWNER_ID, plans_col, users_col, payments_col
from utils.localization import get_string
from handlers.user import get_user_lang
import uuid

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
    help_text += "\n/managesub - Manage subscription plans"
    help_text += "\n/premiumusers - List all premium users"
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

@Client.on_message(filters.command("premiumusers") & filters.private)
async def premium_users_handler(client, message):
    user_id = message.from_user.id
    if not await is_admin(user_id):
        return

    premium_users = await users_col.find({"is_premium": True}).to_list(100)

    if not premium_users:
        await message.reply_text("ℹ️ No premium users found.")
        return

    keyboard = []
    for user in premium_users:
        uid = user["user_id"]
        keyboard.append([
            types.InlineKeyboardButton(f"👤 {uid}", callback_data=f"admin_view_user_{uid}")
        ])

    await message.reply_text(
        "💎 **Premium Users List:**\n\nClick a user ID to view their payment details and plan.",
        reply_markup=types.InlineKeyboardMarkup(keyboard)
    )

@Client.on_callback_query(filters.regex("^admin_view_user_"))
async def admin_view_user_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if not await is_admin(user_id):
        return

    target_uid = int(callback_query.data.split("_")[-1])
    user = await users_col.find_one({"user_id": target_uid})

    if not user:
        await callback_query.answer("User not found.", show_alert=True)
        return

    try:
        chat = await client.get_chat(target_uid)
        name = f"@{chat.username}" if chat.username else f"{chat.first_name} {chat.last_name or ''}"
    except:
        name = "Unknown"

    expiry = user.get("premium_until")
    expiry_str = expiry.strftime("%Y-%m-%d %H:%M UTC") if expiry else "N/A"

    text = f"👤 **User Details:**\n"
    text += f"🆔 **ID:** `{target_uid}`\n"
    text += f"📛 **Name/Username:** {name}\n"
    text += f"📅 **Premium Until:** {expiry_str}\n\n"
    text += f"💳 **Payment History:**\n"

    payments = await payments_col.find({"claimed_by": target_uid, "is_claimed": True}).sort("claimed_at", -1).to_list(10)

    if not payments:
        text += "_No payment records found._"
    else:
        for p in payments:
            amount = p.get("amount", 0)
            txn_id = p.get("txn_id", "N/A")
            plan_name = p.get("plan_info", {}).get("plan_name", "Unknown Plan")
            date = p.get("claimed_at").strftime("%Y-%m-%d") if p.get("claimed_at") else "N/A"

            text += f"• ₹{amount} | {plan_name}\n  UTR: `{txn_id}` | {date}\n"

    keyboard = types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton("🔙 Back to List", callback_data="admin_back_premium")]
    ])

    await callback_query.edit_message_text(text, reply_markup=keyboard)

@Client.on_callback_query(filters.regex("^admin_back_premium$"))
async def admin_back_premium_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if not await is_admin(user_id):
        return

    premium_users = await users_col.find({"is_premium": True}).to_list(100)
    keyboard = []
    for user in premium_users:
        uid = user["user_id"]
        keyboard.append([
            types.InlineKeyboardButton(f"👤 {uid}", callback_data=f"admin_view_user_{uid}")
        ])

    await callback_query.edit_message_text(
        "💎 **Premium Users List:**\n\nClick a user ID to view their payment details and plan.",
        reply_markup=types.InlineKeyboardMarkup(keyboard)
    )

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
            # Ask which plan to assign this QR to
            plans = await plans_col.find().to_list(100)
            keyboard = []
            for plan in plans:
                keyboard.append([
                    types.InlineKeyboardButton(f"Plan: {plan['name']}", callback_data=f"admin_assignqr_{plan['plan_id']}_{copied_msg.id}")
                ])
            keyboard.append([types.InlineKeyboardButton("Global QR (Default)", callback_data=f"admin_assignqr_global_{copied_msg.id}")])

            await callback_query.edit_message_text(
                "🎯 **Assign QR Code**\n\nWhich plan is this QR code for?",
                reply_markup=types.InlineKeyboardMarkup(keyboard)
            )
        else:
            await set_setting(f"{msg_type}_img_channel", db_channel)
            await set_setting(f"{msg_type}_img_id", copied_msg.id)
            await callback_query.edit_message_text(f"✅ Success! This image is now set as the **{msg_type}** image.")
            await callback_query.answer(f"{msg_type} image updated!")
    except Exception as e:
        await callback_query.answer(f"❌ Failed to copy image: {e}", show_alert=True)

@Client.on_callback_query(filters.regex("^admin_assignqr_"))
async def admin_assignqr_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if not await is_admin(user_id):
        return

    data = callback_query.data.split("_")
    plan_id = data[2]
    msg_id = int(data[3])

    db_channel = await get_setting("img_db_channel")

    if plan_id == "global":
        await set_setting("qr_channel_id", db_channel)
        await set_setting("qr_message_id", msg_id)
        await callback_query.edit_message_text("✅ Success! This image is now set as the **Global QR Code**.")
    else:
        await plans_col.update_one(
            {"plan_id": plan_id},
            {"$set": {"qr_channel_id": db_channel, "qr_message_id": msg_id}}
        )
        plan = await plans_col.find_one({"plan_id": plan_id})
        await callback_query.edit_message_text(f"✅ Success! This image is now set as the QR code for plan: **{plan['name']}**.")

    await callback_query.answer("QR Code assigned!")

# Plan Management Section

@Client.on_message(filters.command("managesub") & filters.private)
async def managesub_handler(client, message):
    user_id = message.from_user.id
    if not await is_admin(user_id):
        return

    keyboard = types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton("➕ Add Plan", callback_data="admin_add_plan")],
        [types.InlineKeyboardButton("📜 List Plans", callback_data="admin_list_plans")]
    ])
    await message.reply_text("💎 **Subscription Management**\n\nChoose an action:", reply_markup=keyboard)

@Client.on_callback_query(filters.regex("^admin_managesub_back$"))
async def admin_managesub_back_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if not await is_admin(user_id):
        return

    # Clear temp plan when going back to main menu
    await users_col.update_one({"user_id": user_id}, {"$unset": {"temp_plan": "", "state": ""}})

    keyboard = types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton("➕ Add Plan", callback_data="admin_add_plan")],
        [types.InlineKeyboardButton("📜 List Plans", callback_data="admin_list_plans")]
    ])
    await callback_query.edit_message_text("💎 **Subscription Management**\n\nChoose an action:", reply_markup=keyboard)

@Client.on_callback_query(filters.regex("^admin_add_plan$"))
async def admin_add_plan_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if not await is_admin(user_id):
        return

    # Initialize temp plan if not already present
    user = await users_col.find_one({"user_id": user_id})
    if not user or "temp_plan" not in user:
        temp_plan = {"name": None, "days": None, "price": None}
        await users_col.update_one({"user_id": user_id}, {"$set": {"temp_plan": temp_plan, "state": None}})

    await show_plan_creation_menu(callback_query.message, user_id)

async def show_plan_creation_menu(message, user_id):
    user = await users_col.find_one({"user_id": user_id})
    temp = user.get("temp_plan", {})

    name_text = f"✅ Name: {temp.get('name')}" if temp.get('name') else "❌ Name"
    days_text = f"✅ Days: {temp.get('days')}" if temp.get('days') else "❌ Days"
    price_text = f"✅ Price: {temp.get('price')}" if temp.get('price') else "❌ Price"

    keyboard = types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton(name_text, callback_data="admin_set_plan_name")],
        [types.InlineKeyboardButton(days_text, callback_data="admin_set_plan_days")],
        [types.InlineKeyboardButton(price_text, callback_data="admin_set_plan_price")],
        [types.InlineKeyboardButton("✔️ Confirm", callback_data="admin_confirm_plan")],
        [types.InlineKeyboardButton("🔙 Back", callback_data="admin_managesub_back")]
    ])

    text = "🛠 **Plan Editor**\n\nFill all details below and click Confirm."
    await message.edit_text(text, reply_markup=keyboard)

@Client.on_callback_query(filters.regex("^admin_set_plan_"))
async def admin_set_plan_field_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if not await is_admin(user_id):
        return

    field = callback_query.data.split("_")[-1]
    await users_col.update_one({"user_id": user_id}, {"$set": {"state": f"admin_setting_plan_{field}"}})

    await callback_query.answer(f"Please send the {field} now.", show_alert=True)

@Client.on_callback_query(filters.regex("^admin_confirm_plan$"))
async def admin_confirm_plan_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if not await is_admin(user_id):
        return

    user = await users_col.find_one({"user_id": user_id})
    temp = user.get("temp_plan", {})

    if not all([temp.get("name"), temp.get("days"), temp.get("price")]):
        await callback_query.answer("❌ Please fill all details first!", show_alert=True)
        return

    plan_id = temp.get("plan_id") or str(uuid.uuid4())[:8]

    plan_doc = {
        "plan_id": plan_id,
        "name": temp["name"],
        "days": temp["days"],
        "price": float(temp["price"])
    }

    await plans_col.update_one({"plan_id": plan_id}, {"$set": plan_doc}, upsert=True)
    await users_col.update_one({"user_id": user_id}, {"$unset": {"temp_plan": "", "state": ""}})

    await callback_query.answer("✅ Plan saved successfully!", show_alert=True)
    await admin_managesub_back_callback(client, callback_query)

@Client.on_callback_query(filters.regex("^admin_list_plans$"))
async def admin_list_plans_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if not await is_admin(user_id):
        return

    plans = await plans_col.find().to_list(100)
    if not plans:
        await callback_query.answer("No plans found.", show_alert=True)
        return

    keyboard = []
    for plan in plans:
        keyboard.append([
            types.InlineKeyboardButton(f"{plan['name']} (₹{plan['price']})", callback_data=f"admin_view_plan_{plan['plan_id']}")
        ])

    keyboard.append([types.InlineKeyboardButton("🔙 Back", callback_data="admin_managesub_back")])

    await callback_query.edit_message_text("📜 **Existing Plans:**\n\nClick on a plan to edit or delete it.", reply_markup=types.InlineKeyboardMarkup(keyboard))

@Client.on_callback_query(filters.regex("^admin_view_plan_"))
async def admin_view_plan_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if not await is_admin(user_id):
        return

    plan_id = callback_query.data.split("_")[-1]
    plan = await plans_col.find_one({"plan_id": plan_id})

    if not plan:
        await callback_query.answer("Plan not found.", show_alert=True)
        return

    text = f"💎 **Plan Details:**\n\n"
    text += f"🏷 **Name:** {plan['name']}\n"
    text += f"📅 **Days:** {plan['days']}\n"
    text += f"💰 **Price:** ₹{plan['price']}\n"

    keyboard = types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton("📝 Edit", callback_data=f"admin_edit_plan_{plan_id}")],
        [types.InlineKeyboardButton("🗑 Delete", callback_data=f"admin_delete_plan_{plan_id}")],
        [types.InlineKeyboardButton("🔙 Back", callback_data="admin_list_plans")]
    ])

    await callback_query.edit_message_text(text, reply_markup=keyboard)

@Client.on_callback_query(filters.regex("^admin_edit_plan_"))
async def admin_edit_plan_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if not await is_admin(user_id):
        return

    plan_id = callback_query.data.split("_")[-1]
    plan = await plans_col.find_one({"plan_id": plan_id})

    if not plan:
        await callback_query.answer("Plan not found.", show_alert=True)
        return

    temp_plan = {
        "plan_id": plan["plan_id"],
        "name": plan["name"],
        "days": plan["days"],
        "price": plan["price"]
    }

    await users_col.update_one({"user_id": user_id}, {"$set": {"temp_plan": temp_plan, "state": None}})
    await show_plan_creation_menu(callback_query.message, user_id)

@Client.on_callback_query(filters.regex("^admin_delete_plan_"))
async def admin_delete_plan_callback(client, callback_query):
    user_id = callback_query.from_user.id
    if not await is_admin(user_id):
        return

    plan_id = callback_query.data.split("_")[-1]
    await plans_col.delete_one({"plan_id": plan_id})

    await callback_query.answer("✅ Plan deleted!", show_alert=True)
    await admin_list_plans_callback(client, callback_query)

# Input handler for admin settings
@Client.on_message(filters.private & filters.text, group=1)
async def admin_input_handler(client, message):
    user_id = message.from_user.id
    user = await users_col.find_one({"user_id": user_id})

    if not user or not user.get("state") or not user.get("state").startswith("admin_setting_plan_"):
        return

    if not await is_admin(user_id):
        return

    state = user["state"]
    field = state.split("_")[-1]
    text = message.text.strip()
    temp = user.get("temp_plan", {})

    if field == "name":
        temp["name"] = text
    elif field == "days":
        if not text.isdigit():
            await message.reply_text("❌ Please enter a valid number for days.")
            return
        temp["days"] = int(text)
    elif field == "price":
        try:
            temp["price"] = float(text)
        except ValueError:
            await message.reply_text("❌ Please enter a valid number for price.")
            return

    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {"temp_plan": temp, "state": None}}
    )

    # To keep it interactive, we can send the menu again
    keyboard = types.InlineKeyboardMarkup([[types.InlineKeyboardButton("🔙 Back to Plan Editor", callback_data="admin_add_plan")]])
    await message.reply_text(f"✅ Set {field} to: `{text}`", reply_markup=keyboard)
