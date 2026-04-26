import requests
import pandas as pd
import numpy as np
from datetime import datetime
import os

OKX_BASE = "https://www.okx.com/api/v5/market/candles"
SYMBOL = os.getenv("SYMBOL", "BTC-USDT")

TIMEFRAMES = {
    "Cố (W)":   {"okx": "1W",  "label": "W",   "weight": 5},
    "Ông (3D)": {"okx": "3D",  "label": "3D",  "weight": 4},
    "Cha (D1)": {"okx": "1D",  "label": "D1",  "weight": 3},
    "Con (H12)":{"okx": "12H", "label": "H12", "weight": 2},
    "Cháu (H4)":{"okx": "4H",  "label": "H4",  "weight": 1},
}

def fetch_candles(instId, bar, limit=100):
    params = {"instId": instId, "bar": bar, "limit": limit}
    r = requests.get(OKX_BASE, params=params, timeout=10)
    data = r.json().get("data", [])
    if not data:
        return None
    df = pd.DataFrame(data, columns=["ts","open","high","low","close","vol","volCcy","volCcyQuote","confirm"])
    df = df[df["confirm"] == "1"].copy()
    df["close"] = df["close"].astype(float)
    df["high"]  = df["high"].astype(float)
    df["low"]   = df["low"].astype(float)
    df = df.iloc[::-1].reset_index(drop=True)
    return df

def calc_ma(series, period):
    return series.rolling(window=period).mean()

