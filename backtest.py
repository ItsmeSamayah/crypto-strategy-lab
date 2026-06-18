"""
Backtesting Engine — runs the consensus strategy on historical OHLCV data.
"""
import csv
import pandas as pd
from datetime import datetime
from indicators import calculate_indicators
from strategy import evaluate_consensus
from config import (
    INITIAL_BALANCE_INR, STOP_LOSS_PERCENT, TAKE_PROFIT_PERCENT,
    RISK_PER_TRADE_PERCENT, ATR_SL_MULTIPLIER, RISK_REWARD_RATIO,
    BACKTEST_RESULTS_FILE
)


def _calc_quantity(balance: float, price: float) -> float:
    risk = balance * (RISK_PER_TRADE_PERCENT / 100.0)
    qty  = risk / (price * (STOP_LOSS_PERCENT / 100.0))
    return min(qty, balance / price)


def run_backtest(df_full: pd.DataFrame, threshold: int = 3, adx_threshold: int = 20) -> dict:
    """
    Simulates paper trading on a fully-loaded OHLCV dataframe.
    Returns a results dict with performance metrics + equity curve.
    """
    df = calculate_indicators(df_full.copy())

    balance      = INITIAL_BALANCE_INR
    position     = None
    trades       = []
    peak_balance = balance
    max_drawdown = 0.0
    equity_curve = []
    cooldown     = 0

    for i in range(50, len(df)):
        row   = df.iloc[i]
        price = float(row['close'])
        ts    = row['timestamp']
        atr   = float(row.get('ATR_14', 0))

        # ── SL/TP check (ATR-based) ──
        if position:
            ep  = position['price']
            act = position['action']
            sl_d = atr * ATR_SL_MULTIPLIER if atr > 0 else ep * (STOP_LOSS_PERCENT / 100)
            tp_d = sl_d * RISK_REWARD_RATIO

            hit = False
            if act == 'BUY':
                if price <= ep - sl_d:
                    hit = True
                    reason = 'Stop Loss'
                elif price >= ep + tp_d:
                    hit = True
                    reason = 'Take Profit'
            else:
                if price >= ep + sl_d:
                    hit = True
                    reason = 'Stop Loss'
                elif price <= ep - tp_d:
                    hit = True
                    reason = 'Take Profit'

            if hit:
                pnl = (price - ep) * position['qty'] if act == 'BUY' else (ep - price) * position['qty']
                balance += pnl
                trades.append({'ts': ts, 'pnl': pnl, 'reason': reason})
                position = None
                cooldown = 3

        if cooldown > 0:
            cooldown -= 1

        # ── Strategy ──
        sub_df = df.iloc[:i + 1]
        votes, consensus, regime, adx, atr_v, vol_state, block_msg = evaluate_consensus(
            sub_df, threshold=threshold, adx_threshold=adx_threshold, cooldown_candles_left=cooldown
        )

        if consensus == 'BUY' and not position:
            qty = _calc_quantity(balance, price)
            position = {'action': 'BUY', 'price': price, 'qty': qty}

        elif consensus == 'SELL' and position and position['action'] == 'BUY':
            ep  = position['price']
            pnl = (price - ep) * position['qty']
            balance += pnl
            trades.append({'ts': ts, 'pnl': pnl, 'reason': 'Consensus SELL'})
            position = None
            cooldown = 3

        # ── Equity tracking ──
        unrealized = 0.0
        if position:
            unrealized = (price - position['price']) * position['qty'] if position['action'] == 'BUY' \
                else (position['price'] - price) * position['qty']
        total_equity = balance + unrealized
        equity_curve.append({'ts': ts, 'equity': total_equity})

        if total_equity > peak_balance:
            peak_balance = total_equity
        dd = (peak_balance - total_equity) / peak_balance * 100
        if dd > max_drawdown:
            max_drawdown = dd

    # ── Metrics ──
    n        = len(trades)
    wins     = [t for t in trades if t['pnl'] > 0]
    losses   = [t for t in trades if t['pnl'] <= 0]
    gross_p  = sum(t['pnl'] for t in wins)
    gross_l  = abs(sum(t['pnl'] for t in losses))
    profit_f = gross_p / gross_l if gross_l > 0 else (float('inf') if gross_p > 0 else 0.0)
    net_profit = balance - INITIAL_BALANCE_INR
    total_ret  = (net_profit / INITIAL_BALANCE_INR) * 100
    win_rate   = (len(wins) / n * 100) if n > 0 else 0.0

    results = {
        'total_trades':   n,
        'winning_trades': len(wins),
        'losing_trades':  len(losses),
        'win_rate':       round(win_rate, 2),
        'net_profit':     round(net_profit, 4),
        'total_return':   round(total_ret, 2),
        'profit_factor':  round(profit_f, 2),
        'max_drawdown':   round(max_drawdown, 2),
        'final_balance':  round(balance, 4),
        'equity_curve':   pd.DataFrame(equity_curve) if equity_curve else pd.DataFrame(),
        'trades_list':    trades,
    }

    return results


def save_backtest_results(results: dict, period_label: str):
    """Save backtest summary to CSV for export."""
    headers = ['Period', 'Total Trades', 'Win Rate', 'Net Profit',
               'Max Drawdown', 'Profit Factor', 'Final Balance']
    row = [
        period_label, results['total_trades'], results['win_rate'],
        results['net_profit'], results['max_drawdown'],
        results['profit_factor'], results['final_balance']
    ]

    file_exists = pd.io.common.file_exists(BACKTEST_RESULTS_FILE)
    with open(BACKTEST_RESULTS_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(headers)
        writer.writerow(row)
