marked.setOptions({ breaks: true, gfm: true });

const API = '';
let history = [];
let currentPapers = [];
let pendingPapers = null;
let isStreaming = false;
let sidebarOpen = true;
let papersOpen = false;
let papersGeneration = 0;  // increments each time new papers are rendered

document.getElementById('app').classList.add('papers-collapsed');

// ── Toggles ───────────────────────────────────────────────────────────────────
function toggleSidebar() {
  sidebarOpen = !sidebarOpen;
  document.getElementById('app').classList.toggle('sidebar-collapsed', !sidebarOpen);
}

function togglePapers() {
  papersOpen = !papersOpen;
  document.getElementById('app').classList.toggle('papers-collapsed', !papersOpen);
}

// ── Stats ─────────────────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const r = await fetch('/stats');
    const d = await r.json();
    if (d.total_papers)
      document.getElementById('paper-count').textContent = d.total_papers.toLocaleString();
  } catch {}
}
loadStats();

// ── Input helpers ─────────────────────────────────────────────────────────────
function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 140) + 'px';
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
}

function setInput(text) {
  const inp = document.getElementById('chat-input');
  inp.value = text;
  inp.focus();
  autoResize(inp);
}

// ── Clear ─────────────────────────────────────────────────────────────────────
function clearChat() {
  history = [];
  document.getElementById('chat-messages').innerHTML = `
    <div class="empty-state" id="empty-state">
      <div class="empty-icon">◎</div>
      <div class="empty-title">Search 288k AI papers</div>
      <div class="empty-sub">Ask anything — get grounded answers with real citations and links</div>
      <div class="suggestion-pills">
        <span class="suggestion-pill" onclick="setInput('Explain how attention mechanisms work')">Attention mechanisms</span>
        <span class="suggestion-pill" onclick="setInput('What is knowledge distillation?')">Knowledge distillation</span>
        <span class="suggestion-pill" onclick="setInput('Recent work on multimodal models')">Multimodal models</span>
      </div>
    </div>`;
  clearPapers();
}

function clearPapers() {
  currentPapers = [];
  pendingPapers = null;
  document.getElementById('papers-list').innerHTML =
    '<div class="papers-empty">Papers retrieved for each query will appear here</div>';
  document.getElementById('papers-count').textContent = '0';
  document.getElementById('recommend-section').style.display = 'none';
  papersOpen = false;
  document.getElementById('app').classList.add('papers-collapsed');
}

