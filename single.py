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
claim_url_template = f"https://api-v1.zealy.io/communities/{community}/quests/v2/{{box_id}}/claim"
frontend_url = f"https://zealy.io/cw/{community}/questboard/{{box_id}}/{{quest_id}}"


# 🔎 Filters
params = {
    "filters": ["locked", "available", "inCooldown", "inReview"]
}

# 🔐 DEFAULT HEADERS (will be copied per-account; replace Cookie per account)
headers = {
    "Sec-Ch-Ua-Platform": "macOS",
    "X-Zealy-Subdomain": "reef",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Chromium";v="139", "Not;A=Brand";v="99"',
    "Content-Type": "application/json",
    "Sec-Ch-Ua-Mobile": "?0",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Origin": "https://zealy.io",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://zealy.io/",
    "Accept-Encoding": "gzip, deflate, br",
    "Priority": "u=1, i",
    "Cookie": '''_fbp=fb.1.1752334709102.8206508385164166; intercom-id-nketzd4e=692631c6-4c8e-4619-82da-2d0b2ac8575f; intercom-device-id-nketzd4e=c9859bed-8d52-4b86-87b3-5eb4a52b2a4e; cookie-config={%22analytics%22:true%2C%22marketing%22:true%2C%22functional%22:true}; _tt_enable_cookie=1; _ttp=01K0YF05411T2JBM7H5N0869YA_.tt.1; ttcsid_CO6OII3C77UAL9O5M6RG=1753369023624::gV79Qth__wu8pvkJdHmP.1.1753372570479; ttcsid=1753369023626::5WVRUZRliQU0_6Wkj4IC.1.1753372570479; subdomain=root; connect.sid=s%3A_kGe9R9oFLgwFXUr9TGpGyABM_mjGgO3.kdagBX7wbb2F7hji1SARofKG6Pj5lhqJsBy6txBo%2B9Y; access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJlNjRkZmU1NS00MTFiLTQxZjItOTYzYy02MGE2NzFmYjQ3YmMiLCJhY2NvdW50VHlwZSI6ImRpc2NvcmQiLCJpYXQiOjE3NTYxMTY4NjQsImV4cCI6MTc1ODcwODg2NH0.vE7-PdOz1Gtb-u29CoZ3s91RHZAvz-6VKRpFlZUGgJY; user_metadata=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJlNjRkZmU1NS00MTFiLTQxZjItOTYzYy02MGE2NzFmYjQ3YmMiLCJpYXQiOjE3NTYxMTY4NjQsImV4cCI6MTc1ODcwODg2NH0.UE03CWqDDzuBrQhBLZjXhbgiMdUbzjiuo3-Sqna2Coo; referrer-url=https://zealy.io/my-communities; intercom-session-nketzd4e=S1ZUSC9GR21DMGltb0lWWjV2MWkxYnN1Q1FEeVZzR245MitIQjd1NEdxL3d1b1o4SG43YzQ4MUZkMlhKWTJnZE9ka3g2ZFFoTllPWVV4WUxEQ1dhMFArV3JSSTcwTzROSXVKTFpqcXpMMWc9LS1EcnNsYUZiYTM0bVVWbXRRc2xtakF3PT0=--b4f93624914a924d52965609522b0181cd832a17; mp_331e7ed57ec193ae7fde9e90b8ef68d4_mixpanel=%7B%22distinct_id%22%3A%22%24device%3Ae2f64bdb-7aad-4779-8622-bc9f7799e758%22%2C%22%24device_id%22%3A%22e2f64bdb-7aad-4779-8622-bc9f7799e758%22%2C%22%24initial_referrer%22%3A%22%24direct%22%2C%22%24initial_referring_domain%22%3A%22%24direct%22%2C%22__mps%22%3A%7B%7D%2C%22__mpso%22%3A%7B%22%24initial_referrer%22%3A%22%24direct%22%2C%22%24initial_referring_domain%22%3A%22%24direct%22%7D%2C%22__mpus%22%3A%7B%7D%2C%22__mpa%22%3A%7B%7D%2C%22__mpu%22%3A%7B%7D%2C%22__mpr%22%3A%5B%5D%2C%22__mpap%22%3A%5B%5D%7D; intercom-session-nketzd4e=OVNhNlhxa2Y5c0Y2NTNxWjhnOTFRWSsvaHlDNmlwcmNhbks4dVR1bitDRTFyWGxFdjdZZnlSSzM2MGdjemdaTEhBb2tydHNSWkttNkRSdDJKYzdVN3VCWnRIdlc0ZXVZQ0czT2VQN29qNUk9LS1uaTMwWUJzMHRlUkZncXdFZjJRNGdBPT0=--f7fdca0f2273654f182d94f9f915ff7896a22692'''
}

