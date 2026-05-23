"""
GMC Sierra UAE Monitor — v1
Scrapes Dubizzle, OpenSooq, and YallaMotor for new GMC Sierra listings in the UAE.
Sends Telegram alerts for each new listing, deduped via seen_listings.json.
Runs every 15 minutes via GitHub Actions.
"""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import re
import sys
import json
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SEEN_FILE = Path("seen_listings.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
}

PRICE_PATTERN = re.compile(r"(AED|د\.إ|درهم)\s*[\d,]+", re.IGNORECASE)


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
        print("Telegram timeout, but message was likely delivered.")
        return True
    except Exception as e:
        print(f"Telegram error: {e}")
        return False


def format_listing_message(listing: dict) -> str:
    parts = [f"🚗 <b>New on {listing.get('source', '?')}</b>"]
    title = (listing.get("title") or "").strip()
    if title:
        parts.append(f"\n{title[:250]}")
    price = (listing.get("price") or "").strip()
    if price:
        parts.append(f"\n💰 {price}")
    url = listing.get("url") or ""
    if url:
        parts.append(f"\n\n🔗 {url}")
    return "".join(parts)


# --- Seen listings store ---
def load_seen() -> dict:
    if SEEN_FILE.exists():
        try:
            return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"ids": [], "first_run_complete": False}


def save_seen(seen: dict) -> None:
    seen["updated"] = datetime.now(timezone.utc).isoformat()
    SEEN_FILE.write_text(json.dumps(seen, indent=2), encoding="utf-8")


# --- Scrapers ---
def _extract_price_near(anchor) -> str:
    """Try to find an AED price string near a listing anchor."""
    node = anchor
    for _ in range(4):  # walk up a few levels
        node = node.find_parent() if node else None
        if not node:
            break
        text = node.get_text(" ", strip=True)
        m = PRICE_PATTERN.search(text)
        if m:
            return m.group(0)
    return ""


def scrape_dubizzle() -> list:
    listings = []
    url = "https://uae.dubizzle.com/motors/used-cars/gmc/sierra/?sort=date_desc"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        if "Just a moment" in r.text or "cloudflare" in r.text.lower()[:5000]:
            print("Dubizzle: blocked by Cloudflare")
            return []
        soup = BeautifulSoup(r.text, "lxml")
        seen_hrefs = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/motors/used-cars/" not in href or "sierra" not in href.lower():
                continue
            if href.count("/") < 5:  # heuristic to skip category pages
                continue
            if href in seen_hrefs:
                continue
            seen_hrefs.add(href)
            full_url = urljoin("https://uae.dubizzle.com", href)
            slug = href.rstrip("/").split("/")[-1]
            listings.append({
                "id": f"dubizzle_{slug}",
                "source": "Dubizzle",
                "title": a.get_text(strip=True)[:250] or "GMC Sierra",
                "url": full_url,
                "price": _extract_price_near(a),
            })
    except Exception as e:
        print(f"Dubizzle error: {e}")
    print(f"Dubizzle: found {len(listings)} listings")
    return listings


def scrape_opensooq() -> list:
    listings = []
    url = "https://uae.opensooq.com/en/find/cars-for-sale/all-cities/gmc-sierra"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        seen_hrefs = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/post/" not in href and "/item/" not in href:
                continue
            if "sierra" not in href.lower() and "gmc" not in href.lower():
                continue
            if href in seen_hrefs:
                continue
            seen_hrefs.add(href)
            full_url = urljoin("https://uae.opensooq.com", href)
            slug = href.rstrip("/").split("/")[-1]
            listings.append({
                "id": f"opensooq_{slug}",
                "source": "OpenSooq",
                "title": a.get_text(strip=True)[:250] or "GMC Sierra",
                "url": full_url,
                "price": _extract_price_near(a),
            })
    except Exception as e:
        print(f"OpenSooq error: {e}")
    print(f"OpenSooq: found {len(listings)} listings")
    return listings


def scrape_yallamotor() -> list:
    listings = []
    url = "https://uae.yallamotor.com/used-cars/gmc/sierra"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")
        seen_hrefs = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/used-cars/" not in href:
                continue
            if "sierra" not in href.lower() and "gmc" not in href.lower():
                continue
            if href.count("/") < 4:
                continue
            if href in seen_hrefs:
                continue
            seen_hrefs.add(href)
            full_url = urljoin("https://uae.yallamotor.com", href)
            slug = href.rstrip("/").split("/")[-1]
            listings.append({
                "id": f"yallamotor_{slug}",
                "source": "YallaMotor",
                "title": a.get_text(strip=True)[:250] or "GMC Sierra",
                "url": full_url,
                "price": _extract_price_near(a),
            })
    except Exception as e:
        print(f"YallaMotor error: {e}")
    print(f"YallaMotor: found {len(listings)} listings")
    return listings


# --- Main ---
def main():
    print(f"Starting monitor at {datetime.now(timezone.utc).isoformat()}")

    seen = load_seen()
    seen_ids = set(seen.get("ids", []))
    first_run = not seen.get("first_run_complete", False)
    print(f"Loaded {len(seen_ids)} previously seen listings | first_run={first_run}")

    all_listings = []
    all_listings.extend(scrape_dubizzle())
    all_listings.extend(scrape_opensooq())
    all_listings.extend(scrape_yallamotor())
    print(f"Total listings across all sources: {len(all_listings)}")

    new_listings = [l for l in all_listings if l["id"] not in seen_ids]
    print(f"New (not previously seen): {len(new_listings)}")

    by_source = {}
    for l in all_listings:
        by_source[l["source"]] = by_source.get(l["source"], 0) + 1

    if first_run:
        if len(all_listings) < 3:
            # Scrapers probably aren't working — don't lock in the first-run state yet.
            send_telegram_message(
                f"⚠️ <b>Monitor first run: only {len(all_listings)} listings found</b>\n\n"
                f"Dubizzle: {by_source.get('Dubizzle', 0)}\n"
                f"OpenSooq: {by_source.get('OpenSooq', 0)}\n"
                f"YallaMotor: {by_source.get('YallaMotor', 0)}\n\n"
                "<i>Scrapers may need adjustment. Will retry next cycle.</i>"
            )
            print("Too few listings — first run NOT marked complete. Will retry.")
            return
        # Healthy first run — catalog without alerting per listing.
        for l in all_listings:
            seen_ids.add(l["id"])
        send_telegram_message(
            f"🟢 <b>Monitor armed</b>\n\n"
            f"Catalogued <b>{len(all_listings)}</b> existing Sierra listings.\n"
            f"From now on you'll only get alerts for <i>new</i> ones.\n\n"
            f"Dubizzle: {by_source.get('Dubizzle', 0)}\n"
            f"OpenSooq: {by_source.get('OpenSooq', 0)}\n"
            f"YallaMotor: {by_source.get('YallaMotor', 0)}"
        )
        save_seen({"ids": sorted(seen_ids), "first_run_complete": True})
        print("First run complete.")
        return

    # Normal run — alert on each new listing.
    sent = 0
    for listing in new_listings:
        message = format_listing_message(listing)
        if send_telegram_message(message):
            seen_ids.add(listing["id"])
            sent += 1
            time.sleep(1)  # be polite to Telegram

    save_seen({"ids": sorted(seen_ids), "first_run_complete": True})
    print(f"Run complete. {sent} new alerts sent.")


if __name__ == "__main__":
    main()
