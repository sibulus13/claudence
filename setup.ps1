# setup.ps1
# Bootstrap ~\.claude on a new Windows machine.
# Run once after copying the dotfiles repo into %USERPROFILE%\.claude
# Usage: powershell.exe -NoProfile -ExecutionPolicy Bypass -File setup.ps1

$root = "$env:USERPROFILE\.claude"

# ── 1. Ensure required directories exist ─────────────────────────────────────

@(
    "$root\sounds",
    "$root\skills",
    "$root\telemetry\sessions",
    "$root\telemetry\reports",
    "$root\templates"
) | ForEach-Object {
    if (-not (Test-Path $_)) {
        New-Item $_ -ItemType Directory -Force | Out-Null
        Write-Host "Created $_"
    }
}

# ── 2. settings.json paths are machine-agnostic — nothing to patch ───────────
#
# settings.json hook commands resolve $USERPROFILE at runtime (they run via
# bash), and the .ps1 scripts resolve $HOME, so there is no hardcoded username
# left to rewrite per-machine.

# ── 3. Generate sound files from Windows Media at 80% volume ─────────────────

$windows_media = "C:\Windows\Media"
$sounds_dir    = "$root\sounds"

function Set-WavVolume {
    param([string]$src, [string]$dst, [double]$scale = 0.8)
    if (Test-Path $dst) { return }
    if (-not (Test-Path $src)) { Write-Warning "Source not found: $src"; return }
    $bytes = [System.IO.File]::ReadAllBytes($src)
    $data_pos = 0
    for ($i = 12; $i -lt $bytes.Length - 4; $i++) {
        if ($bytes[$i] -eq 0x64 -and $bytes[$i+1] -eq 0x61 -and $bytes[$i+2] -eq 0x74 -and $bytes[$i+3] -eq 0x61) {
            $data_pos = $i + 8; break
        }
    }
    if ($data_pos -eq 0) { Copy-Item $src $dst; return }
    for ($i = $data_pos; $i -lt $bytes.Length - 1; $i += 2) {
        $sample = [System.BitConverter]::ToInt16($bytes, $i)
        $scaled = [Math]::Max(-32768, [Math]::Min(32767, [int]($sample * $scale)))
        $scaled_bytes = [System.BitConverter]::GetBytes([int16]$scaled)
        $bytes[$i]   = $scaled_bytes[0]
        $bytes[$i+1] = $scaled_bytes[1]
    }
    [System.IO.File]::WriteAllBytes($dst, $bytes)
    Write-Host "Generated $(Split-Path $dst -Leaf) at $([int]($scale*100))% volume"
}

Set-WavVolume "$windows_media\Windows Notify.wav" "$sounds_dir\notify-half.wav"
Set-WavVolume "$windows_media\chimes.wav"          "$sounds_dir\ring-half.wav"
Set-WavVolume "$windows_media\Windows Ding.wav"   "$sounds_dir\ding-half.wav"

# ── 4. Install Pester 5 for classification tests ─────────────────────────────

$pester = Get-Module -ListAvailable -Name Pester | Sort-Object Version -Descending | Select-Object -First 1
if (-not $pester -or $pester.Version -lt [version]'5.0') {
    Write-Host "Installing Pester 5..." -ForegroundColor Yellow
    # NuGet provider is required by Install-Module
    if (-not (Get-PackageProvider -Name NuGet -ErrorAction SilentlyContinue)) {
        Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Force -Scope CurrentUser | Out-Null
    }
    Install-Module Pester -Force -Scope CurrentUser -SkipPublisherCheck -MinimumVersion 5.0
    Write-Host "Pester installed."
} else {
    Write-Host "Pester $($pester.Version) already installed."
}

# ── 5. Install pre-commit hook ────────────────────────────────────────────────

$git_hooks_dir = "$root\.git\hooks"
$hook_src      = "$root\hooks\pre-commit"
if ((Test-Path $git_hooks_dir) -and (Test-Path $hook_src)) {
    Copy-Item $hook_src "$git_hooks_dir\pre-commit" -Force
    Write-Host "Pre-commit hook installed."
} else {
    Write-Host "Skipped pre-commit hook (no .git directory — run after git init)." -ForegroundColor Yellow
}

# ── Done ──────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Fully quit and reopen Claude Code (not just a new terminal)" -ForegroundColor Cyan
Write-Host "  2. In Claude Code, run /hooks to confirm the hooks loaded" -ForegroundColor Cyan
Write-Host "  3. The /retrospect skill will appear in the / menu after restart" -ForegroundColor Cyan
Write-Host ""
Write-Host "Run tests anytime: powershell.exe -File `"$root\tests\run-tests.ps1`"" -ForegroundColor Yellow
