from __future__ import annotations

import argparse
from pathlib import Path
from collections import deque
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
import secrets
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from string import Template
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import Request, urlopen

from als_intel.auth import AuthService, build_auth_config
from als_intel.brand import (
    LANDING_DASHBOARD_URL_PATH,
    LETTERMARK_LOGO_URL_PATH,
    LOGO_URL_PATH,
    favicon_link_tag,
    landing_dashboard_bytes,
    landing_dashboard_mime_type,
    lettermark_logo_bytes,
    lettermark_logo_mime_type,
    logo_bytes,
    logo_mime_type,
    render_inline_logo,
)
from als_intel.landing import APP_ROUTE, render_landing_page
from als_intel.llm import LocalLLMError, build_grounded_prompt, generate_with_ollama, generate_with_ollama_stream
from als_intel.markdown_render import extract_markdown_title, render_markdown_to_html
from als_intel.store import EvidenceStore


DEFAULT_DB_PATH = os.getenv("ALS_DB_PATH", "data/als_intel.sqlite")
DEFAULT_OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
DEFAULT_PORT = int(os.getenv("ALS_WEB_PORT", "8000"))

PUBLIC_PAGE_PATHS = {"/", "/index.html", "/login", "/privacy", "/terms"}
APP_PAGE_PATHS = {APP_ROUTE, f"{APP_ROUTE}/index.html"}
DEFAULT_CONTEXT_LIMIT = int(os.getenv("ALS_CONTEXT_LIMIT", "20"))
DEFAULT_TEMPERATURE = float(os.getenv("ALS_TEMPERATURE", "0.1"))
DEFAULT_TIMEOUT_SECONDS = int(os.getenv("ALS_TIMEOUT_SECONDS", "120"))
DEFAULT_AUTH_ENABLED = os.getenv("ALS_AUTH_ENABLED", "1").strip() not in {"0", "false", "False"}
MAX_CITED_EVIDENCE_ROWS = 80
TELEMETRY_MAX_RECENT = 200

_RECENT_QUERY_TELEMETRY: deque[dict[str, object]] = deque(maxlen=TELEMETRY_MAX_RECENT)
_RECENT_QUERY_TELEMETRY_LOCK = Lock()


