import re
import asyncio
import logging
from pyrogram.errors import MessageIdInvalid

logger = logging.getLogger(__name__)

def parse_sms(text: str):
    text = text.lower()

    # Improved regex for amount and transaction ID
    amount_match = re.search(r'(?:rs|inr)\.?\s*([\d,]+\.?\d*)', text)
    if not amount_match:
        return None
    amount = float(amount_match.group(1).replace(',', ''))

    txn_id_match = re.search(r'(?:txn|transaction|trxn|payment)\s*(?:id|ref no|ref|id is|no):?\s*(\w+)|utr:?\s*(\d+)', text)
    if not txn_id_match:
        return None
    txn_id = next((g for g in txn_id_match.groups() if g is not None), None)

    if amount and txn_id:
        return {"amount": amount, "txn_id": txn_id}
    return None

async def send_and_schedule_deletion(app, chat_id: int, text: str, markup, delay_seconds: int):
    try:
        sent_message = await app.send_message(chat_id, text, reply_markup=markup, disable_web_page_preview=True)
        await asyncio.sleep(delay_seconds)
        await sent_message.delete()
        logger.info(f"Auto-deleted payment message {sent_message.id} for user {chat_id}.")
    except MessageIdInvalid:
        logger.warning(f"Message was already deleted by the user or another process.")
    except Exception as e:
        logger.error(f"Error in send_and_schedule_deletion: {e}")
