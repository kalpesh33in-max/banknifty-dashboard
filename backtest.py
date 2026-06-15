import os
import re
import datetime
from bs4 import BeautifulSoup

def parse_html_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")
    messages = []
    current_date_str = ""
    for div in soup.find_all("div", class_=["message", "service"]):
        if "service" in div["class"]:
            current_date_str = div.get_text().strip()
            continue
        date_div = div.find("div", class_="date")
        if not date_div or not current_date_str: continue
        time_str = date_div.get_text().strip()
        try:
            dt = datetime.datetime.strptime(f"{current_date_str} {time_str}", "%d %B %Y %H:%M")
        except:
            try:
                dt = datetime.datetime.strptime(f"{current_date_str} {time_str}", "%d %b %Y %H:%M")
            except:
                continue
        text_div = div.find("div", class_="text")
        if text_div:
            messages.append({"dt": dt, "text": text_div.get_text(separator="\n").strip()})
    return messages

def run_backtest():
    all_messages = []
    for folder in ["2min", "5min"]:
        dir_path = f"C:\\Users\\kalpe\\gdfl data\\banknifty-dashboard\\{folder}"
        for filename in os.listdir(dir_path):
            if filename.endswith(".html"):
                all_messages.extend(parse_html_file(os.path.join(dir_path, filename)))
    
    all_messages.sort(key=lambda x: x["dt"])
    
    INDEX_SYMBOLS = ["BANKNIFTY", "NIFTY"]
    
    # PARAMETERS (WEIGHTED FOR WRITERS/SC)
    WEIGHT_WR_SC = 1.0
    WEIGHT_BUY_UNW = 0.25 # Lowered to 0.25 as per user request
    
    VOL_2MIN_CUMULATIVE_WEIGHTED = 8.0 # Lowered because BUY/UNW contribute less now
    FUTURES_LEAD_5MIN = 3.0
    PRICE_HOLD_WINDOWS = 1
    OPPOSITE_EXIT_THRESHOLD_WEIGHTED = 12.0
    TRAILING_STOP_POINTS = {"BANKNIFTY": 150, "NIFTY": 50}
    PRICE_WIGGLE_ROOM = {"BANKNIFTY": 50, "NIFTY": 20}
    
    flow_history_2min = {s: [] for s in INDEX_SYMBOLS}
    last_5min_sync = {s: {"bull": 0.0, "bear": 0.0, "fut_bull": 0.0, "fut_bear": 0.0} for s in INDEX_SYMBOLS}
    active_trade = None
    pending_trade = None
    results = []

    def normalize_cr(val_str, unit):
        try:
            val = float(val_str)
            return val if unit == "Cr" else (val / 100 if unit == "L" else 0.0)
        except: return 0.0

    def parse_weighted_metrics(section):
        if not section: return None
        bull = 0.0
        bear = 0.0
        
        # Parse the TYPE table
        rows = re.findall(r"([A-Z_]+)\s+[\d.L(Cr)]+\s+[\d.L(Cr)]+\s+\d+\(([\d.]+)(Cr|L|)\)", section)
        for action, val_str, unit in rows:
            val = normalize_cr(val_str, unit)
            if action in ["PUT_WR", "CALL_SC"]:
                bull += val * WEIGHT_WR_SC
            elif action in ["CALL_WR", "PUT_SC"]:
                bear += val * WEIGHT_WR_SC
            elif action in ["CALL_BUY", "PUT_UNW"]:
                bull += val * WEIGHT_BUY_UNW
            elif action in ["PUT_BUY", "CALL_UNW"]:
                bear += val * WEIGHT_BUY_UNW
        
        # Parse Futures
        fut_bull = 0.0
        fut_bear = 0.0
        fut_part = section.split("---- FUTURES FLOW ----")
        if len(fut_part) > 1:
            fut_bull = normalize_cr(*(re.findall(r"Bullish Turn\s*:\s*([\d.]+)(Cr|L|)", fut_part[1]) or [("0", "")])[-1])
            fut_bear = normalize_cr(*(re.findall(r"Bearish Turn\s*:\s*([\d.]+)(Cr|L|)", fut_part[1]) or [("0", "")])[-1])
            
        return {"bull": bull, "bear": bear, "fut_bull": fut_bull, "fut_bear": fut_bear}

    def get_future_price(text, symbol):
        pattern = rf"💎\s*{re.escape(symbol)}\s*\(FUT:\s*([\d.]+)\)"
        match = re.search(pattern, text, re.IGNORECASE)
        return float(match.group(1)) if match else None

    def extract_instrument_section(text, symbol):
        sym_pat = rf"💎\s*{re.escape(symbol)}\s*\(FUT:"
        m = re.search(sym_pat, text, re.IGNORECASE)
        if not m: return None
        start = m.start()
        next_pos = [len(text)]
        for sym in ["BANKNIFTY", "NIFTY", "SENSEX", "MIDCPNIFTY", "HDFCBANK", "ICICIBANK", "RELIANCE"]:
            if sym == symbol: continue
            m2 = re.search(rf"💎\s*{re.escape(sym)}\s*\(FUT:", text[m.end():], re.IGNORECASE)
            if not m2: m2 = re.search(rf"{re.escape(sym)}\s*\(FUT:", text[m.end():], re.IGNORECASE)
            if m2: next_pos.append(m.end() + m2.start())
        return text[start:min(next_pos)]

    print("Running Simulation (Institutional Weighted)...")
    cutoff = datetime.datetime(2026, 6, 1)
    
    for msg in all_messages:
        if msg["dt"] < cutoff: continue
        text = msg["text"]
        
        if "5 MIN" in text.upper():
            for s in INDEX_SYMBOLS:
                sec = extract_instrument_section(text, s)
                m = parse_weighted_metrics(sec)
                if m:
                    last_5min_sync[s] = {"bull": m["bull"], "bear": m["bear"], "fut_bull": m["fut_bull"], "fut_bear": m["fut_bear"]}
        
        elif "2 MIN" in text.upper():
            current_prices = {}
            current_metrics = {}
            for s in INDEX_SYMBOLS:
                sec = extract_instrument_section(text, s)
                if not sec: continue
                m = parse_weighted_metrics(sec)
                p = get_future_price(sec, s)
                if m and p:
                    flow_history_2min[s].append(m)
                    if len(flow_history_2min[s]) > 10: flow_history_2min[s].pop(0)
                    current_prices[s] = p
                    current_metrics[s] = m

            # Exit Logic
            if active_trade:
                s = active_trade["symbol"]
                p = current_prices.get(s)
                m = current_metrics.get(s)
                if p:
                    if active_trade["side"] == "CALL":
                        if p > active_trade["high"]: active_trade["high"] = p
                        if p < (active_trade["high"] - TRAILING_STOP_POINTS[s]):
                            results.append(f"EXIT  | {msg['dt']} | {s} | {active_trade['side']} | Price: {p} | Reason: Trailing SL")
                            active_trade = None
                    elif active_trade["side"] == "PUT":
                        if p < active_trade["low"]: active_trade["low"] = p
                        if p > (active_trade["low"] + TRAILING_STOP_POINTS[s]):
                            results.append(f"EXIT  | {msg['dt']} | {s} | {active_trade['side']} | Price: {p} | Reason: Trailing SL")
                            active_trade = None
                
                if active_trade and m:
                    opp = m["bear"] if active_trade["side"] == "CALL" else m["bull"]
                    if opp >= OPPOSITE_EXIT_THRESHOLD_WEIGHTED:
                        results.append(f"EXIT  | {msg['dt']} | {s} | {active_trade['side']} | Price: {current_prices.get(s, 'N/A')} | Reason: Weighted Reversal {opp:.2f}Cr")
                        active_trade = None

            # Pending Logic
            if pending_trade:
                s = pending_trade["symbol"]
                p = current_prices.get(s)
                if p:
                    pending_trade["wait_count"] += 1
                    rev_dist = (p - pending_trade["t0_price"]) if pending_trade["side"] == "CALL" else (pending_trade["t0_price"] - p)
                    if rev_dist < -PRICE_WIGGLE_ROOM[s]:
                        pending_trade = None
                    elif pending_trade["wait_count"] >= PRICE_HOLD_WINDOWS:
                        results.append(f"ENTRY | {msg['dt']} | {s} | {pending_trade['side']} | Price: {p}")
                        active_trade = {"symbol": s, "side": pending_trade["side"], "entry": p, "high": p, "low": p}
                        pending_trade = None

            # New Trigger
            if not active_trade and not pending_trade:
                for s in INDEX_SYMBOLS:
                    # Individual Instrument Focus
                    inst_5 = last_5min_sync[s]
                    
                    side = None
                    if inst_5["bull"] > inst_5["bear"]: side = "CALL"
                    elif inst_5["bear"] > inst_5["bull"]: side = "PUT"
                    
                    if not side: continue
                    
                    # Faster Weighted Vol check (Catch 400 pt moves)
                    hist = flow_history_2min[s]
                    if len(hist) < 3: continue
                    cum_vol = sum(h["bull"] if side == "CALL" else h["bear"] for h in hist[-3:])
                    opp_vol = sum(h["bear"] if side == "CALL" else h["bull"] for h in hist[-3:])
                    
                    # 6Cr is sufficient when prioritized for WR/SC
                    if cum_vol >= 6.0 and opp_vol < 2.0:
                        pending_trade = {"symbol": s, "side": side, "t0_price": current_prices.get(s, 0), "wait_count": 0}
                        break

    print("\n--- TRADES LOG (INSTITUTIONAL WEIGHTED) ---")
    for r in results:
        print(r)

if __name__ == "__main__":
    run_backtest()
