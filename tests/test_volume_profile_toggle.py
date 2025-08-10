import asyncio
from typing import Any, Dict
from config import Config
from signal_generator_v2 import PairsCache

# We will monkeypatch internal methods to avoid real API calls.

class DummyPairsCache(PairsCache):
    def __init__(self):  # type: ignore
        super().__init__()
    async def _get_reliable_market_data(self, symbol: str) -> Dict[str, Any]:  # type: ignore
        return {
            'mexc_ticker': {
                'lastPrice': '50000',
                'priceChangePercent': '2.5',
                'highPrice': '51000',
                'lowPrice': '49000'
            },
            'coinglass_summary': {
                'funding_rate': 0.0005,
                'oi_change_24h': 1.2,
                'long_short_ratio': 0.55
            },
            'coinglass_markets': []
        }
    def _compute_volume_profile(self, symbol: str):  # type: ignore
        return {  # type: ignore
            'poc': 50100.0,
            'hvn': [50200.0],
            'lvn': [49800.0],
            'range_pct': 3.0
        }
    def _compute_atr1m(self, symbol: str) -> float:  # type: ignore
        return 0.85

async def _collect(flag: bool) -> str:
    # toggle flag dynamically
    Config.ENABLE_VOLUME_PROFILE_EXPLANATION = flag  # type: ignore
    pc = DummyPairsCache()
    async with pc:
        text = await pc.get_market_explanation('BTCUSDT')
    return text

def test_volume_profile_toggle():
    out_with = asyncio.run(_collect(True))
    out_without = asyncio.run(_collect(False))
    assert ('POC:' in out_with or 'ATR1m:' in out_with), 'Expected micro metrics when flag enabled'
    assert 'POC:' not in out_without and 'ATR1m:' not in out_without, 'Unexpected micro metrics when flag disabled'
