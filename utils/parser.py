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
# Reordered to match longer strings first to avoid "Txn ID" capturing "ID" as the value
# Added specific focus on UTR and longer IDs to handle messages with multiple ID types (like FamApp)
TXN_ID_REGEX = re.compile(r"(?:UTR|Ref No|Ref|Transaction ID|Txn ID|Txn|ID|No):?\s*([A-Za-z0-9]{10,})", re.IGNORECASE)

# Secondary regex specifically for UTR if first one fails to be specific
UTR_ONLY_REGEX = re.compile(r"UTR\s*:\s*([0-9]+)", re.IGNORECASE)

# More comprehensive pattern for generic Indian bank SMS
# "credited with INR 199.00. Txn ID: 423567890123"
# "Rs 199.00 credited to... UTR 423567890123"

def parse_sms(text: str):
    """
    Parses SMS text to extract amount and transaction ID.
    Returns (amount, txn_id) if found, else (None, None).
    """
    amount_match = AMOUNT_REGEX.search(text)

    # Try UTR specific regex first (higher priority for accuracy)
    utr_match = UTR_ONLY_REGEX.search(text)
    if utr_match:
        txn_id = utr_match.group(1)
    else:
        txn_id_match = TXN_ID_REGEX.search(text)
        txn_id = txn_id_match.group(1) if txn_id_match else None

    if amount_match and txn_id:
        try:
            amount = float(amount_match.group(1))
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
