"""
=============================================================================
MODUL STRATEGI & LOGIKA SINYAL (strategy.py)
UAS Algoritma Trading - Bot Dry Run Indodax di Vercel
Mahasiswa   : Indri Destiyana (NIM: 25120200007)
=============================================================================
PENTING (Kepatuhan Rubrik 15% & 25%):
Fungsi sinyal di file ini bersifat DETERMISTIK MURNI dan dipakai BERSAMA
secara identik oleh mesin Backtest historis maupun Bot Live Forward Test.

Spesifikasi Strategi:
- Nama Strategi : Dual EMA Momentum & ATR Volatility Breakout (Adaptasi UTS)
- Tipe          : Long-Only (Tanpa Margin, Tanpa Short, Tanpa Leverage)
- Timeframe     : 1 Jam (tf=60)
- Indikator     : EMA(12), EMA(26), RSI(14), ATR(14), Volume SMA(20)
=============================================================================
"""

import math
from typing import List, Dict, Any, Optional, Tuple

class StrategyConfig:
    EMA_FAST = 12
    EMA_SLOW = 26
    RSI_PERIOD = 14
    RSI_MIN = 45.0
    RSI_MAX = 70.0
    ATR_PERIOD = 14
    ATR_MULT_TRAILING = 2.5  # Sesuai UTS Modul A & B
    VOL_SMA_PERIOD = 20
    STOP_LOSS_PCT = 0.04     # 4.0% hard stop loss
    MAX_OPEN_POSITIONS = 3
    ALLOCATION_PER_POS = 0.30 # 30% modal per koin
    MIN_ORDER_IDR = 25_000   # Batas order ketat mode Pro Indodax


# =============================================================================
# 1. PERHITUNGAN INDIKATOR TEKNIKAL STANDAR
# =============================================================================
def hitung_ema(series: List[float], period: int) -> List[float]:
    """Menghitung Exponential Moving Average (EMA)."""
    if len(series) < period:
        return [0.0] * len(series)

    ema = [0.0] * len(series)
    # Gunakan SMA sebagai seed awal
    sma_seed = sum(series[:period]) / period
    ema[period - 1] = sma_seed
    multiplier = 2.0 / (period + 1)

    for i in range(period, len(series)):
        ema[i] = (series[i] - ema[i - 1]) * multiplier + ema[i - 1]

    return ema


