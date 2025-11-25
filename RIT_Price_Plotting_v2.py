# %% 
import time
import requests
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf
import matplotlib.dates as mdates  # for mapping datetimes to x-axis positions

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

mc = mpf.make_marketcolors(
    up=UP_COLOR,       # rising candles (Close >= Open)
    down=DOWN_COLOR,   # falling candles (Close < Open)
    edge="inherit",
    wick="inherit",
    volume="in"
)

mpf_style = mpf.make_mpf_style(
    base_mpf_style="binance",
    marketcolors=mc,
) # binance, blueskies, brasil, classic, charles, default, mike, nightclouds, starsandstripes, yahoo, sas

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

# We'll use a datetime index for mplfinance
t0 = time.time()
start_time = pd.to_datetime(t0, unit="s")

# ---------- Matplotlib style ----------
size = 20
plt.rcParams['lines.linewidth'] = 3
plt.rcParams.update({'font.size': size})
plt.rc('xtick', labelsize=size - 2)
plt.rc('ytick', labelsize=size - 2)
plt.rc('font', family='serif')

plt.ion()
fig, ax = plt.subplots(figsize=(12, 6))
ax.set_title(f"Real-time candlestick: {TARGET_TICKER}")
ax.set_xlabel("Time (Ticks)")
ax.set_ylabel("Price")

# ---------- Real-time loop ----------
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

    # Get latest price
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

    # ---------- Redraw using mplfinance ----------
    if candles:
        # Build datetime index for buckets (mplfinance requires DatetimeIndex)
        times = [
            start_time + pd.Timedelta(seconds=c["bucket"] * INTERVAL_SEC)
            for c in candles
        ]
        # X-axis values like Method 1: bucket * INTERVAL_SEC
        xs = [c["bucket"] * INTERVAL_SEC for c in candles]

        df = pd.DataFrame(
            {
                "Open":  [c["open"]  for c in candles],
                "High":  [c["high"]  for c in candles],
                "Low":   [c["low"]   for c in candles],
                "Close": [c["close"] for c in candles],
            },
            index=pd.DatetimeIndex(times, name="Date")
        )

        ax.clear()

        # plot into existing axes
        mpf.plot(
            df,
            type="candle",
            style=mpf_style,
            ax=ax,
            show_nontrading=True,
        )

        ax.set_title(f"Real-time candlestick: {TARGET_TICKER}")
        ax.set_xlabel("Time (Ticks)")
        ax.set_ylabel("Price")

        # Horizontal lines as background (y-grid only)
        ax.yaxis.grid(True, linestyle='--', alpha=0.4)

        # Map datetime index to numeric x positions and relabel with Method 1 x-axis (xs)
        x_positions = [mdates.date2num(ts) for ts in df.index]
        ax.set_xticks(x_positions)
        ax.set_xticklabels(xs)  # show "Time (Ticks)" like Method 1, no rotation

    fig.canvas.draw_idle()
    plt.pause(0.01)
    time.sleep(POLL_INTERVAL)

print("Done. Case ended or tick limit reached.")
plt.ioff()
plt.show()

# %%
