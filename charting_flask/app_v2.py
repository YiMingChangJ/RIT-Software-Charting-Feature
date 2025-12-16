# app.py
import io
import time
import textwrap
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from flask import Flask, Response, render_template, request, jsonify

app = Flask(__name__)

"http://127.0.0.1:5000"
# ====== CONFIG ======
API = "http://flserver.rotman.utoronto.ca:14960/v1"
HDRS = {"Authorization": "Basic MTox"}

TICK_LIMIT         = 1800     # freeze once tick>=limit (or case stops)
CASE_POLL_INTERVAL = 0.5
NEWS_POLL_INTERVAL = 1.0

# History polling (avoid hammering endpoint every frame)
HIST_POLL_INTERVAL = 0.5
HISTORY_LIMIT      = 15000     # if API supports "limit", we send it; otherwise ignored

DEFAULT_CANDLE_TICKS = 10     # ticks per candle (10 => 10-tick candles)
VISIBLE_MAX          = None   # None = show all candles; or set e.g. 400

# ------------------ Custom Candlestick Colors ------------------
UP_COLOR   = "#008b66"
DOWN_COLOR = "#d60000"
# --------------------------------------------------------------

# ---------- Setup session ----------
s = requests.Session()
s.headers.update(HDRS)

# ---------- Plot styling ----------
size = 18
plt.rcParams["lines.linewidth"] = 3
plt.rcParams.update({"font.size": size})
plt.rc("xtick", labelsize=size)
plt.rc("ytick", labelsize=size)
plt.rc("font", family="serif")

# ---------- Helpers ----------
def get_tick_status():
    r = s.get(f"{API}/case", timeout=2.0)
    r.raise_for_status()
    j = r.json()
    return int(j["tick"]), str(j["status"])

def get_news_headlines():
    try:
        r = s.get(f"{API}/news", timeout=2.0)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None, None

    cur = ""
    prev = ""

    if isinstance(data, list):
        if len(data) > 0 and isinstance(data[0], dict):
            cur = data[0].get("headline", "") or ""
        if len(data) > 1 and isinstance(data[1], dict):
            prev = data[1].get("headline", "") or ""
    elif isinstance(data, dict):
        cur = data.get("headline", "") or ""
    else:
        cur = str(data)

    return cur, prev

def wrap_headline(text: str, width: int = 100, max_lines: int = 4) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    lines = textwrap.wrap(
        text,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )
    lines = lines[:max_lines]
    return "\n".join(lines)

def get_tickers():
    r = s.get(f"{API}/securities", timeout=2.0)
    r.raise_for_status()
    data = r.json()
    tickers = []
    if isinstance(data, list):
        for sec in data:
            if isinstance(sec, dict) and sec.get("ticker"):
                tickers.append(sec["ticker"])
    return sorted(set(tickers))

def fetch_history_rows(ticker: str):
    """
    Tries to read /securities/history in a robust way.
    Supports:
      - list of dicts
      - dict wrapping (e.g., {"history":[...]})
    Each row may contain:
      - OHLC: open/high/low/close (+ tick)
      - or price series: tick + (close/last/price)
    """
    params = {"ticker": ticker}
    # If your API supports it, this reduces payload; if not, it’s ignored safely.
    params["limit"] = HISTORY_LIMIT

    r = s.get(f"{API}/securities/history", params=params, timeout=3.0)
    r.raise_for_status()
    data = r.json()

    if isinstance(data, dict):
        # common wrappers: {"history": [...]}, or {"data": [...]}
        if "history" in data and isinstance(data["history"], list):
            data = data["history"]
        elif "data" in data and isinstance(data["data"], list):
            data = data["data"]

    if not isinstance(data, list):
        return []

    rows = []
    for row in data:
        if not isinstance(row, dict):
            continue

        t = row.get("tick", None)
        if t is None:
            # sometimes it's "time" or "timestamp"
            t = row.get("timestamp", row.get("time", None))
        try:
            t = int(t)
        except Exception:
            continue

        # If OHLC exists, keep it
        if all(k in row for k in ("open", "high", "low", "close")):
            try:
                rows.append({
                    "tick": t,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low":  float(row["low"]),
                    "close":float(row["close"]),
                })
            except Exception:
                continue
        else:
            # Otherwise, treat as tick-price series
            p = row.get("close", row.get("last", row.get("price", None)))
            if p is None:
                continue
            try:
                rows.append({"tick": t, "price": float(p)})
            except Exception:
                continue

    rows.sort(key=lambda x: x["tick"])
    return rows

