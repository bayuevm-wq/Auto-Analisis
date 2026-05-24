from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("ai-trading-analysis-agent.okx")


@dataclass
class OkxConfig:
    api_key: str
    api_secret: str
    passphrase: str
    base_url: str = "https://okx.com"
    simulated: bool = True
    trade_mode: str = "cash"
    order_size: float | None = None
    order_notional: float | None = None
    inst_id: str | None = None
    submit: str = "preferred"
    pos_side: str | None = None
    leverage: float | None = None
    auto_leverage: bool = False
    mgn_mode: str | None = None
    ssl_verify: bool = True


def _iso_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _sign(api_secret: str, timestamp: str, method: str, path: str, body: str) -> str:
    message = f"{timestamp}{method}{path}{body}"
    digest = hmac.new(api_secret.encode(), message.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _ssl_context(verify: bool) -> ssl.SSLContext | None:
    if verify:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class OkxClient:
    def __init__(self, cfg: OkxConfig) -> None:
        self.cfg = cfg

    def request(self, method: str, path: str, payload: Dict[str, Any]) -> Dict[str, Any] | None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        timestamp = _iso_timestamp()
        sign = _sign(self.cfg.api_secret, timestamp, method, path, body)

        headers = {
            "OK-ACCESS-KEY": self.cfg.api_key,
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.cfg.passphrase,
            "Content-Type": "application/json",
            "User-Agent": "ai-trading-analysis-agent/1.0",
        }
        if self.cfg.simulated:
            headers["x-simulated-trading"] = "1"

        url = f"{self.cfg.base_url}{path}"
        req = Request(url, data=body.encode("utf-8"), headers=headers, method=method)
        try:
            context = _ssl_context(self.cfg.ssl_verify)
            if context is None:
                with urlopen(req, timeout=10) as resp:
                    raw = resp.read().decode("utf-8")
            else:
                logger.warning("OKX SSL verification disabled (unsafe).")
                with urlopen(req, timeout=10, context=context) as resp:
                    raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
        except HTTPError as exc:
            try:
                raw = exc.read().decode("utf-8")
            except Exception:
                raw = str(exc)
            logger.warning("OKX HTTP error %s: %s", exc.code, raw)
        except URLError as exc:
            logger.warning("OKX network error: %s", exc)
        return None

    def set_leverage(
        self,
        inst_id: str,
        leverage: float,
        mgn_mode: str,
        pos_side: str | None = None,
    ) -> Dict[str, Any] | None:
        payload: Dict[str, Any] = {
            "instId": inst_id,
            "lever": str(leverage),
            "mgnMode": mgn_mode,
        }
        if pos_side:
            payload["posSide"] = pos_side
        return self.request("POST", "/api/v5/account/set-leverage", payload)

    def place_limit_order(
        self,
        inst_id: str,
        side: str,
        size: float,
        price: float,
        trade_mode: str,
        pos_side: str | None = None,
        client_id: str | None = None,
        tp_price: float | None = None,
        sl_price: float | None = None,
    ) -> Dict[str, Any] | None:
        def _fmt(val: float) -> str:
            s = f"{val:.10f}"
            return s.rstrip("0").rstrip(".") if "." in s else s

        payload: Dict[str, Any] = {
            "instId": inst_id,
            "tdMode": trade_mode,
            "side": side,
            "ordType": "limit",
            "sz": _fmt(size),
            "px": _fmt(price),
        }
        if client_id:
            payload["clOrdId"] = client_id
        if pos_side:
            payload["posSide"] = pos_side
        if tp_price is not None or sl_price is not None:
            algo_ord = {}
            if tp_price is not None:
                algo_ord["tpTriggerPx"] = _fmt(tp_price)
                algo_ord["tpOrdPx"] = "-1"
            if sl_price is not None:
                algo_ord["slTriggerPx"] = _fmt(sl_price)
                algo_ord["slOrdPx"] = "-1"
            payload["attachAlgoOrds"] = [algo_ord]

        return self.request("POST", "/api/v5/trade/order", payload)

