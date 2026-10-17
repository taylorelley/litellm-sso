"""Prevent generated cache and test output from entering commits."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIRECTORIES = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "smoke-logs",
    "htmlcov",
    "test-results",
    "playwright-report",
}


def test_no_generated_files_are_tracked():
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    bad = []
    for name in filter(None, files):
        path = Path(name)
        if (
            any(part in GENERATED_DIRECTORIES for part in path.parts)
            or path.suffix in {".pyc", ".pyo"}
            or path.name in {".coverage", "coverage.xml", "junit.xml"}
            or path.name.startswith(".coverage.")
        ):
            bad.append(name)
    assert not bad, f"Remove generated files from Git: {bad}"


def test_generated_outputs_are_ignored():
    files = [
        "tests/__pycache__/example.pyc",
        ".pytest_cache/v/cache/nodeids",
        ".ruff_cache/0.1/file",
        "smoke-logs/tested-image-id.txt",
        ".coverage",
        ".coverage.worker",
        "coverage.xml",
        "htmlcov/index.html",
        "junit.xml",
        "test-results/output.json",
        "playwright-report/index.html",
    ]
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"],
        cwd=ROOT,
        input="\n".join(files) + "\n",
        text=True,
        capture_output=True,
        check=True,
    )
    assert set(result.stdout.splitlines()) == set(files)
