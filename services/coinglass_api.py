"""
Coinglass API Integration for Market Data (v4 base)
"""

import aiohttp
import logging
from typing import Dict, List, Any, Optional, cast

logger = logging.getLogger(__name__)


class CoinglassAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://open-api-v4.coinglass.com"
        self.session: Optional[aiohttp.ClientSession] = None

    def _normalize_interval_4h(self, interval: str) -> str:
        iv = str(interval).lower().strip()
        allowed = {"4h", "6h", "8h", "12h", "1d", "1w"}
        aliases = {"24h": "1d", "1day": "1d", "day": "1d", "week": "1w", "1week": "1w"}
        if iv in aliases:
            iv = aliases[iv]
        if iv not in allowed:
            return "4h"
        return iv

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _make_request(self, endpoint: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        headers = {"accept": "application/json", "CG-API-KEY": self.api_key}
        async with session.get(url, params=params, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            text = await resp.text()
            logger.error(f"Coinglass API error: {resp.status} - {text}")
            raise Exception(f"Coinglass API error: {resp.status}")

    async def get_supported_coins(self) -> List[str]:
        data = await self._make_request("/api/futures/supported-coins")
        return data.get("data", [])

    async def get_supported_exchange_pairs(self) -> Dict[str, Any]:
        return await self._make_request("/api/futures/supported-exchange-pairs")

    async def get_pairs_markets(self, symbol: str | None = None) -> Dict[str, Any]:
        # Coinglass often expects base coin (e.g., BTC). Try coin then pair.
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol.replace("USDT", "")
        data: Dict[str, Any] = await self._make_request("/api/futures/pairs-markets", params)
        # Fallback: if empty/none, try full pair symbol
        items_any = data.get("data")
        if symbol and not items_any:
            data = await self._make_request("/futures/pairs-markets", {"symbol": symbol})
        return data

    async def get_price_history(self, symbol: str, interval: str = "4h", limit: int = 100) -> Dict[str, Any]:
        iv = self._normalize_interval_4h(interval)
        params: Dict[str, Any] = {"symbol": symbol.replace("USDT", ""), "interval": iv, "limit": int(limit)}
        return await self._make_request("/api/futures/price/history", params)

    async def get_open_interest_history(self, symbol: str, interval: str = "4h", limit: int = 100) -> Dict[str, Any]:
        iv = self._normalize_interval_4h(interval)
        params: Dict[str, Any] = {"symbol": symbol.replace("USDT", "_USDT"), "interval": iv, "limit": int(limit)}
        return await self._make_request("/api/futures/open-interest/history", params)

    async def get_funding_rate_history(self, symbol: str, interval: str = "4h", limit: int = 100) -> Dict[str, Any]:
        iv = self._normalize_interval_4h(interval)
        params: Dict[str, Any] = {"symbol": symbol.replace("USDT", "_USDT"), "interval": iv, "limit": int(limit)}
        return await self._make_request("/api/futures/funding-rate/history", params)

    # Convenience accessors derived from pairs-markets (avoid specialized endpoints to reduce 404s)
    async def get_open_interest(self, symbol: str) -> Dict[str, Any]:
        try:
            resp: Dict[str, Any] = await self.get_pairs_markets(symbol)
            items_any = resp.get("data")
            if isinstance(items_any, list):
                items_list = cast(List[Dict[str, Any]], items_any)
                for it in items_list:
                    if str(it.get("exchangeName", "")).upper() == "MEXC":
                        return {
                            "symbol": symbol,
                            "open_interest": it.get("openInterest", 0),
                            "open_interest_change_24h": it.get("h24OpenInterestChange", it.get("openInterestChange24h", 0)),
                        }
            return {"symbol": symbol, "open_interest": 0, "open_interest_change_24h": 0}
        except Exception as e:
            logger.error(f"Error getting open interest for {symbol}: {e}")
            return {"symbol": symbol, "open_interest": 0, "open_interest_change_24h": 0}

    async def get_funding_rate(self, symbol: str) -> Dict[str, Any]:
        try:
            resp: Dict[str, Any] = await self.get_pairs_markets(symbol)
            items_any = resp.get("data")
            if isinstance(items_any, list):
                items_list = cast(List[Dict[str, Any]], items_any)
                for it in items_list:
                    if str(it.get("exchangeName", "")).upper() == "MEXC":
                        return {
                            "symbol": symbol,
                            "funding_rate": it.get("fundingRate", 0),
                            "next_funding_time": it.get("nextFundingTime", 0),
                        }
            return {"symbol": symbol, "funding_rate": 0, "next_funding_time": 0}
        except Exception as e:
            logger.error(f"Error getting funding rate for {symbol}: {e}")
            return {"symbol": symbol, "funding_rate": 0, "next_funding_time": 0}

    async def get_long_short_ratio(self, symbol: str, range: str = "h1") -> Dict[str, Any]:
        """Compute long/short ratio using taker-buy-sell-volume endpoint.
        - Endpoint: /api/futures/taker-buy-sell-volume/exchange-list
        - Requires base coin symbol (e.g., BTC) and a range like h1/h4/h12/24h
        Prefers MEXC row if available; otherwise aggregates across exchanges.
        Returns long_rate, short_rate, and long_short_ratio (long_rate/short_rate when short_rate>0).
        """
        try:
            # Normalize base coin symbol
            sym_up = symbol.upper()
            if sym_up.endswith("_USDT"):
                base = sym_up.split("_USDT")[0]
            elif sym_up.endswith("USDT"):
                base = sym_up[:-4]
            else:
                base = sym_up

            # Normalize range to expected forms (h1/h4/h12/24h)
            r = str(range).lower().strip()
            if r.endswith("h") and r[:-1].isdigit():
                r = f"h{r[:-1]}"
            allowed = {"h1", "h4", "h12", "24h", "5m", "15m", "30m"}
            if r not in allowed:
                r = "h1"

            params: Dict[str, Any] = {"symbol": base, "range": r}
            resp = await self._make_request("/api/futures/taker-buy-sell-volume/exchange-list", params)
            items_any = resp.get("data")

            def _as_list(x: Any) -> List[Dict[str, Any]]:
                if isinstance(x, list):
                    raw: List[Any] = cast(List[Any], x)
                    out: List[Dict[str, Any]] = []
                    for it_any in raw:
                        if isinstance(it_any, dict):
                            out.append(cast(Dict[str, Any], it_any))
                    return out
                return []

            rows = _as_list(items_any)
            if not rows:
                return {"symbol": symbol, "long_rate": 0.5, "short_rate": 0.5, "long_short_ratio": 1.0}

            def _f(v: Any) -> float:
                try:
                    return float(v)
                except Exception:
                    return 0.0

            mexc_b = mexc_s = 0.0
            agg_b = agg_s = 0.0
            for row in rows:
                b = _f(row.get("buyVol")) or _f(row.get("buyVolUsd")) or _f(row.get("buy_volume")) or _f(row.get("buy_volume_usd"))
                s = _f(row.get("sellVol")) or _f(row.get("sellVolUsd")) or _f(row.get("sell_volume")) or _f(row.get("sell_volume_usd"))
                agg_b += b
                agg_s += s
                ex = str(row.get("exchangeName") or row.get("exchange") or "").upper()
                if ex == "MEXC":
                    mexc_b, mexc_s = b, s

            def _ratio(b: float, s: float) -> Dict[str, float]:
                total = b + s
                if total <= 0:
                    return {"long_rate": 0.5, "short_rate": 0.5, "long_short_ratio": 1.0}
                long_rate = b / total
                short_rate = s / total
                lsr = (long_rate / short_rate) if short_rate > 1e-9 else 1.0
                return {"long_rate": long_rate, "short_rate": short_rate, "long_short_ratio": lsr}

            preferred = _ratio(mexc_b, mexc_s)
            if preferred["long_rate"] in (0.0, 0) and preferred["short_rate"] in (0.0, 0):
                preferred = _ratio(agg_b, agg_s)

            return {"symbol": symbol, **preferred, "source": "taker-buy-sell-volume", "range": r}
        except Exception as e:
            logger.error(f"Error getting long/short ratio for {symbol}: {e}")
            return {"symbol": symbol, "long_rate": 0.5, "short_rate": 0.5, "long_short_ratio": 1.0}

    async def get_liquidation_history(self, symbol: str, interval: str = "4h", limit: int = 100) -> Dict[str, Any]:
        iv = self._normalize_interval_4h(interval)
        params: Dict[str, Any] = {"symbol": symbol.replace("USDT", "_USDT"), "interval": iv, "limit": int(limit)}
        return await self._make_request("/api/futures/liquidation/history", params)

    async def close(self) -> None:
        if self.session:
            await self.session.close()
            self.session = None
