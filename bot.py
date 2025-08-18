"""
Telegram bot implementation for trading signals (python-telegram-bot v22)
"""
from __future__ import annotations

import asyncio
import logging
import os
from types import TracebackType
from typing import Any, Dict, List, Optional, Protocol, Type, TypedDict, cast

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from utils import (
    format_error_message,
    format_market_analysis,
    format_pairs_list,
    format_signal_message,
    get_timeframe_display,
    truncate_text,
    split_message,
    validate_symbol,
)
from pairs_store import PairsStore
from pairs_usage_store import PairsUsageStore

# Initialize module-level logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load configuration (fallbacks to environment variable if config module is unavailable)
try:
    from config import Config  # type: ignore
except Exception:  # pragma: no cover - minimal fallback
    class Config:  # type: ignore
        TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")


class TimeframeResult(TypedDict, total=False):
    timeframe: str
    trend: str
    volatility: str
    ema20: float
    ema50: float
    rsi: float
    atrp: float
    recommendation: str
    score: float
    explanation: str


class SignalResult(TypedDict, total=False):
    signal: str
    confidence: float
    reasoning: str
    risk_level: str
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    ai_analysis: str
    market_data: Dict[str, Any]


class SignalGeneratorProtocol(Protocol):
    async def __aenter__(self) -> "SignalGeneratorProtocol": ...

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> Optional[bool]: ...

    async def generate_signal(self, symbol: str, force: bool = False) -> Optional[SignalResult]: ...

    async def get_supported_pairs(self) -> List[str]: ...

    async def get_market_explanation(self, symbol: str) -> str: ...

    async def analyze_timeframe(self, symbol: str, timeframe: str) -> Optional[TimeframeResult]: ...


def _get_generator_class() -> Type[SignalGeneratorProtocol]:
    """Return an async context manager class that implements the signal generator protocol.
    Tries ImprovedSignalGenerator, then PairsCache from signal_generator_v2. Falls back to a stub.
    """
    try:
        import signal_generator_v2 as _sg  # type: ignore

        gen = getattr(_sg, "ImprovedSignalGenerator", None)
        if gen is None:
            gen = getattr(_sg, "PairsCache", None)
        if gen is not None:
            return cast(Type[SignalGeneratorProtocol], gen)
    except Exception:
        pass

    class _StubGenerator:
        async def __aenter__(self) -> "SignalGeneratorProtocol":
            return cast(SignalGeneratorProtocol, self)

        async def __aexit__(
            self,
            exc_type: Optional[Type[BaseException]],
            exc: Optional[BaseException],
            tb: Optional[TracebackType],
        ) -> Optional[bool]:
            return False

        async def generate_signal(self, symbol: str, force: bool = False) -> Optional[SignalResult]:
            return None

        async def get_supported_pairs(self) -> List[str]:
            return []

        async def get_market_explanation(self, symbol: str) -> str:  # noqa: ARG002
            return ""

        async def analyze_timeframe(self, symbol: str, timeframe: str) -> Optional[TimeframeResult]:  # noqa: ARG002
            return None

    return cast(Type[SignalGeneratorProtocol], _StubGenerator)


GeneratorClass: Type[SignalGeneratorProtocol] = _get_generator_class()


