import os
import time
import requests
import feedparser
from datetime import datetime
from nsepython import nse_events

# --- Configuration ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    except Exception as e:
        print(f"Telegram Error: {e}")

def get_market_news():
    # Header with current Time
    report = f"🗞️ **INDIAN MARKET NEWS ALERT**\n_Time: {datetime.now().strftime('%H:%M')}_\n"
    report += "---"

    # 1. Hidden Corporate News (NSE Official Filings)
    try:
        report += "\n🚨 **Corporate Filings (Hidden Intel):**\n"
        # nse_events() fetches Board Meetings, Dividends, etc.
        announcements = nse_events()
        # Showing the top 4 most recent events
        for _, row in announcements.head(4).iterrows():
            report += f"🔹 *{row['company']}*: {row['desc'][:60]}...\n"
    except:
        report += "\n⚠️ Corporate filings feed busy."

    # 2. Latest Headlines (Aggregated from Moneycontrol/NDTV)
    try:
        report += "\n📰 **Top Market Headlines:**\n"
        feed = feedparser.parse("https://www.moneycontrol.com/rss/latestnews.xml")
        # Grabbing top 5 news items
        for entry in feed.entries[:5]:
            report += f"• {entry.title}\n"
    except:
        report += "\n⚠️ News feed temporarily unavailable."

    return report

if __name__ == "__main__":
    send_telegram("🛰️ **News & Corporate Action Scanner Active**\nMonitoring NSE Filings & Headlines every 10 mins.")
    while True:
        try:
            full_msg = get_market_news()
            send_telegram(full_msg)
        except Exception as e:
            print(f"Loop Error: {e}")
        
        # Checking every 10 minutes to avoid being blocked by NSE
        time.sleep(600)
