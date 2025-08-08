"""
Coinglass API Integration for Market Data
"""

import aiohttp
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class CoinglassAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://open-api-v4.coinglass.com"
        self.session = None

    async def _get_session(self):
        """Get or create aiohttp session"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _make_request(self, endpoint: str, params: Dict = None) -> Dict:
        """Make HTTP request to Coinglass API"""
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        
        headers = {
            'accept': 'application/json',
            'CG-API-KEY': self.api_key
        }

        try:
            async with session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(f"Coinglass API error: {response.status} - {error_text}")
                    raise Exception(f"Coinglass API error: {response.status}")
        except aiohttp.ClientError as e:
            logger.error(f"HTTP request failed: {e}")
            raise Exception(f"HTTP request failed: {e}")

    async def get_supported_coins(self) -> List[str]:
        """Get list of supported coins"""
        response = await self._make_request('/api/futures/supported-coins')
        return response.get('data', [])

    async def get_supported_exchange_pairs(self) -> Dict:
        """Get supported exchange pairs"""
        return await self._make_request('/api/futures/supported-exchange-pairs')

    async def get_pairs_markets(self, symbol: str = None) -> Dict:
        """Get pairs market data"""
        params = {}
        if symbol:
            params['symbol'] = symbol.replace('USDT', '')  # Remove USDT suffix for Coinglass
        return await self._make_request('/api/futures/pairs-markets', params)

    async def get_price_history(self, symbol: str, interval: str = '4h', limit: int = 100) -> Dict:
        """Get price history (OHLC) data - minimum interval is 4h"""
        params = {
            'symbol': symbol.replace('USDT', ''),  # Remove USDT for Coinglass
            'interval': interval,
            'limit': limit
        }
        return await self._make_request('/api/futures/price/history', params)

    async def get_open_interest(self, symbol: str) -> Dict:
        """Get open interest data for a symbol"""
        try:
            # Get market data which includes open interest information
            response = await self.get_pairs_markets(symbol)
            
            if response.get('success') and response.get('data'):
                # Find MEXC data specifically
                for exchange_data in response['data']:
                    if exchange_data.get('exchangeName') == 'MEXC':
                        return {
                            'symbol': symbol,
                            'open_interest': exchange_data.get('openInterest', 0),
                            'open_interest_change_24h': exchange_data.get('openInterestChange24h', 0)
                        }
            
            return {'symbol': symbol, 'open_interest': 0, 'open_interest_change_24h': 0}
        except Exception as e:
            logger.error(f"Error getting open interest for {symbol}: {e}")
            return {'symbol': symbol, 'open_interest': 0, 'open_interest_change_24h': 0}

    async def get_funding_rate(self, symbol: str) -> Dict:
        """Get funding rate data for a symbol"""
        try:
            response = await self.get_pairs_markets(symbol)
            
            if response.get('success') and response.get('data'):
                for exchange_data in response['data']:
                    if exchange_data.get('exchangeName') == 'MEXC':
                        return {
                            'symbol': symbol,
                            'funding_rate': exchange_data.get('fundingRate', 0),
                            'next_funding_time': exchange_data.get('nextFundingTime', 0)
                        }
            
            return {'symbol': symbol, 'funding_rate': 0, 'next_funding_time': 0}
        except Exception as e:
            logger.error(f"Error getting funding rate for {symbol}: {e}")
            return {'symbol': symbol, 'funding_rate': 0, 'next_funding_time': 0}

    async def get_long_short_ratio(self, symbol: str) -> Dict:
        """Get long/short ratio data for a symbol"""
        try:
            response = await self.get_pairs_markets(symbol)
            
            if response.get('success') and response.get('data'):
                for exchange_data in response['data']:
                    if exchange_data.get('exchangeName') == 'MEXC':
                        long_rate = exchange_data.get('longRate', 0.5)
                        short_rate = 1 - long_rate
                        return {
                            'symbol': symbol,
                            'long_rate': long_rate,
                            'short_rate': short_rate,
                            'long_short_ratio': long_rate / short_rate if short_rate > 0 else 1.0
                        }
            
            return {'symbol': symbol, 'long_rate': 0.5, 'short_rate': 0.5, 'long_short_ratio': 1.0}
        except Exception as e:
            logger.error(f"Error getting long/short ratio for {symbol}: {e}")
            return {'symbol': symbol, 'long_rate': 0.5, 'short_rate': 0.5, 'long_short_ratio': 1.0}

    async def get_market_data(self, symbol: str, timeframe: str) -> Dict:
        """Get comprehensive market data for a symbol and timeframe"""
        try:
            # For timeframes >= 4h, we can get price history
            if timeframe in ['4h', '1d']:
                price_history = await self.get_price_history(symbol, timeframe)
            else:
                price_history = None

            # Get current market data
            pairs_data = await self.get_pairs_markets(symbol)
            
            return {
                'price_history': price_history,
                'market_data': pairs_data,
                'timeframe': timeframe
            }
        except Exception as e:
            logger.error(f"Error getting market data for {symbol} {timeframe}: {e}")
            return {'price_history': None, 'market_data': None, 'timeframe': timeframe}

    async def close(self):
        """Close the session"""
        if self.session:
            await self.session.close()