def build_candles_from_history(rows, candle_ticks: int):
    """
    Converts history rows into candle dicts:
      {bucket, start_tick, open, high, low, close}
    If rows already have OHLC, we still bucket them (so you can pick candle_ticks>1).
    """
    candles = []
    cur = None

    def row_close(r):
        return r.get("close", r.get("price", None))

    for r in rows:
        tick = r["tick"]
        price_close = row_close(r)
        if price_close is None:
            continue

        bucket = tick // candle_ticks
        start_tick = bucket * candle_ticks

        if cur is None or bucket != cur["bucket"]:
            # start new candle
            o = r.get("open", price_close)
            h = r.get("high", price_close)
            l = r.get("low",  price_close)
            c = r.get("close", price_close)

            cur = {
                "bucket": bucket,
                "start_tick": start_tick,
                "open":  float(o),
                "high":  float(h),
                "low":   float(l),
                "close": float(c),
            }
            candles.append(cur)
        else:
            # update existing candle
            h = r.get("high", price_close)
            l = r.get("low",  price_close)
            c = r.get("close", price_close)
            cur["high"]  = max(cur["high"], float(h))
            cur["low"]   = min(cur["low"],  float(l))
            cur["close"] = float(c)

    return candles

# ---------- Global state (news + cache) ----------
current_news = ""
previous_news = ""
last_news_poll = 0.0
last_case_poll = 0.0
last_hist_poll = 0.0

tick = 0
status = "unknown"
finished = False

# cache per ticker+candle_ticks
history_cache = {}   # key: (ticker, candle_ticks) -> dict(candles, last_price, last_tick_seen)

def update_state(ticker: str, candle_ticks: int):
    global last_case_poll, last_news_poll, last_hist_poll
    global tick, status, finished
    global current_news, previous_news

    now = time.time()

    # Poll /case
    if now - last_case_poll >= CASE_POLL_INTERVAL:
        try:
            tick, status = get_tick_status()
        except Exception as e:
            print("Error getting case status:", e)
        else:
            last_case_poll = now
            print(f"tick={tick}, status={status}")

        if tick >= TICK_LIMIT or status.lower() not in ("active", "running"):
            finished = True

    # Poll /news
    if not finished and (now - last_news_poll >= NEWS_POLL_INTERVAL):
        cur, prev = get_news_headlines()
        if cur is not None:
            current_news = cur
        if prev is not None:
            previous_news = prev
        last_news_poll = now

    # Poll /securities/history (cached)
    key = (ticker, candle_ticks)
    if key not in history_cache:
        history_cache[key] = {"candles": [], "last_price": 0.0, "last_tick_seen": -1}

    if now - last_hist_poll >= HIST_POLL_INTERVAL and not (finished and history_cache[key]["candles"]):
        try:
            rows = fetch_history_rows(ticker)
            candles = build_candles_from_history(rows, candle_ticks)
            last_price = 0.0
            if rows:
                last = rows[-1]
                last_price = float(last.get("close", last.get("price", 0.0)))

            history_cache[key] = {
                "candles": candles,
                "last_price": last_price,
                "last_tick_seen": rows[-1]["tick"] if rows else -1,
            }
        except Exception as e:
            print("Error fetching history:", e)

        last_hist_poll = now

