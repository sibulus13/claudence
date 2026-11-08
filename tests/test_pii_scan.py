"""pii-scan/AC-1, pii-scan/AC-2, pii-scan/AC-3, pii-scan/MNC-1:
a commit to the public harness may not add personal data. Fixtures are built from parts so this file passes its own scan."""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pii_scan  # noqa: E402

TERMS = ["Jane Q Owner", "owner-handle-42"]
MAIL = "someone" + "@" + "gmail.com"
SPOTIFY_URI = "spotify:" + "user:abc123xyz"
SPOTIFY_LINK = "https://open.spotify.com/" + "user/abc123xyz"


def test_a_new_email_is_reported():
    assert pii_scan.new_hits("", f"contact: {MAIL}\n", []) == [f"email {MAIL}"]


def test_an_attribution_or_example_address_passes():
    staged = "Co-Authored-By: Claude <noreply@anthropic.com>\nuser.email t@example.test\n"
    assert pii_scan.new_hits("", staged, []) == []


def test_an_ssh_remote_passes_and_a_look_alike_domain_is_reported():
    look_alike = "x" + "@" + "notanthropic.com"
    assert pii_scan.new_hits("", f"git@github.com:o/r.git\n{look_alike}\n", []) == [f"email {look_alike}"]


def test_a_private_term_is_reported_case_insensitively():
    assert pii_scan.new_hits("", "written by jane q owner\n", TERMS) == ["private term 'Jane Q Owner'"]


def test_a_private_term_wrapped_across_lines_is_reported():
    assert pii_scan.new_hits("", "written by jane q\n  owner\n", TERMS) == ["private term 'Jane Q Owner'"]


def test_a_spotify_user_uri_is_reported():
    assert pii_scan.new_hits("", SPOTIFY_URI + "\n", []) == ["spotify user abc123xyz"]


def test_a_spotify_profile_link_is_reported():
    assert pii_scan.new_hits("", SPOTIFY_LINK + "\n", []) == ["spotify user abc123xyz"]


def test_other_spotify_id_shapes_are_reported():
    text = ("https://api.spotify.com/v1/" + "users/old.name_1\n"
            "https://open.spotify.com/intl-de/" + "user/abc123xyz\n"
            "spotify:" + "user:_odd.id\n")
    assert pii_scan.new_hits("", text, []) == ["spotify user _odd.id", "spotify user abc123xyz", "spotify user old.name_1"]


def test_the_refusal_masks_what_it_found():
    assert pii_scan.masked("email " + MAIL, TERMS) == "email s***@gmail.com"
    assert pii_scan.masked("private term 'Jane Q Owner'", TERMS) == "private term #1"
    assert pii_scan.masked("spotify user abc123xyz", TERMS) == "spotify user ab***"


def test_an_occurrence_already_at_head_does_not_block():
    old = f"contact: {MAIL}\n"
    assert pii_scan.new_hits(old, old + "more text\n", TERMS) == []


def test_the_terms_file_is_read_and_a_missing_one_is_none(tmp_path):
    f = tmp_path / "terms.txt"
    f.write_text("# comment\nJane Q Owner\n\n", encoding="utf-8")
    assert pii_scan.load_terms(f) == ["Jane Q Owner"]
    assert pii_scan.load_terms(tmp_path / "absent.txt") is None
    empty = tmp_path / "empty.txt"
    empty.write_text("# only a comment\n", encoding="utf-8")
    assert pii_scan.load_terms(empty) is None


def _repo(tmp_path, marker: bool):
    def git(*a):
        return subprocess.run(["git", *a], cwd=tmp_path, capture_output=True, text=True, timeout=30)

    git("init", "-q")
    git("config", "user.email", "t@example.test")
    git("config", "user.name", "t")
    if marker:
        (tmp_path / ".pii-scan").write_text("", encoding="utf-8")
    return git


def _scan(tmp_path, *paths, terms_file=None, extra_env=None):
    env = dict(os.environ, **(extra_env or {}))
    if terms_file is None:
        terms_file = tmp_path / "terms.txt"
        terms_file.write_text("Jane Q Owner\n", encoding="utf-8")
    env["PII_TERMS_FILE"] = str(terms_file)
    return subprocess.run([sys.executable, pii_scan.__file__, *paths], cwd=tmp_path, capture_output=True, text=True,
                          timeout=30, env=env)


def _repo_with_new_email(tmp_path, marker: bool, terms_file=None):
    git = _repo(tmp_path, marker)
    f = tmp_path / "SKILL.md"
    f.write_text("clean\n", encoding="utf-8")
    git("add", "SKILL.md", ".pii-scan" if marker else "SKILL.md")
    git("commit", "-qm", "base")
    f.write_text(f"clean\nmail me at {MAIL}\n", encoding="utf-8")
    git("add", "SKILL.md")
    return _scan(tmp_path, "SKILL.md", terms_file=terms_file)


def test_a_real_commit_with_personal_data_is_refused_without_echoing_it(tmp_path):
    run = _repo_with_new_email(tmp_path, marker=True)
    assert run.returncode == 1
    assert "s***@gmail.com" in run.stderr
    assert MAIL not in run.stderr


def test_a_commit_message_or_author_with_personal_data_is_refused(tmp_path):
    git = _repo(tmp_path, marker=True)
    msg = tmp_path / "MSG"
    msg.write_text("fix: thing\n\nasked by jane q owner\n", encoding="utf-8")
    assert _scan(tmp_path, "--commit-msg", str(msg)).returncode == 1
    msg.write_text("fix: thing\n", encoding="utf-8")
    assert _scan(tmp_path, "--commit-msg", str(msg)).returncode == 0
    git("config", "user.email", MAIL)
    run = _scan(tmp_path, "--commit-msg", str(msg))
    assert run.returncode == 1
    assert "author" in run.stderr
    git("config", "user.email", "t@example.test")
    env_run = _scan(tmp_path, "--commit-msg", str(msg), extra_env={"GIT_COMMITTER_EMAIL": MAIL})
    assert env_run.returncode == 1
    assert "committer" in env_run.stderr and "author" not in env_run.stderr


def test_the_diff_that_commit_v_appends_is_not_scanned(tmp_path):
    _repo(tmp_path, marker=True)
    msg = tmp_path / "MSG"
    scissors = "# ------------------------ >8 ------------------------\n"
    msg.write_text("fix: drop an old address\n# a comment naming jane q owner\n" + scissors + f"-contact {MAIL}\n",
                   encoding="utf-8")
    assert _scan(tmp_path, "--commit-msg", str(msg)).returncode == 0


def test_a_marked_repo_without_the_terms_file_is_refused(tmp_path):
    git = _repo(tmp_path, marker=True)
    (tmp_path / "a.md").write_text("clean\n", encoding="utf-8")
    git("add", "a.md")
    run = _scan(tmp_path, "a.md", terms_file=tmp_path / "absent.txt")
    assert run.returncode == 1
    assert "no private terms" in run.stderr


def test_a_repo_without_the_marker_is_not_scanned(tmp_path):
    assert _repo_with_new_email(tmp_path, marker=False).returncode == 0


def test_renaming_a_file_that_already_held_data_does_not_block(tmp_path):
    git = _repo(tmp_path, marker=True)
    (tmp_path / "old.md").write_text(f"contact: {MAIL}\n" + "filler line\n" * 20, encoding="utf-8")
    git("add", "old.md", ".pii-scan")
    git("commit", "-qm", "base")
    git("mv", "old.md", "new.md")
    assert _scan(tmp_path, "new.md").returncode == 0
