"""
Notification Framework — Telegram placeholder.
Does NOT actually connect. Logs notification intent locally.
"""
from datetime import datetime
from logger import logger
from config import TELEGRAM_ENABLED, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


# All notification event types the system can fire
EVENT_BUY        = "BUY"
EVENT_SELL       = "SELL"
EVENT_STOP_LOSS  = "STOP_LOSS"
EVENT_TAKE_PROFIT = "TAKE_PROFIT"
EVENT_TRAILING   = "TRAILING_STOP"

# In-memory log of recent notifications (displayed in dashboard)
_notification_log: list[dict] = []


def notify(event: str, message: str):
    """
    Queue a notification for display.
    If Telegram is enabled in the future, this is where the send call goes.
    """
    entry = {
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'event':     event,
        'message':   message,
    }
    _notification_log.append(entry)

    # Keep last 50 entries in memory
    if len(_notification_log) > 50:
        _notification_log.pop(0)

    logger.info(f"[NOTIFICATION] [{event}] {message}")

    # ── Telegram stub ──
    if TELEGRAM_ENABLED:
        _send_telegram(message)


def _send_telegram(message: str):
    """
    Placeholder for future Telegram integration.
    When ready, replace the body with:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message})
    """
    logger.info(f"[TELEGRAM STUB] Would send: {message}")


def get_recent_notifications(n: int = 10) -> list[dict]:
    """Return the last n notifications."""
    return _notification_log[-n:]
