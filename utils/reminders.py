import asyncio
import logging
from datetime import datetime, timedelta
import pytz
from pyrogram import types

logger = logging.getLogger(__name__)

async def start_expiry_reminder_loop(client):
    """
    Background loop that runs periodically to check for upcoming subscription expirations
    and sends 3-day and 1-day warning reminders with a 1-click renewal button.
    """
    while True:
        try:
            await check_and_send_expiry_reminders(client)
        except Exception as e:
            logger.error(f"Error in expiry reminder loop: {e}")
        # Run check every 1 hour
        await asyncio.sleep(3600)

async def check_and_send_expiry_reminders(client):
    from database import users_col
    now_utc = datetime.now(pytz.utc)

    # Find active premium users
    premium_users = await users_col.find({
        "is_premium": True,
        "premium_until": {"$gt": now_utc}
    }).to_list(1000)

    for user in premium_users:
        user_id = user.get("user_id")
        expiry = user.get("premium_until")
        if not expiry or not user_id:
            continue

        if expiry.tzinfo is None:
            expiry = pytz.utc.localize(expiry)

        time_left = expiry - now_utc
        hours_left = time_left.total_seconds() / 3600.0

        reminders_sent = user.get("reminders_sent", [])

        # Check for 3-day reminder (between 48 and 72 hours remaining)
        if 48.0 < hours_left <= 72.0 and "3_day" not in reminders_sent:
            await send_reminder_message(client, user_id, days_left=3, expiry=expiry)
            await users_col.update_one({"_id": user["_id"]}, {"$push": {"reminders_sent": "3_day"}})

        # Check for 1-day reminder (between 0 and 24 hours remaining)
        elif 0.0 < hours_left <= 24.0 and "1_day" not in reminders_sent:
            await send_reminder_message(client, user_id, days_left=1, expiry=expiry)
            await users_col.update_one({"_id": user["_id"]}, {"$push": {"reminders_sent": "1_day"}})

async def send_reminder_message(client, user_id, days_left, expiry):
    from handlers.user import get_user_lang
    from utils.localization import get_string

    lang = await get_user_lang(user_id)
    expiry_str = expiry.strftime("%Y-%m-%d %H:%M UTC")

    text = (
        f"⏳ **Subscription Expiry Reminder**\n\n"
        f"⚠️ Your premium subscription will expire in **{days_left} day{'s' if days_left > 1 else ''}** on `{expiry_str}`.\n\n"
        f"Click below to renew your subscription and keep uninterrupted access!"
    )

    keyboard = types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton("💎 Renew Subscription", callback_data="get_premium")]
    ])

    try:
        await client.send_message(user_id, text, reply_markup=keyboard)
        logger.info(f"Sent {days_left}-day expiry reminder to user {user_id}")
    except Exception as e:
        logger.warning(f"Could not send expiry reminder to user {user_id}: {e}")
