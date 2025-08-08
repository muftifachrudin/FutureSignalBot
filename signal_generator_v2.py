"""
Improved signal generation logic using working APIs only
"""
import asyncio
import time
import logging
from typing import Dict, List, Optional
from mexc_client import MEXCClient
from coinglass_client import CoinglassClient
from gemini_analyzer import GeminiAnalyzer, TradingSignal
from config import Config

logger = logging.getLogger(__name__)

class ImprovedSignalGenerator:
    """Signal generator using only reliable API endpoints"""
    
    def __init__(self):
        self.mexc_client = None
        self.coinglass_client = None
        self.gemini_analyzer = GeminiAnalyzer()
        self.signal_cache = {}
        self.last_request_time = {}
    
    async def __aenter__(self):
        self.mexc_client = MEXCClient()
        self.coinglass_client = CoinglassClient()
        await self.mexc_client.__aenter__()
        await self.coinglass_client.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.mexc_client:
            await self.mexc_client.__aexit__(exc_type, exc_val, exc_tb)
        if self.coinglass_client:
            await self.coinglass_client.__aexit__(exc_type, exc_val, exc_tb)
    
    def _should_generate_signal(self, symbol: str) -> bool:
        """Check rate limiting"""
        current_time = time.time()
        last_time = self.last_request_time.get(symbol, 0)
        return (current_time - last_time) >= Config.SIGNAL_COOLDOWN_SECONDS
    
    def _update_request_time(self, symbol: str):
        """Update request time for rate limiting"""
        self.last_request_time[symbol] = time.time()
    
    async def _get_reliable_market_data(self, symbol: str) -> Dict:
        """Get market data from reliable sources only"""
        market_data = {
            'symbol': symbol,
            'mexc_ticker': {},
            'coinglass_markets': [],
            'price_analysis': {},
            'timestamp': time.time()
        }
        
        # Get MEXC ticker (most reliable)
        try:
            ticker = await self.mexc_client.get_24hr_ticker(symbol)
            if ticker:
                market_data['mexc_ticker'] = ticker
                logger.info(f"MEXC ticker for {symbol}: ${ticker.get('lastPrice', 'N/A')}")
        except Exception as e:
            logger.warning(f"Failed to get MEXC ticker for {symbol}: {e}")
        
        # Get Coinglass market data
        try:
            # Try with both BTC and BTCUSDT for symbol mapping
            base_symbol = symbol.replace('USDT', '')
            markets = await self.coinglass_client.get_pairs_markets(base_symbol)
            if markets and isinstance(markets, list):
                market_data['coinglass_markets'] = markets
                logger.info(f"Coinglass markets for {base_symbol}: {len(markets)} entries")
        except Exception as e:
            logger.warning(f"Failed to get Coinglass markets for {symbol}: {e}")
        
        return market_data
    
    def _analyze_price_action(self, ticker_data: Dict) -> Dict:
        """Analyze price action from ticker data"""
        analysis = {
            'trend': 'NEUTRAL',
            'strength': 0.0,
            'volatility': 'MEDIUM',
            'momentum': 'NEUTRAL'
        }
        
        try:
            if not ticker_data:
                return analysis
            
            price_change = float(ticker_data.get('priceChangePercent', 0))
            volume = float(ticker_data.get('volume', 0))
            high_price = float(ticker_data.get('highPrice', 0))
            low_price = float(ticker_data.get('lowPrice', 0))
            last_price = float(ticker_data.get('lastPrice', 0))
            
            # Trend analysis based on 24h change
            if price_change > 3:
                analysis['trend'] = 'STRONG_BULLISH'
                analysis['strength'] = min(price_change / 10, 1.0)
            elif price_change > 1:
                analysis['trend'] = 'BULLISH'
                analysis['strength'] = price_change / 10
            elif price_change < -3:
                analysis['trend'] = 'STRONG_BEARISH'
                analysis['strength'] = abs(price_change) / 10
            elif price_change < -1:
                analysis['trend'] = 'BEARISH'
                analysis['strength'] = abs(price_change) / 10
            
            # Volatility analysis
            if high_price > 0 and low_price > 0:
                daily_range = ((high_price - low_price) / last_price) * 100
                if daily_range > 5:
                    analysis['volatility'] = 'HIGH'
                elif daily_range < 2:
                    analysis['volatility'] = 'LOW'
            
            # Momentum analysis
            if abs(price_change) > 2:
                analysis['momentum'] = 'STRONG'
            elif abs(price_change) > 0.5:
                analysis['momentum'] = 'MODERATE'
            
        except Exception as e:
            logger.error(f"Error analyzing price action: {e}")
        
        return analysis
    
    def _analyze_market_sentiment(self, coinglass_data: List) -> Dict:
        """Analyze market sentiment from Coinglass data"""
        sentiment = {
            'funding_rate': 0.0,
            'open_interest_trend': 'NEUTRAL',
            'exchange_distribution': {},
            'sentiment_score': 0.0
        }
        
        try:
            if not coinglass_data:
                return sentiment
            
            mexc_data = None
            total_oi = 0
            
            # Find MEXC specific data and calculate totals
            for market in coinglass_data:
                if market.get('exchangeName') == 'MEXC':
                    mexc_data = market
                oi = float(market.get('openInterest', 0))
                total_oi += oi
            
            if mexc_data:
                # Funding rate analysis
                funding_rate = float(mexc_data.get('fundingRate', 0))
                sentiment['funding_rate'] = funding_rate
                
                # Open interest trend
                oi_change = float(mexc_data.get('h24OpenInterestChange', 0))
                if oi_change > 5:
                    sentiment['open_interest_trend'] = 'RISING'
                elif oi_change < -5:
                    sentiment['open_interest_trend'] = 'FALLING'
                
                # Calculate sentiment score
                sentiment_score = 0
                if funding_rate > 0.01:  # Positive funding (bullish)
                    sentiment_score += 0.3
                elif funding_rate < -0.01:  # Negative funding (bearish)
                    sentiment_score -= 0.3
                
                if oi_change > 0:  # Rising OI
                    sentiment_score += 0.2
                elif oi_change < 0:  # Falling OI
                    sentiment_score -= 0.2
                
                sentiment['sentiment_score'] = max(-1.0, min(1.0, sentiment_score))
            
        except Exception as e:
            logger.error(f"Error analyzing market sentiment: {e}")
        
        return sentiment
    
    async def generate_signal(self, symbol: str, force: bool = False) -> Optional[Dict]:
        """Generate trading signal using reliable data"""
        if not force and not self._should_generate_signal(symbol):
            logger.info(f"Signal request for {symbol} rate limited")
            return None
        
        self._update_request_time(symbol)
        
        try:
            # Get reliable market data
            market_data = await self._get_reliable_market_data(symbol)
            
            # Analyze price action
            price_analysis = self._analyze_price_action(market_data['mexc_ticker'])
            market_data['price_analysis'] = price_analysis
            
            # Analyze market sentiment
            sentiment_analysis = self._analyze_market_sentiment(market_data['coinglass_markets'])
            market_data['sentiment_analysis'] = sentiment_analysis
            
            # Generate signal using simplified but effective logic
            signal_result = self._generate_signal_from_analysis(symbol, price_analysis, sentiment_analysis)
            
            # Enhance with Gemini analysis if available
            try:
                gemini_prompt = f"""
Analyze this cryptocurrency market data for {symbol} and provide trading insight:

Price Analysis: {price_analysis}
Market Sentiment: {sentiment_analysis}
Current Price: ${market_data['mexc_ticker'].get('lastPrice', 'N/A')}
24h Change: {market_data['mexc_ticker'].get('priceChangePercent', 'N/A')}%

Based on this data, provide a brief analysis confirming or adjusting the signal direction.
Consider: trend strength, momentum, funding rates, and open interest changes.
"""
                
                gemini_response = await self.gemini_analyzer.explain_market_conditions(symbol, {'analysis': gemini_prompt})
                signal_result['ai_analysis'] = gemini_response[:500]  # Limit length
            except Exception as e:
                logger.warning(f"Gemini analysis failed: {e}")
                signal_result['ai_analysis'] = "AI analysis unavailable"
            
            # Add comprehensive market data
            signal_result['market_data'] = self._format_market_data(market_data)
            
            logger.info(f"Generated {signal_result['signal']} signal for {symbol} (confidence: {signal_result['confidence']:.2f})")
            return signal_result
            
        except Exception as e:
            logger.error(f"Error generating signal for {symbol}: {e}")
            return None
    
    def _generate_signal_from_analysis(self, symbol: str, price_analysis: Dict, sentiment_analysis: Dict) -> Dict:
        """Generate signal from price and sentiment analysis"""
        
        # Base signal determination
        trend = price_analysis.get('trend', 'NEUTRAL')
        strength = price_analysis.get('strength', 0.0)
        sentiment_score = sentiment_analysis.get('sentiment_score', 0.0)
        funding_rate = sentiment_analysis.get('funding_rate', 0.0)
        oi_trend = sentiment_analysis.get('open_interest_trend', 'NEUTRAL')
        
        # Signal logic
        signal = "WAIT"
        confidence = 0.1
        reasoning = ""
        
        # Bullish conditions
        if trend in ['BULLISH', 'STRONG_BULLISH'] and sentiment_score > 0:
            signal = "LONG"
            confidence = min(0.8, 0.4 + strength + abs(sentiment_score))
            reasoning = f"Bullish trend detected with {price_analysis.get('momentum', 'moderate')} momentum. "
            reasoning += f"Positive market sentiment (score: {sentiment_score:.2f}). "
            if oi_trend == 'RISING':
                reasoning += "Rising open interest supports the move. "
            confidence = min(0.9, confidence + 0.1)
        
        # Bearish conditions  
        elif trend in ['BEARISH', 'STRONG_BEARISH'] and sentiment_score < 0:
            signal = "SHORT"
            confidence = min(0.8, 0.4 + strength + abs(sentiment_score))
            reasoning = f"Bearish trend detected with {price_analysis.get('momentum', 'moderate')} momentum. "
            reasoning += f"Negative market sentiment (score: {sentiment_score:.2f}). "
            if oi_trend == 'FALLING':
                reasoning += "Falling open interest confirms weakness. "
            confidence = min(0.9, confidence + 0.1)
        
        # Neutral/Wait conditions
        else:
            reasoning = f"Mixed signals detected. Trend: {trend}, sentiment score: {sentiment_score:.2f}. "
            reasoning += f"Funding rate: {funding_rate:.4f}, OI trend: {oi_trend}. "
            reasoning += "Waiting for clearer directional bias before entering position."
        
        # Risk assessment
        volatility = price_analysis.get('volatility', 'MEDIUM')
        if volatility == 'HIGH':
            risk_level = 'HIGH'
        elif volatility == 'LOW' and confidence > 0.6:
            risk_level = 'LOW'
        else:
            risk_level = 'MEDIUM'
        
        return {
            'signal': signal,
            'confidence': confidence,
            'reasoning': reasoning,
            'risk_level': risk_level,
            'entry_price': None,  # Could be calculated based on current price
            'stop_loss': None,
            'take_profit': None
        }
    
    def _format_market_data(self, market_data: Dict) -> Dict:
        """Format market data for display"""
        ticker = market_data.get('mexc_ticker', {})
        coinglass = market_data.get('coinglass_markets', [])
        
        formatted = {
            'price_data': {
                'markPrice': ticker.get('lastPrice', 0),
                'priceChangePercent': ticker.get('priceChangePercent', 0),
                'volume': ticker.get('volume', 0),
                'highPrice': ticker.get('highPrice', 0),
                'lowPrice': ticker.get('lowPrice', 0)
            },
            'coinglass_data': {},
            'kline_data': {},  # Empty since klines not available
            'timeframes_analyzed': ['24h']  # Only 24h data available
        }
        
        # Extract Coinglass data
        if coinglass:
            mexc_market = next((m for m in coinglass if m.get('exchangeName') == 'MEXC'), {})
            if mexc_market:
                formatted['coinglass_data'] = {
                    'funding_rate': float(mexc_market.get('fundingRate', 0)),
                    'open_interest': float(mexc_market.get('openInterest', 0)),
                    'oi_change_24h': float(mexc_market.get('h24OpenInterestChange', 0)) / 100
                }
        
        return formatted