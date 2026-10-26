# Notion playbook (cue: any Notion MCP tool)
- Writes need the owner's per-action OK (enforced: hooks/guard.py asks). Reads are free. The scheduled tiktok-sync job may update matched Content Bank rows (metrics, Status=Done, review body) unattended; nothing else.
- Add a database property only when a script joins on it or a person sorts/filters by it at a glance; everything else goes in the page body.
- Notion stores datetimes in UTC; the owner's time zone is America/Vancouver.
- Cortex runs use the claude.ai Notion connector with `--setting-sources project,local`, so global hooks do not apply to them; their own capability grants do.
