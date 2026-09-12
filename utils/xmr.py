import requests
import logging
import asyncio

logger = logging.getLogger(__name__)

def _fetch_xmr_price_usd_sync() -> float:
    try:
        res = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=monero&vs_currencies=usd", timeout=5)
        if res.status_code == 200:
            data = res.json()
            if "monero" in data and "usd" in data["monero"]:
                return float(data["monero"]["usd"])
    except Exception as e:
        logger.warning(f"CoinGecko XMR API error: {e}")

    try:
        res = requests.get("https://api.kraken.com/0/public/Ticker?pair=XMRUSD", timeout=5)
        if res.status_code == 200:
            data = res.json()
            result = data.get("result", {})
            for key in result:
                # 'c' is last closed trade array [price, lot_volume]
                return float(result[key]["c"][0])
    except Exception as e:
        logger.warning(f"Kraken XMR API error: {e}")

    # Fallback default estimate if APIs fail
    return 160.0

async def get_xmr_price_in_usd() -> float:
    return await asyncio.to_thread(_fetch_xmr_price_usd_sync)

async def usd_to_xmr(amount_usd: float) -> float:
    xmr_rate = await get_xmr_price_in_usd()
    if xmr_rate <= 0:
        xmr_rate = 160.0
    xmr_val = amount_usd / xmr_rate
    return round(xmr_val, 8)
