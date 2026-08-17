# docs-root.tests.ps1 - coverage for scripts/resolve-docs-root.ps1
#
# Every case runs against a throwaway tree under $TestDrive, so the live registry and
# the real repos are never touched. The env seams (CLAUDE_DOCS_ROOT, CLAUDE_REPO_ROOT,
# CLAUDE_DOC_ROOTS_FILE) are cleared before each test and restored after the file.

BeforeAll {
    $script:Resolver = Join-Path $env:USERPROFILE '.claude/scripts/resolve-docs-root.ps1'

    $script:SavedDocsRoot = $env:CLAUDE_DOCS_ROOT
    $script:SavedRepoRoot = $env:CLAUDE_REPO_ROOT
    $script:SavedRegistry = $env:CLAUDE_DOC_ROOTS_FILE

    function Resolve-Docs([string] $Path) {
        & $script:Resolver -Path $Path -Json | ConvertFrom-Json
    }

    # A directory is "a repo" to the resolver when it holds a .git entry; a plain
    # directory named .git is enough, so the tests never have to shell out to git.
    function New-FakeRepo([string] $Path) {
        New-Item -ItemType Directory -Force -Path (Join-Path $Path '.git') | Out-Null
    }

    function New-Dir([string] $Path) {
        New-Item -ItemType Directory -Force -Path $Path | Out-Null
        return $Path
    }

    # Pester 5 forbids a BeforeEach at the container root, so each Describe calls this.
    function Reset-DocsEnv {
        $env:CLAUDE_DOCS_ROOT = $null
        $env:CLAUDE_REPO_ROOT = $null
        # Point the registry at a path that does not exist, so an unrelated test can
        # never pick up a pin from the live file.
        $env:CLAUDE_DOC_ROOTS_FILE = Join-Path $TestDrive 'no-such-registry.json'
    }
}

AfterAll {
    $env:CLAUDE_DOCS_ROOT      = $script:SavedDocsRoot
    $env:CLAUDE_REPO_ROOT      = $script:SavedRepoRoot
    $env:CLAUDE_DOC_ROOTS_FILE = $script:SavedRegistry
}

