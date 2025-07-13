import os
import re
import asyncio
from datetime import datetime, timedelta
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from PIL import Image, ImageDraw, ImageFont
import qrcode
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Bot Configuration ---
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
    QR_CODE_DIR = "generated_qrcodes"
    DELETE_DELAY = 600 # 10 minutes

    # --- SIMULATION ONLY ---
    # In a real system, these would come from your payment gateway's confirmed transactions.
    # For demonstration, hardcode some "valid" transactions.
    # Key: TXN_ID, Value: Amount
    SIMULATED_VALID_TRANSACTIONS = {
        "TXN69WEEKLY123": 69.00,
        "TXN199MONTHLY456": 199.00,
        "TXN69PARTIAL789": 30.00, # Example of a partial payment
        "TXN199OVERPAY111": 250.00, # Example of an overpayment
    }
    # For a more persistent "local system" for TXN IDs:
    # You could periodically fetch dummy successful TXN IDs from a file or another service
    # that simulates payment confirmations, and insert them into transactions_collection.
    # For this version, we'll just check against `SIMULATED_VALID_TRANSACTIONS` and `transactions_collection`.


# Validate essential configuration
if not all([BotConfig.BOT_TOKEN, BotConfig.API_ID, BotConfig.API_HASH, BotConfig.MONGO_URI, BotConfig.UPI_ID]):
    logger.error("Missing essential environment variables (BOT_TOKEN, API_ID, API_HASH, MONGO_URI, UPI_ID). Please set them in .env.")
    exit(1)

# Ensure QR code directory exists
os.makedirs(BotConfig.QR_CODE_DIR, exist_ok=True)

# --- Database ---
mongo_client = AsyncIOMotorClient(BotConfig.MONGO_URI)
db = mongo_client[BotConfig.MONGO_DB_NAME]
users_collection = db.users # Stores user subscription status
transactions_collection = db.transactions # Stores "confirmed" transactions from the simulated system


# Create indexes for faster lookup
async def create_db_indexes():
    await users_collection.create_index("is_premium")
    await users_collection.create_index("premium_expiry")
    await transactions_collection.create_index("txn_id", unique=True) # Ensures unique TXN IDs
    logger.info("MongoDB indexes ensured.")


# --- Pyrogram Client ---
app = Client("premium_bot", api_id=BotConfig.API_ID, api_hash=BotConfig.API_HASH, bot_token=BotConfig.BOT_TOKEN)

