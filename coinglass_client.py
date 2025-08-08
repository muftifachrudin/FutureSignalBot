"""
Coinglass API client for market sentiment and analytics data (v4 /api endpoints)
"""
import logging
from typing import Any, Dict, List, Optional, Tuple, Type, cast

import aiohttp

from config import Config

logger = logging.getLogger(__name__)


class CoinglassClient:
    """Coinglass API client for market analytics"""

    # Class-level annotations for static analyzers
    api_key: str
    base_url: str
    session: Optional[aiohttp.ClientSession]
    _cache: Dict[str, Tuple[float, Any]]
    _default_ttl_sec: int

    def __init__(self) -> None:
        self.api_key = Config.COINGLASS_API_KEY
        self.base_url = Config.COINGLASS_BASE_URL
        self.session = None
        self._cache = {}
        self._default_ttl_sec = 1800  # 30 minutes

    async def __aenter__(self) -> "CoinglassClient":
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        if self.session:
            await self.session.close()
            self.session = None

    def _get_headers(self) -> Dict[str, str]:
        return {"accept": "application/json", "CG-API-KEY": self.api_key}

    def _normalize_interval_4h(self, interval: str) -> str:
        iv = str(interval).lower().strip()
        allowed = {"4h", "6h", "8h", "12h", "1d", "1w"}
        aliases = {"24h": "1d", "day": "1d", "1day": "1d", "week": "1w", "1week": "1w"}
        if iv in aliases:
            iv = aliases[iv]
        if iv not in allowed:
            if iv.endswith("d") and iv[:-1].isdigit():
                return "1d" if iv != "1d" else iv
            if iv.endswith("w") and iv[:-1].isdigit():
                return "1w" if iv != "1w" else iv
            return "4h"
        return iv

    def _normalize_range(self, rng: str) -> str:
        r = str(rng).lower().strip()
        if r.endswith("h") and r[:-1].isdigit():
            return f"h{r[:-1]}"
        if r in {"h1", "h4", "h12", "24h", "5m", "15m", "30m"}:
            return r
        return "h1"

    async def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.session:
            self.session = aiohttp.ClientSession()
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()
        async with self.session.get(url, params=params, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            text = await resp.text()
            logger.error(f"Coinglass API error: {resp.status} - {text}")
            raise Exception(f"Coinglass API error: {resp.status}")

    def _cache_key(self, endpoint: str, params: Optional[Dict[str, Any]]) -> str:
        if not params:
            return endpoint
        items = sorted((str(k), str(v)) for k, v in params.items())
        return endpoint + "?" + "&".join(f"{k}={v}" for k, v in items)

    async def _cached_request(self, endpoint: str, params: Optional[Dict[str, Any]], ttl_seconds: int) -> Dict[str, Any]:
        import time

        key = self._cache_key(endpoint, params)
        now = time.time()
        hit = self._cache.get(key)
        if hit and (now - hit[0]) < ttl_seconds:
            logger.debug(f"Coinglass cache HIT: {key}")
            data = hit[1]
            if isinstance(data, dict):
                return cast(Dict[str, Any], data)
            return {}
        logger.debug(f"Coinglass cache MISS: {key}")
        data = await self._make_request(endpoint, params)
        self._cache[key] = (now, data)
        return data

    async def get_supported_coins(self) -> List[str]:
        data = await self._make_request("/api/futures/supported-coins")
        items = data.get("data")
        if isinstance(items, list):
            arr = cast(List[Any], items)
            return [str(x) for x in arr]
        return []

    async def get_supported_exchange_pairs(self) -> Dict[str, List[str]]:
        data = await self._make_request("/api/futures/supported-exchange-pairs")
        payload = data.get("data")
        result: Dict[str, List[str]] = {}
        if isinstance(payload, dict):
            for exch, pairs in cast(Dict[str, Any], payload).items():
                if str(exch).upper() != "MEXC":
                    continue
                coll: List[str] = []
                if isinstance(pairs, list):
                    for p in cast(List[Any], pairs):
                        if isinstance(p, dict):
                            pd = cast(Dict[str, Any], p)
                            base = str(pd.get("base_asset") or "").upper()
                            quote = str(pd.get("quote_asset") or "").upper()
                            instrument = str(pd.get("instrument_id") or "")
                            sym = f"{base}{quote}" if base and quote else instrument.replace("_", "")
                            if sym.endswith("USDT"):
                                coll.append(sym)
                if coll:
                    result["MEXC"] = sorted(set(coll))
        return result

    async def get_pairs_markets(self, symbol: str) -> List[Dict[str, Any]]:
        primary = await self._make_request("/api/futures/pairs-markets", {"symbol": symbol})
        items = primary.get("data")
        if not items:
            alt_symbol = symbol.replace("USDT", "_USDT") if "USDT" in symbol else symbol
            primary = await self._make_request("/api/futures/pairs-markets", {"symbol": alt_symbol})
            items = primary.get("data")
        if not items and symbol.upper().endswith("USDT"):
            base = symbol.upper().replace("USDT", "")
            primary = await self._make_request("/api/futures/pairs-markets", {"symbol": base})
            items = primary.get("data")
        if isinstance(items, list):
            arr = cast(List[Any], items)
            return [x for x in arr if isinstance(x, dict)]
        return []

    async def get_price_history(self, symbol: str, interval: str, limit: int = 100) -> List[Dict[str, Any]]:
        iv = self._normalize_interval_4h(interval)
        sym = symbol.replace("USDT", "_USDT") if "USDT" in symbol else symbol
        data = await self._cached_request(
            "/api/futures/price/history",
            {"symbol": sym, "interval": iv, "limit": int(limit)},
            ttl_seconds=self._default_ttl_sec,
        )
        items = data.get("data")
        if isinstance(items, list):
            arr = cast(List[Any], items)
            return [x for x in arr if isinstance(x, dict)]
        return []

    async def get_open_interest_history(self, symbol: str, interval: str = "4h") -> List[Dict[str, Any]]:
        sym = symbol.replace("USDT", "_USDT") if "USDT" in symbol else symbol
        iv = self._normalize_interval_4h(interval)
        data = await self._cached_request(
            "/api/futures/open-interest/history",
            {"symbol": sym, "interval": iv},
            ttl_seconds=self._default_ttl_sec,
        )
        items = data.get("data")
        if isinstance(items, list):
            arr = cast(List[Any], items)
            return [x for x in arr if isinstance(x, dict)]
        return []

    async def get_funding_rates(self, symbol: str, interval: str = "4h") -> Dict[str, Any]:
        iv = self._normalize_interval_4h(interval)
        sym = symbol.replace("USDT", "_USDT") if "USDT" in symbol else symbol
        data = await self._cached_request(
            "/api/futures/funding-rate/history", {"symbol": sym, "interval": iv}, ttl_seconds=self._default_ttl_sec
        )
        payload = data.get("data")
        return cast(Dict[str, Any], payload) if isinstance(payload, dict) else {}

    async def get_long_short_ratio(self, symbol: str, range: str = "h1") -> List[Dict[str, Any]]:
        sym_up = symbol.upper()
        if sym_up.endswith("_USDT"):
            base = sym_up.split("_USDT")[0]
        elif sym_up.endswith("USDT"):
            base = sym_up[:-4]
        else:
            base = sym_up
        requested = self._normalize_range(range)
        candidates = [requested]
        if requested.startswith("h") and requested[1:].isdigit():
            candidates.append(f"{requested[1:]}h")
        elif requested.endswith("h") and requested[:-1].isdigit():
            candidates.append(f"h{requested[:-1]}")
        for rng in candidates:
            logger.debug(f"Fetching LSR (taker-buy-sell-volume) for base={base}, range={rng}")
            data = await self._cached_request(
                "/api/futures/taker-buy-sell-volume/exchange-list",
                {"symbol": base, "range": rng},
                ttl_seconds=600,
            )
            items = data.get("data")
            if isinstance(items, list) and items:
                try:
                    first_dict = cast(Dict[str, Any], items[-1]) if isinstance(items[-1], dict) else None
                    if first_dict is not None:
                        kp: List[str] = list(first_dict.keys())[:6]
                        logger.debug(f"LSR response keys (preview): {kp}")
                except Exception:
                    pass
                arr = cast(List[Any], items)
                return [x for x in arr if isinstance(x, dict)]
        logger.info(f"No LSR data returned for {base} with ranges {candidates}")
        return []

    async def get_liquidation_data(self, symbol: str, interval: str = "4h") -> Dict[str, Any]:
        sym = symbol.replace("USDT", "_USDT") if "USDT" in symbol else symbol
        iv = self._normalize_interval_4h(interval)
        data = await self._cached_request(
            "/api/futures/liquidation/history", {"symbol": sym, "interval": iv}, ttl_seconds=self._default_ttl_sec
        )
        payload = data.get("data")
        return cast(Dict[str, Any], payload) if isinstance(payload, dict) else {}

    async def get_fear_greed_history(self) -> Dict[str, Any]:
        data = await self._cached_request(
            "/api/index/fear-greed-history", None, ttl_seconds=3600
        )
        payload = data.get("data")
        return cast(Dict[str, Any], payload) if isinstance(payload, dict) else {}
