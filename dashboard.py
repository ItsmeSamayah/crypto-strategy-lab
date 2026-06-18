"""
BTC Paper Trading — Professional Trading Terminal UI & Strategy Lab v4
Multi-TF confirmation, ATR SL/TP, trailing stop, analytics,
performance cards, strategy health, export, backtest, notifications,
parallel multi-profile simulation.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import os
import csv
import time
import io
from datetime import datetime, timedelta, date

import config
from config import (
    EXCHANGE_ID, SYMBOL, INITIAL_BALANCE_INR,
    TRADES_LOG_FILE, TRADE_JOURNAL_FILE, DAILY_REPORT_FILE,
    SIGNAL_HISTORY_FILE, DEBUG_LOG_FILE, BACKTEST_RESULTS_FILE,
    ADX_TREND_THRESHOLD, MTF_TIMEFRAMES, ATR_SL_MULTIPLIER, RISK_REWARD_RATIO,
    TELEGRAM_ENABLED
)
from exchange_adapter import ExchangeAdapter
from paper_wallet import PaperWallet
from indicators import calculate_indicators
from strategy import evaluate_consensus, evaluate_multi_timeframe, check_mtf_confirmation
from backtest import run_backtest, save_backtest_results
from notifications import get_recent_notifications

# ═══════════════════════════════════════════════════════════════
# PAGE CONFIG
# ═══════════════════════════════════════════════════════════════
st.set_page_config(page_title="BTC Pro Trading Terminal", page_icon="⚡", layout="wide", initial_sidebar_state="expanded")

# ═══════════════════════════════════════════════════════════════
# THEME CONFIG & STYLING
# ═══════════════════════════════════════════════════════════════
theme = st.sidebar.selectbox("UI Theme", ["Dark Pro", "Cyber Blue", "Emerald Glow"], index=0)

if theme == "Dark Pro":
    primary_color = "#00e676"  # Emerald Green
    danger_color = "#ff1744"   # Crimson Red
    accent_color = "#29b6f6"   # Electric Blue
    bg_color = "#101418"       # Charcoal Black
    card_bg = "#182026"
    card_border = "#2a363f"
    text_color = "#ffffff"
    text_muted = "#8e9ca8"
elif theme == "Cyber Blue":
    primary_color = "#00f0ff"  # Neon Cyan
    danger_color = "#ff007f"   # Neon Magenta
    accent_color = "#a855f7"   # Purple Neon
    bg_color = "#080c14"       # Deep Cyber Space
    card_bg = "#0f1626"
    card_border = "#1b2a47"
    text_color = "#ffffff"
    text_muted = "#748ba3"
else:  # Emerald Glow
    primary_color = "#10b981"  # Emerald
    danger_color = "#ef4444"   # Soft Red
    accent_color = "#f59e0b"   # Amber Gold
    bg_color = "#060a08"       # Forest Black
    card_bg = "#0c1410"
    card_border = "#1a3024"
    text_color = "#ffffff"
    text_muted = "#708c7c"

st.markdown(f"""
<style>
  /* Import Google Font */
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Outfit:wght@400;600;800&display=swap');
  
  /* Apply fonts */
  html, body, [class*="css"], .stApp {{
    font-family: 'Outfit', sans-serif;
  }}
  
  .stApp {{
    background-color: {bg_color} !important;
    color: {text_color} !important;
  }}
  
  /* Glassmorphic Cards */
  .terminal-card {{
    background: {card_bg};
    border: 1px solid {card_border};
    border-radius: 12px;
    padding: 18px;
    margin-bottom: 16px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    backdrop-filter: blur(12px);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
  }}
  
  .terminal-card:hover {{
    transform: translateY(-2px);
    box-shadow: 0 6px 16px rgba(0, 0, 0, 0.3);
  }}
  
  /* Dynamic Signals */
  .signal-buy  {{ color: {primary_color}; font-weight: 800; font-size: 16px; }}
  .signal-sell {{ color: {danger_color}; font-weight: 800; font-size: 16px; }}
  .signal-hold {{ color: #ffd600; font-weight: 800; font-size: 16px; }}
  .signal-side {{ color: {accent_color}; font-weight: 800; font-size: 16px; }}
  .big-consensus {{ font-size: 36px; font-weight: 900; letter-spacing: -0.5px; }}
  
  /* Custom Scrollbars */
  ::-webkit-scrollbar {{
    width: 6px;
    height: 6px;
  }}
  ::-webkit-scrollbar-track {{
    background: {bg_color};
  }}
  ::-webkit-scrollbar-thumb {{
    background: {card_border};
    border-radius: 4px;
  }}
  ::-webkit-scrollbar-thumb:hover {{
    background: {accent_color};
  }}
</style>
""", unsafe_allow_html=True)

theme_colors = {'up': primary_color, 'down': danger_color, 'accent': accent_color, 'text': text_color, 'muted': text_muted}

def hex_to_rgba(hex_color, alpha=0.15):
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        return f"rgba(0, 230, 118, {alpha})"
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"

# ═══════════════════════════════════════════════════════════════
# HELPERS & UTILITIES
# ═══════════════════════════════════════════════════════════════
def fmt(val):
    if val == "BUY":  return f'<span class="signal-buy">▲ BUY</span>'
    if val == "SELL": return f'<span class="signal-sell">▼ SELL</span>'
    if val == "HOLD": return '<span class="signal-hold">● HOLD</span>'
    return f'<span class="signal-side">◈ {val}</span>'

def fmt_trend(t):
    if t == "BULLISH": return f'<span class="signal-buy">▲ BULLISH</span>'
    if t == "BEARISH": return f'<span class="signal-sell">▼ BEARISH</span>'
    return '<span class="signal-hold">● NEUTRAL</span>'

def load_csv(path):
    if os.path.exists(path):
        try:
            df = pd.read_csv(path)
            if not df.empty:
                return df
        except Exception:
            pass
    return pd.DataFrame()

def compute_analytics(trades_df, wallet):
    r = dict(
        total_trades=0, winning_trades=0, losing_trades=0, win_rate=0.0,
        avg_profit=0.0, avg_loss=0.0, largest_win=0.0, largest_loss=0.0,
        profit_factor=0.0, max_drawdown=0.0, total_return_pct=0.0,
        buy_signals=0, sell_signals=0, hold_signals=0,
    )
    if trades_df.empty:
        return r
    closes = trades_df[trades_df['Action'] == 'CLOSE'].copy()
    r['buy_signals']  = len(trades_df[trades_df['Action'] == 'BUY'])
    r['sell_signals'] = len(trades_df[trades_df['Action'] == 'SELL'])
    r['total_trades'] = len(closes)
    if not closes.empty:
        wins   = closes[closes['PnL'] > 0]['PnL']
        losses = closes[closes['PnL'] <= 0]['PnL']
        r['winning_trades'] = len(wins)
        r['losing_trades']  = len(losses)
        r['win_rate']       = round(len(wins) / len(closes) * 100, 1) if len(closes) > 0 else 0.0
        r['avg_profit']     = round(wins.mean(), 2) if not wins.empty else 0.0
        r['avg_loss']       = round(losses.mean(), 2) if not losses.empty else 0.0
        r['largest_win']    = round(wins.max(), 2) if not wins.empty else 0.0
        r['largest_loss']   = round(losses.min(), 2) if not losses.empty else 0.0
        gp = wins.sum(); gl = abs(losses.sum())
        r['profit_factor']  = round(gp / gl, 2) if gl > 0 else (float('inf') if gp > 0 else 0.0)
        if 'Balance' in trades_df.columns:
            bal = trades_df['Balance'].dropna()
            peak = bal.cummax()
            dd = (peak - bal) / peak * 100
            r['max_drawdown'] = round(dd.max(), 2)
    r['total_return_pct'] = round(
        (wallet.balance - 5000.0) / 5000.0 * 100, 2)
    return r

def get_strategy_health(trades_df):
    closes = trades_df[trades_df['Action'] == 'CLOSE'].tail(50) if not trades_df.empty else pd.DataFrame()
    if closes.empty:
        return "yellow", "BREAKEVEN"
    total_pnl = closes['PnL'].sum()
    if total_pnl > 0.05:
        return "green", "PROFITABLE"
    elif total_pnl < -0.05:
        return "red", "LOSING"
    else:
        return "yellow", "BREAKEVEN"

def get_performance_card(trades_df, journal_df):
    today_str = date.today().isoformat()
    week_ago  = (date.today() - timedelta(days=7)).isoformat()
    result = {'trades_today': 0, 'profit_today': 0.0,
              'trades_week': 0, 'profit_week': 0.0, 'avg_duration': 'N/A'}

    if not trades_df.empty:
        closes = trades_df[trades_df['Action'] == 'CLOSE'].copy()
        if not closes.empty:
            closes['date'] = pd.to_datetime(closes['Timestamp']).dt.date.astype(str)
            today_c = closes[closes['date'] == today_str]
            week_c  = closes[closes['date'] >= week_ago]
            result['trades_today'] = len(today_c)
            result['profit_today'] = round(today_c['PnL'].sum(), 2)
            result['trades_week']  = len(week_c)
            result['profit_week']  = round(week_c['PnL'].sum(), 2)

    if not journal_df.empty and 'Trade Duration' in journal_df.columns:
        durations = journal_df['Trade Duration'].dropna()
        durations = durations[durations != 'N/A']
        if not durations.empty:
            try:
                mins = durations.str.replace(' min', '').astype(float)
                avg_m = mins.mean()
                result['avg_duration'] = f"{avg_m:.0f} min"
            except Exception:
                pass
    return result

def init_diagnostics_csv():
    if not os.path.exists(config.DIAGNOSTICS_FILE):
        with open(config.DIAGNOSTICS_FILE, 'w', newline='') as f:
            csv.writer(f).writerow([
                'Timestamp', 'Candle_Timestamp', 'Profile', 'Signal_Type',
                'Votes', 'Threshold', 'ADX_Value', 'ADX_Threshold',
                'Cooldown_Remaining', 'Blocked_Reason', 'Status'
            ])

def log_diagnostic_event(candle_ts, profile, signal_type, votes, threshold, adx_val, adx_threshold, cooldown, blocked_reason, status):
    init_diagnostics_csv()
    df_diag = load_csv(config.DIAGNOSTICS_FILE)
    if not df_diag.empty:
        matches = df_diag[(df_diag['Candle_Timestamp'].astype(str) == str(candle_ts)) & (df_diag['Profile'] == profile)]
        if not matches.empty:
            return
            
    with open(config.DIAGNOSTICS_FILE, 'a', newline='') as f:
        csv.writer(f).writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            str(candle_ts),
            profile,
            signal_type or "NONE",
            votes,
            threshold,
            round(adx_val, 2),
            adx_threshold,
            cooldown,
            blocked_reason,
            status
        ])

def get_diagnostics_metrics(profile_name):
    init_diagnostics_csv()
    df_diag = load_csv(config.DIAGNOSTICS_FILE)
    
    metrics = {
        'total_signals_today': 0,
        'blocked_adx_today': 0,
        'blocked_consensus_today': 0,
        'blocked_cooldown_today': 0,
        'blocked_volatility_today': 0,
        'executed_today': 0,
        'potential_trades_today': 0,
        'actual_trades_today': 0
    }
    
    if df_diag.empty:
        return metrics
        
    today_str = date.today().isoformat()
    df_diag['date'] = pd.to_datetime(df_diag['Timestamp']).dt.date.astype(str)
    df_today = df_diag[(df_diag['date'] == today_str) & (df_diag['Profile'] == profile_name)]
    
    if df_today.empty:
        return metrics
        
    df_unique = df_today.drop_duplicates(subset=['Candle_Timestamp'])
    df_signals = df_unique[df_unique['Signal_Type'].isin(['BUY', 'SELL'])]
    
    metrics['total_signals_today'] = len(df_signals)
    metrics['blocked_adx_today'] = len(df_signals[df_signals['Status'] == 'BLOCKED_ADX'])
    metrics['blocked_consensus_today'] = len(df_signals[df_signals['Status'] == 'BLOCKED_CONSENSUS'])
    metrics['blocked_cooldown_today'] = len(df_signals[df_signals['Status'] == 'BLOCKED_COOLDOWN'])
    metrics['blocked_volatility_today'] = len(df_signals[df_signals['Status'] == 'BLOCKED_VOLATILITY'])
    metrics['executed_today'] = len(df_signals[df_signals['Status'] == 'EXECUTED'])
    metrics['potential_trades_today'] = len(df_signals[df_signals['Status'] != 'BLOCKED_CONSENSUS'])
    
    # Load profile trades log to get actual trades
    p_wallet = PaperWallet(initial_balance=5000.0, profile_name=profile_name)
    trades_df = load_csv(p_wallet.trades_log_file)
    if not trades_df.empty:
        trades_df['date'] = pd.to_datetime(trades_df['Timestamp']).dt.date.astype(str)
        trades_today = trades_df[(trades_df['date'] == today_str) & (trades_df['Action'].isin(['BUY', 'SELL']))]
        metrics['actual_trades_today'] = len(trades_today)
    else:
        metrics['actual_trades_today'] = metrics['executed_today']
        
    return metrics

# ═══════════════════════════════════════════════════════════════
# MULTI-PROFILE TICK ENGINE
# ═══════════════════════════════════════════════════════════════
def run_profile_tick(profile_name, df_profile, mtf_data_profile, is_mtf_enabled, consensus_threshold, adx_threshold, current_price, atr_val_raw):
    # Isolated wallet
    p_wallet = PaperWallet(initial_balance=5000.0, profile_name=profile_name)
    p_wallet.tick_cooldown()
    
    if p_wallet.open_position:
        p_wallet.check_sl_tp(current_price, atr_val=atr_val_raw)
        
    p_votes, p_consensus, p_regime, p_adx, p_atr, p_vol_state, p_block_msg = evaluate_consensus(
        df_profile, threshold=consensus_threshold, adx_threshold=adx_threshold, cooldown_candles_left=p_wallet.cooldown_remaining
    )
    
    p_mtf_block = ""
    if is_mtf_enabled and mtf_data_profile:
        p_trends = evaluate_multi_timeframe(mtf_data_profile)
        if p_consensus != "HOLD":
            confirmed, mtf_reason = check_mtf_confirmation(p_consensus, p_trends)
            if not confirmed:
                p_mtf_block = mtf_reason
                p_consensus = "HOLD"
                p_block_msg = mtf_reason
                
    p_trade_executed = False
    p_block_reason = p_block_msg or "N/A"
    
    if p_consensus != 'HOLD':
        executed, exec_msg, blk = p_wallet.execute_trade(
            p_consensus, current_price, trading_mode="Long + Short", reason="Consensus"
        )
        if executed:
            p_trade_executed = True
            p_block_reason = ""
        else:
            p_block_reason = blk
            
    # Closed candle diagnostics logging
    if len(df_profile) >= 2:
        c_df = df_profile.iloc[:-1]
        c_ts = c_df.iloc[-1]['timestamp']
        c_votes, c_consensus, c_regime, c_adx, c_atr, c_vol_state, c_block_msg = evaluate_consensus(
            c_df, threshold=consensus_threshold, adx_threshold=adx_threshold, cooldown_candles_left=p_wallet.cooldown_remaining
        )
        
        c_mtf_block = ""
        if is_mtf_enabled and mtf_data_profile:
            if c_consensus != "HOLD":
                p_trends = evaluate_multi_timeframe(mtf_data_profile)
                confirmed, mtf_reason = check_mtf_confirmation(c_consensus, p_trends)
                if not confirmed:
                    c_mtf_block = mtf_reason
                    c_consensus = "HOLD"
                    c_block_msg = mtf_reason
                    
        c_buy = list(c_votes.values()).count("BUY")
        c_sell = list(c_votes.values()).count("SELL")
        c_sig = None
        c_votes_cnt = 0
        if c_buy > c_sell and c_buy > 0:
            c_sig = "BUY"
            c_votes_cnt = c_buy
        elif c_sell > c_buy and c_sell > 0:
            c_sig = "SELL"
            c_votes_cnt = c_sell
            
        c_status = "NONE"
        c_blocked_reason = ""
        if c_sig:
            if c_votes_cnt < consensus_threshold:
                c_status = "BLOCKED_CONSENSUS"
                c_blocked_reason = f"Blocked because consensus votes = {c_votes_cnt} and threshold = {consensus_threshold}"
            elif c_adx < adx_threshold:
                c_status = "BLOCKED_ADX"
                c_blocked_reason = f"Blocked because ADX = {c_adx:.1f} and threshold = {adx_threshold}"
            elif c_vol_state == "LOW VOLATILITY":
                c_status = "BLOCKED_VOLATILITY"
                c_blocked_reason = f"Blocked because volatility too low (ATR {c_atr:.2f})"
            elif p_wallet.cooldown_remaining > 0:
                c_status = "BLOCKED_COOLDOWN"
                c_blocked_reason = f"Blocked because cooldown active ({p_wallet.cooldown_remaining} candles left)"
            elif c_mtf_block:
                c_status = "BLOCKED_CONSENSUS"
                c_blocked_reason = c_mtf_block
            else:
                c_status = "EXECUTED"
                
        log_diagnostic_event(
            candle_ts=c_ts,
            profile=profile_name or "Custom",
            signal_type=c_sig,
            votes=c_votes_cnt,
            threshold=consensus_threshold,
            adx_val=c_adx,
            adx_threshold=adx_threshold,
            cooldown=p_wallet.cooldown_remaining,
            blocked_reason=c_blocked_reason,
            status=c_status
        )

# ═══════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════
st.sidebar.title("⚡ BOT TERMINAL")

profile_name = st.sidebar.selectbox("Active Profile", ["Balanced", "Conservative", "Aggressive", "Scalper", "Custom"], index=0)
trading_mode = st.sidebar.selectbox("Trading Mode", ["Long Only", "Long + Short"], index=1)

# Main UI timeframe
candle_interval  = st.sidebar.selectbox("Base Candle Interval", ['1m', '5m', '15m', '1h'], index=1)
risk_pct         = st.sidebar.number_input("Risk Per Trade %", 0.1, 10.0, 1.0, 0.1)
refresh_interval = st.sidebar.number_input("Auto Refresh (s)", 10, 300, 30, 10)
enable_mtf       = st.sidebar.checkbox("Multi-Timeframe Confirmation", value=True)

config.RISK_PER_TRADE_PERCENT = risk_pct

if profile_name == "Conservative":
    threshold = 4
    adx_threshold = 20
    mtf_enabled = True
    profile_timeframe = candle_interval
elif profile_name == "Balanced":
    threshold = 3
    adx_threshold = 15
    mtf_enabled = True
    profile_timeframe = candle_interval
elif profile_name == "Aggressive":
    threshold = 2
    adx_threshold = 10
    mtf_enabled = False
    profile_timeframe = candle_interval
elif profile_name == "Scalper":
    threshold = 2
    adx_threshold = 5
    mtf_enabled = False
    profile_timeframe = "1m"
else: # Custom
    threshold = st.sidebar.slider("Consensus Threshold", 2, 5, 3)
    adx_threshold = st.sidebar.slider("ADX Threshold", 5, 30, 15)
    mtf_enabled = enable_mtf
    profile_timeframe = candle_interval

st.sidebar.info(f"⚡ Config Details:\n- Threshold: {threshold}\n- ADX: {adx_threshold}\n- MTF: {'ON' if mtf_enabled else 'OFF'}\n- Candle: {profile_timeframe}")

st.sidebar.markdown("---")
st.sidebar.subheader("🧪 Trade Testing")
if st.sidebar.button("⚡ Force Test BUY Trade"):
    st.session_state.force_trade = True

st.sidebar.markdown("---")
st.sidebar.subheader("📊 Backtesting")
bt_period = st.sidebar.selectbox("Backtest Period", ["Last 30 Days", "Last 90 Days", "Last 365 Days"])
run_bt    = st.sidebar.button("▶ Run Backtest")

st.sidebar.markdown("---")
st.sidebar.subheader("📤 Export Profile Data")
exp_journal  = st.sidebar.button("Export Trade Journal")
exp_daily    = st.sidebar.button("Export Daily Report")
exp_backtest = st.sidebar.button("Export Backtest Results")

st.sidebar.markdown("---")
st.sidebar.subheader("🔔 Telegram Alerts")
tg_status = "🟢 Enabled" if TELEGRAM_ENABLED else "⚪ Disabled (framework ready)"
st.sidebar.markdown(f"Telegram: {tg_status}")

# ═══════════════════════════════════════════════════════════════
# INITIAL DATA FETCH
# ═══════════════════════════════════════════════════════════════
if 'adapter' not in st.session_state:
    st.session_state.adapter = ExchangeAdapter(EXCHANGE_ID)
adapter = st.session_state.adapter

with st.spinner("Streaming Market Data..."):
    df_main = adapter.fetch_ohlcv(SYMBOL, candle_interval, limit=200)
    df_1m = adapter.fetch_ohlcv(SYMBOL, '1m', limit=200)
    mtf_data = {}
    if mtf_enabled or enable_mtf:
        mtf_data = adapter.fetch_multi_timeframe(SYMBOL, MTF_TIMEFRAMES, limit=100)

if df_main is None or df_main.empty:
    st.error(f"❌ Market stream disconnected. Retrying in {refresh_interval}s...")
    time.sleep(refresh_interval)
    st.rerun()

df_main = calculate_indicators(df_main)
if df_1m is not None and not df_1m.empty:
    df_1m = calculate_indicators(df_1m)
else:
    df_1m = df_main  # fallback

current_price = float(df_main.iloc[-1]['close'])
atr_val_raw   = float(df_main.iloc[-1].get('ATR_14', 0.0))

# Timezone alignment calculation
local_now = datetime.now()
utc_now = datetime.utcnow()
tz_offset = local_now - utc_now
df_main['timestamp_local'] = df_main['timestamp'] + tz_offset
df_1m['timestamp_local'] = df_1m['timestamp'] + tz_offset

# ═══════════════════════════════════════════════════════════════
# EXECUTE PARALLEL SIMULATIONS
# ═══════════════════════════════════════════════════════════════
PROFILES_SIM_CFG = {
    "Conservative": {"consensus_threshold": 4, "adx_threshold": 20, "enable_mtf": True, "timeframe": "main"},
    "Balanced":     {"consensus_threshold": 3, "adx_threshold": 15, "enable_mtf": True, "timeframe": "main"},
    "Aggressive":   {"consensus_threshold": 2, "adx_threshold": 10, "enable_mtf": False, "timeframe": "main"},
    "Scalper":      {"consensus_threshold": 2, "adx_threshold": 5, "enable_mtf": False, "timeframe": "1m"}
}

for p_key, p_cfg in PROFILES_SIM_CFG.items():
    p_df = df_1m if p_cfg['timeframe'] == "1m" else df_main
    p_price = float(p_df.iloc[-1]['close'])
    p_atr = float(p_df.iloc[-1].get('ATR_14', 0.0))
    run_profile_tick(
        profile_name=p_key,
        df_profile=p_df,
        mtf_data_profile=mtf_data if p_cfg['enable_mtf'] else None,
        is_mtf_enabled=p_cfg['enable_mtf'],
        consensus_threshold=p_cfg['consensus_threshold'],
        adx_threshold=p_cfg['adx_threshold'],
        current_price=p_price,
        atr_val_raw=p_atr
    )

# Run custom profile tick if chosen
if profile_name == "Custom":
    run_profile_tick(
        profile_name=None, # None translates to default wallet files
        df_profile=df_main,
        mtf_data_profile=mtf_data if enable_mtf else None,
        is_mtf_enabled=enable_mtf,
        consensus_threshold=threshold,
        adx_threshold=adx_threshold,
        current_price=current_price,
        atr_val_raw=atr_val_raw
    )

# ═══════════════════════════════════════════════════════════════
# RETRIEVE ACTIVE STATE
# ═══════════════════════════════════════════════════════════════
active_profile_suffix = None if profile_name == "Custom" else profile_name
wallet = PaperWallet(initial_balance=INITIAL_BALANCE_INR, profile_name=active_profile_suffix)

# System Diagnostics & Import Validation Expander
with st.sidebar.expander("🛠️ System Diagnostics", expanded=True):
    import inspect
    st.write("**Wallet Module:**", PaperWallet.__module__)
    st.write("**Constructor:**", str(inspect.signature(PaperWallet.__init__)))
    st.write("**Wallet File:**", wallet.wallet_state_file)
    st.write("**Active Profile:**", profile_name)
    st.write("**Trading Mode:**", trading_mode)
    st.write("**Data Source:**", EXCHANGE_ID)
    st.write("**Timeframe:**", profile_timeframe)

df_active = df_1m if profile_name == "Scalper" else df_main
price_active = float(df_active.iloc[-1]['close'])
atr_active = float(df_active.iloc[-1].get('ATR_14', 0.0))

# ── Force trade test ──
if st.session_state.get('force_trade', False):
    st.session_state.force_trade = False
    executed, exec_msg, blk = wallet.execute_trade(
        'BUY', price_active, trading_mode=trading_mode, reason="Forced Test Trade", force=True
    )
    if executed:
        st.success(f"⚡ {exec_msg}")
    st.rerun()

# Get evaluation metrics for the active wallet display
votes, consensus, regime, adx_val, atr_val, vol_state, block_msg = evaluate_consensus(
    df_active, threshold=threshold, adx_threshold=adx_threshold, cooldown_candles_left=wallet.cooldown_remaining
)

# Apply active MTF
mtf_trends = {}
mtf_block = ""
if mtf_enabled and mtf_data:
    mtf_trends = evaluate_multi_timeframe(mtf_data)
    if consensus != "HOLD":
        confirmed, mtf_reason = check_mtf_confirmation(consensus, mtf_trends)
        if not confirmed:
            mtf_block = mtf_reason
            consensus = "HOLD"
            block_msg = mtf_reason

buy_votes  = list(votes.values()).count("BUY")
sell_votes = list(votes.values()).count("SELL")
hold_votes = list(votes.values()).count("HOLD")

# Live diagnostics metrics
diag_metrics = get_diagnostics_metrics(profile_name)

# ═══════════════════════════════════════════════════════════════
# MARKET REGIME BANNER
# ═══════════════════════════════════════════════════════════════
banner_class = "background: rgba(0, 230, 118, 0.15); border: 1px solid var(--primary); color: var(--primary);"
banner_text  = f"🟢 TRENDING MARKET (ADX {adx_val:.1f})"
if regime == "SIDEWAYS":
    banner_class = "background: rgba(41, 182, 246, 0.15); border: 1px solid var(--accent); color: var(--accent);"
    banner_text  = f"🔵 SIDEWAYS MARKET (ADX {adx_val:.1f})"
if vol_state == "HIGH VOLATILITY":
    banner_class = "background: rgba(255, 152, 0, 0.15); border: 1px solid #ff9800; color: #ffcc80;"
    banner_text  = f"🟠 HIGH VOLATILITY (ATR {atr_val:.2f})"
elif vol_state == "LOW VOLATILITY":
    banner_class = "background: rgba(158, 158, 158, 0.15); border: 1px solid #9e9e9e; color: #e0e0e0;"
    banner_text  = f"⚪ LOW VOLATILITY (ATR {atr_val:.2f})"

st.markdown(f'<div style="{banner_class} padding: 12px 24px; border-radius: 8px; font-size: 16px; font-weight: 700; margin-bottom: 20px; text-align: center;">{banner_text}</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# TABS DIVISION
# ═══════════════════════════════════════════════════════════════
tab_terminal, tab_lab = st.tabs(["📈 PRO TRADING TERMINAL", "🧪 STRATEGY LAB"])

# ═══════════════════════════════════════════════════════════════
# TAB 1: PRO TRADING TERMINAL
# ═══════════════════════════════════════════════════════════════
with tab_terminal:
    # ── HERO DASHBOARD ──
    trades_df  = load_csv(wallet.trades_log_file)
    journal_df = load_csv(wallet.trade_journal_file)
    analytics = compute_analytics(trades_df, wallet)
    perf_card = get_performance_card(trades_df, journal_df)
    health_color, health_text = get_strategy_health(trades_df)
    
    total_val = wallet.balance + wallet.get_unrealized_pnl(price_active)
    real_pnl = wallet.realized_pnl
    open_pos_str = "None"
    pos_pnl = 0.0
    
    if wallet.open_position:
        op = wallet.open_position
        dir_emoji = "▲" if op['action'] == 'BUY' else "▼"
        pos_pnl = wallet.get_unrealized_pnl(price_active)
        open_pos_str = f"{dir_emoji} {op['action']} {op['quantity']:.5f} BTC"

    h1, h2, h3, h4, h5 = st.columns(5)
    
    # Portfolio Card
    with h1:
        pnl_val = total_val - 5000.0
        pnl_class = "pnl-green" if pnl_val >= 0 else "pnl-red"
        pnl_arrow = "▲" if pnl_val >= 0 else "▼"
        st.markdown(f"""
        <div class="terminal-card">
            <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">Portfolio Value</div>
            <div style="font-size: 24px; font-weight: 700; color: var(--text-color); margin-top: 4px;">₹{total_val:,.2f}</div>
            <div class="{pnl_class}" style="font-size: 12px; font-weight: bold; margin-top: 4px;">{pnl_arrow} {analytics['total_return_pct']}%</div>
        </div>
        """, unsafe_allow_html=True)

    # Today's PnL
    with h2:
        tpnl = perf_card['profit_today']
        tpnl_class = "pnl-green" if tpnl >= 0 else "pnl-red"
        tpnl_arrow = "▲" if tpnl >= 0 else "▼"
        st.markdown(f"""
        <div class="terminal-card">
            <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">Today's Net Profit</div>
            <div style="font-size: 24px; font-weight: 700; color: var(--text-color); margin-top: 4px;">₹{tpnl:,.2f}</div>
            <div class="{tpnl_class}" style="font-size: 12px; font-weight: bold; margin-top: 4px;">{tpnl_arrow} Today's trades</div>
        </div>
        """, unsafe_allow_html=True)

    # Open Positions
    with h3:
        pos_color = "var(--primary)" if pos_pnl >= 0 else "var(--danger)"
        pos_lbl = "No Active Trade" if open_pos_str == "None" else open_pos_str
        st.markdown(f"""
        <div class="terminal-card">
            <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">Open Positions</div>
            <div style="font-size: 18px; font-weight: 700; color: var(--text-color); margin-top: 8px; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">{pos_lbl}</div>
            <div style="font-size: 12px; color: {pos_color}; font-weight: bold; margin-top: 6px;">uPnL: ₹{pos_pnl:,.2f}</div>
        </div>
        """, unsafe_allow_html=True)

    # Win Rate
    with h4:
        st.markdown(f"""
        <div class="terminal-card">
            <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">Win Rate (All Time)</div>
            <div style="font-size: 24px; font-weight: 700; color: var(--text-color); margin-top: 4px;">{analytics['win_rate']}%</div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Wins: {analytics['winning_trades']} / Losses: {analytics['losing_trades']}</div>
        </div>
        """, unsafe_allow_html=True)

    # Total Trades
    with h5:
        st.markdown(f"""
        <div class="terminal-card">
            <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">Total Trades Logs</div>
            <div style="font-size: 24px; font-weight: 700; color: var(--text-color); margin-top: 4px;">{analytics['total_trades']}</div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Avg Duration: {perf_card['avg_duration']}</div>
        </div>
        """, unsafe_allow_html=True)

    # ── TERMINAL LAYOUT ──
    col_left, col_right = st.columns([2.3, 1])

    with col_left:
        # CHART CARD
        st.markdown("""
        <div class="terminal-card" style="padding: 10px;">
            <div style="font-size: 14px; font-weight: bold; margin: 10px 10px 5px 10px; display: flex; align-items: center; gap: 8px;">
                <span>📈 TRADINGVIEW LIVE BTC CHART</span>
                <span style="background: rgba(0, 230, 118, 0.2); color: var(--primary); border: 1px solid var(--primary); font-size: 9px; font-weight: bold; border-radius: 4px; padding: 2px 6px;">LIVE FEED</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Build TradingView Style Chart
        fig = go.Figure(data=[go.Candlestick(
            x=df_active['timestamp_local'], open=df_active['open'], high=df_active['high'],
            low=df_active['low'], close=df_active['close'], name="BTC/USDT",
            increasing=dict(
                line=dict(color=theme_colors['up']),
                fillcolor=hex_to_rgba(theme_colors['up'], 0.15)
            ),
            decreasing=dict(
                line=dict(color=theme_colors['down']),
                fillcolor=hex_to_rgba(theme_colors['down'], 0.15)
            )
        )])
        
        # Overlay EMA 20 & 50
        fig.add_trace(go.Scatter(x=df_active['timestamp_local'], y=df_active['EMA_20'], name='EMA 20', line=dict(color=theme_colors['accent'], width=1.5)))
        fig.add_trace(go.Scatter(x=df_active['timestamp_local'], y=df_active['EMA_50'], name='EMA 50', line=dict(color='#ffd600', width=1.5, dash='dash')))
        
        # Overlay BUY / SELL / CLOSE Markers from trades log
        if not trades_df.empty:
            df_t = trades_df.copy()
            df_t['Timestamp'] = pd.to_datetime(df_t['Timestamp'])
            
            buys = df_t[df_t['Action'] == 'BUY']
            sells = df_t[df_t['Action'] == 'SELL']
            closes = df_t[df_t['Action'] == 'CLOSE']
            
            if not buys.empty:
                fig.add_trace(go.Scatter(
                    x=buys['Timestamp'], y=buys['Price'],
                    mode='markers', name='BUY (Entry)',
                    marker=dict(symbol='triangle-up', size=11, color='#00e676', line=dict(width=1, color='white'))
                ))
            if not sells.empty:
                fig.add_trace(go.Scatter(
                    x=sells['Timestamp'], y=sells['Price'],
                    mode='markers', name='SELL (Entry)',
                    marker=dict(symbol='triangle-down', size=11, color='#ff1744', line=dict(width=1, color='white'))
                ))
            if not closes.empty:
                fig.add_trace(go.Scatter(
                    x=closes['Timestamp'], y=closes['Price'],
                    mode='markers', name='CLOSE',
                    marker=dict(symbol='x', size=8, color='#ffffff', line=dict(width=1, color='white'))
                ))

        # SL / TP lines
        if wallet.open_position:
            sl_price, tp_price = wallet.compute_sl_tp(atr_active)
            if sl_price:
                fig.add_hline(y=sl_price, line_dash="dash", line_color=theme_colors['down'], annotation_text="Stop Loss (SL)", annotation_position="top left")
            if tp_price:
                fig.add_hline(y=tp_price, line_dash="dash", line_color=theme_colors['up'], annotation_text="Take Profit (TP)", annotation_position="top left")

        fig.update_layout(
            xaxis_rangeslider_visible=False,
            template="plotly_dark",
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color=theme_colors['text']),
            margin=dict(t=5, b=5, l=5, r=5),
            height=420,
            xaxis=dict(gridcolor='rgba(255,255,255,0.05)', showline=True, linecolor=card_border),
            yaxis=dict(gridcolor='rgba(255,255,255,0.05)', showline=True, linecolor=card_border)
        )
        # Candlestick colors are set directly in go.Candlestick() above
        st.plotly_chart(fig, use_container_width=True)
        
        # PORTFOLIO HEATMAP (last 10 closed PnL blocks)
        st.markdown('<div style="font-size: 13px; font-weight: bold; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px;">🟩 PORTFOLIO PERFORMANCE HEATMAP (LAST 10 CLOSED TRADES)</div>', unsafe_allow_html=True)
        
        if not trades_df.empty:
            closes_df = trades_df[trades_df['Action'] == 'CLOSE'].tail(10)
            if not closes_df.empty:
                h_cols = st.columns(10)
                for idx, (_, row) in enumerate(closes_df.iterrows()):
                    pnl = row['PnL']
                    box_color = "var(--primary)" if pnl > 0.0 else "var(--danger)" if pnl < -0.0 else "#ffd600"
                    box_bg = "rgba(0, 230, 118, 0.15)" if pnl > 0.0 else "rgba(255, 23, 68, 0.15)" if pnl < -0.0 else "rgba(255, 214, 0, 0.15)"
                    pnl_txt = f"+₹{pnl:,.2f}" if pnl > 0 else f"-₹{abs(pnl):,.2f}" if pnl < 0 else "₹0.00"
                    
                    with h_cols[idx]:
                        st.markdown(f"""
                        <div style="background: {box_bg}; border: 1px solid {box_color}; border-radius: 6px; padding: 6px; text-align: center;">
                            <div style="font-size: 9px; color: var(--text-muted);">{row['Timestamp'].split(' ')[1][:5]}</div>
                            <div style="font-size: 11px; font-weight: bold; color: {box_color}; margin-top: 2px;">{pnl_txt}</div>
                        </div>
                        """, unsafe_allow_html=True)
            else:
                st.info("No closed trades to display in portfolio heatmap yet.")
        else:
            st.info("No trade records found.")

        # DIAGNOSTICS & LOG DETAILS
        st.markdown('<div style="margin-top:20px;"></div>', unsafe_allow_html=True)
        st.subheader("🔍 Signal Diagnostics & Execution Blockers")
        
        # Block explanation box
        if block_msg or mtf_block:
            blocked_cause = mtf_block or block_msg
            st.warning(f"⚠️ **Trade execution blocked for current candle** | {blocked_cause}")
        elif consensus != "HOLD":
            st.success(f"🎉 **Consensus match ({consensus})** | Passed all filters. Ready/Executed!")
        else:
            st.info("ℹ️ No trade trigger | Consensus is HOLD (Market is Neutral/Sideways)")
            
        d_cols = st.columns(6)
        d_cols[0].metric("Potential Signals", diag_metrics['total_signals_today'])
        d_cols[1].metric("Blocked Consensus", diag_metrics['blocked_consensus_today'])
        d_cols[2].metric("Blocked ADX", diag_metrics['blocked_adx_today'])
        d_cols[3].metric("Blocked Volatility", diag_metrics['blocked_volatility_today'])
        d_cols[4].metric("Blocked Cooldown", diag_metrics['blocked_cooldown_today'])
        d_cols[5].metric("Actual Executed", diag_metrics['executed_today'])

    with col_right:
        # SIGNAL RADAR CARD
        st.markdown('<div class="terminal-card">', unsafe_allow_html=True)
        st.markdown('<div style="font-size: 13px; font-weight: bold; color: var(--text-muted); text-transform: uppercase; margin-bottom: 12px; display:flex; justify-content:space-between;"><span>📡 SIGNAL CONFLICT RADAR</span><span class="signal-hold">● CONSENSUS</span></div>', unsafe_allow_html=True)
        
        # Donut Radar Chart
        labels_radar = ['BUY', 'SELL', 'HOLD']
        values_radar = [buy_votes, sell_votes, hold_votes]
        colors_radar = [primary_color, danger_color, '#ffd600']
        
        fig_radar = go.Figure(data=[go.Pie(
            labels=labels_radar, values=values_radar, hole=.6,
            marker=dict(colors=colors_radar, line=dict(color=card_bg, width=2.5)),
            hoverinfo='label+percent',
            textinfo='value',
            textfont=dict(size=14, color='white')
        )])
        
        fig_radar.add_annotation(
            text=consensus, x=0.5, y=0.5, showarrow=False,
            font=dict(size=24, color='white', weight='bold')
        )
        
        fig_radar.update_layout(
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5),
            margin=dict(t=5, b=5, l=5, r=5),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            height=200,
            template="plotly_dark"
        )
        st.plotly_chart(fig_radar, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # INDICATORS TABLE CARD
        st.markdown('<div class="terminal-card">', unsafe_allow_html=True)
        st.markdown('<div style="font-size: 13px; font-weight: bold; color: var(--text-muted); text-transform: uppercase; margin-bottom: 12px;">🔬 COMPONENT INDICATORS FEED</div>', unsafe_allow_html=True)
        
        tbl = "<table style='width:100%;font-size:14px;border-collapse:collapse'>"
        tbl += f"<tr style='border-bottom:1px solid {card_border}'><th style='text-align:left;padding:6px;color:var(--text-muted)'>Indicator</th><th style='padding:6px;text-align:right;color:var(--text-muted)'>State</th></tr>"
        for k, v in votes.items():
            tbl += f"<tr style='border-bottom:1px solid rgba(255,255,255,0.02)'><td style='padding:6px;font-weight:600'>{k}</td><td style='padding:6px;text-align:right;'>{fmt(v)}</td></tr>"
        tbl += "</table>"
        st.markdown(tbl, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # POSITION RISK MONITOR
        st.markdown('<div class="terminal-card">', unsafe_allow_html=True)
        st.markdown('<div style="font-size: 13px; font-weight: bold; color: var(--text-muted); text-transform: uppercase; margin-bottom: 12px;">📍 ACTIVE POSITION MONITOR</div>', unsafe_allow_html=True)
        
        if wallet.open_position:
            p = wallet.open_position
            sl_pr, tp_pr = wallet.compute_sl_tp(atr_active)
            dur_min = wallet.time_in_trade()
            upnl_val = wallet.get_unrealized_pnl(price_active)
            upnl_pct = wallet.get_unrealized_pnl_pct(price_active)
            pos_side = "LONG ▲" if p['action'] == 'BUY' else "SHORT ▼"
            pos_color = "var(--primary)" if p['action'] == 'BUY' else "var(--danger)"
            
            st.markdown(f"""
            <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                <span style="color:var(--text-muted);">Direction</span>
                <span style="font-weight:bold; color:{pos_color};">{pos_side}</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                <span style="color:var(--text-muted);">Entry Price</span>
                <span style="font-weight:bold;">${p['price']:,.2f}</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                <span style="color:var(--text-muted);">Current Value</span>
                <span style="font-weight:bold;">${price_active:,.2f}</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                <span style="color:var(--text-muted);">Size</span>
                <span style="font-weight:bold;">{p['quantity']:.5f} BTC</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                <span style="color:var(--text-muted);">Stop Loss (ATR)</span>
                <span style="font-weight:bold; color:var(--danger);">${(sl_pr if sl_pr else 0):,.2f}</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                <span style="color:var(--text-muted);">Take Profit (RR 1:2)</span>
                <span style="font-weight:bold; color:var(--primary);">${(tp_pr if tp_pr else 0):,.2f}</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                <span style="color:var(--text-muted);">Unrealized PnL</span>
                <span style="font-weight:bold; color:{'var(--primary)' if upnl_val >=0 else 'var(--danger)'};">₹{upnl_val:,.2f} ({upnl_pct:.2f}%)</span>
            </div>
            <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                <span style="color:var(--text-muted);">Trade Duration</span>
                <span style="font-weight:bold; font-size:12px;">{dur_min}</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.caption("No open position for this profile.")
        st.markdown('</div>', unsafe_allow_html=True)

        # LIVE ACTIVITY FEED CARD
        st.markdown('<div class="terminal-card">', unsafe_allow_html=True)
        st.markdown('<div style="font-size: 13px; font-weight: bold; color: var(--text-muted); text-transform: uppercase; margin-bottom: 12px;">🔔 SYSTEM ALERTS & EVENT FEED</div>', unsafe_allow_html=True)
        
        notifs = get_recent_notifications(12)
        if notifs:
            feed_html = '<div style="max-height: 200px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px;">'
            for n in reversed(notifs):
                evt = n['event']
                msg = n['message']
                stamp = n['timestamp']
                
                badge_bg = "rgba(0, 230, 118, 0.1)" if "BUY" in evt or "PROFIT" in evt or "TRAILING" in evt else "rgba(255, 23, 68, 0.1)" if "SELL" in evt or "STOP" in evt else "rgba(158, 158, 158, 0.1)"
                badge_border = primary_color if "BUY" in evt or "PROFIT" in evt or "TRAILING" in evt else danger_color if "SELL" in evt or "STOP" in evt else "var(--text-muted)"
                
                feed_html += f"""
                <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.04); border-radius: 6px; padding: 6px 10px; display: flex; flex-direction: column; gap: 3px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-weight:bold; font-size:10px; background:{badge_bg}; border:1px solid {badge_border}; color:{badge_border}; padding:1px 4px; border-radius:3px; text-transform:uppercase;">{evt}</span>
                        <span style="font-size:9px; color:var(--text-muted);">{stamp}</span>
                    </div>
                    <div style="font-size:12px; color:var(--text-color);">{msg}</div>
                </div>
                """
            feed_html += '</div>'
            st.markdown(feed_html, unsafe_allow_html=True)
        else:
            st.caption("Waiting for system alerts...")
        st.markdown('</div>', unsafe_allow_html=True)

    # ── TRADE HISTORIES / LOG TABLES ──
    st.markdown('<div style="margin-top:20px;"></div>', unsafe_allow_html=True)
    tab_log, tab_journal, tab_daily = st.tabs(["📋 Complete Trade Log", "📔 Trade Journal", "📅 Daily Reports"])
    
    with tab_log:
        t_df = load_csv(wallet.trades_log_file)
        if not t_df.empty:
            st.dataframe(t_df.tail(25).iloc[::-1], use_container_width=True)
        else:
            st.info("Waiting for first trade to log...")
            
    with tab_journal:
        j_df = load_csv(wallet.trade_journal_file)
        if not j_df.empty:
            st.dataframe(j_df.tail(25).iloc[::-1], use_container_width=True)
        else:
            st.info("No journal records found.")
            
    with tab_daily:
        d_df = load_csv(wallet.daily_report_file)
        if not d_df.empty:
            st.dataframe(d_df.iloc[::-1], use_container_width=True)
        else:
            st.info("No daily aggregates logged yet.")

# ═══════════════════════════════════════════════════════════════
# TAB 2: STRATEGY LAB
# ═══════════════════════════════════════════════════════════════
with tab_lab:
    st.markdown("""
    <div class="terminal-card" style="padding:15px;">
        <div style="font-size:16px; font-weight:bold; color:var(--primary); text-transform:uppercase; margin-bottom:8px;">🧪 STRATEGY LAB MULTI-PROFILE COMPARISON</div>
        <div style="font-size:13px; color:var(--text-muted); line-height:1.4;">
            This module compares four parallel strategy profiles paper-trading side-by-side. 
            Each profile has an independent wallet starting with a budget of <b>₹5,000.00</b>. 
            All wallets execute concurrently on every incoming live tick.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Calculate metrics for all 4 profiles
    lab_results = []
    for key in ["Conservative", "Balanced", "Aggressive", "Scalper"]:
        p_w = PaperWallet(5000.0, key)
        t_df = load_csv(p_w.trades_log_file)
        j_df = load_csv(p_w.trade_journal_file)
        an = compute_analytics(t_df, p_w)
        p_card = get_performance_card(t_df, j_df)
        
        lab_results.append({
            'Profile': key,
            'Current Balance': f"₹{p_w.balance:,.2f}",
            'Net Profit': p_w.balance - 5000.0,
            'Win Rate': f"{an['win_rate']}%",
            'Total Trades': an['total_trades'],
            'Max Drawdown': f"{an['max_drawdown']}%",
            'Profit Factor': an['profit_factor'],
            'Avg Duration': p_card['avg_duration']
        })
        
    df_lab = pd.DataFrame(lab_results)
    
    # Render Comparison Dashboard
    st.subheader("📊 Comparative Performance Dashboard")
    st.dataframe(df_lab, use_container_width=True)
    
    # Leaderboard Ranking
    st.subheader("🥇 Profiles Leaderboard")
    df_sorted = df_lab.sort_values(by="Net Profit", ascending=False).reset_index(drop=True)
    
    rank_cols = st.columns(4)
    medals = ["🥇 Best Profile", "🥈 Second Profile", "🥉 Third Profile", "🏅 Fourth Profile"]
    rank_colors = ["#ffd700", "#c0c0c0", "#cd7f32", "#8e9ca8"]
    
    for rank_idx in range(len(df_sorted)):
        profile_row = df_sorted.iloc[rank_idx]
        medal = medals[rank_idx] if rank_idx < len(medals) else f"Rank {rank_idx+1}"
        col_color = rank_colors[rank_idx] if rank_idx < len(rank_colors) else "var(--text-muted)"
        net_profit_val = profile_row['Net Profit']
        p_sign = "+" if net_profit_val >= 0 else ""
        
        with rank_cols[rank_idx]:
            st.markdown(f"""
            <div style="background:{card_bg}; border: 2px solid {col_color}; border-radius:10px; padding:15px; text-align:center;">
                <div style="font-size:16px; font-weight:bold; color:{col_color};">{medal}</div>
                <div style="font-size:20px; font-weight:800; color:var(--text-color); margin-top:8px;">{profile_row['Profile']}</div>
                <div style="font-size:14px; font-weight:bold; color:{'var(--primary)' if net_profit_val >= 0 else 'var(--danger)'}; margin-top:6px;">{p_sign}₹{net_profit_val:,.2f}</div>
                <div style="font-size:11px; color:var(--text-muted); margin-top:4px;">Win Rate: {profile_row['Win Rate']} · Trades: {profile_row['Total Trades']}</div>
            </div>
            """, unsafe_allow_html=True)
            
    # Equity curve comparison overlay
    st.subheader("📈 Multi-Profile Equity Curve Overlay")
    fig_overlay = go.Figure()
    
    profile_colors = {
        'Conservative': '#ffd600', # Gold Yellow
        'Balanced': '#29b6f6',     # Sky Blue
        'Aggressive': '#ff1744',   # Crimson Red
        'Scalper': '#00e676'       # Emerald Green
    }
    
    has_curves = False
    for p_name in ["Conservative", "Balanced", "Aggressive", "Scalper"]:
        p_w = PaperWallet(5000.0, p_name)
        t_df = load_csv(p_w.trades_log_file)
        if not t_df.empty and 'Balance' in t_df.columns:
            has_curves = True
            fig_overlay.add_trace(go.Scatter(
                x=t_df['Timestamp'], y=t_df['Balance'],
                mode='lines+markers', name=p_name,
                line=dict(color=profile_colors[p_name], width=2)
            ))
            
    if has_curves:
        fig_overlay.add_hline(y=5000.0, line_dash="dash", line_color="gray")
        fig_overlay.update_layout(
            template="plotly_dark",
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(color=theme_colors['text']),
            margin=dict(t=10, b=10, l=10, r=10),
            height=360,
            xaxis=dict(gridcolor='rgba(255,255,255,0.03)'),
            yaxis=dict(gridcolor='rgba(255,255,255,0.03)')
        )
        st.plotly_chart(fig_overlay, use_container_width=True)
    else:
        st.info("Equity comparison chart will plot curves after the first simulated trades execute.")

    # Optimization Report Panel
    st.subheader("🎯 Optimizations & Top Profiles")
    
    # Compute leader profile metrics
    leaders = {
        'profitable': 'N/A', 'profitable_val': -999999.0,
        'active': 'N/A', 'active_val': -1,
        'winrate': 'N/A', 'winrate_val': -1.0,
        'drawdown': 'N/A', 'drawdown_val': 9999.0
    }
    
    for row_idx, row in df_lab.iterrows():
        name = row['Profile']
        net_prof = row['Net Profit']
        trades_cnt = row['Total Trades']
        w_rate = float(row['Win Rate'].replace('%',''))
        dd_pct = float(row['Max Drawdown'].replace('%',''))
        
        if net_prof > leaders['profitable_val']:
            leaders['profitable_val'] = net_prof
            leaders['profitable'] = name
            
        if trades_cnt > leaders['active_val']:
            leaders['active_val'] = trades_cnt
            leaders['active'] = name
            
        if w_rate > leaders['winrate_val']:
            leaders['winrate_val'] = w_rate
            leaders['winrate'] = name
            
        if dd_pct < leaders['drawdown_val'] and trades_cnt > 0:
            leaders['drawdown_val'] = dd_pct
            leaders['drawdown'] = name
            
    opt_cols = st.columns(4)
    
    with opt_cols[0]:
        st.markdown(f"""
        <div class="terminal-card" style="text-align:center;">
            <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">Most Profitable</div>
            <div style="font-size: 20px; font-weight: 800; color: var(--primary); margin-top: 8px;">{leaders['profitable']}</div>
            <div style="font-size: 13px; color: var(--text-color); margin-top: 4px;">Net: ₹{leaders['profitable_val']:+,.2f}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with opt_cols[1]:
        st.markdown(f"""
        <div class="terminal-card" style="text-align:center;">
            <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">Most Active</div>
            <div style="font-size: 20px; font-weight: 800; color: var(--accent); margin-top: 8px;">{leaders['active']}</div>
            <div style="font-size: 13px; color: var(--text-color); margin-top: 4px;">Trades Count: {leaders['active_val']}</div>
        </div>
        """, unsafe_allow_html=True)
        
    with opt_cols[2]:
        st.markdown(f"""
        <div class="terminal-card" style="text-align:center;">
            <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">Highest Win Rate</div>
            <div style="font-size: 20px; font-weight: 800; color: #ffd600; margin-top: 8px;">{leaders['winrate']}</div>
            <div style="font-size: 13px; color: var(--text-color); margin-top: 4px;">Win Rate: {leaders['winrate_val']}%</div>
        </div>
        """, unsafe_allow_html=True)
        
    with opt_cols[3]:
        st.markdown(f"""
        <div class="terminal-card" style="text-align:center;">
            <div style="font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;">Lowest Drawdown</div>
            <div style="font-size: 20px; font-weight: 800; color: var(--text-color); margin-top: 8px;">{leaders['drawdown']}</div>
            <div style="font-size: 13px; color: var(--text-color); margin-top: 4px;">Max Drawdown: {leaders['drawdown_val'] if leaders['drawdown_val'] < 9999.0 else 0.0}%</div>
        </div>
        """, unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# BACKTEST EXECUTION
# ═══════════════════════════════════════════════════════════════
st.markdown("---")
st.subheader("⏪ Historical Backtesting Engine")
if run_bt:
    period_map = {"Last 30 Days": 30, "Last 90 Days": 90, "Last 365 Days": 365}
    days  = period_map[bt_period]
    limit = min(days * 288, 1000)

    with st.spinner(f"Backtesting {profile_name} profile on historical candles..."):
        bt_df = adapter.fetch_ohlcv(SYMBOL, candle_interval, limit=limit)

    if bt_df is not None and not bt_df.empty:
        results = run_backtest(bt_df, threshold=threshold, adx_threshold=adx_threshold)
        save_backtest_results(results, bt_period)

        bt1, bt2, bt3, bt4, bt5 = st.columns(5)
        bt1.metric("Backtest Net Profit",   f"₹{results['net_profit']}")
        bt2.metric("Backtest Win Rate",     f"{results['win_rate']}%")
        bt3.metric("Max Drawdown",          f"{results['max_drawdown']}%")
        bt4.metric("Profit Factor",         results['profit_factor'])
        bt5.metric("Total Executions",      results['total_trades'])

        if not results['equity_curve'].empty:
            fig_bt = go.Figure(data=[go.Scatter(
                x=results['equity_curve']['ts'], y=results['equity_curve']['equity'],
                mode='lines', name='Equity Curve', line=dict(color='#ff9800', width=2)
            )])
            fig_bt.update_layout(
                title=f"Backtest Balance Curve — {bt_period}", 
                template="plotly_dark",
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(gridcolor='rgba(255,255,255,0.03)'),
                yaxis=dict(gridcolor='rgba(255,255,255,0.03)')
            )
            st.plotly_chart(fig_bt, use_container_width=True)
    else:
        st.error("Failed to fetch historical data for backtesting.")

# ═══════════════════════════════════════════════════════════════
# EXPORT ACTIONS
# ═══════════════════════════════════════════════════════════════
if exp_journal:
    jdf = load_csv(wallet.trade_journal_file)
    if not jdf.empty:
        st.download_button(f"⬇ Download {profile_name} Journal CSV", jdf.to_csv(index=False), f"journal_{profile_name}.csv", "text/csv")
    else:
        st.warning("No journal records to export.")

if exp_daily:
    drdf = load_csv(wallet.daily_report_file)
    if not drdf.empty:
        st.download_button(f"⬇ Download {profile_name} Daily Report CSV", drdf.to_csv(index=False), f"daily_report_{profile_name}.csv", "text/csv")
    else:
        st.warning("No daily aggregates to export.")

if exp_backtest:
    bdf = load_csv(BACKTEST_RESULTS_FILE)
    if not bdf.empty:
        st.download_button("⬇ Download Backtest Results CSV", bdf.to_csv(index=False), "backtest_results.csv", "text/csv")
    else:
        st.warning("No backtesting results available. Run a backtest first.")

# ═══════════════════════════════════════════════════════════════
# STREAMLIT TICK AUTO REFRESH
# ═══════════════════════════════════════════════════════════════
time.sleep(refresh_interval)
st.rerun()
