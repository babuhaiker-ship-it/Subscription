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

def _xmr_rpc_call_sync(rpc_url: str, method: str, params: dict = None, rpc_user: str = "", rpc_password: str = "") -> dict:
    """Synchronous Monero RPC call helper with basic auth support."""
    if params is None:
        params = {}
    payload = {
        "jsonrpc": "2.0",
        "id": "0",
        "method": method,
        "params": params
    }
    auth = None
    if rpc_user and rpc_password:
        from requests.auth import HTTPDigestAuth
        auth = HTTPDigestAuth(rpc_user, rpc_password)
    try:
        res = requests.post(rpc_url, json=payload, auth=auth, timeout=10)
        if res.status_code == 200:
            return res.json()
        logger.warning(f"XMR RPC HTTP {res.status_code}: {res.text}")
    except Exception as e:
        logger.error(f"XMR RPC request exception: {e}")
    return {}

async def xmr_rpc_call(rpc_url: str, method: str, params: dict = None, rpc_user: str = "", rpc_password: str = "") -> dict:
    return await asyncio.to_thread(_xmr_rpc_call_sync, rpc_url, method, params, rpc_user, rpc_password)

async def check_xmr_transfers_rpc(rpc_url: str, min_height: int = 0, rpc_user: str = "", rpc_password: str = "") -> list:
    """
    Checks incoming transfers on the connected monero-wallet-rpc server.
    Returns list of incoming transfer dicts.
    """
    res = await xmr_rpc_call(
        rpc_url,
        "get_transfers",
        {"in": True, "filter_by_height": min_height > 0, "min_height": min_height},
        rpc_user,
        rpc_password
    )
    result = res.get("result", {})
    return result.get("in", [])

async def create_xmr_subaddress_rpc(rpc_url: str, label: str = "invoice", account_index: int = 0, rpc_user: str = "", rpc_password: str = "") -> dict:
    """
    Creates a new subaddress on monero-wallet-rpc for clean per-invoice tracking.
    """
    res = await xmr_rpc_call(
        rpc_url,
        "create_address",
        {"account_index": account_index, "label": label},
        rpc_user,
        rpc_password
    )
    result = res.get("result", {})
    return {
        "address": result.get("address"),
        "address_index": result.get("address_index")
    }

async def verify_xmr_txid_rpc(rpc_url: str, txid: str, target_address: str = None, min_amount_xmr: float = 0.0, rpc_user: str = "", rpc_password: str = "") -> dict:
    """
    Verifies a Monero transaction ID against monero-wallet-rpc.
    """
    res = await xmr_rpc_call(
        rpc_url,
        "get_transfer_by_txid",
        {"txid": txid},
        rpc_user,
        rpc_password
    )
    result = res.get("result", {})
    transfer = result.get("transfer", {})
    if not transfer:
        return {"valid": False, "reason": "Transaction not found on connected RPC node."}

    # Convert atomic units (piconeros) to XMR
    received_atomic = transfer.get("amount", 0)
    received_xmr = received_atomic / 1e12

    if min_amount_xmr > 0 and received_xmr < min_amount_xmr * 0.98:
        return {
            "valid": False,
            "reason": f"Insufficient amount: expected ~{min_amount_xmr:.6f} XMR, received {received_xmr:.6f} XMR."
        }

    confirmations = transfer.get("confirmations", 0)
    return {
        "valid": True,
        "txid": txid,
        "amount_xmr": received_xmr,
        "confirmations": confirmations,
        "address": transfer.get("address")
    }
