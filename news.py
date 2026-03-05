import os
import requests
import time
from datetime import datetime

# Use nsepython to get real-time NSE data
# Install via: pip install nsepython
from nsepython import nse_get_fno_lot_size, nse_events, nse_get_index_quote

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

def get_hidden_news():
    try:
        # 1. Fetch live Corporate Announcements from NSE
        # This gives you "Board Meetings", "Results", "Mergers" before the media reports them.
        events = nse_events()
        # We only take the top 3 most recent announcements
        top_news = events.head(3)
        
        news_report = "🚨 *LIVE NSE CORPORATE FILINGS* 🚨\n\n"
        for index, row in top_news.iterrows():
            news_report += f"🔹 *{row['company']}*: {row['desc']}\n"
            news_report += f"⏰ {row['date']}\n\n"
        
        # 2. Market Sentiment (Nifty & BankNifty)
        nifty = nse_get_index_quote("NIFTY 50")
        bnifty = nse_get_index_quote("NIFTY BANK")
        
        report = f"📊 *Live Indices Status*\n"
        report += f"📍 Nifty: {nifty['lastPrice']} ({nifty['pChange']}%)\n"
        report += f"📍 BankNifty: {bnifty['lastPrice']} ({bnifty['pChange']}%)\n\n"
        
        return report + news_report
    except Exception as e:
        return f"⚠️ Scanner Error: {str(e)}"

def start_monitor():
    send_telegram("🚀 **Professional News Scanner Started**\nMonitoring NSE Filings...")
    while True:
        # Check for news every 5 minutes during market hours
        # This helps you get 'hidden' moves before the retail crowd
        update = get_hidden_news()
        send_telegram(update)
        time.sleep(300) 

if __name__ == "__main__":
    start_monitor()
