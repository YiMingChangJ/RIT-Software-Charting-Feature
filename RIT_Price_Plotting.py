# %% 
import time
import requests
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

# ====== CONFIG ======
API = "http://flserver.rotman.utoronto.ca:14960/v1"   # <-- update if you prefer hostname instead of IP
HDRS = {"Authorization": "Basic MTox"}

INTERVAL_SEC  = 10      # set to 10s per candle
POLL_INTERVAL = 0.2     # how often we query /securities (seconds)
TICK_LIMIT    = 1800    # stop after this tick (use 300 if you want a short test)

# ------------------ Custom Candlestick Colors ------------------
# Dark Green and Dark Red (Maroon) by default
UP_COLOR   = "#008b66"  # rising candles (Close >= Open)
DOWN_COLOR = "#d60000"  # falling candles (Close < Open)
# --------------------------------------------------------------

# ---------- Setup session ----------
s = requests.Session()
s.headers.update(HDRS)
# or s.auth = ("1", "0")  # depending on how auth is set up


# ---------- Helper to get case tick & status ----------
def get_tick_status():
    """Return the live simulator tick and status."""
    r = s.get(f"{API}/case", timeout=2.0)
    r.raise_for_status()
    j = r.json()
    return j["tick"], j["status"]


# ---------- Helper to get all securities ----------
def get_all_securities():
    r = s.get(f"{API}/securities", timeout=2.0)
    r.raise_for_status()
    return r.json()


# ---------- Helper to get last price for specific ticker ----------
def get_last_price(ticker):
    securities = get_all_securities()
    for sec in securities:
        if sec["ticker"] == ticker:
            return sec["last"]
    raise KeyError(f"Ticker {ticker} not found in /securities")


# ---------- Helper to get current & previous news ----------
def get_news_headlines():
    """
    Return (current_news, previous_news).

    By spec:
      - most recent news is data[0]
      - previous news is data[1]
    """
    try:
        r = s.get(f"{API}/news", timeout=2.0)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return "", ""

    cur = ""
    prev = ""

    if isinstance(data, list):
        if len(data) > 0:
            cur = _extract_headline(data[0])
        if len(data) > 1:
            prev = _extract_headline(data[1])
    else:
        # Non-list: treat as single current headline
        cur = _extract_headline(data)

    return cur, prev


def _extract_headline(item):
    """Best-effort extraction of a headline string from an item."""
    if isinstance(item, dict):
        for key in ("headline", "title", "news", "text", "message"):
            if key in item:
                return str(item[key])
        return str(item)
    return str(item)


# ---------- Discover tickers & choose ONE ----------
securities = get_all_securities()
all_tickers = [sec["ticker"] for sec in securities]
print("All tickers:", all_tickers)

# Choose the first ticker for now. You can hardcode instead, e.g. TARGET_TICKER = "RTM"
TARGET_TICKER = all_tickers[0]
print("Tracking ticker:", TARGET_TICKER)

# ---------- Candlestick storage ----------
# Each candle is a dict: {bucket, open, high, low, close}
candles = []
current_candle = None

# ---------- Matplotlib style ----------
size = 20
plt.rcParams['lines.linewidth'] = 3
plt.rcParams.update({'font.size': size})
plt.rc('xtick', labelsize=size - 2)
plt.rc('ytick', labelsize=size - 2)
plt.rc('font', family='serif')

plt.ion()
fig, ax = plt.subplots(figsize=(12, 6))

# Make extra space at the top for news + info lines
fig.subplots_adjust(top=0.78)

ax.set_xlabel("Time (Ticks)")
ax.set_ylabel("Price")

# News texts at very top of the figure
previous_news_text = fig.text(
    0.5, 0.97, "", ha="center", va="top",
    fontsize=size - 4, color="dimgray"
)
current_news_text = fig.text(
    0.5, 0.93, "", ha="center", va="top",
    fontsize=size, color="green", fontweight="bold"
)

# Info texts just above the graph (left: index, right: time remaining)
info_left_text = fig.text(
    0.05, 0.84, "", ha="left", va="bottom",
    fontsize=size - 2
)
info_right_text = fig.text(
    0.95, 0.84, "", ha="right", va="bottom",
    fontsize=size - 2
)

