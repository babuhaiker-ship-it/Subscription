from motor.motor_asyncio import AsyncIOMotorClient
from config import config
from datetime import datetime, timedelta
import uuid
import logging

logger = logging.getLogger(__name__)

# --- MongoDB Client ---
mongo_client = AsyncIOMotorClient(config.MONGO_URI)
db = mongo_client[config.MONGO_DB_NAME]
tokens_collection = db['tokens']
incoming_payments_collection = db['incoming_payments']
users_collection = db['users']

async def get_user_state(user_id: int):
    user = await users_collection.find_one({'user_id': user_id})
    return user.get('state') if user else None

async def set_user_state(user_id: int, state: str):
    await users_collection.update_one(
        {'user_id': user_id},
        {'$set': {'state': state}},
        upsert=True
    )

async def find_payment_by_txn_id(txn_id: str):
    return await incoming_payments_collection.find_one({"txn_id": txn_id})

async def log_payment(payment_doc: dict):
    await incoming_payments_collection.insert_one(payment_doc)

async def find_and_claim_payment(txn_id: str, amount: float, user_id: int, valid_time_window):
    claimed_payment = await incoming_payments_collection.find_one_and_update(
        {
            "txn_id": txn_id,
            "amount": amount,
            "is_claimed": False,
            "received_at": {"$gte": valid_time_window}
        },
        {
            "$set": {
                "is_claimed": True,
                "claimed_by_user_id": user_id,
                "claimed_at": datetime.utcnow()
            }
        }
    )
    return claimed_payment

async def find_payment(txn_id: str, amount: float):
    return await incoming_payments_collection.find_one({"txn_id": txn_id, "amount": amount})

async def add_premium_access(user_id: int, duration_days: int):
    now = datetime.utcnow()
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
