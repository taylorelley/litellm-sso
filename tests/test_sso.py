"""Run the patched SSO limit function without importing the proxy dependency tree."""

import ast
import asyncio
import os
import sys
import types
from pathlib import Path
from typing import Final
from unittest.mock import AsyncMock, Mock

import pytest
from test_oss_unlock import mod


@pytest.fixture
def sso(monkeypatch):
    monkeypatch.delenv("LITELLM_OSS_UNLOCK", raising=False)
    monkeypatch.delenv("SSO_FREE_USER_LIMIT", raising=False)
    monkeypatch.setitem(sys.modules, "litellm.proxy.oss_unlock", mod)
    module_path = Path(os.environ.get("OSS_UNLOCK_MODULE", "upstream/litellm/proxy/oss_unlock.py"))
    tree = ast.parse((module_path.parent / "management_endpoints/ui_sso.py").read_text())
    func = next(
        n
        for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "_raise_if_sso_exceeds_free_user_limit"
    )

    class ProxyException(Exception):
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            super().__init__(kwargs["message"])

    count = AsyncMock(return_value=6)
    repository = Mock(return_value=types.SimpleNamespace(count_billable_users=count))
    namespace = {
        "Final": Final,
        "PrismaClient": object,
        "ProxyException": ProxyException,
        "CommonProxyErrors": types.SimpleNamespace(db_not_connected_error=types.SimpleNamespace(value="db required")),
        "ProxyErrorTypes": types.SimpleNamespace(auth_error="auth_error"),
        "status": types.SimpleNamespace(HTTP_403_FORBIDDEN=403),
        "UserRepository": repository,
    }
    exec(compile(ast.Module(body=[func], type_ignores=[]), "ui_sso.py", "exec"), namespace)
    return namespace[func.name], count, ProxyException


@pytest.mark.parametrize(
    "setting,count,blocked", [(None, 5, False), (None, 6, True), ("10", 10, False), ("10", 11, True), ("0", 100, False)]
)
def test_billable_limit(sso, monkeypatch, setting, count, blocked):
    call, counter, error = sso
    counter.return_value = count
    if setting is not None:
        monkeypatch.setenv("SSO_FREE_USER_LIMIT", setting)
    if blocked:
        with pytest.raises(error, match=f"limit of {setting or 5}") as exc:
            asyncio.run(call(False, object()))
        assert exc.value.code == 403
    else:
        asyncio.run(call(False, object()))
    if setting == "0":
        counter.assert_not_awaited()


def test_unlock_skips_count_but_keeps_database_requirement(sso, monkeypatch):
    call, counter, error = sso
    monkeypatch.setenv("LITELLM_OSS_UNLOCK", "sso")
    asyncio.run(call(False, object()))
    counter.assert_not_awaited()
    with pytest.raises(error, match="db required"):
        asyncio.run(call(False, None))


def test_premium_keeps_upstream_bypass(sso, monkeypatch):
    call, counter, _ = sso
    monkeypatch.setenv("SSO_FREE_USER_LIMIT", "invalid")
    asyncio.run(call(True, None))
    counter.assert_not_awaited()


@pytest.mark.parametrize("unlock,allowed", [(None, False), ("key_team_settings", True)])
def test_shared_gate_requires_explicit_feature(monkeypatch, unlock, allowed):
    module_path = Path(os.environ.get("OSS_UNLOCK_MODULE", "upstream/litellm/proxy/oss_unlock.py"))
    tree = ast.parse((module_path.parent / "utils.py").read_text())
    func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_premium_user_check")
    monkeypatch.setenv("LITELLM_OSS_UNLOCK", "all")
    proxy = types.ModuleType("litellm.proxy.proxy_server")
    proxy.premium_user = False
    monkeypatch.setitem(sys.modules, "litellm.proxy.proxy_server", proxy)

    class HTTPException(Exception):
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    namespace = {
        "_oss_unlocked": mod.is_unlocked,
        "CommonProxyErrors": types.SimpleNamespace(not_premium_user=types.SimpleNamespace(value="licence required")),
        "HTTPException": HTTPException,
    }
    exec(compile(ast.Module(body=[func], type_ignores=[]), "utils.py", "exec"), namespace)
    if allowed:
        namespace[func.name](unlock=unlock)
    else:
        with pytest.raises(HTTPException) as exc:
            namespace[func.name]()
        assert exc.value.status_code == 403
