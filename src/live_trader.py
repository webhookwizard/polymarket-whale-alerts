"""REAL-MONEY trading via Polymarket's official Python SDK.

Safety rails (non-negotiable):
  1. Default mode is PAPER. Live orders require BOTH
     POLY_LIVE_TRADING=true AND a well-formed POLY_PRIVATE_KEY.
     If either is missing, every live call refuses and stays paper.
  2. The private key comes ONLY from the environment. It is never
     logged, never printed, never written to disk by this module.
     Log lines use a fingerprint (first/last chars) at most.
  3. POLY_MAX_ORDER_USD caps every single order. Orders above the cap
     are rejected BEFORE anything is signed. The cap lives in code.
  4. Dry-run first: preview_order() signs NOTHING. place_order()
     requires confirmed=True; without it you get NeedsConfirmation
     carrying the exact preview of what WOULD be signed.

The official SDK is `polymarket-client` (PyPI), i.e.
https://github.com/Polymarket/py-sdk — it replaced the archived
py-clob-client. It is an OPTIONAL dependency (requirements-live.txt);
without it, live mode refuses with a clear error and paper mode
is unaffected.
"""
from __future__ import annotations

import logging
import uuid

from .config import Config, looks_like_private_key
from .models import OrderPreview

log = logging.getLogger(__name__)


class LiveTradingDisabled(Exception):
    """Raised when a live order is attempted while the gate is closed."""


class OrderTooLarge(Exception):
    """Raised when an order exceeds POLY_MAX_ORDER_USD (pre-signing)."""


class NeedsConfirmation(Exception):
    """Raised when a live order lacks explicit confirmation.

    Carries the OrderPreview so the caller can show the user exactly
    what WOULD be signed before asking them to confirm.
    """

    def __init__(self, preview: OrderPreview) -> None:
        self.preview = preview
        super().__init__(
            "Live order needs explicit confirmation. "
            f"Preview (NOT signed): {preview.summary()}"
        )


class SdkNotInstalled(Exception):
    """Raised when live mode is requested without polymarket-client."""


class LiveTrader:
    """Real CLOB order placement behind the safety gate.

    Pass sdk=<module> in tests to inject a fake; otherwise the real
    `polymarket` package is imported lazily (only when live is used).
    """

    def __init__(self, config: Config, sdk=None) -> None:
        self.config = config
        self._sdk = sdk  # injected fake in tests; None = lazy real import
        self._client = None
        self._resolved_sdk = None
        ok, reason = config.live_gate()
        if ok:
            log.info(
                "LiveTrader armed (key %s, cap $%.2f/order)",
                config.key_fingerprint(),
                config.max_order_usd,
            )
        else:
            log.info("LiveTrader in PAPER mode: %s", reason)

    # -- gate -----------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self.config.live_enabled

    def _require_live(self) -> None:
        ok, reason = self.config.live_gate()
        if not ok:
            raise LiveTradingDisabled(reason)

    # -- dry run ---------------------------------------------------------
    def preview_order(
        self,
        token_id: str,
        market_title: str,
        side: str,
        outcome: str,
        price: float,
        size_usd: float,
    ) -> OrderPreview:
        """Build a preview. Signs NOTHING, touches NO network.

        size_usd is converted to shares at the limit price.
        """
        side = side.upper()
        if side not in ("BUY", "SELL"):
            raise ValueError(f"side must be BUY or SELL, got {side!r}")
        if not (0 < price < 1):
            raise ValueError(f"price must be in (0,1), got {price!r}")
        if size_usd <= 0:
            raise ValueError("size_usd must be positive")
        size_shares = round(size_usd / price, 4)
        preview = OrderPreview(
            token_id=token_id,
            market_title=market_title,
            side=side,
            outcome=outcome,
            price=round(price, 4),
            size_shares=size_shares,
            usd_value=round(size_shares * price, 2),
        )
        log.info("DRY-RUN preview (not signed): %s", preview.summary())
        return preview

    # -- live placement ---------------------------------------------------
    def place_order(self, preview: OrderPreview, confirmed: bool = False):
        """Place a REAL limit order. Enforces gate -> cap -> confirmation.

        Returns the SDK's order response on success.
        """
        self._require_live()
        if preview.usd_value > self.config.max_order_usd:
            raise OrderTooLarge(
                f"Order ${preview.usd_value:,.2f} exceeds cap "
                f"${self.config.max_order_usd:,.2f} — rejected before signing."
            )
        if not confirmed:
            raise NeedsConfirmation(preview)
        client = self._get_client()
        log.info(
            "CONFIRMED live order: %s (key %s)",
            preview.summary(),
            self.config.key_fingerprint(),
        )
        return self._submit(client, preview)

    # -- SDK plumbing (single isolated touch-point) ------------------------
    def _get_client(self):
        """Build the authenticated SDK client. Key never leaves this method
        except into the SDK constructor; errors are sanitized."""
        if self._client is not None:
            return self._client
        sdk = self._sdk
        if sdk is None:
            try:
                import polymarket  # type: ignore

                sdk = polymarket
            except ImportError:
                raise SdkNotInstalled(
                    "polymarket-client is not installed. "
                    "Run: pip install -r requirements-live.txt"
                )
        self._resolved_sdk = sdk
        if not looks_like_private_key(self.config.private_key):
            # Double-check at signing time even though the gate checked.
            raise LiveTradingDisabled("private key malformed — refusing to sign")
        try:
            client = sdk.SecureClient.create(private_key=self.config.private_key)
        except Exception:
            # Sanitize: never let key material leak through tracebacks.
            raise LiveTradingDisabled(
                "could not initialize trading client "
                f"(key {self.config.key_fingerprint()})"
            ) from None
        self._client = client
        return client

    def _submit(self, client, preview: OrderPreview):
        """The ONE place the SDK is touched. Fully mockable in tests."""
        enum = getattr(self._resolved_sdk, "OrderSide", None)
        if enum is None:  # test fakes may hang it off the client instead
            enum = getattr(client, "OrderSide", None)
        if enum is None:
            raise SdkNotInstalled("cannot resolve OrderSide from the SDK")
        side = enum.BUY if preview.side == "BUY" else enum.SELL
        return client.place_limit_order(
            token_id=preview.token_id,
            price=preview.price,
            size=preview.size_shares,
            side=side,
        )