def hitung_rsi(closes: List[float], period: int = 14) -> List[float]:
    """Menghitung Relative Strength Index (RSI) Wilder."""
    if len(closes) <= period:
        return [50.0] * len(closes)

    rsi = [50.0] * len(closes)
    gains = []
    losses = []

    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(0.0, diff))
        losses.append(max(0.0, -diff))

    if len(gains) < period:
        return rsi

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        rsi[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        idx = i + 1
        if avg_loss == 0:
            rsi[idx] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[idx] = 100.0 - (100.0 / (1.0 + rs))

    return rsi


def hitung_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[float]:
    """Menghitung Average True Range (ATR)."""
    n = len(closes)
    if n < 2:
        return [0.0] * n

    tr = [highs[0] - lows[0]]
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr.append(max(hl, hc, lc))

    if n < period:
        return tr

    atr = [0.0] * n
    atr[period - 1] = sum(tr[:period]) / period
    for i in range(period, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return atr


def hitung_sma(series: List[float], period: int) -> List[float]:
    """Menghitung Simple Moving Average (SMA)."""
    n = len(series)
    sma = [0.0] * n
    if n < period:
        return sma
    running_sum = sum(series[:period])
    sma[period - 1] = running_sum / period
    for i in range(period, n):
        running_sum += series[i] - series[i - period]
        sma[i] = running_sum / period
    return sma


# =============================================================================
# 2. EVALUASI SINYAL CANDLE TERTUTUP (IDENTIK BACKTEST & LIVE)
# =============================================================================
def hitung_seluruh_indikator(bars: List[Dict[str, Any]]) -> Dict[str, List[float]]:
    """Mengekstrak dan menghitung seluruh indikator teknikal dari candle bars."""
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    volumes = [b["volume"] for b in bars]

    ema_fast = hitung_ema(closes, StrategyConfig.EMA_FAST)
    ema_slow = hitung_ema(closes, StrategyConfig.EMA_SLOW)
    rsi = hitung_rsi(closes, StrategyConfig.RSI_PERIOD)
    atr = hitung_atr(highs, lows, closes, StrategyConfig.ATR_PERIOD)
    vol_sma = hitung_sma(volumes, StrategyConfig.VOL_SMA_PERIOD)

    return {
        "closes": closes,
        "highs": highs,
        "lows": lows,
        "volumes": volumes,
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "rsi": rsi,
        "atr": atr,
        "vol_sma": vol_sma,
    }


def evaluasi_sinyal_bar(
    bars: List[Dict[str, Any]],
    posisi_terbuka: Optional[Dict[str, Any]] = None,
    indicators: Optional[Dict[str, List[float]]] = None,
    bar_index: int = -1
) -> Dict[str, Any]:
    """
    Mengevaluasi sinyal BUY, SELL, atau HOLD pada bar tertentu.
    Jika posisi_terbuka None -> Evaluasi potensi BUY
    Jika posisi_terbuka Ada  -> Evaluasi potensi SELL (Exit)
    
    Return:
    {
        "signal": "BUY" | "SELL" | "HOLD",
        "reason": str,
        "metrics": dict (snapshot harga & indikator saat sinyal)
    }
    """
    if len(bars) < max(StrategyConfig.EMA_SLOW, StrategyConfig.VOL_SMA_PERIOD) + 5:
        return {"signal": "HOLD", "reason": "Jumlah candle belum mencukupi warm-up indikator.", "metrics": {}}

    if indicators is None:
        indicators = hitung_seluruh_indikator(bars)

    idx = (len(bars) + bar_index) if bar_index < 0 else bar_index
    prev_idx = idx - 1

    close_curr = indicators["closes"][idx]
    high_curr = indicators["highs"][idx]
    low_curr = indicators["lows"][idx]
    vol_curr = indicators["volumes"][idx]

    ema_f_curr = indicators["ema_fast"][idx]
    ema_s_curr = indicators["ema_slow"][idx]
    ema_f_prev = indicators["ema_fast"][prev_idx]
    ema_s_prev = indicators["ema_slow"][prev_idx]

    rsi_curr = indicators["rsi"][idx]
    atr_curr = indicators["atr"][idx]
    vol_sma_curr = indicators["vol_sma"][idx]

    metrics = {
        "close": close_curr,
        "ema_fast": ema_f_curr,
        "ema_slow": ema_s_curr,
        "rsi": rsi_curr,
        "atr": atr_curr,
        "vol": vol_curr,
        "vol_sma": vol_sma_curr,
    }

    # JIKA SUDAH PUNYA POSISI -> CEK ATURAN EXIT (SELL)
    if posisi_terbuka is not None:
        harga_beli = posisi_terbuka.get("entry_price", close_curr)
        highest_price = max(posisi_terbuka.get("highest_price", harga_beli), high_curr)

        # 1. Hard Stop Loss (misal turun >= 4% dari harga entry)
        rugi_pct = (close_curr - harga_beli) / harga_beli
        if rugi_pct <= -StrategyConfig.STOP_LOSS_PCT:
            return {
                "signal": "SELL",
                "reason": f"Hard Stop Loss tercapai: penurunan {rugi_pct * 100:.2f}% (Batas -{StrategyConfig.STOP_LOSS_PCT*100:.1f}%)",
                "metrics": metrics,
                "highest_price": highest_price
            }

        # 2. Trailing Stop ATR (Sesuai Modul UTS: Puncak - 2.5x ATR)
        trailing_stop_level = highest_price - (StrategyConfig.ATR_MULT_TRAILING * atr_curr)
        if close_curr < trailing_stop_level:
            return {
                "signal": "SELL",
                "reason": f"Trailing Stop ATR terpicu: harga {close_curr:,.0f} < batas trailing {trailing_stop_level:,.0f} (Puncak: {highest_price:,.0f})",
                "metrics": metrics,
                "highest_price": highest_price
            }

        # 3. Trend Reversal Exit (EMA Fast menembus ke bawah EMA Slow)
        if ema_f_curr < ema_s_curr and ema_f_prev >= ema_s_prev:
            return {
                "signal": "SELL",
                "reason": f"Trend Reversal: EMA({StrategyConfig.EMA_FAST}) memotong ke bawah EMA({StrategyConfig.EMA_SLOW})",
                "metrics": metrics,
                "highest_price": highest_price
            }

        return {
            "signal": "HOLD",
            "reason": "Posisi masih dalam koridor aman trend.",
            "metrics": metrics,
            "highest_price": highest_price
        }

    # JIKA BELUM PUNYA POSISI -> CEK ATURAN ENTRY (BUY)
    else:
        # Syarat 1: Golden Cross atau Bullish Trend EMA (Fast > Slow)
        kondisi_trend = (ema_f_curr > ema_s_curr)
        # Syarat 2: Momentum RSI sehat (di atas 45 dan belum overbought < 70)
        kondisi_rsi = (StrategyConfig.RSI_MIN <= rsi_curr <= StrategyConfig.RSI_MAX)
        # Syarat 3: Konfirmasi Volume (Volume candle di atas rata-rata SMA 20)
        kondisi_vol = (vol_curr >= vol_sma_curr) if vol_sma_curr > 0 else True
        # Syarat 4: Momentum Breakout (Harga penutupan di atas EMA Fast)
        kondisi_harga = (close_curr > ema_f_curr)

        if kondisi_trend and kondisi_rsi and kondisi_vol and kondisi_harga:
            return {
                "signal": "BUY",
                "reason": f"Konfirmasi Bullish: EMA Fast({ema_f_curr:,.0f}) > Slow({ema_s_curr:,.0f}), RSI({rsi_curr:.1f}) in range [{StrategyConfig.RSI_MIN}-{StrategyConfig.RSI_MAX}], Vol > SMA20",
                "metrics": metrics
            }

        return {
            "signal": "HOLD",
            "reason": "Belum memenuhi seluruh syarat masuk strategi.",
            "metrics": metrics
        }