// ── Chat ──────────────────────────────────────────────────────────────────────
async function sendMessage() {
  const inp = document.getElementById('chat-input');
  const msg = inp.value.trim();
  if (!msg || isStreaming) return;

  document.getElementById('empty-state')?.remove();

  inp.value = '';
  inp.style.height = 'auto';
  isStreaming = true;
  document.getElementById('send-btn').disabled = true;

  const container = document.getElementById('chat-messages');

  container.insertAdjacentHTML('beforeend', `
    <div class="msg user">
      <div class="avatar user">you</div>
      <div class="bubble user">${escapeHtml(msg)}</div>
    </div>`);

  const typingId = 'typing-' + Date.now();
  container.insertAdjacentHTML('beforeend', `
    <div class="msg" id="${typingId}">
      <div class="avatar ai">ai</div>
      <div class="bubble ai">
        <div class="typing-indicator">
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
          <span class="typing-dot"></span>
        </div>
      </div>
    </div>`);
  scrollBottom();

  const filters = getFilters();

  try {
    const resp = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: msg,
        history: history.slice(-10),
        category: filters.category,
        after: filters.after,
        k: filters.k,
      })
    });

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let sseBuffer = '';
    let replyText = '';
    let bubbleEl = null;

    // ── Append-only streaming ─────────────────────────────────────────────────
    // Strategy: never replace existing DOM. Split incoming text on paragraph
    // boundaries (\n\n). Completed paragraphs are rendered as markdown and
    // appended once. The in-progress paragraph is a single live text node
    // at the tail — only its value changes, so nothing above it ever reflows.

    let renderedUpTo = 0;   // char index of text already turned into HTML nodes
    let tailNode = null;    // text node for the currently-streaming paragraph
    let rafPending = false;

    function flushTail() {
      if (!bubbleEl) return;

      const unrendered = replyText.slice(renderedUpTo);

      // Find the last complete paragraph boundary in unrendered text
      const lastBreak = unrendered.lastIndexOf('\n\n');

      if (lastBreak !== -1) {
        // Render everything up to (and including) the last \n\n as markdown
        const toRender = unrendered.slice(0, lastBreak + 2);
        renderedUpTo += toRender.length;

        // Remove tail node before inserting rendered HTML
        if (tailNode && tailNode.parentNode) tailNode.parentNode.removeChild(tailNode);
        tailNode = null;

        const tmp = document.createElement('div');
        tmp.innerHTML = renderMarkdown(toRender);
        bindCitationEvents(tmp, papersGeneration);
        while (tmp.firstChild) bubbleEl.appendChild(tmp.firstChild);
      }

      // Everything after the last paragraph break goes into the live tail node
      const tail = replyText.slice(renderedUpTo);
      if (tail) {
        if (!tailNode) {
          tailNode = document.createTextNode('');
          bubbleEl.appendChild(tailNode);
        }
        tailNode.nodeValue = tail;
      }
    }

    function scheduleFlush() {
      if (rafPending) return;
      rafPending = true;
      requestAnimationFrame(() => {
        rafPending = false;
        flushTail();
        scrollBottom();
      });
    }

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      sseBuffer += decoder.decode(value, { stream: true });
      const lines = sseBuffer.split('\n');
      sseBuffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const ev = JSON.parse(line.slice(6));

          if (ev.type === 'papers') {
            pendingPapers = ev.papers;
          }

          if (ev.type === 'token') {
            if (!bubbleEl) {
              document.getElementById(typingId)?.remove();
              container.insertAdjacentHTML('beforeend', `
                <div class="msg">
                  <div class="avatar ai">ai</div>
                  <div class="bubble ai streaming" id="streaming-bubble"></div>
                </div>`);
              bubbleEl = document.getElementById('streaming-bubble');
            }
            replyText += ev.text;
            scheduleFlush();
          }

          if (ev.type === 'done') {
            // Render papers first so currentPapers is populated before citation chips are built
            if (pendingPapers) {
              renderPapers(pendingPapers);
              pendingPapers = null;
            }
            // Capture the generation ID for this response
            const bubbleGen = papersGeneration;
            if (bubbleEl) {
              bubbleEl.classList.remove('streaming');
              bubbleEl.innerHTML = renderMarkdown(replyText);
              bindCitationEvents(bubbleEl, bubbleGen);
              bubbleEl.removeAttribute('id');
            }
            history.push({ role: 'user', content: msg });
            history.push({ role: 'assistant', content: replyText });
            scrollBottom();
          }
        } catch {}
      }
    }
  } catch (e) {
    document.getElementById(typingId)?.remove();
    container.insertAdjacentHTML('beforeend', `
      <div class="msg">
        <div class="avatar ai">ai</div>
        <div class="bubble ai" style="color:var(--red)">Error: ${escapeHtml(String(e))}</div>
      </div>`);
  }

  isStreaming = false;
  document.getElementById('send-btn').disabled = false;
  scrollBottom();
}

// ── Citation rendering ───────────────────────────────────────────────────────
// Parse markdown first, then replace [N] in the resulting HTML string,
// then attach hover listeners to the injected chips.

const CIT_RE = /\[(\d+(?:,\s*\d+)*)\]/g;

function renderMarkdown(text) {
  let html = marked.parse(text);
  if (!currentPapers.length) return html;

  // Replace [N] / [1, 2] in the HTML output with chip markup
  html = html.replace(CIT_RE, (match, nums) => {
    const indices = nums.split(',').map(s => parseInt(s.trim()) - 1);
    return indices.map(idx => {
      const paper = currentPapers[idx];
      if (!paper) return match;
      const shortTitle = paper.title.length > 48
        ? paper.title.slice(0, 46).trimEnd() + '…'
        : paper.title;
      return `<a class="citation-chip" data-paper-idx="${idx}" href="${paper.abs_url || '#'}" target="_blank" title="${escapeHtml(paper.title)}">`
        + `<span class="citation-num">${idx + 1}</span>`
        + `</a>`;
    }).join(' ');
  });

  return html;
}

// After setting innerHTML, bind hover events on all chips inside el.
// gen = papersGeneration value at the time this bubble was finalized.
// Hover/scroll only activates if that generation is still the current one.
function bindCitationEvents(el, gen) {
  el.querySelectorAll('.citation-chip').forEach(chip => {
    const idx = parseInt(chip.dataset.paperIdx);

    chip.addEventListener('mouseenter', () => setPaperHover(idx, true, gen));
    chip.addEventListener('mouseleave', () => setPaperHover(idx, false, gen));
    chip.addEventListener('click', (e) => {
      e.preventDefault();
      if (gen === papersGeneration) scrollToCard(idx);
      const paper = currentPapers[idx];
      if (paper?.abs_url) window.open(paper.abs_url, '_blank');
    });
  });
}

