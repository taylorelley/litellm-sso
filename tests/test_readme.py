"""Keep environment variables and feature names documented as the patch grows."""

import ast
from pathlib import Path

from test_oss_unlock import mod

ROOT = Path(__file__).resolve().parents[1]


def environment_reads(source: str) -> set[str]:
    tree = ast.parse(source)
    constants = {
        target.id: node.value.value
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Name)
    }
    names = set()
    for node in ast.walk(tree):
        value = None
        if (
            isinstance(node, ast.Call)
            and node.args
            and ast.unparse(node.func) in {"os.getenv", "os.environ.get", "_env"}
        ):
            value = node.args[0]
        elif isinstance(node, ast.Subscript) and ast.unparse(node.value) == "os.environ":
            value = node.slice
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            names.add(value.value)
        elif isinstance(value, ast.Name) and value.id in constants:
            names.add(constants[value.id])
    return names


def test_runtime_environment_variables_have_reference_rows():
    readme = (ROOT / "README.md").read_text()
    names = set()
    for name in ("branding.py", "oss_unlock.py"):
        names.update(environment_reads((ROOT / "scripts" / name).read_text()))
    names.update({"DOCS_TITLE", "DOCS_DESCRIPTION", "DOCS_FILTERED"})
    rows = {line.split("|", 2)[1].strip().strip("`"): line for line in readme.splitlines() if line.startswith("| `")}
    assert names <= rows.keys(), f"Environment variables missing reference rows: {names - rows.keys()}"
    for name in names:
        columns = rows[name].split("|")
        assert len(columns) >= 6 and all(value.strip() for value in columns[2:5]), (
            f"Document type/default/example for {name}"
        )


def test_environment_discovery_is_not_limited_to_existing_prefixes():
    assert environment_reads(
        'import os\nKEY="NEW_ENV"\nos.getenv(KEY)\nos.environ["ANOTHER_ENV"]\nos.environ.get("OPTION")'
    ) == {"NEW_ENV", "ANOTHER_ENV", "OPTION"}


def test_feature_registry_is_documented():
    readme = (ROOT / "README.md").read_text()
    for feature in mod.FEATURES:
        assert f"| `{feature}` |" in readme