# --- Helper: Generate QR Code with Amount and Plan ---
async def generate_qr_code_image(upi_id, amount, plan_name, user_id):
    # This UPI link is for display/scanning. It doesn't trigger real payment processing in this bot.
    upi_link = f"upi://pay?pa={upi_id}&pn=NyraaExclusive&am={amount:.2f}&cu=INR"

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(upi_link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    draw = ImageDraw.Draw(img)
    try:
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" # Common path on Linux
        if os.path.exists(font_path):
            font = ImageFont.truetype(font_path, 24)
        else:
            font = ImageFont.load_default()
            logger.warning("Default font used. Consider installing 'DejaVuSans-Bold.ttf' or similar for better QR text.")
    except Exception as e:
        logger.error(f"Error loading font: {e}. Using default.")
        font = ImageFont.load_default()

    text_lines = [
        f"Amount: ₹{amount:.2f}",
        f"Plan: {plan_name.capitalize()}",
        f"UPI ID: {upi_id}"
    ]
    
    line_height = font.getbbox("Sample Text")[3] - font.getbbox("Sample Text")[1]
    total_text_height = len(text_lines) * line_height + 20

    img_width, img_height = img.size
    new_img = Image.new("RGB", (img_width, img_height + int(total_text_height)), "white")
    new_img.paste(img, (0, 0))

    draw = ImageDraw.Draw(new_img)
    y_offset = img_height + 10

    for line in text_lines:
        bbox = draw.textbbox((0,0), line, font=font)
        text_width = bbox[2] - bbox[0]
        draw.text(((img_width - text_width) / 2, y_offset), line, font=font, fill=(0, 0, 0))
        y_offset += line_height + 5

    path = os.path.join(BotConfig.QR_CODE_DIR, f"qr_{user_id}_{plan_name}.png")
    new_img.save(path)
    return path, upi_link

# --- SIMULATED PAYMENT VERIFICATION ---
async def _simulate_payment_verification(txn_id: str, expected_amount: float) -> tuple[bool, float]:
    """
    SIMULATES payment verification.
    In a real application, this function would call a Payment Gateway API
    to check the transaction status and amount.

    :param txn_id: The transaction ID provided by the user.
    :param expected_amount: The amount the user was supposed to pay.
    :return: A tuple (is_valid: bool, received_amount: float).
    """
    logger.info(f"Simulating payment verification for TXN ID: {txn_id}, Expected: ₹{expected_amount:.2f}")

    # Step 1: Check against hardcoded simulated valid transactions
    simulated_amount = BotConfig.SIMULATED_VALID_TRANSACTIONS.get(txn_id)
    if simulated_amount is not None:
        if simulated_amount == expected_amount:
            logger.info(f"SIMULATION: Full payment match for {txn_id}")
            return True, simulated_amount
        elif simulated_amount < expected_amount:
            logger.info(f"SIMULATION: Partial payment for {txn_id}. Paid {simulated_amount}, Expected {expected_amount}")
            return True, simulated_amount # Indicate partial but valid TXN
        else: # Overpayment
            logger.info(f"SIMULATION: Overpayment for {txn_id}. Paid {simulated_amount}, Expected {expected_amount}")
            return True, simulated_amount # Indicate overpayment but valid TXN

    # Step 2: Check if this TXN ID has already been "confirmed" and is available in our local transactions collection
    # (This simulates the group monitor or a batch import of TXN IDs from a source)
    confirmed_txn = await transactions_collection.find_one({"txn_id": txn_id, "used_by": None})
    if confirmed_txn:
        actual_amount = confirmed_txn.get("amount", 0.0)
        logger.info(f"SIMULATION: Found in local 'confirmed' transactions. TXN: {txn_id}, Amount: {actual_amount}")
        if actual_amount == expected_amount:
            return True, actual_amount
        elif actual_amount < expected_amount:
            return True, actual_amount # Partial payment from local confirmed
        else: # Overpayment
            return True, actual_amount

    logger.info(f"SIMULATION: TXN ID {txn_id} not found as valid or in local 'confirmed' transactions.")
    return False, 0.0

# --- /start Command ---
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    user_name = message.from_user.first_name if message.from_user else "Dear User"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(p["button_text"], callback_data=f"plan_{name}")]
        for name, p in BotConfig.SUBSCRIPTION_PLANS.items()
    ])
    await message.reply_text(
        f"Dear {user_name}, this is Nyraa Exclusive. Here you can buy tokens. "
        "Please select a plan to continue.",
        reply_markup=keyboard
    )

