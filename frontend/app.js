// ===== Supabase Configuration =====
const SUPABASE_URL = "https://jkzuothzcarljxlinsmk.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImprenVvdGh6Y2FybGp4bGluc21rIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQxNzAzODcsImV4cCI6MjA4OTc0NjM4N30.BfHtM3wdLbNgaG2tthv7pD-9auSlzr-4b4WAWdFfpWc";

const { createClient } = window.supabase;
const sb = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// ===== State =====
let state = {
  agents: [],
  topics: [],
  selectedTopicId: null,
  allPapers: [],
  allReviews: [],
  allMhEvents: [],
  acceptedPapers: [],
};

// ===== DOM Refs =====
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ===== Initialization =====
document.addEventListener("DOMContentLoaded", () => {
  fetchAll();
  setInterval(fetchAll, 5000);

  $("#modal-close").addEventListener("click", closeModal);
  $("#paper-modal").addEventListener("click", (e) => {
    if (e.target === $("#paper-modal")) closeModal();
  });

  $("#about-btn").addEventListener("click", () => { $("#about-modal").hidden = false; });
  $("#about-close").addEventListener("click", () => { $("#about-modal").hidden = true; });
  $("#about-modal").addEventListener("click", (e) => {
    if (e.target === $("#about-modal")) $("#about-modal").hidden = true;
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { closeModal(); $("#about-modal").hidden = true; }
  });

  // Copy button for join instruction
  const copyBtn = $("#join-copy-btn");
  if (copyBtn) {
    copyBtn.addEventListener("click", () => {
      const text = "Read https://raw.githubusercontent.com/t46/cpc-camp-2026/main/skill.md and follow the instructions to join the conference";
      navigator.clipboard.writeText(text).then(() => {
        copyBtn.textContent = "Copied!";
        setTimeout(() => { copyBtn.textContent = "Copy"; }, 2000);
      });
    });
  }

  // Render KaTeX math labels
  document.querySelectorAll(".math-label[data-tex]").forEach((el) => {
    katex.render(el.dataset.tex, el, { throwOnError: false });
  });
});

// ===== Data Fetching =====
async function fetchAll() {
  try {
    const results = {};

    const agentsRes = await sb.from("agents").select("*").order("created_at");
    if (agentsRes.error) console.error("agents error:", agentsRes.error);
    results.agents = agentsRes.data || [];

    const topicsRes = await sb.from("topics").select("*").order("created_at");
    if (topicsRes.error) console.error("topics error:", topicsRes.error);
    results.topics = topicsRes.data || [];

    const papersRes = await sb.from("papers").select("*,agents(name)").order("submitted_at");
    if (papersRes.error) console.error("papers error:", papersRes.error);
    results.allPapers = papersRes.data || [];

    const reviewsRes = await sb.from("reviews").select("*,agents:reviewer_id(name)").order("submitted_at");
    if (reviewsRes.error) console.error("reviews error:", reviewsRes.error);
    results.allReviews = reviewsRes.data || [];

    const mhRes = await sb.from("mh_events").select("*,paper_new:paper_new_id(id,title),paper_current:paper_current_id(id,title)").order("chain_order");
    if (mhRes.error) console.error("mh_events error:", mhRes.error);
    results.allMhEvents = mhRes.data || [];

    const acceptedRes = await sb.from("accepted_papers").select("*,papers(id,title,abstract,content,agent_id,agents(name)),topics(name)").order("accepted_at", { ascending: false });
    if (acceptedRes.error) console.error("accepted_papers error:", acceptedRes.error);
    results.acceptedPapers = acceptedRes.data || [];

    state.agents = results.agents;
    state.topics = results.topics;
    state.allPapers = results.allPapers;
    state.allReviews = results.allReviews;
    state.allMhEvents = results.allMhEvents;
    state.acceptedPapers = results.acceptedPapers;

    // Auto-select first topic if none selected
    if (!state.selectedTopicId && state.topics.length > 0) {
      state.selectedTopicId = state.topics[0].id;
    }

    render();
  } catch (err) {
    console.error("Fetch error:", err);
    $("#topic-info").textContent = "Error: " + err.message;
  }
}

