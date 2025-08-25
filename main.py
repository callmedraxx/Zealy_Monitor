import os
import requests
from concurrent.futures import ThreadPoolExecutor
import time
import threading
import logging
from dotenv import load_dotenv

load_dotenv()

# Optional Telegram notifications (set via environment variables)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage" if TELEGRAM_BOT_TOKEN else None



# runtime knobs
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "2"))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "10"))

# 🔧 CONFIGURABLE COMMUNITY NAME
community = "reef"  # ← Change this to any community slug like "teneo", "fermionprotocol", etc.

# ⛓️ Dynamically Construct URLs
api_url = f"https://api-v1.zealy.io/communities/{community}/questboard/v2"
quest_detail_url_template = f"https://api-v1.zealy.io/communities/{community}/quests/v2/{{quest_id}}"

claim_url_template = f"https://api-v1.zealy.io/communities/{community}/quests/v2/{{quest_id}}/claim"
frontend_url = f"https://zealy.io/cw/{community}/questboard/{{box_id}}/{{quest_id}}"

# 🔎 Filters
params = {
    "filters": ["locked", "available", "inCooldown", "inReview"]
}

# 🔐 DEFAULT HEADERS (will be copied per-account; replace Cookie per account)
headers = {
    "Host": "api-v1.zealy.io",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"https://zealy.io/cw/{community}/questboard",
    "X-Zealy-Subdomain": community,
    "Origin": "https://zealy.io",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Sec-Ch-Ua": '"Not)A;Brand";v="8", "Chromium";v="138"',
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Accept-Encoding": "gzip, deflate, br",
    "X-Next-App-Key": "",
    "Cookie": ''  # placeholder; per-account sessions will set this
}

def send_telegram_message(text: str) -> None:
    """Send a message to the configured Telegram chat. No-op if not configured."""
    if not TELEGRAM_API or not TELEGRAM_CHAT_ID:
       
        return
    try:
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
        resp = requests.post(TELEGRAM_API, data=payload, timeout=10)
        if resp.status_code != 200:
           logging.warning("Telegram API returned %s: %s", resp.status_code, resp.text)
    except Exception as exc:
        logging.exception("Failed to send Telegram message: %s", exc)

def make_session_with_cookie(cookie_value: str):
    """Return a requests.Session with default headers and a Cookie value."""
    sess = requests.Session()
    sess.headers.update(headers)
    if cookie_value:
        sess.headers.update({"Cookie": cookie_value})
    return sess

def parse_accounts_env():
    """Parse accounts from environment.

    Priority:
      1) Per-account env vars: ACCOUNT_1_NAME / ACCOUNT_1_COOKIE ... ACCOUNT_N_NAME / ACCOUNT_N_COOKIE
      2) Fallback single account using headers Cookie
    """
    accounts = []

    # 1) per-account env vars (ACCOUNT_1_NAME / ACCOUNT_1_COOKIE ...)
    for i in range(1, 21):
        name_key = f"ACCOUNT_{i}_NAME"
        cookie_key = f"ACCOUNT_{i}_COOKIE"
        name = os.getenv(name_key)
        cookie = os.getenv(cookie_key)
        if not name and not cookie:
            continue
        if cookie:
            cookie = cookie.strip()
            # strip surrounding quotes if present
            if (cookie.startswith('"') and cookie.endswith('"')) or (cookie.startswith("'") and cookie.endswith("'")):
                cookie = cookie[1:-1]
        accounts.append({"name": name or f"account_{i}", "cookie": cookie or ""})

    # If no accounts found, try to use the default cookie from headers
    if not accounts:
        default_cookie = headers.get("Cookie", "")
        if default_cookie:
            accounts.append({"name": "default_account", "cookie": default_cookie})

    return accounts

def claim_and_notify_for_account(session, account_name, box_id, quest_id, task_id, quest_title, frontend_url_local):
    """Use provided session to claim and notify; include account_name in messages."""
    claim_url = claim_url_template.format(quest_id=quest_id)
    payload = {"taskValues": [{"taskId": task_id, "type": "tweetReact", "tweetUrl": ""}]}
    try:
        res = session.post(claim_url, json=payload, timeout=10)
        if res.status_code == 200:
            msg = f"✅ [{account_name}] Claimed: {quest_title}"
            logging.info(msg)
            send_telegram_message(msg)
        else:
            msg = f"❌ [{account_name}] Failed to claim: {quest_title} → {res.status_code} → {res.text}\nURL: {frontend_url_local}"
            logging.warning(msg)
            send_telegram_message(msg)
    except Exception as e:
        msg = f"❌ [{account_name}] Error claiming {quest_title}: {e}\nURL: {frontend_url_local}"
        logging.exception(msg)
        send_telegram_message(msg)

