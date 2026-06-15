import os
import re
import datetime
from bs4 import BeautifulSoup

def get_metrics(text):
    bull = bear = fut_bull = fut_bear = 0.0
    for action, val_str, unit in re.findall(r'([A-Z_]+)\s+[\d.L(Cr)]+\s+[\d.L(Cr)]+\s+\d+\(([\d.]+)(Cr|L|)\)', text):
        val = float(val_str) if unit == 'Cr' else (float(val_str)/100 if unit == 'L' else 0.0)
        if action in ['PUT_WR', 'CALL_SC']: bull += val
        elif action in ['CALL_WR', 'PUT_SC']: bear += val
        elif action in ['CALL_BUY', 'PUT_UNW']: bull += val * 0.25
        elif action in ['PUT_BUY', 'CALL_UNW']: bear += val * 0.25
    fut = text.split('---- FUTURES FLOW ----')
    if len(fut) > 1:
        f_b = re.findall(r'Bullish Turn\s*:\s*([\d.]+)(Cr|L|)', fut[1])
        if f_b: fut_bull = float(f_b[-1][0]) if f_b[-1][1] == 'Cr' else (float(f_b[-1][0])/100 if f_b[-1][1] == 'L' else 0)
        f_br = re.findall(r'Bearish Turn\s*:\s*([\d.]+)(Cr|L|)', fut[1])
        if f_br: fut_bear = float(f_br[-1][0]) if f_br[-1][1] == 'Cr' else (float(f_br[-1][0])/100 if f_br[-1][1] == 'L' else 0)
    return bull, bear, fut_bull, fut_bear

targets = [
    (datetime.date(2026, 6, 5), datetime.time(10, 20), 'PUT'),
    (datetime.date(2026, 6, 5), datetime.time(10, 45), 'CALL'),
    (datetime.date(2026, 6, 5), datetime.time(11, 10), 'PUT'),
    (datetime.date(2026, 6, 8), datetime.time(11, 0), 'CALL'),
    (datetime.date(2026, 6, 8), datetime.time(12, 51), 'PUT'),
    (datetime.date(2026, 6, 9), datetime.time(11, 20), 'CALL'),
    (datetime.date(2026, 6, 10), datetime.time(13, 0), 'PUT'),
    (datetime.date(2026, 6, 11), datetime.time(11, 0), 'CALL'),
    (datetime.date(2026, 6, 11), datetime.time(12, 48), 'PUT'),
    (datetime.date(2026, 6, 12), datetime.time(13, 20), 'CALL')
]

msgs_2m = []
dir_path = r'C:\Users\kalpe\gdfl data\banknifty-dashboard\2min'
for fn in os.listdir(dir_path):
    if fn.endswith('.html'):
        with open(os.path.join(dir_path, fn), 'r', encoding='utf-8') as f: s = BeautifulSoup(f, 'html.parser')
        d_str = ''
        for div in s.find_all('div', class_=['message', 'service']):
            if 'service' in div.get('class', []):
                d_str = div.get_text().strip()
                continue
            date_div = div.find('div', class_='date')
            if not date_div or not d_str: continue
            try: dt = datetime.datetime.strptime(f"{d_str} {date_div.get_text().strip()}", '%d %B %Y %H:%M')
            except:
                try: dt = datetime.datetime.strptime(f"{d_str} {date_div.get_text().strip()}", '%d %b %Y %H:%M')
                except: continue
            text_div = div.find('div', class_='text')
            if text_div and '2 MIN' in text_div.get_text().upper() and 'BANKNIFTY' in text_div.get_text().upper():
                msgs_2m.append({'dt': dt, 'text': text_div.get_text(separator='\n').strip()})

msgs_2m.sort(key=lambda x: x['dt'])

for d, t, side in targets:
    tgt_dt = datetime.datetime.combine(d, t)
    print(f"\n--- TARGET: {tgt_dt} | {side} ---")
    for m in msgs_2m:
        if tgt_dt - datetime.timedelta(minutes=6) <= m['dt'] <= tgt_dt + datetime.timedelta(minutes=6):
            sec = m['text'].split('💎 NIFTY')[0] if '💎 NIFTY' in m['text'] else m['text']
            bull, bear, fb, fbe = get_metrics(sec)
            print(f"{m['dt'].time()} | OptBull: {bull:5.1f} | OptBear: {bear:5.1f} | FutBull: {fb:5.1f} | FutBear: {fbe:5.1f}")
