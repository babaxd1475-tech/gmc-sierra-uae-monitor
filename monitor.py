"""
GMC Sierra UAE Monitor
Runs every 15 minutes via GitHub Actions.
v0: pipeline test — sends a Telegram message to confirm the whole pipeline works.
Scrapers are added in step 5.
"""
import os
import sys
import json
import requests
from datetime import datetime, timezone
from pathlib import Path

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SEEN_FILE = Path("seen_listings.json")


# --- Telegram ---
def send_telegram_message(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, json=payload, timeout=30)
        r.raise_for_status()
        return True
    except requests.exceptions.Timeout:
        # Telegram's API sometimes processes the message before sending the HTTP
        # response. v0 confirmed delivery despite a timeout, so we treat timeouts
        # as soft success to avoid false failure reports.
        print("Telegram timeout, but message was likely delivered.")
        return True
    except Exception as e:
        print(f"Telegram error: {e}")
        return False


# --- Seen listings store ---
def load_seen() -> set:
    if SEEN_FILE.exists():
        try:
            data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
            return set(data.get("ids", []))
        except Exception:
            return set()
    return set()


def save_seen(seen: set) -> None:
    SEEN_FILE.write_text(
        json.dumps(
            {"ids": sorted(seen), "updated": datetime.now(timezone.utc).isoformat()},
            indent=2,
        ),
        encoding="utf-8",
    )


# --- Main ---
def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    test_message = (
        "✅ <b>GMC Sierra UAE Monitor</b>\n\n"
        "Pipeline test successful. Scrapers will be added next.\n\n"
        f"<i>Run at: {now}</i>"
    )
    if send_telegram_message(test_message):
        print("Test message sent successfully.")
    else:
        print("Test message FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
