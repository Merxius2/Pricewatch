# Good-search on the target host

Pricewatch expects **Good-search MCP to already be running on the same machine** as Pricewatch (your Linux mini-PC). Pricewatch connects over localhost — no cloud tunnel or external search API is required.

## Assumed setup

On the target host, Good-search is installed and running:

```bash
cd ~/Good-search-git
git checkout claude/stealth-browser-parsing-alternatives-28lrsa
bash mcp/install.sh --yes --no-tunnel
```

Keep that MCP process running. Pricewatch will connect to it automatically on startup.

## Pricewatch config

In `.env`, set the MCP URL if you know it:

```env
PRICEWATCH_GOOD_SEARCH_MCP_URL=http://127.0.0.1:8765/mcp
```

If the URL is unknown or the port differs, leave auto-discovery enabled (default):

```env
PRICEWATCH_GOOD_SEARCH_AUTO_DISCOVER=true
```

Pricewatch probes common localhost MCP endpoints on startup and caches the first working one.

Optional overrides if auto-discovery picks the wrong tools:

```env
PRICEWATCH_GOOD_SEARCH_SEARCH_TOOL=search
PRICEWATCH_GOOD_SEARCH_FETCH_TOOL=fetch
```

## Verify on the target

```bash
pricewatch
curl http://localhost:8080/health
```

A healthy response includes:

```json
{
  "good_search": {
    "reachable": true,
    "mcp_url": "http://127.0.0.1:8765/mcp",
    "search_tool": "...",
    "fetch_tool": "...",
    "tools": ["..."]
  }
}
```

The dashboard also shows Good-search status in the header.

## Co-located services

```text
Good-search MCP   →  already running on localhost
Ollama            →  localhost:11434
Pricewatch        →  localhost:8080
```

Pricewatch does not start or manage Good-search — it only connects to the existing MCP server.
