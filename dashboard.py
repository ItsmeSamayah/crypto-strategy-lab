"""
Professional Multi-Asset Trading Terminal with Advanced Strategy UI.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import os
import json
import importlib.util
from pathlib import Path
from datetime import datetime, timedelta

# Force load local config.py
config_path = Path(__file__).parent / "config.py"
spec = importlib.util.spec_from_file_location("local_config", config_path)
bot_config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot_config)

# Force load local strategy.py
strategy_path = Path(__file__).parent / "strategy.py"
spec_strat = importlib.util.spec_from_file_location("local_strategy", strategy_path)
bot_strategy = importlib.util.module_from_spec(spec_strat)
spec_strat.loader.exec_module(bot_strategy)

import ccxt
from indicators import calculate_indicators
from utils import get_active_strategy, save_active_strategy
from reset_engine import reset_paper_trading

# ═══════════════════════════════════════════════════════════════
# PAGE CONFIG & STYLING
# ═══════════════════════════════════════════════════════════════
st.set_page_config(page_title="Multi-Asset Pro Terminal", page_icon="⚡", layout="wide")

primary_color = "#00e676"  # Emerald Green
danger_color = "#ff1744"   # Crimson Red
accent_color = "#29b6f6"   # Electric Blue
bg_color = "#0a0e14"       # Dark Slate
card_bg = "#121820"
card_border = "#1c2530"
text_color = "#ffffff"
text_muted = "#8e9ca8"

st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Outfit:wght@400;600;800&display=swap');
  html, body, [class*="css"], .stApp {{ font-family: 'Outfit', sans-serif; }}
  .stApp {{ background-color: {bg_color} !important; color: {text_color} !important; }}
  
  .terminal-card {{
    background: {card_bg}; border: 1px solid {card_border}; border-radius: 12px;
    padding: 16px; margin-bottom: 16px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  }}
  .signal-buy  {{ color: {primary_color}; font-weight: 800; }}
  .signal-sell {{ color: {danger_color}; font-weight: 800; }}
  .signal-hold {{ color: #ffd600; font-weight: 800; }}
  .signal-side {{ color: {accent_color}; font-weight: 800; }}
  .big-consensus {{ font-size: 32px; font-weight: 900; letter-spacing: -0.5px; text-align: center; }}

  /* CSS Animations */
  @keyframes blink {{
    0% {{ opacity: 1; }}
    50% {{ opacity: 0.2; }}
    100% {{ opacity: 1; }}
  }}
  .live-dot {{
    color: {primary_color};
    animation: blink 1.2s infinite;
    font-weight: bold;
    display: inline-block;
  }}
  .live-pulse {{
    display: inline-block;
    border-radius: 50%;
    animation: blink 1.5s infinite;
  }}

  @keyframes pulse-glow {{
    0% {{ box-shadow: 0 0 5px rgba(0, 230, 118, 0.3); }}
    50% {{ box-shadow: 0 0 15px rgba(0, 230, 118, 0.7); }}
    100% {{ box-shadow: 0 0 5px rgba(0, 230, 118, 0.3); }}
  }}
  .status-bar-live {{
    animation: pulse-glow 2s infinite;
  }}

  @keyframes rotate-radar {{
    from {{ transform: rotate(0deg); }}
    to {{ transform: rotate(360deg); }}
  }}
  .radar-icon {{
    display: inline-block;
    animation: rotate-radar 2.5s linear infinite;
    color: {accent_color};
    font-size: 16px;
    line-height: 1;
  }}
</style>
""", unsafe_allow_html=True)

def fmt(val):
    if val == "BUY":  return f'<span class="signal-buy">▲ BUY</span>'
    if val == "SELL": return f'<span class="signal-sell">▼ SELL</span>'
    if val == "HOLD": return '<span class="signal-hold">● HOLD</span>'
    return f'<span class="signal-side">◈ {val}</span>'

def hex_to_rgba(hex_color, alpha=0.15):
    hex_color = hex_color.lstrip('#')
    return f"rgba({int(hex_color[0:2], 16)}, {int(hex_color[2:4], 16)}, {int(hex_color[4:6], 16)}, {alpha})"

