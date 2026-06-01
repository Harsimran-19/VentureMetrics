"""Single-file local chat UI for testing the research prototype."""

from __future__ import annotations

import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from venture_metrics_agent.app.config import DEFAULT_DB_PATH
from venture_metrics_agent.reasoning import ReasoningOptions, answer_question_reasoning


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Venture Metrics</title>
  <style>
    :root {
      --page: #fdfcfc;
      --surface: #fdfcfc;
      --surface-soft: #f8f7f7;
      --surface-card: #f1eeee;
      --surface-dark: #201d1d;
      --line: rgba(15, 0, 0, .12);
      --line-strong: #646262;
      --ink: #201d1d;
      --ink-deep: #0f0000;
      --body: #424245;
      --muted: #646262;
      --muted-2: #9a9898;
      --on-dark: #fdfcfc;
      --green: #30d158;
      --amber: #ff9f0a;
      --red: #ff3b30;
      --radius: 4px;
    }

    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body {
      margin: 0;
      background: var(--page);
      color: var(--ink);
      font-family: "Berkeley Mono", "IBM Plex Mono", "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      font-size: 16px;
      line-height: 1.5;
      letter-spacing: 0;
      overflow: hidden;
    }
    button, textarea, input { font: inherit; letter-spacing: 0; }
    button { cursor: pointer; }

    .app {
      height: 100vh;
      grid-template-columns: 280px minmax(520px, 1fr) 420px;
      display: grid;
      grid-template-rows: 100vh;
    }
    body.sources-hidden .app {
      grid-template-columns: 280px minmax(520px, 1fr);
    }
    body.sources-hidden .inspector {
      display: none;
    }

    .sidebar {
      border-right: 1px solid var(--line);
      background: var(--surface);
      display: flex;
      flex-direction: column;
      min-width: 0;
    }
    .brand {
      padding: 18px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-mark {
      width: 38px;
      height: 38px;
      border-radius: var(--radius);
      display: grid;
      place-items: center;
      border: 1px solid var(--line-strong);
      background: var(--surface-dark);
      color: var(--on-dark);
      font-weight: 800;
      font-size: 13px;
    }
    .brand-title { min-width: 0; }
    .brand-title strong {
      display: block;
      font-size: 16px;
      line-height: 1.5;
    }
    .brand-title span {
      display: block;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.6;
    }

    .sidebar-actions {
      padding: 14px 18px;
      border-bottom: 1px solid var(--line);
    }
    .sidebar-name {
      padding: 18px;
      border-bottom: 1px solid var(--line);
      font-size: 16px;
      line-height: 1.5;
      font-weight: 700;
    }
    .new-chat {
      width: 100%;
      height: 38px;
      border: 1px solid var(--ink);
      border-radius: var(--radius);
      background: var(--ink);
      color: var(--on-dark);
      font-weight: 500;
    }
    .new-chat:active { background: var(--ink-deep); }

    .status {
      padding: 18px;
      border-bottom: 1px solid var(--line);
    }
    .section-label {
      margin: 0 0 11px;
      color: var(--ink);
      font-size: 14px;
      font-weight: 700;
      line-height: 2;
      letter-spacing: 0;
      text-transform: none;
    }
    .metric-list {
      display: grid;
      gap: 8px;
    }
    .metric-row {
      min-height: 38px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      border: 1px solid var(--line);
      border-radius: 0;
      background: var(--surface);
      padding: 8px 10px;
    }
    .metric-row span {
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
    }
    .metric-row strong {
      font-size: 16px;
      line-height: 1.5;
    }
    .quick-list {
      padding: 18px;
      border-top: 1px solid var(--line);
      overflow: auto;
    }
    .quick-list button {
      width: 100%;
      text-align: left;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--surface);
      color: var(--body);
      padding: 10px;
      margin-top: 8px;
      font-size: 14px;
      line-height: 1.5;
    }
    .quick-list button:hover { border-color: var(--line-strong); color: var(--ink); }

    .chat-pane {
      min-width: 0;
      display: grid;
      grid-template-rows: auto minmax(0, 1fr) auto;
      background: var(--surface);
    }
    .chat-head {
      min-height: 66px;
      padding: 14px 22px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      background: var(--surface);
    }
    .chat-head h1 {
      margin: 0;
      font-size: 16px;
      line-height: 1.5;
      font-weight: 700;
    }
    .chat-head p {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.5;
    }
    .mode-pill {
      flex: 0 0 auto;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--surface-soft);
      color: var(--muted);
      padding: 7px 10px;
      font-size: 14px;
      font-weight: 500;
    }
    .chat-head p,
    .mode-pill {
      display: none;
    }

    .messages {
      min-height: 0;
      overflow: auto;
      padding: 22px;
      scroll-behavior: smooth;
    }
    .thread {
      max-width: 880px;
      margin: 0 auto;
      display: grid;
      gap: 20px;
    }
    .welcome {
      border: 1px solid var(--line);
      border-radius: 0;
      background: var(--surface-soft);
      padding: 12px 18px;
      line-height: 1.55;
    }
    .welcome strong { display: block; margin-bottom: 5px; }
    .welcome p { margin: 0; color: var(--muted); }

    .turn {
      display: grid;
      gap: 9px;
    }
    .turn.user {
      justify-items: end;
    }
    .turn-label {
      color: var(--muted-2);
      font-size: 14px;
      font-weight: 500;
    }
    .bubble {
      max-width: min(760px, 100%);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--surface);
      padding: 14px 15px;
      line-height: 1.58;
      overflow-wrap: anywhere;
    }
    .turn.user .bubble {
      background: var(--surface-soft);
      border-color: var(--line-strong);
      color: var(--ink);
    }
    .assistant-card {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--surface);
      overflow: hidden;
    }
    .assistant-card.selected {
      border-color: var(--line-strong);
    }
    .answer-head {
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      background: var(--surface-soft);
    }
    .badges {
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
    }
    .badge {
      min-height: 24px;
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 3px 9px;
      color: var(--muted);
      background: var(--surface);
      font-size: 14px;
      font-weight: 500;
    }
    .badge.high { color: #176b3a; border-color: rgba(23,107,58,.35); }
    .badge.medium { color: #7a4b00; border-color: rgba(255,159,10,.55); }
    .badge.low { color: #8a1f19; border-color: rgba(255,59,48,.45); }
    .answer-select {
      border: 1px solid var(--line);
      background: var(--surface);
      color: var(--muted);
      border-radius: var(--radius);
      padding: 5px 8px;
      font-size: 14px;
      font-weight: 500;
    }
    .answer-body {
      padding: 16px 16px 10px;
      line-height: 1.62;
    }
    .answer-body p { margin: 0 0 12px; }
    .answer-body p:last-child { margin-bottom: 0; }
    .answer-body ul {
      margin: 0 0 12px 20px;
      padding: 0;
    }
    .answer-body li { margin: 5px 0; }
    .answer-foot {
      padding: 0 16px 15px;
      display: grid;
      gap: 10px;
    }
    .source-strip {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 8px;
    }
    .source-chip {
      border: 1px solid var(--line);
      border-radius: 0;
      padding: 10px;
      text-decoration: none;
      color: inherit;
      background: var(--surface-soft);
      min-width: 0;
    }
    .source-chip:hover {
      border-color: var(--line-strong);
      background: var(--surface-card);
    }
    .source-chip strong {
      display: block;
      color: var(--ink);
      font-size: 14px;
      line-height: 1.3;
      overflow: hidden;
      text-overflow: ellipsis;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
    }
    .source-chip span {
      display: block;
      margin-top: 5px;
      color: var(--muted);
      font-size: 14px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    details.gaps {
      border-top: 1px solid var(--line);
      padding-top: 9px;
      color: var(--muted);
      font-size: 14px;
    }
    details.gaps summary {
      cursor: pointer;
      font-weight: 750;
      color: var(--body);
    }
    details.gaps ul { margin: 8px 0 0 18px; padding: 0; }

    .composer {
      border-top: 1px solid var(--line);
      background: var(--surface);
      padding: 14px 22px 18px;
    }
    .composer-inner {
      max-width: 880px;
      margin: 0 auto;
      border: 1px solid var(--line-strong);
      border-radius: var(--radius);
      background: var(--surface);
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      padding: 10px;
    }
    textarea {
      width: 100%;
      min-height: 48px;
      max-height: 150px;
      resize: none;
      border: 0;
      outline: 0;
      line-height: 1.45;
      padding: 5px 3px;
    }
    .send {
      align-self: end;
      min-width: 82px;
      height: 40px;
      border: 0;
      border-radius: var(--radius);
      background: var(--ink);
      color: var(--on-dark);
      font-weight: 500;
    }
    .send:hover { background: var(--ink-deep); }
    .send:disabled { opacity: .55; cursor: wait; }

    .inspector {
      border-left: 1px solid var(--line);
      background: var(--surface);
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      min-width: 0;
    }
    .inspector-head {
      padding: 18px;
      border-bottom: 1px solid var(--line);
    }
    .inspector-head h2 {
      margin: 0;
      font-size: 16px;
      line-height: 1.5;
    }
    .inspector-head p {
      margin: 5px 0 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.45;
    }
    .inspector-scroll {
      min-height: 0;
      overflow: auto;
      padding: 18px;
    }
    .panel-section {
      margin-bottom: 20px;
    }
    .panel-list {
      display: grid;
      gap: 9px;
    }
    .source-row, .evidence-row {
      border: 1px solid var(--line);
      border-radius: 0;
      background: var(--surface);
      padding: 12px;
    }
    .source-row a {
      display: block;
      color: var(--ink);
      text-decoration: none;
      font-weight: 800;
      line-height: 1.32;
    }
    .source-row a:hover { text-decoration: underline; }
    .meta {
      margin-top: 6px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.35;
    }
    .evidence-row strong {
      display: block;
      font-size: 14px;
      line-height: 1.3;
      margin-bottom: 6px;
    }
    .snippet {
      color: var(--body);
      font-size: 14px;
      line-height: 1.5;
    }
    .empty {
      border: 1px dashed var(--line-strong);
      border-radius: var(--radius);
      padding: 14px;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.45;
      background: var(--surface);
    }

    .typing {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      color: var(--muted);
    }
    .dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #98a2b3;
      animation: pulse 1.1s infinite ease-in-out;
    }
    .dot:nth-child(2) { animation-delay: .15s; }
    .dot:nth-child(3) { animation-delay: .3s; }
    @keyframes pulse {
      0%, 80%, 100% { opacity: .35; transform: translateY(0); }
      40% { opacity: 1; transform: translateY(-2px); }
    }

    @media (max-width: 1180px) {
      body { overflow: auto; }
      .app {
        min-height: 100vh;
        height: auto;
        grid-template-columns: 240px minmax(0, 1fr);
      }
      .inspector {
        grid-column: 1 / -1;
        border-left: 0;
        border-top: 1px solid var(--line);
        min-height: 420px;
      }
      .chat-pane { min-height: 100vh; }
    }

    @media (max-width: 760px) {
      .app { display: block; }
      .sidebar { display: none; }
      .chat-pane { min-height: 100vh; }
      .chat-head { padding: 13px 14px; align-items: flex-start; }
      .mode-pill { display: none; }
      .messages { padding: 14px; }
      .composer { padding: 10px 12px 14px; }
      .composer-inner { grid-template-columns: 1fr; }
      .send { width: 100%; }
      .inspector { display: none; }
    }
  </style>
</head>
<body class="sources-hidden">
  <div class="app">
    <aside class="sidebar">
      <div class="sidebar-name">Venture Metrics</div>

      <div class="sidebar-actions">
        <button class="new-chat" id="newChat">New chat</button>
      </div>

      <section class="status">
        <h2 class="section-label">Data</h2>
        <div class="metric-list" id="status"></div>
      </section>

      <section class="quick-list">
        <h2 class="section-label">Try these</h2>
        <button data-q="Summarize the main themes covered by the indexed Venture Metrics sources, with citations.">Source library overview</button>
        <button data-q="Which official government, university, or science park sources mention startup support in Hong Kong?">Official startup support</button>
        <button data-q="Find sources about startup funding, grants, competitions, or incubation programmes, and separate strong evidence from weak evidence.">Funding and incubation evidence</button>
        <button data-q="What do we know about GBA entrepreneurship policies, and what important gaps still need web verification?">GBA policy gaps</button>
        <button data-q="Which indexed sources discuss university innovation, spin-offs, entrepreneurship education, or student startup support?">University innovation</button>
        <button data-q="List the sources that mention incubators, accelerators, science parks, or startup hubs, grouped by source type.">Incubators and hubs</button>
        <button data-q="Which sources look most reliable for Hong Kong startup policy research, and why?">Most reliable sources</button>
        <button data-q="Which sources appear low-confidence, outdated, inaccessible, or in need of manual verification?">Needs verification</button>
        <button data-q="Compare what the indexed sources say about Hong Kong versus Shenzhen startup support.">HK versus Shenzhen</button>
        <button data-q="What questions can the current indexed source library answer well, and what questions would require web verification?">Answerability check</button>
      </section>
    </aside>

    <main class="chat-pane">
      <header class="chat-head">
        <div>
          <h1>Chat</h1>
        </div>
      </header>

      <section class="messages" id="messages" aria-label="Chat messages">
        <div class="thread" id="thread">
          <div class="welcome" id="welcome">
            <strong>Ask a question.</strong>
            <p>Chat normally, or ask a research question when you want cited evidence.</p>
          </div>
        </div>
      </section>

      <form class="composer" id="composer">
        <div class="composer-inner">
          <textarea id="question" placeholder="Ask a question..."></textarea>
          <button class="send" id="send" type="submit">Ask</button>
        </div>
      </form>
    </main>

    <aside class="inspector">
      <div class="inspector-head">
        <h2>Sources</h2>
        <p id="inspectorSummary">Citations and snippets.</p>
      </div>
      <div class="inspector-scroll" id="inspector">
        <div class="empty">Source details are hidden by default.</div>
      </div>
    </aside>
  </div>

  <script>
    const messages = document.getElementById('messages');
    const thread = document.getElementById('thread');
    const welcome = document.getElementById('welcome');
    const question = document.getElementById('question');
    const composer = document.getElementById('composer');
    const send = document.getElementById('send');
    const statusEl = document.getElementById('status');
    const inspector = document.getElementById('inspector');
    const inspectorSummary = document.getElementById('inspectorSummary');
    const newChat = document.getElementById('newChat');

    const turns = [];
    let selectedAnswerId = null;
    let telemetrySessionId = getOrCreateSessionId();

    function getOrCreateSessionId() {
      const existing = window.localStorage.getItem('ventureMetricsSessionId');
      if (existing) return existing;
      const value = `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      window.localStorage.setItem('ventureMetricsSessionId', value);
      return value;
    }

    function resetSessionId() {
      telemetrySessionId = `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      window.localStorage.setItem('ventureMetricsSessionId', telemetrySessionId);
    }

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, char => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      }[char]));
    }

    function domainFromUrl(url) {
      try {
        return new URL(url).hostname.replace(/^www\./, '');
      } catch {
        return '';
      }
    }

    function confidenceClass(value) {
      const text = String(value || '').toLowerCase();
      if (text.includes('high')) return 'high';
      if (text.includes('medium')) return 'medium';
      return 'low';
    }

    function renderMarkdownLite(text) {
      const safe = escapeHtml(text || '');
      const lines = safe.split(/\n+/).map(line => line.trim()).filter(Boolean);
      if (!lines.length) return '';

      let html = '';
      let inList = false;
      for (const line of lines) {
        if (/^[-*]\s+/.test(line)) {
          if (!inList) {
            html += '<ul>';
            inList = true;
          }
          html += `<li>${formatInline(line.replace(/^[-*]\s+/, ''))}</li>`;
        } else {
          if (inList) {
            html += '</ul>';
            inList = false;
          }
          html += `<p>${formatInline(line)}</p>`;
        }
      }
      if (inList) html += '</ul>';
      return html;
    }

    function formatInline(text) {
      return text
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/\[(\d+)\]/g, '<strong>[$1]</strong>');
    }

    function shouldAutoScroll() {
      return messages.scrollHeight - messages.scrollTop - messages.clientHeight < 180;
    }

    function scrollToBottom(force = false) {
      if (force || shouldAutoScroll()) {
        requestAnimationFrame(() => {
          messages.scrollTop = messages.scrollHeight;
        });
      }
    }

    async function loadStatus() {
      try {
        const response = await fetch('/api/status');
        const data = await response.json();
        statusEl.innerHTML = `
          <div class="metric-row"><span>Documents</span><strong>${data.documents}</strong></div>
          <div class="metric-row"><span>Sources</span><strong>${data.sources_total}</strong></div>
          <div class="metric-row"><span>Failed URLs</span><strong>${data.sources_failed}</strong></div>
        `;
      } catch {
        statusEl.innerHTML = '<div class="empty">Index status is unavailable.</div>';
      }
    }

    function chatHistory() {
      return turns
        .filter(turn => turn.role === 'user' || turn.role === 'assistant')
        .slice(-8)
        .map(turn => ({ role: turn.role, content: turn.content || '' }));
    }

    function addUserTurn(content) {
      document.getElementById('welcome')?.remove();
      turns.push({ role: 'user', content });
      const el = document.createElement('div');
      el.className = 'turn user';
      el.innerHTML = `
        <div class="turn-label">You</div>
        <div class="bubble">${escapeHtml(content)}</div>
      `;
      thread.appendChild(el);
      scrollToBottom(true);
    }

    function addPendingTurn() {
      const id = `answer-${Date.now()}`;
      const el = document.createElement('div');
      el.className = 'turn assistant';
      el.dataset.answerId = id;
      el.innerHTML = `
        <div class="turn-label">Assistant</div>
        <article class="assistant-card selected">
          <div class="answer-head">
            <div class="badges">
              <span class="badge">Thinking</span>
            </div>
          </div>
          <div class="answer-body">
            <div class="typing">
              <span>Working</span>
              <span class="dot"></span>
              <span class="dot"></span>
              <span class="dot"></span>
            </div>
          </div>
        </article>
      `;
      thread.appendChild(el);
      selectedAnswerId = id;
      clearSelected();
      el.querySelector('.assistant-card').classList.add('selected');
      scrollToBottom(true);
      return { id, el };
    }

    function renderAssistantTurn(id, el, data) {
      const citations = data.citations || [];
      const gaps = data.gaps || [];
      const evidence = [...(data.retrieved_evidence || []), ...(data.web_evidence || [])];
      const isCasual = data.source_mode === 'no_tools';
      const hasDetails = !isCasual && (citations.length || evidence.length || gaps.length);
      const confidenceBadge = isCasual ? '' : `
        <span class="badge ${confidenceClass(data.confidence)}">Confidence: ${escapeHtml(data.confidence || 'Unknown')}</span>
      `;
      const sourceButton = hasDetails ? `
        <button class="answer-select" type="button" data-select="${escapeHtml(id)}">Sources</button>
      ` : '';
      const sourceCards = citations.slice(0, 6).map((source, index) => {
        const url = source.url || '#';
        const domain = domainFromUrl(url);
        return `
          <a class="source-chip" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">
            <strong>[${index + 1}] ${escapeHtml(source.title || domain || 'Untitled source')}</strong>
            <span>${escapeHtml(domain || source.source_type || 'source')}</span>
          </a>
        `;
      }).join('');

      const gapsHtml = gaps.length ? `
        <details class="gaps">
          <summary>Data gaps and caveats</summary>
          <ul>${gaps.map(gap => `<li>${escapeHtml(gap)}</li>`).join('')}</ul>
        </details>
      ` : '';

      el.innerHTML = `
        <div class="turn-label">Assistant</div>
        <article class="assistant-card selected">
          ${confidenceBadge || sourceButton ? `
            <div class="answer-head">
              <div class="badges">${confidenceBadge}</div>
              ${sourceButton}
            </div>
          ` : ''}
          <div class="answer-body">${renderMarkdownLite(data.answer || '')}</div>
          <div class="answer-foot">
            ${!isCasual && sourceCards ? `<div class="source-strip">${sourceCards}</div>` : ''}
            ${gapsHtml}
          </div>
        </article>
      `;

      turns.push({
        id,
        role: 'assistant',
        content: data.answer || '',
        data
      });
      bindAnswerSelection(el, id);
      selectAnswer(id);
      hideInspector();
      scrollToBottom();
    }

    function renderErrorTurn(el, message) {
      el.innerHTML = `
        <div class="turn-label">Assistant</div>
        <article class="assistant-card">
          <div class="answer-head">
            <div class="badges"><span class="badge low">Error</span></div>
          </div>
          <div class="answer-body"><p>${escapeHtml(message)}</p></div>
        </article>
      `;
    }

    function bindAnswerSelection(root, id) {
      const card = root.querySelector('.assistant-card');
      const button = root.querySelector('[data-select]');
      card?.addEventListener('click', event => {
        if (event.target.closest('a')) return;
        selectAnswer(id);
      });
      button?.addEventListener('click', event => {
        event.stopPropagation();
        showSourcesFor(id);
      });
    }

    function clearSelected() {
      document.querySelectorAll('.assistant-card.selected').forEach(card => card.classList.remove('selected'));
    }

    function selectAnswer(id) {
      selectedAnswerId = id;
      clearSelected();
      const turnEl = document.querySelector(`[data-answer-id="${CSS.escape(id)}"] .assistant-card`);
      turnEl?.classList.add('selected');
    }

    function hideInspector() {
      document.body.classList.add('sources-hidden');
    }

    function showSourcesFor(id) {
      selectAnswer(id);
      const turn = turns.find(item => item.id === id);
      if (turn?.data) {
        renderInspector(turn.data);
        document.body.classList.remove('sources-hidden');
      }
    }

    function renderInspector(data) {
      const citations = data.citations || [];
      const evidence = [...(data.retrieved_evidence || []), ...(data.web_evidence || [])];
      const gaps = data.gaps || [];

      inspectorSummary.textContent = 'Sources and evidence.';

      const sourceHtml = citations.length ? citations.map((source, index) => {
        const url = source.url || '#';
        const domain = domainFromUrl(url);
        return `
          <div class="source-row">
            <a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">[${index + 1}] ${escapeHtml(source.title || domain || 'Untitled source')}</a>
            <div class="meta">${escapeHtml(domain || source.source_type || 'source')}</div>
          </div>
        `;
      }).join('') : '<div class="empty">No sources were returned for this answer.</div>';

      const evidenceHtml = evidence.length ? evidence.map((item, index) => `
        <div class="evidence-row">
          <strong>${index + 1}. ${escapeHtml(item.title || 'Evidence snippet')}</strong>
          <div class="snippet">${escapeHtml(item.snippet || '')}</div>
          <div class="meta">${escapeHtml(item.source_type || 'source')}</div>
        </div>
      `).join('') : '<div class="empty">No retrieved evidence snippets are available.</div>';

      const gapsHtml = gaps.length ? gaps.map(gap => `<div class="evidence-row"><div class="snippet">${escapeHtml(gap)}</div></div>`).join('') : '<div class="empty">No gaps reported for this answer.</div>';

      inspector.innerHTML = `
        <section class="panel-section">
          <h2 class="section-label">Sources for this answer</h2>
          <div class="panel-list">${sourceHtml}</div>
        </section>
        <section class="panel-section">
          <h2 class="section-label">Evidence snippets</h2>
          <div class="panel-list">${evidenceHtml}</div>
        </section>
        <section class="panel-section">
          <h2 class="section-label">Gaps</h2>
          <div class="panel-list">${gapsHtml}</div>
        </section>
      `;
    }

    async function runQuery(prompt) {
      const text = (prompt || question.value).trim();
      if (!text) return;
      question.value = '';
      send.disabled = true;
      addUserTurn(text);
      const pending = addPendingTurn();

      try {
        const response = await fetch('/api/query', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            question: text,
            top_k: 7,
            history: chatHistory(),
            session_id: telemetrySessionId
          })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Query failed');
        renderAssistantTurn(pending.id, pending.el, data);
      } catch (error) {
        renderErrorTurn(pending.el, error.message || 'Query failed');
      } finally {
        send.disabled = false;
        question.focus();
      }
    }

    composer.addEventListener('submit', event => {
      event.preventDefault();
      runQuery();
    });

    question.addEventListener('keydown', event => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        runQuery();
      }
    });

    document.querySelectorAll('[data-q]').forEach(button => {
      button.addEventListener('click', () => runQuery(button.dataset.q));
    });

    newChat.addEventListener('click', () => {
      turns.length = 0;
      selectedAnswerId = null;
      resetSessionId();
      hideInspector();
      thread.innerHTML = `
        <div class="welcome" id="welcome">
          <strong>Ask a question.</strong>
          <p>Chat normally, or ask a research question when you want cited evidence.</p>
        </div>
      `;
      inspectorSummary.textContent = 'Citations and snippets.';
      inspector.innerHTML = '<div class="empty">Source details are hidden by default.</div>';
      question.focus();
    });

    loadStatus();
    question.focus();
  </script>
