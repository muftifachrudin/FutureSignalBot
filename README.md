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

## Upgrade Terbaru (Agustus 2025)

Fokus peningkatan presisi intraday & skalabilitas data mikro:

- Perintah baru `/scalp <SIMBOL>`: ringkasan scalping cepat (bias intraday, funding, OI, long/short ratio, ATR 1m, estimasi stop & TP, Volume Profile POC/HVN/LVN bila aktif).
- Micro Metrics Layer (1m candles) tersimpan dalam struktur deque per simbol: harga, high, low, volume, true range → menghitung ATR1m & Volume Profile ringan.
- Persistensi micro metrics ke disk (JSON) dengan penulisan periodik & load saat start untuk mengurangi "warm-up" kosong setelah restart.
- Background refresh loop terjadwal untuk menarik 1m klines simbol yang paling baru digunakan tanpa menunggu permintaan user (mengurangi latensi pertama).
- Volume Profile (POC, HVN, LVN, range persentase) diintegrasikan ke:
  - `/scalp` (scalping snapshot) — dikendalikan oleh `ENABLE_VOLUME_PROFILE_SCALP`.
  - Penjelasan pasar `/signal` / `/timeframes` (market explanation) — dikendalikan oleh `ENABLE_VOLUME_PROFILE_EXPLANATION`.
- Toggle konfigurasi granular untuk kinerja & keluaran (lihat bagian Konfigurasi Lanjutan).
- Test unit dasar: validasi toggle Volume Profile (`tests/test_volume_profile_toggle.py`).

### Alur Data Micro Metrics

1. Saat memanggil `/scalp` atau analisis lain, bot memuat/menyegarkan 1m klines simbol.
2. Data dimutakhirkan ke deques (dengan retensi menit = `MICRO_METRICS_RETENTION_MINUTES`).
3. ATR1m dihitung dari true range deques.
4. Volume Profile dibangun cepat dengan bucketizing range harga penutupan + volume.
5. Snapshot scalping/penjelasan pasar dirakit, lalu (opsional) micro metrics disimpan periodik ke file JSON.

### Manfaat

- Restart cepat tidak kehilangan konteks mikro (ATR1m lebih stabil sejak awal).
- Mengurangi burst call API ketika user pertama meminta `/scalp`.
- Memberi lapisan kontekstual tambahan (POC relatif ke harga sekarang, sebaran volume lokal) untuk keputusan intraday.

## Konfigurasi Lanjutan (Variabel Lingkungan Baru)

| Variabel                            | Default                   | Deskripsi                                                                        |
| ----------------------------------- | ------------------------- | -------------------------------------------------------------------------------- |
| `MICRO_METRICS_RETENTION_MINUTES`   | 720                       | Jumlah menit 1m data disimpan per simbol (kapasitas deque).                      |
| `ATR1M_PERIOD`                      | 14                        | Periode perhitungan ATR 1 menit (dalam bar).                                     |
| `VOLUME_PROFILE_BUCKETS`            | 24                        | Jumlah bucket histogram Volume Profile mikro.                                    |
| `ENABLE_VOLUME_PROFILE_SCALP`       | 1                         | Aktif/nonaktif POC/HVN/LVN di output `/scalp`. Set 0 untuk menonaktifkan.        |
| `ENABLE_VOLUME_PROFILE_EXPLANATION` | 1                         | Aktif/nonaktif micro metrics (ATR1m/POC) dalam penjelasan pasar / analisis umum. |
| `SCALP_MAX_MESSAGE_LEN`             | 900                       | Panjang maksimum pesan `/scalp` (pemotongan aman).                               |
| `MICRO_METRICS_PERSIST_PATH`        | `data/micro_metrics.json` | Lokasi file JSON persistensi micro metrics. Pastikan direktori writeable.        |
| `MICRO_METRICS_SAVE_INTERVAL_SEC`   | 60                        | Interval minimum antar penulisan file persistensi (detik).                       |
| `MICRO_BACKGROUND_REFRESH_SEC`      | 60                        | Interval loop refresh background 1m klines. Set lebih besar untuk hemat API.     |
| `MICRO_BACKGROUND_SYMBOL_LIMIT`     | 12                        | Jumlah simbol teratas (berdasar akses terakhir) yang di-refresh di background.   |

