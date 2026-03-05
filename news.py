import os
import time
import requests
import feedparser
import yfinance as yf
from datetime import datetime
from nsepython import nse_optionchain_scrapper, nse_events, nse_get_index_quote

# --- Configuration ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
# PCR Watchlist: Indices + Top 10 Stocks
PCR_WATCHLIST = ['NIFTY', 'BANKNIFTY', 'RELIANCE', 'HDFCBANK', 'ICICIBANK', 'INFY', 'TCS', 'SBIN', 'BHARTIARTL', 'AXISBANK', 'WIPRO', 'LT']

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})
    except Exception as e:
        print(f"Telegram Error: {e}")

def get_pcr(symbol):
    """Calculates PCR safely. Returns 'N/A' on failure."""
    try:
        data = nse_optionchain_scrapper(symbol)
        # PCR = Total Put OI / Total Call OI
        put_oi = data['filtered']['PE']['totOI']
        call_oi = data['filtered']['CE']['totOI']
        if call_oi > 0:
            return round(put_oi / call_oi, 2)
        return 0.0
    except:
        return "N/A"

def get_market_report():
    report = f"📊 **MARKET INTEL & PCR SCANNER**\n_Time: {datetime.now().strftime('%d %b %Y | %H:%M')}_\n"
    report += "---"

    # 1. Global Sentiment (yfinance)
    try:
        report += "\n🌍 *Global Drivers:*"
        # DXY: Dollar Index (Up=Bad), TNX: US 10Y Yield (Up=Bad)
        for name, ticker in {"USD Index": "DX-Y.NYB", "US 10Y Yield": "^TNX"}.items():
            price = yf.Ticker(ticker).history(period="1d")['Close'].iloc[-1]
            report += f"\n• {name}: {price:.2f}"
    except: report += "\n⚠️ Global data sync failed."

    # 2. Indian Index & Stock PCR
    report += "\n\n📈 *Sentiment (PCR):*\n"
    for item in PCR_WATCHLIST:
        val = get_pcr(item)
        if val != "N/A":
            # Trading logic: <0.7 is Bullish, >1.2 is Bearish (Contrarian)
            sentiment = "🟢" if val < 0.8 else "🔴" if val > 1.2 else "🟡"
            report += f"{sentiment} `{item.ljust(10)}`: {val}\n"
        else:
            report += f"⚪ `{item.ljust(10)}`: Market Closed\n"

    # 3. Hidden News (NSE Filings + Moneycontrol)
    try:
        report += "\n🚨 *NSE Corporate Filings:*\n"
        announcements = nse_events().head(2)
        for _, row in announcements.iterrows():
            report += f"🔹 {row['company']}: {row['desc'][:50]}...\n"
            
        report += "\n📰 *Fast News Headlines:*\n"
        feed = feedparser.parse("https://www.moneycontrol.com/rss/latestnews.xml")
        for entry in feed.entries[:3]:
            report += f"• {entry.title}\n"
    except: report += "\n⚠️ News sync failed."

    return report

if __name__ == "__main__":
    send_telegram("🛰️ **Scanner news.py Initialized**\nMonitoring Global Macro, PCR, and News every 5 mins.")
    while True:
        try:
            full_msg = get_market_report()
            send_telegram(full_msg)
        except Exception as e:
            print(f"Main Loop Error: {e}")
        
        # Runs every 5 minutes as requested
        time.sleep(300)
