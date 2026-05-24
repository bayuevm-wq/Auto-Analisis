from __future__ import annotations

from typing import Any, Dict, List

from .analysis_report import AnalysisReport


def _fmt_float(value: Any, nd: int = 2) -> str:
    if value is None:
        return "n/a"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)

    if nd != 2:
        return f"{num:.{nd}f}"

    abs_num = abs(num)
    if abs_num >= 1000:
        precision = 2
    elif abs_num >= 1:
        precision = 4
    elif abs_num >= 0.1:
        precision = 5
    elif abs_num >= 0.01:
        precision = 6
    elif abs_num >= 0.0001:
        precision = 7
    elif abs_num >= 0.000001:
        precision = 8
    else:
        precision = 10
    
    formatted = f"{num:.{precision}f}"
    if '.' in formatted and formatted.endswith('0'):
        formatted = formatted.rstrip('0').rstrip('.')
        if not formatted:
            formatted = "0"
            
    # For trailing padding on integer-like numbers in reports
    if '.' not in formatted and abs_num < 1000:
        formatted += ".00"
        
    return formatted


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{_fmt_float(value, 2)}%"


def _format_zone(zone: Dict[str, Any]) -> str:
    return f"{zone['type']} {_fmt_float(zone['low'])}-{_fmt_float(zone['high'])}"


def _format_levels(levels: List[float]) -> str:
    return ", ".join(_fmt_float(lvl) for lvl in levels) if levels else "n/a"


def _format_zone_list(zones: List[Dict[str, Any]], limit: int = 3) -> str:
    if not zones:
        return "n/a"
    tail = zones[-limit:]
    return "; ".join(_format_zone(z) for z in tail)


def _section(title: str, lines: List[str], out: List[str]) -> None:
    out.append(f"== {title} ==")
    out.extend(lines)
    out.append("")


