---
id: project-manifest
type: feature
standard: 3
tier: T2
risk: [contract, enforcement, data]
status: draft
touches: [harness]
layers: {architecture: none, component: none, functional: none, data: none}
created: "2026-11-03"
owner: harness
---
# Project manifest: one source of truth per fact, process flags, and a checked update cycle

```mermaid
flowchart TD
  F["fleet defaults, versioned (claudence)"] --> E["effective config: merged view"]
  R["repo manifest: catalog-info.yaml (owner-only)"] --> E
  E --> H["harness: checker, gate, session hook"]
  E --> FW["Foreman and Catwalk"]
  D["derived facts: path, theme, branch"] --> E
  X["drift check: manifest vs reality"] -. "reports" .-> R
```

## Decisions (one-way doors)

| # | Decision | Status | Choice | Alternatives | Why it is hard to reverse |
|---|---|---|---|---|---|
| D-B | One source of truth for config | **confirmed** (owner 2026-11-03, D45) | every fact has exactly one writable home; other places read through or are generated | facts copied wherever needed (today) | every reader in the harness, Foreman and Catwalk moves to it |
| D-I | The repo file | open, recommended | `catalog-info.yaml` at the repo root, Backstage-shaped, with the fleet's keys in one `fleet:` block; it `extends` a pinned fleet-defaults version | a `.claude/` file; keys in CLAUDE.md | 28 repos carry it; Foreman, Catwalk and the gate parse it |
| D-J | Process flags | open, recommended | `processes: {v2, v3, loop}`, each `on`, `frozen` or `off`; fleet default v2 `on`, v3 `on`, loop `off`; a repo overrides | one global switch | the checker, the gate and dispatch read them |
| D-K | Who may change the manifest | open, recommended | owner only: the guard refuses agent edits to `catalog-info.yaml` and the fleet defaults | any agent with review | a manifest edit can lower a repo's caution |

## Purpose

Per-project facts live in many copies that already disagree: the tier in CLAUDE.md and in STATE.md, read by five
parsers; three of six Foreman gate commands differ from their repos; `repos.json` has two writers and two schemas
(config inventory, `evidence/probe.md`). The owner wants one source of truth for every config and core fact, a known
creation and update cycle, and feature flags that cut a process version off from the harness (owner, 2026-11-03).

## Goals and non-goals

- Goal: every fact is classified (per repo, fleet default with override, by reference, derived, or state) and has
  one writable home.
- Goal: one effective-config view that agents and humans read instead of raw files.
- Goal: process flags (`v2`, `v3`, `loop`) that the checker, the gate and dispatch obey.
- Goal: the manifest stays true: it is created at intake, changed only by the owner, schema-checked on every commit
  that touches it, and compared with reality on a schedule and before every deploy.
- Non-goal: secrets (env var names only, never values); state such as `reviewQueue` and `backlogItems` (stays in
  STATE.md); Catwalk UI changes (owner-gated).

## Background

- **Single source of truth**: each fact has one writable place; every other appearance reads from it or is generated.
- **Defaults plus override**: a repo file points to a pinned shared base and holds only what differs.
- **Effective config**: a command that prints the merged result, so nobody "fixes" a value set upstream.
- **Schema gate and drift gate**: a schema check on every change, and a separate check of the file against reality.

<details>
<summary>Detail and sources</summary>

- Defaults plus override: Renovate presets (`extends`, pinned by version), ESLint shareable configs, Kustomize
  bases and overlays; each tool merges arrays differently, so merge rules are stated per field.
- Effective config: Renovate `printConfig`, ESLint `--print-config`, `kustomize build`, `nx show project`.
- Schema and drift: RoadieHQ Backstage entity validator, `renovate-config-validator --strict`, `cue vet`;
  `terraform plan -refresh-only`, OpenSSF Scorecard. Backstage keeps the last good descriptor when a new one fails,
  so a broken edit stays invisible unless the commit is checked.
- Catalog rot: a descriptor stays true only when an existing gate reads it; derive what code can tell, hand-write
  only human facts (owner, lifecycle, tier, purpose).
- Notes: `D:/repo/docs/research_notes/Project manifest/` (web_config_sot.md, config_inventory.md).

</details>

### Where each fact lives

