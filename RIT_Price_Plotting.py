# %% 
import time
import requests
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

# ====== CONFIG ======
API = "http://flserver.rotman.utoronto.ca:14960/v1"   # <-- update if you prefer hostname instead of IP
HDRS = {"Authorization": "Basic MTox"}

INTERVAL_SEC       = 10     # set to 10s per candle
POLL_INTERVAL      = 0.2    # how often we query /securities (seconds)
TICK_LIMIT         = 1800   # stop after this tick (use 300 if you want a short test)
CASE_POLL_INTERVAL = 0.5    # how often we poll /case (tick & status)
NEWS_POLL_INTERVAL = 4.0    # how often we poll /news (seconds)
VISIBLE_MAX        = None   # None = show all candles, or set e.g. 400 for speed

# ------------------ Custom Candlestick Colors ------------------
# Dark Green and Dark Red (Maroon) by default
UP_COLOR   = "#008b66"  # rising candles (Close >= Open)
DOWN_COLOR = "#d60000"  # falling candles (Close < Open)
# --------------------------------------------------------------

# ---------- Setup session ----------
s = requests.Session()
s.headers.update(HDRS)
# or s.auth = ("1", "1")  # depending on how auth is set up


# ---------- Helper Functions ----------
def get_tick_status():
    """Return the live simulator tick and status."""
    r = s.get(f"{API}/case")
    j = r.json()
    return j["tick"], j["status"]
def get_news_headlines():
    """
    Return (current_news, previous_news) or (None, None) on error.

    By spec:
      - most recent news is data[0]
      - previous news is data[1]
    """
    try:
        r = s.get(f"{API}/news")
        r.raise_for_status()
        data = r.json()
    except Exception:
        return None, None

    cur = ""
    prev = ""

    if isinstance(data, list):
        if len(data) > 0:
            cur = data[0]['headline']
        if len(data) > 1:
            prev = data[1]['headline']
    else:
        cur = data[0]['headline']

    return cur, prev


tkr = s.get(f"{API}/securities").json()[0]['ticker']

# ---------- Candlestick storage ----------
# Each candle is a dict: {bucket, open, high, low, close}
candles = []
current_candle = None

# ---------- Matplotlib style ----------
size = 15
plt.rcParams['lines.linewidth'] = 3
plt.rcParams.update({'font.size': size})
plt.rc('xtick', labelsize=size+3)
plt.rc('ytick', labelsize=size+3)
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
    fontsize=size, color="#00058b", fontweight="bold"  # dark green title
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

# ---------- News & case state ----------
current_news = ""
previous_news = ""
last_news_poll = 0.0
last_case_poll = 0.0
tick = 0
status = "unknown"

# ---------- Real-time loop ----------
t0 = time.time()

while True:
    now = time.time()
    elapsed = now - t0

    # Poll /case (tick & status) less frequently
    if now - last_case_poll >= CASE_POLL_INTERVAL:
        try:
            tick, status = get_tick_status()
        except Exception as e:
            print("Error getting case status:", e)
            break
        last_case_poll = now
        print(f"tick={tick}, status={status}")

    # Stop condition: tick >= limit OR status not active/running
    if tick >= TICK_LIMIT or status.lower() not in ("active", "running"):
        print(f"Stopping: tick={tick}, status={status}")
        break

    # Get latest price (current index level)
    try:
        price = s.get(f"{API}/securities").json()[0]['last']
    except Exception as e:
        print("Error getting price:", e)
     #    time.sleep(POLL_INTERVAL)
        continue

#     # In case last price is None (no trades yet)
#     if price is None:
#         time.sleep(POLL_INTERVAL)
#         continue

    # Poll /news only every NEWS_POLL_INTERVAL seconds
    if now - last_news_poll >= NEWS_POLL_INTERVAL:
        cur, prev = get_news_headlines()
        if cur is not None:
            current_news = cur
        if prev is not None:
            previous_news = prev
        last_news_poll = now

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
        # Optionally only draw last VISIBLE_MAX candles for speed
        if VISIBLE_MAX is not None and len(candles) > VISIBLE_MAX:
            draw_candles = candles[-VISIBLE_MAX:]
        else:
            draw_candles = candles

        xs     = [c["bucket"] * INTERVAL_SEC for c in draw_candles]
        opens  = [c["open"]  for c in draw_candles]
        highs  = [c["high"]  for c in draw_candles]
        lows   = [c["low"]   for c in draw_candles]
        closes = [c["close"] for c in draw_candles]

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
            if h > body_top:
                ax.vlines(x, body_top, h, color=color, linewidth=1.0)
            if l < body_bottom:
                ax.vlines(x, l, body_bottom, color=color, linewidth=1.0)

            # --- Draw Body ---
            body_height = abs(c - o)
            if body_height == 0:
                body_height = min_body_height  # tiny body so flat candles are visible

            rect = Rectangle(
                (x - width / 2, body_bottom),
                width,
                body_height,
                facecolor=color,
                edgecolor=color,
                alpha=0.7,
            )
            ax.add_patch(rect)

        ax.yaxis.grid(True, linestyle='--', alpha=0.7)
        ax.set_xlim(xs[0] - INTERVAL_SEC, xs[-1] + INTERVAL_SEC)

    ax.relim()
    ax.autoscale_view()

    # ---------- Update info: current index level & time remaining ----------
    remaining_ticks = max(TICK_LIMIT - tick, 0)
    rem_min = remaining_ticks // 60
    rem_sec = remaining_ticks % 60

    info_left_text.set_text(
        r"$\bf{Current\ Index\ Level:}$ " + f"{price}"
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
