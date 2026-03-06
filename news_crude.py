import os, time, requests, yfinance as yf
from datetime import datetime

# Railway Variables
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def get_heavy_lot_alerts():
    try:
        # Using USO (Global Oil Proxy) for stable strike-wise data
        ticker = yf.Ticker("USO")
        expiry = ticker.options[0] # Nearest expiry
        chain = ticker.option_chain(expiry)
        
        # Combine Calls and Puts for analysis
        calls = chain.calls
        puts = chain.puts
        
        alerts = []
        
        # Function to process options
        def analyze_side(df, opt_type):
            # We look for Change in OI > 100 lots
            # Note: In yfinance, 'change' is price change, 'openInterest' is current OI
            # For real-time 'OI Change', you compare with the previous loop's data
            # Here we filter for high volume 'Heavy Activity'
            heavy_activity = df[df['volume'] > 100] 
            
            for _, row in heavy_activity.iterrows():
                strike = row['strike']
                price_change = row['change']
                vol = row['volume']
                
                # Sentiment Logic
                if price_change > 0:
                    sentiment = "🚀 BUYING (Long Buildup)"
                else:
                    sentiment = "✍️ WRITING (Short Buildup)"
                
                alerts.append(f"🎯 {opt_type} Strike: `{strike}`\n📦 Lots: {vol}\n💡 Sentiment: {sentiment}\n")

        analyze_side(calls, "CALL")
        analyze_side(puts, "PUT")

        if not alerts:
            return None
            
        header = f"🚨 **HEAVY LOT ALERT (>100)**\n_{datetime.now().strftime('%H:%M')}_\n---\n"
        return header + "\n".join(alerts[:5]) # Top 5 alerts

    except Exception as e:
        return f"⚠️ Scan Error: {str(e)}"

def send_telegram(msg):
    if msg:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

if __name__ == "__main__":
    while True:
        msg = get_heavy_lot_alerts()
        send_telegram(msg)
        time.sleep(600) # Check every 10 minutes to stay in 'Safe Zone'
