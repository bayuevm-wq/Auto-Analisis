from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List

from report_engine.analysis_report import AnalysisReport

from .okx_client import OkxClient, OkxConfig

logger = logging.getLogger("ai-trading-analysis-agent.okx")

_QUOTE_SUFFIXES: List[str] = ["USDT", "USDC", "USD", "BTC", "ETH"]


def _derive_inst_id(pair: str) -> str:
    symbol = pair.strip()
    if ":" in symbol:
        symbol = symbol.split(":", 1)[1]
    symbol = symbol.replace("/", "").replace("-", "")
    for quote in _QUOTE_SUFFIXES:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            base = symbol[:-len(quote)]
            return f"{base}-{quote}"
    return symbol


def _parse_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return None


def _resolve_order_size(cfg: OkxConfig, entry_price: float | None) -> float | None:
    if cfg.order_notional is not None and cfg.order_notional > 0:
        if entry_price is None or entry_price <= 0:
            return None
        size = cfg.order_notional / float(entry_price)
        return size
    if cfg.order_size is not None and cfg.order_size > 0:
        return cfg.order_size
    return None


def _resolve_pos_side(cfg: OkxConfig, side_key: str) -> str | None:
    if cfg.pos_side is None:
        return None
    pos_side = cfg.pos_side.strip().lower()
    if pos_side == "auto":
        return side_key
    if pos_side in {"long", "short"}:
        return pos_side
    return None


def _build_okx_config(cfg: Dict[str, Any], pair: str) -> OkxConfig | None:
    okx_cfg = cfg.get("okx") or {}
    if not okx_cfg.get("enable", False):
        return None

    api_key = okx_cfg.get("api_key") or os.getenv("OKX_API_KEY", "")
    api_secret = okx_cfg.get("api_secret") or os.getenv("OKX_API_SECRET", "")
    passphrase = okx_cfg.get("passphrase") or os.getenv("OKX_PASSPHRASE", "")
    if not api_key or not api_secret or not passphrase:
        logger.warning("OKX enabled but missing credentials; skipping submit.")
        return None

    mode = (okx_cfg.get("mode") or "").strip().lower()
    simulated = okx_cfg.get("simulated")
    if simulated is None:
        simulated = False if mode == "live" else True

    trade_mode = okx_cfg.get("trade_mode", "cash")
    order_size = _parse_optional_float(okx_cfg.get("order_size") or os.getenv("OKX_ORDER_SIZE"))
    order_notional = _parse_optional_float(okx_cfg.get("order_notional") or os.getenv("OKX_ORDER_NOTIONAL"))
    inst_id = okx_cfg.get("inst_id") or _derive_inst_id(pair)
    submit = okx_cfg.get("submit", "preferred")
    pos_side = okx_cfg.get("pos_side") or None
    leverage = _parse_optional_float(okx_cfg.get("leverage") or os.getenv("OKX_LEVERAGE"))
    auto_leverage = _parse_optional_bool(okx_cfg.get("auto_leverage", False))
    mgn_mode = (okx_cfg.get("mgn_mode") or "").strip().lower() or None
    base_url = okx_cfg.get("base_url", "https://okx.com")
    ssl_verify = _parse_optional_bool(okx_cfg.get("ssl_verify"))

    if mgn_mode is None and trade_mode in {"cross", "isolated"}:
        mgn_mode = trade_mode

    return OkxConfig(
        api_key=api_key,
        api_secret=api_secret,
        passphrase=passphrase,
        base_url=base_url,
        simulated=bool(simulated),
        trade_mode=trade_mode,
        order_size=order_size,
        order_notional=order_notional,
        inst_id=inst_id,
        submit=submit,
        pos_side=pos_side,
        leverage=leverage,
        auto_leverage=True if auto_leverage is None else auto_leverage,
        mgn_mode=mgn_mode,
        ssl_verify=True if ssl_verify is None else ssl_verify,
    )


