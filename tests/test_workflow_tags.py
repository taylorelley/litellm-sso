import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/build.yml"
DEFAULT_REF = "v1.105.1"


def generate_tags(tmp_path, ref, sha="a" * 40, branch="refs/heads/main"):
    source = (
        WORKFLOW.read_text()
        .split("python - <<'PY'\n", 1)[1]
        .split("\n          PY", 1)[0]
    )
    (tmp_path / "UPSTREAM_REF").write_text(DEFAULT_REF)
    output = tmp_path / "outputs"
    output.unlink(missing_ok=True)
    env = {
        **os.environ,
        "REQUESTED_REF": ref,
        "IMAGE_REPOSITORY": "Example/Image",
        "GITHUB_SHA": sha,
        "GITHUB_REF": branch,
        "GITHUB_OUTPUT": str(output),
    }
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    result.check_returncode()
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert values["ref"] == (ref or DEFAULT_REF)
    tags = values["tags"].split(",")
    assert all(tag.startswith("ghcr.io/example/image:") for tag in tags)
    assert all(
        re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", tag.split(":")[1])
        for tag in tags
    )
    return tags


@pytest.mark.parametrize(
    "refs", [("feature/foo", "feature-foo"), ("a" * 126 + "x", "a" * 126 + "y")]
)
def test_distinct_refs_have_distinct_tags(tmp_path, refs):
    first = generate_tags(tmp_path, refs[0])
    second = generate_tags(tmp_path, refs[1])
    assert set(first).isdisjoint(second)
    assert generate_tags(tmp_path, refs[0]) == first
    other_build = generate_tags(tmp_path, refs[0], sha="b" * 40)
    assert first[0] == other_build[0]
    assert first[1] != other_build[1]


@pytest.mark.parametrize(
    "ref,branch,latest",
    [
        ("", "refs/heads/main", True),
        (DEFAULT_REF, "refs/heads/main", True),
        (DEFAULT_REF, "refs/pull/1/merge", False),
        ("other", "refs/heads/main", False),
    ],
)
def test_latest_tag_behavior(tmp_path, ref, branch, latest):
    tags = generate_tags(tmp_path, ref, branch=branch)
    assert ("ghcr.io/example/image:latest" in tags) == latest


@pytest.mark.parametrize("ref", ["-invalid", "ref\nvalue", "a" * 128, "ref;command"])
def test_invalid_refs_are_rejected(tmp_path, ref):
    with pytest.raises(subprocess.CalledProcessError) as exc:
        generate_tags(tmp_path, ref)
    assert "Invalid upstream ref" in exc.value.stderr
