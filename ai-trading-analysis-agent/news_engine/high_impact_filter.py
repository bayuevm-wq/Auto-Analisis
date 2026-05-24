"""
High-Impact Economic Event Filter
==================================
Blocks trade entries when a major macro event (FOMC, CPI, NFP, etc.)
is scheduled within a configurable safety window (default 2 hours).

The calendar is maintained as a hardcoded list that should be updated
monthly. An optional live-fetch fallback can be added later.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

logger = logging.getLogger("news_engine.high_impact_filter")

# ── Hardcoded High-Impact Event Calendar (Update Monthly) ─────────────
# Format: (month, day, hour_utc, event_name)
# Source: ForexFactory / Investing.com economic calendar
# These are US-centric events that move BTC/Crypto the most.
HIGH_IMPACT_EVENTS_2026: List[tuple] = [
    # ── January 2026 ──
    (1, 10, 13, "NFP (Non-Farm Payrolls)"),
    (1, 14, 13, "CPI (Consumer Price Index)"),
    (1, 29, 19, "FOMC Rate Decision"),
    # ── February 2026 ──
    (2, 7, 13, "NFP (Non-Farm Payrolls)"),
    (2, 12, 13, "CPI (Consumer Price Index)"),
    (2, 27, 13, "Core PCE Price Index"),
    # ── March 2026 ──
    (3, 6, 13, "NFP (Non-Farm Payrolls)"),
    (3, 11, 12, "CPI (Consumer Price Index)"),
    (3, 18, 18, "FOMC Rate Decision"),
    (3, 26, 12, "GDP Final"),
    # ── April 2026 ──
    (4, 3, 12, "NFP (Non-Farm Payrolls)"),
    (4, 10, 12, "CPI (Consumer Price Index)"),
    (4, 15, 12, "Retail Sales"),
    (4, 30, 12, "Core PCE Price Index"),
    # ── May 2026 ──
    (5, 1, 12, "NFP (Non-Farm Payrolls)"),
    (5, 6, 18, "FOMC Rate Decision"),
    (5, 13, 12, "CPI (Consumer Price Index)"),
    (5, 29, 12, "GDP Preliminary"),
    # ── June 2026 ──
    (6, 5, 12, "NFP (Non-Farm Payrolls)"),
    (6, 10, 12, "CPI (Consumer Price Index)"),
    (6, 17, 18, "FOMC Rate Decision"),
    (6, 26, 12, "Core PCE Price Index"),
    # ── July 2026 ──
    (7, 2, 12, "NFP (Non-Farm Payrolls)"),
    (7, 14, 12, "CPI (Consumer Price Index)"),
    (7, 29, 18, "FOMC Rate Decision"),
    (7, 31, 12, "Core PCE Price Index"),
    # ── August 2026 ──
    (8, 7, 12, "NFP (Non-Farm Payrolls)"),
    (8, 12, 12, "CPI (Consumer Price Index)"),
    (8, 28, 12, "GDP Second Estimate"),
    # ── September 2026 ──
    (9, 4, 12, "NFP (Non-Farm Payrolls)"),
    (9, 10, 12, "CPI (Consumer Price Index)"),
    (9, 16, 18, "FOMC Rate Decision"),
    (9, 25, 12, "Core PCE Price Index"),
    # ── October 2026 ──
    (10, 2, 12, "NFP (Non-Farm Payrolls)"),
    (10, 13, 12, "CPI (Consumer Price Index)"),
    (10, 29, 12, "GDP Advance"),
    (10, 30, 12, "Core PCE Price Index"),
    # ── November 2026 ──
    (11, 4, 18, "FOMC Rate Decision"),
    (11, 6, 13, "NFP (Non-Farm Payrolls)"),
    (11, 10, 13, "CPI (Consumer Price Index)"),
    (11, 25, 13, "GDP Second Estimate"),
    # ── December 2026 ──
    (12, 4, 13, "NFP (Non-Farm Payrolls)"),
    (12, 10, 13, "CPI (Consumer Price Index)"),
    (12, 16, 19, "FOMC Rate Decision"),
    (12, 23, 13, "Core PCE Price Index"),
]

# Safety window: block entries this many hours before AND after the event
PRE_EVENT_BLOCK_HOURS = 2.0
POST_EVENT_BLOCK_HOURS = 0.5


def _build_event_datetimes(year: int = None) -> List[Dict[str, Any]]:
    """Convert hardcoded tuples into datetime objects."""
    if year is None:
        year = datetime.now(timezone.utc).year

    events = []
    event_list = HIGH_IMPACT_EVENTS_2026

    for month, day, hour_utc, name in event_list:
        try:
            dt = datetime(year, month, day, hour_utc, 0, 0, tzinfo=timezone.utc)
            events.append({"datetime": dt, "name": name})
        except ValueError:
            continue
    return events


def check_high_impact_window(
    pre_hours: float = PRE_EVENT_BLOCK_HOURS,
    post_hours: float = POST_EVENT_BLOCK_HOURS,
) -> Dict[str, Any]:
    """
    Check if we are within a high-impact event window.

    Returns:
        {
            "blocked": bool,
            "event_name": str or None,
            "hours_until": float or None,   # negative = event already passed
            "status": str                    # human-readable status line
        }
    """
    now = datetime.now(timezone.utc)
    events = _build_event_datetimes(now.year)

    nearest_event = None
    nearest_delta_hours = float("inf")

    for event in events:
        delta = (event["datetime"] - now).total_seconds() / 3600.0
        if abs(delta) < abs(nearest_delta_hours):
            nearest_delta_hours = delta
            nearest_event = event

    if nearest_event is None:
        return {
            "blocked": False,
            "event_name": None,
            "hours_until": None,
            "status": "✅ No scheduled high-impact events found",
        }

    event_name = nearest_event["name"]
    hours_until = nearest_delta_hours

    # Block zone: [event - pre_hours, event + post_hours]
    if -post_hours <= hours_until <= pre_hours:
        if hours_until >= 0:
            status = f"🔴 BLOCKED — {event_name} in {hours_until:.1f}h (No new entries)"
        else:
            status = f"🔴 BLOCKED — {event_name} released {abs(hours_until):.1f}h ago (Wait for dust to settle)"
        return {
            "blocked": True,
            "event_name": event_name,
            "hours_until": round(hours_until, 2),
            "status": status,
        }

    # Warning zone: within 6 hours
    if 0 < hours_until <= 6.0:
        status = f"🟡 WARNING — {event_name} in {hours_until:.1f}h (Reduce size)"
        return {
            "blocked": False,
            "event_name": event_name,
            "hours_until": round(hours_until, 2),
            "status": status,
        }

    # Clear
    if hours_until > 0:
        status = f"✅ Clear — Next event: {event_name} in {hours_until:.0f}h"
    else:
        status = f"✅ Clear — Last event: {event_name} ({abs(hours_until):.0f}h ago)"

    return {
        "blocked": False,
        "event_name": event_name,
        "hours_until": round(hours_until, 2),
        "status": status,
    }


if __name__ == "__main__":
    result = check_high_impact_window()
    print(f"Blocked: {result['blocked']}")
    print(f"Status:  {result['status']}")
