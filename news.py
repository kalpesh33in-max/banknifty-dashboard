import os
import requests
import time
import yfinance as yf
from datetime import datetime
from nsepython import nse_events, nse_get_index_quote

# NEW: Library for reading news feeds quickly
import feedparser 

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def get_pro_news():
    news_report = "\n📰 *Pro News (Moneycontrol/BQ):*\n"
    # Moneycontrol RSS Feed for Top News
    feed_url = "https://www.moneycontrol.com/rss/latestnews.xml"
    feed = feedparser.parse(feed_url)
    
    # Get top 3 headlines
    for entry in feed.entries[:3]:
        news_report += f"• {entry.title}\n"
    return news_report

def get_combined_intel():
    report = f"🕒 *Market Pulse: {datetime.now().strftime('%H:%M')}*\n"
    report += "---"
    
    # 1. Global Drivers
    try:
        global_tickers = {"USD Index": "DX-Y.NYB", "US 10Y Yield": "^TNX"}
        report += "\n🌍 *Global:* "
        for name, sym in global_tickers.items():
            price = yf.Ticker(sym).history(period="1d")['Close'].iloc[-1]
            report += f"{name}: {price:.2f} | "
    except: pass

    # 2. Indian Indices & Hidden NSE Filings
    try:
        nifty = nse_get_index_quote("NIFTY 50")
        report += f"\n\n🇮🇳 *Nifty:* {nifty['lastPrice']} ({nifty['pChange']}%)\n"
        
        events = nse_events()
        report += "\n🚨 *NSE Filings:* "
        for _, row in events.head(2).iterrows():
            report += f"\n- {row['company']}: {row['desc'][:50]}..."
    except: pass

    # 3. Aggregated Professional News
    report += get_pro_news()
    
    return report

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

if __name__ == "__main__":
    send_telegram("🚀 **Advanced Hybrid Scanner Active**\nTracking NSE, YFinance, & Moneycontrol Pro feeds.")
    while True:
        send_telegram(get_combined_intel())
        time.sleep(900) # Every 15 mins
