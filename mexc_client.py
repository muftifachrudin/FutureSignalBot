"""
MEXC API client for futures trading data
"""
import hmac
import hashlib
import time
import aiohttp
import asyncio
from typing import Dict, List, Optional, Any, cast
from config import Config
import logging

logger = logging.getLogger(__name__)

class MEXCClient:
    """MEXC API client for fetching futures trading data"""
    
    def __init__(self):
        self.api_key = Config.MEXC_API_KEY
        self.secret_key = Config.MEXC_SECRET_KEY
        self.base_url = Config.MEXC_BASE_URL
        self.contract_base_url = getattr(Config, "MEXC_CONTRACT_BASE_URL", "https://contract.mexc.com")
        self.session = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        timeout = aiohttp.ClientTimeout(total=12, connect=6, sock_connect=6, sock_read=8)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self
    
    async def __aexit__(self, exc_type: Optional[type], exc_val: Optional[BaseException], exc_tb: Optional[Any]):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    def _generate_signature(self, query_string: str) -> str:
        """Generate HMAC-SHA256 signature for MEXC API"""
        return hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _get_headers(self, signed: bool = False) -> Dict[str, str]:
        """Get request headers; include API key only for signed requests"""
        headers: Dict[str, str] = {
            'Content-Type': 'application/json'
        }
        if signed and self.api_key:
            headers['X-MEXC-APIKEY'] = self.api_key
        return headers
    
    async def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None, signed: bool = False) -> Dict[str, Any]:
        """Make authenticated request to MEXC API"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        # Allow full URL endpoints (for contract base) or join with default base
        if endpoint.startswith("http"):
            url = endpoint
        else:
            url = f"{self.base_url}{endpoint}"
        
        if params is None:
            params = {}
        
        if signed:
            timestamp = int(time.time() * 1000)
            params['timestamp'] = timestamp
            
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            signature = self._generate_signature(query_string)
            params['signature'] = signature
        
        headers = self._get_headers(signed)
        
        last_err: Optional[Exception] = None
        for attempt in range(3):
            try:
                async with self.session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"MEXC API error: {response.status} - {error_text}")
                        last_err = Exception(f"MEXC API error: {response.status}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_err = e
                logger.warning(f"MEXC request attempt {attempt+1} failed: {e}")
            await asyncio.sleep(1 * (2 ** attempt))
        # If we get here, all attempts failed
        assert last_err is not None
        raise last_err

    async def _make_contract_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make request to MEXC Contract (futures) public API base."""
        if not self.session:
            self.session = aiohttp.ClientSession()
        base = self.contract_base_url.rstrip("/")
        url = f"{base}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        last_err: Optional[Exception] = None
        for attempt in range(3):
            try:
                async with self.session.get(url, params=params or {}, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"MEXC Contract API error: {response.status} - {error_text}")
                        last_err = Exception(f"MEXC Contract API error: {response.status}")
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_err = e
                logger.warning(f"MEXC Contract request attempt {attempt+1} failed: {e}")
            await asyncio.sleep(1 * (2 ** attempt))
        assert last_err is not None
        raise last_err
    
    async def get_exchange_info(self) -> Dict[str, Any]:
        """Get exchange information including trading pairs"""
        try:
            return await self._make_request("/api/v3/exchangeInfo")
        except Exception as e:
            logger.error(f"Error getting exchange info: {e}")
            return {}
    
    async def get_klines(self, symbol: str, interval: str, limit: int = 100) -> List[List[Any]]:
        """Get kline/candlestick data"""
        # MEXC spot klines expects: 1m,5m,15m,30m,1h,4h,1d,1w
        interval_map = {
            '1m': '1m',
            '5m': '5m',
            '15m': '15m',
            '30m': '30m',
            '1h': '1h',
            '4h': '4h',
            '1d': '1d',
            '1w': '1w',
        }
        mexc_interval = interval_map.get(interval, interval)
        params: Dict[str, Any] = {
            'symbol': symbol,
            'interval': mexc_interval,
            'limit': limit
        }
        
        try:
            response = await self._make_request("/api/v3/klines", params)
            return response if isinstance(response, list) else []
        except Exception as e:
            logger.error(f"Error getting klines for {symbol}: {e}")
            # Fallback: try contract kline and adapt to spot-like structure
            try:
                contract_map = {
                    '1m': 'Min1', '5m': 'Min5', '15m': 'Min15', '30m': 'Min30',
                    '1h': 'Min60', '4h': 'Hour4', '1d': 'Day1', '1w': 'Week1'
                }
                c_interval = contract_map.get(mexc_interval, 'Min15')
                res = await self.get_contract_kline(symbol, c_interval)
                items: List[Dict[str, Any]] = []
                raw_val = res.get('kline')
                if isinstance(raw_val, list):
                    raw_list = cast(List[Any], raw_val)
                    for el_any in raw_list:
                        if isinstance(el_any, dict):
                            items.append(cast(Dict[str, Any], el_any))
                kl: List[List[Any]] = []
                for it in items:
                    # contract returns: {time, open, close, high, low, volume}
                    try:
                        t_raw = it.get('time', 0)
                        o_raw = it.get('open', 0)
                        h_raw = it.get('high', 0)
                        l_raw = it.get('low', 0)
                        c_raw = it.get('close', 0)
                        v_raw = it.get('volume', 0)
                        ot = int(t_raw if isinstance(t_raw, (int, float, str)) else 0)
                        o = float(o_raw if isinstance(o_raw, (int, float, str)) else 0)
                        h = float(h_raw if isinstance(h_raw, (int, float, str)) else 0)
                        l = float(l_raw if isinstance(l_raw, (int, float, str)) else 0)
                        c = float(c_raw if isinstance(c_raw, (int, float, str)) else 0)
                        v = float(v_raw if isinstance(v_raw, (int, float, str)) else 0)
                        # adapt to spot kline array structure
                        kl.append([ot, o, h, l, c, v, ot, v, 0, 0, 0, 0])
                    except Exception:
                        continue
                return kl[:limit]
            except Exception:
                return []
    
    async def get_24hr_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get 24hr ticker price change statistics"""
        params = {'symbol': symbol}
        
        try:
            # Try spot ticker first
            data = await self._make_request("/api/v3/ticker/24hr", params)
            if data:
                # Normalize numeric fields
                try:
                    if isinstance(data.get("priceChangePercent"), str):
                        data["priceChangePercent"] = float(data["priceChangePercent"])
                except Exception:
                    pass
                return data
        except Exception as e:
            logger.warning(f"Spot 24hr ticker failed for {symbol}: {e}")
        # Fallback to contract ticker (different schema)
        try:
            # Contract ticker returns a wrapper with success/code/data; allow symbol param
            contract_symbol = symbol if "_" in symbol else f"{symbol.replace('USDT','')}_USDT"
            res = await self._make_contract_request("/api/v1/contract/ticker", {"symbol": contract_symbol})
            if res.get("success"):
                data_val: Any = res.get("data")
                d_dict: Dict[str, Any] = {}
                # Some deployments return list; pick matching symbol
                if isinstance(data_val, list):
                    data_list = cast(List[Any], data_val)
                    for obj_any in data_list:
                        if isinstance(obj_any, dict):
                            obj = cast(Dict[str, Any], obj_any)
                            if str(obj.get("symbol") or "") == contract_symbol:
                                d_dict = obj
                            break
                    if not d_dict:
                        for obj_any in data_list:
                            if isinstance(obj_any, dict):
                                d_dict = cast(Dict[str, Any], obj_any)
                                break
                elif isinstance(data_val, dict):
                    d_dict = cast(Dict[str, Any], data_val)
                if d_dict:
                    rise_raw = d_dict.get("riseFallRate", 0)
                    try:
                        # Contract API riseFallRate is fraction (e.g., 0.0123 -> 1.23%)
                        rv = float(rise_raw) if isinstance(rise_raw, (int, float, str)) else 0.0
                        price_change_pct = rv * 100 if abs(rv) <= 1 else rv
                    except Exception:
                        price_change_pct = 0
                    return {
                        "symbol": str(d_dict.get("symbol") or contract_symbol).replace("_", ""),
                        "lastPrice": d_dict.get("lastPrice"),
                        "highPrice": d_dict.get("high24Price"),
                        "lowPrice": d_dict.get("lower24Price"),
                        "volume": d_dict.get("volume24"),
                        "priceChangePercent": price_change_pct,
                    }
        except Exception as e:
            logger.warning(f"Contract ticker fallback failed for {symbol}: {e}")
        return {}

    async def get_contract_symbols(self) -> List[str]:
        """Fetch list of contract symbols as a fallback for pairs.
        Returns symbols formatted like BTCUSDT.
        """
        try:
            res = await self._make_contract_request("/api/v1/contract/detail")
            data = res.get("data")
            symbols: List[str] = []
            if isinstance(data, list):
                data_list2 = cast(List[Any], data)
                for item in data_list2:
                    if not isinstance(item, dict):
                        continue
                    item_dict: Dict[str, Any] = cast(Dict[str, Any], item)
                    sym_val = item_dict.get("symbol") or item_dict.get("symbolName")
                    sym = str(sym_val) if isinstance(sym_val, str) else None
                    if sym:
                        symbols.append(sym.replace("_", ""))
            return sorted(set(symbols))
        except Exception as e:
            logger.warning(f"Failed to fetch contract symbols: {e}")
            return []
    
    async def get_funding_rate(self, symbol: str) -> Dict[str, Any]:
        """Get current funding rate for futures"""
        try:
            # Use MEXC Contract funding rate public endpoint
            # Note: Contract API expects symbol format like BTC_USDT
            contract_symbol = symbol if "_" in symbol else f"{symbol.replace('USDT','')}_USDT"
            res = await self._make_contract_request(f"/api/v1/contract/funding_rate/{contract_symbol}")
            if res.get("success") and isinstance(res.get("data"), dict):
                return res["data"]
        except Exception as e:
            logger.warning(f"Contract funding_rate failed for {symbol}: {e}")
        return {}
    
    async def get_open_interest(self, symbol: str) -> Dict[str, Any]:
        """Get open interest for futures"""
        params = {'symbol': symbol}
        
        try:
            # Try different endpoints for open interest
            endpoints = [
                "/api/v3/openInterest",
                "/fapi/v1/openInterest"
            ]
            
            for endpoint in endpoints:
                try:
                    result = await self._make_request(endpoint, params, signed=False)
                    if result:
                        return result
                except:
                    continue
                    
            return {}
        except Exception as e:
            logger.error(f"Error getting open interest for {symbol}: {e}")
            return {}

    async def get_contract_kline(self, symbol: str, interval: str = "Min15", start: Optional[int] = None, end: Optional[int] = None) -> Dict[str, Any]:
        """Get contract kline data from MEXC contract API. Interval: Min1, Min5, Min15, Min30, Min60, Hour4, Hour8, Day1, Week1, Month1"""
        contract_symbol = symbol if "_" in symbol else f"{symbol.replace('USDT','')}_USDT"
        params: Dict[str, Optional[str]] = {"interval": interval}
        if start:
            params["start"] = str(start)
        if end:
            params["end"] = str(end)
        res = await self._make_contract_request(f"/api/v1/contract/kline/{contract_symbol}", params)
        return res.get("data", {})

    async def get_index_price(self, symbol: str) -> Dict[str, Any]:
        """Get contract index price for symbol."""
        contract_symbol = symbol if "_" in symbol else f"{symbol.replace('USDT','')}_USDT"
        res = await self._make_contract_request(f"/api/v1/contract/index_price/{contract_symbol}")
        return res.get("data", {})

    async def get_fair_price(self, symbol: str) -> Dict[str, Any]:
        """Get contract fair price for symbol."""
        contract_symbol = symbol if "_" in symbol else f"{symbol.replace('USDT','')}_USDT"
        res = await self._make_contract_request(f"/api/v1/contract/fair_price/{contract_symbol}")
        return res.get("data", {})
    
    async def get_long_short_ratio(self, symbol: str, period: str = "5m") -> Dict[str, Any]:
        """Get long/short ratio"""
        params = {
            'symbol': symbol,
            'period': period
        }
        
        try:
            return await self._make_request("/futures/data/globalLongShortAccountRatio", params)
        except Exception as e:
            logger.error(f"Error getting long/short ratio for {symbol}: {e}")
            return {}
