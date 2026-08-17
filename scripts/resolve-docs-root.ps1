# resolve-docs-root.ps1 - decide WHERE this session's docs belong.
#
# The Terse-Output Contract routes anything longer than a sentence out of the
# terminal and into a repo doc (docs/SESSION_LOG.md, docs/DECISIONS.md). That only
# works if "the repo" is unambiguous, so this resolves one docs root per session and
# keeps each project's log on its OWN version-control line instead of pooling every
# project's history into ~/.claude.
#
# ASCII only, deliberately: Windows PowerShell 5.1 reads a BOM-less .ps1 as ANSI, so
# a stray em dash inside a string literal is a parse error, not a cosmetic issue.
#
# Precedence (first hit wins):
#   1. $env:CLAUDE_DOCS_ROOT        explicit override for this shell / this session
#   2. .claude-docs-root marker     nearest ancestor holding the file. Empty file =>
#                                   "the folder I sit in"; otherwise its one line is
#                                   the root (absolute, or relative to the marker).
#                                   Travels WITH the repo and is itself committed.
#   3. doc-roots.json registry      machine-local pins, longest matching ancestor wins.
#                                   Use when the repo must not carry a marker file.
#   4. nearest ancestor with .git   the default: docs land on the project's own VC line
#   5. repo-org project folder      <repo root>/<Category>/<project> for a workspace
#                                   with no VC of its own (see the repo-org convention)
#   6. ~/.claude/docs               last resort, reported as source 'fallback'
#
# Rules 2 and 3 exist for the case the resolver cannot decide on its own: a workspace
# that is a folder INSIDE a larger repo (D:\repo\Life\pylon lives in the D:\repo\Life
# repo). Rule 4 would put pylon's log in Life's; a marker or a pin overrides that.
#
# Output: -Json emits the full record; -Hook emits SessionStart additionalContext;
# bare invocation prints the docs directory, for `cd $(...)`-style use.
[CmdletBinding()]
param(
  [string] $Path,
  [switch] $Json,
  [switch] $Hook
)

$ErrorActionPreference = 'SilentlyContinue'

# Forward slashes, no trailing slash, lower-cased - the comparison form only.
# Display values keep their original casing.
function Convert-ToComparablePath([string] $p) {
  if (-not $p) { return '' }
  return ($p -replace '\\', '/').TrimEnd('/').ToLowerInvariant()
}

function Convert-ToDisplayPath([string] $p) {
  if (-not $p) { return '' }
  return ($p -replace '\\', '/').TrimEnd('/')
}

# cwd and every ancestor, nearest first.
function Get-AncestorChain([string] $start) {
  $chain = @()
  $cur = $start
  while ($cur) {
    $chain += $cur
    $parent = Split-Path $cur -Parent
    if (-not $parent -or $parent -eq $cur) { break }
    $cur = $parent
  }
  return $chain
}

# The repo root the repo-org convention hangs off (D:\repo here). Machine-specific, so
# it comes from the same places terminal.lua reads it from - never hardcoded.
function Get-RepoRoot {
  if ($env:CLAUDE_REPO_ROOT) { return Convert-ToDisplayPath $env:CLAUDE_REPO_ROOT }
  $localLua = Join-Path $env:USERPROFILE '.claude/terminal.local.lua'
  if (Test-Path $localLua) {
    $raw = Get-Content $localLua -Raw
    if ($raw -match "repo_root\s*=\s*'([^']+)'") { return Convert-ToDisplayPath $Matches[1] }
    if ($raw -match 'repo_root\s*=\s*"([^"]+)"') { return Convert-ToDisplayPath $Matches[1] }
  }
  return Convert-ToDisplayPath (Join-Path $env:USERPROFILE 'repo')
}

