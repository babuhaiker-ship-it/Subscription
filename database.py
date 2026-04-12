import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI, DB_NAME, MAIN_BOT_DB_NAME, DEFAULT_PRICE, DEFAULT_UPI_ID, DEFAULT_QR_URL, OWNER_ID

client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]
main_db = client[MAIN_BOT_DB_NAME] if MAIN_BOT_DB_NAME else None

# Collections
users_col = db.users
main_tokens_col = main_db['tokens'] if main_db is not None else None
plans_col = db.plans
payments_col = db.payments  # Unclaimed payments from SMS
settings_col = db.settings
admins_col = db.admins  # Store admin IDs

async def init_settings():
    """Initializes default settings in the database if not present."""
    default_settings = {
        "price": DEFAULT_PRICE,
        "upi_id": DEFAULT_UPI_ID,
        "qr_url": DEFAULT_QR_URL,
        "welcome_msg_en": "Welcome to **SpicyNyraa's Premium Bot**! 💎\n\nGet exclusive access to premium content, special features, and more by joining our premium plan.",
        "welcome_msg_hi": "**SpicyNyraa के प्रीमियम बॉट** में आपका स्वागत है! 💎\n\nहमारे प्रीमियम प्लान में शामिल होकर विशेष सामग्री और सुविधाओं तक पहुँच प्राप्त करें।",
        "success_msg_en": "🎉 **Payment Verified!**\n\nYou now have 30 days of premium access. Go to @SpicyNyraa_bot and send /start to begin!",
        "success_msg_hi": "🎉 **भुगतान सत्यापित!**\n\nअब आपके पास 30 दिनों का प्रीमियम एक्सेस है। @SpicyNyraa_bot पर जाएं और शुरू करने के लिए /start भेजें!",
        "qr_channel_id": None,
        "qr_message_id": None,
        "welcome_img_channel": None,
        "welcome_img_id": None,
        "success_img_channel": None,
        "success_img_id": None,
        "instr_img_channel": None,
        "instr_img_id": None,
        "img_db_channel": None,
        "sms_group_id": None
    }
    for key, value in default_settings.items():
        await settings_col.update_one({"key": key}, {"$setOnInsert": {"value": value}}, upsert=True)

async def get_setting(key, default=None):
    setting = await settings_col.find_one({"key": key})
    return setting["value"] if setting else default

async def set_setting(key, value):
    await settings_col.update_one({"key": key}, {"$set": {"value": value}}, upsert=True)

async def is_admin(user_id):
    if user_id == OWNER_ID:
        return True
    admin = await admins_col.find_one({"user_id": user_id})
    return admin is not None

async def add_admin(user_id):
    await admins_col.update_one({"user_id": user_id}, {"$set": {"user_id": user_id}}, upsert=True)

async def get_db_stats():
    total_users = await users_col.count_documents({})
    premium_users = await users_col.count_documents({"is_premium": True})
    total_payments = await payments_col.count_documents({"is_claimed": True})
    total_revenue = await payments_col.aggregate([
        {"$match": {"is_claimed": True}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ]).to_list(1)
    revenue = total_revenue[0]["total"] if total_revenue else 0
    return total_users, premium_users, revenue
