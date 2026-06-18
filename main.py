"""
Main entry point for the Multi-Asset Paper Trading Bot.
"""
import time
import pandas as pd
import ccxt
from datetime import datetime
from config import EXCHANGE_ID, TIMEFRAME, POLL_INTERVAL_SECONDS, ASSETS, INITIAL_CAPITAL, TRADING_PROFILES, MTF_TIMEFRAMES
from logger import logger
from paper_wallet import PaperWallet
from indicators import calculate_indicators
from strategy import evaluate_consensus, evaluate_multi_timeframe, check_mtf_confirmation
from utils import get_active_strategy
import threading

def fetch_data(exchange, symbol, timeframe, limit=100):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        return None

def run_asset(asset_symbol):
    """Run trading bot for a single asset, executing the user-selected profile."""
    # Parse asset symbol like BTC/USDT to get BTC
    name = asset_symbol.split('/')[0]
    initial_capital = INITIAL_CAPITAL.get(name, 5000)
    
    logger.info(f"Starting Trading Bot Thread for {name} ({asset_symbol})")
    
    exchange_class = getattr(ccxt, EXCHANGE_ID)
    exchange = exchange_class({'enableRateLimit': True})
    
    # Initialize a single wallet for this asset
    wallet = PaperWallet(initial_balance=initial_capital, asset_name=name)
    
    while True:
        try:
            # 1. Read active profile from disk dynamically on each tick
            active_profile = get_active_strategy(name)
            p_cfg = TRADING_PROFILES.get(active_profile, TRADING_PROFILES['Balanced'])
            
            # 2. Fetch main timeframe data
            df = fetch_data(exchange, asset_symbol, TIMEFRAME, limit=100)
            if df is not None and not df.empty:
                # 3. Calculate main indicators
                df = calculate_indicators(df)
                current_price = float(df.iloc[-1]['close'])
                atr_val = float(df.iloc[-1].get('ATR_14', 0.0))
                
                # 4. Fetch & calculate MTF data
                mtf_data = {}
                for tf in MTF_TIMEFRAMES:
                    mtf_df = fetch_data(exchange, asset_symbol, tf, limit=50)
                    if mtf_df is not None and not mtf_df.empty:
                        mtf_data[tf] = calculate_indicators(mtf_df)
                
                mtf_trends = evaluate_multi_timeframe(mtf_data)
                
                # 5. Fetch BTC/USDT data for correlation filter if not BTC
                btc_df = None
                if name != "BTC":
                    btc_df = fetch_data(exchange, "BTC/USDT", TIMEFRAME, limit=100)
                    if btc_df is not None and not btc_df.empty:
                        btc_df = calculate_indicators(btc_df)
                
                # 6. Check Risk Management (SL/TP)
                if wallet.open_position:
                    closed = wallet.check_sl_tp(current_price, atr_val)
                    if closed:
                        logger.info(f"[{name}] Position closed due to SL/TP.")
                
                wallet.tick_cooldown()
                
                # 7. Evaluate Consensus using Smart Market Regime, AI Confidence Score, and BTC Correlation
                votes, consensus, regime, adx_val, atr_ret, vol_state, block_msg, confidence_score, trade_quality = evaluate_consensus(
                    df, 
                    threshold=p_cfg['consensus_threshold'], 
                    adx_threshold=p_cfg['adx_threshold'], 
                    cooldown_candles_left=wallet.cooldown_remaining,
                    mtf_trends=mtf_trends,
                    btc_df=btc_df,
                    asset_name=name
                )
                
                # 8. Record correlation status
                btc_corr_status = "PASSED"
                if "correlation" in block_msg.lower():
                    btc_corr_status = "BLOCKED"
                
                # Format trade execution metadata for logs & journals
                log_reason = f"{active_profile} | Regime: {regime} | Conf: {confidence_score} ({trade_quality}) | BTC Corr: {btc_corr_status}"
                
                # Execute based on final consensus
                if consensus != 'HOLD':
                    wallet.execute_trade(consensus, current_price, trading_mode="Long + Short", reason=log_reason)
                    logger.info(f"[{name}] Executed trade: {consensus} @ {current_price} | Info: {log_reason}")
                elif block_msg:
                    # Write diagnostic to log
                    logger.debug(f"[{name}] Signal block details: {block_msg} | {log_reason}")
                        
        except Exception as e:
            logger.error(f"Unexpected error in main loop for {name}: {e}")
        
        time.sleep(POLL_INTERVAL_SECONDS)

def run_bot():
    """Start trading bots for each asset in parallel."""
    threads = []
    for asset_symbol in ASSETS:
        t = threading.Thread(target=run_asset, args=(asset_symbol,), daemon=True)
        t.start()
        threads.append(t)
    
    # Keep main thread alive
    for t in threads:
        t.join()

if __name__ == "__main__":
    try:
        logger.info("Initializing Multi-Asset Engine with Advanced Strategy Pack...")
        run_bot()
    except KeyboardInterrupt:
        print("\nShutting down bots...")
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
