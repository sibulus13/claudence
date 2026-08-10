#!/usr/bin/env python3
"""hooks.test.py — integration tests for the macOS hook ports.

Each hook is run the way Claude Code runs it — a subprocess fed a JSON payload on
stdin — against a throwaway HOME, then the files it wrote are asserted. This is
the suite that would have caught the two upstream wiring bugs (the permission
event name, and KPIs written to a file nothing reads), because it checks what
lands on disk rather than what the code intends to write.

  ./tests/hooks.test.py     exit 0 = all pass, 1 = a failure
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable or '/usr/bin/python3'

# Imported for its pure helpers only — the rest of the suite drives hooks as
# subprocesses. hooklib is path constants at import time, so this touches nothing.
sys.path.insert(0, REPO)
import statusline   # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


def check(name, actual, expected):
    global PASS, FAIL
    if actual == expected:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append('%s\n    expected %r\n    got      %r' % (name, expected, actual))


def check_true(name, condition, detail=''):
    check(name + (' — ' + detail if detail and not condition else ''), bool(condition), True)


class Sandbox(object):
    """A throwaway HOME so hooks write into a temp tree, not the real ~/.claude.

    hooklib resolves every path from expanduser('~'), which honours $HOME, so
    overriding it in the child environment is enough to fully isolate a run.
    """

    def __init__(self):
        self.home = tempfile.mkdtemp(prefix='claudence-test-')
        os.makedirs(os.path.join(self.home, '.claude'), exist_ok=True)

    def close(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def path(self, *parts):
        return os.path.join(self.home, '.claude', *parts)

    def run(self, script, payload=None, args=(), env=None):
        """Run a hook and return (exit_code, stdout)."""
        child_env = dict(os.environ)
        child_env['HOME'] = self.home
        child_env['CLAUDENCE_SILENT'] = '1'
        child_env.pop('WEZTERM_PANE', None)
        if env:
            child_env.update(env)
        proc = subprocess.run(
            [PY, os.path.join(REPO, script)] + list(args),
            input=json.dumps(payload) if payload is not None else '',
            env=child_env, capture_output=True, text=True, timeout=60,
        )
        if proc.returncode != 0:
            FAILURES.append('%s exited %d\n    stderr: %s'
                            % (script, proc.returncode, proc.stderr.strip()[:600]))
            global FAIL
            FAIL += 1
        return proc.returncode, proc.stdout

    def events(self, session_id):
        path = self.path('telemetry', 'sessions', '%s.jsonl' % session_id)
        if not os.path.exists(path):
            return []
        with open(path, 'r', encoding='utf-8') as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def json_at(self, *parts):
        path = self.path(*parts)
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as fh:
            return json.load(fh)


SID = 'aabbccdd-1111-2222-3333-444455556666'
SID2 = 'bbccddee-1111-2222-3333-444455556666'

# ── log-prompt: classification, KPI state, run flag ──────────────────────────
box = Sandbox()
try:
    box.run('telemetry/log-prompt.py',
            {'session_id': SID, 'prompt': 'Build the goals screen', 'cwd': '/Users/x/repo/app'})
    events = box.events(SID)
    check('log-prompt: one event appended', len(events), 1)
    check('log-prompt: event is a prompt', events[0].get('event'), 'prompt')
    check('log-prompt: first prompt classifies as first_prompt',
          events[0].get('classification'), 'first_prompt')
    check('log-prompt: prompt_chars recorded', events[0].get('prompt_chars'), 22)
    check('log-prompt: cwd recorded', events[0].get('cwd'), '/Users/x/repo/app')

    state = box.json_at('telemetry', 'state-%s.json' % SID)
    check('log-prompt: state prompts=1', state.get('prompts'), 1)
    check('log-prompt: state overrides=0', state.get('overrides'), 0)
    # The label is a condensed topic, not the prompt verbatim: filler is dropped and a
    # leading verb becomes a category, so the status bar reads as a subject not a quote.
    check('log-prompt: theme condensed to a categorised topic',
          state['themes'][0]['label'], 'build: goals screen')
    check_true('log-prompt: running flag written',
               os.path.exists(box.path('telemetry', 'running-%s.flag' % SID)))
    check_true('log-prompt: turn-start stamp written (per-session, not shared)',
               os.path.exists(box.path('telemetry', 'start-%s.stamp' % SID)))

    # A stop, then override language -> override, and the counter increments.
    box.run('telemetry/analyze-session.py', {'session_id': SID})
    box.run('telemetry/log-prompt.py',
            {'session_id': SID, 'prompt': "Actually, scrap that and use a table instead",
             'cwd': '/Users/x/repo/app'})
    events = box.events(SID)
    check('log-prompt: post-stop override language classifies as override',
          events[-1].get('classification'), 'override')
    state = box.json_at('telemetry', 'state-%s.json' % SID)
    check('log-prompt: state overrides=1', state.get('overrides'), 1)
    check('log-prompt: state prompts=2', state.get('prompts'), 2)
    check('log-prompt: override pushes a new theme', len(state['themes']), 2)
finally:
    box.close()

# A new subject phrased as a followup must still split the theme. These two prompts
# shared only "taking" and "look" — conversational scaffolding — which scored exactly
# at THEME_SHIFT_JACCARD and fused two unrelated topics into one row reading "×2".
box = Sandbox()
try:
    box.run('telemetry/log-prompt.py',
            {'session_id': SID, 'cwd': '/Users/x/repo/app',
             'prompt': 'Taking a look at our open policy, the imported version does not '
                       'open in a new tab but a new terminal'})
    box.run('telemetry/analyze-session.py', {'session_id': SID})   # a turn completed
    box.run('telemetry/log-prompt.py',
            {'session_id': SID, 'cwd': '/Users/x/repo/app',
             'prompt': 'Also taking a look at the status bar summary section, it is not '
                       'reflective of what we have been working on'})
    state = box.json_at('telemetry', 'state-%s.json' % SID)
    check('log-prompt: scaffolding is not subject — a new topic splits', len(state['themes']), 2)
    check('log-prompt: label carries the subject, not the scaffolding',
          state['themes'][0]['label'], 'status bar summary section reflective working')
finally:
    box.close()

# ── log-permission: first vs repeat, and the state file the status bar reads ──
box = Sandbox()
try:
    payload = {'session_id': SID, 'tool_name': 'Bash',
               'tool_input': {'command': 'rm -rf build && pnpm build'}}
    box.run('telemetry/log-permission.py', payload)
    events = box.events(SID)
    check('log-permission: first request uses the name every reader looks for',
          events[0].get('event'), 'permission_req')
    check('log-permission: tool recorded', events[0].get('tool'), 'Bash')
    check('log-permission: command preview recorded',
          events[0].get('input_preview'), 'rm -rf build && pnpm build')

    box.run('telemetry/log-permission.py', payload)
    events = box.events(SID)
    check('log-permission: same tool again -> perm_req_repeat',
          events[1].get('event'), 'perm_req_repeat')

    state = box.json_at('telemetry', 'state-%s.json' % SID)
    check_true('log-permission: KPIs land in state-<sid>.json, not current-session.json',
               state is not None)
    check('log-permission: perm_reqs=1', state.get('perm_reqs'), 1)
    check('log-permission: perm_repeats=1', state.get('perm_repeats'), 1)
    check_true('log-permission: no orphan current-session.json is written',
               not os.path.exists(box.path('telemetry', 'current-session.json')))

    # A different tool starts over at first-time.
    box.run('telemetry/log-permission.py',
            {'session_id': SID, 'tool_name': 'WebFetch', 'tool_input': {'url': 'https://x'}})
    events = box.events(SID)
    check('log-permission: a different tool is a first request',
          events[2].get('event'), 'permission_req')
    check('log-permission: unknown input field -> empty preview',
          events[2].get('input_preview'), '')
finally:
    box.close()

# ── log-tool-done / record-compact ───────────────────────────────────────────
box = Sandbox()
try:
    box.run('telemetry/log-tool-done.py',
            {'session_id': SID, 'tool_name': 'Read', 'tool_input': {'file_path': '/tmp/a.ts'}})
    events = box.events(SID)
    check('log-tool-done: event appended', events[0].get('event'), 'tool_done')
    check('log-tool-done: file_path used as the preview',
          events[0].get('input_preview'), '/tmp/a.ts')

    box.run('telemetry/record-compact.py',
            {'session_id': SID, 'summary': 'Ported the hooks', 'trigger': 'auto'})
    events = box.events(SID)
    check('record-compact: event appended', events[1].get('event'), 'compact')
    check('record-compact: trigger recorded', events[1].get('trigger'), 'auto')
    check('record-compact: summary preserved', events[1].get('summary'), 'Ported the hooks')

    # Empty stdin must be a clean no-op, never a traceback: Claude Code surfaces a
    # non-zero hook exit to the user on every single turn.
    code, _ = box.run('telemetry/log-tool-done.py', None)
    check('hooks: empty stdin exits 0', code, 0)
finally:
    box.close()

# ── analyze-session: scoring, report, rolling averages, cumulative ───────────
box = Sandbox()
try:
    # first_prompt(0) + override(+3) + addition(+1) + denied Bash permission(+1) = 5
    box.run('telemetry/log-prompt.py', {'session_id': SID, 'prompt': 'Start the port',
                                        'cwd': '/Users/x/repo/app'})
    box.run('telemetry/analyze-session.py', {'session_id': SID})
    box.run('telemetry/log-prompt.py', {'session_id': SID,
                                        'prompt': 'Actually use python3 instead',
                                        'cwd': '/Users/x/repo/app'})
    box.run('telemetry/log-permission.py', {'session_id': SID, 'tool_name': 'Bash',
                                            'tool_input': {'command': 'rm -rf /'}})
    box.run('telemetry/log-prompt.py', {'session_id': SID,
                                        'prompt': 'Also do not run destructive commands',
                                        'cwd': '/Users/x/repo/app'})
    box.run('telemetry/analyze-session.py',
            {'session_id': SID, 'cost': {'total_cost_usd': 1.2345},
             'context_window': {'used_percentage': 42}})

    report = box.json_at('telemetry', 'reports', '%s.json' % SID[:8])
    check_true('analyze-session: report written', report is not None)
    check('analyze-session: score = override(3) + denial_context(1) + denied perm(1)',
          report.get('score'), 5)
    check('analyze-session: overrides counted', report.get('overrides'), 1)
    check('analyze-session: denial_context counted', report.get('denial_ctx_count'), 1)
    check('analyze-session: permission request counted', report.get('perm_req_count'), 1)
    check('analyze-session: cost recorded', report.get('cost_usd'), 1.2345)
    check('analyze-session: ctx recorded', report.get('ctx_pct'), 42)
    check('analyze-session: prompts counted', report.get('prompt_count'), 3)
    # A DENIED request yields no allow rule: the user said no, so suggesting they
    # pre-approve it would invert their decision. Only approvals become rules.
    check('analyze-session: a denied request yields no allow rule',
          report.get('allow_suggestions'), [])
    check('analyze-session: one turn per prompt', len(report.get('turns') or []), 3)
    check_true('analyze-session: the denied request appears as a deny decision',
               any(d.get('decision') == 'deny'
                   for turn in report['turns'] for d in turn['decisions']))
    check_true('analyze-session: running flag cleared',
               not os.path.exists(box.path('telemetry', 'running-%s.flag' % SID)))
    check('analyze-session: stop events appended', len(
        [e for e in box.events(SID) if e.get('event') == 'stop']), 2)

    averages = box.json_at('telemetry', 'rolling-averages.json')
    check('analyze-session: rolling averages record both sessions',
          averages.get('session_count'), 2)
    check('analyze-session: override rate averaged over the window',
          averages.get('avg_o_rate'), round((0.0 + round(1 / 3, 4)) / 2, 4))

    cumulative = box.json_at('telemetry', 'cumulative.json')
    check('analyze-session: cumulative score accumulated',
          cumulative.get('total_score'), 5)
    check('analyze-session: only scoring sessions count toward review',
          cumulative.get('sessions_since_review'), 1)

    ledger = os.path.join(box.path('telemetry', 'cost-ledger.jsonl'))
    check_true('analyze-session: cost ledger appended', os.path.exists(ledger))

    # The real Stop payload carries neither cost nor context — only the status line
    # sees them. 125 ledger rows were written with both null before the fallback
    # existed, so assert the path Claude Code actually takes, not the seeded one.
    box.run('telemetry/log-prompt.py', {'session_id': SID2, 'prompt': 'go',
                                        'cwd': '/Users/x/repo/app'})
    box.run('statusline.py', {'session_id': SID2, 'cost': {'total_cost_usd': 3.5},
                              'context_window': {'used_percentage': 71}})
    box.run('telemetry/analyze-session.py', {'session_id': SID2})
    fallback = box.json_at('telemetry', 'reports', '%s.json' % SID2[:8])
    check('analyze-session: cost recovered from the status line', fallback.get('cost_usd'), 3.5)
    check('analyze-session: ctx recovered from the status line', fallback.get('ctx_pct'), 71)

    # An approved request (a later tool_done for the same tool) scores 0 and
    # becomes a suggestion instead.
    box2 = Sandbox()
    try:
        box2.run('telemetry/log-prompt.py', {'session_id': SID, 'prompt': 'go',
                                             'cwd': '/Users/x/repo/app'})
        box2.run('telemetry/log-permission.py',
                 {'session_id': SID, 'tool_name': 'Bash', 'tool_input': {'command': 'pnpm test'}})
        box2.run('telemetry/log-tool-done.py',
                 {'session_id': SID, 'tool_name': 'Bash', 'tool_input': {'command': 'pnpm test'}})
        box2.run('telemetry/analyze-session.py', {'session_id': SID})
        report2 = box2.json_at('telemetry', 'reports', '%s.json' % SID[:8])
        check('analyze-session: an approved request adds no friction',
              report2.get('score'), 0)
        check('analyze-session: an approved request yields an allow suggestion',
              report2.get('allow_suggestions'), ['Bash(pnpm:*)'])
    finally:
        box2.close()

    # Missing session_id is a no-op, not a crash.
    code, _ = box.run('telemetry/analyze-session.py', {'cost': {'total_cost_usd': 1}})
    check('analyze-session: no session_id exits 0', code, 0)
finally:
    box.close()

# ── notify-attention: the flag file terminal.lua's tab bar reads ─────────────
box = Sandbox()
try:
    box.run('telemetry/notify-attention.py',
            {'session_id': SID, 'cwd': '/Users/x/repo/app'},
            args=['--reason', 'stop', '--silent'], env={'WEZTERM_PANE': '7'})
    flag = box.json_at('workspaces', 'attention', 'pane-7.json')
    check_true('notify-attention: flag written for the pane', flag is not None)
    check('notify-attention: cwd recorded', flag.get('cwd'), '/Users/x/repo/app')
    check('notify-attention: repo label is the cwd leaf', flag.get('repo'), 'app')
    check('notify-attention: pane recorded as a number', flag.get('pane'), 7)
    check('notify-attention: reason recorded', flag.get('reason'), 'stop')
    check_true('notify-attention: timestamp recorded', isinstance(flag.get('ts'), int))

    # The flag must be BOM-less compact JSON — wezterm.json_parse chokes on a BOM.
    with open(box.path('workspaces', 'attention', 'pane-7.json'), 'rb') as fh:
        raw = fh.read()
    check_true('notify-attention: flag has no UTF-8 BOM', not raw.startswith(b'\xef\xbb\xbf'))
    check_true('notify-attention: flag is compact JSON', b', ' not in raw)

    # No pane -> headless agent -> nothing to navigate to, so no flag.
    box.run('telemetry/notify-attention.py',
            {'session_id': SID, 'cwd': '/Users/x/repo/other'},
            args=['--reason', 'stop', '--silent'])
    check_true('notify-attention: no WEZTERM_PANE -> no flag written',
               box.json_at('workspaces', 'attention', 'pane-None.json') is None
               and len(os.listdir(box.path('workspaces', 'attention'))) == 1)

    # A temp/scratchpad cwd must not light a tab.
    box.run('telemetry/notify-attention.py',
            {'session_id': SID, 'cwd': '/private/var/folders/ab/cd/T/scratch'},
            args=['--reason', 'stop', '--silent'], env={'WEZTERM_PANE': '9'})
    check_true('notify-attention: a macOS temp cwd is not flagged',
               box.json_at('workspaces', 'attention', 'pane-9.json') is None)
    box.run('telemetry/notify-attention.py',
            {'session_id': SID, 'cwd': '/tmp/whatever'},
            args=['--reason', 'stop', '--silent'], env={'WEZTERM_PANE': '10'})
    check_true('notify-attention: /tmp cwd is not flagged',
               box.json_at('workspaces', 'attention', 'pane-10.json') is None)
finally:
    box.close()

# ── record-pane-session: the pane -> conversation binding for restore ────────
box = Sandbox()
try:
    box.run('scripts/record-pane-session.py',
            {'session_id': SID, 'cwd': '/Users/x/repo/app/'},
            env={'WEZTERM_PANE': '3'})
    binding = box.json_at('workspaces', 'pane-sessions', 'pane-3.json')
    check_true('record-pane-session: binding written', binding is not None)
    check('record-pane-session: session id recorded', binding.get('session'), SID)
    check('record-pane-session: trailing slash normalised off',
          binding.get('cwd'), '/Users/x/repo/app')
    check('record-pane-session: pane recorded', binding.get('pane'), 3)

    box.run('scripts/record-pane-session.py', {'session_id': SID}, env={})
    check_true('record-pane-session: no pane -> nothing written',
               len(os.listdir(box.path('workspaces', 'pane-sessions'))) == 1)
finally:
    box.close()

# ── statusline: the segments the bar is supposed to render ───────────────────
box = Sandbox()
try:
    box.run('telemetry/log-prompt.py', {'session_id': SID, 'prompt': 'go',
                                        'cwd': '/Users/x/repo/app'})
    box.run('telemetry/analyze-session.py', {'session_id': SID})
    box.run('telemetry/log-prompt.py', {'session_id': SID,
                                        'prompt': 'Actually do it differently instead',
                                        'cwd': '/Users/x/repo/app'})
    _code, out = box.run('statusline.py', {
        'session_id': SID,
        'model': {'display_name': 'Claude Opus 5'},
        'effort': {'level': 'high'},
        'cost': {'total_cost_usd': 4.5678},
        'context_window': {'used_percentage': 78},
        'workspace': {'current_dir': '/Users/x/repo/app'},
    })
    check_true('statusline: prompt count shown', '2 Prompts' in out, out)
    check_true('statusline: override count shown', '1 Overrides' in out, out)
    check_true('statusline: model tier + version shown', 'OP5' in out, out)
    check_true('statusline: effort abbreviated', ' H' in out, out)
    check_true('statusline: context percentage shown', 'ctx 78%' in out, out)
    check_true('statusline: 60-79% is a warning, not COMPACT', 'COMPACT' not in out, out)
    check_true('statusline: cost rounded to cents', '$4.57' in out, out)
    # The spinner terminates the metrics row, not the whole output — the theme row
    # and any helm rows follow it. Assert against the row that actually owns it.
    check_true('statusline: spinner shown while running',
               out.split('\n')[0].rstrip().endswith(('|', '/', '-', '\\', '\x1b[0m')), out)
    # No WEZTERM_PANE in the sandbox, so the topic row must still render from the
    # theme log-prompt.py tracked for that override prompt.
    check_true('statusline: topic falls back to the tracked theme', 'differently' in out, out)

    _code, out = box.run('statusline.py', {'session_id': SID,
                                           'context_window': {'used_percentage': 91}})
    check_true('statusline: >=80% context demands a compact', 'ctx 91% COMPACT' in out, out)

    # No payload at all still prints one line rather than failing.
    code, out = box.run('statusline.py', None)
    check('statusline: empty stdin exits 0', code, 0)
    check('statusline: empty stdin prints a single blank row', out, '\n')

    # The topic row prefers Claude Code's own task title, which arrives with a
    # spinner glyph on the front and is sometimes not a task at all. Sandbox.run
    # drops WEZTERM_PANE, so the rendered row above exercises the fallback.
    check('statusline: spinner glyph stripped from the pane title',
          statusline.clean_pane_title('✳ Fix Claudance tab behavior on macOS'),
          'Fix Claudance tab behavior on macOS')
    check('statusline: braille spinner frame stripped too',
          statusline.clean_pane_title('⠂ Analyze the open policy'),
          'Analyze the open policy')
    check('statusline: a shell is not a topic', statusline.clean_pane_title('zsh'), '')
    check('statusline: untitled Claude is not a topic',
          statusline.clean_pane_title('✳ Claude Code'), '')

    # helm-status.json breadcrumb rows.
    project = os.path.join(box.home, 'project')
    os.makedirs(project, exist_ok=True)
    with open(os.path.join(project, 'helm-status.json'), 'w', encoding='utf-8') as fh:
        json.dump({'currentTask': 'Porting the hooks',
                   'blockers': ['no lua binary', 'no pwsh'],
                   'nextPlanned': 'Wire WezTerm'}, fh)
    _code, out = box.run('statusline.py',
                         {'session_id': SID, 'workspace': {'current_dir': project}})
    check_true('statusline: helm current task row', 'Porting the hooks' in out, out)
    check_true('statusline: helm blocker rows', 'no lua binary' in out and 'no pwsh' in out, out)
    check_true('statusline: helm next-planned row', 'Wire WezTerm' in out, out)
finally:
    box.close()

# ── startup-reminder: dev-command detection ─────────────────────────────────
box = Sandbox()
try:
    project = os.path.join(box.home, 'proj')
    os.makedirs(project, exist_ok=True)

    _code, out = box.run('startup-reminder.py', {'cwd': project})
    check('startup-reminder: silent when nothing is detectable', out, '')

    with open(os.path.join(project, 'package.json'), 'w', encoding='utf-8') as fh:
        json.dump({'scripts': {'dev': 'next dev'}}, fh)
    _code, out = box.run('startup-reminder.py', {'cwd': project})
    check_true('startup-reminder: npm fallback when no lockfile', 'npm run dev' in out, out)

    open(os.path.join(project, 'pnpm-lock.yaml'), 'w').close()
    _code, out = box.run('startup-reminder.py', {'cwd': project})
    check_true('startup-reminder: pnpm inferred from the lockfile', 'pnpm dev' in out, out)
    payload = json.loads(out)
    check('startup-reminder: emits a SessionStart hook payload',
          payload['hookSpecificOutput']['hookEventName'], 'SessionStart')

    with open(os.path.join(project, '.startup-cmd'), 'w', encoding='utf-8') as fh:
        fh.write('./scripts/dev.sh --watch\n')
    _code, out = box.run('startup-reminder.py', {'cwd': project})
    check_true('startup-reminder: .startup-cmd overrides everything',
               './scripts/dev.sh --watch' in out, out)
finally:
    box.close()

# ── workspace-state: the four injected blocks, and silence without a contract ──
box = Sandbox()
try:
    project = os.path.join(box.home, 'ws')
    docs = os.path.join(project, 'docs')
    os.makedirs(docs, exist_ok=True)

    _code, out = box.run('scripts/workspace-state.py', {'cwd': project})
    check('workspace-state: silent with no contract files', out, '')

    with open(os.path.join(docs, 'TODO.md'), 'w', encoding='utf-8') as fh:
        fh.write('# TODO\n\n## Now\n\n- blocked on a person\n\n## Next\n\n- the agreed step\n\n'
                 '## Backlog\n\n- deliberately deferred\n')
    with open(os.path.join(docs, 'JOURNAL.md'), 'w', encoding='utf-8') as fh:
        fh.write('# Journal\n\n## 2026-08-10\n\n### 12:00 · `PIVOT` · the newest entry\n\n'
                 '## 2026-08-09\n\n### 09:00 · `OLD` · the previous day\n')

    subprocess.run(['git', 'init', '-q', project], check=True, timeout=30)
    subprocess.run(['git', '-C', project, 'add', '.'], check=True, timeout=30)
    subprocess.run(['git', '-C', project, '-c', 'user.email=t@t', '-c', 'user.name=t',
                    'commit', '-qm', 'docs: the committed change'], check=True, timeout=30)

    _code, out = box.run('scripts/workspace-state.py', {'cwd': project})
    ctx = json.loads(out)['hookSpecificOutput']['additionalContext']
    check_true('workspace-state: injects Now', 'blocked on a person' in ctx, ctx)
    check_true('workspace-state: injects Next', 'the agreed step' in ctx, ctx)
    check_true('workspace-state: omits Backlog', 'deliberately deferred' not in ctx, ctx)
    check_true('workspace-state: injects the newest journal entry only',
               'the newest entry' in ctx and 'the previous day' not in ctx, ctx)
    check_true('workspace-state: injects the commit log',
               'docs: the committed change' in ctx, ctx)
finally:
    box.close()

# ── open-workspace: state-doc discovery must match the hook's search order ─────
# The launcher and workspace-state.py must never disagree about which file is the
# state of a project, so this asserts the same canonical name, aliases and order.
box = Sandbox()
try:
    launcher = os.path.join(REPO, 'scripts', 'open-workspace.sh')

    def resolve(path):
        proc = subprocess.run(['bash', launcher, '--state-doc', path],
                              capture_output=True, text=True, timeout=30)
        return proc.stdout.strip(), proc.returncode

    empty = os.path.join(box.home, 'empty')
    os.makedirs(empty, exist_ok=True)
    got, code = resolve(empty)
    check('open-workspace: no state doc reports none', got, 'none')
    check_true('open-workspace: missing doc is not an error', code == 0, str(code))

    aliased = os.path.join(box.home, 'aliased', 'docs')
    os.makedirs(aliased, exist_ok=True)
    open(os.path.join(aliased, 'context.md'), 'w').close()
    got, _ = resolve(os.path.dirname(aliased))
    check('open-workspace: legacy alias found', got, 'docs/context.md')

    open(os.path.join(aliased, 'STATE.md'), 'w').close()
    got, _ = resolve(os.path.dirname(aliased))
    check('open-workspace: canonical name wins over an alias', got, 'docs/STATE.md')

    rooted = os.path.join(box.home, 'rooted')
    os.makedirs(rooted, exist_ok=True)
    open(os.path.join(rooted, 'STATE.md'), 'w').close()
    got, _ = resolve(rooted)
    check('open-workspace: repo root searched after docs/', got, './STATE.md')

    # The same alias list is written in python, bash and lua — three runtimes
    # that cannot share a constant. Assert they agree, because the failure mode
    # is silent: an alias added in one place leaves the other two blind to it.
    def names_in(relpath, pattern):
        with open(os.path.join(REPO, relpath), 'r', encoding='utf-8') as fh:
            body = fh.read()
        return set(re.findall(pattern, body))

    expected = {'STATE.md', 'context.md', 'workflow_state.md', 'KNOWLEDGE.md'}
    sources = {
        'workspace-state.py': names_in('scripts/workspace-state.py',
                                       r"'(STATE\.md|context\.md|workflow_state\.md|KNOWLEDGE\.md)'"),
        'open-workspace.sh': names_in('scripts/open-workspace.sh',
                                      r"\b(STATE\.md|context\.md|workflow_state\.md|KNOWLEDGE\.md)\b"),
        'terminal.lua': names_in('terminal.lua',
                                 r"'(STATE\.md|context\.md|workflow_state\.md|KNOWLEDGE\.md)'"),
    }
    for src, found in sources.items():
        check_true('state-doc aliases agree: %s' % src, found == expected,
                   'missing %s' % sorted(expected - found))
finally:
    box.close()

# ── state-health: the drift check must actually fire, and be clearable ─────────
# Same lesson as loop-health below: a check that cannot fail is decoration, so
# assert it warns on real drift AND goes quiet the one way it should.
box = Sandbox()
try:
    proj = os.path.join(box.home, 'drifting')
    os.makedirs(os.path.join(proj, 'docs'), exist_ok=True)
    os.makedirs(os.path.join(proj, 'src'), exist_ok=True)

    def write_state(last_verified):
        with open(os.path.join(proj, 'docs', 'STATE.md'), 'w', encoding='utf-8') as fh:
            fh.write('---\npurpose: p\nupdate-trigger: t\nlast-verified: %s\nstatus: current\n'
                     '---\n\n# S\n\n```mermaid\nflowchart TD\n  A --> B\n```\n' % last_verified)

    def commit(msg, day):
        subprocess.run(['git', '-C', proj, 'add', '.'], capture_output=True, timeout=30)
        subprocess.run(['git', '-C', proj, '-c', 'user.email=t@t', '-c', 'user.name=t',
                        'commit', '-qm', msg, '--date=%s' % day], capture_output=True, timeout=30)

    def drift_out():
        proc = subprocess.run([PY, os.path.join(REPO, 'scripts', 'state-health.py'), '--drift'],
                              cwd=proj, capture_output=True, text=True, timeout=60)
        return proc.stdout

    write_state('2026-08-01')
    with open(os.path.join(proj, 'docs', 'TODO.md'), 'w', encoding='utf-8') as fh:
        fh.write('# TODO\n\n## Now\n\n## Next\n\n## Backlog\n')
    subprocess.run(['git', '-C', proj, 'init', '-q', '.'], capture_output=True, timeout=30)
    commit('docs: baseline', '2026-08-01')

    out = drift_out()
    check_true('state-health: quiet when no code landed after last-verified',
               'DRIFTING' not in out, out)

    for i in range(1, 5):
        with open(os.path.join(proj, 'src', 'f%d.py' % i), 'w') as fh:
            fh.write('v%d\n' % i)
        commit('feat: shipped thing %d' % i, '2026-08-0%d' % (4 + i))

    out = drift_out()
    check_true('state-health: warns when code outran the doc', 'DRIFTING' in out, out)
    check_true('state-health: names the commit count', '4 non-doc commits' in out, out)

    # Editing the doc must NOT clear drift — only re-verifying it does. Otherwise
    # touching a file would launder the signal the check exists to raise.
    commit('docs: tweak without re-verifying', '2026-08-09')
    out = drift_out()
    check_true('state-health: a doc edit does not launder drift', 'DRIFTING' in out, out)

    write_state('2026-08-09')
    commit('docs: re-verified', '2026-08-09')
    out = drift_out()
    check_true('state-health: bumping last-verified clears it', 'DRIFTING' not in out, out)
finally:
    box.close()

# ── loop-health: the canary must fire on nulls, and stay quiet before baseline ─
# The whole point of this check is that it caught a null ledger. A version that
# cannot fail is decoration, so assert it fails on the bad input.
box = Sandbox()
try:
    tele = box.path('telemetry')
    improve = box.path('improve')
    os.makedirs(tele, exist_ok=True)
    os.makedirs(os.path.join(tele, 'reports'), exist_ok=True)
    os.makedirs(improve, exist_ok=True)
    open(os.path.join(tele, 'reports', 'aabbccdd.json'), 'w').write('{}')

    def write_ledger(rows):
        with open(os.path.join(tele, 'cost-ledger.jsonl'), 'w') as fh:
            for r in rows:
                fh.write(json.dumps(r) + '\n')

    def sanity_out():
        # Not box.run: that treats a non-zero exit as a harness failure, and a
        # non-zero exit is exactly what this check is supposed to produce.
        env = dict(os.environ, HOME=box.home, CLAUDENCE_SILENT='1')
        proc = subprocess.run([PY, os.path.join(REPO, 'telemetry/loop-health.py'), '--sanity'],
                              input='', env=env, capture_output=True, text=True, timeout=60)
        return proc.returncode, proc.stdout + proc.stderr

    nulls = [{'ts': '2026-08-10T12:00:0%d-07:00' % i, 'cost_usd': None, 'ctx_pct': None}
             for i in range(6)]
    write_ledger(nulls)
    code, out = sanity_out()
    check_true('loop-health: fails when the ledger is null', code == 1, out)
    check_true('loop-health: names the meta file in the remedy', 'meta-<id>.json' in out, out)

    good = [{'ts': '2026-08-10T12:00:0%d-07:00' % i, 'cost_usd': 1.0, 'ctx_pct': 40}
            for i in range(6)]
    write_ledger(good)
    code, out = sanity_out()
    check_true('loop-health: passes when the ledger is populated', code == 0, out)

    # Rows before the baseline are legitimately null and must not trip it,
    # otherwise the check cries wolf for weeks after any fix lands.
    with open(os.path.join(improve, 'ledger-baseline.json'), 'w') as fh:
        json.dump({'ts': '2026-08-10T11:00:00-07:00'}, fh)
    write_ledger([{'ts': '2026-08-09T12:00:00-07:00', 'cost_usd': None, 'ctx_pct': None}] * 30 + good)
    code, out = sanity_out()
    check_true('loop-health: pre-baseline nulls are exempt', code == 0, out)
finally:
    box.close()

print('%d passed, %d failed' % (PASS, FAIL))
for failure in FAILURES:
    print('FAIL | %s' % failure)
sys.exit(1 if FAIL else 0)
