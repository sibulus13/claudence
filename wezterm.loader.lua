-- Installed by setup.sh as ~/.config/wezterm/wezterm.lua.
--
-- WezTerm only looks for its config at a fixed set of paths, and the real config
-- lives in the dotfiles checkout instead. This loader is the indirection: it
-- hands off to ~/.claude/terminal.lua (a symlink into the checkout), which
-- registers itself in WezTerm's reload watch list so saving terminal.lua still
-- triggers a live reload even though WezTerm never sees it as the entry point.
return dofile(os.getenv('HOME') .. '/.claude/terminal.lua')
