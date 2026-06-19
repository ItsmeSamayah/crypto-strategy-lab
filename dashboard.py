import streamlit as st
import pandas as pd
import json
import csv
from pathlib import Path
import ccxt
import datetime
import time

# --- Configuration ---
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
WALLETS_DIR = DATA_DIR / "wallets"
TRADES_DIR = DATA_DIR / "trades"

# Ensure directories exist
for p in [WALLETS_DIR, TRADES_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# Asset definitions
ASSETS = [
    {"symbol": "BTC/USDT", "name": "BTC", "initial_capital": 5000},
    {"symbol": "ETH/USDT", "name": "ETH", "initial_capital": 5000},
    {"symbol": "SOL/USDT", "name": "SOL", "initial_capital": 5000},
]

# Binance exchange via ccxt (public endpoints only)
binance = ccxt.binance({"enableRateLimit": True})

# --- Helper Functions ---
def fetch_market_data(symbol: str, limit: int = 100):
    """Fetch recent OHLCV candles for a symbol.
    Returns a DataFrame with columns: timestamp, open, high, low, close, volume.
    """
    try:
        ohlcv = binance.fetch_ohlcv(symbol, timeframe='1m', limit=limit)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        st.error(f"Failed to fetch market data for {symbol}: {e}")
        return None

def generate_signal(df: pd.DataFrame) -> str:
    """Simple SMA crossover signal.
    Returns 'buy', 'sell' or 'hold'.
    """
    if df is None or df.empty:
        return "hold"
    df["sma_short"] = df["close"].rolling(window=5).mean()
    df["sma_long"] = df["close"].rolling(window=20).mean()
    if df["sma_short"].iloc[-1] > df["sma_long"].iloc[-1]:
        return "buy"
    elif df["sma_short"].iloc[-1] < df["sma_long"].iloc[-1]:
        return "sell"
    else:
        return "hold"

def load_wallet(name: str, initial_capital: float) -> dict:
    wallet_file = WALLETS_DIR / f"wallet_{name}.json"
    if wallet_file.exists():
        try:
            with open(wallet_file) as f:
                data = json.load(f)
            return data
        except Exception:
            return {"balance": initial_capital, "position": 0, "last_price": None}
    else:
        return {"balance": initial_capital, "position": 0, "last_price": None}

def save_wallet(name: str, wallet: dict):
    wallet_file = WALLETS_DIR / f"wallet_{name}.json"
    with open(wallet_file, "w") as f:
        json.dump(wallet, f, indent=2)

def log_trade(name: str, side: str, price: float, amount: float, timestamp: str):
    trades_file = TRADES_DIR / f"trades_{name}.csv"
    file_exists = trades_file.exists()
    with open(trades_file, "a", newline="") as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow(["timestamp", "side", "price", "amount"])
        writer.writerow([timestamp, side, price, amount])

def execute_trade(name: str, signal: str, price: float, wallet: dict):
    # Very naive execution: whole balance used for buy, full position sold on sell
    if signal == "buy" and wallet["position"] == 0:
        amount = wallet["balance"] / price
        wallet["position"] = amount
        wallet["balance"] = 0
        wallet["last_price"] = price
        timestamp = datetime.datetime.utcnow().isoformat()
        log_trade(name, "buy", price, amount, timestamp)
    elif signal == "sell" and wallet["position"] > 0:
        proceeds = wallet["position"] * price
        amount = wallet["position"]
        wallet["balance"] = proceeds
        wallet["position"] = 0
        wallet["last_price"] = price
        timestamp = datetime.datetime.utcnow().isoformat()
        log_trade(name, "sell", price, amount, timestamp)
    # else hold – nothing to do
    return wallet

# --- Streamlit UI ---
st.set_page_config(page_title="Multi‑Asset Portfolio Dashboard", layout="wide")
st.title("📊 Multi‑Asset Portfolio Dashboard")

# Auto‑refresh every 30 seconds
st.experimental_set_query_params()
st.autorefresh(interval=30_000, limit=None, key="dashboard_refresh")

# Loading spinner while fetching and processing data
with st.spinner("Fetching live market data & updating portfolio…"):
    wallets = {}
    for asset in ASSETS:
        name = asset["name"]
        wallet = load_wallet(name, asset["initial_capital"])  # load or initialise
        df = fetch_market_data(asset["symbol"], limit=100)
        if df is not None:
            signal = generate_signal(df)
            latest_price = df["close"].iloc[-1]
            wallet = execute_trade(name, signal, latest_price, wallet)
        else:
            latest_price = wallet.get("last_price", 0)
        save_wallet(name, wallet)
        wallets[name] = wallet["balance"] + wallet.get("position", 0) * latest_price

# Portfolio summary
total_value = sum(wallets.values())
total_initial = sum(a["initial_capital"] for a in ASSETS)
total_pnl = total_value - total_initial

col1, col2, col3 = st.columns(3)
col1.metric("Total Portfolio Value (INR)", f"{total_value:,.2f}")
col2.metric("Total PnL (INR)", f"{total_pnl:,.2f}")

# Total trades metric
total_trades = 0
for asset in ASSETS:
    trades_file = TRADES_DIR / f"trades_{asset['name']}.csv"
    if trades_file.exists():
        try:
            df = pd.read_csv(trades_file)
            total_trades += len(df)
        except Exception:
            pass
col3.metric("Total Trades", total_trades)

st.subheader("Asset Summary")
summary_rows = []
for asset in ASSETS:
    name = asset["name"]
    init = asset["initial_capital"]
    bal = wallets.get(name, init)
    net = bal - init
    summary_rows.append({"Asset": name, "Balance (INR)": bal, "Net Profit (INR)": net})
summary_df = pd.DataFrame(summary_rows)
st.dataframe(summary_df)

st.subheader("Asset Leaderboard")
leaderboard = summary_df.sort_values(by="Net Profit (INR)", ascending=False).reset_index(drop=True)
st.table(leaderboard)

st.caption("Dashboard now fetches live Binance data, generates signals, updates wallets, and logs trades automatically every 30 seconds.")
