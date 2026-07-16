"use strict";

const state = {
  selectedFile: null,
  auditRecords: [],
  loadingTimer: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const elements = {
  form: $("#evaluation-form"),
  fileInput: $("#proposal-file"),
  dropZone: $("#drop-zone"),
  dropCopy: $("#drop-copy"),
  criteria: $("#rfp-criteria"),
  criteriaCount: $("#criteria-count"),
  evaluateButton: $("#evaluate-button"),
  resultEmpty: $("#result-empty"),
  resultLoading: $("#result-loading"),
  resultContent: $("#result-content"),
  auditList: $("#audit-list"),
  auditEmpty: $("#audit-empty"),
  auditSearch: $("#audit-search"),
  rankingBody: $("#ranking-body"),
  rankingEmpty: $("#ranking-empty"),
  toast: $("#toast"),
};

const sampleCriteria = [
  "Complete implementation within 16 weeks.",
  "Maintain PCI-DSS compliance throughout migration.",
  "Hold valid ISO 27001 and SOC 2 Type II certifications.",
  "Provide 24/7 monitoring and managed support.",
  "Guarantee at least 99.9% service uptime.",
  "Keep the total first-year investment below $200,000.",
].join("\n");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatDate(value, includeTime = false) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown date";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    ...(includeTime ? { timeStyle: "short" } : {}),
  }).format(date);
}

function scoreLabel(score) {
  if (score >= 90) return "Excellent fit";
  if (score >= 75) return "Strong fit";
  if (score >= 60) return "Moderate fit";
  if (score >= 40) return "Limited fit";
  return "High risk";
}

function consistencyMeta(value) {
  if (value === true) return { label: "Verified", className: "" };
  if (value === false) return { label: "Concern found", className: "danger" };
  return { label: "Check unavailable", className: "warning" };
}

async function apiRequest(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail = typeof payload === "object" && payload?.detail
      ? payload.detail
      : typeof payload === "string" && payload
        ? payload
        : `Request failed with status ${response.status}.`;
    throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg).join("; ") : detail);
  }
  return payload;
}

function showToast(message, type = "success") {
  elements.toast.textContent = message;
  elements.toast.className = `toast show${type === "error" ? " error" : ""}`;
  window.clearTimeout(showToast.timeout);
  showToast.timeout = window.setTimeout(() => {
    elements.toast.classList.remove("show");
  }, 4200);
}

