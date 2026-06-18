"""
Configuration settings for the consensus bot.
"""

EXCHANGE_ID = 'binance'
SYMBOL = 'BTC/USDT'
TIMEFRAME = '5m'
POLL_INTERVAL_SECONDS = 300  # 5 minutes

# Paper Trading settings
INITIAL_BALANCE_INR = 5000.0

# Risk Management
RISK_PER_TRADE_PERCENT = 1.0  # Risk 1% of account balance per trade
STOP_LOSS_PERCENT = 2.0       # 2% stop loss (fallback if ATR unavailable)
TAKE_PROFIT_PERCENT = 4.0     # 4% take profit (fallback)
ATR_SL_MULTIPLIER = 1.5       # Stop Loss = 1.5 × ATR
RISK_REWARD_RATIO = 2.0       # Take Profit = SL distance × 2
TRAILING_STOP_ATR = 1.0       # Move SL to breakeven after +1 ATR profit

# Paths
TRADES_LOG_FILE = 'trades.csv'
APP_LOG_FILE = 'bot.log'
WALLET_STATE_FILE = 'wallet.json'
DEBUG_LOG_FILE = 'debug.log'
TRADE_JOURNAL_FILE = 'trade_journal.csv'
DAILY_REPORT_FILE = 'daily_report.csv'
SIGNAL_HISTORY_FILE = 'signal_history.csv'
BACKTEST_RESULTS_FILE = 'backtest_results.csv'

# Indicator Periods
ATR_PERIOD = 14
ADX_PERIOD = 14
MIN_ATR_RATIO = 0.001       # ATR must be > 0.1% of price to allow trades
ADX_TREND_THRESHOLD = 20    # ADX > 20 = Trending, ADX < 20 = Sideways
COOLDOWN_CANDLES = 3         # Minimum candles to wait after closing a trade

# Multi-Timeframe Confirmation
MTF_TIMEFRAMES = ['5m', '15m', '1h']

# Telegram Notifications (placeholder — not connected)
TELEGRAM_ENABLED = False
TELEGRAM_BOT_TOKEN = ''
TELEGRAM_CHAT_ID = ''

# Trading Profiles
TRADING_PROFILES = {
    'Conservative': {'consensus_threshold': 4, 'adx_threshold': 20},
    'Balanced':     {'consensus_threshold': 3, 'adx_threshold': 15},
    'Aggressive':   {'consensus_threshold': 2, 'adx_threshold': 10},
}

# Diagnostics
DIAGNOSTICS_FILE = 'diagnostics.csv'
