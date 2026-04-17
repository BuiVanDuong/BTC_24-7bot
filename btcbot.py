import ccxt
import pandas as pd
import talib
import requests
from datetime import datetime
import os
import time

# -----------------------------
# Cấu hình OKX API + Telegram
# -----------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
OKX_API_KEY = os.environ.get("OKX_API_KEY")
OKX_SECRET = os.environ.get("OKX_SECRET")
OKX_PASSPHRASE = os.environ.get("OKX_PASSPHRASE")
SYMBOL = "BTC/USDT"

exchange = ccxt.okx({
    "apiKey": OKX_API_KEY,
    "secret": OKX_SECRET,
    "password": OKX_PASSPHRASE,
    "enableRateLimit": True
})

TIMEFRAMES = {"1H":"1h","4H":"4h","12H":"12h","1D":"1d","2D":"2D","3D":"3D","1W":"1w"}
RSI_PERIOD = 14
MA_FAST = 9
MA_SLOW = 45

# -----------------------------
# Lấy OHLCV
# -----------------------------
def fetch_ohlcv(symbol, timeframe, limit=500, retries=3):
    for attempt in range(retries):
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"Fetch error {timeframe}, attempt {attempt+1}: {e}")
            time.sleep(2**attempt)
    raise Exception(f"Failed to fetch OHLCV for {timeframe} after {retries} attempts")

def merge_n_day(df_d1, n):
    df_n = pd.DataFrame()
    df_n['open'] = df_d1['open'].iloc[::n].reset_index(drop=True)
    df_n['close'] = df_d1['close'].iloc[n-1::n].reset_index(drop=True)
    df_n['high'] = df_d1['high'].rolling(n).max().iloc[n-1::n].reset_index(drop=True)
    df_n['low']  = df_d1['low'].rolling(n).min().iloc[n-1::n].reset_index(drop=True)
    df_n['volume'] = df_d1['volume'].rolling(n).sum().iloc[n-1::n].reset_index(drop=True)
    df_n['timestamp'] = df_d1['timestamp'].iloc[n-1::n].reset_index(drop=True)
    df_n.fillna(method='ffill', inplace=True)
    return df_n

# -----------------------------
# Phân tích RSI + MA + Trend
# -----------------------------
def analyze_df(df):
    if len(df) < RSI_PERIOD:
        return "Halfway", 50, "", df['close'].iloc[-1], 0, 0
    df['rsi'] = talib.RSI(df['close'], RSI_PERIOD)
    df['ma9'] = talib.SMA(df['close'], MA_FAST)
    df['ma45'] = talib.SMA(df['close'], MA_SLOW)
    last = df.iloc[-1]
    rsi, ma9, ma45, close = last['rsi'], last['ma9'], last['ma45'], last['close']
    trend = "Halfway"
    if len(df) >= 5:
        if close > df['close'].iloc[-5] and rsi > df['rsi'].iloc[-5]:
            trend = "Rising"
        elif close < df['close'].iloc[-5] and rsi < df['rsi'].iloc[-5]:
            trend = "Falling"
    trap = ""
    if rsi < 20: trap="⚠️ Oversold"
    elif rsi > 80: trap="⚠️ Overbought"
    return trend, rsi, trap, close, ma9, ma45

# -----------------------------
# Trạng thái Form Point
# -----------------------------
def forming_state(rsi, ma9, ma45):
    if ma9 != 0 and abs(rsi - ma9)/ma9 <= 0.01:
        return "Sắp hình thành (1)"
    elif (ma9 < rsi < ma45) or (ma45 < rsi < ma9):
        return "Đang hình thành (2)"
    else:
        return None

