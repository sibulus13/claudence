"""Batch harness for spec-standard-v3/AC-1: judge every work item with ONE checker, imported once, and dump the results.

    python corpus_batch.py <scripts dir of the checker> <json file: list of README paths> <json file: output>

For each README the checker runs at each of the 6 statuses (the status line is rewritten in memory by an overlay tree, so
the real tests and cited files stay in place) with `require_sections` on and off, and with `for_source_commit`. An
exception is recorded, not raised, so a checker that crashes on an item is compared like any other result.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

STATUSES = ["draft", "spec-locked", "building", "shipped", "killed", "promoted"]


def main(scripts: str, cases_file: str, out_file: str) -> None:
    sys.path.insert(0, scripts)
    import spec_check  # the one import of this checker

    class StatusTree(spec_check.DiskTree):
        def __init__(self, root: Path, readme: str, status: str) -> None:
            super().__init__(root)
            self.readme, self.status = readme, status

        def read(self, rel: str) -> str | None:
            text = super().read(rel)
            if rel == self.readme and text is not None:
                text = re.sub(r"^status:.*$", f"status: {self.status}", text, count=1, flags=re.M)
            return text

    results: dict[str, list] = {}
    for readme in json.loads(Path(cases_file).read_text(encoding="utf-8")):
        path = Path(readme)
        root = path.resolve().parents[3]
        rel = path.resolve().relative_to(root).as_posix()
        for status in STATUSES:
            for require_sections, source_commit in [(False, False), (True, False), (False, True)]:
                key = f"{readme}|{status}|rs={require_sections}|fsc={source_commit}"
                try:
                    errors, warnings = spec_check.check_work_item(StatusTree(root, rel, status), rel, source_commit,
                                                                  require_sections)
                    results[key] = [errors, warnings]
                except Exception as e:  # noqa: BLE001 - a crash is a result to compare, not an error of the harness
                    results[key] = ["EXC", type(e).__name__, str(e)]
    Path(out_file).write_text(json.dumps(results, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:4])