Describe 'resolve-docs-root: precedence chain' {
    BeforeEach { Reset-DocsEnv }

    It 'rule 4 (default): resolves to the nearest ancestor holding .git' {
        $repo = New-Dir (Join-Path $TestDrive 'proj')
        New-FakeRepo $repo
        $deep = New-Dir (Join-Path $repo 'src/components')

        $r = Resolve-Docs $deep
        $r.source | Should -Be 'git'
        $r.root   | Should -Be (($repo -replace '\\','/'))
        $r.docs   | Should -Be (($repo -replace '\\','/') + '/docs')
        $r.tracked | Should -BeTrue
    }

    It 'rule 4 picks the NEAREST repo, not an outer one' {
        $outer = New-Dir (Join-Path $TestDrive 'outer')
        New-FakeRepo $outer
        $inner = New-Dir (Join-Path $outer 'inner')
        New-FakeRepo $inner

        (Resolve-Docs $inner).root | Should -Be (($inner -replace '\\','/'))
    }

    It 'rule 1: CLAUDE_DOCS_ROOT overrides everything below it' {
        $repo = New-Dir (Join-Path $TestDrive 'envproj')
        New-FakeRepo $repo
        Set-Content -Path (Join-Path $repo '.claude-docs-root') -Value '' -Encoding utf8
        $env:CLAUDE_DOCS_ROOT = 'D:/elsewhere'

        $r = Resolve-Docs $repo
        $r.source | Should -Be 'env'
        $r.root   | Should -Be 'D:/elsewhere'
    }

    It 'rule 2: an EMPTY marker means "the folder the marker sits in"' {
        $outer = New-Dir (Join-Path $TestDrive 'markerouter')
        New-FakeRepo $outer
        $sub = New-Dir (Join-Path $outer 'workspace')
        Set-Content -Path (Join-Path $sub '.claude-docs-root') -Value '' -Encoding utf8

        $r = Resolve-Docs $sub
        $r.source | Should -Be 'marker'
        $r.root   | Should -Be (($sub -replace '\\','/'))
    }

    It 'rule 2: a marker beats the enclosing repo (the pylon-inside-Life case)' {
        $lifeRepo = New-Dir (Join-Path $TestDrive 'Life')
        New-FakeRepo $lifeRepo
        $pylon = New-Dir (Join-Path $lifeRepo 'pylon')
        Set-Content -Path (Join-Path $pylon '.claude-docs-root') -Value '' -Encoding utf8

        $r = Resolve-Docs (New-Dir (Join-Path $pylon 'Catalog'))
        $r.root   | Should -Be (($pylon -replace '\\','/'))
        $r.source | Should -Be 'marker'
        # Still version-controlled, but by the PARENT repo - the caller must be told.
        $r.tracked | Should -BeTrue
        $r.shared  | Should -BeTrue
        $r.vcsRoot | Should -Be (($lifeRepo -replace '\\','/'))
    }

    It 'rule 2: a marker holding a RELATIVE path resolves against the marker folder' {
        $repo = New-Dir (Join-Path $TestDrive 'relmarker')
        New-Dir (Join-Path $repo 'writeups') | Out-Null
        Set-Content -Path (Join-Path $repo '.claude-docs-root') -Value 'writeups' -Encoding utf8

        (Resolve-Docs $repo).root | Should -Be ((Join-Path $repo 'writeups') -replace '\\','/')
    }

    It 'rule 2: a marker holding an ABSOLUTE path is taken verbatim' {
        $repo = New-Dir (Join-Path $TestDrive 'absmarker')
        Set-Content -Path (Join-Path $repo '.claude-docs-root') -Value 'D:/pinned/place' -Encoding utf8

        (Resolve-Docs $repo).root | Should -Be 'D:/pinned/place'
    }

    It 'rule 2: the NEAREST marker wins over one further up' {
        $top = New-Dir (Join-Path $TestDrive 'nearmarker')
        Set-Content -Path (Join-Path $top '.claude-docs-root') -Value 'D:/top' -Encoding utf8
        $sub = New-Dir (Join-Path $top 'sub')
        Set-Content -Path (Join-Path $sub '.claude-docs-root') -Value 'D:/sub' -Encoding utf8

        (Resolve-Docs $sub).root | Should -Be 'D:/sub'
    }

    It 'rule 3: a registry pin beats the enclosing repo' {
        $repo = New-Dir (Join-Path $TestDrive 'pinned')
        New-FakeRepo $repo
        $ws = New-Dir (Join-Path $repo 'workspace')

        $registry = Join-Path $TestDrive 'registry.json'
        @{ ($ws -replace '\\','/') = 'D:/pinned/docs' } | ConvertTo-Json | Set-Content -Path $registry -Encoding utf8
        $env:CLAUDE_DOC_ROOTS_FILE = $registry

        $r = Resolve-Docs $ws
        $r.source | Should -Be 'registry'
        $r.root   | Should -Be 'D:/pinned/docs'
    }

    It 'rule 3: the LONGEST matching pin wins, so a child pin beats its parent' {
        $parent = New-Dir (Join-Path $TestDrive 'pinparent')
        $child  = New-Dir (Join-Path $parent 'child')

        $registry = Join-Path $TestDrive 'registry-longest.json'
        @{
            ($parent -replace '\\','/') = 'D:/parent-docs'
            ($child  -replace '\\','/') = 'D:/child-docs'
        } | ConvertTo-Json | Set-Content -Path $registry -Encoding utf8
        $env:CLAUDE_DOC_ROOTS_FILE = $registry

        (Resolve-Docs $child).root  | Should -Be 'D:/child-docs'
        (Resolve-Docs $parent).root | Should -Be 'D:/parent-docs'
    }

    It 'rule 3: a marker still outranks a registry pin' {
        $ws = New-Dir (Join-Path $TestDrive 'markerbeatspin')
        Set-Content -Path (Join-Path $ws '.claude-docs-root') -Value 'D:/from-marker' -Encoding utf8

        $registry = Join-Path $TestDrive 'registry-loses.json'
        @{ ($ws -replace '\\','/') = 'D:/from-registry' } | ConvertTo-Json | Set-Content -Path $registry -Encoding utf8
        $env:CLAUDE_DOC_ROOTS_FILE = $registry

        (Resolve-Docs $ws).root | Should -Be 'D:/from-marker'
    }

    It 'rule 5: an un-versioned workspace falls back to the repo-org Category/project folder' {
        $repoRoot = New-Dir (Join-Path $TestDrive 'reporoot')
        $project  = New-Dir (Join-Path $repoRoot 'Category/project')
        $deep     = New-Dir (Join-Path $project 'nested/deeper')
        $env:CLAUDE_REPO_ROOT = $repoRoot

        $r = Resolve-Docs $deep
        $r.source  | Should -Be 'repo-org'
        $r.root    | Should -Be (($project -replace '\\','/'))
        $r.tracked | Should -BeFalse
    }

    It 'rule 5 does not fire at the repo root itself (no Category/project to name)' {
        $repoRoot = New-Dir (Join-Path $TestDrive 'bareroot')
        $env:CLAUDE_REPO_ROOT = $repoRoot

        (Resolve-Docs $repoRoot).source | Should -Be 'fallback'
    }

    It 'rule 6: nothing matched reports source fallback, not a silent guess' {
        $orphan = New-Dir (Join-Path $TestDrive 'orphan/deep')
        $env:CLAUDE_REPO_ROOT = Join-Path $TestDrive 'somewhere-else'

        $r = Resolve-Docs $orphan
        $r.source | Should -Be 'fallback'
        $r.root   | Should -Be (($env:USERPROFILE -replace '\\','/') + '/.claude')
    }
}

