<!--
  Template for ~/.claude/CLAUDE.local.md — the machine- and client-specific half of the
  global instructions. setup.sh copies this to ~/.claude/CLAUDE.local.md if that file does
  not exist. It is never committed and is not symlinked into the claudence repo, so a
  client name cannot reach the public checkout by accident.

  The rule: ~/.claude/CLAUDE.md is generic and publishable. Anything naming a client, a
  tenant, a private project, or an absolute path on one machine lives here.

  Delete the sections you do not need — an empty file is a valid file.
-->

# Machine and client specifics

## Known repo placements

Concrete `~/repo/<Category>/<project>` decisions worth remembering, so the categorisation
rule in the global file has something to resolve against.

| Project | Path | Why this category |
|---|---|---|
| _example_ | `~/repo/AI/<project>` | media/AI pipeline |

## Client knowledge bases and doc mirrors

Feeds the **Local Knowledge First** ordering in the global file — step 2, "local mirrors of
team documentation".

| Client / org | Knowledge base | Wiki mirrors | Artifact index |
|---|---|---|---|
| _example_ | `~/repo/<Org>/knowledge-base` | `~/repo/<Org>/wikis/` | `docs/ARTIFACTS.md` in that repo |

## Reference implementations

Named so the global rules can point at a real example instead of describing one.

| Rule | Reference |
|---|---|
| Knowledge-lifecycle driver (front-matter validation, staleness, provenance) | `<repo>/drivers/index_docs.py` |
| Visual-first doc exemplar | `<path to a doc that does it well>` |

## Local surfaces and dashboards

Anything that exists only on this machine — dashboards, local hostnames, ports.

| Surface | Where |
|---|---|
| _example dashboard_ | _local URL or path_ |

## Anything else machine-bound

Absolute paths, hostnames, per-machine ports, local service credentials **by reference only**
— never paste a secret here; name the keychain entry or env var that holds it.
