import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "premium_bot")
MAIN_BOT_DB_NAME = os.getenv("MAIN_BOT_DB_NAME")
SMS_GROUP_ID = int(os.getenv("SMS_GROUP_ID", "0"))
PORT = int(os.getenv("PORT", "8080"))
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# Default Settings (can be overridden by DB)
DEFAULT_PRICE = 199
DEFAULT_UPI_ID = "example@upi"
DEFAULT_QR_URL = "https://example.com/qr.png"
MAIN_BOT_USERNAME = "@SpicyNyraa_bot"
