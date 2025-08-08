"""
Improved signal generation logic using working APIs only
"""
import asyncio
import time
import logging
from typing import Dict, List, Optional, Any
from mexc_client import MEXCClient
from coinglass_client import CoinglassClient
from gemini_analyzer import GeminiAnalyzer, TradingSignal
from config import Config
import math
import statistics

logger = logging.getLogger(__name__)

class ImprovedSignalGenerator:
    """Signal generator using only reliable API endpoints"""
    
    def __init__(self):
        self.mexc_client = None
        self.coinglass_client = None
        self.gemini_analyzer = GeminiAnalyzer()
        self.signal_cache = {}
        self.last_request_time = {}
        self._pairs_cache = {"ts": 0.0, "data": []}
    
    async def __aenter__(self):
        self.mexc_client = MEXCClient()
        self.coinglass_client = CoinglassClient()
        await self.mexc_client.__aenter__()
        await self.coinglass_client.__aenter__()
        return self
    
    async def __aexit__(self, exc_type: Optional[type], exc_val: Optional[BaseException], exc_tb: Optional[Any]) -> None:
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
    
    async def _get_reliable_market_data(self, symbol: str) -> Dict[str, Any]:
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
    
    def _analyze_price_action(self, ticker_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze price action from ticker data"""
        analysis = {
            'trend': 'NEUTRAL',
            'strength': 0.0,
            'volatility': 'MEDIUM',
            'momentum': 'NEUTRAL',
            'price_change_percent': 0.0,
            'daily_range_percent': 0.0,
            'volume': 0.0
        }
        
        try:
            if not ticker_data:
                return analysis
            
            price_change = float(ticker_data.get('priceChangePercent', 0))
            volume = float(ticker_data.get('volume', 0))
            high_price = float(ticker_data.get('highPrice', 0))
            low_price = float(ticker_data.get('lowPrice', 0))
            last_price = float(ticker_data.get('lastPrice', 0))
            analysis['price_change_percent'] = price_change
            analysis['volume'] = volume
            
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
                analysis['daily_range_percent'] = daily_range
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
    
    def _analyze_market_sentiment(self, coinglass_data: List[Dict[str, Any]]) -> Dict[str, Any]:
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
            funding_samples: List[float] = []
            oi_change_samples: List[float] = []
            
            for market in coinglass_data:
                # Collect samples for robust fallback
                try:
                    if 'fundingRate' in market:
                        funding_samples.append(float(market.get('fundingRate') or 0.0))
                except Exception:
                    pass
                try:
                    if 'h24OpenInterestChange' in market:
                        oi_change_samples.append(float(market.get('h24OpenInterestChange') or 0.0))
                except Exception:
                    pass
                if market.get('exchangeName') == 'MEXC':
                    mexc_data = market

            # Prefer MEXC metrics, else use median across exchanges to avoid 0.0
            def _median(values: List[float]) -> float:
                try:
                    return statistics.median([v for v in values if isinstance(v, (int, float))]) if values else 0.0
                except Exception:
                    return 0.0

            funding_rate = 0.0
            oi_change = 0.0
            if mexc_data:
                try:
                    funding_rate = float(mexc_data.get('fundingRate') or 0.0)
                except Exception:
                    funding_rate = 0.0
                try:
                    oi_change = float(mexc_data.get('h24OpenInterestChange') or 0.0)
                except Exception:
                    oi_change = 0.0

            if abs(funding_rate) < 1e-9:
                funding_rate = _median(funding_samples)
            if abs(oi_change) < 1e-9:
                oi_change = _median(oi_change_samples)

            sentiment['funding_rate'] = funding_rate
            if oi_change > 5:
                sentiment['open_interest_trend'] = 'RISING'
            elif oi_change < -5:
                sentiment['open_interest_trend'] = 'FALLING'

            # Sentiment score blending funding and OI
            score = 0.0
            if funding_rate > 0.01:
                score += 0.3
            elif funding_rate < -0.01:
                score -= 0.3
            if oi_change > 0:
                score += 0.2
            elif oi_change < 0:
                score -= 0.2
            sentiment['sentiment_score'] = max(-1.0, min(1.0, score))
            
        except Exception as e:
            logger.error(f"Error analyzing market sentiment: {e}")
        
        return sentiment
    
    async def generate_signal(self, symbol: str, force: bool = False) -> Optional[Dict[str, Any]]:
        """Generate trading signal using reliable data"""
        now = time.time()
        if not force and not self._should_generate_signal(symbol):
            # Try return cached signal within cooldown window
            cached = self.signal_cache.get(symbol)
            if cached and (now - cached.get('timestamp', 0)) <= Config.SIGNAL_COOLDOWN_SECONDS:
                logger.info(f"Returning cached signal for {symbol} (within cooldown)")
                return cached.get('data')
            logger.info(f"Signal request for {symbol} rate limited and no cache available")
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

            # Cache the result with timestamp for quick reuse
            self.signal_cache[symbol] = {"timestamp": time.time(), "data": signal_result}

            logger.info(f"Generated {signal_result['signal']} signal for {symbol} (confidence: {signal_result['confidence']:.2f})")
            return signal_result
            
        except Exception as e:
            logger.error(f"Error generating signal for {symbol}: {e}")
            return None
    
    def _generate_signal_from_analysis(self, symbol: str, price_analysis: Dict[str, Any], sentiment_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate signal from price and sentiment analysis"""
        
        # Base signal determination
        trend = price_analysis.get('trend', 'NEUTRAL')
        strength = price_analysis.get('strength', 0.0)
        sentiment_score = sentiment_analysis.get('sentiment_score', 0.0)
        funding_rate = sentiment_analysis.get('funding_rate', 0.0)
        oi_trend = sentiment_analysis.get('open_interest_trend', 'NEUTRAL')
        
        # Signal logic (improved, non-zero confidence & localized)
        signal = "WAIT"
        confidence = 0.2  # minimal baseline agar tidak 0
        reasoning = ""
        
        # Bullish conditions
        if trend in ['BULLISH', 'STRONG_BULLISH'] and sentiment_score > 0:
            signal = "LONG"
            # tambahkan bobot dari perubahan harga & OI
            price_chg = float(price_analysis.get('price_change_percent', 0.0))
            base = 0.4 + strength + min(abs(sentiment_score), 0.6)
            base += 0.1 if oi_trend == 'RISING' else 0.0
            base += 0.05 if price_chg > 2 else 0.0
            confidence = max(confidence, min(0.92, base))
            reasoning = (
                f"Tren bullish terdeteksi dengan momentum {price_analysis.get('momentum', 'sedang')}. "
                f"Sentimen pasar positif (skor: {sentiment_score:.2f}). "
            )
            if oi_trend == 'RISING':
                reasoning += "Open interest yang meningkat mendukung kenaikan. "
        
        # Bearish conditions  
        elif trend in ['BEARISH', 'STRONG_BEARISH'] and sentiment_score < 0:
            signal = "SHORT"
            price_chg = float(price_analysis.get('price_change_percent', 0.0))
            base = 0.4 + strength + min(abs(sentiment_score), 0.6)
            base += 0.1 if oi_trend == 'FALLING' else 0.0
            base += 0.05 if price_chg < -2 else 0.0
            confidence = max(confidence, min(0.92, base))
            reasoning = (
                f"Tren bearish terdeteksi dengan momentum {price_analysis.get('momentum', 'sedang')}. "
                f"Sentimen pasar negatif (skor: {sentiment_score:.2f}). "
            )
            if oi_trend == 'FALLING':
                reasoning += "Open interest yang menurun menegaskan pelemahan. "
        
        # Neutral/Wait conditions
        else:
            price_chg = float(price_analysis.get('price_change_percent', 0.0))
            reasoning = (
                f"Sinyal campuran terdeteksi. Tren: {trend}, skor sentimen: {sentiment_score:.2f}. "
                f"Funding rate: {funding_rate:.4f}, OI: {oi_trend}, Perubahan 24j: {price_chg:.2f}%. "
                "Tunggu konfirmasi arah yang lebih jelas sebelum masuk posisi."
            )
        
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
    
    def _format_market_data(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
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
            def _to_float(x):
                try:
                    return float(x)
                except Exception:
                    return 0.0
            funding = _to_float(mexc_market.get('fundingRate')) if mexc_market else 0.0
            oi = _to_float(mexc_market.get('openInterest')) if mexc_market else 0.0
            oi_chg = _to_float(mexc_market.get('h24OpenInterestChange')) if mexc_market else 0.0
            # Fallback to median across exchanges when missing/zero
            if (not mexc_market) or (abs(funding) < 1e-9 and abs(oi_chg) < 1e-9):
                f_samples = [_to_float(m.get('fundingRate')) for m in coinglass if 'fundingRate' in m]
                oi_samples = [_to_float(m.get('h24OpenInterestChange')) for m in coinglass if 'h24OpenInterestChange' in m]
                try:
                    funding = statistics.median([v for v in f_samples if isinstance(v, (int, float)) and not math.isnan(v)]) if f_samples else 0.0
                except Exception:
                    funding = 0.0
                try:
                    oi_chg = statistics.median([v for v in oi_samples if isinstance(v, (int, float)) and not math.isnan(v)]) if oi_samples else 0.0
                except Exception:
                    oi_chg = 0.0
            formatted['coinglass_data'] = {
                'funding_rate': funding,
                'open_interest': oi,
                'oi_change_24h': oi_chg  # keep as percent value
            }
        
        return formatted

    async def analyze_timeframe(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        """Analyze a symbol for a given timeframe using MEXC klines and simple indicators.
        timeframe: one of '5m','15m','30m','1h','4h'
        Returns dict with indicators and recommendation, or None if unavailable.
        """
        tf = timeframe.lower()
        tf_map = {"5m": "5m", "15m": "15m", "30m": "30m", "1h": "1h", "4h": "4h"}
        if tf not in tf_map:
            tf = "15m"

        # Fetch klines (spot). Need enough candles for EMA50/RSI(14): request 200
        klines = await self.mexc_client.get_klines(symbol, tf_map[tf], limit=200)
        if not klines or len(klines) < 60:
            return None

        # Parse closes/highs/lows
        closes: List[float] = []
        highs: List[float] = []
        lows: List[float] = []
        for k in klines:
            try:
                # Expected format: [openTime, open, high, low, close, volume, closeTime, ...]
                highs.append(float(k[2]))
                lows.append(float(k[3]))
                closes.append(float(k[4]))
            except Exception:
                continue
        if len(closes) < 60:
            return None

        def ema(series: List[float], period: int) -> float:
            if not series or period <= 1:
                return series[-1] if series else 0.0
            k = 2 / (period + 1)
            ema_val = series[0]
            for price in series[1:]:
                ema_val = price * k + ema_val * (1 - k)
            return ema_val

        def rsi(series: List[float], period: int = 14) -> float:
            if len(series) < period + 1:
                return 50.0
            gains = []
            losses = []
            for i in range(1, len(series)):
                change = series[i] - series[i - 1]
                gains.append(max(change, 0.0))
                losses.append(max(-change, 0.0))
            # Use simple moving average of last 'period'
            avg_gain = sum(gains[-period:]) / period
            avg_loss = sum(losses[-period:]) / max(period, 1)
            if avg_loss == 0:
                return 100.0
            rs = avg_gain / avg_loss
            return 100 - (100 / (1 + rs))

        def atr_pct(h: List[float], l: List[float], c: List[float], period: int = 14) -> float:
            if len(c) < period + 1:
                return 0.0
            trs: List[float] = []
            prev_close = c[0]
            for i in range(1, len(c)):
                tr = max(h[i] - l[i], abs(h[i] - prev_close), abs(l[i] - prev_close))
                trs.append(tr)
                prev_close = c[i]
            if not trs:
                return 0.0
            atr = sum(trs[-period:]) / period
            last_close = c[-1] if c else 1.0
            return (atr / last_close) * 100

        ema20 = ema(closes[-120:], 20)
        ema50 = ema(closes[-120:], 50)
        rsi14 = rsi(closes, 14)
        atrp = atr_pct(highs, lows, closes, 14)

        trend = "BULLISH" if ema20 >= ema50 else "BEARISH"
        volatility = "HIGH" if atrp > 3.5 else ("LOW" if atrp < 1.5 else "MEDIUM")

        # Recommendation score blending heuristic features (simulating a small DL model output)
        score = 0.5
        if trend == "BULLISH":
            score += 0.15
        else:
            score -= 0.15
        # RSI contribution: prefer 45-65, penalize extremes
        if 45 <= rsi14 <= 65:
            score += 0.1
        elif rsi14 < 30:
            score -= 0.15
        elif rsi14 > 70:
            score -= 0.15
        # Volatility adjustment
        if volatility == "LOW":
            score += 0.05
        elif volatility == "HIGH":
            score -= 0.05
        score = max(0.0, min(1.0, score))

        if score >= 0.6 and trend == "BULLISH":
            reco = "LONG"
        elif score <= 0.4 and trend == "BEARISH":
            reco = "SHORT"
        else:
            reco = "WAIT"

        explanation = (
            f"EMA20 {('>' if ema20 >= ema50 else '<')} EMA50 → {trend}. "
            f"RSI(14) {rsi14:.1f} menunjukkan {'overbought' if rsi14>70 else ('oversold' if rsi14<30 else 'netral')}. "
            f"ATR% {atrp:.2f} → volatilitas {volatility}. Rekomendasi: {reco}."
        )

        return {
            'timeframe': tf,
            'trend': trend,
            'volatility': volatility,
            'ema20': float(ema20),
            'ema50': float(ema50),
            'rsi': float(rsi14),
            'atrp': float(atrp),
            'recommendation': reco,
            'score': float(score),
            'explanation': explanation,
        }

    async def get_market_explanation(self, symbol: str) -> str:
        """Return a concise market explanation string for a symbol.
        Uses Gemini when available, otherwise falls back to a simple summary built from reliable data.
        """
        try:
            market_data = await self._get_reliable_market_data(symbol)

            # Prefer Gemini explanation if available
            try:
                explanation = await self.gemini_analyzer.explain_market_conditions(symbol, market_data)
                if explanation:
                    return explanation
            except Exception as e:
                logger.warning(f"Gemini explanation failed for {symbol}: {e}")

            # Fallback: build a lightweight human-readable summary
            ticker = market_data.get('mexc_ticker', {})
            cg_list = market_data.get('coinglass_markets', [])
            funding_rate = 0.0
            oi_change = 0.0
            if cg_list:
                mexc_market = next((m for m in cg_list if m.get('exchangeName') == 'MEXC'), {})
                if mexc_market:
                    try:
                        funding_rate = float(mexc_market.get('fundingRate', 0))
                    except Exception:
                        funding_rate = 0.0
                    try:
                        oi_change = float(mexc_market.get('h24OpenInterestChange', 0))
                    except Exception:
                        oi_change = 0.0

            change_pct = 0.0
            try:
                change_pct = float(ticker.get('priceChangePercent', 0))
            except Exception:
                change_pct = 0.0

            parts = []
            last_price = ticker.get('lastPrice')
            if last_price:
                parts.append(f"Harga: ${last_price} | 24j: {change_pct:.2f}%")
            if funding_rate:
                parts.append(f"Funding: {funding_rate:.4%}")
            if oi_change:
                parts.append(f"OI 24j: {oi_change:.2f}%")

            sentiment_hint = "Kondisi netral."
            if change_pct > 1 and funding_rate >= 0 and oi_change >= 0:
                sentiment_hint = "Bias bullish dengan dukungan funding/OI."
            elif change_pct < -1 and funding_rate <= 0 and oi_change <= 0:
                sentiment_hint = "Bias bearish dengan funding/OI yang negatif."

            summary = " | ".join(parts) if parts else "Data terbatas tersedia."
            return f"{summary}\n{sentiment_hint}"

        except Exception as e:
            logger.error(f"Error building market explanation for {symbol}: {e}")
            return "Unable to analyze market conditions right now."

    async def get_supported_pairs(self) -> List[str]:
        """Return a list of supported trading pairs (USDT quote) from MEXC exchange info.
        Falls back to a small default list if API unavailable.
        """
        try:
            # Cache with TTL 60s
            now = time.time()
            if (now - float(self._pairs_cache.get('ts', 0))) <= 60 and self._pairs_cache.get('data'):
                return list(self._pairs_cache['data'])

            info = await self.mexc_client.get_exchange_info()
            pairs: List[str] = []
            symbols_list = []
            if isinstance(info, dict):
                # Common schema: { symbols: [ { symbol, quoteAsset, status } ] }
                symbols_list = info.get('symbols') or info.get('data') or []
            if isinstance(symbols_list, list):
                for s in symbols_list:
                    sym = s.get('symbol') or s.get('symbolName') or ''
                    quote = s.get('quoteAsset') or ''
                    status = (s.get('status') or '').upper()
                    if sym and (sym.endswith('USDT') or quote == 'USDT'):
                        # Filter to active symbols when status provided
                        if not status or status in ('ENABLED', 'TRADING', 'ONLINE'):
                            pairs.append(sym)
            # Deduplicate and sort
            if pairs:
                pairs = sorted(set(pairs))
                self._pairs_cache = {"ts": now, "data": pairs}
                return pairs
        except Exception as e:
            logger.warning(f"Failed to load supported pairs from MEXC: {e}")

        # Fallback popular pairs
        return [
            'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'SOLUSDT',
            'XRPUSDT', 'DOGEUSDT', 'DOTUSDT', 'MATICUSDT', 'LTCUSDT'
        ]