| Class | Facts | Home | Changed when |
|---|---|---|---|
| Per repo (1:1) | profile (`yolo`, `public`, `revenue`), gate command, archived, depends-on, post-merge steps, deploy target and URL, notification source | `catalog-info.yaml` `fleet:` block | intake; a profile change (first public user, first payment); archive; deploy setup |
| Fleet default, repo may override | process flags, autonomy (derived from profile), package manager, docs root, state-doc path, owner, size limits | `~/.claude/contracts/fleet-defaults.v1.yaml`, pinned by version; override in the repo file | fleet decision (owner); a repo's exception |
| By reference (pointed to, never copied) | spec standard, contracts, theme rules, `.env.example`, settings and hooks, TeleFi commands | a path or contract id in the manifest | when the referenced file changes, nothing in the manifest does |
| Derived (computed, never written) | repo path, theme, remote, default branch, `deploymentTier` (from profile: `revenue` is `live`) | the effective-config view | never stored |
| State (not config) | `reviewQueue`, `backlogItems`, phase | `docs/STATE.md` | as work moves |

## Approach

Baseline: today's copies (CLAUDE.md tier line, STATE.md, `~/.foreman/repos.json`, `.pre-commit-config.yaml`).

| Dimension | A: keep copies, add a sync check | B: recommended (one manifest, defaults by reference, effective view) | C: a central registry only (`repos.json`) |
|---|---|---|---|
| Disagreement between copies | 0 detected, still possible | + impossible: one writable home | + |
| Lives with the repo | 0 | + in git, reviewed with the code | - outside the repo |
| Readers to change | + none | - five parsers move to one reader | - |
| Owner control | 0 | + guard-protected file | 0 |
| Reversibility | + | 0 the old copies become generated | - |
| Build complexity | + | - schema, two readers, migration, drift check | 0 |

Chosen: **B**.

## Milestones

```mermaid
flowchart TD
  P1["P1 walking skeleton: schema, defaults, reader, effective view"] --> P2["P2 process flags enforced"]
  P1 --> P3["P3 Foreman and Catwalk read the manifest"]
  P2 --> P4["P4 migrate all repos, retire copies"]
  P3 --> P4
  P4 --> P5["P5 drift checks: scheduled and before deploy"]
  classDef planned fill:#eeeeee,color:#333,stroke:#9e9e9e
  class P1,P2,P3,P4,P5 planned
```

| Milestone | Status | Slice (what works after it) | Depends on | Owns | Outer test (red first) | Unblocks |
|---|---|---|---|---|---|---|
| P1 | planned | the schema, fleet defaults and Python reader exist; `fleet config <repo>` prints the effective config with each value's source; claudence and cashcow have manifests; `spec_v3` reads the profile from it | - | `contracts/project-manifest.v1.json`, `contracts/fleet-defaults.v1.yaml`, `scripts/manifest.py` | AC-1 | agentic-loop M2 (profiles) |
| P2 | planned | the checker and gate obey `processes`; dispatch drafts only in an `on` version; the session hook shows the flags | P1 | `scripts/spec_check.py`, `scripts/spec_gate.py`, `hooks/session_context.py` | AC-4 | process versions cut off by flag |
| P3 | planned | Foreman and Catwalk read tier, profile, gate command and autonomy through a JS reader tested on the same fixtures | P1 | `D:/repo/Factory/foreman/core/manifest.js`, `D:/repo/Factory/catwalk/src/lib/manifest.ts` | AC-6 | one tier for every reader |
| P4 | planned | every repo has a manifest generated from today's copies and reviewed by the owner; the CLAUDE.md tier line and STATE.md tier are removed or generated; the three gate-command mismatches are fixed | P2, P3 | `scripts/manifest_migrate.py` | AC-8 | the copies stop drifting |
| P5 | planned | a scheduled drift check compares each manifest with reality and reports through TeleFi; a deploy for `public` or `revenue` is refused while its drift report is not clean | P4 | `scripts/manifest_drift.py` | AC-10 | the manifest stays true |

## Contracts

| Name | Version | Schema | Fixtures |
|---|---|---|---|
| repo manifest (`catalog-info.yaml` `fleet:` block) | v1 | `contracts/project-manifest.v1.json` | `contracts/fixtures/manifest-*.yaml` |
| fleet defaults and merge rules per field | v1 | `contracts/fleet-defaults.v1.yaml` | `contracts/fixtures/defaults-*.yaml` |
| effective config (the merged view, each value with its source) | v1 | `contracts/effective-config.v1.json` | `contracts/fixtures/effective-*.json` |
| drift report | v1 | `contracts/manifest-drift.v1.json` | `contracts/fixtures/drift-*.json` |

## Behaviour