function bindCardHover(card, idx) {
  card.addEventListener('mouseenter', () => setCitationHover(idx, true));
  card.addEventListener('mouseleave', () => setCitationHover(idx, false));
}

function setPaperHover(idx, on, gen) {
  // Only highlight if this bubble's papers are still the ones currently displayed
  if (gen !== papersGeneration) return;
  const card = document.querySelector(`#papers-list .paper-card[data-index="${idx}"]`);
  if (!card) return;
  card.classList.toggle('hovered', on);
  if (on) {
    if (!papersOpen) {
      papersOpen = true;
      document.getElementById('app').classList.remove('papers-collapsed');
    }
    const list = document.getElementById('papers-list');
    const listRect = list.getBoundingClientRect();
    const cardRect = card.getBoundingClientRect();
    if (cardRect.bottom > listRect.bottom || cardRect.top < listRect.top) {
      card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }
}

function setCitationHover(idx, on) {
  document.querySelectorAll(`.citation-chip[data-paper-idx="${idx}"]`)
    .forEach(chip => chip.classList.toggle('hovered', on));
}

function scrollToCard(idx) {
  if (!papersOpen) {
    papersOpen = true;
    document.getElementById('app').classList.remove('papers-collapsed');
  }
  setTimeout(() => {
    const card = document.querySelector(`#papers-list .paper-card[data-index="${idx}"]`);
    if (card) card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, papersOpen ? 0 : 380);
}

// ── Papers ────────────────────────────────────────────────────────────────────
function renderPapers(papers) {
  currentPapers = papers;
  papersGeneration++;
  const list = document.getElementById('papers-list');
  document.getElementById('papers-count').textContent = papers.length;

  list.innerHTML = papers.map((p, i) => {
    const score = p.score || 0;
    const sc = score >= 0.85 ? 's-high' : score >= 0.70 ? 's-mid' : 's-low';
    const date = (p.published || '').slice(0, 10);
    const cat  = p.primary_category || '';
    const abs  = (p.abstract || '').slice(0, 500);
    return `
      <div class="paper-card animating" onclick="toggleAbstract(this)" data-index="${i}">
        <div class="paper-index">${i + 1}</div>
        <div class="paper-body">
          <div class="paper-title">
            <a href="${p.abs_url || '#'}" target="_blank" onclick="event.stopPropagation()">${escapeHtml(p.title)}</a>
          </div>
          <div class="paper-meta">
            <span class="paper-tag">${cat}</span>
            <span class="paper-date">${date}</span>
            <span class="paper-score ${sc}">${score.toFixed(2)}</span>
          </div>
          <div class="paper-abstract">
            <p>${escapeHtml(abs)}...</p>
            <div class="paper-links">
              <a class="paper-link" href="${p.abs_url || '#'}" target="_blank">abstract</a>
              ${p.pdf_url ? `<a class="paper-link" href="${p.pdf_url}" target="_blank">PDF</a>` : ''}
            </div>
          </div>
        </div>
      </div>`;
  }).join('');

  const sel = document.getElementById('recommend-select');
  sel.innerHTML = papers.map((p, i) =>
    `<option value="${i}">${p.title.slice(0, 60)}...</option>`
  ).join('');
  document.getElementById('recommend-section').style.display = 'block';

  if (!papersOpen) {
    papersOpen = true;
    document.getElementById('app').classList.remove('papers-collapsed');
  }

  list.querySelectorAll('.paper-card.animating').forEach((card, i) => {
    card.style.animationDelay = `${i * 120}ms`;
  });

  // Bind hover for citation ↔ card cross-highlight
  list.querySelectorAll('.paper-card').forEach((card) => {
    const idx = parseInt(card.dataset.index);
    bindCardHover(card, idx);
  });
}

function toggleAbstract(el) { el.classList.toggle('open'); }

// ── Recommendations ───────────────────────────────────────────────────────────
function getRecommendations() {
  const idx = parseInt(document.getElementById('recommend-select').value);
  const paper = currentPapers[idx];
  if (!paper) return;

  // Send as a new chat message — triggers full RAG pipeline naturally
  const query = `Find papers similar to: "${paper.title}"`;
  setInput(query);
  sendMessage();
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function getFilters() {
  return {
    category: document.getElementById('filter-category').value || null,
    after:    null,
    k: parseInt(document.getElementById('filter-k').value),
  };
}

function scrollBottom() {
  const c = document.getElementById('chat-messages');
  c.scrollTop = c.scrollHeight;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}