def make_figure(ticker: str, candle_ticks: int):
    fig, ax = plt.subplots(figsize=(19, 11))
    fig.subplots_adjust(top=0.78)

    wrapped_current = wrap_headline(current_news or "", width=85, max_lines=4)
    wrapped_previous = wrap_headline(previous_news or "", width=110, max_lines=3)

    previous_news_text = fig.text(
        0.5, 0.97, "", ha="center", va="top",
        fontsize=size - 4, color="dimgray"
    )
    current_news_text = fig.text(
        0.5, 0.91, "", ha="center", va="top",
        fontsize=size, color="#00058b", fontweight="bold"
    )

    info_left_text = fig.text(0.1, 0.8, "", ha="left", va="bottom", fontsize=size)
    info_right_text = fig.text(0.9, 0.8, "", ha="right", va="bottom", fontsize=size)

    ax.yaxis.grid(True, linestyle="--", alpha=0.7)
    ax.set_xlabel("Tick")
    ax.set_ylabel("Price")

    key = (ticker, candle_ticks)
    cache = history_cache.get(key, {"candles": [], "last_price": 0.0})
    candles = cache["candles"]
    last_price = cache["last_price"]

    if candles:
        draw_candles = candles[-VISIBLE_MAX:] if (VISIBLE_MAX and len(candles) > VISIBLE_MAX) else candles

        xs     = [c["start_tick"] for c in draw_candles]
        opens  = [c["open"] for c in draw_candles]
        highs  = [c["high"] for c in draw_candles]
        lows   = [c["low"] for c in draw_candles]
        closes = [c["close"] for c in draw_candles]

        width = candle_ticks * 0.6

        price_range = max(highs) - min(lows)
        min_body_height = price_range * 0.001 if price_range > 0 else 0.01

        for x, o, h, l, c in zip(xs, opens, highs, lows, closes):
            color = UP_COLOR if c >= o else DOWN_COLOR

            body_top = max(o, c)
            body_bottom = min(o, c)

            if h > body_top:
                ax.vlines(x, body_top, h, color=color, linewidth=1.0)
            if l < body_bottom:
                ax.vlines(x, l, body_bottom, color=color, linewidth=1.0)

            body_height = abs(c - o)
            if body_height == 0:
                body_height = min_body_height

            rect = Rectangle(
                (x - width / 2, body_bottom),
                width,
                body_height,
                facecolor=color,
                edgecolor=color,
                alpha=0.7,
            )
            ax.add_patch(rect)

        ax.set_xlim(xs[0] - candle_ticks, xs[-1] + candle_ticks)

    ax.relim()
    ax.autoscale_view()

    remaining_ticks = max(TICK_LIMIT - tick, 0)
    rem_min = remaining_ticks // 60
    rem_sec = remaining_ticks % 60

    info_left_text.set_text(r"$\bf{Ticker:}$ " + f"{ticker}   " + r"$\bf{Last:}$ " + f"{last_price}")
    info_right_text.set_text(r"$\bf{Time\ Remaining:}$ " + f"{rem_min:02d}:{rem_sec:02d}")

    previous_news_text.set_text(wrapped_previous or "")
    current_news_text.set_text(wrapped_current or "")

    return fig

# ---------- Routes ----------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/tickers")
def tickers():
    try:
        return jsonify({"tickers": get_tickers()})
    except Exception as e:
        return jsonify({"tickers": [], "error": str(e)}), 500

@app.route("/chart.png")
def chart_png():
    ticker = request.args.get("ticker", "").strip()
    candle_ticks = request.args.get("candle", "").strip()

    # defaults
    if not ticker:
        try:
            ticker = get_tickers()[0]
        except Exception:
            ticker = "CRZY"

    try:
        candle_ticks = int(candle_ticks) if candle_ticks else DEFAULT_CANDLE_TICKS
        candle_ticks = max(1, candle_ticks)
    except Exception:
        candle_ticks = DEFAULT_CANDLE_TICKS

    update_state(ticker, candle_ticks)
    fig = make_figure(ticker, candle_ticks)

    output = io.BytesIO()
    FigureCanvas(fig).print_png(output)
    plt.close(fig)
    return Response(output.getvalue(), mimetype="image/png")

if __name__ == "__main__":
    app.run(debug=True)