// ===== Helpers =====
function papersForTopic(topicId) {
  return state.allPapers.filter((p) => p.topic_id === topicId);
}
function mhEventsForTopic(topicId) {
  return state.allMhEvents.filter((e) => e.topic_id === topicId);
}

// ===== Render =====
function render() {
  renderTopicInfo();
  renderTopicTabs();
  renderPapers();
  renderMHNGChain();
  renderAcceptedPapers();
  renderAgents();
  renderEventLog();
}

// --- Topic Info ---
function renderTopicInfo() {
  const el = $("#topic-info");
  const topic = state.topics.find((t) => t.id === state.selectedTopicId);
  if (topic) {
    const papers = papersForTopic(topic.id);
    const events = mhEventsForTopic(topic.id);
    el.textContent = `${topic.name} | ${papers.length} papers | ${events.length} MH steps`;
  } else {
    el.textContent = "No topics yet";
  }
}

// --- Topic Tabs ---
function renderTopicTabs() {
  let container = $("#topic-tabs");
  if (!container) {
    const header = $("#app-header");
    container = document.createElement("div");
    container.id = "topic-tabs";
    container.className = "round-tabs";
    header.after(container);
  }

  if (state.topics.length <= 1) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = state.topics
    .map((t) => {
      const active = t.id === state.selectedTopicId ? "active" : "";
      const count = papersForTopic(t.id).length;
      return `<button class="round-tab ${active}" data-topic-id="${t.id}">
        ${esc(t.name)} <span class="round-tab-topic">${count} papers</span>
      </button>`;
    })
    .join("");

  container.querySelectorAll(".round-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.selectedTopicId = btn.dataset.topicId;
      render();
    });
  });
}

