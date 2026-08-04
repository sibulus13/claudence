#!/usr/bin/env python3
"""analyze-session.py — Stop hook (port of analyze-session.ps1).

Logs the stop event, scores the session's friction, maintains rolling averages
and the cumulative tracker, writes a per-session report, and plays the
completion sound.

Friction scoring per session:
  +3  override              user exited the flow post-stop to redirect
  +1  addition              user queued context while Claude was running
  +1  denial_context        user denied a tool call and gave a reason
  +0  followup              clean next step post-stop
  +0  perm_req approved     not pre-approved but allowed; yields an allow-rule
                            suggestion only, no friction
  +1  perm_req denied       tool blocked and denied; real friction
  +1  perm_repeat approved  approved twice; belongs in the allow list
  +2  perm_repeat denied    blocked and denied again; high friction

Sound: elapsed > 30s OR score >= 5 OR retrospect needed -> ring, else notify.
Retrospection threshold: sessions_since_review >= 3 AND cumulative score >= 6.
"""

import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))

import hooklib as H                            # noqa: E402
from classification import PERM_EVENTS         # noqa: E402

ROLLING_WINDOW = 5
RING_ELAPSED_SECS = 30
RING_SCORE = 5
RETRO_MIN_SESSIONS = 3
RETRO_MIN_SCORE = 6
DING_WINDOW_SECS = 60
NOTE_EXCERPT = 80


def elapsed_seconds(session_id):
    """Seconds since this session's last prompt, or 0 when unknown."""
    try:
        with open(H.start_stamp(session_id), 'r', encoding='utf-8') as fh:
            started = H.parse_ts(fh.read().strip())
    except Exception:
        return 0.0
    if not started:
        return 0.0
    return max(0.0, (datetime.now(started.tzinfo) - started).total_seconds())


def allow_suggestion(req):
    """The permission rule string that would stop this request recurring.

    Bash is special-cased to a command-prefix rule because allowing the bare
    Bash tool would allow every command, which is not what the user consented to.
    """
    tool = req.get('tool')
    preview = req.get('input_preview') or ''
    if tool == 'Bash' and preview:
        return 'Bash(%s:*)' % preview.split()[0]
    if tool and tool != 'unknown':
        return tool
    return None


