from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import pandas as pd


@dataclass
class LiquidityPool:
    side: str
    level: float
    strength: int


@dataclass
class LiquidityEvent:
    side: str
    level: float
    swept: bool


def _within_tolerance(a: float, b: float, tolerance: float) -> bool:
    if a == 0:
        return False
    return abs(a - b) / a <= tolerance


def detect_equal_highs_lows(df: pd.DataFrame, tolerance: float = 0.002) -> Tuple[List[LiquidityPool], List[LiquidityPool]]:
    highs = df["high"].values
    lows = df["low"].values

    buy_side: List[LiquidityPool] = []
    sell_side: List[LiquidityPool] = []

    # Simple scan for recent equal highs/lows
    for i in range(2, len(df) - 2):
        if _within_tolerance(highs[i], highs[i - 2], tolerance):
            buy_side.append(LiquidityPool(side="buy", level=float(highs[i]), strength=2))
        if _within_tolerance(lows[i], lows[i - 2], tolerance):
            sell_side.append(LiquidityPool(side="sell", level=float(lows[i]), strength=2))

    return buy_side, sell_side


def detect_liquidity_sweep(
    df: pd.DataFrame,
    buy_side: List[LiquidityPool],
    sell_side: List[LiquidityPool],
) -> List[LiquidityEvent]:
    events: List[LiquidityEvent] = []
    last = df.iloc[-1]
    for pool in buy_side:
        if last["high"] > pool.level and last["close"] < pool.level:
            events.append(LiquidityEvent(side="buy", level=pool.level, swept=True))
    for pool in sell_side:
        if last["low"] < pool.level and last["close"] > pool.level:
            events.append(LiquidityEvent(side="sell", level=pool.level, swept=True))
    return events


def distance_to_liquidity(df: pd.DataFrame, pools: List[LiquidityPool]) -> Optional[float]:
    if not pools:
        return None
    last_price = float(df["close"].iloc[-1])
    distances = [abs(last_price - pool.level) for pool in pools]
    return float(min(distances))
