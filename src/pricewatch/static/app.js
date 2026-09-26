const state = {
  items: [],
  reviews: [],
  editingId: null,
  filter: "",
  defaultCheckIntervalMinutes: 60,
};

const els = {
  statsTotal: document.getElementById("stat-total"),
  statsEnabled: document.getElementById("stat-enabled"),
  statsAlerts: document.getElementById("stat-alerts"),
  statsReviews: document.getElementById("stat-reviews"),
  statsLastRun: document.getElementById("stat-last-run"),
  reviewsPanel: document.getElementById("reviews-panel"),
  reviewsContainer: document.getElementById("reviews-container"),
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
};

function formatMoney(value, currency = "EUR") {
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
  if (!els.toast) return;
  els.toast.textContent = message;
  els.toast.className = `toast ${type}`;
  setTimeout(() => els.toast?.classList.add("hidden"), 3500);
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
  const [stats, items, reviews, health] = await Promise.all([
    api("/api/stats"),
    api("/api/items"),
    api("/api/match-reviews"),
    api("/health"),
  ]);
  state.items = items;
  state.reviews = reviews;
  state.defaultCheckIntervalMinutes = health.check_interval_minutes ?? 60;
  renderStats(stats);
  renderServiceStatus(health);
  renderReviews();
  renderItems();
}

function renderServiceStatus(health) {
  if (!els.serviceStatus || !els.goodSearchStatus) return;
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
}

function renderStats(stats) {
  if (els.statsTotal) els.statsTotal.textContent = stats.total_items;
  if (els.statsEnabled) els.statsEnabled.textContent = stats.enabled_items;
  if (els.statsAlerts) els.statsAlerts.textContent = stats.alerts_active;
  if (els.statsReviews) els.statsReviews.textContent = stats.pending_match_reviews;
  if (els.statsLastRun) els.statsLastRun.textContent = formatDate(stats.last_run_at);
}

function renderReviews() {
  if (!els.reviewsContainer || !els.reviewsPanel) return;
  els.reviewsContainer.innerHTML = "";
  els.reviewsPanel.classList.toggle("hidden", state.reviews.length === 0);

  state.reviews.forEach((review) => {
    const card = document.createElement("article");
    card.className = "review-card";
    card.innerHTML = `
      <h3>Is this the same product as ${escapeHtml(review.item_name || "your item")}?</h3>
      <div class="review-meta">
        <strong>${escapeHtml(review.found_title || "Unknown listing")}</strong><br>
        ${escapeHtml(review.found_site)} · ${formatMoney(review.found_price, review.found_currency || "EUR")}
      </div>
      <div class="review-meta">${escapeHtml(review.match_reason || "")}</div>
      <div class="review-meta"><a href="${escapeHtml(review.found_url)}" target="_blank" rel="noreferrer">${escapeHtml(review.found_url)}</a></div>
      ${review.page_excerpt ? `<div class="review-meta">${escapeHtml(review.page_excerpt.slice(0, 280))}...</div>` : ""}
      <div class="review-actions">
        <button class="btn btn-primary" data-review-action="confirm" data-id="${review.id}">Yes, same product</button>
        <button class="btn btn-secondary" data-review-action="reject" data-id="${review.id}">No, different product</button>
      </div>
    `;
    els.reviewsContainer.appendChild(card);
  });
}

function alertLabel(item) {
  if (item.alert_type === "any_drop") return "Alert on any drop";
  if (item.alert_type === "percent_drop") return `Alert on ${item.percent_drop || "?"}% drop`;
  return `Target ${formatMoney(item.target_price, item.currency)}`;
}

function autoCheckIntervalMinutes(item) {
  return item.check_interval_minutes ?? state.defaultCheckIntervalMinutes;
}

function autoCheckDot(item) {
  if (!item.enabled) {
    return '<span class="autocheck-dot off" title="Auto-check off"></span>';
  }
  const mins = autoCheckIntervalMinutes(item);
  return `<span class="autocheck-dot on" title="Auto-check every ${mins} minutes"></span>`;
}

function autoCheckBadge(item) {
  if (!item.enabled) {
    return {
      html: '<span class="badge autocheck off" title="Automatic scheduled checks are paused">Auto-check off</span>',
    };
  }
  const mins = autoCheckIntervalMinutes(item);
  const custom = item.check_interval_minutes != null ? " (custom)" : "";
  return {
    html: `<span class="badge autocheck on" title="Price is checked automatically every ${mins} minutes${custom}">⟳ every ${mins}m</span>`,
  };
}

function productPageUrl(item) {
  return item.product_url || item.current_source_url || null;
}

function itemTitleHtml(item) {
  const url = productPageUrl(item);
  const name = escapeHtml(item.name);
  if (!url) return name;
  const safeUrl = escapeHtml(url);
  return `<a class="item-title-link" href="${safeUrl}" target="_blank" rel="noreferrer noopener">${name}</a>`;
}