def monitor_account(account):
    """Run the monitoring loop for a single account.

    account: dict with keys 'name' and 'cookie'
    """
    account_name = account.get("name")
    print(f"Starting monitor for account: {account_name}")
    account_cookie = account.get("cookie")
    print(f"Using cookie: {account_cookie[:30]}... (length {len(account_cookie)})")
    session = make_session_with_cookie(account_cookie)
    seen_local = set()
    executor_local = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    local_fetch_count = 1

    while True:
        try:
            logging.info("[%s] Fetching.... Attempt #%d", account_name, local_fetch_count)
            local_fetch_count += 1
            resp = session.get(api_url, params=params, timeout=10)
            logging.debug("[%s] Response: %s", account_name, resp.text[:200] + "..." if len(resp.text) > 200 else resp.text)
            if resp.status_code != 200:
                logging.warning("[%s] Error fetching questboard: %s", account_name, resp.status_code)
                time.sleep(POLL_INTERVAL)
                continue

            data = resp.json()
            for box in data:
                box_id = box.get("id")
                quests = box.get("quests", [])

                for quest in quests:
                    quest_id = quest.get("id")
                    quest_title = quest.get("name")
                    if not quest_id or quest_id in seen_local:
                        continue

                    detail_url = quest_detail_url_template.format(quest_id=quest_id)
                    frontend = frontend_url.format(box_id=box_id, quest_id=quest_id)
                    detail_res = session.get(detail_url, timeout=10)
                    if detail_res.status_code != 200:
                        continue

                    tasks = detail_res.json().get("tasks", [])
                    for task in tasks:
                        task_id = task.get("id")
                        task_type = task.get("type")
                        message = f"[{account_name}] Found task: {quest_title}\nType: {task_type}\nURL: {frontend}"
                        logging.info(message)
                        send_telegram_message(message)

                        if task_type == "tweetReact":
                            logging.info("[%s] Claiming: %s", account_name, quest_title)
                            seen_local.add(quest_id)
                            executor_local.submit(claim_and_notify_for_account, session, account_name, box_id, quest_id, task_id, quest_title, frontend)
                        else:
                            logging.info("[%s] Non-tweetReact task: %s", account_name, quest_title)

        except Exception as e:
            logging.exception("[%s] General error: %s", account_name, e)
            send_telegram_message(f"[{account_name}] General error: {e}")

        time.sleep(POLL_INTERVAL)

def main():
    """Main function to start the bot."""
    print("🚀 Starting Zealy Bot...")
    
    # Parse accounts from environment
    accounts = parse_accounts_env()
    
    if not accounts:
        print("❌ No accounts found! Please set up environment variables:")
        print("   ACCOUNT_1_NAME=MyAccount")
        print("   ACCOUNT_1_COOKIE=your_cookie_here")
        print("   (or ACCOUNT_2_NAME, ACCOUNT_2_COOKIE, etc. for multiple accounts)")
        return
    
    print(f"✅ Found {len(accounts)} account(s):")
    for i, acc in enumerate(accounts, 1):
        cookie_preview = acc['cookie'][:50] + "..." if len(acc['cookie']) > 50 else acc['cookie']
        print(f"   {i}. {acc['name']} (cookie: {cookie_preview})")
    
    # Start monitoring each account in a separate thread
    threads = []
    for account in accounts:
        thread = threading.Thread(target=monitor_account, args=(account,), daemon=True)
        thread.start()
        threads.append(thread)
        print(f"✅ Started monitoring thread for: {account['name']}")
    
    try:
        # Keep main thread alive
        while True:
            time.sleep(60)  # Check every minute
            # Optional: Check if all threads are still alive
            alive_threads = [t for t in threads if t.is_alive()]
            if len(alive_threads) != len(threads):
                print(f"⚠️  Warning: {len(threads) - len(alive_threads)} thread(s) died!")
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")

if __name__ == "__main__":
    main()