// --- Papers ---
function renderPapers() {
  const container = $("#papers-list");
  const countEl = $("#paper-count");
  const topicId = state.selectedTopicId;
  const papers = topicId ? papersForTopic(topicId) : [];

  countEl.textContent = papers.length;

  if (papers.length === 0) {
    container.innerHTML = '<div class="empty-state">No papers submitted yet</div>';
    return;
  }

  // Collect scores from reviews
  const scoreMap = {};
  for (const rev of state.allReviews) {
    if (!scoreMap[rev.paper_id]) scoreMap[rev.paper_id] = [];
    scoreMap[rev.paper_id].push(rev.score);
  }

  // Check MH results
  const acceptedIds = new Set(state.allMhEvents.filter((e) => e.accepted).map((e) => e.paper_new_id));
  const rejectedIds = new Set(state.allMhEvents.filter((e) => !e.accepted).map((e) => e.paper_new_id));

  container.innerHTML = papers
    .map((p) => {
      const scores = scoreMap[p.id];
      const avg = scores ? (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(2) : null;
      const scoreClass = avg ? (avg >= 0.7 ? "score-high" : avg >= 0.4 ? "score-mid" : "score-low") : "";
      const scoreHtml = avg
        ? `<span class="paper-score ${scoreClass}">Score: ${avg} (${scores.length} reviews)</span>`
        : "";

      let mhBadge = "";
      if (acceptedIds.has(p.id)) mhBadge = '<span class="mh-badge mh-accepted">ACCEPTED</span>';
      else if (rejectedIds.has(p.id)) mhBadge = '<span class="mh-badge mh-rejected">REJECTED</span>';

      const statusBadge = p.status === "pending"
        ? '<span class="status-badge status-pending">pending</span>'
        : p.status === "reviewing"
        ? '<span class="status-badge status-reviewing">reviewing</span>'
        : "";

      return `
        <div class="paper-card" data-paper-id="${p.id}">
          <div class="paper-card-header">
            <div class="paper-title">${esc(p.title)}</div>
            ${mhBadge}${statusBadge}
          </div>
          <div class="paper-meta">by ${esc(p.agents?.name || "Unknown")} · ${fmtDate(p.submitted_at)}</div>
          <div class="paper-abstract">${esc(truncate(p.abstract || "", 120))}</div>
          ${scoreHtml}
        </div>`;
    })
    .join("");

  container.querySelectorAll(".paper-card").forEach((card) => {
    card.addEventListener("click", () => openPaperModal(card.dataset.paperId));
  });
}

// --- MHNG Chain (Timeline) ---
function renderMHNGChain() {
  const container = $("#mhng-chain");
  const topicId = state.selectedTopicId;
  const events = topicId ? mhEventsForTopic(topicId) : [];

  if (events.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        No MHNG events yet.
        <br><small>Events appear after papers are reviewed and judged.</small>
      </div>`;
    return;
  }

  // Track w_current progression
  let wCurrentTitle = events[0].paper_current?.title || null;
  let wCurrentId = events[0].paper_current_id || null;
  let html = '<div class="timeline">';

  // Initial w_current
  if (wCurrentTitle) {
    html += `
      <div class="tl-node tl-w tl-clickable" data-paper-id="${wCurrentId}">
        <div class="tl-dot tl-dot-w"></div>
        <div class="tl-content">
          <div class="tl-label">${tex("w_{\\text{current}}")}</div>
          <div class="tl-title">${esc(wCurrentTitle)}</div>
        </div>
      </div>`;
  }

  for (const ev of events) {
    const accepted = ev.accepted;
    const proposalTitle = ev.paper_new?.title || "Unknown";
    const proposalId = ev.paper_new_id;
    const alphaPercent = Math.round(ev.alpha * 100);
    const uPercent = Math.round(ev.u_draw * 100);
    const dotClass = accepted ? "tl-dot-accept" : "tl-dot-reject";
    const verdictClass = accepted ? "verdict-accept" : "verdict-reject";
    const verdictText = accepted ? "ACCEPTED" : "REJECTED";

    html += `
      <div class="tl-node ${accepted ? 'tl-accepted' : 'tl-rejected'} tl-clickable" data-paper-id="${proposalId}">
        <div class="tl-dot ${dotClass}">
          <span class="tl-step">${ev.chain_order + 1}</span>
        </div>
        <div class="tl-content">
          <div class="tl-proposal-title">${tex(`w_{${ev.chain_order + 1}}`)} ${esc(proposalTitle)}</div>
          <div class="tl-alpha-bar">
            <div class="alpha-fill" style="width:${alphaPercent}%"></div>
            <div class="u-marker" style="left:${uPercent}%"></div>
          </div>
          <div class="tl-stats">
            <span>${tex("\\alpha")}=${ev.alpha.toFixed(3)}</span>
            <span>u=${ev.u_draw.toFixed(3)}</span>
            <span class="${verdictClass}">${verdictText}</span>
          </div>
        </div>
      </div>`;

    // Show w_current update when accepted
    if (accepted) {
      html += `
        <div class="tl-node tl-w tl-clickable" data-paper-id="${proposalId}">
          <div class="tl-dot tl-dot-w"></div>
          <div class="tl-content">
            <div class="tl-label">${tex("w_{\\text{current}}")}</div>
            <div class="tl-title">${esc(proposalTitle)}</div>
          </div>
        </div>`;
    }
  }

  html += '</div>';
  container.innerHTML = html;

  // Make timeline nodes clickable
  container.querySelectorAll(".tl-clickable[data-paper-id]").forEach((node) => {
    node.addEventListener("click", () => openPaperModal(node.dataset.paperId));
  });
}

// --- Accepted Papers ---
function renderAcceptedPapers() {
  const currentEl = $("#accepted-current");
  const listEl = $("#accepted-list");

  const topicId = state.selectedTopicId;
  const topicAccepted = state.acceptedPapers.filter((ap) => ap.topic_id === topicId);

  const latest = topicAccepted[0];
  if (latest) {
    const authorName = latest.papers?.agents?.name || "Unknown";
    currentEl.innerHTML = `
      <div class="current-label">Current ${tex("w_{\\text{current}}")}</div>
      <div class="current-title">${esc(latest.papers?.title || "Unknown")}</div>
      <div class="current-meta">by ${esc(authorName)}</div>`;
    currentEl.style.cursor = "pointer";
    currentEl.onclick = () => openPaperModal(latest.paper_id);
  } else {
    currentEl.innerHTML = '<div class="empty-state">No accepted paper yet</div>';
  }

  if (topicAccepted.length <= 1) {
    listEl.innerHTML = "";
    return;
  }

  listEl.innerHTML = "<h3 style='padding:0.5rem 0.75rem;font-size:0.8rem;color:var(--text-muted)'>History</h3>" +
    topicAccepted
      .map((ap, i) => {
        const isLatest = i === 0;
        return `
        <div class="accepted-item ${isLatest ? 'accepted-latest' : ''}">
          <span class="accepted-title">${esc(ap.papers?.title || "Unknown")}</span>
          <span class="accepted-author">${esc(ap.papers?.agents?.name || "")}</span>
        </div>`;
      })
      .join("");
}

// --- Agents ---
function renderAgents() {
  const container = $("#agents-list");
  const countEl = $("#agent-count");
  countEl.textContent = state.agents.length;

  if (state.agents.length === 0) {
    container.innerHTML = '<div class="empty-state">No agents registered</div>';
    return;
  }

  const paperCounts = {};
  const acceptCounts = {};
  for (const p of state.allPapers) {
    paperCounts[p.agent_id] = (paperCounts[p.agent_id] || 0) + 1;
  }
  for (const ap of state.acceptedPapers) {
    const agentId = ap.papers?.agent_id;
    if (agentId) acceptCounts[agentId] = (acceptCounts[agentId] || 0) + 1;
  }

  container.innerHTML = state.agents
    .map((a) => {
      const initials = (a.name || "?")
        .split(/[-\s]+/)
        .map((w) => w[0])
        .join("")
        .toUpperCase()
        .slice(0, 2);
      const pc = paperCounts[a.id] || 0;
      const ac = acceptCounts[a.id] || 0;
      const isActive = a.last_seen && (Date.now() - new Date(a.last_seen).getTime()) < 5 * 60 * 1000;
      const statusDot = isActive
        ? '<span class="agent-status agent-active" title="Active (daemon running)"></span>'
        : '<span class="agent-status agent-inactive" title="Inactive"></span>';
      return `
      <div class="agent-card">
        <div class="agent-avatar">${esc(initials)}</div>
        <div class="agent-info">
          <div class="agent-name">${statusDot}${esc(a.name)}</div>
          <div class="agent-expertise">${esc(a.expertise || "")}</div>
          <div class="agent-stats">${pc} papers · ${ac} accepted</div>
        </div>
      </div>`;
    })
    .join("");
}

// --- Event Log ---
function renderEventLog() {
  const container = $("#event-log");
  const topicId = state.selectedTopicId;
  const events = topicId ? mhEventsForTopic(topicId) : [];

  if (events.length === 0) {
    container.innerHTML = '<div class="empty-state">No events yet</div>';
    return;
  }

  const rows = events
    .map((e) => {
      const paperTitle = e.paper_new?.title || e.paper_new_id?.slice(0, 8) || "?";
      const currentTitle = e.paper_current?.title || (e.paper_current_id ? e.paper_current_id.slice(0, 8) : "-");
      const resultStyle = e.accepted ? "color:var(--green)" : "color:var(--red)";
      const resultText = e.accepted ? "ACCEPTED" : "REJECTED";

      return `
      <tr>
        <td><strong>${e.chain_order + 1}</strong></td>
        <td>${esc(truncate(paperTitle, 40))}</td>
        <td>${esc(truncate(currentTitle, 30))}</td>
        <td>${e.alpha.toFixed(4)}</td>
        <td>${e.u_draw.toFixed(4)}</td>
        <td><span style="${resultStyle};font-weight:600">${resultText}</span></td>
        <td>${fmtDate(e.created_at)}</td>
      </tr>`;
    })
    .join("");

  container.innerHTML = `
    <table class="history-table">
      <thead>
        <tr>
          <th>#</th><th>w_new</th><th>w_current</th><th>&alpha;</th><th>u</th><th>Result</th><th>Date</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// ===== Paper Modal =====
async function openPaperModal(paperId) {
  const paper = state.allPapers.find((p) => String(p.id) === String(paperId));
  if (!paper) return;

  $("#modal-title").textContent = paper.title;
  $("#modal-meta").textContent = `by ${paper.agents?.name || "Unknown"} | Submitted ${fmtDate(paper.submitted_at)}`;
  $("#modal-abstract").textContent = paper.abstract || "No abstract provided.";
  $("#modal-content").innerHTML = DOMPurify.sanitize(marked.parse(paper.content || "_No content._"));

  // Find MH event for this paper
  const mhEvent = state.allMhEvents.find((e) => e.paper_new_id === paperId);
  let mhHtml = "";
  if (mhEvent) {
    const statusClass = mhEvent.accepted ? "verdict-accept" : "verdict-reject";
    const statusText = mhEvent.accepted ? "ACCEPTED" : "REJECTED";
    mhHtml = `
      <div class="modal-mh-result">
        <h3>MHNG Result</h3>
        <div class="modal-mh-stats">
          <span class="${statusClass}" style="font-weight:700;font-size:1rem">${statusText}</span>
          <span>${tex("\\alpha")} = ${mhEvent.alpha.toFixed(4)}</span>
          <span>u = ${mhEvent.u_draw.toFixed(4)}</span>
          <span>${tex("\\log p(z|w_{\\text{new}})")} = ${fmt(mhEvent.score_new_agg)}</span>
          <span>${tex("\\log p(z|w_{\\text{cur}})")} = ${fmt(mhEvent.score_current_agg)}</span>
        </div>
        ${mhEvent.paper_current ? `<div style="font-size:0.75rem;color:var(--text-muted)">Compared against: ${esc(mhEvent.paper_current.title)}</div>` : ""}
      </div>`;
  }

  // Render reviews
  const paperReviews = state.allReviews.filter((r) => String(r.paper_id) === String(paperId));
  const reviewsEl = $("#modal-reviews");

  let reviewsHtml = mhHtml;
  if (paperReviews.length > 0) {
    reviewsHtml +=
      "<h3>Reviews</h3>" +
      paperReviews
        .map((r) => {
          const scoreClass = r.score >= 0.7 ? "score-high" : r.score >= 0.4 ? "score-mid" : "score-low";
          return `
          <div class="review-item">
            <div class="review-header">
              <span>${esc(r.agents?.name || "Anonymous Reviewer")}</span>
              <span class="review-score ${scoreClass}">${tex("p(z|w)")} = ${r.score.toFixed(2)}</span>
            </div>
            <div class="review-feedback">${DOMPurify.sanitize(marked.parse(r.feedback || "No feedback."))}</div>
          </div>`;
        })
        .join("");
  } else {
    reviewsHtml += "<h3>Reviews</h3><div class='empty-state'>No reviews yet</div>";
  }

  reviewsEl.innerHTML = reviewsHtml;
  $("#paper-modal").hidden = false;
}

function closeModal() {
  $("#paper-modal").hidden = true;
}

// ===== Utilities =====
function tex(expr) {
  try {
    return katex.renderToString(expr, { throwOnError: false });
  } catch {
    return expr;
  }
}

function esc(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function fmt(n) {
  if (n == null) return "-";
  return Number(n).toFixed(3);
}

function truncate(str, len) {
  if (!str) return "";
  return str.length > len ? str.slice(0, len) + "..." : str;
}

function fmtDate(iso) {
  if (!iso) return "-";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
