#!/usr/bin/env python3
"""hooklib.py — shared plumbing for the macOS hook ports.

Every hook in telemetry/ receives a JSON payload on stdin and appends to the
per-session JSONL under ~/.claude/telemetry/sessions/. This module holds the
parts they all need: payload parsing, the timestamp format the JSONL uses,
tolerant JSON/JSONL readers, and sound playback.

macOS notes vs the PowerShell originals:
  * Timestamps keep PowerShell's 'o'-style shape (local time + offset) so a
    session log written on either platform parses with parse_ts below.
  * Sound is afplay against /System/Library/Sounds instead of
    System.Media.SoundPlayer against C:\\Windows\\Media. There are no .wav
    files to generate, so setup.sh has nothing to do here — the volume scaling
    setup.ps1 did by rewriting PCM samples is afplay's -v flag instead.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

HOME = os.path.expanduser('~')
CLAUDE_DIR = os.path.join(HOME, '.claude')
TELEMETRY_DIR = os.path.join(CLAUDE_DIR, 'telemetry')
SESSIONS_DIR = os.path.join(TELEMETRY_DIR, 'sessions')
REPORTS_DIR = os.path.join(TELEMETRY_DIR, 'reports')
WORKSPACES_DIR = os.path.join(CLAUDE_DIR, 'workspaces')

# Logical sound names (kept from the Windows build so settings.json hook args and
# analyze-session read the same way on both platforms) -> macOS system sounds.
# A file dropped in ~/.claude/sounds/ with the same stem overrides the mapping,
# which is how you customize without editing code.
BOTTLE = '/System/Library/Sounds/Bottle.aiff'

# One sound for all three roles on macOS. The three names still exist because they
# are the cross-platform contract — Windows maps them to three distinct .wav files
# and hook args read the same on both — but a chime that only fires when Claude
# actually wants you does not need to encode WHICH kind of wanting in its timbre.
# Distinguishing Glass from Bottle from Ping was information nobody was decoding.
SYSTEM_SOUNDS = {
    'ring-half': BOTTLE,    # was Glass; before that chimes.wav
    'notify-half': BOTTLE,  # was Pop, softened to Bottle in 27d220b — now the only voice
    'ding-half': BOTTLE,    # was Ping; before that Windows Ding.wav
}
def _sound_override(name):
    """Per-machine override, so changing a chime never needs a code edit.

    CLAUDENCE_SOUND_NOTIFY_HALF=/System/Library/Sounds/Purr.aiff swaps one sound;
    dropping <name>.aiff into ~/.claude/sounds/ still wins over both, and that
    is the route for a custom file rather than a system one.
    """
    return os.environ.get('CLAUDENCE_SOUND_' + name.upper().replace('-', '_'))


SOUND_VOLUME = '0.56'  # 30% below the 0.8 the Windows build baked into its .wav samples.
                       # Now that the chime is rare it can also be quieter: it no longer
                       # has to compete for notice against its own repetition.


def read_stdin_json():
    """The hook payload, or None when stdin is empty/not JSON.

    Hooks must never fail loudly: a crash here would surface as a Claude Code
    hook error on every prompt, so callers treat None as "no telemetry".
    """
    try:
        raw = sys.stdin.read()
    except Exception:
        return None
    if not raw or not raw.strip():
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def now_iso():
    """Local time with offset — the shape PowerShell's Get-Date -Format 'o' emits."""
    return datetime.now().astimezone().isoformat()


_TS_FRAC = re.compile(r'\.(\d+)')


def parse_ts(value):
    """Parse a timestamp from the session JSONL into an aware datetime, or None.

    Handles every shape the logs contain: a trailing 'Z', an explicit ±HH:MM
    offset, and PowerShell's 7-digit fractional seconds (datetime.fromisoformat
    on Python 3.9 accepts only 3 or 6 digits, and no 'Z' at all — hence the
    normalizing instead of a bare fromisoformat call).
    """
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    if s.endswith('Z') or s.endswith('z'):
        s = s[:-1] + '+00:00'

    def _trim(m):
        digits = m.group(1)[:6].ljust(6, '0')
        return '.' + digits

    s = _TS_FRAC.sub(_trim, s, count=1)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    # A naive timestamp is local time by convention (that is what 'o' writes when
    # the offset is stripped); anchoring it keeps comparisons total.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return dt


def ts_key(event):
    """Sort/compare key for an event dict — unparseable timestamps sort first."""
    dt = parse_ts(event.get('ts')) if isinstance(event, dict) else None
    return dt or datetime.min.replace(tzinfo=timezone.utc)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def read_json(path, default=None):
    """Parse a JSON file, returning `default` on any problem.

    A partially-written file is normal here — statusline runs while agents are
    mid-write — so a failed parse means "skip this tick", never an error.
    """
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            raw = fh.read()
    except Exception:
        return default
    raw = raw.lstrip('\ufeff')
    if not raw.strip():
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def write_json(path, obj):
    ensure_dir(os.path.dirname(path))
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(obj, fh, indent=2)
        fh.write('\n')


