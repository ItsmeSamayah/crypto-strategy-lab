"""
Paper Wallet — persistent simulation wallet with ATR-based SL/TP,
trailing stop, trade journal, daily report, and cooldown.
"""
import csv
import os
import json
from datetime import datetime, date
from logger import logger
from notifications import notify, EVENT_BUY, EVENT_SELL, EVENT_STOP_LOSS, EVENT_TAKE_PROFIT, EVENT_TRAILING
from config import (
    TRADES_LOG_FILE, WALLET_STATE_FILE, TRADE_JOURNAL_FILE, DAILY_REPORT_FILE,
    RISK_PER_TRADE_PERCENT, STOP_LOSS_PERCENT, TAKE_PROFIT_PERCENT,
    ATR_SL_MULTIPLIER, RISK_REWARD_RATIO, TRAILING_STOP_ATR, COOLDOWN_CANDLES
)


class PaperWallet:
    def __init__(self, initial_balance: float, asset_name: str = None, profile_name: str = None):
        self.asset_name = asset_name
        self.profile_name = profile_name
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.open_position = None
        self.realized_pnl = 0.0
        self.cooldown_remaining = 0
        self._journal_entry = None

        # Ensure data directories exist
        os.makedirs(os.path.join('data', 'wallets'), exist_ok=True)
        os.makedirs(os.path.join('data', 'trades'), exist_ok=True)
        
        # Build suffix
        suffix = ""
        if asset_name and profile_name:
            suffix = f"_{asset_name}_{profile_name}"
        elif asset_name:
            suffix = f"_{asset_name}"
        elif profile_name:
            suffix = f"_{profile_name}"

        # Dynamically set filenames based on suffix
        self.wallet_state_file = os.path.join('data', 'wallets', f"wallet{suffix}.json") if suffix else WALLET_STATE_FILE
        self.trades_log_file = os.path.join('data', 'trades', f"trades{suffix}.csv") if suffix else TRADES_LOG_FILE
        self.trade_journal_file = os.path.join('data', 'trades', f"journal{suffix}.csv") if suffix else TRADE_JOURNAL_FILE
        self.daily_report_file = os.path.join('data', 'trades', f"daily_report{suffix}.csv") if suffix else DAILY_REPORT_FILE

        self.load_from_json()

        self._init_csv(self.trades_log_file,
                       ['Timestamp', 'Action', 'Price', 'Quantity', 'Balance', 'PnL', 'Reason'])
        self._init_csv(self.trade_journal_file,
                       ['Timestamp', 'Action', 'Entry Price', 'Exit Price',
                        'Quantity', 'Profit/Loss', 'Profit %', 'Trade Duration', 'Signal Reason'])
        self._init_csv(self.daily_report_file,
                       ['Date', 'Starting Balance', 'Ending Balance',
                        'Trades', 'Wins', 'Losses', 'Net Profit'])

    # ── PERSISTENCE ──────────────────────────────────────────
    def load_from_json(self):
        if os.path.exists(self.wallet_state_file):
            try:
                with open(self.wallet_state_file, 'r') as f:
                    data = json.load(f)
                self.balance            = data.get('balance', self.initial_balance)
                self.open_position      = data.get('open_position', None)
                self.realized_pnl       = data.get('realized_pnl', 0.0)
                self.cooldown_remaining = data.get('cooldown_remaining', 0)
                self._journal_entry     = data.get('journal_entry', None)
            except Exception as e:
                logger.error(f"Failed to load wallet state: {e}")

    def save_to_json(self):
        data = {
            'balance':            self.balance,
            'open_position':      self.open_position,
            'realized_pnl':       self.realized_pnl,
            'cooldown_remaining': self.cooldown_remaining,
            'journal_entry':      self._journal_entry,
        }
        with open(self.wallet_state_file, 'w') as f:
            json.dump(data, f, indent=4)

    # ── CSV HELPERS ──────────────────────────────────────────
    @staticmethod
    def _init_csv(path, headers):
        if not os.path.exists(path):
            with open(path, 'w', newline='') as f:
                csv.writer(f).writerow(headers)

    def _log_trade(self, action, price, quantity, pnl, reason):
        with open(self.trades_log_file, 'a', newline='') as f:
            csv.writer(f).writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                action, price, quantity, round(self.balance, 4), round(pnl, 4), reason
            ])

    def _log_journal(self, entry):
        with open(self.trade_journal_file, 'a', newline='') as f:
            csv.writer(f).writerow(entry)

    # ── TICK ─────────────────────────────────────────────────
    def tick_cooldown(self):
        if self.cooldown_remaining > 0:
            self.cooldown_remaining -= 1
            self.save_to_json()

    # ── PnL ──────────────────────────────────────────────────
    def get_unrealized_pnl(self, current_price: float) -> float:
        if not self.open_position:
            return 0.0
        ep  = self.open_position['price']
        qty = self.open_position['quantity']
        return (current_price - ep) * qty if self.open_position['action'] == 'BUY' \
            else (ep - current_price) * qty

    def get_unrealized_pnl_pct(self, current_price: float) -> float:
        if not self.open_position:
            return 0.0
        ep   = self.open_position['price']
        qty  = self.open_position['quantity']
        cost = ep * qty
        return (self.get_unrealized_pnl(current_price) / cost) * 100 if cost else 0.0

    def time_in_trade(self) -> str:
        if not self.open_position or 'opened_at' not in self.open_position:
            return "N/A"
        try:
            opened = datetime.fromisoformat(self.open_position['opened_at'])
            delta  = datetime.now() - opened
            total_s = int(delta.total_seconds())
            h, rem  = divmod(total_s, 3600)
            m, s    = divmod(rem, 60)
            return f"{h}h {m}m {s}s"
        except Exception:
            return "N/A"

    def time_in_trade_minutes(self) -> float:
        if not self.open_position or 'opened_at' not in self.open_position:
            return 0.0
        try:
            opened = datetime.fromisoformat(self.open_position['opened_at'])
            return (datetime.now() - opened).total_seconds() / 60.0
        except Exception:
            return 0.0

    # ── ATR-BASED SL/TP ─────────────────────────────────────
    def compute_sl_tp(self, atr_val: float):
        """
        Compute ATR-based stop-loss and take-profit prices.
        Returns (sl_price, tp_price) or (None, None) if no position.
        """
        if not self.open_position or atr_val <= 0:
            return None, None

        ep   = self.open_position['price']
        act  = self.open_position['action']
        sl_d = atr_val * ATR_SL_MULTIPLIER
        tp_d = sl_d * RISK_REWARD_RATIO

        if act == 'BUY':
            sl = ep - sl_d
            tp = ep + tp_d
        else:
            sl = ep + sl_d
            tp = ep - tp_d

        # Override SL if trailing stop has moved it to breakeven
        if self.open_position.get('trailing_sl') is not None:
            sl = self.open_position['trailing_sl']

        return round(sl, 2), round(tp, 2)

    def check_sl_tp(self, current_price: float, atr_val: float = 0.0) -> bool:
        """Check ATR-based SL/TP and trailing stop."""
        if not self.open_position:
            return False

        ep  = self.open_position['price']
        act = self.open_position['action']

        # ── Trailing stop: move SL to breakeven after +1 ATR ──
        if atr_val > 0 and self.open_position.get('trailing_sl') is None:
            if act == 'BUY' and (current_price - ep) >= atr_val * TRAILING_STOP_ATR:
                self.open_position['trailing_sl'] = ep  # breakeven
                self.save_to_json()
                notify(EVENT_TRAILING, f"Trailing stop activated — SL moved to breakeven ${ep:.2f}")
            elif act == 'SELL' and (ep - current_price) >= atr_val * TRAILING_STOP_ATR:
                self.open_position['trailing_sl'] = ep
                self.save_to_json()
                notify(EVENT_TRAILING, f"Trailing stop activated — SL moved to breakeven ${ep:.2f}")

        sl, tp = self.compute_sl_tp(atr_val)

        # ATR-based SL/TP
        if sl is not None and tp is not None:
            if act == 'BUY':
                if current_price <= sl:
                    self.close_position(current_price, "Stop Loss (ATR)")
                    notify(EVENT_STOP_LOSS, f"Stop Loss hit at ${current_price:.2f}")
                    return True
                if current_price >= tp:
                    self.close_position(current_price, "Take Profit (ATR)")
                    notify(EVENT_TAKE_PROFIT, f"Take Profit hit at ${current_price:.2f}")
                    return True
            else:
                if current_price >= sl:
                    self.close_position(current_price, "Stop Loss (ATR)")
                    notify(EVENT_STOP_LOSS, f"Stop Loss hit at ${current_price:.2f}")
                    return True
                if current_price <= tp:
                    self.close_position(current_price, "Take Profit (ATR)")
                    notify(EVENT_TAKE_PROFIT, f"Take Profit hit at ${current_price:.2f}")
                    return True

        # Fallback percentage-based SL/TP
        pnl_pct = (current_price - ep) / ep * 100 if act == 'BUY' else (ep - current_price) / ep * 100
        if pnl_pct <= -STOP_LOSS_PERCENT:
            self.close_position(current_price, "Stop Loss (%)")
            notify(EVENT_STOP_LOSS, f"Stop Loss (%) hit at ${current_price:.2f}")
            return True
        if pnl_pct >= TAKE_PROFIT_PERCENT:
            self.close_position(current_price, "Take Profit (%)")
            notify(EVENT_TAKE_PROFIT, f"Take Profit (%) hit at ${current_price:.2f}")
            return True

        return False

    # ── TRADE EXECUTION ──────────────────────────────────────
    def _calc_quantity(self, price: float) -> float:
        risk_amount = self.balance * (RISK_PER_TRADE_PERCENT / 100.0)
        quantity    = risk_amount / (price * (STOP_LOSS_PERCENT / 100.0))
        return min(quantity, self.balance / price)

    def execute_trade(self, action: str, current_price: float,
                      trading_mode: str = "Long Only",
                      reason: str = "Consensus",
                      force: bool = False):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if force:
            if self.open_position:
                self.close_position(current_price, "Forced Close")
            qty = self._calc_quantity(current_price)
            self.open_position = {
                'action': 'BUY', 'price': current_price,
                'quantity': qty, 'opened_at': datetime.now().isoformat(),
                'trailing_sl': None,
            }
            self._journal_entry = {
                'opened_at': now, 'action': 'BUY',
                'entry_price': current_price, 'quantity': qty, 'reason': reason
            }
            self._log_trade('BUY', current_price, qty, 0.0, reason)
            self.cooldown_remaining = 0
            self.save_to_json()
            notify(EVENT_BUY, f"Forced BUY @ ${current_price:.2f}")
            return True, "Forced BUY executed", ""

        if action == 'BUY':
            if not self.open_position:
                qty = self._calc_quantity(current_price)
                self.open_position = {
                    'action': 'BUY', 'price': current_price,
                    'quantity': qty, 'opened_at': datetime.now().isoformat(),
                    'trailing_sl': None,
                }
                self._journal_entry = {
                    'opened_at': now, 'action': 'BUY',
                    'entry_price': current_price, 'quantity': qty, 'reason': reason
                }
                self._log_trade('BUY', current_price, qty, 0.0, reason)
                self.save_to_json()
                notify(EVENT_BUY, f"BUY (Long) @ ${current_price:.2f}")
                return True, "BUY executed (Opened Long)", ""

            elif self.open_position['action'] == 'SELL':
                self.close_position(current_price, reason)
                notify(EVENT_BUY, f"BUY closed Short @ ${current_price:.2f}")
                return True, "BUY executed (Closed Short)", ""
            else:
                return False, "", "BUY ignored — Long already open"

        elif action == 'SELL':
            if not self.open_position:
                if trading_mode == "Long + Short":
                    qty = self._calc_quantity(current_price)
                    self.open_position = {
                        'action': 'SELL', 'price': current_price,
                        'quantity': qty, 'opened_at': datetime.now().isoformat(),
                        'trailing_sl': None,
                    }
                    self._journal_entry = {
                        'opened_at': now, 'action': 'SELL',
                        'entry_price': current_price, 'quantity': qty, 'reason': reason
                    }
                    self._log_trade('SELL', current_price, qty, 0.0, reason)
                    self.save_to_json()
                    notify(EVENT_SELL, f"SELL (Short) @ ${current_price:.2f}")
                    return True, "SELL executed (Opened Short)", ""
                else:
                    return False, "SELL ignored — no open position (Long Only)", \
                           "Long Only mode blocks Shorts"

            elif self.open_position['action'] == 'BUY':
                self.close_position(current_price, reason)
                notify(EVENT_SELL, f"SELL closed Long @ ${current_price:.2f}")
                return True, "SELL executed (Closed Long)", ""
            else:
                return False, "", "SELL ignored — Short already open"

        return False, "", "Unknown state"

    def close_position(self, current_price: float, reason: str = "Consensus"):
        if not self.open_position:
            return
        ep     = self.open_position['price']
        qty    = self.open_position['quantity']
        action = self.open_position['action']
        opened_at = self.open_position.get('opened_at', '')

        pnl = (current_price - ep) * qty if action == 'BUY' else (ep - current_price) * qty
        self.balance      += pnl
        self.realized_pnl += pnl

        if self._journal_entry:
            entry_price = self._journal_entry.get('entry_price', ep)
            cost = entry_price * qty
            pnl_pct = (pnl / cost) * 100 if cost else 0.0
            duration = "N/A"
            if opened_at:
                try:
                    delta = datetime.now() - datetime.fromisoformat(opened_at)
                    duration = f"{int(delta.total_seconds() // 60)} min"
                except Exception:
                    pass
            self._log_journal([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                action, round(entry_price, 2), round(current_price, 2),
                round(qty, 6), round(pnl, 4), round(pnl_pct, 2),
                duration, self._journal_entry.get('reason', reason)
            ])

        logger.info(f"Closed {action} @ {current_price:.2f} | PnL: {pnl:.4f} | Reason: {reason}")
        self._log_trade('CLOSE', current_price, qty, pnl, reason)
        self._update_daily_report(pnl)

        self.open_position      = None
        self._journal_entry     = None
        self.cooldown_remaining = COOLDOWN_CANDLES
        self.save_to_json()

    def _update_daily_report(self, pnl: float):
        today = date.today().isoformat()
        rows  = []
        found = False

        if os.path.exists(self.daily_report_file):
            with open(self.daily_report_file, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['Date'] == today:
                        row['Ending Balance'] = round(self.balance, 4)
                        row['Trades']     = int(row['Trades'])  + 1
                        row['Wins']       = int(row['Wins'])    + (1 if pnl > 0 else 0)
                        row['Losses']     = int(row['Losses'])  + (1 if pnl <= 0 else 0)
                        row['Net Profit'] = round(float(row['Net Profit']) + pnl, 4)
                        found = True
                    rows.append(row)

        if not found:
            rows.append({
                'Date':             today,
                'Starting Balance': round(self.balance - pnl, 4),
                'Ending Balance':   round(self.balance, 4),
                'Trades': 1, 'Wins': 1 if pnl > 0 else 0,
                'Losses': 1 if pnl <= 0 else 0,
                'Net Profit': round(pnl, 4),
            })

        with open(self.daily_report_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'Date', 'Starting Balance', 'Ending Balance',
                'Trades', 'Wins', 'Losses', 'Net Profit'])
            writer.writeheader()
            writer.writerows(rows)

    def get_status(self, current_price: float) -> str:
        if self.open_position:
            action = self.open_position['action']
            entry  = self.open_position['price']
            qty    = self.open_position['quantity']
            upnl   = self.get_unrealized_pnl(current_price)
            typ    = "Long" if action == "BUY" else "Short"
            return f"{typ} {qty:.6f} @ {entry:.2f} (uPnL: {upnl:.4f})"
        return "None"
