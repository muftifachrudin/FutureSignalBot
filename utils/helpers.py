"""
Helper utility functions for the trading signals bot
"""
import re
import time
import json
import hashlib
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone, timedelta
from models.signal_models import TradingSignal, SignalType, RiskLevel, TrendDirection
import logging

logger = logging.getLogger(__name__)

def format_signal_message(signal: TradingSignal) -> str:
    """Format trading signal for Telegram message"""
    try:
        # Signal emoji mapping
        signal_emoji = {
            SignalType.LONG: '🟢',
            SignalType.SHORT: '🔴',
            SignalType.WAIT: '🟡'
        }
        
        # Risk level emoji mapping
        risk_emoji = {
            RiskLevel.LOW: '🟢',
            RiskLevel.MEDIUM: '🟡', 
            RiskLevel.HIGH: '🔴'
        }
        
        emoji = signal_emoji.get(signal.signal, '⚪')
        risk_color = risk_emoji.get(signal.risk_level, '⚪')
        
        # Basic signal information
        message = f"""
{emoji} **{signal.signal.value} Signal for {signal.symbol}**

📊 **Confidence:** {signal.confidence:.1%}
⚠️ **Risk Level:** {risk_color} {signal.risk_level.value}

💭 **Analysis:**
{signal.reasoning}
"""
        
        # Add price levels if available
        if signal.entry_price:
            message += f"\n🎯 **Entry Price:** {format_price(signal.entry_price)}"
        
        if signal.stop_loss:
            message += f"\n🛑 **Stop Loss:** {format_price(signal.stop_loss)}"
        
        if signal.take_profit:
            message += f"\n🎁 **Take Profit:** {format_price(signal.take_profit)}"
        
        if signal.current_price:
            message += f"\n💰 **Current Price:** {format_price(signal.current_price)}"
        
        # Add market sentiment if available
        if signal.sentiment:
            funding_emoji = "📈" if signal.sentiment.funding_rate > 0 else "📉"
            message += f"\n\n📈 **Market Data:**"
            message += f"\n{funding_emoji} Funding Rate: {format_percentage(signal.sentiment.funding_rate)}"
            message += f"\n⚖️ Long/Short Ratio: {signal.sentiment.long_short_ratio:.2f}"
            
            if signal.sentiment.open_interest_change_24h != 0:
                oi_emoji = "📈" if signal.sentiment.open_interest_change_24h > 0 else "📉"
                message += f"\n{oi_emoji} OI Change 24h: {format_percentage(signal.sentiment.open_interest_change_24h)}"
        
        # Add timeframe analysis summary
        if signal.timeframe_analysis:
            bullish_tfs = sum(1 for tf_data in signal.timeframe_analysis.values() 
                            if tf_data.trend == TrendDirection.BULLISH)
            bearish_tfs = sum(1 for tf_data in signal.timeframe_analysis.values() 
                            if tf_data.trend == TrendDirection.BEARISH)
            total_tfs = len(signal.timeframe_analysis)
            
            message += f"\n\n⏰ **Timeframe Consensus:**"
            message += f"\n🟢 Bullish: {bullish_tfs}/{total_tfs}"
            message += f"\n🔴 Bearish: {bearish_tfs}/{total_tfs}"
        
        # Add timestamp
        message += f"\n\n🕐 Generated: {signal.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        
        return message
        
    except Exception as e:
        logger.error(f"Error formatting signal message: {e}")
        return f"❌ Error formatting signal for {signal.symbol if hasattr(signal, 'symbol') else 'Unknown'}"

def format_price(price: float, symbol: str = "USDT") -> str:
    """Format price with appropriate decimal places"""
    try:
        if price >= 1000:
            return f"${price:,.2f}"
        elif price >= 1:
            return f"${price:.4f}"
        elif price >= 0.01:
            return f"${price:.6f}"
        else:
            return f"${price:.8f}"
    except (TypeError, ValueError):
        return "N/A"

def format_percentage(value: float, decimals: int = 2) -> str:
    """Format percentage value"""
    try:
        return f"{value * 100:.{decimals}f}%"
    except (TypeError, ValueError):
        return "N/A"

def format_large_number(number: float) -> str:
    """Format large numbers with K, M, B suffixes"""
    try:
        if abs(number) >= 1_000_000_000:
            return f"{number / 1_000_000_000:.2f}B"
        elif abs(number) >= 1_000_000:
            return f"{number / 1_000_000:.2f}M"
        elif abs(number) >= 1_000:
            return f"{number / 1_000:.2f}K"
        else:
            return f"{number:.2f}"
    except (TypeError, ValueError):
        return "N/A"

