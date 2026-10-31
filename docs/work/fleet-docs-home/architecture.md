# Architecture: one resolver for the fleet docs location

```mermaid
flowchart LR
  subgraph Before
    A1["fleet_status, path_pins, upkeep_config, repo_move, session_context, harness_lint"] --> P1["~/.claude/docs/fleet (literal in each)"]
    A2["tests, ledger SKILL"] --> P1
  end
  subgraph After
    B1["same readers"] --> RS["fleet_paths.fleet_docs_dir()"]
    RS --> EV["env FLEET_DOCS"]
    RS --> RR["REPO_ROOT / docs"]
    EV --> P2["D:/repo/docs"]
    RR --> P2
  end
```

Authoritative source: the location is one fact, owned by the resolver. `D:/repo` (`FLEET_ROOT` override) is owned by the same module as `REPO_ROOT`; `hooks/guard.py` imports it from there.

Not moved here: Cortex (`bin/upkeep.js`, `config/capabilities.json`, `agents/harness-steward.md`) hard-codes the old drafts dir outside this repo; the parent updates it together with the folder move.