# ═══════════════════════════════════════════════════════════════
# DATA LOADING HELPERS
# ═══════════════════════════════════════════════════════════════
@st.cache_data(ttl=5)
def fetch_market_data(symbol, timeframe="5m", limit=100):
    try:
        exchange_class = getattr(ccxt, bot_config.EXCHANGE_ID)
        exchange = exchange_class({'enableRateLimit': True})
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return calculate_indicators(df)
    except Exception as e:
        return pd.DataFrame()

def load_wallet(asset):
    path = os.path.join('data', 'wallets', f'wallet_{asset}.json')
    if os.path.exists(path):
        try:
            with open(path, 'r') as f: return json.load(f)
        except: pass
    return {"balance": bot_config.INITIAL_CAPITAL.get(asset, 5000), "realized_pnl": 0.0, "open_position": None}

def load_trades(asset):
    path = os.path.join('data', 'trades', f'trades_{asset}.csv')
    if os.path.exists(path):
        try: return pd.read_csv(path)
        except: pass
    return pd.DataFrame()

def load_journal(asset):
    path = os.path.join('data', 'trades', f'journal_{asset}.csv')
    if os.path.exists(path):
        try: return pd.read_csv(path)
        except: pass
    return pd.DataFrame()

def load_daily_report(asset):
    path = os.path.join('data', 'trades', f'daily_report_{asset}.csv')
    if os.path.exists(path):
        try: return pd.read_csv(path)
        except: pass
    return pd.DataFrame()

def get_stats(asset):
    w = load_wallet(asset)
    t = load_trades(asset)
    j = load_journal(asset)
    
    initial = bot_config.INITIAL_CAPITAL.get(asset, 5000)
    bal = w.get('balance', initial)
    net_pnl = bal - initial
    
    wr = 0.0
    total = 0
    pf = 0.0
    dd = 0.0
    
    if not j.empty and 'Profit/Loss' in j.columns:
        total = len(j)
        wins = len(j[j['Profit/Loss'] > 0])
        wr = (wins / total * 100) if total > 0 else 0.0
        
        gross_profit = j[j['Profit/Loss'] > 0]['Profit/Loss'].sum()
        gross_loss = abs(j[j['Profit/Loss'] < 0]['Profit/Loss'].sum())
        pf = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
        
    if not t.empty and 'Balance' in t.columns:
        peak = t['Balance'].cummax()
        drawdown = (t['Balance'] - peak) / peak * 100
        dd = drawdown.min()
        
    return {
        "asset": asset, "balance": bal, "net_pnl": net_pnl,
        "win_rate": wr, "trades": total, "pf": pf, "dd": dd,
        "wallet": w, "trades_df": t, "journal_df": j
    }

def get_scrolling_logs():
    log_path = 'bot.log'
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r') as f:
                lines = f.readlines()
            last_lines = lines[-12:]
            formatted = []
            for line in last_lines:
                parts = line.split(' - ')
                if len(parts) >= 3:
                    ts = parts[0].split(' ')[1].split(',')[0]
                    msg = parts[2].strip()
                    color = text_color
                    if "buy" in msg.lower() or "long" in msg.lower():
                        color = primary_color
                    elif "sell" in msg.lower() or "short" in msg.lower():
                        color = danger_color
                    elif "blocked" in msg.lower():
                        color = "#ffb300"
                    formatted.append(f'<div style="font-family: \'JetBrains Mono\', monospace; font-size: 11px; margin-bottom: 4px; color: {color};"><span style="color: {text_muted};">[{ts}]</span> {msg}</div>')
            return "".join(formatted)
        except: pass
    return '<div style="color: #8e9ca8;">Connecting to feed...</div>'

# ═══════════════════════════════════════════════════════════════
# STATE & ANIMATIONS PREPARATION
# ═══════════════════════════════════════════════════════════════
assets = [a.split('/')[0] for a in bot_config.ASSETS]
portfolio_stats = [get_stats(a) for a in assets]
df_portfolio = pd.DataFrame(portfolio_stats)

# 1. Pulse Color Determination
pulse_color = primary_color
for a in assets:
    t_df = load_trades(a)
    if not t_df.empty:
        try:
            last_trade = datetime.strptime(t_df.iloc[-1]['Timestamp'], "%Y-%m-%d %H:%M:%S")
            if (datetime.now() - last_trade).total_seconds() < 8:
                pulse_color = danger_color  # Red flash on execution
                break
        except: pass

