import os
import requests
from concurrent.futures import ThreadPoolExecutor
import time
import threading
import logging
import json
from dotenv import load_dotenv
from flask import Flask, request, render_template_string

load_dotenv()

app = Flask(__name__)

# Global dict to store sessions per account
sessions = {}

# Optional Telegram notifications (set via environment variables)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage" if TELEGRAM_BOT_TOKEN else None

  

# runtime knobs
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "2"))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "10"))

# 🔧 CONFIGURABLE COMMUNITY NAME
community = "reef"  # ← Change this to any community slug like "teneo", "fermion protocol "

# ⛓️ Dynamically Construct URLs
api_url = f"https://api-v1.zealy.io/communities/{community}/questboard/v2"
quest_detail_url_template = f"https://api-v1.zealy.io/communities/{community}/quests/v2/{{quest_id}}"

claim_url_template = f"https://api-v1.zealy.io/communities/{community}/quests/v2/{{quest_id}}/claim"
frontend_url = f"https://zealy.io/cw/{community}/questboard/{{box_id}}/{{quest_id}}"
file_upload = f"https://api-v1.zealy.io/files"

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

    import time
    max_retries = 3
    base_delay = 2

    for attempt in range(max_retries):
        try:
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
            # Increased timeout and added retry logic
            resp = requests.post(TELEGRAM_API, data=payload, timeout=30)
            if resp.status_code == 200:
                return  # Success, exit function
            else:
                logging.warning("Telegram API returned %s: %s (attempt %d/%d)",
                              resp.status_code, resp.text, attempt + 1, max_retries)
        except requests.exceptions.RequestException as exc:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)  # Exponential backoff
                logging.warning("Telegram request failed (attempt %d/%d): %s. Retrying in %d seconds...",
                              attempt + 1, max_retries, exc, delay)
                time.sleep(delay)
            else:
                logging.error("Failed to send Telegram message after %d attempts: %s", max_retries, exc)
        except Exception as exc:
            logging.exception("Unexpected error sending Telegram message: %s", exc)
            return

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

def is_instagram_task(quest_data):
    """Check if the quest is an Instagram task based on name or description."""
    name = quest_data.get("name", "").lower()
    if "instagram" in name:
        return True
    
    # Check description for instagram links or mentions
    desc = quest_data.get("description", {})
    content = desc.get("content", [])
    for item in content:
        if item.get("type") == "paragraph":
            for sub in item.get("content", []):
                text = sub.get("text", "").lower()
                if "instagram" in text:
                    return True
                if sub.get("marks"):
                    for mark in sub.get("marks", []):
                        if mark.get("type") == "link":
                            href = mark.get("attrs", {}).get("href", "")
                            if "instagram.com" in href:
                                return True
    return False

def extract_instagram_links(quest_data):
    """Extract Instagram links from the quest description."""
    links = []
    desc = quest_data.get("description", {})
    content = desc.get("content", [])
    
    def extract_from_content(content_list):
        """Recursively extract links from content list."""
        for item in content_list:
            item_type = item.get("type")
            
            # Handle paragraphs
            if item_type == "paragraph":
                for sub in item.get("content", []):
                    if sub.get("marks"):
                        for mark in sub.get("marks", []):
                            if mark.get("type") == "link":
                                href = mark.get("attrs", {}).get("href", "")
                                if "instagram.com" in href:
                                    links.append(href)
                    # Also check for nested content
                    if sub.get("content"):
                        extract_from_content(sub.get("content", []))
            
            # Handle lists (orderedList, bulletList)
            elif item_type in ["orderedList", "bulletList"]:
                for list_item in item.get("content", []):
                    if list_item.get("type") == "listItem":
                        extract_from_content(list_item.get("content", []))
            
            # Handle other nested content
            elif item.get("content"):
                extract_from_content(item.get("content", []))
    
    extract_from_content(content)
    return links

