# SessionStart hook — reminds you of the current repo's startup/dev command when a session opens.
# Detects a startup command generically so it works across projects. Precedence:
#   1. .startup-cmd file (one line) — an explicit per-repo override (use for non-standard commands)
#   2. dev.ps1 / restart.ps1 / start.ps1 / run.ps1  (Windows launchers)
#   3. dev.sh / start.sh / restart.sh               (shell launchers)
#   4. package.json scripts.dev|start               (pm inferred from lockfile)
#   5. docker-compose.yml / compose.yaml
#   6. Makefile with a dev|start|run target
# Silent when the repo has no recognizable startup command (no nagging).
$ErrorActionPreference = 'SilentlyContinue'
try {
  $raw = [Console]::In.ReadToEnd()
  $cwd = $null
  if ($raw) { try { $cwd = ($raw | ConvertFrom-Json).cwd } catch {} }
  if (-not $cwd) { $cwd = (Get-Location).Path }
  $repo = Split-Path $cwd -Leaf
  $cmd = $null

  $startupFile = Join-Path $cwd '.startup-cmd'
  if (Test-Path $startupFile) {
    $cmd = (Get-Content $startupFile -Raw).Trim()
  }
  elseif (Test-Path (Join-Path $cwd 'dev.ps1'))     { $cmd = './dev.ps1' }
  elseif (Test-Path (Join-Path $cwd 'restart.ps1')) { $cmd = './restart.ps1' }
  elseif (Test-Path (Join-Path $cwd 'start.ps1'))   { $cmd = './start.ps1' }
  elseif (Test-Path (Join-Path $cwd 'run.ps1'))     { $cmd = './run.ps1' }
  elseif (Test-Path (Join-Path $cwd 'dev.sh'))      { $cmd = './dev.sh' }
  elseif (Test-Path (Join-Path $cwd 'start.sh'))    { $cmd = './start.sh' }
  elseif (Test-Path (Join-Path $cwd 'restart.sh'))  { $cmd = './restart.sh' }
  elseif (Test-Path (Join-Path $cwd 'package.json')) {
    $pkg = Get-Content (Join-Path $cwd 'package.json') -Raw | ConvertFrom-Json
    $pm = if (Test-Path (Join-Path $cwd 'pnpm-lock.yaml')) { 'pnpm' }
          elseif (Test-Path (Join-Path $cwd 'yarn.lock')) { 'yarn' }
          else { 'npm run' }
    if ($pkg.scripts.dev)       { $cmd = "$pm dev" }
    elseif ($pkg.scripts.start) { $cmd = "$pm start" }
  }
  elseif (Test-Path (Join-Path $cwd 'docker-compose.yml')) { $cmd = 'docker compose up' }
  elseif (Test-Path (Join-Path $cwd 'compose.yaml'))       { $cmd = 'docker compose up' }
  elseif (Test-Path (Join-Path $cwd 'Makefile')) {
    $mk = Get-Content (Join-Path $cwd 'Makefile') -Raw
    foreach ($t in 'dev','start','run') { if ($mk -match "(?m)^$t\s*:") { $cmd = "make $t"; break } }
  }

  if ($cmd) {
    $ctx = "Startup command for '$repo': run  $cmd  to launch this project's services (hot reload / dev). " +
           "Surface this to the user near the start of your first reply."
    $out = @{ hookSpecificOutput = @{ hookEventName = 'SessionStart'; additionalContext = $ctx } } | ConvertTo-Json -Compress
    [Console]::Out.Write($out)
  }
} catch { }
