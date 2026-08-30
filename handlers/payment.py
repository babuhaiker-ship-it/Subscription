from pyrogram import Client, filters, types
from database import users_col, payments_col, btc_payments_col, get_setting, set_setting, main_tokens_col, plans_col
from utils.localization import get_string
from utils.btc import derive_btc_address, inr_to_btc, usd_to_btc, check_btc_address_transactions
from datetime import datetime, timedelta
import pytz
import asyncio
import uuid
import logging

logger = logging.getLogger(__name__)

@Client.on_callback_query(filters.regex("^pay_btc_"))
async def btc_payment_init_handler(client, callback_query):
    user_id = callback_query.from_user.id
    lang = await get_user_lang(user_id)
    plan_id = callback_query.data.split("_")[-1]

    if plan_id == "default":
        price_inr = await get_setting("price", 199)
        price_usd = await get_setting("price_usd", 3.99)
        days = 30
        plan = {"name": "Monthly Plan", "price": price_inr, "price_usd": price_usd, "days": days, "plan_id": "default"}
    else:
        plan = await plans_col.find_one({"plan_id": plan_id})
        if not plan:
            await callback_query.answer("Plan not found.", show_alert=True)
            return
        price_inr = plan["price"]
        price_usd = plan.get("price_usd", round(price_inr / 88.0, 2))
        days = plan["days"]

    xpub = await get_setting("btc_xpub", "")
    if not xpub:
        await callback_query.answer("❌ Bitcoin payment method is currently disabled or XPUB is not configured by admin.", show_alert=True)
        return
    expiry_minutes = await get_setting("btc_expiry_minutes", 60)

    # Check for existing active unexpired invoice for this user and plan
    now_utc = datetime.now(pytz.utc)
    active_inv = await btc_payments_col.find_one({
        "user_id": user_id,
        "plan_id": plan_id,
        "is_claimed": False,
        "expires_at": {"$gt": now_utc}
    })

    if active_inv:
        btc_address = active_inv["address"]
        btc_amount = active_inv["btc_amount"]
        expiry_dt = active_inv["expires_at"]
        inv_id = str(active_inv["_id"])
    else:
        # Atomic increment of index
        settings_doc = await db_get_and_inc_btc_index() if 'db_get_and_inc_btc_index' in globals() else None
        # Retrieve current index and increment
        curr_index = await get_setting("btc_address_index", 0)
        await set_setting("btc_address_index", curr_index + 1)

        try:
            btc_address = derive_btc_address(xpub, curr_index)
        except Exception as e:
            logger.error(f"Error deriving BTC address: {e}")
            await callback_query.answer("❌ Error generating BTC address. Please contact support.", show_alert=True)
            return

        btc_amount = await usd_to_btc(price_usd)
        expiry_dt = now_utc + timedelta(minutes=expiry_minutes)

        inv_doc = {
            "user_id": user_id,
            "plan_id": plan_id,
            "address": btc_address,
            "address_index": curr_index,
            "btc_amount": btc_amount,
            "price_inr": price_inr,
            "price_usd": price_usd,
            "created_at": now_utc,
            "expires_at": expiry_dt,
            "is_claimed": False
        }
        res = await btc_payments_col.insert_one(inv_doc)
        inv_id = str(res.inserted_id)

    expiry_str = expiry_dt.strftime("%Y-%m-%d %H:%M UTC")
    text = get_string("btc_instr", lang=lang, plan_name=plan["name"], days=days, btc_amount=btc_amount, price_usd=price_usd, address=btc_address, expiry_str=expiry_str)

    keyboard = types.InlineKeyboardMarkup([
        [types.InlineKeyboardButton(get_string("btn_check_btc", lang=lang), callback_data=f"check_btc_{inv_id}")],
        [types.InlineKeyboardButton(get_string("btn_back", lang=lang), callback_data="get_premium")]
    ])

    sent_msg = await callback_query.edit_message_text(text, reply_markup=keyboard)

    # Schedule auto deletion when the invoice expires (e.g., expiry_minutes)
    delay_seconds = int((expiry_dt - now_utc).total_seconds())
    if delay_seconds > 0:
        from handlers.user import delete_after
        asyncio.create_task(delete_after(callback_query.message, delay_seconds))

