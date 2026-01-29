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
users_collection = db['users']
settings_collection = db['settings']

async def get_woohoo_config():
    return await settings_collection.find_one({'_id': 'woohoo_config'})

async def set_woohoo_config(config: dict):
    await settings_collection.update_one(
        {'_id': 'woohoo_config'},
        {'$set': config},
        upsert=True
    )

async def get_gifting_details():
    return await settings_collection.find_one({'_id': 'gifting_details'})

async def set_gifting_details(details: dict):
    await settings_collection.update_one(
        {'_id': 'gifting_details'},
        {'$set': details},
        upsert=True
    )

async def get_user_state(user_id: int):
    user = await users_collection.find_one({'user_id': user_id})
    return user.get('state') if user else None

async def set_user_state(user_id: int, state: str):
    await users_collection.update_one(
        {'user_id': user_id},
        {'$set': {'state': state}},
        upsert=True
    )

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