# -----------------------------
# Phân tích đa khung
# -----------------------------
def multi_timeframe_analysis():
    trends, rsis, traps, formings, closes = {}, {}, {}, {}, {}
    for label, tf in TIMEFRAMES.items():
        try:
            if tf=='2D':
                df_d1 = fetch_ohlcv(SYMBOL,'1d',500)
                df = merge_n_day(df_d1,2)
            elif tf=='3D':
                df_d1 = fetch_ohlcv(SYMBOL,'1d',500)
                df = merge_n_day(df_d1,3)
            else:
                df = fetch_ohlcv(SYMBOL,tf,500)
            trend, rsi, trap, close, ma9, ma45 = analyze_df(df)
            trends[label] = trend
            rsis[label] = rsi
            traps[label] = trap
            closes[label] = close
            formings[label] = forming_state(rsi, ma9, ma45)
        except Exception as e:
            print(f"Error processing {label}: {e}")
            trends[label] = "Halfway"
            rsis[label] = 50
            traps[label] = ""
            closes[label] = 0
            formings[label] = None
    return trends, rsis, traps, formings, closes

# -----------------------------
# Trend Arrow màu
# -----------------------------
def trend_arrow(trend):
    if trend=="Rising": return "⬆️🟢"
    elif trend=="Falling": return "⬇️🔴"
    else: return "➡️🟡"

# -----------------------------
# Cascade + Plan giao dịch
# -----------------------------
def generate_plan(trends, formings, closes):
    cascade_order = ['H4','H12','D1','3D','1W']
    cascade_list = []
    for k in cascade_order:
        state = formings.get(k)
        trend = trends.get(k,"Halfway")
        if trend in ["Rising","Falling"] or state is not None:
            arrow = trend_arrow(trend)
            form_text = f", {state}" if state else ""
            cascade_list.append(f"{k}({arrow}{form_text})")
    follow = []
    for i in range(len(cascade_list)-1):
        follow.append(f"{cascade_list[i]} đang kéo {cascade_list[i+1].split('(')[0]} → nếu đủ lực sẽ kéo theo")
    follow_msg = "\n".join(follow)

    all_keys = ['1H','4H','12H','1D','2D','3D','1W']
    up_count = sum(1 for k in all_keys if trends.get(k)=="Rising")
    down_count = sum(1 for k in all_keys if trends.get(k)=="Falling")
    total = len(all_keys)
    percent_up = round(up_count/total*100)
    percent_down = round(down_count/total*100)

    plan_msg = f"Plan giao dịch:\n- Đồng thuận BUY: {up_count}/{total} khung (~{percent_up}%)\n"
    plan_msg += f"- Đồng thuận SELL: {down_count}/{total} khung (~{percent_down}%)\n"
    for k in all_keys:
        state = formings.get(k)
        if state:
            plan_msg += f"- Khung {k} {state}, Trend={trends[k]}, Giá=${closes[k]:.2f}\n"
    if percent_up>=70:
        plan_msg += "- Xác suất tiếp tục tăng cao → có thể vào lệnh BUY\n"
    elif percent_down>=70:
        plan_msg += "- Xác suất tiếp tục giảm cao → có thể vào lệnh SELL\n"
    else:
        plan_msg += "- Đồng thuận chưa đủ → giữ trạng thái HOLD\n"

    cascade_str = " → ".join(cascade_list)
    return cascade_str, follow_msg, plan_msg

# -----------------------------
# Gửi Telegram
# -----------------------------
def send_telegram(trends, rsis, traps, formings, closes):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cascade_str, follow_msg, plan_msg = generate_plan(trends, formings, closes)
    price_now = closes.get('1H',0)
    msg = (
        f"⏰ {timestamp}\nGiá BTC/USDT: ~${price_now}\n\n"
        f"Cascade:\n{cascade_str}\n\nFollow:\n{follow_msg}\n\n{plan_msg}"
    )
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg}
        )
        print(resp.json())
    except Exception as e:
        print("Error sending Telegram message:", e)

# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    trends, rsis, traps, formings, closes = multi_timeframe_analysis()
    send_telegram(trends, rsis, traps, formings, closes)