def main():
    data = H.read_stdin_json() or {}
    session_id = data.get('session_id')
    if not session_id:
        return
    session_id = str(session_id)

    cost = (data.get('cost') or {})
    cost_usd = cost.get('total_cost_usd')
    ctx = (data.get('context_window') or {})
    ctx_pct = ctx.get('used_percentage')
    ctx_pct = int(ctx_pct) if ctx_pct is not None else None

    # Claude has stopped — clear the spinner flag.
    try:
        os.remove(H.running_flag(session_id))
    except Exception:
        pass

    session_path = H.session_file(session_id)
    H.ensure_dir(H.SESSIONS_DIR)

    # Log the stop FIRST, so the next prompt's classifier can see it.
    H.append_jsonl(session_path, {
        'ts': H.now_iso(),
        'session_id': session_id,
        'event': 'stop',
    })

    elapsed = elapsed_seconds(session_id)
    events = H.read_jsonl(session_path)
    if not events:
        return

    prompts = [e for e in events if e.get('event') == 'prompt']
    perm_reqs = [e for e in events if e.get('event') == 'permission_req']
    perm_repeats = [e for e in events if e.get('event') == 'perm_req_repeat']
    tool_dones = [e for e in events if e.get('event') == 'tool_done']
    compacts = [e for e in events if e.get('event') == 'compact']

    # A request followed by a completion of the same tool was approved; one
    # without was denied. Keyed by the request's own timestamp string.
    approved = set()
    for req in perm_reqs + perm_repeats:
        req_ts = H.parse_ts(req.get('ts'))
        for done in tool_dones:
            done_ts = H.parse_ts(done.get('ts'))
            if (done.get('tool') == req.get('tool')
                    and req_ts is not None and done_ts is not None
                    and done_ts > req_ts):
                approved.add(req.get('ts'))
                break

    score = 0
    denied_perm_count = 0
    notes = []
    suggestions = []

    def suggest(req):
        rule = allow_suggestion(req)
        if rule and rule not in suggestions:
            suggestions.append(rule)

    for prompt in prompts:
        excerpt = str(prompt.get('prompt_text') or '')[:NOTE_EXCERPT]
        kind = prompt.get('classification')
        if kind == 'override':
            score += 3
            notes.append('Override (+3): user redirected post-stop - %s' % excerpt)
        elif kind == 'addition':
            score += 1
            notes.append('Add/Alt (+1): queued while running - %s' % excerpt)
        elif kind == 'denial_context':
            score += 1
            notes.append('Denied+ctx (+1): tool denied with reason - %s' % excerpt)
        # first_prompt and followup score 0

    for req in perm_reqs:
        label = '%s - %s' % (req.get('tool'), req.get('input_preview'))
        if req.get('ts') in approved:
            notes.append('Permission approved (suggest allowing): %s' % label)
            suggest(req)
        else:
            denied_perm_count += 1
            score += 1
            notes.append('Permission denied (+1): %s' % label)

    for req in perm_repeats:
        label = '%s - %s' % (req.get('tool'), req.get('input_preview'))
        if req.get('ts') in approved:
            score += 1
            notes.append('Repeat approved (+1, strongly suggest allowing): %s' % label)
            suggest(req)
        else:
            denied_perm_count += 1
            score += 2
            notes.append('Repeat denied (+2): %s blocked again - %s'
                         % (req.get('tool'), req.get('input_preview')))

    # Per-turn breakdown: a turn spans one prompt up to the next prompt.
    turns = []
    for index, prompt in enumerate(prompts):
        turn_start = H.parse_ts(prompt.get('ts'))
        turn_end = (H.parse_ts(prompts[index + 1].get('ts'))
                    if index + 1 < len(prompts) else None)

        turn_events = []
        for event in events:
            event_ts = H.parse_ts(event.get('ts'))
            if event_ts is None or turn_start is None or event_ts <= turn_start:
                continue
            if turn_end is not None and event_ts >= turn_end:
                continue
            turn_events.append(event)

        decisions = [{
            'tool': e.get('tool'),
            'preview': e.get('input_preview'),
            'repeat': e.get('event') == 'perm_req_repeat',
            'decision': 'approve' if e.get('ts') in approved else 'deny',
        } for e in turn_events if e.get('event') in PERM_EVENTS]

        turns.append({
            'classification': prompt.get('classification'),
            'prompt_chars': prompt.get('prompt_chars'),
            'tool_calls': len([e for e in turn_events if e.get('event') == 'tool_done']),
            'decisions': decisions,
        })

    cwd = (prompts[0].get('cwd') if prompts else '') or ''
    short_id = session_id[:8]
    overrides = len([p for p in prompts if p.get('classification') == 'override'])
    additions = len([p for p in prompts if p.get('classification') == 'addition'])
    denial_ctxs = len([p for p in prompts if p.get('classification') == 'denial_context'])

    H.ensure_dir(H.REPORTS_DIR)
    H.write_json(os.path.join(H.REPORTS_DIR, '%s.json' % short_id), {
        'ts': H.now_iso(),
        'session_id': session_id,
        'cwd': cwd,
        'elapsed_sec': round(elapsed, 1),
        'cost_usd': cost_usd,
        'ctx_pct': ctx_pct,
        'score': score,
        'total_events': len(events),
        'prompt_count': len(prompts),
        'overrides': overrides,
        'additions': additions,
        'denial_ctx_count': denial_ctxs,
        'perm_req_count': len(perm_reqs),
        'perm_repeat_count': len(perm_repeats),
        'compact_count': len(compacts),
        'transcript_path': os.path.join(H.CLAUDE_DIR, 'history.jsonl'),
        'session_jsonl': session_path,
        'friction_notes': notes,
        'allow_suggestions': suggestions,
        'turns': turns,
    })

    H.append_jsonl(os.path.join(H.TELEMETRY_DIR, 'cost-ledger.jsonl'), {
        'ts': H.now_iso(),
        'session_id': short_id,
        'cwd': cwd,
        'cost_usd': round(cost_usd, 4) if cost_usd is not None else None,
        'ctx_pct': ctx_pct,
        'elapsed_sec': round(elapsed, 1),
        'prompt_count': len(prompts),
        'score': score,
    })

    # Rolling averages over the last ROLLING_WINDOW sessions — the baseline the
    # status bar compares this session's rates against.
    if prompts:
        count = len(prompts)
        rates = {
            'o_rate': round(overrides / count, 4),
            'a_rate': round(additions / count, 4),
            'dc_rate': round(denial_ctxs / count, 4),
            'b_rate': round(denied_perm_count / count, 4),
        }
        avg_path = os.path.join(H.TELEMETRY_DIR, 'rolling-averages.json')
        avg = H.read_json(avg_path)
        if not isinstance(avg, dict):
            avg = {'window': ROLLING_WINDOW, 'sessions': []}
        sessions = [s for s in (avg.get('sessions') or []) if isinstance(s, dict)]
        entry = {
            'id': short_id,
            'ts': H.now_iso(),
            'cwd': cwd,
            'prompts': count,
            'overrides': overrides,
            'additions': additions,
            'denial_ctxs': denial_ctxs,
            'perm_reqs': len(perm_reqs),
            'perm_repeats': len(perm_repeats),
            'cost_usd': round(cost_usd, 4) if cost_usd is not None else None,
            'elapsed_sec': round(elapsed, 1),
        }
        entry.update(rates)
        sessions.append(entry)
        sessions = sessions[-ROLLING_WINDOW:]

        avg['window'] = ROLLING_WINDOW
        avg['sessions'] = sessions
        for key in ('o_rate', 'a_rate', 'dc_rate', 'b_rate'):
            total = sum(float(s.get(key) or 0) for s in sessions)
            avg['avg_%s' % key] = round(total / len(sessions), 4)
        avg['session_count'] = len(sessions)
        H.write_json(avg_path, avg)

    cumulative_path = os.path.join(H.TELEMETRY_DIR, 'cumulative.json')
    cum = H.read_json(cumulative_path)
    if not isinstance(cum, dict):
        cum = {'total_score': 0, 'sessions_since_review': 0, 'last_review_ts': ''}
    if score > 0:
        cum['total_score'] = int(cum.get('total_score', 0)) + score
        cum['sessions_since_review'] = int(cum.get('sessions_since_review', 0)) + 1
    H.write_json(cumulative_path, cum)

    retrospect_needed = (int(cum.get('sessions_since_review', 0)) >= RETRO_MIN_SESSIONS
                         and int(cum.get('total_score', 0)) >= RETRO_MIN_SCORE)
    play_ring = (elapsed > RING_ELAPSED_SECS or score >= RING_SCORE or retrospect_needed)

    # One Stop chime per minute across ALL sessions (shared on-disk stamp), so
    # several sessions finishing together don't stack sounds. The visual flags
    # from notify-attention.py are not throttled, so every finished session is
    # still visible on the tab bar.
    stamp = os.path.join(H.WORKSPACES_DIR, '.last-ding-stop')
    if H.throttle(stamp, DING_WINDOW_SECS):
        time.sleep(0.4)
        H.play_sound('ring-half' if play_ring else 'notify-half')

    if retrospect_needed:
        cum['total_score'] = 0
        cum['sessions_since_review'] = 0
        cum['last_review_ts'] = H.now_iso()
        H.write_json(cumulative_path, cum)

        suggest_str = (' Suggested allow rules: %s.' % ', '.join(suggestions)) if suggestions else ''
        sys.stdout.write(json.dumps({
            'systemMessage': (
                'Friction has accumulated across recent sessions (score: %d this session).'
                '%s Run /retrospect to review friction points, update allow rules, and '
                'refresh memory context.' % (score, suggest_str)
            )
        }, separators=(',', ':')))


if __name__ == '__main__':
    main()
