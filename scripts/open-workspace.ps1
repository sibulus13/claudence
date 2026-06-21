<#
.SYNOPSIS
  Open (or focus) a named WezTerm workspace for a Claude Code project.

.DESCRIPTION
  - If a workspace with the given name already exists in WezTerm, activates it.
  - Otherwise creates a new workspace with a dual-pane layout:
      Left  — claude --continue  (agent session)
      Right — PowerShell shell   (aux: dev server, git, etc.)
  - Updates the workspace registry for discovery (sorted by lastUsed).
  - Writes active.json for Nexus dashboard sync.

.EXAMPLE
  open-workspace.ps1 -WorkspaceName helm -ProjectPath "D:\repo\Life\second-brain"
  open-workspace.ps1 -WorkspaceName crucible -ProjectPath "D:\repo\Stock\Research 2026" -RightCmd "python main.py"
#>
param(
  [Parameter(Mandatory)][string]$WorkspaceName,
  [Parameter(Mandatory)][string]$ProjectPath,
  [string]$IdeaFilename = '',
  [string]$RightCmd     = ''   # leave empty for a plain shell
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RegistryDir  = "$env:USERPROFILE\.claude\workspaces"
$RegistryPath = "$RegistryDir\registry.json"
$ActivePath   = "$RegistryDir\active.json"
$Now          = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')

# ── Ensure registry dir exists ────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path $RegistryDir | Out-Null

# ── Check if workspace already open in WezTerm ───────────────────────────────
# Use --format json (available in all modern WezTerm builds) instead of
# parsing the text table, which varies in column order across versions.
$existingPane = $null
try {
  $panes = wezterm cli list --format json 2>$null | ConvertFrom-Json
  $existingPane = ($panes | Where-Object { $_.workspace -eq $WorkspaceName } |
    Select-Object -First 1).pane_id
} catch { }

if ($existingPane) {
  Write-Host "Focusing existing workspace '$WorkspaceName' (pane $existingPane)"
  wezterm cli activate-pane --pane-id $existingPane | Out-Null
} else {
  Write-Host "Creating workspace '$WorkspaceName' in $ProjectPath"

  # ── Left pane: Claude Code ─────────────────────────────────────────────────
  $leftPaneId = (wezterm cli spawn `
    --workspace $WorkspaceName `
    --cwd $ProjectPath `
    -- powershell.exe -NoProfile -NoExit -Command "claude --continue").Trim()

  Start-Sleep -Milliseconds 600

  # ── Right pane: aux shell or custom command ────────────────────────────────
  if ($RightCmd -ne '') {
    $rightArgs = @('cli', 'split-pane', '--pane-id', $leftPaneId, '--right', '--cwd', $ProjectPath, '--') + ($RightCmd -split '\s+')
    $rightPaneId = (& wezterm @rightArgs).Trim()
  } else {
    $rightPaneId = (wezterm cli split-pane `
      --pane-id $leftPaneId `
      --right `
      --cwd $ProjectPath `
      -- powershell.exe -NoProfile -NoExit).Trim()
  }

  # ── Name the tab ──────────────────────────────────────────────────────────
  wezterm cli set-tab-title --pane-id $leftPaneId --title $WorkspaceName | Out-Null

  # ── Return focus to left pane (agent) ────────────────────────────────────
  wezterm cli activate-pane --pane-id $leftPaneId | Out-Null

  Write-Host "Workspace '$WorkspaceName' ready — left=$leftPaneId right=$rightPaneId"
}

# ── Update workspace registry ────────────────────────────────────────────────
if (Test-Path $RegistryPath) {
  $reg = Get-Content $RegistryPath -Raw | ConvertFrom-Json
  $workspaces = [System.Collections.Generic.List[object]]($reg.workspaces)
} else {
  $workspaces = [System.Collections.Generic.List[object]]@()
}

$entry = $workspaces | Where-Object { $_.name -eq $WorkspaceName } | Select-Object -First 1
if ($entry) {
  $entry.lastUsed  = $Now
  $entry.useCount  = [int]$entry.useCount + 1
  $entry.projectPath = $ProjectPath
} else {
  $workspaces.Add([PSCustomObject]@{
    name        = $WorkspaceName
    projectPath = $ProjectPath
    ideaFilename= $IdeaFilename
    lastUsed    = $Now
    useCount    = 1
  })
}

# Keep the 20 most recently used
$sorted = $workspaces | Sort-Object -Property lastUsed -Descending | Select-Object -First 20
[PSCustomObject]@{ workspaces = $sorted } | ConvertTo-Json -Depth 5 |
  Out-File -FilePath $RegistryPath -Encoding utf8

# ── Write active.json for Nexus sync ─────────────────────────────────────────
[PSCustomObject]@{
  workspace = $WorkspaceName
  cwd       = $ProjectPath.Replace('\', '/')
  updatedAt = $Now
} | ConvertTo-Json | Out-File -FilePath $ActivePath -Encoding utf8