| AC | Traces | Given / when | Pass when | Fail when | Test |
|---|---|---|---|---|---|
| AC-1 | P1 | `fleet config` on a repo with a manifest that overrides one default | prints every fact with its value and source (default, override, derived) | a value or its source is wrong | tests/test_project_manifest.py |
| AC-2 | P1, D-I | manifests: valid; an unknown key; a wrong type; a profile outside the enum; an `extends` naming no pinned version | valid read; each other refused by name | a bad manifest is read | tests/test_project_manifest.py |
| AC-3 | P1, D-B | a repo with a manifest and a stale CLAUDE.md tier line | every harness reader takes the manifest's value | any reader uses the copy | tests/test_project_manifest.py |
| AC-4 | P2, D-J | each process at `on`, `frozen` and `off`: a new item, a status move of an existing item, a dispatch | `on` allows all; `frozen` refuses only the new item; `off` refuses new items and moves and dispatch names the flag | a flag is ignored | tests/test_project_manifest.py |
| AC-5 | P2, D-K | an agent edit to `catalog-info.yaml` or the fleet defaults | the guard refuses it | it lands | tests/test_project_manifest.py |
| AC-6 | P3 | the same fixtures through the Python and JS readers | identical effective config | they differ | tests/test_project_manifest.py |
| AC-7 | P3 | Foreman merging in a repo whose manifest gate command differs from `repos.json` | Foreman runs the manifest's command | it runs the stale one | tests/test_project_manifest.py |
| AC-8 | P4 | the migration on a temp copy of every repo | each manifest is valid, every fact has one home, the diff is shown for owner review, nothing is committed without it | a fact is lost or a copy left writable | tests/test_project_manifest.py |
| AC-9 | P4, compatibility | every v2 and v3 item in the fleet after migration | judged exactly as before | any result changes | tests/test_project_manifest.py |
| AC-10 | P5 | drift fixtures: a lockfile for a package manager other than the manifest's; a gate command missing from `package.json`; a `yolo` repo with live payment keys named in its env example; a clean repo | each mismatch reported by name; the clean one silent | a mismatch is missed | tests/test_project_manifest.py |
| AC-11 | P5 | a deploy of a `revenue` repo with an open drift report, then a clean one | refused, then allowed | otherwise | tests/test_project_manifest.py |
| AC-12 | docs | SPEC-STANDARD-V3.md, the dispatch playbook, DEVELOPMENT_LIFECYCLE.md | each names the manifest as the source of every per-project fact | a doc names a copy | tests/test_project_manifest.py |

## Outcomes

| Dimension | Level | Row or n/a reason | AC |
|---|---|---|---|
| success | L3 | every reader gets one value with its source | AC-1 |
| invalid input | L3 | malformed manifests are refused by name | AC-2 |
| dependency fails | L3 | a missing manifest falls back to the tier's profile, never to a looser one | AC-3 |
| timeout | L1 | the reader is a file parse with no network or waits | |
| crash mid-step | L3 | the migration writes nothing until the owner accepts its diff | AC-8 |
| concurrent actor | L3 | only the owner may edit the manifest | AC-5 |
| duplicate or replay | L1 | re-running the reader or the migration on the same files gives the same result | |
| arrival channel | L3 | flags apply to commits, merges and dispatches alike | AC-4 |
| performance or cost | L1 | a single small file per repo is parsed on demand | |
| security | L3 | a repo cannot lower its own caution: owner-only edits, `live` never below `revenue` | AC-5 |
| data and compatibility | L3 | existing items are judged unchanged after migration | AC-9 |
| operability | L3 | drift is reported and blocks deploys of `public` and `revenue` repos | AC-11 |

## Assumptions

| Assumption | Observed | If violated |
|---|---|---|
| Backstage allows a custom `fleet:` block in `catalog-info.yaml` | `D:/repo/docs/research_notes/Project manifest/web_config_sot.md:1` | flag: if not, the block moves under `metadata.annotations` or a sibling file named in the descriptor |
| The guard can protect a file outside `.claude/` | `C:/Users/Michael/.claude/hooks/guard.py:1` | refuse: P2 does not ship until AC-5 passes |
| Foreman and Catwalk can read a repo file at merge and render time | `D:/repo/docs/research_notes/Project manifest/config_inventory.md:1` | defer: P3 keeps `repos.json` as a generated cache |

## Probe

[Probe](evidence/probe.md): the owner's D-B answer verbatim, the config inventory and the web practice.