</body>
</html>
"""


class AgentHandler(BaseHTTPRequestHandler):
    db_path: Path = DEFAULT_DB_PATH

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/?"):
            self._send_html(HTML)
            return
        if self.path == "/api/status":
            self._send_json(_status(self.db_path))
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path != "/api/query":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            user_question = str(payload.get("question") or "").strip()
            top_k = int(payload.get("top_k") or 7)
            use_web_fallback = bool(payload.get("use_web_fallback", True))
            remember_web_results = bool(payload.get("remember_web_results", False))
            history = _clean_history(payload.get("history", []))
            session_id = str(payload.get("session_id") or "").strip() or None
            if not user_question:
                raise ValueError("Question is required.")
            response = answer_question_reasoning(
                self.db_path,
                user_question,
                options=ReasoningOptions(
                    top_k=top_k,
                    use_web_fallback=use_web_fallback,
                    remember_web_results=remember_web_results,
                ),
                chat_history=history,
                telemetry_session_id=session_id,
            )
            self._send_json(response)
        except Exception as exc:  # noqa: BLE001 - local demo server should expose actionable errors.
            self._send_json({"error": str(exc)}, status=500)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict, *, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server(host: str = "127.0.0.1", port: int = 8000, db_path: str | Path = DEFAULT_DB_PATH) -> None:
    AgentHandler.db_path = Path(db_path)
    server = ThreadingHTTPServer((host, port), AgentHandler)
    print(f"Research prototype UI running at http://{host}:{port}")
    server.serve_forever()


def _status(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        return {
            "documents": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
            "chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
            "sources_total": conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
            "sources_failed": conn.execute("SELECT COUNT(*) FROM sources WHERE status = 'failed'").fetchone()[0],
        }
    finally:
        conn.close()


def _clean_history(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    cleaned: list[dict[str, str]] = []
    for item in value[-8:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        cleaned.append({"role": role, "content": content[:1200]})
    return cleaned