PAGE_TEMPLATE = Template(
    """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>MTVL AI</title>
    $favicon_tag
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Courier+Prime:wght@400;700&display=swap" rel="stylesheet" />
    <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght@400;500;600&display=swap" rel="stylesheet" />
    <style>
      :root {
        --bg: #f7f9fb;
        --surface: #ffffff;
        --panel: #f1f5f9;
        --panel-strong: #eceef0;
        --text: #191c1e;
        --muted: #54647a;
        --muted-strong: #505f76;
        --primary: #0f52ba;
        --primary-strong: #003c90;
        --border: #e2e8f0;
        --border-strong: #cbd5e1;
        --ok: #16a34a;
        --warn: #b91c1c;
        --warn-bg: #fff1f2;
        --warn-border: #fecdd3;
      }
      * { box-sizing: border-box; }
      .material-symbols-outlined {
        font-family: 'Material Symbols Outlined';
        font-weight: normal;
        font-style: normal;
        font-size: 20px;
        line-height: 1;
        letter-spacing: normal;
        text-transform: none;
        display: inline-block;
        white-space: nowrap;
        word-wrap: normal;
        direction: ltr;
        font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
      }
      body {
        margin: 0;
        font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
        background: var(--bg);
        color: var(--text);
        overflow: hidden;
      }
      .topbar {
        height: 64px;
        border-bottom: 1px solid var(--border);
        background: var(--surface);
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 32px;
        position: sticky;
        top: 0;
        z-index: 10;
      }
      .topbar-left {
        display: flex;
        align-items: center;
        gap: 24px;
      }
      .nav {
        display: flex;
        gap: 22px;
        margin-left: 12px;
      }
      .nav button {
        border: 0;
        border-bottom: 2px solid transparent;
        background: transparent;
        color: var(--muted-strong);
        border-radius: 0;
        padding: 24px 0 22px;
        font-size: 11px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        font-weight: 600;
        cursor: pointer;
      }
      .nav button.active {
        color: var(--primary-strong);
        border-color: var(--primary-strong);
      }
      .brand {
        display: inline-flex;
        align-items: center;
        text-decoration: none;
        line-height: 0;
      }
      .statusrow {
        display: flex;
        gap: 12px;
        align-items: center;
        color: var(--muted);
        font-size: 0.78rem;
      }
      .metric-cluster {
        display: flex;
        align-items: center;
        gap: 18px;
        border-left: 1px solid var(--border);
        padding-left: 24px;
        margin-left: 4px;
        height: 32px;
      }
      .metric-chip {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        font-size: 11px;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: var(--muted-strong);
      }
      .dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: var(--ok);
        display: inline-block;
        margin-right: 6px;
      }
      .layout {
        max-width: 1440px;
        margin: 0 auto;
        padding: 16px 32px;
        height: calc(100vh - 64px);
        display: grid;
        grid-template-columns: 250px minmax(0, 1fr) 350px;
        gap: 16px;
      }
      .layout > .panel {
        min-height: 0;
      }
      .layout.filters-collapsed {
        grid-template-columns: 64px minmax(0, 1fr) 350px;
      }
      @media (max-width: 1180px) {
        .layout {
          grid-template-columns: 1fr;
          height: calc(100vh - 64px);
          padding: 16px;
        }
      }
      .card {
        border: 1px solid var(--border);
        background: var(--surface);
        border-radius: 4px;
      }
      .panel {
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 4px;
      }
      .filter-panel {
        display: flex;
        flex-direction: column;
        min-height: 0;
      }
      .filter-panel .head {
        flex-shrink: 0;
      }
      .filter-panel-body {
        display: flex;
        flex-direction: column;
        min-height: 0;
        flex: 1;
      }
      .panel .head,
      .card .head {
        padding: 12px 14px;
        border-bottom: 1px solid var(--border);
        font-size: 16px;
        font-weight: 600;
      }
      .p12 { padding: 12px; }
      .filters {
        display: grid;
        gap: 18px;
        overflow: auto;
        flex: 1;
        align-content: start;
        grid-auto-rows: min-content;
      }
      .type-list {
        display: grid;
        gap: 8px;
      }
      .type-list label {
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .label {
        font-size: 11px;
        text-transform: uppercase;
        color: var(--muted);
        letter-spacing: 0.08em;
        margin-bottom: 8px;
        font-weight: 600;
      }
      .stack6 > * + * { margin-top: 8px; }
      .btn {
        border: 1px solid var(--border-strong);
        background: #fff;
        border-radius: 4px;
        padding: 8px 14px;
        cursor: pointer;
        color: #334155;
        font-size: 13px;
        font-weight: 500;
      }
      .btn.primary {
        background: var(--primary);
        color: white;
        border-color: var(--primary);
      }
      .btn.primary:hover { background: var(--primary-strong); }
      .btn:disabled { opacity: 0.6; cursor: not-allowed; }
      .icon-btn {
        border: 0;
        background: transparent;
        color: var(--muted-strong);
        padding: 0;
        width: 20px;
        height: 20px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
      }
      .icon-btn:disabled {
        opacity: 0.35;
        cursor: not-allowed;
      }
      .switch-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 10px;
      }
      .switch {
        position: relative;
        display: inline-block;
        width: 40px;
        height: 22px;
      }
      .switch input {
        opacity: 0;
        width: 0;
        height: 0;
      }
      .slider {
        position: absolute;
        inset: 0;
        cursor: pointer;
        background: #cbd5e1;
        transition: 0.2s;
        border-radius: 999px;
      }
      .slider:before {
        position: absolute;
        content: "";
        height: 16px;
        width: 16px;
        left: 3px;
        top: 3px;
        background: white;
        transition: 0.2s;
        border-radius: 50%;
      }
      .switch input:checked + .slider {
        background: var(--primary);
      }
      .switch input:checked + .slider:before {
        transform: translateX(18px);
      }
      .filter-actions {
        border-top: 1px solid var(--border);
        background: var(--panel);
        padding: 10px 12px 12px;
        display: flex;
        gap: 8px;
        justify-content: flex-end;
      }
      .filter-panel.collapsed .filter-panel-body {
        display: none;
      }
      .filter-panel.collapsed .head {
        border-bottom: 0;
      }
      .filter-panel.collapsed .filter-title {
        display: none;
      }
      .avatar-btn {
        width: 32px;
        height: 32px;
        border-radius: 999px;
        border: 1px solid var(--border-strong);
        background: linear-gradient(180deg, #d8e5fb 0%, #f4f7fb 100%);
        color: var(--primary-strong);
        font-size: 11px;
        font-weight: 700;
        display: inline-flex;
        align-items: center;
        justify-content: center;
      }
      input[type="text"],
      input[type="number"],
      select,
      textarea {
        width: 100%;
        border: 1px solid var(--border);
        border-radius: 4px;
        padding: 9px 12px;
        font: inherit;
        background: white;
      }
      input[type="checkbox"] { accent-color: var(--primary); }
      textarea {
        min-height: 92px;
        resize: vertical;
        padding-right: 52px;
        font-size: 14px;
        line-height: 1.65;
      }
      input[type="range"] {
        width: 100%;
        accent-color: var(--primary);
      }
      .main {
        display: grid;
        grid-template-rows: auto 1fr;
        min-height: 0;
        overflow: hidden;
        height: 100%;
      }
      #assistantView {
        display: grid;
        grid-template-rows: auto minmax(0, 1fr) auto;
        min-height: 0;
        height: 100%;
      }
      .card.main {
        border: 0;
        background: transparent;
      }
      .center-col {
        display: grid;
        grid-template-rows: minmax(0, 1fr) auto;
        min-height: 0;
        gap: 12px;
        height: 100%;
        overflow: hidden;
      }
      .querybox {
        padding: 16px;
        background: #fff;
        border: 1px solid var(--border-strong);
        border-radius: 4px;
        margin-bottom: 14px;
      }
      .query-actions {
        display: flex;
        gap: 8px;
        margin-top: 10px;
        align-items: center;
      }
      .query-stack {
        position: relative;
      }
      .send-btn {
        position: absolute;
        right: 12px;
        bottom: 12px;
        width: 30px;
        height: 30px;
        border-radius: 4px;
        border: 0;
        background: var(--primary);
        color: #fff;
        display: inline-flex;
        align-items: center;
        justify-content: center;
      }
      .send-btn.loading {
        background: var(--primary-strong);
        cursor: wait;
        pointer-events: none;
      }
      .send-btn .spinner {
        width: 14px;
        height: 14px;
        border: 2px solid rgba(255, 255, 255, 0.35);
        border-top-color: #ffffff;
        border-radius: 50%;
        animation: spin 0.8s linear infinite;
      }
      @keyframes spin {
        to { transform: rotate(360deg); }
      }
      .searchbox {
        max-width: 220px;
      }
      .report {
        padding: 0 0 12px;
        overflow: auto;
        display: grid;
        gap: 14px;
        min-height: 0;
      }
      .section {
        border: 1px solid var(--border);
        border-radius: 4px;
        padding: 16px;
        background: #fff;
      }
      .section h4 {
        margin: 0 0 8px;
        font-size: 11px;
        text-transform: uppercase;
        color: var(--muted);
        letter-spacing: 0.08em;
        font-weight: 600;
      }
      .md-content {
        font-size: 14px;
        line-height: 1.65;
        color: var(--text);
        display: grid;
        gap: 12px;
      }
      .md-content p {
        margin: 0;
      }
      .md-content strong {
        font-weight: 700;
        color: #0f172a;
      }
      .md-content em {
        font-style: italic;
      }
      .md-content code {
        font-family: 'Courier Prime', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        font-size: 12px;
        background: #f1f5f9;
        border: 1px solid var(--border);
        border-radius: 4px;
        padding: 1px 5px;
      }
      .md-content ul,
      .md-content ol {
        margin: 0 0 0 20px;
        padding: 0;
      }
      .md-content li {
        margin-bottom: 6px;
      }
      .md-content h1,
      .md-content h2,
      .md-content h3,
      .md-content h4 {
        margin: 0;
        text-transform: none;
        letter-spacing: normal;
        color: #0f172a;
      }
      .md-content h1 { font-size: 20px; }
      .md-content h2 { font-size: 18px; }
      .md-content h3 { font-size: 16px; }
      .md-content h4 { font-size: 15px; }
      .report-shell {
        border: 1px solid var(--border);
        border-radius: 4px;
        background: #fff;
        padding: 24px 18px 18px;
      }
      .report-shell.loading {
        background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
      }
      #report .report-shell > .section + .section {
        margin-top: 10px;
      }
      .report-head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding-bottom: 14px;
        border-bottom: 1px solid #f1f5f9;
        margin-bottom: 18px;
      }
      .report-title {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 20px;
        font-weight: 600;
      }
      .loading-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: var(--primary);
        box-shadow: 0 0 0 rgba(15, 82, 186, 0.35);
        animation: pulse-dot 1.3s ease-out infinite;
      }
      .loading-copy {
        margin: 10px 0 14px;
      }
      .loading-skeleton {
        display: grid;
        gap: 10px;
      }
      .loading-line {
        height: 10px;
        border-radius: 999px;
        background: linear-gradient(90deg, #e2e8f0 0%, #f8fafc 50%, #e2e8f0 100%);
        background-size: 220px 100%;
        animation: shimmer 1.2s linear infinite;
      }
      .loading-line.wide { width: 92%; }
      .loading-line.mid { width: 72%; }
      .loading-line.short { width: 48%; }
      @keyframes pulse-dot {
        0% { transform: scale(0.92); box-shadow: 0 0 0 0 rgba(15, 82, 186, 0.35); }
        70% { transform: scale(1.06); box-shadow: 0 0 0 10px rgba(15, 82, 186, 0); }
        100% { transform: scale(0.92); box-shadow: 0 0 0 0 rgba(15, 82, 186, 0); }
      }
      @keyframes shimmer {
        from { background-position: -220px 0; }
        to { background-position: 220px 0; }
      }
      .runtime-badge,
      .count-badge {
        background: var(--panel-strong);
        border: 1px solid var(--border-strong);
        border-radius: 4px;
        color: var(--muted-strong);
        padding: 4px 8px;
        font-family: 'Courier Prime', ui-monospace, monospace;
        font-size: 12px;
      }
      .count-badge {
        font-weight: 400;
      }
      .chips {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
      }
      .chip {
        border: 1px solid var(--border-strong);
        border-radius: 4px;
        padding: 3px 8px;
        font-size: 12px;
        background: #f8fafc;
        display: inline-flex;
        align-items: center;
        gap: 4px;
      }
      .warn {
        border-color: var(--warn-border);
        background: var(--warn-bg);
      }
      .actions {
        display: flex;
        gap: 10px;
        padding: 14px 0 0;
        border-top: 1px solid var(--border);
      }
      .center-actions {
        padding: 12px;
        border-top: 0;
        background: var(--surface);
      }
      .report-actions {
        margin-top: 10px;
      }
      .actions .spacer { flex: 1; }
      .evidence-wrap {
        display: flex;
        flex-direction: column;
        min-height: 0;
        overflow: hidden;
      }
      .evidence-head {
        flex-shrink: 0;
        padding: 12px 14px;
        border-bottom: 1px solid var(--border);
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: 10px;
      }
      .panel-hint {
        flex-shrink: 0;
        padding: 12px 16px;
        text-align: center;
        font-size: 12px;
        line-height: 1.5;
        color: #64748b;
        font-style: italic;
        background: #f8fafc;
        border-bottom: 1px solid var(--border);
      }
      .evidence-list {
        flex: 1;
        min-height: 0;
        overflow: auto;
        padding: 12px;
        display: grid;
        gap: 10px;
        align-content: start;
        grid-auto-rows: min-content;
      }
      .evidence-panels {
        flex-shrink: 0;
        border-top: 1px solid var(--border);
        background: #fff;
      }
      .panel-scroll {
        max-height: 168px;
        overflow-y: auto;
        overscroll-behavior: contain;
        padding-right: 2px;
      }
      .db-status-chip {
        position: relative;
      }
      .db-status-popover {
        position: absolute;
        top: calc(100% + 10px);
        left: 0;
        width: min(320px, 78vw);
        padding: 14px;
        background: #fff;
        border: 1px solid var(--border);
        border-radius: 10px;
        box-shadow: 0 16px 36px -14px rgba(15, 23, 42, 0.35);
        opacity: 0;
        visibility: hidden;
        transform: translateY(-6px);
        transition: opacity 0.16s ease, transform 0.16s ease, visibility 0.16s;
        z-index: 60;
        pointer-events: none;
        text-align: left;
        font-weight: 400;
      }
      .db-status-popover::before {
        content: '';
        position: absolute;
        top: -6px;
        left: 18px;
        width: 12px;
        height: 12px;
        background: #fff;
        border-left: 1px solid var(--border);
        border-top: 1px solid var(--border);
        transform: rotate(45deg);
      }
      .db-status-chip:hover .db-status-popover,
      .db-status-chip:focus-within .db-status-popover {
        opacity: 1;
        visibility: visible;
        transform: translateY(0);
        pointer-events: auto;
      }
      .db-popover-head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 8px;
        margin-bottom: 10px;
      }
      .db-popover-title {
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #334155;
      }
      .db-popover-total {
        font-size: 22px;
        font-weight: 700;
        color: var(--primary-strong);
        line-height: 1.1;
      }
      .db-popover-meta {
        font-size: 11px;
        color: var(--muted);
        margin-bottom: 10px;
      }
      .db-popover-sources {
        display: grid;
        gap: 8px;
      }
      .db-popover-source-row {
        display: flex;
        justify-content: space-between;
        gap: 8px;
        font-size: 11px;
        color: #475569;
      }
      .db-popover-bar {
        width: 100%;
        height: 5px;
        background: #f1f5f9;
        border-radius: 999px;
        overflow: hidden;
        margin-top: 3px;
      }
      .db-popover-bar > span {
        display: block;
        height: 100%;
        border-radius: 999px;
        background: var(--primary-strong);
      }
      .db-popover-foot {
        margin-top: 10px;
        padding-top: 10px;
        border-top: 1px solid #f1f5f9;
        font-size: 11px;
        color: #64748b;
      }
      .ev {
        border: 1px solid var(--border);
        border-left-width: 4px;
        border-radius: 4px;
        background: white;
        padding: 12px;
        display: grid;
        gap: 10px;
        cursor: pointer;
      }
      .ev.supports { border-left-color: var(--ok); }
      .ev.contradicts { border-left-color: var(--warn); }
      .ev.neutral { border-left-color: #3b82f6; }
      .ev-top {
        display: flex;
        justify-content: space-between;
        gap: 8px;
        align-items: center;
      }
      .mono {
        font-family: 'Courier Prime', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        font-size: 12px;
      }
      .muted { color: var(--muted); }
      .small { font-size: 13px; line-height: 1.55; }
      .tiny { font-size: 11px; }
      .compare {
        border-top: 1px solid var(--border);
        padding: 12px;
        display: grid;
        gap: 8px;
        background: #fff;
      }
      .compare input[type="text"] {
        font-size: 13px;
      }
      .row { display: flex; gap: 8px; align-items: center; }
      .right {
        justify-content: flex-end;
      }
      .status-msg { font-size: 12px; color: var(--muted); min-height: 1rem; margin-top: 8px; }
      .error { color: #b91c1c; }
      .drawer-backdrop {
        position: fixed;
        inset: 0;
        background: rgba(15, 23, 42, 0.35);
        opacity: 0;
        pointer-events: none;
        transition: opacity 0.16s ease;
        z-index: 20;
      }
      .drawer {
        position: fixed;
        top: 0;
        right: 0;
        width: min(520px, 92vw);
        height: 100vh;
        background: var(--surface);
        border-left: 1px solid var(--border);
        transform: translateX(100%);
        transition: transform 0.16s ease;
        z-index: 21;
        display: grid;
        grid-template-rows: auto 1fr;
      }
      .drawer.open { transform: translateX(0); }
      .drawer-backdrop.open {
        opacity: 1;
        pointer-events: auto;
      }
      .drawer-head {
        padding: 12px;
        border-bottom: 1px solid var(--border);
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .drawer-body {
        padding: 12px;
        overflow: auto;
        display: grid;
        gap: 12px;
      }
      .drawer-list {
        display: grid;
        gap: 8px;
      }
      .drawer-item {
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 8px;
        background: #fff;
      }
      .hidden { display: none !important; }
      .sessions-list {
        display: grid;
        gap: 8px;
      }
      .session-row {
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 8px;
        background: #fff;
        cursor: pointer;
      }
      .session-row:hover {
        border-color: var(--primary);
      }
      .settings-grid {
        display: grid;
        gap: 10px;
      }
      .settings-modal {
        position: fixed;
        inset: 0;
        z-index: 30;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 16px;
        opacity: 0;
        pointer-events: none;
        transition: opacity 0.24s ease;
      }
      .settings-modal.open {
        opacity: 1;
        pointer-events: auto;
      }
      .settings-modal-backdrop {
        position: absolute;
        inset: 0;
        background: rgba(15, 23, 42, 0.42);
        backdrop-filter: blur(3px);
      }
      .settings-modal-panel {
        position: relative;
        width: min(760px, 94vw);
        max-height: 90vh;
        display: grid;
        grid-template-rows: auto 1fr auto;
        border: 1px solid var(--border-strong);
        border-radius: 8px;
        background: var(--surface);
        box-shadow: 0 24px 64px rgba(15, 23, 42, 0.2);
        transform: translateY(12px) scale(0.985);
        transition: transform 0.24s ease;
      }
      .settings-modal.open .settings-modal-panel {
        transform: translateY(0) scale(1);
      }
      .settings-modal-head {
        padding: 16px 20px;
        border-bottom: 1px solid var(--border-strong);
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      .settings-modal-body {
        padding: 18px;
        overflow: auto;
        display: grid;
        gap: 14px;
      }
      .settings-section {
        border: 1px solid var(--border-strong);
        border-radius: 6px;
        padding: 16px;
        background: var(--surface-container-low, #f8fafc);
      }
      .settings-section-title {
        font-size: 22px;
        line-height: 1.1;
        font-weight: 600;
      }
      .settings-readonly {
        width: 100%;
        border: 1px solid var(--border);
        border-radius: 4px;
        padding: 9px 12px;
        background: #e5e7eb;
        color: #334155;
        font-family: 'Courier Prime', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        font-size: 13px;
      }
      .settings-modal-footer {
        padding: 12px 18px;
        border-top: 1px solid var(--border-strong);
        background: #f8fafc;
        display: flex;
        justify-content: flex-end;
        gap: 10px;
      }
      .status-link {
        cursor: pointer;
        text-decoration: underline dotted;
        text-underline-offset: 2px;
      }
      .status-link:focus-visible {
        outline: 2px solid var(--primary);
        outline-offset: 2px;
        border-radius: 3px;
      }
      .db-toolbar {
        display: grid;
        gap: 10px;
      }
      .db-search-row {
        display: grid;
        grid-template-columns: 1fr auto auto;
        gap: 8px;
      }
      .db-meta {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        align-items: center;
      }
      .db-results {
        display: grid;
        gap: 10px;
      }
      .db-node {
        border: 1px solid var(--border-strong);
        border-radius: 6px;
        padding: 10px;
        background: #fff;
        display: grid;
        gap: 8px;
      }
      .db-node-head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 10px;
      }
      .db-node-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 6px 12px;
      }
      .db-pagination {
        display: flex;
        justify-content: flex-end;
        align-items: center;
        gap: 8px;
      }
      .db-meta-summary {
        border-top: 1px dashed var(--border);
        padding-top: 8px;
      }
      .db-meta-detail {
        border: 1px solid var(--border);
        border-radius: 6px;
        background: #f8fafc;
        padding: 8px;
        display: grid;
        gap: 8px;
      }
      .db-meta-detail-list {
        margin: 0;
        padding-left: 18px;
        display: grid;
        gap: 2px;
      }
      .review-layout {
        display: grid;
        grid-template-columns: 1.15fr 1fr;
        gap: 12px;
      }
      .review-list {
        display: grid;
        gap: 8px;
      }
      .review-item {
        border: 1px solid var(--border-strong);
        border-radius: 6px;
        background: #fff;
        padding: 10px;
        display: grid;
        gap: 7px;
      }
      .review-item.active {
        border-color: var(--primary);
        box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.18);
      }
      .review-meta {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }
      .review-chip {
        border: 1px solid var(--border-strong);
        border-radius: 999px;
        padding: 2px 8px;
        background: #f8fafc;
        font-size: 11px;
      }
      .review-panel {
        border: 1px solid var(--border-strong);
        border-radius: 6px;
        background: #fff;
        padding: 12px;
        display: grid;
        gap: 10px;
        align-content: start;
      }
      .review-history {
        border-top: 1px solid var(--border);
        padding-top: 10px;
        display: grid;
        gap: 6px;
      }
      .hypo-controls {
        display: grid;
        gap: 10px;
      }
      .hypo-grid {
        display: grid;
        grid-template-columns: 1.2fr 0.8fr;
        gap: 12px;
      }
      .hypo-list {
        display: grid;
        gap: 8px;
      }
      .hypo-card {
        border: 1px solid var(--border-strong);
        border-radius: 6px;
        background: #fff;
        padding: 10px;
        display: grid;
        gap: 7px;
      }
      .hypo-removed {
        border: 1px dashed var(--border-strong);
        border-radius: 6px;
        background: #fff;
        padding: 10px;
        display: grid;
        gap: 7px;
      }
      @media (max-width: 900px) {
        .db-search-row {
          grid-template-columns: 1fr;
        }
        .db-node-grid {
          grid-template-columns: 1fr;
        }
        .review-layout {
          grid-template-columns: 1fr;
        }
        .hypo-grid {
          grid-template-columns: 1fr;
        }
      }
      .compare-grid {
        display: grid;
        gap: 10px;
      }
      .compare-cols {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
      }
      .tutorial-overlay {
        position: fixed;
        inset: 0;
        z-index: 120;
        pointer-events: none;
      }
      .tutorial-spotlight {
        position: fixed;
        border: 2px solid var(--primary);
        border-radius: 10px;
        box-shadow: 0 0 0 9999px rgba(15, 23, 42, 0.52), 0 0 0 3px rgba(59, 130, 246, 0.18);
        transition: all 0.2s ease;
      }
      .tutorial-card {
        position: fixed;
        width: min(360px, calc(100vw - 24px));
        border: 1px solid var(--border-strong);
        border-radius: 8px;
        background: #ffffff;
        box-shadow: 0 24px 64px rgba(2, 6, 23, 0.3);
        padding: 14px;
        display: grid;
        gap: 10px;
        pointer-events: auto;
      }
      .tutorial-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
      }
      .tutorial-actions {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 8px;
      }
      .tutorial-target {
        position: relative;
        z-index: 121;
      }
      @media (max-width: 1180px) {
        .compare-cols { grid-template-columns: 1fr; }
      }
    </style>
  </head>
  <body>
    <header class="topbar">
      <div class="topbar-left">
        <a href="/" class="brand" title="MTVL AI">$logo_html</a>
        <div class="metric-cluster">
          <div class="metric-chip"><span class="material-symbols-outlined" style="font-size:16px">model_training</span><span id="status-model">$model</span></div>
          <div class="metric-chip db-status-chip">
            <span id="statusDbDot" class="dot"></span>
            <span id="status-db" class="status-link" role="button" tabindex="0" aria-describedby="statusDbPopover" title="Database status">DB synced</span>
            <div id="statusDbPopover" class="db-status-popover" role="tooltip">
              <div class="db-popover-head">
                <span id="statusDbPopoverTitle" class="db-popover-title">Database status</span>
                <span id="statusDbPopoverDot" class="dot"></span>
              </div>
              <div id="statusDbPopoverTotal" class="db-popover-total">-</div>
              <div id="statusDbPopoverMeta" class="db-popover-meta">Checking sync status...</div>
              <div id="statusDbPopoverSources" class="db-popover-sources"></div>
              <div id="statusDbPopoverFoot" class="db-popover-foot">Loading database status...</div>
            </div>
          </div>
        </div>
      </div>
      <div class="statusrow">
        <div class="nav" style="margin-left:0">
          <button id="navAssistant" class="active">Assistant</button>
          <button id="navSessions">Saved Sessions</button>
        </div>
        <button id="openDatabase" class="icon-btn" title="Database (disabled)" disabled><span class="material-symbols-outlined">database</span></button>
        <button id="openSettings" class="icon-btn" title="Settings"><span class="material-symbols-outlined">settings</span></button>
        <button id="openHypothesisQueue" class="icon-btn" title="Hypothesis queue"><span class="material-symbols-outlined">psychology</span></button>
        <span id="authBadge" class="tiny muted">guest</span>
        <button id="logoutBtn" class="btn tiny hidden">Logout</button>
        <button id="openProfile" class="avatar-btn" title="Review queue">AI</button>
      </div>
    </header>
    <main class="layout">
      <aside id="filterPanel" class="panel filter-panel">
        <div class="head" style="display:flex;justify-content:space-between;align-items:center;"><span id="filterTitle" class="filter-title">Evidence Filters</span><button id="toggleFilters" class="icon-btn" title="Collapse/expand filters"><span class="material-symbols-outlined" style="font-size:18px;color:var(--muted)">filter_list</span></button></div>
        <div class="filter-panel-body">
        <div class="p12 filters">
          <div>
            <div id="evidenceTypeLabel" class="label">Evidence type</div>
            <div class="type-list small">
              <label><input type="checkbox" name="etype" value="observational" checked /> Observational</label>
              <label><input type="checkbox" name="etype" value="interventional" checked /> Interventional</label>
              <label><input type="checkbox" name="etype" value="mechanistic" /> Mechanistic</label>
              <label><input type="checkbox" name="etype" value="genetic" /> Genetic</label>
              <label><input type="checkbox" name="etype" value="negative" /> Negative findings</label>
            </div>
          </div>
          <div>
            <div id="publicationDateLabel" class="label">Publication date</div>
            <select id="dateWindow">
              <option value="last5">Last 5 years</option>
              <option value="last10">Last 10 years</option>
              <option value="all" selected>All time</option>
            </select>
          </div>
          <div>
            <div id="minReliabilityLabel" class="label" style="display:flex;justify-content:space-between;align-items:center;">Min reliability <span id="relLabel" class="mono" style="color:var(--primary-strong)">60%</span></div>
            <input id="minRel" type="range" min="0" max="1" step="0.01" value="0.60" oninput="document.getElementById('relLabel').textContent=Math.round(this.value*100)+'%'" onchange="document.getElementById('relLabel').textContent=Math.round(this.value*100)+'%'" />
            <div class="tiny muted" style="display:flex;justify-content:space-between;margin-top:4px"><span>0%</span><span>100%</span></div>
          </div>
          <div class="switch-row">
            <span id="highlightContradictionsLabel" class="small">Highlight contradictions</span>
            <label class="switch" aria-label="Highlight contradictions">
              <input id="highlightContradictions" type="checkbox" checked />
              <span class="slider"></span>
            </label>
          </div>
        </div>
        <div class="filter-actions">
            <button id="resetFilters" class="btn">Reset</button>
            <button id="applyFilters" class="btn primary">Apply</button>
        </div>
        </div>
      </aside>

      <div class="center-col">
      <section class="card main">
        <div id="assistantView">
        <div class="querybox">
          <div id="queryEvidenceLabel" class="label">Query evidence database</div>
          <div class="query-stack">
            <textarea id="question" placeholder="Enter clinical question or hypothesis..."></textarea>
            <button id="send" class="send-btn" title="Send"><span class="material-symbols-outlined" style="font-size:18px">send</span></button>
          </div>
          <div id="chatStatus" class="status-msg hidden"></div>
        </div>
        <div id="report" class="report">
          <div class="report-shell">
            <div class="report-head">
              <div class="report-title"><span class="material-symbols-outlined" style="color:var(--primary)">psychiatry</span>Synthesis Report</div>
            </div>
            <div class="small muted">Run a query to generate an investigator report.</div>
          </div>
        </div>
        <div id="reportActions" class="actions center-actions card report-actions hidden">
          <button id="saveSession" class="btn" disabled><span class="material-symbols-outlined" style="font-size:18px;vertical-align:middle;margin-right:6px">save</span>Save Session</button>
          <button id="exportSummary" class="btn" disabled><span class="material-symbols-outlined" style="font-size:18px;vertical-align:middle;margin-right:6px">download</span>Export Summary</button>
          <div class="spacer"></div>
          <button id="copyCitations" class="btn" disabled><span class="material-symbols-outlined" style="font-size:18px;vertical-align:middle;margin-right:6px">content_copy</span>Copy Citations</button>
        </div>
        </div>
        <div id="sessionsView" class="p12 hidden">
          <div class="row" style="margin-bottom:10px">
            <div id="savedSessionsLabel" class="label" style="margin:0">Saved sessions</div>
            <div class="spacer"></div>
            <button id="refreshSessions" class="btn tiny">Refresh</button>
          </div>
          <div id="sessionsList" class="sessions-list"></div>
        </div>
      </section>
      </div>

      <aside class="panel evidence-wrap">
        <div class="evidence-head">
          <div>
            <span id="evidenceNodesLabel" style="display:flex;align-items:center;gap:8px"><span class="material-symbols-outlined" style="font-size:18px;color:var(--muted)">view_list</span>Evidence Nodes</span>
          </div>
          <span class="count-badge"><span id="evidenceCount">0</span> <span id="evidenceFoundSuffix">found</span></span>
        </div>
        <div id="evidenceListHint" class="panel-hint hidden"></div>
        <div id="evidenceList" class="evidence-list"></div>
        <div class="evidence-panels">
        <div class="compare">
          <div id="compareNodesLabel" class="label">Compare nodes</div>
          <div class="row">
            <input id="compareA" type="text" placeholder="Drop CLM ID" style="border-style:dashed;text-align:center;background:#fff" />
            <span class="material-symbols-outlined" style="font-size:16px;color:var(--muted)">compare_arrows</span>
            <input id="compareB" type="text" placeholder="Drop CLM ID" style="border-style:dashed;text-align:center;background:#fff" />
          </div>
          <button id="runCompare" class="btn">Compare</button>
          <div id="compareResult" class="tiny muted"></div>
        </div>
        <div class="compare" style="margin-top:0;border-top:1px solid var(--border)">
          <div class="row" style="justify-content:space-between;align-items:center;margin-bottom:6px">
            <div id="diagnosticsTitle" class="label" style="margin:0">Diagnostics</div>
            <button id="refreshDiagnostics" class="btn tiny">Refresh</button>
          </div>
          <div id="diagnosticsList" class="panel-scroll tiny muted">No diagnostics yet.</div>
        </div>
        <div class="compare" style="margin-top:0;border-top:1px solid var(--border)">
          <div class="row" style="justify-content:space-between;align-items:center;margin-bottom:6px">
            <div id="failureAtlasTitle" class="label" style="margin:0">Failure Atlas</div>
            <button id="refreshFailureAtlas" class="btn tiny">Refresh</button>
          </div>
          <div id="failureAtlasList" class="panel-scroll tiny muted">No failure atlas entries yet.</div>
        </div>
        </div>
      </aside>
    </main>
    <div id="drawerBackdrop" class="drawer-backdrop"></div>
    <aside id="lineageDrawer" class="drawer">
      <div class="drawer-head">
        <strong id="drawerTitle">Claim details</strong>
        <button id="closeDrawer" class="btn">Close</button>
      </div>
      <div id="drawerBody" class="drawer-body">
        <div class="small muted">Click an evidence row to inspect lineage and contradictions.</div>
      </div>
    </aside>
    <div id="settingsDrawer" class="settings-modal" aria-hidden="true">
      <div id="settingsModalBackdrop" class="settings-modal-backdrop"></div>
      <div class="settings-modal-panel">
        <div class="settings-modal-head">
          <strong id="settingsTitle" class="settings-section-title">Settings</strong>
          <button id="closeSettingsIcon" class="icon-btn" title="Close settings"><span class="material-symbols-outlined">close</span></button>
        </div>
        <div class="settings-modal-body">
          <section class="settings-section">
            <div style="max-width:340px">
              <div class="label" style="margin-bottom:6px">General Settings</div>
              <div id="settingsLanguageLabel" class="small" style="margin-bottom:8px;color:#0f172a;font-weight:600">Language Selector</div>
              <select id="settingsLanguage">
                <option value="en">English</option>
                <option value="es">Español</option>
              </select>
              <div id="tutorialControlsLabel" class="small" style="margin-top:14px;margin-bottom:8px;color:#0f172a;font-weight:600">Tutorial</div>
              <div class="row" style="gap:8px;justify-content:flex-start">
                <button id="startShortTutorial" class="btn tiny">Tutorial corto</button>
                <button id="startLongTutorial" class="btn tiny">Tutorial largo</button>
              </div>
            </div>
          </section>
          <section class="settings-section">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
              <div class="small" style="font-size:24px;line-height:1.2;font-weight:600;color:#0f172a">Technical Configuration</div>
              <span class="tiny mono" style="padding:2px 8px;border-radius:4px;background:#e2e8f0;border:1px solid #cbd5e1;color:#334155;text-transform:uppercase;letter-spacing:0.05em;font-weight:700">Read Only</span>
            </div>
            <div class="settings-grid" style="grid-template-columns:1fr 1fr;gap:12px">
              <div>
                <div id="settingsModelLabel" class="label" style="margin-bottom:6px">AI Model</div>
                <input id="settingsModel" class="settings-readonly" type="text" readonly />
              </div>
              <div>
                <div id="settingsHostLabel" class="label" style="margin-bottom:6px">Host</div>
                <input id="settingsHost" class="settings-readonly" type="text" readonly />
              </div>
              <div style="grid-column:1 / -1">
                <div id="settingsContextLabel" class="label" style="margin-bottom:6px">Context Limit</div>
                <input id="settingsContextLimit" class="settings-readonly" type="text" readonly />
              </div>
              <div style="display:none">
                <div id="settingsTemperatureLabel" class="label" style="margin-bottom:6px">Temperature</div>
                <input id="settingsTemperature" type="number" min="0" max="2" step="0.01" />
              </div>
              <div style="display:none">
                <div id="settingsTimeoutLabel" class="label" style="margin-bottom:6px">Timeout seconds</div>
                <input id="settingsTimeout" type="number" min="1" max="600" />
              </div>
            </div>
          </section>
        </div>
        <div class="settings-modal-footer">
          <button id="closeSettings" class="btn">Cancel</button>
          <button id="applySettings" class="btn primary">Save Changes</button>
        </div>
      </div>
    </div>
    <div id="dbExplorerModal" class="settings-modal" aria-hidden="true">
      <div id="dbExplorerModalBackdrop" class="settings-modal-backdrop"></div>
      <div class="settings-modal-panel">
        <div class="settings-modal-head">
          <strong id="dbExplorerTitle" class="settings-section-title">Database explorer</strong>
          <button id="closeDbExplorerIcon" class="icon-btn" title="Close database explorer"><span class="material-symbols-outlined">close</span></button>
        </div>
        <div class="settings-modal-body">
          <section class="settings-section db-toolbar">
            <div id="dbSearchLabel" class="label">Search nodes</div>
            <div class="db-search-row">
              <input id="dbSearchInput" type="text" placeholder="Search by claim text, claim id, entity, outcome, or DOI" />
              <button id="dbSearchButton" class="btn primary">Search</button>
              <button id="dbClearSearch" class="btn">Clear</button>
            </div>
            <div class="db-meta tiny muted">
              <span id="dbResultsMeta">0 / 0</span>
              <span id="dbExplorerStatus"></span>
            </div>
          </section>
          <section class="settings-section">
            <div id="dbExplorerRows" class="db-results"></div>
          </section>
        </div>
        <div class="settings-modal-footer">
          <div class="db-pagination" style="margin-right:auto">
            <button id="dbPrevPage" class="btn">Prev</button>
            <span id="dbPageLabel" class="mono tiny">Page 1</span>
            <button id="dbNextPage" class="btn">Next</button>
          </div>
          <button id="closeDbExplorer" class="btn">Close</button>
        </div>
      </div>
    </div>
    <div id="reviewQueueModal" class="settings-modal" aria-hidden="true">
      <div id="reviewQueueModalBackdrop" class="settings-modal-backdrop"></div>
      <div class="settings-modal-panel">
        <div class="settings-modal-head">
          <strong id="reviewQueueTitle" class="settings-section-title">Review queue</strong>
          <button id="closeReviewQueueIcon" class="icon-btn" title="Close review queue"><span class="material-symbols-outlined">close</span></button>
        </div>
        <div class="settings-modal-body">
          <section class="settings-section">
            <div class="row" style="justify-content:space-between;align-items:center;margin-bottom:10px">
              <div id="reviewQueueSubtitle" class="label" style="margin:0">Claims requiring human review</div>
              <button id="refreshReviewQueue" class="btn tiny">Refresh</button>
            </div>
            <div class="review-layout">
              <div id="reviewFlagsList" class="review-list"></div>
              <div class="review-panel">
                <div id="reviewSelectedClaim" class="mono">-</div>
                <div>
                  <div id="reviewerLabel" class="label" style="margin-bottom:6px">Reviewer</div>
                  <input id="reviewerInput" type="text" placeholder="reviewer_a" />
                </div>
                <div>
                  <div id="reviewNotesLabel" class="label" style="margin-bottom:6px">Notes</div>
                  <textarea id="reviewNotesInput" style="min-height:80px" placeholder="Optional notes"></textarea>
                </div>
                <div class="row" style="flex-wrap:wrap">
                  <button id="approveClaim" class="btn primary">Approve</button>
                  <button id="rejectClaim" class="btn">Reject</button>
                  <button id="needsEvidenceClaim" class="btn">Needs more evidence</button>
                </div>
                <div id="reviewDecisionStatus" class="tiny muted"></div>
                <div class="review-history">
                  <div id="reviewHistoryLabel" class="label" style="margin:0">Decision history</div>
                  <div id="reviewHistoryList" class="tiny muted"></div>
                </div>
              </div>
            </div>
          </section>
        </div>
        <div class="settings-modal-footer">
          <button id="closeReviewQueue" class="btn">Close</button>
        </div>
      </div>
    </div>
    <div id="hypothesisQueueModal" class="settings-modal" aria-hidden="true">
      <div id="hypothesisQueueModalBackdrop" class="settings-modal-backdrop"></div>
      <div class="settings-modal-panel">
        <div class="settings-modal-head">
          <strong id="hypothesisQueueTitle" class="settings-section-title">Hypothesis queue</strong>
          <button id="closeHypothesisQueueIcon" class="icon-btn" title="Close hypothesis queue"><span class="material-symbols-outlined">close</span></button>
        </div>
        <div class="settings-modal-body">
          <section class="settings-section hypo-controls">
            <div class="row" style="justify-content:space-between;align-items:center">
              <div id="hypothesisControlsLabel" class="label" style="margin:0">Promotion controls</div>
              <button id="refreshHypothesisQueue" class="btn tiny">Refresh</button>
            </div>
            <label class="small"><input id="hypoRequireSignoff" type="checkbox" checked /> <span id="hypoRequireSignoffLabel">Require review signoff</span></label>
            <label class="small"><input id="hypoEnforceCausalGate" type="checkbox" /> <span id="hypoEnforceCausalGateLabel">Enforce causal gate</span></label>
            <div id="hypothesisMeta" class="tiny muted">-</div>
          </section>
          <section class="settings-section hypo-grid">
            <div>
              <div id="hypothesisPromotedLabel" class="label">Promoted hypotheses</div>
              <div id="hypothesisQueueList" class="hypo-list"></div>
            </div>
            <div>
              <div id="hypothesisRemovedLabel" class="label">Filtered out by controls</div>
              <div id="hypothesisRemovedList" class="hypo-list"></div>
            </div>
          </section>
        </div>
        <div class="settings-modal-footer">
          <button id="closeHypothesisQueue" class="btn">Close</button>
        </div>
      </div>
    </div>
    <div id="tutorialOverlay" class="tutorial-overlay hidden" aria-hidden="true">
      <div id="tutorialSpotlight" class="tutorial-spotlight"></div>
      <section id="tutorialCard" class="tutorial-card" role="dialog" aria-modal="false" aria-live="polite" aria-label="Interactive tutorial">
        <div class="tutorial-head">
          <strong id="tutorialTitle">Quick tour</strong>
          <span id="tutorialProgress" class="mono tiny">1 / 1</span>
        </div>
        <div id="tutorialBody" class="small"></div>
        <div id="tutorialHint" class="tiny muted" style="min-height:18px"></div>
        <div class="tutorial-actions">
          <button id="tutorialBack" class="btn tiny">Back</button>
          <button id="tutorialStop" class="btn tiny">Stop</button>
          <button id="tutorialNext" class="btn tiny primary">Next</button>
        </div>
      </section>
    </div>

    <script>
      const state = {
        model: '$model',
        dbPath: '$db_path',
        authEnabled: $auth_enabled,
        isAuthenticated: false,
        currentUser: null,
        csrfToken: '',
        host: '$ollama_host',
        language: 'es',
        contextLimit: Number('$context_limit'),
        temperature: Number('$temperature'),
        timeoutSeconds: Number('$timeout_seconds'),
        messages: [],
        evidenceRows: [],
        lastReport: null,
        activeSessionId: null,
        currentEvidenceQuery: '',
        currentComparePayload: null,
        dbBrowserQuery: '',
        dbBrowserOffset: 0,
        dbBrowserLimit: 12,
        dbBrowserTotal: 0,
        dbMetadataCache: {},
        dbStatusSnapshot: null,
        reviewFlags: [],
        selectedReviewClaimId: '',
        hypothesisRows: [],
        hypothesisRemovedEntities: [],
        hypothesisLimit: 8,
        tutorial: {
          running: false,
          stepIndex: 0,
          mode: 'short',
          actions: {
            question_typed: false,
            report_ready: false,
            evidence_clicked: false,
            filters_applied: false,
            db_explorer_opened: false,
            sessions_view_opened: false,
            hypothesis_queue_opened: false,
            review_queue_opened: false,
          },
        },
      };

      const nativeFetch = window.fetch.bind(window);
      window.fetch = (input, init = {}) => {
        const headers = new Headers((init && init.headers) || {});
        if (state.authEnabled && state.csrfToken && !headers.has('X-CSRF-Token')) {
          headers.set('X-CSRF-Token', state.csrfToken);
        }
        return nativeFetch(input, { ...init, headers });
      };

      const I18N = {
        en: {
          nav_assistant: 'Assistant',
          nav_sessions: 'Saved Sessions',
          filter_title: 'Evidence Filters',
          evidence_type: 'Evidence type',
          publication_date: 'Publication date',
          min_reliability: 'Min reliability',
          highlight_contradictions: 'Highlight contradictions',
          reset: 'Reset',
          apply: 'Apply',
          query_evidence: 'Query evidence database',
          question_placeholder: 'Enter clinical question or hypothesis...',
          saved_sessions: 'Saved sessions',
          refresh: 'Refresh',
          evidence_nodes: 'Evidence Nodes',
          found: 'found',
          compare_nodes: 'Compare nodes',
          run_compare: 'Run compare',
          settings: 'Settings',
          close: 'Cancel',
          language: 'Language Selector',
          model: 'AI Model',
          host: 'Host',
          context_limit: 'Context Limit',
          temperature: 'Temperature',
          timeout_seconds: 'Timeout seconds',
          apply_settings: 'Save Changes',
          save_session: 'Save session',
          export_summary: 'Export summary',
          copy_citations: 'Copy citations',
          db_explorer_title: 'Database explorer',
          db_search_label: 'Search nodes',
          db_search_placeholder: 'Search by claim text, claim id, entity, outcome, or DOI',
          db_search: 'Search',
          db_clear: 'Clear',
          db_prev: 'Prev',
          db_next: 'Next',
          db_close: 'Close',
          db_no_rows: 'No nodes found for the current search.',
          db_open_hint: 'Open database explorer',
          db_meta_title: 'Source metadata',
          db_meta_view: 'View full metadata',
          db_meta_hide: 'Hide metadata',
          db_meta_loading: 'Loading metadata...',
          db_meta_error: 'Metadata unavailable',
          db_meta_not_found: 'No source metadata found for this node.',
          db_meta_journal: 'Journal',
          db_meta_pubdate: 'Pub date',
          db_meta_authors: 'Authors',
          db_meta_mesh_terms: 'MeSH terms',
          db_meta_abstract: 'Abstract',
          yes: 'yes',
          no: 'no',
          review_queue: 'Review queue',
          review_queue_subtitle: 'Claims requiring human review',
          reviewer: 'Reviewer',
          notes: 'Notes',
          refresh: 'Refresh',
          approve: 'Approve',
          reject: 'Reject',
          needs_more_evidence: 'Needs more evidence',
          decision_history: 'Decision history',
          no_review_flags: 'No review flags at the moment.',
          review_decision_saved: 'Review decision saved.',
          hypothesis_queue: 'Hypothesis queue',
          promotion_controls: 'Promotion controls',
          require_review_signoff: 'Require review signoff',
          enforce_causal_gate: 'Enforce causal gate',
          promoted_hypotheses: 'Promoted hypotheses',
          filtered_out_controls: 'Filtered out by controls',
          no_hypotheses: 'No hypotheses were promoted with current controls.',
          no_filtered_entities: 'No entities were filtered out.',
          db_synced: 'DB synced',
          db_out_of_sync: 'DB out of sync',
          db_unavailable: 'DB unavailable',
          db_popover_title: 'Database status',
          db_popover_total_label: 'evidence nodes',
          db_popover_last_sync: 'Last sync',
          db_popover_ready: 'Database is online and query-ready.',
          db_popover_waiting: 'Database online, waiting for first ingestion.',
          db_popover_loading: 'Loading database status...',
          db_popover_unavailable: 'Database status is unavailable.',
          db_popover_hint: 'Click to open the database explorer.',
          evidence_hint_idle: 'Cited evidence will appear here after you run a query.',
          evidence_hint_empty: 'No evidence nodes were cited in this report.',
          report_title: 'Synthesis Report',
          generated_in: 'Generated in {seconds}s',
          direct_answer: 'Direct answer',
          supporting_nodes: 'Supporting evidence nodes',
          contradictions_uncertainty: 'Contradictions and uncertainty',
          next_validation_step: 'Next validation step',
          run_this_query: 'Run this query',
          generating_report: 'Generating Synthesis Report',
          in_progress: 'In progress',
          loading_copy: 'Analyzing evidence and composing a fresh report for your query.',
          type_question_first: 'Type a question first.',
          generating_new_report: 'Generating a new synthesis report...',
          stream_loading_evidence: 'Loading and filtering evidence...',
          stream_building_prompt: 'Building grounded prompt...',
          stream_generating: 'Generating answer...',
          stream_post_processing: 'Linking citations and synthesis metadata...',
          stream_done: 'Streaming complete. {count} rows used.',
          telemetry_phase_summary: 'Phases(s): load {loading}, prompt {prompt}, gen {gen}, post {post}, total {total}.',
          diagnostics_title: 'Diagnostics',
          diagnostics_empty: 'No diagnostics yet.',
          rows_retrieved: 'Rows retrieved',
          rows_cited: 'Rows cited',
          response_mode: 'Response mode',
          response_mode_stream: 'stream',
          response_mode_sync: 'sync',
          response_mode_sync_fallback: 'sync fallback',
          guardrail_flags: 'Guardrails',
          verification_flags: 'Verification',
          failure_atlas_title: 'Failure Atlas',
          failure_atlas_empty: 'No failure atlas entries yet.',
          failure_atlas_total: 'Failed or negative records',
          failure_atlas_structured: 'Structured trial failures',
          trial_status: 'Trial status',
          termination_reason: 'Termination reason',
          primary_endpoint_result: 'Primary endpoint result',
          root_cause: 'Root cause',
          done_rows_used: 'Done. {count} rows used.',
          no_report_to_save: 'No report to save yet.',
          session_saved: 'Session saved to database.',
          no_saved_sessions: 'No saved sessions.',
          loading_sessions: 'Loading sessions...',
          loaded_latest_session: 'Loaded latest saved session.',
          filters_updated: 'Filters updated. Run a query to refresh cited evidence nodes.',
          filters_reset: 'Filters reset. Run a query to refresh cited evidence nodes.',
          no_report_to_export: 'No report to export yet.',
          exported_summary: 'Exported JSON and Markdown summary.',
          no_citations_to_copy: 'No citations to copy yet.',
          no_supporting_ids: 'No supporting claim ids found.',
          copied_claims: 'Copied {count} claim ids with DOIs.',
          settings_applied: 'Settings applied for this session.',
          profile_disabled: 'Profile controls are not enabled in simple investigator mode.',
          compare_prompt: 'Provide two claim ids to compare.',
          shared_supporting: 'shared supporting',
          shared_contradicting: 'shared contradicting',
          follow_up: 'Follow-up',
          default_follow_up: 'Run targeted validation for conflicting endpoints.',
          updated: 'Updated',
          claim_a: 'Claim A',
          claim_b: 'Claim B',
          study_type: 'Study type',
          effect: 'Effect',
          use_in_compare: 'Use in compare',
          start_tour: 'Start Tour',
          tutorial_title: 'Quick tour: investigate with confidence',
          tutorial_back: 'Back',
          tutorial_next: 'Next',
          tutorial_finish: 'Finish',
          tutorial_stop: 'Stop',
          tutorial_progress: 'Step {current} of {total}',
          tutorial_wait_for_action: 'Complete the highlighted action to continue.',
          tutorial_done: 'Tutorial completed. You can relaunch it anytime from Start Tour.',
          tutorial_stopped: 'Tutorial stopped. You can restart it from Start Tour.',
          tutorial_step_query_title: 'Step 1: Ask a clear question',
          tutorial_step_query_body: 'Use this box to define one concrete investigation question. Keep it short and specific.',
          tutorial_step_send_title: 'Step 2: Run the investigation',
          tutorial_step_send_body: 'Click Send to generate a synthesis report grounded in evidence. Wait until the report appears.',
          tutorial_step_report_title: 'Step 3: Read the synthesis',
          tutorial_step_report_body: 'This report is your synthesis: direct answer, cited evidence, uncertainty, and a concrete next move.',
          tutorial_step_validation_title: 'Step 4: Validation section',
          tutorial_step_validation_body: 'Pay special attention to contradictions and the Next validation step. This is where you decide what to verify next.',
          tutorial_step_diagnostics_title: 'Step 5: Diagnostics area',
          tutorial_step_diagnostics_body: 'Diagnostics explains how the response was built: rows retrieved, citations used, timing, and guardrails.',
          tutorial_step_save_title: 'Step 6: Save session',
          tutorial_step_save_body: 'Save Session stores your current investigation state so you can continue later without losing context.',
          tutorial_step_export_title: 'Step 7: Export summary',
          tutorial_step_export_body: 'Export Summary downloads your synthesis in JSON and Markdown for reporting and sharing.',
          tutorial_step_copy_title: 'Step 8: Copy citations',
          tutorial_step_copy_body: 'Copy Citations puts supporting claim IDs and source DOIs on your clipboard for fast referencing.',
          tutorial_step_db_open_title: 'Step 9: Open evidence database explorer',
          tutorial_step_db_open_body: 'Click DB synced to open the evidence database explorer and inspect indexed claims directly.',
          tutorial_step_db_explorer_title: 'Step 10: Explore evidence database',
          tutorial_step_db_explorer_body: 'Use this explorer to search claims, review metadata, and inspect provenance before making decisions.',
          tutorial_step_sessions_nav_title: 'Step 11: Open saved sessions',
          tutorial_step_sessions_nav_body: 'Go to Saved Sessions to revisit previous investigations and recover their report context.',
          tutorial_step_sessions_list_title: 'Step 12: Saved sessions list',
          tutorial_step_sessions_list_body: 'Select any session to restore question, synthesis, and cited evidence in one click.',
          tutorial_step_hypothesis_open_title: 'Step 13: Open hypothesis queue',
          tutorial_step_hypothesis_open_body: 'The hypothesis queue proposes prioritized candidate hypotheses from current evidence and controls.',
          tutorial_step_hypothesis_queue_title: 'Step 14: How hypothesis queue works',
          tutorial_step_hypothesis_queue_body: 'Promoted hypotheses are candidates to pursue now. Filtered entities were excluded by signoff/causal controls.',
          tutorial_step_review_open_title: 'Step 15: Open review queue',
          tutorial_step_review_open_body: 'The review queue is where high-risk or uncertain claims are escalated for human decisions.',
          tutorial_step_review_queue_title: 'Step 16: How review queue works',
          tutorial_step_review_queue_body: 'Choose a claim, add reviewer notes, and record approve/reject/needs-more-evidence to keep an auditable trail.',
          tutorial_step_evidence_title: 'Step 17: Inspect evidence nodes',
          tutorial_step_evidence_body: 'These are cited evidence nodes. Green tends to support, red contradicts, and yellow is mixed/neutral.',
          tutorial_step_lineage_title: 'Step 18: Open lineage details',
          tutorial_step_lineage_body: 'Click one evidence node to inspect citation lineage and supporting versus contradicting context.',
          tutorial_step_filters_title: 'Step 19: Refine filters',
          tutorial_step_filters_body: 'Adjust filters to narrow evidence quality and scope, then click Apply.',
          tutorial_step_compare_title: 'Step 20: Compare two claims',
          tutorial_step_compare_body: 'Use compare to check overlap and contradictions between two claim IDs.',
          tutorial_controls_label: 'Tutorial',
          tutorial_short_button: 'Short tutorial',
          tutorial_long_button: 'Long tutorial',
          tutorial_mode_short: 'Short Tour',
          tutorial_mode_full: 'Full Tour',
          tutorial_mode_label: 'Tutorial mode',
        },
        es: {
          nav_assistant: 'Asistente',
          nav_sessions: 'Sesiones guardadas',
          filter_title: 'Filtros de evidencia',
          evidence_type: 'Tipo de evidencia',
          publication_date: 'Fecha de publicacion',
          min_reliability: 'Confiabilidad minima',
          highlight_contradictions: 'Resaltar contradicciones',
          reset: 'Restablecer',
          apply: 'Aplicar',
          query_evidence: 'Consultar base de evidencia',
          question_placeholder: 'Escribe una pregunta clinica o hipotesis...',
          saved_sessions: 'Sesiones guardadas',
          refresh: 'Actualizar',
          evidence_nodes: 'Nodos de evidencia',
          found: 'encontrados',
          compare_nodes: 'Comparar nodos',
          run_compare: 'Comparar',
          settings: 'Configuracion',
          close: 'Cancelar',
          language: 'Selector de idioma',
          model: 'Modelo IA',
          host: 'Host',
          context_limit: 'Limite de contexto',
          temperature: 'Temperatura',
          timeout_seconds: 'Tiempo de espera (s)',
          apply_settings: 'Guardar cambios',
          save_session: 'Guardar sesion',
          export_summary: 'Exportar resumen',
          copy_citations: 'Copiar citas',
          db_explorer_title: 'Explorador de base de datos',
          db_search_label: 'Buscar nodos',
          db_search_placeholder: 'Buscar por texto, id, entidad, resultado o DOI',
          db_search: 'Buscar',
          db_clear: 'Limpiar',
          db_prev: 'Anterior',
          db_next: 'Siguiente',
          db_close: 'Cerrar',
          db_no_rows: 'No se encontraron nodos para la busqueda actual.',
          db_open_hint: 'Abrir explorador de base de datos',
          db_meta_title: 'Metadatos de la fuente',
          db_meta_view: 'Ver metadatos completos',
          db_meta_hide: 'Ocultar metadatos',
          db_meta_loading: 'Cargando metadatos...',
          db_meta_error: 'Metadatos no disponibles',
          db_meta_not_found: 'No se encontraron metadatos de fuente para este nodo.',
          db_meta_journal: 'Revista',
          db_meta_pubdate: 'Fecha de publicacion',
          db_meta_authors: 'Autores',
          db_meta_mesh_terms: 'Terminos MeSH',
          db_meta_abstract: 'Resumen',
          yes: 'si',
          no: 'no',
          review_queue: 'Cola de revision',
          review_queue_subtitle: 'Claims que requieren revision humana',
          reviewer: 'Revisor',
          notes: 'Notas',
          approve: 'Aprobar',
          reject: 'Rechazar',
          needs_more_evidence: 'Necesita mas evidencia',
          decision_history: 'Historial de decisiones',
          no_review_flags: 'No hay alertas de revision en este momento.',
          review_decision_saved: 'Decision de revision guardada.',
          hypothesis_queue: 'Cola de hipotesis',
          promotion_controls: 'Controles de promocion',
          require_review_signoff: 'Requerir aprobacion de revision',
          enforce_causal_gate: 'Aplicar puerta causal',
          promoted_hypotheses: 'Hipotesis promovidas',
          filtered_out_controls: 'Filtradas por controles',
          no_hypotheses: 'No se promovieron hipotesis con los controles actuales.',
          no_filtered_entities: 'No hay entidades filtradas.',
          db_synced: 'BD sincronizada',
          db_out_of_sync: 'BD fuera de sincronizacion',
          db_unavailable: 'BD no disponible',
          db_popover_title: 'Estado de la base de datos',
          db_popover_total_label: 'nodos de evidencia',
          db_popover_last_sync: 'Ultima sincronizacion',
          db_popover_ready: 'Base de datos en linea y lista para consultas.',
          db_popover_waiting: 'Base de datos en linea, pendiente de primera ingesta.',
          db_popover_loading: 'Cargando estado de la base de datos...',
          db_popover_unavailable: 'Estado de la base de datos no disponible.',
          db_popover_hint: 'Haz clic para abrir el explorador de base de datos.',
          evidence_hint_idle: 'Los nodos citados apareceran aqui cuando ejecutes una consulta.',
          evidence_hint_empty: 'Este informe no cito nodos de evidencia.',
          report_title: 'Informe de sintesis',
          generated_in: 'Generado en {seconds}s',
          direct_answer: 'Respuesta directa',
          supporting_nodes: 'Nodos de evidencia de soporte',
          contradictions_uncertainty: 'Contradicciones e incertidumbre',
          next_validation_step: 'Siguiente paso de validacion',
          run_this_query: 'Ejecutar esta consulta',
          generating_report: 'Generando informe de sintesis',
          in_progress: 'En progreso',
          loading_copy: 'Analizando evidencia y redactando un informe nuevo para tu consulta.',
          type_question_first: 'Primero escribe una pregunta.',
          generating_new_report: 'Generando un nuevo informe de sintesis...',
          stream_loading_evidence: 'Cargando y filtrando evidencia...',
          stream_building_prompt: 'Construyendo prompt con evidencia...',
          stream_generating: 'Generando respuesta...',
          stream_post_processing: 'Vinculando citas y metadatos de sintesis...',
          stream_done: 'Transmision completada. {count} filas utilizadas.',
          telemetry_phase_summary: 'Fases(s): carga {loading}, prompt {prompt}, gen {gen}, post {post}, total {total}.',
          diagnostics_title: 'Diagnostico',
          diagnostics_empty: 'Sin diagnosticos por ahora.',
          rows_retrieved: 'Filas recuperadas',
          rows_cited: 'Filas citadas',
          response_mode: 'Modo de respuesta',
          response_mode_stream: 'stream',
          response_mode_sync: 'sync',
          response_mode_sync_fallback: 'sync fallback',
          guardrail_flags: 'Guardrails',
          verification_flags: 'Verification',
          failure_atlas_title: 'Atlas de fallos',
          failure_atlas_empty: 'Sin entradas en el atlas de fallos.',
          failure_atlas_total: 'Registros fallidos o negativos',
          failure_atlas_structured: 'Fallos estructurados de ensayo',
          trial_status: 'Estado del ensayo',
          termination_reason: 'Motivo de terminacion',
          primary_endpoint_result: 'Resultado del endpoint primario',
          root_cause: 'Causa raiz',
          done_rows_used: 'Listo. {count} filas utilizadas.',
          no_report_to_save: 'Aun no hay informe para guardar.',
          session_saved: 'Sesion guardada en la base de datos.',
          no_saved_sessions: 'No hay sesiones guardadas.',
          loading_sessions: 'Cargando sesiones...',
          loaded_latest_session: 'Se cargo la ultima sesion guardada.',
          filters_updated: 'Filtros actualizados. Ejecuta una consulta para refrescar los nodos citados.',
          filters_reset: 'Filtros restablecidos. Ejecuta una consulta para refrescar los nodos citados.',
          no_report_to_export: 'Aun no hay informe para exportar.',
          exported_summary: 'Resumen JSON y Markdown exportado.',
          no_citations_to_copy: 'Aun no hay citas para copiar.',
          no_supporting_ids: 'No se encontraron ids de soporte.',
          copied_claims: 'Se copiaron {count} ids con DOI.',
          settings_applied: 'Configuracion aplicada para esta sesion.',
          profile_disabled: 'Los controles de perfil no estan habilitados en modo investigador simple.',
          compare_prompt: 'Ingresa dos ids de claim para comparar.',
          shared_supporting: 'soporte compartido',
          shared_contradicting: 'contradicciones compartidas',
          follow_up: 'Siguiente paso',
          default_follow_up: 'Ejecuta una validacion dirigida para endpoints en conflicto.',
          updated: 'Actualizado',
          claim_a: 'Claim A',
          claim_b: 'Claim B',
          study_type: 'Tipo de estudio',
          effect: 'Efecto',
          use_in_compare: 'Usar en comparacion',
          start_tour: 'Iniciar tutorial',
          tutorial_title: 'Recorrido rapido: investiga con confianza',
          tutorial_back: 'Atras',
          tutorial_next: 'Siguiente',
          tutorial_finish: 'Finalizar',
          tutorial_stop: 'Detener',
          tutorial_progress: 'Paso {current} de {total}',
          tutorial_wait_for_action: 'Completa la accion resaltada para continuar.',
          tutorial_done: 'Tutorial completado. Puedes reiniciarlo en cualquier momento con Iniciar tutorial.',
          tutorial_stopped: 'Tutorial detenido. Puedes reiniciarlo con Iniciar tutorial.',
          tutorial_step_query_title: 'Paso 1: Formula una pregunta clara',
          tutorial_step_query_body: 'Usa esta caja para definir una pregunta concreta de investigacion. Mantenla breve y especifica.',
          tutorial_step_send_title: 'Paso 2: Ejecuta la investigacion',
          tutorial_step_send_body: 'Haz clic en Enviar para generar un informe de sintesis basado en evidencia. Espera a que aparezca el informe.',
          tutorial_step_report_title: 'Paso 3: Lee la sintesis',
          tutorial_step_report_body: 'Este informe es tu sintesis: respuesta directa, evidencia citada, incertidumbre y siguiente accion.',
          tutorial_step_validation_title: 'Paso 4: Seccion de validacion',
          tutorial_step_validation_body: 'Fijate en contradicciones y en Siguiente paso de validacion. Aqui decides que verificar despues.',
          tutorial_step_diagnostics_title: 'Paso 5: Area de diagnostico',
          tutorial_step_diagnostics_body: 'Diagnostico muestra como se construyo la respuesta: filas recuperadas, citas usadas, tiempos y guardrails.',
          tutorial_step_save_title: 'Paso 6: Guardar sesion',
          tutorial_step_save_body: 'Guardar sesion conserva el estado actual de la investigacion para continuar luego sin perder contexto.',
          tutorial_step_export_title: 'Paso 7: Exportar resumen',
          tutorial_step_export_body: 'Exportar resumen descarga la sintesis en JSON y Markdown para reporte y colaboracion.',
          tutorial_step_copy_title: 'Paso 8: Copiar citas',
          tutorial_step_copy_body: 'Copiar citas coloca en portapapeles los IDs de claim y DOIs de soporte para referenciar rapido.',
          tutorial_step_db_open_title: 'Paso 9: Abrir explorador de evidencias',
          tutorial_step_db_open_body: 'Haz clic en BD sincronizada para abrir el explorador de base de evidencias e inspeccionar claims indexados.',
          tutorial_step_db_explorer_title: 'Paso 10: Explorar base de evidencias',
          tutorial_step_db_explorer_body: 'Usa este explorador para buscar claims, revisar metadatos y validar procedencia antes de decidir.',
          tutorial_step_sessions_nav_title: 'Paso 11: Abrir sesiones guardadas',
          tutorial_step_sessions_nav_body: 'Ve a Sesiones guardadas para recuperar investigaciones previas y su contexto completo.',
          tutorial_step_sessions_list_title: 'Paso 12: Lista de sesiones guardadas',
          tutorial_step_sessions_list_body: 'Selecciona una sesion para restaurar pregunta, sintesis y evidencia citada con un clic.',
          tutorial_step_hypothesis_open_title: 'Paso 13: Abrir cola de hipotesis',
          tutorial_step_hypothesis_open_body: 'La cola de hipotesis propone candidatos priorizados a partir de la evidencia y los controles.',
          tutorial_step_hypothesis_queue_title: 'Paso 14: Como funciona la cola de hipotesis',
          tutorial_step_hypothesis_queue_body: 'Hipotesis promovidas son candidatas para accionar ahora. Entidades filtradas fueron excluidas por controles.',
          tutorial_step_review_open_title: 'Paso 15: Abrir cola de revision',
          tutorial_step_review_open_body: 'La cola de revision concentra claims de mayor riesgo o incertidumbre para decision humana.',
          tutorial_step_review_queue_title: 'Paso 16: Como funciona la cola de revision',
          tutorial_step_review_queue_body: 'Selecciona un claim, agrega notas y registra aprobar/rechazar/mas evidencia para dejar trazabilidad.',
          tutorial_step_evidence_title: 'Paso 17: Revisa nodos de evidencia',
          tutorial_step_evidence_body: 'Estos son nodos citados. Verde suele apoyar, rojo contradice y amarillo es mixto/neutral.',
          tutorial_step_lineage_title: 'Paso 18: Abre detalles de linaje',
          tutorial_step_lineage_body: 'Haz clic en un nodo para revisar linaje de citas y contexto de soporte vs contradiccion.',
          tutorial_step_filters_title: 'Paso 19: Ajusta filtros',
          tutorial_step_filters_body: 'Ajusta filtros para acotar calidad y alcance de evidencia, luego haz clic en Aplicar.',
          tutorial_step_compare_title: 'Paso 20: Compara dos claims',
          tutorial_step_compare_body: 'Usa comparar para revisar solapamientos y contradicciones entre dos IDs de claim.',
          tutorial_controls_label: 'Tutorial',
          tutorial_short_button: 'Tutorial corto',
          tutorial_long_button: 'Tutorial largo',
          tutorial_mode_short: 'Tour corto',
          tutorial_mode_full: 'Tour completo',
          tutorial_mode_label: 'Modo del tutorial',
        },
      };

      function t(key) {
        const lang = Object.prototype.hasOwnProperty.call(I18N, state.language) ? state.language : 'en';
        return I18N[lang][key] || I18N.en[key] || key;
      }

      function tf(key, vars) {
        return t(key).replace(/\{(\w+)\}/g, function(_, name) {
          return Object.prototype.hasOwnProperty.call(vars || {}, name) ? String(vars[name]) : '';
        });
      }

      function byId(id) { return document.getElementById(id); }

      function escapeHtml(input) {
        return String(input || '')
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/\"/g, '&quot;')
          .replace(/'/g, '&#39;');
      }

      function inlineMarkdown(text) {
        let out = escapeHtml(text);
        out = out.replace(/`([^`]+)`/g, function(_, g1) { return '<code>' + g1 + '</code>'; });
        out = out.replace(/\*\*([^*]+)\*\*/g, function(_, g1) { return '<strong>' + g1 + '</strong>'; });
        out = out.replace(/\*([^*]+)\*/g, function(_, g1) { return '<em>' + g1 + '</em>'; });
        return out;
      }

      function renderMarkdown(text) {
        const lines = String(text || '').replace(/\\r\\n/g, '\\n').split('\\n');
        const html = [];
        let inUl = false;
        let inOl = false;

        function closeLists() {
          if (inUl) {
            html.push('</ul>');
            inUl = false;
          }
          if (inOl) {
            html.push('</ol>');
            inOl = false;
          }
        }

        for (const rawLine of lines) {
          const line = rawLine.trimEnd();
          const trimmed = line.trim();

          if (!trimmed) {
            closeLists();
            continue;
          }

          const headingMatch = trimmed.match(/^(#{1,4})\s+(.*)$$/);
          if (headingMatch) {
            closeLists();
            const level = headingMatch[1].length;
            html.push('<h' + level + '>' + inlineMarkdown(headingMatch[2]) + '</h' + level + '>');
            continue;
          }

          const ulMatch = trimmed.match(/^[-*]\s+(.*)$$/);
          if (ulMatch) {
            if (inOl) {
              html.push('</ol>');
              inOl = false;
            }
            if (!inUl) {
              html.push('<ul>');
              inUl = true;
            }
            html.push('<li>' + inlineMarkdown(ulMatch[1]) + '</li>');
            continue;
          }

          const olMatch = trimmed.match(/^\d+\.\s+(.*)$$/);
          if (olMatch) {
            if (inUl) {
              html.push('</ul>');
              inUl = false;
            }
            if (!inOl) {
              html.push('<ol>');
              inOl = true;
            }
            html.push('<li>' + inlineMarkdown(olMatch[1]) + '</li>');
            continue;
          }

          closeLists();
          html.push('<p>' + inlineMarkdown(trimmed) + '</p>');
        }

        closeLists();
        return html.join('');
      }

      function applyTranslations() {
        const textById = {
          navAssistant: t('nav_assistant'),
          navSessions: t('nav_sessions'),
          filterTitle: t('filter_title'),
          evidenceTypeLabel: t('evidence_type'),
          publicationDateLabel: t('publication_date'),
          highlightContradictionsLabel: t('highlight_contradictions'),
          resetFilters: t('reset'),
          applyFilters: t('apply'),
          queryEvidenceLabel: t('query_evidence'),
          savedSessionsLabel: t('saved_sessions'),
          refreshSessions: t('refresh'),
          evidenceNodesLabel: t('evidence_nodes'),
          evidenceFoundSuffix: t('found'),
          compareNodesLabel: t('compare_nodes'),
          runCompare: t('run_compare'),
          diagnosticsTitle: t('diagnostics_title'),
          refreshDiagnostics: t('refresh'),
          failureAtlasTitle: t('failure_atlas_title'),
          refreshFailureAtlas: t('refresh'),
          settingsTitle: t('settings'),
          closeSettings: t('close'),
          settingsLanguageLabel: t('language'),
          tutorialControlsLabel: t('tutorial_controls_label'),
          startShortTutorial: t('tutorial_short_button'),
          startLongTutorial: t('tutorial_long_button'),
          settingsModelLabel: t('model'),
          settingsHostLabel: t('host'),
          settingsContextLabel: t('context_limit'),
          settingsTemperatureLabel: t('temperature'),
          settingsTimeoutLabel: t('timeout_seconds'),
          applySettings: t('apply_settings'),
          saveSession: t('save_session'),
          exportSummary: t('export_summary'),
          copyCitations: t('copy_citations'),
          dbExplorerTitle: t('db_explorer_title'),
          dbSearchLabel: t('db_search_label'),
          dbSearchButton: t('db_search'),
          dbClearSearch: t('db_clear'),
          dbPrevPage: t('db_prev'),
          dbNextPage: t('db_next'),
          closeDbExplorer: t('db_close'),
          reviewQueueTitle: t('review_queue'),
          reviewQueueSubtitle: t('review_queue_subtitle'),
          refreshReviewQueue: t('refresh'),
          reviewerLabel: t('reviewer'),
          reviewNotesLabel: t('notes'),
          approveClaim: t('approve'),
          rejectClaim: t('reject'),
          needsEvidenceClaim: t('needs_more_evidence'),
          reviewHistoryLabel: t('decision_history'),
          closeReviewQueue: t('close'),
          hypothesisQueueTitle: t('hypothesis_queue'),
          hypothesisControlsLabel: t('promotion_controls'),
          refreshHypothesisQueue: t('refresh'),
          hypoRequireSignoffLabel: t('require_review_signoff'),
          hypoEnforceCausalGateLabel: t('enforce_causal_gate'),
          hypothesisPromotedLabel: t('promoted_hypotheses'),
          hypothesisRemovedLabel: t('filtered_out_controls'),
          closeHypothesisQueue: t('close'),
          tutorialTitle: t('tutorial_title'),
          tutorialBack: t('tutorial_back'),
          tutorialStop: t('tutorial_stop'),
          tutorialNext: t('tutorial_next'),
        };

        Object.keys(textById).forEach((id) => {
          const el = byId(id);
          if (el) {
            el.textContent = textById[id];
          }
        });

        const q = byId('question');
        if (q) {
          q.placeholder = t('question_placeholder');
        }
        const dbSearch = byId('dbSearchInput');
        if (dbSearch) {
          dbSearch.placeholder = t('db_search_placeholder');
        }
        const dbStatus = byId('status-db');
        if (dbStatus) {
          dbStatus.title = t('db_popover_hint');
        }
        const dbPopoverTitle = byId('statusDbPopoverTitle');
        if (dbPopoverTitle) {
          dbPopoverTitle.textContent = t('db_popover_title');
        }
        if (state.dbStatusSnapshot) {
          renderDbStatusPopover(state.dbStatusSnapshot);
        }
        const reviewerInput = byId('reviewerInput');
        if (reviewerInput) {
          reviewerInput.placeholder = 'reviewer_a';
        }
        const notesInput = byId('reviewNotesInput');
        if (notesInput) {
          notesInput.placeholder = t('notes');
        }
        const profileBtn = byId('openProfile');
        if (profileBtn) {
          profileBtn.title = t('review_queue');
        }
        const tutorialModeSelect = byId('tutorialModeSelect');
        if (tutorialModeSelect) {
          tutorialModeSelect.title = t('tutorial_mode_label');
          const shortOption = tutorialModeSelect.querySelector('option[value="short"]');
          const fullOption = tutorialModeSelect.querySelector('option[value="full"]');
          if (shortOption) {
            shortOption.textContent = t('tutorial_mode_short');
          }
          if (fullOption) {
            fullOption.textContent = t('tutorial_mode_full');
          }
        }
        const hypothesisBtn = byId('openHypothesisQueue');
        if (hypothesisBtn) {
          hypothesisBtn.title = t('hypothesis_queue');
        }

        const minRelLabel = byId('minReliabilityLabel');
        if (minRelLabel) {
          minRelLabel.innerHTML = t('min_reliability') + ' <span id="relLabel" class="mono" style="color:var(--primary-strong)">' + Math.round(Number(byId('minRel').value || '0') * 100) + '%</span>';
        }

        if (state.lastReport) {
          renderReport(state.lastReport);
        }
        renderEvidenceRows(state.evidenceRows || []);
        if (state.currentComparePayload) {
          renderComparePayload(state.currentComparePayload);
        }
      }

      function setChatStatus(text, isError = false) {
        const el = byId('chatStatus');
        if (!el) {
          return;
        }
        el.textContent = text;
        el.classList.remove('hidden');
        el.classList.toggle('error', isError);
      }

      function updateAuthUI() {
        const badge = byId('authBadge');
        const logoutBtn = byId('logoutBtn');
        const navSessions = byId('navSessions');
        const sendBtn = byId('send');
        const canUseApp = !state.authEnabled || state.isAuthenticated;
        if (badge) {
          badge.textContent = state.isAuthenticated && state.currentUser
            ? String(state.currentUser.email || state.currentUser.user_id || 'user')
            : 'guest';
        }
        if (logoutBtn) {
          logoutBtn.classList.toggle('hidden', !state.isAuthenticated);
        }
        if (navSessions) {
          navSessions.disabled = !canUseApp;
        }
        if (sendBtn) {
          sendBtn.disabled = !canUseApp;
        }
      }

      async function fetchAuthStatus() {
        if (!state.authEnabled) {
          state.isAuthenticated = true;
          state.currentUser = { user_id: 'anonymous', email: 'anonymous@local' };
          state.csrfToken = '';
          updateAuthUI();
          return;
        }
        try {
          const resp = await fetch('/api/auth/status');
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.error || 'auth status failed');
          state.isAuthenticated = Boolean(data.authenticated);
          state.currentUser = data.user || null;
          state.csrfToken = String(data.csrf_token || '');
          updateAuthUI();
        } catch (_) {
          state.isAuthenticated = false;
          state.currentUser = null;
          state.csrfToken = '';
          updateAuthUI();
        }
      }

      function startAuthRefreshLoop() {
        if (!state.authEnabled) {
          return;
        }
        window.setInterval(() => {
          if (state.isAuthenticated) {
            fetchAuthStatus().catch(() => undefined);
          }
        }, 5 * 60 * 1000);
      }

      async function logout() {
        try {
          await fetch('/api/auth/logout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
          });
        } catch (_) {}
        state.isAuthenticated = false;
        state.currentUser = null;
        state.csrfToken = '';
        state.activeSessionId = null;
        state.lastReport = null;
        state.messages = [];
        updateAuthUI();
        if (state.authEnabled) {
          window.location.assign('/login');
        }
      }

      function renderDiagnosticsRows(rows) {
        const root = byId('diagnosticsList');
        if (!root) {
          return;
        }
        if (!Array.isArray(rows) || !rows.length) {
          root.textContent = t('diagnostics_empty');
          return;
        }

        const chunks = rows.map((trace) => {
          const phase = trace && typeof trace.phase_seconds === 'object' ? trace.phase_seconds : {};
          const toFixed = (value) => {
            const num = Number(value);
            return Number.isFinite(num) ? num.toFixed(2) : '0.00';
          };
          const mode = trace.fallback_used
            ? t('response_mode_sync_fallback')
            : (trace.mode === 'stream' ? t('response_mode_stream') : t('response_mode_sync'));
          const flags = Array.isArray(trace.guardrail_flags) && trace.guardrail_flags.length
            ? trace.guardrail_flags.join(', ')
            : '-';
          const verificationFlags = Array.isArray(trace.verification_flags) && trace.verification_flags.length
            ? trace.verification_flags.join(', ')
            : '-';

          return (
            '<div class="tiny" style="border:1px solid var(--border);border-radius:8px;padding:8px;margin-bottom:8px;background:#fff">' +
              '<div style="display:flex;justify-content:space-between;gap:8px"><span class="mono">' + escapeHtml(String(trace.trace_id || 'trace')) + '</span><span>' + escapeHtml(mode) + '</span></div>' +
              '<div class="muted" style="margin-top:4px">' +
                tf('telemetry_phase_summary', {
                  loading: toFixed(phase.loading_evidence),
                  prompt: toFixed(phase.building_prompt),
                  gen: toFixed(phase.generating),
                  post: toFixed(phase.post_processing),
                  total: toFixed(trace.total_seconds),
                }) +
              '</div>' +
              '<div style="margin-top:4px">' + t('rows_retrieved') + ': ' + Number(trace.evidence_count || 0) + ' | ' + t('rows_cited') + ': ' + Number(trace.cited_evidence_count || 0) + '</div>' +
              '<div style="margin-top:2px">' + t('guardrail_flags') + ': ' + escapeHtml(flags) + '</div>' +
              '<div style="margin-top:2px">' + t('verification_flags') + ': ' + escapeHtml(verificationFlags) + '</div>' +
            '</div>'
          );
        });

        root.innerHTML = chunks.join('');
      }

      async function fetchRecentDiagnostics() {
        const root = byId('diagnosticsList');
        if (root) {
          root.textContent = t('loading_copy');
        }
        try {
          const resp = await fetch('/api/telemetry/recent?limit=8');
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.error || 'diagnostics failed');
          renderDiagnosticsRows(Array.isArray(data.traces) ? data.traces : []);
        } catch (error) {
          if (root) {
            root.textContent = String(error);
          }
        }
      }

      function renderFailureAtlasRows(atlas) {
        const root = byId('failureAtlasList');
        if (!root) {
          return;
        }
        const entries = atlas && Array.isArray(atlas.entries) ? atlas.entries : [];
        if (!entries.length) {
          root.textContent = t('failure_atlas_empty');
          return;
        }

        const summary = (
          '<div class="tiny muted" style="margin-bottom:8px">' +
            escapeHtml(t('failure_atlas_total')) + ': ' + Number(atlas.total_failed_or_negative_records || 0) +
            ' | ' + escapeHtml(t('failure_atlas_structured')) + ': ' + Number(atlas.structured_trial_failures || 0) +
          '</div>'
        );

        const chunks = entries.slice(0, 12).map((entry) => {
          const endpointResult = String(entry.primary_endpoint_result || '-');
          const trialStatus = String(entry.trial_status || '-');
          const terminationReason = String(entry.termination_reason || '-');
          const rootCause = String(entry.root_cause || '-');
          return (
            '<div class="tiny" style="border:1px solid var(--border);border-radius:8px;padding:8px;margin-bottom:8px;background:#fff">' +
              '<div style="display:flex;justify-content:space-between;gap:8px"><span class="mono">' + escapeHtml(String(entry.claim_id || 'claim')) + '</span><span>' + escapeHtml(String(entry.entity || '')) + '</span></div>' +
              '<div class="muted" style="margin-top:4px">' + escapeHtml(String(entry.outcome || '')) + '</div>' +
              '<div style="margin-top:4px">' + t('trial_status') + ': ' + escapeHtml(trialStatus) + '</div>' +
              '<div style="margin-top:2px">' + t('termination_reason') + ': ' + escapeHtml(terminationReason) + '</div>' +
              '<div style="margin-top:2px">' + t('primary_endpoint_result') + ': ' + escapeHtml(endpointResult) + '</div>' +
              '<div style="margin-top:2px">' + t('root_cause') + ': ' + escapeHtml(rootCause) + '</div>' +
            '</div>'
          );
        });

        root.innerHTML = summary + chunks.join('');
      }

      async function fetchFailureAtlas() {
        const root = byId('failureAtlasList');
        if (root) {
          root.textContent = t('loading_copy');
        }
        try {
          const resp = await fetch('/api/failure-atlas');
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.error || 'failure atlas failed');
          renderFailureAtlasRows(data);
        } catch (error) {
          if (root) {
            root.textContent = String(error);
          }
        }
      }

      function getFilters() {
        const evidenceTypes = Array.from(document.querySelectorAll('input[name="etype"]:checked')).map((el) => el.value);
        return {
          evidence_types: evidenceTypes,
          date_window: byId('dateWindow').value,
          min_reliability: Number(byId('minRel').value),
          highlight_contradictions: byId('highlightContradictions').checked,
        };
      }

      function openDrawer() {
        byId('drawerBackdrop').classList.add('open');
        byId('lineageDrawer').classList.add('open');
      }

      function closeDrawer() {
        byId('drawerBackdrop').classList.remove('open');
        byId('lineageDrawer').classList.remove('open');
      }

      function openSettingsDrawer() {
        const modal = byId('settingsDrawer');
        if (!modal) {
          return;
        }
        applySettingsFromState();
        modal.classList.add('open');
        modal.setAttribute('aria-hidden', 'false');
      }

      function closeSettingsDrawer() {
        const modal = byId('settingsDrawer');
        if (!modal) {
          return;
        }
        modal.classList.remove('open');
        modal.setAttribute('aria-hidden', 'true');
      }

      function renderDbExplorerRows(rows, total, offset, limit) {
        const root = byId('dbExplorerRows');
        const meta = byId('dbResultsMeta');
        const pageLabel = byId('dbPageLabel');
        const prev = byId('dbPrevPage');
        const next = byId('dbNextPage');

        root.innerHTML = '';
        const safeTotal = Number(total || 0);
        const safeOffset = Number(offset || 0);
        const safeLimit = Number(limit || state.dbBrowserLimit || 12);
        const start = safeTotal ? safeOffset + 1 : 0;
        const end = safeOffset + (Array.isArray(rows) ? rows.length : 0);
        meta.textContent = start + '-' + end + ' / ' + safeTotal;
        pageLabel.textContent = 'Page ' + String(Math.floor(safeOffset / safeLimit) + 1);
        prev.disabled = safeOffset <= 0;
        next.disabled = end >= safeTotal;

        if (!Array.isArray(rows) || !rows.length) {
          const empty = document.createElement('div');
          empty.className = 'small muted';
          empty.textContent = t('db_no_rows');
          root.appendChild(empty);
          return;
        }

        function listToHtml(values) {
          const safe = Array.isArray(values) ? values.filter((v) => String(v || '').trim()) : [];
          if (!safe.length) {
            return '<span class="muted">n/a</span>';
          }
          return '<ul class="db-meta-detail-list">' +
            safe.slice(0, 12).map((v) => '<li>' + escapeHtml(String(v)) + '</li>').join('') +
            '</ul>';
        }

        function renderDbMetadataDetailHtml(metadata) {
          if (!metadata || typeof metadata !== 'object') {
            return '<div class="small muted">' + t('db_meta_not_found') + '</div>';
          }
          const provenance = metadata && typeof metadata.metadata === 'object' ? metadata.metadata : {};
          const apiEndpoint = String(provenance.api_endpoint || 'n/a');
          const queryUsed = String(provenance.query_used || 'n/a');
          const sourceVersion = String(provenance.source_version || 'n/a');
          const sourceLicense = String(provenance.source_license || 'n/a');
          const extractedAt = String(provenance.extracted_at || 'n/a');
          return (
            '<div class="db-node-grid tiny">' +
              '<div><strong>' + t('db_meta_journal') + ':</strong> ' + escapeHtml(String(metadata.journal || 'n/a')) + '</div>' +
              '<div><strong>' + t('db_meta_pubdate') + ':</strong> ' + escapeHtml(String(metadata.pubdate || 'n/a')) + '</div>' +
              '<div style="grid-column:1 / -1"><strong>API endpoint:</strong> ' + escapeHtml(apiEndpoint) + '</div>' +
              '<div><strong>Query used:</strong> ' + escapeHtml(queryUsed) + '</div>' +
              '<div><strong>Source version:</strong> ' + escapeHtml(sourceVersion) + '</div>' +
              '<div><strong>Source license:</strong> ' + escapeHtml(sourceLicense) + '</div>' +
              '<div><strong>Extracted at:</strong> ' + escapeHtml(extractedAt) + '</div>' +
              '<div style="grid-column:1 / -1"><strong>' + t('db_meta_abstract') + ':</strong> ' + escapeHtml(String(metadata.abstract_text || '')) + '</div>' +
              '<div style="grid-column:1 / -1"><strong>' + t('db_meta_authors') + ':</strong> ' + listToHtml(metadata.authors) + '</div>' +
              '<div style="grid-column:1 / -1"><strong>' + t('db_meta_mesh_terms') + ':</strong> ' + listToHtml(metadata.mesh_terms) + '</div>' +
            '</div>'
          );
        }

        rows.forEach((row) => {
          const card = document.createElement('article');
          card.className = 'db-node';
          const rawReliability = row ? row.reliability_score : undefined;
          const hasReliability = rawReliability !== null && rawReliability !== undefined && String(rawReliability).trim() !== '';
          const reliability = hasReliability ? Number(rawReliability) : NaN;
          const reliabilityLabel = Number.isFinite(reliability) ? Math.round(reliability * 100) + '%' : '';
          const claimId = String(row.claim_id || '');
          const sourceMeta = row && typeof row.source_metadata === 'object' ? row.source_metadata : null;
          const metadataHtml = sourceMeta
            ? (
                '<div class="db-node-grid tiny db-meta-summary">' +
                  '<div style="grid-column:1 / -1"><strong>' + t('db_meta_title') + ':</strong></div>' +
                  '<div><strong>' + t('db_meta_journal') + ':</strong> ' + escapeHtml(String(sourceMeta.journal || 'n/a')) + '</div>' +
                  '<div><strong>' + t('db_meta_pubdate') + ':</strong> ' + escapeHtml(String(sourceMeta.pubdate || 'n/a')) + '</div>' +
                  '<div><strong>' + t('db_meta_authors') + ':</strong> ' + escapeHtml(String(sourceMeta.authors_count || 0)) + '</div>' +
                  '<div><strong>' + t('db_meta_mesh_terms') + ':</strong> ' + escapeHtml(String(sourceMeta.mesh_terms_count || 0)) + '</div>' +
                  '<div style="grid-column:1 / -1"><strong>' + t('db_meta_abstract') + ':</strong> ' + (sourceMeta.has_abstract ? t('yes') : t('no')) + '</div>' +
                  '<div style="grid-column:1 / -1"><strong>API:</strong> ' + escapeHtml(String(sourceMeta.api_endpoint || 'n/a')) + '</div>' +
                  '<div style="grid-column:1 / -1"><strong>Query:</strong> ' + escapeHtml(String(sourceMeta.query_used || 'n/a')) + '</div>' +
                '</div>'
              )
            : '';
          card.innerHTML =
            '<div class="db-node-head">' +
              '<span class="mono" style="padding:2px 8px;border-radius:4px;border:1px solid var(--border);background:#eef2f7">' + escapeHtml(String(row.claim_id || 'n/a')) + '</span>' +
              (reliabilityLabel
                ? '<span class="mono" style="padding:2px 8px;border-radius:4px;border:1px solid var(--border-strong);background:#f8fafc">' + escapeHtml(reliabilityLabel) + '</span>'
                : '') +
            '</div>' +
            '<div class="small" style="line-height:1.45">' + escapeHtml(String(row.claim_text || '')) + '</div>' +
            '<div class="db-node-grid tiny muted">' +
              '<div><strong>Entity:</strong> ' + escapeHtml(String(row.entity || 'n/a')) + '</div>' +
              '<div><strong>Outcome:</strong> ' + escapeHtml(String(row.outcome || 'n/a')) + '</div>' +
              '<div><strong>Effect:</strong> ' + escapeHtml(String(row.effect_direction || 'n/a')) + '</div>' +
              '<div><strong>Study:</strong> ' + escapeHtml(String(row.study_type || 'n/a')) + '</div>' +
              '<div><strong>Causal type:</strong> ' + escapeHtml(String(row.causal_evidence_type || 'n/a')) + '</div>' +
              '<div><strong>Year:</strong> ' + escapeHtml(String(row.year || 'n/a')) + '</div>' +
              '<div style="grid-column:1 / -1"><strong>Source:</strong> ' +
                (row.source_url
                  ? '<a class="mono" href="' + escapeHtml(String(row.source_url)) + '" target="_blank" rel="noopener noreferrer" style="color:var(--primary-strong)">' + escapeHtml(String(row.source_doi || row.source_url || 'n/a')) + '</a>'
                  : '<span class="mono">' + escapeHtml(String(row.source_doi || 'n/a')) + '</span>') +
              '</div>' +
            '</div>' +
            metadataHtml +
            '<div class="row" style="justify-content:flex-end">' +
              '<button class="btn tiny db-meta-toggle" data-claim-id="' + escapeHtml(claimId) + '">' + t('db_meta_view') + '</button>' +
            '</div>' +
            '<div class="db-meta-detail hidden" data-claim-id="' + escapeHtml(claimId) + '"></div>';

          const toggle = card.querySelector('.db-meta-toggle');
          const detail = card.querySelector('.db-meta-detail');
          if (toggle && detail) {
            toggle.addEventListener('click', async () => {
              const opened = !detail.classList.contains('hidden');
              if (opened) {
                detail.classList.add('hidden');
                detail.innerHTML = '';
                toggle.textContent = t('db_meta_view');
                return;
              }

              detail.classList.remove('hidden');
              toggle.textContent = t('db_meta_hide');
              detail.innerHTML = '<div class="small muted">' + t('db_meta_loading') + '</div>';

              if (Object.prototype.hasOwnProperty.call(state.dbMetadataCache, claimId)) {
                detail.innerHTML = renderDbMetadataDetailHtml(state.dbMetadataCache[claimId]);
                return;
              }

              try {
                const resp = await fetch('/api/database/node/metadata', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ claim_id: claimId }),
                });
                const data = await resp.json();
                if (!resp.ok) throw new Error(data.error || 'metadata fetch failed');
                const metadata = data && data.found ? data.metadata : null;
                state.dbMetadataCache[claimId] = metadata;
                detail.innerHTML = renderDbMetadataDetailHtml(metadata);
              } catch (error) {
                detail.innerHTML = '<div class="small" style="color:#b91c1c">' + t('db_meta_error') + ': ' + escapeHtml(String(error)) + '</div>';
              }
            });
          }
          root.appendChild(card);
        });
      }

      async function fetchDbExplorerRows(resetOffset = false) {
        if (resetOffset) {
          state.dbBrowserOffset = 0;
        }
        const status = byId('dbExplorerStatus');
        const query = String(byId('dbSearchInput').value || '').trim();
        state.dbBrowserQuery = query;
        status.textContent = 'Loading...';
        try {
          const resp = await fetch('/api/database/nodes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              query: state.dbBrowserQuery,
              limit: state.dbBrowserLimit,
              offset: state.dbBrowserOffset,
            }),
          });
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.error || 'database fetch failed');
          state.dbBrowserTotal = Number(data.total || 0);
          renderDbExplorerRows(data.rows || [], data.total || 0, data.offset || 0, data.limit || state.dbBrowserLimit);
          status.textContent = '';
        } catch (error) {
          status.textContent = String(error);
        }
      }

      function openDbExplorer() {
        const modal = byId('dbExplorerModal');
        if (!modal) {
          return;
        }
        modal.classList.add('open');
        modal.setAttribute('aria-hidden', 'false');
        tutorialSignal('db_explorer_opened');
        fetchDbExplorerRows(true);
      }

      function closeDbExplorer() {
        const modal = byId('dbExplorerModal');
        if (!modal) {
          return;
        }
        modal.classList.remove('open');
        modal.setAttribute('aria-hidden', 'true');
      }

      function renderReviewHistory(rows) {
        const root = byId('reviewHistoryList');
        root.innerHTML = '';
        const safeRows = Array.isArray(rows) ? rows : [];
        if (!safeRows.length) {
          root.textContent = '-';
          return;
        }
        safeRows.slice(0, 8).forEach((row) => {
          const line = document.createElement('div');
          line.className = 'tiny';
          line.textContent =
            String(row.decided_at || '') + ' | ' +
            String(row.decision || 'n/a') + ' | ' +
            String(row.reviewer || 'n/a') +
            (row.notes ? ' | ' + String(row.notes) : '');
          root.appendChild(line);
        });
      }

      async function fetchReviewHistory(claimId) {
        const status = byId('reviewDecisionStatus');
        if (!claimId) {
          renderReviewHistory([]);
          return;
        }
        try {
          const resp = await fetch('/api/review/decisions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ claim_id: claimId, limit: 20 }),
          });
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.error || 'review history fetch failed');
          renderReviewHistory(data.rows || []);
        } catch (error) {
          status.textContent = String(error);
        }
      }

      function selectReviewClaim(claimId) {
        state.selectedReviewClaimId = String(claimId || '');
        byId('reviewSelectedClaim').textContent = state.selectedReviewClaimId || '-';
        Array.from(document.querySelectorAll('.review-item')).forEach((node) => {
          node.classList.toggle('active', node.getAttribute('data-claim-id') === state.selectedReviewClaimId);
        });
        fetchReviewHistory(state.selectedReviewClaimId);
      }

      function renderReviewFlags(rows) {
        const root = byId('reviewFlagsList');
        root.innerHTML = '';
        const safeRows = Array.isArray(rows) ? rows : [];
        if (!safeRows.length) {
          const empty = document.createElement('div');
          empty.className = 'small muted';
          empty.textContent = t('no_review_flags');
          root.appendChild(empty);
          byId('reviewSelectedClaim').textContent = '-';
          renderReviewHistory([]);
          return;
        }

        safeRows.forEach((row, index) => {
          const item = document.createElement('button');
          item.className = 'review-item';
          item.setAttribute('data-claim-id', String(row.claim_id || ''));
          item.type = 'button';
          const reasons = Array.isArray(row.reasons) ? row.reasons : [];
          item.innerHTML =
            '<div class="db-node-head">' +
              '<span class="mono">' + escapeHtml(String(row.claim_id || 'n/a')) + '</span>' +
              '<span class="review-chip">risk ' + escapeHtml(String(Math.round(Number(row.risk_score || 0) * 100))) + '%</span>' +
            '</div>' +
            '<div class="tiny muted">' + escapeHtml(String(row.entity || 'n/a')) + '</div>' +
            '<div class="review-meta">' +
              '<span class="review-chip">delta ' + escapeHtml(String(row.confidence_delta || 0)) + '</span>' +
              '<span class="review-chip">density ' + escapeHtml(String(row.contradiction_density || 0)) + '</span>' +
            '</div>' +
            '<div class="tiny">' + escapeHtml(reasons.join('; ') || '-') + '</div>';
          item.addEventListener('click', () => selectReviewClaim(String(row.claim_id || '')));
          root.appendChild(item);

          if (index === 0 && !state.selectedReviewClaimId) {
            state.selectedReviewClaimId = String(row.claim_id || '');
          }
        });

        selectReviewClaim(state.selectedReviewClaimId || String(safeRows[0].claim_id || ''));
      }

      async function fetchReviewFlags() {
        const status = byId('reviewDecisionStatus');
        status.textContent = 'Loading...';
        try {
          const resp = await fetch('/api/review/flags', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
          });
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.error || 'review flags fetch failed');
          state.reviewFlags = Array.isArray(data.flags) ? data.flags : [];
          if (!state.reviewFlags.some((row) => String(row.claim_id || '') === state.selectedReviewClaimId)) {
            state.selectedReviewClaimId = '';
          }
          renderReviewFlags(state.reviewFlags);
          status.textContent = '';
        } catch (error) {
          status.textContent = String(error);
        }
      }

      async function submitReviewDecision(decision) {
        const claimId = String(state.selectedReviewClaimId || '').trim();
        if (!claimId) {
          byId('reviewDecisionStatus').textContent = 'Select a claim first.';
          return;
        }
        const reviewer = String(byId('reviewerInput').value || '').trim() || 'investigator_ui';
        const notes = String(byId('reviewNotesInput').value || '').trim();
        const status = byId('reviewDecisionStatus');
        status.textContent = 'Saving...';
        try {
          const resp = await fetch('/api/review/decision', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              claim_id: claimId,
              decision,
              reviewer,
              notes,
            }),
          });
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.error || 'review decision failed');
          status.textContent = t('review_decision_saved');
          byId('reviewNotesInput').value = '';
          await fetchReviewFlags();
          await fetchReviewHistory(claimId);
          if (byId('hypothesisQueueModal').classList.contains('open')) {
            await fetchHypothesisQueue();
          }
        } catch (error) {
          status.textContent = String(error);
        }
      }

      function openReviewQueue() {
        const modal = byId('reviewQueueModal');
        if (!modal) {
          return;
        }
        modal.classList.add('open');
        modal.setAttribute('aria-hidden', 'false');
        tutorialSignal('review_queue_opened');
        fetchReviewFlags();
      }

      function closeReviewQueue() {
        const modal = byId('reviewQueueModal');
        if (!modal) {
          return;
        }
        modal.classList.remove('open');
        modal.setAttribute('aria-hidden', 'true');
      }

      function renderHypothesisQueue(payload) {
        const list = byId('hypothesisQueueList');
        const removed = byId('hypothesisRemovedList');
        const meta = byId('hypothesisMeta');
        const rows = Array.isArray(payload.queue) ? payload.queue : [];
        const removedEntities = Array.isArray(payload.removed_entities) ? payload.removed_entities : [];

        list.innerHTML = '';
        removed.innerHTML = '';
        meta.textContent = 'promoted ' + String(rows.length) + ' / baseline ' + String(Number(payload.baseline_total || 0));

        if (!rows.length) {
          const empty = document.createElement('div');
          empty.className = 'small muted';
          empty.textContent = t('no_hypotheses');
          list.appendChild(empty);
        } else {
          rows.forEach((row) => {
            const card = document.createElement('article');
            card.className = 'hypo-card';
            const supportCount = Array.isArray(row.supporting_evidence) ? row.supporting_evidence.length : 0;
            const contraCount = Array.isArray(row.contradictory_evidence) ? row.contradictory_evidence.length : 0;
            card.innerHTML =
              '<div class="db-node-head">' +
                '<strong>' + escapeHtml(String(row.entity || 'n/a')) + '</strong>' +
                '<span class="review-chip">priority ' + escapeHtml(String(Math.round(Number(row.priority_score || 0) * 100))) + '%</span>' +
              '</div>' +
              '<div class="small">' + escapeHtml(String(row.hypothesis || '')) + '</div>' +
              '<div class="tiny muted">support ' + supportCount + ' | contradict ' + contraCount + ' | causal risk ' + escapeHtml(String(row.causal_risk_score || 0)) + ' | trial feasibility ' + escapeHtml(String(row.trial_feasibility_score || 0)) + '</div>';
            list.appendChild(card);
          });
        }

        if (!removedEntities.length) {
          const empty = document.createElement('div');
          empty.className = 'small muted';
          empty.textContent = t('no_filtered_entities');
          removed.appendChild(empty);
        } else {
          removedEntities.forEach((entity) => {
            const card = document.createElement('article');
            card.className = 'hypo-removed';
            card.textContent = String(entity);
            removed.appendChild(card);
          });
        }
      }

      async function fetchHypothesisQueue() {
        const requireSignoff = byId('hypoRequireSignoff').checked;
        const enforceGate = byId('hypoEnforceCausalGate').checked;
        const meta = byId('hypothesisMeta');
        meta.textContent = 'Loading...';
        try {
          const resp = await fetch('/api/hypothesis/queue', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              limit: state.hypothesisLimit,
              require_review_signoff: requireSignoff,
              enforce_causal_gate: enforceGate,
            }),
          });
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.error || 'hypothesis queue failed');
          state.hypothesisRows = Array.isArray(data.queue) ? data.queue : [];
          state.hypothesisRemovedEntities = Array.isArray(data.removed_entities) ? data.removed_entities : [];
          renderHypothesisQueue(data);
        } catch (error) {
          meta.textContent = String(error);
        }
      }

      function openHypothesisQueue() {
        const modal = byId('hypothesisQueueModal');
        if (!modal) {
          return;
        }
        modal.classList.add('open');
        modal.setAttribute('aria-hidden', 'false');
        tutorialSignal('hypothesis_queue_opened');
        fetchHypothesisQueue();
      }

      function closeHypothesisQueue() {
        const modal = byId('hypothesisQueueModal');
        if (!modal) {
          return;
        }
        modal.classList.remove('open');
        modal.setAttribute('aria-hidden', 'true');
      }

      function renderLineageDrawer(payload) {
        const claim = payload.claim || {};
        const lineage = payload.lineage || {};
        const counts = payload.lineage_counts || {};

        byId('drawerTitle').textContent = 'Claim ' + (claim.claim_id || 'N/A');
        const body = byId('drawerBody');
        body.innerHTML = '';

        const claimCard = document.createElement('div');
        claimCard.className = 'section';
        claimCard.innerHTML =
          '<h4>Claim</h4>' +
          '<div class="small">' + (claim.claim_text || 'No claim text available.') + '</div>' +
          '<div class="tiny muted" style="margin-top:8px">' +
          'Entity: ' + (claim.entity || 'n/a') + ' | Outcome: ' + (claim.outcome || 'n/a') +
          ' | Reliability: ' + Number(claim.reliability_score || 0).toFixed(2) +
          '</div>';

        const summaryCard = document.createElement('div');
        summaryCard.className = 'section';
        summaryCard.innerHTML =
          '<h4>Lineage counts</h4>' +
          '<div class="chips">' +
          '<span class="chip">Supporting: ' + Number(counts.supporting || 0) + '</span>' +
          '<span class="chip">Contradicting: ' + Number(counts.contradicting || 0) + '</span>' +
          '<span class="chip">Neutral: ' + Number(counts.neutral || 0) + '</span>' +
          '</div>';

        function buildListCard(title, rows) {
          const card = document.createElement('div');
          card.className = 'section';
          card.innerHTML = '<h4>' + title + '</h4>';
          const wrap = document.createElement('div');
          wrap.className = 'drawer-list';
          if (!rows.length) {
            const empty = document.createElement('div');
            empty.className = 'small muted';
            empty.textContent = 'No rows.';
            wrap.appendChild(empty);
          } else {
            rows.slice(0, 10).forEach((row) => {
              const item = document.createElement('div');
              item.className = 'drawer-item';
              item.innerHTML =
                '<div class="mono">' + (row.claim_id || 'n/a') + '</div>' +
                '<div class="tiny muted" style="margin-top:4px">' +
                (row.source_doi || 'no-doi') +
                ' | reliability ' + Number(row.reliability_score || 0).toFixed(2) +
                '</div>';
              wrap.appendChild(item);
            });
          }
          card.appendChild(wrap);
          return card;
        }

        body.appendChild(claimCard);
        body.appendChild(summaryCard);
        body.appendChild(buildListCard('Supporting citations', Array.isArray(lineage.supporting_citations) ? lineage.supporting_citations : []));
        body.appendChild(buildListCard('Contradicting citations', Array.isArray(lineage.contradicting_citations) ? lineage.contradicting_citations : []));
        body.appendChild(buildListCard('Neutral citations', Array.isArray(lineage.neutral_citations) ? lineage.neutral_citations : []));
      }

      async function fetchLineage(claimId) {
        try {
          const resp = await fetch('/api/evidence/' + encodeURIComponent(claimId));
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.error || 'lineage fetch failed');
          renderLineageDrawer(data);
          openDrawer();
        } catch (error) {
          setChatStatus(String(error), true);
        }
      }

      function getEvidenceScoreStyle(index, total) {
        if (index <= Math.max(0, Math.ceil(total / 3) - 1)) {
          return {
            cardClass: 'supports',
            badgeStyle: 'border:1px solid #bbf7d0;color:#15803d;background:#f0fdf4',
          };
        }
        if (index >= Math.max(0, total - Math.ceil(total / 3))) {
          return {
            cardClass: 'contradicts',
            badgeStyle: 'border:1px solid #fecdd3;color:#b91c1c;background:#fff1f2',
          };
        }
        return {
          cardClass: 'neutral',
          badgeStyle: 'border:1px solid #fde68a;color:#a16207;background:#fffbeb',
        };
      }

      function renderEvidenceListHint(mode) {
        const hint = byId('evidenceListHint');
        if (!hint) {
          return;
        }
        if (mode === 'hidden') {
          hint.classList.add('hidden');
          hint.textContent = '';
          return;
        }
        hint.classList.remove('hidden');
        hint.textContent = mode === 'empty' ? t('evidence_hint_empty') : t('evidence_hint_idle');
      }

      function renderEvidenceRows(rows) {
        const orderedRows = Array.isArray(rows)
          ? rows.slice().sort((left, right) => Number(right.reliability_score || 0) - Number(left.reliability_score || 0))
          : [];
        byId('evidenceCount').textContent = String(orderedRows.length);
        const list = byId('evidenceList');
        list.innerHTML = '';
        if (!orderedRows.length) {
          renderEvidenceListHint(state.lastReport ? 'empty' : 'idle');
          return;
        }
        renderEvidenceListHint('hidden');

        orderedRows.forEach((row, index) => {
          const card = document.createElement('div');
          const rawScore = row ? row.reliability_score : undefined;
          const hasScore = rawScore !== null && rawScore !== undefined && String(rawScore).trim() !== '';
          const score = hasScore ? Number(rawScore) : NaN;
          const scorePercent = Number.isFinite(score) ? Math.round(score * 100) : null;
          const scoreStyle = getEvidenceScoreStyle(index, orderedRows.length);
          card.className = 'ev ' + scoreStyle.cardClass;

          const top = document.createElement('div');
          top.className = 'ev-top';
          top.innerHTML =
            '<span class="mono" style="background:#eef2f7;border:1px solid var(--border);padding:2px 6px;border-radius:4px">' + (row.claim_id || '') + '</span>' +
            (scorePercent === null
              ? ''
              : '<span class="mono" title="Reliability score" style="padding:2px 6px;border-radius:4px;' + scoreStyle.badgeStyle + '">' + scorePercent + '%</span>');

          const text = document.createElement('div');
          text.className = 'small';
          text.textContent = String(row.claim_text || '').slice(0, 180);

          const meta = document.createElement('div');
          meta.className = 'tiny muted';
          meta.innerHTML =
            '<div style="display:flex;justify-content:space-between;gap:8px;padding-top:6px;border-top:1px solid #f1f5f9">' +
            '<span>' + t('study_type') + ': ' + String(row.study_type || 'unknown').toUpperCase() + ' | ' + t('effect') + ': ' + String(row.effect_direction || 'neutral').toUpperCase() + '</span>' +
            (row.source_url
              ? '<a class="mono" href="' + escapeHtml(String(row.source_url)) + '" target="_blank" rel="noopener noreferrer" style="color:var(--primary-strong)">' + escapeHtml(String(row.source_doi || row.source_url || 'n/a')) + '</a>'
              : '<span class="mono" style="color:var(--primary-strong)">' + escapeHtml(String(row.source_doi || 'n/a')) + '</span>') +
            '</div>';

          const add = document.createElement('button');
          add.className = 'btn tiny';
          add.textContent = t('use_in_compare');
          add.addEventListener('click', (event) => {
            event.stopPropagation();
            if (!byId('compareA').value) {
              byId('compareA').value = row.claim_id || '';
            } else {
              byId('compareB').value = row.claim_id || '';
            }
          });

          card.addEventListener('click', () => {
            if (row.claim_id) {
              tutorialSignal('evidence_clicked');
              fetchLineage(String(row.claim_id));
            }
          });

          card.appendChild(top);
          card.appendChild(text);
          card.appendChild(meta);
          card.appendChild(add);
          list.appendChild(card);
        });
      }

      function renderReport(payload) {
        const root = byId('report');
        root.innerHTML = '';
        const synthesis = payload.synthesis || {};

        const shell = document.createElement('div');
        shell.className = 'report-shell';

        const header = document.createElement('div');
        header.className = 'report-head';
        header.innerHTML =
          '<div class="report-title"><span class="material-symbols-outlined" style="color:var(--primary)">psychiatry</span>' + t('report_title') + '</div>' +
          '<div class="runtime-badge">' + tf('generated_in', { seconds: Number(payload.generated_seconds || 0).toFixed(1) }) + '</div>';

        const transparency = document.createElement('div');
        transparency.className = 'tiny muted';
        transparency.style.marginTop = '8px';
        const modeText = payload.response_mode === 'stream'
          ? t('response_mode_stream')
          : (payload.response_mode === 'sync' ? t('response_mode_sync') : t('response_mode_sync_fallback'));
        const guardrailFlags = Array.isArray(payload.guardrail_flags) && payload.guardrail_flags.length
          ? payload.guardrail_flags.join(', ')
          : '-';
        transparency.innerHTML =
          t('rows_retrieved') + ': ' + Number(payload.evidence_count || 0) +
          ' | ' + t('rows_cited') + ': ' + Number(Array.isArray(payload.evidence_rows) ? payload.evidence_rows.length : 0) +
          ' | ' + t('model') + ': ' + escapeHtml(String(payload.model || state.model || 'n/a')) +
          ' | ' + t('response_mode') + ': ' + escapeHtml(modeText) +
          ' | ' + t('guardrail_flags') + ': ' + escapeHtml(guardrailFlags);

        const direct = document.createElement('div');
        direct.className = 'section';
        direct.innerHTML = '<h4>' + t('direct_answer') + '</h4><div class="md-content">' + renderMarkdown(synthesis.direct_answer || payload.answer || '') + '</div>';
        const supportIds = Array.isArray(synthesis.supporting_claim_ids) ? synthesis.supporting_claim_ids : [];

        const hasContradictions = typeof synthesis.contradictions_summary === 'string' && synthesis.contradictions_summary.trim().length > 0;
        const hasNextStep = typeof synthesis.next_validation_step === 'string' && synthesis.next_validation_step.trim().length > 0;

        shell.appendChild(header);
        shell.appendChild(transparency);
        shell.appendChild(direct);

        if (supportIds.length) {
          const support = document.createElement('div');
          support.className = 'section';
          support.innerHTML = '<h4>' + t('supporting_nodes') + '</h4>';
          const chips = document.createElement('div');
          chips.className = 'chips';
          supportIds.forEach((cid) => {
            const chip = document.createElement('span');
            chip.className = 'chip mono';
            chip.innerHTML = '<span class="material-symbols-outlined" style="font-size:14px;color:#16a34a">check_circle</span> ' + String(cid);
            chips.appendChild(chip);
          });
          support.appendChild(chips);
          shell.appendChild(support);
        }

        if (hasContradictions) {
          const contradictions = document.createElement('div');
          contradictions.className = 'section warn';
          contradictions.innerHTML = '<h4><span class="material-symbols-outlined" style="font-size:14px;vertical-align:text-bottom;margin-right:4px">warning</span>' + t('contradictions_uncertainty') + '</h4>';
          const contradictionText = document.createElement('div');
          contradictionText.className = 'md-content';
          contradictionText.innerHTML = renderMarkdown(String(synthesis.contradictions_summary));
          contradictions.appendChild(contradictionText);
          shell.appendChild(contradictions);
        }

        if (hasNextStep) {
          const next = document.createElement('div');
          next.className = 'section';
          const nextStepText = String(synthesis.next_validation_step);
          next.innerHTML = '<h4><span class="material-symbols-outlined" style="font-size:14px;vertical-align:text-bottom;margin-right:4px">science</span>' + t('next_validation_step') + '</h4><div class="md-content">' + renderMarkdown(nextStepText) + '</div>';
          const runNext = document.createElement('button');
          runNext.className = 'icon-btn';
          runNext.style.marginTop = '10px';
          runNext.style.width = 'auto';
          runNext.style.height = 'auto';
          runNext.style.color = 'var(--primary-strong)';
          runNext.style.fontSize = '12px';
          runNext.style.fontWeight = '600';
          runNext.textContent = t('run_this_query');
          runNext.addEventListener('click', () => {
            byId('question').value = nextStepText;
            sendQuestion();
          });
          next.appendChild(runNext);
          shell.appendChild(next);
        }

        root.appendChild(shell);
        updateReportActionsAvailability(true);
      }

      function renderReportLoading() {
        const root = byId('report');
        root.innerHTML = '';

        const shell = document.createElement('div');
        shell.className = 'report-shell loading';

        const header = document.createElement('div');
        header.className = 'report-head';
        header.innerHTML =
          '<div class="report-title"><span class="loading-dot" aria-hidden="true"></span>' + t('generating_report') + '</div>' +
          '<div class="runtime-badge">' + t('in_progress') + '</div>';

        const copy = document.createElement('div');
        copy.className = 'small muted loading-copy';
        copy.textContent = t('loading_copy');

        const skeleton = document.createElement('div');
        skeleton.className = 'loading-skeleton';
        skeleton.innerHTML =
          '<div class="loading-line wide"></div>' +
          '<div class="loading-line mid"></div>' +
          '<div class="loading-line wide"></div>' +
          '<div class="loading-line short"></div>';

        shell.appendChild(header);
        shell.appendChild(copy);
        shell.appendChild(skeleton);
        root.appendChild(shell);
      }

      function renderStreamingReportShell() {
        const root = byId('report');
        root.innerHTML = '';

        const shell = document.createElement('div');
        shell.className = 'report-shell loading';
        shell.id = 'streamReportShell';

        const header = document.createElement('div');
        header.className = 'report-head';
        header.innerHTML =
          '<div class="report-title"><span class="loading-dot" aria-hidden="true"></span>' + t('generating_report') + '</div>' +
          '<div class="runtime-badge" id="streamPhaseBadge">' + t('in_progress') + '</div>';

        const direct = document.createElement('div');
        direct.className = 'section';
        direct.innerHTML = '<h4>' + t('direct_answer') + '</h4><div id="streamAnswer" class="md-content"></div>';

        const supportSkeleton = document.createElement('div');
        supportSkeleton.className = 'section';
        supportSkeleton.innerHTML =
          '<h4>' + t('supporting_nodes') + '</h4>' +
          '<div class="chips" style="gap:8px">' +
            '<span class="loading-line short" style="height:20px;width:96px;border-radius:999px"></span>' +
            '<span class="loading-line short" style="height:20px;width:110px;border-radius:999px"></span>' +
            '<span class="loading-line short" style="height:20px;width:90px;border-radius:999px"></span>' +
          '</div>';

        const contradictionSkeleton = document.createElement('div');
        contradictionSkeleton.className = 'section warn';
        contradictionSkeleton.innerHTML =
          '<h4><span class="material-symbols-outlined" style="font-size:14px;vertical-align:text-bottom;margin-right:4px">warning</span>' + t('contradictions_uncertainty') + '</h4>' +
          '<div class="loading-skeleton" style="margin-top:8px">' +
            '<div class="loading-line wide"></div>' +
            '<div class="loading-line mid"></div>' +
          '</div>';

        const nextStepSkeleton = document.createElement('div');
        nextStepSkeleton.className = 'section';
        nextStepSkeleton.innerHTML =
          '<h4><span class="material-symbols-outlined" style="font-size:14px;vertical-align:text-bottom;margin-right:4px">science</span>' + t('next_validation_step') + '</h4>' +
          '<div class="loading-skeleton" style="margin-top:8px">' +
            '<div class="loading-line wide"></div>' +
            '<div class="loading-line short"></div>' +
          '</div>';

        shell.appendChild(header);
        shell.appendChild(direct);
        shell.appendChild(supportSkeleton);
        shell.appendChild(contradictionSkeleton);
        shell.appendChild(nextStepSkeleton);
        root.appendChild(shell);
      }

      function updateStreamingAnswer(answerText) {
        const answerEl = byId('streamAnswer');
        if (!answerEl) {
          return;
        }
        answerEl.innerHTML = renderMarkdown(String(answerText || ''));
      }

      function setStreamingPhase(phase) {
        const badge = byId('streamPhaseBadge');
        if (!badge) {
          return;
        }
        if (phase === 'loading_evidence') {
          badge.textContent = t('stream_loading_evidence');
          return;
        }
        if (phase === 'building_prompt') {
          badge.textContent = t('stream_building_prompt');
          return;
        }
        if (phase === 'generating') {
          badge.textContent = t('stream_generating');
          return;
        }
        if (phase === 'post_processing') {
          badge.textContent = t('stream_post_processing');
          return;
        }
        badge.textContent = t('in_progress');
      }

      async function readNdjsonStream(response, onEvent) {
        if (!response.body || !response.body.getReader) {
          throw new Error('Streaming is not supported by this browser.');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let shouldStop = false;

        while (true) {
          const packet = await reader.read();
          if (packet.done) {
            break;
          }
          buffer += decoder.decode(packet.value, { stream: true });
          const lines = buffer.split('\\n');
          buffer = lines.pop() || '';

          lines.forEach((line) => {
            const trimmed = String(line || '').trim();
            if (!trimmed) {
              return;
            }
            try {
              const parsed = JSON.parse(trimmed);
              const signal = onEvent(parsed);
              if (signal === 'stop') {
                shouldStop = true;
              }
            } catch (error) {
              // Ignore malformed line fragments.
              if (error && error.name !== 'SyntaxError') {
                throw error;
              }
            }
          });

          if (shouldStop) {
            try {
              await reader.cancel();
            } catch (_) {}
            break;
          }
        }

        const trailing = buffer.trim();
        if (trailing && !shouldStop) {
          try {
            const signal = onEvent(JSON.parse(trailing));
            if (signal === 'stop') {
              shouldStop = true;
            }
          } catch (error) {
            // Ignore malformed trailing line.
            if (error && error.name !== 'SyntaxError') {
              throw error;
            }
          }
        }
      }

      function createStreamAnswerAnimator(onRender, intervalMs = 32, maxCharsPerTick = 18) {
        let queue = '';
        let rendered = '';
        let timer = null;

        function flushTick() {
          if (!queue.length) {
            if (timer) {
              clearInterval(timer);
              timer = null;
            }
            return;
          }
          const take = Math.min(maxCharsPerTick, queue.length);
          rendered += queue.slice(0, take);
          queue = queue.slice(take);
          onRender(rendered);
        }

        return {
          enqueue(deltaText) {
            const text = String(deltaText || '');
            if (!text) {
              return;
            }
            queue += text;
            if (!timer) {
              timer = setInterval(flushTick, intervalMs);
            }
            flushTick();
          },
          async drain() {
            while (queue.length) {
              flushTick();
              await new Promise((resolve) => setTimeout(resolve, intervalMs));
            }
            if (timer) {
              clearInterval(timer);
              timer = null;
            }
            return rendered;
          },
          current() {
            return rendered + queue;
          },
          stop() {
            if (timer) {
              clearInterval(timer);
              timer = null;
            }
          },
        };
      }

      function formatTelemetrySummary(telemetry) {
        if (!telemetry || typeof telemetry !== 'object') {
          return '';
        }
        const phase = telemetry.phase_seconds && typeof telemetry.phase_seconds === 'object'
          ? telemetry.phase_seconds
          : {};
        const toFixed = (value) => {
          const num = Number(value);
          return Number.isFinite(num) ? num.toFixed(2) : '0.00';
        };
        return tf('telemetry_phase_summary', {
          loading: toFixed(phase.loading_evidence),
          prompt: toFixed(phase.building_prompt),
          gen: toFixed(phase.generating),
          post: toFixed(phase.post_processing),
          total: toFixed(telemetry.total_seconds),
        });
      }

      function updateReportActionsAvailability(hasReport) {
        const showActions = Boolean(hasReport);
        const actions = byId('reportActions');
        const saveBtn = byId('saveSession');
        const exportBtn = byId('exportSummary');
        const copyBtn = byId('copyCitations');

        if (actions) {
          actions.classList.toggle('hidden', !showActions);
        }
        if (saveBtn) {
          saveBtn.disabled = !showActions;
        }
        if (exportBtn) {
          exportBtn.disabled = !showActions;
        }
        if (copyBtn) {
          copyBtn.disabled = !showActions;
        }
      }

      function renderComparePayload(data) {
        const root = byId('compareResult');
        const followup = data.follow_up_suggestion || t('default_follow_up');
        root.innerHTML =
          '<div class="compare-grid">' +
            '<div class="compare-cols">' +
              '<div class="section">' +
                '<h4>' + t('claim_a') + '</h4>' +
                '<div class="mono">' + (data.claim_a.claim_id || 'n/a') + '</div>' +
                '<div class="small" style="margin-top:6px">' + (data.claim_a.claim_text || '') + '</div>' +
              '</div>' +
              '<div class="section">' +
                '<h4>' + t('claim_b') + '</h4>' +
                '<div class="mono">' + (data.claim_b.claim_id || 'n/a') + '</div>' +
                '<div class="small" style="margin-top:6px">' + (data.claim_b.claim_text || '') + '</div>' +
              '</div>' +
            '</div>' +
            '<div class="tiny muted">' + t('shared_supporting') + ': ' + data.shared_supporting_count + ' | ' + t('shared_contradicting') + ': ' + data.shared_contradicting_count + '</div>' +
            '<div class="tiny">' + t('follow_up') + ': ' + followup + '</div>' +
          '</div>';
      }

      function formatCompactCount(value) {
        const count = Number(value || 0);
        if (!Number.isFinite(count) || count < 0) {
          return '0';
        }
        return count.toLocaleString();
      }

      function formatRelativeIso(isoText) {
        if (!isoText) {
          return 'n/a';
        }
        const parsed = new Date(String(isoText));
        if (Number.isNaN(parsed.getTime())) {
          return String(isoText);
        }
        const deltaMs = Date.now() - parsed.getTime();
        const minutes = Math.round(deltaMs / 60000);
        if (minutes < 1) {
          return 'just now';
        }
        if (minutes < 60) {
          return minutes + 'm ago';
        }
        const hours = Math.round(minutes / 60);
        if (hours < 48) {
          return hours + 'h ago';
        }
        const days = Math.round(hours / 24);
        return days + 'd ago';
      }

      function renderDbPopoverSources(rows, total) {
        const root = byId('statusDbPopoverSources');
        if (!root) {
          return;
        }
        const safeRows = Array.isArray(rows) ? rows : [];
        if (!safeRows.length) {
          root.innerHTML = '<div class="db-popover-foot" style="margin:0;padding:0;border:0">' + escapeHtml(t('db_popover_waiting')) + '</div>';
          return;
        }
        const denom = total > 0 ? total : 1;
        root.innerHTML = safeRows.slice(0, 5).map((row) => {
          const source = escapeHtml(String(row && row.source ? row.source : 'unknown'));
          const count = Number(row && row.articles ? row.articles : 0);
          const safeCount = Number.isFinite(count) && count > 0 ? count : 0;
          const width = Math.max(0, Math.min(100, (safeCount / denom) * 100));
          return '<div>'
            + '<div class="db-popover-source-row"><span>' + source + '</span><span>' + formatCompactCount(safeCount) + '</span></div>'
            + '<div class="db-popover-bar"><span style="width:' + width.toFixed(1) + '%"></span></div>'
            + '</div>';
        }).join('');
      }

      function renderDbStatusPopover(data) {
        const totalEl = byId('statusDbPopoverTotal');
        const metaEl = byId('statusDbPopoverMeta');
        const footEl = byId('statusDbPopoverFoot');
        const dotEl = byId('statusDbPopoverDot');
        const titleEl = byId('statusDbPopoverTitle');
        if (!totalEl || !metaEl) {
          return;
        }
        if (titleEl) {
          titleEl.textContent = t('db_popover_title');
        }
        const total = Number(data && data.records_total ? data.records_total : 0);
        const sourceRows = data && Array.isArray(data.source_breakdown) ? data.source_breakdown : [];
        const syncText = formatRelativeIso(data && data.latest_sync_at ? data.latest_sync_at : '');
        totalEl.textContent = formatCompactCount(total);
        metaEl.textContent = t('db_popover_last_sync') + ': ' + syncText + ' · ' + formatCompactCount(total) + ' ' + t('db_popover_total_label');
        renderDbPopoverSources(sourceRows, total);
        if (footEl) {
          footEl.textContent = total > 0 ? t('db_popover_ready') : t('db_popover_waiting');
        }
        if (dotEl) {
          dotEl.style.background = total > 0 ? 'var(--ok)' : 'var(--warn)';
        }
      }

      async function fetchStatus() {
        const dbEl = byId('status-db');
        const dbDotEl = byId('statusDbDot');
        const metaEl = byId('statusDbPopoverMeta');
        if (metaEl) {
          metaEl.textContent = t('db_popover_loading');
        }
        try {
          const resp = await fetch('/api/status');
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.error || 'status failed');
          state.dbStatusSnapshot = data;
          byId('status-model').textContent = String(data.model || state.model || 'unknown');
          if (Boolean(data.db_synced)) {
            dbEl.textContent = t('db_synced');
            dbEl.classList.remove('error');
            if (dbDotEl) dbDotEl.style.background = 'var(--ok)';
          } else {
            dbEl.textContent = t('db_out_of_sync');
            dbEl.classList.add('error');
            if (dbDotEl) dbDotEl.style.background = 'var(--warn)';
          }
          renderDbStatusPopover(data);
        } catch (_) {
          dbEl.textContent = t('db_unavailable');
          dbEl.classList.add('error');
          if (dbDotEl) dbDotEl.style.background = 'var(--warn)';
          if (metaEl) {
            metaEl.textContent = t('db_popover_unavailable');
          }
          const footEl = byId('statusDbPopoverFoot');
          if (footEl) {
            footEl.textContent = t('db_popover_unavailable');
          }
        }
      }

      async function fetchEvidence() {
        const filters = getFilters();
        const endpoint = '/api/evidence/filter';
        const payload = { filters, limit: 500 };
        try {
          const resp = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.error || 'evidence query failed');
          state.evidenceRows = Array.isArray(data.rows) ? data.rows : [];
          renderEvidenceRows(state.evidenceRows);
        } catch (error) {
          setChatStatus(String(error), true);
        }
      }

      async function runCompare() {
        const claimA = byId('compareA').value.trim();
        const claimB = byId('compareB').value.trim();
        if (!claimA || !claimB) {
          byId('compareResult').textContent = t('compare_prompt');
          return;
        }
        try {
          const resp = await fetch('/api/evidence/compare', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ claim_a: claimA, claim_b: claimB }),
          });
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.error || 'compare failed');
          state.currentComparePayload = data;
          renderComparePayload(data);
        } catch (error) {
          byId('compareResult').textContent = String(error);
        }
      }

      async function sendQuestion() {
        if (state.authEnabled && !state.isAuthenticated) {
          setChatStatus('Please sign in first.', true);
          updateAuthUI();
          return;
        }
        const question = byId('question').value.trim();
        if (!question) {
          setChatStatus(t('type_question_first'), true);
          return;
        }
        const sendBtn = byId('send');
        const sendIcon = sendBtn ? sendBtn.querySelector('.material-symbols-outlined') : null;
        state.messages.push({ role: 'user', content: question });
        state.lastReport = null;
        state.evidenceRows = [];
        state.tutorial.actions.report_ready = false;
        updateReportActionsAvailability(false);
        renderStreamingReportShell();
        renderEvidenceRows([]);
        setChatStatus(t('generating_new_report'));
        if (sendBtn) {
          sendBtn.disabled = true;
          sendBtn.classList.add('loading');
          if (sendIcon) {
            sendIcon.classList.add('hidden');
          }
          if (!sendBtn.querySelector('.spinner')) {
            const spinner = document.createElement('span');
            spinner.className = 'spinner';
            spinner.setAttribute('aria-hidden', 'true');
            sendBtn.appendChild(spinner);
          }
        }
        try {
          const payload = {
            messages: state.messages,
            db_path: state.dbPath,
            host: state.host,
            model: state.model,
            context_limit: state.contextLimit,
            temperature: state.temperature,
            timeout_seconds: state.timeoutSeconds,
            language: state.language,
            filters: getFilters(),
          };

          let streamSucceeded = false;
          try {
            const resp = await fetch('/api/chat/stream', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload),
            });
            if (!resp.ok) {
              let message = 'chat failed';
              try {
                const data = await resp.json();
                message = data.error || message;
              } catch (_) {}
              throw new Error(message);
            }

            const animator = createStreamAnswerAnimator(updateStreamingAnswer);
            let streamedAnswer = '';
            let finalPayload = null;

            await readNdjsonStream(resp, function(event) {
              if (!event || typeof event !== 'object') {
                return;
              }

              if (event.type === 'status') {
                setStreamingPhase(String(event.phase || ''));
                if (event.phase === 'loading_evidence') {
                  setChatStatus(t('stream_loading_evidence'));
                } else if (event.phase === 'building_prompt') {
                  setChatStatus(t('stream_building_prompt'));
                } else if (event.phase === 'generating') {
                  setChatStatus(t('stream_generating'));
                } else if (event.phase === 'post_processing') {
                  setChatStatus(t('stream_post_processing'));
                }
                return;
              }

              if (event.type === 'chunk') {
                const delta = String(event.delta || '');
                streamedAnswer += delta;
                animator.enqueue(delta);
                return;
              }

              if (event.type === 'final') {
                finalPayload = event;
                return 'stop';
              }

              if (event.type === 'error') {
                animator.stop();
                throw new Error(String(event.error || 'chat stream failed'));
              }
            });

            const animatedAnswer = await animator.drain();
            if (!finalPayload) {
              throw new Error('chat stream ended unexpectedly');
            }

            const finalAnswer = finalPayload.answer || streamedAnswer || animatedAnswer || '';
            state.messages.push({ role: 'assistant', content: finalAnswer });
            state.lastReport = finalPayload;
            state.evidenceRows = Array.isArray(finalPayload.evidence_rows) ? finalPayload.evidence_rows : [];
            renderReport(finalPayload);
            renderEvidenceRows(state.evidenceRows);
            tutorialSignal('report_ready');
            fetchRecentDiagnostics();
            const streamStatus = tf('stream_done', { count: Number(finalPayload.evidence_count || 0) });
            const streamTelemetry = formatTelemetrySummary(finalPayload.telemetry);
            setChatStatus(streamTelemetry ? (streamStatus + ' ' + streamTelemetry) : streamStatus);
            streamSucceeded = true;
          } catch (streamError) {
            setChatStatus('Streaming unavailable, falling back to standard response...');
          }

          if (!streamSucceeded) {
            const fallbackResp = await fetch('/api/chat', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload),
            });
            const fallbackData = await fallbackResp.json();
            if (!fallbackResp.ok) throw new Error(fallbackData.error || 'chat failed');
            state.messages.push({ role: 'assistant', content: fallbackData.answer || '' });
            state.lastReport = fallbackData;
            state.evidenceRows = Array.isArray(fallbackData.evidence_rows) ? fallbackData.evidence_rows : [];
            renderReport(fallbackData);
            renderEvidenceRows(state.evidenceRows);
            tutorialSignal('report_ready');
            fetchRecentDiagnostics();
            const fallbackStatus = tf('done_rows_used', { count: fallbackData.evidence_count });
            const fallbackTelemetry = formatTelemetrySummary(fallbackData.telemetry);
            setChatStatus(fallbackTelemetry ? (fallbackStatus + ' ' + fallbackTelemetry) : fallbackStatus);
          }
        } catch (error) {
          setChatStatus(String(error), true);
        } finally {
          if (sendBtn) {
            sendBtn.disabled = false;
            sendBtn.classList.remove('loading');
            const spinner = sendBtn.querySelector('.spinner');
            if (spinner) {
              spinner.remove();
            }
            if (sendIcon) {
              sendIcon.classList.remove('hidden');
            }
          }
        }
      }

      async function saveSession() {
        if (state.authEnabled && !state.isAuthenticated) {
          setChatStatus('Please sign in first.', true);
          return;
        }
        if (!state.lastReport) {
          setChatStatus(t('no_report_to_save'), true);
          return;
        }
        try {
          const question = String(byId('question').value || '').trim();
          const resp = await fetch('/api/session/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              session_id: state.activeSessionId,
              title: question ? question.slice(0, 80) : 'Investigator session',
              question,
              report: state.lastReport,
              messages: state.messages,
              filters: getFilters(),
              evidence_claim_ids: state.evidenceRows.slice(0, 100).map((row) => String(row.claim_id || '')).filter(Boolean),
            }),
          });
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.error || 'session save failed');
          state.activeSessionId = data.session_id || state.activeSessionId;
          setChatStatus(t('session_saved'));
        } catch (error) {
          setChatStatus(String(error), true);
        }
      }

      async function loadLatestSessionId() {
        try {
          const resp = await fetch('/api/session/list?limit=1');
          const data = await resp.json();
          if (!resp.ok || !Array.isArray(data.sessions) || !data.sessions.length) {
            return;
          }
          state.activeSessionId = data.sessions[0].session_id || null;
        } catch (_) {
          return;
        }
      }

      async function renderSavedSessions() {
        if (state.authEnabled && !state.isAuthenticated) {
          byId('sessionsList').innerHTML = '<div class="small muted">Please sign in to view saved sessions.</div>';
          return;
        }
        const list = byId('sessionsList');
        list.innerHTML = '<div class="small muted">' + t('loading_sessions') + '</div>';
        try {
          const resp = await fetch('/api/session/list?limit=100');
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.error || 'list sessions failed');
          const sessions = Array.isArray(data.sessions) ? data.sessions : [];
          list.innerHTML = '';
          if (!sessions.length) {
            list.innerHTML = '<div class="small muted">' + t('no_saved_sessions') + '</div>';
            return;
          }
          sessions.forEach((row) => {
            const item = document.createElement('button');
            item.className = 'session-row';
            item.innerHTML =
              '<div class="mono">' + String(row.session_id || '') + '</div>' +
              '<div class="small" style="margin-top:4px">' + String(row.title || 'Untitled') + '</div>' +
              '<div class="tiny muted" style="margin-top:4px">' + t('updated') + ': ' + String(row.updated_at || '') + '</div>';
            item.addEventListener('click', async () => {
              state.activeSessionId = String(row.session_id || '');
              await loadSession(state.activeSessionId);
              switchView('assistant');
            });
            list.appendChild(item);
          });
        } catch (error) {
          list.innerHTML = '<div class="small error">' + String(error) + '</div>';
        }
      }

      async function composeSynthesis() {
        try {
          const resp = await fetch('/api/synthesis', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              filters: getFilters(),
            }),
          });
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.error || 'compose synthesis failed');
          const composition = data.composition || {};
          const debateCount = Number((composition.debate_report || {}).round_count || 0);
          const hypothesisCount = Array.isArray(composition.hypothesis_queue) ? composition.hypothesis_queue.length : 0;
          setChatStatus('Synthesis composed: ' + hypothesisCount + ' hypotheses, ' + debateCount + ' debate rounds.');
        } catch (error) {
          setChatStatus(String(error), true);
        }
      }

      function switchView(viewName) {
        if (state.authEnabled && !state.isAuthenticated && viewName === 'sessions') {
          setChatStatus('Please sign in to access saved sessions.', true);
          updateAuthUI();
          return;
        }
        const assistant = byId('assistantView');
        const sessions = byId('sessionsView');
        const navAssistant = byId('navAssistant');
        const navSessions = byId('navSessions');

        if (viewName === 'sessions') {
          assistant.classList.add('hidden');
          sessions.classList.remove('hidden');
          navAssistant.classList.remove('active');
          navSessions.classList.add('active');
          tutorialSignal('sessions_view_opened');
          renderSavedSessions();
          return;
        }
        sessions.classList.add('hidden');
        assistant.classList.remove('hidden');
        navSessions.classList.remove('active');
        navAssistant.classList.add('active');
      }

      function applySettingsFromState() {
        byId('settingsModel').value = state.model;
        byId('settingsHost').value = state.host;
        byId('settingsLanguage').value = state.language;
        byId('settingsContextLimit').value = String(state.contextLimit);
        byId('settingsTemperature').value = String(state.temperature);
        byId('settingsTimeout').value = String(state.timeoutSeconds);
      }

      function saveSettingsToState() {
        state.model = String(byId('settingsModel').value || state.model).trim() || state.model;
        state.host = String(byId('settingsHost').value || state.host).trim() || state.host;
        state.language = String(byId('settingsLanguage').value || state.language).trim() || state.language;
        state.contextLimit = Number(byId('settingsContextLimit').value || state.contextLimit);
        state.temperature = Number(byId('settingsTemperature').value || state.temperature);
        state.timeoutSeconds = Number(byId('settingsTimeout').value || state.timeoutSeconds);
        byId('status-model').textContent = state.model;
        applyTranslations();
        closeSettingsDrawer();
        setChatStatus(t('settings_applied'));
      }

      async function loadSession(sessionId) {
        if (!sessionId) {
          return;
        }
        try {
          const resp = await fetch('/api/session/' + encodeURIComponent(sessionId));
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.error || 'session load failed');
          const report = data.report || {};
          if (report.answer || report.synthesis) {
            state.lastReport = report;
            state.evidenceRows = Array.isArray(report.evidence_rows) ? report.evidence_rows : [];
            renderReport(report);
            renderEvidenceRows(state.evidenceRows);
          } else {
            updateReportActionsAvailability(false);
            state.evidenceRows = [];
            renderEvidenceRows([]);
          }
          if (Array.isArray(data.messages) && data.messages.length) {
            state.messages = data.messages;
          }
          if (data.question) {
            byId('question').value = String(data.question);
          }
          setChatStatus(t('loaded_latest_session'));
        } catch (_) {
          return;
        }
      }

      function _makeSessionId() {
        return 'sess_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
      }

      function ensureSessionId() {
        if (!state.activeSessionId) {
          state.activeSessionId = _makeSessionId();
        }
        return state.activeSessionId;
      }

      ensureSessionId();

      bindClick('applyFilters', () => {
        setChatStatus(t('filters_updated'));
        tutorialSignal('filters_applied');
      });
      bindClick('resetFilters', () => {
        Array.from(document.querySelectorAll('input[name="etype"]')).forEach((el) => {
          el.checked = ['observational', 'interventional'].includes(el.value);
        });
        const dateWindow = byId('dateWindow');
        if (dateWindow) {
          dateWindow.value = 'all';
        }
        const minRel = byId('minRel');
        if (minRel) {
          minRel.value = '0.60';
        }
        const relLabel = byId('relLabel');
        if (relLabel) {
          relLabel.textContent = '60%';
        }
        const highlight = byId('highlightContradictions');
        if (highlight) {
          highlight.checked = true;
        }
        setChatStatus(t('filters_reset'));
      });

      function exportSummary() {
        if (!state.lastReport) {
          setChatStatus(t('no_report_to_export'), true);
          return;
        }
        (async () => {
          try {
            const resp = await fetch('/api/export/summary', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ report: state.lastReport }),
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || 'export failed');

            const jsonBlob = new Blob([String(data.json_content || '')], { type: 'application/json' });
            const mdBlob = new Blob([String(data.markdown_content || '')], { type: 'text/markdown' });

            const aJson = document.createElement('a');
            aJson.href = URL.createObjectURL(jsonBlob);
            aJson.download = String(data.json_filename || 'synthesis_report.json');
            aJson.click();
            URL.revokeObjectURL(aJson.href);

            const aMd = document.createElement('a');
            aMd.href = URL.createObjectURL(mdBlob);
            aMd.download = String(data.markdown_filename || 'synthesis_report.md');
            aMd.click();
            URL.revokeObjectURL(aMd.href);

            setChatStatus(t('exported_summary'));
          } catch (error) {
            setChatStatus(String(error), true);
          }
        })();
      }

      async function copyCitations() {
        if (!state.lastReport || !state.lastReport.synthesis) {
          setChatStatus(t('no_citations_to_copy'), true);
          return;
        }
        const ids = Array.isArray(state.lastReport.synthesis.supporting_claim_ids)
          ? state.lastReport.synthesis.supporting_claim_ids
          : [];
        if (!ids.length) {
          setChatStatus(t('no_supporting_ids'), true);
          return;
        }
        const doiMap = new Map();
        state.evidenceRows.forEach((row) => {
          if (row && row.claim_id) {
            doiMap.set(String(row.claim_id), String(row.source_doi || 'n/a'));
          }
        });
        const lines = ids.map((id) => {
          const cid = String(id);
          return cid + ' | ' + (doiMap.get(cid) || 'doi-unknown');
        });
        await navigator.clipboard.writeText(lines.join('\\n'));
        setChatStatus(tf('copied_claims', { count: ids.length }));
      }

      function updateReliabilityLabel() {
        const slider = byId('minRel');
        const label = byId('relLabel');
        if (!slider || !label) {
          return;
        }
        label.textContent = Math.round(Number(slider.value) * 100) + '%';
      }

      function bindEvent(id, eventName, handler) {
        const el = byId(id);
        if (!el) {
          return null;
        }
        el.addEventListener(eventName, handler);
        return el;
      }

      function bindClick(id, handler) {
        return bindEvent(id, 'click', handler);
      }

      const TUTORIAL_VERSION = '2026-07-05-v1';
      const TUTORIAL_STORAGE_KEY = 'als_tool_tutorial';
      let tutorialTargetEl = null;
      let tutorialRenderTimer = null;

      function loadTutorialProgress() {
        try {
          const raw = window.localStorage.getItem(TUTORIAL_STORAGE_KEY);
          if (!raw) {
            return { version: '', status: '' };
          }
          const parsed = JSON.parse(raw);
          return {
            version: String(parsed.version || ''),
            status: String(parsed.status || ''),
          };
        } catch (_) {
          return { version: '', status: '' };
        }
      }

      function saveTutorialProgress(status) {
        try {
          window.localStorage.setItem(
            TUTORIAL_STORAGE_KEY,
            JSON.stringify({
              version: TUTORIAL_VERSION,
              status: String(status || ''),
              updated_at: new Date().toISOString(),
            })
          );
        } catch (_) {}
      }

      function shouldAutoStartTutorial() {
        const progress = loadTutorialProgress();
        if (progress.version !== TUTORIAL_VERSION) {
          return true;
        }
        return progress.status !== 'completed' && progress.status !== 'dismissed';
      }

      function getTutorialSteps(mode = 'full') {
        const fullSteps = [
          {
            id: 'query',
            selector: '#question',
            titleKey: 'tutorial_step_query_title',
            bodyKey: 'tutorial_step_query_body',
            requiredAction: 'question_typed',
          },
          {
            id: 'send',
            selector: '#send',
            titleKey: 'tutorial_step_send_title',
            bodyKey: 'tutorial_step_send_body',
            requiredAction: 'report_ready',
          },
          {
            id: 'report',
            selector: '#report',
            titleKey: 'tutorial_step_report_title',
            bodyKey: 'tutorial_step_report_body',
            readyWhen: () => Boolean(state.lastReport),
          },
          {
            id: 'validation',
            selector: '#report',
            titleKey: 'tutorial_step_validation_title',
            bodyKey: 'tutorial_step_validation_body',
            readyWhen: () => Boolean(state.lastReport),
          },
          {
            id: 'diagnostics',
            selector: '#diagnosticsList',
            titleKey: 'tutorial_step_diagnostics_title',
            bodyKey: 'tutorial_step_diagnostics_body',
          },
          {
            id: 'save_session',
            selector: '#saveSession',
            titleKey: 'tutorial_step_save_title',
            bodyKey: 'tutorial_step_save_body',
            readyWhen: () => Boolean(state.lastReport),
          },
          {
            id: 'export_summary',
            selector: '#exportSummary',
            titleKey: 'tutorial_step_export_title',
            bodyKey: 'tutorial_step_export_body',
            readyWhen: () => Boolean(state.lastReport),
          },
          {
            id: 'copy_citations',
            selector: '#copyCitations',
            titleKey: 'tutorial_step_copy_title',
            bodyKey: 'tutorial_step_copy_body',
            readyWhen: () => Boolean(state.lastReport),
          },
          {
            id: 'open_db_explorer',
            selector: '#status-db',
            titleKey: 'tutorial_step_db_open_title',
            bodyKey: 'tutorial_step_db_open_body',
            requiredAction: 'db_explorer_opened',
          },
          {
            id: 'db_explorer',
            selector: '#dbExplorerModal .db-toolbar',
            titleKey: 'tutorial_step_db_explorer_title',
            bodyKey: 'tutorial_step_db_explorer_body',
            readyWhen: () => {
              const modal = byId('dbExplorerModal');
              return Boolean(modal && modal.classList.contains('open'));
            },
          },
          {
            id: 'sessions_nav',
            selector: '#navSessions',
            titleKey: 'tutorial_step_sessions_nav_title',
            bodyKey: 'tutorial_step_sessions_nav_body',
            requiredAction: 'sessions_view_opened',
          },
          {
            id: 'sessions_list',
            selector: '#sessionsList',
            titleKey: 'tutorial_step_sessions_list_title',
            bodyKey: 'tutorial_step_sessions_list_body',
            readyWhen: () => {
              const view = byId('sessionsView');
              return Boolean(view && !view.classList.contains('hidden'));
            },
          },
          {
            id: 'open_hypothesis_queue',
            selector: '#openHypothesisQueue',
            titleKey: 'tutorial_step_hypothesis_open_title',
            bodyKey: 'tutorial_step_hypothesis_open_body',
            requiredAction: 'hypothesis_queue_opened',
          },
          {
            id: 'hypothesis_queue',
            selector: '#hypothesisQueueModal .hypo-grid',
            titleKey: 'tutorial_step_hypothesis_queue_title',
            bodyKey: 'tutorial_step_hypothesis_queue_body',
            readyWhen: () => {
              const modal = byId('hypothesisQueueModal');
              return Boolean(modal && modal.classList.contains('open'));
            },
          },
          {
            id: 'open_review_queue',
            selector: '#openProfile',
            titleKey: 'tutorial_step_review_open_title',
            bodyKey: 'tutorial_step_review_open_body',
            requiredAction: 'review_queue_opened',
          },
          {
            id: 'review_queue',
            selector: '#reviewQueueModal .review-layout',
            titleKey: 'tutorial_step_review_queue_title',
            bodyKey: 'tutorial_step_review_queue_body',
            readyWhen: () => {
              const modal = byId('reviewQueueModal');
              return Boolean(modal && modal.classList.contains('open'));
            },
          },
          {
            id: 'evidence',
            selector: '#evidenceList',
            titleKey: 'tutorial_step_evidence_title',
            bodyKey: 'tutorial_step_evidence_body',
            readyWhen: () => Array.isArray(state.evidenceRows) && state.evidenceRows.length > 0,
          },
          {
            id: 'lineage',
            selector: '#evidenceList .ev',
            titleKey: 'tutorial_step_lineage_title',
            bodyKey: 'tutorial_step_lineage_body',
            requiredAction: 'evidence_clicked',
            readyWhen: () => Array.isArray(state.evidenceRows) && state.evidenceRows.length > 0,
          },
          {
            id: 'filters',
            selector: '#filterPanel',
            titleKey: 'tutorial_step_filters_title',
            bodyKey: 'tutorial_step_filters_body',
            requiredAction: 'filters_applied',
          },
          {
            id: 'compare',
            selector: '.compare',
            titleKey: 'tutorial_step_compare_title',
            bodyKey: 'tutorial_step_compare_body',
          },
        ];
        if (String(mode || 'full') !== 'short') {
          return fullSteps;
        }
        const shortIds = new Set(['query', 'send', 'validation', 'evidence', 'filters']);
        return fullSteps.filter((step) => shortIds.has(String(step.id || '')));
      }

      function tutorialClearTarget() {
        if (tutorialTargetEl && tutorialTargetEl.classList) {
          tutorialTargetEl.classList.remove('tutorial-target');
        }
        tutorialTargetEl = null;
      }

      function tutorialPositionCard(targetRect) {
        const card = byId('tutorialCard');
        if (!card) {
          return;
        }
        const margin = 12;
        const maxTop = Math.max(8, window.innerHeight - card.offsetHeight - 8);
        const preferredRight = targetRect.right + margin;
        const preferredLeft = targetRect.left - card.offsetWidth - margin;

        let left = preferredRight;
        if (preferredRight + card.offsetWidth > window.innerWidth - 8) {
          left = preferredLeft;
        }
        if (left < 8 || window.innerWidth < 860) {
          left = Math.max(8, Math.min(window.innerWidth - card.offsetWidth - 8, targetRect.left));
        }

        let top = targetRect.top;
        if (top > maxTop) {
          top = maxTop;
        }
        if (top < 8) {
          top = 8;
        }

        card.style.left = Math.round(left) + 'px';
        card.style.top = Math.round(top) + 'px';
      }

      function tutorialRenderCurrentStep() {
        if (!state.tutorial.running) {
          return;
        }
        const steps = getTutorialSteps(state.tutorial.mode);
        const step = steps[state.tutorial.stepIndex];
        if (!step) {
          return;
        }

        if (tutorialRenderTimer) {
          clearTimeout(tutorialRenderTimer);
          tutorialRenderTimer = null;
        }

        const overlay = byId('tutorialOverlay');
        const spotlight = byId('tutorialSpotlight');
        const title = byId('tutorialTitle');
        const body = byId('tutorialBody');
        const hint = byId('tutorialHint');
        const progress = byId('tutorialProgress');
        const nextBtn = byId('tutorialNext');
        const backBtn = byId('tutorialBack');
        if (!overlay || !spotlight || !title || !body || !hint || !progress || !nextBtn || !backBtn) {
          return;
        }

        const ready = typeof step.readyWhen === 'function' ? Boolean(step.readyWhen()) : true;
        const target = ready ? document.querySelector(step.selector) : null;
        if (!target) {
          hint.textContent = t('tutorial_wait_for_action');
          spotlight.style.width = '0px';
          spotlight.style.height = '0px';
          tutorialClearTarget();
          tutorialRenderTimer = window.setTimeout(tutorialRenderCurrentStep, 250);
          return;
        }

        tutorialClearTarget();
        tutorialTargetEl = target;
        tutorialTargetEl.classList.add('tutorial-target');

        const requiredAction = String(step.requiredAction || '');
        const stepComplete = !requiredAction || Boolean(state.tutorial.actions[requiredAction]);
        hint.textContent = stepComplete ? '' : t('tutorial_wait_for_action');

        title.textContent = t(step.titleKey);
        body.textContent = t(step.bodyKey);
        progress.textContent = tf('tutorial_progress', { current: state.tutorial.stepIndex + 1, total: steps.length });
        backBtn.disabled = state.tutorial.stepIndex <= 0;
        nextBtn.disabled = !stepComplete;
        nextBtn.textContent = state.tutorial.stepIndex === steps.length - 1 ? t('tutorial_finish') : t('tutorial_next');

        const rect = target.getBoundingClientRect();
        const pad = 6;
        spotlight.style.left = Math.round(rect.left - pad) + 'px';
        spotlight.style.top = Math.round(rect.top - pad) + 'px';
        spotlight.style.width = Math.max(0, Math.round(rect.width + pad * 2)) + 'px';
        spotlight.style.height = Math.max(0, Math.round(rect.height + pad * 2)) + 'px';

        tutorialPositionCard(rect);
      }

      function tutorialStop(status) {
        const overlay = byId('tutorialOverlay');
        if (overlay) {
          overlay.classList.add('hidden');
          overlay.setAttribute('aria-hidden', 'true');
        }
        tutorialClearTarget();
        state.tutorial.running = false;
        if (tutorialRenderTimer) {
          clearTimeout(tutorialRenderTimer);
          tutorialRenderTimer = null;
        }
        if (status === 'completed') {
          saveTutorialProgress('completed');
          setChatStatus(t('tutorial_done'));
        } else if (status === 'dismissed') {
          saveTutorialProgress('dismissed');
          setChatStatus(t('tutorial_stopped'));
        }
      }

      function tutorialStart(manual = false, selectedMode = '') {
        if (!manual && !shouldAutoStartTutorial()) {
          return;
        }
        const normalizedMode = String(selectedMode || '').trim().toLowerCase();
        state.tutorial.mode = normalizedMode === 'full' ? 'full' : 'short';
        state.tutorial.running = true;
        state.tutorial.stepIndex = 0;
        state.tutorial.actions.question_typed = Boolean(String(byId('question') ? byId('question').value : '').trim());
        state.tutorial.actions.report_ready = false;
        state.tutorial.actions.evidence_clicked = false;
        state.tutorial.actions.filters_applied = false;
        state.tutorial.actions.db_explorer_opened = false;
        state.tutorial.actions.sessions_view_opened = false;
        state.tutorial.actions.hypothesis_queue_opened = false;
        state.tutorial.actions.review_queue_opened = false;
        const overlay = byId('tutorialOverlay');
        if (overlay) {
          overlay.classList.remove('hidden');
          overlay.setAttribute('aria-hidden', 'false');
        }
        tutorialRenderCurrentStep();
      }

      function tutorialSignal(actionName) {
        const action = String(actionName || '').trim();
        if (!action) {
          return;
        }
        state.tutorial.actions[action] = true;
        if (state.tutorial.running) {
          tutorialRenderCurrentStep();
        }
      }

      function tutorialNextStep() {
        if (!state.tutorial.running) {
          return;
        }
        const steps = getTutorialSteps(state.tutorial.mode);
        const currentStep = steps[state.tutorial.stepIndex];
        if (!currentStep) {
          return;
        }
        if (currentStep.requiredAction && !state.tutorial.actions[currentStep.requiredAction]) {
          tutorialRenderCurrentStep();
          return;
        }
        if (state.tutorial.stepIndex >= steps.length - 1) {
          tutorialStop('completed');
          return;
        }
        state.tutorial.stepIndex += 1;
        tutorialRenderCurrentStep();
      }

      function tutorialBackStep() {
        if (!state.tutorial.running) {
          return;
        }
        if (state.tutorial.stepIndex <= 0) {
          tutorialRenderCurrentStep();
          return;
        }
        state.tutorial.stepIndex -= 1;
        tutorialRenderCurrentStep();
      }

      bindEvent('minRel', 'input', updateReliabilityLabel);
      bindEvent('minRel', 'change', updateReliabilityLabel);
      bindClick('toggleFilters', () => {
        const panel = byId('filterPanel');
        const layout = document.querySelector('main.layout');
        if (!panel) {
          return;
        }
        const isCollapsed = panel.classList.toggle('collapsed');
        if (layout) {
          layout.classList.toggle('filters-collapsed', isCollapsed);
        }
      });
      bindClick('navAssistant', () => switchView('assistant'));
      bindClick('navSessions', () => switchView('sessions'));
      bindClick('refreshSessions', renderSavedSessions);
      bindClick('openHypothesisQueue', openHypothesisQueue);
      bindClick('closeHypothesisQueue', closeHypothesisQueue);
      bindClick('closeHypothesisQueueIcon', closeHypothesisQueue);
      bindClick('hypothesisQueueModalBackdrop', closeHypothesisQueue);
      bindClick('refreshHypothesisQueue', fetchHypothesisQueue);
      bindEvent('hypoRequireSignoff', 'change', fetchHypothesisQueue);
      bindEvent('hypoEnforceCausalGate', 'change', fetchHypothesisQueue);
      bindClick('openProfile', openReviewQueue);
      bindClick('closeReviewQueue', closeReviewQueue);
      bindClick('closeReviewQueueIcon', closeReviewQueue);
      bindClick('reviewQueueModalBackdrop', closeReviewQueue);
      bindClick('refreshReviewQueue', fetchReviewFlags);
      bindClick('approveClaim', () => submitReviewDecision('approve'));
      bindClick('rejectClaim', () => submitReviewDecision('reject'));
      bindClick('needsEvidenceClaim', () => submitReviewDecision('needs_more_evidence'));
      bindClick('status-db', openDbExplorer);
      bindEvent('status-db', 'keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          openDbExplorer();
        }
      });
      bindClick('closeDbExplorer', closeDbExplorer);
      bindClick('closeDbExplorerIcon', closeDbExplorer);
      bindClick('dbExplorerModalBackdrop', closeDbExplorer);
      bindClick('dbSearchButton', () => fetchDbExplorerRows(true));
      bindEvent('dbSearchInput', 'keydown', (event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          fetchDbExplorerRows(true);
        }
      });
      bindClick('dbClearSearch', () => {
        const input = byId('dbSearchInput');
        if (input) {
          input.value = '';
        }
        fetchDbExplorerRows(true);
      });
      bindClick('dbPrevPage', () => {
        state.dbBrowserOffset = Math.max(0, state.dbBrowserOffset - state.dbBrowserLimit);
        fetchDbExplorerRows(false);
      });
      bindClick('dbNextPage', () => {
        state.dbBrowserOffset = state.dbBrowserOffset + state.dbBrowserLimit;
        fetchDbExplorerRows(false);
      });
      bindClick('openSettings', openSettingsDrawer);
      bindClick('startShortTutorial', () => {
        closeSettingsDrawer();
        tutorialStart(true, 'short');
      });
      bindClick('startLongTutorial', () => {
        closeSettingsDrawer();
        tutorialStart(true, 'full');
      });
      bindClick('closeSettings', closeSettingsDrawer);
      bindClick('closeSettingsIcon', closeSettingsDrawer);
      bindClick('settingsModalBackdrop', closeSettingsDrawer);
      bindClick('applySettings', saveSettingsToState);
      bindClick('send', sendQuestion);
      bindClick('tutorialBack', tutorialBackStep);
      bindClick('tutorialStop', () => tutorialStop('dismissed'));
      bindClick('tutorialNext', tutorialNextStep);
      bindEvent('question', 'keydown', (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
          event.preventDefault();
          sendQuestion();
        }
      });
      bindEvent('question', 'input', () => {
        const value = String(byId('question').value || '').trim();
        if (value) {
          tutorialSignal('question_typed');
        }
      });
      bindClick('runCompare', runCompare);
      bindClick('refreshDiagnostics', fetchRecentDiagnostics);
      bindClick('refreshFailureAtlas', fetchFailureAtlas);
      bindClick('logoutBtn', logout);
      bindClick('saveSession', saveSession);
      bindClick('exportSummary', exportSummary);
      bindClick('copyCitations', copyCitations);
      bindClick('closeDrawer', closeDrawer);
      bindClick('drawerBackdrop', () => {
        closeDrawer();
        closeSettingsDrawer();
      });
      window.addEventListener('resize', tutorialRenderCurrentStep);
      window.addEventListener('scroll', tutorialRenderCurrentStep, { passive: true });
      window.addEventListener('keydown', (event) => {
        if (!state.tutorial.running) {
          return;
        }
        if (event.key === 'Escape') {
          event.preventDefault();
          tutorialStop('dismissed');
          return;
        }
        if (event.key === 'Enter') {
          const nextBtn = byId('tutorialNext');
          if (nextBtn && !nextBtn.disabled) {
            event.preventDefault();
            tutorialNextStep();
          }
        }
      });

      (async () => {
        applySettingsFromState();
        applyTranslations();
        await fetchAuthStatus();
        startAuthRefreshLoop();
        fetchStatus();
        if (!state.authEnabled || state.isAuthenticated) {
          fetchRecentDiagnostics();
          fetchFailureAtlas();
          renderEvidenceRows([]);
          await loadLatestSessionId();
          await loadSession(state.activeSessionId);
          tutorialStart(false, 'short');
        }
        updateReportActionsAvailability(Boolean(state.lastReport));
        updateReliabilityLabel();
      })();
    </script>
  </body>
</html>
"""
)


