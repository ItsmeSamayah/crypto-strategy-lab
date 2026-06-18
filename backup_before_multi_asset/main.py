"""
Main entry point for the Paper Trading Bot.
"""
import time
import pandas as pd
import ccxt
from datetime import datetime
from config import EXCHANGE_ID, SYMBOL, TIMEFRAME, INITIAL_BALANCE_INR, POLL_INTERVAL_SECONDS
from logger import logger
from paper_wallet import PaperWallet
from indicators import calculate_indicators
from strategy import evaluate_consensus

def fetch_data(exchange, symbol, timeframe, limit=100):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        return None

def print_dashboard(current_price, votes, consensus, wallet):
    print("\n" + "="*40)
    print(f"Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"BTC Price: {current_price:.2f}")
    print("-" * 40)
    for ind, vote in votes.items():
        print(f"{ind}: {vote}")
    print("-" * 40)
    print(f"Consensus: {consensus}")
    print("-" * 40)
    print(f"Balance: ₹{wallet.balance:.2f}")
    print(f"Open Position Status: {wallet.get_status(current_price)}")
    print("="*40 + "\n")

def run_bot():
    logger.info("Starting Paper Trading Bot...")
    logger.info(f"Exchange: {EXCHANGE_ID}, Symbol: {SYMBOL}, Timeframe: {TIMEFRAME}")
    
    exchange_class = getattr(ccxt, EXCHANGE_ID)
    exchange = exchange_class({'enableRateLimit': True})
    
    wallet = PaperWallet(initial_balance=INITIAL_BALANCE_INR)

    while True:
        try:
            # Fetch data
            df = fetch_data(exchange, SYMBOL, TIMEFRAME, limit=100)
            if df is not None and not df.empty:
                # Calculate indicators
                df = calculate_indicators(df)
                
                current_price = df.iloc[-1]['close']
                
                # Check Risk Management first
                if wallet.open_position:
                    closed = wallet.check_sl_tp(current_price)
                    if closed:
                        logger.info("Position closed due to SL/TP.")
                
                # Evaluate strategy
                votes, consensus, *_ = evaluate_consensus(df)
                
                # Execute based on consensus
                if consensus != 'HOLD':
                    wallet.execute_trade(consensus, current_price, reason="Consensus")
                
                # Print Dashboard
                print_dashboard(current_price, votes, consensus, wallet)
                
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
            
        time.sleep(POLL_INTERVAL_SECONDS)

def backtest():
    """
    Simple backtest module using historical data.
    """
    print("\n--- Running Backtest ---")
    exchange_class = getattr(ccxt, EXCHANGE_ID)
    exchange = exchange_class({'enableRateLimit': True})
    
    wallet = PaperWallet(initial_balance=INITIAL_BALANCE_INR)
    
    # Fetch a larger chunk of data for backtesting
    df = fetch_data(exchange, SYMBOL, TIMEFRAME, limit=1000)
    if df is None or df.empty:
        print("Failed to fetch data for backtesting.")
        return
        
    df = calculate_indicators(df)
    
    # Track metrics
    trades_count = 0
    winning_trades = 0
    gross_profit = 0.0
    gross_loss = 0.0
    peak_balance = wallet.balance
    max_drawdown = 0.0
    
    # Simulate step by step from index 50 to end
    for i in range(50, len(df)):
        sub_df = df.iloc[:i+1]
        current_price = sub_df.iloc[-1]['close']
        
        # Check SL/TP
        if wallet.open_position:
            entry = wallet.open_position['price']
            action = wallet.open_position['action']
            qty = wallet.open_position['quantity']
            
            closed = wallet.check_sl_tp(current_price)
            if closed:
                pnl = wallet.realized_pnl - getattr(wallet, '_last_realized_pnl', wallet.realized_pnl)
                trades_count += 1
                if pnl > 0:
                    winning_trades += 1
                    gross_profit += pnl
                else:
                    gross_loss += abs(pnl)
                wallet._last_realized_pnl = wallet.realized_pnl

        # Evaluate strategy
        votes, consensus, *_ = evaluate_consensus(sub_df)
        
        # Execute
        if consensus == 'BUY' and not wallet.open_position:
            wallet.execute_trade('BUY', current_price, reason="Consensus")
            wallet._last_realized_pnl = wallet.realized_pnl
        elif consensus == 'SELL' and wallet.open_position:
            wallet.close_position(current_price, "Consensus")
            pnl = wallet.realized_pnl - wallet._last_realized_pnl
            trades_count += 1
            if pnl > 0:
                winning_trades += 1
                gross_profit += pnl
            else:
                gross_loss += abs(pnl)
                
        # Drawdown tracking
        if wallet.balance > peak_balance:
            peak_balance = wallet.balance
        dd = (peak_balance - wallet.balance) / peak_balance * 100
        if dd > max_drawdown:
            max_drawdown = dd
            
    # Final metrics
    total_return_pct = ((wallet.balance - INITIAL_BALANCE_INR) / INITIAL_BALANCE_INR) * 100
    win_rate = (winning_trades / trades_count * 100) if trades_count > 0 else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float('inf') if gross_profit > 0 else 0.0)
    
    print(f"Total Return: {total_return_pct:.2f}%")
    print(f"Number of Trades: {trades_count}")
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"Max drawdown: {max_drawdown:.2f}%")
    print(f"Profit Factor: {profit_factor:.2f}")
    print(f"Final Balance: ₹{wallet.balance:.2f}")
    print("------------------------\n")

if __name__ == "__main__":
    import sys
    try:
        if len(sys.argv) > 1 and sys.argv[1] == '--backtest':
            backtest()
        else:
            run_bot()
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
    finally:
        input("\nPress Enter to exit...")