function updateFile(file) {
  if (!file) return;
  const extension = `.${file.name.split(".").pop()?.toLowerCase()}`;
  if (![".pdf", ".docx", ".xlsx"].includes(extension)) {
    showToast("Choose a PDF, DOCX, or XLSX proposal.", "error");
    return;
  }

  state.selectedFile = file;
  elements.dropZone.classList.add("file-selected");
  elements.dropCopy.innerHTML = `
    <strong>${escapeHtml(file.name)}</strong>
    <p>${formatFileSize(file.size)} · Ready to evaluate</p>
    <small>Click or drop another file to replace</small>
  `;
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function setEvaluationState(mode) {
  elements.resultEmpty.hidden = mode !== "empty";
  elements.resultLoading.hidden = mode !== "loading";
  elements.resultContent.hidden = mode !== "result";
  elements.evaluateButton.disabled = mode === "loading";
  elements.evaluateButton.querySelector(".button-label").textContent = mode === "loading"
    ? "Evaluation in progress"
    : "Run evaluation";

  window.clearInterval(state.loadingTimer);
  if (mode !== "loading") return;

  const messages = [
    "Extracting document evidence...",
    "Comparing evidence with RFP criteria...",
    "Recomputing semantic consistency...",
  ];
  let step = 0;
  $("#loading-message").textContent = messages[step];
  $$(".loading-steps span").forEach((item, index) => item.classList.toggle("active", index === step));
  state.loadingTimer = window.setInterval(() => {
    step = Math.min(step + 1, messages.length - 1);
    $("#loading-message").textContent = messages[step];
    $$(".loading-steps span").forEach((item, index) => item.classList.toggle("active", index <= step));
  }, 3500);
}

function renderResult(record) {
  const meta = consistencyMeta(record.consistent);
  $("#result-vendor").textContent = record.vendor_name;
  $("#result-score").textContent = record.score;
  $("#score-label").textContent = scoreLabel(record.score);
  $("#result-date").textContent = `Evaluated ${formatDate(record.timestamp, true)}`;
  $("#result-reasoning").textContent = record.reasoning;
  $("#result-concern").textContent = record.consistent === true
    ? "The stored score matches the independently recomputed semantic score."
    : record.concern || record.consistency_error || "The consistency review did not complete.";

  const status = $("#result-status");
  status.textContent = meta.label;
  status.className = `status-badge ${meta.className}`.trim();
  $("#score-ring").style.setProperty("--score", record.score);

  $("#hero-score").textContent = record.score;
  $("#hero-progress").style.width = `${record.score}%`;
  $("#hero-consistency").textContent = meta.label;
  setEvaluationState("result");
}

async function submitEvaluation(event) {
  event.preventDefault();
  if (!state.selectedFile) {
    showToast("Select a proposal document first.", "error");
    elements.dropZone.focus();
    return;
  }
  const criteria = elements.criteria.value.trim();
  if (!criteria) {
    showToast("Add the RFP evaluation criteria.", "error");
    elements.criteria.focus();
    return;
  }

  const formData = new FormData();
  formData.append("file", state.selectedFile);
  formData.append("rfp_criteria", criteria);
  setEvaluationState("loading");

  try {
    const record = await apiRequest("/score-vendor", { method: "POST", body: formData });
    renderResult(record);
    await refreshAudit();
    showToast("Vendor evaluation completed and added to the audit trail.");
  } catch (error) {
    setEvaluationState("empty");
    showToast(error.message || "Evaluation failed.", "error");
  }
}

function updateMetrics(records) {
  const total = records.length;
  const average = total ? Math.round(records.reduce((sum, item) => sum + item.score, 0) / total) : null;
  const verified = records.filter((item) => item.consistent === true).length;
  $("#metric-total").textContent = total;
  $("#metric-average").textContent = average === null ? "—" : average;
  $("#metric-verified").textContent = verified;

  if (records[0] && $("#hero-score").textContent === "—") {
    $("#hero-score").textContent = records[0].score;
    $("#hero-progress").style.width = `${records[0].score}%`;
    $("#hero-consistency").textContent = consistencyMeta(records[0].consistent).label;
  }
}

function renderAudit(filter = "") {
  const query = filter.trim().toLowerCase();
  const records = state.auditRecords.filter((item) => item.vendor_name.toLowerCase().includes(query));
  elements.auditEmpty.hidden = records.length > 0;
  elements.auditList.innerHTML = records.map((record) => {
    const meta = consistencyMeta(record.consistent);
    return `
      <article class="audit-card">
        <div class="audit-score">${escapeHtml(record.score)}</div>
        <div class="audit-main">
          <h3>${escapeHtml(record.vendor_name)}</h3>
          <p>${escapeHtml(record.reasoning)}</p>
        </div>
        <div class="audit-meta">
          <span class="verification ${meta.className}">${escapeHtml(meta.label)}</span>
          <time datetime="${escapeHtml(record.timestamp)}">${escapeHtml(formatDate(record.timestamp, true))}</time>
          <code title="Audit ID">${escapeHtml(record.audit_id.slice(0, 12))}…</code>
        </div>
      </article>
    `;
  }).join("");
}

async function renderRankings() {
  const records = state.auditRecords;
  elements.rankingEmpty.hidden = records.length > 0;
  if (!records.length) {
    elements.rankingBody.innerHTML = "";
    return;
  }

  const request = records.map((item) => ({
    name: item.vendor_name,
    score: item.score,
    reasoning: item.reasoning,
  }));

  try {
    const rankings = await apiRequest("/rank-vendors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });

    elements.rankingBody.innerHTML = rankings.map((vendor, index) => {
      const source = records.find((item) => item.vendor_name === vendor.name && item.score === vendor.score) || {};
      const meta = consistencyMeta(source.consistent);
      return `
        <tr>
          <td><span class="rank-number">${index + 1}</span></td>
          <td class="vendor-cell"><strong>${escapeHtml(vendor.name)}</strong><small>${escapeHtml(vendor.reasoning)}</small></td>
          <td><span class="table-score">${escapeHtml(vendor.score)}</span> / 100</td>
          <td><span class="verification ${meta.className}">${escapeHtml(meta.label)}</span></td>
          <td>${escapeHtml(formatDate(source.timestamp))}</td>
        </tr>
      `;
    }).join("");
  } catch (error) {
    showToast(error.message || "Could not refresh rankings.", "error");
  }
}

async function refreshAudit() {
  try {
    const records = await apiRequest("/audit-trail");
    state.auditRecords = [...records].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    updateMetrics(state.auditRecords);
    renderAudit(elements.auditSearch.value);
    await renderRankings();
  } catch (error) {
    showToast(error.message || "Could not load the audit trail.", "error");
  }
}

async function submitQuestion(event) {
  event.preventDefault();
  const rfpText = $("#rfp-text").value.trim();
  const question = $("#chat-question").value.trim();
  if (!rfpText || !question) return;

  const button = $("#ask-button");
  const answer = $("#chat-answer");
  button.disabled = true;
  button.textContent = "Thinking...";
  answer.textContent = "Finding the closest semantic evidence...";

  const formData = new FormData();
  formData.append("rfp_text", rfpText);
  formData.append("question", question);

  try {
    const payload = await apiRequest("/chat", { method: "POST", body: formData });
    answer.textContent = payload.answer;
  } catch (error) {
    answer.textContent = "Relevant evidence could not be retrieved.";
    showToast(error.message || "RFP question failed.", "error");
  } finally {
    button.disabled = false;
    button.innerHTML = "Ask <span>→</span>";
  }
}

function initializeFileUpload() {
  elements.dropZone.addEventListener("click", () => elements.fileInput.click());
  elements.dropZone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      elements.fileInput.click();
    }
  });
  elements.fileInput.addEventListener("change", () => updateFile(elements.fileInput.files[0]));
  ["dragenter", "dragover"].forEach((type) => elements.dropZone.addEventListener(type, (event) => {
    event.preventDefault();
    elements.dropZone.classList.add("dragover");
  }));
  ["dragleave", "drop"].forEach((type) => elements.dropZone.addEventListener(type, (event) => {
    event.preventDefault();
    elements.dropZone.classList.remove("dragover");
  }));
  elements.dropZone.addEventListener("drop", (event) => updateFile(event.dataTransfer.files[0]));
}

