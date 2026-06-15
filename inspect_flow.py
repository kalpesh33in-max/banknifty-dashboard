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

def inspect_flow():
    all_messages = []
    for folder in ["2min", "5min"]:
        dir_path = f"C:\\Users\\kalpe\\gdfl data\\banknifty-dashboard\\{folder}"
        for filename in os.listdir(dir_path):
            if filename.endswith(".html"):
                all_messages.extend(parse_html_file(os.path.join(dir_path, filename)))
    
    all_messages.sort(key=lambda x: x["dt"])
    
    print("\n--- BANKNIFTY FLOW JUNE 11 (10:30 - 13:30) ---")
    for msg in all_messages:
        if msg["dt"].date() == datetime.date(2026, 6, 11) and (10 <= msg["dt"].hour <= 13):
            if "BANKNIFTY" in msg["text"]:
                p = re.search(r"BANKNIFTY \(FUT:\s*([\d.]+)\)", msg["text"])
                p_str = p.group(1) if p else "N/A"
                print(f"[{msg['dt'].time()}] {'2M' if '2 MIN' in msg['text'] else '5M'} | FUT: {p_str}")
                print(msg["text"][:800])
                print("-" * 50)

if __name__ == "__main__":
    inspect_flow()
