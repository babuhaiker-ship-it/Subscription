import asyncio
import logging
from pyrogram.errors import MessageIdInvalid

logger = logging.getLogger(__name__)

class PaymentQueue:
    def __init__(self, processor_func):
        self.queue = asyncio.Queue()
        self.processor_func = processor_func
        self.is_processing = False
        self._worker_task = None

    async def add(self, user_id, client, callback_query):
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self.worker())
        await self.queue.put((user_id, client, callback_query))

    async def worker(self):
        while True:
            user_id, client, callback_query = await self.queue.get()
            self.is_processing = True
            try:
                await self.processor_func(user_id, client, callback_query)
            except Exception as e:
                logger.error(f"Error processing payment for user {user_id}: {e}")
            finally:
                self.is_processing = False
                self.queue.task_done()

    def get_wait_time(self):
        # Current processing + items in queue
        count = self.queue.qsize()
        if self.is_processing:
            count += 1
        return count * 2

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
