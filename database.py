import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI, DB_NAME, MAIN_BOT_DB_NAME, DEFAULT_PRICE, DEFAULT_QR_URL, OWNER_ID

client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]
main_db = client[MAIN_BOT_DB_NAME] if MAIN_BOT_DB_NAME else None

# Collections
users_col = db.users
main_tokens_col = main_db['tokens'] if main_db is not None else None
main_users_col = main_db['users'] if main_db is not None else None
plans_col = db.plans
payments_col = db.payments  # Unclaimed payments from SMS
btc_payments_col = db.btc_payments # Bitcoin invoices & payments
settings_col = db.settings
admins_col = db.admins  # Store admin IDs

# In-memory settings cache for high-throughput read operations
_settings_cache = {}

async def create_db_indexes():
    """Creates database indexes to optimize query performance and enforce uniqueness."""
    try:
        # Users indexes
        await users_col.create_index("user_id", unique=True)
        await users_col.create_index("is_premium")
        await users_col.create_index("premium_until")

        # Plans indexes
        await plans_col.create_index("plan_id", unique=True)

        # Payments indexes
        await payments_col.create_index([("txn_id", 1), ("amount", 1)])
        await payments_col.create_index("is_claimed")
        await payments_col.create_index("claimed_by")

        # Bitcoin Payments indexes
        await btc_payments_col.create_index([("user_id", 1), ("plan_id", 1), ("is_claimed", 1)])
        await btc_payments_col.create_index("address")
        await btc_payments_col.create_index("expires_at")

        # Settings index
        await settings_col.create_index("key", unique=True)

        # Admins index
        await admins_col.create_index("user_id", unique=True)
    except Exception as e:
        print(f"Warning: Exception while creating DB indexes: {e}")

async def init_settings():
    """Initializes default settings in the database if not present."""
    default_settings = {
        "price": DEFAULT_PRICE,
        "price_usd": 3.99,
        "qr_url": DEFAULT_QR_URL,
        "btc_xpub": "",
        "btc_address_index": 0,
        "btc_expiry_minutes": 60,
        "welcome_msg_en": "Welcome to **Payment Bot**! 💎\n\nGet exclusive access to premium content, special features, and more by joining our premium plan.",
        "welcome_msg_hi": "**पेमेंट बॉट** में आपका स्वागत है! 💎\n\nहमारे प्रीमियम प्लान में शामिल होकर विशेष सामग्री और सुविधाओं तक पहुँच प्राप्त करें।",
        "success_msg_en": "🎉 **Payment Verified!**\n\nYou now have premium access. Send /start to begin!",
        "success_msg_hi": "🎉 **भुगतान सत्यापित!**\n\nअब आपके पास प्रीमियम एक्सेस है। शुरू करने के लिए /start भेजें!",
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
        if key in ["welcome_msg_en", "welcome_msg_hi", "success_msg_en", "success_msg_hi"]:
            await settings_col.update_one({"key": key}, {"$set": {"value": value}}, upsert=True)
        else:
            await settings_col.update_one({"key": key}, {"$setOnInsert": {"value": value}}, upsert=True)

async def get_setting(key, default=None):
    if key in _settings_cache:
        return _settings_cache[key]
    setting = await settings_col.find_one({"key": key})
    val = setting["value"] if setting else default
    _settings_cache[key] = val
    return val

async def set_setting(key, value):
    _settings_cache[key] = value
    await settings_col.update_one({"key": key}, {"$set": {"value": value}}, upsert=True)

async def get_and_inc_btc_index():
    """Atomically retrieves and increments the BTC address derivation index."""
    res = await settings_col.find_one_and_update(
        {"key": "btc_address_index"},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=True
    )
    new_val = res.get("value", 1)
    _settings_cache["btc_address_index"] = new_val
    return new_val - 1

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
