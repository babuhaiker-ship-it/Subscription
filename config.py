import os

class PaymentConfig:
    BOT_TOKEN = os.getenv('BOT_TOKEN', '7673807124:AAETa1Bty4C4CU0De1PuP31FwMXLmgPwQLk')
    API_ID = int(os.getenv('API_ID', '29800015'))
    API_HASH = os.getenv('API_HASH', 'c8f37108be31ab9ea2818bfe533fbb6f')
    MONGO_URI = os.getenv('MONGO_URI', 'mongodb+srv://Pyasipriya:00pEcao9sYhNC5VQ@cluster0.2dfenf7.mongodb.net/spicybot?retryWrites=true&w=majority&appName=Cluster0')
    MONGO_DB_NAME = os.getenv('MONGO_DB_NAME', 'spicybot')
    PAYMENT_GROUP_ID = int(os.getenv('PAYMENT_GROUP_ID', '-1002685844988'))
    PREMIUM_PRICE_INR = float(os.getenv('PREMIUM_PRICE_INR', '199'))
    PREMIUM_DURATION_DAYS = int(os.getenv('PREMIUM_DURATION_DAYS', '30'))
    YOUR_UPI_ID = os.getenv('YOUR_UPI_ID', "your-upi-id@oksbi")
    QR_CODE_URL = os.getenv('QR_CODE_URL', "https://i.postimg.cc/YOUR_QR_CODE.png")
    PAYMENT_WINDOW_MINUTES = int(os.getenv('PAYMENT_WINDOW_MINUTES', '10'))
    TRANSACTION_VALIDITY_HOURS = int(os.getenv('TRANSACTION_VALIDITY_HOURS', '24'))

config = PaymentConfig()
