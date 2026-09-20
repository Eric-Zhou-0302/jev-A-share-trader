<h1 align="center">jev-A-share-trader</h1>

<p align="center"><strong>A Jev-powered technical analysis workspace for China A-shares</strong></p>
<p align="center">Read market structure through price and volume.</p>
<p align="center">
  <a href="README.md">简体中文</a> · <strong>English</strong>
  <br />
  <a href="#quick-start">Quick start</a> · <a href="#technical-analysis-coverage">Indicators</a> · <a href="docs/methodology.md">Methodology</a> · <a href="docs/usage.md">User guide</a>
</p>

---

**Eight analytical dimensions. One traceable assessment.**

`jev-A-share-trader` retrieves A-share market data through AKShare or Tushare, computes technical indicators and pattern evidence, and asks Jev to assess each dimension. Code then aggregates those assessments into a single **Buy, Hold, or Sell** decision. Analyze an individual stock, follow a watchlist, or scan the Shanghai, Shenzhen, and Beijing exchanges.

Every analysis answers three questions:

| Decision | Horizon | Technical evidence |
| --- | --- | --- |
| **Buy / Hold / Sell** | Automatically selects **2–5** or **5–20 trading days** | Supporting, opposing, and contextual evidence, linked to the relevant candles |

Analysis uses the latest completed trading session. During market hours, daily data ends at the previous session; weekly and monthly analysis also uses completed periods only.

## Features

- **Stock workspace** — Search by code or name, explore daily / weekly / monthly candles, switch between moving averages, Bollinger bands, volume, MACD, and RSI, and inspect individual indicators and evidence.
- **Watchlists and market scans** — Cover all three A-share exchanges with progress tracking, pause, resume, and failed-item retries. Default filters exclude ST / delisting stocks, stocks with no trading volume, and insufficient history.
- **Two data providers** — Switch between AKShare and Tushare Pro in settings, or implement a custom provider.
- **Web and CLI** — Share local watchlists, analysis history, and scan jobs. Export results as JSON, CSV, or HTML.
- **Chinese and English** — The interface and reports default to Chinese and support English.

## Quick start

Requires **Python 3.11+**, plus **Node.js 22.12+** for the web interface. Use macOS, Linux, or WSL on Windows. A Python virtual environment of your choice is recommended.

### 1. Install and start

Download or clone the project, then run from its root directory:

```bash
python -m pip install -e .
npm --prefix frontend ci
npm --prefix frontend run build
jev serve
```

