import requests
import logging
import asyncio
from bip_utils import Bip84, Bip84Coins, Bip44, Bip44Coins, Bip49, Bip49Coins, Bip44Changes

logger = logging.getLogger(__name__)

def derive_btc_address(xpub_key: str, index: int = 0) -> str:
    """
    Derives a Bitcoin address from extended public key (xpub/zpub/ypub) at specified index.
    """
    key_str = xpub_key.strip()
    if key_str.startswith("zpub"):
        obj = Bip84.FromExtendedKey(key_str, Bip84Coins.BITCOIN)
    elif key_str.startswith("ypub"):
        obj = Bip49.FromExtendedKey(key_str, Bip49Coins.BITCOIN)
    elif key_str.startswith("xpub"):
        try:
            obj = Bip84.FromExtendedKey(key_str, Bip84Coins.BITCOIN)
        except Exception:
            obj = Bip44.FromExtendedKey(key_str, Bip44Coins.BITCOIN)
    else:
        raise ValueError("Unsupported extended key format. Key must start with xpub, zpub, or ypub.")

    return obj.Change(Bip44Changes.CHAIN_EXT).AddressIndex(index).PublicKey().ToAddress()

def _fetch_btc_price_sync() -> float:
    try:
        res = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=inr", timeout=5)
        if res.status_code == 200:
            data = res.json()
            if "bitcoin" in data and "inr" in data["bitcoin"]:
                return float(data["bitcoin"]["inr"])
    except Exception as e:
        logger.warning(f"CoinGecko API error: {e}")

    try:
        res = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=5)
        if res.status_code == 200:
            usdt_price = float(res.json()["price"])
            return usdt_price * 88.0
    except Exception as e:
        logger.warning(f"Binance API error: {e}")

    return 8000000.0

async def get_btc_price_in_inr() -> float:
    return await asyncio.to_thread(_fetch_btc_price_sync)

async def inr_to_btc(amount_inr: float) -> float:
    btc_rate = await get_btc_price_in_inr()
    if btc_rate <= 0:
        btc_rate = 8000000.0
    btc_val = amount_inr / btc_rate
    return round(btc_val, 8)

def _check_btc_address_sync(address: str):
    try:
        url = f"https://mempool.space/api/address/{address}/txs"
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return []

        txs = res.json()
        received = []
        for tx in txs:
            txid = tx.get("txid")
            confirmed = tx.get("status", {}).get("confirmed", False)
            total_sats = 0
            for vout in tx.get("vout", []):
                if vout.get("scriptpubkey_address") == address:
                    total_sats += vout.get("value", 0)
            if total_sats > 0:
                received.append({
                    "txid": txid,
                    "value_sats": total_sats,
                    "value_btc": total_sats / 1e8,
                    "confirmed": confirmed
                })
        return received
    except Exception as e:
        logger.error(f"Error checking mempool.space for address {address}: {e}")
        return []

async def check_btc_address_transactions(address: str):
    return await asyncio.to_thread(_check_btc_address_sync, address)
