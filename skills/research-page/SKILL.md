---
name: research-page
description: One page of research before any new work, for any project, internal or external. Compares what we already have with current practice, names the gaps, and picks the top changes. Use before a spec, a tool or convention choice, or an improvement review. Trading studies keep their own protocol and put this page in front.
---

# Research page

Every research persona follows these steps in order: the main-session researcher, Foreman's `research` mode and any
session doing research. Answer the questions on one page and stop when they are answered: this is not a survey.

## Steps

1. **Local first.** Follow the `context-index` skill (`C:/Users/Michael/.claude/skills/context-index/SKILL.md`): run
   `python C:/Users/Michael/.claude/scripts/context_index.py lookup <term> ...`, then read the research catalog
   (`D:/repo/docs/context/research.md`) and the tech radar (`D:/repo/docs/TECH_RADAR.md`) for earlier verdicts.
   Extend an earlier page rather than redoing it.
2. **Have.** Grep every repo for the role, then read the roadmap, specs, decisions, reports, memory and the fleet docs.
   Files named in the brief are a starting point, not the scope. Cite absolute `file:line`. Run the thing if it exists.
3. **Standard.** Current practice, primary sources first, dated. Label blogs and vendor pages as weak. Say what you
   could not confirm. Include the widely used, free, well-validated off-the-shelf options (platform, library or
   service), whatever they run on.
   - **Community scan:** search GitHub (`gh search repos`, awesome-lists), Reddit and Hacker News for projects that
     already do what we built or plan, and for practitioners' verdicts on each option (thread link and date).
   - **Adoption health**, from `gh api repos/<owner>/<repo>` and its releases and contributors: stars, forks, watchers,
     contributors, last push, last release, releases in 90 days, licence, archived. Put it in the radar row.
   - **Default ring thresholds** (assumed 2026-11-08, revisit after 10 radar decisions): Adopt needs a push in the last
     30 days, a release in the last 90, an OSI licence, and broad adoption (about 5k+ stars or 50+ contributors, or a
     foundation or major vendor behind it). Trial needs active maintenance and about 1k+ stars. Anything less is
     Assess or Borrow-idea. Below the bar on adoption is a finding the owner sees, even for something we already use.
4. **Gap.** Compare the two, row by row. A difference is only a gap if it costs something real.
5. **Do.** The top 3 changes, ranked by how much it hurts today, with evidence from our own records. Name what to ignore.
6. **Propose adoption.** Every off-the-shelf component that fits becomes a row in `D:/repo/docs/TECH_RADAR.md` with
   ring `proposed` (or a move between rings), its evidence and the next step. Adopting what is widespread and
   reliable beats building; building needs a stated reason.
7. **Persist.** Write the page to `D:/repo/docs/reports/<yyyy-mm-dd>-<slug>.md` (a project-only study goes in that
   repo's `docs/research/`), add one row under its category in `D:/repo/docs/context/research.md`, and add or re-date
   context-index rows for every local file that answered something.

## Rules

- **Constraints come only from the owner or a recorded decision**, cited by id or file:line. An environment fact
  ("not installed", "needs Docker", "needs a server") is a cost to weigh, never a filter (owner 2026-11-08: the
  2026-10-31 lifecycle research dropped Docker options on a constraint nobody had set). Every rejection names its
  source.
- Measure before you claim: counts from real logs beat opinions.
- Reuse beats building. If something fits, say so and stop.
- "What we have" includes plans as well as code. Search the roadmap (`$FLEET_DOCS/LEDGER.md`), `$FLEET_DOCS/ARCHITECTURE_*.md`, and every repo's `docs/work` and `docs/specs` for the role before proposing anything.
- Keep to 300 words plus one comparison table and the radar rows.
- Give each row a criticality: high, medium or low. Only high rows reach the owner.
- State your sample and who rated it when you classify anything by judgement.

## Output

```
Question: <one line>
| Area | Have | Standard | Gap | Criticality |
Do: 1, 2, 3
Radar: | Component | Ring | Replaces or adds | Health (stars / forks / watchers / contributors / last release) | Evidence | Next step |
Ignore: ...
Sources: ...
```