function initializeNavigation() {
  const links = $$(".nav-link");
  links.forEach((link) => link.addEventListener("click", () => {
    links.forEach((item) => item.classList.toggle("active", item === link));
  }));

  const observer = new IntersectionObserver((entries) => {
    const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (!visible) return;
    links.forEach((link) => link.classList.toggle("active", link.dataset.section === visible.target.id));
  }, { rootMargin: "-25% 0px -60%", threshold: [0.05, 0.3] });
  $$("main section[id]").forEach((section) => observer.observe(section));
}

function initializeTheme() {
  const saved = localStorage.getItem("procurelens-theme");
  const theme = saved || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  document.documentElement.dataset.theme = theme;
  $("#theme-toggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("procurelens-theme", next);
  });
}

function initialize() {
  initializeTheme();
  initializeNavigation();
  initializeFileUpload();
  elements.form.addEventListener("submit", submitEvaluation);
  $("#chat-form").addEventListener("submit", submitQuestion);
  $("#sample-criteria").addEventListener("click", () => {
    elements.criteria.value = sampleCriteria;
    elements.criteria.dispatchEvent(new Event("input"));
    elements.criteria.focus();
  });
  elements.criteria.addEventListener("input", () => {
    elements.criteriaCount.textContent = `${elements.criteria.value.length} characters`;
  });
  elements.auditSearch.addEventListener("input", () => renderAudit(elements.auditSearch.value));
  $("#refresh-rankings").addEventListener("click", refreshAudit);
  $("#view-audit").addEventListener("click", () => {
    elements.auditSearch.value = $("#result-vendor").textContent;
    renderAudit(elements.auditSearch.value);
    $("#audit").scrollIntoView({ behavior: "smooth" });
  });
  refreshAudit();
}

document.addEventListener("DOMContentLoaded", initialize);
