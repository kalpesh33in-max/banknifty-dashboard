import sys

with open("C:\\Users\\kalpe\\gdfl data\\banknifty-dashboard\\scanner_bot.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update State Tracking
content = content.replace(
    "flow_rows_by_symbol = {}",
    "flow_rows_2min = {}\nflow_rows_5min = {}"
)

# 2. Update evaluate_direct_signals
old_direct = """def evaluate_direct_signals(symbol, rows, side):
    latest_metrics = rows[-1]["metrics"]
    if side_from_bias(latest_metrics.get("option_bias", "")) != side:
        return None

    turn_sum = 0.0
    opposite_sum = 0.0
    for row in rows:
        turn, opposite = side_turn_values(row["metrics"], side)
        turn_sum += turn
        opposite_sum += opposite

    if opposite_sum > 1.0:
        return None

    wr_label, sc_label, itm_wr, otm_wr, itm_sc, otm_sc = get_side_components(rows, side)

    signal_type = None
    trigger_line = ""

    if otm_wr >= 15.0:
        signal_type = "DIRECT: AGGRESSIVE OTM WRITER"
        trigger_line = f"{wr_label} OTM {fmt_cr(otm_wr)} >= 15.00Cr"
    elif itm_wr >= 8.0:
        signal_type = "DIRECT: AGGRESSIVE ITM WRITER"
        trigger_line = f"{wr_label} ITM {fmt_cr(itm_wr)} >= 8.00Cr"
    elif itm_sc >= 10.0:
        signal_type = "DIRECT: AGGRESSIVE ITM SHORT COVERING"
        trigger_line = f"{sc_label} ITM {fmt_cr(itm_sc)} >= 10.00Cr"

    if not signal_type:
        return None

    future_check = future_side_check(rows, side)
    _, _, top_components = component_support(rows, side)

    return {
        "mode": "FULL",
        "symbol": symbol,
        "side": side,
        "rows": rows,
        "turn_sum": turn_sum,
        "opposite_sum": opposite_sum,
        "signal_label": signal_type,
        "trigger_line": trigger_line,
        "option_bias": latest_metrics.get("option_bias", "NA"),
        "future": future_check,
        "latest_price": rows[-1].get("price"),
        "is_direct": True,
        "top_components": top_components
    }"""

new_direct = """def evaluate_direct_signals(symbol, rows, rows_5min, side):
    latest_metrics = rows[-1]["metrics"]
    if side_from_bias(latest_metrics.get("option_bias", "")) != side:
        return None

    turn_sum = 0.0
    opposite_sum = 0.0
    for row in rows:
        turn, opposite = side_turn_values(row["metrics"], side)
        turn_sum += turn
        opposite_sum += opposite

    if opposite_sum > 1.0:
        return None

    wr_label, sc_label, itm_wr, otm_wr, itm_sc, otm_sc = get_side_components(rows, side)
    
    # 5 MIN flow check
    latest_5min_row = [rows_5min[-1]] if rows_5min else []
    _, _, itm_wr_5, otm_wr_5, itm_sc_5, otm_sc_5 = get_side_components(latest_5min_row, side)

    signal_type = None
    trigger_line = ""

    if otm_wr >= 15.0 and otm_wr_5 >= 1.5:
        signal_type = "DIRECT: AGGRESSIVE OTM WRITER"
        trigger_line = f"{wr_label} OTM {fmt_cr(otm_wr)} >= 15.00Cr (5MIN {fmt_cr(otm_wr_5)} >= 1.50Cr)"
    elif otm_sc >= 15.0 and otm_sc_5 >= 1.5:
        signal_type = "DIRECT: AGGRESSIVE OTM SHORT COVERING"
        trigger_line = f"{sc_label} OTM {fmt_cr(otm_sc)} >= 15.00Cr (5MIN {fmt_cr(otm_sc_5)} >= 1.50Cr)"
    elif itm_sc >= 10.0 and itm_sc_5 >= 1.0:
        signal_type = "DIRECT: AGGRESSIVE ITM SHORT COVERING"
        trigger_line = f"{sc_label} ITM {fmt_cr(itm_sc)} >= 10.00Cr (5MIN {fmt_cr(itm_sc_5)} >= 1.00Cr)"
    elif itm_wr >= 8.0:
        signal_type = "DIRECT: AGGRESSIVE ITM WRITER"
        trigger_line = f"{wr_label} ITM {fmt_cr(itm_wr)} >= 8.00Cr"

    if not signal_type:
        return None

    future_check = future_side_check(rows, side)
    _, _, top_components = component_support(rows, side)

    return {
        "mode": "FULL",
        "symbol": symbol,
        "side": side,
        "rows": rows,
        "turn_sum": turn_sum,
        "opposite_sum": opposite_sum,
        "signal_label": signal_type,
        "trigger_line": trigger_line,
        "option_bias": latest_metrics.get("option_bias", "NA"),
        "future": future_check,
        "latest_price": rows[-1].get("price"),
        "is_direct": True,
        "top_components": top_components
    }"""

content = content.replace(old_direct, new_direct)

# 3. Update evaluate_full_signal
old_full = """def evaluate_full_signal(symbol, active=None):
    rows = flow_rows_by_symbol.get(symbol, [])
    
    for window in (1, 2):
        if len(rows) < window:
            continue
        recent = rows[-window:]
        candidates = [
            candidate for candidate in (
                evaluate_direct_signals(symbol, recent, "CALL"),
                evaluate_direct_signals(symbol, recent, "PUT"),
            ) if candidate
        ]
        if candidates:
            return max(candidates, key=lambda item: item["turn_sum"])

    min_window = max(1, TURN_MIN_WINDOW)
    max_window = max(min_window, TURN_MAX_WINDOW)
    for window in range(min_window, max_window + 1):
        if len(rows) < window:
            continue
        recent = rows[-window:]
        candidates = [
            candidate for candidate in (
                evaluate_standard_signal(symbol, recent, "CALL"),
                evaluate_standard_signal(symbol, recent, "PUT"),
            ) if candidate
        ]
        if candidates:
            return max(candidates, key=lambda item: item["turn_sum"])
            
    return None"""

new_full = """def evaluate_full_signal(symbol, active=None):
    rows = flow_rows_2min.get(symbol, [])
    rows_5min = flow_rows_5min.get(symbol, [])
    
    for window in (1, 2):
        if len(rows) < window:
            continue
        recent = rows[-window:]
        candidates = [
            candidate for candidate in (
                evaluate_direct_signals(symbol, recent, rows_5min, "CALL"),
                evaluate_direct_signals(symbol, recent, rows_5min, "PUT"),
            ) if candidate
        ]
        if candidates:
            return max(candidates, key=lambda item: item["turn_sum"])

    min_window = max(1, TURN_MIN_WINDOW)
    max_window = max(min_window, TURN_MAX_WINDOW)
    for window in range(min_window, max_window + 1):
        if len(rows) < window:
            continue
        recent = rows[-window:]
        candidates = [
            candidate for candidate in (
                evaluate_standard_signal(symbol, recent, "CALL"),
                evaluate_standard_signal(symbol, recent, "PUT"),
            ) if candidate
        ]
        if candidates:
            return max(candidates, key=lambda item: item["turn_sum"])
            
    return None"""

content = content.replace(old_full, new_full)

# 4. Update evaluate_watch_signal
old_watch = """def evaluate_watch_signal(symbol):
    rows = flow_rows_by_symbol.get(symbol, [])"""
new_watch = """def evaluate_watch_signal(symbol):
    rows = flow_rows_2min.get(symbol, [])"""
content = content.replace(old_watch, new_watch)

# 5. Update main handler
old_handler = """        if "2 MIN" not in text.upper():
            return

        max_keep_rows = max(TURN_MAX_WINDOW + 3, 8)
        for symbol in STRATEGY_SYMBOLS:
            if symbol not in WATCH_SYMBOLS:
                continue

            section = extract_instrument_section(text, symbol)
            metrics = parse_flow_metrics(section)
            if not metrics:
                continue

            price = get_future_price(section, symbol)
            rows = flow_rows_by_symbol.setdefault(symbol, [])
            rows.append(build_flow_row(now, price, metrics))
            if len(rows) > max_keep_rows:
                del rows[:-max_keep_rows]

            active = active_signal_for(symbol, now)
            full_signal = evaluate_full_signal(symbol, active)
            if full_signal:
                await send_full_signal(client, target_entity, symbol, full_signal, now)
                continue

            watch_signal = evaluate_watch_signal(symbol)
            if watch_signal:
                await send_watch_signal(client, target_entity, symbol, watch_signal, now)"""

new_handler = """        upper_text = text.upper()
        if "2 MIN" in upper_text:
            interval = 2
        elif "5 MIN" in upper_text:
            interval = 5
        else:
            return

        max_keep_rows = max(TURN_MAX_WINDOW + 3, 8)
        for symbol in STRATEGY_SYMBOLS:
            if symbol not in WATCH_SYMBOLS:
                continue

            section = extract_instrument_section(text, symbol)
            metrics = parse_flow_metrics(section)
            if not metrics:
                continue

            price = get_future_price(section, symbol)
            
            if interval == 2:
                rows = flow_rows_2min.setdefault(symbol, [])
            else:
                rows = flow_rows_5min.setdefault(symbol, [])
                
            rows.append(build_flow_row(now, price, metrics))
            if len(rows) > max_keep_rows:
                del rows[:-max_keep_rows]

            if interval == 2:
                active = active_signal_for(symbol, now)
                full_signal = evaluate_full_signal(symbol, active)
                if full_signal:
                    await send_full_signal(client, target_entity, symbol, full_signal, now)
                    continue

                watch_signal = evaluate_watch_signal(symbol)
                if watch_signal:
                    await send_watch_signal(client, target_entity, symbol, watch_signal, now)"""

content = content.replace(old_handler, new_handler)

with open("C:\\Users\\kalpe\\gdfl data\\banknifty-dashboard\\scanner_bot.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Scanner Bot update written!")