# 2. Toast alerts for Executions
for a in assets:
    t_df = load_trades(a)
    if not t_df.empty and 'Timestamp' in t_df.columns:
        try:
            last_trade = datetime.strptime(t_df.iloc[-1]['Timestamp'], "%Y-%m-%d %H:%M:%S")
            if (datetime.now() - last_trade).total_seconds() < 6:
                act = t_df.iloc[-1]['Action']
                pr = t_df.iloc[-1]['Price']
                emoji = "🟢" if act == "BUY" else "🔴"
                st.toast(f"{emoji} {act} EXECUTED: {a} @ ${pr:,.2f}", icon="⚡")
        except: pass

# 3. Global Floating Status Bar
st.markdown(f"""
<div style="position: fixed; top: 10px; right: 50px; z-index: 99999;">
  <div class="status-bar-live" style="background: {card_bg}; border: 1px solid {primary_color}; border-radius: 8px; padding: 6px 12px; font-family: 'JetBrains Mono', monospace; font-size: 11px; display: flex; align-items: center; gap: 8px; color: {text_color};">
    <span class="live-dot" style="font-size: 14px;">●</span> <span>LIVE ANALYZING</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# TERMINAL HEADER
# ═══════════════════════════════════════════════════════════════
st.markdown(f"""
<div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
  <h1 style="margin: 0; font-family: 'Outfit', sans-serif; font-weight: 800;">⚡ Multi-Asset Pro Trading Terminal</h1>
  <span class="live-pulse" style="width: 12px; height: 12px; background-color: {pulse_color}; box-shadow: 0 0 10px {pulse_color}; margin-top: 10px;"></span>
</div>
""", unsafe_allow_html=True)

# Tabs
tab_names = ["🌐 Portfolio Overview"] + [f"{a} Terminal" for a in assets]
tabs = st.tabs(tab_names)

# ─── PORTFOLIO OVERVIEW ────────────────────────────────────────
with tabs[0]:
    st.markdown("### 🌐 Multi-Asset Portfolio Dashboard")
    
    total_capital = sum(bot_config.INITIAL_CAPITAL.values())
    total_current = df_portfolio['balance'].sum()
    total_pnl = total_current - total_capital
    pnl_pct = (total_pnl / total_capital) * 100
    total_trades = df_portfolio['trades'].sum()
    open_positions = sum(1 for m in portfolio_stats if m['wallet'].get('open_position'))
    
    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f'<div class="terminal-card"><h4>Total Capital</h4><h2>₹{total_capital:,.2f}</h2></div>', unsafe_allow_html=True)
    with c2: 
        c_color = primary_color if total_pnl >= 0 else danger_color
        st.markdown(f'<div class="terminal-card"><h4>Total Profit / Return</h4><h2 style="color:{c_color}">₹{total_pnl:,.2f} ({pnl_pct:.2f}%)</h2></div>', unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="terminal-card"><h4>Total Portfolio Trades</h4><h2>{total_trades}</h2></div>', unsafe_allow_html=True)
    with c4: st.markdown(f'<div class="terminal-card"><h4>Active Open Positions</h4><h2>{open_positions}</h2></div>', unsafe_allow_html=True)

    c_left, c_right = st.columns([1.5, 1])
    
    with c_left:
        st.markdown('<div class="terminal-card">', unsafe_allow_html=True)
        st.subheader("🏆 Asset Leaderboard")
        leaderboard_data = []
        for m in portfolio_stats:
            a = m['asset']
            w = m['wallet']
            strat = get_active_strategy(a)
            
            open_pos = "None"
            if w.get('open_position'):
                op = w['open_position']
                open_pos = f"{op.get('action','')} {op.get('quantity',0):.4f} @ ₹{op.get('price',0):.2f}"
                
            leaderboard_data.append({
                "Asset": a,
                "Active Strategy": strat,
                "Wallet Balance": f"₹{m['balance']:,.2f}",
                "Net Profit": f"₹{m['net_pnl']:,.2f}",
                "Win Rate": f"{m['win_rate']:.1f}%",
                "Trades Count": m['trades'],
                "Open Position": open_pos,
                "Drawdown": f"{m['dd']:.1f}%"
            })
        st.dataframe(pd.DataFrame(leaderboard_data), use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c_right:
        # Strategy Engine Activity Feed
        st.markdown('<div class="terminal-card" style="height: 100%;">', unsafe_allow_html=True)
        st.subheader("📡 Strategy Engine Activity Feed")
        log_html = get_scrolling_logs()
        st.markdown(f"""
        <div style="background-color: #06090d; border: 1px solid #1c2530; border-radius: 8px; padding: 12px; height: 180px; overflow-y: auto; box-shadow: inset 0 2px 8px rgba(0,0,0,0.8);">
          {log_html}
        </div>
        """, unsafe_allow_html=True)
        st.markdown('\u003c/div\u003e', unsafe_allow_html=True)

    # ─── RESET PAPER TRADING ─────────────────────────────────────
    st.markdown("---")
    st.markdown('<div class="terminal-card">', unsafe_allow_html=True)
    st.subheader("⚠️ Reset Paper Trading System")

    # Confirmation gate using session state
    if "confirm_reset" not in st.session_state:
        st.session_state.confirm_reset = False
    if "reset_done" not in st.session_state:
        st.session_state.reset_done = False
    if "reset_summary" not in st.session_state:
        st.session_state.reset_summary = None

    if st.session_state.reset_done and st.session_state.reset_summary:
        s = st.session_state.reset_summary
        st.markdown(f"""
        <div style="background:{hex_to_rgba(primary_color, 0.1)}; border: 1px solid {primary_color};
             border-radius: 10px; padding: 20px; text-align: center;">
          <div style="font-size: 28px; font-weight: 900; color: {primary_color};">✅ Paper Trading Reset Complete</div>
          <div style="margin-top: 16px; font-family: 'JetBrains Mono', monospace; font-size: 14px; color: {text_color};">
            <div>BTC Wallet: <b>₹{s['new_balances']['BTC']:,.2f}</b></div>
            <div>ETH Wallet: <b>₹{s['new_balances']['ETH']:,.2f}</b></div>
            <div>SOL Wallet: <b>₹{s['new_balances']['SOL']:,.2f}</b></div>
            <div style="margin-top:8px;">Total Capital: <b>₹{s['total_capital']:,.2f}</b></div>
            <div>Trades: <b>0</b> &nbsp;|&nbsp; PnL: <b>₹0.00</b></div>
            <div style="color:{text_muted}; font-size:11px; margin-top: 8px;">
              Archived to: {s['archive_path']}<br/>Reset at: {s['reset_at']}
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("🔄 Start New Session", key="start_new_session"):
            st.session_state.reset_done = False
            st.session_state.reset_summary = None
            st.session_state.confirm_reset = False
            st.rerun()
    elif st.session_state.confirm_reset:
        st.warning("⚠️ **Reset all paper trading data?** This action cannot be undone.")
        col_cancel, col_confirm = st.columns([1, 1])
        with col_cancel:
            if st.button("❌ Cancel", key="cancel_reset", use_container_width=True):
                st.session_state.confirm_reset = False
                st.rerun()
        with col_confirm:
            if st.button("🔴 Confirm Reset", key="confirm_reset_btn", use_container_width=True, type="primary"):
                with st.spinner("Archiving data and resetting wallets..."):
                    # Fetch live prices for position closure
                    live_prices = {}
                    try:
                        exchange_class = getattr(ccxt, bot_config.EXCHANGE_ID)
                        exchange = exchange_class({'enableRateLimit': True})
                        for sym in bot_config.ASSETS:
                            ticker = exchange.fetch_ticker(sym)
                            asset_key = sym.split('/')[0]
                            live_prices[asset_key] = ticker['last']
                    except Exception as e:
                        for a in assets:
                            live_prices[a] = 0.0
                    
                    summary = reset_paper_trading(live_prices)
                    st.session_state.reset_summary = summary
                    st.session_state.reset_done = True
                    st.session_state.confirm_reset = False
                st.rerun()
    else:
        st.markdown(f"""
        <div style="color: {text_muted}; font-size: 13px; margin-bottom: 12px;">
          Closes all positions at market price, archives trade logs, and restores all wallets to ₹5000 each.
          Strategy settings, risk settings, and preferences are <b>not</b> affected.
        </div>
        """, unsafe_allow_html=True)
        if st.button("⚠️ Reset Paper Trading", key="reset_btn", type="secondary"):
            st.session_state.confirm_reset = True
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

# ─── ASSET TERMINALS ───────────────────────────────────────────
for i, asset_symbol in enumerate(bot_config.ASSETS, start=1):
    asset = assets[i-1]
    with tabs[i]:
        st.markdown(f"### ⚡ {asset} Terminal")

        
        # Strategy Selector and Profile Config
        col_select, col_empty = st.columns([1.5, 3])
        with col_select:
            current_strat = get_active_strategy(asset)
            selected_strat = st.selectbox(
                f"Select Active Strategy Profile ({asset})",
                options=["Conservative", "Balanced", "Aggressive", "Scalper"],
                index=["Conservative", "Balanced", "Aggressive", "Scalper"].index(current_strat),
                key=f"strat_select_{asset}"
            )
            if selected_strat != current_strat:
                save_active_strategy(asset, selected_strat)
                st.success(f"Strategy changed to {selected_strat}!")
                st.rerun()
                
        p_cfg = bot_config.TRADING_PROFILES[selected_strat]
        stat = next(m for m in portfolio_stats if m['asset'] == asset)
        w = stat['wallet']
        
        # Real-time data processing
        df = fetch_market_data(asset_symbol)
        current_price = float(df.iloc[-1]['close']) if not df.empty else 0.0
        
        # Fetch & calculate MTF data
        mtf_data = {}
        for tf in bot_config.MTF_TIMEFRAMES:
            mtf_df = fetch_market_data(asset_symbol, tf, limit=50)
            if not mtf_df.empty:
                mtf_data[tf] = mtf_df
        mtf_trends = bot_strategy.evaluate_multi_timeframe(mtf_data)
        
        # Fetch BTC/USDT data for correlation filter if not BTC
        btc_df = None
        if asset != "BTC":
            btc_df = fetch_market_data("BTC/USDT")
            
        # Evaluate consensus live for the dashboard using new modules
        votes, consensus, regime, adx_val, atr_val, vol_state, block_msg, confidence_score, trade_quality = bot_strategy.evaluate_consensus(
            df, 
            threshold=p_cfg['consensus_threshold'], 
            adx_threshold=p_cfg['adx_threshold'], 
            cooldown_candles_left=w.get('cooldown_remaining', 0),
            mtf_trends=mtf_trends,
            btc_df=btc_df,
            asset_name=asset
        )
        
        # Portfolio KPIs Row
        p_pnl = stat['net_pnl']
        p_pnl_c = primary_color if p_pnl >= 0 else danger_color
        kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
        with kpi1: st.markdown(f'<div class="terminal-card"><h5>Current Price</h5><h3>${current_price:,.2f}</h3></div>', unsafe_allow_html=True)
        with kpi2: st.markdown(f'<div class="terminal-card"><h5>Wallet Balance</h5><h3>₹{stat["balance"]:,.2f}</h3></div>', unsafe_allow_html=True)
        with kpi3: st.markdown(f'<div class="terminal-card"><h5>Net Profit</h5><h3 style="color:{p_pnl_c}">₹{p_pnl:,.2f}</h3></div>', unsafe_allow_html=True)
        with kpi4: st.markdown(f'<div class="terminal-card"><h5>Win Rate</h5><h3>{stat["win_rate"]:.1f}%</h3></div>', unsafe_allow_html=True)
        with kpi5: st.markdown(f'<div class="terminal-card"><h5>Total Trades</h5><h3>{stat["trades"]}</h3></div>', unsafe_allow_html=True)
        
        # Main Layout
        colL, colR = st.columns([2, 1])
        
        with colL:
            st.markdown('<div class="terminal-card">', unsafe_allow_html=True)
            
            # Live Data Refresh Indicator
            st.markdown(f"""
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
              <div style="display: flex; align-items: center; gap: 5px;">
                <span class="live-dot">●</span>
                <span style="font-size: 11px; font-weight: bold; color: {primary_color}; letter-spacing: 0.5px;">LIVE FEED</span>
              </div>
              <div style="font-size: 10px; color: {text_muted}; font-family: 'JetBrains Mono', monospace;">
                Last Refresh: {datetime.now().strftime('%H:%M:%S')}
              </div>
            </div>
            """, unsafe_allow_html=True)
            
            st.subheader(f"📊 Market Candlestick Chart ({bot_config.TIMEFRAME})")
            
            if not df.empty:
                fig = go.Figure(data=[go.Candlestick(
                    x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
                    increasing_line_color=primary_color, decreasing_line_color=danger_color
                )])
                
                op = w.get('open_position')
                if op:
                    ep = op['price']
                    fig.add_hline(y=ep, line_dash="dash", line_color=accent_color, annotation_text=f"Entry: {ep}")
                    sl_d = atr_val * bot_config.ATR_SL_MULTIPLIER
                    tp_d = sl_d * bot_config.RISK_REWARD_RATIO
                    if op['action'] == 'BUY':
                        fig.add_hline(y=ep-sl_d, line_dash="dot", line_color=danger_color, annotation_text="SL")
                        fig.add_hline(y=ep+tp_d, line_dash="dot", line_color=primary_color, annotation_text="TP")
                    else:
                        fig.add_hline(y=ep+sl_d, line_dash="dot", line_color=danger_color, annotation_text="SL")
                        fig.add_hline(y=ep-tp_d, line_dash="dot", line_color=primary_color, annotation_text="TP")
                
                fig.update_layout(template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0,r=0,t=0,b=0), height=400, xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            
            # Trade Journal & Daily Report
            st.markdown('<div class="terminal-card">', unsafe_allow_html=True)
            tab_logs, tab_reports = st.tabs(["📓 Trade Journal", "📅 Daily Reports"])
            
            with tab_logs:
                j_df = stat['journal_df']
                if not j_df.empty:
                    st.dataframe(j_df.tail(20).iloc[::-1], use_container_width=True, hide_index=True)
                else:
                    st.write("No trades logged yet.")
            
            with tab_reports:
                rep_df = load_daily_report(asset)
                if not rep_df.empty:
                    st.dataframe(rep_df.tail(20).iloc[::-1], use_container_width=True, hide_index=True)
                else:
                    st.write("No daily reports generated yet.")
            st.markdown('</div>', unsafe_allow_html=True)
            
        with colR:
            # Consensus Engine
            st.markdown('<div class="terminal-card">', unsafe_allow_html=True)
            st.subheader("⚙️ Consensus Engine")
            
            # Animated consensus wheel
            st.markdown(f"""
            <div style="display: flex; align-items: center; justify-content: center; gap: 8px; margin-bottom: 12px;">
              <span class="radar-icon">🔄</span>
              <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: {accent_color}; font-weight: bold; letter-spacing: 0.5px;">RUNNING ENGINE... 100%</span>
            </div>
            """, unsafe_allow_html=True)
            
            sig_html = fmt(consensus)
            st.markdown(f'<div class="big-consensus" style="padding:15px; border-bottom:1px solid {card_border}; margin-bottom:15px;">{sig_html}</div>', unsafe_allow_html=True)
            
            # AI Confidence Score display
            score_color = primary_color if confidence_score >= bot_config.CONFIDENCE_THRESHOLD else text_muted
            st.markdown(f"""
            <div style="margin-bottom: 15px; background-color: #06090d; border: 1px solid #1c2530; border-radius: 8px; padding: 12px; text-align: center;">
              <div style="font-size: 11px; color: {text_muted}; text-transform: uppercase; letter-spacing: 0.5px;">AI Confidence Score</div>
              <div style="font-size: 28px; font-weight: 800; color: {score_color}; font-family: 'JetBrains Mono', monospace;">
                {confidence_score}<span style="font-size: 14px; color: {text_muted};">/100</span>
              </div>
              <div style="font-size: 11px; color: {text_color}; font-weight: bold; margin-top: 4px;">
                Quality: <span style="color: {score_color};">{trade_quality}</span>
              </div>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"<div style='color:{text_muted}; font-size:11px; margin-bottom:5px; font-weight: bold;'>SIGNAL CONFLICT RADAR</div>", unsafe_allow_html=True)
            for ind, vote in votes.items():
                st.markdown(f"<div style='display:flex; justify-content:space-between; font-family:\"JetBrains Mono\"; margin-bottom:4px;'><span>{ind}</span> {fmt(vote)}</div>", unsafe_allow_html=True)
                
            st.markdown("---")
            
            # ADX / ATR Regime Analysis
            st.markdown("#### 🔍 Smart Market Regime")
            
            reg_color = accent_color if regime == 'TRENDING' else (primary_color if regime == 'RANGING' else danger_color)
            st.markdown(f"**Detected Regime:** <span style='color:{reg_color}; font-weight:bold;'>{regime}</span>", unsafe_allow_html=True)
            
            # Display active ruleset based on regime
            if regime == "TRENDING":
                active_rule = "EMA/MACD Trend Following active"
            elif regime == "RANGING":
                active_rule = "RSI/Bollinger mean-reversion active"
            else:
                active_rule = "ATR Volatility Breakout active"
            st.markdown(f"<div style='font-size: 11px; color: {accent_color}; font-style: italic; margin-bottom: 8px;'>🔧 {active_rule}</div>", unsafe_allow_html=True)
            
            st.markdown(f"**ADX:** {adx_val:.2f} ({'Trending' if adx_val >= p_cfg['adx_threshold'] else 'Sideways'})")
            st.markdown(f"**Volatility:** {vol_state} (ATR: {atr_val:.2f})")
            
            # Correlation Filter Status
            st.markdown("---")
            st.markdown("#### 🌐 BTC Correlation Filter")
            if asset == "BTC":
                st.markdown('<span style="color: #00e676; font-weight:bold;">🟢 MASTER ASSET (Not Filtered)</span>', unsafe_allow_html=True)
            else:
                btc_status = "🟢 PASSED"
                if block_msg and "correlation" in block_msg.lower():
                    btc_status = "🔴 BLOCKED"
                st.markdown(f"Status: <span style='font-weight:bold;'>{btc_status}</span>", unsafe_allow_html=True)
                
            if block_msg:
                st.error(f"🛡️ **System Status:** {block_msg}")
            
            st.markdown("---")
            
            # Open Position Monitor
            st.markdown("#### Active Position Monitor")
            op = w.get('open_position')
            if op:
                act = op['action']
                ep = op['price']
                qty = op['quantity']
                upnl = (current_price - ep) * qty if act == 'BUY' else (ep - current_price) * qty
                upnl_c = primary_color if upnl >= 0 else danger_color
                st.markdown(f"""
                <div style="background:{hex_to_rgba(accent_color, 0.1)}; border:1px solid {accent_color}; padding:10px; border-radius:8px;">
                    <div style="color:{accent_color}; font-weight:bold;">{act} {qty:.4f} @ ${ep:.2f}</div>
                    <div style="color:{upnl_c}; font-size:18px; font-weight:bold;">uPnL: ₹{upnl:.2f}</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.info("No active position.")
            st.markdown('</div>', unsafe_allow_html=True)
            
            # Trade History Log
            st.markdown('<div class="terminal-card">', unsafe_allow_html=True)
            st.subheader("📜 Recent Trade Signals")
            t_df = load_trades(asset)
            if not t_df.empty:
                st.dataframe(t_df.tail(10).iloc[::-1][['Timestamp', 'Action', 'Price', 'PnL', 'Reason']], use_container_width=True, hide_index=True)
            else:
                st.write("No signals logged yet.")
            st.markdown('</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# FOOTER STATUS
# ═══════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown(f"""
<div style="display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: {text_muted}; padding: 10px 0; font-family: 'JetBrains Mono', monospace;">
  <div>Market Feed: <span style="color: {primary_color}; font-weight: bold;">🟢 Connected</span></div>
  <div>Exchange: <span>Binance Data Feed (Paper Mode)</span></div>
  <div>Assets: <span>BTC | ETH | SOL</span></div>
  <div>Strategies Running: <span>3 Active</span></div>
  <div>Last Tick: <span>{datetime.now().strftime('%H:%M:%S')}</span></div>
</div>
""", unsafe_allow_html=True)
