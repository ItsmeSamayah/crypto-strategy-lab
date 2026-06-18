# Cryptocurrency Paper-Trading Bot

A modular Bitcoin paper-trading system that uses a consensus voting strategy based on real market data. It never places real trades and purely simulates execution.

## Features
- Fetches real-time 5-minute candles via CCXT (CoinDCX).
- 5 Technical Indicators: RSI(14), MACD, EMA Trend (20 & 50), Momentum, Volume Trend.
- Consensus Engine: Requires 4/5 agreement to trigger a trade.
- Risk Management: 1% risk per trade, 2% stop loss, 4% take profit.
- Simple backtesting module included.

## Setup Instructions (Windows)

1. **Install Dependencies**
   Open a terminal in this directory and run:
   ```cmd
   pip install -r requirements.txt
   ```

2. **Run the Bot**
   To start the live paper trading bot (polls every 5 minutes):
   ```cmd
   python main.py
   ```

3. **Run a Backtest**
   To run a simulated backtest on the last 1000 candles:
   ```cmd
   python main.py --backtest
   ```

## Warning
**Paper Trading Only!** This bot does not and cannot connect to live trading facilities to place real orders. Do not use this logic with real money without thorough testing and consideration.
