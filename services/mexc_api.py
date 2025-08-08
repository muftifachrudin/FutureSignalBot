"""
MEXC Exchange API Integration
"""

import hashlib
import hmac
import time
import aiohttp
import json
import logging
from typing import Dict, List, Any
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class MexcAPI:
    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = "https://api.mexc.com"
        self.session = None

    async def _get_session(self):
        """Get or create aiohttp session"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    def _generate_signature(self, query_string: str) -> str:
        """Generate signature for authenticated requests"""
        return hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    async def _make_request(self, method: str, endpoint: str, params: Dict = None, signed: bool = False) -> Dict:
        """Make HTTP request to MEXC API"""
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        
        headers = {
            'X-MEXC-APIKEY': self.api_key,
            'Content-Type': 'application/json'
        }

        if params is None:
            params = {}

        if signed:
            params['timestamp'] = int(time.time() * 1000)
            query_string = urlencode(params)
            params['signature'] = self._generate_signature(query_string)

        try:
            async with session.request(method, url, params=params, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(f"MEXC API error: {response.status} - {error_text}")
                    raise Exception(f"MEXC API error: {response.status}")
        except aiohttp.ClientError as e:
            logger.error(f"HTTP request failed: {e}")
            raise Exception(f"HTTP request failed: {e}")

    async def get_exchange_info(self) -> Dict:
        """Get exchange trading rules and symbol information"""
        return await self._make_request('GET', '/api/v3/exchangeInfo')

    async def get_kline_data(self, symbol: str, interval: str, limit: int = 100) -> List[Dict]:
        """Get kline/candlestick data"""
        # Convert interval format (5m -> 5m, 1h -> 1h, 4h -> 4h)
        interval_map = {
            '5m': '5m',
            '15m': '15m',
            '30m': '30m',
            '1h': '1h',
            '4h': '4h'
        }
        
        mexc_interval = interval_map.get(interval, interval)
        
        params = {
            'symbol': symbol,
            'interval': mexc_interval,
            'limit': limit
        }
        
        response = await self._make_request('GET', '/api/v3/klines', params)
        
        # Convert response to more readable format
        klines = []
        for kline in response:
            klines.append({
                'open_time': kline[0],
                'open': float(kline[1]),
                'high': float(kline[2]),
                'low': float(kline[3]),
                'close': float(kline[4]),
                'volume': float(kline[5]),
                'close_time': kline[6],
                'quote_volume': float(kline[7]),
                'count': int(kline[8])
            })
        
        return klines

    async def get_ticker_24hr(self, symbol: str) -> Dict:
        """Get 24hr ticker price change statistics"""
        params = {'symbol': symbol}
        return await self._make_request('GET', '/api/v3/ticker/24hr', params)

    async def get_current_price(self, symbol: str) -> Dict:
        """Get current price for a symbol"""
        params = {'symbol': symbol}
        return await self._make_request('GET', '/api/v3/ticker/price', params)

    async def get_account_info(self) -> Dict:
        """Get account information (requires authentication)"""
        return await self._make_request('GET', '/api/v3/account', signed=True)

    async def close(self):
        """Close the session"""
        if self.session:
            await self.session.close()
