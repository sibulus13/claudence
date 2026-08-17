# Alt+O repo launcher — coverage contract.
#
# discover_repos() keys on a `.git` child, so a project that lives INSIDE another
# repo (Life/pylon) or behind a prune (_Misc/Music/spotifyDL) is invisible to the
# launcher unless it is listed in EXTRA_PROJECTS. These tests assert the three
# ways that coverage silently rots:
#   1. an EXTRA_PROJECTS path is renamed/moved  -> entry vanishes from the launcher
#   2. a REPO_ALIASES key no longer resolves    -> product name unsearchable
#   3. a pinned favorite is not discoverable    -> star pinned to nothing
#
# The Lua tables are parsed out of terminal.lua rather than duplicated here, so
# the test tracks the config instead of a copy of it.

BeforeAll {
    $script:TerminalLua = Join-Path $env:USERPROFILE '.claude/terminal.lua'
    $script:Src = Get-Content $script:TerminalLua -Raw

    # Repo root comes from the gitignored terminal.local.lua, same as WezTerm does.
    $localLua = Join-Path $env:USERPROFILE '.claude/terminal.local.lua'
    $script:RepoRoot = if (Test-Path $localLua) {
        ([regex]::Match((Get-Content $localLua -Raw), "repo_root\s*=\s*'([^']+)'")).Groups[1].Value
    } else { '' }
    if (-not $script:RepoRoot) { $script:RepoRoot = Join-Path $env:USERPROFILE 'repo' }
    $script:RepoRoot = $script:RepoRoot -replace '/', '\'

    function Get-LuaTableBody([string]$Name) {
        $m = [regex]::Match($script:Src, "(?s)local\s+$Name\s*=\s*\{(.*?)\r?\n\}")
        if (-not $m.Success) { throw "table '$Name' not found in terminal.lua" }
        # Strip line comments so a commented-out entry is not read as live.
        ($m.Groups[1].Value -split "`n" | ForEach-Object { ($_ -split '--')[0] }) -join "`n"
    }

    # EXTRA_PROJECTS = { 'Life/pylon', ... }
    $script:ExtraProjects = [regex]::Matches((Get-LuaTableBody 'EXTRA_PROJECTS'), "'([^']+)'") |
        ForEach-Object { $_.Groups[1].Value }

    # REPO_ALIASES = { ['web/cashcow'] = 'Tarive', ... }
    $script:AliasKeys = [regex]::Matches((Get-LuaTableBody 'REPO_ALIASES'), "\['([^']+)'\]") |
        ForEach-Object { $_.Groups[1].Value }

    # Everything the launcher would list: the pruned git walk + EXTRA_PROJECTS.
    # Mirrors the PowerShell embedded in discover_repos().
    function Get-LauncherRels([switch]$WalkOnly) {
        $r = $script:RepoRoot
        $prune = @{'node_modules'=1;'.git'=1;'dist'=1;'.next'=1;'build'=1;'out'=1;
            '.worktrees'=1;'archive'=1;'_Misc'=1;'example'=1;'examples'=1;'.venv'=1;
            'venv'=1;'__pycache__'=1;'target'=1;'obj'=1;'.turbo'=1;'.cache'=1}
        $o = New-Object System.Collections.Generic.List[string]
        $s = New-Object System.Collections.Generic.Stack[object]
        $s.Push(@{P=$r;D=0})
        while ($s.Count) {
            $c = $s.Pop()
            if (Test-Path -LiteralPath (Join-Path $c.P '.git')) { $o.Add($c.P) }
            if ($c.D -ge 4) { continue }
            try {
                foreach ($d in [System.IO.Directory]::EnumerateDirectories($c.P)) {
                    $n = [System.IO.Path]::GetFileName($d)
                    if ($prune.ContainsKey($n)) { continue }
                    $s.Push(@{P=$d;D=$c.D+1})
                }
            } catch {}
        }
        if (-not $WalkOnly) {
            foreach ($e in $script:ExtraProjects) {
                $q = Join-Path $r ($e -replace '/', '\')
                if (Test-Path -LiteralPath $q -PathType Container) { $o.Add($q) }
            }
        }
        # Absolute -> repo-relative, forward-slashed: the launcher's `rel` key.
        $o | Sort-Object -Unique | ForEach-Object {
            if ($_.Length -gt $r.Length) { ($_.Substring($r.Length + 1)) -replace '\\', '/' }
        }
    }

    $script:Rels = @(Get-LauncherRels)
    $script:RelsLower = @($script:Rels | ForEach-Object { $_.ToLower() })
}

Describe 'Alt+O launcher: EXTRA_PROJECTS' {
    It 'lists at least one non-repo project (the table is wired up at all)' {
        $script:ExtraProjects.Count | Should -BeGreaterThan 0
    }

    It 'points every entry at a directory that still exists' {
        $missing = $script:ExtraProjects | Where-Object {
            -not (Test-Path -LiteralPath (Join-Path $script:RepoRoot ($_ -replace '/', '\')) -PathType Container)
        }
        $missing -join ', ' | Should -BeNullOrEmpty
    }

    It 'uses forward slashes, matching the rel keys the launcher compares against' {
        ($script:ExtraProjects | Where-Object { $_ -match '\\' }) -join ', ' | Should -BeNullOrEmpty
    }

    It 'lists only paths the pruned git walk misses (every entry earns its row)' {
        # Being a git repo is not disqualifying — spotifyDL is one, it just sits
        # under the pruned _Misc. What would be redundant is an entry the WALK
        # already returns; that entry should be deleted, not carried here.
        $walk = @(Get-LauncherRels -WalkOnly | ForEach-Object { $_.ToLower() })
        $redundant = $script:ExtraProjects | Where-Object { $walk -contains $_.ToLower() }
        $redundant -join ', ' | Should -BeNullOrEmpty
    }
}

Describe 'Alt+O launcher: coverage' {
    It 'surfaces Crucible (Stock/Research 2026), which the git walk finds' {
        $script:RelsLower | Should -Contain 'stock/research 2026'
    }

    It 'surfaces Life/pylon, which lives inside the Life repo' {
        $script:RelsLower | Should -Contain 'life/pylon'
    }

    It 'still surfaces a plain top-level repo' {
        $script:RelsLower | Should -Contain 'ai/nuwa'
    }
}

Describe 'Alt+O launcher: REPO_ALIASES' {
    It 'keys every alias to a path the launcher actually lists' {
        # A dead key means the product name (Crucible, Cortex) is unsearchable.
        $orphans = $script:AliasKeys | Where-Object { $script:RelsLower -notcontains $_ }
        $orphans -join ', ' | Should -BeNullOrEmpty
    }

    It 'stores keys lower-cased and forward-slashed, as the lookup expects' {
        ($script:AliasKeys | Where-Object { $_ -cne $_.ToLower() -or $_ -match '\\' }) -join ', ' |
            Should -BeNullOrEmpty
    }

    It 'renders the product name alongside the path in the launcher label' {
        $script:Src | Should -Match "alias and \(alias \.\."
    }
}

Describe 'Alt+O launcher: pinned favorites' {
    BeforeAll {
        $cfgPath = Join-Path $env:USERPROFILE '.claude/repos.json'
        $script:Favorites = if (Test-Path $cfgPath) {
            @((Get-Content $cfgPath -Raw | ConvertFrom-Json).favorites)
        } else { @() }
    }

    It 'can reach every pinned favorite from the launcher' {
        # Alt+P pins by tab title, which can name a path discover_repos never
        # returns — the star then points at a row that is never drawn.
        $dead = $script:Favorites | Where-Object { $_ -and $script:RelsLower -notcontains $_.ToLower() }
        $dead -join ', ' | Should -BeNullOrEmpty
    }
}
