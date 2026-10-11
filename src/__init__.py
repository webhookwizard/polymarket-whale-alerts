"""polymarket-whale-alerts: real-time Polymarket whale watcher.

Paper mode is the default everywhere. Live (real-money) trading is
gated behind POLY_LIVE_TRADING=true + POLY_PRIVATE_KEY and a per-order
USD cap — see src/live_trader.py for the safety rails.
"""

__version__ = "0.1.0"
