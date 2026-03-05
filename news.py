import os, time, requests, feedparser, yfinance as yf
from datetime import datetime

# Railway Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# We use a session to persist cookies, which helps bypass some NSE blocks
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "accept-language": "en-US,en;q=0.9",
    "accept-encoding": "gzip, deflate, br"
})

def get_pcr_stable(symbol):
    try:
        # Step 1: Hit the main page to get cookies (Crucial for Railway)
        session.get("https://www.nseindia.com", timeout=10)
        
        # Step 2: Hit the API
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}" if symbol in ['NIFTY', 'BANKNIFTY'] else f"https://www.nseindia.com/api/option-chain-equities?symbol={symbol}"
        
        response = session.get(url, timeout=10)
        data = response.json()
        
        put_oi = data['filtered']['PE']['totOI']
        call_oi = data['filtered']['CE']['totOI']
        return round(put_oi / call_oi, 2) if call_oi > 0 else 0.0
    except:
        return "Blocked"

def run_scanner():
    # This will still give you News and Global data even if NSE blocks the PCR part
    report = f"🕒 Update: {datetime.now().strftime('%H:%M')}\n"
    
    # Global Data (Never blocked)
    dxy = yf.Ticker("DX-Y.NYB").history(period="1d")['Close'].iloc[-1]
    report += f"🌍 USD Index: {dxy:.2f}\n"
    
    # PCR Data
    pcr_n = get_pcr_stable("NIFTY")
    report += f"📊 Nifty PCR: {pcr_n}\n"
    
    # News (Never blocked)
    feed = feedparser.parse("https://www.moneycontrol.com/rss/latestnews.xml")
    report += f"📰 News: {feed.entries[0].title}\n"
    
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
                  json={"chat_id": CHAT_ID, "text": report})

if __name__ == "__main__":
    while True:
        run_scanner()
        time.sleep(300)
