import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI, DB_NAME, DEFAULT_PRICE, DEFAULT_UPI_ID, DEFAULT_QR_URL

client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]

# Collections
users_col = db.users
payments_col = db.payments  # Unclaimed payments from SMS
settings_col = db.settings
admins_col = db.admins  # Store admin IDs

async def init_settings():
    """Initializes default settings in the database if not present."""
    default_settings = {
        "price": DEFAULT_PRICE,
        "upi_id": DEFAULT_UPI_ID,
        "qr_url": DEFAULT_QR_URL,
        "welcome_msg": "Welcome to the Premium Bot! 💎 Click below to get access.",
        "success_msg": "🎉 Payment Verified! Go to @SpicyNyraa_bot and send /start",
        "qr_channel_id": None, # Channel where QR images are stored
        "qr_message_id": None # Message ID of the QR image
    }
    for key, value in default_settings.items():
        await settings_col.update_one({"key": key}, {"$setOnInsert": {"value": value}}, upsert=True)

async def get_setting(key, default=None):
    setting = await settings_col.find_one({"key": key})
    return setting["value"] if setting else default

async def set_setting(key, value):
    await settings_col.update_one({"key": key}, {"$set": {"value": value}}, upsert=True)

async def is_admin(user_id):
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
