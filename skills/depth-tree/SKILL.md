---
name: depth-tree
description: Build a click-to-expand hierarchy artifact — a system, product, org, roadmap or codebase rendered as collapsible depth levels where every row advertises whether it opens. Use when asked for a zoomable, drill-down, nested, expandable or multi-level map, when a Mermaid diagram is about to become too big to read, or when the same content needs to work at both an executive and an engineer altitude. Triggers: "zoomable diagram", "drill down", "expand into", "high level then detail", "nested map", "hierarchical view", "make this explorable".
version: 1.0.0
---

# /depth-tree

Produce a self-contained HTML artifact where a subject is expressed as one hierarchy the
reader opens level by level, instead of as several diagrams they have to reconcile.

Assets in this skill directory:

| File | What it is |
|---|---|
| `template.html` | The whole thing. Copy it, edit `CONFIG` and `DATA`, publish. No dependencies, no build step. |

## When this is the right shape

Use it when the content is **genuinely a hierarchy** and the reader needs more than one
altitude — a product's capabilities, a codebase's modules, an org, a roadmap, an audit.
The win over a static diagram is that a proposal or a risk can sit **at the exact node it
attaches to** rather than in a separate list at the end.

Do **not** use it for:

- **A graph with cycles** — a system-context diagram where everything talks to everything.
  Use Mermaid `flowchart`.
- **A sequence over time** — Mermaid `sequenceDiagram`. Time is an axis, not a depth.
- **A comparison of options** — a table, or two diagrams side by side showing the one edge
  that differs.

Mixing is fine and often correct: the tree carries the drill-down, and one or two static
figures below it carry what the tree cannot. Do not bolt fake zoom controls onto those
figures — a CSS transform over an SVG is not zoom, it is a scaling bug waiting to be
reported.

## Steps

### 1. Find the real hierarchy before writing any HTML

Do not invent the top level. Derive it from something in the subject that already
enumerates it — a module switch, a nav, a route namespace, a directory layout, a set of
personas. Say in the artifact where the top level came from.

### 2. Copy the template

```
cp <this skill dir>/template.html <target>/<name>.html
```

Put it in the project's own repo where possible, not a scratch dir — the artifact URL is
stable across redeploys of the *same file path*, so a durable path is what lets you update
it later instead of minting a duplicate.

### 3. Fill `CONFIG`

Three things, all near the top of the `<script>`:

- **Chrome** — `eyebrow`, `title`, `standfirst`, `sources`. The standfirst must state the
  reading rule, because the affordance is the feature.
- **`types`** — the *kind* channel, 5–7 entries, each one hue number. Both light and dark
  themes derive from it, so adding a category is one line and never needs a second palette.
  Set `sat: "low"` for a deliberately muted kind, `hollow: true` for an outline dot,
  `accent: true` to tint the whole row.
- **`statuses`** — the *lifecycle* channel. **Source these from something real** — a
  feature-flag file, a roadmap, a ticket state machine — and say where in `sources`. An
  invented status vocabulary is the fastest way to make the map untrustworthy.

Change `--accent-h` in the CSS to re-theme the entire page. Neutrals are biased toward it,
so the chrome stays in one family.

### 4. Fill `DATA`

```js
n(label, type, note, children, opts)
```

- `label` — short. Inline HTML allowed (`<code>`, `<strong>`).
- `type` — a key from `CONFIG.types`.
- `note` — **why it matters, not what it is.** "Runs hourly but only acts every three hours
  in the tenant's timezone" earns its place; "handles the refresh" does not.
- `opts.kind` — `theme` for the top level (mono bold, separated by a rule), `flow` for the
  second (semibold), omitted below that. This is typographic weight, not semantics.
- `opts.status` — a key from `CONFIG.statuses`.

Authoring rules that keep it readable:

- **5–8 top-level themes**, named as verbs the reader came to do, not as system nouns.
  `UPDATE — report progress` beats `Progress Update Subsystem`.
- **3–4 levels total.** Five is a sign two levels want merging.
- **Leaves are facts.** A leaf needing a paragraph is really a flow with hidden children.
- **Place proposals and gaps at their injection point.** This is the entire reason to use a
  tree instead of a slide. A "gap" node naming an absent thing, sitting directly above the
  proposal that depends on it, does work no list can.
- **`startDepth: 1`** unless there is a reason otherwise — the reader should land on the top
  level, all closed, and choose where to go.

### 5. Publish

Load `artifact-design` if you are changing the visual direction; the template already
carries a considered one, so a straight content fill does not need it. Then `Artifact` with
the file path, a stable favicon, and a one-sentence description.

If the project keeps an artifact index, add the row in the same turn.

## Design invariants — do not break these

1. **The affordance rule.** A row states, before it is clicked, whether it opens: caret plus
   a descendant count, or a terminal dash with no hover state and no pointer cursor. This is
   the whole premise; a tree that hides its own depth is worse than a flat list.
2. **Two colour channels, kept separate.** Fill/dot = kind of thing. Pill = lifecycle status.
   Collapsing them into one hue makes both unreadable.
3. **Heading-to-body spacing lives on the flex container** (`.body { gap }`), not on a
   margin. Margins collapse and go inconsistent the moment a pill wraps to a second line.
   This was a real bug in v1 — the label and its note rendered 1px apart.
4. **Both themes, always.** Tokens are redefined under `prefers-color-scheme` *and* under
   `:root[data-theme]`, because the artifact viewer's toggle must beat the OS preference in
   both directions.
5. **No external hosts.** Published artifacts run under a strict CSP — no CDN scripts, fonts
   or images. That is why this template has zero dependencies.

## When it outgrows this

The template is deliberately ~120 lines of engine over a JSON array, because a disclosure
tree is the one case where a library buys almost nothing. Reach past it when:

- **The model should outlive the page** → **LikeC4** or **Structurizr**. Architecture as text
  in a DSL, drill-down as the native interaction, diffs in a pull request. This is the fix for
  a hand-maintained map going stale.
- **It ships inside a React app** → **React Flow** (`@xyflow/react`), whose sub-flow primitive
  handles nesting; pair with `elkjs` or `dagre` for layout.
- **It needs a real layout algorithm** rather than indentation → `d3-hierarchy`, or `@visx/hierarchy`
  for the React-flavoured version.
- **Thousands of nodes** → Cytoscape.js with the `expand-collapse` extension.
