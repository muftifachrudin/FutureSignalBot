"""
MEXC API client for futures trading data
"""
import hmac
import hashlib
import time
import json
import aiohttp
import asyncio
from typing import Dict, List, Optional
from config import Config
import logging

logger = logging.getLogger(__name__)

class MEXCClient:
    """MEXC API client for fetching futures trading data"""
    
    def __init__(self):
        self.api_key = Config.MEXC_API_KEY
        self.secret_key = Config.MEXC_SECRET_KEY
        self.base_url = Config.MEXC_BASE_URL
        self.session = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
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
        """Get request headers"""
        headers = {
            'X-MEXC-APIKEY': self.api_key,
            'Content-Type': 'application/json'
        }
        return headers
    
    async def _make_request(self, endpoint: str, params: Dict = None, signed: bool = False) -> Dict:
        """Make authenticated request to MEXC API"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        
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
        
        try:
            async with self.session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(f"MEXC API error: {response.status} - {error_text}")
                    raise Exception(f"MEXC API error: {response.status}")
        except Exception as e:
            logger.error(f"Error making request to MEXC: {e}")
            raise
    
    async def get_exchange_info(self) -> Dict:
        """Get exchange information including trading pairs"""
        try:
            return await self._make_request("/api/v3/exchangeInfo")
        except Exception as e:
            logger.error(f"Error getting exchange info: {e}")
            return {}
    
    async def get_klines(self, symbol: str, interval: str, limit: int = 100) -> List[List]:
        """Get kline/candlestick data"""
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }
        
        try:
            response = await self._make_request("/api/v3/klines", params)
            return response if isinstance(response, list) else []
        except Exception as e:
            logger.error(f"Error getting klines for {symbol}: {e}")
            return []
    
    async def get_24hr_ticker(self, symbol: str) -> Dict:
        """Get 24hr ticker price change statistics"""
        params = {'symbol': symbol}
        
        try:
            return await self._make_request("/api/v3/ticker/24hr", params)
        except Exception as e:
            logger.error(f"Error getting 24hr ticker for {symbol}: {e}")
            return {}
    
    async def get_funding_rate(self, symbol: str) -> Dict:
        """Get current funding rate for futures"""
        params = {'symbol': symbol}
        
        try:
            # Try different endpoints for funding rate
            endpoints = [
                "/api/v3/premiumIndex",
                "/fapi/v1/premiumIndex", 
                "/api/v3/ticker/price"
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
            logger.error(f"Error getting funding rate for {symbol}: {e}")
            return {}
    
    async def get_open_interest(self, symbol: str) -> Dict:
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
    
    async def get_long_short_ratio(self, symbol: str, period: str = "5m") -> Dict:
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