def submit_okx_signal(report: AnalysisReport, pair: str, cfg: Dict[str, Any]) -> None:
    okx_config = _build_okx_config(cfg, pair)
    if okx_config is None:
        return

    setup = report.trade_setup
    if "long" not in setup or "short" not in setup:
        logger.warning("Trade setup missing long/short; skipping OKX submit.")
        return

    if (okx_config.order_size is None or okx_config.order_size <= 0) and (
        okx_config.order_notional is None or okx_config.order_notional <= 0
    ):
        logger.warning("OKX order_size/order_notional not set; skipping submit.")
        return

    submit_mode = (okx_config.submit or "preferred").strip().lower()
    if submit_mode == "both":
        sides = ["long", "short"]
    elif submit_mode in {"long", "short"}:
        sides = [submit_mode]
    else:
        preferred = setup.get("preferred")
        if preferred in {"long", "short"}:
            sides = [preferred]
        else:
            logger.info("OKX submit skipped: preferred side is neutral.")
            return

    client = OkxClient(okx_config)

    for side_key in sides:
        side_setup = setup.get(side_key, {})
        entry_price = side_setup.get("entry")
        if entry_price is None:
            logger.warning("OKX submit skipped: missing entry for %s.", side_key)
            continue

        size = _resolve_order_size(okx_config, float(entry_price))
        if size is None or size <= 0:
            logger.warning("OKX submit skipped: size not resolvable for %s.", side_key)
            continue

        pos_side = _resolve_pos_side(okx_config, side_key)
        inst_id = okx_config.inst_id or _derive_inst_id(pair)
        tp_price = side_setup.get("take_profit")
        sl_price = side_setup.get("stop_loss")

        calc_leverage = okx_config.leverage
        if okx_config.auto_leverage and entry_price is not None and sl_price is not None:
            ep = float(entry_price)
            sl = float(sl_price)
            if ep > 0:
                dist = abs(ep - sl) / ep
                if dist > 0:
                    calc_leverage = float(int(1.0 / dist))
                    # Cap auto leverage to user's configured leverage to avoid OKX max limits
                    max_lev = okx_config.leverage if (okx_config.leverage and okx_config.leverage > 0) else 50.0
                    calc_leverage = min(calc_leverage, max_lev)
                    # Safety: floor at 1x and cap at 20x when SL is extremely tight
                    calc_leverage = max(1.0, calc_leverage)
                    if dist < 0.005:  # SL < 0.5% — likely too tight
                        calc_leverage = min(calc_leverage, 20.0)
                        logger.warning("SL distance too tight (%.2f%%), capping auto-leverage to %.0fx", dist * 100, calc_leverage)
                    logger.info("Auto-leverage calculated: %sx (SL distance: %.2f%%)", calc_leverage, dist*100)

        if calc_leverage is not None and calc_leverage > 0:
            if okx_config.trade_mode == "cash":
                logger.info("OKX leverage skipped: trade_mode is cash.")
            elif not okx_config.mgn_mode:
                logger.warning("OKX leverage skipped: mgn_mode not set.")
            else:
                lev_resp = client.set_leverage(
                    inst_id=inst_id,
                    leverage=calc_leverage,
                    mgn_mode=okx_config.mgn_mode,
                    pos_side=pos_side,
                )
                if lev_resp and lev_resp.get("code") != "0":
                    logger.warning("OKX set_leverage failed: %s", lev_resp)

        side = "buy" if side_key == "long" else "sell"
        client_id = f"signal{side_key}{int(time.time())}"
        response = client.place_limit_order(
            inst_id=inst_id,
            side=side,
            size=size,
            price=float(entry_price),
            trade_mode=okx_config.trade_mode,
            pos_side=pos_side,
            client_id=client_id,
            tp_price=float(tp_price) if tp_price is not None else None,
            sl_price=float(sl_price) if sl_price is not None else None,
        )
        if response is None:
            logger.warning("OKX submit failed for %s.", side_key)
        else:
            logger.info("OKX submit response for %s: %s", side_key, response)

