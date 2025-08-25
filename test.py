import os, requests
from dotenv import load_dotenv

load_dotenv()

BOT = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT = "@zealyclaimmonitor"

r = requests.post(f"https://api.telegram.org/bot{BOT}/sendMessage",
                  data={"chat_id": CHAT, "text": "test from script"})
print(r.status_code, r.json())