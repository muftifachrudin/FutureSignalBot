# FutureSignalBot

Bot Telegram sinyal MEXC Futures dengan data multi-sumber (Coinglass v4) dan analisis timeframe, UI Bahasa Indonesia, logging, dan caching. Opsional: komentar AI (Gemini).

## Fitur Utama

- Sinyal Futures berbasis data pasar real-time.
- Integrasi Coinglass v4 (open-api-v4.coinglass.com) dengan metrik:
  - Funding rate, Open Interest, perubahan OI 24 jam.
  - Long/Short Ratio (taker buy/sell volume) dengan fallback multi-range.
  - Likuidasi (liquidation/history) dan Fear & Greed Index (history) untuk sentimen.
- Analisis timeframe (EMA/RSI/ATR) dan rekomendasi ringkas.
- Antarmuka Telegram berbahasa Indonesia (Menu Utama, tombol klik /timeframes, dll).
- Optimasi performa: TTL caching untuk endpoint berfrekuensi rendah (≥ 4 jam), cooldown per-simbol, timeouts & retries.
- Logging berkas bergulir di `logs/bot.log` dan penanganan error yang rapi.
- Endpoint MEXC sudah dimigrasikan ke domain `.fm` agar tidak terblokir.

## Persyaratan

- Python 3.11
- Akun Bot Telegram (token dari BotFather)
- (Opsional) API key Coinglass v4 untuk metrik lanjutan
- (Opsional) API key Gemini untuk komentar AI

## Instalasi Cepat (Windows PowerShell)

1. Clone repo ini dan masuk ke folder proyek.
2. Buat/aktifkan virtual env (VS Code task sudah disiapkan), lalu instal dependensi:
   - Menggunakan `requirements.txt` (disarankan untuk kesesuaian): `pip install -r requirements.txt`
3. Salin `.env.example` menjadi `.env`, isi variabel berikut:
   - TELEGRAM_BOT_TOKEN (wajib)
   - COINGLASS_API_KEY (opsional, dibutuhkan untuk metrik Coinglass)
   - MEXC_API_KEY, MEXC_SECRET_KEY (opsional)
   - GEMINI_API_KEY (opsional)

Catatan:

- Base URL Coinglass: `https://open-api-v4.coinglass.com` menggunakan header `CG-API-KEY` dan endpoint berawalan `/api`.
- Beberapa endpoint histori Coinglass mensyaratkan minimal interval 4 jam; bot sudah menormalkan otomatis dan melakukan TTL caching.

## Menjalankan Bot

Pilihan A — via VS Code Task:

- Task: "Run bot (venv)" atau "Start bot (venv)"

Pilihan B — via PowerShell:

- Dari root proyek: `& .\.venv\Scripts\python.exe .\main.py`

Bot menggunakan python-telegram-bot v22 dengan `run_polling` (blocking). Hentikan dengan Ctrl+C.

## Uji Cepat (tanpa Telegram)

Jalankan skrip uji cepat untuk melihat metrik Coinglass dan ringkasan sinyal:

- `& .\.venv\Scripts\python.exe .\scripts\quick_signal_test.py BTCUSDT`

Output akan menampilkan funding, OI, perubahan OI 24 jam, LSR (jika tersedia), likuidasi, dan skor sentimen.

## Perintah Telegram Utama

- /start — Tampilkan Menu Utama (Bahasa Indonesia)
- /menu — Navigasi cepat fitur bot
- /signal <SIMBOL> — Analisis dan sinyal singkat (contoh: /signal BTCUSDT)
- /timeframes <SIMBOL> — Analisis EMA/RSI/ATR lintas timeframe dengan tombol klik
- /help — Bantuan ringkas dan tip penggunaan

Tips:

- SIMBOL mengikuti format MEXC: contoh BTCUSDT, ETHUSDT, SOLUSDT.
- Jika LSR tidak tersedia untuk range tertentu, bot mencoba fallback ke range lain.

## Logging & Caching

- Log tersimpan di `logs/bot.log` dengan rotasi otomatis.
- Endpoint dengan interval ≥ 4 jam menggunakan TTL cache untuk mengurangi rate limit.
- Terdapat cooldown per-simbol untuk mencegah spam permintaan.

## Troubleshooting

- Bot tidak mau jalan / token salah: pastikan `TELEGRAM_BOT_TOKEN` benar di `.env`.
- Metrik Coinglass kosong: pastikan `COINGLASS_API_KEY` aktif dan kuota tersedia; beberapa koin/range bisa tidak tersedia — coba simbol/range lain.
- Error 409 dari Telegram: jalankan hanya satu instance bot (Windows lock sudah diaktifkan di `main.py`).
- Koneksi lambat/timeout: jaringan atau rate limit; tunggu sebentar, bot sudah ada retries + caching.

## Deploy ke Azure (opsional)

Skema umum: Docker image → ACR → Azure Container Apps (ACA) dengan Log Analytics.

Siapkan di GitHub (Actions):

- Secrets: AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID (OIDC), TELEGRAM_BOT_TOKEN, COINGLASS_API_KEY (opsional), MEXC_API_KEY/MEXC_SECRET_KEY (opsional), GEMINI_API_KEY (opsional).
- Variables: ACR_LOGIN_SERVER, AZURE_RESOURCE_GROUP, ACA_ENV_NAME, ACA_APP_NAME.

Alur: push ke `main` → build Docker → push ke ACR → deploy ke ACA. Aplikasi membaca konfigurasi dari environment variables (tanpa `.env` di dalam image).

Catatan:

- Contoh workflow GitHub Actions dan bicep/terraform belum disertakan. Tambahkan sesuai kebutuhan Anda, atau gunakan Azure Developer CLI (azd) bila diinginkan.

## Struktur Proyek (ringkas)

- `main.py` — Entry point, logging & single-instance lock (Windows)
- `bot/telegram_bot.py` — Handler perintah & UI Bahasa Indonesia
- `signal_generator_v2.py` — Inti logika sinyal + analisis timeframe
- `services/` — Klien API (Coinglass v4, MEXC .fm)
- `scripts/quick_signal_test.py` — Uji metrik cepat untuk simbol
- `logs/` — Output log

## Keamanan

- Jangan commit `.env`. Gunakan secrets di CI/CD.
- Batasi distribusi token API dan rotasi secara berkala.

## Lisensi

Gunakan sesuai kebutuhan Anda. Tambahkan berkas LICENSE jika ingin membagikan lisensi spesifik (mis. MIT).
