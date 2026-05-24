from __future__ import annotations

from typing import Dict, List

import pandas as pd

from feature_engine.liquidity_features import (
    LiquidityEvent,
    LiquidityPool,
    detect_equal_highs_lows,
    detect_liquidity_sweep,
    distance_to_liquidity,
)


def analyze_liquidity(df: pd.DataFrame) -> Dict[str, object]:
    buy_side, sell_side = detect_equal_highs_lows(df)
    sweeps: List[LiquidityEvent] = detect_liquidity_sweep(df, buy_side, sell_side)

    buy_distance = distance_to_liquidity(df, buy_side)
    sell_distance = distance_to_liquidity(df, sell_side)

    return {
        "buy_side_pools": buy_side,
        "sell_side_pools": sell_side,
        "sweeps": sweeps,
        "distance_to_buy_liquidity": buy_distance,
        "distance_to_sell_liquidity": sell_distance,
    }