def validate_symbol(symbol: str) -> str:
    """Validate and normalize trading symbol"""
    if not symbol:
        raise ValueError("Symbol cannot be empty")
    
    # Remove whitespace and convert to uppercase
    symbol = symbol.strip().upper()
    
    # Remove common prefixes/suffixes
    symbol = symbol.replace('$', '').replace('USD', '').replace('PERP', '')
    
    # Add USDT if not present and doesn't end with known quote currencies
    quote_currencies = ['USDT', 'BUSD', 'BTC', 'ETH', 'BNB']
    has_quote = any(symbol.endswith(quote) for quote in quote_currencies)
    
    if not has_quote:
        symbol += 'USDT'
    
    # Validate format
    if not re.match(r'^[A-Z0-9]{3,20}$', symbol):
        raise ValueError(f"Invalid symbol format: {symbol}")
    
    # Length validation
    if len(symbol) < 4 or len(symbol) > 20:
        raise ValueError(f"Symbol length must be between 4-20 characters: {symbol}")
    
    return symbol

def calculate_risk_reward_ratio(entry: float, stop_loss: float, take_profit: float) -> Optional[float]:
    """Calculate risk-reward ratio"""
    try:
        if not all([entry, stop_loss, take_profit]):
            return None
        
        risk = abs(entry - stop_loss)
        reward = abs(take_profit - entry)
        
        if risk == 0:
            return None
        
        return reward / risk
    except (TypeError, ValueError, ZeroDivisionError):
        return None

def calculate_position_size(account_balance: float, risk_percentage: float, entry: float, stop_loss: float) -> Optional[float]:
    """Calculate position size based on risk management"""
    try:
        if not all([account_balance, risk_percentage, entry, stop_loss]):
            return None
        
        risk_amount = account_balance * (risk_percentage / 100)
        price_difference = abs(entry - stop_loss)
        
        if price_difference == 0:
            return None
        
        position_size = risk_amount / price_difference
        return position_size
    except (TypeError, ValueError, ZeroDivisionError):
        return None

def is_market_hours() -> bool:
    """Check if it's trading hours (crypto markets are 24/7)"""
    return True  # Crypto markets never close

def calculate_timeframe_weight(timeframe: str) -> float:
    """Calculate weight for different timeframes in analysis"""
    weights = {
        '5m': 0.1,
        '15m': 0.15,
        '30m': 0.2,
        '1h': 0.25,
        '4h': 0.3
    }
    return weights.get(timeframe, 0.1)

def calculate_trend_strength(price_data: List[Dict]) -> float:
    """Calculate trend strength from price data"""
    try:
        if len(price_data) < 2:
            return 0.0
        
        closes = [float(candle.get('close', 0)) for candle in price_data]
        if not closes:
            return 0.0
        
        # Calculate price change percentage
        price_change = (closes[-1] - closes[0]) / closes[0]
        
        # Calculate consistency (how many candles follow the trend)
        trend_up = closes[-1] > closes[0]
        consistent_candles = 0
        
        for i in range(1, len(closes)):
            if trend_up and closes[i] >= closes[i-1]:
                consistent_candles += 1
            elif not trend_up and closes[i] <= closes[i-1]:
                consistent_candles += 1
        
        consistency = consistent_candles / (len(closes) - 1)
        
        # Combine price change and consistency
        strength = min(abs(price_change) * 10, 1.0) * consistency
        
        # Apply direction
        return strength if price_change > 0 else -strength
    except (TypeError, ValueError, IndexError):
        return 0.0

def detect_support_resistance(price_data: List[Dict], window: int = 20) -> Dict[str, Optional[float]]:
    """Detect support and resistance levels"""
    try:
        if len(price_data) < window:
            return {'support': None, 'resistance': None}
        
        highs = [float(candle.get('high', 0)) for candle in price_data[-window:]]
        lows = [float(candle.get('low', 0)) for candle in price_data[-window:]]
        
        if not highs or not lows:
            return {'support': None, 'resistance': None}
        
        # Simple support/resistance calculation
        resistance = max(highs)
        support = min(lows)
        
        return {'support': support, 'resistance': resistance}
    except (TypeError, ValueError, IndexError):
        return {'support': None, 'resistance': None}

def format_timeframe_analysis(timeframe_data: Dict) -> str:
    """Format timeframe analysis for display"""
    try:
        if not timeframe_data:
            return "No timeframe data available"
        
        lines = []
        for tf, data in timeframe_data.items():
            trend_emoji = {
                TrendDirection.BULLISH: "🟢",
                TrendDirection.BEARISH: "🔴",
                TrendDirection.NEUTRAL: "⚪"
            }.get(data.trend, "⚪")
            
            strength_bar = "█" * int(abs(data.strength) * 5)
            lines.append(f"{tf}: {trend_emoji} {data.trend.value} {strength_bar}")
        
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Error formatting timeframe analysis: {e}")
        return "Error formatting timeframe data"

