-- Template for terminal.local.lua (which is gitignored).
-- Copy this file to terminal.local.lua and set your machine-specific values:
--   cp terminal.local.example.lua terminal.local.lua
-- terminal.lua reads it at startup; values here are referenced, not committed.
return {
  -- Absolute path (forward slashes) to the folder the repo launcher (Alt+O)
  -- scans for git repos, and the default cwd for the Nexus home tab.
  repo_root = 'C:/path/to/your/repos',

  -- Optional. Display label per repo, keyed by the path relative to repo_root,
  -- forward-slashed and lowercased. Purely cosmetic — the tab keeps its real
  -- title, so session restore and Alt+G targeting are unaffected. Lives here
  -- because a folder-to-product mapping is usually private.
  repo_aliases = {
    ['web/legacy-folder-name'] = 'Product',
  },
}
