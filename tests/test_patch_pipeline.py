"""Regression checks for failure handling and enterprise import detection."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import apply_patch as runner
import generate_patch as generator


@pytest.mark.parametrize(
    "source",
    [
        "from litellm_enterprise.proxy import handler",
        "from litellm.proxy import enterprise",
        "import enterprise.auth",
        "from litellm_enterprise.proxy import (\n    handler,\n)",
        '__import__("litellm_enterprise.proxy")',
        'importlib.import_module("enterprise.auth")',
    ],
)
def test_rejects_added_enterprise_import(tmp_path, source):
    with pytest.raises(generator.EditError, match="enterprise import"):
        runner.validate_scope(tmp_path, {"litellm/proxy/test.py": source})


@pytest.mark.parametrize(
    "path", ["enterprise/test.py", "../test.py", "/tmp/test.py", "litellm/proxy/enterprise/test.py"]
)
def test_rejects_non_mit_paths(tmp_path, path):
    with pytest.raises(generator.EditError):
        runner.validate_scope(tmp_path, {path: "value = 1\n"})


def test_existing_enterprise_import_is_not_new(tmp_path):
    path = tmp_path / "litellm/proxy/test.py"
    path.parent.mkdir(parents=True)
    path.write_text("from litellm_enterprise import handler\nvalue = 1\n")
    runner.validate_scope(tmp_path, {"litellm/proxy/test.py": path.read_text().replace("1", "2")})


@pytest.fixture
def mini_upstream(tmp_path, monkeypatch):
    root = tmp_path / "upstream"
    target = root / "litellm/test.py"
    target.parent.mkdir(parents=True)
    target.write_text("value = 1\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    monkeypatch.setattr(generator, "FILES", {})
    monkeypatch.setattr(runner, "FILES", generator.FILES)
    monkeypatch.setattr(generator, "EDITS_DONE", [])

    def transform():
        generator.replace_once("litellm/test.py", "value = 1", "value = 2")

    monkeypatch.setattr(generator, "transform", transform)
    patch = tmp_path / "customizations.patch"
    patch.write_text(generator.generate(root))
    monkeypatch.setattr(runner, "PATCH", patch)
    return root, target, patch


def test_check_is_read_only_and_reapplication_fails(mini_upstream):
    root, target, _ = mini_upstream
    runner.apply(root, check=True)
    assert target.read_text() == "value = 1\n"
    runner.apply(root)
    assert target.read_text() == "value = 2\n"
    with pytest.raises(generator.EditError):
        runner.apply(root)
    assert target.read_text() == "value = 2\n"


def test_stale_patch_does_not_modify_upstream(mini_upstream):
    root, target, patch = mini_upstream
    patch.write_text(patch.read_text().replace("value = 2", "value = 3"))
    with pytest.raises(generator.EditError, match="differs from its sources"):
        runner.apply(root)
    assert target.read_text() == "value = 1\n"


def test_late_generator_failure_is_atomic(mini_upstream, monkeypatch):
    root, target, patch = mini_upstream
    original_patch = patch.read_text()

    def fail_after_edit():
        generator.replace_once("litellm/test.py", "value = 1", "value = 2")
        generator.replace_once("litellm/test.py", "missing anchor", "new")

    monkeypatch.setattr(generator, "transform", fail_after_edit)
    with pytest.raises(generator.EditError, match="expected one exact match"):
        generator.generate(root)
    assert target.read_text() == "value = 1\n"
    assert patch.read_text() == original_patch