LOGIN_TEMPLATE = Template(
    """
<!doctype html>
<html lang="en" class="light">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>MTVL AI | Authentication</title>
    $favicon_tag
    <script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Courier+Prime&display=swap" rel="stylesheet" />
    <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet" />
    <style>
      body {
        font-family: 'Inter', sans-serif;
        background-color: #f8fafc;
      }
      .material-symbols-outlined {
        font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
        display: inline-block;
        vertical-align: middle;
      }
      .evidence-card {
        border: 1px solid #e2e8f0;
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
      }
      .evidence-card:hover {
        border-color: #cbd5e1;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
      }
      .accent-bar {
        width: 4px;
        background-color: #003c90;
        border-radius: 4px 0 0 4px;
      }
      .skeleton {
        position: relative;
        overflow: hidden;
        background: #e2e8f0;
      }
      .skeleton::after {
        content: '';
        position: absolute;
        inset: 0;
        transform: translateX(-100%);
        background: linear-gradient(90deg, rgba(226, 232, 240, 0) 0%, rgba(248, 250, 252, 0.9) 50%, rgba(226, 232, 240, 0) 100%);
        animation: skeleton-shimmer 1.2s ease-in-out infinite;
      }
      @keyframes skeleton-shimmer {
        100% {
          transform: translateX(100%);
        }
      }
      #loginDbWidget.loading #loginTotalNodes,
      #loginDbWidget.loading #loginDbUpdatedText,
      #loginDbWidget.loading #loginDbState {
        color: transparent;
      }
      #loginDbWidget.loading #loginTotalNodes,
      #loginDbWidget.loading #loginDbUpdatedText,
      #loginDbWidget.loading #loginDbState,
      #loginDbWidget.loading .login-source-skeleton {
        border-radius: 4px;
      }
      #loginDbWidget.loading #loginTotalNodes,
      #loginDbWidget.loading #loginDbUpdatedText,
      #loginDbWidget.loading #loginDbState,
      #loginDbWidget.loading .login-source-skeleton {
        background: #e2e8f0;
      }
      #loginDbWidget.loading #loginTotalNodes,
      #loginDbWidget.loading #loginDbUpdatedText,
      #loginDbWidget.loading #loginDbState,
      #loginDbWidget.loading .login-source-skeleton {
        position: relative;
        overflow: hidden;
      }
      #loginDbWidget.loading #loginTotalNodes::after,
      #loginDbWidget.loading #loginDbUpdatedText::after,
      #loginDbWidget.loading #loginDbState::after,
      #loginDbWidget.loading .login-source-skeleton::after {
        content: '';
        position: absolute;
        inset: 0;
        transform: translateX(-100%);
        background: linear-gradient(90deg, rgba(226, 232, 240, 0) 0%, rgba(248, 250, 252, 0.9) 50%, rgba(226, 232, 240, 0) 100%);
        animation: skeleton-shimmer 1.2s ease-in-out infinite;
      }
    </style>
  </head>
  <body class="min-h-screen flex flex-col justify-between overflow-hidden">
    <div class="flex-grow flex items-center justify-center p-4 relative z-10 flex-col">
      <main class="w-full max-w-[420px] bg-white evidence-card rounded-lg overflow-hidden flex shadow-sm">
        <div class="accent-bar"></div>
        <div class="flex-1 p-6 flex flex-col gap-6 relative">
          <a href="/" class="absolute top-4 left-4 text-sm text-blue-900 hover:underline">← Back to home</a>
          <div class="flex flex-col items-center text-center gap-2">
            $logo_html
            <p class="text-xs font-semibold text-blue-900 uppercase tracking-widest">Open Source Intelligence</p>
          </div>
          <div id="loginIntro" class="flex flex-col gap-1 text-center">
            <h2 class="text-2xl font-semibold text-slate-900">Sign In</h2>
            <p id="loginIntroText" class="text-sm text-slate-600 px-4">Enter your email to receive a magic link.</p>
          </div>
          <div id="loginRequestPanel" class="flex flex-col gap-4">
            <form id="loginForm" class="flex flex-col gap-4">
              <div class="flex flex-col gap-1">
                <label class="text-xs font-medium text-slate-600 ml-1" for="loginEmail">Email</label>
                <div class="relative">
                  <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-[20px]">mail</span>
                  <input id="loginEmail" class="w-full pl-10 pr-4 py-2.5 bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-900/20 focus:border-blue-900 text-sm" placeholder="name@university.edu" required type="email" />
                </div>
              </div>
              <button id="requestMagicLink" class="w-full bg-blue-900 hover:bg-blue-700 text-white text-sm font-semibold py-3 rounded-lg transition-colors flex items-center justify-center gap-2 group shadow-sm active:scale-[0.98]" type="submit">
                Send Magic Link
                <span class="material-symbols-outlined text-[20px] transition-transform group-hover:translate-x-1">arrow_forward</span>
              </button>
            </form>
            <div id="loginStatus" class="text-xs text-slate-500 text-center">Use your email to receive a secure sign-in link.</div>
          </div>
          <div id="loginResultPanel" class="hidden flex flex-col gap-4 text-center">
            <div id="loginResultIconWrap" class="w-12 h-12 mx-auto flex items-center justify-center rounded-full">
              <span id="loginResultIcon" class="material-symbols-outlined !text-[28px]">mark_email_read</span>
            </div>
            <div class="flex flex-col gap-2">
              <h3 id="loginResultTitle" class="text-lg font-semibold text-slate-900">Check your email</h3>
              <p id="loginResultMessage" class="text-sm text-slate-600 px-2"></p>
              <p id="loginResultHint" class="text-xs text-slate-500 px-2"></p>
            </div>
            <div id="loginDevLinkWrap" class="text-xs hidden text-center">
              <a id="loginDevLink" href="#" target="_blank" rel="noopener noreferrer" class="text-blue-900 underline">Open dev magic link</a>
            </div>
            <button id="loginTryAgain" type="button" class="text-sm font-medium text-blue-900 hover:underline">Use a different email</button>
          </div>
        </div>
      </main>
      <div id="loginDbWidget" class="w-full max-w-[420px] mt-4 bg-white/90 border border-slate-200 rounded-lg p-4 flex flex-col gap-2 shadow-sm backdrop-blur-sm loading">
        <div class="flex justify-between items-center">
          <h3 class="text-xs font-semibold text-slate-800 uppercase tracking-widest">Database Status</h3>
          <div class="flex items-center gap-1.5">
            <span id="loginDbDot" class="w-2 h-2 bg-emerald-500 rounded-full"></span>
            <span id="loginDbUpdated" class="text-[11px] text-slate-600">Last Updated: <span id="loginDbUpdatedText">checking...</span></span>
          </div>
        </div>
        <div class="flex items-baseline gap-2">
          <span id="loginTotalNodes" class="text-xl font-semibold text-blue-900">-</span>
          <span class="text-xs text-slate-600">Total Evidence Nodes</span>
        </div>
        <div id="loginSourceList" class="flex flex-col gap-2 mt-1">
          <div class="login-source-skeleton h-2.5 w-full"></div>
          <div class="login-source-skeleton h-2.5 w-[86%]"></div>
          <div class="login-source-skeleton h-2.5 w-[73%]"></div>
        </div>
        <div id="loginDbState" class="text-[11px] text-slate-500 mt-1">Loading database state...</div>
      </div>
    </div>
    <footer class="w-full bg-slate-100 border-t border-slate-200 flex flex-col md:flex-row justify-between items-center px-4 py-6 max-w-[1440px] mx-auto relative z-10">
      <span class="text-xs text-slate-600">© $current_year MTVL AI. Open source project.</span>
      <div class="flex gap-6 mt-4 md:mt-0">
        <a class="text-xs text-slate-600 hover:underline hover:text-blue-900" href="/privacy">Privacy Policy</a>
        <a class="text-xs text-slate-600 hover:underline hover:text-blue-900" href="/terms">Terms of Service</a>
      </div>
    </footer>
    <script>
      const state = { authEnabled: $auth_enabled };

      function byId(id) {
        return document.getElementById(id);
      }

      function setLoginStatus(text, isError = false) {
        const el = byId('loginStatus');
        if (!el) return;
        el.textContent = String(text || '');
        el.classList.toggle('text-red-700', Boolean(isError));
        el.classList.toggle('text-slate-500', !isError);
      }

      function showLoginRequestPanel() {
        const requestPanel = byId('loginRequestPanel');
        const resultPanel = byId('loginResultPanel');
        const intro = byId('loginIntro');
        const introText = byId('loginIntroText');
        if (requestPanel) requestPanel.classList.remove('hidden');
        if (resultPanel) resultPanel.classList.add('hidden');
        if (intro) intro.classList.remove('hidden');
        if (introText) introText.textContent = 'Enter your email to receive a magic link.';
        setLoginStatus('Use your email to receive a secure sign-in link.', false);
      }

      function showLoginResultPanel({ title, message, hint = '', isError = false, devLink = '' }) {
        const requestPanel = byId('loginRequestPanel');
        const resultPanel = byId('loginResultPanel');
        const intro = byId('loginIntro');
        const iconWrap = byId('loginResultIconWrap');
        const icon = byId('loginResultIcon');
        const titleEl = byId('loginResultTitle');
        const messageEl = byId('loginResultMessage');
        const hintEl = byId('loginResultHint');
        const tryAgain = byId('loginTryAgain');
        const devWrap = byId('loginDevLinkWrap');
        const devLinkEl = byId('loginDevLink');
        if (requestPanel) requestPanel.classList.add('hidden');
        if (resultPanel) resultPanel.classList.remove('hidden');
        if (intro) intro.classList.add('hidden');
        if (iconWrap) {
          iconWrap.classList.toggle('bg-emerald-100', !isError);
          iconWrap.classList.toggle('text-emerald-700', !isError);
          iconWrap.classList.toggle('bg-red-100', isError);
          iconWrap.classList.toggle('text-red-700', isError);
        }
        if (icon) icon.textContent = isError ? 'error' : 'mark_email_read';
        if (titleEl) titleEl.textContent = String(title || (isError ? 'Could not send email' : 'Check your email'));
        if (messageEl) messageEl.textContent = String(message || '');
        if (hintEl) {
          hintEl.textContent = String(hint || '');
          hintEl.classList.toggle('hidden', !hint);
        }
        if (tryAgain) tryAgain.classList.toggle('hidden', titleEl && titleEl.textContent === 'Verifying sign-in link');
        if (devWrap && devLinkEl) {
          if (!isError && devLink) {
            devLinkEl.href = String(devLink);
            devWrap.classList.remove('hidden');
          } else {
            devWrap.classList.add('hidden');
          }
        }
      }

      function setLoginSendingState() {
        const requestPanel = byId('loginRequestPanel');
        const resultPanel = byId('loginResultPanel');
        const submitButton = byId('requestMagicLink');
        if (requestPanel) requestPanel.classList.remove('hidden');
        if (resultPanel) resultPanel.classList.add('hidden');
        if (submitButton) submitButton.disabled = true;
        setLoginStatus('Sending magic link...', false);
      }

      function clearLoginSendingState() {
        const submitButton = byId('requestMagicLink');
        if (submitButton) submitButton.disabled = false;
      }

      function formatCompactCount(value) {
        const n = Number(value || 0);
        if (!Number.isFinite(n) || n <= 0) return '0';
        if (n >= 1000000) return (n / 1000000).toFixed(1).replace(/\.0$$/, '') + 'M+';
        if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$$/, '') + 'k';
        return String(n);
      }

      function formatRelativeIso(isoText) {
        const raw = String(isoText || '').trim();
        if (!raw) return 'not yet synced';
        const ms = Date.parse(raw);
        if (!Number.isFinite(ms)) return raw;
        const deltaMinutes = Math.max(0, Math.floor((Date.now() - ms) / 60000));
        if (deltaMinutes < 1) return 'just now';
        if (deltaMinutes < 60) return deltaMinutes + 'm ago';
        const deltaHours = Math.floor(deltaMinutes / 60);
        if (deltaHours < 24) return deltaHours + 'h ago';
        const deltaDays = Math.floor(deltaHours / 24);
        return deltaDays + 'd ago';
      }

      function escapeHtml(text) {
        return String(text || '')
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;')
          .replace(/'/g, '&#39;');
      }

      function renderSourceBreakdown(rows, total) {
        const list = byId('loginSourceList');
        if (!list) return;
        const safeRows = Array.isArray(rows) ? rows : [];
        if (!safeRows.length) {
          list.innerHTML = '<div class="text-[11px] text-slate-500">No source metadata available yet.</div>';
          return;
        }
        const denom = total > 0 ? total : 1;
        const shades = ['bg-blue-900', 'bg-blue-800', 'bg-blue-700', 'bg-blue-600', 'bg-slate-500'];
        list.innerHTML = safeRows.map((row, index) => {
          const source = escapeHtml(String(row && row.source ? row.source : 'unknown'));
          const count = Number(row && row.articles ? row.articles : 0);
          const safeCount = Number.isFinite(count) && count > 0 ? count : 0;
          const width = Math.max(0, Math.min(100, (safeCount / denom) * 100));
          const widthText = width.toFixed(1).replace(/\.0$$/, '');
          const cls = shades[Math.min(index, shades.length - 1)];
          return '<div class="flex flex-col gap-1">'
            + '<div class="flex justify-between text-[11px] text-slate-600">'
            + '<span>' + source + '</span>'
            + '<span>' + formatCompactCount(safeCount) + '</span>'
            + '</div>'
            + '<div class="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">'
            + '<div class="' + cls + ' h-full rounded-full" style="width: ' + widthText + '%"></div>'
            + '</div>'
            + '</div>';
        }).join('');
      }

      function renderLoginMetadata(data) {
        const widget = byId('loginDbWidget');
        const totalNodes = byId('loginTotalNodes');
        const updatedText = byId('loginDbUpdatedText');
        const dot = byId('loginDbDot');
        const dbState = byId('loginDbState');

        const total = Number(data.records_total || 0);
        const sourceRows = Array.isArray(data.source_breakdown) ? data.source_breakdown : [];
        const syncText = formatRelativeIso(data.latest_sync_at);

        if (widget) widget.classList.remove('loading');
        if (totalNodes) totalNodes.textContent = formatCompactCount(total);
        if (updatedText) updatedText.textContent = syncText;
        renderSourceBreakdown(sourceRows, total);

        if (dot) {
          dot.classList.remove('bg-emerald-500', 'bg-amber-500');
          dot.classList.add(total > 0 ? 'bg-emerald-500' : 'bg-amber-500');
        }
        if (dbState) dbState.textContent = total > 0 ? 'Database is online and query-ready.' : 'Database online, waiting for first ingestion.';
      }

      async function fetchAuthStatus() {
        if (!state.authEnabled) {
          window.location.replace('/app');
          return;
        }
        try {
          const resp = await fetch('/api/auth/status');
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.error || 'auth status failed');
          if (data.authenticated) {
            const params = new URLSearchParams(window.location.search || '');
            const next = String(params.get('next') || '/app').trim() || '/app';
            window.location.replace(next.startsWith('/') ? next : '/app');
          }
        } catch (_) {}
      }

      async function fetchLoginMetadata() {
        const widget = byId('loginDbWidget');
        const dbState = byId('loginDbState');
        const sourceList = byId('loginSourceList');
        if (widget) widget.classList.add('loading');
        if (sourceList) {
          sourceList.innerHTML = '<div class="login-source-skeleton h-2.5 w-full"></div>'
            + '<div class="login-source-skeleton h-2.5 w-[86%]"></div>'
            + '<div class="login-source-skeleton h-2.5 w-[73%]"></div>';
        }
        if (dbState) dbState.textContent = 'Loading database state...';
        try {
          const resp = await fetch('/api/auth/login-metadata');
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.error || 'metadata failed');
          renderLoginMetadata(data);
        } catch (error) {
          if (widget) widget.classList.remove('loading');
          if (dbState) dbState.textContent = String(error);
        }
      }

      async function requestMagicLink() {
        const emailInput = byId('loginEmail');
        const email = String(emailInput && emailInput.value ? emailInput.value : '').trim();
        if (!email) {
          setLoginStatus('Email is required.', true);
          return;
        }
        setLoginSendingState();
        try {
          const resp = await fetch('/api/auth/request-link', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email }),
          });
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.error || 'Could not send magic link');
          const deliveryMode = String(data.delivery_mode || 'smtp');
          const devLink = data.magic_link ? String(data.magic_link) : '';
          showLoginResultPanel({
            title: 'Check your email',
            message: deliveryMode === 'smtp'
              ? 'We sent a secure sign-in link to ' + email + '.'
              : 'Your sign-in link is ready for ' + email + '.',
            hint: deliveryMode === 'smtp'
              ? 'Open your inbox and click the link to continue. It expires in 15 minutes. Check spam if you do not see it.'
              : 'Use the dev link below to sign in during local testing.',
            isError: false,
            devLink,
          });
        } catch (error) {
          showLoginResultPanel({
            title: 'Could not send email',
            message: String(error),
            hint: 'Please try again. If the problem continues, contact your administrator.',
            isError: true,
          });
        } finally {
          clearLoginSendingState();
        }
      }

      async function verifyMagicLinkFromUrl() {
        const params = new URLSearchParams(window.location.search || '');
        const token = String(params.get('magic_token') || '').trim();
        if (!token) return;
        showLoginResultPanel({
          title: 'Verifying sign-in link',
          message: 'Please wait while we verify your magic link.',
          hint: '',
          isError: false,
        });
        try {
          const resp = await fetch('/api/auth/verify-link', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token }),
          });
          const data = await resp.json();
          if (!resp.ok) throw new Error(data.error || 'Could not verify magic link');
          const params = new URLSearchParams(window.location.search || '');
          const next = String(params.get('next') || '/app').trim() || '/app';
          window.location.replace(next.startsWith('/') ? next : '/app');
        } catch (error) {
          showLoginResultPanel({
            title: 'Sign-in link invalid',
            message: String(error),
            hint: 'Request a new magic link to try again.',
            isError: true,
          });
        }
      }

      const form = byId('loginForm');
      if (form) {
        form.addEventListener('submit', (event) => {
          event.preventDefault();
          requestMagicLink();
        });
      }

      const tryAgainButton = byId('loginTryAgain');
      if (tryAgainButton) {
        tryAgainButton.addEventListener('click', () => {
          showLoginRequestPanel();
        });
      }

      (async () => {
        await fetchAuthStatus();
        await fetchLoginMetadata();
        await verifyMagicLinkFromUrl();
      })();
    </script>
  </body>
</html>
"""
)