def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert value to int"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def truncate_text(text: str, max_length: int = 4000) -> str:
    """Truncate text to fit Telegram message limits"""
    if not text:
        return ""
    
    if len(text) <= max_length:
        return text
    
    # Try to truncate at sentence boundary
    truncated = text[:max_length - 3]
    last_sentence = truncated.rfind('.')
    
    if last_sentence > max_length * 0.8:  # If we can keep at least 80% of content
        return truncated[:last_sentence + 1] + "..."
    
    return truncated + "..."

def generate_signal_id(symbol: str, timestamp: datetime) -> str:
    """Generate unique signal ID"""
    data = f"{symbol}_{timestamp.timestamp()}"
    return hashlib.md5(data.encode()).hexdigest()[:12]

def is_rate_limited(last_request_time: float, cooldown_seconds: int) -> bool:
    """Check if request is rate limited"""
    return (time.time() - last_request_time) < cooldown_seconds

def get_time_until_next_request(last_request_time: float, cooldown_seconds: int) -> int:
    """Get seconds until next request is allowed"""
    time_passed = time.time() - last_request_time
    return max(0, int(cooldown_seconds - time_passed))

def format_duration(seconds: int) -> str:
    """Format duration in human-readable format"""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"

def extract_symbol_from_text(text: str) -> Optional[str]:
    """Extract trading symbol from free text"""
    try:
        # Remove common words and clean text
        text = text.upper().strip()
        
        # Look for common patterns
        patterns = [
            r'\b([A-Z]{2,10}USDT)\b',  # Direct USDT pairs
            r'\b([A-Z]{2,10})\s*USDT\b',  # Symbol space USDT
            r'\b([A-Z]{2,10})/USDT\b',  # Symbol/USDT
            r'\b([A-Z]{2,10})\b'  # Just symbol
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                symbol = match.group(1)
                return validate_symbol(symbol)
        
        return None
    except Exception:
        return None

def calculate_volatility(price_data: List[Dict], period: int = 20) -> float:
    """Calculate price volatility"""
    try:
        if len(price_data) < period:
            return 0.0
        
        closes = [float(candle.get('close', 0)) for candle in price_data[-period:]]
        
        if len(closes) < 2:
            return 0.0
        
        # Calculate percentage changes
        changes = []
        for i in range(1, len(closes)):
            if closes[i-1] != 0:
                change = (closes[i] - closes[i-1]) / closes[i-1]
                changes.append(change)
        
        if not changes:
            return 0.0
        
        # Calculate standard deviation
        mean_change = sum(changes) / len(changes)
        variance = sum((x - mean_change) ** 2 for x in changes) / len(changes)
        volatility = variance ** 0.5
        
        return min(volatility, 1.0)  # Cap at 100%
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0

def format_market_conditions(analysis_data: Dict) -> str:
    """Format market conditions summary"""
    try:
        conditions = []
        
        # Trend analysis
        if 'trend' in analysis_data:
            trend = analysis_data['trend']
            conditions.append(f"📊 Trend: {trend}")
        
        # Volatility
        if 'volatility' in analysis_data:
            vol = analysis_data['volatility']
            vol_desc = "High" if vol > 0.7 else "Medium" if vol > 0.3 else "Low"
            conditions.append(f"📈 Volatility: {vol_desc}")
        
        # Volume
        if 'volume_trend' in analysis_data:
            vol_trend = analysis_data['volume_trend']
            conditions.append(f"📊 Volume: {vol_trend}")
        
        return " | ".join(conditions) if conditions else "Market conditions unclear"
    except Exception as e:
        logger.error(f"Error formatting market conditions: {e}")
        return "Unable to determine market conditions"

def validate_price_levels(entry: float, stop_loss: float, take_profit: float, signal_type: SignalType) -> bool:
    """Validate price levels make sense for the signal type"""
    try:
        if not all([entry, stop_loss, take_profit]):
            return True  # Optional levels
        
        if signal_type == SignalType.LONG:
            # For long: stop_loss < entry < take_profit
            return stop_loss < entry < take_profit
        elif signal_type == SignalType.SHORT:
            # For short: take_profit < entry < stop_loss  
            return take_profit < entry < stop_loss
        
        return True  # WAIT signals don't need validation
    except (TypeError, ValueError):
        return False
