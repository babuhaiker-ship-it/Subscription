import asyncio
import logging
import uuid
import re
from datetime import datetime, timedelta
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import MessageIdInvalid
from motor.motor_asyncio import AsyncIOMotorClient
from playwright.async_api import async_playwright
import os
import json
import asyncio
from datetime import datetime, timedelta, timezone

# --- Configuration ---
class PaymentConfig:
    BOT_TOKEN = '7673807124:AAETa1Bty4C4CU0De1PuP31FwMXLmgPwQLk'
    API_ID = 29800015
    API_HASH = 'c8f37108be31ab9ea2818bfe533fbb6f'
    MONGO_URI = 'mongodb+srv://Pyasipriya:00pEcao9sYhNC5VQ@cluster0.2dfenf7.mongodb.net/spicybot?retryWrites=true&w=majority&appName=Cluster0'
    MONGO_DB_NAME = 'spicybot'
    ADMIN_ID = 0  # Replace with your actual Telegram Admin ID
    AMAZON_EMAIL = "your-email@example.com"
    AMAZON_PASSWORD = "your-password"
    PREMIUM_PRICE_INR = 199
    PREMIUM_DURATION_DAYS = 30
    SESSION_FILE = "amazon_session.json"
    REDEEM_URL = "https://www.amazon.in/gc/redeem"
    PAYMENT_WINDOW_MINUTES = 15

config = PaymentConfig()

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Pyrogram & MongoDB Client ---
app = Client("payment_bot", api_id=config.API_ID, api_hash=config.API_HASH, bot_token=config.BOT_TOKEN)
mongo_client = AsyncIOMotorClient(config.MONGO_URI)
db = mongo_client[config.MONGO_DB_NAME]
tokens_collection = db['tokens']
incoming_payments_collection = db['incoming_payments']
users_collection = db['users']

# --- State Management ---
user_state = {}
redemption_lock = asyncio.Lock()
otp_future = None

# --- Amazon Automation ---
class AmazonRedeemer:
    def __init__(self, config):
        self.config = config
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None

    async def start(self):
        if not self.playwright:
            self.playwright = await async_playwright().start()

        launch_options = {
            "headless": True, # You can set to False for debugging
            "args": ["--no-sandbox", "--disable-setuid-sandbox"]
        }
        self.browser = await self.playwright.chromium.launch(**launch_options)

        if os.path.exists(self.config.SESSION_FILE):
            with open(self.config.SESSION_FILE, 'r') as f:
                storage_state = json.load(f)
            self.context = await self.browser.new_context(storage_state=storage_state)
        else:
            self.context = await self.browser.new_context()

        self.page = await self.context.new_page()

    async def stop(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None

    async def save_session(self):
        storage = await self.context.storage_state()
        with open(self.config.SESSION_FILE, 'w') as f:
            json.dump(storage, f)

    async def is_logged_in(self):
        try:
            await self.page.goto("https://www.amazon.in/gp/history", timeout=30000)
            # If redirected to sign-in, it's not logged in
            return "signin" not in self.page.url
        except Exception:
            return False

    async def login(self, admin_callback):
        """
        admin_callback is an async function that asks the admin for OTP and returns it.
        """
        await self.page.goto("https://www.amazon.in/ap/signin?openid.pape.max_auth_age=0&openid.return_to=https%3A%2F%2Fwww.amazon.in%2F%3Fref_%3Dnav_signin&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.assoc_handle=inflex&openid.mode=checkid_setup&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0")

        # Email
        await self.page.fill("#ap_email", self.config.AMAZON_EMAIL)
        await self.page.click("#continue")

        # Password
        await self.page.wait_for_selector("#ap_password", timeout=5000)
        await self.page.fill("#ap_password", self.config.AMAZON_PASSWORD)
        await self.page.click("#signInSubmit")

        # Check for OTP or CAPTCHA
        await asyncio.sleep(5)

        if "approval" in self.page.url or "otp" in self.page.url or await self.page.query_selector("#auth-mfa-otpcode"):
            otp = await admin_callback("Amazon needs an OTP. Please send it here:")
            if otp:
                await self.page.fill("#auth-mfa-otpcode", otp)
                await self.page.click("#auth-signin-button")
                await asyncio.sleep(5)

        if await self.is_logged_in():
            await self.save_session()
            return True
        return False

    async def redeem_voucher(self, code):
        try:
            await self.page.goto(self.config.REDEEM_URL, timeout=30000)

            # Check if we need to login again
            if "signin" in self.page.url:
                return {"success": False, "error": "session_expired"}

            await self.page.fill("#gc-redemption-input", code)
            await self.page.click("#gc-redemption-apply-button")

            await asyncio.sleep(3) # Wait for processing

            # Check for success message
            success_box = await self.page.query_selector("#gc-redemption-success")
            if success_box:
                text = await success_box.inner_text()
                # Try to extract amount from text like "₹100.00 has been added..."
                amount_match = re.search(r'(?:₹|rs\.?)\s*([\d,]+\.?\d*)', text)
                amount = 0
                if amount_match:
                    amount = float(amount_match.group(1).replace(',', ''))
                return {"success": True, "amount": amount, "message": text}

            # Check for error message
            error_box = await self.page.query_selector("#gc-redemption-error")
            if error_box:
                error_text = await error_box.inner_text()
                return {"success": False, "error": "invalid_code", "message": error_text.strip()}

            return {"success": False, "error": "unknown", "message": "Could not determine redemption result."}
        except Exception as e:
            logger.error(f"Error during redemption: {e}")
            return {"success": False, "error": "exception", "message": str(e)}

redeemer = AmazonRedeemer(config)

# --- Helper Functions ---

async def add_premium_access(user_id: int, duration_days: int):
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=duration_days)
    token = {
        'token_id': str(uuid.uuid4()),
        'created_at': now,
        'expires_at': expires_at,
        'is_admin_granted': True
    }
    try:
        await tokens_collection.update_one(
            {'user_id': user_id},
            {'$push': {'tokens': token}},
            upsert=True
        )
        await users_collection.update_one(
            {'user_id': user_id},
            {'$set': {'last_premium_check_status': True}},
            upsert=True
        )
        logger.info(f"Premium access granted for user {user_id} for {duration_days} days.")
        return True
    except Exception as e:
        logger.error(f"Failed to grant premium access for user {user_id}: {e}")
        return False