class TradingSignalBot:
    # Per-user state for custom pair input flow
    awaiting_custom: Dict[int, str]
    def __init__(self) -> None:
        self.token: str = Config.TELEGRAM_BOT_TOKEN
        # Fully parameterize Application generics to avoid Unknown types from stubs
        self.application: Optional[Application[Any, Any, Any, Any, Any, Any]] = None
        self.signal_generator: Optional[SignalGeneratorProtocol] = None
        # Dynamic pairs store (admin-managed watchlist)
        try:
            path = getattr(Config, 'PAIRS_WATCHLIST_PATH', '') or None
        except Exception:
            path = None
        self.pairs_store: PairsStore = PairsStore(path)
        # Track users awaiting a custom pair input; value indicates mode ('both' => signal+analysis)
        self.awaiting_custom = {}
        # Popular pairs usage tracking
        try:
            usage_path = getattr(Config, 'PAIRS_USAGE_PATH', '') or None
        except Exception:
            usage_path = None
        self.usage_store: PairsUsageStore = PairsUsageStore(usage_path)

    def run(self) -> None:
        """Run the bot using Application.run_polling (blocking)."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            logger.info("Starting Telegram bot (run_polling)...")
            self.application = Application.builder().token(self.token).build()
            self._add_handlers()
            # Initialize the signal generator context
            self.signal_generator = loop.run_until_complete(self._enter_signal_generator())
            assert self.application is not None
            self.application.run_polling(close_loop=False)
        except Exception as e:
            logger.exception(f"Bot encountered an error: {e}")
        finally:
            try:
                if self.signal_generator:
                    loop.run_until_complete(self.signal_generator.__aexit__(None, None, None))
            except Exception as e:
                logger.warning(f"Error during signal generator cleanup: {e}")
            finally:
                asyncio.set_event_loop(None)
                loop.close()

    async def _enter_signal_generator(self) -> SignalGeneratorProtocol:
        gen = GeneratorClass()
        await gen.__aenter__()
        return gen

    async def stop(self) -> None:
        try:
            if self.application:
                await self.application.stop()
        except Exception as e:
            logger.warning(f"Error during bot stop: {e}")
        finally:
            if self.signal_generator:
                try:
                    await self.signal_generator.__aexit__(None, None, None)
                except Exception as e2:
                    logger.warning(f"Error during signal generator exit: {e2}")

    def _add_handlers(self) -> None:
        application: Optional[Application[Any, Any, Any, Any, Any, Any]] = self.application
        if application is None:
            logger.warning("Application not initialized; cannot add handlers yet.")
            return
        # Global error handler
        application.add_error_handler(self.error_handler)
        # Command handlers
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("signal", self.signal_command))
        application.add_handler(CommandHandler("scalp", self.scalp_command))
        application.add_handler(CommandHandler("analyze", self.analyze_command))
        application.add_handler(CommandHandler("pairs", self.pairs_command))
        application.add_handler(CommandHandler("pairs_add", self.pairs_add_command))
        application.add_handler(CommandHandler("pairs_remove", self.pairs_remove_command))
        application.add_handler(CommandHandler("timeframes", self.timeframes_command))
        application.add_handler(CommandHandler("about", self.about_command))
        # Callback & message handlers
        application.add_handler(CallbackQueryHandler(self.button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_symbol_message))

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:  # pragma: no cover
        """Handle all unexpected errors to avoid noisy stack traces."""
        try:
            logger.error("Unhandled exception in Telegram handler", exc_info=context.error)
            if isinstance(update, Update) and update.effective_message:
                await update.effective_message.reply_text(
                    "⚠️ Terjadi kesalahan tak terduga. Silakan coba lagi."
                )
        except Exception:
            # Never raise inside the error handler
            pass

    # Commands
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        msg = update.effective_message
        if not msg:
            return
        # Concise welcome like image 3
        welcome_message = (
            "\n".join([
                "🤖 **Selamat datang di Bot Sinyal Perdagangan MEXC Futures!**",
                "",
                "Pilih menu di bawah untuk memulai:",
            ])
        )
        keyboard = [
            [InlineKeyboardButton("📊 Pasangan Populer", callback_data="popular_pairs")],
            [InlineKeyboardButton("📈 Dapatkan Sinyal", callback_data="get_signal"),
             InlineKeyboardButton("🔍 Analisis Pasar", callback_data="market_analysis")],
            [InlineKeyboardButton("ℹ️ Bantuan", callback_data="help")]
        ]
        await msg.reply_text(welcome_message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        msg = update.effective_message
        if not msg:
            return
        help_message = (
            "\n".join([
                "📚 **Panduan Bantuan**",
                "",
                "**🎯 Perintah Sinyal:**",
                "• `/signal BTCUSDT` - Dapatkan sinyal untuk Bitcoin",
                "• `/signal ETH` - Sinyal cepat (USDT otomatis ditambahkan)",
                "",
                "**📊 Perintah Analisis:**  ",
                "• `/analyze BTCUSDT` - Analisis pasar rinci",
                "• `/pairs` - Lihat semua pasangan yang didukung",
                "• `/timeframes` - Lihat timeframe analisis",
                "",
                "**🤖 Tipe Sinyal:**",
                "• 🟢 **LONG** - Sinyal beli saat kondisi bullish",
                "• 🔴 **SHORT** - Sinyal jual saat kondisi bearish  ",
                "• 🟡 **WAIT** - Tunggu saat kondisi belum jelas",
                "",
                "**📈 Faktor Analisis:**",
                "• Tren harga pada 5 timeframe",
                "• Perubahan open interest (OI)",
                "• Funding rate (biaya pendanaan)",
                "• Rasio long/short",
                "• Konfirmasi volume",
                "• Support/resistance",
                "",
                "**⚠️ Manajemen Risiko:**",
                "• Selalu gunakan stop loss",
                "• Atur ukuran posisi sesuai",
                "• Jangan mempertaruhkan lebih dari yang sanggup rugi",
                "• Sinyal hanya untuk edukasi",
                "",
                "**🔄 Batasan Permintaan:**",
                "• Cooldown 5 menit per pasangan",
                "• Mencegah spam dan menjaga kualitas analisis",
                "",
                "**💡 Tips:**",
                "• Jadikan sinyal sebagai bagian dari analisis menyeluruh",
                "• Kombinasikan dengan riset pribadi",
                "• Perhatikan banyak timeframe",
                "• Ikuti aturan manajemen risiko",
            ])
        )
        await msg.reply_text(help_message, parse_mode='Markdown')

    async def about_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        msg = update.effective_message
        if not msg:
            return
        about_message = (
            "\n".join([
                "🤖 **Bot Sinyal Perdagangan MEXC Futures**",
                "",
                "**🔧 Teknologi:**",
                "• 🤖 Gemini AI untuk analisis cerdas",
                "• 📊 Coinglass API untuk sentimen pasar",
                "• 💹 MEXC API untuk data trading",
                "• ⚡ Analisis multi-timeframe real-time",
                "",
                "**📈 Sumber Data:**",
                "• Aksi harga di 5 timeframe",
                "• Perubahan open interest",
                "• Funding rate",
                "• Rasio long/short",
                "• Volume dan volatilitas",
                "• Support/resistance",
                "",
                "**🎯 Logika Sinyal:**",
                "• **LONG**: Kesesuaian bullish + funding positif + short ratio tinggi + OI naik",
                "• **SHORT**: Kesesuaian bearish + funding negatif + long ratio tinggi + OI turun  ",
                "• **WAIT**: Sinyal campuran atau kondisi belum jelas",
                "",
                "**⚠️ Disclaimer Penting:**",
                "• Sinyal untuk tujuan edukasi",
                "• Kinerja masa lalu tidak menjamin hasil masa depan",
                "• Selalu gunakan manajemen risiko yang benar",
                "• Jangan invest lebih dari yang mampu ditanggung",
                "• Bukan nasihat finansial",
                "",
                "**🔒 Keamanan:**",
                "• Tidak perlu izin trading",
                "• Akses data pasar read-only",
                "• Manajemen API key yang aman",
                "• Tidak menyimpan data pribadi",
                "",
                "**📧 Dukungan:**",
                "Untuk masalah teknis atau pertanyaan, silakan hubungi dukungan.",
                "",
                "**Version:** 1.0.0",
                "**Last Updated:** 2025",
            ])
        )
        await msg.reply_text(about_message, parse_mode='Markdown')

    async def timeframes_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        msg = update.effective_message
        if not msg:
            return
        message = (
            "\n".join([
                "⏰ **Rentang Waktu (Timeframes)**",
                "",
                "Pilih timeframe untuk analisis khusus, lalu pilih pasangan (mis. BTCUSDT):",
                "",
                "• 5m — scalping cepat",
                "• 15m — intraday aktif  ",
                "• 30m — tren menengah",
                "• 1h — konfirmasi tren",
                "• 4h — arah utama",
                "",
                get_timeframe_display(),
                "",
                "Setelah memilih timeframe, pilih pasangan untuk melihat analisis indikator (EMA/RSI/ATR) dan rekomendasi.",
            ])
        )
        keyboard = [
            [
                InlineKeyboardButton("5m", callback_data="tf_5m"),
                InlineKeyboardButton("15m", callback_data="tf_15m"),
                InlineKeyboardButton("30m", callback_data="tf_30m"),
                InlineKeyboardButton("1h", callback_data="tf_1h"),
                InlineKeyboardButton("4h", callback_data="tf_4h"),
            ],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
        ]
        await msg.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def pairs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        msg = update.effective_message
        if not msg:
            return
        processing_msg = await msg.reply_text("🔄 **Memuat daftar pasangan yang didukung...**", parse_mode='Markdown')
        # Combine dynamic watchlist with exchange supported (intersection to avoid stale)
        try:
            assert self.signal_generator is not None
            supported = set(await self.signal_generator.get_supported_pairs())
        except Exception:
            # Explicit type annotation to avoid 'set[Unknown]' diagnostic
            supported: set[str] = set()
        watchlist = await self.pairs_store.get_pairs()
        display_pairs = [p for p in watchlist if p in supported] or watchlist
        message = format_pairs_list(display_pairs)
        admin_hint = ""
        if self._is_admin(update):
            admin_hint = ("\n\n🔧 Admin: gunakan /pairs_add SYMBOL atau /pairs_remove SYMBOL."
                          " Contoh: /pairs_add ARBUSDT")
        message += admin_hint
        keyboard = [
            [InlineKeyboardButton("🎯 Dapatkan Sinyal", callback_data="get_signal_input"),
             InlineKeyboardButton("➕ Pair Kustom", callback_data="custom_pair")],
            [InlineKeyboardButton("🔄 Muat Ulang", callback_data="refresh_pairs")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
        ]
        await processing_msg.edit_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    def _is_admin(self, update: Update) -> bool:
        try:
            user_id = update.effective_user.id if update.effective_user else None
        except Exception:
            return False
        return bool(user_id and user_id in getattr(Config, 'ADMIN_USER_IDS', []))

    async def pairs_add_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        if not msg:
            return
        if not self._is_admin(update):
            await msg.reply_text("❌ Akses ditolak. Hanya admin yang dapat menambah pasangan.")
            return
        if not context.args:
            await msg.reply_text("Gunakan: /pairs_add SYMBOL (mis. /pairs_add ARBUSDT)")
            return
        symbol = validate_symbol(context.args[0])
        added = await self.pairs_store.add_pair(symbol)
        if added:
            await msg.reply_text(f"✅ Ditambahkan: {symbol}")
        else:
            await msg.reply_text(f"⚠️ Gagal menambah {symbol}. Mungkin sudah ada atau simbol tidak valid.")

    async def pairs_remove_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        if not msg:
            return
        if not self._is_admin(update):
            await msg.reply_text("❌ Akses ditolak. Hanya admin yang dapat menghapus pasangan.")
            return
        if not context.args:
            await msg.reply_text("Gunakan: /pairs_remove SYMBOL (mis. /pairs_remove ARBUSDT)")
            return
        symbol = validate_symbol(context.args[0])
        removed = await self.pairs_store.remove_pair(symbol)
        if removed:
            await msg.reply_text(f"🗑️ Dihapus: {symbol}")
        else:
            await msg.reply_text(f"⚠️ {symbol} tidak ditemukan di watchlist.")

    async def signal_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        if not msg:
            return
        if not context.args:
            await msg.reply_text(
                "❌ Mohon sertakan simbol trading.\n\n**Contoh:** `/signal BTCUSDT`",
                parse_mode='Markdown'
            )
            return
        symbol = validate_symbol(context.args[0])
        processing_msg = await msg.reply_text(
            f"🔄 **Menganalisis {symbol}...**\n\nMengambil data dari berbagai sumber...",
            parse_mode='Markdown'
        )
        assert self.signal_generator is not None
        # Track usage
        try:
            await self.usage_store.increment(symbol)
        except Exception:
            pass
        signal = await self.signal_generator.generate_signal(symbol)
        if signal:
            message = format_signal_message(symbol, cast(Dict[str, Any], signal)) + f"\n\n{get_timeframe_display()}"
            keyboard = [
                [InlineKeyboardButton("🔄 Muat Ulang", callback_data=f"refresh_signal_{symbol}")],
                [InlineKeyboardButton("📊 Analisis Pasar", callback_data=f"analyze_{symbol}")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
            ]
            parts = split_message(message)
            # Replace the first message, then send follow-ups if any
            await processing_msg.edit_text(parts[0], reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            for extra in parts[1:]:
                await msg.reply_text(extra, parse_mode='Markdown')
        else:
            await processing_msg.edit_text(format_error_message("Gagal membuat sinyal.", symbol), parse_mode='Markdown')

    async def scalp_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        if not msg:
            return
        if not context.args:
            await msg.reply_text(
                "❌ Mohon sertakan simbol trading.\n\n**Contoh:** `/scalp BTCUSDT`",
                parse_mode='Markdown'
            )
            return
        symbol = validate_symbol(context.args[0])
        processing_msg = await msg.reply_text(
            f"⚡ **Scalping snapshot {symbol}...**",
            parse_mode='Markdown'
        )
        try:
            assert self.signal_generator is not None
            # dynamic check if generator has get_scalp_snapshot
            gen = self.signal_generator
            if hasattr(gen, 'get_scalp_snapshot'):
                snapshot = await cast(Any, gen).get_scalp_snapshot(symbol)
            else:
                snapshot = None
            if snapshot:
                keyboard = [
                    [InlineKeyboardButton("🔄 Refresh", callback_data=f"signal_{symbol}"),
                     InlineKeyboardButton("📊 Analisis", callback_data=f"analyze_{symbol}")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
                ]
                await processing_msg.edit_text(truncate_text(snapshot), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            else:
                await processing_msg.edit_text(
                    format_error_message("Gagal membuat snapshot scalping (fitur belum siap).", symbol),
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"Error scalp command {symbol}: {e}")
            await processing_msg.edit_text(
                format_error_message("Kesalahan saat membuat snapshot scalping.", symbol),
                parse_mode='Markdown'
            )

    async def analyze_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.effective_message
        if not msg:
            return
        if not context.args:
            await msg.reply_text(
                "❌ Mohon sertakan simbol trading.\n\n**Contoh:** `/analyze BTCUSDT`",
                parse_mode='Markdown'
            )
            return
        symbol = validate_symbol(context.args[0])
        processing_msg = await msg.reply_text(
            f"🔍 **Menganalisis kondisi pasar {symbol}...**",
            parse_mode='Markdown'
        )
        assert self.signal_generator is not None
        # Track usage
        try:
            await self.usage_store.increment(symbol)
        except Exception:
            pass
        analysis = await self.signal_generator.get_market_explanation(symbol)
        if analysis:
            message = format_market_analysis(symbol, analysis)
            keyboard = [
                [InlineKeyboardButton("🎯 Dapatkan Sinyal", callback_data=f"signal_{symbol}")],
                [InlineKeyboardButton("🔄 Muat Ulang Analisis", callback_data=f"analyze_{symbol}")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
            ]
            parts = split_message(message)
            await processing_msg.edit_text(parts[0], reply_markup=InlineKeyboardMarkup(keyboard))
            for extra in parts[1:]:
                await msg.reply_text(extra)
        else:
            await processing_msg.edit_text(format_error_message("Gagal menganalisis kondisi pasar.", symbol), parse_mode='Markdown')

    async def handle_symbol_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        msg = update.effective_message
        if not msg or not msg.text:
            return
        # If awaiting custom input for this user, consume this message as the symbol
        user_id = update.effective_user.id if update.effective_user else None
        awaiting_mode = self.awaiting_custom.pop(int(user_id), None) if user_id else None
        try:
            symbol = validate_symbol(msg.text)
        except ValueError:
            await msg.reply_text(
                "❌ Format simbol tidak valid. Gunakan format seperti `BTCUSDT` atau ketik `/help` untuk bantuan.",
                parse_mode='Markdown'
            )
            return
        if awaiting_mode == 'both':
            try:
                processing = await msg.reply_text(f"🔄 Memproses **{symbol}** (sinyal + analisis)...", parse_mode='Markdown')
                assert self.signal_generator is not None
                try:
                    await self.usage_store.increment(symbol, by=2)
                except Exception:
                    pass
                signal = await self.signal_generator.generate_signal(symbol)
                analysis = await self.signal_generator.get_market_explanation(symbol)
                if signal:
                    message = format_signal_message(symbol, cast(Dict[str, Any], signal)) + f"\n\n{get_timeframe_display()}"
                    sig_kb = [
                        [InlineKeyboardButton("🔄 Muat Ulang", callback_data=f"refresh_signal_{symbol}")],
                        [InlineKeyboardButton("📊 Analisis", callback_data=f"analyze_{symbol}")],
                        [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
                    ]
                    parts = split_message(message)
                    await processing.edit_text(parts[0], reply_markup=InlineKeyboardMarkup(sig_kb), parse_mode='Markdown')
                    for extra in parts[1:]:
                        await msg.reply_text(extra, parse_mode='Markdown')
                else:
                    await processing.edit_text(format_error_message("Gagal membuat sinyal.", symbol), parse_mode='Markdown')
                if analysis:
                    atext = format_market_analysis(symbol, analysis)
                    for chunk in split_message(atext):
                        await msg.reply_text(chunk, parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Error in custom pair processing for {symbol}: {e}")
                await msg.reply_text(format_error_message("Terjadi kesalahan saat memproses pair kustom.", symbol), parse_mode='Markdown')
        else:
            keyboard = [
                [InlineKeyboardButton("🎯 Dapatkan Sinyal", callback_data=f"signal_{symbol}")],
                [InlineKeyboardButton("📊 Analisis Pasar", callback_data=f"analyze_{symbol}")]
            ]
            await msg.reply_text(
                f"📈 **{symbol}** - Pilih aksi di bawah:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )

    # Callback router
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        query = update.callback_query
        if not query:
            return
        await query.answer()
        data = query.data or ""
        try:
            if data == "popular_pairs":
                await self._handle_popular_pairs(query)
            elif data == "main_menu":
                await self._render_main_menu(query)
            elif data in ("get_signal", "get_signal_input"):
                await self._handle_get_signal_prompt(query)
            elif data == "market_analysis":
                await self._handle_market_analysis_prompt(query)
            elif data.startswith("tf_") and data.count("_") == 1:
                timeframe = data.split("_", 1)[1]
                await self._handle_timeframe_select(query, timeframe)
            elif data.startswith("tf_analyze_"):
                parts = data.split("_", 3)
                if len(parts) == 4:
                    timeframe = parts[2]
                    symbol = parts[3]
                    await self._handle_timeframe_analyze(query, timeframe, symbol)
            elif data == "help":
                await self._handle_help_callback(query)
            elif data.startswith("signal_"):
                symbol = data.split("_", 1)[1]
                await self._handle_signal_callback(query, symbol)
            elif data.startswith("analyze_"):
                symbol = data.split("_", 1)[1]
                await self._handle_analyze_callback(query, symbol)
            elif data.startswith("refresh_signal_"):
                symbol = data.split("_", 2)[2]
                await self._handle_refresh_signal(query, symbol)
            elif data == "refresh_pairs":
                await self._handle_refresh_pairs(query)
            elif data == "custom_pair":
                await self._handle_custom_pair_prompt(query)
            else:
                await query.edit_message_text("❌ Aksi tidak dikenal.")
        except Exception as e:
            logger.error(f"Error handling callback {data}: {e}")
            await query.edit_message_text("❌ An error occurred. Please try again.")

    # Callback helpers
    async def _render_main_menu(self, query: CallbackQuery) -> None:
        welcome_message = (
            "\n".join([
                "🤖 **Selamat datang di Bot Sinyal Perdagangan MEXC Futures!**",
                "",
                "Pilih menu di bawah untuk memulai:",
            ])
        )
        keyboard = [
            [InlineKeyboardButton("📊 Pasangan Populer", callback_data="popular_pairs")],
            [InlineKeyboardButton("📈 Dapatkan Sinyal", callback_data="get_signal"),
             InlineKeyboardButton("🔍 Analisis Pasar", callback_data="market_analysis")],
            [InlineKeyboardButton("ℹ️ Bantuan", callback_data="help")]
        ]
        await query.edit_message_text(welcome_message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _handle_popular_pairs(self, query: CallbackQuery) -> None:
        # Build dynamic top-N by usage, intersect with supported symbols for safety
        try:
            assert self.signal_generator is not None
            supported = await self.signal_generator.get_supported_pairs()
        except Exception:
            supported = []
        try:
            top = await self.usage_store.get_top_n(8, allowed=supported or None)
        except Exception:
            top = []
        # Fallback to a small static list if no usage yet
        if not top:
            top = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT", "XRPUSDT", "DOGEUSDT", "ARBUSDT"]
        message = "🔥 **Pasangan Populer**\n\nPilih pasangan untuk mendapatkan sinyal:\n\n"
        keyboard: List[List[InlineKeyboardButton]] = []
        # Render in 2-column rows
        for i in range(0, len(top), 2):
            row: List[InlineKeyboardButton] = []
            for j in range(2):
                if i + j < len(top):
                    pair = top[i + j]
                    row.append(InlineKeyboardButton(pair, callback_data=f"signal_{pair}"))
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("📋 Semua Pasangan", callback_data="refresh_pairs")])
        keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")])
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _handle_get_signal_prompt(self, query: CallbackQuery) -> None:
        message = (
            "\n".join([
                "🎯 **Dapatkan Sinyal**",
                "",
                "Kirim simbol trading untuk mendapatkan analisis berbasis AI:",
                "",
                "**Contoh:**",
                "• `BTCUSDT` atau cukup `BTC`",
                "• `ETHUSDT` atau cukup `ETH`  ",
                "• `ADAUSDT` atau cukup `ADA`",
                "",
                "Atau gunakan: `/signal SYMBOL`",
            ])
        )
        keyboard = [[InlineKeyboardButton("🔥 Pasangan Populer", callback_data="popular_pairs")]]
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _handle_timeframe_select(self, query: CallbackQuery, timeframe: str) -> None:
        message = (
            "\n".join([
                f"⏰ Timeframe dipilih: **{timeframe}**",
                "",
                "Pilih pasangan untuk dianalisis pada timeframe ini, atau kirim simbol manual (mis. `BTCUSDT`).",
            ])
        )
        # Use dynamic top-N for timeframe selection too (smaller set)
        keyboard: List[List[InlineKeyboardButton]] = []
        try:
            assert self.signal_generator is not None
            supported = await self.signal_generator.get_supported_pairs()
        except Exception:
            supported = []
        try:
            top = await self.usage_store.get_top_n(6, allowed=supported or None)
        except Exception:
            top = []
        if not top:
            top = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT", "XRPUSDT"]
        row: List[InlineKeyboardButton] = []
        for i, p in enumerate(top, start=1):
            row.append(InlineKeyboardButton(p, callback_data=f"tf_analyze_{timeframe}_{p}"))
            if i % 3 == 0:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")])
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _handle_timeframe_analyze(self, query: CallbackQuery, timeframe: str, symbol: str) -> None:
        await query.edit_message_text(
            f"🔍 **Analisis {symbol} ({timeframe})...**\n\nMenghitung indikator (EMA/RSI/ATR) dan rekomendasi...",
            parse_mode='Markdown'
        )
        try:
            assert self.signal_generator is not None
            result = await self.signal_generator.analyze_timeframe(symbol, timeframe)
            if not result:
                await query.edit_message_text(
                    format_error_message("Gagal menganalisis timeframe.", symbol),
                    parse_mode='Markdown'
                )
                return
            lines = [
                f"⏰ Timeframe: {result.get('timeframe')} | Simbol: {symbol}",
                f"📈 Tren: {result.get('trend')} | Volatilitas: {result.get('volatility')}",
                f"EMA20: {float(result.get('ema20', 0.0)):.4f} | EMA50: {float(result.get('ema50', 0.0)):.4f}",
                f"RSI(14): {float(result.get('rsi', 0.0)):.2f} | ATR%: {float(result.get('atrp', 0.0)):.2f}%",
                f"🤖 Rekomendasi: {result.get('recommendation')} | Skor: {float(result.get('score', 0.0)):.2f}",
            ]
            summary = "\n".join(lines)
            explanation = result.get('explanation') or ""
            message = f"{summary}\n\n{truncate_text(explanation)}"
            keyboard = [
                [InlineKeyboardButton("🎯 Dapatkan Sinyal 24j", callback_data=f"signal_{symbol}")],
                [
                    InlineKeyboardButton("5m", callback_data="tf_5m"),
                    InlineKeyboardButton("15m", callback_data="tf_15m"),
                    InlineKeyboardButton("30m", callback_data="tf_30m"),
                    InlineKeyboardButton("1h", callback_data="tf_1h"),
                    InlineKeyboardButton("4h", callback_data="tf_4h"),
                ],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
            ]
            await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error in timeframe analyze for {symbol} {timeframe}: {e}")
            await query.edit_message_text(
                format_error_message("Terjadi kesalahan saat analisis timeframe.", symbol),
                parse_mode='Markdown'
            )

    async def _handle_market_analysis_prompt(self, query: CallbackQuery) -> None:
        message = (
            "\n".join([
                "📊 **Analisis Pasar**",
                "",
                "Kirim simbol trading untuk analisis pasar rinci:",
                "",
                "**Contoh:**",
                "• `BTCUSDT` - Analisis Bitcoin",
                "• `ETHUSDT` - Analisis Ethereum",
                "• `BNBUSDT` - Analisis BNB",
                "",
                "Atau gunakan: `/analyze SYMBOL`",
            ])
        )
        keyboard = [[InlineKeyboardButton("🔥 Pasangan Populer", callback_data="popular_pairs")]]
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _handle_help_callback(self, query: CallbackQuery) -> None:
        help_message = (
            "\n".join([
                "📚 **Bantuan Cepat**",
                "",
                "**Perintah:**",
                "• `/signal BTCUSDT` - Dapatkan sinyal",
                "• `/analyze ETHUSDT` - Analisis pasar",
                "• `/pairs` - Pasangan yang didukung",
                "• `/help` - Bantuan rinci",
                "",
                "**Tipe Sinyal:**",
                "• 🟢 LONG - Sinyal beli",
                "• 🔴 SHORT - Sinyal jual  ",
                "• 🟡 WAIT - Tunggu",
                "",
                "**Tips Penggunaan:**",
                "• Sinyal diperbarui setiap 5 menit",
                "• Gunakan manajemen risiko yang benar",
                "• Hanya untuk edukasi",
                "",
                "**More help:** `/help`",
            ])
        )
        keyboard = [
            [InlineKeyboardButton("🎯 Dapatkan Sinyal", callback_data="get_signal")],
            [InlineKeyboardButton("📊 Analisis", callback_data="market_analysis")],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
        ]
        await query.edit_message_text(help_message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _handle_signal_callback(self, query: CallbackQuery, symbol: str) -> None:
        await query.edit_message_text(
            f"🔄 **Membuat sinyal untuk {symbol}...**\n\nMenganalisis data pasar...",
            parse_mode='Markdown'
        )
        assert self.signal_generator is not None
        try:
            await self.usage_store.increment(symbol)
        except Exception:
            pass
        signal = await self.signal_generator.generate_signal(symbol)
        if signal:
            message = format_signal_message(symbol, cast(Dict[str, Any], signal)) + f"\n\n{get_timeframe_display()}"
            keyboard = [
                [InlineKeyboardButton("🔄 Muat Ulang", callback_data=f"refresh_signal_{symbol}")],
                [InlineKeyboardButton("📊 Analisis", callback_data=f"analyze_{symbol}")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
            ]
            parts = split_message(message)
            await query.edit_message_text(parts[0], reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            # Send any remaining chunks as new messages (guard None)
            if self.application:
                chat_id: Optional[int] = None
                try:
                    if getattr(query, 'from_user', None):
                        chat_id = query.from_user.id  # type: ignore[assignment]
                    elif getattr(query, 'message', None) and getattr(query.message, 'chat', None):
                        chat_id = query.message.chat.id  # type: ignore[assignment]
                except Exception:
                    chat_id = None
                if chat_id is not None:
                    for extra in parts[1:]:
                        await self.application.bot.send_message(chat_id=chat_id, text=extra, parse_mode='Markdown')
        else:
            await query.edit_message_text(format_error_message("Gagal membuat sinyal.", symbol), parse_mode='Markdown')

    async def _handle_analyze_callback(self, query: CallbackQuery, symbol: str) -> None:
        await query.edit_message_text(
            f"🔍 **Menganalisis {symbol}...**\n\nMengumpulkan data pasar...",
            parse_mode='Markdown'
        )
        assert self.signal_generator is not None
        try:
            await self.usage_store.increment(symbol)
        except Exception:
            pass
        analysis = await self.signal_generator.get_market_explanation(symbol)
        if analysis:
            message = format_market_analysis(symbol, analysis)
            keyboard = [
                [InlineKeyboardButton("🎯 Dapatkan Sinyal", callback_data=f"signal_{symbol}")],
                [InlineKeyboardButton("🔄 Muat Ulang", callback_data=f"analyze_{symbol}")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
            ]
            parts = split_message(message)
            await query.edit_message_text(parts[0], reply_markup=InlineKeyboardMarkup(keyboard))
            if self.application:
                chat_id: Optional[int] = None
                try:
                    if getattr(query, 'from_user', None):
                        chat_id = query.from_user.id  # type: ignore[assignment]
                    elif getattr(query, 'message', None) and getattr(query.message, 'chat', None):
                        chat_id = query.message.chat.id  # type: ignore[assignment]
                except Exception:
                    chat_id = None
                if chat_id is not None:
                    for extra in parts[1:]:
                        await self.application.bot.send_message(chat_id=chat_id, text=extra)
        else:
            await query.edit_message_text(format_error_message("Gagal menganalisis pasar.", symbol), parse_mode='Markdown')

    async def _handle_refresh_signal(self, query: CallbackQuery, symbol: str) -> None:
        await query.edit_message_text(
            f"🔄 **Refreshing signal for {symbol}...**",
            parse_mode='Markdown'
        )
        assert self.signal_generator is not None
        signal = await self.signal_generator.generate_signal(symbol, force=True)
        if signal:
            message = format_signal_message(symbol, cast(Dict[str, Any], signal)) + f"\n\n{get_timeframe_display()}"
            keyboard = [
                [InlineKeyboardButton("🔄 Muat Ulang", callback_data=f"refresh_signal_{symbol}")],
                [InlineKeyboardButton("📊 Analisis", callback_data=f"analyze_{symbol}")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
            ]
            parts = split_message(message)
            await query.edit_message_text(parts[0], reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            if self.application:
                chat_id: Optional[int] = None
                try:
                    if getattr(query, 'from_user', None):
                        chat_id = query.from_user.id  # type: ignore[assignment]
                    elif getattr(query, 'message', None) and getattr(query.message, 'chat', None):
                        chat_id = query.message.chat.id  # type: ignore[assignment]
                except Exception:
                    chat_id = None
                if chat_id is not None:
                    for extra in parts[1:]:
                        await self.application.bot.send_message(chat_id=chat_id, text=extra, parse_mode='Markdown')
        else:
            await query.edit_message_text(format_error_message("Failed to refresh signal.", symbol), parse_mode='Markdown')

    async def _handle_refresh_pairs(self, query: CallbackQuery) -> None:
        await query.edit_message_text("🔄 **Memuat daftar pasangan yang didukung...**", parse_mode='Markdown')
        assert self.signal_generator is not None
        pairs = await self.signal_generator.get_supported_pairs()
        if pairs:
            message = format_pairs_list(pairs)
            keyboard = [
                [InlineKeyboardButton("🎯 Dapatkan Sinyal", callback_data="get_signal"),
                 InlineKeyboardButton("➕ Pair Kustom", callback_data="custom_pair")],
                [InlineKeyboardButton("🔄 Muat Ulang", callback_data="refresh_pairs")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
            ]
            await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await query.edit_message_text(format_error_message("Gagal memuat daftar pasangan."), parse_mode='Markdown')

    async def _handle_custom_pair_prompt(self, query: CallbackQuery) -> None:
        user_id = query.from_user.id if query.from_user else None
        if user_id:
            # Expect a symbol next; mode 'both' => generate signal+analysis automatically
            self.awaiting_custom[int(user_id)] = 'both'
        message = (
            "\n".join([
                "🧩 **Pair Kustom**",
                "",
                "Kirim simbol trading apapun (contoh: `BTCUSDT` atau cukup `BTC`).",
                "Bot akan langsung membuat sinyal dan analisis untuk simbol tersebut.",
            ])
        )
        keyboard = [[InlineKeyboardButton("🔥 Pasangan Populer", callback_data="popular_pairs")],
                    [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]]
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
