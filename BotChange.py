# Telegram UPI Subscription Bot (Fixed & Complete)

import os
import re
import asyncio
from datetime import datetime, timedelta
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from PIL import Image, ImageDraw, ImageFont
import qrcode
import logging

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
class BotConfig:
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "7673807124:AAETa1Bty4C4CU0De1PuP31FwMXLmgPwQLk")
    API_ID = int(os.environ.get("API_ID", 29800015))
    API_HASH = os.environ.get("API_HASH", "c8f37108be31ab9ea2818bfe533fbb6f")
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://Pyasipriya:00pEcao9sYhNC5VQ@cluster0.2dfenf7.mongodb.net/spicybot?retryWrites=true&w=majority&appName=Cluster0")
    MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "spicybot")
    UPI_LINK = os.environ.get("UPI_LINK", "upi://pay?pa=you@upi&pn=YourName&mc=0000&tid=00000000000000&tr=YourRef&am=1.00")
    QR_CODE_IMAGE_URL = os.environ.get("QR_CODE_IMAGE_URL", "https://placehold.co/300x300/000000/FFFFFF?text=Scan+QR")
    TXN_GROUP_ID = int(os.environ.get("TXN_GROUP_ID", -1002685844988))
    SUBSCRIPTION_PLANS = {
        "weekly": {"amount": 49, "duration_days": 7},
        "monthly": {"amount": 149, "duration_days": 30},
    }
    PAYMENT_MESSAGE_DELETE_DELAY = 600
    ADMIN_IDS = [123456789]
# --- Database ---
mongo_client = AsyncIOMotorClient(BotConfig.MONGO_URI)
db = mongo_client[BotConfig.MONGO_DB_NAME]
users_collection = db.users
transactions_collection = db.transactions

# --- Pyrogram Client ---
app = Client("premium_bot", api_id=BotConfig.API_ID, api_hash=BotConfig.API_HASH, bot_token=BotConfig.BOT_TOKEN)

# --- Helper: Generate QR Code ---
async def generate_qr_code(upi_id, amount, plan_name, user_id):
    upi_link = f"upi://pay?pa={upi_id}&pn=PremiumBot&am={amount:.2f}&cu=INR"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(upi_link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except IOError:
        font = ImageFont.load_default()

    text = f"Amount: ₹{amount:.2f}\nPlan: {plan_name.capitalize()}"
    text_width, text_height = draw.textsize(text, font=font)
    img_width, img_height = img.size
    new_img = Image.new("RGB", (img_width, img_height + text_height + 20), "white")
    new_img.paste(img, (0, 0))
    draw = ImageDraw.Draw(new_img)
    draw.text(((img_width - text_width) / 2, img_height + 10), text, font=font, fill=(0, 0, 0))

    path = os.path.join(BotConfig.QR_CODE_DIR, f"qr_{user_id}_{plan_name}.png")
    new_img.save(path)
    return path, upi_link

# --- /start Command ---
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(p["button_text"], callback_data=f"plan_{name}")]
        for name, p in BotConfig.SUBSCRIPTION_PLANS.items()
    ])
    await message.reply_text(f"Hi {message.from_user.first_name}!\n\nChoose your premium plan:", reply_markup=keyboard)

# --- Plan Selection ---
@app.on_callback_query(filters.regex("^plan_"))
async def plan_callback(client, callback):
    user_id = callback.from_user.id
    plan_type = callback.data.split("_")[1]

    if plan_type not in BotConfig.SUBSCRIPTION_PLANS:
        return await callback.answer("Invalid plan.", show_alert=True)

    plan = BotConfig.SUBSCRIPTION_PLANS[plan_type]
    qr_path, upi_link = await generate_qr_code(BotConfig.UPI_ID, plan["amount"], plan_type, user_id)

    caption = (
        f"**Selected Plan: {plan_type.capitalize()} (₹{plan['amount']:.2f})**\n\n"
        f"1. Scan the QR or click [UPI Link]({upi_link})\n"
        "2. After payment, reply with your Transaction ID."
    )

    await client.send_photo(user_id, photo=qr_path, caption=caption, parse_mode="markdown")
    os.remove(qr_path)

    await users_collection.update_one(
        {"_id": user_id},
        {"$set": {"current_plan": plan_type, "expected_amount": plan["amount"]}},
        upsert=True
    )

# --- Handle Transaction ID Submission ---
@app.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def handle_txn_id(client, message):
    user_id = message.from_user.id
    txn_id = message.text.strip()

    if not re.fullmatch(r"\d{10,20}", txn_id):
        return await message.reply_text("❌ Invalid Transaction ID format.")

    user = await users_collection.find_one({"_id": user_id})
    if not user or "current_plan" not in user:
        return await message.reply_text("❌ Please select a plan using /start first.")

    plan_type = user["current_plan"]
    expected_amount = user["expected_amount"]
    txn = await transactions_collection.find_one({"txn_id": txn_id, "amount": expected_amount, "used_by": {"$exists": False}})

    if not txn:
        return await message.reply_text("❌ Transaction not found or already used.")

    expiry = datetime.utcnow() + timedelta(days=BotConfig.SUBSCRIPTION_PLANS[plan_type]["duration_days"])

    await users_collection.update_one(
        {"_id": user_id},
        {"$set": {"is_premium": True, "premium_expiry": expiry, "active_plan": plan_type}},
        upsert=True
    )

    await transactions_collection.update_one(
        {"_id": txn["_id"]},
        {"$set": {"used_by": user_id, "used_at": datetime.utcnow()}}
    )

    await message.reply_text("🎉 Premium access granted! Enjoy.")
    await users_collection.update_one({"_id": user_id}, {"$unset": {"current_plan": "", "expected_amount": ""}})

# --- Group Listener for UPI Confirmation ---
@app.on_message(filters.chat(BotConfig.PAYMENT_GROUP_ID) & filters.text)
async def txn_monitor(client, message):
    txn_match = re.search(r"(?:Txn ID|Ref No|UPI Ref No)[:\s]*(\d{10,20})", message.text, re.I)
    amt_match = re.search(r"(?:INR|Rs\.?)[\s₹]*([\d,.]+)", message.text, re.I)

    if txn_match and amt_match:
        txn_id = txn_match.group(1)
        amount = float(amt_match.group(1).replace(",", ""))
        if not await transactions_collection.find_one({"txn_id": txn_id}):
            await transactions_collection.insert_one({
                "txn_id": txn_id,
                "amount": amount,
                "timestamp": datetime.utcnow(),
                "used_by": None
            })
            await client.send_message(BotConfig.PAYMENT_GROUP_ID, f"✅ Transaction recorded:\n`{txn_id}`\nAmount: ₹{amount:.2f}", parse_mode="markdown")

# --- Bot Runner ---
if __name__ == "__main__":
    async def main():
        await app.start()
        logger.info("Bot started.")
        await app.idle()
    asyncio.run(main())
