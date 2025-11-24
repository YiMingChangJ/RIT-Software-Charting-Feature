#%% 
import time
import requests
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

API = "http://flserver.rotman.utoronto.ca:14960/v1"
HDRS = {"Authorization": "Basic MTox"}

# ==== CONFIG ====
INTERVAL_SEC = 5      # set to 5 or 10 for 5s/10s per candle
POLL_INTERVAL = 0.5   # how often we query /securities (seconds)

# ---------- Setup session ----------
s = requests.Session()
s.headers.update(HDRS)
# or s.auth + ("2", "2")

# ---------- Helper to get case tick & status ----------
def get_tick_status():
    """Return the live simulator tick and status."""
    r = s.get(f"{API}/case", timeout=2.0)
    r.raise_for_status()
    j = r.json()
    return j["tick"], j["status"]

# ---------- Discover tickers & choose ONE ----------
resp = s.get(f"{API}/securities", timeout=2.0)
resp.raise_for_status()
securities = resp.json()

all_tickers = [sec["ticker"] for sec in securities]
print("All tickers:", all_tickers)

# Choose the first ticker for now. You can hardcode instead, e.g. TARGET_TICKER = "RTM"
TARGET_TICKER = all_tickers[0]
print("Tracking ticker:", TARGET_TICKER)

# ---------- Find index of target ticker in /securities array ----------
ticker_to_idx = {sec["ticker"]: i for i, sec in enumerate(securities)}
if TARGET_TICKER not in ticker_to_idx:
    raise ValueError(f"{TARGET_TICKER} not found in /securities")

target_idx = ticker_to_idx[TARGET_TICKER]

# ---------- Candlestick storage ----------
# Each candle is a dict: {bucket, open, high, low, close}
candles = []
current_candle = None

# ---------- Matplotlib style ----------
size = 20
plt.rcParams['lines.linewidth'] = 1.5
plt.rcParams.update({'font.size': size})
plt.rc('xtick', labelsize=size-2)
plt.rc('ytick', labelsize=size-2)
plt.rc('font', family='serif')

plt.ion()
fig, ax = plt.subplots(figsize=(12, 6))
ax.set_title(f"Real-time candlestick: {TARGET_TICKER}")
ax.set_xlabel("Time (seconds since start)")
ax.set_ylabel("Price")

# ---------- Real-time loop ----------
t0 = time.time()

while True:
    # Check case status
    tick, status = get_tick_status()
    print(f"tick={tick}, status={status}")

    # Stop condition: tick > 300 OR status not active/running
    if tick > 300 or status.lower() not in ("active", "running"):
        print(f"Stopping: tick={tick}, status={status}")
        break

    # Get latest prices
    resp = s.get(f"{API}/securities", timeout=2.0)
    if not resp.ok:
        print("Bad response from /securities:", resp.status_code)
        time.sleep(POLL_INTERVAL)
        continue

    securities = resp.json()
    sec = securities[target_idx]
    price = sec["last"]

    now = time.time()
    elapsed = now - t0

    # Determine which candle "bucket" this time belongs to
    bucket = int(elapsed // INTERVAL_SEC)  # 0,1,2,...

    if current_candle is None or bucket != current_candle["bucket"]:
        # Start a new candle
        current_candle = {
            "bucket": bucket,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
        }
        candles.append(current_candle)
    else:
        # Update existing candle
        current_candle["high"] = max(current_candle["high"], price)
        current_candle["low"]  = min(current_candle["low"], price)
        current_candle["close"] = price

    # ---------- Redraw candlesticks ----------
    ax.clear()
    ax.set_title(f"Real-time candlestick: {TARGET_TICKER}")
    ax.set_xlabel("Time (seconds since start)")
    ax.set_ylabel("Price")

    if candles:
        xs = [c["bucket"] * INTERVAL_SEC for c in candles]
        opens  = [c["open"]  for c in candles]
        highs  = [c["high"]  for c in candles]
        lows   = [c["low"]   for c in candles]
        closes = [c["close"] for c in candles]

        width = INTERVAL_SEC * 0.6  # candle body width in time units

        for x, o, h, l, c in zip(xs, opens, highs, lows, closes):
            color = "green" if c >= o else "red"

            # Wick
            ax.vlines(x, l, h, color=color, linewidth=1.0)

            # Body
            body_bottom = min(o, c)
            body_height = abs(c - o)
            if body_height == 0:
                # Draw a tiny body so flat candles are visible
                body_height = (max(highs) - min(lows)) * 0.001
            rect = Rectangle(
                (x - width / 2, body_bottom),
                width,
                body_height,
                facecolor=color,
                edgecolor=color,
                alpha=0.7,
            )
            ax.add_patch(rect)

        ax.set_xlim(xs[0] - INTERVAL_SEC, xs[-1] + INTERVAL_SEC)

    ax.relim()
    ax.autoscale_view()

    fig.canvas.draw_idle()
    plt.pause(0.01)
    time.sleep(POLL_INTERVAL)

print("Done. Case ended or tick limit reached.")
plt.ioff()
plt.show()

# %%
