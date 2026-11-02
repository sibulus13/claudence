# Harness (claudence)

The working language of the agent harness: how a piece of work is specified, reviewed, built and shipped, and how the
commit gate judges it.

## Work items and their lifecycle

**Work item**:
The persistent specification of one feature, fix or build: a folder `docs/work/<id>/` with a README and layer files.
_Avoid_: spec (alone), ticket, task

**Lifecycle**:
The fixed set of statuses a work item can hold and the moves allowed between them.
_Avoid_: workflow, pipeline

**Move**:
A change of a work item's status from one lifecycle status to another in a commit.
_Avoid_: transition (in prose), status change

**Lock**:
The move from `draft` to `spec-locked`: the design is settled and may be built.
_Avoid_: freeze, approve

**Historical item**:
A work item last committed before the References and Operating envelope sections existed, judged with warnings until its next move.
_Avoid_: legacy item, grandfathered item

## Review

**Review record**:
The file a reviewer leaves in a work item's `reviews/` folder, naming the kind of review, the reviewer, the verdict and the content it judged.
_Avoid_: review note, sign-off, approval

**Design review**:
An independent review of a work item's specification before it is locked.
_Avoid_: spec review, design check

**Verify review**:
A short independent review of only the fixes made after a fix-first verdict.
_Avoid_: re-review, follow-up review

**Fresh**:
Said of a review record whose judged content is exactly the content being committed.
_Avoid_: current, up to date, recent

**Verdict**:
A review's outcome, one of `pass`, `fix-first` or `block`; `pass` means lock at a design review and ship at a code review.
_Avoid_: SHIP, GO, CONFIRMED, approval

**Rating**:
The weight of one finding: R (real, must fix), F (fragile, should fix), H (hardening, optional).
_Avoid_: severity, critical/warn/info, blocker/concern/nit

**Review budget**:
One review, at most one fix round, then one verify review; a second fix-first verdict goes to the architect.
_Avoid_: review rounds, fix budget

## Records

**Trace**:
The append-only record of a work item's stages, one stage record per line in `trace.jsonl`.
_Avoid_: cycle log, phase log, session log

**Stage record**:
One stage's decision, the alternatives considered, why, the evidence and its cost.
_Avoid_: thinking, notes, summary

**Drift report**:
The generated account, at ship, of every change made to a spec after its lock, and of which stage found each gap.
_Avoid_: spec diff, consolidation

## Design closure

**Outcome inventory**:
The table, per state machine in a design, of every outcome each stage can produce and how each one ends.
_Avoid_: edge-case list, failure modes, state matrix

**Outcome kind**:
One entry of the fixed checklist every stage is checked against, such as timeout, crash mid-step or arrival channel.
_Avoid_: failure type, scenario

**Arrival channel**:
A way the input to a stage can reach it, such as a commit, a merge, a squash or a rename.
_Avoid_: entry point, input path

**Closed off**:
Said of an outcome that is refused, recovered or escalated by a named rule or test, as opposed to nominal.
_Avoid_: handled, covered

**Adversary pass**:
A fresh-context agent's attempt to add outcomes the designer missed, before the design review.
_Avoid_: red team, devil's advocate
