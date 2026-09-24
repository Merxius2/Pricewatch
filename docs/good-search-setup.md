# Good-search setup

Pricewatch uses your local **[Good-search](https://github.com/katjabunich/Good-search)** MCP service for stealth-browser web search and page parsing. This is the search backend referenced in the project — not a hosted third-party API.

## Install Good-search

On your mini-PC:

```bash
cd ~
git clone git@github.com:katjabunich/Good-search.git Good-search-git
cd Good-search-git
git checkout claude/stealth-browser-parsing-alternatives-28lrsa
bash mcp/install.sh --yes --no-tunnel
```

The install script starts Good-search locally without a cloud tunnel. Note the MCP URL it prints (commonly something like `http://127.0.0.1:8765/mcp`).

## Configure Pricewatch

Copy the MCP URL into your Pricewatch `.env`:

```env
PRICEWATCH_GOOD_SEARCH_MCP_URL=http://127.0.0.1:8765/mcp
```

If Pricewatch cannot auto-detect the right tools, set them explicitly after checking `/health`:

```env
PRICEWATCH_GOOD_SEARCH_SEARCH_TOOL=search
PRICEWATCH_GOOD_SEARCH_FETCH_TOOL=fetch
```

## Verify

With both Ollama and Good-search running:

```bash
pricewatch
curl http://localhost:8080/health
```

The health response includes discovered Good-search tools when the MCP service is reachable.

## Typical mini-PC stack

```text
Ollama (localhost:11434)
Good-search MCP (localhost:8765/mcp)
Pricewatch dashboard (localhost:8080)
```

Run Good-search before Pricewatch, or configure systemd units so Good-search starts first.
