import os

class PaymentConfig:
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    API_ID = int(os.getenv('API_ID', 0))
    API_HASH = os.getenv('API_HASH')
    MONGO_URI = os.getenv('MONGO_URI')
    MONGO_DB_NAME = os.getenv('MONGO_DB_NAME', 'spicybot')
    PAYMENT_GROUP_ID = int(os.getenv('PAYMENT_GROUP_ID', 0))
    PREMIUM_PRICE_INR = int(os.getenv('PREMIUM_PRICE_INR', 199))
    PREMIUM_DURATION_DAYS = int(os.getenv('PREMIUM_DURATION_DAYS', 30))
    YOUR_UPI_ID = os.getenv('YOUR_UPI_ID')
    QR_CODE_URL = os.getenv('QR_CODE_URL')
    PAYMENT_WINDOW_MINUTES = int(os.getenv('PAYMENT_WINDOW_MINUTES', 10))
    TRANSACTION_VALIDITY_HOURS = int(os.getenv('TRANSACTION_VALIDITY_HOURS', 24))
    PORT = int(os.getenv('PORT', 8080))

config = PaymentConfig()