# --- Admin Helper ---

async def admin_otp_callback(prompt):
    global otp_future
    await app.send_message(config.ADMIN_ID, prompt)
    otp_future = asyncio.get_event_loop().create_future()
    try:
        # Wait for 2 minutes for OTP
        otp = await asyncio.wait_for(otp_future, timeout=120)
        return otp
    except asyncio.TimeoutError:
        await app.send_message(config.ADMIN_ID, "❌ OTP timeout. Login failed.")
        return None
    except Exception as e:
        logger.error(f"Error in admin_otp_callback: {e}")
        return None
    finally:
        otp_future = None

# --- Bot Handlers ---

@app.on_message(filters.command("login") & filters.user(config.ADMIN_ID))
async def login_cmd(client, message):
    await message.reply("⏳ Starting Amazon login process...")
    success = await redeemer.login(admin_otp_callback)
    if success:
        await message.reply("✅ Successfully logged into Amazon!")
    else:
        await message.reply("❌ Login failed. Check logs or try again.")

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    user_state.pop(message.from_user.id, None)
    await message.reply(
        "Welcome! Use this bot to get premium access for @SpicyNyraa_bot.\n\n"
        f"**Premium Price:** ₹{config.PREMIUM_PRICE_INR}\n"
        "**Payment Method:** Amazon Pay Gift Card Voucher",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("💰 Buy Premium Access", callback_data="buy_premium")
        ]])
    )

@app.on_callback_query(filters.regex("buy_premium"))
async def buy_premium_callback(client, callback_query):
    await callback_query.message.delete()
    user_id = callback_query.from_user.id

    # Check user balance
    user_doc = await users_collection.find_one({"user_id": user_id}) or {}
    total_paid = user_doc.get("total_paid", 0)
    remaining = max(0, config.PREMIUM_PRICE_INR - total_paid)

    payment_text = (
        f"🎟 **Amazon Pay Gift Card Payment**\n\n"
        f"Price: ₹{config.PREMIUM_PRICE_INR}\n"
        f"You have already paid: ₹{total_paid}\n"
        f"**Amount Remaining:** ₹{remaining}\n\n"
        "Please send the **Amazon Pay Gift Card Voucher Code** here.\n"
        "You can also send a screenshot for reference, but make sure to type or paste the code as text."
    )

    if remaining > 0:
        user_state[user_id] = "awaiting_voucher"
        await client.send_message(user_id, payment_text)
    else:
        await callback_query.answer("You already have enough balance! Type /start to refresh.", show_alert=True)

