# Good-search MCP setup

Pricewatch uses your **Good-search MCP server** on the mini-PC. After install, the server is exposed via **Tailscale Funnel** with a secret URL.

## Install (on the mini-PC)

```bash
cd ~
git clone git@github.com:katjabunich/Good-search.git Good-search-git
cd Good-search-git
git checkout claude/stealth-browser-parsing-alternatives-28lrsa
bash mcp/install.sh --yes --no-tunnel
```

The install script prints a URL like:

```text
https://your-host.tailXXXX.ts.net/mcp/<secret-token>
```

**Treat that URL as a password** — anyone with it can drive the browser on your machine.

## Configure Pricewatch

Put the full MCP URL in `.env` (never commit this file):

```env
PRICEWATCH_GOOD_SEARCH_MCP_URL=https://your-host.tailXXXX.ts.net/mcp/your-secret-token
PRICEWATCH_GOOD_SEARCH_AUTO_DISCOVER=false
```

Pricewatch uses the Good-search `scrape` tool to:

- Search via DuckDuckGo HTML results (`PRICEWATCH_GOOD_SEARCH_SEARCH_URL_TEMPLATE`)
- Fetch product pages with `maxAgeSec=0` for fresh prices

## Verify

```bash
pricewatch
curl http://localhost:8080/health
```

Expected:

```json
{
  "good_search": {
    "reachable": true,
    "mcp_url": "https://your-host.tailXXXX.ts.net/mcp/<secret>",
    "scrape_tool": "scrape",
    "tools": ["scrape", "browse_open", "browse_act", "browse_close", "server_update"]
  }
}
```

The API redacts the secret path segment in responses.

## Architecture

```text
Pricewatch (mini-PC or LAN)
      │
      ▼
Good-search MCP (Tailscale Funnel URL)
      │
      └── stealth Chromium on mini-PC
```

Pricewatch can run on the same mini-PC or another machine on your tailnet, as long as it can reach the Funnel URL.