def format_report(report: AnalysisReport) -> str:
    sd_zones = report.supply_demand
    demand = [z for z in sd_zones if z["type"] == "demand"]
    supply = [z for z in sd_zones if z["type"] == "supply"]

    text: List[str] = []
    
    es = getattr(report, "executive_summary", {})
    conf = getattr(report, "confidence_metrics", {})
    setup = report.trade_setup
    mgmt = getattr(report, "trade_management", {})
    trigs = getattr(report, "specific_triggers", {})
    
    # 0. TRADING ALERT BANNER
    text.append(f"## 🚨 TRADING ALERT: {report.chart_context['pair']} {report.chart_context['timeframe'].upper()}")
    
    action = es.get("action", "STANDBY")
    final_conv = conf.get("final_conviction", "Unknown") if conf else "Unknown"
    
    status_icon = "⚠️ STANDBY"
    if "ENTER" in action: status_icon = "🟢 ACTIVE"
    elif "RECALIBRATING" in action: status_icon = "🛑 RECALIBRATING (Data Outdated)"
    elif "RISK OFF" in action: status_icon = "⚠️ RISK OFF (Macro Extreme)"
    elif "NO TRADE" in action or "CASH ONLY" in action or "STANDBY" in action: status_icon = "🛑 HALTED"
    
    if "RECALIBRATING" in action or "RISK OFF" in action:
        text.append(f"**STATUS:** {status_icon}")
    else:
        text.append(f"**STATUS:** {status_icon} ({action})")
    
    is_expired = False
    if conf and ("EXPIRED" in conf.get("structure_age", "") or "Data Outdated" in action or "RISK OFF" in action or "Macro Extreme" in action):
        is_expired = True
        text.append(f"**FINAL CONVICTION:** 0.0% (Data Expired / High Risk Macro)")
    else:
        text.append(f"**FINAL CONVICTION:** {final_conv}")

    fallback_warning = es.get("data_fallback_warning")
    if fallback_warning:
        text.append(f"**⚠️ DATA SOURCE WARNING:** {fallback_warning}")
        
    text.append("\n---")
    
    # 1. TRADE SETUP
    if not is_expired:
        if "long" in setup or "short" in setup:
            long_setup = setup.get("long", {})
            short_setup = setup.get("short", {})
            preferred = setup.get("preferred", "n/a")
            preferred_prob = None
            if preferred == "long":
                preferred_prob = long_setup.get("probability")
            elif preferred == "short":
                preferred_prob = short_setup.get("probability")
            preferred_line = (
                f"Preferred: {preferred} ({_fmt_pct(preferred_prob)})"
                if preferred in {"long", "short"}
                else f"Preferred: {preferred}"
            )
            _section(
                "🚀 TRADE SETUP",
                [
                    f"Last Price: {_fmt_float(setup.get('last_price'))}",
                    preferred_line,
                    f"Risk Allocation: {setup.get('risk_alloc_str', 'N/A')}",
                    "",
                    "Long (Limit):",
                    f"Entry: {_fmt_float(long_setup.get('entry'))}",
                    f"SL: {_fmt_float(long_setup.get('stop_loss'))}",
                    f"TP1: {_fmt_float(long_setup.get('tp1'))}",
                    f"TP2: {_fmt_float(long_setup.get('tp2'))}",
                    f"TP3: {_fmt_float(long_setup.get('tp3'))}",
                    f"RR (TP2): {_fmt_float(long_setup.get('rr'))}",
                    f"Prob: {_fmt_pct(long_setup.get('probability'))}",
                    f"Risk (Max Pos): {_fmt_float(long_setup.get('position_size_pct'))}%",
                    "",
                    "Short (Limit):",
                    f"Entry: {_fmt_float(short_setup.get('entry'))}",
                    f"SL: {_fmt_float(short_setup.get('stop_loss'))}",
                    f"TP1: {_fmt_float(short_setup.get('tp1'))}",
                    f"TP2: {_fmt_float(short_setup.get('tp2'))}",
                    f"TP3: {_fmt_float(short_setup.get('tp3'))}",
                    f"RR (TP2): {_fmt_float(short_setup.get('rr'))}",
                    f"Prob: {_fmt_pct(short_setup.get('probability'))}",
                    f"Risk (Max Pos): {_fmt_float(short_setup.get('position_size_pct'))}%",
                ],
                text,
            )
        else:
            tp1 = setup.get("tp1", setup.get("take_profit"))
            tp2 = setup.get("tp2", setup.get("take_profit"))
            tp3 = setup.get("tp3", setup.get("take_profit"))
            _section(
                "🚀 TRADE SETUP",
                [
                    f"Entry: {_fmt_float(setup['entry'])}",
                    f"SL: {_fmt_float(setup['stop_loss'])}",
                    f"TP1: {_fmt_float(tp1)}",
                    f"TP2: {_fmt_float(tp2)}",
                    f"TP3: {_fmt_float(tp3)}",
                    f"RR (TP2): {_fmt_float(setup['rr'])}",
                ],
                text,
            )
    # 1. RISK DASHBOARD
    _section(
        "🛡️ RISK DASHBOARD",
        [
            f"* **VIX:** {es.get('vix_str', 'N/A')}",
            f"* **DXY:** {es.get('dxy_str', 'N/A')}",
            f"* **SPX Correlation:** {es.get('spx_str', 'N/A')}",
            f"* **News Filter:** {es.get('news_filter', 'N/A')}"
        ],
        text
    )
    
    # 2. TRADE PLAN
    if is_expired:
        _section(
            "📈 TRADE PLAN (RE-EVALUATING)",
            [
                f"* **Bias:** {es.get('bias', 'Neutral')}",
                f"* **Status:** Data Expired or Macro Extrema detected. Setup invalidated.",
            ],
            text
        )
    else:
        preferred_side = setup.get("preferred", "neutral") if setup else "neutral"
        if preferred_side == "long":
            trigger_line = trigs.get('long', '').replace('\\n', ' + ')
        elif preferred_side == "short":
            trigger_line = trigs.get('short', '').replace('\\n', ' + ')
        else:
            trigger_line = "N/A"
            
        invalid_line = mgmt.get("long_invalidation", "") if preferred_side == "long" else mgmt.get("short_invalidation", "")
        
        plan_bullets = [
            f"* **Bias:** {es.get('bias', 'Neutral')}",
        ]
        
        advice = es.get("execution_advice")
        if advice:
            plan_bullets.append(f"* **Eksekusi:** {advice}")
            
        plan_bullets.extend([
            f"* **Trigger:** {trigger_line}",
            f"* **Invalidation:** {invalid_line}",
        ])
        
        _section(
            "📈 TRADE PLAN",
            plan_bullets,
            text
        )
        
    # 3. CRITICAL NOTES
    notes = []
    _note_idx = 1
    if conf:
        notes.append(f"{_note_idx}. **Structure Age:** {conf.get('structure_age', 'Unknown')}")
        _note_idx += 1
    
    vol_poc = report.volume_analysis.get('poc', 0)
    last_price = setup.get('last_price', 0) if setup else 0
    if vol_poc > 0:
        poc_status = "Bearish zone" if last_price < vol_poc else "Bullish zone"
        notes.append(f"{_note_idx}. **Volume POC:** Price vs POC (${vol_poc:.2f}) -> {poc_status}")
        _note_idx += 1
    
    if report.analysis_summary.get("volatility_squeeze"):
        notes.append(f"{_note_idx}. **⚠️ Volatility Squeeze:** BB Width sangat rendah — breakout imminent. Tunggu konfirmasi arah sebelum entry.")
        _note_idx += 1
    
    if report.analysis_summary.get("rsi_warning"):
        notes.append(f"{_note_idx}. **{report.analysis_summary['rsi_warning']}**")
        _note_idx += 1
    
    if report.analysis_summary.get("div_conflict"):
        notes.append(f"{_note_idx}. **{report.analysis_summary['div_conflict']}**")
        _note_idx += 1
    
    if report.analysis_summary.get("exhaustion"):
        notes.append(f"{_note_idx}. **{report.analysis_summary['exhaustion']}**")
        _note_idx += 1
    
    if report.analysis_summary.get("wyckoff_htf_conflict"):
        notes.append(f"{_note_idx}. **{report.analysis_summary['wyckoff_htf_conflict']}**")
        _note_idx += 1
    
    # Pre-penalty breakdown visibility — always show if any penalties exist
    if conf and conf.get("penalty_breakdown") and conf.get("penalty_breakdown") != "None":
        notes.append(f"{_note_idx}. **Penalty Breakdown:** {conf.get('penalty_breakdown')}")
        _note_idx += 1
        
    _section(
        "🔍 CRITICAL NOTES",
        notes,
        text
    )

    _section(
        "1 Chart Context",
        [
            f"Pair: {report.chart_context['pair']}",
            f"Timeframe: {report.chart_context['timeframe']}",
            f"Source: {report.chart_context['source']}",
            f"Style: {report.chart_context.get('style', 'n/a')}",
        ],
        text,
    )

    _section(
        "2 Multi Timeframe Context",
        [
            report.multi_timeframe_context.get("summary", "n/a"),
            f"HTF Trend: {report.multi_timeframe_context.get('htf_trend', 'unknown')}",
        ],
        text,
    )
    
    dxy_line = f"DXY trend: {es.get('dxy_str', 'N/A')}"
    vix_line = f"VIX regime: {es.get('vix_str', 'N/A')}"
    corr_line = f"Correlation: {es.get('corr_str', 'N/A')}"

    _section(
        "3 Macro Context Enhancement",
        [dxy_line, vix_line, corr_line],
        text,
    )

    _section(
        "3 Market Structure",
        [
            f"Trend: {report.market_structure['trend']}",
            f"BOS: {report.market_structure['bos']} | CHOCH: {report.market_structure['choch']}",
        ],
        text,
    )

    _section(
        "4 Wyckoff Phase",
        [
            f"Phase: {report.wyckoff_phase['phase']}",
            f"Signals: {', '.join(report.wyckoff_phase['signals']) or 'none'}",
        ],
        text,
    )

    _section(
        "5 Supply and Demand",
        [
            f"Supply zones: {_format_zone_list(supply)}",
            f"Demand zones: {_format_zone_list(demand)}",
        ],
        text,
    )

    vol_lines = [
        f"VWAP: {_fmt_float(report.volume_analysis.get('vwap'))} | {report.analysis_summary.get('vwap', '')}",
        f"OBV: {_fmt_float(report.volume_analysis.get('obv'))} | {report.analysis_summary.get('obv', '')}",
        f"Volume Profile POC: {_fmt_float(report.volume_analysis.get('poc'))} | {report.analysis_summary.get('poc', '')}",
    ]
    if report.analysis_summary.get('volume_conflict'):
        vol_lines.append(report.analysis_summary['volume_conflict'])

    _section(
        "6 Volume Analysis",
        vol_lines,
        text,
    )

    _section(
        "7 Volatility Tracking",
        [
            f"ATR: {_fmt_float(report.volatility.get('atr', 0.0), 4)}",
            f"Bollinger Band Width: {_fmt_float(report.volatility.get('bb_width', 0.0), 4)} | {report.analysis_summary.get('bb_width', '')}",
        ],
        text,
    )

    _section(
        "8 Liquidity Analysis",
        [
            f"Buy-side pools: {len(report.liquidity_analysis['buy_side_pools'])}",
            f"Sell-side pools: {len(report.liquidity_analysis['sell_side_pools'])}",
            f"Sweeps: {len(report.liquidity_analysis['sweeps'])}",
        ],
        text,
    )

    _section(
        "9 Liquidity Map",
        [
            f"Distance to buy liquidity: {_fmt_float(report.liquidity_analysis['distance_to_buy_liquidity'])}",
            f"Distance to sell liquidity: {_fmt_float(report.liquidity_analysis['distance_to_sell_liquidity'])}",
        ],
        text,
    )

    _section(
        "10 Smart Money Concepts",
        [
            f"Order blocks: {len(report.smc['order_blocks'])}",
            f"FVG: {len(report.smc['fvg'])}",
            f"FVG CE Triggers: {len(report.smc.get('fvg_ce', []))}",
        ],
        text,
    )

    _section(
        "11 Premium / Discount",
        [
            f"Premium: {_fmt_float(report.premium_discount['premium'])}",
            f"Discount: {_fmt_float(report.premium_discount['discount'])}",
        ],
        text,
    )

    kl_lines = []
    for lvl in report.key_levels:
        kl_lines.append(f"• ${_fmt_float(lvl['price'])} - {lvl['reasons']}")
        
    _section(
        "12 Key Levels to Watch (Top Confluences)",
        kl_lines if kl_lines else ["None"],
        text,
    )

    _section(
        "13 Pullback Zones",
        [_format_levels(report.pullback_zones.get("zones", []))],
        text,
    )

    rsi_div_str = (
        "Bullish Hidden" if bool(report.momentum.get("rsi_bullish_hidden")) else
        "Bearish Hidden" if bool(report.momentum.get("rsi_bearish_hidden")) else
        "Bullish" if bool(report.momentum.get("bullish_divergence")) else
        "Bearish" if bool(report.momentum.get("bearish_divergence")) else "None"
    )
    macd_div_str = (
        "Bullish" if bool(report.momentum.get("macd_bullish_div")) else
        "Bearish" if bool(report.momentum.get("macd_bearish_div")) else "None"
    )
    
    roc_price = report.momentum.get('roc_price', 0.0)
    roc_mom = report.momentum.get('roc_momentum', 0.0)
    if roc_price > 0 and roc_mom < 0:
        mom_diag = "Bullish Exhaustion (Price up, Momentum down)"
    elif roc_price < 0 and roc_mom > 0:
        mom_diag = "Bearish Exhaustion (Price down, Momentum up)"
    else:
        mom_diag = "Aligned"

    _section(
        "14 Momentum Diagnostics",
        [
            f"RSI: {_fmt_float(report.momentum['rsi'])} | Divergence: {rsi_div_str}",
            f"MACD Hist: {_fmt_float(report.momentum['macd_hist'], 4)} | Divergence: {macd_div_str}",
            f"Momentum: {_fmt_float(report.momentum['momentum'], 4)}",
            f"Price ROC: {_fmt_float(report.momentum.get('roc_price', 0.0), 2)}% | Mom ROC: {_fmt_float(report.momentum.get('roc_momentum', 0.0), 2)}% | Exhaustion Scan: {mom_diag}",
        ],
        text,
    )

    if is_expired:
        _section(
            "15 Probability Model",
            ["[SUSPENDED DUE TO OUTDATED/EXTREME CONDITIONS]"],
            text,
        )
    else:
        _bull = report.probability_model['bullish']
        _bear = report.probability_model['bearish']
        _neut = report.probability_model['neutral']
        _total_prob = _bull + _bear + _neut
        _uncertainty = max(0.0, 100.0 - _total_prob)
        
        prob_lines = [
            f"Bullish: {_bull:.2f}%",
            f"Bearish: {_bear:.2f}%",
            f"Neutral: {_neut:.2f}%",
        ]
        if _uncertainty > 0.5:  # Only show if meaningful gap exists
            prob_lines.append(f"Penalty Absorbed: {_uncertainty:.1f}% (conviction reduced by post-hoc penalties)")
        
        _section(
            "15 Probability Model",
            prob_lines,
            text,
        )

    _section(
        "16 Market Bias",
        [report.market_bias.get("bias", "n/a")],
        text,
    )


    # Legacy Entry trigger removed, handled in Executive summary Trade Plan

    
    if mgmt and not is_expired:
        _section(
            "18 Trade Management Rules",
            [
                f"Validity: {mgmt.get('validity', '')}",
                f"Structure Age: {mgmt.get('structure_age', '')}",
                f"Long Invalidation: {mgmt.get('long_invalidation', '')}",
                f"Short Invalidation: {mgmt.get('short_invalidation', '')}",
                f"Timeout Rule: {mgmt.get('timeout_rule', '')}",
            ],
            text,
        )

    if conf and not is_expired:
        conf_lines = [
            f"Pre-Penalty Conviction: {conf.get('pre_penalty_conviction', 'N/A')}",
            f"Total Penalties: {conf.get('total_penalties', '0%')}",
            f"Penalty Breakdown: {conf.get('penalty_breakdown', 'None')}",
            f"Base Conviction: {conf.get('base_conviction', '')}",
            f"Decay Adjustment: {conf.get('decay_adj', '')}",
            f"Final Conviction: {conf.get('final_conviction', '')}",
        ]
        _section(
            "19 Confidence Metrics",
            conf_lines,
            text,
        )

    if trigs and not is_expired:
        _section(
            "20 Specific Trigger Conditions",
            [
                "Long Trigger:",
                *trigs.get('long', '').split('\\n'),
                "",
                "Short Trigger:",
                *trigs.get('short', '').split('\\n'),
            ],
            text,
        )

    return "\n".join(text).strip()
