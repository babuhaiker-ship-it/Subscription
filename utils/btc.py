import requests
import logging
import asyncio
import hmac
import hashlib
import struct
import base58
import ecdsa

logger = logging.getLogger(__name__)

CHARSET = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'

def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()

def ripemd160(data: bytes) -> bytes:
    h = hashlib.new('ripemd160')
    h.update(sha256(data))
    return h.digest()

def b58check_encode(version: bytes, payload: bytes) -> str:
    data = version + payload
    checksum = sha256(sha256(data))[:4]
    return base58.b58encode(data + checksum).decode('ascii')

def bech32_polymod(values):
    GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = ((chk & 0x1ffffff) << 5) ^ v
        for i in range(5):
            chk ^= GEN[i] if ((b >> i) & 1) else 0
    return chk

def bech32_hrp_expand(hrp):
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]

def bech32_create_checksum(hrp, data):
    values = bech32_hrp_expand(hrp) + data
    polymod = bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ 1
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]

def convertbits(data, frombits, tobits, pad=True):
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            return None
        acc = (acc << frombits) | value
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return ret

def segwit_addr_encode(hrp, witver, witprog):
    data = [witver] + convertbits(witprog, 8, 5)
    checksum = bech32_create_checksum(hrp, data)
    return hrp + '1' + ''.join([CHARSET[d] for d in data + checksum])

def derive_bip32_child_pubkey(parent_pubkey_bytes: bytes, parent_chain_code: bytes, index: int) -> tuple[bytes, bytes]:
    data = parent_pubkey_bytes + struct.pack('>I', index)
    I = hmac.new(parent_chain_code, data, hashlib.sha512).digest()
    IL, IR = I[:32], I[32:]

    il_int = int.from_bytes(IL, 'big')
    curve = ecdsa.SECP256k1
    if il_int >= curve.order:
        raise ValueError('Scalar out of bounds')

    p_point = ecdsa.VerifyingKey.from_string(parent_pubkey_bytes, curve=curve).pubkey.point
    c_point = il_int * curve.generator + p_point

    x = c_point.x()
    y = c_point.y()
    prefix = b'\x02' if y % 2 == 0 else b'\x03'
    child_pubkey_bytes = prefix + x.to_bytes(32, 'big')
    return child_pubkey_bytes, IR

def derive_btc_address(xpub_key: str, index: int = 0, change: int = 0) -> str:
    """
    Derives a Bitcoin address from extended public key (xpub/zpub/ypub) using zero C-extension dependencies.
    """
    ext_key = xpub_key.strip()
    raw = base58.b58decode_check(ext_key)
    version = raw[:4]
    chain_code = raw[13:45]
    pubkey = raw[45:78]

    change_pub, change_chain = derive_bip32_child_pubkey(pubkey, chain_code, change)
    idx_pub, _ = derive_bip32_child_pubkey(change_pub, change_chain, index)

    h160 = ripemd160(idx_pub)

    if version in (b'\x04\xb2\x47\x46', b'\x04\xb2\x43\x0c'): # zpub (Native SegWit bc1q...)
        return segwit_addr_encode('bc', 0, list(h160))
    elif version == b'\x04\x9d\x7d\x41': # ypub (Nested SegWit 3...)
        redeem_script = b'\x00\x14' + h160
        script_hash = ripemd160(redeem_script)
        return b58check_encode(b'\x05', script_hash)
    elif version == b'\x04\x88\xb2\x1e': # xpub (Legacy 1...)
        return b58check_encode(b'\x00', h160)
    else:
        return segwit_addr_encode('bc', 0, list(h160))

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