Catatan: Set nilai dengan menambahkannya ke `.env` atau `/etc/futuresignalbot.env` lalu restart service.

## Perintah Tambahan (Baru)

- `/scalp <SIMBOL>` – Snapshot scalping (bias intraday, ATR1m, POC, risk sizing heuristik). Gunakan sebagai referensi cepat, bukan saran finansial.

## Struktur Data Persistensi

File JSON `MICRO_METRICS_PERSIST_PATH` menyimpan per simbol:

```jsonc
{
  "BTCUSDT": {
    "prices": [...],
    "highs": [...],
    "lows": [...],
    "vols": [...],
    "times": [...],
    "trs": [...]
  }
}
```

File ditulis atomik (tulis → rename) untuk meminimalkan korupsi.

## Kinerja & Tuning

- Kurangi `MICRO_METRICS_RETENTION_MINUTES` jika memori terbatas.
- Naikkan `MICRO_BACKGROUND_REFRESH_SEC` (misal 120–180) bila rate limit ketat.
- Nonaktifkan profil mikro di analisis umum (`ENABLE_VOLUME_PROFILE_EXPLANATION=0`) bila ingin output lebih ringkas.
- Set `ENABLE_VOLUME_PROFILE_SCALP=0` jika fokus hanya ATR1m.

## Pengujian (Tests)

Test unit sederhana telah ditambahkan:

```
pytest -k volume_profile_toggle -q
```

Memverifikasi bahwa ketika `ENABLE_VOLUME_PROFILE_EXPLANATION` dimatikan, teks penjelasan pasar tidak menyertakan label POC / ATR1m.

## Troubleshooting Tambahan (Micro Layer)

| Gejala                        | Penyebab Umum                                 | Solusi                                                  |
| ----------------------------- | --------------------------------------------- | ------------------------------------------------------- |
| ATR1m selalu 0                | Data 1m belum cukup bar                       | Jalankan `/scalp` 1–2 menit atau periksa koneksi klines |
| POC/HVN/LVN kosong            | Volume Profile dinonaktifkan atau data kurang | Pastikan flag enable & set retention > 30               |
| File persistensi tidak muncul | Direktori `data/` belum ada / permission      | `mkdir -p data` & cek permission user service           |
| Output /scalp terpotong       | Melebihi `SCALP_MAX_MESSAGE_LEN`              | Naikkan nilai atau kurangi detail bucket                |

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
  \n+## Deploy di Linux VM (systemd)
  Contoh: Ubuntu 22.04, jalankan 24/7 dengan systemd.

### 1. User & Direktori

```bash
sudo useradd -r -m -d /opt/futuresignalbot -s /usr/sbin/nologin fsbot
sudo chown fsbot:fsbot /opt/futuresignalbot
```

### 2. Clone & Install

```bash
sudo -u fsbot bash -c 'cd /opt/futuresignalbot && git clone https://github.com/youruser/FutureSignalBot .'
sudo -u fsbot bash -c 'cd /opt/futuresignalbot && python3.11 -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/pip install -r requirements.txt'
```

### 3. Environment File

`/etc/futuresignalbot.env` (chmod 640 root:fsbot):

```
TELEGRAM_BOT_TOKEN=xxxx
COINGLASS_API_KEY=xxxx
MEXC_API_KEY=xxxx
MEXC_SECRET_KEY=xxxx
GEMINI_API_KEY=xxxx
PYTHONUNBUFFERED=1
```

```bash
sudo bash -c 'chmod 640 /etc/futuresignalbot.env && chown root:fsbot /etc/futuresignalbot.env'
```

### 4. systemd Unit

Salin `systemd/futuresignalbot.service` ke `/etc/systemd/system/`:

```bash
sudo cp systemd/futuresignalbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now futuresignalbot
```

### 5. Verifikasi & Log

```bash
systemctl status futuresignalbot --no-pager
journalctl -u futuresignalbot -f
```

Log file juga ada di `logs/bot.log`.

### 6. Update Versi

