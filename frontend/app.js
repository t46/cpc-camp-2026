// ===== Supabase Configuration =====
// Set these to your Supabase project values
const SUPABASE_URL = "YOUR_SUPABASE_URL";
const SUPABASE_ANON_KEY = "YOUR_SUPABASE_ANON_KEY";

const { createClient } = window.supabase;
const sb = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
console.log("Supabase client initialized:", sb);

// ===== State =====
let state = {
  agents: [],
  rounds: [],
  selectedRoundId: null,
  allPapers: [],
  allReviews: [],
  allMhEvents: [],
  acceptedPapers: [],
};

const PHASE_ORDER = ["submission", "review", "judgment", "completed"];

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

  // About modal
  $("#about-btn").addEventListener("click", () => { $("#about-modal").hidden = false; });
  $("#about-close").addEventListener("click", () => { $("#about-modal").hidden = true; });
  $("#about-modal").addEventListener("click", (e) => {
    if (e.target === $("#about-modal")) $("#about-modal").hidden = true;
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { closeModal(); $("#about-modal").hidden = true; }
  });
});

// ===== Data Fetching =====
async function fetchAll() {
  try {
    // Fetch each independently to isolate errors
    const results = {};

    const agentsRes = await sb.from("agents").select("*").order("created_at");
    if (agentsRes.error) console.error("agents error:", agentsRes.error);
    results.agents = agentsRes.data || [];

    const roundsRes = await sb.from("rounds").select("*,topics(name,description)").order("id", { ascending: false });
    if (roundsRes.error) console.error("rounds error:", roundsRes.error);
    results.rounds = roundsRes.data || [];

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
    state.rounds = results.rounds;
    state.allPapers = results.allPapers;
    state.allReviews = results.allReviews;
    state.allMhEvents = results.allMhEvents;
    state.acceptedPapers = results.acceptedPapers;

    console.log("Fetched state:", {
      agents: state.agents.length,
      rounds: state.rounds.length,
      papers: state.allPapers.length,
      reviews: state.allReviews.length,
      mhEvents: state.allMhEvents.length,
      accepted: state.acceptedPapers.length,
    });

    // Auto-select latest round if none selected
    if (!state.selectedRoundId && state.rounds.length > 0) {
      state.selectedRoundId = state.rounds[0].id;
    }

    render();
  } catch (err) {
    console.error("Fetch error:", err);
    document.getElementById("round-info").textContent = "Error: " + err.message;
  }
}

// ===== Helpers =====
function selectedRound() {
  return state.rounds.find((r) => r.id === state.selectedRoundId);
}
function papersForRound(roundId) {
  return state.allPapers.filter((p) => p.round_id === roundId);
}
function reviewsForRound(roundId) {
  return state.allReviews.filter((r) => r.round_id === roundId);
}
function mhEventsForRound(roundId) {
  return state.allMhEvents.filter((e) => e.round_id === roundId);
}

// ===== Render =====
function render() {
  renderRoundInfo();
  renderPhasePipeline();
  renderRoundTabs();
  renderPapers();
  renderMHNGChain();
  renderAcceptedPapers();
  renderAgents();
  renderRoundHistory();
}

// --- Round Info ---
function renderRoundInfo() {
  const el = $("#round-info");
  const r = selectedRound();
  if (r) {
    const topicName = r.topics?.name || "Unknown Topic";
    el.textContent = `Round #${r.id} | ${topicName} | Phase: ${r.phase}`;
  } else {
    el.textContent = "No rounds yet";
  }
}

// --- Phase Pipeline ---
function renderPhasePipeline() {
  const phase = selectedRound()?.phase || "";
  const phaseIdx = PHASE_ORDER.indexOf(phase);
  const nodes = $$(".phase-node");
  const connectors = $$(".phase-connector");

  nodes.forEach((node, i) => {
    node.classList.remove("active", "done");
    if (i < phaseIdx) node.classList.add("done");
    else if (i === phaseIdx) node.classList.add("active");
  });

  connectors.forEach((conn, i) => {
    conn.classList.remove("done");
    if (i < phaseIdx) conn.classList.add("done");
  });
}

// --- Round Tabs ---
function renderRoundTabs() {
  let container = $("#round-tabs");
  if (!container) {
    // Create round tabs before dashboard
    const pipeline = $("#phase-pipeline");
    container = document.createElement("div");
    container.id = "round-tabs";
    container.className = "round-tabs";
    pipeline.after(container);
  }

  container.innerHTML = state.rounds
    .map((r) => {
      const active = r.id === state.selectedRoundId ? "active" : "";
      const topicName = r.topics?.name || "";
      return `<button class="round-tab ${active}" data-round-id="${r.id}">
        Round ${r.id} <span class="round-tab-topic">${esc(topicName)}</span>
        <span class="round-tab-phase">${r.phase}</span>
      </button>`;
    })
    .join("");

  container.querySelectorAll(".round-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.selectedRoundId = Number(btn.dataset.roundId);
      render();
    });
  });
}

