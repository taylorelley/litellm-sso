"""Behavior tests against actual installed modules, without external services."""

import asyncio
import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from litellm.proxy import proxy_server
from litellm.proxy.management_endpoints import organization_endpoints, ui_sso
from litellm.proxy.management_helpers import audit_logs, team_metadata_validation
from litellm.proxy.oss_unlock import FEATURES, is_unlocked
from litellm.proxy.utils import _premium_user_check


class InstalledRuntimeTests(unittest.TestCase):
    def test_all_feature_switches_and_shared_gate(self):
        for feature in FEATURES:
            for setting, enabled in (("", False), (feature, True), ("all", True), ("typo", False)):
                with (
                    self.subTest(feature=feature, setting=setting),
                    patch.dict(os.environ, {"LITELLM_OSS_UNLOCK": setting}),
                ):
                    self.assertEqual(is_unlocked(feature), enabled)
                    with patch.object(proxy_server, "premium_user", False):
                        if enabled:
                            _premium_user_check(unlock=feature)
                        else:
                            with self.assertRaises(HTTPException):
                                _premium_user_check(unlock=feature)
            with (
                patch.dict(os.environ, {"LITELLM_OSS_UNLOCK": "all"}),
                patch.object(proxy_server, "premium_user", False),
            ):
                with self.assertRaises(HTTPException):
                    _premium_user_check()

    def test_sso_installed_function(self):
        for setting, count, denied in (("5", 5, False), ("5", 6, True), ("9", 10, True), ("0", 100, False)):
            repository = Mock(count_billable_users=AsyncMock(return_value=count))
            with (
                self.subTest(setting=setting),
                patch.dict(os.environ, {"SSO_FREE_USER_LIMIT": setting}),
                patch.object(ui_sso, "UserRepository", return_value=repository),
            ):
                if denied:
                    with self.assertRaises(ui_sso.ProxyException) as exc:
                        asyncio.run(ui_sso._raise_if_sso_exceeds_free_user_limit(False, object()))
                    self.assertEqual(str(exc.exception.code), "403")
                else:
                    asyncio.run(ui_sso._raise_if_sso_exceeds_free_user_limit(False, object()))
                if setting == "0":
                    repository.count_billable_users.assert_not_awaited()
        with patch.dict(os.environ, {"SSO_FREE_USER_LIMIT": "invalid"}):
            with self.assertRaisesRegex(ValueError, "SSO_FREE_USER_LIMIT"):
                asyncio.run(ui_sso._raise_if_sso_exceeds_free_user_limit(False, object()))

    def test_sso_unlock_keeps_database_requirement_and_premium_bypass(self):
        repository = Mock(count_billable_users=AsyncMock(return_value=100))
        with (
            patch.dict(os.environ, {"LITELLM_OSS_UNLOCK": "sso"}),
            patch.object(ui_sso, "UserRepository", return_value=repository),
        ):
            os.environ.pop("SSO_FREE_USER_LIMIT", None)
            asyncio.run(ui_sso._raise_if_sso_exceeds_free_user_limit(False, object()))
            repository.count_billable_users.assert_not_awaited()
            with self.assertRaises(ui_sso.ProxyException) as exc:
                asyncio.run(ui_sso._raise_if_sso_exceeds_free_user_limit(False, None))
            self.assertEqual(str(exc.exception.code), "403")
            repository.count_billable_users.assert_not_awaited()
        with patch.dict(os.environ, {"SSO_FREE_USER_LIMIT": "invalid"}):
            asyncio.run(ui_sso._raise_if_sso_exceeds_free_user_limit(True, None))

    def test_default_sso_limit_in_installed_code(self):
        repository = Mock(count_billable_users=AsyncMock(return_value=6))
        with (
            patch.dict(os.environ, {"LITELLM_OSS_UNLOCK": ""}),
            patch.object(ui_sso, "UserRepository", return_value=repository),
        ):
            os.environ.pop("SSO_FREE_USER_LIMIT", None)
            with self.assertRaises(ui_sso.ProxyException) as exc:
                asyncio.run(ui_sso._raise_if_sso_exceeds_free_user_limit(False, object()))
            self.assertEqual(str(exc.exception.code), "403")
            self.assertIn("limit of 5", str(exc.exception))

    def test_organization_gate(self):
        with patch.object(proxy_server, "premium_user", False):
            with patch.dict(os.environ, {"LITELLM_OSS_UNLOCK": ""}):
                with self.assertRaises(HTTPException) as exc:
                    asyncio.run(organization_endpoints._enterprise_license_required(None))
                self.assertEqual(exc.exception.status_code, 403)
            with patch.dict(os.environ, {"LITELLM_OSS_UNLOCK": "organizations"}):
                asyncio.run(organization_endpoints._enterprise_license_required(None))

    def test_audit_gate_keeps_explicit_configuration(self):
        with (
            patch.object(proxy_server, "premium_user", False),
            patch.object(audit_logs.litellm, "store_audit_logs", None),
            patch.object(audit_logs, "get_secret_bool", return_value=None),
        ):
            for setting, enabled in (("", False), ("audit_logs", True), ("all", True)):
                with patch.dict(os.environ, {"LITELLM_OSS_UNLOCK": setting}):
                    self.assertEqual(audit_logs.is_audit_logging_enabled(), enabled)
                    self.assertFalse(audit_logs.is_audit_logging_enabled(False))

    def test_unlocked_validation_still_validates(self):
        async def validator(payload):
            return {"valid": False, "error_message": "rejected by validator"}

        with patch.dict(os.environ, {"LITELLM_OSS_UNLOCK": "custom_team_metadata_validation"}):
            with self.assertRaises(HTTPException) as exc:
                asyncio.run(
                    team_metadata_validation.run_team_metadata_validation(
                        validator=validator,
                        payload={},
                        premium_user=False,
                        timeout_seconds=1,
                        unavailable_message="offline",
                    )
                )
            self.assertEqual(exc.exception.status_code, 400)
            self.assertIn("rejected by validator", str(exc.exception.detail))


if __name__ == "__main__":
    unittest.main()
