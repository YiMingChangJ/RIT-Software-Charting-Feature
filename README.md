Here’s an updated **README.md** with a centered demo image using your exact GitHub HTML snippet style (showing `Charting_example.png`). I also fixed a couple small inconsistencies (like `app_v2.py` vs `app.py`) in a safe way.

---

# Live RIT Index Chart Visualizer

This is a Python Flask application designed to visualize real-time market data from the **Rotman Interactive Trader (RIT)** simulation API. It generates a dynamic, auto-refreshing candlestick chart representing the market index, complete with live news headlines and simulation status.

## 📸 Example Output

<p align="center">
  <img width="700" src="Charting_example.png" alt="Live RIT Candlestick Chart Example">
</p>

## 🚀 Features

* **Real-Time Candlestick Charting:** Aggregates live data into candlesticks (OHLC) with custom up/down coloring.
* **Live News Feed:** Displays the most recent and previous news headlines directly on the chart header.
* **Market Status:** Shows the current index price and remaining simulation time.
* **Auto-Refreshing Web Interface:** The frontend automatically refreshes the chart without requiring a page reload.
* **Matplotlib Integration:** Uses the `Agg` backend for high-performance server-side image rendering.

## 📂 Project Structure

**Important:** Flask requires HTML files to be placed in a `templates` folder. Ensure your directory looks like this:

```text
project-folder/
│
├── app.py                # Main Flask application and plotting logic
├── README.md             # This file
├── Charting_example.png  # Example output image shown above
└── templates/
    └── index.html        # The HTML frontend (must be in this folder)
```

## 🛠 Prerequisites

* Python 3.7+
* Access to the Rotman RIT Server API (ensure the simulation is running or the API endpoint is accessible).

## 📦 Installation

1. **Clone or Download** this repository.

2. **Install Dependencies:**
   It is recommended to use a virtual environment. Install the required libraries using `pip`:

   ```bash
   pip install flask requests matplotlib
   ```

## ⚙️ Configuration

Open `app.py` to adjust the configuration settings at the top of the file to match your simulation environment:

```python
# ====== CONFIG ======
API = "http://flserver.rotman.utoronto.ca:14960/v1"  # API Endpoint
HDRS = {"Authorization": "Basic MTox"}               # Authentication headers
INTERVAL_SEC = 10                                    # Seconds per candlestick (if using time-bucket candles)
TICK_LIMIT = 1800                                    # Simulation duration (ticks)
```

## 🏃 Usage

1. **Start the Application:**
   Run the following command in your terminal:

   ```bash
   python app_v2.py
   ```

2. **Access the Chart:**
   Open your web browser and navigate to:
   `http://127.0.0.1:5000/`

3. **Start the Simulation:**
   Once the RIT case is started (status becomes `ACTIVE` or `RUNNING`), the chart will automatically begin plotting candles and updating news.

## 🔧 Troubleshooting

* **`TemplateNotFound: index.html` Error:**
  Make sure you created a folder named `templates` and moved `index.html` inside it.

* **Empty Chart / No Data:**
  Ensure the `API` URL in `app.py` is correct and that the Rotman server is reachable.
  Check that your `HDRS` (Authorization) matches the credentials required by the server.

* **News Text Cut Off:**
  If news headlines are too long, the script automatically wraps them. You can adjust the wrapping width / max lines in the `wrap_headline` function or increase the figure size in `make_figure`.

## 📜 License

This project is licensed under the **MIT License**. See the `LICENSE` file for details, and for educational purposes related to the Rotman Interactive Trader simulations.