# ---------- Real-time loop ----------
t0 = time.time()

while True:
    # Check case status
    try:
        tick, status = get_tick_status()
    except Exception as e:
        print("Error getting case status:", e)
        break

    print(f"tick={tick}, status={status}")

    # Stop condition: tick >= limit OR status not active/running
    if tick >= TICK_LIMIT or status.lower() not in ("active", "running"):
        print(f"Stopping: tick={tick}, status={status}")
        break

    # Get latest price (current index level)
    try:
        price = get_last_price(TARGET_TICKER)
    except Exception as e:
        print("Error getting price:", e)
        time.sleep(POLL_INTERVAL)
        continue

    # In case last price is None (no trades yet)
    if price is None:
        time.sleep(POLL_INTERVAL)
        continue

    # Get current & previous news directly from /news
    current_news, previous_news = get_news_headlines()

    now = time.time()
    elapsed = now - t0

    # Determine which candle "bucket" this time belongs to
    bucket = int(elapsed // INTERVAL_SEC)  # 0,1,2,...

    if current_candle is None or bucket != current_candle["bucket"]:
        # Start a new candle
        current_candle = {
            "bucket": bucket,
            "open":  price,
            "high":  price,
            "low":   price,
            "close": price,
        }
        candles.append(current_candle)
    else:
        # Update existing candle
        current_candle["high"]  = max(current_candle["high"], price)
        current_candle["low"]   = min(current_candle["low"],  price)
        current_candle["close"] = price

    # ---------- Redraw candlesticks ----------
    ax.clear()
    ax.set_xlabel("Time (Ticks)")
    ax.set_ylabel("Price")

    if candles:
        xs     = [c["bucket"] * INTERVAL_SEC for c in candles]
        opens  = [c["open"]  for c in candles]
        highs  = [c["high"]  for c in candles]
        lows   = [c["low"]   for c in candles]
        closes = [c["close"] for c in candles]

        width = INTERVAL_SEC * 0.6  # candle body width in time units

        # Precompute a minimal visible body size for completely flat candles
        price_range = max(highs) - min(lows)
        min_body_height = price_range * 0.001 if price_range > 0 else 0.01

        for x, o, h, l, c in zip(xs, opens, highs, lows, closes):
            # Use custom colors
            color = UP_COLOR if c >= o else DOWN_COLOR

            # Determine the top and bottom of the rectangular body
            body_top = max(o, c)
            body_bottom = min(o, c)

            # --- Draw Wicks (only the portions not covered by the bar) ---

            # 1. Upper Wick (from High 'h' down to body_top)
            if h > body_top:
                ax.vlines(x, body_top, h, color=color, linewidth=1.0)

            # 2. Lower Wick (from body_bottom down to Low 'l')
            if l < body_bottom:
                ax.vlines(x, l, body_bottom, color=color, linewidth=1.0)

            # --- Draw Body ---
            body_height = abs(c - o)
            if body_height == 0:
                # Draw a tiny body so flat candles are visible
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

        ax.yaxis.grid(True, linestyle='--', alpha=0.4)
        ax.set_xlim(xs[0] - INTERVAL_SEC, xs[-1] + INTERVAL_SEC)

    ax.relim()
    ax.autoscale_view()

    # ---------- Update info: current index level & time remaining ----------
    remaining_ticks = max(TICK_LIMIT - tick, 0)
    rem_min = remaining_ticks // 60
    rem_sec = remaining_ticks % 60

    info_left_text.set_text(
        r"$\bf{Current\ Index\ Level:}$ " + f"{price:.2f}"
    )
    info_right_text.set_text(
        r"$\bf{Time\ Remaining:}$ " + f"{rem_min:02d}:{rem_sec:02d}"
    )

    # ---------- Update news texts (figure title area) ----------
    previous_news_text.set_text(previous_news or "")
    current_news_text.set_text(current_news or "")

    fig.canvas.draw_idle()
    plt.pause(0.01)
    time.sleep(POLL_INTERVAL)

print("Done. Case ended or tick limit reached.")
plt.ioff()
plt.show()

# %%
