from __future__ import annotations

from typing import Dict


def score_to_probabilities(score: float) -> Dict[str, float]:
    """Map score [-1, 1] to bullish/bearish/neutral probabilities.

    Multiplier 0.42 gives effective output range ~12%-85%, making
    conviction thresholds (55%, 65%) meaningfully reachable.
    """
    bull = 0.5 + (score * 0.42)
    bear = 0.5 - (score * 0.42)
    neutral = max(0.03, 0.15 - abs(score) * 0.12)

    total = bull + bear + neutral
    bull /= total
    bear /= total
    neutral /= total

    return {
        "bullish": round(bull * 100, 2),
        "bearish": round(bear * 100, 2),
        "neutral": round(neutral * 100, 2),
    }