```bash
sudo systemctl stop futuresignalbot
sudo -u fsbot bash -c 'cd /opt/futuresignalbot && git pull && .venv/bin/pip install -r requirements.txt'
sudo systemctl start futuresignalbot
```

### 7. Mode Docker (Alternatif)

```bash
docker build -t futuresignalbot:latest .
docker run -d --name futuresignalbot --restart=unless-stopped --env-file /etc/futuresignalbot.env futuresignalbot:latest
```

Image sudah mengabaikan `.env` (lihat `.dockerignore`).

### Catatan Keamanan

- User non-login (`fsbot`) membatasi akses.
- `Restart=on-failure` otomatis restart saat crash.
- Gunakan firewall & rotasi log bila beban tinggi.

## Keamanan

- Jangan commit `.env`. Gunakan secrets di CI/CD.
- Batasi distribusi token API dan rotasi secara berkala.

## Lisensi

Gunakan sesuai kebutuhan Anda. Tambahkan berkas LICENSE jika ingin membagikan lisensi spesifik (mis. MIT).

---

## Operasional & Keamanan Lanjutan

### Rotasi Kredensial

Jika token/API key terekspos:

1. Revoke & generate baru (Telegram BotFather, MEXC, Coinglass, Gemini).
2. Update `/etc/futuresignalbot.env` dan sinkronkan ke `/opt/futuresignalbot/.env`.
3. `sudo systemctl restart futuresignalbot.service`
4. Verifikasi: `curl -s https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe | grep '"ok":true'`

### Rewrite Git History (Hapus Jejak Secrets)

```
pip install git-filter-repo
git rm --cached .env || true
cat > replace.txt <<'R'
OLD_TELEGRAM_TOKEN==REMOVED_SECRET
OLD_MEXC_KEY==REMOVED_SECRET
OLD_MEXC_SECRET==REMOVED_SECRET
OLD_COINGLASS_KEY==REMOVED_SECRET
OLD_GEMINI_KEY==REMOVED_SECRET
R
git filter-repo --path .env --invert-paths
git filter-repo --replace-text replace.txt
git push --force origin main
```

Regenerasi token sebelum force push.

### systemd Watchdog (Opsional)

Tambahkan ke unit override:

```
sudo systemctl edit futuresignalbot.service
```

Isi:

```
[Service]
WatchdogSec=60
StartLimitIntervalSec=300
StartLimitBurst=5
```

Reload: `sudo systemctl daemon-reload && sudo systemctl restart futuresignalbot.service`

### Health Check Timer (Opsional)

```
sudo tee /usr/local/bin/fsbot-health.sh >/dev/null <<'EOF'
#!/usr/bin/env bash
set -e
[ -f /opt/futuresignalbot/.env ] && source /opt/futuresignalbot/.env
curl -s --max-time 8 https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe | grep -q '"ok":true' || systemctl restart futuresignalbot.service
EOF
sudo chmod 700 /usr/local/bin/fsbot-health.sh
sudo tee /etc/systemd/system/fsbot-health.service >/dev/null <<'EOF'
[Unit]
Description=Health check FutureSignalBot
[Service]
Type=oneshot
ExecStart=/usr/bin/bash /usr/local/bin/fsbot-health.sh
EOF
sudo tee /etc/systemd/system/fsbot-health.timer >/dev/null <<'EOF'
[Unit]
Description=Run health check every 5 minutes
[Timer]
OnBootSec=2m
OnUnitActiveSec=5m
Unit=fsbot-health.service
[Install]
WantedBy=timers.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now fsbot-health.timer
```

### Firewall & Hardening

- Batasi port (SSH 22; 80/443 jika perlu webhook).
- UFW / NSG aturan minimal; pertimbangkan Fail2ban.
- Permissions secrets 640 root:fsbot atau 600 root:root.

### Logging

- RotatingFileHandler aktif (2MB x3). Tambah logrotate bila volume tinggi.

### Pembersihan Debug

Hapus `ExecStartPre` sementara dari unit setelah troubleshooting.

### Roadmap Teknis

- Mode webhook + proxy TLS
- Penyimpanan historis sinyal (evaluasi performa)
- Key Vault / Secrets Manager integrasi
- Observability (metrics/tracing) Application Insights / Prometheus
