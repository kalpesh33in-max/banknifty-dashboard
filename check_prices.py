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

def check_prices():
    all_messages = []
    for folder in ["2min"]:
        dir_path = f"C:\\Users\\kalpe\\gdfl data\\banknifty-dashboard\\{folder}"
        for filename in os.listdir(dir_path):
            if filename.endswith(".html"):
                all_messages.extend(parse_html_file(os.path.join(dir_path, filename)))
    
    all_messages.sort(key=lambda x: x["dt"])
    
    print("\n--- BANKNIFTY PRICES JUNE 3 AFTER 11:30 AM ---")
    for msg in all_messages:
        if msg["dt"].date() == datetime.date(2026, 6, 3) and (msg["dt"].hour > 11 or (msg["dt"].hour == 11 and msg["dt"].minute >= 30)):
            match = re.search(r"BANKNIFTY \(FUT:\s*([\d.]+)\)", msg["text"])
            if match:
                print(f"[{msg['dt'].time()}] {match.group(1)}")

if __name__ == "__main__":
    check_prices()
