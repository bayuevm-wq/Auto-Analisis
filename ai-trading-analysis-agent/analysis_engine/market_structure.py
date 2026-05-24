from __future__ import annotations

from typing import Dict

import pandas as pd

from feature_engine.structure_features import classify_structure


def analyze_market_structure(df: pd.DataFrame) -> Dict[str, object]:
    state = classify_structure(df)
    return {
        "trend": state.trend,
        "last_swing_high": state.last_swing_high,
        "last_swing_low": state.last_swing_low,
        "bos": state.bos,
        "choch": state.choch,
    }
