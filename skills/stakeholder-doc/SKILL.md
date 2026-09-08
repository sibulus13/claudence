---
name: stakeholder-doc
description: Build or revise a decision document for named senior readers — a business case, funding ask, or proposal. Runs the four passes that this estate learned the hard way: verify every figure against its source, cut everything that does not earn its place, answer every objection rather than only naming it, and dispatch an independent reviewer whose mandate is to delete. Invoke when writing anything a chief executive, product director or engineering lead will decide on.
---

# Stakeholder document

**A decision document fails in four ways, and they are independent.** It can be wrong, it can be
bloated, it can be unpersuasive, or it can be aimed at nobody. **Each pass below closes one, and the
order matters** — condensing a document whose figures are wrong just produces a shorter wrong
document.

**Built 2026-08-26 from the passes that actually caught defects on a real funding case.** Four
published claims were withdrawn during that build; every one was caught by a pass below, and none
by re-reading.

## Pass 0 · Name the readers, and what each decides

**Before any structure, write down who decides what.** Not job titles — decisions.

| For each reader, state | Why it changes the document |
|---|---|
| **The decision they own** | *Is it a business* and *is it the right build* are different documents. A reader with no decision is an audience, not a reader |
| **What they will actually test** | The one who checks the arithmetic and the one who checks the persona need different sections at depth |
| ⚠️ **Whether they are a reader or the SPONSOR** | **A sponsor who handed the scope down still needs convincing of the implementation.** Treating them as pre-agreed leaves a hole exactly where their attention lands — the build plan, usually |
| **What failure looks like to them** | Capital wasted · a roadmap slot wasted · an unbounded maintenance surface. Three different fears, three different mitigations |

**Then decide how the document serves several readers.** One page with a role filter is cheapest to
keep current; separate documents drift. **If you filter, check that no reader is asked to endorse a
number they cannot see** — a product lead endorsing a price while the cost sections are hidden from
them is a real hazard, found in review.

## Pass 1 · VERIFY — every figure, against its own source

**Do this first and do it exhaustively.** Not the load-bearing ones; all of them.

| Check | The failure it catches |
|---|---|
| **Re-derive the number, do not re-read it** | A figure copied forward twice is a figure nobody has checked. Four were wrong on the real case |
| ⚠️ **Search BOTH directions for an absent link** | *"Projects cannot be traced to a plan"* was published from listing columns on one table. **The foreign key was on the other one.** An absent reference proves nothing until both sides are listed |
| ⚠️ **A derived figure is not a measured one** | A click-count presented as measurement was arithmetic on a measured unit. **State which it is, or drop it** |
| **Check the denominators agree** | Two counts over 194 and 196 in one document invites a reader to compute a wrong percentage |
| **Check the parts sum to the whole** | *7 answered, 10 partial, 2 missing* against a stated twenty. A dropped term is the commonest arithmetic defect |
| **Date every external figure** | A market survey quoted two years later on a fast-moving variable may now be wrong in your favour |
| **Name the evidence grade** | Our own record · a named organisation's own account · a vendor page · an aggregator. **An aggregator figure is a lead, never evidence** |
| ⚠️ **Sample the content behind a text-matching claim** | *"57 customers share identical text"* is worthless if the text is filler. Measure the length distribution before relying on it |

**Where two of your own documents disagree, publish neither** until one is resolved. That happened
and it was caught by the reviewer, not by the author.

## Pass 2 · CUT — every line justifies staying

| Delete on sight | Example |
|---|---|
| **Any sentence about the document rather than the subject** | *"as stated in our persona framework"* · *"this wording goes in a quote"* · *"shown as the arithmetic rather than a total"* |
| **Self-congratulation** | *"and it is stated rather than dressed up"* · *"none of it is hidden"* |
| **A claim line that restates the exhibit beneath it** | If the table says it, the prose above must not |
| **The same number in more than two places** | One was in five. Keep the exhibit and the assumptions row; cut the rest |
| **A gloss that repeats its own label** | *"Act on it — doing something with the answer"* |
| **Adverbs and intensifiers** | *actually · genuinely · diverse · fragilely* |
| **The closing note about how the document was written** | It is the last thing anyone reads and it says nothing |

⭐ **The heading test, which catches the most.** A heading that begins *What…* or *Why…* is a topic
label. **The assertion is usually already written one line below** — promote it, and the line below
becomes deletable. That is two savings from one edit.

## Pass 3 · PERSUADE — answer the objection, do not only name it

**Naming what would break a claim is honest and unpersuasive.** State the objection a sceptical
reader would actually raise, then answer it.

| Rule | Why |
|---|---|
| **The objection must be one they would raise** | *"Two figures were dropped from earlier drafts, why trust these?"* is the document interviewing itself. Nobody outside knows what earlier drafts said |
| **The answer must answer THAT objection** | An evidentiary objection answered with a delivery-mechanism answer concedes the point for free |
| ⭐ **Check whether your own evidence already refutes it** | A real case conceded *"stated pain, not measured behaviour"* while holding a **4.2× measured gradient** in a file the same section cited |
| **Where there is no answer, say so and leave it** | One unanswered risk stated plainly buys more credibility than four mitigations, three of which are thin |
| **Prefer a footnote for a caveat that is not an objection** | Not everything doubtful deserves a boxed rebuttal |

## Pass 4 · REVIEW — dispatch an independent reviewer to delete

**Not to approve.** A reviewer asked to review will find it good. Give this mandate:

> Your mandate is to CUT. Report: every sentence deletable with no loss · every repeat, naming which
> copy goes · every heading that is a topic label, with a replacement · every visual that duplicates
> the prose beside it · every objection that is a straw man or whose answer does not answer it · every
> phrase a reader would have to decode · every number the reader cannot place. Aim for at least
> twenty deletions if they exist. **"I found little" is a finding you must justify.**

**Then judge the findings rather than applying them.** On the real case the reviewer's severe
findings were right and two of its recommendations were wrong — it proposed deleting a section the
owner had specifically asked for. **Apply the facts, argue the taste, and say which you rejected.**

## What the passes do not cover

| Not covered | Consequence |
|---|---|
| **Whether the reader agrees** | Every pass improves the document, none improves the case |
| **A figure nobody has ever measured** | Verification finds the gap, it cannot fill it. Say *unmeasured* |
| **Tone for an individual** | These are the general standards. **Gather what each named reader actually reacted to and keep it beside this skill** — that is the only way it gets tailored rather than generic |
