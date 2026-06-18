"""
Paper Trading Reset Engine
Handles archival, position closure, and fresh wallet creation.
Never touches live-trading settings or strategy configuration.
"""
import os
import json
import shutil
import csv
from datetime import datetime
from pathlib import Path

WALLETS_DIR = Path("data") / "wallets"
TRADES_DIR  = Path("data") / "trades"
ARCHIVE_ROOT = Path("data") / "archive"

ASSETS = ["BTC", "ETH", "SOL"]
INITIAL_CAPITAL = {"BTC": 5000, "ETH": 5000, "SOL": 5000}

WALLET_FILES = [f"wallet_{a}.json" for a in ASSETS]
TRADES_FILES = [f"trades_{a}.csv" for a in ASSETS]
JOURNAL_FILES = [f"journal_{a}.csv" for a in ASSETS]
REPORT_FILES  = [f"daily_report_{a}.csv" for a in ASSETS]

ACTIVE_STRATEGIES_FILE = Path("data") / "active_strategies.json"


def get_archive_path() -> Path:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
    return ARCHIVE_ROOT / ts


def archive_all_data() -> str:
    """Move all current trading data into a timestamped archive folder. Returns the archive path."""
    archive_path = get_archive_path()
    archive_path.mkdir(parents=True, exist_ok=True)

    all_files = (
        WALLET_FILES + TRADES_FILES + JOURNAL_FILES + REPORT_FILES
    )

    for fname in all_files:
        for base_dir in [WALLETS_DIR, TRADES_DIR]:
            src = base_dir / fname
            if src.exists():
                shutil.copy2(src, archive_path / fname)

    # Also archive root-level CSVs
    root_csvs = [
        "trades.csv", "trade_journal.csv", "daily_report.csv",
        "signal_history.csv", "diagnostics.csv"
    ]
    for fname in root_csvs:
        src = Path(fname)
        if src.exists():
            shutil.copy2(src, archive_path / fname)

    return str(archive_path)


def close_open_position(wallet_path: Path, asset_name: str, current_price: float) -> str | None:
    """
    If a wallet has an open position, close it at the given market price and update the wallet JSON.
    Returns a status message or None.
    """
    if not wallet_path.exists():
        return None

    with open(wallet_path, "r") as f:
        data = json.load(f)

    pos = data.get("open_position")
    if not pos:
        return None

    action = pos["action"]
    entry  = pos["price"]
    qty    = pos["quantity"]

    if action == "BUY":
        pnl = (current_price - entry) * qty
    else:
        pnl = (entry - current_price) * qty

    data["balance"] = round(data.get("balance", INITIAL_CAPITAL[asset_name]) + pnl, 4)
    data["realized_pnl"] = round(data.get("realized_pnl", 0.0) + pnl, 4)
    data["open_position"] = None
    data["cooldown_remaining"] = 0

    with open(wallet_path, "w") as f:
        json.dump(data, f, indent=4)

    return f"{asset_name}: closed {action} @ ${current_price:.2f} | PnL ₹{pnl:.2f}"


def write_fresh_wallet(asset: str) -> None:
    """Write a clean wallet JSON with initial capital."""
    WALLETS_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "balance": INITIAL_CAPITAL[asset],
        "open_position": None,
        "realized_pnl": 0.0,
        "cooldown_remaining": 0,
        "journal_entry": None
    }
    with open(WALLETS_DIR / f"wallet_{asset}.json", "w") as f:
        json.dump(data, f, indent=4)


def write_fresh_csv(path: Path, headers: list[str]) -> None:
    """Write an empty CSV with headers only."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        csv.writer(f).writerow(headers)


def reset_paper_trading(current_prices: dict[str, float]) -> dict:
    """
    Full paper-trading reset:
      1. Archive existing data
      2. Close open positions at provided market prices
      3. Write fresh wallets and empty CSVs

    Returns a summary dict with archive path and new wallet balances.
    """
    # Step 1: Archive
    archive_path = archive_all_data()

    # Step 2: Close open positions (best-effort, data already archived)
    closure_log = []
    for asset in ASSETS:
        wallet_path = WALLETS_DIR / f"wallet_{asset}.json"
        price = current_prices.get(asset, 0.0)
        msg = close_open_position(wallet_path, asset, price)
        if msg:
            closure_log.append(msg)

    # Step 3: Fresh wallets
    for asset in ASSETS:
        write_fresh_wallet(asset)

    # Step 4: Empty CSVs
    for asset in ASSETS:
        write_fresh_csv(
            TRADES_DIR / f"trades_{asset}.csv",
            ["Timestamp", "Action", "Price", "Quantity", "Balance", "PnL", "Reason"]
        )
        write_fresh_csv(
            TRADES_DIR / f"journal_{asset}.csv",
            ["Timestamp", "Action", "Entry Price", "Exit Price",
             "Quantity", "Profit/Loss", "Profit %", "Trade Duration", "Signal Reason"]
        )
        write_fresh_csv(
            TRADES_DIR / f"daily_report_{asset}.csv",
            ["Date", "Starting Balance", "Ending Balance", "Trades", "Wins", "Losses", "Net Profit"]
        )

    return {
        "archive_path": archive_path,
        "closure_log": closure_log,
        "new_balances": {a: INITIAL_CAPITAL[a] for a in ASSETS},
        "total_capital": sum(INITIAL_CAPITAL.values()),
        "reset_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
