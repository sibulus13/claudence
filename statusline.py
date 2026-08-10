#!/usr/bin/env python3
"""statusline.py — the status bar (port of statusline.ps1).

Runs after each assistant message. Prints session KPIs with rolling-average
trend comparison, then any agent breadcrumb rows from the repo's helm-status.json.

Layout (no history):   OP5 H  6 Prompts  1 Overrides  |  ctx 69%  $3.45  34m
Layout (with history): OP5 H  6 Prompts  1 Overrides/11%  |  ctx 78%  $4.52  3h 54m
Layout (retro needed): !retro  6 Prompts  ...

  N Prompts     prompts this session (cyan)
  N Overrides   /R% rate when history exists; rate colour = trend vs the average
  N Add/Alt     context injected mid-run (yellow)
  N Denied+ctx  tool denied with a reason (red; hidden when 0)
  !retro        friction threshold reached — run /retrospect
  ctx N%        context window used (green < 60, yellow < 80, red + COMPACT above)
  $N.NN         session cost (dim)
  Xm / Xh Ym    elapsed (dim)
  | / - \\      spinner — Claude is currently running (yellow)

Then its own row: ▸ the current topic ×N turns. The label is Claude Code's own task
title (read back from WezTerm), falling back to log-prompt.py's tracked theme.
"""

import json
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'telemetry', 'lib'))

import hooklib as H   # noqa: E402

E = '\033'
RESET = E + '[0m'
CYAN = E + '[36m'
GREEN = E + '[32m'
YELLOW = E + '[33m'
RED = E + '[31m'
DIM = E + '[2m'
GREY = E + '[38;5;240m'      # extra-recessed tone for a stale task row
MAGENTA = E + '[35m'
THEME_WIDTH = 62   # the theme owns its own row, so it only has to fit one line
BLUE = E + '[34m'

TREND_THRESHOLD = 0.10       # 10 percentage points before a rate is called worse/better
CTX_WARN = 60
CTX_CRITICAL = 80
HELM_FRESH_HOURS = 24        # hide the breadcrumb entirely past this age
STALE_HINT_HOURS = 4         # past this, grey the task row and append an age hint
MAX_BLOCKER_ROWS = 3
SPINNER_FRAMES = ('|', '/', '-', '\\')

# A pane title that names no task — Claude Code before it has summarised one, or a
# plain shell. Falling back to the tracked label beats showing "zsh" as the topic.
GENERIC_PANE_TITLES = frozenset(('', 'claude code', 'zsh', 'bash', 'fish', 'sh'))
WEZTERM_TIMEOUT_S = 1        # the row is worth ~10ms, never a stalled status bar

EFFORT_ABBR = {'low': 'L', 'medium': 'M', 'high': 'H',
               'xhigh': 'XH', 'max': 'MX', 'auto': 'A'}
MODEL_TIERS = (('opus', 'OP', MAGENTA), ('sonnet', 'SN', BLUE),
               ('haiku', 'HK', GREEN), ('fable', 'FB', CYAN))


def trend_colour(current, average):
    """Rate colour encodes the trend: red = worse than the average, green = better."""
    diff = current - average
    if diff > TREND_THRESHOLD:
        return RED
    if diff < -TREND_THRESHOLD:
        return GREEN
    return RESET


def get_nested(data, *path):
    node = data
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def resolve_effort(payload):
    """Effort level from the live payload, falling back to settings.json.

    stdin carries either a plain string or a {level: "high"} object.
    """
    value = payload.get('effort')
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict) and value.get('level'):
        return str(value['level'])
    settings = H.read_json(os.path.join(H.CLAUDE_DIR, 'settings.json'), {})
    value = settings.get('effortLevel') if isinstance(settings, dict) else None
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict) and value.get('level'):
        return str(value['level'])
    return None


def model_label(payload):
    """Short tier + version label with an effort suffix, e.g. "OP5 H"."""
    name = get_nested(payload, 'model', 'display_name')
    if not name:
        return ''
    name = str(name)
    lowered = name.lower()
    tier, colour = name[:2].upper(), CYAN
    for needle, code, code_colour in MODEL_TIERS:
        if needle in lowered:
            tier, colour = code, code_colour
            break

    version = ''
    digits = ''
    for char in name:
        if char.isdigit() or (char == '.' and digits):
            digits += char
        elif digits:
            break
    version = digits.rstrip('.')

    effort = resolve_effort(payload)
    suffix = ''
    if effort:
        lowered_effort = str(effort).lower()
        abbr = EFFORT_ABBR.get(lowered_effort, lowered_effort[:2].upper())
        suffix = '%s %s%s' % (DIM, abbr, RESET)
    return '%s%s%s%s%s  ' % (colour, tier, version, RESET, suffix)