def write_json_compact(path, obj):
    """Compact, BOM-less UTF-8 — the form wezterm.json_parse reads in terminal.lua."""
    ensure_dir(os.path.dirname(path))
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(json.dumps(obj, separators=(',', ':')))


def read_jsonl(path):
    """Every parseable object in a JSONL file; malformed lines are skipped."""
    out = []
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            for line in fh:
                line = line.strip().lstrip('\ufeff')
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return out
    return out


def append_jsonl(path, obj):
    ensure_dir(os.path.dirname(path))
    with open(path, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(obj, separators=(',', ':')) + '\n')


def session_file(session_id):
    return os.path.join(SESSIONS_DIR, '%s.jsonl' % session_id)


def state_file(session_id):
    """Per-session KPI file the status bar reads.

    Keyed by session id so parallel terminals never collide — the same reason
    log-prompt.ps1 moved off a single shared current-session.json.
    """
    return os.path.join(TELEMETRY_DIR, 'state-%s.json' % session_id)


def meta_file(session_id):
    """Cost and context usage, as last seen by the status line.

    Its own file rather than a key in state_file: the status line writes this on
    every assistant message while log-prompt.py read-modify-writes the state file,
    and a merged write would clobber one or the other.
    """
    return os.path.join(TELEMETRY_DIR, 'meta-%s.json' % session_id)


def running_flag(session_id):
    return os.path.join(TELEMETRY_DIR, 'running-%s.flag' % session_id)


def start_stamp(session_id):
    """Turn-start marker used for the Stop sound's elapsed-time decision.

    Per-session, unlike the Windows build's single %TEMP%\\claude_start.txt:
    that file was shared by every concurrent session, so with two terminals open
    each Stop read whichever session most recently submitted a prompt and the
    elapsed time — hence the ring-vs-notify choice — was wrong.
    """
    return os.path.join(TELEMETRY_DIR, 'start-%s.stamp' % session_id)


def resolve_sound(name):
    """Absolute path for a logical sound name, or None if nothing is available.

    Accepts 'ring-half', 'ring-half.wav' or a bare path, so hook args written for
    the Windows build ('-Sound ding-half.wav') keep working unchanged.
    """
    if not name:
        return None
    if os.path.isabs(name) and os.path.exists(name):
        return name
    stem = os.path.basename(name)
    stem = re.sub(r'\.(wav|aiff|aif|mp3|m4a)$', '', stem, flags=re.IGNORECASE)
    local_dir = os.path.join(CLAUDE_DIR, 'sounds')
    for ext in ('.aiff', '.aif', '.wav', '.mp3', '.m4a'):
        candidate = os.path.join(local_dir, stem + ext)
        if os.path.exists(candidate):
            return candidate
    system = _sound_override(stem) or SYSTEM_SOUNDS.get(stem)
    if system and os.path.exists(system):
        return system
    return None


def play_sound(name, blocking=True):
    """Play a logical sound through afplay. Never raises — audio is never critical.

    CLAUDENCE_SILENT=1 suppresses playback entirely: the test suite exercises the
    Stop hook repeatedly, and it is also the escape hatch for a quiet session
    without editing the hook wiring.
    """
    if os.environ.get('CLAUDENCE_SILENT') == '1':
        return
    path = resolve_sound(name)
    if not path:
        return
    argv = ['/usr/bin/afplay', '-v', SOUND_VOLUME, path]
    try:
        if blocking:
            subprocess.run(argv, timeout=10,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(argv,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def throttle(stamp_path, window_secs, now=None):
    """True when `window_secs` have passed since the last claim on this stamp.

    On-disk because each hook is a separate short-lived process and they cannot
    share memory: this is what stops N sessions finishing together from
    producing a chime storm. Claims the stamp as a side effect when it returns
    True, so callers should only call it when they intend to make the sound.
    """
    now = int(now if now is not None else datetime.now(timezone.utc).timestamp())
    last = 0
    try:
        with open(stamp_path, 'r', encoding='utf-8') as fh:
            last = int(float(fh.read().strip()))
    except Exception:
        last = 0
    if now - last < window_secs:
        return False
    try:
        ensure_dir(os.path.dirname(stamp_path))
        with open(stamp_path, 'w', encoding='utf-8') as fh:
            fh.write(str(now))
    except Exception:
        pass
    return True


def norm_cwd(cwd):
    """Forward slashes, no trailing slash — matches attention.lua's norm_path input."""
    if not cwd:
        return ''
    return cwd.replace('\\', '/').rstrip('/')


def tool_input_preview(tool_input, limit):
    """The first identifying field of a tool call, truncated. '' when unknown."""
    if not isinstance(tool_input, dict):
        return ''
    for key in ('command', 'file_path', 'pattern', 'query'):
        value = tool_input.get(key)
        if value:
            return str(value)[:limit]
    return ''
