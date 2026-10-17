"""Keep environment variables and feature names documented as the patch grows."""

import ast
import re
from pathlib import Path

from test_oss_unlock import mod

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_environment_variables_have_reference_rows():
    readme = (ROOT / "README.md").read_text()
    names = set()
    for name in ("branding.py", "oss_unlock.py"):
        tree = ast.parse((ROOT / "scripts" / name).read_text())
        names.update(
            n.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant)
            and isinstance(n.value, str)
            and re.fullmatch(r"(?:BRAND_|SSO_|LITELLM_OSS_)[A-Z_]+", n.value)
        )
    names.update(
        {"BRAND_PRIMARY_COLOR_DARK", "BRAND_PRIMARY_FOREGROUND_DARK", "DOCS_TITLE", "DOCS_DESCRIPTION", "DOCS_FILTERED"}
    )
    rows = {line.split("|", 2)[1].strip().strip("`"): line for line in readme.splitlines() if line.startswith("| `")}
    assert names <= rows.keys(), f"Environment variables missing reference rows: {names - rows.keys()}"
    for name in names:
        assert len(rows[name].split("|")) >= 6, f"Document type/default/example for {name}"


def test_feature_registry_is_documented():
    readme = (ROOT / "README.md").read_text()
    for feature in mod.FEATURES:
        assert f"| `{feature}` |" in readme
