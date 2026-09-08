#!/usr/bin/env python3
"""summarize-theme.py — async, real semantic intent summary for one status-bar theme.

OBJECTIVE — the status bar should show what the user is actually trying to
accomplish, synthesized across every prompt in the current theme, not a
truncated excerpt of the latest one.

log-prompt.py's theme_label() is a synchronous, stdlib-only fallback (it must
finish before Claude responds, per that hook's own docstring) — a truncated
clause, at best. This script is the deliberately-async upgrade: spawned
detached from log-prompt.py, never waited on, so a real model call's latency
(observed ~5-6s) never touches the hook path. Owner-authorized 2026-08-31:
"summarize intent, not per prompt... feel free to include a slight delay and
semantic parsing of intention."

Invoked as: summarize-theme.py <session_id> <theme_ts>

Reads every real (non-system_notification) prompt recorded under the theme
starting at <theme_ts>, asks a cheap model for an intent summary across all of
them, and writes the result back into that one theme entry in
state-<session_id>.json — found by matching <theme_ts>, so a theme that has
since rotated out of the tracked list (a fast-moving session can shift topics
before this returns) is silently skipped rather than resurrected.

Uses the already-authenticated `claude` CLI rather than a separate API key:
`--settings '{"hooks":{}}'` suppresses this repo's own hooks for the call
(verified empirically — no session file is written for it), which matters
because a non-suppressed sub-call would otherwise recurse into log-prompt.py
under a throwaway session id and could fire Stop-hook side effects (a sound,
a tab-bar flag) for a call the user never asked to be notified about.
`--restricted` removes command/code execution — this is a pure text task.

Every failure mode (no `claude` on PATH, no network, a timeout, empty output)
is silent: this is a nice-to-have enhancement over an already-working
fallback label, never something that should surface an error anywhere.
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))

import hooklib as H   # noqa: E402

MAX_PROMPTS = 20          # bound the joined text so the call stays cheap and fast
MAX_PROMPT_CHARS = 4000   # total budget across all joined prompts
MAX_LABEL_CHARS = 60      # matches log-prompt.py's MAX_THEME_LABEL
CALL_TIMEOUT_S = 20

INSTRUCTION = (
    'TASK: output ONLY a plain-text phrase of at most 8 words summarizing the INTENT '
    'behind the following user messages, as a whole, not just the last one. Do not ask '
    'questions. Do not add preamble, quotes, or punctuation at the end. Just the phrase.\n\n'
    'MESSAGES:\n'
)


def gather_prompts(session_id, theme_ts):
    """Every real prompt at or after theme_ts, oldest first, capped in count and size."""
    events = H.read_jsonl(H.session_file(session_id))
    theme_dt = H.parse_ts(theme_ts)
    if theme_dt is None:
        return []
    texts = []
    for ev in events:
        if ev.get('event') != 'prompt' or ev.get('classification') == 'system_notification':
            continue
        ts = H.parse_ts(ev.get('ts'))
        if ts is None or ts < theme_dt:
            continue
        text = str(ev.get('prompt_text') or '').strip()
        if text:
            texts.append(text)
    return texts[-MAX_PROMPTS:]


def build_message_block(texts):
    joined = []
    total = 0
    for t in texts:
        if total + len(t) > MAX_PROMPT_CHARS:
            break
        joined.append(t)
        total += len(t)
    return '\n---\n'.join(joined)


def call_model(message_block):
    try:
        proc = subprocess.run(
            ['claude', '-p', '--restricted', '--model', 'haiku',
             '--settings', '{"hooks":{}}', INSTRUCTION + message_block],
            capture_output=True, text=True, timeout=CALL_TIMEOUT_S)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    out = (proc.stdout or '').strip()
    return out or None


def clean_summary(text):
    """One line, word-boundary truncated — same shape log-prompt.py's labels use."""
    line = ' '.join(text.split('\n')[0].split())
    if len(line) <= MAX_LABEL_CHARS:
        return line
    cut = line[:MAX_LABEL_CHARS]
    cut = cut.rsplit(' ', 1)[0] if ' ' in cut else cut
    return cut.rstrip(' .,;:!?') + '…'


def write_back(session_id, theme_ts, summary):
    path = H.state_file(session_id)
    state = H.read_json(path)
    if not isinstance(state, dict):
        return
    themes = state.get('themes') or []
    target = next((t for t in themes if isinstance(t, dict) and t.get('ts') == theme_ts), None)
    if target is None:
        return   # this theme has already rotated out — do not resurrect it
    target['label'] = summary
    H.write_json(path, state)


def main():
    if len(sys.argv) < 3:
        return
    session_id, theme_ts = sys.argv[1], sys.argv[2]

    texts = gather_prompts(session_id, theme_ts)
    if not texts:
        return
    message_block = build_message_block(texts)
    if not message_block:
        return

    raw = call_model(message_block)
    if not raw:
        return
    summary = clean_summary(raw)
    if not summary:
        return
    write_back(session_id, theme_ts, summary)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        pass
