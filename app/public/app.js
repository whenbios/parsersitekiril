const state = {
  activeJobType: null,
  jobId: null,
  collectorJobId: null,
  results: [],
  collectedResults: [],
};

const collectForm = document.getElementById("collectForm");
const filterUrlInput = document.getElementById("filterUrlInput");
const collectorSummary = document.getElementById("collectorSummary");
const collectorBody = document.getElementById("collectorBody");
const downloadCollectedCsvBtn = document.getElementById("downloadCollectedCsvBtn");
const downloadCollectedXlsxBtn = document.getElementById("downloadCollectedXlsxBtn");
const runCollectedEnrichmentBtn = document.getElementById("runCollectedEnrichmentBtn");

const uploadForm = document.getElementById("uploadForm");
const linksForm = document.getElementById("linksForm");
const fileInput = document.getElementById("fileInput");
const fileName = document.getElementById("fileName");
const linksInput = document.getElementById("linksInput");
const resultsBody = document.getElementById("resultsBody");
const jobStatus = document.getElementById("jobStatus");
const refreshBtn = document.getElementById("refreshBtn");
const downloadCsvBtn = document.getElementById("downloadCsvBtn");
const downloadXlsxBtn = document.getElementById("downloadXlsxBtn");
const progressSummary = document.getElementById("progressLabel");
const progressCounts = document.getElementById("progressCounts");
const progressFill = document.getElementById("progressFill");
const progressStats = document.getElementById("progressStats");
const drawer = document.getElementById("detailsDrawer");
const drawerContent = document.getElementById("drawerContent");
const closeDrawer = document.getElementById("closeDrawer");

let pollTimer = null;

fileInput.addEventListener("change", () => {
  fileName.textContent = fileInput.files.length ? fileInput.files[0].name : "Файл еще не выбран";
});

collectForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const filterUrl = filterUrlInput.value.trim();
  if (!filterUrl) return;

  state.activeJobType = "collector";
  state.collectorJobId = null;
  state.collectedResults = [];
  renderCollectorTable();
  syncCollectorButtons();
  setStatus("processing", "Сбор ссылок");

  const response = await fetch("/collectors/workua/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filter_url: filterUrl }),
  });
  const data = await response.json();
  state.collectorJobId = data.job_id;
  syncCollectorButtons();
  startPolling();
});

runCollectedEnrichmentBtn.addEventListener("click", async () => {
  if (!state.collectorJobId) return;
  setStatus("processing", "Запуск анализа");
  const response = await fetch(`/collectors/workua/${state.collectorJobId}/start-enrichment`, {
    method: "POST",
  });
  const data = await response.json();
  state.activeJobType = "enrichment";
  state.jobId = data.job_id;
  setExportButtons();
  startPolling();
});

downloadCollectedCsvBtn.addEventListener("click", () => {
  if (state.collectorJobId) window.open(`/collectors/workua/${state.collectorJobId}/export.csv`, "_blank");
});

downloadCollectedXlsxBtn.addEventListener("click", () => {
  if (state.collectorJobId) window.open(`/collectors/workua/${state.collectorJobId}/export.xlsx`, "_blank");
});

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!fileInput.files.length) return;
  const form = new FormData();
  form.append("file", fileInput.files[0]);
  state.activeJobType = "enrichment";
  setStatus("processing", "Загрузка");
  const response = await fetch("/jobs/upload", { method: "POST", body: form });
  const data = await response.json();
  state.jobId = data.job_id;
  setExportButtons();
  startPolling();
});

linksForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const lines = linksInput.value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) return;

  const items = lines.map((line, index) => {
    const [company, url] = line.includes("|") ? line.split("|", 2) : ["", line];
    return {
      row_index: index + 2,
      company_name: company.trim() || `Link ${index + 1}`,
      workua_url: url.trim(),
    };
  });

  state.activeJobType = "enrichment";
  setStatus("processing", "Запуск");
  const response = await fetch("/jobs/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });
  const data = await response.json();
  state.jobId = data.job_id;
  setExportButtons();
  startPolling();
});

refreshBtn.addEventListener("click", async () => {
  if (state.activeJobType === "collector" && state.collectorJobId) {
    await refreshCollectorResults();
  } else if (state.jobId) {
    await refreshResults();
  }
});

downloadCsvBtn.addEventListener("click", () => {
  if (state.jobId) window.open(`/jobs/${state.jobId}/export.csv`, "_blank");
});

downloadXlsxBtn.addEventListener("click", () => {
  if (state.jobId) window.open(`/jobs/${state.jobId}/export.xlsx`, "_blank");
});

