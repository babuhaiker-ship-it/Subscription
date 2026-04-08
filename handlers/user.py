from pyrogram import Client, filters, types
from database import users_col, get_setting, is_admin, OWNER_ID, plans_col
from utils.localization import get_string
import asyncio

async def get_user_lang(user_id):
    user = await users_col.find_one({"user_id": user_id})
    return user.get("lang", "en") if user else "en"

async def send_custom_msg(client, user_id, msg_type, text, reply_markup=None):
    img_channel = await get_setting(f"{msg_type}_img_channel")
    img_id = await get_setting(f"{msg_type}_img_id")

    if img_channel and img_id:
        try:
            return await client.copy_message(
                chat_id=user_id,
                from_chat_id=img_channel,
                message_id=img_id,
                caption=text,
                reply_markup=reply_markup
            )
        except Exception as e:
            print(f"Error sending image for {msg_type}: {e}")
            return await client.send_message(user_id, text, reply_markup=reply_markup)
    else:
        return await client.send_message(user_id, text, reply_markup=reply_markup)

@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    lang = await get_user_lang(user_id)

    # Save user if not exists
    await users_col.update_one({"user_id": user_id}, {"$set": {"user_id": user_id}}, upsert=True)

    welcome_text = await get_setting(f"welcome_msg_{lang}", get_string("welcome", lang=lang))
    keyboard = types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton(get_string("btn_get_premium", lang=lang), callback_data="get_premium")],
        [types.InlineKeyboardButton(get_string("btn_change_lang", lang=lang), callback_data="change_lang")]
    ])

    await send_custom_msg(client, user_id, "welcome", welcome_text, reply_markup=keyboard)

@Client.on_callback_query(filters.regex("^change_lang$"))
async def change_lang_handler(client, callback_query):
    lang = await get_user_lang(callback_query.from_user.id)
    keyboard = types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton("English 🇬🇧", callback_data="set_lang_en")],
        [types.InlineKeyboardButton("Hindi 🇮🇳", callback_data="set_lang_hi")]
    ])
    await callback_query.edit_message_text(get_string("select_lang", lang=lang), reply_markup=keyboard)

@Client.on_callback_query(filters.regex("^set_lang_"))
async def set_lang_handler(client, callback_query):
    new_lang = callback_query.data.split("_")[-1]
    await users_col.update_one({"user_id": callback_query.from_user.id}, {"$set": {"lang": new_lang}})

    await callback_query.answer(get_string("lang_set", lang=new_lang))
    # Return to start screen
    welcome_text = await get_setting(f"welcome_msg_{new_lang}", get_string("welcome", lang=new_lang))
    keyboard = types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton(get_string("btn_get_premium", lang=new_lang), callback_data="get_premium")],
        [types.InlineKeyboardButton(get_string("btn_change_lang", lang=new_lang), callback_data="change_lang")]
    ])

    # We delete and resend to support image update if needed
    await callback_query.message.delete()
    await send_custom_msg(client, callback_query.from_user.id, "welcome", welcome_text, reply_markup=keyboard)

@Client.on_callback_query(filters.regex("^get_premium$"))
async def get_premium_handler(client, callback_query):
    user_id = callback_query.from_user.id
    lang = await get_user_lang(user_id)

    plans = await plans_col.find().to_list(100)

    if plans:
        # Show plan selection
        keyboard = []
        for plan in plans:
            keyboard.append([
                types.InlineKeyboardButton(f"{plan['name']} - ₹{plan['price']}", callback_data=f"select_plan_{plan['plan_id']}")
            ])

        await callback_query.edit_message_text(
            get_string("select_plan", lang=lang),
            reply_markup=types.InlineKeyboardMarkup(keyboard)
        )
    else:
        # Fallback to default price
        price = await get_setting("price", 199)
        await show_payment_instructions(client, user_id, lang, price)
        await callback_query.message.delete()

@Client.on_callback_query(filters.regex("^select_plan_"))
async def select_plan_handler(client, callback_query):
    user_id = callback_query.from_user.id
    lang = await get_user_lang(user_id)
    plan_id = callback_query.data.split("_")[-1]

    plan = await plans_col.find_one({"plan_id": plan_id})
    if not plan:
        await callback_query.answer("Plan not found.", show_alert=True)
        return

    # Store selected plan in user doc
    await users_col.update_one({"user_id": user_id}, {"$set": {"selected_plan_id": plan_id}})

    await show_payment_instructions(client, user_id, lang, plan["price"], plan)
    await callback_query.message.delete()

async def show_payment_instructions(client, user_id, lang, price, plan=None):
    upi_id = await get_setting("upi_id", "example@upi")

    pay_text = await get_setting(f"pay_instr_{lang}", get_string("pay_instr", lang=lang, price=price, upi_id=upi_id))
    if "{price}" in pay_text or "{upi_id}" in pay_text:
        try:
            pay_text = pay_text.format(price=price, upi_id=upi_id)
        except:
            pass

    keyboard = types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton(get_string("btn_i_have_paid", lang=lang), callback_data="i_have_paid")]
    ])

    # Prioritize: Plan-specific QR > Instruction Image > Global QR
    instr_channel = None
    instr_id = None

    if plan:
        instr_channel = plan.get("qr_channel_id")
        instr_id = plan.get("qr_message_id")

    if not instr_channel:
        instr_channel = await get_setting("instr_img_channel")
        instr_id = await get_setting("instr_img_id")

    if not instr_channel:
        instr_channel = await get_setting("qr_channel_id")
        instr_id = await get_setting("qr_message_id")

    sent_msg = await send_custom_msg(client, user_id, "instr", pay_text, reply_markup=keyboard)

    if sent_msg and not getattr(sent_msg, "photo", None) and instr_channel and instr_id:
        try:
            await sent_msg.delete()
            sent_msg = await client.copy_message(
                chat_id=user_id,
                from_chat_id=instr_channel,
                message_id=instr_id,
                caption=pay_text,
                reply_markup=keyboard
            )
        except Exception as e:
            print(f"Error copying instruction/QR code: {e}")

    if sent_msg:
        asyncio.create_task(delete_after(sent_msg, 600))

async def delete_after(message, delay):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except:
        pass

@Client.on_message(filters.command("help") & filters.private)
async def help_handler(client, message):
    user_id = message.from_user.id
    lang = await get_user_lang(user_id)

    help_text = get_string("help_user", lang=lang)

    if await is_admin(user_id):
        # Admin also gets admin help
        admin_help_text = get_string("admin_help", lang=lang)
        admin_help_text += "\n/setwelcome <en/hi> <text> - Set welcome message"
        admin_help_text += "\n/setsuccess <en/hi> <text> - Set success message"
        admin_help_text += "\n/setinstr <en/hi> <text> - Set payment instructions"
        if user_id == OWNER_ID:
            admin_help_text += "\n/addadmin <user_id> - Add a new admin (Owner only)"
        help_text += f"\n\n--- Admin Section ---\n{admin_help_text}"

    await message.reply_text(help_text)
