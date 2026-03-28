# setup.ps1
# Bootstrap ~\.claude on a new Windows machine.
# Run once after cloning the dotfiles repo to C:\Users\<user>\.claude
# Usage: powershell.exe -NoProfile -ExecutionPolicy Bypass -File setup.ps1

$root = "$env:USERPROFILE\.claude"

# Ensure required directories exist
@(
    "$root\sounds",
    "$root\telemetry\sessions",
    "$root\telemetry\reports",
    "$root\templates"
) | ForEach-Object {
    if (-not (Test-Path $_)) {
        New-Item $_ -ItemType Directory -Force | Out-Null
        Write-Host "Created $_"
    }
}

# Copy Windows system sounds at 80% amplitude into sounds\
# Requires the WAV files to either be committed to the repo (preferred)
# or regenerated from the Windows media library here.
$windows_media = "C:\Windows\Media"
$sounds_dir    = "$root\sounds"

function Set-WavVolume {
    param([string]$src, [string]$dst, [double]$scale = 0.8)
    if (Test-Path $dst) { return }
    if (-not (Test-Path $src)) { Write-Warning "Source not found: $src"; return }
    $bytes = [System.IO.File]::ReadAllBytes($src)
    # Find 'data' chunk (PCM samples start after the 8-byte chunk header)
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

Set-WavVolume "$windows_media\Windows Notify.wav"  "$sounds_dir\notify-half.wav"
Set-WavVolume "$windows_media\chimes.wav"            "$sounds_dir\ring-half.wav"
Set-WavVolume "$windows_media\Windows Ding.wav"     "$sounds_dir\ding-half.wav"

# Install Pester 5 for classification tests
$pester = Get-Module -ListAvailable -Name Pester | Sort-Object Version -Descending | Select-Object -First 1
if (-not $pester -or $pester.Version -lt [version]'5.0') {
    Write-Host "Installing Pester 5..." -ForegroundColor Yellow
    Install-Module Pester -Force -Scope CurrentUser -SkipPublisherCheck -MinimumVersion 5.0
    Write-Host "Pester installed."
} else {
    Write-Host "Pester $($pester.Version) already installed."
}

# Install pre-commit hook
$git_hooks_dir = "$root\.git\hooks"
$hook_src      = "$root\hooks\pre-commit"
if ((Test-Path $git_hooks_dir) -and (Test-Path $hook_src)) {
    Copy-Item $hook_src "$git_hooks_dir\pre-commit" -Force
    Write-Host "Pre-commit hook installed."
} else {
    Write-Host "Skipped pre-commit hook (no .git directory found — run after git init)." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Setup complete. Open a new Claude Code session to activate hooks." -ForegroundColor Green
Write-Host "If hooks don't fire, open /hooks in Claude Code to reload settings." -ForegroundColor Yellow
Write-Host "Run tests anytime: powershell.exe -File `"$root\tests\run-tests.ps1`"" -ForegroundColor Cyan