# --- Plan Selection ---
@app.on_callback_query(filters.regex("^plan_"))
async def plan_callback(client, callback):
    await callback.answer() # Acknowledge the callback query immediately

    user_id = callback.from_user.id
    plan_type = callback.data.split("_")[1]

    if plan_type not in BotConfig.SUBSCRIPTION_PLANS:
        return await callback.edit_message_text("❌ Invalid plan selected. Please try again or use /start.")

    plan = BotConfig.SUBSCRIPTION_PLANS[plan_type]
    amount = plan["amount"]

    qr_path, upi_link = await generate_qr_code_image(BotConfig.UPI_ID, amount, plan_type, user_id)

    caption = (
        f"**Selected Plan: {plan_type.capitalize()} (₹{amount:.2f})**\n\n"
        f"1. Scan the QR or click [UPI Link]({upi_link})\n"
        "2. After you have sent the payment, **send your TXN ID to confirm.**"
    )

    try:
        # Edit the message to show the QR and payment instructions
        await callback.message.edit_reply_markup(reply_markup=None) # Remove previous buttons
        sent_message = await client.send_photo(
            user_id,
            photo=qr_path,
            caption=caption,
            parse_mode="markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel_payment")]])
        )
        os.remove(qr_path) # Delete QR image after sending

        # Store pending transaction info for the user
        await users_collection.update_one(
            {"_id": user_id},
            {"$set": {
                "awaiting_txn": True,
                "expected_plan": plan_type,
                "expected_amount": amount,
                "last_qr_message_id": sent_message.id # To reference if needed
            }},
            upsert=True
        )
        logger.info(f"User {user_id} selected {plan_type} plan. Awaiting TXN ID.")

    except Exception as e:
        logger.error(f"Failed to send QR photo for user {user_id}: {e}")
        if os.path.exists(qr_path):
            os.remove(qr_path) # Clean up generated QR if sending failed
        await callback.edit_message_text("❌ Failed to send payment details. Please try again.")

# --- Handle Transaction ID Submission ---
@app.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def handle_txn_id(client, message):
    user_id = message.from_user.id
    txn_id = message.text.strip()

    # Basic regex for transaction ID (adjust as needed for specific formats)
    if not re.fullmatch(r"^[a-zA-Z0-9]{10,30}$", txn_id):
        return await message.reply_text("❌ Invalid Transaction ID format. Please ensure it's correct.")

    user = await users_collection.find_one({"_id": user_id})

    # Check if the user is in a state where we expect a TXN ID
    if not user or not user.get("awaiting_txn"):
        return await message.reply_text("I'm not expecting a Transaction ID from you right now. Please use /start to select a plan first.")

    expected_plan = user["expected_plan"]
    expected_amount = user["expected_amount"]

    confirm_message = await message.reply_text("🔎 Verifying your payment, please wait...")

    # --- SIMULATED VERIFICATION CALL ---
    # This calls our local simulation function. In a real bot, this would be an API call.
    is_valid_txn, received_amount = await _simulate_payment_verification(txn_id, expected_amount)

    if is_valid_txn:
        if received_amount == expected_amount:
            # Full payment
            expiry = datetime.utcnow() + timedelta(days=BotConfig.SUBSCRIPTION_PLANS[expected_plan]["duration_days"])

            await users_collection.update_one(
                {"_id": user_id},
                {"$set": {"is_premium": True, "premium_expiry": expiry, "active_plan": expected_plan},
                 "$unset": {"awaiting_txn": "", "expected_plan": "", "expected_amount": "", "last_qr_message_id": ""}},
                upsert=True
            )
            # Mark TXN ID as used in our local transactions_collection (if it came from there)
            await transactions_collection.update_one(
                {"txn_id": txn_id, "used_by": None},
                {"$set": {"used_by": user_id, "used_at": datetime.utcnow()}}
            )

            await confirm_message.edit_text("🎉 Payment successful! Premium access granted! Enjoy.")
            logger.info(f"User {user_id} granted premium access for plan {expected_plan} with TXN {txn_id}.")

        elif received_amount < expected_amount:
            # Partial payment
            remaining_amount = expected_amount - received_amount
            user_name = message.from_user.first_name if message.from_user else "Dear User"
            
            # Update expected amount for subsequent partial payment
            await users_collection.update_one(
                {"_id": user_id},
                {"$set": {"expected_amount": remaining_amount, "awaiting_txn": True}} # Keep awaiting TXN
            )
            await confirm_message.edit_text(
                f"You {user_name} have paid partially (₹{received_amount:.2f}). To get full access, send ₹{remaining_amount:.2f} more.\n"
                "Please send the new TXN ID after completing the payment."
            )
            logger.info(f"User {user_id} made partial payment for {expected_plan}. Remaining: ₹{remaining_amount:.2f}")

        else: # received_amount > expected_amount (overpayment)
            # For overpayment, grant access and inform. Refund is typically manual.
            expiry = datetime.utcnow() + timedelta(days=BotConfig.SUBSCRIPTION_PLANS[expected_plan]["duration_days"])

            await users_collection.update_one(
                {"_id": user_id},
                {"$set": {"is_premium": True, "premium_expiry": expiry, "active_plan": expected_plan},
                 "$unset": {"awaiting_txn": "", "expected_plan": "", "expected_amount": "", "last_qr_message_id": ""}},
                upsert=True
            )
            await transactions_collection.update_one(
                {"txn_id": txn_id, "used_by": None},
                {"$set": {"used_by": user_id, "used_at": datetime.utcnow()}}
            )
            await confirm_message.edit_text(
                f"🎉 Payment successful! You paid ₹{received_amount:.2f}, which is more than required. "
                "You have been granted full access. For any refunds on overpayment, please contact support."
            )
            logger.info(f"User {user_id} overpaid for {expected_plan} (Paid: {received_amount}, Expected: {expected_amount}). Access granted.")

    else:
        # Invalid TXN ID
        await confirm_message.edit_text(
            "❌ Invalid TXN ID or payment not found. Please double-check your TXN ID and try again."
        )
        logger.warning(f"User {user_id} submitted invalid TXN ID: {txn_id}")


