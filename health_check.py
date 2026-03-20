from aiohttp import web
import asyncio
import logging

logger = logging.getLogger(__name__)

async def handle(request):
    return web.Response(text="Bot is running!")

async def start_health_check_server():
    app = web.Application()
    app.add_routes([web.get('/', handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    logger.info("Starting health check server on port 8080...")
    await site.start()
