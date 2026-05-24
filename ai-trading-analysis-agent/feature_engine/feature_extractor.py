from __future__ import annotations

import logging
from typing import Dict, Tuple

import pandas as pd

from .indicator_features import (
    atr,
    ema,
    macd,
    price_momentum,
    rsi,
    trend_strength,
    volume_imbalance,
    volume_spike,
    detect_rsi_divergence,
    vwap,
    obv,
    volume_profile_poc,
    bb_width,
    detect_macd_divergence,
    roc,
)

logger = logging.getLogger(__name__)


def generate_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, float]]:
    df = df.copy()

    df["ema_fast"] = ema(df["close"], 12)
    df["ema_slow"] = ema(df["close"], 26)
    df["ema_slope"] = df["ema_fast"].diff()
    df["ma_cross"] = df["ema_fast"] > df["ema_slow"]

    df["rsi"] = rsi(df["close"], 14)
    divs = detect_rsi_divergence(df, df["rsi"], 14)
    macd_df = macd(df["close"], 12, 26, 9)
    df["macd"] = macd_df["macd"]
    df["macd_signal"] = macd_df["signal"]
    df["macd_hist"] = macd_df["hist"]
    df["momentum"] = price_momentum(df["close"], 10)

    df["atr"] = atr(df, 14)
    df["trend_strength"] = trend_strength(df["close"], 20)

    df["volume_spike"] = volume_spike(df["volume"], 20, 1.5)
    df["volume_imbalance"] = volume_imbalance(df["volume"], 20)

    df["vwap"] = vwap(df)
    obv_df = obv(df)
    df["obv"] = obv_df["obv"]
    df["obv_ema"] = obv_df["obv_ema"]
    poc = volume_profile_poc(df, 50)
    bb_df = bb_width(df["close"], 20)
    df["bb_width"] = bb_df["width"]
    df["bb_zscore"] = bb_df["zscore"]
    macd_divs = detect_macd_divergence(df, df["macd_hist"], 14)
    df["roc_price"] = roc(df["close"], 10)
    # momentum can be 0 or small, so fillna/replace to 0 might be needed inside roc
    df["roc_momentum"] = roc(df["momentum"], 10)
    
    last = df.iloc[-1]
    features: Dict[str, float] = {
        "ema_slope": float(last["ema_slope"]) if pd.notna(last["ema_slope"]) else 0.0,
        "ma_cross": float(last["ma_cross"]),
        "rsi": float(last["rsi"]) if pd.notna(last["rsi"]) else 50.0,
        "macd_hist": float(last["macd_hist"]) if pd.notna(last["macd_hist"]) else 0.0,
        "momentum": float(last["momentum"]) if pd.notna(last["momentum"]) else 0.0,
        "atr": float(last["atr"]) if pd.notna(last["atr"]) else 0.0,
        "trend_strength": float(last["trend_strength"]) if pd.notna(last["trend_strength"]) else 0.0,
        "volume_spike": float(last["volume_spike"]),
        "volume_imbalance": float(last["volume_imbalance"]) if pd.notna(last["volume_imbalance"]) else 0.0,
        "bullish_divergence": float(divs["bullish"]),
        "bearish_divergence": float(divs["bearish"]),
        "rsi_bullish_hidden": float(divs["bullish_hidden"]),
        "rsi_bearish_hidden": float(divs["bearish_hidden"]),
        "vwap": float(last["vwap"]) if pd.notna(last["vwap"]) else 0.0,
        "obv": float(last["obv"]) if pd.notna(last["obv"]) else 0.0,
        "obv_ema": float(last["obv_ema"]) if pd.notna(last["obv_ema"]) else 0.0,
        "poc": float(poc),
        "bb_width": float(last["bb_width"]) if pd.notna(last["bb_width"]) else 0.0,
        "bb_zscore": float(last["bb_zscore"]) if pd.notna(last["bb_zscore"]) else 0.0,
        "macd_bullish_div": float(macd_divs["bullish"]),
        "macd_bearish_div": float(macd_divs["bearish"]),
        "roc_price": float(last["roc_price"]) if pd.notna(last["roc_price"]) else 0.0,
        "roc_momentum": float(last["roc_momentum"]) if pd.notna(last["roc_momentum"]) else 0.0,
    }

    logger.info("Generated features")
    return df, features