closeDrawer.addEventListener("click", () => drawer.classList.add("hidden"));
drawer.addEventListener("click", (event) => {
  if (event.target === drawer) drawer.classList.add("hidden");
});

async function refreshCollectorResults() {
  const statusResponse = await fetch(`/collectors/workua/${state.collectorJobId}/status`);
  const statusData = await statusResponse.json();
  updateCollectorProgress(statusData);

  const resultsResponse = await fetch(`/collectors/workua/${state.collectorJobId}/results`);
  const resultsData = await resultsResponse.json();
  state.collectedResults = resultsData.items;
  renderCollectorTable();
  syncCollectorButtons();

  if (statusData.status === "completed") {
    stopPolling();
  }
}

async function refreshResults() {
  const statusResponse = await fetch(`/jobs/${state.jobId}/status`);
  const statusData = await statusResponse.json();
  updateEnrichmentProgress(statusData);

  const statusKind =
    statusData.status === "completed"
      ? "done"
      : statusData.status === "failed"
        ? "failed"
        : "processing";
  setStatus(statusKind, translateStatus(statusData.status));

  const resultsResponse = await fetch(`/jobs/${state.jobId}/results`);
  const resultsData = await resultsResponse.json();
  state.results = resultsData.items;
  renderTable();

  if (statusData.status === "completed" || statusData.status === "failed") {
    stopPolling();
  }
}

