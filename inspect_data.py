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
            date_text = div.get_text().strip()
            current_date_str = date_text
            continue
        date_div = div.find("div", class_="date")
        if not date_div or not current_date_str: continue
        time_str = date_div.get_text().strip()
        timestamp_str = f"{current_date_str} {time_str}"
        try: dt = datetime.datetime.strptime(timestamp_str, "%d %B %Y %H:%M")
        except:
            try: dt = datetime.datetime.strptime(timestamp_str, "%d %b %Y %H:%M")
            except: continue
        text_div = div.find("div", class_="text")
        if not text_div: continue
        text = text_div.get_text(separator="\n").strip()
        messages.append({"dt": dt, "text": text})
    return messages

def inspect_times():
    targets = [
        (datetime.datetime(2026, 6, 12, 12, 50), datetime.datetime(2026, 6, 12, 15, 30)),
        (datetime.datetime(2026, 6, 11, 12, 50), datetime.datetime(2026, 6, 11, 15, 30)),
        (datetime.datetime(2026, 6, 11, 10, 50), datetime.datetime(2026, 6, 11, 11, 30)),
        (datetime.datetime(2026, 6, 10, 12, 50), datetime.datetime(2026, 6, 10, 13, 30)),
    ]
    
    all_messages = []
    for folder in ["2min", "5min"]:
        dir_path = f"C:\\Users\\kalpe\\gdfl data\\banknifty-dashboard\\{folder}"
        for filename in os.listdir(dir_path):
            if filename.endswith(".html"):
                all_messages.extend(parse_html_file(os.path.join(dir_path, filename)))
    
    all_messages.sort(key=lambda x: x["dt"])
    
    for start, end in targets:
        print(f"\n--- WINDOW: {start} to {end} ---")
        for msg in all_messages:
            if start <= msg["dt"] <= end:
                # Only print if it contains the symbol and flow
                if "BANKNIFTY" in msg["text"] and ("2 MIN" in msg["text"] or "5 MIN" in msg["text"]):
                    print(f"[{msg['dt']}] {msg['text'][:500]}...") # Print first 500 chars

if __name__ == "__main__":
    inspect_times()
