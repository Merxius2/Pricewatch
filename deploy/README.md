# Deploy Pricewatch on the mini-PC

Pricewatch runs on the **same Linux mini-PC** as Ollama and Good-search.

## One-command install (on the mini-PC)

```bash
curl -fsSL https://raw.githubusercontent.com/Merxius2/Pricewatch/main/deploy/install.sh | sudo bash
```

With your Good-search MCP URL:

```bash
curl -fsSL https://raw.githubusercontent.com/Merxius2/Pricewatch/main/deploy/install.sh | \
  sudo PRICEWATCH_GOOD_SEARCH_MCP_URL='https://your-host.ts.net/mcp/your-secret' bash
```

## Manual install

```bash
sudo git clone https://github.com/Merxius2/Pricewatch.git /opt/pricewatch
cd /opt/pricewatch
sudo cp .env.example .env
# edit .env — set PRICEWATCH_GOOD_SEARCH_MCP_URL
sudo python3 -m venv .venv
sudo .venv/bin/pip install -e .
sudo cp deploy/pricewatch.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pricewatch
```

## Verify

```bash
curl http://localhost:8080/health
systemctl status pricewatch
```

Open the dashboard at `http://<mini-pc-ip>:8080/` from any device on your Tailnet or LAN.

## Update

```bash
sudo bash /opt/pricewatch/deploy/update.sh
```

Full reinstall (venv, systemd, timer):

```bash
sudo bash /opt/pricewatch/deploy/install.sh
```

## Auto-update from `main`

`deploy/install.sh` enables **`pricewatch-update.timer`**, which runs every **10 minutes** (and once shortly after boot). When `origin/main` has new commits, the mini-PC pulls, reinstalls the Python package, and restarts the service.

```bash
systemctl status pricewatch-update.timer
journalctl -u pricewatch-update.service -n 20
sudo systemctl start pricewatch-update.service   # run a check now
```

Disable auto-update:

```bash
sudo systemctl disable --now pricewatch-update.timer
```
