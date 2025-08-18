"""Improved signal generation logic using working APIs only (extended with micro metrics persistence & background refresh)."""
import time
import logging
import json
import asyncio
from pathlib import Path
from collections import deque, defaultdict
from typing import Dict, List, Optional, Any, TypedDict, Type, Protocol, runtime_checkable, cast, Mapping, Tuple, Deque
from types import TracebackType
from mexc_client import MEXCClient
from coinglass_client import CoinglassClient
from gemini_analyzer import GeminiAnalyzer
from config import Config
import math
import statistics
logger = logging.getLogger(__name__)

class PairsCacheData(TypedDict):
    ts: float
    data: List[str]

class PriceAnalysis(TypedDict):
    trend: str
    strength: float
    volatility: str
    momentum: str
    price_change_percent: float
    daily_range_percent: float
    volume: float

class MarketSentiment(TypedDict):
    funding_rate: float
    open_interest_trend: str
    exchange_distribution: Dict[str, Any]
    sentiment_score: float
    oi_change_24h: float
    long_short_ratio: float

@runtime_checkable
class AsyncContextManagerLike(Protocol):
    async def __aenter__(self) -> Any: ...
    async def __aexit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]) -> None: ...
class PairsCache:
    def __init__(self):
            self.mexc_client: Optional[AsyncContextManagerLike] = None
            self.coinglass_client: Optional[AsyncContextManagerLike] = None
            self.gemini_analyzer = GeminiAnalyzer()
            # caches and rate-limit tracking
            self.last_request_time: Dict[str, float] = {}
            self.signal_cache: Dict[str, Dict[str, Any]] = {}
            self._pairs_cache: PairsCacheData = {"ts": 0.0, "data": []}
            # micro metrics store (symbol -> deques)
            self._micro_prices: Dict[str, Deque[float]] = {}
            self._micro_highs: Dict[str, Deque[float]] = {}
            self._micro_lows: Dict[str, Deque[float]] = {}
            self._micro_volumes: Dict[str, Deque[float]] = {}
            self._micro_times: Dict[str, Deque[float]] = {}
            self._micro_tr: Dict[str, Deque[float]] = {}  # true ranges for 1m ATR
            # persistence & background loop
            self._last_persist_ts: float = 0.0
            self._bg_task = None  # background asyncio task

    # -------------- Micro Metrics Helpers --------------
    def _init_micro_store(self, symbol: str):
        maxlen = max(10, int(Config.MICRO_METRICS_RETENTION_MINUTES))
        if symbol not in self._micro_prices:
            self._micro_prices[symbol] = deque(maxlen=maxlen)
            self._micro_highs[symbol] = deque(maxlen=maxlen)
            self._micro_lows[symbol] = deque(maxlen=maxlen)
            self._micro_volumes[symbol] = deque(maxlen=maxlen)
            self._micro_times[symbol] = deque(maxlen=maxlen)
            self._micro_tr[symbol] = deque(maxlen=maxlen)

    def _update_micro_metrics_from_1m(self, symbol: str, klines: List[List[Any]]):
        if not klines:
            return
        self._init_micro_store(symbol)
        prices = self._micro_prices[symbol]
        highs = self._micro_highs[symbol]
        lows = self._micro_lows[symbol]
        vols = self._micro_volumes[symbol]
        tsq = self._micro_times[symbol]
        trq = self._micro_tr[symbol]
        # ensure chronological
        klines_sorted = sorted(klines, key=lambda k: k[0])[-Config.MICRO_METRICS_RETENTION_MINUTES:]
        prev_close = prices[-1] if prices else None
        existing_ts = set(tsq)
        for k in klines_sorted:
            try:
                t = float(k[0])
                if t in existing_ts:
                    continue
                high = float(k[2]); low = float(k[3]); close = float(k[4]); vol = float(k[5]) if len(k) >5 else 0.0
                prices.append(close)
                highs.append(high)
                lows.append(low)
                vols.append(vol)
                tsq.append(t)
                if prev_close is None:
                    prev_close = close
                tr = max(high-low, abs(high-prev_close), abs(low-prev_close))
                trq.append(tr)
                prev_close = close
            except Exception:
                continue

    def _compute_atr1m(self, symbol: str) -> float:
        trq = self._micro_tr.get(symbol)
        prices = self._micro_prices.get(symbol)
        if not trq or not prices:
            return 0.0
        period = max(2, int(Config.ATR1M_PERIOD))
        if len(trq) < period:
            return 0.0
        atr = sum(list(trq)[-period:]) / period
        last_price = prices[-1] if prices else 1.0
        if last_price <= 0:
            return 0.0
        return (atr / last_price) * 100.0

    def _compute_volume_profile(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not Config.ENABLE_VOLUME_PROFILE_SCALP:
            return None
        prices = self._micro_prices.get(symbol)
        vols = self._micro_volumes.get(symbol)
        highs = self._micro_highs.get(symbol)
        lows = self._micro_lows.get(symbol)
        if not prices or not vols or len(prices) < 10 or not highs or not lows:
            return None
        try:
            pmin = min(lows)
            pmax = max(highs)
            if pmax <= pmin:
                return None
            buckets = max(6, min(200, int(Config.VOLUME_PROFILE_BUCKETS)))
            step = (pmax - pmin) / buckets
            hist: Dict[int, float] = defaultdict(float)
            # approximate: assign each close's volume to bucket
            for price, vol in zip(prices, vols):
                idx = int((price - pmin) / step)
                if idx >= buckets:
                    idx = buckets -1
                hist[idx] += vol
            # find POC and high/low volume nodes
            if not hist:
                return None
            poc_idx = max(hist.items(), key=lambda x: x[1])[0]
            poc_price = pmin + poc_idx * step + step/2
            # compute top 3 buckets
            sorted_hist = sorted(hist.items(), key=lambda x: x[1], reverse=True)
            hvn_prices = [pmin + idx*step + step/2 for idx,_ in sorted_hist[:3]]
            lvn_prices = [pmin + idx*step + step/2 for idx,_ in sorted(hist.items(), key=lambda x: x[1])[:2]]
            return {
                'poc': poc_price,
                'hvn': hvn_prices,
                'lvn': lvn_prices,
                'range_pct': ((pmax - pmin)/prices[-1])*100 if prices[-1]>0 else 0
            }
        except Exception:
            return None

    async def get_scalp_snapshot(self, symbol: str) -> Optional[str]:
        """
        Improved: Only signal long/short if price is at strongest 1H/4H support/resistance.
        - If at strongest resistance: signal short, TP to nearest/farthest support, SL above resistance/volatility.
        - If at strongest support: signal long, TP to nearest/farthest resistance, SL below support/volatility.
        - Else: signal wait.
        Combines liquidity heatmap, funding, OI for entry/TP/SL logic.
        """
        # --- 1. Update micro metrics ---
        try:
            if self.mexc_client:
                kl = await cast(Any, self.mexc_client).get_klines(symbol, '1m', limit=Config.ATR1M_PERIOD + 20)
            else:
                kl = []
        except Exception:
            kl = []
        self._update_micro_metrics_from_1m(symbol, cast(List[List[Any]], kl or []))

        # --- 2. Gather all market data ---
        atr1m: float = self._compute_atr1m(symbol)
        vol_prof: Optional[Dict[str, Any]] = self._compute_volume_profile(symbol)
        data = await self._get_reliable_market_data(symbol)
        ticker = cast(Dict[str, Any], data.get('mexc_ticker') or {})
        price = ticker.get('lastPrice')
        try:
            p = float(price) if price is not None else None
        except Exception:
            p = None
        cg_summary: Dict[str, Any] = cast(Dict[str, Any], data.get('coinglass_summary') or {})
        funding = float(cg_summary.get('funding_rate') or 0)
        oi_chg = float(cg_summary.get('oi_change_24h') or 0)
        lsr = cg_summary.get('long_short_ratio')
        # Try fetch very short-term taker L/S ratio as extra context (5m or 15m)
        short_lsr: Optional[float] = None
        try:
            if self.coinglass_client:
                client = cast(Any, self.coinglass_client)
                for rng in ('5m', '15m', '30m'):
                    hist = await client.get_long_short_ratio(symbol, range=rng)
                    val = self._extract_long_short_ratio(hist)
                    if val is not None:
                        short_lsr = val
                        break
        except Exception:
            short_lsr = None

    # --- 3. Find strongest S/R on 1H/4H ---
        strongest_res: Optional[float] = None
        strongest_sup: Optional[float] = None
        tf_highs: List[float] = []
        tf_lows: List[float] = []
        for tf, win in [('1h', 24), ('4h', 12)]:
            if not self.mexc_client:
                kl_tf_any: Any = []
            else:
                try:
                    kl_tf_any = await cast(Any, self.mexc_client).get_klines(symbol, tf, limit=max(win * 2, 60))
                except Exception:
                    kl_tf_any = []
            # Ensure shapes and types
            kl_tf_list: List[List[Any]] = cast(List[List[Any]], kl_tf_any or [])
            highs_tf_local: List[float] = [float(k[2]) for k in kl_tf_list if len(k) > 3]
            lows_tf_local: List[float] = [float(k[3]) for k in kl_tf_list if len(k) > 3]
            if highs_tf_local:
                tf_highs.extend(highs_tf_local[-win:])
            if lows_tf_local:
                tf_lows.extend(lows_tf_local[-win:])
        if tf_highs:
            strongest_res = max(tf_highs)
        if tf_lows:
            strongest_sup = min(tf_lows)

        # --- 4. Build S/R price ranges and whether price ever touched them ---
        # Range width based on micro ATR and a minimum pct
        sr_base_pct: float = 0.0015  # 0.15%
        sr_range_pct: float = max(sr_base_pct, (atr1m / 100.0) * 0.6)
        support_range: Optional[Tuple[float, float]] = None
        resistance_range: Optional[Tuple[float, float]] = None
        if strongest_sup is not None and isinstance(p, (int, float)) and p:
            half = max(1e-12, float(p) * sr_range_pct)
            support_range = (max(0.0, strongest_sup - half), strongest_sup + half)
        if strongest_res is not None and isinstance(p, (int, float)) and p:
            half = max(1e-12, float(p) * sr_range_pct)
            resistance_range = (max(0.0, strongest_res - half), strongest_res + half)

        # Check if price ever touched ranges recently (using 1m micro highs/lows)
        def _touched(rng: Optional[Tuple[float, float]]) -> bool:
            if not rng:
                return False
            lo, hi = rng
            highs = self._micro_highs.get(symbol) or deque()
            lows = self._micro_lows.get(symbol) or deque()
            try:
                for h, l in zip(highs, lows):
                    if l <= hi and h >= lo:
                        return True
            except Exception:
                return False
            return False

        touched_sup = _touched(support_range)
        touched_res = _touched(resistance_range)

        # Direction: short-term using last two closes
        last_close = None
        prev_close = None
        try:
            closes = self._micro_prices.get(symbol) or deque()
            if len(closes) >= 2:
                last_close = float(closes[-1])
                prev_close = float(closes[-2])
        except Exception:
            last_close = None
            prev_close = None
        direction_up = (last_close is not None and prev_close is not None and last_close > prev_close)
        direction_down = (last_close is not None and prev_close is not None and last_close < prev_close)

        # --- 5. Combine with liquidity heatmap, funding, OI for entry logic ---
        # (For now, use funding, OI, and short-term L/S as proxy for liquidity heatmap)
        bias: str = 'WAIT'
        reason: str = ""
        entry: Optional[float] = None
        tp1: Optional[float] = None
        tp2: Optional[float] = None
        sl: Optional[float] = None

        # Range-touch logic:
        # - If price has touched resistance range and now moving down -> SHORT
        # - If price has touched support range and now moving up -> LONG
        # - Else WAIT
        if touched_res and direction_down and strongest_res is not None and strongest_sup is not None:
            bias = 'SHORT'
            reason = "Harga menyentuh area resisten dan berbalik turun."
            entry = float(p) if isinstance(p, (int, float)) and p else strongest_res
            rng = max(0.0, strongest_res - strongest_sup)
            tp1 = strongest_res - (rng * 0.5) if rng > 0 else strongest_sup
            tp2 = strongest_sup
            # SL di atas batas atas range resisten + buffer ATR
            hi = resistance_range[1] if resistance_range else strongest_res
            sl = hi * (1 + max(0.002, atr1m / 100))
        elif touched_sup and direction_up and strongest_res is not None and strongest_sup is not None:
            bias = 'LONG'
            reason = "Harga menyentuh area support dan berbalik naik."
            entry = float(p) if isinstance(p, (int, float)) and p else strongest_sup
            rng = max(0.0, strongest_res - strongest_sup)
            tp1 = strongest_sup + (rng * 0.5) if rng > 0 else strongest_res
            tp2 = strongest_res
            lo = support_range[0] if support_range else strongest_sup
            sl = lo * (1 - max(0.002, atr1m / 100))
        else:
            bias = 'WAIT'
            if not (touched_sup or touched_res):
                reason = "Harga belum pernah menyentuh area support/resisten terbaru."
            else:
                reason = "Menunggu konfirmasi arah setelah menyentuh area."

        # --- 6. Format output ---
        lines: List[str] = []
        lines.append(f"⚡ *Scalping {symbol}*")
        lines.append(f"Sinyal: {bias}")
        if entry is not None:
            lines.append(f"Harga Entri: {entry:.2f}")
        elif isinstance(p, (int, float)) and p:
            lines.append(f"Harga Entri: {p:.2f}")
        elif price:
            # fallback to raw price string if formatting failed
            lines.append(f"Harga Entri: {price}")
        if bias in ('LONG', 'SHORT') and sl is not None:
            lines.append(f"SL: {sl:.2f}")
        if bias in ('LONG', 'SHORT') and tp1 is not None and tp2 is not None:
            lines.append(f"TP1: {tp1:.2f} | TP2: {tp2:.2f}")
        if resistance_range and strongest_res is not None:
            lines.append(f"Area Resisten (1H/4H): [{resistance_range[0]:.2f} - {resistance_range[1]:.2f}] (pusat {strongest_res:.2f})")
        if support_range and strongest_sup is not None:
            lines.append(f"Area Support (1H/4H): [{support_range[0]:.2f} - {support_range[1]:.2f}] (pusat {strongest_sup:.2f})")
        lines.append(f"Funding: {funding:.4f} | OI 24j: {oi_chg:+.2f}%")
        if lsr is not None:
            try:
                lines.append(f"Long/Short: {float(lsr):.2f}")
            except Exception:
                pass
        if short_lsr is not None:
            lines.append(f"LS (5-15m): {short_lsr:.2f}")
        lines.append(f"ATR 1m({Config.ATR1M_PERIOD}): {atr1m:.2f}%")
        # Lightly surface POC from volume profile to add context
        try:
            if vol_prof and isinstance(vol_prof.get('poc'), (int, float)):
                lines.append(f"POC (1m VP): {float(vol_prof['poc']):.2f}")
        except Exception:
            pass
        lines.append(reason)
        lines.append("Catatan: Sinyal muncul jika harga memasuki area S/R dan berbalik arah. TP/SL berasal dari area S/R & volatilitas. Funding/OI ditampilkan sebagai konteks.")
        snapshot = "\n".join(lines)
        if len(snapshot) > Config.SCALP_MAX_MESSAGE_LEN:
            snapshot = snapshot[: Config.SCALP_MAX_MESSAGE_LEN]
        return snapshot

    # -------------- Persistence & Background Refresh --------------
    def _load_micro_metrics(self) -> None:
        path = Path(Config.MICRO_METRICS_PERSIST_PATH)
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            retention = max(10, int(Config.MICRO_METRICS_RETENTION_MINUTES))
            for sym, payload_any in data.items():
                if not isinstance(payload_any, dict):
                    continue
                payload = cast(Dict[str, Any], payload_any)
                try:
                    self._micro_prices[sym] = deque(payload.get('prices', [])[-retention:], maxlen=retention)
                    self._micro_highs[sym] = deque(payload.get('highs', [])[-retention:], maxlen=retention)
                    self._micro_lows[sym] = deque(payload.get('lows', [])[-retention:], maxlen=retention)
                    self._micro_volumes[sym] = deque(payload.get('vols', [])[-retention:], maxlen=retention)
                    self._micro_times[sym] = deque(payload.get('times', [])[-retention:], maxlen=retention)
                    self._micro_tr[sym] = deque(payload.get('trs', [])[-retention:], maxlen=retention)
                except Exception:
                    continue
            logger.info("Micro metrics loaded from persistence store")
        except Exception as e:
            logger.warning(f"Failed loading micro metrics: {e}")

    def _save_micro_metrics(self, force: bool = False) -> None:
        now = time.time()
        if not force and (now - self._last_persist_ts) < Config.MICRO_METRICS_SAVE_INTERVAL_SEC:
            return
        path = Path(Config.MICRO_METRICS_PERSIST_PATH)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            blob: Dict[str, Any] = {}
            for sym in self._micro_prices:
                blob[sym] = {
                    'prices': list(self._micro_prices[sym]),
                    'highs': list(self._micro_highs[sym]),
                    'lows': list(self._micro_lows[sym]),
                    'vols': list(self._micro_volumes[sym]),
                    'times': list(self._micro_times[sym]),
                    'trs': list(self._micro_tr[sym]),
                }
            tmp = path.with_suffix('.tmp')
            tmp.write_text(json.dumps(blob), encoding='utf-8')
            tmp.replace(path)
            self._last_persist_ts = now
        except Exception as e:
            logger.warning(f"Failed saving micro metrics: {e}")

    async def _background_refresh_loop(self):
        interval = max(15, int(Config.MICRO_BACKGROUND_REFRESH_SEC))
        while True:
            try:
                # choose most recently requested symbols
                ordered = sorted(self.last_request_time.items(), key=lambda x: x[1], reverse=True)
                symbols = [s for s, _ in ordered[:Config.MICRO_BACKGROUND_SYMBOL_LIMIT]]
                for sym in symbols:
                    try:
                        if self.mexc_client:
                            kl = await cast(Any, self.mexc_client).get_klines(sym, '1m', limit=Config.ATR1M_PERIOD + 5)
                        else:
                            kl = []
                        self._update_micro_metrics_from_1m(sym, cast(List[List[Any]], kl or []))
                    except Exception:
                        continue
                self._save_micro_metrics()
            except asyncio.CancelledError:
                break
            except Exception:
                pass
            await asyncio.sleep(interval)

    # (context manager methods defined later in file)

    # --- Helper extractors (placed before usage to satisfy type analyzers) ---
    def _extract_funding_from_response(self, data: Any) -> Tuple[float, List[float]]:
        """Extract funding rate for MEXC or median across exchanges. Returns (mexc_or_0, samples)."""
        mexc_rate = 0.0
        samples: List[float] = []
        try:
            if isinstance(data, dict):
                # Possible formats: { 'MEXC': rate, ... } or { 'list': [ ... ] }
                items: List[Dict[str, Any]] = []
                if 'list' in data and isinstance(data['list'], list):
                    raw_list = cast(List[Any], data['list'])
                    items = [cast(Dict[str, Any], it) for it in raw_list if isinstance(it, dict)]
                else:
                    items = []
                    for k, v in cast(Mapping[str, Any], data).items():
                        if isinstance(v, (int, float, str)):
                            items.append({'exchangeName': str(k), 'fundingRate': v})
                for it in items:
                    ex = str(it.get('exchangeName') or it.get('exchange') or '').upper()
                    try:
                        fr = float(it.get('fundingRate') or 0.0)
                    except Exception:
                        fr = 0.0
                    samples.append(fr)
                    if ex == 'MEXC':
                        mexc_rate = fr
            elif isinstance(data, list):
                for it_any in cast(List[Any], data):
                    if not isinstance(it_any, dict):
                        continue
                    it = cast(Dict[str, Any], it_any)
                    ex = str(it.get('exchangeName') or it.get('exchange') or '').upper()
                    try:
                        fr = float(it.get('fundingRate') or 0.0)
                    except Exception:
                        fr = 0.0
                    samples.append(fr)
                    if ex == 'MEXC':
                        mexc_rate = fr
        except Exception:
            pass
        return mexc_rate, samples

    def _compute_oi_change_24h(self, history: Any) -> Tuple[float, float]:
        """Compute last open interest and 24h percent change from 4h history."""
        try:
            series: List[Dict[str, Any]] = []
            if isinstance(history, list):
                for it_any in cast(List[Any], history):
                    if isinstance(it_any, dict):
                        series.append(cast(Dict[str, Any], it_any))
            if not series:
                return 0.0, 0.0
            def get_val(d: Dict[str, Any]) -> float:
                for k in ('openInterest', 'oi', 'value', 'open_interest'):
                    if k in d:
                        try:
                            return float(d[k])
                        except Exception:
                            continue
                return 0.0
            vals = [get_val(d) for d in series if get_val(d) > 0]
            if not vals:
                return 0.0, 0.0
            last = vals[-1]
            # 24h back at 4h interval ≈ 6 steps
            prev = vals[-7] if len(vals) >= 7 else vals[0]
            if prev <= 0:
                return last, 0.0
            change_pct = ((last - prev) / prev) * 100.0
            return last, change_pct
        except Exception:
            return 0.0, 0.0

    def _extract_long_short_ratio(self, history: Any) -> Optional[float]:
        """Extract long/short ratio in [0,1] from various payload shapes.
        Supports:
        - [{ longShortRatio }]
        - [{ longRate, shortRate }]
        - taker-buy-sell-volume/exchange-list: list of items with buy/sell volumes
          keys like buyVol/sellVol/buyVolUsd/sellVolUsd. Prefer MEXC row; otherwise aggregate.
        """
        try:
            # If dict with data list, unwrap safely to a local variable
            items_any: Any = history
            if isinstance(history, dict):
                d: Dict[str, Any] = cast(Dict[str, Any], history)
                data_field: Any = d.get('data')
                if isinstance(data_field, list):
                    items_any = cast(List[Any], data_field)

            if not isinstance(items_any, list) or not items_any:
                return None

            # If items contain direct ratio fields
            last_any = cast(Any, items_any[-1])
            if isinstance(last_any, dict):
                last: Dict[str, Any] = cast(Dict[str, Any], last_any)
                if 'longShortRatio' in last:
                    val = float(last['longShortRatio'])
                    return val if 0.0 <= val <= 1.0 else max(0.0, min(1.0, val / 100 if val > 1.0 else val))
                long_rate = last.get('longRate')
                short_rate = last.get('shortRate')
                if long_rate is not None and short_rate is not None:
                    try:
                        l = float(long_rate)
                        s = float(short_rate)
                        total = l + s
                        return (l / total) if total > 0 else None
                    except Exception:
                        pass

            # Attempt taker-buy-sell-volume parsing
            def vol_pair(d: Mapping[str, Any]) -> tuple[float, float]:
                def f(x: Any) -> float:
                    try:
                        return float(x)
                    except Exception:
                        return 0.0
                buy = f(d.get('buyVol')) or f(d.get('buy_volume')) or f(d.get('buyVolUsd')) or f(d.get('buy_volume_usd'))
                sell = f(d.get('sellVol')) or f(d.get('sell_volume')) or f(d.get('sellVolUsd')) or f(d.get('sell_volume_usd'))
                return buy, sell

            mexc_buy = mexc_sell = 0.0
            agg_buy = agg_sell = 0.0
            for it_any in cast(List[Any], items_any):
                if not isinstance(it_any, dict):
                    continue
                row = cast(Mapping[str, Any], it_any)
                b, s = vol_pair(row)
                agg_buy += b
                agg_sell += s
                exch = str(row.get('exchangeName') or row.get('exchange') or '').upper()
                if exch == 'MEXC':
                    mexc_buy, mexc_sell = b, s

            def ratio(b: float, s: float) -> Optional[float]:
                total = b + s
                if total <= 0:
                    return None
                r = b / total
                return max(0.0, min(1.0, r))

            # Prefer MEXC, else aggregate across exchanges
            return ratio(mexc_buy, mexc_sell) or ratio(agg_buy, agg_sell)

        except Exception:
            return None

    def _normalize_coinglass_markets(self, data: Any) -> List[Dict[str, Any]]:
        """Normalize coinglass markets payload into a list of dict rows."""
        rows: List[Dict[str, Any]] = []
        try:
            if isinstance(data, list):
                raw_list: List[Any] = cast(List[Any], data)
                for it_any in raw_list:
                    if isinstance(it_any, dict):
                        rows.append(cast(Dict[str, Any], it_any))
            elif isinstance(data, dict):
                # common shapes: { data: [...] } or { list: [...] }
                # Cast to a typed Mapping so 'get' is not partially unknown for type checkers.
                mapping = cast(Mapping[str, Any], data)
                for key in ("data", "list", "markets"):
                    val: Any = mapping.get(key)
                    if isinstance(val, list):
                        raw_list2: List[Any] = cast(List[Any], val)
                        for it_any in raw_list2:
                            if isinstance(it_any, dict):
                                rows.append(cast(Dict[str, Any], it_any))
                        break
        except Exception:
            rows = []
        return rows
    async def __aenter__(self):
        self.mexc_client = cast(AsyncContextManagerLike, MEXCClient())
        self.coinglass_client = cast(AsyncContextManagerLike, CoinglassClient())
        # load persisted micro metrics and launch background loop
        self._load_micro_metrics()
        try:
            if self._bg_task is None:
                self._bg_task = asyncio.create_task(self._background_refresh_loop())
        except Exception:
            pass
        return self
    async def __aexit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]) -> None:
        if self.mexc_client:
            await self.mexc_client.__aexit__(exc_type, exc_val, exc_tb)
        if self.coinglass_client:
            await self.coinglass_client.__aexit__(exc_type, exc_val, exc_tb)
        try:
            if self._bg_task:
                self._bg_task.cancel()
        except Exception:
            pass
        self._save_micro_metrics(force=True)
    
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
        market_data: Dict[str, Any] = {
            'symbol': symbol,
            'mexc_ticker': cast(Dict[str, Any], {}),
            'coinglass_markets': cast(List[Dict[str, Any]], []),
            'coinglass_summary': cast(Dict[str, Any], {}),
            'coinglass_liquidations': cast(Dict[str, Any], {}),
            'fear_greed': cast(Dict[str, Any], {}),
            'price_analysis': cast(Dict[str, Any], {}),
            'timestamp': time.time()
        }
        
        # Get MEXC ticker (most reliable)
        try:
            if self.mexc_client:
                ticker = cast(Dict[str, Any], await cast(Any, self.mexc_client).get_24hr_ticker(symbol))
                if ticker:
                    market_data['mexc_ticker'] = ticker
                    logger.info(f"MEXC ticker for {symbol}: ${ticker.get('lastPrice', 'N/A')}")
        except Exception as e:
            logger.warning(f"Failed to get MEXC ticker for {symbol}: {e}")
        
        # Get Coinglass analytics (funding, OI change, long/short) from pairs-markets (more reliable)
        try:
            summary: Dict[str, Any] = {}
            if self.coinglass_client:
                base_symbol = symbol  # use full symbol; client handles formatting
                client = cast(Any, self.coinglass_client)
                markets_raw = await client.get_pairs_markets(base_symbol)
                markets = self._normalize_coinglass_markets(markets_raw)
                market_data['coinglass_markets'] = markets
                funding_samples: List[float] = []
                oi_samples: List[float] = []
                mexc_fr = 0.0
                mexc_oi = 0.0
                mexc_oi_chg = 0.0
                mexc_lsr: Optional[float] = None

                for m in markets:
                    try:
                        fr = float(m.get('fundingRate') or m.get('funding_rate') or 0.0)
                        funding_samples.append(fr)
                    except Exception:
                        pass
                    try:
                        oi_chg = float(
                            m.get('h24OpenInterestChange')
                            or m.get('openInterestChange24h')
                            or m.get('open_interest_change_percent_24h')
                            or 0.0
                        )
                        oi_samples.append(oi_chg)
                    except Exception:
                        pass
                    exch = str(m.get('exchangeName') or m.get('exchange_name') or m.get('exchange') or '').upper()
                    if exch == 'MEXC':
                        try:
                            mexc_fr = float(m.get('fundingRate') or m.get('funding_rate') or 0.0)
                        except Exception:
                            mexc_fr = 0.0
                        try:
                            mexc_oi = float(
                                m.get('openInterest')
                                or m.get('open_interest')
                                or m.get('open_interest_usd')
                                or 0.0
                            )
                        except Exception:
                            mexc_oi = 0.0
                        try:
                            mexc_oi_chg = float(
                                m.get('h24OpenInterestChange')
                                or m.get('openInterestChange24h')
                                or m.get('open_interest_change_percent_24h')
                                or 0.0
                            )
                        except Exception:
                            mexc_oi_chg = 0.0
                        # derive long/short ratio if available
                        lr = m.get('longRate') or m.get('long_rate')
                        sr = m.get('shortRate') or m.get('short_rate')
                        if lr is not None and sr is not None:
                            try:
                                l = float(lr)
                                s = float(sr)
                                total = l + s
                                mexc_lsr = (l / total) if total > 0 else None
                            except Exception:
                                mexc_lsr = None

                # prefer MEXC metrics; fallback to medians
                funding_rate = mexc_fr if abs(mexc_fr) > 0 else (
                    statistics.median([v for v in funding_samples if not math.isnan(v)]) if funding_samples else 0.0
                )
                oi_change_24h = mexc_oi_chg if abs(mexc_oi_chg) > 0 else (
                    statistics.median([v for v in oi_samples if not math.isnan(v)]) if oi_samples else 0.0
                )

                # If LSR not present in pairs-markets, try taker-buy-sell-volume/exchange-list with fallback ranges
                if mexc_lsr is None:
                    for rng in ('h1', 'h4', '24h'):
                        try:
                            lsr_hist: Any = await client.get_long_short_ratio(base_symbol, range=rng)
                            extracted = self._extract_long_short_ratio(lsr_hist)
                            if extracted is not None:
                                mexc_lsr = extracted
                                break
                        except Exception:
                            continue

                # Fetch liquidation pressure (>=4h window) and Fear & Greed index (global)
                try:
                    liq = await client.get_liquidation_data(base_symbol, interval='4h')
                    market_data['coinglass_liquidations'] = liq or {}
                except Exception:
                    market_data['coinglass_liquidations'] = {}
                try:
                    fg = await client.get_fear_greed_history()
                    market_data['fear_greed'] = fg or {}
                except Exception:
                    market_data['fear_greed'] = {}

                summary = {
                    'funding_rate': float(funding_rate),
                    'open_interest': float(mexc_oi),
                    'oi_change_24h': float(oi_change_24h),
                    'long_short_ratio': float(mexc_lsr) if mexc_lsr is not None else None,
                }
            market_data['coinglass_summary'] = summary
            # Mark data freshness info for UI/debug
            market_data['coinglass_meta'] = {
                'pairs_markets': 'realtime',
                'lsr_source': 'pairs-markets' if summary.get('long_short_ratio') is not None else 'taker-buy-sell-volume(4h)'
            }
        except Exception as e:
            logger.warning(f"Failed to get Coinglass analytics for {symbol}: {e}")
        
        return market_data

    def _analyze_price_action(self, ticker_data: Dict[str, Any]) -> PriceAnalysis:
        """Analyze price action from ticker data"""
        analysis: PriceAnalysis = {
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
    def _analyze_market_sentiment(self, coinglass_data: Any) -> MarketSentiment:
        """Analyze market sentiment from Coinglass data.
        Accepts either a pre-computed summary dict (preferred) or a raw markets list for backward compatibility.
        """
        sentiment: MarketSentiment = {
            'funding_rate': 0.0,
            'open_interest_trend': 'NEUTRAL',
            'exchange_distribution': {},
            'sentiment_score': 0.0,
            'oi_change_24h': 0.0,
            'long_short_ratio': 0.0,
        }
        
        try:
            # Preferred: summary dict
            if isinstance(coinglass_data, dict) and coinglass_data:
                cg: Dict[str, Any] = cast(Dict[str, Any], coinglass_data)
                funding_rate = float(cg.get('funding_rate') or 0.0)
                oi_change = float(cg.get('oi_change_24h') or 0.0)
                lsr_val: Any = cg.get('long_short_ratio')
                if lsr_val is not None:
                    try:
                        sentiment['long_short_ratio'] = float(lsr_val)
                    except Exception:
                        pass
                sentiment['funding_rate'] = funding_rate
                if oi_change > 5:
                    sentiment['open_interest_trend'] = 'RISING'
                elif oi_change < -5:
                    sentiment['open_interest_trend'] = 'FALLING'
                sentiment['oi_change_24h'] = oi_change
                # Score
                score = 0.0
                if funding_rate > 0.0:
                    score += min(0.4, abs(funding_rate) * 10)
                elif funding_rate < 0.0:
                    score -= min(0.4, abs(funding_rate) * 10)
                if oi_change > 0.0:
                    score += min(0.3, oi_change / 20)
                elif oi_change < 0.0:
                    score -= min(0.3, abs(oi_change) / 20)
                # Incorporate liquidation imbalance and Fear & Greed if present in coinglass_data wrapper
                try:
                    # Expect caller to pass extended dict with optional keys
                    cg_ext = cast(Dict[str, Any], coinglass_data)
                    liq = cast(Dict[str, Any], cg_ext.get('coinglass_liquidations') or {})
                    fg = cast(Dict[str, Any], cg_ext.get('fear_greed') or {})
                    # liquidation: sum long vs short USD; tilt score slightly
                    long_liq = float(liq.get('longVolUsd', 0) or liq.get('long_volume_usd', 0) or 0)
                    short_liq = float(liq.get('shortVolUsd', 0) or liq.get('short_volume_usd', 0) or 0)
                    total_liq = long_liq + short_liq
                    if total_liq > 0:
                        bias = (long_liq - short_liq) / total_liq  # -1..1 (short-dominant negative)
                        score += max(-0.15, min(0.15, bias * 0.3))
                    # fear & greed: expect latest value under 'value' or last item list
                    fg_val = 50.0
                    if 'value' in fg:
                        try:
                            fg_val = float(fg.get('value') or 50)
                        except Exception:
                            fg_val = 50.0
                    elif 'list' in fg and isinstance(fg['list'], list) and fg['list']:
                        try:
                            fg_val = float(cast(Any, fg['list'][-1]).get('value', 50))
                        except Exception:
                            fg_val = 50.0
                    # Map 0..100 to -0.2..+0.2 contribution around 50
                    score += max(-0.2, min(0.2, (fg_val - 50.0) / 50.0 * 0.2))
                except Exception:
                    pass
                sentiment['sentiment_score'] = max(-1.0, min(1.0, score))
                return sentiment

            # Fallback: markets list (legacy path)
            if not coinglass_data:
                return sentiment
            mexc_data: Optional[Dict[str, Any]] = None
            funding_samples: List[float] = []
            oi_change_samples: List[float] = []
            markets_list: List[Dict[str, Any]] = [cast(Dict[str, Any], m) for m in cast(List[Any], coinglass_data) if isinstance(m, dict)]
            for market in markets_list:
                try:
                    fr = market.get('fundingRate') or market.get('funding_rate')
                    if fr is not None:
                        funding_samples.append(float(fr or 0.0))
                except Exception:
                    pass
                try:
                    oi_raw = (
                        market.get('h24OpenInterestChange')
                        or market.get('openInterestChange24h')
                        or market.get('open_interest_change_percent_24h')
                    )
                    if oi_raw is not None:
                        oi_change_samples.append(float(oi_raw or 0.0))
                except Exception:
                    pass
                if (market.get('exchangeName') or market.get('exchange_name')) == 'MEXC':
                    mexc_data = market

            def _median(values: List[float]) -> float:
                try:
                    cleaned = [v for v in values if not math.isnan(v)]
                    return statistics.median(cleaned) if cleaned else 0.0
                except Exception:
                    return 0.0

            funding_rate = 0.0
            oi_change = 0.0
            if mexc_data:
                try:
                    funding_rate = float(mexc_data.get('fundingRate') or mexc_data.get('funding_rate') or 0.0)
                except Exception:
                    funding_rate = 0.0
                try:
                    oi_change = float(
                        mexc_data.get('h24OpenInterestChange')
                        or mexc_data.get('openInterestChange24h')
                        or mexc_data.get('open_interest_change_percent_24h')
                        or 0.0
                    )
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
            sentiment['oi_change_24h'] = oi_change

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
            
            # Analyze market sentiment (prefer summary)
            cg_summary_dict: Dict[str, Any] = cast(Dict[str, Any], market_data.get('coinglass_summary') or {})
            # Pass extended context so liquidation and fear/greed can affect score
            extended_ctx: Dict[str, Any] = {
                **cg_summary_dict,
                'coinglass_liquidations': market_data.get('coinglass_liquidations'),
                'fear_greed': market_data.get('fear_greed'),
            } if cg_summary_dict else {}
            sentiment_analysis = self._analyze_market_sentiment(extended_ctx if extended_ctx else market_data.get('coinglass_markets', []))
            market_data['sentiment_analysis'] = sentiment_analysis
            
            # Generate signal using simplified but effective logic
            signal_result = self._generate_signal_from_analysis(symbol, price_analysis, sentiment_analysis)
            
            # Enhance with Gemini analysis if available
            try:
                # Build a richer structured snapshot for Gemini
                ticker = cast(Dict[str, Any], market_data.get('mexc_ticker', {}) or {})
                cg_summary = cast(Dict[str, Any], market_data.get('coinglass_summary', {}) or {})
                liq = cast(Dict[str, Any], market_data.get('coinglass_liquidations', {}) or {})
                fg = cast(Dict[str, Any], market_data.get('fear_greed', {}) or {})
                try:
                    long_liq_any: Any = liq.get('longVolUsd') or liq.get('long_volume_usd') or 0
                    long_liq = float(long_liq_any) if long_liq_any not in (None, "") else 0.0
                except Exception:
                    long_liq = 0.0
                try:
                    short_liq_any: Any = liq.get('shortVolUsd') or liq.get('short_volume_usd') or 0
                    short_liq = float(short_liq_any) if short_liq_any not in (None, "") else 0.0
                except Exception:
                    short_liq = 0.0
                fg_val: Optional[float] = None
                try:
                    if 'value' in fg:
                        fg_val = float(fg.get('value') or 0)
                    else:
                        list_any = fg.get('list')  # fg is Dict[str, Any]
                        if isinstance(list_any, list) and list_any:
                            last_fg_candidate = cast(Any, list_any[-1])
                            if isinstance(last_fg_candidate, dict):
                                last_fg_dict: Dict[str, Any] = cast(Dict[str, Any], last_fg_candidate)
                                val_raw: Any = last_fg_dict.get('value')
                                try:
                                    if val_raw is not None:
                                        fg_val = float(val_raw)
                                except Exception:
                                    fg_val = None
                except Exception:
                    fg_val = None
                structured: Dict[str, Any] = {
                    'symbol': symbol,
                    'price': {
                        'last': ticker.get('lastPrice'),
                        'change_pct_24h': ticker.get('priceChangePercent'),
                        'high_24h': ticker.get('highPrice'),
                        'low_24h': ticker.get('lowPrice'),
                        'volume_24h': ticker.get('volume')
                    },
                    'derived_price_analysis': price_analysis,
                    'sentiment_analysis': sentiment_analysis,
                    'coinglass_summary': cg_summary,
                    'risk_metrics': {
                        'funding_rate': cg_summary.get('funding_rate'),
                        'open_interest': cg_summary.get('open_interest'),
                        'oi_change_24h_pct': cg_summary.get('oi_change_24h'),
                        'long_short_ratio': cg_summary.get('long_short_ratio'),
                        'liquidations_long_usd': long_liq,
                        'liquidations_short_usd': short_liq,
                        'fear_greed_index': fg_val,
                    }
                }
                gemini_prompt = f"""
Anda adalah analis futures kripto profesional. Evaluasi data terstruktur berikut dan berikan insight trading ringkas (<=180 kata) dalam Bahasa Indonesia.

1. Validasi apakah arah sinyal '{signal_result['signal']}' sudah tepat.
2. Jika berbeda, sarankan penyesuaian dan jelaskan alasan (funding, OI, rasio long/short, momentum, volatilitas).
3. Identifikasi 1-2 risiko utama (mis. funding ekstrem, OI divergen, volatilitas tinggi, ketidakseimbangan likuidasi).
4. Beri nada objektif, hindari hype, sertakan peringatan risiko.

DATA:
{structured}

Format keluaran:
- Ringkasan arah & konfirmasi
- Faktor pendukung (bullet pendek)
- Risiko / waspada
- Catatan manajemen risiko singkat
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
    
    def _generate_signal_from_analysis(self, symbol: str, price_analysis: Mapping[str, Any], sentiment_analysis: Mapping[str, Any]) -> Dict[str, Any]:
        """Generate signal from price and sentiment analysis"""
        # Base signal determination
        trend = price_analysis.get('trend', 'NEUTRAL')
        strength = price_analysis.get('strength', 0.0)
        sentiment_score = float(sentiment_analysis.get('sentiment_score', 0.0))
        funding_rate = float(sentiment_analysis.get('funding_rate', 0.0))
        oi_trend = sentiment_analysis.get('open_interest_trend', 'NEUTRAL')
        oi_change_val = float(sentiment_analysis.get('oi_change_24h', 0.0))
        lsr_val = float(sentiment_analysis.get('long_short_ratio', 0.0))

        # Signal logic (improved, non-zero confidence & localized)
        signal = "WAIT"
        confidence = 0.2  # minimal baseline agar tidak 0
        reasoning = ""

        # Bullish conditions
        if trend in ['BULLISH', 'STRONG_BULLISH'] and sentiment_score > 0:
            signal = "LONG"
            # tambahkan bobot dari perubahan harga & OI
            price_chg = float(price_analysis.get('price_change_percent', 0.0))
            base = 0.4 + float(strength) + min(abs(sentiment_score), 0.6)
            base += 0.1 if oi_trend == 'RISING' else 0.0
            base += 0.05 if price_chg > 2 else 0.0
            confidence = max(confidence, min(0.92, base))
            reasoning = (
                f"Tren bullish terdeteksi dengan momentum {price_analysis.get('momentum', 'sedang')}. "
                f"Sentimen positif (skor: {sentiment_score:.2f}), funding {funding_rate:.4f}, OI 24j {oi_change_val:.2f}%. "
            )
            if oi_trend == 'RISING':
                reasoning += "Open interest yang meningkat mendukung kenaikan. "
            if lsr_val:
                reasoning += f"Rasio long/short: {lsr_val:.2f}. "

        # Bearish conditions
        elif trend in ['BEARISH', 'STRONG_BEARISH'] and sentiment_score < 0:
            signal = "SHORT"
            price_chg = float(price_analysis.get('price_change_percent', 0.0))
            base = 0.4 + float(strength) + min(abs(sentiment_score), 0.6)
            base += 0.1 if oi_trend == 'FALLING' else 0.0
            base += 0.05 if price_chg < -2 else 0.0
            confidence = max(confidence, min(0.92, base))
            reasoning = (
                f"Tren bearish terdeteksi dengan momentum {price_analysis.get('momentum', 'sedang')}. "
                f"Sentimen negatif (skor: {sentiment_score:.2f}), funding {funding_rate:.4f}, OI 24j {oi_change_val:.2f}%. "
            )
            if oi_trend == 'FALLING':
                reasoning += "Open interest yang menurun menegaskan pelemahan. "
            if lsr_val:
                reasoning += f"Rasio long/short: {lsr_val:.2f}. "

        # Neutral/Wait conditions
        else:
            price_chg = float(price_analysis.get('price_change_percent', 0.0))
            reasoning = (
                f"Sinyal campuran. Tren: {trend}. Sentimen {sentiment_score:.2f}, funding {funding_rate:.4f}, "
                f"OI {oi_trend}, OI 24j {oi_change_val:.2f}%, Perubahan harga 24j {price_chg:.2f}%. "
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
            'entry_price': None,
            'stop_loss': None,
            'take_profit': None
        }
    
    def _format_market_data(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format market data for display"""
        ticker = market_data.get('mexc_ticker', {})
        coinglass: List[Dict[str, Any]] = cast(List[Dict[str, Any]], market_data.get('coinglass_markets') or [])
        cg_summary: Dict[str, Any] = cast(Dict[str, Any], market_data.get('coinglass_summary') or {})
        liq_data: Dict[str, Any] = cast(Dict[str, Any], market_data.get('coinglass_liquidations') or {})
        fg_data: Dict[str, Any] = cast(Dict[str, Any], market_data.get('fear_greed') or {})

        def _to_float(x: Any) -> float:
            try:
                return float(x)
            except Exception:
                return 0.0

        # Explicitly type inner dicts to avoid Unknown
        price_data: Dict[str, float] = {
            'markPrice': _to_float(ticker.get('lastPrice', 0)),
            'priceChangePercent': _to_float(ticker.get('priceChangePercent', 0)),
            'volume': _to_float(ticker.get('volume', 0)),
            'highPrice': _to_float(ticker.get('highPrice', 0)),
            'lowPrice': _to_float(ticker.get('lowPrice', 0))
        }
        coinglass_data: Dict[str, float] = {}
        kline_data: Dict[str, Any] = {}

        formatted: Dict[str, Any] = {
            'price_data': price_data,
            'coinglass_data': coinglass_data,
            'kline_data': kline_data,
            'timeframes_analyzed': ['24h']
        }

        # Prefer summary if present
        if cg_summary:
            fr = _to_float(cg_summary.get('funding_rate'))
            oi = _to_float(cg_summary.get('open_interest'))
            oi_chg = _to_float(cg_summary.get('oi_change_24h'))
            lsr = cg_summary.get('long_short_ratio')
            if lsr is not None:
                try:
                    coinglass_data['long_short_ratio'] = float(lsr)
                except Exception:
                    pass
            formatted['coinglass_data'] = {
                'funding_rate': fr,
                'open_interest': oi,
                'oi_change_24h': oi_chg,
                **({'long_short_ratio': float(lsr)} if lsr is not None else {})
            }
        elif coinglass:
            mexc_market: Optional[Dict[str, Any]] = next((m for m in coinglass if (m.get('exchangeName') or m.get('exchange_name')) == 'MEXC'), None)
            if mexc_market:
                funding = _to_float(mexc_market.get('fundingRate') or mexc_market.get('funding_rate'))
                oi = _to_float(mexc_market.get('openInterest') or mexc_market.get('open_interest') or mexc_market.get('open_interest_usd'))
                oi_chg = _to_float(
                    mexc_market.get('h24OpenInterestChange')
                    or mexc_market.get('openInterestChange24h')
                    or mexc_market.get('open_interest_change_percent_24h')
                )
            else:
                funding = 0.0
                oi = 0.0
                oi_chg = 0.0
            # Fallback to median across exchanges when missing/zero
            if abs(funding) < 1e-9:
                f_samples = [
                    _to_float(m.get('fundingRate') or m.get('funding_rate'))
                    for m in coinglass if (m.get('fundingRate') is not None or m.get('funding_rate') is not None)
                ]
                try:
                    funding = statistics.median([v for v in f_samples if not math.isnan(v)]) if f_samples else 0.0
                except Exception:
                    funding = 0.0
            if abs(oi_chg) < 1e-9:
                oi_samples = [
                    _to_float(
                        m.get('h24OpenInterestChange')
                        or m.get('openInterestChange24h')
                        or m.get('open_interest_change_percent_24h')
                    )
                    for m in coinglass
                    if (
                        m.get('h24OpenInterestChange') is not None
                        or m.get('openInterestChange24h') is not None
                        or m.get('open_interest_change_percent_24h') is not None
                    )
                ]
                try:
                    oi_chg = statistics.median([v for v in oi_samples if not math.isnan(v)]) if oi_samples else 0.0
                except Exception:
                    oi_chg = 0.0
            formatted['coinglass_data'] = {
                'funding_rate': funding,
                'open_interest': oi,
                'oi_change_24h': oi_chg
            }

        # Add liquidation and fear/greed snapshots if present
        try:
            long_liq = float(liq_data.get('longVolUsd', 0) or liq_data.get('long_volume_usd', 0) or 0)
            short_liq = float(liq_data.get('shortVolUsd', 0) or liq_data.get('short_volume_usd', 0) or 0)
            if long_liq or short_liq:
                formatted['coinglass_data'].update({
                    'liquidations_long_usd': long_liq,
                    'liquidations_short_usd': short_liq
                })
        except Exception:
            pass
        try:
            fg_val = None
            if 'value' in fg_data:
                fg_val = float(fg_data.get('value') or 0)
            elif 'list' in fg_data and isinstance(fg_data['list'], list) and fg_data['list']:
                fg_val = float(cast(Any, fg_data['list'][-1]).get('value', 0))
            if fg_val is not None and fg_val > 0:
                formatted['coinglass_data']['fear_greed'] = fg_val
        except Exception:
            pass

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
        klines_raw: Any = None
        if self.mexc_client:
            klines_raw = await cast(Any, self.mexc_client).get_klines(symbol, tf_map[tf], limit=200)
        klines: List[List[Any]] = cast(List[List[Any]], klines_raw or [])
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
            gains: List[float] = []
            losses: List[float] = []
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
            'explanation': explanation
        }
    async def get_market_explanation(self, symbol: str) -> str:
        """Return a concise market explanation string for a symbol.
        Uses Gemini when available, otherwise falls back to a simple summary built from reliable data.
        """
        try:
            market_data = await self._get_reliable_market_data(symbol)
            # Pre-compute structured metrics for local enrichment
            ticker = cast(Dict[str, Any], market_data.get('mexc_ticker') or {})
            cg_summary: Dict[str, Any] = cast(Dict[str, Any], market_data.get('coinglass_summary') or {})
            last_price = None
            change_pct = 0.0
            high_price = None
            low_price = None
            try:
                if ticker:
                    last_price = float(ticker.get('lastPrice') or 0)
                    change_pct = float(ticker.get('priceChangePercent') or 0)
                    high_price = float(ticker.get('highPrice') or 0)
                    low_price = float(ticker.get('lowPrice') or 0)
            except Exception:
                pass
            daily_range_pct = 0.0
            if last_price and high_price and low_price and last_price > 0:
                try:
                    daily_range_pct = ((high_price - low_price) / last_price) * 100.0
                except Exception:
                    daily_range_pct = 0.0
            funding_rate = float(cg_summary.get('funding_rate') or 0.0)
            oi_change = float(cg_summary.get('oi_change_24h') or 0.0)
            lsr = cg_summary.get('long_short_ratio')
            try:
                lsr_f = float(lsr) if lsr is not None else None
            except Exception:
                lsr_f = None

            def _classify_vol(r: float) -> str:
                if r > 7: return 'SANGAT TINGGI'
                if r > 5: return 'TINGGI'
                if r > 3: return 'MENENGAH'
                if r > 1.5: return 'RENDAH'
                return 'SANGAT RENDAH'

            vol_class = _classify_vol(daily_range_pct)

            # Short-term (scalping) directional bias heuristic
            bias = 'NETRAL'
            if change_pct > 0.6 and funding_rate >= 0 and oi_change > 0:  # sustained interest up
                bias = 'BULLISH INTRADAY'
            elif change_pct < -0.6 and funding_rate <= 0 and oi_change < 0:
                bias = 'BEARISH INTRADAY'
            elif abs(change_pct) > 0.4:
                bias = 'MODERAT ' + ('BULLISH' if change_pct > 0 else 'BEARISH')

            # Suggested scalping setup (pure heuristic – educational)
            scalping_lines: List[str] = []
            if last_price:
                # Dynamic micro volatility baseline
                micro_vol = max(0.08, min(0.25, daily_range_pct / 20))  # percent of price as base risk window
                stop_pct = micro_vol * (1.2 if vol_class in ('TINGGI','SANGAT TINGGI') else 0.9)
                tp_pct = stop_pct * (1.4 if bias.startswith('BULLISH') or bias.startswith('BEARISH') else 1.2)
                # If long/short ratio extreme, adjust risk (contrarian caution)
                if lsr_f is not None:
                    if lsr_f > 0.65:  # long crowded
                        stop_pct *= 0.9
                        tp_pct *= 1.05
                    elif lsr_f < 0.35:  # short crowded
                        stop_pct *= 0.9
                        tp_pct *= 1.05
                def _fmt(p: float) -> str:
                    return f"{p:.2f}%"
                # Position bias and invalidation hint
                if bias.startswith('BULLISH'):
                    scalping_lines.append(f"Bias: 🟢 {bias}")
                elif bias.startswith('BEARISH'):
                    scalping_lines.append(f"Bias: 🔴 {bias}")
                else:
                    scalping_lines.append(f"Bias: ⚪ {bias}")
                scalping_lines.append(f"Volatilitas Harian: {vol_class} (~{daily_range_pct:.2f}%)")
                if funding_rate:
                    scalping_lines.append(f"Funding: {funding_rate:.4f} ({'positif' if funding_rate>0 else 'negatif'})")
                if oi_change:
                    scalping_lines.append(f"OI 24j: {oi_change:+.2f}%")
                if lsr_f is not None:
                    scalping_lines.append(f"Rasio Long/Short: {lsr_f:.2f}")
                scalping_lines.append(f"Rasio R/R target: ~1:{(tp_pct/stop_pct):.2f}")
                scalping_lines.append(f"Stop (perkiraan): {_fmt(stop_pct)} | TP awal: {_fmt(tp_pct)}")
                scalping_lines.append("Gunakan konfirmasi order book / momentum 1-5m.")

            indicator_summary: List[str] = []
            if last_price:
                indicator_summary.append(f"Harga: ${last_price:.2f}")
            indicator_summary.append(f"Perubahan 24j: {change_pct:+.2f}%")
            indicator_summary.append(f"Range 24j: {daily_range_pct:.2f}% ({vol_class})")
            indicator_summary.append(f"Funding: {funding_rate:.4f}")
            indicator_summary.append(f"OI 24j: {oi_change:+.2f}%")
            if lsr_f is not None:
                indicator_summary.append(f"Long/Short: {lsr_f:.2f}")
            # --- Micro (1m) Volume Profile & ATR Integration ---
            micro_lines: List[str] = []
            if Config.ENABLE_VOLUME_PROFILE_EXPLANATION:
                try:
                    vp = self._compute_volume_profile(symbol)
                    atr1m = self._compute_atr1m(symbol)
                    if atr1m:
                        micro_lines.append(f"ATR1m: {atr1m:.2f}%")
                    if vp and last_price:
                        poc = vp.get('poc')
                        rngp = vp.get('range_pct')
                        if isinstance(poc, (int,float)) and poc > 0 and last_price > 0:
                            diff_poc = (last_price - poc)/last_price * 100.0
                            micro_lines.append(f"POC: {poc:.2f} (Δ{diff_poc:+.2f}%)")
                        if isinstance(rngp, (int,float)) and rngp >= 0:
                            micro_lines.append(f"VRng: {rngp:.2f}%")
                except Exception:
                    pass
            if micro_lines:
                # append micro metrics compactly
                indicator_summary.append(" | ".join(micro_lines))
            indicator_block = " • ".join(indicator_summary)

            # Try Gemini explanation first
            try:
                micro_for_ai = ''
                try:
                    if micro_lines and Config.ENABLE_VOLUME_PROFILE_EXPLANATION:
                        micro_for_ai = "\nMicro Profil: " + "; ".join(micro_lines)
                except Exception:
                    micro_for_ai = ''
                gemini_prompt = (
                    f"Ringkas kondisi pasar untuk {symbol} berdasarkan data berikut.\n"
                    f"Ticker MEXC: {market_data.get('mexc_ticker', {})}\n"
                    f"Jumlah entri Coinglass: {len(market_data.get('coinglass_markets', []))}\n"
                    f"Indikator Lokal: {indicator_block}{micro_for_ai}\n"
                    "Berikan ringkasan singkat (<= 4 kalimat) dalam bahasa Indonesia. "
                    "Sertakan heading 'Update Pasar' lalu bagian 'Indikator Kunci:' dengan bullet ringkas jika cukup ruang."
                )
                resp = await self.gemini_analyzer.explain_market_conditions(symbol, {'analysis': gemini_prompt})
                # Treat empty or geo-block error responses as fallback triggers
                if resp and 'FAILED_PRECONDITION' not in resp and 'lokasi' not in resp.lower() and 'location is not supported' not in resp.lower():
                    trimmed = resp[:1200]
                    needs_indicators = 'Indikator Kunci' not in trimmed or trimmed.strip().endswith(':') or trimmed.strip().endswith('Kunci')
                    if needs_indicators:
                        trimmed += f"\n\n**Indikator Kunci (Heuristik Lokal):**\n{indicator_block}"
                    if scalping_lines:
                        trimmed += "\n\n**Scalping Setup (Eksperimental):**\n" + "\n".join(f"- {l}" for l in scalping_lines)
                    return trimmed
                else:
                    if resp:
                        logger.info("Gemini response indicates geo-block or error; using fallback summary.")
            except Exception as e:
                logger.warning(f"Gemini explanation failed for {symbol}: {e}")

            # Fallback: build a lightweight human-readable summary
            ticker = market_data.get('mexc_ticker', {})
            cg_list: List[Dict[str, Any]] = cast(List[Dict[str, Any]], market_data.get('coinglass_markets') or [])
            funding_rate = 0.0
            oi_change = 0.0
            if cg_list:
                mexc_market: Optional[Dict[str, Any]] = next((m for m in cg_list if m.get('exchangeName') == 'MEXC'), None)
                if mexc_market:
                    try:
                        funding_rate = float(mexc_market.get('fundingRate') or 0)
                    except Exception:
                        funding_rate = 0.0
                    try:
                        oi_change = float(mexc_market.get('h24OpenInterestChange') or 0)
                    except Exception:
                        oi_change = 0.0

            try:
                change_pct = float(ticker.get('priceChangePercent', 0))
            except Exception:
                change_pct = 0.0

            parts: List[str] = []
            lp = ticker.get('lastPrice')
            if lp:
                parts.append(f"Harga: ${lp} ({change_pct:+.2f}%)")
            if funding_rate:
                parts.append(f"Funding: {funding_rate:.4f}")
            if oi_change:
                parts.append(f"OI 24j: {oi_change:+.2f}%")
            parts.append(f"Range: {daily_range_pct:.2f}% ({vol_class})")
            base_summary = " | ".join(parts) if parts else "Data terbatas tersedia."
            enriched = base_summary + f"\n\n**Indikator Kunci (Heuristik Lokal):**\n{indicator_block}"
            if scalping_lines:
                enriched += "\n\n**Scalping Setup (Eksperimental):**\n" + "\n".join(f"- {l}" for l in scalping_lines)
            return enriched
        except Exception as e:
            logger.error(f"Failed to build market explanation for {symbol}: {e}")
            return "Penjelasan pasar tidak tersedia saat ini."
        return "Penjelasan pasar tidak tersedia saat ini."

    async def get_supported_pairs(self) -> List[str]:
        now = time.time()
        try:
            if (now - float(self._pairs_cache.get('ts', 0))) <= 60 and self._pairs_cache.get('data'):
                return list(self._pairs_cache['data'])

            info: Dict[str, Any] = {}
            if self.mexc_client:
                # Ensure typed mapping to avoid Unknown types from dynamic API response
                info = cast(Dict[str, Any], await cast(Any, self.mexc_client).get_exchange_info())
            pairs: List[str] = []
            symbols_candidates: List[Dict[str, Any]] = []
            # Common schema: { symbols: [ { symbol, quoteAsset, status } ] }
            raw_symbols_obj: object = info.get('symbols') or info.get('data') or []
            if isinstance(raw_symbols_obj, list):
                # Keep only dict items and type them explicitly
                raw_symbols_list: List[Any] = cast(List[Any], raw_symbols_obj)
                symbols_candidates = [cast(Dict[str, Any], d) for d in raw_symbols_list if isinstance(d, dict)]
            if symbols_candidates:
                for s in symbols_candidates:
                    sym = cast(str, s.get('symbol') or s.get('symbolName') or '')
                    quote = cast(str, s.get('quoteAsset') or '')
                    status = cast(str, (s.get('status') or '')).upper()
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