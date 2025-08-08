"""
Utility functions for the trading bot
"""
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

def escape_markdown(text: str) -> str:
    """Escape characters that can break Telegram Markdown parsing.
    This is a light escape suitable for 'Markdown' mode (not MarkdownV2).
    """
    try:
        return (
            text.replace("*", "\\*")
                .replace("_", "\\_")
                .replace("[", "\\[")
                .replace("]", "\\]")
                .replace("(", "\\(")
                .replace(")", "\\)")
                .replace("`", "\\`")
        )
    except Exception:
        return text

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

def format_signal_message(symbol: str, signal_data: Dict[str, Any]) -> str:
    """Format trading signal untuk pesan Telegram (Bahasa Indonesia)."""
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

        message = (
            f"\n{signal_emoji} **Sinyal {signal}** untuk **{symbol}**\n\n"
            f"📊 **Kepercayaan:** {confidence:.1%}\n"
            f"⚠️ **Tingkat Risiko:** {risk_emoji} {risk_level}\n"
        )

        # Add detailed market statistics
        if price_data:
            current_price = price_data.get('markPrice', 0)
            change_24h = safe_get(price_data, 'priceChangePercent', default=0)
            volume_24h = safe_get(price_data, 'volume', default=0)

            message += (
                "\n📈 **Data Harga:**\n"
                f"• Saat ini: ${format_price(float(current_price))}\n"
                f"• Perubahan 24j: {format_percentage(float(change_24h)/100) if change_24h else 'N/A'}\n"
                f"• Volume 24j: {format_volume(float(volume_24h)) if volume_24h else 'N/A'}\n"
            )

        # Add K-line data if available
        kline_data = market_data.get('kline_data', {})
        if kline_data:
            message += "\n📊 **Data K-line (Multi-timeframe):**\n"
            for timeframe, data in kline_data.items():
                if data:
                    open_price = float(data.get('open', 0))
                    high_price = float(data.get('high', 0))
                    low_price = float(data.get('low', 0))
                    close_price = float(data.get('close', 0))
                    message += (
                        f"• {timeframe}: O:{format_price(open_price)} H:{format_price(high_price)} "
                        f"L:{format_price(low_price)} C:{format_price(close_price)}\n"
                    )

        # Add Coinglass sentiment data
        if coinglass_data:
            funding_rate = safe_get(coinglass_data, 'funding_rate')
            open_interest = safe_get(coinglass_data, 'open_interest')
            long_short_ratio = safe_get(coinglass_data, 'long_short_ratio')
            oi_change = safe_get(coinglass_data, 'oi_change_24h')
            liq_long = safe_get(coinglass_data, 'liquidations_long_usd')
            liq_short = safe_get(coinglass_data, 'liquidations_short_usd')
            fear_greed = safe_get(coinglass_data, 'fear_greed')

            message += "\n🔍 **Sentimen Pasar:**\n"
            if funding_rate is not None:
                funding_emoji = '🟢' if funding_rate > 0 else '🔴' if funding_rate < 0 else '⚪'
                message += f"• Tingkat Pendanaan: {funding_emoji} {format_percentage(funding_rate)}\n"

            if open_interest is not None:
                message += f"• Open Interest: {format_volume(open_interest)}\n"

            if oi_change is not None:
                try:
                    oi_val = float(oi_change)
                except Exception:
                    oi_val = 0.0
                oi_emoji = '🟢' if oi_val > 0 else '🔴' if oi_val < 0 else '⚪'
                # Coinglass OI change is already percent value, print directly with %
                message += f"• Perubahan OI 24j: {oi_emoji} {oi_val:.2f}%\n"

            if long_short_ratio is not None:
                try:
                    lsr = float(long_short_ratio)
                except Exception:
                    lsr = 0.0
                ls_emoji = '🟢' if lsr > 0.6 else '🔴' if lsr < 0.4 else '⚪'
                message += f"• Rasio Long/Short: {ls_emoji} {lsr:.2f}\n"

            # Optional: liquidation totals and Fear & Greed
            if liq_long is not None or liq_short is not None:
                try:
                    ll = float(liq_long or 0)
                    ls = float(liq_short or 0)
                    if ll or ls:
                        message += f"• Likuidasi: Long ${format_volume(ll)} | Short ${format_volume(ls)}\n"
                except Exception:
                    pass

            if fear_greed is not None:
                try:
                    fg = float(fear_greed)
                    if fg > 0:
                        message += f"• Fear & Greed: {fg:.0f}/100\n"
                except Exception:
                    pass

        message += (
            "\n💭 **Analisis:**\n" + escape_markdown(reasoning) + "\n"
        )

        # Trading levels
        if entry_price:
            message += f"\n🎯 **Entry:** ${format_price(entry_price)}"

        if stop_loss:
            message += f"\n🛑 **Stop Loss:** ${format_price(stop_loss)}"

        if take_profit:
            message += f"\n🎁 **Take Profit:** ${format_price(take_profit)}"

        # Timeframes analyzed
        timeframes = market_data.get('timeframes_analyzed', ['5m', '15m', '30m', '1h', '4h'])
        message += f"\n\n📊 **Rentang Waktu Dianalisis:** {' | '.join(timeframes)}"

        message += f"\n\n⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"

        return message

    except Exception as e:
        logger.error(f"Error formatting signal message: {e}")
        return f"❌ Error memformat sinyal untuk {symbol}"

