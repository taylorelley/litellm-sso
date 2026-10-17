"""Tests for litellm/proxy/oss_unlock.py, loaded from the patched upstream checkout.

OSS_UNLOCK_MODULE=path/to/litellm/proxy/oss_unlock.py pytest tests/
"""

import importlib.util
import os

import pytest

_path = os.environ.get("OSS_UNLOCK_MODULE", "upstream/litellm/proxy/oss_unlock.py")
_spec = importlib.util.spec_from_file_location("oss_unlock", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.delenv("LITELLM_OSS_UNLOCK", raising=False)
    monkeypatch.delenv("SSO_FREE_USER_LIMIT", raising=False)


def test_default_is_locked_and_preserves_value():
    for f in mod.FEATURES:
        assert mod.is_unlocked(f) is False
    for value in (True, False, None):
        assert mod.premium_or_unlocked(value, "jwt_auth") is value


def test_specific_features(monkeypatch):
    monkeypatch.setenv("LITELLM_OSS_UNLOCK", " JWT_auth , audit_logs ")
    assert mod.is_unlocked("jwt_auth") and mod.is_unlocked("audit_logs")
    assert not mod.is_unlocked("organizations")
    assert mod.premium_or_unlocked(False, "jwt_auth") is True
    assert mod.premium_or_unlocked(False, "organizations") is False


def test_all(monkeypatch):
    monkeypatch.setenv("LITELLM_OSS_UNLOCK", "all")
    assert all(mod.is_unlocked(f) for f in mod.FEATURES)


def test_unknown_names(monkeypatch):
    monkeypatch.setenv("LITELLM_OSS_UNLOCK", "all,jwt_auth,nope,ALSO_NOPE")
    assert mod.unknown_features() == ["nope", "also_nope"]
    with pytest.raises(KeyError):
        mod.is_unlocked("not_a_feature")


@pytest.mark.parametrize("raw, expected", [(None, 5), ("0", 0), ("12", 12), (" 8 ", 8)])
def test_sso_limit(monkeypatch, raw, expected):
    monkeypatch.delenv("SSO_FREE_USER_LIMIT", raising=False)
    if raw is not None:
        monkeypatch.setenv("SSO_FREE_USER_LIMIT", raw)
    assert mod.sso_user_limit() == expected


@pytest.mark.parametrize("feature", ["sso", "all"])
def test_sso_unlock_and_explicit_limit_precedence(monkeypatch, feature):
    monkeypatch.delenv("SSO_FREE_USER_LIMIT", raising=False)
    monkeypatch.setenv("LITELLM_OSS_UNLOCK", feature)
    assert mod.sso_user_limit() == 0
    monkeypatch.setenv("SSO_FREE_USER_LIMIT", "7")
    assert mod.sso_user_limit() == 7


@pytest.mark.parametrize("raw", ["", "no", "-1", "2.5"])
def test_invalid_sso_limit_is_rejected(monkeypatch, raw):
    monkeypatch.setenv("SSO_FREE_USER_LIMIT", raw)
    monkeypatch.setenv("LITELLM_OSS_UNLOCK", "all")
    with pytest.raises(ValueError, match="SSO_FREE_USER_LIMIT must be a non-negative integer"):
        mod.sso_user_limit()
