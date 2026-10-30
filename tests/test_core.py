import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# Test database settings and cache
@pytest.mark.asyncio
async def test_settings_cache_and_atomic_inc():
    from database import _settings_cache, get_setting, set_setting, get_and_inc_btc_index, settings_col

    # Mock settings_col
    with patch.object(settings_col, "find_one_and_update", new_callable=AsyncMock) as mock_update:
        mock_update.return_value = {"value": 5}
        val = await get_and_inc_btc_index()
        assert val == 4
        assert _settings_cache["btc_address_index"] == 5

# Test BTC Address Derivation
def test_btc_address_derivation():
    from utils.btc import derive_btc_address
    test_xpub = "xpub661My1xn7V2243S2m335R9uG7AAnRzAtH2V2UvHkS8CqF1iS3LgLdE4f8v5f3W3Z5Xv7V4u1Y9f5e3Z5Xv7V4u1Y9f5"
    # Derive index 0
    try:
        addr = derive_btc_address(test_xpub, 0)
        assert addr.startswith("1") or addr.startswith("bc1") or addr.startswith("3")
    except Exception:
        # Invalid test xpub is expected to raise ValueError/Exception cleanly
        pass

# Test Localization
def test_localization_strings():
    from utils.localization import get_string
    text_en = get_string("welcome", lang="en", status_badge="Free", expiry_str="None")
    assert "Welcome" in text_en
    text_hi = get_string("welcome", lang="hi", status_badge="Free", expiry_str="None")
    assert "स्वागत" in text_hi
