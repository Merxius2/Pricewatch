# Pricewatch

Pricewatch is a self-hosted price tracking tool designed to run on a Linux mini-PC with a local LLM via [Ollama](https://ollama.com). It provides a web dashboard to add, edit, and remove tracked products, then periodically checks prices using [Damn Good Search](https://damngoodsearch.com) and your local model to extract the current price.

## Features

- **Dashboard** — view all tracked products, current prices, alerts, and check status
- **CRUD controls** — add, edit, delete, enable/disable products from the UI
- **Alert types**
  - Price at or below a target threshold
  - Any price drop
  - Percentage drop from the previous price
- **Automatic checks** — background scheduler with global and per-product intervals
- **Manual checks** — run a check for one product or all enabled products
- **Price history** — store and review past checks per product
- **Ollama integration** — local LLM extracts structured price data from search results
- **Good Search integration** — web search + page contents for accurate price discovery

## Architecture

```text
Dashboard (browser)
      │
      ▼
FastAPI + SQLite
      │
      ├── Scheduler (APScheduler)
      │
      └── Price checker
            ├── Good Search API (search + contents)
            └── Ollama (local LLM price extraction)
```

## Quick start

### 1. Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) running locally
- A Damn Good Search API key from [damngoodsearch.com](https://damngoodsearch.com)

Pull a model:

```bash
ollama pull llama3.2
```

### 2. Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Edit `.env` and set at least:

```env
PRICEWATCH_GOOD_SEARCH_API_KEY=dgs_live_...
PRICEWATCH_OLLAMA_MODEL=llama3.2
```

### 3. Run

```bash
pricewatch
```

Open `http://localhost:8080` for the dashboard.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PRICEWATCH_HOST` | `0.0.0.0` | Bind address |
| `PRICEWATCH_PORT` | `8080` | HTTP port |
| `PRICEWATCH_DATABASE_URL` | `sqlite:///./data/pricewatch.db` | SQLite database path |
| `PRICEWATCH_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API URL |
| `PRICEWATCH_OLLAMA_MODEL` | `llama3.2` | Model used for price extraction |
| `PRICEWATCH_GOOD_SEARCH_BASE_URL` | `https://damngoodsearch.com/api/v1` | Good Search API base URL |
| `PRICEWATCH_GOOD_SEARCH_API_KEY` | _(empty)_ | Good Search bearer token |
| `PRICEWATCH_CHECK_INTERVAL_MINUTES` | `60` | Default scheduler interval |

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/items` | List tracked products |
| `POST` | `/api/items` | Create a product |
| `PATCH` | `/api/items/{id}` | Update a product |
| `DELETE` | `/api/items/{id}` | Delete a product |
| `POST` | `/api/items/{id}/check` | Check one product now |
| `POST` | `/api/check-all` | Check all enabled products |
| `GET` | `/api/stats` | Dashboard stats |
| `GET` | `/health` | Health/info endpoint |

## Deploy on a mini-PC

A sample systemd unit is included at `deploy/pricewatch.service`. Typical setup:

```bash
sudo useradd --system --home /opt/pricewatch pricewatch
sudo cp -r . /opt/pricewatch
sudo cp deploy/pricewatch.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pricewatch
```

Ensure Ollama is running before Pricewatch starts.

## Roadmap ideas

- Webhook/email/Telegram notifications when alerts trigger
- Sparkline charts for price trends on each card
- Import/export tracked items as JSON or CSV
- Multi-retailer comparison for the same product
- Auth for the dashboard when exposed beyond localhost
- Support alternate search providers behind the same interface

## Development

```bash
pip install -e .
pricewatch
```

The SQLite database is created automatically on first startup in `./data/`.