def friction_row(state, averages):
    """The prompt/override/addition/denial segment.

    Rates are only shown once there are >= 2 recorded sessions to compare
    against — a rate against no baseline is noise.
    """
    prompts = int(state.get('prompts') or 0)
    counts = {
        'overrides': (int(state.get('overrides') or 0), RED, 'Overrides', 'o_rate'),
        'additions': (int(state.get('additions') or 0), YELLOW, 'Add/Alt', 'a_rate'),
        'denial_contexts': (int(state.get('denial_contexts') or 0), RED, 'Denied+ctx', 'dc_rate'),
    }

    has_history = bool(averages) and int(averages.get('session_count') or 0) >= 2
    out = ''
    for key in ('overrides', 'additions', 'denial_contexts'):
        count, colour, label, rate_key = counts[key]
        if count <= 0:
            continue
        if has_history and prompts > 0:
            rate = count / prompts
            average = float(averages.get('avg_%s' % rate_key) or 0.0)
            rate_col = trend_colour(rate, average)
            out += '  %s%d %s%s/%s%d%%%s' % (colour, count, label, RESET,
                                             rate_col, int(rate * 100), RESET)
        else:
            out += '  %s%d %s%s' % (colour, count, label, RESET)
    return out


def clean_pane_title(title):
    """Claude Code's task title, minus the spinner glyph it prefixes.

    Strips any leading non-alphanumerics rather than enumerating the glyphs, since
    the frame set (✳, the braille cycle) is Claude Code's to change. Returns '' for
    a title that names no task, so the caller can fall back.
    """
    title = ' '.join(str(title or '').split())
    while title and not title[0].isalnum():
        title = title[1:].lstrip()
    return '' if title.lower() in GENERIC_PANE_TITLES else title


def pane_title():
    """The task title Claude Code already generated, read back out of WezTerm.

    The tracked theme label is an extractive one — the first few non-filler words of
    the prompt — so it reads as word salad next to the summary Claude Code writes to
    the terminal title for the same turn ("Taking look open policy macOS imported"
    vs "Fix Claudance tab behavior on macOS"). Prefer the one that was actually
    summarised instead of sharpening the heuristic. '' when not under WezTerm.
    """
    pane = os.environ.get('WEZTERM_PANE')
    if not pane:
        return ''
    try:
        proc = subprocess.run(['wezterm', 'cli', 'list', '--format', 'json'],
                              capture_output=True, text=True, timeout=WEZTERM_TIMEOUT_S)
        panes = json.loads(proc.stdout)
    except Exception:
        return ''      # no wezterm on PATH, no mux, unparseable — the row is optional
    return clean_pane_title(next((p.get('title') for p in panes
                                  if str(p.get('pane_id')) == pane), ''))


def theme_row(state):
    """The topic the session is currently on.

    Label comes from the pane title when there is one; otherwise the theme
    log-prompt.py tracked (pushed on an override or a Jaccard shift below
    THEME_SHIFT_JACCARD). The turn count stays tracked either way, so a
    long-running topic is visibly long-running even as its title is rewritten.
    """
    if not state:
        return ''      # no session, no topic — don't invent one from the pane title
    themes = [t for t in (state.get('themes') or []) if isinstance(t, dict)]
    label = pane_title() or (str(themes[0].get('label') or '').strip() if themes else '')
    if not label:
        return ''
    label = ' '.join(label.split())
    if len(label) > THEME_WIDTH:
        label = label[:THEME_WIDTH - 1].rstrip() + '\u2026'
    turns = int(themes[0].get('turns') or 0) if themes else 0
    suffix = ('%s \u00d7%d%s' % (DIM, turns, RESET)) if turns > 1 else ''
    return '%s\u25b8%s %s%s' % (DIM, RESET, label, suffix)


def meta_row(payload):
    ctx_pct = get_nested(payload, 'context_window', 'used_percentage')
    cost_usd = get_nested(payload, 'cost', 'total_cost_usd')

    parts = []
    if ctx_pct is not None:
        ctx_pct = int(ctx_pct)
        # Zones follow context-rot research and proactive-compact practice:
        # under 60% healthy, 60-79% compact at the next boundary, 80%+ compact now.
        if ctx_pct >= CTX_CRITICAL:
            parts.append('%sctx %d%% COMPACT%s' % (RED, ctx_pct, RESET))
        elif ctx_pct >= CTX_WARN:
            parts.append('%sctx %d%%%s' % (YELLOW, ctx_pct, RESET))
        else:
            parts.append('%sctx %d%%%s' % (GREEN, ctx_pct, RESET))
    if cost_usd is not None:
        parts.append('%s$%.2f%s' % (DIM, float(cost_usd), RESET))
    if not parts:
        return ''
    return '  %s|%s  %s' % (DIM, RESET, '  '.join(parts))


