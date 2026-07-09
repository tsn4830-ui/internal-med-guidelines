const state = {
  catalog: null,
  articles: [],
  department: "all",
  query: "",
  type: "all",
  sort: "newest",
  freeOnly: false,
  examOnly: false,
  clinicalOnly: false,
  reviewedOnly: false,
  bookmarksOnly: false,
  activeTopic: null,
  bookmarks: new Set(JSON.parse(localStorage.getItem("im-review-bookmarks") || "[]")),
};

const els = {
  searchInput: document.querySelector("#searchInput"),
  departmentSelect: document.querySelector("#departmentSelect"),
  sortSelect: document.querySelector("#sortSelect"),
  freeOnlyToggle: document.querySelector("#freeOnlyToggle"),
  examToggle: document.querySelector("#examToggle"),
  clinicalToggle: document.querySelector("#clinicalToggle"),
  reviewedToggle: document.querySelector("#reviewedToggle"),
  bookmarksToggle: document.querySelector("#bookmarksToggle"),
  statsBand: document.querySelector("#statsBand"),
  topicList: document.querySelector("#topicList"),
  topicCount: document.querySelector("#topicCount"),
  resultList: document.querySelector("#resultList"),
  resultCount: document.querySelector("#resultCount"),
  sourceInfoButton: document.querySelector("#sourceInfoButton"),
  sourceDialog: document.querySelector("#sourceDialog"),
};

async function boot() {
  bindEvents();
  try {
    const response = await fetch("data/catalog.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.catalog = await response.json();
    state.articles = Array.isArray(state.catalog.articles) ? state.catalog.articles : [];
    populateDepartments();
    render();
  } catch (error) {
    els.resultList.innerHTML = `<div class="empty-state">資料載入失敗：${escapeHtml(error.message)}</div>`;
  }
}

function bindEvents() {
  els.searchInput.addEventListener("input", () => {
    state.query = els.searchInput.value.trim().toLowerCase();
    render();
  });
  els.departmentSelect.addEventListener("change", () => {
    state.department = els.departmentSelect.value;
    state.activeTopic = null;
    render();
  });
  els.sortSelect.addEventListener("change", () => {
    state.sort = els.sortSelect.value;
    render();
  });
  els.freeOnlyToggle.addEventListener("change", () => {
    state.freeOnly = els.freeOnlyToggle.checked;
    render();
  });
  els.examToggle.addEventListener("change", () => {
    state.examOnly = els.examToggle.checked;
    render();
  });
  els.clinicalToggle.addEventListener("change", () => {
    state.clinicalOnly = els.clinicalToggle.checked;
    render();
  });
  els.reviewedToggle.addEventListener("change", () => {
    state.reviewedOnly = els.reviewedToggle.checked;
    render();
  });
  els.bookmarksToggle.addEventListener("change", () => {
    state.bookmarksOnly = els.bookmarksToggle.checked;
    render();
  });
  document.querySelectorAll(".type-tab").forEach((button) => {
    button.addEventListener("click", () => {
      state.type = button.dataset.type;
      document.querySelectorAll(".type-tab").forEach((tab) => tab.classList.toggle("is-active", tab === button));
      render();
    });
  });
  els.sourceInfoButton.addEventListener("click", () => els.sourceDialog.showModal());
}

function populateDepartments() {
  const departments = unique(state.articles.map((article) => article.department).filter(Boolean)).sort();
  els.departmentSelect.innerHTML = [
    `<option value="all">全部科別</option>`,
    ...departments.map((department) => `<option value="${escapeAttr(department)}">${escapeHtml(department)}</option>`),
  ].join("");
}

function render() {
  const filtered = getFilteredArticles();
  renderStats(filtered);
  renderTopics(filtered);
  renderResults(filtered);
}

function getFilteredArticles() {
  const filtered = state.articles.filter((article) => {
    if (state.department !== "all" && article.department !== state.department) return false;
    if (state.activeTopic && article.disease !== state.activeTopic) return false;
    if (state.type !== "all" && article.articleType !== state.type) return false;
    if (state.freeOnly && !article.freeFullText) return false;
    if (state.examOnly && !isExamPriority(article)) return false;
    if (state.clinicalOnly && !isClinicalPriority(article)) return false;
    if (state.reviewedOnly && !isReviewed(article)) return false;
    if (state.bookmarksOnly && !state.bookmarks.has(article.id)) return false;
    if (!state.query) return true;
    return searchableText(article).includes(state.query);
  });

  return filtered.sort((a, b) => {
    if (state.sort === "exam") return priorityValue(b.examPriority) - priorityValue(a.examPriority) || score(b) - score(a);
    if (state.sort === "clinical") return priorityValue(b.clinicalPriority) - priorityValue(a.clinicalPriority) || score(b) - score(a);
    if (state.sort === "journal") return String(a.journal || "").localeCompare(String(b.journal || ""));
    return Number(b.year || 0) - Number(a.year || 0) || score(b) - score(a);
  });
}

function renderStats(filtered) {
  const all = state.articles;
  const generatedAt = state.catalog?.meta?.generatedAt ? formatDate(state.catalog.meta.generatedAt) : "未更新";
  const stats = [
    ["目前顯示", filtered.length],
    ["總收錄", all.length],
    ["免費全文", all.filter((item) => item.freeFullText).length],
    ["更新日期", generatedAt],
  ];
  els.statsBand.innerHTML = stats
    .map(([label, value]) => `<div class="stat-item"><span class="stat-label">${label}</span><span class="stat-value">${value}</span></div>`)
    .join("");
}

function renderTopics(filtered) {
  const visibleForPanel = state.articles.filter((article) => state.department === "all" || article.department === state.department);
  const topics = groupCount(visibleForPanel, "disease");
  els.topicCount.textContent = `${topics.length}`;
  els.topicList.innerHTML = [
    topicButton(null, "全部疾病", visibleForPanel.length, state.activeTopic === null),
    ...topics.map(([topic, count]) => topicButton(topic, topic, count, state.activeTopic === topic)),
  ].join("");

  els.topicList.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeTopic = button.dataset.topic || null;
      render();
    });
  });

  els.resultCount.textContent = `${filtered.length}`;
}

