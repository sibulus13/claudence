-- restore.lua — PURE decision logic for WezTerm session restore: how old a saved
-- layout may be, which tabs count, and what command a pane gets relaunched with.
-- No wezterm/io/os dependencies: data in, data out, so it can be unit-tested in
-- isolation (see tests/restore.test.lua). terminal.lua calls this, so the tested
-- logic IS the runtime logic.
--
-- This module exists because the restore path was the one part of the terminal
-- with no test at all, and it failed the way untested code fails: silently. A
-- 12-hour freshness cap threw away every tab across any overnight or weekend
-- close, and because the discard was mute it read as "nothing was ever saved".

local M = {}

-- How old a saved layout may be and still be restored. 168 h matches
-- record-pane-session.py's ORPHAN_MAX_AGE_DAYS = 7: past a week the
-- pane -> session bindings have been reaped anyway, so a restore could only fall
-- back to --continue's guess.
M.MAX_H = 168

-- Fallback restore command when the pane's exact session id is unknown:
-- --continue resumes the cwd's MOST RECENT conversation (wrong when a repo has
-- several — M.claude_cmd's --resume path is the precise one). --permission-mode
-- auto starts it in the classifier-driven Auto mode so restored agents don't sit
-- in ask-everything mode.
M.CLAUDE_FALLBACK = 'claude --continue --permission-mode auto'

-- Programs worth re-launching on restore. Claude is matched by name (M.resume_cmd);
-- everything here is a long-running dev process whose exact invocation is
-- reconstructed from argv. Keyed by the executable's leaf name, lower-cased, sans
-- .exe. The interactive SHELLS (pwsh/powershell/cmd/bash/zsh) are deliberately
-- absent — an idle prompt must NOT be captured as a command, or restore would
-- relaunch a shell inside a shell. Extend freely.
M.RESUMABLE = {
  node = true, python = true, python3 = true, bun = true, deno = true,
  pnpm = true, npm = true, yarn = true, vite = true, next = true,
  vim = true, nvim = true, nano = true, jupyter = true, ssh = true,
  cargo = true, go = true, docker = true, ['docker-compose'] = true,
}

-- Is a layout saved at `saved_at` still fresh at `now`? Returns the verdict AND
-- the age, because the caller has to be able to SAY why it dropped the layout.
function M.layout_is_fresh(saved_at, now, max_h)
  local age_h = ((tonumber(now) or 0) - (tonumber(saved_at) or 0)) / 3600
  return age_h <= (tonumber(max_h) or M.MAX_H), age_h
end

-- A tab whose identity is a repo-relative path — the only kind that round-trips.
-- 'Nexus' and shell-named tabs carry no path, so they are neither saved nor
-- restored; a '~/'-prefixed title is a home-relative tab that predates the
-- convention and is skipped rather than resolved to the wrong directory.
function M.is_repo_tab(title)
  if type(title) ~= 'string' or title == '' then return false end
  if title:match('^~/') then return false end
  return title:find('/') ~= nil
end

-- The recorded id, or nil. UUID-shaped only: this value is interpolated into a
-- launch command, so a malformed file must not be able to inject shell text.
function M.valid_session_id(sid)
  if type(sid) ~= 'string' or sid == '' then return nil end
  if not sid:match('^[%w%-]+$') then return nil end
  return sid
end

-- Resume THIS conversation when the pane's binding was captured, else fall back
-- to the cwd's most recent one.
function M.claude_cmd(sid)
  local id = M.valid_session_id(sid)
  if id then return 'claude --resume ' .. id .. ' --permission-mode auto' end
  return M.CLAUDE_FALLBACK
end

-- An executable path reduced to the key RESUMABLE is written in.
function M.leaf_name(path)
  local leaf = tostring(path or ''):gsub('\\', '/'):match('[^/]+$') or ''
  return (leaf:lower():gsub('%.exe$', ''))
end

-- Quote one argv token for the shell that will re-run it (only when it contains
-- whitespace, to keep the common case readable). PowerShell doubles an embedded
-- single quote; a POSIX shell has to close the quote, escape it, and reopen.
function M.quote_arg(a, is_win)
  a = tostring(a or '')
  if not a:find('%s') then return a end
  if is_win then return "'" .. a:gsub("'", "''") .. "'" end
  return "'" .. a:gsub("'", "'\\''") .. "'"
end

-- What to relaunch in a pane, or nil for an idle shell / a transient command not
-- worth resuming. Claude keeps its proven name-based detection (its foreground
-- name contains "claude" throughout the session, even while shelling out
-- mid-tool); other whitelisted programs are reconstructed verbatim from argv.
function M.resume_cmd(fg_name, sid, executable, argv, is_win)
  if tostring(fg_name or ''):lower():find('claude') then return M.claude_cmd(sid) end
  if not M.RESUMABLE[M.leaf_name(executable)] then return nil end
  if type(argv) ~= 'table' or #argv == 0 then return nil end
  local parts = {}
  for _, a in ipairs(argv) do parts[#parts + 1] = M.quote_arg(a, is_win) end
  return table.concat(parts, ' ')
end

-- Spawn args for a restored pane: cd into the repo, run the saved command, then
-- hand the pane to an interactive login shell so a dev server that crashes
-- leaves a usable prompt instead of a dead pane. `exec` replaces the wrapper, so
-- no extra shell layer lingers in the process tree. Braces keep a compound
-- command (`a && b`) from binding only its first clause to the `;`. nil command
-- → nil, and the caller spawns a plain shell.
function M.launch_args(cmd, cwd, shell, is_win)
  if not cmd or cmd == '' then return nil end
  if is_win then
    return {
      'powershell.exe', '-NoProfile', '-NoLogo', '-NoExit', '-Command',
      "Set-Location '" .. tostring(cwd):gsub("'", "''") .. "'; " .. cmd,
    }
  end
  return {
    shell, '-lc',
    "cd '" .. tostring(cwd):gsub("'", "'\\''") .. "' && { " .. cmd .. "; }; exec " .. shell .. " -l",
  }
end

return M
