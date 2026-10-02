# open-in-vscode.ps1 — open a clicked file (from WezTerm's open-uri handler) in the
# owner's preferred app (owner rule, 2026-10-02):
#   - code, text and markdown -> VS Code at its line (markdown flips to preview);
#   - scripts/executables     -> VS Code, ALWAYS (the OS default would RUN them);
#   - anything else with a Windows default app (video, image, PDF, audio...) -> that app;
#   - no default app          -> VS Code.
#
# $Target is "<path>", "<path>:<line>", or "<path>:<line>:<col>".
# -DryRun prints the chosen opener instead of launching (for testing).
param([Parameter(Mandatory = $true)][string]$Target, [switch]$DryRun)

$ErrorActionPreference = 'SilentlyContinue'

$bare = $Target -replace ':\d+(?::\d+)?$', ''
$ext = [System.IO.Path]::GetExtension($bare).ToLowerInvariant()
$inEditor = @('.md', '.markdown', '.mdx', '.txt', '.log', '.json', '.jsonl', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.csv', '.tsv', '.xml', '.html', '.css', '.scss',
  '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx', '.py', '.lua', '.rs', '.go', '.java', '.cs', '.c', '.h', '.cpp', '.sql', '.sh', '.c4', '.env', '.gitignore', '')
$executable = @('.ps1', '.psm1', '.bat', '.cmd', '.exe', '.msi', '.vbs', '.vbe', '.wsf', '.wsh', '.jse', '.hta', '.scr', '.com', '.lnk', '.reg', '.dll')

function Get-DefaultApp([string]$e) {
  $choice = (Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\$e\UserChoice" -ErrorAction SilentlyContinue).ProgId
  if ($choice) { return $choice }
  $progId = (Get-ItemProperty "Registry::HKEY_CLASSES_ROOT\$e" -ErrorAction SilentlyContinue).'(default)'
  if ($progId) { return $progId }
  return $null
}

$useDefault = (Test-Path -LiteralPath $bare -PathType Leaf) -and ($inEditor -notcontains $ext) -and ($executable -notcontains $ext) -and (Get-DefaultApp $ext)
if ($DryRun) { if ($useDefault) { "default:$(Get-DefaultApp $ext)" } else { 'vscode' }; return }
if ($useDefault) { Invoke-Item -LiteralPath $bare; return }

# Resolve the VS Code CLI (.cmd shim).
$code = "$env:LOCALAPPDATA\Programs\Microsoft VS Code\bin\code.cmd"
if (-not (Test-Path $code)) {
  $g = Get-Command code -ErrorAction SilentlyContinue
  if ($g) { $code = $g.Source } else { return }
}

# Open in the existing window and jump to the line[:col].
& $code -r -g $Target | Out-Null

# Markdown → switch to the built-in preview. There's no CLI flag for it, so send
# Ctrl+Shift+F8 — a DEDICATED binding (in VS Code's keybindings.json) scoped to
# `editorLangId == markdown && editorTextFocus` → markdown.showPreview. Unlike
# Ctrl+Shift+V (which is paste in terminals), this chord is inert outside a
# markdown editor, so a mistimed keystroke can never paste/run anything. Sent
# only once VS Code is the foreground window.
$bare = $Target -replace ':\d+(?::\d+)?$', ''
if ($bare -match '\.(md|markdown|mdx)$') {
  Add-Type -AssemblyName System.Windows.Forms
  if (-not ('Native.Win32Fg' -as [type])) {
    Add-Type -Namespace Native -Name Win32Fg -MemberDefinition @'
[DllImport("user32.dll")] public static extern System.IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern int GetWindowThreadProcessId(System.IntPtr hWnd, out int procId);
'@
  }
  # Wait up to ~6s for VS Code to come to the foreground, then send the chord.
  for ($i = 0; $i -lt 50; $i++) {
    Start-Sleep -Milliseconds 120
    $procId = 0
    [void][Native.Win32Fg]::GetWindowThreadProcessId([Native.Win32Fg]::GetForegroundWindow(), [ref]$procId)
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($proc -and $proc.ProcessName -like '*Code*') {
      Start-Sleep -Milliseconds 200
      [System.Windows.Forms.SendKeys]::SendWait('^+{F8}')
      break
    }
  }
}
