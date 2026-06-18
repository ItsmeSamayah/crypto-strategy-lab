"""
Exchange Adapter — Future-ready abstraction layer.
Supports multi-timeframe data fetching.
"""
import ccxt
import pandas as pd
from logger import logger


class ExchangeAdapter:
    """
    Thin wrapper around CCXT.
    All strategy/wallet code calls only this class, never ccxt directly.
    """

    def __init__(self, exchange_id: str):
        self.exchange_id = exchange_id.lower()
        self.exchange = self._build_exchange(exchange_id)

    def _build_exchange(self, exchange_id: str):
        if exchange_id == 'coindcx':
            logger.warning("CoinDCX adapter not yet supported — falling back to Binance.")
            exchange_id = 'binance'
        elif exchange_id == 'bybit':
            logger.info("Bybit adapter selected.")

        if hasattr(ccxt, exchange_id):
            cls = getattr(ccxt, exchange_id)
            return cls({'enableRateLimit': True})
        else:
            logger.error(f"Exchange '{exchange_id}' not found. Defaulting to Binance.")
            return ccxt.binance({'enableRateLimit': True})

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> pd.DataFrame:
        """Fetch OHLCV candles and return a clean DataFrame."""
        try:
            raw = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(raw, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            logger.error(f"[{self.exchange_id}] fetch_ohlcv error: {e}")
            return pd.DataFrame()

    def fetch_multi_timeframe(self, symbol: str, timeframes: list[str], limit: int = 100) -> dict[str, pd.DataFrame]:
        """
        Fetch OHLCV for multiple timeframes in one call.
        Returns: { '5m': DataFrame, '15m': DataFrame, '1h': DataFrame, ... }
        """
        result = {}
        for tf in timeframes:
            result[tf] = self.fetch_ohlcv(symbol, tf, limit=limit)
        return result

    def get_ticker_price(self, symbol: str) -> float:
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return float(ticker['last'])
        except Exception as e:
            logger.error(f"[{self.exchange_id}] get_ticker_price error: {e}")
            return 0.0
