"""pytest configuration shared by the harness tests: registers the `corpus` marker (spec-standard-v3/AC-1)."""


def pytest_configure(config) -> None:
    config.addinivalue_line("markers", "corpus: one-time acceptance check over real work items outside the repo "
                                       "(skipped with a named reason when its inputs are absent)")
