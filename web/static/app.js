const form = document.querySelector("#search-form");
const input = document.querySelector("#query");
const submit = form.querySelector("button[type=submit]");
const resultsSection = document.querySelector("#results-section");
const results = document.querySelector("#results");
const empty = document.querySelector("#empty");
const status = document.querySelector("#status");
const summary = document.querySelector("#result-summary");
const embedLatency = document.querySelector("#embed-latency");
const totalLatency = document.querySelector("#total-latency");
const namespaceLabel = document.querySelector("#namespace-label");
const corpusSize = document.querySelector("#corpus-size");

const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[char]);

const safeDimension = (value) => {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? Math.round(number) : 1;
};

const compactText = (value, fallback, limit) => {
  const normalized = String(value || fallback).replace(/\s+/g, " ").trim();
  return normalized.length <= limit ? normalized : `${normalized.slice(0, limit - 1).trimEnd()}…`;
};

function renderRows(rows) {
  results.innerHTML = rows.map((row, index) => {
    const width = safeDimension(row.width);
    const height = safeDimension(row.height);
    const distance = Number.isFinite(row.$dist) ? row.$dist.toFixed(4) : "match";
    const title = compactText(row.title, "Untitled image", 180);
    const description = compactText(row.description, "Freely licensed image from Wikimedia Commons.", 240);
    const artist = compactText(row.artist, "Commons contributor", 120);
    return `
      <li class="result">
        <a class="image-link" data-rank="${index + 1}" href="${escapeHtml(row.source_url)}" target="_blank" rel="noreferrer" style="aspect-ratio:${width}/${height}">
          <img src="${escapeHtml(row.image_url)}" alt="${escapeHtml(title)}" loading="lazy" width="${width}" height="${height}">
        </a>
        <h3><a href="${escapeHtml(row.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(title)}</a></h3>
        <p class="description">${escapeHtml(description)}</p>
        <p class="meta"><span>${escapeHtml(artist)}</span><span>·</span><a href="${escapeHtml(row.license_url || row.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(row.license_name || "source license")}</a><span>·</span><span>distance ${distance}</span></p>
      </li>`;
  }).join("");
}

async function runSearch(query) {
  submit.disabled = true;
  submit.querySelector("span").textContent = "Searching…";
  status.textContent = "The gateway is running CLIP's text tower on CPU…";
  embedLatency.textContent = "embedding…";
  resultsSection.hidden = true;
  empty.hidden = true;
  empty.querySelector("h2").textContent = "No close images yet.";
  empty.querySelector("p").textContent = "Try a broader visual description.";
  try {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query, top_k: 16 }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `Search failed (${response.status})`);
    const rows = data.rows || [];
    embedLatency.textContent = data.performance?.embedding_ms == null
      ? "cache hit"
      : `${Number(data.performance.embedding_ms).toFixed(2)} ms`;
    totalLatency.textContent = `${Number(data.took_ms).toFixed(1)} ms`;
    namespaceLabel.textContent = `${data.serving?.prefer || "local"} · ${data.serving?.dims || 512}d · ${data.serving?.query_modality || "text"}→image`;
    summary.textContent = `${rows.length} images for “${query}”`;
    if (rows.length) {
      renderRows(rows);
      resultsSection.hidden = false;
      resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      empty.hidden = false;
    }
    const tokens = data.performance?.embedding_tokens;
    status.textContent = `Gateway echo: local CLIP on CPU · ${tokens == null ? "cached query vector" : `${tokens} text tokens`} · no GPU workers.`;
    history.replaceState(null, "", `?q=${encodeURIComponent(query)}`);
  } catch (error) {
    embedLatency.textContent = "unavailable";
    empty.hidden = false;
    empty.querySelector("h2").textContent = "Search is temporarily unavailable.";
    empty.querySelector("p").textContent = error.message;
    status.textContent = error.message;
  } finally {
    submit.disabled = false;
    submit.querySelector("span").textContent = "Search images";
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = input.value.trim();
  if (query) runSearch(query);
});

document.querySelectorAll(".examples button").forEach((button) => {
  button.addEventListener("click", () => {
    input.value = button.textContent;
    runSearch(input.value);
  });
});

fetch("/api/config").then((response) => response.json()).then((config) => {
  namespaceLabel.textContent = config.namespace;
}).catch(() => {});

fetch("/api/stats").then((response) => response.json()).then((stats) => {
  corpusSize.textContent = Number.isFinite(stats.approx_row_count)
    ? Number(stats.approx_row_count).toLocaleString()
    : "unavailable";
}).catch(() => {
  corpusSize.textContent = "unavailable";
});

const initial = new URL(location.href).searchParams.get("q");
if (initial) {
  input.value = initial;
  runSearch(initial);
}
