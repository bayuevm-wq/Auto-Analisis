from __future__ import annotations

from typing import Dict, List

import pandas as pd


def _nearest_zone(zones: List[Dict[str, object]], zone_type: str) -> Dict[str, object] | None:
    filtered = [z for z in zones if z["type"] == zone_type]
    if not filtered:
        return None
    return filtered[-1]


def score_direction(
    df: pd.DataFrame,
    features: Dict[str, float],
    structure: Dict[str, object],
    liquidity: Dict[str, object],
    zones: List[Dict[str, object]],
    regime: str,
    htf_trend: str = "unknown",
    wyckoff: Dict[str, object] | None = None,
    timeframe: str = "4h",
    smc: Dict[str, object] | None = None,
    news_sentiment: float = 0.0,
) -> float:
    """Compute a directional score in [-1, 1].

    Positive = bullish bias, negative = bearish bias.  The score is built
    from an additive model across multiple analysis dimensions.
    """
    is_intraday = timeframe.lower() in {"1m", "3m", "5m", "15m", "30m", "45m", "1h", "60m"}
    w_struct = 1.5 if is_intraday else 1.0
    w_liq = 1.3 if is_intraday else 1.0
    w_htf = 0.8 if is_intraday else 1.2
    w_wyckoff = 0.7 if is_intraday else 1.2

    score = 0.0

    # ── Market Structure ──────────────────────────────────────────────
    if structure["trend"] == "bullish":
        score += (0.2 * w_struct)
    elif structure["trend"] == "bearish":
        score -= (0.2 * w_struct)

    if structure.get("bos"):
        score += (0.1 * w_struct) if structure["trend"] == "bullish" else (-0.1 * w_struct)
    if structure.get("choch"):
        score += (-0.1 * w_struct) if structure["trend"] == "bullish" else (0.1 * w_struct)

    # ── HTF Alignment ─────────────────────────────────────────────────
    if htf_trend != "unknown":
        if htf_trend == structure["trend"] and htf_trend in {"bullish", "bearish"}:
            score += (0.15 * w_htf) if htf_trend == "bullish" else (-0.15 * w_htf)
        elif htf_trend != structure["trend"] and htf_trend in {"bullish", "bearish"}:
            score += (-0.1 * w_htf) if htf_trend == "bearish" else (0.1 * w_htf)

    # ── RSI ───────────────────────────────────────────────────────────
    rsi = features.get("rsi", 50.0)
    bearish_div = bool(features.get("bearish_divergence", 0.0))
    bullish_div = bool(features.get("bullish_divergence", 0.0))

    if rsi > 55:
        score += 0.1
    elif rsi < 45:
        score -= 0.1
        
    # Penalize shorting deeply oversold / longing deeply overbought without divergence
    if rsi < 30 and not bearish_div:
        score += 0.5
    if rsi > 70 and not bullish_div:
        score -= 0.5

    # ── RSI Hidden Divergence ─────────────────────────────────────────
    if features.get("rsi_bullish_hidden"):
        score += 0.08
    if features.get("rsi_bearish_hidden"):
        score -= 0.08

    # ── MACD ──────────────────────────────────────────────────────────
    macd_hist = features.get("macd_hist", 0.0)
    score += 0.1 if macd_hist > 0 else -0.1 if macd_hist < 0 else 0.0

    # ── MACD Divergence ───────────────────────────────────────────────
    if features.get("macd_bullish_div"):
        score += 0.1
    if features.get("macd_bearish_div"):
        score -= 0.1

    # ── Momentum ──────────────────────────────────────────────────────
    momentum = features.get("momentum", 0.0)
    score += 0.1 if momentum > 0 else -0.1 if momentum < 0 else 0.0

    # ── VWAP ──────────────────────────────────────────────────────────
    vwap = features.get("vwap", 0.0)
    last_price_score = float(df["close"].iloc[-1])
    if vwap > 0:
        score += 0.05 if last_price_score > vwap else -0.05

    # ── Rate of Change exhaustion ─────────────────────────────────────
    roc_price = features.get("roc_price", 0.0)
    roc_mom = features.get("roc_momentum", 0.0)
    if roc_price > 0 and roc_mom < 0:
        score -= 0.05  # Bullish exhaustion
    elif roc_price < 0 and roc_mom > 0:
        score += 0.05  # Bearish exhaustion

    # ── Volume Spike & Imbalance ──────────────────────────────────────
    vol_spike = features.get("volume_spike", 0.0)
    vol_imbalance = features.get("volume_imbalance", 0.0)
    if vol_spike:
        # A volume spike reinforces the current candle direction
        last_candle_dir = 1 if df["close"].iloc[-1] > df["open"].iloc[-1] else -1
        score += 0.05 * last_candle_dir
    if vol_imbalance > 0.5:
        score += 0.03
    elif vol_imbalance < -0.5:
        score -= 0.03

    # ── Liquidity proximity ───────────────────────────────────────────
    buy_dist = liquidity.get("distance_to_buy_liquidity")
    sell_dist = liquidity.get("distance_to_sell_liquidity")
    if buy_dist is not None and sell_dist is not None:
        score += (0.05 * w_liq) if buy_dist < sell_dist else (-0.05 * w_liq)

    # ── Supply / Demand zones ─────────────────────────────────────────
    demand_zone = _nearest_zone(zones, "demand")
    supply_zone = _nearest_zone(zones, "supply")
    last_price = float(df["close"].iloc[-1])
    if demand_zone is not None and last_price > demand_zone["high"]:
        score += 0.05
    if supply_zone is not None and last_price < supply_zone["low"]:
        score -= 0.05

    # ── Regime ────────────────────────────────────────────────────────
    if "trending-bullish" in regime:
        score += 0.05
    if "trending-bearish" in regime:
        score -= 0.05

    # ── Premium / Discount Zone ───────────────────────────────────────
    # ICT concept: buy in discount (<25% of range), sell in premium (>75%)
    swing_high = float(df["high"].rolling(window=20).max().iloc[-1])
    swing_low = float(df["low"].rolling(window=20).min().iloc[-1])
    range_size = swing_high - swing_low
    if range_size > 0:
        price_position = (last_price - swing_low) / range_size
        if price_position < 0.25:  # Discount zone → favors long
            score += 0.08
        elif price_position > 0.75:  # Premium zone → favors short
            score -= 0.08

    # ── Wyckoff Phase ─────────────────────────────────────────────────
    if wyckoff is not None:
        phase = wyckoff.get("phase", "neutral")
        signals = wyckoff.get("signals", [])

        if phase == "accumulation":
            score += (0.1 * w_wyckoff)
        elif phase == "distribution":
            score -= (0.1 * w_wyckoff)
        elif phase == "markup":
            score += (0.1 * w_wyckoff)
        elif phase == "markdown":
            score -= (0.1 * w_wyckoff)

        if "spring" in signals:
            score += (0.15 * w_wyckoff)
        if "upthrust" in signals:
            score -= (0.15 * w_wyckoff)

    # ── Wyckoff vs HTF Tie-Breaker ────────────────────────────────────
    # When Wyckoff phase direction conflicts with HTF trend, apply a deep
    # conviction cut. Wyckoff phase (distribution/accumulation) often leads
    # HTF trend reversal, so we trust it as the tie-breaker.
    if wyckoff is not None and htf_trend in {"bullish", "bearish"}:
        phase = wyckoff.get("phase", "neutral")
        wyckoff_direction = {
            "accumulation": "bullish", "markup": "bullish",
            "distribution": "bearish", "markdown": "bearish",
        }.get(phase, "neutral")

        if wyckoff_direction != "neutral" and wyckoff_direction != htf_trend:
            # Conflict detected: deep conviction penalty against the HTF direction
            # 0.25 translates to ~10.5% conviction shift — strong enough to flip decisions
            conflict_penalty = 0.25
            if htf_trend == "bullish":
                score -= conflict_penalty  # Wyckoff bearish signal overrides
            else:
                score += conflict_penalty  # Wyckoff bullish signal overrides

    # NOTE: Wyckoff vs Ranging HTF penalty is handled as an explicit post-hoc
    # penalty in build_report() for full penalty tracker visibility.
    # Do NOT add score-level penalty here to avoid double-counting.

    # ── FVG Consequent Encroachment ───────────────────────────────────
    if smc is not None and "fvg_ce" in smc:
        for ce in smc["fvg_ce"]:
            if ce["type"] == "bullish":
                score += 0.08
            elif ce["type"] == "bearish":
                score -= 0.08

    # ── News Sentiment NLP ────────────────────────────────────────────
    if news_sentiment != 0.0:
        # A +1.0 compound score maxes out at +0.15 probability score impact
        score += (news_sentiment * 0.15)

    return max(-1.0, min(1.0, score))