def claim_tweet_task(box_id, quest_id, task_id, quest_title):
    claim_url = claim_url_template.format(quest_id=quest_id)
    frontend_url= frontend_url.format(box_id=box_id, quest_id=quest_id)
    payload = {"taskValues":[{"taskId":task_id,"type":"tweetReact","tweetUrl":""}]}

    
    try:
        res = requests.post(claim_url, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            print(f"✅ Claimed: {quest_title}")
            print(f"🔗 Proof: {frontend_url}")
        else:
            print(f"❌ Failed: {quest_title} → {res.status_code} → {res.text}")
            print(f"🔗 Claim Manually: {frontend_url}")
    except Exception as e:
        print(f"❌ Error claiming {quest_title}: {e}")
        print(f"🔗 Claim Manually: {frontend_url}")


def claim_and_notify(box_id, quest_id, quest_title, frontend_url_local):
    """Claim using the API and send Telegram notifications about result.

    This function mirrors the original claim behavior but also notifies via
    Telegram for success/failure/errors.
    """
    claim_url = claim_url_template.format(box_id=box_id)
    print(f"Claim URL: {claim_url}")
    payload = {
        "taskValues": [
            {
                "taskId": quest_id,
                "type": "tweetReact",
                "tweetUrl": ""
            }
        ]
    }
    print(f"Payload: {payload}")
    try:
        res = requests.post(claim_url, json=payload, headers=headers, timeout=10)
        logging.debug(f"Claim response: {res}")
        if res.status_code == 200:
            msg = f"✅ Claimed: {quest_title}\nURL: {frontend_url_local}"
            print(msg)
            #send_telegram_message(msg)
        else:
            msg = f"❌ Failed: {quest_title} → {res.status_code} → {res.text}\nURL: {frontend_url_local}"
            print(msg)
            #send_telegram_message(msg)
    except Exception as e:
        msg = f"❌ Error claiming {quest_title}: {e}\nURL: {frontend_url_local}"
        print(msg)
        #send_telegram_message(msg)


def send_telegram_message(text: str) -> None:
    """Send a message to the configured Telegram chat. No-op if not configured."""
    if not TELEGRAM_API or not TELEGRAM_CHAT_ID:
        logging.debug("Telegram not configured, skipping message: %s", text)
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
      2) ACCOUNTS_FILE -> JSON array of {name,cookie}
      3) Legacy ACCOUNTS string: name:cookie;name2:cookie2;...
      4) Fallback single account using ACCOUNT_NAME / ACCOUNT_COOKIE or headers Cookie
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

    if accounts:
        return accounts


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
            print("response", resp)
            if resp.status_code != 200:
                logging.warning("[%s] Error fetching questboard: %s", account_name, resp.status_code)
                time.sleep(POLL_INTERVAL)
                continue

            data = resp.json()
            print("Data:", data)
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
                        task_type = task.get("type")
                        message = f"[{account_name}] Found task: {quest_title}\nType: {task_type}\nURL: {frontend}"
                        logging.info(message)
                        send_telegram_message(message)

                        if task_type == "tweetReact":
                            logging.info("[%s] Claiming: %s", account_name, quest_title)
                            seen_local.add(quest_id)
                            executor_local.submit(claim_tweet_task,box_id, quest_id, quest_title)
                            #executor_local.submit(claim_and_notify_for_account, session, account_name, box_id, quest_id, quest_title, frontend)
                        else:
                            logging.info("[%s] Non-tweetReact task: %s", account_name, quest_title)

        except Exception as e:
            logging.exception("[%s] General error: %s", account_name, e)
            send_telegram_message(f"[{account_name}] General error: {e}")

        time.sleep(POLL_INTERVAL)


def claim_and_notify_for_account(session, account_name, box_id, quest_id, quest_title, frontend_url_local):
    """Use provided session to claim and notify; include account_name in messages."""
    claim_url = claim_url_template.format(box_id=box_id)
    payload = {"taskValues": [{"taskId": quest_id, "type": "tweetReact", "tweetUrl": ""}]}
    try:
        res = session.post(claim_url, json=payload, timeout=10)
        if res.status_code == 200:
            msg = f"✅ [{account_name}] Claimed: {quest_title}\nURL: {frontend_url_local}"
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


