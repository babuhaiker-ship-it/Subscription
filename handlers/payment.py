from pyrogram import Client, filters, types
from database import users_col, payments_col, get_setting
from utils.localization import get_string
from datetime import datetime, timedelta
import pytz
import asyncio

# Helper to get user's language
from handlers.user import get_user_lang

@Client.on_callback_query(filters.regex("^i_have_paid$"))
async def i_have_paid_handler(client, callback_query):
    user_id = callback_query.from_user.id
    lang = await get_user_lang(user_id)
    price = await get_setting("price", 199)

    ask_txn_text = get_string("ask_txn", lang=lang, price=price)

    # Update user state to 'awaiting_payment'
    await users_col.update_one({"user_id": user_id}, {"$set": {"state": "awaiting_payment"}})

    await callback_query.message.reply_text(ask_txn_text)
    await callback_query.answer()

@Client.on_message(filters.private & filters.text & ~filters.command(["start", "admin", "stats", "setprice", "setupi", "setqr", "help", "help_admin", "setwelcome", "setsuccess", "setinstr", "addadmin"]))
async def payment_submission_handler(client, message):
    user_id = message.from_user.id
    user = await users_col.find_one({"user_id": user_id})

    if not user or user.get("state") != "awaiting_payment":
        return

    lang = await get_user_lang(user_id)
    price = await get_setting("price", 199)

    # Try to extract txn_id and amount from user message
    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.reply_text(get_string("error_invalid_format", lang=lang, price=price))
        return

    user_txn_id = parts[0]
    try:
        user_amount = float(parts[1])
    except ValueError:
        await message.reply_text(get_string("error_invalid_format", lang=lang, price=price))
        return

    # User input validation
    if user_amount != float(price):
        await message.reply_text(get_string("error_amount", lang=lang, price=price))
        return

    # Bot verification message
    verifying_msg = await message.reply_text(get_string("verifying", lang=lang))
    await asyncio.sleep(2) # Human-like delay

    # Atomic find and claim operation
    # 1. Find a payment that matches the txn_id and amount
    # 2. Check if it's already claimed
    # 3. Check if it's not older than 24 hours

    one_day_ago = datetime.now(pytz.utc) - timedelta(hours=24)

    query = {
        "txn_id": user_txn_id,
        "amount": user_amount,
        "is_claimed": False,
        "received_at": {"$gte": one_day_ago}
    }

    update = {
        "$set": {
            "is_claimed": True,
            "claimed_by": user_id,
            "claimed_at": datetime.now(pytz.utc)
        }
    }

    # Atomically find and update the payment record
    claimed_payment = await payments_col.find_one_and_update(query, update)

    if claimed_payment:
        # Payment found and claimed! Grant premium
        premium_expiry = datetime.now(pytz.utc) + timedelta(days=30)

        await users_col.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "is_premium": True,
                    "premium_until": premium_expiry,
                    "state": None # Clear state
                }
            }
        )

        success_text = await get_setting(f"success_msg_{lang}", get_string("success", lang=lang))

        # Check for success image
        from handlers.user import send_custom_msg
        await verifying_msg.delete()
        await send_custom_msg(client, user_id, "success", success_text)
    else:
        # Check why it failed for better error message
        existing_payment = await payments_col.find_one({"txn_id": user_txn_id})

        if not existing_payment:
            error_text = get_string("error_not_found", lang=lang)
        elif existing_payment.get("is_claimed"):
            error_text = get_string("error_claimed", lang=lang)
        elif existing_payment.get("received_at") < one_day_ago:
            error_text = get_string("error_expired", lang=lang)
        elif existing_payment.get("amount") != user_amount:
            error_text = get_string("error_amount", lang=lang, price=price)
        else:
            error_text = get_string("error_not_found", lang=lang)

        await verifying_msg.edit_text(error_text)