function Resolve-DocsRoot([string] $startPath) {
  $start = $startPath
  if (-not $start) { $start = (Get-Location).Path }
  $chain = Get-AncestorChain $start

  # 1. environment override
  if ($env:CLAUDE_DOCS_ROOT) {
    return @{ root = Convert-ToDisplayPath $env:CLAUDE_DOCS_ROOT; source = 'env' }
  }

  # 2. marker file, nearest ancestor first
  foreach ($dir in $chain) {
    $marker = Join-Path $dir '.claude-docs-root'
    if (Test-Path $marker -PathType Leaf) {
      $body = (Get-Content $marker -Raw)
      if ($body) { $body = $body.Trim() }
      if (-not $body) { return @{ root = Convert-ToDisplayPath $dir; source = 'marker' } }
      $first = ($body -split "`n")[0].Trim()
      if ([System.IO.Path]::IsPathRooted($first)) {
        return @{ root = Convert-ToDisplayPath $first; source = 'marker' }
      }
      return @{ root = Convert-ToDisplayPath (Join-Path $dir $first); source = 'marker' }
    }
  }

  # 3. registry pins - longest matching ancestor wins, so a pin on a subfolder beats
  #    a pin on its parent.
  # $env:CLAUDE_DOC_ROOTS_FILE redirects the registry; the tests use it so they never
  # have to write to the live one.
  $registryPath = $env:CLAUDE_DOC_ROOTS_FILE
  if (-not $registryPath) { $registryPath = Join-Path $env:USERPROFILE '.claude/workspaces/doc-roots.json' }
  if (Test-Path $registryPath) {
    $reg = $null
    try { $reg = Get-Content $registryPath -Raw | ConvertFrom-Json } catch {}
    if ($reg) {
      $best = $null; $bestLen = -1
      foreach ($prop in $reg.PSObject.Properties) {
        $key = Convert-ToComparablePath $prop.Name
        if (-not $key) { continue }
        foreach ($dir in $chain) {
          if ((Convert-ToComparablePath $dir) -eq $key) {
            if ($key.Length -gt $bestLen) { $bestLen = $key.Length; $best = [string]$prop.Value }
          }
        }
      }
      if ($best) { return @{ root = Convert-ToDisplayPath $best; source = 'registry' } }
    }
  }

  # 4. nearest version-control root
  foreach ($dir in $chain) {
    if (Test-Path (Join-Path $dir '.git')) {
      return @{ root = Convert-ToDisplayPath $dir; source = 'git' }
    }
  }

  # 5. repo-org project folder: <repo root>/<Category>/<project>
  $repoRoot = Get-RepoRoot
  $repoRootCmp = Convert-ToComparablePath $repoRoot
  $startCmp = Convert-ToComparablePath $start
  if ($repoRootCmp -and $startCmp.StartsWith($repoRootCmp + '/')) {
    $displayStart = Convert-ToDisplayPath $start
    $displaySegs = $displayStart.Substring($repoRoot.Length + 1) -split '/'
    if ($displaySegs.Count -ge 2) {
      $proj = $repoRoot + '/' + $displaySegs[0] + '/' + $displaySegs[1]
      return @{ root = $proj; source = 'repo-org' }
    }
  }

  # 6. last resort
  return @{ root = Convert-ToDisplayPath (Join-Path $env:USERPROFILE '.claude'); source = 'fallback' }
}

function Get-DocsRecord([string] $startPath) {
  $start = $startPath
  if (-not $start) { $start = (Get-Location).Path }
  $hit = Resolve-DocsRoot $start

  # Is the docs dir going to be version-controlled, and by which repo? A root inside a
  # PARENT repo is legal but worth surfacing - that is the shared-log case a marker or
  # a pin is meant to resolve.
  $vcsRoot = $null
  foreach ($dir in (Get-AncestorChain $hit.root)) {
    if (Test-Path (Join-Path $dir '.git')) { $vcsRoot = Convert-ToDisplayPath $dir; break }
  }

  return [ordered]@{
    cwd     = Convert-ToDisplayPath $start
    root    = $hit.root
    docs    = $hit.root + '/docs'
    log     = $hit.root + '/docs/SESSION_LOG.md'
    journal = $hit.root + '/docs/DECISIONS.md'
    source  = $hit.source
    vcsRoot = $vcsRoot
    tracked = [bool]$vcsRoot
    shared  = [bool]($vcsRoot -and ((Convert-ToComparablePath $vcsRoot) -ne (Convert-ToComparablePath $hit.root)))
  }
}

# ---- entry points ----------------------------------------------------------
if ($Hook) {
  try {
    $cwd = $null
    $raw = [Console]::In.ReadToEnd()
    if ($raw) { try { $cwd = ($raw | ConvertFrom-Json).cwd } catch {} }
    if (-not $cwd) { $cwd = (Get-Location).Path }
    $r = Get-DocsRecord $cwd

    $ctx = "Docs root for this session: $($r.docs) (resolved by: $($r.source)). " +
           "Per the Terse-Output Contract, write verbose detail to $($r.log) and decisions to $($r.journal), " +
           "citing each with a one-line pointer instead of expanding the terminal. Create either file if absent."
    if (-not $r.tracked) {
      $ctx += " WARNING: this root is NOT under version control, so those docs would be untracked - " +
              "tell the user and confirm the location before writing."
    }
    elseif ($r.shared) {
      $ctx += " Note: the docs land in the $($r.vcsRoot) repo, which this folder shares with sibling projects. " +
              "If this workspace should keep its own log, say so - a .claude-docs-root marker or a doc-roots.json pin fixes it."
    }
    if ($r.source -eq 'fallback') {
      $ctx += " Source 'fallback' means nothing matched; confirm the intended workspace with the user."
    }

    $out = @{ hookSpecificOutput = @{ hookEventName = 'SessionStart'; additionalContext = $ctx } } | ConvertTo-Json -Compress
    [Console]::Out.Write($out)
  } catch { }
  return
}

$record = Get-DocsRecord $Path
if ($Json) { $record | ConvertTo-Json -Compress } else { $record.docs }
