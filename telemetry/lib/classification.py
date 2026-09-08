#!/usr/bin/env python3
"""classification.py — pure prompt-classification logic (port of lib/classification.ps1).

No I/O, no side effects, no paths: log-prompt.py imports it and
tests/classification.test.py exercises it directly, so the tested logic IS the
runtime logic.

Classifications:
  first_prompt        — no prior events in session
  followup            — Claude had stopped; prompt is a clean next step (including
                        post-stop additive language)
  override            — Claude had stopped; user explicitly redirects the direction
  addition            — Claude is running; user queues context or a parallel task
  denial_context      — Claude is running; user denied a tool call and is explaining
  system_notification — a `<task-notification>`/`<cross-session-message>` delivery;
                        not something the user typed, scored as zero friction

Friction scores (applied in analyze-session.py):
  override +3    addition +1    denial_context +1    followup/first_prompt/system_notification 0
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hooklib import parse_ts   # noqa: E402  (needs the path fix above)

# A background-agent completion or a peer session's message arrives through the
# same UserPromptSubmit path as real user text, tagged at the start of the body.
# Their content routinely contains everyday words ("instead", "forget", "also")
# that the override/addition regexes below would otherwise misread as user
# friction — so this must be checked, and short-circuit, before any of them run.
_SYSTEM_NOTIFICATION = re.compile(r'^\s*<(task-notification|cross-session-message)\b',
                                   re.IGNORECASE)


def is_system_notification(text):
    """True when the prompt is a system-injected delivery, not user-typed text."""
    if not text or not str(text).strip():
        return False
    return bool(_SYSTEM_NOTIFICATION.match(str(text)))

# Start-anchored: these words redirect meaning only when they lead the prompt,
# so "There's no issue with that" must not read as an override.
_OVERRIDE_START = [
    re.compile(r'^\s*actually\b', re.IGNORECASE),
    re.compile(r'^\s*no[,\s!]', re.IGNORECASE),
    re.compile(r'^\s*wait[,\s]', re.IGNORECASE),
    re.compile(r'^\s*stop\b', re.IGNORECASE),
    re.compile(r'^\s*undo\b', re.IGNORECASE),
]

# Anywhere: these unambiguously signal replacement regardless of position.
_OVERRIDE_ANY = [
    re.compile(r'\bforget\s+(that|this|it)\b', re.IGNORECASE),
    re.compile(r'\binstead\b', re.IGNORECASE),
    re.compile(r'\bscratch\s+that\b', re.IGNORECASE),
    re.compile(r'\bstart\s+over\b', re.IGNORECASE),
    re.compile(r'\bnever\s+mind\b', re.IGNORECASE),
    re.compile(r'\bcancel\s+(that|this)\b', re.IGNORECASE),
    re.compile(r'\bignore\s+(that|this|previous|the\s+previous)\b', re.IGNORECASE),
    re.compile(r'\bdisregard\b', re.IGNORECASE),
    re.compile(r"\blet.s\s+\w+\s+instead\b", re.IGNORECASE),
]

_ADDITION_PATTERNS = [
    re.compile(r'\balso\b', re.IGNORECASE),
    re.compile(r'\badditionally\b', re.IGNORECASE),
    re.compile(r'\bnote\s+that\b', re.IGNORECASE),
    re.compile(r"\bdon.t\s+forget\b", re.IGNORECASE),
    re.compile(r'\bby\s+the\s+way\b', re.IGNORECASE),
    re.compile(r'\boh\s+and\b', re.IGNORECASE),
    re.compile(r'\bone\s+more\s+thing\b', re.IGNORECASE),
    re.compile(r'\bforgot\s+to\s+(mention|add|say|include)\b', re.IGNORECASE),
    re.compile(r"\bwhile\s+you.re\s+at\s+it\b", re.IGNORECASE),
    re.compile(r'\bfurthermore\b', re.IGNORECASE),
    re.compile(r'\bseparately\b', re.IGNORECASE),
]

# A permission request logged under either name counts as "a tool wanted approval".
PERM_EVENTS = ('permission_req', 'perm_req_repeat')


def is_override(text):
    if not text or not str(text).strip():
        return False
    text = str(text)
    return any(p.search(text) for p in _OVERRIDE_START + _OVERRIDE_ANY)


def is_addition(text):
    """Detects additive language.

    Not called from classify() — post-stop additive prompts classify as
    'followup' — but kept because it is the documented signal and is unit-tested
    directly, matching the PowerShell original.
    """
    if not text or not str(text).strip():
        return False
    text = str(text)
    return any(p.search(text) for p in _ADDITION_PATTERNS)


def _ts(event):
    return parse_ts(event.get('ts')) if isinstance(event, dict) else None


def _last_of(events, event_name):
    found = None
    for event in events:
        if isinstance(event, dict) and event.get('event') == event_name:
            found = event
    return found


def is_denial_context(prior_events):
    """True when the current turn holds a permission request that no tool_done answered.

    An unmatched request means the tool was denied, so the prompt the user is
    submitting now is them explaining why — distinct friction from a plain
    mid-run addition. Scoped to events after the most recent prompt so a denial
    from an earlier turn cannot keep re-triggering.
    """
    if not prior_events:
        return False

    last_prompt = _last_of(prior_events, 'prompt')
    if last_prompt is not None:
        prompt_ts = _ts(last_prompt)
        turn_events = []
        for event in prior_events:
            event_ts = _ts(event)
            if prompt_ts is not None and event_ts is not None and event_ts > prompt_ts:
                turn_events.append(event)
    else:
        turn_events = list(prior_events)

    perm_events = [e for e in turn_events if e.get('event') in PERM_EVENTS]
    if not perm_events:
        return False

    tool_dones = [e for e in turn_events if e.get('event') == 'tool_done']

    for req in perm_events:
        req_ts = _ts(req)
        matched = False
        for done in tool_dones:
            done_ts = _ts(done)
            if (done.get('tool') == req.get('tool')
                    and req_ts is not None and done_ts is not None
                    and done_ts > req_ts):
                matched = True
                break
        if not matched:
            return True   # unmatched request = denied
    return False


def classify(prompt_text, prior_events):
    """The classification for a prompt, given the session's events so far."""
    if is_system_notification(prompt_text):
        return 'system_notification'
    if not prior_events:
        return 'first_prompt'

    last_stop = _last_of(prior_events, 'stop')
    last_prompt = _last_of(prior_events, 'prompt')

    if last_prompt is None:
        return 'first_prompt'

    stop_ts = _ts(last_stop) if last_stop is not None else None
    prompt_ts = _ts(last_prompt)
    claude_stopped = (stop_ts is not None and prompt_ts is not None and stop_ts > prompt_ts)

    if not claude_stopped:
        # Claude is still generating — a denied tool call outranks a plain addition.
        if is_denial_context(prior_events):
            return 'denial_context'
        return 'addition'

    if is_override(prompt_text):
        return 'override'
    return 'followup'