# 🌀 Infinite refresh loop
seen = set()  # optional: to avoid repeating exact claims
executor = ThreadPoolExecutor(max_workers=10)
fetch_count = 1

while True:
    try:
        print(f"Fetching.... Attempt #{fetch_count}")
        msg = f"Fetching.... Attempt #{fetch_count}"
        fetch_count += 1
        response = requests.get(api_url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            for box in data:
                box_id = box.get("id")
                quests = box.get("quests", [])

                for quest in quests:
                    quest_id = quest.get("id")
                    quest_title = quest.get("name")

                    if quest_id in seen:
                        continue  # skip already handled quests

                    detail_url = quest_detail_url_template.format(quest_id=quest_id)
                    frontend = frontend_url.format(box_id=box_id, quest_id=quest_id)
                    detail_res = requests.get(detail_url, headers=headers)

                    if detail_res.status_code != 200:
                        continue

                    tasks = detail_res.json().get("tasks", [])
                    for task in tasks:
                        task_type = task.get("type")
                        task_id = task.get("id")
                        # Notify for every found task with the frontend URL
                        message = f"Found task: {quest_title}\nType: {task_type}\nURL: {frontend}"
                        print(f"🔎 {message}")
                        send_telegram_message(message)

                        if task_type == "tweetReact":
                            print(f"🚀 Claiming: {quest_title}")
                            seen.add(quest_id)
                            # Submit claim in the background
                            executor.submit(claim_tweet_task, box_id, quest_id, task_id, quest_title, frontend)
                        else:
                            print(f"📌 Non-tweetReact task (no auto-claim): {quest_title}")
        else:
            print(f"❌ Error fetching questboard: {response.status_code}")
            send_telegram_message(f"Error fetching questboard: {response.status_code}")

    except Exception as e:
        print(f"❌ General error: {e}")
        send_telegram_message(f"General error: {e}")

    time.sleep(2)  # ⏱️ Avoid rate-limiting or bans — adjust as needed

                        #my cookie 
                        #"Cookie": '''_fbp=fb.1.1752334709102.8206508385164166; intercom-id-nketzd4e=692631c6-4c8e-4619-82da-2d0b2ac8575f; intercom-device-id-nketzd4e=c9859bed-8d52-4b86-87b3-5eb4a52b2a4e; access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiI4MDlkZmUzOC03YzJlLTQyYmYtOGU5Yy00YTdjZDdlNjU3ZTgiLCJhY2NvdW50VHlwZSI6ImRpc2NvcmQiLCJpYXQiOjE3NTIzMzQ5MzAsImV4cCI6MTc1NDkyNjkzMH0.6p3S8FlVguzlD2m2_4TfdBDzhsBnnTelnKgleSWw-VA; user_metadata=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiI4MDlkZmUzOC03YzJlLTQyYmYtOGU5Yy00YTdjZDdlNjU3ZTgiLCJpYXQiOjE3NTIzMzQ5MzAsImV4cCI6MTc1NDkyNjkzMH0.DFf8dK42D2mOugqdFbO-iiE_gDTKh-xPCRE22uuK8T4; cookie-config={"analytics":true,"marketing":true,"functional":true}; subdomain=root; connect.sid=s%3AoQc6uEfiGn1zr8e8WQK8LxVpEgiab3kC.lkujOMyLqci0yB4JzzBpuFzPgO9jVt2r7seCn2E2Dfo; mp_331e7ed57ec193ae7fde9e90b8ef68d4_mixpanel={"distinct_id":"$device:e2f64bdb-7aad-4779-8622-bc9f7799e758","$device_id":"e2f64bdb-7aad-4779-8622-bc9f7799e758","$initial_referrer":"$direct","$initial_referring_domain":"$direct","__mps":{},"__mpso":{"$initial_referrer":"$direct","$initial_referring_domain":"$direct"},"__mpus":{},"__mpa":{},"__mpu":{},"__mpr":[],"__mpap":[]}; referrer-url=https://zealy.io/cw/nodeshift/questboard/1bdde954-9820-45cd-be2c-b7daccaf0d15/981ded70-4109-4847-825b-251660265ff4; intercom-session-nketzd4e=MjI4MmpDV3NQL24zMjVmbGhNWHVzSS9IOEMzZDlLVFVNRkE3eHdlSnN5QW4yU1lXdE11N1drd3d4aXNrbTNDeGFHQXNDWndTczJRa241NmxwbmcwcWhabXlzU05zQkZ6YmQ4dHB6VWZCM1U9LS1BV20wa2Y4NC9BQ0xDa3hSUjh1dnF3PT0=--f8cfcbc862ae0375069303c9845ab4868b51f828'''

#                         POST /communities/reef/quests/v2/932ae9c7-3570-4942-bcdf-ef56e8d71b9e/claim HTTP/2
# Host: api-v1.zealy.io
# Cookie: _fbp=fb.1.1752334709102.8206508385164166; intercom-id-nketzd4e=692631c6-4c8e-4619-82da-2d0b2ac8575f; intercom-device-id-nketzd4e=c9859bed-8d52-4b86-87b3-5eb4a52b2a4e; cookie-config={%22analytics%22:true%2C%22marketing%22:true%2C%22functional%22:true}; _tt_enable_cookie=1; _ttp=01K0YF05411T2JBM7H5N0869YA_.tt.1; ttcsid_CO6OII3C77UAL9O5M6RG=1753369023624::gV79Qth__wu8pvkJdHmP.1.1753372570479; ttcsid=1753369023626::5WVRUZRliQU0_6Wkj4IC.1.1753372570479; subdomain=root; connect.sid=s%3Ac5RE_e7Vm7qn3Fn1hE62JBZxNXdKa93o.gNMRMpslCHR%2ForJYlsxRvLq7Fh%2BBZv9cpMhHU2l3inE; access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJlNjRkZmU1NS00MTFiLTQxZjItOTYzYy02MGE2NzFmYjQ3YmMiLCJhY2NvdW50VHlwZSI6ImRpc2NvcmQiLCJpYXQiOjE3NTYxMTY4NjQsImV4cCI6MTc1ODcwODg2NH0.vE7-PdOz1Gtb-u29CoZ3s91RHZAvz-6VKRpFlZUGgJY; user_metadata=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOiJlNjRkZmU1NS00MTFiLTQxZjItOTYzYy02MGE2NzFmYjQ3YmMiLCJpYXQiOjE3NTYxMTY4NjQsImV4cCI6MTc1ODcwODg2NH0.UE03CWqDDzuBrQhBLZjXhbgiMdUbzjiuo3-Sqna2Coo; referrer-url=https://zealy.io/my-communities; mp_331e7ed57ec193ae7fde9e90b8ef68d4_mixpanel=%7B%22distinct_id%22%3A%22%24device%3Ae2f64bdb-7aad-4779-8622-bc9f7799e758%22%2C%22%24device_id%22%3A%22e2f64bdb-7aad-4779-8622-bc9f7799e758%22%2C%22%24initial_referrer%22%3A%22%24direct%22%2C%22%24initial_referring_domain%22%3A%22%24direct%22%2C%22__mps%22%3A%7B%7D%2C%22__mpso%22%3A%7B%22%24initial_referrer%22%3A%22%24direct%22%2C%22%24initial_referring_domain%22%3A%22%24direct%22%7D%2C%22__mpus%22%3A%7B%7D%2C%22__mpa%22%3A%7B%7D%2C%22__mpu%22%3A%7B%7D%2C%22__mpr%22%3A%5B%5D%2C%22__mpap%22%3A%5B%5D%7D; intercom-session-nketzd4e=b0d3VUpFV3NFekxjRkkxVFdaemJMUWFVNHpaTnZ5b2d3VytzUGJIMmhhNHVFTlVLUWJBeFZnM2JORXlMbVB1WktWbTIwZ0xmZVU2azA5bURNVytqTldaa2RadDl1d2xRMjd5d2hCb3V0bFU9LS1LM0xxeE9jVlM1M3RTZVJrMjVoOWZRPT0=--a9bca1e0083ad896b532af50137180ba3e70b4ff
# Content-Length: 100
# Sec-Ch-Ua-Platform: "macOS"
# X-Zealy-Subdomain: reef
# Accept-Language: en-US,en;q=0.9
# Sec-Ch-Ua: "Chromium";v="139", "Not;A=Brand";v="99"
# Content-Type: application/json
# Sec-Ch-Ua-Mobile: ?0
# User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36
# Accept: */*
# Origin: https://zealy.io
# Sec-Fetch-Site: same-site
# Sec-Fetch-Mode: cors
# Sec-Fetch-Dest: empty
# Referer: https://zealy.io/
# Accept-Encoding: gzip, deflate, br
# Priority: u=1, i

# {"taskValues":[{"taskId":"391f343a-63e5-4891-8ba8-916e80e1ce5f","type":"tweetReact","tweetUrl":""}]}