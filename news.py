import os, requests, time, yfinance as yf, feedparser
from datetime import datetime
from nsepython import nse_optionchain_scrapper, nse_events, nse_get_index_quote

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# List of 10 Stocks you want to track PCR for
WATCHLIST = ['RELIANCE', 'HDFCBANK', 'ICICIBANK', 'INFY', 'TCS', 'SBIN', 'BHARTIARTL', 'AXISBANK', 'WIT', 'LT']

def get_pcr(symbol, is_index=False):
    try:
        # Fetching Option Chain
        payload = nse_optionchain_scrapper(symbol)
        
        # PCR Formula = Total Put OI / Total Call OI
        total_put_oi = payload['filtered']['CE']['totOI'] # nsepython returns total for filtered
        total_call_oi = payload['filtered']['PE']['totOI']
        
        pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0
        return round(pcr, 2)
    except:
        return "N/A"

def get_combined_report():
    report = f"🚀 **Market Intel + PCR Scanner** ({datetime.now().strftime('%H:%M')})\n"
    report += "---"

    # 1. INDEX PCR (Nifty & Bank Nifty)
    report += "\n📊 **Index Sentiment (PCR):**\n"
    for idx in ["NIFTY", "BANKNIFTY"]:
        pcr_val = get_pcr(idx, True)
        sentiment = "🟢 Bullish" if float(pcr_val) < 0.7 else "🔴 Bearish" if float(pcr_val) > 1.2 else "🟡 Neutral"
        report += f"• {idx}: {pcr_val} ({sentiment})\n"

    # 2. STOCK WATCHLIST PCR (Top 10)
    report += "\n🎯 **Stock Watchlist PCR:**\n"
    # To save time/avoid rate limits, we can scan top 5-10
    for stock in WATCHLIST[:10]:
        val = get_pcr(stock)
        report += f"`{stock.ljust(10)}`: {val} | "
    
    # 3. GLOBAL & NEWS (From previous version)
    report += "\n\n📰 **Top Headlines:**\n"
    feed = feedparser.parse("https://www.moneycontrol.com/rss/latestnews.xml")
    for entry in feed.entries[:2]:
        report += f"• {entry.title}\n"

    return report

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

if __name__ == "__main__":
    send_telegram("✅ **PCR & News Bot Active**\nIndices + 10 Stocks tracking every 5m.")
    while True:
        try:
            msg = get_combined_report()
            send_telegram(msg)
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(300) # 5 Minutes