LEGAL_TEMPLATE = Template(
    """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>$page_title | MTVL AI</title>
    $favicon_tag
    <script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
    <style>
      body {
        font-family: 'Inter', sans-serif;
        background-color: #f8fafc;
      }
      .legal-card {
        border: 1px solid #e2e8f0;
        box-shadow: 0 6px 18px -12px rgba(15, 23, 42, 0.24);
      }
      .doc-content h2.doc-heading,
      .doc-content h3.doc-heading,
      .doc-content h4.doc-heading {
        color: #0f172a;
        font-weight: 600;
        margin-top: 1.75rem;
        margin-bottom: 0.75rem;
      }
      .doc-content h2.doc-heading { font-size: 1.25rem; }
      .doc-content h3.doc-heading { font-size: 1.125rem; }
      .doc-content h4.doc-heading { font-size: 1rem; }
      .doc-content .doc-paragraph {
        margin-bottom: 1rem;
        line-height: 1.65;
      }
      .doc-content .doc-ul,
      .doc-content .doc-ol {
        margin: 0 0 1rem 1.25rem;
        padding-left: 1rem;
      }
      .doc-content .doc-ul { list-style: disc; }
      .doc-content .doc-ol { list-style: decimal; }
      .doc-content li { margin-bottom: 0.35rem; }
      .doc-content .doc-inline-code {
        background: #f1f5f9;
        border-radius: 0.25rem;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        font-size: 0.85em;
        padding: 0.1rem 0.35rem;
      }
      .doc-content .doc-link {
        color: #1e3a8a;
        text-decoration: underline;
      }
      .doc-content .doc-link:hover { color: #1d4ed8; }
      .doc-content .doc-table-wrap {
        margin: 1rem 0 1.25rem;
        overflow-x: auto;
      }
      .doc-content .doc-table {
        border-collapse: collapse;
        font-size: 0.875rem;
        width: 100%;
      }
      .doc-content .doc-table th,
      .doc-content .doc-table td {
        border: 1px solid #e2e8f0;
        padding: 0.55rem 0.75rem;
        text-align: left;
        vertical-align: top;
      }
      .doc-content .doc-table th {
        background: #f8fafc;
        color: #0f172a;
        font-weight: 600;
      }
      .doc-nav {
        border-bottom: 1px solid #e2e8f0;
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem 1rem;
        margin-bottom: 1.5rem;
        padding-bottom: 1rem;
      }
      .doc-nav a {
        color: #475569;
        font-size: 0.875rem;
        text-decoration: none;
      }
      .doc-nav a:hover { color: #1e3a8a; text-decoration: underline; }
      .doc-nav a.is-active {
        color: #1e3a8a;
        font-weight: 600;
      }
    </style>
  </head>
  <body class="min-h-screen flex flex-col">
    <main class="flex-1 w-full max-w-4xl mx-auto p-6 md:p-10">
      <div class="legal-card bg-white rounded-xl p-6 md:p-8">
        <div class="flex items-center justify-between gap-3 mb-6">
          <h1 class="text-2xl font-semibold text-slate-900">$page_title</h1>
          <a href="/" class="text-sm text-blue-900 hover:underline">Back to home</a>
        </div>
        <div class="doc-content text-sm leading-6 text-slate-700">
          $page_body
        </div>
      </div>
    </main>
    <footer class="w-full border-t border-slate-200 bg-white px-6 py-4 text-xs text-slate-600">
      <div class="max-w-4xl mx-auto flex items-center justify-between gap-3">
        <span>© $current_year MTVL AI. Open source project.</span>
        <div class="flex items-center gap-4">
          <a href="/privacy" class="hover:underline">Privacy Policy</a>
          <a href="/terms" class="hover:underline">Terms of Service</a>
        </div>
      </div>
    </footer>
  </body>
</html>
"""
)


