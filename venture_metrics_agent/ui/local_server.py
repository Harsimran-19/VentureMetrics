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
      --canvas: #fdfcfc;
      --paper: #ffffff;
      --ink: #17151f;
      --ink-soft: #383342;
      --muted: #706879;
      --faint: #a79daf;
      --line: #e5e2df;
      --line-strong: #cfc8c2;
      --stone: #f4f1ed;
      --stone-soft: #faf8f5;
      --green: #003c33;
      --green-soft: #eef8f4;
      --navy: #16223a;
      --blue: #315fd8;
      --sky: #eaf6fb;
      --coral: #ff6b4a;
      --coral-soft: #fff0eb;
      --yellow: #f7cf5f;
      --pink: #f7eaf2;
      --purple: #eeeaf8;
      --success: #087a53;
      --warning: #925b00;
      --danger: #b42318;
      --shadow: 0 16px 36px rgba(23, 21, 31, .08);
      --radius-xs: 4px;
      --radius-sm: 8px;
      --radius-md: 8px;
      --radius-lg: 8px;
    }

    * { box-sizing: border-box; }
    html, body {
      width: 100%;
      height: 100%;
    }
    body {
      margin: 0;
      background: var(--canvas);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 16px;
      line-height: 1.5;
      letter-spacing: 0;
      overflow: hidden;
    }
    button, textarea, input { font: inherit; letter-spacing: 0; }
    button { cursor: pointer; }
    a { color: inherit; }

    .app {
      height: 100dvh;
      min-height: 0;
      display: grid;
      grid-template-columns: 314px minmax(0, 1fr) 420px;
      background: var(--canvas);
      background-image: url("data:image/svg+xml,%3Csvg width='88' height='88' viewBox='0 0 88 88' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M88 0H0V88' fill='none' stroke='%23eee8e1' stroke-width='1'/%3E%3Cpath d='M0 88L88 0' fill='none' stroke='%23f7eee8' stroke-width='1'/%3E%3C/svg%3E");
      background-size: 88px 88px;
    }
    body.sources-hidden .app { grid-template-columns: 314px minmax(0, 1fr); }
    body.sources-hidden .inspector { display: none; }

    .sidebar {
      min-width: 0;
      min-height: 0;
      height: 100%;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      background: var(--paper);
      border-right: 1px solid var(--line);
      backdrop-filter: blur(18px);
    }
    .brand {
      padding: 24px 22px 18px;
      border-bottom: 1px solid var(--line);
      position: relative;
    }
    .brand-line {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-title {
      display: grid;
      gap: 10px;
    }
    .brand-title strong {
      display: inline-block;
      font-size: 30px;
      line-height: 1;
      font-weight: 860;
      letter-spacing: 0;
      position: relative;
      width: max-content;
      max-width: 100%;
    }
    .brand-title strong::after {
      content: "";
      position: absolute;
      left: 0;
      right: 0;
      bottom: 1px;
      height: 9px;
      background: var(--coral-soft);
      z-index: -1;
    }
    .brand-title em {
      display: inline-flex;
      align-items: center;
      width: max-content;
      max-width: 100%;
      min-height: 20px;
      padding: 2px 0;
      border-top: 1px solid var(--line-strong);
      border-bottom: 1px solid var(--line-strong);
      color: var(--muted);
      font-size: 12px;
      font-style: normal;
      font-weight: 760;
      letter-spacing: .08em;
      text-transform: uppercase;
    }
    .brand::after {
      content: "";
      position: absolute;
      left: 22px;
      right: 22px;
      bottom: -2px;
      height: 4px;
      border-radius: 99px;
      background: var(--green);
    }

    .sidebar-actions {
      padding: 16px 22px;
      border-bottom: 1px solid var(--line);
    }
    .new-chat {
      width: 100%;
      min-height: 44px;
      border: 0;
      border-radius: var(--radius-sm);
      background: var(--coral);
      color: #fff;
      font-weight: 840;
      box-shadow: 0 10px 22px rgba(255, 107, 74, .2);
      transition: transform .18s ease, box-shadow .18s ease, background .18s ease;
    }
    .new-chat:hover { transform: translateY(-1px); background: var(--ink); box-shadow: 0 14px 28px rgba(23, 21, 31, .2); }
    .new-chat:active { transform: translateY(0); }

    .section-label {
      margin: 0 0 12px;
      color: var(--ink);
      font-size: 15px;
      font-weight: 820;
    }
    .status {
      padding: 20px 22px;
      border-bottom: 1px solid var(--line);
    }
    .metric-list { display: grid; gap: 10px; }
    .metric-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      min-height: 48px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--paper);
      transition: transform .18s ease, border-color .18s ease;
    }
    .metric-row:nth-child(1) { box-shadow: inset 4px 0 0 var(--green); }
    .metric-row:nth-child(2) { box-shadow: inset 4px 0 0 var(--blue); }
    .metric-row:nth-child(3) { box-shadow: inset 4px 0 0 var(--coral); }
    .metric-row:hover { transform: translateX(2px); border-color: var(--line-strong); }
    .metric-row span { color: var(--muted); font-size: 14px; }
    .metric-row strong { color: var(--ink); font-size: 18px; }

    .quick-list {
      flex: 1 1 auto;
      min-height: 0;
      padding: 20px 22px 24px;
      overflow: auto;
      overscroll-behavior: contain;
      scrollbar-gutter: stable;
    }
    .quick-list button {
      width: 100%;
      min-height: 48px;
      text-align: left;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--paper);
      color: var(--ink-soft);
      padding: 12px 34px 12px 14px;
      margin-top: 9px;
      font-size: 14px;
      line-height: 1.34;
      box-shadow: inset 0 -2px 0 var(--stone);
      transition: transform .18s ease, border-color .18s ease, background .18s ease, box-shadow .18s ease;
      position: relative;
    }
    .quick-list button::after {
      content: "→";
      position: absolute;
      right: 13px;
      top: 50%;
      color: var(--faint);
      font-weight: 800;
      transform: translateY(-50%);
      transition: transform .18s ease, color .18s ease;
    }
    .quick-list button:nth-of-type(2n) { box-shadow: inset 0 -2px 0 var(--sky); }
    .quick-list button:nth-of-type(3n) { box-shadow: inset 0 -2px 0 var(--coral-soft); }
    .quick-list button:hover {
      transform: translateX(2px);
      border-color: var(--green);
      background: var(--stone-soft);
      color: var(--ink);
      box-shadow: inset 0 -2px 0 var(--green);
    }
    .quick-list button:hover::after {
      color: var(--green);
      transform: translate(3px, -50%);
    }

    .chat-pane {
      min-width: 0;
      min-height: 0;
      height: 100%;
      overflow: hidden;
      display: grid;
      grid-template-rows: auto minmax(0, 1fr) auto;
    }
    .chat-head {
      min-height: 62px;
      padding: 14px 30px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      border-bottom: 1px solid var(--line);
      background: rgba(253, 252, 252, .9);
      backdrop-filter: blur(18px);
      position: relative;
    }
    .chat-head::after {
      content: "";
      position: absolute;
      left: 30px;
      right: 30px;
      bottom: -1px;
      height: 3px;
      background: var(--line);
    }
    .chat-head h1 {
      margin: 0;
      font-size: 20px;
      line-height: 1;
      font-weight: 820;
      letter-spacing: 0;
    }
    .chat-head p, .mode-pill { display: none; }

    .messages {
      min-height: 0;
      overflow: auto;
      overscroll-behavior: contain;
      scrollbar-gutter: stable;
      padding: 30px;
      scroll-behavior: smooth;
    }
    .thread {
      max-width: 940px;
      margin: 0 auto;
      display: grid;
      gap: 22px;
    }

    .empty-chat {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 75vh;
      position: relative;
    }
    
    .empty-hero {
      font-family: CohereText, "Space Grotesk", Inter, ui-sans-serif, system-ui, sans-serif;
      font-size: 96px;
      font-weight: 860;
      line-height: 1;
      letter-spacing: -1.92px;
      color: var(--primary, #17171c);
      margin: 0;
      display: inline-block;
      position: relative;
      animation: enterUp 0.8s cubic-bezier(0.16, 1, 0.3, 1) both;
    }

    .word-metrics {
      position: relative;
      display: inline-block;
      padding-bottom: 8px;
    }

    .word-metrics::after {
      content: "";
      position: absolute;
      left: 0;
      right: 0;
      bottom: 0;
      height: 16px;
      background-color: var(--coral, #ff7759);
      border-radius: 0;
      transform: scaleX(0);
      transform-origin: left;
      animation: revealLine 0.8s cubic-bezier(0.86, 0, 0.07, 1) 0.4s forwards;
    }

    @keyframes revealLine {
      to { transform: scaleX(1); }
    }


    .turn {
      display: grid;
      gap: 6px;
      animation: enterUp .32s ease both;
    }
    .turn.user { justify-items: end; }
    .turn-label {
      color: var(--faint);
      font-size: 13px;
      font-weight: 700;
    }
    .turn.assistant .turn-label { display: none; }
    .bubble {
      max-width: min(760px, 100%);
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      background: var(--paper);
      padding: 15px 16px;
      box-shadow: 0 8px 24px rgba(7, 24, 41, .06);
      overflow-wrap: anywhere;
    }
    .turn.user .bubble {
      background: var(--ink);
      border-color: var(--ink);
      color: #fff;
      box-shadow: 0 12px 24px rgba(23, 21, 31, .14);
    }
    .assistant-card {
      width: 100%;
      border: 1px solid var(--line-strong);
      border-radius: var(--radius-lg);
      background: var(--paper);
      box-shadow: var(--shadow);
      overflow: hidden;
      transition: border-color .18s ease, transform .18s ease;
      position: relative;
    }
    .assistant-card.selected { border-color: rgba(255, 107, 74, .55); }
    .assistant-card:hover { transform: translateY(-2px); }
    .answer-head {
      padding: 12px 16px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 10px;
      background: var(--stone-soft);
    }
    .badges { display: flex; flex-wrap: wrap; gap: 8px; }
    .badge {
      min-height: 28px;
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      padding: 4px 10px;
      color: var(--ink);
      background: var(--paper);
      font-size: 13px;
      font-weight: 820;
    }
    .badge.high { color: var(--success); border-color: rgba(8,122,83,.28); background: var(--green-soft); }
    .badge.medium { color: var(--warning); border-color: rgba(146,91,0,.3); background: #fff1b6; }
    .badge.low { color: var(--danger); border-color: rgba(180,35,24,.28); background: #ffe5df; }
    .badge.mode { color: #2e2387; background: #efeaff; border-color: rgba(143,108,255,.24); }
    .answer-select {
      border: 0;
      background: var(--ink);
      color: #fff;
      border-radius: var(--radius-sm);
      padding: 9px 13px;
      font-size: 13px;
      font-weight: 820;
      transition: transform .18s ease, box-shadow .18s ease;
    }
    .answer-select:hover { transform: translateY(-1px); box-shadow: 0 10px 20px rgba(23,23,28,.17); }
    .answer-body {
      padding: 18px 20px 12px;
      color: var(--ink-soft);
      line-height: 1.64;
    }
    .answer-body p { margin: 0 0 13px; }
    .answer-body p:last-child { margin-bottom: 0; }
    .answer-body ul { margin: 0 0 13px 20px; padding: 0; }
    .answer-body li { margin: 5px 0; }
    .answer-foot {
      padding: 0 20px 20px;
      display: grid;
      gap: 12px;
    }
    .answer-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      color: var(--muted);
      font-size: 13px;
      border-top: 1px solid var(--line);
      padding-top: 10px;
    }
    .answer-meta strong { color: var(--ink-soft); font-weight: 760; }
    .source-strip {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 10px;
    }
    .source-chip {
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      padding: 12px;
      text-decoration: none;
      color: inherit;
      background: #fff8e8;
      min-width: 0;
      transition: transform .18s ease, border-color .18s ease, background .18s ease;
    }
    .source-chip:nth-child(2n) { background: var(--sky); }
    .source-chip:nth-child(3n) { background: var(--coral-soft); }
    .source-chip:hover { transform: translateY(-2px); border-color: var(--green); background: var(--green-soft); }
    .source-chip strong {
      display: -webkit-box;
      color: var(--ink);
      font-size: 14px;
      line-height: 1.34;
      overflow: hidden;
      text-overflow: ellipsis;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
    }
    .source-chip span {
      display: block;
      margin-top: 6px;
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    details.gaps {
      border-top: 1px solid var(--line);
      padding-top: 10px;
      color: var(--muted);
      font-size: 14px;
    }
    details.gaps summary { cursor: pointer; font-weight: 760; color: var(--ink-soft); }
    details.gaps ul { margin: 9px 0 0 18px; padding: 0; }

    .composer {
      border-top: 1px solid var(--line);
      background: rgba(253, 252, 252, .9);
      backdrop-filter: blur(18px);
      padding: 16px 30px 20px;
    }
    .composer-inner {
      max-width: 940px;
      margin: 0 auto;
      border: 2px solid transparent;
      border-radius: var(--radius-sm);
      background: var(--paper);
      border-color: var(--line-strong);
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      padding: 12px;
      box-shadow: 0 16px 42px rgba(69, 43, 18, .14);
    }
    textarea {
      width: 100%;
      min-height: 52px;
      max-height: 150px;
      resize: none;
      border: 0;
      outline: 0;
      color: var(--ink);
      line-height: 1.45;
      padding: 8px 5px;
      background: transparent;
    }
    textarea::placeholder { color: var(--faint); }
    .send {
      align-self: end;
      min-width: 104px;
      height: 44px;
      border: 0;
      border-radius: var(--radius-sm);
      background: var(--coral);
      color: #fff;
      font-weight: 860;
      transition: transform .18s ease, box-shadow .18s ease, background .18s ease;
    }
    .send:hover { transform: translateY(-1px); background: var(--green); box-shadow: 0 12px 24px rgba(0,60,51,.18); }
    .send:disabled { opacity: .62; cursor: wait; transform: none; box-shadow: none; }

    .inspector {
      min-width: 0;
      min-height: 0;
      height: 100%;
      overflow: hidden;
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      border-left: 1px solid var(--line);
      background: var(--stone-soft);
      animation: slideIn .22s ease both;
    }
    .inspector-head {
      padding: 22px;
      border-bottom: 1px solid var(--line-strong);
      background: var(--paper);
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 14px;
    }
    .inspector-title { min-width: 0; }
    .inspector-head h2 { margin: 0; font-size: 32px; line-height: 1.05; font-weight: 760; }
    .inspector-head p { margin: 7px 0 0; color: var(--muted); font-size: 14px; }
    .close-sources {
      width: 34px;
      height: 34px;
      flex: 0 0 auto;
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--stone-soft);
      color: var(--ink);
      font-size: 20px;
      line-height: 1;
      font-weight: 700;
      transition: background .18s ease, border-color .18s ease, transform .18s ease;
    }
    .close-sources:hover {
      background: var(--coral-soft);
      border-color: var(--coral);
      transform: translateY(-1px);
    }
    .inspector-scroll {
      min-height: 0;
      overflow: auto;
      overscroll-behavior: contain;
      scrollbar-gutter: stable;
      padding: 20px;
    }
    .panel-section { margin-bottom: 22px; }
    .panel-list { display: grid; gap: 10px; }
    .source-row, .evidence-row, .empty {
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--paper);
      padding: 13px;
    }
    .source-row {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr);
      gap: 11px;
      align-items: start;
      transition: border-color .18s ease, transform .18s ease, background .18s ease;
    }
    .source-row:hover {
      border-color: var(--green);
      background: var(--stone-soft);
      transform: translateY(-1px);
    }
    .source-number {
      width: 28px;
      height: 28px;
      display: grid;
      place-items: center;
      border-radius: 50%;
      background: var(--green-soft);
      color: var(--green);
      font-size: 13px;
      font-weight: 820;
    }
    .source-row a {
      display: block;
      color: var(--ink);
      text-decoration: none;
      font-weight: 760;
      line-height: 1.34;
    }
    .source-row a:hover { color: var(--blue); }
    .source-content { min-width: 0; }
    .meta { margin-top: 7px; color: var(--muted); font-size: 13px; line-height: 1.35; }
    .evidence-row {
      background: var(--stone-soft);
      border-left: 4px solid var(--line-strong);
    }
    .evidence-row { display: block; font-size: 14px; line-height: 1.34; margin-bottom: 7px; }
    .snippet { color: var(--ink-soft); font-size: 14px; line-height: 1.48; }
    .empty { color: var(--muted); font-size: 14px; line-height: 1.45; border-style: dashed; }
    strong {
      font-weight: 820;
      color: var(--ink);
    }
    .research-progress {
      max-width: 520px;
      padding: 2px 0;
    }
    .progress-main {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 14px;
      font-weight: 650;
    }
    .progress-ring {
      width: 14px;
      height: 14px;
      border-radius: 50%;
      border: 2px solid var(--line-strong);
      border-top-color: var(--coral);
      animation: spin .8s linear infinite;
      flex: 0 0 auto;
    }

    @keyframes pulse {
      0%, 80%, 100% { opacity: .35; transform: translateY(0); }
      40% { opacity: 1; transform: translateY(-3px); }
    }
    @keyframes spin {
      to { transform: rotate(360deg); }
    }
    @keyframes enterUp {
      from { opacity: 0; transform: translateY(14px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @keyframes slideIn {
      from { opacity: 0; transform: translateX(16px); }
      to { opacity: 1; transform: translateX(0); }
    }
    @keyframes floatLine {
      0%, 100% { transform: translateY(0); opacity: .9; }
      50% { transform: translateY(-8px); opacity: .65; }
    }
    @keyframes driftLines {
      from { transform: translateX(-12px) rotate(-8deg); }
      to { transform: translateX(12px) rotate(-8deg); }
    }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after { animation-duration: .001ms !important; animation-iteration-count: 1 !important; transition: none !important; scroll-behavior: auto !important; }
    }
    @media (max-width: 1180px) {
      .app {
        grid-template-columns: 248px minmax(0, 1fr);
      }
      body.sources-hidden .app {
        grid-template-columns: 248px minmax(0, 1fr);
      }
      .brand { padding: 20px 18px 16px; }
      .brand::after { left: 18px; right: 18px; }
      .brand-title strong { font-size: 25px; }
      .sidebar-actions, .status { padding-left: 18px; padding-right: 18px; }
      .quick-list { padding: 18px 18px 22px; }
      .chat-head { padding-left: 24px; padding-right: 24px; }
      .chat-head::after { left: 24px; right: 24px; }
      .messages { padding: 24px; }
      .composer { padding: 14px 24px 18px; }
      .inspector {
        position: fixed;
        top: 0;
        right: 0;
        bottom: 0;
        z-index: 20;
        width: min(420px, calc(100vw - 248px));
        max-width: 100vw;
        border-left: 1px solid var(--line);
        box-shadow: -18px 0 36px rgba(23, 21, 31, .12);
      }
    }
    @media (max-width: 820px) {
      body { overflow: hidden; }
      .app {
        height: 100dvh;
        display: grid;
        grid-template-columns: minmax(0, 1fr);
        grid-template-rows: auto minmax(0, 1fr);
        background-size: 72px 72px;
      }
      body.sources-hidden .app {
        grid-template-columns: minmax(0, 1fr);
      }
      .sidebar {
        height: auto;
        max-height: 35dvh;
        border-right: 0;
        border-bottom: 1px solid var(--line);
        display: grid;
        grid-template-columns: minmax(0, 1fr) auto;
        grid-template-areas:
          "brand action"
          "status status"
          "quick quick";
        overflow: hidden;
      }
      .brand {
        grid-area: brand;
        min-width: 0;
        padding: 14px 14px 10px;
        border-bottom: 0;
      }
      .brand::after { display: none; }
      .brand-title { gap: 6px; }
      .brand-title strong {
        font-size: 22px;
        line-height: 1.05;
      }
      .brand-title em { font-size: 11px; }
      .sidebar-actions {
        grid-area: action;
        align-self: center;
        padding: 12px 14px 10px 0;
        border-bottom: 0;
      }
      .new-chat {
        width: auto;
        min-width: 92px;
        min-height: 40px;
        padding: 0 14px;
      }
      .status {
        grid-area: status;
        padding: 0 14px 10px;
        border-bottom: 0;
      }
      .status .section-label { display: none; }
      .metric-list {
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 8px;
      }
      .metric-row {
        min-height: 54px;
        display: grid;
        gap: 2px;
        padding: 8px 9px;
        align-content: center;
      }
      .metric-row:hover { transform: none; }
      .metric-row span {
        font-size: 11px;
        line-height: 1.15;
      }
      .metric-row strong { font-size: 17px; line-height: 1; }
      .quick-list {
        grid-area: quick;
        display: flex;
        align-items: center;
        gap: 8px;
        min-height: 0;
        padding: 0 14px 12px;
        overflow-x: auto;
        overflow-y: hidden;
        scrollbar-gutter: auto;
      }
      .quick-list .section-label {
        flex: 0 0 auto;
        margin: 0;
        font-size: 12px;
        color: var(--muted);
        white-space: nowrap;
      }
      .quick-list button {
        width: auto;
        flex: 0 0 min(78vw, 300px);
        min-height: 40px;
        margin-top: 0;
        padding: 9px 30px 9px 11px;
        font-size: 13px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .quick-list button:hover { transform: none; }
      .chat-pane {
        min-height: 0;
        height: 100%;
      }
      .chat-head {
        min-height: 52px;
        padding: 14px 16px;
        align-items: center;
      }
      .chat-head::after {
        left: 16px;
        right: 16px;
      }
      .chat-head h1 { font-size: 18px; }
      .messages {
        padding: 16px;
        scrollbar-gutter: auto;
      }
      .thread { gap: 16px; }
      .empty-chat {
        min-height: 46vh;
        align-items: flex-start;
      }
      .empty-hero {
        font-size: clamp(42px, 13vw, 72px);
        letter-spacing: 0;
      }
      .word-metrics::after { height: 10px; }
      .bubble {
        max-width: 92%;
        padding: 13px 14px;
      }
      .assistant-card:hover { transform: none; }
      .answer-head {
        align-items: flex-start;
        justify-content: space-between;
        flex-wrap: wrap;
      }
      .answer-select { width: 100%; }
      .answer-body { padding: 16px 15px 10px; }
      .answer-foot {
        padding: 0 15px 16px;
      }
      .source-strip {
        grid-template-columns: minmax(0, 1fr);
      }
      .composer {
        padding: 10px 12px calc(12px + env(safe-area-inset-bottom));
      }
      .composer-inner {
        grid-template-columns: 1fr;
        gap: 8px;
        padding: 10px;
        border-radius: var(--radius-md);
        box-shadow: 0 10px 28px rgba(69, 43, 18, .12);
      }
      textarea {
        min-height: 46px;
        max-height: 120px;
      }
      .send {
        width: 100%;
        height: 42px;
      }
      .inspector {
        top: auto;
        left: 0;
        right: 0;
        bottom: 0;
        width: 100%;
        height: min(76dvh, 680px);
        border-left: 0;
        border-top: 1px solid var(--line);
        box-shadow: 0 -18px 36px rgba(23, 21, 31, .16);
        animation: sheetIn .22s ease both;
      }
      .inspector-head {
        padding: 16px;
        align-items: center;
      }
      .inspector-head h2 { font-size: 24px; }
      .inspector-head p { display: none; }
      .inspector-scroll {
        padding: 14px;
        scrollbar-gutter: auto;
      }
      .source-row, .evidence-row, .empty { padding: 12px; }
    }
    @media (max-width: 520px) {
      .sidebar { max-height: 39dvh; }
      .brand-title strong { font-size: 19px; }
      .new-chat {
        min-width: 78px;
        min-height: 38px;
        padding: 0 10px;
        font-size: 13px;
      }
      .metric-list { gap: 6px; }
      .metric-row {
        min-height: 50px;
        padding: 7px;
      }
      .metric-row span { font-size: 10px; }
      .metric-row strong { font-size: 15px; }
      .quick-list button { flex-basis: min(82vw, 280px); }
      .messages { padding: 14px 12px; }
      .answer-meta { display: grid; gap: 6px; }
    }
    @keyframes sheetIn {
      from { opacity: 0; transform: translateY(18px); }
      to { opacity: 1; transform: translateY(0); }
    }
  </style>
</head>
<body class="sources-hidden">
  <div class="app">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-line">
          <div class="brand-title">
            <strong>Venture Metrics</strong>
            MVP Version
          </div>
        </div>
      </div>

      <div class="sidebar-actions">
        <button class="new-chat" id="newChat">New chat</button>
      </div>

      <section class="status">
        <h2 class="section-label">Library</h2>
        <div class="metric-list" id="status"></div>
      </section>

      <section class="quick-list">
        <h2 class="section-label">Research Questions</h2>
        <button data-q="Where can a founder get official startup support in Hong Kong, including government programmes, science parks, and incubators?">Startup support in Hong Kong</button>
        <button data-q="Which grants, funds, or competition-based programmes appear most relevant for early-stage startups in the indexed evidence?">Grants, funds, and competitions</button>
        <button data-q="Compare the startup support options mentioned for Hong Kong and Shenzhen, including policy, funding, and ecosystem support.">Compare Hong Kong vs Shenzhen</button>
        <button data-q="What do the Shenzhen policy sources say about startup subsidies, talent support, and commercialising research?">Shenzhen policy and commercialisation</button>
        <button data-q="Which Hong Kong universities provide spinout, technology transfer, or incubator support for founders?">Hong Kong university spinouts</button>
        <button data-q="Which mainland university incubators or science parks look most relevant as benchmarks for commercialization and startup support?">Mainland incubator benchmarks</button>
        <button data-q="What patent, intellectual property, or commercialization support is available in Hong Kong for startups or university-linked founders?">Patent and IP support</button>
        <button data-q="Which associations, alliances, or ecosystem organisations could help a startup build connections across Hong Kong and Shenzhen?">GBA ecosystem connectors</button>
        <button data-q="Which hiring platforms, labour portals, or talent programmes look most relevant for startup recruitment in Hong Kong, the UK, and Canada?">Startup hiring channels</button>
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
          <div class="empty-chat" id="emptyState">
            <h2 class="empty-hero">Venture <span class="word-metrics">Metrics</span></h2>
          </div>
        </div>
      </section>

      <form class="composer" id="composer">
        <div class="composer-inner">
          <textarea id="question" placeholder="Ask about Venture Metrics sources..."></textarea>
          <button class="send" id="send" type="submit">Ask</button>
        </div>
      </form>
    </main>

    <aside class="inspector">
      <div class="inspector-head">
        <div class="inspector-title">
          <h2>Sources</h2>
          <p id="inspectorSummary">Sources and short notes.</p>
        </div>
        <button class="close-sources" id="closeSources" type="button" aria-label="Close sources">×</button>
      </div>
      <div class="inspector-scroll" id="inspector">
        <div class="empty">Sources will appear here after an answer.</div>
      </div>
    </aside>
  </div>

  <script>
    const messages = document.getElementById('messages');
    const thread = document.getElementById('thread');
    const question = document.getElementById('question');
    const composer = document.getElementById('composer');
    const send = document.getElementById('send');
    const statusEl = document.getElementById('status');
    const inspector = document.getElementById('inspector');
    const inspectorSummary = document.getElementById('inspectorSummary');
    const newChat = document.getElementById('newChat');
    const closeSources = document.getElementById('closeSources');

    const turns = [];
    const loadingTimers = new Map();
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
          <div class="metric-row"><span>Pages read</span><strong>${data.documents}</strong></div>
          <div class="metric-row"><span>Saved sources</span><strong>${data.sources_total}</strong></div>
          <div class="metric-row"><span>Links to review</span><strong>${data.sources_failed}</strong></div>
        `;
      } catch {
        statusEl.innerHTML = '<div class="empty">Library status is not available right now.</div>';
      }
    }

    function chatHistory() {
      return turns
        .filter(turn => turn.role === 'user' || turn.role === 'assistant')
        .slice(-8)
        .map(turn => ({ role: turn.role, content: turn.content || '' }));
    }

    function addUserTurn(content) {
      const emptyState = document.getElementById('emptyState');
      if (emptyState) emptyState.remove();

      turns.push({ role: 'user', content });
      const el = document.createElement('div');
      el.className = 'turn user';
      el.innerHTML = `
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
        <article class="assistant-card selected">
          <div class="answer-body">
            <div class="research-progress" aria-label="Research progress">
              <div class="progress-main">
                <span class="progress-ring" aria-hidden="true"></span>
                <span data-loading-title>Checking sources...</span>
              </div>
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

    function updatePendingStatus(el, message) {
      const title = el.querySelector('[data-loading-title]');
      if (title && message) title.textContent = message;
    }

    function stopLoadingStatus(id) {
      const timer = loadingTimers.get(id);
      if (timer) {
        window.clearInterval(timer);
        loadingTimers.delete(id);
      }
    }

    function renderAssistantTurn(id, el, data) {
      stopLoadingStatus(id);
      const shouldKeepSourcesOpen = !document.body.classList.contains('sources-hidden');
      const citations = data.citations || [];
      const gaps = data.gaps || [];
      const evidence = [...(data.retrieved_evidence || []), ...(data.web_evidence || [])];
      const isCasual = data.source_mode === 'no_tools';
      const hasDetails = !isCasual && (citations.length || evidence.length || gaps.length);
      const sourceButton = hasDetails ? `
        <button class="answer-select" type="button" data-select="${escapeHtml(id)}">Show sources</button>
      ` : '';
      const sourceCards = citations.slice(0, 6).map((source, index) => {
        const url = source.url || '#';
        const domain = domainFromUrl(url);
        return `
          <a class="source-chip" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">
            <strong>[${index + 1}] ${escapeHtml(source.title || domain || 'Source')}</strong>
            <span>${escapeHtml(domain || source.source_type || 'source')}</span>
          </a>
        `;
      }).join('');

      const gapsHtml = gaps.length ? `
        <details class="gaps">
          <summary>What is still unclear</summary>
          <ul>${gaps.map(gap => `<li>${escapeHtml(gap)}</li>`).join('')}</ul>
        </details>
      ` : '';
      const metaHtml = !isCasual ? `
        <div class="answer-meta">
          <span><strong>Confidence:</strong> ${escapeHtml(data.confidence || 'Unknown')}</span>
          <span><strong>Sources:</strong> ${citations.length}</span>
        </div>
      ` : '';

      el.innerHTML = `
        <article class="assistant-card selected">
          ${sourceButton ? `
            <div class="answer-head">
              ${sourceButton}
            </div>
          ` : ''}
          <div class="answer-body">${renderMarkdownLite(data.answer || '')}</div>
          <div class="answer-foot">
            ${!isCasual && sourceCards ? `<div class="source-strip">${sourceCards}</div>` : ''}
            ${gapsHtml}
            ${metaHtml}
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
      if (shouldKeepSourcesOpen) {
        renderInspector(data);
        document.body.classList.remove('sources-hidden');
      } else {
        hideInspector();
      }
      scrollToBottom();
    }

    function renderErrorTurn(el, message) {
      const id = el.dataset.answerId;
      if (id) stopLoadingStatus(id);
      el.innerHTML = `
        <article class="assistant-card">
          <div class="answer-head">
            <div class="badges"><span class="badge low">Could not answer</span></div>
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

      inspectorSummary.textContent = 'Sources and short notes.';

      const sourceHtml = citations.length ? citations.map((source, index) => {
        const url = source.url || '#';
        const domain = domainFromUrl(url);
        return `
          <div class="source-row">
            <div class="source-number">${index + 1}</div>
            <div class="source-content">
              <a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(source.title || domain || 'Source')}</a>
              <div class="meta">${escapeHtml(domain || source.source_type || 'source')}</div>
            </div>
          </div>
        `;
      }).join('') : '<div class="empty">No source links were returned for this answer.</div>';

      const evidenceHtml = evidence.length ? evidence.map((item, index) => `
        <div class="evidence-row">
          <strong>${index + 1}. ${escapeHtml(item.title || 'Source note')}</strong>
          <div class="snippet">${escapeHtml(item.snippet || '')}</div>
          <div class="meta">${escapeHtml(item.source_type || 'source')}</div>
        </div>
      `).join('') : '<div class="empty">No short notes are available.</div>';

      const gapsHtml = gaps.length ? gaps.map(gap => `<div class="evidence-row"><div class="snippet">${escapeHtml(gap)}</div></div>`).join('') : '<div class="empty">No open gaps were reported.</div>';

      inspector.innerHTML = `
        <section class="panel-section">
          <h2 class="section-label">Source links</h2>
          <div class="panel-list">${sourceHtml}</div>
        </section>
        <section class="panel-section">
          <h2 class="section-label">Source notes</h2>
          <div class="panel-list">${evidenceHtml}</div>
        </section>
        <section class="panel-section">
          <h2 class="section-label">Still unclear</h2>
          <div class="panel-list">${gapsHtml}</div>
        </section>
      `;
      inspector.scrollTop = 0;
    }

    async function runQuery(prompt) {
      const text = (prompt || question.value).trim();
      if (!text) return;
      question.value = '';
      send.disabled = true;
      addUserTurn(text);
      const pending = addPendingTurn();

      try {
        const response = await fetch('/api/query-stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            question: text,
            top_k: 7,
            history: chatHistory(),
            session_id: telemetrySessionId
          })
        });
        if (!response.ok) {
          const data = await response.json().catch(() => ({}));
          throw new Error(data.error || 'Query failed');
        }
        const data = await readQueryStream(response, pending.el);
        renderAssistantTurn(pending.id, pending.el, data);
      } catch (error) {
        renderErrorTurn(pending.el, error.message || 'Query failed');
      } finally {
        send.disabled = false;
        question.focus();
      }
    }

    async function readQueryStream(response, pendingEl) {
      if (!response.body || !response.body.getReader) {
        updatePendingStatus(pendingEl, 'Writing answer...');
        return response.json();
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let finalPayload = null;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) continue;
          const event = JSON.parse(trimmed);
          if (event.type === 'progress') {
            updatePendingStatus(pendingEl, event.message);
          } else if (event.type === 'final') {
            finalPayload = event.response;
          } else if (event.type === 'error') {
            throw new Error(event.error || 'Query failed');
          }
        }
      }

      if (buffer.trim()) {
        const event = JSON.parse(buffer.trim());
        if (event.type === 'final') finalPayload = event.response;
        if (event.type === 'error') throw new Error(event.error || 'Query failed');
      }
      if (!finalPayload) throw new Error('Query finished without an answer.');
      return finalPayload;
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
        <div class="empty-chat" id="emptyState">
          <h2 class="empty-hero">Venture <span class="word-metrics">Metrics</span></h2>
        </div>
      `;
      inspectorSummary.textContent = 'Sources and short notes.';
      inspector.innerHTML = '<div class="empty">Sources will appear here after an answer.</div>';
      question.focus();
    });

    closeSources.addEventListener('click', () => {
      hideInspector();
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

    def do_HEAD(self) -> None:
        if self.path == "/" or self.path.startswith("/?"):
            self._send_html(HTML, include_body=False)
            return
        if self.path == "/api/status":
            self._send_json(_status(self.db_path), include_body=False)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if self.path == "/api/query":
                self._handle_query(payload)
                return
            if self.path == "/api/query-stream":
                self._handle_query_stream(payload)
                return
            self.send_error(404)
        except Exception as exc:  # noqa: BLE001 - local demo server should expose actionable errors.
            self._send_json({"error": str(exc)}, status=500)

    def _handle_query(self, payload: dict) -> None:
        user_question = str(payload.get("question") or "").strip()
        top_k = int(payload.get("top_k") or 7)
        use_web_fallback = bool(payload.get("use_web_fallback", True))
        remember_web_results = bool(payload.get("remember_web_results", True))
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

    def _handle_query_stream(self, payload: dict) -> None:
        user_question = str(payload.get("question") or "").strip()
        top_k = int(payload.get("top_k") or 7)
        use_web_fallback = bool(payload.get("use_web_fallback", True))
        remember_web_results = bool(payload.get("remember_web_results", True))
        history = _clean_history(payload.get("history", []))
        session_id = str(payload.get("session_id") or "").strip() or None
        if not user_question:
            raise ValueError("Question is required.")

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        def emit(event: dict) -> None:
            self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()

        try:
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
                progress_callback=emit,
            )
            emit({"type": "final", "response": response})
        except Exception as exc:  # noqa: BLE001 - stream local demo errors to the client.
            emit({"type": "error", "error": str(exc)})

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_html(self, html: str, *, include_body: bool = True) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def _send_json(self, payload: dict, *, status: int = 200, include_body: bool = True) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
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
