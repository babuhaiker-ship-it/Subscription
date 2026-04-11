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
TXN_ID_REGEX = re.compile(r"(?:UTR|Ref No|Ref|Transaction ID|Txn ID|Txn|ID|No):?[\s\:]*([A-Za-z0-9]{8,})", re.IGNORECASE)

# Secondary regex specifically for UTR if first one fails to be specific
UTR_ONLY_REGEX = re.compile(r"UTR\s*:\s*([0-9]+)", re.IGNORECASE)

# More comprehensive pattern for generic Indian bank SMS
# "credited with INR 199.00. Txn ID: 423567890123"
# "Rs 199.00 credited to... UTR 423567890123"

def parse_sms(text: str):
    """
    Parses SMS text to extract amount and transaction ID.
    Returns (amount, [txn_ids]) if found, else (None, []).
    """
    # Normalize text by removing asterisks and separators
    text = re.sub(r'[\*\-\=]', ' ', text)
    amount_match = AMOUNT_REGEX.search(text)
    if not amount_match:
        return None, []

    try:
        amount = float(amount_match.group(1))
    except (ValueError, IndexError):
        return None, []

    # Find all potential IDs
    txn_ids = []

    # 1. Try UTR specific
    for match in UTR_ONLY_REGEX.finditer(text):
        if match.group(1) not in txn_ids:
            txn_ids.append(match.group(1))

    # 2. Try general
    for match in TXN_ID_REGEX.finditer(text):
        if match.group(1) not in txn_ids:
            txn_ids.append(match.group(1))

    return amount, txn_ids

async def store_payment(amount: float, txn_ids: list):
    """
    Stores the parsed payment in MongoDB for each unique ID found.
    Uses a group_id to ensure claiming one claims all for that specific SMS.
    """
    if not txn_ids:
        return False, "No Transaction IDs found"

    # Check if ANY of these IDs already exist
    existing = await payments_col.find_one({"txn_id": {"$in": txn_ids}})
    if existing:
        return False, "Duplicate Transaction ID detected"

    import uuid
    group_id = str(uuid.uuid4())
    received_at = datetime.now(pytz.utc)

    for tid in txn_ids:
        payment_data = {
            "amount": amount,
            "txn_id": tid,
            "group_id": group_id, # Link multiple IDs from same SMS
            "is_claimed": False,
            "received_at": received_at,
            "claimed_by": None,
            "claimed_at": None
        }
        await payments_col.insert_one(payment_data)

    return True, f"Stored {len(txn_ids)} ID(s) for ₹{amount}"
