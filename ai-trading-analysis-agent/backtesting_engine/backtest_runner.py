from __future__ import annotations

from typing import Dict

import pandas as pd

from .performance_metrics import compute_metrics
from .strategy_simulator import ema_crossover_strategy


def run_backtest(df: pd.DataFrame) -> Dict[str, float]:
    equity_curve, trades = ema_crossover_strategy(df)
    metrics = compute_metrics(equity_curve, trades)
    return metrics
