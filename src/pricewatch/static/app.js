const state = {
  items: [],
  editingId: null,
  filter: "",
};

const els = {
  statsTotal: document.getElementById("stat-total"),
  statsEnabled: document.getElementById("stat-enabled"),
  statsAlerts: document.getElementById("stat-alerts"),
  statsLastRun: document.getElementById("stat-last-run"),
  itemsContainer: document.getElementById("items-container"),
  emptyState: document.getElementById("empty-state"),
  searchInput: document.getElementById("search-input"),
  itemDialog: document.getElementById("item-dialog"),
  historyDialog: document.getElementById("history-dialog"),
  itemForm: document.getElementById("item-form"),
  dialogTitle: document.getElementById("dialog-title"),
  percentDropField: document.getElementById("percent-drop-field"),
  toast: document.getElementById("toast"),
  serviceStatus: document.getElementById("service-status"),
  goodSearchStatus: document.getElementById("good-search-status"),
  ollamaStatus: document.getElementById("ollama-status"),
};

function formatMoney(value, currency = "USD") {
  if (value == null) return "—";
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatDate(value) {
  if (!value) return "Never";
  return new Date(value).toLocaleString();
}

function showToast(message, type = "success") {
  els.toast.textContent = message;
  els.toast.className = `toast ${type}`;
  setTimeout(() => els.toast.classList.add("hidden"), 3500);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed (${response.status})`);
  }
  if (response.status === 204) return null;
  return response.json();
}

async function loadDashboard() {
  const [stats, items, health] = await Promise.all([
    api("/api/stats"),
    api("/api/items"),
    api("/health"),
  ]);
  state.items = items;
  renderStats(stats);
  renderServiceStatus(health);
  renderItems();
}

function renderServiceStatus(health) {
  els.serviceStatus.classList.remove("hidden");

  const goodSearch = health.good_search || {};
  if (goodSearch.reachable) {
    els.goodSearchStatus.textContent = `Good-search: ${goodSearch.scrape_tool || "connected"}`;
    els.goodSearchStatus.className = "status-pill ok";
    els.goodSearchStatus.title = `${goodSearch.mcp_url}\nTools: ${(goodSearch.tools || []).join(", ")}`;
  } else {
    els.goodSearchStatus.textContent = "Good-search: offline";
    els.goodSearchStatus.className = "status-pill warn";
    els.goodSearchStatus.title = goodSearch.error || "Not reachable";
  }

  els.ollamaStatus.textContent = `Ollama: ${health.model || "configured"}`;
  els.ollamaStatus.className = "status-pill ok";
  els.ollamaStatus.title = health.ollama || "";
}

function renderStats(stats) {
  els.statsTotal.textContent = stats.total_items;
  els.statsEnabled.textContent = stats.enabled_items;
  els.statsAlerts.textContent = stats.alerts_active;
  els.statsLastRun.textContent = formatDate(stats.last_run_at);
}

function alertLabel(item) {
  if (item.alert_type === "any_drop") return "Alert on any drop";
  if (item.alert_type === "percent_drop") return `Alert on ${item.percent_drop || "?"}% drop`;
  return `Target ${formatMoney(item.target_price, item.currency)}`;
}

function priceDelta(item) {
  if (item.current_price == null || item.previous_price == null) return null;
  const diff = item.current_price - item.previous_price;
  if (diff === 0) return null;
  return {
    diff,
    className: diff < 0 ? "down" : "up",
    text: `${diff < 0 ? "↓" : "↑"} ${formatMoney(Math.abs(diff), item.currency)}`,
  };
}

function matchesFilter(item) {
  const q = state.filter.trim().toLowerCase();
  if (!q) return true;
  return [item.name, item.search_query, item.tags, item.notes]
    .filter(Boolean)
    .some((value) => value.toLowerCase().includes(q));
}

function renderItems() {
  const filtered = state.items.filter(matchesFilter);
  els.itemsContainer.innerHTML = "";
  els.emptyState.classList.toggle("hidden", filtered.length > 0);

  filtered.forEach((item) => {
    const delta = priceDelta(item);
    const card = document.createElement("article");
    card.className = `item-card ${item.alert_triggered ? "alert" : ""} ${item.enabled ? "" : "disabled"}`;
    card.innerHTML = `
      <div class="item-top">
        <div>
          <div class="item-title">${escapeHtml(item.name)}</div>
          <div class="item-meta">${escapeHtml(item.search_query)}</div>
        </div>
        <div class="badges">
          ${item.alert_triggered ? '<span class="badge warning">Alert</span>' : ""}
          <span class="badge ${item.last_check_status}">${item.last_check_status}</span>
          ${item.enabled ? '<span class="badge success">Enabled</span>' : '<span class="badge">Paused</span>'}
        </div>
      </div>
      <div class="price-row">
        <span class="current-price">${formatMoney(item.current_price, item.currency)}</span>
        ${delta ? `<span class="price-delta ${delta.className}">${delta.text}</span>` : ""}
      </div>
      <div class="badges">
        <span class="badge">${alertLabel(item)}</span>
        ${item.lowest_price != null ? `<span class="badge">Low ${formatMoney(item.lowest_price, item.currency)}</span>` : ""}
        ${item.tags ? `<span class="badge">${escapeHtml(item.tags)}</span>` : ""}
      </div>
      <div class="item-meta">Last checked: ${formatDate(item.last_checked_at)}</div>
      ${item.last_check_error ? `<div class="item-meta" style="color: var(--danger)">${escapeHtml(item.last_check_error)}</div>` : ""}
      <div class="card-actions">
        <button class="btn btn-secondary" data-action="check" data-id="${item.id}">Check now</button>
        <button class="btn btn-ghost" data-action="history" data-id="${item.id}">History</button>
        <button class="btn btn-ghost" data-action="edit" data-id="${item.id}">Edit</button>
        <button class="btn btn-danger" data-action="delete" data-id="${item.id}">Delete</button>
      </div>
    `;
    els.itemsContainer.appendChild(card);
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function openDialog(item = null) {
  state.editingId = item ? item.id : null;
  els.dialogTitle.textContent = item ? "Edit product" : "Add product";
  els.itemForm.reset();
  els.itemForm.enabled.checked = true;
  els.itemForm.currency.value = "USD";

  if (item) {
    for (const field of ["name", "search_query", "product_url", "target_price", "percent_drop", "currency", "tags", "notes", "check_interval_minutes"]) {
      if (item[field] != null) els.itemForm[field].value = item[field];
    }
    els.itemForm.alert_type.value = item.alert_type;
    els.itemForm.enabled.checked = item.enabled;
  }

  togglePercentField();
  els.itemDialog.showModal();
}

function togglePercentField() {
  const show = els.itemForm.alert_type.value === "percent_drop";
  els.percentDropField.classList.toggle("hidden", !show);
}

function formPayload() {
  const form = new FormData(els.itemForm);
  const payload = Object.fromEntries(form.entries());
  payload.enabled = Boolean(els.itemForm.enabled.checked);
  payload.target_price = payload.target_price ? Number(payload.target_price) : null;
  payload.percent_drop = payload.percent_drop ? Number(payload.percent_drop) : null;
  payload.check_interval_minutes = payload.check_interval_minutes
    ? Number(payload.check_interval_minutes)
    : null;
  payload.product_url = payload.product_url || null;
  payload.tags = payload.tags || null;
  payload.notes = payload.notes || null;
  return payload;
}

async function saveItem(event) {
  event.preventDefault();
  const payload = formPayload();
  try {
    if (state.editingId) {
      await api(`/api/items/${state.editingId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      showToast("Product updated");
    } else {
      await api("/api/items", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showToast("Product added");
    }
    els.itemDialog.close();
    await loadDashboard();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function deleteItem(id) {
  if (!confirm("Delete this tracked product?")) return;
  try {
    await api(`/api/items/${id}`, { method: "DELETE" });
    showToast("Product deleted");
    await loadDashboard();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function checkItem(id) {
  try {
    const result = await api(`/api/items/${id}/check`, { method: "POST" });
    showToast(
      result.success
        ? `Checked: ${formatMoney(result.price, result.currency || "USD")}${result.alert_triggered ? " — alert!" : ""}`
        : result.message || "Check failed",
      result.success ? "success" : "error",
    );
    await loadDashboard();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function showHistory(id) {
  try {
    const item = await api(`/api/items/${id}`);
    document.getElementById("history-title").textContent = `History — ${item.name}`;
    const container = document.getElementById("history-content");
    container.innerHTML = item.price_history.length
      ? item.price_history.map((entry) => `
          <div class="history-item">
            <strong>${formatMoney(entry.price, entry.currency)}</strong>
            <div class="item-meta">${formatDate(entry.checked_at)} · ${entry.status}</div>
            ${entry.source_url ? `<div class="item-meta"><a href="${escapeHtml(entry.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(entry.source_url)}</a></div>` : ""}
            ${entry.error ? `<div class="item-meta" style="color: var(--danger)">${escapeHtml(entry.error)}</div>` : ""}
          </div>
        `).join("")
      : '<div class="item-meta">No history yet.</div>';
    els.historyDialog.showModal();
  } catch (error) {
    showToast(error.message, "error");
  }
}

document.getElementById("add-item-btn").addEventListener("click", () => openDialog());
document.getElementById("empty-add-btn").addEventListener("click", () => openDialog());
document.getElementById("close-dialog").addEventListener("click", () => els.itemDialog.close());
document.getElementById("cancel-dialog").addEventListener("click", () => els.itemDialog.close());
document.getElementById("close-history").addEventListener("click", () => els.historyDialog.close());
els.itemForm.addEventListener("submit", saveItem);
els.itemForm.alert_type.addEventListener("change", togglePercentField);
els.searchInput.addEventListener("input", (event) => {
  state.filter = event.target.value;
  renderItems();
});

document.getElementById("check-all-btn").addEventListener("click", async () => {
  const button = document.getElementById("check-all-btn");
  button.disabled = true;
  try {
    const result = await api("/api/check-all", { method: "POST" });
    showToast(`Checked ${result.checked} product(s)`);
    await loadDashboard();
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
  }
});

els.itemsContainer.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const id = Number(button.dataset.id);
  const action = button.dataset.action;
  if (action === "edit") openDialog(state.items.find((item) => item.id === id));
  if (action === "delete") deleteItem(id);
  if (action === "check") checkItem(id);
  if (action === "history") showHistory(id);
});

loadDashboard().catch((error) => showToast(error.message, "error"));
setInterval(() => loadDashboard().catch(() => {}), 30000);