def calc_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(window=period).mean()
    loss  = (-delta.clip(upper=0)).rolling(window=period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def detect_form(df):
    if df is None or len(df) < 50:
        return {"direction": None, "diem": 0, "pct": 0, "rsi": None, "ma9": None, "ma45": None, "price": None,
                "gap_pct": 0, "gap_status": "N/A", "trigger": "Không đủ dữ liệu"}

    df = df.copy()
    df["ma9"]  = calc_ma(df["close"], 9)
    df["ma45"] = calc_ma(df["close"], 45)
    df["rsi"]  = calc_rsi(df["close"], 14)

    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    prev2 = df.iloc[-3]

    price = last["close"]
    ma9   = last["ma9"]
    ma45  = last["ma45"]
    rsi   = last["rsi"]

    if pd.isna(ma9) or pd.isna(ma45) or pd.isna(rsi):
        return {"direction": None, "diem": 0, "pct": 0, "rsi": rsi, "ma9": ma9, "ma45": ma45, "price": price,
                "gap_pct": 0, "gap_status": "N/A", "trigger": "Không đủ dữ liệu"}

    sell_d1 = (prev["ma9"] >= prev["ma45"]) and (ma9 < ma45)
    sell_d2 = (ma9 < ma45) and (prev["ma9"] < prev["ma45"]) and \
              (abs(prev["ma9"] - prev["ma45"]) / prev["ma45"] < 0.005) and \
              (ma9 < prev["ma9"])
    sell_d3 = (ma9 < ma45) and (price < ma45) and (rsi < 50)

    buy_d1  = (prev["ma9"] <= prev["ma45"]) and (ma9 > ma45)
    buy_d2  = (ma9 > ma45) and (prev["ma9"] > prev["ma45"]) and \
              (abs(prev["ma9"] - prev["ma45"]) / prev["ma45"] < 0.005) and \
              (ma9 > prev["ma9"])
    buy_d3  = (ma9 > ma45) and (price > ma45) and (rsi > 50)

    sell_score = sum([sell_d1, sell_d2, sell_d3])
    buy_score  = sum([buy_d1,  buy_d2,  buy_d3])

    if sell_score == 0 and buy_score == 0:
        if ma9 < ma45 and rsi < 55:
            direction = "SELL"
            diem = 0
            pct  = round((1 - (ma9/ma45)) * 100 * 10, 1)
        elif ma9 > ma45 and rsi > 45:
            direction = "BUY"
            diem = 0
            pct  = round(((ma9/ma45) - 1) * 100 * 10, 1)
        else:
            direction = None
            diem = 0
            pct  = 0
    elif sell_score >= buy_score:
        direction = "SELL"
        diem = sell_score
        pct  = round((sell_score / 3) * 100)
    else:
        direction = "BUY"
        diem = buy_score
        pct  = round((buy_score / 3) * 100)

    gap_now      = (ma9 - ma45) / ma45 * 100
    gap_prev     = (prev["ma9"] - prev["ma45"]) / prev["ma45"] * 100
    gap_abs_now  = abs(gap_now)
    gap_abs_prev = abs(gap_prev)

    if gap_abs_now < gap_abs_prev * 0.92:
        gap_status = "thu hẹp 🔻"
    elif gap_abs_now > gap_abs_prev * 1.08:
        gap_status = "nới rộng 🔺"
    else:
        gap_status = "ổn định ➡️"

    if diem == 1:
        trigger = f"Điểm 1 — MA9 vừa {'cắt lên' if direction == 'BUY' else 'cắt xuống'} MA45"
    elif diem == 2:
        trigger = f"Điểm 2 — Retest MA45 {'thành công' if direction == 'BUY' else 'thất bại'}"
    elif diem == 3:
        trigger = f"Điểm 3 + Gap {gap_status.split()[0]}"
    elif diem == 0 and gap_status.startswith("thu hẹp"):
        trigger = f"Gap thu hẹp — sắp {'cắt lên' if direction == 'BUY' else 'cắt xuống'}"
    else:
        trigger = f"Theo dõi — MA {'trên' if direction == 'BUY' else 'dưới'} chuẩn"

    return {
        "direction":  direction,
        "diem":       diem,
        "pct":        min(pct, 99) if diem == 0 else pct,
        "rsi":        round(rsi, 1),
        "ma9":        round(ma9, 2),
        "ma45":       round(ma45, 2),
        "price":      round(price, 2),
        "gap_pct":    round(gap_abs_now, 3),
        "gap_status": gap_status,
        "trigger":    trigger,
    }

def analyze_all(symbol=None):
    sym = symbol or SYMBOL
    results = {}
    for name, cfg in TIMEFRAMES.items():
        df = fetch_candles(sym, cfg["okx"])
        results[name] = {**detect_form(df), "label": cfg["label"], "weight": cfg["weight"]}
    return results

def calc_score(results):
    directions = [v["direction"] for v in results.values() if v["direction"]]
    if not directions:
        return 0, None
    buy_count  = directions.count("BUY")
    sell_count = directions.count("SELL")
    total = len(TIMEFRAMES)
    if sell_count > buy_count:
        return round((sell_count / total) * 100), "SELL"
    elif buy_count > sell_count:
        return round((buy_count / total) * 100), "BUY"
    return 0, None

def detect_cascade(results):
    order = list(TIMEFRAMES.keys())[::-1]
    cascade_buy  = []
    cascade_sell = []
    for name in order:
        v = results.get(name, {})
        if v.get("direction") == "BUY":
            cascade_buy.append(v["label"])
        if v.get("direction") == "SELL":
            cascade_sell.append(v["label"])
    return cascade_buy, cascade_sell

# ─────────────────────────────────────────────

TELEGRAM_TOKEN   = os.getenv("BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("CHAT_ID")
MIN_SCORE        = int(os.getenv("MIN_SCORE", "60"))

CHECK = "✅"
WAIT  = "⏳"
UP    = "↑"
DOWN  = "↓"

FAMILY = {
    "Cố (W)":    "Cố",
    "Ông (3D)":  "Ông",
    "Cha (D1)":  "Cha",
    "Con (H12)": "Con",
    "Cháu (H4)": "Cháu",
}

def analyze_cascade_impact(results, direction):
    order     = ["Cháu (H4)", "Con (H12)", "Cha (D1)", "Ông (3D)", "Cố (W)"]
    confirmed = [k for k in order if results.get(k, {}).get("direction") == direction]
    pending   = [k for k in order if results.get(k, {}).get("direction") != direction]
    impact_lines = []

    for i in range(len(confirmed) - 1):
        small    = FAMILY[confirmed[i]]
        big      = FAMILY[confirmed[i + 1]]
        tf_small = results[confirmed[i]]["label"]
        tf_big   = results[confirmed[i + 1]]["label"]
        arrow    = UP if direction == "BUY" else DOWN
        impact_lines.append(f"📡 {small}({tf_small})({arrow}) đang kéo {big}({tf_big}) theo")

    if pending and len(confirmed) >= 2:
        next_p    = pending[-1]
        tf_p      = results[next_p]["label"]
        name_p    = FAMILY[next_p]
        remaining = len(pending)
        if remaining == 1:
            impact_lines.append(f"🔭 {name_p}({tf_p}) chưa xác nhận — nếu đủ mạnh sẽ kéo toàn bộ hệ thống")
        else:
            impact_lines.append(
                f"🔭 Cascade đã lan tới {FAMILY[confirmed[-1]]}({results[confirmed[-1]]['label']}) "
                f"→ xu hướng {'BUY' if direction == 'BUY' else 'SELL'} đang hình thành ở khung lớn"
            )

    n = len(confirmed)
    if n == 5:
        strength = "Rất mạnh 🚀" if direction == "BUY" else "Rất mạnh 📉"
        desc     = "Toàn bộ 5 khung đồng thuận — lực kéo cực mạnh!"
    elif n == 4:
        strength = "Mạnh 💪"
        desc     = f"4/5 khung — chỉ còn {FAMILY[pending[0]]} chưa xác nhận"
    elif n == 3:
        pend_str = " + ".join([FAMILY[p] for p in pending])
        strength = "Trung bình ⚡"
        desc     = f"3/5 khung — cần thêm {pend_str} xác nhận"
    elif n == 2:
        strength = "Yếu ⚠️"
        desc     = f"Chỉ {n}/5 khung — chờ thêm khung lớn hơn"
    else:
        strength = "Rất yếu 🔸"
        desc     = "Chưa đủ tín hiệu cascade"

    return {"impact_lines": impact_lines, "strength": strength, "desc": desc,
            "confirmed": confirmed, "pending": pending}

def build_trade_plan(results, direction, score, cascade_info, symbol):
    lines     = ["🎯 *Plan giao dịch*"]
    price     = results.get("Cháu (H4)", {}).get("price", 0)
    ma9_h4    = results.get("Cháu (H4)", {}).get("ma9", 0) or 0
    ma45_h4   = results.get("Cháu (H4)", {}).get("ma45", 0) or 0
    confirmed = cascade_info["confirmed"]
    pending   = cascade_info["pending"]
    n         = len(confirmed)
    d1_diem   = results.get("Cha (D1)", {}).get("diem", 0)
    w_diem    = results.get("Cố (W)", {}).get("diem", 0)

    if n >= 4:
        lines.append(f"Tất cả các khung từ H4 → W đều đồng thuận hướng {'lên' if direction == 'BUY' else 'xuống'}.")
    elif n == 3:
        c_str = " + ".join([FAMILY[c] for c in confirmed])
        lines.append(f"{c_str} đồng thuận — cascade đang lan lên khung lớn.")
    else:
        c_str = " + ".join([FAMILY[c] for c in confirmed])
        lines.append(f"Mới có {c_str} — chưa đủ cascade mạnh.")

    if direction == "SELL":
        if d1_diem >= 2: lines.append("D1 đang trả trap đỉnh → xác suất tiếp tục giảm cao (~70%).")
        if w_diem  >= 1: lines.append("W breakout xuống → đà giảm đang được xác nhận.")
    else:
        if d1_diem >= 2: lines.append("D1 đang trả trap đáy → xác suất tiếp tục tăng cao (~70%).")
        if w_diem  >= 1: lines.append("W breakout lên → đà tăng đang được xác nhận.")

    lines.append("")

    if score >= MIN_SCORE and n >= 3:
        action = "BUY" if direction == "BUY" else "SELL"
        arrow  = "↗️" if direction == "BUY" else "↘️"
        lines.append(f"Nếu muốn vào lệnh *{action}*: {arrow}")
        lines.append(f"{CHECK} Đồng thuận: ĐẠT ({n}/5 khung)")
        lines.append(f"📍 Vào tại vùng giá ~ *${price:,.2f}*")
        atr = max(abs(ma9_h4 - ma45_h4) * 2, price * 0.015)
        if direction == "SELL":
            sl  = round(price + atr, 2)
            tp1 = round(price - atr * 1.5, 2)
            tp2 = round(price - atr * 2.5, 2)
            tp3 = round(price - atr * 4.0, 2)
        else:
            sl  = round(price - atr, 2)
            tp1 = round(price + atr * 1.5, 2)
            tp2 = round(price + atr * 2.5, 2)
            tp3 = round(price + atr * 4.0, 2)
        lines.append(f"🛑 SL: ~${sl:,.2f} ({'trên đỉnh' if direction == 'SELL' else 'dưới đáy'} gần nhất)")
        lines.append(f"🎯 TP1: ~${tp1:,.2f}  |  TP2: ~${tp2:,.2f}  |  TP3: ~${tp3:,.2f}")
        lines.append("")
        lines.append("⚠️ Risk tối đa 1% account/lệnh — tuân thủ FTMO rules")
    elif score >= 40 and n >= 2:
        pend_str = " + ".join([FAMILY[p] for p in pending[:2]])
        lines.append(f"⏳ Tín hiệu đang hình thành — chưa đủ điều kiện vào")
        lines.append(f"👀 Chờ: *{pend_str}* xác nhận")
        lines.append(f"📍 Vùng entry tiềm năng: ~${price:,.2f}")
    else:
        lines.append(f"🔸 Chưa đủ tín hiệu (Score: {score}%)")
        lines.append("👀 Tiếp tục quan sát, không hành động")

    return lines

def format_message(results, score, direction, cascade_buy, cascade_sell, symbol="BTC-USDT"):
    now          = datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")
    cascade_info = analyze_cascade_impact(results, direction)
    lines        = []

    trigger_frame = cascade_info["confirmed"][0] if cascade_info["confirmed"] else None
    trigger_title = results[trigger_frame]["trigger"] if trigger_frame else "Đang theo dõi"
    tf_label      = results[trigger_frame]["label"] if trigger_frame else ""

    lines += [
        f"{'─' * 28}",
        f"🤖 *XTB Bot* | {symbol}",
        f"🕐 {now}",
        f"⚡ *{tf_label} → {trigger_title}*",
        f"{'─' * 28}",
        "",
    ]

    n_confirm = len(cascade_info["confirmed"])
    total     = len(TIMEFRAMES)
    checks    = CHECK * n_confirm + WAIT * (total - n_confirm)
    lines.append(f"Đồng thuận: {n_confirm}/{total} khung {checks}")
    lines.append("")

    dir_icons = {"BUY": "🟢", "SELL": "🔴", None: "⚪"}
    lines.append("🏡 *Cố Ông Cha Con Cháu*")
    for name, v in results.items():
        d          = v.get("direction")
        emoji      = dir_icons[d]
        diem       = v.get("diem", 0)
        pct        = v.get("pct", 0)
        chk        = CHECK if d == direction else WAIT
        label      = v.get("label", "")
        gap_status = v.get("gap_status", "")
        gap_note   = f" | {gap_status}" if "thu hẹp" in gap_status or "nới rộng" in gap_status else ""
        lines.append(f"{emoji} {FAMILY[name]}({label}) {pct}% | Đ{diem}{chk}{gap_note}")

    lines.append(f"Score: *+{score}%*")
    lines.append("")

    if n_confirm >= 2:
        arrow     = UP if direction == "BUY" else DOWN
        chain_str = " → ".join([f"{FAMILY[c]}({results[c]['label']})({arrow})" for c in cascade_info["confirmed"]])
        lines.append(f"🔗 Chuỗi cascade {'BUY' if direction == 'BUY' else 'SELL'}: {chain_str}")
        has_breakout = any("Điểm 3" in results[c].get("trigger", "") for c in cascade_info["confirmed"])
        if has_breakout:
            lines.append("💥 có BREAKOUT → lực kéo rất mạnh!")
        lines += cascade_info["impact_lines"]
        lines.append(f"📊 {cascade_info['desc']}")
        gap_alerts = [f"{FAMILY[k]}({results[k]['label']})" for k in cascade_info["pending"]
                      if "thu hẹp" in results[k].get("gap_status", "")]
        if gap_alerts:
            lines.append(f"🔔 Gap đang thu hẹp ở: {', '.join(gap_alerts)} → sắp có tín hiệu")
        lines.append("")

    lines += build_trade_plan(results, direction, score, cascade_info, symbol)
    lines += ["", f"{'─' * 28}", "⚡ _XTB Bot | OKX Data_"]

    return "\n".join(lines)

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  Chưa set BOT_TOKEN / CHAT_ID\n")
        print(message)
        return False
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    r    = requests.post(url, data=data, timeout=10)
    if r.status_code == 200:
        print("✅ Đã gửi Telegram!")
        return True
    print(f"❌ Lỗi: {r.status_code} — {r.text}")
    return False

def run(symbol=None, force=False):
    sym = symbol or os.getenv("SYMBOL", "BTC-USDT")
    print(f"🔍 Analyzing {sym}...")
    results                   = analyze_all(sym)
    score, direction          = calc_score(results)
    cascade_buy, cascade_sell = detect_cascade(results)
    print(f"Score: {score}% | Direction: {direction}")
    for name, v in results.items():
        print(f"  {FAMILY[name]}: {v.get('direction')} | Đ{v.get('diem')} | {v.get('pct')}% | RSI {v.get('rsi')}")
    if score >= MIN_SCORE or force:
        msg = format_message(results, score, direction, cascade_buy, cascade_sell, sym)
        send_telegram(msg)
    else:
        print(f"Score {score}% < {MIN_SCORE}% — không gửi")

if __name__ == "__main__":
    run(force=True)