function priceHistoryChartHtml(item) {
  const points = (item.price_history || [])
    .filter((entry) => entry.price != null)
    .sort((a, b) => new Date(a.checked_at) - new Date(b.checked_at));

  if (points.length === 0) {
    return '<div class="price-chart empty">No price history yet — run a check to start the chart.</div>';
  }

  if (points.length === 1) {
    return `<div class="price-chart empty">One data point (${formatMoney(points[0].price, item.currency)}) — check again for a trend.</div>`;
  }

  const prices = points.map((entry) => entry.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const width = 320;
  const height = 88;
  const padX = 6;
  const padY = 8;

  const coords = prices.map((price, index) => {
    const x = padX + (index / (prices.length - 1)) * (width - padX * 2);
    const y = padY + (1 - (price - min) / range) * (height - padY * 2);
    return { x, y, price };
  });

  const polyline = coords.map((point) => `${point.x},${point.y}`).join(" ");
  const area = [
    `${coords[0].x},${height - padY}`,
    ...coords.map((point) => `${point.x},${point.y}`),
    `${coords[coords.length - 1].x},${height - padY}`,
  ].join(" ");

  const last = prices[prices.length - 1];
  const first = prices[0];
  const trend = last <= first ? "down" : "up";

  return `
    <div class="price-chart-wrap">
      <div class="price-chart-header">
        <span class="price-chart-title">Price history</span>
        <span class="price-chart-range">${formatMoney(min, item.currency)} – ${formatMoney(max, item.currency)}</span>
      </div>
      <svg class="price-chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Price history chart">
        <polygon class="price-chart-area ${trend}" points="${area}"></polygon>
        <polyline class="price-chart-line ${trend}" points="${polyline}"></polyline>
      </svg>
    </div>
  `;
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
  if (!els.itemsContainer) return;
  const filtered = state.items.filter(matchesFilter);
  els.itemsContainer.innerHTML = "";
  if (els.emptyState) els.emptyState.classList.toggle("hidden", filtered.length > 0);

  filtered.forEach((item) => {
    const delta = priceDelta(item);
    const card = document.createElement("article");
    card.className = `item-card ${item.alert_triggered ? "alert" : ""} ${item.enabled ? "" : "disabled"}`;
    card.innerHTML = `
      <div class="item-top">
        <div>
          <div class="item-title-row">
            ${autoCheckDot(item)}
            <div class="item-title">${itemTitleHtml(item)}</div>
          </div>
          <div class="item-meta">${escapeHtml(item.search_query)}</div>
          ${productPageUrl(item) ? `<div class="item-meta item-link"><a href="${escapeHtml(productPageUrl(item))}" target="_blank" rel="noreferrer noopener">Open product page ↗</a></div>` : ""}
        </div>
        <div class="badges">
          ${item.alert_triggered ? '<span class="badge warning">Alert</span>' : ""}
          ${autoCheckBadge(item).html}
          <span class="badge ${item.last_check_status}">${item.last_check_status}</span>
        </div>
      </div>
      <div class="price-row">
        <span class="current-price">${formatMoney(item.current_price, item.currency)}</span>
        ${delta ? `<span class="price-delta ${delta.className}">${delta.text}</span>` : ""}
      </div>
      ${priceHistoryChartHtml(item)}
      ${item.pending_match_reviews ? `<div class="badges"><span class="badge warning">${item.pending_match_reviews} review(s)</span></div>` : ""}
      <div class="item-meta">Last checked: ${formatDate(item.last_checked_at)} · ${alertLabel(item)}</div>
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
  els.itemForm.also_search_other_sites.checked = true;
  els.itemForm.currency.value = "EUR";

  if (item) {
    for (const field of ["name", "preferred_site", "search_query", "product_url", "target_price", "percent_drop", "currency", "tags", "notes", "check_interval_minutes"]) {
      if (item[field] != null) els.itemForm[field].value = item[field];
    }
    els.itemForm.alert_type.value = item.alert_type;
    els.itemForm.enabled.checked = item.enabled;
    els.itemForm.also_search_other_sites.checked = item.also_search_other_sites;
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
  payload.also_search_other_sites = Boolean(els.itemForm.also_search_other_sites.checked);
  payload.preferred_site = payload.preferred_site || null;
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

async function checkItem(id, button = null) {
  const originalLabel = button?.textContent;
  if (button) {
    button.disabled = true;
    button.textContent = "Checking…";
  }
  try {
    const result = await api(`/api/items/${id}/check`, { method: "POST" });
    const site = result.source_site ? ` on ${result.source_site}` : "";
    const reviews = result.pending_reviews ? ` · ${result.pending_reviews} match review(s)` : "";
    showToast(
      result.success
        ? `Checked: ${formatMoney(result.price, result.currency || "EUR")}${site}${result.alert_triggered ? " — alert!" : ""}${reviews}`
        : `${result.message || "Check failed"}${reviews}`,
      result.success ? "success" : "error",
    );
    await loadDashboard();
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalLabel;
    }
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
            ${entry.source_site ? `<div class="item-meta">Site: ${escapeHtml(entry.source_site)}</div>` : ""}
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

async function resolveReview(id, action) {
  try {
    await api(`/api/match-reviews/${id}/${action}`, { method: "POST" });
    showToast(action === "confirm" ? "Product match confirmed" : "Listing rejected");
    await loadDashboard();
  } catch (error) {
    showToast(error.message, "error");
  }
}

els.reviewsContainer.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-review-action]");
  if (!button) return;
  resolveReview(Number(button.dataset.id), button.dataset.reviewAction);
});

els.itemsContainer.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const id = Number(button.dataset.id);
  const action = button.dataset.action;
  if (action === "edit") openDialog(state.items.find((item) => item.id === id));
  if (action === "delete") deleteItem(id);
  if (action === "check") checkItem(id, button);
  if (action === "history") showHistory(id);
});

loadDashboard().catch((error) => showToast(error.message, "error"));
setInterval(() => loadDashboard().catch(() => {}), 30000);
