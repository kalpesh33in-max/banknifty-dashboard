import os
import requests
import time
import yfinance as yf
from datetime import datetime
from nsepython import nse_get_fno_lot_sizes, nse_events, nse_get_index_quote

# Railway Environment Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    except Exception as e:
        print(f"Telegram Error: {e}")

def get_combined_intel():
    report = f"🕒 *Market Update: {datetime.now().strftime('%H:%M')}*\n"
    report += "---"
    
    # 1. GLOBAL PARAMETERS (yfinance) - The 'Hidden' Market Drivers
    try:
        # DXY: Dollar Index (Up = Bad for Nifty), BZ=F: Brent Crude (Up = Bad for India)
        global_tickers = {"USD Index": "DX-Y.NYB", "Brent Crude": "BZ=F", "US 10Y Yield": "^TNX"}
        report += "\n🌍 *Global Triggers:*\n"
        for name, sym in global_tickers.items():
            t = yf.Ticker(sym).history(period="1d")
            if not t.empty:
                price = t['Close'].iloc[-1]
                report += f"• {name}: {price:.2f}\n"
    except:
        report += "\n⚠️ Global data sync failed."

    # 2. INDIAN INDEX & CORPORATE NEWS (nsepython)
    try:
        # Indices
        nifty = nse_get_index_quote("NIFTY 50")
        report += f"\n🇮🇳 *Indian Indices:*\n"
        report += f"📍 Nifty: {nifty.get('lastPrice', 'N/A')} ({nifty.get('pChange', '0')}%)\n"
        
        # 'Hidden' Corporate Announcements
        events = nse_events()
        top_news = events.head(3)
        report += "\n🚨 *Latest NSE Filings:*\n"
        for _, row in top_news.iterrows():
            report += f"🔹 *{row['company']}*: {row['desc'][:60]}...\n"
    except Exception as e:
        report += f"\n⚠️ NSE Data error: {str(e)}"

    return report

def monitor():
    send_telegram("🛰️ **Hybrid News Scanner Online**\nTracking NSE & Global Macro...")
    while True:
        # Runs every 10 minutes to stay within API limits but stay 'quick'
        msg = get_combined_intel()
        send_telegram(msg)
        time.sleep(600) 

if __name__ == "__main__":
    monitor()
