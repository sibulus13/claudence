# open-in-cursor.ps1 — open a clicked file (from WezTerm's open-uri handler) in
# Cursor at its line. Markdown files additionally flip to the built-in preview.
#
# $Target is "<path>", "<path>:<line>", or "<path>:<line>:<col>".
param([Parameter(Mandatory = $true)][string]$Target)

$ErrorActionPreference = 'SilentlyContinue'

# Resolve the Cursor CLI (.cmd shim).
$cursor = 'C:\Program Files\cursor\resources\app\bin\cursor.cmd'
if (-not (Test-Path $cursor)) {
  $g = Get-Command cursor -ErrorAction SilentlyContinue
  if ($g) { $cursor = $g.Source } else { return }
}

# Open in the existing window and jump to the line[:col].
& $cursor -r -g $Target | Out-Null

# Markdown → switch to the built-in preview. There's no CLI flag for it, so send
# Ctrl+Shift+F8 — a DEDICATED binding (in Cursor's keybindings.json) scoped to
# `editorLangId == markdown && editorTextFocus` → markdown.showPreview. Unlike
# Ctrl+Shift+V (which is paste in terminals), this chord is inert outside a
# markdown editor, so a mistimed keystroke can never paste/run anything. Sent
# only once Cursor is the foreground window.
$bare = $Target -replace ':\d+(?::\d+)?$', ''
if ($bare -match '\.(md|markdown|mdx)$') {
  Add-Type -AssemblyName System.Windows.Forms
  if (-not ('Native.Win32Fg' -as [type])) {
    Add-Type -Namespace Native -Name Win32Fg -MemberDefinition @'
[DllImport("user32.dll")] public static extern System.IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern int GetWindowThreadProcessId(System.IntPtr hWnd, out int procId);
'@
  }
  # Wait up to ~6s for Cursor to come to the foreground, then send the chord.
  for ($i = 0; $i -lt 50; $i++) {
    Start-Sleep -Milliseconds 120
    $procId = 0
    [void][Native.Win32Fg]::GetWindowThreadProcessId([Native.Win32Fg]::GetForegroundWindow(), [ref]$procId)
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($proc -and $proc.ProcessName -like '*ursor*') {
      Start-Sleep -Milliseconds 200
      [System.Windows.Forms.SendKeys]::SendWait('^+{F8}')
      break
    }
  }
}
