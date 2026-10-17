"""Exercise every patched gate with locked, selective, and all-feature settings."""

import ast
import copy
import difflib
import os
import subprocess
from collections import Counter
from functools import lru_cache
from pathlib import Path

import pytest
from test_oss_unlock import mod

AUDITED_SITES = {
    "admin_only_routes": 1,
    "allowed_ips": 1,
    "allowed_routes": 2,
    "audit_logs": 2,
    "auto_router": 2,
    "custom_team_metadata_validation": 1,
    "dynamic_callback_disabling": 1,
    "email_customization": 1,
    "enforced_params": 2,
    "fine_tuning": 4,
    "guardrail_dynamic_params": 1,
    "jwt_auth": 3,
    "key_rotation": 1,
    "key_team_settings": 10,
    "logging_destinations": 5,
    "model_access_groups": 1,
    "model_audit_fields": 1,
    "model_max_budget": 2,
    "oauth2_auth": 2,
    "organizations": 1,
    "priority_reservation": 2,
    "request_size_limits": 4,
    "secret_managers": 4,
    "spend_reports": 3,
    "tag_budgets": 1,
    "team_admins": 3,
    "team_models": 2,
    "ui": 4,
    "worker_registry": 1,
}


def gate_sites():
    root = Path(os.environ.get("OSS_UNLOCK_MODULE", "upstream/litellm/proxy/oss_unlock.py")).parents[2]
    patch = Path(__file__).resolve().parents[1] / "patches/0001-oss-customizations.patch"
    result = []
    for line in patch.read_text().splitlines():
        if not line.startswith("+++ b/") or line.endswith("/oss_unlock.py"):
            continue
        rel = line[6:]
        tree = ast.parse((root / rel).read_text())
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id in ("_premium_or_unlocked", "_oss_unlocked") and isinstance(node.args[-1], ast.Constant):
                feature = node.args[-1].value
                expr = node
                if isinstance(parents.get(expr), (ast.UnaryOp, ast.Compare)):
                    expr = parents[expr]
                result.append((rel, node.lineno, feature, node.func.id, expr))
            elif node.func.id == "_premium_user_check":
                for kw in node.keywords:
                    if kw.arg == "unlock":
                        result.append((rel, node.lineno, kw.value.value, "shared", kw.value))
    return result


SITES = gate_sites()


def test_all_feature_gates_are_audited():
    assert Counter(site[2] for site in SITES) == AUDITED_SITES
    assert set(AUDITED_SITES) | {"sso"} == set(mod.FEATURES)


@pytest.mark.parametrize("site", SITES, ids=lambda site: f"{site[2]}:{site[0]}:{site[1]}")
@pytest.mark.parametrize("premium", [False, None, True])
@pytest.mark.parametrize("setting", ["locked", "selective", "all", "unrelated"])
def test_gate_behavior(site, premium, setting, monkeypatch):
    rel, line, feature, kind, expression = site
    raw = {"locked": "", "selective": feature, "all": "all", "unrelated": "not_a_feature"}[setting]
    monkeypatch.setenv("LITELLM_OSS_UNLOCK", raw)
    enabled = setting in ("selective", "all")
    if kind == "shared":
        assert mod.is_unlocked(feature) is enabled
        return
    actual = eval(
        compile(ast.Expression(expression), f"{rel}:{line}", "eval"),
        {
            "premium_user": premium,
            "_premium_or_unlocked": mod.premium_or_unlocked,
            "_oss_unlocked": mod.is_unlocked,
        },
    )

    if kind == "_oss_unlocked":
        expected = enabled if feature == "auto_router" else not enabled
    else:
        baseline = original_expression(rel, line)
        expected = eval(
            compile(ast.Expression(baseline), "unpatched-upstream", "eval"),
            {"premium_user": True if enabled else premium},
        )
    assert actual == expected


@lru_cache(maxsize=None)
def original_expressions(rel: str) -> dict[int, ast.expr]:
    root = Path(os.environ.get("OSS_UNLOCK_MODULE", "upstream/litellm/proxy/oss_unlock.py")).parents[2].resolve()
    original = subprocess.check_output(["git", "-C", str(root), "show", f"HEAD:{rel}"], text=True)
    patched = (root / rel).read_text()
    tree = ast.parse(original)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    predicates = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "premium_user" and isinstance(node.ctx, ast.Load):
            expression = parents[node] if isinstance(parents.get(node), (ast.Compare, ast.UnaryOp)) else node
            predicates[node.lineno] = expression
    mapped = {}
    diff = difflib.SequenceMatcher(None, original.splitlines(), patched.splitlines())
    for operation, i1, i2, j1, j2 in diff.get_opcodes():
        if operation == "insert":
            continue
        for patched_line in range(j1, j2):
            original_line = i1 + min(patched_line - j1, i2 - i1 - 1) + 1
            if original_line in predicates:
                mapped[patched_line + 1] = predicates[original_line]
    return mapped


def original_expression(rel: str, line: int) -> ast.expr:
    return original_expressions(rel)[line]


def test_gate_oracle_rejects_reversed_comparison(monkeypatch):
    site = next(site for site in SITES if isinstance(site[4], ast.Compare) and isinstance(site[4].ops[0], ast.IsNot))
    mutated = list(site)
    mutated[4] = copy.deepcopy(site[4])
    mutated[4].ops[0] = ast.Is()
    with pytest.raises(AssertionError):
        test_gate_behavior(tuple(mutated), False, "locked", monkeypatch)