def check_match(account_name, ig_link):
    """Check if the Instagram link matches any stored link for the account and return URLs if found."""
    logging.info(f"Checking match for {account_name} and link {ig_link}")
    json_path = f'uploads/{account_name}/links.json'
    if os.path.exists(json_path):
        with open(json_path) as f:
            links = json.load(f)
            logging.info(f"Found links for {account_name}: {links}")
        if ig_link in links:
            return links[ig_link]  # Return the list of URLs [url1, url2]
    return None

def remove_claimed_link(account_name, instagram_link):
    """Remove a claimed Instagram link and its URLs from the JSON file."""
    json_path = f'uploads/{account_name}/links.json'
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r') as f:
                links = json.load(f)
            
            if instagram_link in links:
                del links[instagram_link]
                with open(json_path, 'w') as f:
                    json.dump(links, f, indent=2)
                logging.info("[%s] Removed claimed link from JSON: %s", account_name, instagram_link)
            else:
                logging.warning("[%s] Link not found in JSON for removal: %s", account_name, instagram_link)
        except Exception as e:
            logging.error("[%s] Error removing link from JSON: %s", account_name, e)


def claim_and_notify_for_account(session, account_name, box_id, quest_id, task_id, quest_title, frontend_url_local, task_type, file_urls=None, instagram_link=None):
    """Use provided session to claim and notify; include account_name in messages."""
    claim_url = claim_url_template.format(quest_id=quest_id)
    if task_type == "tweetReact":
        payload = {"taskValues": [{"taskId": task_id, "type": "tweetReact", "tweetUrl": ""}]}
    elif task_type == "file" and file_urls:
        # For Instagram tasks with uploaded images
        payload = {"taskValues": [{"taskId": task_id, "fileUrls": file_urls, "type": "file"}]}
    elif task_type == "file":
        payload = {"taskValues": [{"taskId": task_id, "type": "file", "files": []}]}
    else:
        payload = {"taskValues": [{"taskId": task_id, "type": task_type}]}
    try:
        res = session.post(claim_url, json=payload, timeout=10)
        if res.status_code == 200:
            msg = f"✅ [{account_name}] Claimed: {quest_title}"
            logging.info(msg)
            print
            send_telegram_message(msg)
            
            # Clean up the used Instagram link from JSON after successful claim
            if instagram_link and file_urls:
                remove_claimed_link(account_name, instagram_link)
        else:
            msg = f"❌ [{account_name}] Failed to claim: {quest_title} → {res.status_code} → {res.text}\nURL: {frontend_url_local}"
            logging.warning(msg)
            send_telegram_message(msg)
    except Exception as e:
        msg = f"❌ [{account_name}] Error claiming {quest_title}: {e}\nURL: {frontend_url_local}"
        logging.exception(msg)
        send_telegram_message(msg)


@app.route('/')
def index():
    html = '''
    <html>
    <body>
    <h1>Upload Instagram Link and Images</h1>
    <form action="/upload" method="post" enctype="multipart/form-data">
        Account Name: <input type="text" name="account_name" required><br>
        Instagram Link: <input type="text" name="link" required><br>
        Image 1: <input type="file" name="image1" accept="image/*" required><br>
        Image 2: <input type="file" name="image2" accept="image/*" required><br>
        <input type="submit" value="Upload">
    </form>
    </body>
    </html>
    '''
    return render_template_string(html)

