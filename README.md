# Market / Crypto Backtester Pro

Streamlit terminal for downloading Binance OHLCV candles, viewing interactive
Plotly charts, running Backtrader-based strategy backtests, optimizing strategy
parameters, and deploying the application with Docker.

## Features

- Binance spot OHLCV download through `ccxt`.
- Local candle cache in `data/cache/` for faster repeated analysis.
- Interactive candlestick and volume charts with Plotly.
- Backtrader execution engine with trade logs, equity curves, and indicators.
- Strategy auto-discovery from the `strategies/` package.
- Included strategies: moving average cross and Liq2 VWMA.
- Parameter optimization modes: brute force, random search, and genetic search.
- Runtime strategy profiles and optimization history stored outside Git.
- Docker and server deployment assets under `deploy/`.

## Project Layout

```text
.
├── app.py                         # Streamlit UI
├── backtest/engine.py             # Backtest and optimization engine
├── data/downloader.py             # Binance downloader and cache helpers
├── strategies/                    # Strategy implementations
├── utils/                         # Strategy loading, profiles, optimization store
├── deploy/                        # Docker Compose, server scripts, runbooks
├── Optimization Docs/             # Optimization notes and small reproducibility docs
├── .streamlit/config.toml         # Streamlit theme
├── Dockerfile
└── requirements.txt
```

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

Then open the Streamlit URL printed in the terminal, usually
`http://localhost:8501`.

## Docker

```powershell
docker build -t market .
docker run --rm -p 8501:8501 market
```

For server deployment, use the files in `deploy/`:

- `deploy/SERVER_MIGRATION_RUNBOOK.md`
- `deploy/CODEX_DEPLOY_PROMPT.md`
- `deploy/docker-compose.server.yml`

## Data Policy

Market data and runtime state are intentionally not stored in Git. A fresh clone
can recreate them by running the app and downloading data again.

Excluded local/runtime paths include:

- `data.csv`
- `trades_log.csv`
- `data/cache/`
- `output/`
- `strategy_profiles.json`
- `deploy/runtime/`
- `deploy/artifacts/`
- `Данные и Бекстест/`
- compressed/raw market-data dumps such as `*.csv.gz`, `*.parquet`, `*.sqlite`

Use `strategy_profiles.example.json` as the safe empty template for runtime
profiles. The real `strategy_profiles.json` should stay local or live in the
server runtime volume.

## Restoring From Git

1. Clone the repository.
2. Install dependencies from `requirements.txt`.
3. Run `streamlit run app.py`.
4. Download the required Binance candles from the UI.
5. Run backtests and optimizations; generated files will be recreated locally.

## Notes For Future Codex Work

- `CODEX_PROJECT_HANDOFF_PROMPT.md` contains a ready prompt for future Codex
  instances that need to restore and continue the project from GitHub.
- Do not use `git add .` without checking ignored and staged files.
- Keep market data, cache files, logs, and optimization runtime state out of Git.
- Add new strategies under `strategies/`; they will be picked up by
  `utils/strategy_loader.py` when they follow the existing strategy interface.