def format_market_analysis(symbol: str, analysis: str) -> str:
    """Format analisis pasar untuk Telegram (Bahasa Indonesia)."""
    try:
        message = f"""
📈 **Analisis Pasar {symbol}**

{analysis}

⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
        return message
        
    except Exception as e:
        logger.error(f"Error formatting market analysis: {e}")
        return f"❌ Error formatting analysis for {symbol}"

def format_pairs_list(pairs: List[str], page: int = 1, page_size: int = 20) -> str:
    """Format daftar pasangan yang didukung dengan paginasi (Bahasa Indonesia)."""
    try:
        if not pairs:
            return "❌ Tidak ada pasangan yang didukung"
        
        total_pairs = len(pairs)
        total_pages = (total_pairs + page_size - 1) // page_size
        
        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, total_pairs)
        
        page_pairs = pairs[start_idx:end_idx]

        message = f"📋 **Daftar Pasangan Perdagangan** (Halaman {page}/{total_pages})\n\n"

        for i, pair in enumerate(page_pairs, 1):
            message += f"{start_idx + i}. `{pair}`\n"
        
        if total_pages > 1:
            message += f"\n📄 Menampilkan {len(page_pairs)} dari total {total_pairs} pasangan"
        
        return message

    except Exception as e:
        logger.error(f"Error formatting pairs list: {e}")
        return "❌ Error memformat daftar pasangan"

def validate_symbol(symbol: str) -> str:
    """Validasi dan normalisasi simbol trading"""
    try:
        # Remove whitespace and convert to uppercase
        symbol = symbol.strip().upper()
        
        # Add USDT if not present
        if not symbol.endswith('USDT'):
            symbol += 'USDT'
        
        # Basic validation
        if len(symbol) < 4 or len(symbol) > 20:
            raise ValueError("Panjang simbol tidak valid")
        
        return symbol
        
    except Exception as e:
        logger.error(f"Error validating symbol {symbol}: {e}")
        raise ValueError(f"Simbol tidak valid: {symbol}")

def is_rate_limited(last_time: float, cooldown_seconds: int) -> bool:
    """Check if action is rate limited"""
    return (time.time() - last_time) < cooldown_seconds

def get_timeframe_display() -> str:
    """Teks rentang waktu yang dianalisis (Bahasa Indonesia)."""
    timeframes = ["5m", "15m", "30m", "1h", "4h"]
    return "📊 **Rentang Waktu Dianalisis:** " + " | ".join(timeframes)

def truncate_text(text: str, max_length: int = 4000) -> str:
    """Truncate text to fit Telegram message limits"""
    if len(text) <= max_length:
        return text
    
    return text[:max_length - 3] + "..."

from typing import Mapping, cast

def safe_get(data: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely get nested dictionary values"""
    try:
        cur: Any = data
        for key in keys:
            if isinstance(cur, Mapping) and key in cur:
                # Help type checkers understand the mapping access
                cur = cast(Mapping[str, Any], cur)[key]  # type: ignore[index]
            else:
                return default
        return cur
    except (KeyError, TypeError):
        return default

def format_error_message(error: str, symbol: Optional[str] = None) -> str:
    """Format pesan error untuk pengguna (Bahasa Indonesia)."""
    symbol_text = f" untuk {symbol}" if symbol else ""
    return f"❌ **Error{symbol_text}**\n\n{error}\n\nSilakan coba lagi nanti atau hubungi dukungan."

def log_api_call(api_name: str, endpoint: str, success: bool, duration: Optional[float] = None):
    """Log API call for monitoring"""
    status = "SUCCESS" if success else "FAILED"
    duration_text = f" ({duration:.2f}s)" if duration else ""
    logger.info(f"API Call - {api_name}: {endpoint} - {status}{duration_text}")
