# Probe: pii-scan (2026-11-08)

## 1. Existing specs and code in the area
- `docs/work/spec-gate/README.md`: the hook framework (pre-commit, commit-msg stage) this plugs into; no content check.
- `docs/work/decision-ids/README.md`: same pattern (compare staged with HEAD so old data never blocks); reused.
- `docs/work/agentic-loop/README.md:72`: names PII only as a risk class for `revenue` repos; no scanner.
- `hooks/guard.py`: guards tool calls, not commit content. Nothing else in `scripts/`, `hooks/`, `rules/` or `playbooks/` scans for personal data (grep for pii, personal data, email address).
- Installer: `scripts/install_fleet_hooks.py:17` copies `git-hooks/fleet-pre-commit-config.yaml` into fleet repos, not claudence's own `.pre-commit-config.yaml`. So this hook covers claudence only until it is added there.

## 2. Real runs
- The design review (record `reviews/2026-11-08-design-da7f04e3.md`) ran the hook directly and through pre-commit 4.7.0 in a temp repo: a staged personal email exits 1; a clean file exits 0. 7 mutations of the code were all caught by the tests.
- Live gaps it found, each now a test: a missing terms file passed silently (pre-commit hides a passing hook's output); a term wrapped across lines passed; an `open.spotify.com/user/<id>` link passed; `git mv` of a file that already held an email was refused.
- Corpus run: on the claudence tree at HEAD, the only hit was a test fixture address, now built from parts.

## 3. Current practice (searched 2026-11-08)
- gitleaks with a custom `.gitleaks.toml` email rule: secrets-first; terms would need an untracked config; binary not installed here. https://hoop.dev/blog/stop-pii-leaks-with-pre-commit-security-hooks
- gdprlint: Python pre-commit tool, 64 rules plus custom regex in JSON, block or warn per rule. https://pypi.org/project/gdprlint/
- git-customs: pre-push gate that can ask an LLM to list PII in added lines; catches names pattern matchers miss. https://pkg.go.dev/github.com/jackchuka/git-customs
- Security review 2026-11-08 (record pending) added: commit metadata, masked output, empty terms file, more Spotify ID shapes; the rest is backlog in the README Root cause.
- Known failure modes across them: false positives on fixtures and docs (needs allowlists), and `--no-verify` bypass (pair with CI when enforcement matters).

Verdict: keep the 100-line local hook for now. It needs two things the tools above do not give out of the box: private terms kept outside the public repo, and a compare-with-HEAD rule so existing data never blocks. Revisit when the scan spreads to the other public repos (telefi, meter, certify, spotifyDL): then try gdprlint with an untracked custom-rule file.

## 4. State machine touched
`contracts/work-item.lifecycle.v1.json`: draft -> spec-locked -> building -> shipped. The hook adds no state; it only refuses a commit.

## Adversary questions
- Who loses if it is wrong? A false negative publishes the owner's data in a public repo (cannot be unpublished). A false positive blocks a commit loudly, with the reason named.
- Bypass: `git commit --no-verify`, or deleting the marker. Accepted for a single-owner repo; a CI check is out of scope.