@Client.on_callback_query(filters.regex("^check_btc_"))
async def check_btc_payment_handler(client, callback_query):
    user_id = callback_query.from_user.id
    lang = await get_user_lang(user_id)
    inv_id = callback_query.data.split("_")[-1]

    from bson import ObjectId
    try:
        invoice = await btc_payments_col.find_one({"_id": ObjectId(inv_id)})
    except Exception:
        invoice = None

    if not invoice:
        await callback_query.answer("❌ Invoice not found.", show_alert=True)
        return

    if invoice.get("is_claimed"):
        await callback_query.answer("✅ This Bitcoin payment has already been verified!", show_alert=True)
        return

    now_utc = datetime.now(pytz.utc)
    if invoice.get("expires_at") and invoice["expires_at"].tzinfo is None:
        invoice["expires_at"] = pytz.utc.localize(invoice["expires_at"])

    if now_utc > invoice["expires_at"]:
        await callback_query.answer("❌ This Bitcoin payment invoice has expired. Please select a plan again.", show_alert=True)
        return

    await callback_query.answer("⏳ Checking Bitcoin network for your transaction...", show_alert=False)

    btc_address = invoice["address"]
    req_btc = invoice["btc_amount"]
    req_sats = int(req_btc * 1e8)

    txs = await check_btc_address_transactions(btc_address)

    valid_tx = None
    for tx in txs:
        # Require received satoshis to match (allow small margin for roundings)
        if tx["value_sats"] >= req_sats * 0.98:
            valid_tx = tx
            break

    if not valid_tx:
        await callback_query.answer(f"⚠️ No payment received yet on {btc_address[:10]}... Please try again after sending BTC.", show_alert=True)
        return

    # Claim the payment atomically
    res = await btc_payments_col.update_one(
        {"_id": invoice["_id"], "is_claimed": False},
        {"$set": {
            "is_claimed": True,
            "claimed_by": user_id,
            "claimed_at": now_utc,
            "txid": valid_tx["txid"]
        }}
    )

    if res.modified_count == 0:
        await callback_query.answer("⚠️ Payment already processed.", show_alert=True)
        return

    # Grant Premium Access
    plan_id = invoice["plan_id"]
    plan = await plans_col.find_one({"plan_id": plan_id})
    days = plan["days"] if plan else 30

    premium_expiry = now_utc + timedelta(days=days)

    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {
            "is_premium": True,
            "premium_until": premium_expiry,
            "state": None
        }}
    )

    # Sync with main bot database
    token_doc = {
        'token_id': str(uuid.uuid4()),
        'created_at': now_utc,
        'expires_at': premium_expiry,
        'is_admin_granted': True
    }
    if main_tokens_col is not None:
        try:
            await main_tokens_col.update_one(
                {'user_id': user_id},
                {'$push': {'tokens': token_doc}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Failed to write premium token to main bot DB for BTC user {user_id}: {e}")

    success_text = await get_setting(f"success_msg_{lang}", get_string("success", lang=lang))
    from handlers.user import send_custom_msg
    await send_custom_msg(client, user_id, "success", success_text)

# Helper to get user's language
from handlers.user import get_user_lang

@Client.on_callback_query(filters.regex("^i_have_paid$"))
async def i_have_paid_handler(client, callback_query):
    user_id = callback_query.from_user.id
    lang = await get_user_lang(user_id)

    user = await users_col.find_one({"user_id": user_id})
    plan_id = user.get("selected_plan_id")
    plan = await plans_col.find_one({"plan_id": plan_id}) if plan_id else None

    price = plan["price"] if plan else await get_setting("price", 199)

    ask_txn_text = get_string("ask_txn", lang=lang, price=price)

    # Update user state to 'awaiting_payment'
    await users_col.update_one({"user_id": user_id}, {"$set": {"state": "awaiting_payment"}})

    await callback_query.message.reply_text(ask_txn_text)
    await callback_query.answer()

@Client.on_message(filters.private & filters.text & ~filters.command(["start", "admin", "stats", "setprice", "setupi", "setqr", "help", "help_admin", "setwelcome", "setsuccess", "setinstr", "addadmin", "managesub"]))
async def payment_submission_handler(client, message):
    user_id = message.from_user.id
    user = await users_col.find_one({"user_id": user_id})

    if not user or user.get("state") != "awaiting_payment":
        return

    lang = await get_user_lang(user_id)

    plan_id = user.get("selected_plan_id")
    plan = await plans_col.find_one({"plan_id": plan_id}) if plan_id else None

    price = plan["price"] if plan else await get_setting("price", 199)
    days = plan["days"] if plan else 30

    # User sends only the Transaction ID / UTR now
    user_txn_id = message.text.strip()

    # Basic validation: Indian UPI UTRs are usually 12 digits, but we can be flexible
    if not user_txn_id or len(user_txn_id) < 8:
        await message.reply_text(get_string("error_invalid_format", lang=lang, price=price))
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
        "amount": float(price), # We match against the bot's current price
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
        # If this payment is part of a group (multiple IDs for same SMS), claim them all
        group_id = claimed_payment.get("group_id")

        # Prepare plan info for recording
        plan_info = {
            "plan_id": plan_id,
            "plan_name": plan["name"] if plan else "Default"
        }

        if group_id:
            await payments_col.update_many(
                {"group_id": group_id, "is_claimed": False},
                {
                    "$set": {
                        "is_claimed": True,
                        "claimed_by": user_id,
                        "claimed_at": datetime.now(pytz.utc),
                        "plan_info": plan_info
                    }
                }
            )
        else:
            # Update the single record we just found
            await payments_col.update_one(
                {"_id": claimed_payment["_id"]},
                {
                    "$set": {
                        "is_claimed": True,
                        "claimed_by": user_id,
                        "claimed_at": datetime.now(pytz.utc),
                        "plan_info": plan_info
                    }
                }
            )

        # Payment found and claimed! Grant premium
        premium_expiry = datetime.now(pytz.utc) + timedelta(days=days)

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

        # Sync with main bot's database
        token_doc = {
            'token_id': str(uuid.uuid4()),
            'created_at': datetime.now(pytz.utc),
            'expires_at': premium_expiry,
            'is_admin_granted': True
        }
        if main_tokens_col is not None:
            try:
                await main_tokens_col.update_one(
                    {'user_id': user_id},
                    {'$push': {'tokens': token_doc}},
                    upsert=True
                )
            except Exception as e:
                logger.error(f"Failed to write premium token to main bot DB for user {user_id}: {e}")
        else:
            logger.warning(f"Main bot DB not configured, skipping sync for user {user_id}")

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
        elif existing_payment.get("amount") != float(price):
            error_text = get_string("error_amount", lang=lang, price=price)
        else:
            error_text = get_string("error_not_found", lang=lang)

        await verifying_msg.edit_text(error_text)