// --- Papers ---
function renderPapers() {
  const container = $("#papers-list");
  const countEl = $("#paper-count");
  const roundId = state.selectedRoundId;
  const papers = roundId ? papersForRound(roundId) : [];
  const reviews = roundId ? reviewsForRound(roundId) : [];

  countEl.textContent = papers.length;

  if (papers.length === 0) {
    container.innerHTML = '<div class="empty-state">No papers submitted yet</div>';
    return;
  }

  // Collect average scores from reviews
  const scoreMap = {};
  for (const rev of reviews) {
    if (!scoreMap[rev.paper_id]) scoreMap[rev.paper_id] = [];
    scoreMap[rev.paper_id].push(rev.score);
  }

  // Check which paper is the MH result for this round
  const events = roundId ? mhEventsForRound(roundId) : [];
  const acceptedIds = new Set(events.filter((e) => e.accepted).map((e) => e.paper_new_id));
  const rejectedIds = new Set(events.filter((e) => !e.accepted).map((e) => e.paper_new_id));

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

      return `
        <div class="paper-card" data-paper-id="${p.id}">
          <div class="paper-card-header">
            <div class="paper-title">${esc(p.title)}</div>
            ${mhBadge}
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

// --- MHNG Chain ---
function renderMHNGChain() {
  const container = $("#mhng-chain");
  const roundId = state.selectedRoundId;
  const events = roundId ? mhEventsForRound(roundId) : [];

  if (events.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div style="font-size:1.5rem;margin-bottom:0.5rem;">⛓</div>
        No MHNG events yet for this round.
        <br><small>Events appear after the judgment phase.</small>
      </div>`;
    return;
  }

  // Build the chain visualization
  let chainHtml = '<div class="chain-container">';

  // Show w_current at the start
  const firstEvent = events[0];
  if (firstEvent.paper_current) {
    chainHtml += `
      <div class="chain-start">
        <div class="chain-start-label">w_current (before)</div>
        <div class="chain-start-title">${esc(firstEvent.paper_current.title)}</div>
      </div>
      <div class="chain-arrow">→</div>`;
  } else {
    chainHtml += `
      <div class="chain-start">
        <div class="chain-start-label">Start</div>
        <div class="chain-start-title">No prior w_current</div>
      </div>
      <div class="chain-arrow">→</div>`;
  }

  for (const ev of events) {
    const accepted = ev.accepted;
    const statusClass = accepted ? "accepted" : "rejected";
    const verdictClass = accepted ? "verdict-accept" : "verdict-reject";
    const verdictText = accepted ? "✓ ACCEPTED" : "✗ REJECTED";
    const proposalTitle = ev.paper_new?.title || "Unknown";

    // Calculate the ratio visually
    const alphaPercent = Math.round(ev.alpha * 100);
    const uPercent = Math.round(ev.u_draw * 100);

    chainHtml += `
      <div class="chain-event ${statusClass}">
        <div class="chain-order-badge">#${ev.chain_order + 1}</div>
        <div class="chain-title" title="${esc(proposalTitle)}">${esc(truncate(proposalTitle, 40))}</div>
        <div class="chain-alpha-bar">
          <div class="alpha-fill" style="width:${alphaPercent}%"></div>
          <div class="u-marker" style="left:${uPercent}%"></div>
          <div class="alpha-label">α=${ev.alpha.toFixed(3)} | u=${ev.u_draw.toFixed(3)}</div>
        </div>
        <div class="chain-scores">
          <span>log p(z|w_new)=${fmt(ev.score_new_agg)}</span>
          <span>log p(z|w_cur)=${fmt(ev.score_current_agg)}</span>
        </div>
        <div class="chain-verdict ${verdictClass}">${verdictText}</div>
      </div>`;

    if (events.indexOf(ev) < events.length - 1) {
      chainHtml += '<div class="chain-arrow">→</div>';
    }
  }

  // Show final w_current
  const lastAccepted = [...events].reverse().find((e) => e.accepted);
  const finalTitle = lastAccepted ? lastAccepted.paper_new?.title : firstEvent.paper_current?.title;
  chainHtml += `
    <div class="chain-arrow">→</div>
    <div class="chain-end">
      <div class="chain-end-label">w_current (after)</div>
      <div class="chain-end-title">${esc(finalTitle || "No change")}</div>
    </div>`;

  chainHtml += "</div>";
  container.innerHTML = chainHtml;
}