def _json_response(
    handler: BaseHTTPRequestHandler,
    status: int,
    payload: dict[str, Any],
    *,
    extra_headers: dict[str, str] | None = None,
) -> None:
    body = json.dumps(payload, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    if extra_headers:
        for key, value in extra_headers.items():
            handler.send_header(str(key), str(value))
    handler.end_headers()
    handler.wfile.write(body)


def _stream_json_event(handler: BaseHTTPRequestHandler, payload: dict[str, Any]) -> None:
    line = json.dumps(payload, ensure_ascii=True).encode("utf-8") + b"\n"
    handler.wfile.write(line)
    handler.wfile.flush()


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, object]:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length > 0 else b"{}"
    try:
        parsed = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Request body must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Request body must be a JSON object")
    return parsed


def _new_trace_id() -> str:
    return f"trace_{int(time.time() * 1000)}_{int(time.perf_counter() * 1000000) % 1000000:06d}"


def _append_query_telemetry(trace: dict[str, object]) -> None:
    with _RECENT_QUERY_TELEMETRY_LOCK:
        _RECENT_QUERY_TELEMETRY.appendleft(trace)


def _recent_query_telemetry(limit: int = 25) -> list[dict[str, object]]:
    safe_limit = max(1, min(int(limit or 25), TELEMETRY_MAX_RECENT))
    with _RECENT_QUERY_TELEMETRY_LOCK:
        return list(_RECENT_QUERY_TELEMETRY)[:safe_limit]


def _extract_latest_user_message(messages: list[dict[str, object]]) -> str:
    for message in reversed(messages):
        if str(message.get("role", "")).lower() == "user":
            content = str(message.get("content", "")).strip()
            if content:
                return content
    return ""


def _build_chat_prompt(
  messages: list[dict[str, object]],
  evidence_rows: list[dict[str, object]],
  context_limit: int,
  language: str,
) -> str:
    latest_user_message = _extract_latest_user_message(messages)
    if not latest_user_message:
        raise ValueError("At least one user message is required")

    prompt = build_grounded_prompt(latest_user_message, evidence_rows, context_limit=context_limit)
    language_normalized = str(language or "en").strip().lower()
    if language_normalized == "es":
      prompt += "\n\nOutput language requirement: Respond entirely in Spanish."
    else:
      prompt += "\n\nOutput language requirement: Respond entirely in English."
    transcript_lines: list[str] = []
    for message in messages[-20:]:
        role = str(message.get("role", "")).strip().lower()
        content = str(message.get("content", "")).strip()
        if not role or not content:
            continue
        transcript_lines.append(f"{role.title()}: {content}")

    if transcript_lines:
        prompt += "\n\nConversation history:\n" + "\n".join(transcript_lines)
    return prompt


