import re
from datetime import datetime, timedelta
import pytz
from database import payments_col

# Common Indian bank SMS patterns for amount and transaction ID/UTR
# "INR 199.00 credited... Txn: 423567890123"
# "Rs 199.00... Ref: 423567890123"
# "Money received... UTR: 423567890123"

# Regular expressions for Amount
AMOUNT_REGEX = re.compile(r"(?:INR|Rs\.?|Amount:?|₹)\s*(\d+(?:\.\d{1,2})?)", re.IGNORECASE)
# Regular expressions for Transaction ID / UTR / Ref No
TXN_ID_REGEX = re.compile(r"(?:Txn|Ref|UTR|Transaction ID|ID|No):?\s*([A-Za-z0-9]+)", re.IGNORECASE)

# More comprehensive pattern for generic Indian bank SMS
# "credited with INR 199.00. Txn ID: 423567890123"
# "Rs 199.00 credited to... UTR 423567890123"

def parse_sms(text: str):
    """
    Parses SMS text to extract amount and transaction ID.
    Returns (amount, txn_id) if found, else (None, None).
    """
    amount_match = AMOUNT_REGEX.search(text)
    txn_id_match = TXN_ID_REGEX.search(text)

    if amount_match and txn_id_match:
        try:
            amount = float(amount_match.group(1))
            txn_id = txn_id_match.group(1)
            return amount, txn_id
        except (ValueError, IndexError):
            pass
    return None, None

async def store_payment(amount: float, txn_id: str):
    """
    Stores the parsed payment in MongoDB.
    Prevents duplicates by checking txn_id.
    """
    # Check if this txn_id already exists to prevent duplicate processing
    existing = await payments_col.find_one({"txn_id": txn_id})
    if existing:
        return False, "Duplicate Transaction ID"

    # Store new payment
    payment_data = {
        "amount": amount,
        "txn_id": txn_id,
        "is_claimed": False,
        "received_at": datetime.now(pytz.utc),
        "claimed_by": None,
        "claimed_at": None
    }
    await payments_col.insert_one(payment_data)
    return True, "Payment Stored"
