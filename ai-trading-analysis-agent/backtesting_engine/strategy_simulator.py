from __future__ import annotations

from typing import Dict, List, Tuple

import pandas as pd


def ema_crossover_strategy(
    df: pd.DataFrame,
    fee_pct: float = 0.001,       # 0.1% round-trip (maker+taker)
    slippage_pct: float = 0.0005, # 0.05% slippage per trade
) -> Tuple[pd.Series, List[Dict[str, float]]]:
    """
    Simple EMA crossover strategy for backtesting.
    Includes fee and slippage deductions for realistic results.
    Returns equity curve and list of trade results.
    """
    cost_per_trade = fee_pct + slippage_pct  # Total friction per side

    position = 0  # 1 long, -1 short, 0 flat
    entry_price = 0.0
    equity = 1.0
    equity_curve = []
    trades: List[Dict[str, float]] = []

    for i in range(1, len(df)):
        row = df.iloc[i]
        signal = 1 if row["ema_fast"] > row["ema_slow"] else -1
        price = float(row["close"])

        if position == 0:
            position = signal
            entry_price = price
            equity *= (1 - cost_per_trade)  # Entry cost
        elif signal != position:
            pnl = (price - entry_price) / entry_price if position == 1 else (entry_price - price) / entry_price
            pnl -= cost_per_trade  # Exit cost
            equity *= 1 + pnl
            trades.append({"pnl": pnl})
            position = signal
            entry_price = price
            equity *= (1 - cost_per_trade)  # Re-entry cost

        equity_curve.append(equity)

    equity_series = pd.Series(equity_curve, index=df.index[1:])
    return equity_series, trades
