from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Any


@dataclass
class AnalysisReport:
    chart_context: Dict[str, Any]
    macro_context: Dict[str, Any]
    multi_timeframe_context: Dict[str, Any]
    market_structure: Dict[str, Any]
    wyckoff_phase: Dict[str, Any]
    supply_demand: List[Dict[str, Any]]
    volume_analysis: Dict[str, Any]
    volatility: Dict[str, Any]
    liquidity_analysis: Dict[str, Any]
    liquidity_map: Dict[str, Any]
    smc: Dict[str, Any]
    premium_discount: Dict[str, Any]
    key_levels: List[Dict[str, Any]]
    pullback_zones: Dict[str, Any]
    momentum: Dict[str, Any]
    probability_model: Dict[str, Any]
    market_bias: Dict[str, Any]
    trade_setup: Dict[str, Any]
    entry_trigger: Dict[str, Any]
    analysis_summary: Dict[str, str]
    executive_summary: Dict[str, str]
    trade_management: Dict[str, str]
    confidence_metrics: Dict[str, str]
    specific_triggers: Dict[str, str]
    backtest: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return self.__dict__
