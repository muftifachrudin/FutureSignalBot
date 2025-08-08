"""
Utility functions for the trading bot
"""
import time
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

def format_price(price: float, decimals: int = 4) -> str:
    """Format price with appropriate decimal places"""
    try:
        return f"{price:.{decimals}f}"
    except:
        return "N/A"

def format_percentage(value: float, decimals: int = 2) -> str:
    """Format percentage value"""
    try:
        return f"{value * 100:.{decimals}f}%"
    except:
        return "N/A"

def format_volume(volume: float) -> str:
    """Format volume with appropriate suffixes"""
    try:
        if volume >= 1_000_000_000:
            return f"{volume / 1_000_000_000:.2f}B"
        elif volume >= 1_000_000:
            return f"{volume / 1_000_000:.2f}M"
        elif volume >= 1_000:
            return f"{volume / 1_000:.2f}K"
        else:
            return f"{volume:.2f}"
    except:
        return "N/A"

def format_signal_message(symbol: str, signal_data: Dict) -> str:
    """Format trading signal for Telegram message"""
    try:
        signal = signal_data.get('signal', 'WAIT')
        confidence = signal_data.get('confidence', 0.0)
        reasoning = signal_data.get('reasoning', 'No reasoning provided')
        entry_price = signal_data.get('entry_price')
        stop_loss = signal_data.get('stop_loss')
        take_profit = signal_data.get('take_profit')
        risk_level = signal_data.get('risk_level', 'MEDIUM')
        
        # Market data
        market_data = signal_data.get('market_data', {})
        price_data = market_data.get('price_data', {})
        coinglass_data = market_data.get('coinglass_data', {})
        
        # Signal emoji
        signal_emoji = {
            'LONG': '🟢',
            'SHORT': '🔴', 
            'WAIT': '🟡'
        }.get(signal, '⚪')
        
        # Risk emoji
        risk_emoji = {
            'LOW': '🟢',
            'MEDIUM': '🟡',
            'HIGH': '🔴'
        }.get(risk_level, '⚪')
        
        message = f"""
{signal_emoji} **{signal}** Signal for **{symbol}**

📊 **Confidence:** {confidence:.1%}
⚠️ **Risk Level:** {risk_emoji} {risk_level}
"""
        
        # Add detailed market statistics
        if price_data:
            current_price = price_data.get('markPrice', 0)
            change_24h = safe_get(price_data, 'priceChangePercent', default=0)
            volume_24h = safe_get(price_data, 'volume', default=0)
            
            message += f"""
📈 **Price Data:**
• Current: ${format_price(float(current_price))}
• 24h Change: {format_percentage(float(change_24h)/100) if change_24h else 'N/A'}
• 24h Volume: {format_volume(float(volume_24h)) if volume_24h else 'N/A'}
"""
        
        # Add K-line data if available
        kline_data = market_data.get('kline_data', {})
        if kline_data:
            message += f"""
📊 **K-line Data (Multi-timeframe):**
"""
            for timeframe, data in kline_data.items():
                if data:
                    open_price = float(data.get('open', 0))
                    high_price = float(data.get('high', 0))
                    low_price = float(data.get('low', 0))
                    close_price = float(data.get('close', 0))
                    
                    message += f"• {timeframe}: O:{format_price(open_price)} H:{format_price(high_price)} L:{format_price(low_price)} C:{format_price(close_price)}\n"
        
        # Add Coinglass sentiment data
        if coinglass_data:
            funding_rate = safe_get(coinglass_data, 'funding_rate')
            open_interest = safe_get(coinglass_data, 'open_interest')
            long_short_ratio = safe_get(coinglass_data, 'long_short_ratio')
            oi_change = safe_get(coinglass_data, 'oi_change_24h')
            
            message += f"""
🔍 **Market Sentiment:**
"""
            if funding_rate is not None:
                funding_emoji = '🟢' if funding_rate > 0 else '🔴' if funding_rate < 0 else '⚪'
                message += f"• Funding Rate: {funding_emoji} {format_percentage(funding_rate)}\n"
            
            if open_interest is not None:
                message += f"• Open Interest: {format_volume(open_interest)}\n"
            
            if oi_change is not None:
                oi_emoji = '🟢' if oi_change > 0 else '🔴' if oi_change < 0 else '⚪'
                message += f"• OI 24h Change: {oi_emoji} {format_percentage(oi_change)}\n"
            
            if long_short_ratio is not None:
                ls_emoji = '🟢' if long_short_ratio > 0.6 else '🔴' if long_short_ratio < 0.4 else '⚪'
                message += f"• Long/Short Ratio: {ls_emoji} {long_short_ratio:.2f}\n"
        
        message += f"""
💭 **Analysis:**
{reasoning}
"""
        
        # Trading levels
        if entry_price:
            message += f"\n🎯 **Entry:** ${format_price(entry_price)}"
        
        if stop_loss:
            message += f"\n🛑 **Stop Loss:** ${format_price(stop_loss)}"
        
        if take_profit:
            message += f"\n🎁 **Take Profit:** ${format_price(take_profit)}"
        
        # Timeframes analyzed
        timeframes = market_data.get('timeframes_analyzed', ['5m', '15m', '30m', '1h', '4h'])
        message += f"\n\n📊 **Analyzed Timeframes:** {' | '.join(timeframes)}"
        
        message += f"\n\n⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        
        return message
        
    except Exception as e:
        logger.error(f"Error formatting signal message: {e}")
        return f"❌ Error formatting signal for {symbol}"

