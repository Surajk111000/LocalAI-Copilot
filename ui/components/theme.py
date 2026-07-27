"""Shared theme + layout helpers (dark / light)."""

from __future__ import annotations

import streamlit as st

DARK_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
:root {
  --bg-0: #0d1117; --bg-1: #161b22; --bg-2: #1c2128; --border: #30363d;
  --text: #e6edf3; --muted: #8b949e; --accent: #3fb950; --accent-2: #58a6ff;
}
html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; color: var(--text); }
.stApp {
  background: radial-gradient(1200px 600px at 10% -10%, #1a2332 0%, transparent 55%),
              radial-gradient(900px 500px at 100% 0%, #13201a 0%, transparent 50%),
              var(--bg-0);
}
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #0f141b 0%, #0d1117 100%);
  border-right: 1px solid var(--border);
  min-width: 320px !important; max-width: 420px !important;
}
.copilot-brand {
  font-size: 1.55rem; font-weight: 600; margin: 0 0 0.15rem 0;
  background: linear-gradient(90deg, #e6edf3, #3fb950);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.copilot-sub { color: var(--muted); font-size: 0.9rem; margin-bottom: 0.8rem; }
.token-pill {
  display: inline-block; background: #21262d; border: 1px solid var(--border);
  border-radius: 6px; padding: 0.15rem 0.5rem;
  font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; color: var(--accent-2);
}
.loading-pulse { animation: pulse 1.2s ease-in-out infinite; color: var(--accent-2); }
@keyframes pulse { 0%,100%{opacity:.45} 50%{opacity:1} }
div[data-testid="stChatMessage"] {
  background: var(--bg-1); border: 1px solid var(--border); border-radius: 10px;
}
.stButton > button {
  border-radius: 8px; border: 1px solid var(--border); background: var(--bg-2); color: var(--text);
}
.stButton > button[kind="primary"] {
  background: linear-gradient(180deg, #238636, #1a7f37); border-color: #2ea043;
}
code, pre, .stCode { font-family: 'JetBrains Mono', monospace !important; }
</style>
"""

LIGHT_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
:root {
  --bg-0: #f6f8fa; --bg-1: #ffffff; --bg-2: #eef2f6; --border: #d0d7de;
  --text: #1f2328; --muted: #656d76; --accent: #1a7f37; --accent-2: #0969da;
}
html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; color: var(--text); }
.stApp {
  background: radial-gradient(1000px 500px at 0% 0%, #e7f2ff 0%, transparent 50%),
              radial-gradient(800px 400px at 100% 0%, #e9f7ee 0%, transparent 45%),
              var(--bg-0);
}
[data-testid="stSidebar"] {
  background: #ffffff; border-right: 1px solid var(--border);
  min-width: 320px !important; max-width: 420px !important;
}
.copilot-brand {
  font-size: 1.55rem; font-weight: 600; margin: 0 0 0.15rem 0;
  background: linear-gradient(90deg, #1f2328, #1a7f37);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.copilot-sub { color: var(--muted); font-size: 0.9rem; margin-bottom: 0.8rem; }
.token-pill {
  display: inline-block; background: #eef2f6; border: 1px solid var(--border);
  border-radius: 6px; padding: 0.15rem 0.5rem;
  font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; color: var(--accent-2);
}
div[data-testid="stChatMessage"] {
  background: var(--bg-1); border: 1px solid var(--border); border-radius: 10px;
}
.stButton > button {
  border-radius: 8px; border: 1px solid var(--border); background: var(--bg-2); color: var(--text);
}
.stButton > button[kind="primary"] {
  background: linear-gradient(180deg, #2da44e, #1a7f37); border-color: #1a7f37; color: #fff;
}
code, pre, .stCode { font-family: 'JetBrains Mono', monospace !important; }
</style>
"""


def inject_theme(theme: str | None = None) -> None:
    choice = (theme or st.session_state.get("ui_theme") or "dark").lower()
    st.session_state.ui_theme = choice
    st.markdown(LIGHT_CSS if choice == "light" else DARK_CSS, unsafe_allow_html=True)


def brand_header(subtitle: str = "") -> None:
    st.markdown(
        '<div class="copilot-brand">Local AI Coding Copilot</div>',
        unsafe_allow_html=True,
    )
    if subtitle:
        st.markdown(f'<div class="copilot-sub">{subtitle}</div>', unsafe_allow_html=True)