Describe 'resolve-docs-root: record shape' {
    BeforeEach { Reset-DocsEnv }

    It 'names the two contract docs under the resolved root' {
        $repo = New-Dir (Join-Path $TestDrive 'shape')
        New-FakeRepo $repo

        $r = Resolve-Docs $repo
        $r.log     | Should -Be (($repo -replace '\\','/') + '/docs/SESSION_LOG.md')
        $r.journal | Should -Be (($repo -replace '\\','/') + '/docs/DECISIONS.md')
    }

    It 'flags an untracked root so the caller can warn instead of writing blind' {
        $plain = New-Dir (Join-Path $TestDrive 'notrack')
        Set-Content -Path (Join-Path $plain '.claude-docs-root') -Value '' -Encoding utf8

        $r = Resolve-Docs $plain
        $r.tracked | Should -BeFalse
        $r.vcsRoot | Should -BeNullOrEmpty
    }

    It 'normalises separators and strips a trailing slash' {
        $repo = New-Dir (Join-Path $TestDrive 'norm')
        New-FakeRepo $repo

        (Resolve-Docs ($repo + '\')).root | Should -Be (($repo -replace '\\','/'))
        (Resolve-Docs $repo).root         | Should -Not -Match '\\'
    }
}

Describe 'resolve-docs-root: hook output' {
    BeforeEach { Reset-DocsEnv }

    It 'emits SessionStart additionalContext naming the resolved log' {
        $repo = New-Dir (Join-Path $TestDrive 'hookproj')
        New-FakeRepo $repo

        $payload = @{ cwd = $repo } | ConvertTo-Json -Compress
        $out = $payload | powershell.exe -NoProfile -File $script:Resolver -Hook | ConvertFrom-Json

        $out.hookSpecificOutput.hookEventName | Should -Be 'SessionStart'
        $out.hookSpecificOutput.additionalContext | Should -Match 'SESSION_LOG\.md'
        $out.hookSpecificOutput.additionalContext | Should -Match 'DECISIONS\.md'
    }

    It 'warns when the resolved root is not under version control' {
        $plain = New-Dir (Join-Path $TestDrive 'hooknotrack')
        Set-Content -Path (Join-Path $plain '.claude-docs-root') -Value '' -Encoding utf8

        $payload = @{ cwd = $plain } | ConvertTo-Json -Compress
        $out = $payload | powershell.exe -NoProfile -File $script:Resolver -Hook | ConvertFrom-Json

        $out.hookSpecificOutput.additionalContext | Should -Match 'NOT under version control'
    }

    It 'notes when the docs would land in a repo shared with sibling projects' {
        $repo = New-Dir (Join-Path $TestDrive 'hookshared')
        New-FakeRepo $repo
        $ws = New-Dir (Join-Path $repo 'workspace')
        Set-Content -Path (Join-Path $ws '.claude-docs-root') -Value '' -Encoding utf8

        $payload = @{ cwd = $ws } | ConvertTo-Json -Compress
        $out = $payload | powershell.exe -NoProfile -File $script:Resolver -Hook | ConvertFrom-Json

        $out.hookSpecificOutput.additionalContext | Should -Match 'shares with sibling projects'
    }
}

Describe 'resolve-docs-root: live layout' {
    BeforeEach { Reset-DocsEnv }

    It 'sends a nested folder to its own project repo' {
        if (-not (Test-Path 'D:/repo/Stock/Research 2026/.git')) { Set-ItResult -Skipped -Because 'repo absent'; return }
        (Resolve-Docs 'D:/repo/Stock/Research 2026/dashboard-new').root | Should -Be 'D:/repo/Stock/Research 2026'
    }

    It 'sends a workspace with no VC of its own up to the repo that tracks it' {
        if (-not (Test-Path 'D:/repo/Life/.git')) { Set-ItResult -Skipped -Because 'repo absent'; return }
        $r = Resolve-Docs 'D:/repo/Life/karaoke'
        $r.root   | Should -Be 'D:/repo/Life'
        $r.source | Should -Be 'git'
    }

    It 'keeps claudence pointed at its own tree' {
        (Resolve-Docs (Join-Path $env:USERPROFILE '.claude')).root |
            Should -Be (($env:USERPROFILE -replace '\\','/') + '/.claude')
    }
}