def _apply_evidence_filters(evidence_rows: list[dict[str, object]], filters: dict[str, object]) -> list[dict[str, object]]:
    if not filters:
        return list(evidence_rows)
    evidence_types = {
        str(x).strip().lower()
        for x in (filters.get("evidence_types") or [])
        if str(x).strip()
    }
    date_window = str(filters.get("date_window", "all")).strip().lower()
    highlight_contradictions = bool(filters.get("highlight_contradictions", False))
    try:
        min_reliability = float(filters.get("min_reliability", 0.0))
    except (TypeError, ValueError):
        min_reliability = 0.0

    current_year = time.gmtime().tm_year

    output: list[dict[str, object]] = []
    for row in evidence_rows:
      raw_reliability = row.get("reliability_score")
      if raw_reliability in {None, ""}:
        if min_reliability > 0.0:
          continue
        reliability = 0.0
      else:
        try:
          reliability = float(raw_reliability)
        except (TypeError, ValueError):
          if min_reliability > 0.0:
            continue
          reliability = 0.0

      if reliability < min_reliability:
        continue

      if evidence_types:
        causal_type = str(row.get("causal_evidence_type", "")).strip().lower()
        if causal_type not in evidence_types:
          continue

      row_year = int(row.get("year", 0) or 0)
      if date_window == "last5" and row_year and row_year < current_year - 5:
        continue
      if date_window == "last10" and row_year and row_year < current_year - 10:
        continue

      output.append(row)

    if highlight_contradictions:
        output.sort(
            key=lambda row: (
                0 if str(row.get("effect_direction", "")).strip().lower() == "contradicts" else 1,
                -float(row.get("reliability_score", 0.0) or 0.0),
            )
        )

    return output


def _contradiction_pairs_from_rows(
    evidence_rows: list[dict[str, object]],
    *,
    limit: int = 300,
  ) -> list[dict[str, str | float]]:
    safe_limit = max(1, min(int(limit or 300), 2000))
    by_entity: dict[str, dict[str, list[dict[str, object]]]] = {}

    for row in evidence_rows:
      entity = str(row.get("entity", "")).strip().lower()
      if not entity:
        continue
      direction = str(row.get("effect_direction", "")).strip().lower()
      bucket = by_entity.setdefault(entity, {"supports": [], "contradicts": []})
      if direction == "supports":
        bucket["supports"].append(row)
      elif direction == "contradicts":
        bucket["contradicts"].append(row)

    output: list[dict[str, str | float]] = []
    for entity, buckets in by_entity.items():
      supports = sorted(
        buckets.get("supports", []),
        key=lambda row: -float(row.get("reliability_score", 0.0) or 0.0),
      )[:15]
      contradicts = sorted(
        buckets.get("contradicts", []),
        key=lambda row: -float(row.get("reliability_score", 0.0) or 0.0),
      )[:15]
      if not supports or not contradicts:
        continue

      for support in supports:
        for contra in contradicts:
          outcome_a = str(support.get("outcome", ""))
          outcome_b = str(contra.get("outcome", ""))
          score_a = float(support.get("reliability_score", 0.0) or 0.0)
          score_b = float(contra.get("reliability_score", 0.0) or 0.0)
          contradiction_type = "direction_conflict"
          follow_up = "Run replication study with matched endpoint definitions and harmonized analysis plan."
          if outcome_a != outcome_b:
            contradiction_type = "endpoint_mismatch"
            follow_up = "Design an endpoint-alignment study with both outcomes measured in the same cohort."
          output.append(
            {
              "claim_a": str(support.get("claim_id", "")),
              "claim_b": str(contra.get("claim_id", "")),
              "entity": entity,
              "outcome_a": outcome_a,
              "outcome_b": outcome_b,
              "score_a": score_a,
              "score_b": score_b,
              "contradiction_type": contradiction_type,
              "follow_up_experiment": follow_up,
            }
          )
          if len(output) >= safe_limit:
            output.sort(key=lambda row: -(float(row.get("score_a", 0.0)) + float(row.get("score_b", 0.0))))
            return output

    output.sort(key=lambda row: -(float(row.get("score_a", 0.0)) + float(row.get("score_b", 0.0))))
    return output[:safe_limit]


def _should_translate_cited_rows(*, payload: dict[str, object], language: str) -> bool:
    if str(language or "").strip().lower() != "es":
      return False

    explicit = payload.get("translate_evidence_rows")
    if isinstance(explicit, bool):
      return explicit
    if isinstance(explicit, str):
      normalized = explicit.strip().lower()
      if normalized in {"1", "true", "yes", "on"}:
        return True
      if normalized in {"0", "false", "no", "off"}:
        return False

    return str(os.getenv("ALS_TRANSLATE_EVIDENCE_ROWS", "0")).strip().lower() in {"1", "true", "yes", "on"}


def _search_evidence_rows(evidence_rows: list[dict[str, object]], query: str) -> list[dict[str, object]]:
    q = query.strip().lower()
    if not q:
        return list(evidence_rows)

    output: list[dict[str, object]] = []
    for row in evidence_rows:
        haystack = " ".join(
            [
                str(row.get("claim_id", "")),
                str(row.get("claim_text", "")),
                str(row.get("entity", "")),
                str(row.get("outcome", "")),
                str(row.get("source_doi", "")),
            ]
        ).lower()
        if q in haystack:
            output.append(row)
    return output


def _build_source_url_for_row(row: dict[str, object]) -> str:
    claim_id = str(row.get("claim_id", "") or "").strip()
    source_doi = str(row.get("source_doi", "") or "").strip()
    if not source_doi:
        return ""

    lower_source = source_doi.lower()
    if lower_source.startswith("http://") or lower_source.startswith("https://"):
        return source_doi

    if claim_id.upper().startswith("PUBMED_") and source_doi.isdigit():
        return f"https://pubmed.ncbi.nlm.nih.gov/{source_doi}/"

    if claim_id.upper().startswith("CTGOV_") and source_doi.upper().startswith("NCT"):
        return f"https://clinicaltrials.gov/study/{source_doi}"

    if claim_id.upper().startswith("NCBI_GENE_") and source_doi.isdigit():
      return f"https://www.ncbi.nlm.nih.gov/gene/{source_doi}"

    if claim_id.upper().startswith("UNIPROT_"):
      return f"https://www.uniprot.org/uniprotkb/{source_doi}"

    if claim_id.upper().startswith("GO_"):
      return f"https://www.ebi.ac.uk/QuickGO/term/{source_doi}"

    if claim_id.upper().startswith("REACTOME_"):
      return f"https://reactome.org/content/detail/{source_doi}"

    if claim_id.upper().startswith("GEO_"):
      return f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={source_doi}"

    if claim_id.upper().startswith("ARRAYEXPRESS_"):
      return f"https://www.ebi.ac.uk/biostudies/arrayexpress/studies/{source_doi}"

    if claim_id.upper().startswith("KEGG_"):
      return f"https://www.kegg.jp/entry/{source_doi}"

    if claim_id.upper().startswith("PRIDE_"):
      return f"https://www.ebi.ac.uk/pride/archive/projects/{source_doi}"

    if claim_id.upper().startswith("METABOLOMICS_WORKBENCH_"):
      return f"https://www.metabolomicsworkbench.org/data/show_study.php?STUDY_ID={source_doi}"

    if claim_id.upper().startswith("CHEMBL_"):
      return f"https://www.ebi.ac.uk/chembl/compound_report_card/{source_doi}/"

    if claim_id.upper().startswith("OPEN_TARGETS_"):
      return f"https://platform.opentargets.org/search?q={source_doi}"

    if claim_id.upper().startswith("FDA_LABELS_"):
      return "https://open.fda.gov/apis/drug/label/"

    if source_doi.isdigit():
        return f"https://pubmed.ncbi.nlm.nih.gov/{source_doi}/"

    if source_doi.upper().startswith("NCT"):
        return f"https://clinicaltrials.gov/study/{source_doi}"

    return f"https://doi.org/{source_doi}"


def _attach_source_urls_to_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for row in rows:
        updated = dict(row)
        updated["source_url"] = _build_source_url_for_row(updated)
        output.append(updated)
    return output


def _parse_positive_int(value: object, default: int, *, min_value: int = 1, max_value: int = 500) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < min_value:
        return min_value
    if parsed > max_value:
        return max_value
    return parsed


def _parse_non_negative_int(value: object, default: int, *, max_value: int = 100000) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < 0:
        return 0
    if parsed > max_value:
        return max_value
    return parsed


def _resolve_chat_evidence_limit(payload: dict[str, object]) -> int | None:
    raw_value = payload.get("evidence_max_rows")
    if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
      raw_value = os.getenv("ALS_CHAT_EVIDENCE_MAX_ROWS", "0")

    try:
      parsed = int(raw_value)
    except (TypeError, ValueError):
      parsed = 0

    if parsed <= 0:
      return None
    return min(parsed, 20000)


def _paginate_rows(rows: list[dict[str, object]], *, limit: int, offset: int) -> tuple[list[dict[str, object]], int, bool]:
    total = len(rows)
    start = min(offset, total)
    end = min(start + limit, total)
    page_rows = rows[start:end]
    return page_rows, total, end < total


def _build_report_markdown(payload: dict[str, object]) -> str:
    synthesis = payload.get("synthesis") if isinstance(payload.get("synthesis"), dict) else {}
    synthesis = synthesis if isinstance(synthesis, dict) else {}

    answer = str(synthesis.get("direct_answer") or payload.get("answer") or "")
    supporting_ids = synthesis.get("supporting_claim_ids") if isinstance(synthesis.get("supporting_claim_ids"), list) else []
    supporting_ids = [str(x) for x in supporting_ids]
    contradictions = str(synthesis.get("contradictions_summary") or "")
    next_step = str(synthesis.get("next_validation_step") or "")
    generated_seconds = float(payload.get("generated_seconds", 0.0) or 0.0)

    lines = [
        "# Investigator Synthesis Report",
        "",
        f"Generated seconds: {generated_seconds:.3f}",
        "",
        "## Direct Answer",
        answer or "N/A",
    ]

    if supporting_ids:
      lines.extend(["", "## Supporting Evidence Nodes"])
      for claim_id in supporting_ids:
        lines.append(f"- {claim_id}")

    if contradictions:
      lines.extend(["", "## Contradictions and Uncertainty", contradictions])

    if next_step:
      lines.extend(["", "## Next Validation Step", next_step])

    lines.append("")

    return "\n".join(lines)


def _build_investigator_synthesis(
    *,
    evidence_rows: list[dict[str, object]],
    contradiction_rows: list[dict[str, object]],
    require_review_signoff: bool,
    approved_claim_ids: set[str],
    store: Any | None = None,
) -> dict[str, object]:
    from als_intel.agents.debate import build_debate_report
    from als_intel.agents.orchestrator import build_agent_report
    from als_intel.agents.systems_biology import build_systems_biology_report
    from als_intel.hypothesis import build_hypothesis_queue

    systems_biology_report: dict[str, object] = {"count": 0, "items": []}
    support_map: list[dict[str, object]] = []
    neighbor_rows: list[dict[str, object]] = []
    if store is not None:
        support_map = store.graph_support_contradiction_map(limit=30)
        for row in support_map:
            entity = str(row.get("entity", "")).strip()
            if not entity:
                continue
            for neighbor in store.graph_neighbors(entity, limit=6):
                neighbor_rows.append(
                    {
                        "entity": entity,
                        "neighbor_entity": str(neighbor.get("neighbor_label", "")),
                        "neighbor_label": str(neighbor.get("neighbor_label", "")),
                        "edge_type": str(neighbor.get("edge_type", "")),
                        "neighbor_type": str(neighbor.get("neighbor_type", "")),
                        "polarity": str(neighbor.get("polarity", "")),
                        "weight": neighbor.get("weight", 0.0),
                    }
                )
        systems_biology_report = build_systems_biology_report(
            evidence_rows=evidence_rows,
            support_map_rows=support_map,
            graph_neighbor_rows=neighbor_rows,
            limit=5,
        )

    agent_report = build_agent_report(
        evidence_rows=evidence_rows,
        contradiction_rows=contradiction_rows,
        require_review_signoff=require_review_signoff,
        approved_claim_ids=approved_claim_ids,
        support_map_rows=support_map or None,
        graph_neighbor_rows=neighbor_rows or None,
        systems_biology_limit=5,
    )
    if isinstance(agent_report.get("systems_biology_agent"), dict):
        systems_biology_report = agent_report["systems_biology_agent"]

    return {
        "agent_report": agent_report,
        "hypothesis_queue": build_hypothesis_queue(
            evidence_rows=evidence_rows,
            contradiction_rows=contradiction_rows,
            limit=5,
            require_review_signoff=require_review_signoff,
            approved_claim_ids=approved_claim_ids,
        ),
        "debate_report": build_debate_report(
            evidence_rows=evidence_rows,
            contradiction_rows=contradiction_rows,
        ),
        "systems_biology_report": systems_biology_report,
    }


def _evaluate_report_gate(
    *,
    report_payload: dict[str, object],
    evidence_rows: list[dict[str, object]],
    contradiction_rows: list[dict[str, object]],
  ) -> dict[str, object]:
    freshness_window_years = max(0, int(os.getenv("ALS_RUN_GATE_FRESHNESS_WINDOW_YEARS", "5") or 5))
    max_contradiction_density = float(os.getenv("ALS_RUN_GATE_MAX_CONTRADICTION_DENSITY", "1.0") or 1.0)
    require_citation_integrity = os.getenv("ALS_RUN_GATE_REQUIRE_CITATION_INTEGRITY", "1").strip() not in {"0", "false", "False"}
    require_contradiction_summary = os.getenv("ALS_RUN_GATE_REQUIRE_CONTRADICTION_SUMMARY", "1").strip() not in {"0", "false", "False"}

    latest_year = max((int(row.get("year", 0) or 0) for row in evidence_rows), default=0)
    now_year = datetime.now(timezone.utc).year
    freshness_ok = latest_year >= (now_year - freshness_window_years) if latest_year > 0 else False

    composition = report_payload.get("composition") if isinstance(report_payload.get("composition"), dict) else {}
    agent_report = composition.get("agent_report") if isinstance(composition.get("agent_report"), dict) else {}
    supporting_claim_ids = agent_report.get("supporting_claim_ids") if isinstance(agent_report.get("supporting_claim_ids"), list) else []
    evidence_claim_id_set = {str(row.get("claim_id", "")).strip() for row in evidence_rows if str(row.get("claim_id", "")).strip()}
    citation_integrity_measured = bool(supporting_claim_ids) and all(
      str(cid).strip() in evidence_claim_id_set for cid in supporting_claim_ids
    )
    citation_integrity_ok = citation_integrity_measured if require_citation_integrity else True

    contradiction_density = 0.0
    if evidence_rows:
      contradiction_density = len(contradiction_rows) / float(len(evidence_rows))
    contradiction_coverage_measured = not contradiction_rows or bool(agent_report.get("contradictions_summary"))
    contradiction_density_ok = contradiction_density <= max_contradiction_density
    contradiction_coverage_ok = (
      contradiction_density_ok
      and (contradiction_coverage_measured if require_contradiction_summary else True)
    )

    checks = {
      "freshness": {
        "passed": freshness_ok,
        "latest_year": latest_year,
        "threshold_year": now_year - freshness_window_years,
        "window_years": freshness_window_years,
      },
      "citation_integrity": {
        "passed": citation_integrity_ok,
        "measured_passed": citation_integrity_measured,
        "required": require_citation_integrity,
        "supporting_claim_ids_count": len(supporting_claim_ids),
      },
      "contradiction_coverage": {
        "passed": contradiction_coverage_ok,
        "summary_measured_passed": contradiction_coverage_measured,
        "summary_required": require_contradiction_summary,
        "density_passed": contradiction_density_ok,
        "max_density": round(max_contradiction_density, 4),
        "contradiction_density": round(contradiction_density, 4),
        "contradictions": len(contradiction_rows),
      },
    }
    passed = all(bool(item.get("passed", False)) for item in checks.values())
    return {
      "passed": passed,
      "checks": checks,
      "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_replay_diff(
    *,
    baseline_run: dict[str, object],
    current_report: dict[str, object],
    current_quality_gate: dict[str, object],
  ) -> dict[str, object]:
    baseline_report = baseline_run.get("report") if isinstance(baseline_run.get("report"), dict) else {}
    baseline_gate = baseline_run.get("quality_gate") if isinstance(baseline_run.get("quality_gate"), dict) else {}

    baseline_composition = baseline_report.get("composition") if isinstance(baseline_report.get("composition"), dict) else {}
    baseline_agent_report = baseline_composition.get("agent_report") if isinstance(baseline_composition.get("agent_report"), dict) else {}
    baseline_supporting_claim_ids = [
        str(cid).strip()
        for cid in baseline_agent_report.get("supporting_claim_ids", [])
        if str(cid).strip()
    ] if isinstance(baseline_agent_report.get("supporting_claim_ids"), list) else []

    current_composition = current_report.get("composition") if isinstance(current_report.get("composition"), dict) else {}
    current_agent_report = current_composition.get("agent_report") if isinstance(current_composition.get("agent_report"), dict) else {}
    current_supporting_claim_ids = [
        str(cid).strip()
        for cid in current_agent_report.get("supporting_claim_ids", [])
        if str(cid).strip()
    ] if isinstance(current_agent_report.get("supporting_claim_ids"), list) else []

    baseline_count = int(baseline_report.get("evidence_count", 0) or 0)
    current_count = int(current_report.get("evidence_count", 0) or 0)
    baseline_pass = bool(baseline_gate.get("passed", False))
    current_pass = bool(current_quality_gate.get("passed", False))

    baseline_checks = baseline_gate.get("checks") if isinstance(baseline_gate.get("checks"), dict) else {}
    current_checks = current_quality_gate.get("checks") if isinstance(current_quality_gate.get("checks"), dict) else {}
    baseline_contradictions = int(
        (baseline_checks.get("contradiction_coverage") or {}).get("contradictions", 0)
        if isinstance(baseline_checks.get("contradiction_coverage"), dict) else 0
    )
    current_contradictions = int(
        (current_checks.get("contradiction_coverage") or {}).get("contradictions", 0)
        if isinstance(current_checks.get("contradiction_coverage"), dict) else 0
    )
    baseline_density = float(
        (baseline_checks.get("contradiction_coverage") or {}).get("contradiction_density", 0.0)
        if isinstance(baseline_checks.get("contradiction_coverage"), dict) else 0.0
    )
    current_density = float(
        (current_checks.get("contradiction_coverage") or {}).get("contradiction_density", 0.0)
        if isinstance(current_checks.get("contradiction_coverage"), dict) else 0.0
    )

    baseline_citation_set = set(baseline_supporting_claim_ids)
    current_citation_set = set(current_supporting_claim_ids)
    shared_citations = sorted(baseline_citation_set.intersection(current_citation_set))
    union_count = len(baseline_citation_set.union(current_citation_set))
    citation_overlap_ratio = (len(shared_citations) / union_count) if union_count else 1.0

    check_status_changed: list[str] = []
    for check_name in sorted(set(baseline_checks.keys()).union(set(current_checks.keys()))):
        baseline_check_passed = bool(
            (baseline_checks.get(check_name) or {}).get("passed", False)
            if isinstance(baseline_checks.get(check_name), dict) else False
        )
        current_check_passed = bool(
            (current_checks.get(check_name) or {}).get("passed", False)
            if isinstance(current_checks.get(check_name), dict) else False
        )
        if baseline_check_passed != current_check_passed:
            check_status_changed.append(check_name)

    return {
        "baseline_run_id": str(baseline_run.get("run_id", "")),
        "evidence_count_delta": current_count - baseline_count,
        "quality_gate_changed": baseline_pass != current_pass,
        "baseline_passed": baseline_pass,
        "current_passed": current_pass,
        "citation_overlap": {
            "baseline_count": len(baseline_supporting_claim_ids),
            "current_count": len(current_supporting_claim_ids),
            "shared_count": len(shared_citations),
            "shared_claim_ids": shared_citations[:20],
            "overlap_ratio": round(citation_overlap_ratio, 4),
        },
        "contradiction_delta": {
            "baseline_count": baseline_contradictions,
            "current_count": current_contradictions,
            "count_delta": current_contradictions - baseline_contradictions,
            "baseline_density": round(baseline_density, 4),
            "current_density": round(current_density, 4),
            "density_delta": round(current_density - baseline_density, 4),
        },
        "changed_checks": check_status_changed,
    }


def _build_autonomous_run_report(
    *,
    objective: str,
    filters: dict[str, object],
    evidence_rows: list[dict[str, object]],
    contradiction_rows: list[dict[str, object]],
    require_review_signoff: bool,
    approved_claim_ids: set[str],
    store: EvidenceStore | None = None,
  ) -> dict[str, object]:
    composition = _build_investigator_synthesis(
      evidence_rows=evidence_rows,
      contradiction_rows=contradiction_rows,
      require_review_signoff=require_review_signoff,
      approved_claim_ids=approved_claim_ids,
      store=store,
    )
    return {
      "objective": objective,
      "filters": filters,
      "evidence_count": len(evidence_rows),
      "composition": composition,
      "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _execute_investigation_run(
    *,
    store: EvidenceStore,
    user_id: str,
    run_id: str,
    objective: str,
    filters: dict[str, object],
    require_review_signoff: bool,
  ) -> dict[str, object]:
    evidence_rows = _attach_source_urls_to_rows(store.all_evidence())
    filtered_rows = _apply_evidence_filters(evidence_rows, filters)
    contradictions = store.contradiction_pairs()
    approved_claim_ids = store.approved_claim_ids() if require_review_signoff else set()
    report = _build_autonomous_run_report(
      objective=objective,
      filters=filters,
      evidence_rows=filtered_rows,
      contradiction_rows=contradictions,
      require_review_signoff=require_review_signoff,
      approved_claim_ids=approved_claim_ids,
      store=store,
    )
    gate = _evaluate_report_gate(
      report_payload=report,
      evidence_rows=filtered_rows,
      contradiction_rows=contradictions,
    )
    handoff_on_gate_fail = str(os.getenv("ALS_AUTOMATION_HANDOFF_ON_GATE_FAIL", "1")).strip() not in {"0", "false", "False"}
    approval_status = "auto_approved"
    if require_review_signoff:
        approval_status = "pending"
    elif handoff_on_gate_fail and not bool(gate.get("passed", False)):
        approval_status = "pending"

    store.complete_investigation_run(
      user_id=user_id,
      run_id=run_id,
      status="completed",
      report=report,
      quality_gate=gate,
      replay_diff={},
      approval_status=approval_status,
    )
    return store.get_investigation_run(user_id=user_id, run_id=run_id)


def _score_experiment_variant(run_row: dict[str, object]) -> float:
    quality_gate = run_row.get("quality_gate") if isinstance(run_row.get("quality_gate"), dict) else {}
    checks = quality_gate.get("checks") if isinstance(quality_gate.get("checks"), dict) else {}
    contradiction = checks.get("contradiction_coverage") if isinstance(checks.get("contradiction_coverage"), dict) else {}
    contradiction_density = float(contradiction.get("contradiction_density", 1.0) or 1.0)
    evidence_count = int(run_row.get("evidence_count") or (run_row.get("report") or {}).get("evidence_count", 0) or 0)
    gate_bonus = 100.0 if bool(quality_gate.get("passed", False)) else 0.0
    return round(gate_bonus + float(evidence_count) - (contradiction_density * 100.0), 4)


def _execute_due_queued_runs(
    *,
    store: EvidenceStore,
    due_runs: list[dict[str, object]],
    backoff_base_seconds: int,
  ) -> list[dict[str, object]]:
    executed_rows: list[dict[str, object]] = []
    for run in due_runs:
      run_id = str(run.get("run_id", ""))
      user_id = str(run.get("user_id", ""))
      if not run_id or not user_id:
        continue
      try:
        final_row = _execute_investigation_run(
          store=store,
          user_id=user_id,
          run_id=run_id,
          objective=str(run.get("objective", "")),
          filters=run.get("filters") if isinstance(run.get("filters"), dict) else {},
          require_review_signoff=bool(run.get("require_review_signoff", False)),
        )
        executed_rows.append(final_row)
      except Exception as exc:
        attempts = int(run.get("attempt_count", 1) or 1)
        retry_state = store.retry_or_fail_investigation_run(
          user_id=user_id,
          run_id=run_id,
          error_text=str(exc),
          backoff_seconds=backoff_base_seconds * max(1, attempts),
        )
        executed_rows.append(
          {
            "run_id": run_id,
            "user_id": user_id,
            "status": "queued" if bool(retry_state.get("requeued", False)) else "failed",
            "retry": retry_state,
            "error_text": str(exc),
          }
        )
    return executed_rows


def _build_synthesis(
    *,
    answer: str,
    evidence_rows: list[dict[str, object]],
    contradiction_rows: list[dict[str, object]],
) -> dict[str, object]:
  del contradiction_rows  # Synthesis sections are extracted from the model answer only.

  evidence_claim_ids = [str(r.get("claim_id", "")) for r in evidence_rows if str(r.get("claim_id", "")).strip()]
  evidence_claim_id_set = set(evidence_claim_ids)

  mentioned_claim_ids: list[str] = []
  for match in re.finditer(r"claim_id\s*[:=]\s*([A-Za-z0-9_:\-]+)", answer, flags=re.IGNORECASE):
    claim_id = str(match.group(1) or "").strip()
    if not claim_id or claim_id not in evidence_claim_id_set or claim_id in mentioned_claim_ids:
      continue
    mentioned_claim_ids.append(claim_id)

  for claim_id in sorted(evidence_claim_ids, key=len, reverse=True):
    if claim_id in mentioned_claim_ids:
      continue
    if re.search(rf"(?<![A-Za-z0-9_]){re.escape(claim_id)}(?![A-Za-z0-9_])", answer):
      mentioned_claim_ids.append(claim_id)

  supporting_claim_ids = mentioned_claim_ids[:5]

  def _extract_section(text: str, heading_patterns: list[str]) -> str:
    headings_group = "|".join(heading_patterns)
    pattern = re.compile(
      rf"(?is)(?:\*\*\s*(?:{headings_group})\s*\*\*|^\s*#{{1,4}}\s*(?:{headings_group})\s*$)\s*(.+?)(?=\n\s*(?:\*\*|#{{1,4}}\s)|\Z)",
    )
    match = pattern.search(text)
    if not match:
      return ""
    return str(match.group(1) or "").strip()

  contradictions_summary = _extract_section(
    answer,
    [
      r"Contradictions\s+or\s+Uncertainty",
      r"Contradicciones\s+o\s+incertidumbre",
    ],
  )
  next_validation_step = _extract_section(
    answer,
    [
      r"Suggested\s+Validation\s+Next\s+Steps",
      r"Pasos\s+de\s+validaci[o\u00f3]n\s+sugeridos",
      r"Siguientes?\s+pasos?\s+de\s+validaci[o\u00f3]n",
    ],
  )

  synthesis: dict[str, object] = {
    "direct_answer": answer,
  }
  if mentioned_claim_ids:
    synthesis["mentioned_claim_ids"] = mentioned_claim_ids
  if supporting_claim_ids:
    synthesis["supporting_claim_ids"] = supporting_claim_ids
  if contradictions_summary:
    synthesis["contradictions_summary"] = contradictions_summary
  if next_validation_step:
    synthesis["next_validation_step"] = next_validation_step
  return synthesis


def _step_requires_external_integration(step_text: str) -> bool:
    text = str(step_text or "").strip().lower()
    if not text:
      return False

    external_markers = [
      "gtex",
      "tcga",
      "depmap",
      "geo",
      "arrayexpress",
      "uk biobank",
      "clinicaltrials.gov",
      "pubmed api",
      "public database",
      "public dataset",
      "base de datos publica",
      "bases de datos publicas",
      "dataset publico",
      "datos publicos",
      "external api",
      "api externa",
    ]
    return any(marker in text for marker in external_markers)


def _label_next_step_for_capability(step_text: str, language: str) -> tuple[str, bool]:
    normalized = str(step_text or "").strip()
    if not normalized:
      return "", False

    lower = normalized.lower()
    if lower.startswith("requires external integration:") or lower.startswith("requiere integracion externa:"):
      return normalized, False

    if not _step_requires_external_integration(normalized):
      return normalized, False

    language_normalized = str(language or "en").strip().lower()
    if language_normalized == "es":
      return f"Requiere integracion externa: {normalized}", True
    return f"Requires external integration: {normalized}", True


def _verify_cited_claim_ids(
    *,
    synthesis: dict[str, object],
    evidence_rows: list[dict[str, object]],
) -> tuple[dict[str, object], list[str]]:
    guarded = dict(synthesis)
    flags: list[str] = []
    by_id = {
        str(row.get("claim_id", "")).strip(): row
        for row in evidence_rows
        if str(row.get("claim_id", "")).strip()
    }

    for field in ("mentioned_claim_ids", "supporting_claim_ids"):
        raw_ids = guarded.get(field) if isinstance(guarded.get(field), list) else []
        verified: list[str] = []
        for claim_id in raw_ids:
            cid = str(claim_id).strip()
            if not cid:
                continue
            row = by_id.get(cid)
            if row is None:
                flags.append(f"invalid_claim_id:{cid}")
                continue
            if not str(row.get("claim_text", "")).strip():
                flags.append(f"empty_claim_text:{cid}")
            verified.append(cid)
        if verified:
            guarded[field] = verified
        elif field in guarded:
            guarded[field] = []
    return guarded, flags


def _apply_response_guardrails(
    *,
    answer: str,
    synthesis: dict[str, object],
    evidence_rows: list[dict[str, object]],
    contradiction_rows: list[dict[str, object]],
  language: str,
) -> tuple[dict[str, object], list[str]]:
    guarded = dict(synthesis)
    flags: list[str] = []

    direct_answer = str(guarded.get("direct_answer") or answer or "").strip()
    if not direct_answer:
        direct_answer = str(answer or "").strip()
        flags.append("direct_answer_filled")
    guarded["direct_answer"] = direct_answer

    evidence_claim_ids = [str(r.get("claim_id", "")).strip() for r in evidence_rows if str(r.get("claim_id", "")).strip()]
    evidence_claim_id_set = set(evidence_claim_ids)

    mentioned_raw = guarded.get("mentioned_claim_ids") if isinstance(guarded.get("mentioned_claim_ids"), list) else []
    mentioned_claim_ids = [
        str(cid).strip() for cid in mentioned_raw
        if str(cid).strip() and str(cid).strip() in evidence_claim_id_set
    ]
    if evidence_rows and not mentioned_claim_ids:
        ranked = sorted(
            evidence_rows,
            key=lambda row: -float(row.get("reliability_score", 0.0) or 0.0),
        )
        mentioned_claim_ids = [
            str(row.get("claim_id", "")).strip()
            for row in ranked
            if str(row.get("claim_id", "")).strip()
        ][:5]
        if mentioned_claim_ids:
            flags.append("mentioned_claim_ids_filled")
    if mentioned_claim_ids:
        guarded["mentioned_claim_ids"] = mentioned_claim_ids

    supporting_raw = guarded.get("supporting_claim_ids") if isinstance(guarded.get("supporting_claim_ids"), list) else []
    supporting_claim_ids = [
        str(cid).strip() for cid in supporting_raw
        if str(cid).strip() and str(cid).strip() in evidence_claim_id_set
    ]
    if evidence_rows and not supporting_claim_ids:
        supporting_claim_ids = mentioned_claim_ids[:5]
        if supporting_claim_ids:
            flags.append("supporting_claim_ids_filled")
    if supporting_claim_ids:
        guarded["supporting_claim_ids"] = supporting_claim_ids

    contradictions_summary = str(guarded.get("contradictions_summary") or "").strip()
    if contradiction_rows and not contradictions_summary:
        contradictions_summary = (
            "Conflicting evidence is present across sources and study designs; "
            "treat this conclusion as provisional until stratified validation is completed."
        )
        flags.append("contradictions_summary_filled")
    if contradictions_summary:
        guarded["contradictions_summary"] = contradictions_summary

    next_validation_step = str(guarded.get("next_validation_step") or "").strip()
    if not next_validation_step:
        numbered_steps = re.findall(r"(?m)^\s*\d+[\.)]\s+(.+)$", str(answer or ""))
        if numbered_steps:
            next_validation_step = str(numbered_steps[0]).strip()
            flags.append("next_validation_step_extracted")
        elif contradiction_rows:
            next_validation_step = "Run a stratified follow-up validation focusing on cohort and endpoint differences."
            flags.append("next_validation_step_filled")
    if next_validation_step:
      labeled_next_step, was_labeled = _label_next_step_for_capability(next_validation_step, language)
      if was_labeled:
        flags.append("next_validation_step_external_labeled")
      guarded["next_validation_step"] = labeled_next_step

    guarded, verification_flags = _verify_cited_claim_ids(
        synthesis=guarded,
        evidence_rows=evidence_rows,
    )
    flags.extend(verification_flags)
    guarded["verification_flags"] = verification_flags

    return guarded, flags


def _rank_cited_evidence_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    if not rows:
        return []

    current_year = time.gmtime().tm_year
    remaining = list(rows)
    selected: list[dict[str, object]] = []
    by_study_type: dict[str, int] = {}

    def _row_score(row: dict[str, object], diversity_penalty: float) -> float:
        reliability = float(row.get("reliability_score", 0.0) or 0.0)
        year = int(row.get("year", 0) or 0)
        recency = 0.0
        if year > 0:
            recency = max(0.0, min(1.0, (year - 2000) / max(1, current_year - 2000)))
        study_type = str(row.get("study_type", "")).strip().lower()
        study_bonus = {
            "interventional": 0.08,
            "meta_analysis": 0.06,
            "genetic": 0.05,
            "mechanistic": 0.04,
            "observational": 0.03,
        }.get(study_type, 0.02)
        return reliability * 0.72 + recency * 0.18 + study_bonus - diversity_penalty

    while remaining:
        best_row = None
        best_score = float("-inf")
        for row in remaining:
            study_type = str(row.get("study_type", "")).strip().lower() or "unknown"
            penalty = by_study_type.get(study_type, 0) * 0.04
            score = _row_score(row, penalty)
            if score > best_score:
                best_score = score
                best_row = row
        assert best_row is not None
        selected.append(best_row)
        remaining.remove(best_row)
        best_type = str(best_row.get("study_type", "")).strip().lower() or "unknown"
        by_study_type[best_type] = by_study_type.get(best_type, 0) + 1

    return selected


def _extract_json_array(raw_text: str) -> list[object]:
    raw_text = str(raw_text or "").strip()
    if not raw_text:
        return []
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    start = raw_text.find("[")
    end = raw_text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        parsed = json.loads(raw_text[start : end + 1])
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _translate_evidence_rows_for_language(
    *,
    rows: list[dict[str, object]],
    language: str,
    model: str,
    host: str,
    temperature: float,
    timeout_seconds: int,
    max_rows: int | None = None,
) -> list[dict[str, object]]:
    language_normalized = str(language or "en").strip().lower()
    if language_normalized != "es" or not rows:
        return rows

    effective_rows = rows
    if max_rows is not None:
        safe_max = max(1, int(max_rows))
        effective_rows = rows[:safe_max]

    source_texts = [str(row.get("claim_text", "")).strip() for row in effective_rows]
    if not any(source_texts):
        return effective_rows

    numbered_lines = [f"{idx + 1}. {text}" for idx, text in enumerate(source_texts)]
    prompt = (
        "Translate the following clinical evidence node texts from English to Spanish.\n"
        "Return ONLY a valid JSON array of strings with exactly the same length and order.\n"
        "Do not add commentary, markdown, numbering, or extra keys.\n\n"
        "Texts:\n"
        + "\n".join(numbered_lines)
    )

    try:
        translated_raw = generate_with_ollama(
            prompt=prompt,
            model=model,
            host=host,
            temperature=0.0,
            timeout_seconds=timeout_seconds,
        )
    except Exception:
      return effective_rows

    translated_items = _extract_json_array(translated_raw)
    if len(translated_items) != len(effective_rows):
      return effective_rows

    translated_rows: list[dict[str, object]] = []
    for index, row in enumerate(effective_rows):
        updated = dict(row)
        translated_text = str(translated_items[index] if translated_items[index] is not None else "").strip()
        if translated_text:
            updated["claim_text"] = translated_text
        translated_rows.append(updated)
    return translated_rows


def render_index_page(
    *,
    db_path: str,
    ollama_host: str,
    model: str,
    context_limit: int,
    temperature: float,
    timeout_seconds: int,
    auth_enabled: bool,
) -> bytes:
    html = PAGE_TEMPLATE.substitute(
        db_path=db_path,
        ollama_host=ollama_host,
        model=model,
        context_limit=context_limit,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
      auth_enabled=("true" if auth_enabled else "false"),
      logo_html=render_inline_logo(height_px=28),
      favicon_tag=favicon_link_tag(),
    )
    return html.encode("utf-8")


def render_login_page(*, auth_enabled: bool) -> bytes:
  html = LOGIN_TEMPLATE.substitute(
    auth_enabled=("true" if auth_enabled else "false"),
    current_year=str(datetime.now(timezone.utc).year),
    logo_html=render_inline_logo(height_px=48),
    favicon_tag=favicon_link_tag(),
  )
  return html.encode("utf-8")


def render_privacy_policy_page() -> bytes:
  body = """
<p>MTVL AI is an open source research project. This page describes our local deployment defaults and expected data handling behavior.</p>
<h2 class="text-lg font-semibold text-slate-900 mt-6 mb-2">1. Data Collected</h2>
<p>The application can store scientific evidence rows, user account email for authentication, login sessions, and user activity logs used for auditability.</p>
<h2 class="text-lg font-semibold text-slate-900 mt-6 mb-2">2. Purpose</h2>
<p>Data is processed to support ALS and related motor neuron disease investigation, user authentication, and reproducible analysis workflows.</p>
<h2 class="text-lg font-semibold text-slate-900 mt-6 mb-2">3. Storage Model</h2>
<p>By default, data is stored locally in your configured SQLite database. Hosting operators are responsible for backups, retention, and access control.</p>
<h2 class="text-lg font-semibold text-slate-900 mt-6 mb-2">4. Third-Party Services</h2>
<p>When configured, external biomedical APIs and model endpoints may be queried to retrieve evidence and generate responses. Review your deployment settings before production use.</p>
<h2 class="text-lg font-semibold text-slate-900 mt-6 mb-2">5. Security</h2>
<p>Use HTTPS in production, secure cookie settings, and managed secrets for SMTP/API credentials. Restrict database access to trusted operators.</p>
<h2 class="text-lg font-semibold text-slate-900 mt-6 mb-2">6. Open Source Disclaimer</h2>
<p>MTVL AI is provided as open source software and can be self-hosted. Data governance obligations are determined by your organization and jurisdiction.</p>
<h2 class="text-lg font-semibold text-slate-900 mt-6 mb-2">7. Governance and Oversight</h2>
<p>Review the project mission and oversight model in the repository docs:</p>
<ul>
  <li><a href="/docs/MISSION.md" class="text-blue-900 hover:underline">Mission</a></li>
  <li><a href="/docs/ETHICS_AND_OVERSIGHT.md" class="text-blue-900 hover:underline">Ethics and Oversight</a></li>
  <li><a href="/docs/HUMAN_OVERSIGHT.md" class="text-blue-900 hover:underline">Human Oversight</a></li>
</ul>
"""
  html = LEGAL_TEMPLATE.substitute(
    page_title="Privacy Policy",
    page_body=body,
    current_year=str(datetime.now(timezone.utc).year),
    favicon_tag=favicon_link_tag(),
  )
  return html.encode("utf-8")