function topicButton(topic, label, count, active) {
  const meta = topic ? relatedDepartments(topic) : "所有分類";
  return `
    <button class="topic-button ${active ? "is-active" : ""}" type="button" data-topic="${escapeAttr(topic || "")}">
      <span>
        <span class="topic-name">${escapeHtml(label)}</span>
        <span class="topic-meta">${escapeHtml(meta)}</span>
      </span>
      <span class="topic-count">${count}</span>
    </button>
  `;
}

function renderResults(filtered) {
  if (!filtered.length) {
    els.resultList.innerHTML = `<div class="empty-state">沒有符合條件的文獻。調整篩選或先執行自動更新腳本。</div>`;
    return;
  }
  els.resultList.innerHTML = filtered.map(articleCard).join("");
  els.resultList.querySelectorAll("[data-bookmark]").forEach((button) => {
    button.addEventListener("click", () => {
      const id = button.dataset.bookmark;
      if (state.bookmarks.has(id)) state.bookmarks.delete(id);
      else state.bookmarks.add(id);
      localStorage.setItem("im-review-bookmarks", JSON.stringify([...state.bookmarks]));
      render();
    });
  });
}

function articleCard(article) {
  const badges = [
    article.articleType ? badge(article.articleType, "type") : "",
    article.freeFullText ? badge("免費全文", "free") : "",
    isExamPriority(article) ? badge("專考高頻", "exam") : "",
    isClinicalPriority(article) ? badge("臨床必讀", "clinical") : "",
    !isReviewed(article) ? badge(statusLabel(article.curationStatus), "pending") : "",
  ].join("");

  const links = [
    article.links?.pubmed ? linkChip("PubMed", article.links.pubmed) : "",
    article.links?.pmc ? linkChip("PMC", article.links.pmc) : "",
    article.links?.doi ? linkChip("DOI", article.links.doi) : "",
    article.links?.source ? linkChip("來源", article.links.source) : "",
  ].join("");

  const bookmarked = state.bookmarks.has(article.id);
  const points = Array.isArray(article.keyPoints) && article.keyPoints.length
    ? `<ul class="key-points">${article.keyPoints.slice(0, 3).map((point) => `<li>${escapeHtml(point)}</li>`).join("")}</ul>`
    : "";

  return `
    <article class="article-card">
      <div class="article-topline">
        <div>
          <h3 class="article-title">${escapeHtml(article.title || "Untitled")}</h3>
          <div class="article-meta">
            ${escapeHtml(article.journal || "Unknown source")} · ${escapeHtml(String(article.year || "n.d."))}<br />
            ${escapeHtml(article.department || "未分類")} / ${escapeHtml(article.disease || "未分類")}
            ${article.pmid ? ` · PMID ${escapeHtml(article.pmid)}` : ""}
          </div>
        </div>
        <button class="bookmark-button ${bookmarked ? "is-active" : ""}" type="button" data-bookmark="${escapeAttr(article.id)}" aria-label="收藏">
          ${bookmarked ? "★" : "☆"}
        </button>
      </div>
      <div class="badge-row">${badges}</div>
      ${points}
      <div class="article-links">${links}</div>
    </article>
  `;
}

function badge(label, type) {
  return `<span class="badge ${type}">${escapeHtml(label)}</span>`;
}

function linkChip(label, url) {
  return `<a class="link-chip" href="${escapeAttr(url)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`;
}

function searchableText(article) {
  return [
    article.id,
    article.pmid,
    article.title,
    article.journal,
    article.department,
    article.disease,
    article.articleType,
    ...(article.tags || []),
    ...(article.keyPoints || []),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function relatedDepartments(topic) {
  return unique(state.articles.filter((article) => article.disease === topic).map((article) => article.department).filter(Boolean)).join("、");
}

function groupCount(items, key) {
  const map = new Map();
  items.forEach((item) => {
    const value = item[key] || "未分類";
    map.set(value, (map.get(value) || 0) + 1);
  });
  return [...map.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

function unique(values) {
  return [...new Set(values)];
}

function isReviewed(article) {
  return ["reviewed", "curated"].includes(article.curationStatus);
}

function isExamPriority(article) {
  if (!isCuratedForPriority(article)) return false;
  return ["high", "core"].includes(article.examPriority) || Number(article.examWeight || 0) >= 4;
}

function isClinicalPriority(article) {
  if (!isCuratedForPriority(article)) return false;
  return ["high", "core"].includes(article.clinicalPriority) || Number(article.clinicalWeight || 0) >= 4;
}

function isCuratedForPriority(article) {
  return isReviewed(article) || article.curationStatus === "seed";
}

function priorityValue(priority) {
  return { core: 4, high: 3, medium: 2, low: 1, unrated: 0 }[priority] || 0;
}

function score(article) {
  return Number(article.score || 0) + priorityValue(article.examPriority) * 10 + priorityValue(article.clinicalPriority) * 10;
}

function statusLabel(status) {
  return status === "seed" ? "示例來源" : "待審核";
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("zh-TW", { year: "numeric", month: "2-digit", day: "2-digit" });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

boot();
