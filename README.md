# Pricewatch

Pricewatch is a self-hosted price tracking tool designed to run on a Linux mini-PC with a local LLM via [Ollama](https://ollama.com). It provides a web dashboard to add, edit, and remove tracked products, then periodically checks prices using your local **[Good-search](https://github.com/katjabunich/Good-search)** MCP service and Ollama to extract the current price.

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
- **Good-search integration** — local stealth-browser search + page parsing via MCP

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
            ├── Good-search MCP (local search + page parsing)
            └── Ollama (local LLM price extraction)
```

## Quick start

### 1. Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) running locally
- **Good-search MCP already running** on the same host ([setup reference](docs/good-search-setup.md))

Pull a model:

```bash
ollama pull llama3.2
```

Pricewatch auto-connects to the local Good-search MCP on startup.

### 2. Install Pricewatch

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Edit `.env` and set at least:

```env
PRICEWATCH_GOOD_SEARCH_MCP_URL=http://127.0.0.1:8765/mcp
PRICEWATCH_OLLAMA_MODEL=llama3.2
```

If auto-discovery cannot find Good-search, set `PRICEWATCH_GOOD_SEARCH_MCP_URL` to the URL printed by your MCP install.

### 3. Run

```bash
pricewatch
```

Open `http://localhost:8080` for the dashboard.

Verify dependencies:

```bash
curl http://localhost:8080/health
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `PRICEWATCH_HOST` | `0.0.0.0` | Bind address |
| `PRICEWATCH_PORT` | `8080` | HTTP port |
| `PRICEWATCH_DATABASE_URL` | `sqlite:///./data/pricewatch.db` | SQLite database path |
| `PRICEWATCH_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API URL |
| `PRICEWATCH_OLLAMA_MODEL` | `llama3.2` | Model used for price extraction |
| `PRICEWATCH_GOOD_SEARCH_MCP_URL` | `http://127.0.0.1:8765/mcp` | Good-search MCP endpoint |
| `PRICEWATCH_GOOD_SEARCH_AUTO_DISCOVER` | `true` | Probe localhost MCP URLs on startup |
| `PRICEWATCH_GOOD_SEARCH_MCP_URL_CANDIDATES` | _(built-in list)_ | Comma-separated MCP URLs to probe |
| `PRICEWATCH_GOOD_SEARCH_SEARCH_TOOL` | _(auto)_ | Override search tool name |
| `PRICEWATCH_GOOD_SEARCH_FETCH_TOOL` | _(auto)_ | Override fetch/parse tool name |
| `PRICEWATCH_GOOD_SEARCH_TIMEOUT_SECONDS` | `120` | MCP request timeout |
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

Ensure **Good-search MCP** and **Ollama** are already running on the target host before starting Pricewatch.

## Roadmap ideas

- Webhook/email/Telegram notifications when alerts trigger
- Sparkline charts for price trends on each card
- Import/export tracked items as JSON or CSV
- Multi-retailer comparison for the same product
- Auth for the dashboard when exposed beyond localhost

## Development

```bash
pip install -e .
pricewatch
```

The SQLite database is created automatically on first startup in `./data/`.
