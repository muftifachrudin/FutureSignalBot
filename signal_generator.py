"""
Main signal generation logic combining all data sources
"""
import asyncio
import time
from typing import Dict, List, Optional, Tuple
from mexc_client import MEXCClient
from coinglass_client import CoinglassClient
from gemini_analyzer import GeminiAnalyzer, TradingSignal, MarketAnalysis
from config import Config
import logging

logger = logging.getLogger(__name__)

class SignalGenerator:
    """Main class for generating trading signals"""
    
    def __init__(self):
        self.mexc_client = None
        self.coinglass_client = None
        self.gemini_analyzer = GeminiAnalyzer()
        self.signal_cache = {}  # Cache signals to avoid spam
        self.last_request_time = {}  # Rate limiting
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.mexc_client = MEXCClient()
        self.coinglass_client = CoinglassClient()
        await self.mexc_client.__aenter__()
        await self.coinglass_client.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.mexc_client:
            await self.mexc_client.__aexit__(exc_type, exc_val, exc_tb)
        if self.coinglass_client:
            await self.coinglass_client.__aexit__(exc_type, exc_val, exc_tb)
    
    def _should_generate_signal(self, symbol: str) -> bool:
        """Check if enough time has passed since last signal for this symbol"""
        current_time = time.time()
        last_time = self.last_request_time.get(symbol, 0)
        
        return (current_time - last_time) >= Config.SIGNAL_COOLDOWN_SECONDS
    
    def _update_request_time(self, symbol: str):
        """Update last request time for rate limiting"""
        self.last_request_time[symbol] = time.time()
    
    async def _collect_mexc_data(self, symbol: str) -> Dict:
        """Collect data from MEXC API"""
        mexc_data = {}
        
        try:
            # Get klines for multiple timeframes
            timeframes = {
                '5m': '5m',
                '15m': '15m', 
                '30m': '30m',
                '1h': '1h',
                '4h': '4h'
            }
            
            mexc_data['klines'] = {}
            for tf_name, tf_interval in timeframes.items():
                klines = await self.mexc_client.get_klines(symbol, tf_interval, 50)
                mexc_data['klines'][tf_name] = klines
            
            # Get 24hr ticker
            mexc_data['ticker_24hr'] = await self.mexc_client.get_24hr_ticker(symbol)
            
            # Get funding rate
            mexc_data['funding_rate'] = await self.mexc_client.get_funding_rate(symbol)
            
            # Get open interest
            mexc_data['open_interest'] = await self.mexc_client.get_open_interest(symbol)
            
            # Get long/short ratio
            mexc_data['long_short_ratio'] = await self.mexc_client.get_long_short_ratio(symbol)
            
        except Exception as e:
            logger.error(f"Error collecting MEXC data for {symbol}: {e}")
        
        return mexc_data
    
    async def _collect_coinglass_data(self, symbol: str) -> Dict:
        """Collect data from Coinglass API"""
        coinglass_data = {}
        
        try:
            # Get pairs market data
            coinglass_data['pairs_markets'] = await self.coinglass_client.get_pairs_markets(symbol)
            
            # Get price history (only 4h+ available)
            coinglass_data['price_history'] = await self.coinglass_client.get_price_history(symbol, '4h', 50)
            
            # Get open interest history
            coinglass_data['oi_history'] = await self.coinglass_client.get_open_interest_history(symbol)
            
            # Get funding rates
            coinglass_data['funding_rates'] = await self.coinglass_client.get_funding_rates(symbol)
            
            # Get long/short ratio
            coinglass_data['long_short_ratio'] = await self.coinglass_client.get_long_short_ratio(symbol)
            
            # Get liquidation data
            coinglass_data['liquidations'] = await self.coinglass_client.get_liquidation_data(symbol)
            
        except Exception as e:
            logger.error(f"Error collecting Coinglass data for {symbol}: {e}")
        
        return coinglass_data
    
    def _analyze_timeframe_trends(self, klines_data: Dict) -> Dict[str, str]:
        """Analyze trends across different timeframes"""
        trends = {}
        
        for timeframe, klines in klines_data.items():
            if not klines or len(klines) < 2:
                trends[timeframe] = "NEUTRAL"
                continue
            
            try:
                # Get recent candles
                recent_candles = klines[-10:]  # Last 10 candles
                
                # Calculate simple trend
                prices = [float(candle[4]) for candle in recent_candles]  # Close prices
                
                if len(prices) >= 2:
                    price_change = (prices[-1] - prices[0]) / prices[0]
                    
                    if price_change > 0.02:  # 2% increase
                        trends[timeframe] = "BULLISH"
                    elif price_change < -0.02:  # 2% decrease
                        trends[timeframe] = "BEARISH"
                    else:
                        trends[timeframe] = "NEUTRAL"
                else:
                    trends[timeframe] = "NEUTRAL"
                    
            except Exception as e:
                logger.error(f"Error analyzing {timeframe} trend: {e}")
                trends[timeframe] = "NEUTRAL"
        
        return trends
    
    def _calculate_signal_strength(self, trends: Dict[str, str], oi_data: Dict, funding_data: Dict, ratio_data: Dict) -> float:
        """Calculate overall signal strength based on multiple factors"""
        strength = 0.0
        
        # Timeframe alignment (40% weight)
        bullish_count = sum(1 for trend in trends.values() if trend == "BULLISH")
        bearish_count = sum(1 for trend in trends.values() if trend == "BEARISH")
        total_timeframes = len(trends)
        
        if total_timeframes > 0:
            if bullish_count > bearish_count:
                strength += (bullish_count / total_timeframes) * 0.4
            elif bearish_count > bullish_count:
                strength -= (bearish_count / total_timeframes) * 0.4
        
        # Open Interest (20% weight)
        try:
            if oi_data and 'openInterest' in oi_data:
                # This would need actual OI change calculation
                strength += 0.1  # Placeholder
        except:
            pass
        
        # Funding Rate (20% weight)
        try:
            if funding_data and 'lastFundingRate' in funding_data:
                funding_rate = float(funding_data['lastFundingRate'])
                if funding_rate > Config.FUNDING_RATE_THRESHOLD:
                    strength -= 0.1  # Negative funding suggests short pressure
                elif funding_rate < -Config.FUNDING_RATE_THRESHOLD:
                    strength += 0.1  # Positive funding suggests long pressure
        except:
            pass
        
        # Long/Short Ratio (20% weight)
        try:
            if ratio_data and isinstance(ratio_data, list) and ratio_data:
                latest_ratio = ratio_data[-1]
                if 'longAccount' in latest_ratio and 'shortAccount' in latest_ratio:
                    long_ratio = float(latest_ratio['longAccount'])
                    if long_ratio > Config.RATIO_THRESHOLD:
                        strength -= 0.1  # Too many longs, potential reversal
                    elif long_ratio < (1 - Config.RATIO_THRESHOLD):
                        strength += 0.1  # Many shorts, potential squeeze
        except:
            pass
        
        return max(-1.0, min(1.0, strength))
    
    def _construct_structured_market_data(self, mexc_data: Dict, coinglass_data: Dict, symbol: str) -> Dict:
        """Construct structured market data for signal formatting"""
        structured_data = {
            'price_data': {},
            'coinglass_data': {},
            'kline_data': {},
            'timeframes_analyzed': ['5m', '15m', '30m', '1h', '4h']
        }
        
        # Process MEXC price data
        if mexc_data.get('ticker_24hr'):
            ticker = mexc_data['ticker_24hr']
            structured_data['price_data'] = {
                'markPrice': ticker.get('lastPrice', 0),
                'priceChangePercent': ticker.get('priceChangePercent', 0),
                'volume': ticker.get('volume', 0),
                'openPrice': ticker.get('openPrice', 0),
                'highPrice': ticker.get('highPrice', 0),
                'lowPrice': ticker.get('lowPrice', 0)
            }
        
        # Process K-line data for multiple timeframes
        if mexc_data.get('klines'):
            for timeframe, klines in mexc_data['klines'].items():
                if klines and len(klines) > 0:
                    # Get the latest candle
                    latest_candle = klines[-1]
                    structured_data['kline_data'][timeframe] = {
                        'open': latest_candle[1],
                        'high': latest_candle[2],
                        'low': latest_candle[3],
                        'close': latest_candle[4],
                        'volume': latest_candle[5]
                    }
        
        # Process Coinglass sentiment data
        try:
            # Funding rate
            if mexc_data.get('funding_rate'):
                funding = mexc_data['funding_rate']
                if funding and 'lastFundingRate' in funding:
                    structured_data['coinglass_data']['funding_rate'] = float(funding['lastFundingRate'])
            
            # Open interest
            if mexc_data.get('open_interest'):
                oi = mexc_data['open_interest']
                if oi and 'openInterest' in oi:
                    structured_data['coinglass_data']['open_interest'] = float(oi['openInterest'])
            
            # Long/Short ratio
            if mexc_data.get('long_short_ratio'):
                ls_ratio = mexc_data['long_short_ratio']
                if ls_ratio and isinstance(ls_ratio, list) and ls_ratio:
                    latest_ratio = ls_ratio[-1]
                    if 'longAccount' in latest_ratio:
                        structured_data['coinglass_data']['long_short_ratio'] = float(latest_ratio['longAccount'])
            
            # Additional Coinglass data
            if coinglass_data.get('pairs_markets'):
                cg_data = coinglass_data['pairs_markets']
                if isinstance(cg_data, list) and cg_data:
                    for market in cg_data:
                        if market.get('exchangeName') == 'MEXC':
                            if 'h24OpenInterestChange' in market:
                                structured_data['coinglass_data']['oi_change_24h'] = float(market['h24OpenInterestChange']) / 100
                            break
                            
        except Exception as e:
            logger.error(f"Error processing sentiment data: {e}")
        
        return structured_data
    
    async def generate_signal(self, symbol: str, force: bool = False) -> Optional[TradingSignal]:
        """Generate trading signal for a symbol"""
        # Check rate limiting
        if not force and not self._should_generate_signal(symbol):
            logger.info(f"Signal request for {symbol} rate limited")
            return None
        
        # Update request time
        self._update_request_time(symbol)
        
        try:
            # Collect data from both sources concurrently
            logger.info(f"Collecting market data for {symbol}")
            mexc_data, coinglass_data = await asyncio.gather(
                self._collect_mexc_data(symbol),
                self._collect_coinglass_data(symbol),
                return_exceptions=True
            )
            
            # Handle exceptions
            if isinstance(mexc_data, Exception):
                logger.error(f"MEXC data collection failed: {mexc_data}")
                mexc_data = {}
            
            if isinstance(coinglass_data, Exception):
                logger.error(f"Coinglass data collection failed: {coinglass_data}")
                coinglass_data = {}
            
            # Combine all market data
            combined_data = {
                'symbol': symbol,
                'mexc': mexc_data,
                'coinglass': coinglass_data,
                'timestamp': time.time()
            }
            
            # Analyze trends
            timeframe_trends = {}
            if 'klines' in mexc_data:
                timeframe_trends = self._analyze_timeframe_trends(mexc_data['klines'])
            
            # Calculate signal strength
            signal_strength = self._calculate_signal_strength(
                timeframe_trends,
                mexc_data.get('open_interest', {}),
                mexc_data.get('funding_rate', {}),
                mexc_data.get('long_short_ratio', {})
            )
            
            # Add analysis to combined data
            combined_data['analysis'] = {
                'timeframe_trends': timeframe_trends,
                'signal_strength': signal_strength
            }
            
            # Get market analysis from Gemini
            logger.info(f"Analyzing market data with Gemini AI for {symbol}")
            market_analysis = await self.gemini_analyzer.analyze_market_data(combined_data)
            
            # Generate trading signal
            logger.info(f"Generating trading signal for {symbol}")
            trading_signal = await self.gemini_analyzer.generate_trading_signal(
                symbol, combined_data, market_analysis
            )
            
            # Construct structured market data for the response
            structured_market_data = self._construct_structured_market_data(mexc_data, coinglass_data, symbol)
            
            # Add market data to the signal
            trading_signal.market_data = structured_market_data
            
            # Cache the signal
            self.signal_cache[symbol] = {
                'signal': trading_signal,
                'timestamp': time.time()
            }
            
            logger.info(f"Generated {trading_signal.signal} signal for {symbol} with {trading_signal.confidence:.2f} confidence")
            return trading_signal
            
        except Exception as e:
            logger.error(f"Error generating signal for {symbol}: {e}")
            return None
    
    async def get_market_explanation(self, symbol: str) -> str:
        """Get detailed market explanation"""
        try:
            # Collect basic data
            mexc_data = await self._collect_mexc_data(symbol)
            coinglass_data = await self._collect_coinglass_data(symbol)
            
            combined_data = {
                'symbol': symbol,
                'mexc': mexc_data,
                'coinglass': coinglass_data
            }
            
            return await self.gemini_analyzer.explain_market_conditions(symbol, combined_data)
            
        except Exception as e:
            logger.error(f"Error getting market explanation for {symbol}: {e}")
            return f"Unable to analyze market conditions for {symbol}: {str(e)}"
    
    async def get_supported_pairs(self) -> List[str]:
        """Get list of supported trading pairs"""
        try:
            # Get from Coinglass first (more reliable)
            cg_pairs = await self.coinglass_client.get_supported_exchange_pairs()
            
            if cg_pairs and 'MEXC' in cg_pairs:
                return cg_pairs['MEXC'][:50]  # Limit to first 50 pairs
            
            # Fallback to MEXC directly
            exchange_info = await self.mexc_client.get_exchange_info()
            if 'symbols' in exchange_info:
                usdt_pairs = [
                    symbol['symbol'] for symbol in exchange_info['symbols']
                    if symbol['quoteAsset'] == 'USDT' and symbol['status'] == 'TRADING'
                ]
                return usdt_pairs[:50]  # Limit to first 50 pairs
            
            return []
            
        except Exception as e:
            logger.error(f"Error getting supported pairs: {e}")
            return []
