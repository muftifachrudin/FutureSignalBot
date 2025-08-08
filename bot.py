"""
Telegram bot implementation for trading signals (python-telegram-bot v22)
"""
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from signal_generator_v2 import ImprovedSignalGenerator
from config import Config
from utils import (
    format_signal_message, format_market_analysis, format_pairs_list,
    validate_symbol, format_error_message, get_timeframe_display, truncate_text
)

logger = logging.getLogger(__name__)

class TradingSignalBot:
    """Main Telegram bot class"""

    def __init__(self):
        self.token = Config.TELEGRAM_BOT_TOKEN
        self.signal_generator = None
        self.application = None

    def run(self):
        """Run the bot using Application.run_polling (blocking)."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            self.signal_generator = loop.run_until_complete(self._enter_signal_generator())
            self.application = Application.builder().token(self.token).build()
            self._add_handlers()
            logger.info("Starting Telegram bot (run_polling)...")
            self.application.run_polling(close_loop=False)
        finally:
            if self.signal_generator:
                loop.run_until_complete(self.signal_generator.__aexit__(None, None, None))
            loop.close()

    async def _enter_signal_generator(self) -> ImprovedSignalGenerator:
        gen = ImprovedSignalGenerator()
        await gen.__aenter__()
        return gen

    async def stop(self):
        try:
            if self.application:
                await self.application.stop()
            if self.signal_generator:
                await self.signal_generator.__aexit__(None, None, None)
        except Exception as e:
            logger.warning(f"Error during bot stop: {e}")

    def _add_handlers(self):
        application = self.application
        if application is None:
            logger.warning("Application not initialized; cannot add handlers yet.")
            return
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("signal", self.signal_command))
        application.add_handler(CommandHandler("analyze", self.analyze_command))
        application.add_handler(CommandHandler("pairs", self.pairs_command))
        application.add_handler(CommandHandler("timeframes", self.timeframes_command))
        application.add_handler(CommandHandler("about", self.about_command))
        application.add_handler(CallbackQueryHandler(self.button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_symbol_message))

    # Commands
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.effective_message
        if not msg:
            return
        welcome_message = (
            "\n".join([
                "🤖 **Selamat datang di Bot Sinyal Perdagangan MEXC Futures!**",
                "",
                "Bot ini memberikan sinyal trading berbasis AI untuk futures MEXC menggunakan:",
                "• 📊 Analisis multi-timeframe (5m, 15m, 30m, 1h, 4h)",
                "• 📈 Data sentimen pasar dari Coinglass",
                "• 🤖 Analisis AI Gemini (opsional)",
                "• 💹 Data harga dari MEXC",
                "",
                "**Perintah yang tersedia:**",
                "• `/signal <SYMBOL>` - Dapatkan sinyal trading",
                "• `/analyze <SYMBOL>` - Analisis pasar",
                "• `/pairs` - Daftar pasangan yang didukung",
                "• `/timeframes` - Rentang waktu yang dianalisis",
                "• `/help` - Bantuan rinci",
                "• `/about` - Tentang bot",
                "",
                "**Contoh:**",
                "• `/signal BTCUSDT` - Sinyal BTC",
                "• `/analyze ETHUSDT` - Analisis ETH",
                "",
                "⚠️ **Disclaimer:** Sinyal hanya untuk edukasi. Lakukan riset sendiri dan kelola risiko dengan bijak.",
            ])
        )
        keyboard = [
            [InlineKeyboardButton("📊 Pasangan Populer", callback_data="popular_pairs")],
            [InlineKeyboardButton("📈 Dapatkan Sinyal", callback_data="get_signal"),
             InlineKeyboardButton("🔍 Analisis Pasar", callback_data="market_analysis")],
            [InlineKeyboardButton("ℹ️ Bantuan", callback_data="help")]
        ]
        await msg.reply_text(welcome_message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    async def about_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    async def timeframes_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    async def pairs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.effective_message
        if not msg:
            return
        processing_msg = await msg.reply_text("🔄 **Memuat daftar pasangan yang didukung...**", parse_mode='Markdown')
        assert self.signal_generator is not None
        pairs = await self.signal_generator.get_supported_pairs()
        if pairs:
            message = format_pairs_list(pairs)
            keyboard = [
                [InlineKeyboardButton("🎯 Dapatkan Sinyal", callback_data="get_signal_input")],
                [InlineKeyboardButton("🔄 Muat Ulang", callback_data="refresh_pairs")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
            ]
            await processing_msg.edit_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await processing_msg.edit_text(format_error_message("Gagal memuat daftar pasangan."), parse_mode='Markdown')

    async def signal_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        signal = await self.signal_generator.generate_signal(symbol)
        if signal:
            message = format_signal_message(symbol, signal) + f"\n\n{get_timeframe_display()}"
            keyboard = [
                [InlineKeyboardButton("🔄 Muat Ulang", callback_data=f"refresh_signal_{symbol}")],
                [InlineKeyboardButton("📊 Analisis Pasar", callback_data=f"analyze_{symbol}")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
            ]
            await processing_msg.edit_text(truncate_text(message), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await processing_msg.edit_text(format_error_message("Gagal membuat sinyal.", symbol), parse_mode='Markdown')

    async def analyze_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        analysis = await self.signal_generator.get_market_explanation(symbol)
        if analysis:
            message = format_market_analysis(symbol, analysis)
            keyboard = [
                [InlineKeyboardButton("🎯 Dapatkan Sinyal", callback_data=f"signal_{symbol}")],
                [InlineKeyboardButton("🔄 Muat Ulang Analisis", callback_data=f"analyze_{symbol}")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
            ]
            await processing_msg.edit_text(truncate_text(message), reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await processing_msg.edit_text(format_error_message("Gagal menganalisis kondisi pasar.", symbol), parse_mode='Markdown')

    async def handle_symbol_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.effective_message
        if not msg or not msg.text:
            return
        try:
            symbol = validate_symbol(msg.text)
        except ValueError:
            await msg.reply_text(
                "❌ Format simbol tidak valid. Gunakan format seperti `BTCUSDT` atau ketik `/help` untuk bantuan.",
                parse_mode='Markdown'
            )
            return
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
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            else:
                await query.edit_message_text("❌ Aksi tidak dikenal.")
        except Exception as e:
            logger.error(f"Error handling callback {data}: {e}")
            await query.edit_message_text("❌ An error occurred. Please try again.")

    # Callback helpers
    async def _render_main_menu(self, query: CallbackQuery):
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

    async def _handle_popular_pairs(self, query: CallbackQuery):
        popular_pairs = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT", "DOTUSDT"]
        message = "🔥 **Pasangan Populer**\n\nPilih pasangan untuk mendapatkan sinyal:\n\n"
        keyboard = []
        for i in range(0, len(popular_pairs), 2):
            row = []
            for j in range(2):
                if i + j < len(popular_pairs):
                    pair = popular_pairs[i + j]
                    row.append(InlineKeyboardButton(pair, callback_data=f"signal_{pair}"))
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("📋 Semua Pasangan", callback_data="refresh_pairs")])
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _handle_get_signal_prompt(self, query: CallbackQuery):
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

    async def _handle_timeframe_select(self, query: CallbackQuery, timeframe: str):
        message = (
            "\n".join([
                f"⏰ Timeframe dipilih: **{timeframe}**",
                "",
                "Pilih pasangan untuk dianalisis pada timeframe ini, atau kirim simbol manual (mis. `BTCUSDT`).",
            ])
        )
        popular_pairs = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT", "XRPUSDT"]
        keyboard = []
        row = []
        for i, p in enumerate(popular_pairs, start=1):
            row.append(InlineKeyboardButton(p, callback_data=f"tf_analyze_{timeframe}_{p}"))
            if i % 3 == 0:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")])
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    async def _handle_timeframe_analyze(self, query: CallbackQuery, timeframe: str, symbol: str):
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
                f"EMA20: {result.get('ema20'):.4f} | EMA50: {result.get('ema50'):.4f}",
                f"RSI(14): {result.get('rsi'):.2f} | ATR%: {result.get('atrp'):.2f}%",
                f"🤖 Rekomendasi: {result.get('recommendation')} | Skor: {result.get('score'):.2f}",
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

    async def _handle_market_analysis_prompt(self, query: CallbackQuery):
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

    async def _handle_help_callback(self, query: CallbackQuery):
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

    async def _handle_signal_callback(self, query: CallbackQuery, symbol: str):
        await query.edit_message_text(
            f"🔄 **Membuat sinyal untuk {symbol}...**\n\nMenganalisis data pasar...",
            parse_mode='Markdown'
        )
        assert self.signal_generator is not None
        signal = await self.signal_generator.generate_signal(symbol)
        if signal:
            message = format_signal_message(symbol, signal) + f"\n\n{get_timeframe_display()}"
            keyboard = [
                [InlineKeyboardButton("🔄 Muat Ulang", callback_data=f"refresh_signal_{symbol}")],
                [InlineKeyboardButton("📊 Analisis", callback_data=f"analyze_{symbol}")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
            ]
            await query.edit_message_text(truncate_text(message), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await query.edit_message_text(format_error_message("Gagal membuat sinyal.", symbol), parse_mode='Markdown')

    async def _handle_analyze_callback(self, query: CallbackQuery, symbol: str):
        await query.edit_message_text(
            f"🔍 **Menganalisis {symbol}...**\n\nMengumpulkan data pasar...",
            parse_mode='Markdown'
        )
        assert self.signal_generator is not None
        analysis = await self.signal_generator.get_market_explanation(symbol)
        if analysis:
            message = format_market_analysis(symbol, analysis)
            keyboard = [
                [InlineKeyboardButton("🎯 Dapatkan Sinyal", callback_data=f"signal_{symbol}")],
                [InlineKeyboardButton("🔄 Muat Ulang", callback_data=f"analyze_{symbol}")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
            ]
            await query.edit_message_text(truncate_text(message), reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text(format_error_message("Gagal menganalisis pasar.", symbol), parse_mode='Markdown')

    async def _handle_refresh_signal(self, query: CallbackQuery, symbol: str):
        await query.edit_message_text(
            f"🔄 **Refreshing signal for {symbol}...**",
            parse_mode='Markdown'
        )
        assert self.signal_generator is not None
        signal = await self.signal_generator.generate_signal(symbol, force=True)
        if signal:
            message = format_signal_message(symbol, signal) + f"\n\n{get_timeframe_display()}"
            keyboard = [
                [InlineKeyboardButton("🔄 Muat Ulang", callback_data=f"refresh_signal_{symbol}")],
                [InlineKeyboardButton("📊 Analisis", callback_data=f"analyze_{symbol}")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
            ]
            await query.edit_message_text(truncate_text(message), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await query.edit_message_text(format_error_message("Failed to refresh signal.", symbol), parse_mode='Markdown')

    async def _handle_refresh_pairs(self, query: CallbackQuery):
        await query.edit_message_text("🔄 **Memuat daftar pasangan yang didukung...**", parse_mode='Markdown')
        assert self.signal_generator is not None
        pairs = await self.signal_generator.get_supported_pairs()
        if pairs:
            message = format_pairs_list(pairs)
            keyboard = [
                [InlineKeyboardButton("🎯 Dapatkan Sinyal", callback_data="get_signal")],
                [InlineKeyboardButton("🔄 Muat Ulang", callback_data="refresh_pairs")],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="main_menu")]
            ]
            await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await query.edit_message_text(format_error_message("Gagal memuat daftar pasangan."), parse_mode='Markdown')