def render_terms_page() -> bytes:
  body = """
<p>These Terms of Service govern use of MTVL AI, an open source project for biomedical evidence analysis.</p>
<h2 class="text-lg font-semibold text-slate-900 mt-6 mb-2">1. Intended Use</h2>
<p>The software is intended for research support and investigation workflows. It does not provide medical advice.</p>
<h2 class="text-lg font-semibold text-slate-900 mt-6 mb-2">2. Operator Responsibilities</h2>
<p>Instance operators are responsible for deployment security, user access management, legal compliance, and data protection controls.</p>
<h2 class="text-lg font-semibold text-slate-900 mt-6 mb-2">3. Open Source License</h2>
<p>Use, modification, and redistribution are governed by the repository license. Verify the license terms in your local checkout before commercial usage.</p>
<h2 class="text-lg font-semibold text-slate-900 mt-6 mb-2">4. No Warranty</h2>
<p>The software is provided "as is" without warranties of any kind, to the maximum extent allowed by applicable law.</p>
<h2 class="text-lg font-semibold text-slate-900 mt-6 mb-2">5. Limitation of Liability</h2>
<p>Contributors and maintainers are not liable for direct or indirect damages arising from use, misuse, or inability to use the software.</p>
<h2 class="text-lg font-semibold text-slate-900 mt-6 mb-2">6. Governance and Oversight</h2>
<p>Ethical use expectations and human oversight requirements are documented in:</p>
<ul>
  <li><a href="/docs/MISSION.md" class="text-blue-900 hover:underline">Mission</a></li>
  <li><a href="/docs/ETHICS_AND_OVERSIGHT.md" class="text-blue-900 hover:underline">Ethics and Oversight</a></li>
  <li><a href="/docs/HUMAN_OVERSIGHT.md" class="text-blue-900 hover:underline">Human Oversight</a></li>
</ul>
"""
  html = LEGAL_TEMPLATE.substitute(
    page_title="Terms of Service",
    page_body=body,
    current_year=str(datetime.now(timezone.utc).year),
    favicon_tag=favicon_link_tag(),
  )
  return html.encode("utf-8")


def _repo_docs_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "docs"


GOVERNANCE_DOC_NAMES = (
    "MISSION.md",
    "ETHICS_AND_OVERSIGHT.md",
    "HUMAN_OVERSIGHT.md",
)


def _governance_doc_nav(current_name: str) -> str:
    links: list[str] = []
    for doc_name in GOVERNANCE_DOC_NAMES:
        label = doc_name.replace(".md", "").replace("_", " ").title()
        active_class = " is-active" if doc_name == current_name else ""
        links.append(
            f'<a href="/docs/{doc_name}" class="doc-nav-link{active_class}">{label}</a>'
        )
    return f'<nav class="doc-nav" aria-label="Governance documentation">{"".join(links)}</nav>'


def render_governance_doc_page(doc_name: str) -> bytes | None:
    safe_name = Path(doc_name).name
    if not safe_name.endswith(".md"):
        return None
    doc_path = _repo_docs_dir() / safe_name
    if not doc_path.is_file():
        return None
    markdown = doc_path.read_text(encoding="utf-8")
    page_title = extract_markdown_title(markdown) or safe_name.replace(".md", "").replace("_", " ")
    body = (
        _governance_doc_nav(safe_name)
        + render_markdown_to_html(markdown, skip_top_heading=True)
    )
    html = LEGAL_TEMPLATE.substitute(
        page_title=page_title,
        page_body=body,
        current_year=str(datetime.now(timezone.utc).year),
        favicon_tag=favicon_link_tag(),
    )
    return html.encode("utf-8")


def _write_brand_logo(handler: BaseHTTPRequestHandler) -> None:
    data = logo_bytes()
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", logo_mime_type())
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "public, max-age=86400")
    handler.end_headers()
    handler.wfile.write(data)


def _write_static_asset(handler: BaseHTTPRequestHandler, *, data: bytes, mime_type: str) -> None:
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", mime_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "public, max-age=86400")
    handler.end_headers()
    handler.wfile.write(data)


def _is_public_page(path: str) -> bool:
    return path in PUBLIC_PAGE_PATHS or path.startswith("/docs/")


def _is_app_page(path: str) -> bool:
    return path in APP_PAGE_PATHS