@app.on_message((filters.text | filters.caption) & filters.private)
async def handle_messages(client, message):
    user_id = message.from_user.id
    text = message.text or message.caption

    # Admin OTP handling
    global otp_future
    if user_id == config.ADMIN_ID and otp_future and not otp_future.done() and text:
        otp_future.set_result(text.strip())
        return

    # User voucher handling
    if user_state.get(user_id) == "awaiting_voucher" and text:
        code_match = re.search(r'[A-Z0-9]{4}-[A-Z0-9]{6}-[A-Z0-9]{4}', text.upper())
        if not code_match:
            # Maybe it's just a raw code without dashes or different format?
            # Amazon codes are usually 14-15 chars?
            # Actually they are often XXXX-XXXXXX-XXXX
            code = text.strip().upper()
        else:
            code = code_match.group(0)

        if len(code) < 10:
            await message.reply("❌ That doesn't look like a valid Amazon voucher code. Please try again.")
            return

        if redemption_lock.locked():
            await message.reply("⏳ Another redemption is in progress. Please wait about 5 minutes and try again.")
            return

        async with redemption_lock:
            wait_msg = await message.reply("⏳ Verifying voucher... please wait. This can take up to 2 minutes.")

            # Check if session is still valid
            if not await redeemer.is_logged_in():
                logger.info("Session expired, attempting silent login...")
                # Try to login without OTP if possible (using saved password)
                # But if OTP is needed, we notify admin
                success = await redeemer.login(admin_otp_callback)
                if not success:
                    await wait_msg.edit_text("❌ System busy or login required. Admin has been notified. Please try again later.")
                    return

            result = await redeemer.redeem_voucher(code)

            if result["success"]:
                amount = result["amount"]
                # Update database
                await users_collection.update_one(
                    {"user_id": user_id},
                    {"$inc": {"total_paid": amount}},
                    upsert=True
                )

                # Log the payment
                await incoming_payments_collection.insert_one({
                    "user_id": user_id,
                    "code": code,
                    "amount": amount,
                    "timestamp": datetime.now(timezone.utc)
                })

                # Check new total
                user_doc = await users_collection.find_one({"user_id": user_id})
                new_total = user_doc.get("total_paid", 0)

                # Notify admin
                admin_msg = (
                    f"💰 **New Payment!**\n\n"
                    f"User: {message.from_user.first_name} (@{message.from_user.username})\n"
                    f"ID: `{user_id}`\n"
                    f"Code: `{code}`\n"
                    f"Amount: ₹{amount}\n"
                    f"User Total: ₹{new_total}"
                )
                await client.send_message(config.ADMIN_ID, admin_msg)

                if new_total >= config.PREMIUM_PRICE_INR:
                    if await add_premium_access(user_id, config.PREMIUM_DURATION_DAYS):
                        # Optionally reset total_paid or subtract 199
                        await users_collection.update_one({"user_id": user_id}, {"$inc": {"total_paid": -config.PREMIUM_PRICE_INR}})
                        await wait_msg.edit_text(f"✅ **Voucher Redeemed!** Added ₹{amount}.\n\n🎉 **Congratulations!** You now have premium access. Total paid: ₹{new_total}.\nGo to @SpicyNyraa_bot and press /start!")
                        user_state.pop(user_id, None)
                    else:
                        await wait_msg.edit_text(f"✅ **Voucher Redeemed!** Added ₹{amount}.\n\n❌ Error granting access. Admin has been notified.")
                else:
                    missing = config.PREMIUM_PRICE_INR - new_total
                    await wait_msg.edit_text(f"✅ **Voucher Redeemed!** Added ₹{amount}.\n\nTotal paid: ₹{new_total}. You still need ₹{missing} more for premium.")
            else:
                # Handle error
                error_msg = result.get("message", "Invalid code or already redeemed.")
                if result.get("error") == "session_expired":
                    await wait_msg.edit_text("❌ System session expired. Admin is logging back in. Please try again in 5 minutes.")
                    await client.send_message(config.ADMIN_ID, "⚠️ Amazon session expired! Use /login to restore.")
                else:
                    await wait_msg.edit_text(f"❌ **Redemption Failed:** {error_msg}")
                    # Log failure
                    fail_msg = (
                        f"❌ **Redemption Failed**\n\n"
                        f"User: {message.from_user.first_name} (@{message.from_user.username})\n"
                        f"ID: `{user_id}`\n"
                        f"Code: `{code}`\n"
                        f"Error: {error_msg}"
                    )
                    await client.send_message(config.ADMIN_ID, fail_msg)

async def main():
    await redeemer.start()
    await app.start()
    logger.info("Bot started.")
    await idle()
    await app.stop()
    await redeemer.stop()

if __name__ == "__main__":
    asyncio.run(main())
