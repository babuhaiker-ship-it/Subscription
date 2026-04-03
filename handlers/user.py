from pyrogram import Client, filters, types
from database import users_col, get_setting, set_setting, is_admin, add_admin, get_db_stats
from utils.localization import get_string
import asyncio

async def get_user_lang(user_id):
    user = await users_col.find_one({"user_id": user_id})
    return user.get("lang", "en") if user else "en"

@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    user_id = message.from_user.id
    lang = await get_user_lang(user_id)

    # Save user if not exists
    await users_col.update_one({"user_id": user_id}, {"$set": {"user_id": user_id}}, upsert=True)

    welcome_text = get_string("welcome", lang=lang)
    keyboard = types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton(get_string("btn_get_premium", lang=lang), callback_data="get_premium")],
        [types.InlineKeyboardButton(get_string("btn_change_lang", lang=lang), callback_data="change_lang")]
    ])

    await message.reply_text(welcome_text, reply_markup=keyboard)

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
    welcome_text = get_string("welcome", lang=new_lang)
    keyboard = types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton(get_string("btn_get_premium", lang=new_lang), callback_data="get_premium")],
        [types.InlineKeyboardButton(get_string("btn_change_lang", lang=new_lang), callback_data="change_lang")]
    ])
    await callback_query.edit_message_text(welcome_text, reply_markup=keyboard)

@Client.on_callback_query(filters.regex("^get_premium$"))
async def get_premium_handler(client, callback_query):
    user_id = callback_query.from_user.id
    lang = await get_user_lang(user_id)

    price = await get_setting("price", 199)
    upi_id = await get_setting("upi_id", "example@upi")

    pay_text = get_string("pay_instr", lang=lang, price=price, upi_id=upi_id)
    keyboard = types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton(get_string("btn_i_have_paid", lang=lang), callback_data="i_have_paid")]
    ])

    # Try to send QR image if configured
    qr_channel_id = await get_setting("qr_channel_id")
    qr_message_id = await get_setting("qr_message_id")

    sent_msg = None
    if qr_channel_id and qr_message_id:
        try:
            # Copy QR image from the specified channel/message
            sent_msg = await client.copy_message(
                chat_id=user_id,
                from_chat_id=qr_channel_id,
                message_id=qr_message_id,
                caption=pay_text,
                reply_markup=keyboard
            )
            # Delete the previous message (welcome screen)
            await callback_query.message.delete()
        except Exception as e:
            print(f"Error copying QR code: {e}")
            # Fallback to plain text if QR code fails
            sent_msg = await callback_query.edit_message_text(pay_text, reply_markup=keyboard)
    else:
        sent_msg = await callback_query.edit_message_text(pay_text, reply_markup=keyboard)

    # Auto-delete instruction after 10 minutes (600 seconds)
    if sent_msg:
        await asyncio.sleep(600)
        try:
            await sent_msg.delete()
        except:
            pass
