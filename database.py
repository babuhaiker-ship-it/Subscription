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

async def get_price():
    doc = await settings_collection.find_one({'_id': 'price_config'})
    return doc.get('price', config.PREMIUM_PRICE_INR) if doc else config.PREMIUM_PRICE_INR

async def set_price(price: int):
    await settings_collection.update_one(
        {'_id': 'price_config'},
        {'$set': {'price': price}},
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
