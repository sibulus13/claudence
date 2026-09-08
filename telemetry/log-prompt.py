#!/usr/bin/env python3
"""log-prompt.py — UserPromptSubmit hook (port of log-prompt.ps1).

OBJECTIVE — mark when a turn began, so elapsed time and friction are measurable.

Synchronous on purpose: it must finish before Claude responds, so the status bar
is always current for the turn the user just started.

Classifies the prompt via lib/classification.py, appends it to the session
JSONL, and updates the per-session KPI file the status bar reads.
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))

import hooklib as H                       # noqa: E402
from classification import classify       # noqa: E402

MAX_PROMPT_EXCERPT = 1000
MAX_THEME_LABEL = 60
MAX_THEMES = 3
THEME_SHIFT_JACCARD = 0.2   # below this overlap with the current theme, call it a new one
REFRESH_INTERVAL_TURNS = 5  # re-summarize at turn 1, then every 5th — bounds model-call cost


def load_state(path, session_id):
    state = H.read_json(path)
    if not isinstance(state, dict) or state.get('session_id') != session_id:
        state = {
            'session_id': session_id,
            'prompts': 0,
            'overrides': 0,
            'additions': 0,
            'denial_contexts': 0,
            'perm_reqs': 0,
            'perm_repeats': 0,
            'started_at': H.now_iso(),
        }
    return state


# Conversational scaffolding, shared via hooklib.FILLER — used here to pick the
# category prefix and to keep the Jaccard shift check comparing subject words
# instead of filler, never to decide what's actually shown (see theme_label below).

# Leading verb → a coarse category, so the row says what kind of work it is before
# it says what it is about. Deliberately small; a taxonomy nobody maintains is worse
# than none. First match on the first few salient words wins.
CATEGORIES = (
    ('fix',     ('fix', 'fixes', 'broken', 'break', 'breaking', 'bug', 'wrong', 'fails',
                 'failing', 'error', 'issue', 'repair')),
    ('check',   ('check', 'analyze', 'analyse', 'verify', 'confirm', 'audit', 'inspect',
                 'investigate', 'smoke', 'test', 'tests', 'testing', 'validate')),
    ('build',   ('add', 'build', 'create', 'implement', 'write', 'set', 'setup', 'install',
                 'generate', 'produce')),
    ('change',  ('change', 'update', 'replace', 'refactor', 'rename', 'move', 'split',
                 'merge', 'consolidate', 'clean', 'scrub', 'remove', 'delete')),
    ('ship',    ('commit', 'push', 'deploy', 'publish', 'release', 'remote', 'branch')),
    ('explain', ('explain', 'what', 'why', 'which', 'who', 'describe', 'summarize',
                 'summarise', 'compare', 'propose', 'recommend', 'link', 'show')),
)


def _salient(text):
    """Content words in order, filler and punctuation dropped, duplicates collapsed.

    Used only to pick theme_category()'s prefix — never to build the displayed label,
    which needs the original words in their original order to read as a sentence.
    """
    # Drop apostrophes rather than splitting on them, so "don't" becomes "dont" and is
    # caught by FILLER instead of surviving as a stray "don".
    text = text.replace("'", '').replace('’', '')
    out, seen = [], set()
    for raw in ''.join(c if (c.isalnum() or c == '-') else ' ' for c in text).split():
        w = raw.strip('-')
        low = w.lower()
        if len(low) < 3 or low in H.FILLER or low in seen:
            continue
        seen.add(low)
        out.append(w)
    return out


def theme_category(words):
    """Coarse kind-of-work, from the first few salient words. '' when nothing matches."""
    head = {w.lower() for w in words[:6]}
    for name, triggers in CATEGORIES:
        if head & set(triggers):
            return name
    return ''


def theme_label(prompt_text):
    """A condensed topic for the prompt — a truncated, readable clause, not word salad.

    Used to strip filler and rejoin only the salient words in whatever order they
    survived filtering ("mind probably skipping session start reusing"), which reads
    as scrambled keywords rather than a sentence a person can parse at a glance. Now
    keeps the prompt's own words and order intact — filler-stripping still decides the
    category prefix (via _salient/theme_category) and the Jaccard shift check's
    vocabulary (via _words), but never what actually gets displayed.
    """
    first = next((ln.strip() for ln in prompt_text.split('\n') if ln.strip()), '')
    if not first:
        return ''
    words = _salient(first)
    category = theme_category(words) if words else ''
    prefix = ('%s: ' % category) if category else ''

    body = first
    # "build: Build the goals screen" says it twice — drop the leading word the
    # category came from so the prefix carries that meaning instead. Natural casing
    # is kept rather than forced, so "build: the goals screen" reads as a phrase
    # rather than a sentence restarting mid-label.
    if category:
        m = re.match(r'^(\W*)(\w+)(.*)$', body, re.DOTALL)
        if m and m.group(2).lower().startswith(category):
            rest = m.group(3).lstrip(' ,:;-')
            if rest:
                body = rest

    budget = MAX_THEME_LABEL - len(prefix)
    if len(body) > budget:
        # Cut at the last whole word inside the budget — a label ending "categorizati…"
        # reads worse than one word shorter, and a half-word ending is not a sentence.
        cut = body[:budget]
        cut = cut.rsplit(' ', 1)[0] if ' ' in cut else cut
        body = cut.rstrip(' .,;:!?') + '…'
    return prefix + body if body else first[:MAX_THEME_LABEL].rstrip()


def _words(text):
    """Salient words only, for the Jaccard shift check — never for display.

    Without filler exclusion, two unrelated sentences already share several length>2
    filler words ("the", "and", "for"), which would inflate their apparent overlap and
    make the shift check less sensitive exactly when theme_label() started keeping
    filler words in the DISPLAYED text. The comparison must stay on subject words
    regardless of what the label looks like.
    """
    return H.salient_words(text)


def update_themes(state, classification, label, event_ts):
    """Keep a reverse-chronological list of the last few distinct topics.

    Zero-token: a direction change is exactly what the classifier already calls
    'override' (and a session's first prompt), so those push a new theme and
    everything else continues the current one. The Jaccard check is the safety
    net for a genuine new scope the classifier did not label as an override.

    `event_ts` is the SAME timestamp already written for this prompt's own JSONL
    event, not a fresh H.now_iso() call — summarize-theme.py gathers every prompt
    at or after a theme's 'ts', so a brand-new theme's start time must exactly
    match its own first prompt's event time or that prompt gets excluded from its
    own summary.
    """
    themes = [t for t in (state.get('themes') or []) if t]

    is_new = classification in ('override', 'first_prompt') or not themes

    if (not is_new and classification != 'addition' and themes and label):
        current = _words(str(themes[0].get('label', '')))
        incoming = _words(label)
        if current and incoming:
            union = current | incoming
            jaccard = len(current & incoming) / len(union) if union else 0
            if jaccard < THEME_SHIFT_JACCARD:
                is_new = True

    if is_new and label:
        themes.insert(0, {'label': label, 'ts': event_ts, 'turns': 1})
        del themes[MAX_THEMES:]
    elif themes:
        themes[0]['turns'] = int(themes[0].get('turns', 0)) + 1

    state['themes'] = themes

    if not themes:
        return None
    turns = int(themes[0].get('turns', 0))
    if turns == 1 or turns % REFRESH_INTERVAL_TURNS == 0:
        return themes[0].get('ts')
    return None


def spawn_theme_summary(session_id, theme_ts):
    """Fire the async semantic-intent summarizer, detached, never waited on.

    A few ms to fork+exec — nothing here can slow this synchronous hook down.
    The child does the actual (multi-second) model call and writes its result
    back into state-<session_id>.json on its own schedule.

    CLAUDENCE_SILENT=1 (the test suite's existing "no external/audible side
    effects" convention, already used by hooklib.play_sound) skips this too —
    a test run must never make a real `claude` API call.
    """
    if not theme_ts or os.environ.get('CLAUDENCE_SILENT') == '1':
        return
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'summarize-theme.py')
    try:
        subprocess.Popen(
            [sys.executable or 'python3', script, session_id, theme_ts],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            start_new_session=True)
    except Exception:
        pass


def cleanup_stale():
    """Drop per-session files that outlived their session.

    State files older than 7 days belong to ended sessions; running flags older
    than 6 hours belong to crashed ones, and a stale flag means a status-bar
    spinner that never stops.
    """
    import time
    now = time.time()
    try:
        for name in os.listdir(H.TELEMETRY_DIR):
            path = os.path.join(H.TELEMETRY_DIR, name)
            if not os.path.isfile(path):
                continue
            age = now - os.path.getmtime(path)
            expired = ((name.startswith('state-') and name.endswith('.json') and age > 7 * 86400)
                       or (name.startswith('running-') and name.endswith('.flag') and age > 6 * 3600)
                       or (name.startswith('start-') and name.endswith('.stamp') and age > 6 * 3600))
            if expired:
                os.remove(path)
    except Exception:
        pass


def main():
    data = H.read_stdin_json() or {}
    session_id = str(data.get('session_id') or 'unknown')
    prompt_text = str(data.get('prompt') or '')
    cwd = str(data.get('cwd') or os.environ.get('PWD') or os.getcwd())

    session_path = H.session_file(session_id)
    state_path = H.state_file(session_id)
    H.ensure_dir(H.SESSIONS_DIR)

    # Turn-start marker for the Stop hook's elapsed-time sound decision.
    try:
        with open(H.start_stamp(session_id), 'w', encoding='utf-8') as fh:
            fh.write(H.now_iso())
    except Exception:
        pass

    prior = H.read_jsonl(session_path)
    classification = classify(prompt_text, prior)

    excerpt = prompt_text
    if len(excerpt) > MAX_PROMPT_EXCERPT:
        excerpt = excerpt[:MAX_PROMPT_EXCERPT] + '...'

    # Captured once and reused for both the JSONL event and a brand-new theme's own
    # 'ts' below — two separate H.now_iso() calls a few lines apart would otherwise
    # make the theme's start time strictly LATER than its own first prompt's event
    # time, so summarize-theme.py's "events at or after theme_ts" filter excluded
    # exactly the one prompt that started the theme. Same instant, same string.
    event_ts = H.now_iso()
    H.append_jsonl(session_path, {
        'ts': event_ts,
        'session_id': session_id,
        'event': 'prompt',
        'classification': classification,
        'prompt_chars': len(prompt_text),
        'prompt_text': excerpt,
        'cwd': cwd,
    })

    state = load_state(state_path, session_id)
    # A task-notification/cross-session-message delivery is logged for provenance
    # above, but it is not a user prompt: it must not inflate the visible prompt
    # count, score as override/addition friction, or overwrite the status bar's
    # topic rows with notification body text instead of the real conversation.
    refresh_ts = None
    if classification != 'system_notification':
        state['prompts'] = int(state.get('prompts', 0)) + 1
        counter = {'override': 'overrides', 'addition': 'additions',
                   'denial_context': 'denial_contexts'}.get(classification)
        if counter:
            state[counter] = int(state.get(counter, 0)) + 1
        refresh_ts = update_themes(state, classification, theme_label(prompt_text), event_ts)
    state['cwd'] = cwd
    H.write_json(state_path, state)

    if refresh_ts:
        spawn_theme_summary(session_id, refresh_ts)

    # Claude is now running — the status bar spinner reads this flag.
    try:
        with open(H.running_flag(session_id), 'w', encoding='utf-8') as fh:
            fh.write(H.now_iso())
    except Exception:
        pass

    cleanup_stale()


if __name__ == '__main__':
    main()
