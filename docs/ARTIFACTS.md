# Published artifacts — tooling and method

The register for artifacts that are **not about a specific project's subject matter**: tooling
notes, method comparisons, dotfiles documentation. Project artifacts live in that project's own
index — Envisio's is `~/repo/Envisio/knowledge-base/docs/ARTIFACTS.md`.

Artifacts are rendered HTML pages hosted on claude.ai, **private by default**, shareable from the
page's share menu. They live outside git, so **without this index they are unfindable**: a new
session has no memory of them and a URL nobody wrote down is gone. Sources live in
`docs/artifacts/` here, which is what makes them re-publishable.

Browse all of them at <https://claude.ai/code/artifacts>. Enumerate from a session with
`Artifact action: "list"`.

| Artifact | What it holds | Source | Updated |
|---|---|---|---|
| [**Hierarchical diagram tooling**](https://claude.ai/code/artifact/811c07fe-e359-4d9f-97e7-805c00864b03) | Which component systems give you click-to-drill hierarchy diagrams — LikeC4 · Structurizr · React Flow · d3-hierarchy · visx · Cytoscape — and when to hand-roll instead. Companion to the `/depth-tree` skill. | `docs/artifacts/hierarchy-diagram-tooling.html` | 2026-08-06 |
| [**Claudence on macOS**](https://claude.ai/code/artifact/8fa7c197-e39d-4628-a710-2836dd80d023) | The dotfiles port — what changed from the PowerShell originals and what is not carried over. Companion to `docs/MACOS-PORT.md`. | not kept locally | 2026-08-04 |

## Rules

- **Register in the same turn you publish.** An unindexed artifact is a lost artifact. This is not
  a tidy-up step to do later — later is a different session with no memory of the URL.
- **Which index.** About a project's subject → that project's index. About tooling, method, or this
  machine → here. If a project has no index and is accumulating artifacts, create one.
- **Keep the source in the repo.** A file path in git is what lets a future session redeploy to the
  same URL. Where no local source exists, say so in the table rather than leaving the column blank.
- **Update in place.** Republishing the same file path keeps the URL within a conversation; from any
  other conversation, pass the artifact's `url`. Publishing without it mints a *new* URL and
  silently orphans the old — the main way these get duplicated.
- **Keep the favicon stable** across redeploys; people find the tab by its icon.
- **Moving a source file does not move the artifact.** The URL belongs to the artifact, not the
  path. If you relocate the source, the next publish must pass the recorded `url` or it mints a
  fresh URL and orphans the old one. This happened on 2026-08-06 when the tooling note's source
  moved here from the Envisio knowledge base — `0ae4616e-2a77-4497-91ae-68b92ed2af33` is that
  orphan, superseded immediately and left unreferenced. The tool has no delete action, so a
  mistaken publish is permanent; check the returned URL against this table every time.
