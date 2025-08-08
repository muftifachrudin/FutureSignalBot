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

💭 **Analysis:**
{reasoning}
"""
        
        if entry_price:
            message += f"\n🎯 **Entry:** {format_price(entry_price)}"
        
        if stop_loss:
            message += f"\n🛑 **Stop Loss:** {format_price(stop_loss)}"
        
        if take_profit:
            message += f"\n🎁 **Take Profit:** {format_price(take_profit)}"
        
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