function renderCollectorTable() {
  if (!state.collectedResults.length) {
    collectorBody.innerHTML = `<tr><td colspan="3" class="empty-state">После сбора здесь появится список вакансий.</td></tr>`;
    return;
  }

  collectorBody.innerHTML = state.collectedResults
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.company_name || "Без названия")}</td>
          <td><a href="${item.workua_url}" target="_blank" rel="noopener">${escapeHtml(item.workua_url)}</a></td>
          <td>${escapeHtml(String(item.page_number || ""))}</td>
        </tr>
      `,
    )
    .join("");
}

function renderTable() {
  if (!state.results.length) {
    resultsBody.innerHTML = `<tr><td colspan="6" class="empty-state">После запуска здесь появятся результаты.</td></tr>`;
    return;
  }

  resultsBody.innerHTML = state.results
    .map((item, index) => {
      const website = item.website
        ? `<a href="${item.website}" target="_blank" rel="noopener">${escapeHtml(item.website)}</a>`
        : "-";
      const best = item.best_contact ? `<span class="contact-pill">${escapeHtml(item.best_contact)}</span>` : "-";
      const backup = item.backup_contact || "-";
      const workua = item.workua_fallback || "-";

      return `
        <tr data-index="${index}">
          <td>${escapeHtml(item.company_name || "Без названия")}</td>
          <td>${website}</td>
          <td>${best}</td>
          <td>${escapeHtml(backup)}</td>
          <td>${escapeHtml(workua)}</td>
          <td class="status-cell ${escapeHtml(item.status || "")}">${escapeHtml(translateStatus(item.status || ""))}</td>
        </tr>
      `;
    })
    .join("");

  resultsBody.querySelectorAll("tr[data-index]").forEach((row) => {
    row.addEventListener("click", () => {
      const item = state.results[Number(row.dataset.index)];
      renderDrawer(item);
    });
  });
}

function renderDrawer(item) {
  drawerContent.innerHTML = `
    <h2 class="drawer-title">${escapeHtml(item.company_name || "Без названия")}</h2>
    ${item.website ? `<a class="drawer-link" href="${item.website}" target="_blank" rel="noopener">${escapeHtml(item.website)}</a>` : ""}
    ${detailGroup("Главное", [
      ["Лучший контакт", item.best_contact],
      ["Запасной контакт", item.backup_contact],
      ["Контакт из Work.ua", item.workua_fallback],
      ["Статус", translateStatus(item.status || "")],
      ["Комментарий", item.notes],
    ])}
    ${detailGroup("Контакты с сайта", [
      ["Основной email", item.email_outreach],
      ["Дополнительный email", item.email_secondary],
      ["Email руководителя", item.manager_email],
      ["Email маркетинга", item.marketing_email],
      ["Telegram", item.telegram_1],
      ["WhatsApp", item.whatsapp],
      ["Прямой телефон", item.phone_direct],
      ["Публичный телефон", item.phone_public],
      ["Другие телефоны", [item.phone_1, item.phone_2, item.phone_3].filter(Boolean).join(", ")],
      ["Instagram", item.instagram],
      ["Facebook", item.facebook],
      ["LinkedIn", item.linkedin],
    ])}
    ${detailGroup("Контакты из Work.ua", [
      ["Email", item.workua_email],
      ["Telegram", item.workua_telegram],
      ["Телефон", item.workua_phone],
    ])}
    ${item.error ? detailGroup("Если возникла проблема", [["Ошибка", item.error]]) : ""}
  `;
  drawer.classList.remove("hidden");
}

function detailGroup(title, rows) {
  return `
    <section class="detail-group">
      <h3>${escapeHtml(title)}</h3>
      ${rows.map(([label, value]) => detailRow(label, value)).join("")}
    </section>
  `;
}

function detailRow(label, value) {
  const safeValue = value ? escapeHtml(String(value)) : "-";
  return `<div class="detail-row"><div class="detail-label">${escapeHtml(label)}</div><div>${safeValue}</div></div>`;
}

function setStatus(kind, label) {
  jobStatus.className = `status-chip ${kind}`;
  jobStatus.textContent = label;
}

function updateCollectorProgress(statusData) {
  const total = statusData.total_pages || statusData.processed_pages || 0;
  const processed = statusData.processed_pages || 0;
  const percent = total ? Math.min(100, Math.round((processed / total) * 100)) : 0;

  progressSummary.textContent =
    statusData.status === "completed"
      ? "Сбор вакансий завершен"
      : statusData.status === "failed"
        ? "Сбор вакансий завершился с ошибкой"
        : "Идет сбор вакансий из фильтра Work.ua";
  progressCounts.textContent = total ? `${processed} из ${total} страниц обработано` : `${processed} страниц обработано`;
  progressFill.style.width = `${percent}%`;
  progressStats.innerHTML = `
    <span>Собрано вакансий: ${statusData.found_items}</span>
    <span>Обработано страниц: ${statusData.processed_pages}</span>
    <span>Всего страниц: ${statusData.total_pages || "—"}</span>
  `;

  collectorSummary.textContent =
    statusData.status === "completed"
      ? `Найдено ${statusData.found_items} вакансий на ${statusData.processed_pages} страницах.`
      : `Собрано ${statusData.found_items} вакансий. Обработано страниц: ${statusData.processed_pages}.`;

  const statusKind =
    statusData.status === "completed"
      ? "done"
      : statusData.status === "failed"
        ? "failed"
        : "processing";
  setStatus(statusKind, statusData.status === "completed" ? "Список собран" : "Сбор ссылок");
}

function updateEnrichmentProgress(statusData) {
  const done = statusData.done_items + statusData.failed_items;
  const total = statusData.total_items || 0;
  const percent = total ? Math.min(100, Math.round((done / total) * 100)) : 0;

  progressSummary.textContent =
    statusData.status === "completed"
      ? "Проверка завершена"
      : statusData.status === "failed"
        ? "Проверка завершилась с ошибкой"
        : "Идет анализ контактов";
  progressCounts.textContent = total ? `${done} из ${total} проверено` : "0 из 0 проверено";
  progressFill.style.width = `${percent}%`;
  progressStats.innerHTML = `
    <span>Готово: ${statusData.done_items}</span>
    <span>В работе: ${statusData.processing_items}</span>
    <span>В очереди: ${statusData.queued_items}</span>
    <span>Ошибки: ${statusData.failed_items}</span>
  `;
}

function syncCollectorButtons() {
  const enabled = Boolean(state.collectorJobId && state.collectedResults.length);
  downloadCollectedCsvBtn.disabled = !enabled;
  downloadCollectedXlsxBtn.disabled = !enabled;
  runCollectedEnrichmentBtn.disabled = !enabled;
}

function setExportButtons() {
  const enabled = Boolean(state.jobId);
  downloadCsvBtn.disabled = !enabled;
  downloadXlsxBtn.disabled = !enabled;
}

function startPolling() {
  stopPolling();
  if (state.activeJobType === "collector") {
    refreshCollectorResults();
    pollTimer = window.setInterval(refreshCollectorResults, 2500);
    return;
  }
  refreshResults();
  pollTimer = window.setInterval(refreshResults, 2500);
}

function stopPolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
}

function translateStatus(status) {
  if (status === "completed" || status === "done") return "Готово";
  if (status === "failed") return "Ошибка";
  if (status === "partial") return "Частично";
  if (status === "processing") return "В работе";
  if (status === "queued") return "В очереди";
  if (status === "new") return "Новая";
  return status || "-";
}

function escapeHtml(value) {
  return value
    .toString()
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