# --- Cancel Payment Callback ---
@app.on_callback_query(filters.regex("^cancel_payment$"))
async def cancel_payment_callback(client, callback):
    user_id = callback.from_user.id
    # Remove user from awaiting TXN state
    await users_collection.update_one(
        {"_id": user_id},
        {"$unset": {"awaiting_txn": "", "expected_plan": "", "expected_amount": "", "last_qr_message_id": ""}}
    )
    await callback.message.edit_reply_markup(reply_markup=None) # Remove the cancel button
    await callback.edit_message_text("Payment process cancelled. You can restart with /start.")
    logger.info(f"User {user_id} cancelled payment process.")


# --- Manual "Payment Confirmation" for testing the simulated system ---
# This simulates getting a transaction notification for the `transactions_collection`.
# In a real bot, this data would flow from a payment gateway webhook or batch file.
@app.on_message(filters.command("confirm_txn") & filters.private & filters.user(BotConfig.API_ID)) # Only accessible by bot owner for testing
async def manual_confirm_txn(client, message):
    args = message.text.split(maxsplit=2)
    if len(args) != 3:
        return await message.reply_text("Usage: `/confirm_txn <TXN_ID> <AMOUNT>`")
    
    txn_id_to_add = args[1]
    try:
        amount_to_add = float(args[2])
    except ValueError:
        return await message.reply_text("Invalid amount provided.")

    try:
        result = await transactions_collection.insert_one({
            "txn_id": txn_id_to_add,
            "amount": amount_to_add,
            "timestamp": datetime.utcnow(),
            "used_by": None # Mark as unused initially
        })
        await message.reply_text(f"Simulated transaction `{txn_id_to_add}` with amount ₹{amount_to_add:.2f} added to local 'confirmed' database.")
        logger.info(f"Manually added simulated TXN: {txn_id_to_add}, Amount: {amount_to_add}")
    except Exception as e:
        await message.reply_text(f"Failed to add simulated transaction: {e}")
        logger.error(f"Error manually adding TXN {txn_id_to_add}: {e}")


# --- Bot Runner ---
if __name__ == "__main__":
    async def main():
        logger.info("Initializing bot...")
        await create_db_indexes() # Ensure indexes on startup
        
        # You might add some initial dummy data to SIMULATED_VALID_TRANSACTIONS
        # or load from a file for more complex testing scenarios.

        await app.start()
        logger.info("Telegram UPI Subscription Bot started (Simulated Payment Verification).")
        await app.idle() # Keeps the bot running until interrupted

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt).")
    except Exception as e:
        logger.exception("Bot encountered an unhandled error during startup:")
