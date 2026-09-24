# Pricewatch

Pricewatch is a self-hosted price tracking tool designed to run with a local LLM via [Ollama](https://ollama.com) and your **[Good-search](https://github.com/katjabunich/Good-search)** MCP server on a Linux mini-PC.

It provides a web dashboard to add, edit, and remove tracked products, then periodically checks prices by scraping live pages through Good-search and extracting prices with Ollama.

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
- **Ollama integration** — local LLM extracts structured price data from page content
- **Good-search integration** — stealth-browser `scrape` tool via Tailscale Funnel MCP URL
- **Preferred website** — check a site you choose first, then optionally search other retailers
- **Product match reviews** — dashboard prompts when the LLM isn't sure two listings are the same product

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
            ├── Good-search MCP (scrape + browse tools)
            └── Ollama (local LLM price extraction)
```

## Quick start

### 1. Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) running locally
- Good-search MCP installed on your mini-PC ([setup guide](docs/good-search-setup.md))

Pull a model:

```bash
ollama pull llama3.2
```

### 2. Install Pricewatch

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Edit `.env` with your Good-search MCP URL from the install output:

```env
PRICEWATCH_GOOD_SEARCH_MCP_URL=https://your-host.tailXXXX.ts.net/mcp/your-secret-token
PRICEWATCH_GOOD_SEARCH_AUTO_DISCOVER=false
PRICEWATCH_OLLAMA_MODEL=llama3.2
```

The MCP URL is a secret — do not commit it.

### 3. Run

```bash
pricewatch
```

Open `http://localhost:8080` for the dashboard.

Verify:

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
| `PRICEWATCH_GOOD_SEARCH_MCP_URL` | _(required)_ | Full Tailscale Funnel MCP URL |
| `PRICEWATCH_GOOD_SEARCH_AUTO_DISCOVER` | `false` | Probe localhost MCP URLs if true |
| `PRICEWATCH_GOOD_SEARCH_SCRAPE_TOOL` | `scrape` | Good-search scrape tool name |
| `PRICEWATCH_GOOD_SEARCH_SEARCH_URL_TEMPLATE` | DuckDuckGo HTML | Search URL template (`{query}`) |
| `PRICEWATCH_GOOD_SEARCH_MAX_CHARS` | `20000` | Max chars per scrape |
| `PRICEWATCH_GOOD_SEARCH_MAX_TIER` | `2` | Scrape escalation tier (0–2) |
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

A sample systemd unit is included at `deploy/pricewatch.service`. Ensure Ollama is running; Good-search MCP is managed separately.

## Development

```bash
pip install -e .
pricewatch
```

The SQLite database is created automatically on first startup in `./data/`.