class ChatHandler(BaseHTTPRequestHandler):
    server_version = "ALSIntelChat/2.0"
    protocol_version = "HTTP/1.1"

    def _settings(self) -> dict[str, object]:
        return {
            "db_path": os.getenv("ALS_DB_PATH", DEFAULT_DB_PATH),
            "ollama_host": os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST),
            "model": os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
            "context_limit": int(os.getenv("ALS_CONTEXT_LIMIT", str(DEFAULT_CONTEXT_LIMIT))),
            "temperature": float(os.getenv("ALS_TEMPERATURE", str(DEFAULT_TEMPERATURE))),
            "timeout_seconds": int(os.getenv("ALS_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))),
        "auth_enabled": os.getenv("ALS_AUTH_ENABLED", "1").strip() not in {"0", "false", "False"},
        }

    def _auth_service(self) -> AuthService:
      return AuthService(build_auth_config())

    def _client_ip(self) -> str:
      forwarded = str(self.headers.get("X-Forwarded-For", "")).strip()
      if forwarded:
        return forwarded.split(",", 1)[0].strip()
      return str(self.client_address[0] if self.client_address else "")

    def _cookie_value(self, key: str) -> str:
      raw = str(self.headers.get("Cookie", ""))
      for item in raw.split(";"):
        part = item.strip()
        if not part or "=" not in part:
          continue
        k, v = part.split("=", 1)
        if k.strip() == key:
          return v.strip()
      return ""

    def _session_token(self, cookie_name: str) -> str:
      bearer = str(self.headers.get("Authorization", "")).strip()
      if bearer.lower().startswith("bearer "):
        token = bearer[7:].strip()
        if token:
          return token
      return self._cookie_value(cookie_name)

    def _csrf_secret(self) -> str:
      return str(os.getenv("ALS_CSRF_SECRET", "als-csrf-secret-local"))

    def _csrf_token_for_session(self, session_token: str) -> str:
      raw = f"{self._csrf_secret()}:{session_token}".encode("utf-8")
      return hashlib.sha256(raw).hexdigest()

    def _csrf_token_from_request(self) -> str:
      return str(self.headers.get("X-CSRF-Token", "")).strip()

    def _require_csrf(self, *, settings: dict[str, object], auth_service: AuthService, path: str) -> bool:
      if not bool(settings.get("auth_enabled", False)):
        return True
      session_token = self._session_token(auth_service.config.cookie_name)
      if not session_token:
        _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
        return False
      expected = self._csrf_token_for_session(session_token)
      provided = self._csrf_token_from_request()
      if not provided or not secrets.compare_digest(expected, provided):
        _json_response(self, HTTPStatus.FORBIDDEN, {"error": "CSRF token is required"})
        return False
      return True

    def _current_user(self, settings: dict[str, object]) -> dict[str, str] | None:
      if not bool(settings.get("auth_enabled", False)):
        return {"user_id": "anonymous", "email": "anonymous@local"}
      service = self._auth_service()
      token = self._session_token(service.config.cookie_name)
      if not token:
        return None
      store = self._store(str(settings["db_path"]))
      return service.resolve_session(store=store, session_token=token)

    def _require_auth(self, settings: dict[str, object]) -> dict[str, str] | None:
      user = self._current_user(settings)
      if user is None:
        _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
        return None
      return user

    def _record_activity(
      self,
      *,
      settings: dict[str, object],
      user_id: str,
      activity_type: str,
      endpoint: str,
      payload: dict[str, object] | None = None,
    ) -> None:
      if not bool(settings.get("auth_enabled", False)):
        return
      store = self._store(str(settings["db_path"]))
      store.log_user_activity(
        user_id=user_id,
        activity_type=activity_type,
        endpoint=endpoint,
        payload=payload,
      )

    def _format_auth_cookie(self, *, auth_service: AuthService, value: str, max_age: int) -> str:
      same_site = str(auth_service.config.cookie_same_site or "Lax").capitalize()
      if same_site not in {"Lax", "Strict", "None"}:
        same_site = "Lax"
      cookie_expires = datetime.now(timezone.utc) + timedelta(seconds=max_age)
      cookie_value = (
        f"{auth_service.config.cookie_name}={value}; "
        f"Path={auth_service.config.cookie_path}; "
        f"SameSite={same_site}; "
        f"Max-Age={max_age}; "
        f"Expires={cookie_expires.strftime('%a, %d %b %Y %H:%M:%S GMT')}"
      )
      if auth_service.config.cookie_http_only:
        cookie_value += "; HttpOnly"
      if auth_service.config.cookie_secure:
        cookie_value += "; Secure"
      if auth_service.config.cookie_domain:
        cookie_value += f"; Domain={auth_service.config.cookie_domain}"
      return cookie_value

    def _store(self, db_path: str) -> EvidenceStore:
        store = EvidenceStore(db_path)
        store.init_db()
        return store

    def _handle_worker_tick(self, *, provided_token: str, limit: int) -> None:
        expected_token = str(os.getenv("ALS_AUTOMATION_WORKER_TOKEN", "")).strip()
        if not expected_token or provided_token != expected_token:
            _json_response(self, HTTPStatus.FORBIDDEN, {"error": "invalid worker token"})
            return
        backoff_base_seconds = _parse_positive_int(
            os.getenv("ALS_RUN_RETRY_BACKOFF_SECONDS", "30"),
            30,
            max_value=3600,
        )
        now_iso = datetime.now(timezone.utc).isoformat()
        settings = self._settings()
        store = self._store(str(settings["db_path"]))
        due_runs = store.claim_due_queued_runs(now_iso=now_iso, limit=limit)
        executed_rows = _execute_due_queued_runs(
            store=store,
            due_runs=due_runs,
            backoff_base_seconds=backoff_base_seconds,
        )
        _json_response(
            self,
            HTTPStatus.OK,
            {
                "rows": executed_rows,
                "executed": len(executed_rows),
                "claimed": len(due_runs),
                "limit": limit,
                "now": now_iso,
            },
        )

    def _is_browser_page_request(self, path: str) -> bool:
        if path == "/healthz":
            return False
        if path.startswith("/api/"):
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query_params = parse_qs(parsed.query)

        if path == LOGO_URL_PATH:
            try:
                _write_brand_logo(self)
            except FileNotFoundError:
                self.send_error(HTTPStatus.NOT_FOUND, "Logo not found")
            return

        if path == LETTERMARK_LOGO_URL_PATH:
            try:
                _write_static_asset(
                    self,
                    data=lettermark_logo_bytes(),
                    mime_type=lettermark_logo_mime_type(),
                )
            except FileNotFoundError:
                self.send_error(HTTPStatus.NOT_FOUND, "Logo not found")
            return

        if path == LANDING_DASHBOARD_URL_PATH:
            try:
                _write_static_asset(
                    self,
                    data=landing_dashboard_bytes(),
                    mime_type=landing_dashboard_mime_type(),
                )
            except FileNotFoundError:
                self.send_error(HTTPStatus.NOT_FOUND, "Image not found")
            return

        settings = self._settings()
        auth_user: dict[str, str] | None = None
        if bool(settings.get("auth_enabled", False)) and self._is_browser_page_request(path):
            auth_user = self._current_user(settings)
            magic_token = str((query_params.get("magic_token") or [""])[0]).strip()
            if auth_user is None:
                if magic_token and path in {"/", "/index.html"}:
                    location = f"/login?magic_token={quote(magic_token, safe='')}"
                    self.send_response(HTTPStatus.FOUND)
                    self.send_header("Location", location)
                    self.end_headers()
                    return
                if not _is_public_page(path):
                    next_target = path
                    if parsed.query:
                        next_target = f"{path}?{parsed.query}"
                    location = f"/login?next={quote(next_target, safe='/?:=&')}"
                    self.send_response(HTTPStatus.FOUND)
                    self.send_header("Location", location)
                    self.end_headers()
                    return
            if auth_user is not None:
                if path == "/login":
                    next_query = str((query_params.get("next") or [APP_ROUTE])[0]).strip() or APP_ROUTE
                    if not next_query.startswith("/"):
                        next_query = APP_ROUTE
                    self.send_response(HTTPStatus.FOUND)
                    self.send_header("Location", next_query)
                    self.end_headers()
                    return
                if path in {"/", "/index.html"}:
                    self.send_response(HTTPStatus.FOUND)
                    self.send_header("Location", APP_ROUTE)
                    self.end_headers()
                    return
                if not _is_public_page(path) and not _is_app_page(path):
                    self.send_response(HTTPStatus.FOUND)
                    self.send_header("Location", APP_ROUTE)
                    self.end_headers()
                    return

        if path in {"/", "/index.html"}:
            body = render_landing_page(auth_enabled=bool(settings["auth_enabled"]))
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path in APP_PAGE_PATHS:
            body = render_index_page(
                db_path=str(settings["db_path"]),
                ollama_host=str(settings["ollama_host"]),
                model=str(settings["model"]),
                context_limit=int(settings["context_limit"]),
                temperature=float(settings["temperature"]),
                timeout_seconds=int(settings["timeout_seconds"]),
                auth_enabled=bool(settings["auth_enabled"]),
            )
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/login":
            if not bool(settings.get("auth_enabled", False)):
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", APP_ROUTE)
                self.end_headers()
                return
            body = render_login_page(auth_enabled=bool(settings["auth_enabled"]))
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/privacy":
          body = render_privacy_policy_page()
          self.send_response(HTTPStatus.OK)
          self.send_header("Content-Type", "text/html; charset=utf-8")
          self.send_header("Content-Length", str(len(body)))
          self.end_headers()
          self.wfile.write(body)
          return

        if path == "/terms":
          body = render_terms_page()
          self.send_response(HTTPStatus.OK)
          self.send_header("Content-Type", "text/html; charset=utf-8")
          self.send_header("Content-Length", str(len(body)))
          self.end_headers()
          self.wfile.write(body)
          return

        if path.startswith("/docs/"):
            doc_name = unquote(path[len("/docs/"):]).lstrip("/")
            body = render_governance_doc_page(doc_name)
            if body is None:
                self.send_response(HTTPStatus.NOT_FOUND)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"Governance document not found")
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/healthz":
            _json_response(self, HTTPStatus.OK, {"status": "ok"})
            return

        if path == "/api/status":
            try:
                settings = self._settings()
                store = self._store(str(settings["db_path"]))
                summary = store.summary()
                flags = store.review_flags()
                source_breakdown = store.source_article_breakdown()
                latest_sync_at = store.latest_sync_timestamp()
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "records_total": int(summary.get("records", 0)),
                        "avg_reliability": float(summary.get("avg_reliability", 0.0)),
                        "supports_count": int(summary.get("supports", 0)),
                        "contradicts_count": int(summary.get("contradicts", 0)),
                        "review_flags_count": len(flags),
                        "model": str(settings.get("model", "")),
                        "db_synced": True,
                        "source_breakdown": source_breakdown,
                        "latest_sync_at": latest_sync_at,
                    },
                )
            except Exception as exc:  # pragma: no cover
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if path == "/api/auth/status":
          try:
            settings = self._settings()
            auth_service = self._auth_service()
            token = self._session_token(auth_service.config.cookie_name)
            store = self._store(str(settings["db_path"]))
            user, rotated_token = auth_service.resolve_session_with_rotation(
              store=store,
              session_token=token,
              user_agent=str(self.headers.get("User-Agent", "")),
              ip_address=self._client_ip(),
            ) if token else (None, None)
            csrf_token: str | None = None
            if user is not None:
              session_token = rotated_token or token
              if session_token:
                csrf_token = self._csrf_token_for_session(session_token)
            extra_headers = None
            if rotated_token:
              extra_headers = {
                "Set-Cookie": self._format_auth_cookie(
                  auth_service=auth_service,
                  value=rotated_token,
                  max_age=auth_service.config.session_ttl_seconds,
                )
              }
            _json_response(
              self,
              HTTPStatus.OK,
              {
                "auth_enabled": bool(settings.get("auth_enabled", False)),
                "authenticated": user is not None,
                "user": user,
                "csrf_token": csrf_token,
              },
              extra_headers=extra_headers,
            )
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/auth/login-metadata":
            try:
                settings = self._settings()
                store = self._store(str(settings["db_path"]))
                summary = store.summary()
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "db_path": str(settings["db_path"]),
                        "records_total": int(summary.get("records", 0)),
                        "source_breakdown": store.source_article_breakdown(),
                        "latest_sync_at": store.latest_sync_timestamp(),
                        "avg_reliability": float(summary.get("avg_reliability", 0.0)),
                    },
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if path == "/api/auth/audit":
            try:
                settings = self._settings()
                user = self._require_auth(settings)
                if user is None:
                    return
                limit = _parse_positive_int((query_params.get("limit") or ["100"])[0], 100, max_value=500)
                activity_type = str((query_params.get("activity_type") or [""])[0]).strip()
                store = self._store(str(settings["db_path"]))
                rows = store.list_user_activity(
                    user_id=str(user["user_id"]),
                    limit=limit,
                    activity_type=activity_type or None,
                )
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "rows": rows,
                        "total": len(rows),
                        "limit": limit,
                        "activity_type": activity_type or None,
                    },
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if path == "/api/investigation/runs":
            try:
                settings = self._settings()
                user = self._require_auth(settings)
                if user is None:
                    return
                limit = _parse_positive_int((query_params.get("limit") or ["20"])[0], 20, max_value=200)
                store = self._store(str(settings["db_path"]))
                rows = store.list_investigation_runs(user_id=str(user["user_id"]), limit=limit)
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "rows": rows,
                        "total": len(rows),
                        "limit": limit,
                    },
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if path == "/api/investigation/runs/review-queue":
          try:
            settings = self._settings()
            user = self._require_auth(settings)
            if user is None:
              return
            limit = _parse_positive_int((query_params.get("limit") or ["50"])[0], 50, max_value=200)
            offset = _parse_non_negative_int((query_params.get("offset") or ["0"])[0], 0, max_value=10000)
            status_filter = str((query_params.get("status") or [""])[0]).strip().lower()
            risk_filter = str((query_params.get("risk") or [""])[0]).strip().lower()
            sort_value = str((query_params.get("sort") or ["created_desc"])[0]).strip().lower()
            store = self._store(str(settings["db_path"]))
            rows, total, has_more = store.list_investigation_review_queue(
              user_id=str(user["user_id"]),
              limit=limit,
              offset=offset,
              status=status_filter,
              risk_level=risk_filter,
              sort=sort_value,
            )
            _json_response(
              self,
              HTTPStatus.OK,
              {
                "rows": rows,
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "status": status_filter or "any",
                "risk": risk_filter or "any",
                "sort": sort_value or "created_desc",
              },
            )
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/investigation/runs/review-queue/summary":
          try:
            settings = self._settings()
            user = self._require_auth(settings)
            if user is None:
              return
            store = self._store(str(settings["db_path"]))
            payload = store.investigation_review_queue_summary(user_id=str(user["user_id"]))
            _json_response(
              self,
              HTTPStatus.OK,
              payload,
            )
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/investigation/templates":
          try:
            settings = self._settings()
            user = self._require_auth(settings)
            if user is None:
              return
            limit = _parse_positive_int((query_params.get("limit") or ["50"])[0], 50, max_value=200)
            store = self._store(str(settings["db_path"]))
            rows = store.list_investigation_templates(user_id=str(user["user_id"]), limit=limit)
            _json_response(
              self,
              HTTPStatus.OK,
              {
                "rows": rows,
                "total": len(rows),
                "limit": limit,
              },
            )
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/automation/experiments":
          try:
            settings = self._settings()
            user = self._require_auth(settings)
            if user is None:
              return
            limit = _parse_positive_int((query_params.get("limit") or ["20"])[0], 20, max_value=200)
            store = self._store(str(settings["db_path"]))
            rows = store.list_automation_experiments(user_id=str(user["user_id"]), limit=limit)
            _json_response(
              self,
              HTTPStatus.OK,
              {
                "rows": rows,
                "total": len(rows),
                "limit": limit,
              },
            )
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/automation/exports":
          try:
            settings = self._settings()
            user = self._require_auth(settings)
            if user is None:
              return
            limit = _parse_positive_int((query_params.get("limit") or ["20"])[0], 20, max_value=200)
            store = self._store(str(settings["db_path"]))
            rows = store.list_automation_exports(user_id=str(user["user_id"]), limit=limit)
            _json_response(
              self,
              HTTPStatus.OK,
              {
                "rows": rows,
                "total": len(rows),
                "limit": limit,
              },
            )
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/automation/dashboard":
          try:
            settings = self._settings()
            user = self._require_auth(settings)
            if user is None:
              return
            window_days = _parse_positive_int((query_params.get("days") or ["30"])[0], 30, max_value=365)
            store = self._store(str(settings["db_path"]))
            user_id = str(user["user_id"])
            metrics = store.investigation_dashboard_metrics(user_id=user_id, days=window_days)
            review_queue_summary = store.investigation_review_queue_summary(user_id=user_id)
            metrics["review_queue"] = review_queue_summary
            _json_response(self, HTTPStatus.OK, metrics)
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/failure-atlas":
          try:
            from als_intel.agents.historical import build_failure_atlas

            settings = self._settings()
            user = self._require_auth(settings)
            if user is None:
              return
            store = self._store(str(settings["db_path"]))
            atlas = build_failure_atlas(store.all_evidence_with_provenance())
            _json_response(self, HTTPStatus.OK, atlas)
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/automation/freshness/alarms":
          try:
            settings = self._settings()
            user = self._require_auth(settings)
            if user is None:
              return
            stale_after_hours = _parse_positive_int(
              (query_params.get("stale_after_hours") or [os.getenv("ALS_FRESHNESS_STALE_HOURS", "24")])[0],
              int(os.getenv("ALS_FRESHNESS_STALE_HOURS", "24") or "24"),
              max_value=24 * 365,
            )
            failure_threshold = _parse_non_negative_int(
              (query_params.get("failure_threshold") or [os.getenv("ALS_FRESHNESS_FAILURE_THRESHOLD", "2")])[0],
              int(os.getenv("ALS_FRESHNESS_FAILURE_THRESHOLD", "2") or "2"),
              max_value=100,
            )
            store = self._store(str(settings["db_path"]))
            rows = store.freshness_alarms(
              stale_after_hours=stale_after_hours,
              failure_threshold=failure_threshold,
            )
            _json_response(
              self,
              HTTPStatus.OK,
              {
                "rows": rows,
                "total": len(rows),
                "stale_after_hours": stale_after_hours,
                "failure_threshold": failure_threshold,
              },
            )
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/investigation/runs/worker/tick":
          try:
            provided_token = str((query_params.get("token") or [""])[0]).strip()
            auth_header = str(self.headers.get("Authorization", "")).strip()
            if auth_header.lower().startswith("bearer "):
              provided_token = auth_header[7:].strip() or provided_token
            limit = _parse_positive_int((query_params.get("limit") or ["20"])[0], 20, max_value=200)
            self._handle_worker_tick(provided_token=provided_token, limit=limit)
          except Exception as exc:
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
          return

        if path == "/api/investigation/runs/queued/execute":
            try:
                settings = self._settings()
                user = self._require_auth(settings)
                if user is None:
                    return
                limit = _parse_positive_int((query_params.get("limit") or ["5"])[0], 5, max_value=50)
                backoff_base_seconds = _parse_positive_int(
                    os.getenv("ALS_RUN_RETRY_BACKOFF_SECONDS", "30"),
                    30,
                    max_value=3600,
                )
                now_iso = datetime.now(timezone.utc).isoformat()
                store = self._store(str(settings["db_path"]))
                due_runs = [
                    row
                    for row in store.claim_due_queued_runs(now_iso=now_iso, limit=limit)
                    if str(row.get("user_id", "")) == str(user["user_id"])
                ]
                executed_rows = _execute_due_queued_runs(
                  store=store,
                  due_runs=due_runs,
                  backoff_base_seconds=backoff_base_seconds,
                )

                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "rows": executed_rows,
                        "executed": len(executed_rows),
                        "limit": limit,
                        "now": now_iso,
                    },
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if path.startswith("/api/investigation/runs/"):
            run_id = unquote(path.removeprefix("/api/investigation/runs/")).strip()
            if not run_id:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "run_id is required"})
                return
            try:
                settings = self._settings()
                user = self._require_auth(settings)
                if user is None:
                    return
                store = self._store(str(settings["db_path"]))
                row = store.get_investigation_run(user_id=str(user["user_id"]), run_id=run_id)
                _json_response(self, HTTPStatus.OK, row)
            except ValueError as exc:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if path == "/api/telemetry/recent":
            try:
                limit = _parse_positive_int((query_params.get("limit") or ["25"])[0], 25, max_value=TELEMETRY_MAX_RECENT)
                traces = _recent_query_telemetry(limit)
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "traces": traces,
                        "total": len(traces),
                        "limit": limit,
                    },
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if path == "/api/session/list":
            try:
                settings = self._settings()
                user = self._require_auth(settings)
                if user is None:
                    return
                limit = _parse_positive_int((query_params.get("limit") or ["50"])[0], 50, max_value=200)
                offset = _parse_non_negative_int((query_params.get("offset") or ["0"])[0], 0)
                store = self._store(str(settings["db_path"]))
                sessions = store.list_investigator_sessions(
                    user_id=str(user["user_id"]),
                    limit=min(5000, offset + limit),
                )
                paged_sessions = sessions[offset : offset + limit]
                self._record_activity(
                    settings=settings,
                    user_id=str(user["user_id"]),
                    activity_type="session_list",
                    endpoint=path,
                    payload={"limit": limit, "offset": offset},
                )
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "sessions": paged_sessions,
                        "total": len(sessions),
                        "limit": limit,
                        "offset": offset,
                        "has_more": offset + limit < len(sessions),
                    },
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if path.startswith("/api/session/"):
            session_id = unquote(path.removeprefix("/api/session/")).strip()
            if not session_id:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "session_id is required"})
                return
            try:
                settings = self._settings()
                user = self._require_auth(settings)
                if user is None:
                    return
                store = self._store(str(settings["db_path"]))
                payload = store.get_investigator_session(user_id=str(user["user_id"]), session_id=session_id)
                self._record_activity(
                    settings=settings,
                    user_id=str(user["user_id"]),
                    activity_type="session_get",
                    endpoint=path,
                    payload={"session_id": session_id},
                )
                _json_response(self, HTTPStatus.OK, payload)
            except ValueError as exc:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": str(exc)})
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if path.startswith("/api/evidence/"):
            claim_id = unquote(path.removeprefix("/api/evidence/")).strip()
            if not claim_id:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "claim_id is required"})
                return
            try:
                settings = self._settings()
                store = self._store(str(settings["db_path"]))
                _json_response(self, HTTPStatus.OK, store.claim_lineage(claim_id))
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path not in {
            "/api/auth/request-link",
            "/api/auth/verify-link",
            "/api/auth/logout",
            "/api/chat",
          "/api/chat/stream",
            "/api/evidence/filter",
            "/api/evidence/search",
            "/api/database/nodes",
            "/api/database/node/metadata",
            "/api/hypothesis/queue",
            "/api/review/flags",
            "/api/review/decision",
            "/api/review/decisions",
            "/api/evidence/compare",
            "/api/session/save",
            "/api/export/summary",
            "/api/synthesis",
            "/api/investigation/runs/start",
            "/api/investigation/runs/replay",
            "/api/investigation/runs/queue",
            "/api/investigation/runs/queued/execute",
            "/api/investigation/runs/approve",
            "/api/investigation/runs/rollback",
            "/api/investigation/templates/save",
            "/api/investigation/templates/run",
            "/api/automation/experiments/run",
            "/api/export/automated",
            "/api/investigation/runs/worker/tick",
        }:
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        try:
            payload = _read_json_body(self)
            settings = self._settings()
            auth_service = self._auth_service()

            if path == "/api/investigation/runs/worker/tick":
                auth_header = str(self.headers.get("Authorization", "")).strip()
                provided_token = ""
                if auth_header.lower().startswith("bearer "):
                    provided_token = auth_header[7:].strip()
                if not provided_token:
                    provided_token = str(payload.get("token", "")).strip()
                limit = _parse_positive_int(payload.get("limit", 20), 20, max_value=200)
                self._handle_worker_tick(provided_token=provided_token, limit=limit)
                return

            if path == "/api/auth/request-link":
                email = str(payload.get("email", "")).strip()
                store = self._store(str(settings["db_path"]))
                normalized_email = AuthService.normalize_email(email)
                existing_user = store.get_user_by_email(normalized_email)
                if existing_user is None and AuthService.is_valid_email(normalized_email):
                    deterministic_user_id = f"usr_{AuthService.token_hash(normalized_email)[:16]}"
                    existing_user = store.get_or_create_user(user_id=deterministic_user_id, email=normalized_email)
                try:
                    _, magic_link = auth_service.create_magic_link(
                        store=store,
                        email=email,
                        requested_ip=self._client_ip(),
                    )
                except ValueError as exc:
                    message = str(exc)
                    if "Too many magic-link requests" in message:
                        if existing_user is not None:
                            store.log_user_activity(
                                user_id=str(existing_user["user_id"]),
                                activity_type="auth_magic_link_rate_limited",
                                endpoint=path,
                                payload={},
                            )
                        _json_response(self, HTTPStatus.TOO_MANY_REQUESTS, {"error": message})
                        return
                    raise
                delivery = auth_service.send_magic_link(email=normalized_email, magic_link=magic_link)
                if existing_user is not None:
                    store.log_user_activity(
                        user_id=str(existing_user["user_id"]),
                        activity_type="auth_magic_link_requested",
                        endpoint=path,
                        payload={"delivery_mode": delivery.get("mode", "unknown")},
                    )
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "email": normalized_email,
                        "delivery_mode": delivery.get("mode", "unknown"),
                        "magic_link": delivery.get("magic_link") if delivery.get("mode") == "dev" else None,
                    },
                )
                return

            if path == "/api/auth/verify-link":
                token = str(payload.get("token", "")).strip()
                if not token:
                    raise ValueError("token is required")
                store = self._store(str(settings["db_path"]))
                previous_session = self._session_token(auth_service.config.cookie_name)
                if previous_session:
                  auth_service.revoke_session(store=store, session_token=previous_session)
                user, session_token = auth_service.consume_magic_token(
                    store=store,
                    token=token,
                    user_agent=str(self.headers.get("User-Agent", "")),
                    ip_address=self._client_ip(),
                )
                cookie_value = self._format_auth_cookie(
                    auth_service=auth_service,
                    value=session_token,
                    max_age=auth_service.config.session_ttl_seconds,
                )
                store.log_user_activity(
                    user_id=str(user["user_id"]),
                    activity_type="auth_login",
                    endpoint=path,
                    payload={"email": str(user["email"])},
                )
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "authenticated": True,
                        "user": user,
                        "csrf_token": self._csrf_token_for_session(session_token),
                    },
                    extra_headers={"Set-Cookie": cookie_value},
                )
                return

            if path == "/api/auth/logout":
                if bool(settings.get("auth_enabled", False)) and not self._require_csrf(
                    settings=settings,
                    auth_service=auth_service,
                    path=path,
                ):
                    return
                token = self._session_token(auth_service.config.cookie_name)
                store = self._store(str(settings["db_path"]))
                user_for_logout = self._current_user(settings)
                if token:
                    auth_service.revoke_session(store=store, session_token=token)
                if user_for_logout is not None:
                    store.log_user_activity(
                        user_id=str(user_for_logout["user_id"]),
                        activity_type="auth_logout",
                        endpoint=path,
                        payload={},
                    )
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {"ok": True},
                    extra_headers={
                        "Set-Cookie": self._format_auth_cookie(
                            auth_service=auth_service,
                            value="",
                            max_age=0,
                        )
                    },
                )
                return

            public_paths: set[str] = {
                "/api/auth/request-link",
                "/api/auth/verify-link",
            }
            current_user: dict[str, str] | None = None
            if not bool(settings.get("auth_enabled", False)):
              current_user = {"user_id": "anonymous", "email": "anonymous@local"}
            elif path not in public_paths:
              current_user = self._require_auth(settings)
              if current_user is None:
                return
              if not self._require_csrf(
                settings=settings,
                auth_service=auth_service,
                path=path,
              ):
                return

            if path == "/api/chat/stream":
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-transform")
                self.send_header("Connection", "close")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()

                trace_id = _new_trace_id()
                trace_started_perf = time.perf_counter()
                trace: dict[str, object] = {
                    "trace_id": trace_id,
                    "mode": "stream",
                    "path": path,
                    "started_at": int(time.time()),
                    "status": "ok",
                    "phase_seconds": {},
                }
                if current_user is not None:
                    trace["user_id"] = str(current_user.get("user_id", ""))

                try:
                    phase_loading_started = time.perf_counter()
                    _stream_json_event(self, {"type": "status", "phase": "loading_evidence", "message": "Loading and filtering evidence..."})

                    settings = self._settings()
                    db_path = str(payload.get("db_path") or settings["db_path"])
                    store = self._store(db_path)

                    filters = payload.get("filters", {})
                    if not isinstance(filters, dict):
                        filters = {}
                    filtered_rows = _attach_source_urls_to_rows(
                      store.filter_evidence(
                        filters=filters,
                        limit=_resolve_chat_evidence_limit(payload),
                      )
                    )

                    raw_messages = payload.get("messages", [])
                    if not isinstance(raw_messages, list):
                        raise ValueError("messages must be a list")
                    messages = [message for message in raw_messages if isinstance(message, dict)][-40:]

                    host = str(payload.get("host") or settings["ollama_host"])
                    model = str(payload.get("model") or settings["model"])
                    context_limit = _parse_positive_int(payload.get("context_limit") or settings["context_limit"], int(settings["context_limit"]), max_value=200)
                    temperature = float(payload.get("temperature") or settings["temperature"])
                    timeout_seconds = int(payload.get("timeout_seconds") or settings["timeout_seconds"])
                    language = str(payload.get("language") or "en").strip().lower()
                    if language not in {"en", "es"}:
                        language = "en"

                    trace["model"] = model
                    trace["language"] = language
                    trace["phase_seconds"]["loading_evidence"] = round(time.perf_counter() - phase_loading_started, 4)

                    _stream_json_event(self, {"type": "status", "phase": "building_prompt", "message": "Building grounded prompt..."})
                    phase_prompt_started = time.perf_counter()
                    prompt = _build_chat_prompt(messages, filtered_rows, context_limit, language)
                    trace["phase_seconds"]["building_prompt"] = round(time.perf_counter() - phase_prompt_started, 4)
                    _stream_json_event(self, {"type": "status", "phase": "generating", "message": "Generating answer..."})

                    phase_generation_started = time.perf_counter()
                    streamed_chunks: list[str] = []
                    for chunk in generate_with_ollama_stream(
                        prompt=prompt,
                        model=model,
                        host=host,
                        temperature=temperature,
                        timeout_seconds=timeout_seconds,
                    ):
                        streamed_chunks.append(chunk)
                        _stream_json_event(self, {"type": "chunk", "delta": chunk})

                    answer = "".join(streamed_chunks).strip()
                    if not answer:
                        raise LocalLLMError("Local LLM response was empty.")

                    generated_seconds = time.perf_counter() - phase_generation_started
                    trace["phase_seconds"]["generating"] = round(generated_seconds, 4)

                    _stream_json_event(self, {"type": "status", "phase": "post_processing", "message": "Linking citations and synthesis metadata..."})
                    phase_post_started = time.perf_counter()
                    contradictions = _contradiction_pairs_from_rows(filtered_rows, limit=300)
                    synthesis = _build_synthesis(answer=answer, evidence_rows=filtered_rows, contradiction_rows=contradictions)
                    synthesis, guardrail_flags = _apply_response_guardrails(
                      answer=answer,
                      synthesis=synthesis,
                      evidence_rows=filtered_rows,
                      contradiction_rows=contradictions,
                      language=language,
                    )
                    mentioned_claim_ids = synthesis.get("mentioned_claim_ids") if isinstance(synthesis.get("mentioned_claim_ids"), list) else []
                    mentioned_claim_id_set = {str(x) for x in mentioned_claim_ids if str(x).strip()}
                    cited_evidence_rows = [
                        row for row in filtered_rows if str(row.get("claim_id", "")).strip() in mentioned_claim_id_set
                    ]
                    cited_evidence_rows = _rank_cited_evidence_rows(cited_evidence_rows)
                    cited_evidence_rows = cited_evidence_rows[:MAX_CITED_EVIDENCE_ROWS]
                    if _should_translate_cited_rows(payload=payload, language=language):
                      cited_evidence_rows = _translate_evidence_rows_for_language(
                        rows=cited_evidence_rows,
                        language=language,
                        model=model,
                        host=host,
                        temperature=temperature,
                        timeout_seconds=min(timeout_seconds, 20),
                        max_rows=20,
                      )
                    trace["phase_seconds"]["post_processing"] = round(time.perf_counter() - phase_post_started, 4)
                    trace["evidence_count"] = len(filtered_rows)
                    trace["cited_evidence_count"] = len(cited_evidence_rows)
                    trace["guardrail_flags"] = guardrail_flags
                    trace["verification_flags"] = (
                        synthesis.get("verification_flags")
                        if isinstance(synthesis.get("verification_flags"), list)
                        else []
                    )
                    trace["total_seconds"] = round(sum(float(v) for v in trace["phase_seconds"].values()), 4)
                    _append_query_telemetry(trace)
                    if current_user is not None:
                        self._record_activity(
                            settings=settings,
                            user_id=str(current_user["user_id"]),
                            activity_type="chat_stream",
                            endpoint=path,
                            payload={"evidence_count": len(filtered_rows), "trace_id": str(trace.get("trace_id", ""))},
                        )

                    _stream_json_event(
                        self,
                        {
                            "type": "final",
                            "answer": answer,
                            "evidence_count": len(filtered_rows),
                            "model": model,
                            "host": host,
                            "generated_seconds": round(generated_seconds, 3),
                            "synthesis": synthesis,
                            "evidence_rows": cited_evidence_rows,
                            "response_mode": "stream",
                            "guardrail_flags": guardrail_flags,
                            "telemetry": trace,
                        },
                    )
                except Exception as exc:
                    trace["status"] = "error"
                    trace["error"] = str(exc)
                    trace["total_seconds"] = round(time.perf_counter() - trace_started_perf, 4)
                    _append_query_telemetry(trace)
                    _stream_json_event(self, {"type": "error", "error": str(exc)})
                self.close_connection = True
                return

            if path == "/api/session/save":
                if current_user is None:
                    _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                    return
                session_id = str(payload.get("session_id", "")).strip()
                if not session_id:
                    raise ValueError("session_id is required")

                title = str(payload.get("title", "")).strip()
                question = str(payload.get("question", "")).strip()
                messages = payload.get("messages", [])
                report = payload.get("report", {})
                filters = payload.get("filters", {})
                evidence_claim_ids = payload.get("evidence_claim_ids", [])

                if not isinstance(messages, list):
                    raise ValueError("messages must be a list")
                if not isinstance(report, dict):
                    raise ValueError("report must be an object")
                if not isinstance(filters, dict):
                    raise ValueError("filters must be an object")
                if not isinstance(evidence_claim_ids, list):
                    raise ValueError("evidence_claim_ids must be a list")

                store = self._store(str(settings["db_path"]))
                saved = store.save_investigator_session(
                    user_id=str(current_user["user_id"]),
                    session_id=session_id,
                    title=title,
                    question=question,
                    messages=[m for m in messages if isinstance(m, dict)],
                    report=report,
                    filters=filters,
                    evidence_claim_ids=[str(cid) for cid in evidence_claim_ids if str(cid).strip()],
                )
                self._record_activity(
                    settings=settings,
                    user_id=str(current_user["user_id"]),
                    activity_type="session_save",
                    endpoint=path,
                    payload={"session_id": session_id, "message_count": len(messages)},
                )
                _json_response(self, HTTPStatus.OK, saved)
                return

            if path == "/api/evidence/compare":
                claim_a = str(payload.get("claim_a", "")).strip()
                claim_b = str(payload.get("claim_b", "")).strip()
                if not claim_a or not claim_b:
                    raise ValueError("claim_a and claim_b are required")
                settings = self._settings()
                store = self._store(str(settings["db_path"]))
                left = store.claim_lineage(claim_a)
                right = store.claim_lineage(claim_b)

                left_support = {
                    str(row.get("claim_id", ""))
                    for row in left.get("lineage", {}).get("supporting_citations", [])
                }
                right_support = {
                    str(row.get("claim_id", ""))
                    for row in right.get("lineage", {}).get("supporting_citations", [])
                }
                left_contra = {
                    str(row.get("claim_id", ""))
                    for row in left.get("lineage", {}).get("contradicting_citations", [])
                }
                right_contra = {
                    str(row.get("claim_id", ""))
                    for row in right.get("lineage", {}).get("contradicting_citations", [])
                }

                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "claim_a": left.get("claim", {}),
                        "claim_b": right.get("claim", {}),
                        "shared_supporting_count": len(left_support & right_support),
                        "shared_contradicting_count": len(left_contra & right_contra),
                    "follow_up_suggestion": (
                      "Run a stratified follow-up experiment focused on endpoint differences across cohorts and study design."
                    ),
                    },
                )
                return

            if path == "/api/export/summary":
                report = payload.get("report", {})
                if not isinstance(report, dict):
                    raise ValueError("report must be an object")
                markdown = _build_report_markdown(report)
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "json_filename": "synthesis_report.json",
                        "json_content": json.dumps(report, indent=2),
                        "markdown_filename": "synthesis_report.md",
                        "markdown_content": markdown,
                    },
                )
                return

            if path == "/api/database/nodes":
                settings = self._settings()
                store = self._store(str(settings["db_path"]))
                rows = _attach_source_urls_to_rows(store.all_evidence())
                rows.sort(
                    key=lambda row: (
                        -int(row.get("year", 0) or 0),
                        -float(row.get("reliability_score", 0.0) or 0.0),
                    )
                )
                query = str(payload.get("query", ""))
                searched_rows = _search_evidence_rows(rows, query)
                limit = _parse_positive_int(payload.get("limit", 25), 25, max_value=200)
                offset = _parse_non_negative_int(payload.get("offset", 0), 0)
                page_rows, total, has_more = _paginate_rows(searched_rows, limit=limit, offset=offset)
                enriched_rows: list[dict[str, object]] = []
                for row in page_rows:
                    row_claim_id = str(row.get("claim_id", "")).strip()
                    source_metadata = store.get_evidence_source_metadata(row_claim_id) if row_claim_id else None
                    row_with_meta: dict[str, object] = dict(row)
                    if source_metadata is not None:
                        metadata_payload = source_metadata.get("metadata", {})
                        if not isinstance(metadata_payload, dict):
                            metadata_payload = {}
                        row_with_meta["source_metadata"] = {
                            "journal": str(source_metadata.get("journal", "") or ""),
                            "pubdate": str(source_metadata.get("pubdate", "") or ""),
                            "authors_count": len(source_metadata.get("authors", [])),
                            "mesh_terms_count": len(source_metadata.get("mesh_terms", [])),
                            "has_abstract": bool(str(source_metadata.get("abstract_text", "") or "").strip()),
                            "enriched_at": str(source_metadata.get("enriched_at", "") or ""),
                            "api_endpoint": str(metadata_payload.get("api_endpoint", "") or ""),
                            "query_used": str(metadata_payload.get("query_used", "") or ""),
                            "source_version": str(metadata_payload.get("source_version", "") or ""),
                            "source_license": str(metadata_payload.get("source_license", "") or ""),
                        }
                    enriched_rows.append(row_with_meta)
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "rows": enriched_rows,
                        "total": total,
                        "limit": limit,
                        "offset": offset,
                        "has_more": has_more,
                    },
                )
                return

            if path == "/api/database/node/metadata":
                claim_id = str(payload.get("claim_id", "")).strip()
                if not claim_id:
                    raise ValueError("claim_id is required")
                settings = self._settings()
                store = self._store(str(settings["db_path"]))
                metadata = store.get_evidence_source_metadata(claim_id)
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "claim_id": claim_id,
                        "found": metadata is not None,
                        "metadata": metadata,
                    },
                )
                return

            if path == "/api/review/flags":
                settings = self._settings()
                store = self._store(str(settings["db_path"]))
                delta_threshold = float(payload.get("delta_threshold", 0.15) or 0.15)
                contradiction_density_threshold = float(payload.get("contradiction_density_threshold", 0.34) or 0.34)
                flags = store.review_flags(
                    delta_threshold=delta_threshold,
                    contradiction_density_threshold=contradiction_density_threshold,
                )
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "flags": flags,
                        "total": len(flags),
                    },
                )
                return

            if path == "/api/review/decision":
                claim_id = str(payload.get("claim_id", "")).strip()
                decision = str(payload.get("decision", "")).strip()
                reviewer = str(payload.get("reviewer", "")).strip()
                notes = str(payload.get("notes", "")).strip()
                if not claim_id:
                    raise ValueError("claim_id is required")
                if not decision:
                    raise ValueError("decision is required")
                if not reviewer:
                    raise ValueError("reviewer is required")

                settings = self._settings()
                store = self._store(str(settings["db_path"]))
                store.record_review_decision(
                    claim_id=claim_id,
                    decision=decision,
                    reviewer=reviewer,
                    notes=notes,
                )
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "claim_id": claim_id,
                        "decision": decision,
                        "reviewer": reviewer,
                    },
                )
                return

            if path == "/api/review/decisions":
                claim_id = str(payload.get("claim_id", "")).strip() or None
                limit = _parse_positive_int(payload.get("limit", 20), 20, max_value=200)
                settings = self._settings()
                store = self._store(str(settings["db_path"]))
                rows = store.list_review_decisions(claim_id=claim_id, limit=limit)
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "rows": rows,
                        "total": len(rows),
                        "limit": limit,
                    },
                )
                return

            if path == "/api/hypothesis/queue":
                from als_intel.hypothesis import build_hypothesis_queue

                settings = self._settings()
                store = self._store(str(settings["db_path"]))
                evidence_rows = store.all_evidence()
                contradiction_rows = store.contradiction_pairs()

                limit = _parse_positive_int(payload.get("limit", 8), 8, max_value=50)
                require_review_signoff = bool(payload.get("require_review_signoff", False))
                enforce_causal_gate = bool(payload.get("enforce_causal_gate", False))
                overrides_raw = payload.get("causal_gate_override_entities", [])
                if not isinstance(overrides_raw, list):
                    overrides_raw = []
                overrides = {str(x).strip() for x in overrides_raw if str(x).strip()}

                approved_claim_ids = store.approved_claim_ids() if require_review_signoff else set()

                queue = build_hypothesis_queue(
                    evidence_rows=evidence_rows,
                    contradiction_rows=contradiction_rows,
                    limit=limit,
                    require_review_signoff=require_review_signoff,
                    approved_claim_ids=approved_claim_ids,
                    enforce_causal_gate=enforce_causal_gate,
                    causal_promotion_overrides=overrides,
                )
                baseline_queue = build_hypothesis_queue(
                    evidence_rows=evidence_rows,
                    contradiction_rows=contradiction_rows,
                    limit=limit,
                    require_review_signoff=False,
                    approved_claim_ids=set(),
                    enforce_causal_gate=False,
                    causal_promotion_overrides=set(),
                )
                baseline_entities = {str(row.get("entity", "")).strip() for row in baseline_queue if str(row.get("entity", "")).strip()}
                queue_entities = {str(row.get("entity", "")).strip() for row in queue if str(row.get("entity", "")).strip()}
                removed_entities = sorted(baseline_entities - queue_entities)

                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "queue": queue,
                        "baseline_total": len(baseline_queue),
                        "total": len(queue),
                        "removed_entities": removed_entities,
                        "require_review_signoff": require_review_signoff,
                        "enforce_causal_gate": enforce_causal_gate,
                    },
                )
                return

            if path == "/api/investigation/runs/start":
                if current_user is None:
                    _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                    return
                objective = str(payload.get("objective", "")).strip()
                if not objective:
                    raise ValueError("objective is required")
                filters = payload.get("filters", {})
                if not isinstance(filters, dict):
                    raise ValueError("filters must be an object")
                require_review_signoff = bool(payload.get("require_review_signoff", False))
                idempotency_key = str(payload.get("idempotency_key", "")).strip()
                max_attempts = _parse_positive_int(payload.get("max_attempts", 1), 1, max_value=10)

                store = self._store(str(settings["db_path"]))
                if idempotency_key:
                    existing = store.find_investigation_run_by_idempotency(
                        user_id=str(current_user["user_id"]),
                        idempotency_key=idempotency_key,
                    )
                    if existing is not None:
                        _json_response(self, HTTPStatus.OK, existing)
                        return
                run_id = f"run_{int(time.time() * 1000)}_{int(time.perf_counter() * 1000) % 1000:03d}"
                store.create_investigation_run(
                    run_id=run_id,
                    user_id=str(current_user["user_id"]),
                    objective=objective,
                    filters=filters,
                    require_review_signoff=require_review_signoff,
                    idempotency_key=idempotency_key,
                    max_attempts=max_attempts,
                    replay_of_run_id="",
                )
                try:
                    _execute_investigation_run(
                        store=store,
                        user_id=str(current_user["user_id"]),
                        run_id=run_id,
                        objective=objective,
                        filters=filters,
                        require_review_signoff=require_review_signoff,
                    )
                except Exception as exc:
                    retry_state = store.retry_or_fail_investigation_run(
                        user_id=str(current_user["user_id"]),
                        run_id=run_id,
                        error_text=str(exc),
                        backoff_seconds=_parse_positive_int(
                            os.getenv("ALS_RUN_RETRY_BACKOFF_SECONDS", "30"),
                            30,
                            max_value=3600,
                        ),
                    )
                    if not bool(retry_state.get("requeued", False)):
                        raise

                final_row = store.get_investigation_run(user_id=str(current_user["user_id"]), run_id=run_id)
                self._record_activity(
                    settings=settings,
                    user_id=str(current_user["user_id"]),
                    activity_type="investigation_run_started",
                    endpoint=path,
                    payload={"run_id": run_id, "objective": objective, "idempotency_key": idempotency_key},
                )
                _json_response(self, HTTPStatus.OK, final_row)
                return

            if path == "/api/investigation/runs/queue":
                if current_user is None:
                    _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                    return
                objective = str(payload.get("objective", "")).strip()
                if not objective:
                    raise ValueError("objective is required")
                filters = payload.get("filters", {})
                if not isinstance(filters, dict):
                    raise ValueError("filters must be an object")
                require_review_signoff = bool(payload.get("require_review_signoff", False))
                idempotency_key = str(payload.get("idempotency_key", "")).strip()
                delay_seconds = _parse_non_negative_int(payload.get("delay_seconds", 0), 0, max_value=86400)
                max_attempts = _parse_positive_int(payload.get("max_attempts", 3), 3, max_value=10)

                store = self._store(str(settings["db_path"]))
                if idempotency_key:
                    existing = store.find_investigation_run_by_idempotency(
                        user_id=str(current_user["user_id"]),
                        idempotency_key=idempotency_key,
                    )
                    if existing is not None:
                        _json_response(self, HTTPStatus.OK, existing)
                        return

                run_id = f"run_{int(time.time() * 1000)}_{int(time.perf_counter() * 1000) % 1000:03d}"
                scheduled_for = (datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat()
                queued = store.queue_investigation_run(
                    run_id=run_id,
                    user_id=str(current_user["user_id"]),
                    objective=objective,
                    filters=filters,
                    require_review_signoff=require_review_signoff,
                    idempotency_key=idempotency_key,
                    scheduled_for=scheduled_for,
                    max_attempts=max_attempts,
                )
                self._record_activity(
                    settings=settings,
                    user_id=str(current_user["user_id"]),
                    activity_type="investigation_run_queued",
                    endpoint=path,
                    payload={"run_id": run_id, "scheduled_for": scheduled_for, "delay_seconds": delay_seconds},
                )
                _json_response(self, HTTPStatus.OK, queued)
                return

            if path == "/api/investigation/runs/approve":
                if current_user is None:
                  _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                  return
                run_id = str(payload.get("run_id", "")).strip()
                decision = str(payload.get("decision", "approved")).strip().lower()
                reviewer = str(payload.get("reviewer") or current_user.get("email") or current_user.get("user_id") or "").strip()
                if not run_id:
                  raise ValueError("run_id is required")
                if decision not in {"approved", "rejected", "pending"}:
                  raise ValueError("decision must be approved, rejected, or pending")

                store = self._store(str(settings["db_path"]))
                row = store.set_investigation_run_approval(
                  user_id=str(current_user["user_id"]),
                  run_id=run_id,
                  status=decision,
                  reviewer=reviewer,
                )
                _json_response(self, HTTPStatus.OK, row)
                return

            if path == "/api/investigation/runs/rollback":
                if current_user is None:
                  _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                  return
                source_run_id = str(payload.get("run_id", "")).strip()
                if not source_run_id:
                  raise ValueError("run_id is required")
                reason = str(payload.get("reason", "Rollback requested")).strip() or "Rollback requested"
                queue_mode = bool(payload.get("queue", True))
                delay_seconds = _parse_non_negative_int(payload.get("delay_seconds", 0), 0, max_value=86400)

                store = self._store(str(settings["db_path"]))
                source_run = store.get_investigation_run(
                  user_id=str(current_user["user_id"]),
                  run_id=source_run_id,
                )
                objective = str(source_run.get("objective", "")).strip()
                filters = source_run.get("filters") if isinstance(source_run.get("filters"), dict) else {}
                require_review_signoff = bool(source_run.get("require_review_signoff", False))
                max_attempts = int(source_run.get("max_attempts") or 3)

                rollback_run_id = f"run_{int(time.time() * 1000)}_{int(time.perf_counter() * 1000) % 1000:03d}"
                if queue_mode:
                  rollback_row = store.queue_investigation_run(
                    run_id=rollback_run_id,
                    user_id=str(current_user["user_id"]),
                    objective=objective,
                    filters=filters,
                    require_review_signoff=require_review_signoff,
                    idempotency_key=f"rollback:{source_run_id}:{rollback_run_id}",
                    scheduled_for=(datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat(),
                    max_attempts=max_attempts,
                  )
                else:
                  store.create_investigation_run(
                    run_id=rollback_run_id,
                    user_id=str(current_user["user_id"]),
                    objective=objective,
                    filters=filters,
                    require_review_signoff=require_review_signoff,
                    idempotency_key=f"rollback:{source_run_id}:{rollback_run_id}",
                    max_attempts=max_attempts,
                  )
                  rollback_row = _execute_investigation_run(
                    store=store,
                    user_id=str(current_user["user_id"]),
                    run_id=rollback_run_id,
                    objective=objective,
                    filters=filters,
                    require_review_signoff=require_review_signoff,
                  )

                source_after = store.mark_investigation_run_rolled_back(
                  user_id=str(current_user["user_id"]),
                  run_id=source_run_id,
                  rollback_run_id=rollback_run_id,
                )
                _json_response(
                  self,
                  HTTPStatus.OK,
                  {
                    "source_run": source_after,
                    "rollback_run": rollback_row,
                    "reason": reason,
                  },
                )
                return

            if path == "/api/investigation/templates/save":
                if current_user is None:
                  _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                  return
                name = str(payload.get("name", "")).strip()
                objective = str(payload.get("objective", "")).strip()
                filters = payload.get("filters", {})
                require_review_signoff = bool(payload.get("require_review_signoff", False))
                template_id = str(payload.get("template_id", "")).strip()
                if not name:
                  raise ValueError("name is required")
                if not objective:
                  raise ValueError("objective is required")
                if not isinstance(filters, dict):
                  raise ValueError("filters must be an object")
                if not template_id:
                  template_id = f"tpl_{int(time.time() * 1000)}_{int(time.perf_counter() * 1000) % 1000:03d}"

                store = self._store(str(settings["db_path"]))
                saved = store.save_investigation_template(
                  template_id=template_id,
                  user_id=str(current_user["user_id"]),
                  name=name,
                  objective=objective,
                  filters=filters,
                  require_review_signoff=require_review_signoff,
                )
                _json_response(self, HTTPStatus.OK, saved)
                return

            if path == "/api/investigation/templates/run":
                if current_user is None:
                  _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                  return
                template_id = str(payload.get("template_id", "")).strip()
                if not template_id:
                  raise ValueError("template_id is required")
                queue_mode = bool(payload.get("queue", True))
                delay_seconds = _parse_non_negative_int(payload.get("delay_seconds", 0), 0, max_value=86400)
                max_attempts = _parse_positive_int(payload.get("max_attempts", 3), 3, max_value=10)

                store = self._store(str(settings["db_path"]))
                template = store.get_investigation_template(
                  user_id=str(current_user["user_id"]),
                  template_id=template_id,
                )
                store.touch_investigation_template(
                  user_id=str(current_user["user_id"]),
                  template_id=template_id,
                )
                objective = str(template.get("objective", ""))
                filters = template.get("filters") if isinstance(template.get("filters"), dict) else {}
                require_review_signoff = bool(template.get("require_review_signoff", False))
                run_id = f"run_{int(time.time() * 1000)}_{int(time.perf_counter() * 1000) % 1000:03d}"
                if queue_mode:
                  row = store.queue_investigation_run(
                    run_id=run_id,
                    user_id=str(current_user["user_id"]),
                    objective=objective,
                    filters=filters,
                    require_review_signoff=require_review_signoff,
                    idempotency_key=f"template:{template_id}:{run_id}",
                    scheduled_for=(datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat(),
                    max_attempts=max_attempts,
                  )
                else:
                  store.create_investigation_run(
                    run_id=run_id,
                    user_id=str(current_user["user_id"]),
                    objective=objective,
                    filters=filters,
                    require_review_signoff=require_review_signoff,
                    idempotency_key=f"template:{template_id}:{run_id}",
                    max_attempts=max_attempts,
                  )
                  row = _execute_investigation_run(
                    store=store,
                    user_id=str(current_user["user_id"]),
                    run_id=run_id,
                    objective=objective,
                    filters=filters,
                    require_review_signoff=require_review_signoff,
                  )
                _json_response(
                  self,
                  HTTPStatus.OK,
                  {
                    "template": template,
                    "run": row,
                  },
                )
                return

            if path == "/api/automation/experiments/run":
                if current_user is None:
                  _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                  return
                name = str(payload.get("name", "")).strip() or "Automation experiment"
                objective = str(payload.get("objective", "")).strip()
                base_filters = payload.get("filters", {})
                variant_a = payload.get("variant_a", {})
                variant_b = payload.get("variant_b", {})
                if not objective:
                  raise ValueError("objective is required")
                if not isinstance(base_filters, dict):
                  raise ValueError("filters must be an object")
                if not isinstance(variant_a, dict) or not isinstance(variant_b, dict):
                  raise ValueError("variant_a and variant_b must be objects")

                variant_a_filters = variant_a.get("filters", {}) if isinstance(variant_a.get("filters"), dict) else {}
                variant_b_filters = variant_b.get("filters", {}) if isinstance(variant_b.get("filters"), dict) else {}
                require_signoff_a = bool(variant_a.get("require_review_signoff", False))
                require_signoff_b = bool(variant_b.get("require_review_signoff", False))

                store = self._store(str(settings["db_path"]))
                run_id_a = f"run_{int(time.time() * 1000)}_{int(time.perf_counter() * 1000) % 1000:03d}"
                run_id_b = f"run_{int(time.time() * 1000) + 1}_{int(time.perf_counter() * 1000) % 1000:03d}"

                merged_a = dict(base_filters)
                merged_a.update(variant_a_filters)
                merged_b = dict(base_filters)
                merged_b.update(variant_b_filters)

                store.create_investigation_run(
                  run_id=run_id_a,
                  user_id=str(current_user["user_id"]),
                  objective=objective,
                  filters=merged_a,
                  require_review_signoff=require_signoff_a,
                  idempotency_key=f"exp:{name}:a:{run_id_a}",
                  max_attempts=1,
                )
                result_a = _execute_investigation_run(
                  store=store,
                  user_id=str(current_user["user_id"]),
                  run_id=run_id_a,
                  objective=objective,
                  filters=merged_a,
                  require_review_signoff=require_signoff_a,
                )

                store.create_investigation_run(
                  run_id=run_id_b,
                  user_id=str(current_user["user_id"]),
                  objective=objective,
                  filters=merged_b,
                  require_review_signoff=require_signoff_b,
                  idempotency_key=f"exp:{name}:b:{run_id_b}",
                  max_attempts=1,
                )
                result_b = _execute_investigation_run(
                  store=store,
                  user_id=str(current_user["user_id"]),
                  run_id=run_id_b,
                  objective=objective,
                  filters=merged_b,
                  require_review_signoff=require_signoff_b,
                )

                score_a = _score_experiment_variant(result_a)
                score_b = _score_experiment_variant(result_b)
                winner = "a" if score_a >= score_b else "b"
                experiment_id = f"exp_{int(time.time() * 1000)}_{int(time.perf_counter() * 1000) % 1000:03d}"
                experiment = store.create_automation_experiment(
                  experiment_id=experiment_id,
                  user_id=str(current_user["user_id"]),
                  name=name,
                  objective=objective,
                  filters=base_filters,
                  variant_a=variant_a,
                  variant_b=variant_b,
                  result={
                    "run_id_a": run_id_a,
                    "run_id_b": run_id_b,
                    "score_a": score_a,
                    "score_b": score_b,
                  },
                  winner_variant=winner,
                )
                _json_response(self, HTTPStatus.OK, experiment)
                return

            if path == "/api/export/automated":
                if current_user is None:
                  _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                  return
                run_id = str(payload.get("run_id", "")).strip()
                channel = str(payload.get("channel", "markdown_file")).strip().lower()
                if not run_id:
                  raise ValueError("run_id is required")
                if channel not in {"markdown_file", "json_file", "webhook"}:
                  raise ValueError("channel must be markdown_file, json_file, or webhook")

                store = self._store(str(settings["db_path"]))
                run_row = store.get_investigation_run(user_id=str(current_user["user_id"]), run_id=run_id)
                report = run_row.get("report") if isinstance(run_row.get("report"), dict) else {}
                markdown = _build_report_markdown(report)
                delivery_id = f"dly_{int(time.time() * 1000)}_{int(time.perf_counter() * 1000) % 1000:03d}"

                result_payload: dict[str, object] = {}
                status = "delivered"
                error_text = ""
                if channel in {"markdown_file", "json_file"}:
                  export_dir = str(os.getenv("ALS_AUTOMATION_EXPORT_DIR", "data/automation_exports")).strip() or "data/automation_exports"
                  os.makedirs(export_dir, exist_ok=True)
                  suffix = "md" if channel == "markdown_file" else "json"
                  file_path = os.path.join(export_dir, f"{run_id}.{suffix}")
                  content = markdown if channel == "markdown_file" else json.dumps(report, indent=2)
                  with open(file_path, "w", encoding="utf-8") as handle:
                    handle.write(content)
                  result_payload = {"file_path": file_path, "bytes": len(content.encode("utf-8"))}
                else:
                  webhook_url = str(payload.get("webhook_url", "")).strip()
                  if not webhook_url:
                    raise ValueError("webhook_url is required for webhook channel")
                  try:
                    req = Request(
                      webhook_url,
                      data=json.dumps(
                        {
                          "run_id": run_id,
                          "objective": run_row.get("objective", ""),
                          "quality_gate": run_row.get("quality_gate", {}),
                          "report": report,
                          "markdown": markdown,
                        },
                        ensure_ascii=True,
                      ).encode("utf-8"),
                      headers={"Content-Type": "application/json"},
                      method="POST",
                    )
                    with urlopen(req, timeout=float(os.getenv("ALS_AUTOMATION_EXPORT_TIMEOUT_SECONDS", "8") or "8")) as resp:
                      result_payload = {
                        "status_code": int(getattr(resp, "status", 200)),
                        "reason": str(getattr(resp, "reason", "")),
                      }
                  except (HTTPError, URLError, TimeoutError) as exc:
                    status = "failed"
                    error_text = str(exc)
                    result_payload = {"error": error_text}

                store.set_investigation_run_export_status(
                  user_id=str(current_user["user_id"]),
                  run_id=run_id,
                  export_status="delivered" if status == "delivered" else "failed",
                )
                export_row = store.record_automation_export(
                  delivery_id=delivery_id,
                  user_id=str(current_user["user_id"]),
                  run_id=run_id,
                  channel=channel,
                  payload={"run_id": run_id, "channel": channel},
                  result=result_payload,
                  status=status,
                  error_text=error_text,
                )
                if status != "delivered":
                  _json_response(self, HTTPStatus.BAD_GATEWAY, export_row)
                  return
                _json_response(self, HTTPStatus.OK, export_row)
                return

            if path == "/api/investigation/runs/replay":
                if current_user is None:
                    _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
                    return
                source_run_id = str(payload.get("source_run_id", "")).strip()
                if not source_run_id:
                    raise ValueError("source_run_id is required")

                store = self._store(str(settings["db_path"]))
                baseline_run = store.get_investigation_run(user_id=str(current_user["user_id"]), run_id=source_run_id)
                objective = str(baseline_run.get("objective", "")).strip()
                filters = baseline_run.get("filters") if isinstance(baseline_run.get("filters"), dict) else {}

                run_id = f"run_{int(time.time() * 1000)}_{int(time.perf_counter() * 1000) % 1000:03d}"
                store.create_investigation_run(
                    run_id=run_id,
                    user_id=str(current_user["user_id"]),
                    objective=objective,
                    filters=filters,
                  require_review_signoff=False,
                    replay_of_run_id=source_run_id,
                )

                evidence_rows = _attach_source_urls_to_rows(store.all_evidence())
                filtered_rows = _apply_evidence_filters(evidence_rows, filters)
                contradictions = store.contradiction_pairs()
                report = _build_autonomous_run_report(
                    objective=objective,
                    filters=filters,
                    evidence_rows=filtered_rows,
                    contradiction_rows=contradictions,
                    require_review_signoff=False,
                    approved_claim_ids=set(),
                )
                gate = _evaluate_report_gate(
                    report_payload=report,
                    evidence_rows=filtered_rows,
                    contradiction_rows=contradictions,
                )
                replay_diff = _build_replay_diff(
                    baseline_run=baseline_run,
                    current_report=report,
                    current_quality_gate=gate,
                )
                store.complete_investigation_run(
                    user_id=str(current_user["user_id"]),
                    run_id=run_id,
                    status="completed",
                    report=report,
                    quality_gate=gate,
                    replay_diff=replay_diff,
                )

                final_row = store.get_investigation_run(user_id=str(current_user["user_id"]), run_id=run_id)
                self._record_activity(
                    settings=settings,
                    user_id=str(current_user["user_id"]),
                    activity_type="investigation_run_replayed",
                    endpoint=path,
                    payload={"run_id": run_id, "source_run_id": source_run_id},
                )
                _json_response(self, HTTPStatus.OK, final_row)
                return

            settings = self._settings()
            db_path = str(payload.get("db_path") or settings["db_path"])
            store = self._store(db_path)

            filters = payload.get("filters", {})
            if not isinstance(filters, dict):
                filters = {}
            filtered_rows = _attach_source_urls_to_rows(
              store.filter_evidence(
                filters=filters,
                limit=_resolve_chat_evidence_limit(payload),
              )
            )

            limit = _parse_positive_int(payload.get("limit", 50), 50, max_value=500)
            offset = _parse_non_negative_int(payload.get("offset", 0), 0)

            if path == "/api/evidence/filter":
                page_rows, total, has_more = _paginate_rows(filtered_rows, limit=limit, offset=offset)
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "rows": page_rows,
                        "total": total,
                        "limit": limit,
                        "offset": offset,
                        "has_more": has_more,
                    },
                )
                return

            if path == "/api/evidence/search":
                query = str(payload.get("query", ""))
                searched_rows = _search_evidence_rows(filtered_rows, query)
                page_rows, total, has_more = _paginate_rows(searched_rows, limit=limit, offset=offset)
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "rows": page_rows,
                        "total": total,
                        "limit": limit,
                        "offset": offset,
                        "has_more": has_more,
                    },
                )
                return

            if path == "/api/synthesis":
                require_review_signoff = bool(payload.get("require_review_signoff", False))
                approved_claim_ids_raw = payload.get("approved_claim_ids", [])
                if not isinstance(approved_claim_ids_raw, list):
                    raise ValueError("approved_claim_ids must be a list")
                approved_claim_ids = {str(x) for x in approved_claim_ids_raw if str(x).strip()}
                contradictions = _contradiction_pairs_from_rows(filtered_rows, limit=300)
                composition = _build_investigator_synthesis(
                    evidence_rows=filtered_rows,
                    contradiction_rows=contradictions,
                    require_review_signoff=require_review_signoff,
                    approved_claim_ids=approved_claim_ids,
                    store=store,
                )
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "evidence_count": len(filtered_rows),
                        "composition": composition,
                    },
                )
                return

            raw_messages = payload.get("messages", [])
            if not isinstance(raw_messages, list):
                raise ValueError("messages must be a list")
            messages = [message for message in raw_messages if isinstance(message, dict)][-40:]

            host = str(payload.get("host") or settings["ollama_host"])
            model = str(payload.get("model") or settings["model"])
            context_limit = _parse_positive_int(payload.get("context_limit") or settings["context_limit"], int(settings["context_limit"]), max_value=200)
            temperature = float(payload.get("temperature") or settings["temperature"])
            timeout_seconds = int(payload.get("timeout_seconds") or settings["timeout_seconds"])
            language = str(payload.get("language") or "en").strip().lower()
            if language not in {"en", "es"}:
              language = "en"

            trace: dict[str, object] = {
              "trace_id": _new_trace_id(),
              "mode": "sync",
              "path": path,
              "started_at": int(time.time()),
              "status": "ok",
              "model": model,
              "language": language,
              "phase_seconds": {},
            }
            if current_user is not None:
                trace["user_id"] = str(current_user.get("user_id", ""))

            phase_prompt_started = time.perf_counter()
            prompt = _build_chat_prompt(messages, filtered_rows, context_limit, language)
            trace["phase_seconds"]["building_prompt"] = round(time.perf_counter() - phase_prompt_started, 4)

            phase_generation_started = time.perf_counter()
            answer = generate_with_ollama(
                prompt=prompt,
                model=model,
                host=host,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
            )
            generated_seconds = time.perf_counter() - phase_generation_started
            trace["phase_seconds"]["generating"] = round(generated_seconds, 4)

            phase_post_started = time.perf_counter()
            contradictions = _contradiction_pairs_from_rows(filtered_rows, limit=300)
            synthesis = _build_synthesis(answer=answer, evidence_rows=filtered_rows, contradiction_rows=contradictions)
            synthesis, guardrail_flags = _apply_response_guardrails(
                answer=answer,
                synthesis=synthesis,
                evidence_rows=filtered_rows,
                contradiction_rows=contradictions,
              language=language,
            )
            mentioned_claim_ids = synthesis.get("mentioned_claim_ids") if isinstance(synthesis.get("mentioned_claim_ids"), list) else []
            mentioned_claim_id_set = {str(x) for x in mentioned_claim_ids if str(x).strip()}
            cited_evidence_rows = [
              row for row in filtered_rows if str(row.get("claim_id", "")).strip() in mentioned_claim_id_set
            ]
            cited_evidence_rows = _rank_cited_evidence_rows(cited_evidence_rows)
            cited_evidence_rows = cited_evidence_rows[:MAX_CITED_EVIDENCE_ROWS]
            if _should_translate_cited_rows(payload=payload, language=language):
              cited_evidence_rows = _translate_evidence_rows_for_language(
                rows=cited_evidence_rows,
                language=language,
                model=model,
                host=host,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
              )
            trace["phase_seconds"]["post_processing"] = round(time.perf_counter() - phase_post_started, 4)
            trace["phase_seconds"]["loading_evidence"] = 0.0
            trace["evidence_count"] = len(filtered_rows)
            trace["cited_evidence_count"] = len(cited_evidence_rows)
            trace["guardrail_flags"] = guardrail_flags
            trace["verification_flags"] = (
                synthesis.get("verification_flags")
                if isinstance(synthesis.get("verification_flags"), list)
                else []
            )
            trace["total_seconds"] = round(sum(float(v) for v in trace["phase_seconds"].values()), 4)
            _append_query_telemetry(trace)
            if current_user is not None:
              self._record_activity(
                settings=settings,
                user_id=str(current_user["user_id"]),
                activity_type="chat_sync",
                endpoint=path,
                payload={"evidence_count": len(filtered_rows), "trace_id": str(trace.get("trace_id", ""))},
              )

            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "answer": answer,
                    "evidence_count": len(filtered_rows),
                    "model": model,
                    "host": host,
                    "generated_seconds": round(generated_seconds, 3),
                    "synthesis": synthesis,
                    "evidence_rows": cited_evidence_rows,
                    "response_mode": "sync",
                    "guardrail_flags": guardrail_flags,
                    "telemetry": trace,
                },
            )
        except ValueError as exc:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except LocalLLMError as exc:
            _json_response(self, HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
        except Exception as exc:  # pragma: no cover
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="als-intel-web", description="Local ALS investigator web UI")
    parser.add_argument("--host", default=os.getenv("ALS_WEB_HOST", "0.0.0.0"), help="Host interface to bind")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite evidence database path")
    parser.add_argument("--model", default=DEFAULT_OLLAMA_MODEL, help="Ollama model name")
    parser.add_argument("--ollama-host", default=DEFAULT_OLLAMA_HOST, help="Ollama base URL")
    parser.add_argument("--context-limit", type=int, default=DEFAULT_CONTEXT_LIMIT, help="Evidence rows included in prompt")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE, help="LLM sampling temperature")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="LLM request timeout")
    parser.add_argument("--auth-enabled", action="store_true", default=DEFAULT_AUTH_ENABLED, help="Enable authentication guardrails")
    parser.add_argument("--magic-link-dev-mode", action="store_true", default=os.getenv("ALS_MAGIC_LINK_DEV_MODE", "1") in {"1", "true", "True"}, help="Return dev magic links in API responses")
    parser.add_argument("--app-base-url", default=os.getenv("ALS_APP_BASE_URL", "http://localhost:8000"), help="Public base URL used in magic links")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    os.environ["ALS_DB_PATH"] = args.db
    os.environ["OLLAMA_HOST"] = args.ollama_host
    os.environ["OLLAMA_MODEL"] = args.model
    os.environ["ALS_CONTEXT_LIMIT"] = str(args.context_limit)
    os.environ["ALS_TEMPERATURE"] = str(args.temperature)
    os.environ["ALS_TIMEOUT_SECONDS"] = str(args.timeout_seconds)
    os.environ["ALS_AUTH_ENABLED"] = "1" if bool(args.auth_enabled) else "0"
    os.environ["ALS_MAGIC_LINK_DEV_MODE"] = "1" if bool(args.magic_link_dev_mode) else "0"
    os.environ["ALS_APP_BASE_URL"] = str(args.app_base_url)

    server = ThreadingHTTPServer((args.host, args.port), ChatHandler)
    print(f"ALS Intel Investigator UI running on http://{args.host}:{args.port}")
    print(f"Using database: {args.db}")
    print(f"Using Ollama host: {args.ollama_host}")
    print(f"Using model: {args.model}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
