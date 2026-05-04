# Codex Project Handoff Prompt

Use this prompt when another Codex instance needs to restore, understand, and
continue the Market project using GitHub as the only source of truth.

```text
You are working with the Market / Crypto Backtester Pro repository from GitHub.
Your goal is to restore the full project from Git, understand its architecture,
and continue implementation without relying on any local market data from the
previous machine.

Repository context:
- Project type: Python Streamlit application.
- Main UI: app.py.
- Backtest engine: backtest/engine.py.
- Binance OHLCV downloader/cache helpers: data/downloader.py.
- Strategy implementations: strategies/.
- Utility modules: utils/.
- Deployment assets: Dockerfile and deploy/.
- Main runtime dependencies: streamlit, pandas, numpy, plotly, ccxt,
  backtrader, requests.

Important data policy:
- The repository intentionally excludes market data and runtime state.
- Do not expect data.csv, trades_log.csv, data/cache/, output/,
  strategy_profiles.json, or deploy/runtime/ to exist after cloning.
- Do not commit downloaded candles, compressed Binance dumps, cache files,
  logs, pycache files, optimization runtime state, or local server artifacts.
- If you need candles, run the app and download them again through the UI or
  use the downloader utilities.

Restore locally:
1. Clone the repository.
2. Create and activate a virtual environment.
3. Install dependencies with:
   pip install -r requirements.txt
4. Run:
   streamlit run app.py
5. Download the required Binance market data from the app UI.
6. Run backtests or optimizations from the Streamlit interface.

Suggested first inspection:
1. Read README.md.
2. Read app.py at the constants/imports area to understand the UI entry points.
3. Read backtest/engine.py for backtest and optimization flow.
4. Read data/downloader.py for OHLCV download/cache behavior.
5. Read strategies/base_strategy.py and the concrete strategy files.
6. Read deploy/SERVER_MIGRATION_RUNBOOK.md if server deployment is needed.

Development rules:
- Preserve the existing runtime/data exclusion policy.
- Before staging, always run:
  git status --ignored --short
  git diff --cached --name-status
- Never use blind git add . unless ignore rules and staged files are checked.
- If generated files appear, update .gitignore/.dockerignore rather than
  committing them.
- Keep strategy code in strategies/ and ensure it can be discovered by
  utils/strategy_loader.py.
- Keep real strategy_profiles.json local; use strategy_profiles.example.json as
  the safe template.

Verification before commit:
- Run:
  python -m compileall app.py backtest data strategies utils
  git diff --cached --check
- Confirm that added/modified staged files do not include:
  __pycache__, *.pyc, data.csv, trades_log.csv, data/cache, output,
  strategy_profiles.json, deploy/runtime, deploy/artifacts, raw market dumps.

GitHub repository description:
Streamlit crypto backtesting terminal for Binance OHLCV data with Backtrader
strategies, Plotly charts, parameter optimization, and Docker deployment.

Suggested GitHub topics:
python, streamlit, crypto, binance, ccxt, backtrader, plotly, backtesting,
quantitative-trading, docker
```