def runtime_row(state):
    started = H.parse_ts(state.get('started_at'))
    if not started:
        return ''
    minutes = int((datetime.now(started.tzinfo) - started).total_seconds() // 60)
    if minutes >= 60:
        return '  %s%dh %dm%s' % (DIM, minutes // 60, minutes % 60, RESET)
    return '  %s%dm%s' % (DIM, minutes, RESET)


def spinner(session_id):
    if not session_id or not os.path.exists(H.running_flag(session_id)):
        return ''
    now = datetime.now()
    frame = SPINNER_FRAMES[(now.second * 4 + now.microsecond // 250000) % len(SPINNER_FRAMES)]
    return '  %s%s%s' % (YELLOW, frame, RESET)


def helm_rows(payload):
    """Agent breadcrumb rows read from the session cwd's helm-status.json.

    stdin carries this session's own cwd, so the breadcrumb is inherently
    per-session/per-tab — it cannot show another project's state.
    """
    cwd = get_nested(payload, 'workspace', 'current_dir') or payload.get('cwd')
    if not cwd:
        return []
    helm = H.read_json(os.path.join(str(cwd), 'helm-status.json'))
    if not isinstance(helm, dict):
        return []

    age_hours = None
    updated = H.parse_ts(helm.get('updatedAt'))
    if updated:
        age_hours = (datetime.now(updated.tzinfo) - updated).total_seconds() / 3600
    if age_hours is not None and age_hours >= HELM_FRESH_HOURS:
        return []

    try:
        columns = int(os.environ.get('COLUMNS') or 100)
    except ValueError:
        columns = 100
    limit = max(20, columns - 4)

    def fit(text):
        text = ' '.join(str(text).split())
        return text if len(text) <= limit else text[:limit - 1] + '…'

    rows = []
    aging = age_hours is not None and age_hours >= STALE_HINT_HOURS
    task_colour = GREY if aging else DIM
    age_suffix = ''
    if aging:
        age = ('%dh' % int(age_hours)) if age_hours < 24 else ('%dd' % int(age_hours / 24))
        age_suffix = ' %s(%s ago)%s' % (GREY, age, RESET)

    if helm.get('currentTask'):
        rows.append('%s▸ %s%s%s' % (task_colour, fit(helm['currentTask']), RESET, age_suffix))

    blockers = [b for b in (helm.get('blockers') or []) if b]
    shown = min(len(blockers), MAX_BLOCKER_ROWS)
    for blocker in blockers[:shown]:
        rows.append('%s⚠ %s%s' % (YELLOW, fit(blocker), RESET))
    if len(blockers) > shown:
        rows.append('%s⚠ +%d more%s' % (YELLOW, len(blockers) - shown, RESET))

    if helm.get('nextPlanned'):
        rows.append('%s→ %s%s' % (DIM, fit(helm['nextPlanned']), RESET))
    return rows


def main():
    payload = H.read_stdin_json() or {}
    session_id = payload.get('session_id')
    session_id = str(session_id) if session_id else None

    state = H.read_json(H.state_file(session_id), {}) if session_id else {}
    if not isinstance(state, dict):
        state = {}

    # Only the status line's payload carries cost and context usage — the Stop hook's
    # does not, which is why cost-ledger.jsonl recorded nulls. Park them in their own
    # file so the read-modify-write on state-<id>.json cannot clobber them.
    if session_id:
        meta = {'ctx_pct': get_nested(payload, 'context_window', 'used_percentage'),
                'cost_usd': get_nested(payload, 'cost', 'total_cost_usd'),
                'ts': H.now_iso()}
        if meta['ctx_pct'] is not None or meta['cost_usd'] is not None:
            H.write_json_compact(H.meta_file(session_id), meta)
    averages = H.read_json(os.path.join(H.TELEMETRY_DIR, 'rolling-averages.json'), {})
    if not isinstance(averages, dict):
        averages = {}

    cumulative = H.read_json(os.path.join(H.TELEMETRY_DIR, 'cumulative.json'), {})
    retro_needed = (isinstance(cumulative, dict)
                    and int(cumulative.get('sessions_since_review') or 0) >= 3
                    and int(cumulative.get('total_score') or 0) >= 6)

    prompts = int(state.get('prompts') or 0)
    # Omit the count rather than show a misleading 0 for a session with no state yet.
    prompt_str = ('%s%d Prompts%s' % (CYAN, prompts, RESET)) if prompts > 0 else ''
    retro_prefix = ('%s!retro%s  ' % (RED, RESET)) if retro_needed else ''

    sys.stdout.write(''.join([
        model_label(payload),
        retro_prefix,
        prompt_str,
        friction_row(state, averages),
        meta_row(payload),
        runtime_row(state),
        spinner(session_id),
    ]) + '\n')

    # The theme is prose of variable length; the row above is fixed-width metrics.
    # Mixing them pushed the line past 80 columns and truncated both. Own row.
    theme = theme_row(state)
    if theme:
        sys.stdout.write(theme + '\n')

    for row in helm_rows(payload):
        sys.stdout.write(row + '\n')


if __name__ == '__main__':
    main()