@app.route('/upload', methods=['POST'])
def upload():
    account_name = request.form['account_name']
    link = request.form['link']
    image1 = request.files['image1']
    image2 = request.files['image2']
    
    # Get session for the account
    session = sessions.get(account_name)
    if not session:
        return f'Session for account {account_name} not found. Please ensure the bot is running and monitoring this account.'
    
    # Upload images using the same session
    files_url = f"https://api-v1.zealy.io/files"
    
    # Upload image1
    files = {'file': (image1.filename, image1.stream, image1.mimetype)}
    response = session.post(files_url, files=files)
    if response.status_code != 200:
        return f'Failed to upload image1: {response.text}'
    url1 = response.json()['url']
    logging.info("[%s] Uploaded image1: %s -> %s", account_name, image1.filename, url1)
    
    # Upload image2
    files = {'file': (image2.filename, image2.stream, image2.mimetype)}
    response = session.post(files_url, files=files)
    if response.status_code != 200:
        return f'Failed to upload image2: {response.text}'
    url2 = response.json()['url']
    logging.info("[%s] Uploaded image2: %s -> %s", account_name, image2.filename, url2)
    
    # Save links and URLs
    json_path = f'uploads/{account_name}/links.json'
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    if os.path.exists(json_path):
        with open(json_path) as f:
            links = json.load(f)
    else:
        links = {}
    links[link] = [url1, url2]
    with open(json_path, 'w') as f:
        json.dump(links, f)
    
    return f'Uploaded for {account_name}: {link} with URLs {url1}, {url2}'

def monitor_account(account):
    """Run the monitoring loop for a single account.

    account: dict with keys 'name' and 'cookie'
    """
    account_name = account.get("name")
    print(f"Starting monitor for account: {account_name}")
    account_cookie = account.get("cookie")
    print(f"Using cookie: {account_cookie[:30]}... (length {len(account_cookie)})")
    session = make_session_with_cookie(account_cookie)
    sessions[account_name] = session
    seen_local = set()
    executor_local = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    local_fetch_count = 1

    while True:
        try:
            logging.info("[%s] Fetching.... Attempt #%d", account_name, local_fetch_count)
            print(f"[{account_name}] Fetching.... Attempt #{local_fetch_count}")
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

                    quest_data = detail_res.json()
                    tasks = quest_data.get("tasks", [])
                    for task in tasks:
                        task_id = task.get("id")
                        task_type = task.get("type")
                        message = f"[{account_name}] Found task: {quest_title}\nType: {task_type}\nURL: {frontend}"
                        print(message)
                        logging.info(message)
                        send_telegram_message(message)

                        if task_type == "tweetReact":
                            logging.info("[%s] Claiming: %s", account_name, quest_title)
                            seen_local.add(quest_id)
                            executor_local.submit(claim_and_notify_for_account, session, account_name, box_id, quest_id, task_id, quest_title, frontend, task_type)
                        elif task_type == "file" and is_instagram_task(quest_data):
                            instagram_links = extract_instagram_links(quest_data)
                            logging.info("[%s] Instagram links found: %s", account_name, instagram_links)
                            print(f"Instagram links found: {instagram_links}")
                            if instagram_links:
                                logging.info("[%s] Instagram task found: %s, links: %s", account_name, quest_title, instagram_links)
                                for ig_link in instagram_links:
                                    file_urls = check_match(account_name, ig_link)
                                    if file_urls:
                                        logging.info("[%s] Match found for %s, claiming: %s with URLs: %s", account_name, ig_link, quest_title, file_urls)
                                        seen_local.add(quest_id)
                                        executor_local.submit(claim_and_notify_for_account, session, account_name, box_id, quest_id, task_id, quest_title, frontend, task_type, file_urls, ig_link)
                                        break
                                else:
                                    logging.info("[%s] No match for Instagram links: %s", account_name, instagram_links)
                            else:
                                logging.info("[%s] File task but no Instagram links: %s", account_name, quest_title)
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
    
    # Create uploads folder
    os.makedirs('uploads', exist_ok=True)
    
    # Start monitoring each account in a separate thread
    threads = []
    for account in accounts:
        thread = threading.Thread(target=monitor_account, args=(account,), daemon=True)
        thread.start()
        threads.append(thread)
        print(f"✅ Started monitoring thread for: {account['name']}")
    
    # Start Flask app in a separate thread
    flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False), daemon=True)
    flask_thread.start()
    print("✅ Started Flask web server on http://0.0.0.0:5000")
    print("🌐 Access the upload page at: http://YOUR_SERVER_IP:5000")
    
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