// --- Accepted Papers ---
function renderAcceptedPapers() {
  const currentEl = $("#accepted-current");
  const listEl = $("#accepted-list");

  const latest = state.acceptedPapers[0];
  if (latest) {
    const authorName = latest.papers?.agents?.name || "Unknown";
    currentEl.innerHTML = `
      <div class="current-label">Current w_current (Global Scientific Representation)</div>
      <div class="current-title">${esc(latest.papers?.title || "Unknown")}</div>
      <div class="current-meta">by ${esc(authorName)} · Accepted in Round ${latest.round_id}</div>`;
  } else {
    currentEl.innerHTML = '<div class="empty-state">No accepted paper yet</div>';
  }

  if (state.acceptedPapers.length === 0) {
    listEl.innerHTML = "";
    return;
  }

  listEl.innerHTML = "<h3 style='padding:0.5rem 0.75rem;font-size:0.8rem;color:var(--text-muted)'>History of w_current</h3>" +
    state.acceptedPapers
      .map((ap) => {
        const isLatest = ap === latest;
        return `
        <div class="accepted-item ${isLatest ? 'accepted-latest' : ''}">
          <span class="accepted-round">R${ap.round_id}</span>
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

  // Count papers and accepted papers per agent
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
      return `
      <div class="agent-card">
        <div class="agent-avatar">${esc(initials)}</div>
        <div class="agent-info">
          <div class="agent-name">${esc(a.name)}</div>
          <div class="agent-expertise">${esc(a.expertise || "")}</div>
          <div class="agent-stats">${pc} papers · ${ac} accepted</div>
        </div>
      </div>`;
    })
    .join("");
}

// --- Round History ---
function renderRoundHistory() {
  const container = $("#round-history");

  if (state.rounds.length === 0) {
    container.innerHTML = '<div class="empty-state">No rounds yet</div>';
    return;
  }

  const acceptedMap = {};
  for (const ap of state.acceptedPapers) {
    if (!acceptedMap[ap.round_id]) {
      acceptedMap[ap.round_id] = ap;
    }
  }

  // Count papers and events per round
  const rows = state.rounds
    .map((r) => {
      const ap = acceptedMap[r.id];
      const paperTitle = ap?.papers?.title || "-";
      const topicName = r.topics?.name || "-";
      const paperCount = papersForRound(r.id).length;
      const reviewCount = reviewsForRound(r.id).length;
      const eventCount = mhEventsForRound(r.id).length;
      const acceptCount = mhEventsForRound(r.id).filter((e) => e.accepted).length;
      const rejectCount = eventCount - acceptCount;

      const phaseColors = {
        submission: "var(--accent)",
        review: "var(--yellow)",
        judgment: "var(--purple)",
        completed: "var(--green)",
      };

      return `
      <tr class="${r.id === state.selectedRoundId ? 'history-selected' : ''}"
          style="cursor:pointer" data-round-id="${r.id}">
        <td><strong>${r.id}</strong></td>
        <td>${esc(topicName)}</td>
        <td><span style="color:${phaseColors[r.phase] || 'inherit'}">${r.phase}</span></td>
        <td>${paperCount}</td>
        <td>${reviewCount}</td>
        <td><span style="color:var(--green)">${acceptCount}✓</span> / <span style="color:var(--red)">${rejectCount}✗</span></td>
        <td>${esc(truncate(paperTitle, 40))}</td>
        <td>${fmtDate(r.completed_at)}</td>
      </tr>`;
    })
    .join("");

  container.innerHTML = `
    <table class="history-table">
      <thead>
        <tr>
          <th>Round</th><th>Topic</th><th>Phase</th><th>Papers</th><th>Reviews</th><th>MH Results</th><th>w_current</th><th>Completed</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;

  // Click row to select round
  container.querySelectorAll("tr[data-round-id]").forEach((row) => {
    row.addEventListener("click", () => {
      state.selectedRoundId = Number(row.dataset.roundId);
      render();
    });
  });
}

// ===== Paper Modal =====
async function openPaperModal(paperId) {
  const paper = state.allPapers.find((p) => String(p.id) === String(paperId));
  if (!paper) return;

  $("#modal-title").textContent = paper.title;
  $("#modal-meta").textContent = `by ${paper.agents?.name || "Unknown"} | Round ${paper.round_id} | Submitted ${fmtDate(paper.submitted_at)}`;
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
          <span>α = ${mhEvent.alpha.toFixed(4)}</span>
          <span>u = ${mhEvent.u_draw.toFixed(4)}</span>
          <span>log p(z|w_new) = ${fmt(mhEvent.score_new_agg)}</span>
          <span>log p(z|w_cur) = ${fmt(mhEvent.score_current_agg)}</span>
        </div>
        ${mhEvent.paper_current ? `<div style="font-size:0.75rem;color:var(--text-muted)">Compared against: ${esc(mhEvent.paper_current.title)}</div>` : ""}
      </div>`;
  }

  // Render reviews for this paper
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
              <span class="review-score ${scoreClass}">p(z|w) = ${r.score.toFixed(2)}</span>
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