Open **[http://127.0.0.1:8765](http://127.0.0.1:8765)**.

For CLI-only use, install the Python package; Node.js and the frontend build are unnecessary.

### 2. Configure your accounts

Open **Settings**, enter your Jev API key, and select a data provider:

| Service | Purpose | Credentials |
| --- | --- | --- |
| Jev / TypeSafe | Structured assessment of technical state | Your API key |
| AKShare (default) | Market and reference data | No API key required |
| Tushare Pro | Market and reference data | Your Token with access to the required endpoints |

You can also enter credentials through hidden CLI prompts:

```bash
jev configure
jev configure --provider tushare --tushare-token
```

The first command configures Jev; the second is only needed for Tushare. The `TYPESAFE_API_KEY` and `TUSHARE_TOKEN` environment variables are also supported and take precedence over local settings.

**Without a Jev key, you can still inspect candles, indicators, and bullish / bearish facts.** The app shows “No decision” instead of substituting a default recommendation.

### 3. Run an analysis

Enter a stock code such as `000001` in the workspace and select “Analyze,” or run:

```bash
jev analyze 000001
```

## Technical analysis coverage

Indicators are organized into eight dimensions, preserving both agreement and conflict rather than counting every indicator as a separate vote.

| Dimension | Indicators and analysis |
| --- | --- |
| **Trend** | SMA / EMA 5, 10, 20, 60, 120, 250; WMA, HMA, KAMA; DMI / ADX, Aroon, SAR, Supertrend; moving-average slopes and crosses |
| **Momentum** | MACD, RSI 6/14/24, KDJ, Stochastic, CCI, Williams %R, ROC, MOM, TRIX, TSI; divergence candidates at confirmed pivots |
| **Price and volume** | Volume averages and ratios, turnover, OBV, MFI, CMF, A/D, ADOSC, PVT, VWMA; price-volume confirmation |
| **Volatility** | ATR / NATR, Bollinger, Keltner, Donchian, historical volatility, bandwidth, %B, squeezes |
| **Price structure** | Range position, confirmed highs and lows, trendlines, breakout persistence / failure, unfilled gaps |
| **Candlesticks** | Bodies and shadows; 14 patterns including doji, hammer, engulfing, morning / evening star, harami, three white soldiers, and three black crows |
| **Multiple timeframes** | Completed weekly MA10/20 and monthly MA6/12; alignment and conflict across timeframes |
| **Relative strength** | 5/20/60-day performance versus CSI 300 and the stock’s industry, correlation, index trends, and universe breadth |

Industry, weekly / monthly, and market-breadth context depends on permissions, available history, and sample coverage. Missing inputs are explicitly marked, not filled with zeros. See the [methodology](docs/methodology.md) for parameters, pattern definitions, and data conventions.

## How Jev is used

```text
AKShare / Tushare
       ↓
Completed market data
       ↓
Python computes indicators, patterns, and technical facts
       ↓
Jev assesses each dimension across two candidate horizons
       ↓
Code aggregates direction, disagreement, and volatility risk
       ↓
One decision + one horizon + supporting and opposing evidence
```

Jev receives structured technical state. Indicator calculations, evidence dates, and aggregation rules are inspectable. If the model or required market data fails, no Buy / Hold / Sell decision is produced. There is no technical-signal prescreen: every stock passing basic data validation and eligibility filters enters model assessment during a scan.

The workspace and records run locally. Market-data retrieval and Jev inference require internet access, and technical state is sent to TypeSafe. The project does not supply, host, or resell market data; data access and model charges belong to the user’s accounts.

## Command line

```bash
# Inspect technical facts without calling Jev
jev analyze 000001 --technical-only

# Export an English HTML report; json / csv are also supported
jev --lang en analyze 000001 --format html --output analysis.html

# Add a stock and scan the watchlist
jev watch add 000001
jev scan --scope watchlist

# Scan the full market
jev scan --scope market

# List jobs, resume a job, and retry failed items
jev jobs
jev scan --resume JOB_ID --retry
```

Press `Ctrl+C` to pause a scan. Full-market scans generate substantial data requests and model calls; individual stocks or a watchlist are useful starting points. See the [user guide](docs/usage.md) for more commands, caching, and resume conditions.

## Documentation and development

The detailed documents below are currently in Chinese.

| Document | Contents |
| --- | --- |
| [User guide](docs/usage.md) | Configuration, CLI, scan recovery, local storage, and troubleshooting |
| [Methodology](docs/methodology.md) | Data cutoffs, indicator formulas, Jev questions, and aggregation rules |
| [Data providers](docs/providers.md) | AKShare / Tushare endpoints and the custom-provider contract |
| [Requirements](docs/requirements.md) | Product scope and interaction conventions |
| [Changelog](CHANGELOG.md) | Version history and feature changes |

Stack: Python · FastAPI · pandas · TA-Lib · SQLite · React · TypeScript · Vite.

<details>
<summary>Local development and checks</summary>

Run from the project root:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check src tests
npm --prefix frontend run build
```

For frontend development, run `jev serve` in one terminal and `npm --prefix frontend run dev` in another. Open [http://127.0.0.1:5173](http://127.0.0.1:5173); API requests are proxied to the backend. Interactive API documentation is available at [http://127.0.0.1:8765/docs](http://127.0.0.1:8765/docs).

</details>

## Scope

The current focus is technical research based on the latest completed session. There is no backtesting, portfolio management, order execution, or entry / stop-loss / target pricing. Decision rules have not been validated through return backtests, and Jev probabilities are not empirical trading win rates. The service is intended for personal local use and does not include public multi-user authentication.

Charts use TradingView Lightweight Charts. Its [third-party license](licenses/lightweight-charts-LICENSE.txt) and [copyright notice](licenses/lightweight-charts-NOTICE.txt) are included.