def format_market_analysis(symbol: str, analysis: str) -> str:
    """Format market analysis for Telegram"""
    try:
        message = f"""
📈 **Market Analysis for {symbol}**

{analysis}

⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
        return message
        
    except Exception as e:
        logger.error(f"Error formatting market analysis: {e}")
        return f"❌ Error formatting analysis for {symbol}"

def format_pairs_list(pairs: List[str], page: int = 1, page_size: int = 20) -> str:
    """Format supported pairs list with pagination"""
    try:
        if not pairs:
            return "❌ No supported pairs found"
        
        total_pairs = len(pairs)
        total_pages = (total_pairs + page_size - 1) // page_size
        
        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, total_pairs)
        
        page_pairs = pairs[start_idx:end_idx]
        
        message = f"📋 **Supported Trading Pairs** (Page {page}/{total_pages})\n\n"
        
        for i, pair in enumerate(page_pairs, 1):
            message += f"{start_idx + i}. `{pair}`\n"
        
        if total_pages > 1:
            message += f"\n📄 Showing {len(page_pairs)} of {total_pairs} total pairs"
        
        return message
        
    except Exception as e:
        logger.error(f"Error formatting pairs list: {e}")
        return "❌ Error formatting pairs list"

def validate_symbol(symbol: str) -> str:
    """Validate and normalize trading symbol"""
    try:
        # Remove whitespace and convert to uppercase
        symbol = symbol.strip().upper()
        
        # Add USDT if not present
        if not symbol.endswith('USDT'):
            symbol += 'USDT'
        
        # Basic validation
        if len(symbol) < 4 or len(symbol) > 20:
            raise ValueError("Invalid symbol length")
        
        return symbol
        
    except Exception as e:
        logger.error(f"Error validating symbol {symbol}: {e}")
        raise ValueError(f"Invalid symbol: {symbol}")

def is_rate_limited(last_time: float, cooldown_seconds: int) -> bool:
    """Check if action is rate limited"""
    return (time.time() - last_time) < cooldown_seconds

def get_timeframe_display() -> str:
    """Get formatted timeframe information"""
    timeframes = ["5m", "15m", "30m", "1h", "4h"]
    return "📊 **Analyzed Timeframes:** " + " | ".join(timeframes)

def truncate_text(text: str, max_length: int = 4000) -> str:
    """Truncate text to fit Telegram message limits"""
    if len(text) <= max_length:
        return text
    
    return text[:max_length - 3] + "..."

def safe_get(data: Dict, *keys, default: Any = None) -> Any:
    """Safely get nested dictionary values"""
    try:
        for key in keys:
            data = data[key]
        return data
    except (KeyError, TypeError):
        return default

def format_error_message(error: str, symbol: str = None) -> str:
    """Format error message for user display"""
    symbol_text = f" for {symbol}" if symbol else ""
    return f"❌ **Error{symbol_text}**\n\n{error}\n\nPlease try again later or contact support."

def log_api_call(api_name: str, endpoint: str, success: bool, duration: float = None):
    """Log API call for monitoring"""
    status = "SUCCESS" if success else "FAILED"
    duration_text = f" ({duration:.2f}s)" if duration else ""
    logger.info(f"API Call - {api_name}: {endpoint} - {status}{duration_text}")
