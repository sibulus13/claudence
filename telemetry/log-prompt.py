#!/usr/bin/env python3
"""log-prompt.py — UserPromptSubmit hook (port of log-prompt.ps1).

OBJECTIVE — mark when a turn began, so elapsed time and friction are measurable.

Synchronous on purpose: it must finish before Claude responds, so the status bar
is always current for the turn the user just started.

Classifies the prompt via lib/classification.py, appends it to the session
JSONL, and updates the per-session KPI file the status bar reads.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))

import hooklib as H                       # noqa: E402
from classification import classify       # noqa: E402

MAX_PROMPT_EXCERPT = 1000
MAX_THEME_LABEL = 60
MAX_THEMES = 3
THEME_SHIFT_JACCARD = 0.2   # below this overlap with the current theme, call it a new one


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


# Conversational scaffolding. Stripping it matters twice over: the label reads as a
# topic instead of a quote, and the Jaccard shift check below compares subject words
# instead of filler — three differently-phrased prompts about one subject used to
# score as three separate themes.
FILLER = frozenset("""
a an and are as at be been but by can cant could did do does doesnt doing done dont
for from get gets got had has have having how i id ill im in into is isnt it its ive
just let lets like make makes making may me might much must my need needs no nope not
now of off on once one only or other our out over own please put said same see seem
seems shall she should since so some still such sure take than that thats the their
them then there these they this those though through thus to too try under until up
upon us use used using very via want wants was we well were what when where which
while who why will with within would yes yet you your yours
also actually anything else given premise regard regarding rather really something
come each more right because seem seems back here there thing things way ways
ensure likewise moving forward currently current default one two both either
look looks looking taking took keep keeps seeing bit lets
whats theres heres weve youve wasnt arent couldnt wouldnt didnt havent hasnt wont
""".split())

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
    """Content words in order, filler and punctuation dropped, duplicates collapsed."""
    # Drop apostrophes rather than splitting on them, so "don't" becomes "dont" and is
    # caught by FILLER instead of surviving as a stray "don".
    text = text.replace("'", '').replace('’', '')
    out, seen = [], set()
    for raw in ''.join(c if (c.isalnum() or c == '-') else ' ' for c in text).split():
        w = raw.strip('-')
        low = w.lower()
        if len(low) < 3 or low in FILLER or low in seen:
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
    """A condensed topic for the prompt, not the prompt itself.

    Was the verbatim first line, which read as a quote and — because the shift check
    below is a Jaccard over the label — let phrasing differences split one subject
    into several themes.
    """
    first = next((ln.strip() for ln in prompt_text.split('\n') if ln.strip()), '')
    if not first:
        return ''
    words = _salient(first)
    if not words:
        # All filler ("ok, do it then") — keep something rather than lose the theme.
        return first[:MAX_THEME_LABEL].rstrip()
    category = theme_category(words)
    # "build: Build goals screen" says it twice — drop the word the category came from.
    if category and words and words[0].lower().startswith(category):
        words = words[1:] or words
    prefix = ('%s: ' % category) if category else ''
    # Drop whole words rather than cutting one in half — a label ending "categorizati…"
    # is harder to read than one word shorter.
    body = []
    for w in words[:6]:
        if len(prefix) + len(' '.join(body + [w])) > MAX_THEME_LABEL:
            break
        body.append(w)
    return prefix + ' '.join(body) if body else (prefix + words[0])[:MAX_THEME_LABEL]


def _words(text):
    return {w for w in ''.join(c if c.isalnum() else ' ' for c in text.lower()).split()
            if len(w) > 2}


def update_themes(state, classification, label):
    """Keep a reverse-chronological list of the last few distinct topics.

    Zero-token: a direction change is exactly what the classifier already calls
    'override' (and a session's first prompt), so those push a new theme and
    everything else continues the current one. The Jaccard check is the safety
    net for a genuine new scope the classifier did not label as an override.
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
        themes.insert(0, {'label': label, 'ts': H.now_iso(), 'turns': 1})
        del themes[MAX_THEMES:]
    elif themes:
        themes[0]['turns'] = int(themes[0].get('turns', 0)) + 1

    state['themes'] = themes


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

    H.append_jsonl(session_path, {
        'ts': H.now_iso(),
        'session_id': session_id,
        'event': 'prompt',
        'classification': classification,
        'prompt_chars': len(prompt_text),
        'prompt_text': excerpt,
        'cwd': cwd,
    })

    state = load_state(state_path, session_id)
    state['prompts'] = int(state.get('prompts', 0)) + 1
    counter = {'override': 'overrides', 'addition': 'additions',
               'denial_context': 'denial_contexts'}.get(classification)
    if counter:
        state[counter] = int(state.get(counter, 0)) + 1
    state['cwd'] = cwd
    update_themes(state, classification, theme_label(prompt_text))
    H.write_json(state_path, state)

    # Claude is now running — the status bar spinner reads this flag.
    try:
        with open(H.running_flag(session_id), 'w', encoding='utf-8') as fh:
            fh.write(H.now_iso())
    except Exception:
        pass

    cleanup_stale()


if __name__ == '__main__':
    main()
