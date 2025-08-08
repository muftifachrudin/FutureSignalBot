"""
Coinglass API client for market sentiment and analytics data
"""
import aiohttp
import asyncio
from typing import Dict, List, Optional
from config import Config
import logging

logger = logging.getLogger(__name__)

class CoinglassClient:
    """Coinglass API client for market analytics"""
    
    def __init__(self):
        self.api_key = Config.COINGLASS_API_KEY
        self.base_url = Config.COINGLASS_BASE_URL
        self.session = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with API key"""
        return {
            'accept': 'application/json',
            'CG-API-KEY': self.api_key
        }
    
    async def _make_request(self, endpoint: str, params: Dict = None) -> Dict:
        """Make request to Coinglass API"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()
        
        try:
            async with self.session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(f"Coinglass API error: {response.status} - {error_text}")
                    raise Exception(f"Coinglass API error: {response.status}")
        except Exception as e:
            logger.error(f"Error making request to Coinglass: {e}")
            raise
    
    async def get_supported_coins(self) -> List[str]:
        """Get list of supported coins"""
        try:
            response = await self._make_request("/futures/supported-coins")
            return response.get('data', [])
        except Exception as e:
            logger.error(f"Error getting supported coins: {e}")
            return []
    
    async def get_supported_exchange_pairs(self) -> Dict:
        """Get supported exchange pairs (filtered for MEXC and USDT)"""
        try:
            response = await self._make_request("/futures/supported-exchange-pairs")
            data = response.get('data', {})
            
            # Filter for MEXC exchange and USDT pairs
            mexc_pairs = {}
            for exchange, pairs in data.items():
                if exchange.upper() == 'MEXC':
                    usdt_pairs = [pair for pair in pairs if pair.endswith('USDT')]
                    mexc_pairs[exchange] = usdt_pairs
            
            return mexc_pairs
        except Exception as e:
            logger.error(f"Error getting exchange pairs: {e}")
            return {}
    
    async def get_pairs_markets(self, symbol: str) -> Dict:
        """Get market data for specific trading pair"""
        params = {'symbol': symbol}
        
        try:
            response = await self._make_request("/futures/pairs-markets", params)
            return response.get('data', {})
        except Exception as e:
            logger.error(f"Error getting pairs markets for {symbol}: {e}")
            return {}
    
    async def get_price_history(self, symbol: str, interval: str, limit: int = 100) -> List[Dict]:
        """Get OHLC price history (minimum interval 4h as per API limitation)"""
        # Map intervals to Coinglass format
        interval_map = {
            '4h': '4h',
            '1d': '1d',
            '1w': '1w'
        }
        
        if interval not in interval_map:
            logger.warning(f"Interval {interval} not supported by Coinglass, using 4h")
            interval = '4h'
        
        params = {
            'symbol': symbol,
            'interval': interval_map[interval],
            'limit': limit
        }
        
        try:
            response = await self._make_request("/futures/price/history", params)
            return response.get('data', [])
        except Exception as e:
            logger.error(f"Error getting price history for {symbol}: {e}")
            return []
    
    async def get_open_interest_history(self, symbol: str, interval: str = "4h") -> List[Dict]:
        """Get open interest history"""
        params = {
            'symbol': symbol,
            'interval': interval
        }
        
        try:
            response = await self._make_request("/futures/openInterest/history", params)
            return response.get('data', [])
        except Exception as e:
            logger.error(f"Error getting OI history for {symbol}: {e}")
            return []
    
    async def get_funding_rates(self, symbol: str) -> Dict:
        """Get funding rates across exchanges"""
        params = {'symbol': symbol}
        
        try:
            response = await self._make_request("/futures/funding_rates", params)
            return response.get('data', {})
        except Exception as e:
            logger.error(f"Error getting funding rates for {symbol}: {e}")
            return {}
    
    async def get_long_short_ratio(self, symbol: str, interval: str = "4h") -> List[Dict]:
        """Get long/short position ratio"""
        params = {
            'symbol': symbol,
            'interval': interval
        }
        
        try:
            response = await self._make_request("/futures/longShortRatio", params)
            return response.get('data', [])
        except Exception as e:
            logger.error(f"Error getting long/short ratio for {symbol}: {e}")
            return []
    
    async def get_liquidation_data(self, symbol: str, interval: str = "4h") -> Dict:
        """Get liquidation data"""
        params = {
            'symbol': symbol,
            'interval': interval
        }
        
        try:
            response = await self._make_request("/futures/liquidation_orders", params)
            return response.get('data', {})
        except Exception as e:
            logger.error(f"Error getting liquidation data for {symbol}: {e}")
            return {}
