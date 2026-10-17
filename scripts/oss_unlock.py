"""
Per-feature opt-in for capabilities that upstream gates behind a licence check in
MIT-licensed code.

    LITELLM_OSS_UNLOCK=jwt_auth,audit_logs,organizations     # specific features
    LITELLM_OSS_UNLOCK=all                                   # every feature below

Unset (the default) keeps upstream behaviour exactly. Read at call time, so values set
through the proxy config's environment_variables are honoured.

Only gates whose protected code is MIT-licensed are covered. Checks that guard code from
upstream's separately licensed `enterprise/` directory or `litellm_enterprise` package
are deliberately left untouched and cannot be unlocked here.
"""

from __future__ import annotations

import os
from typing import Final

ENV_VAR: Final = "LITELLM_OSS_UNLOCK"

FEATURES: Final[dict[str, str]] = {
    "admin_only_routes": "general_settings.admin_only_routes",
    "allowed_ips": "general_settings.allowed_ips",
    "allowed_routes": "general_settings.allowed_routes and public_routes",
    "audit_logs": "Audit logs for management changes",
    "auto_router": "Unlimited auto-routers per classifier/customisation capability",
    "custom_team_metadata_validation": "general_settings.custom_team_metadata_validate",
    "dynamic_callback_disabling": "Disabling callbacks per request",
    "email_customization": "Custom logo and support contact in alert emails",
    "enforced_params": "general_settings.enforced_params",
    "fine_tuning": "/fine_tuning endpoints",
    "guardrail_dynamic_params": "Per-request guardrail extra_body",
    "jwt_auth": "JWT auth for the proxy and MCP token exchange",
    "key_rotation": "Regenerating virtual keys",
    "key_team_settings": "Key/team/project guardrails, policies, tags, prompts, logging, "
    "secret manager settings, passthrough routes and key duration",
    "logging_destinations": "GCS bucket, GCS Pub/Sub and Azure Blob logging",
    "model_access_groups": "Model access groups on wildcard routes",
    "model_audit_fields": "created_at/updated_at/created_by/updated_by on model info",
    "model_max_budget": "Per-model budgets on keys and teams",
    "oauth2_auth": "OAuth2 token validation",
    "organizations": "/organization endpoints",
    "priority_reservation": "TPM/RPM reservation by priority (dynamic rate limiter)",
    "request_size_limits": "max_request_size_mb, max_response_size_mb, max_file_size_mb",
    "secret_managers": "AWS KMS v2, Google, HashiCorp and CyberArk secret managers",
    "sso": "Unlimited users for built-in SSO providers",
    "spend_reports": "/global/spend/report and get_spend_routes key permission",
    "tag_budgets": "Budgets per request tag",
    "team_admins": "Team admin role",
    "team_models": "Team-scoped models",
    "ui": "Show licence-gated features in the admin UI (sets the UI's premium flag)",
    "worker_registry": "general_settings.worker_registry",
}


def _enabled() -> frozenset[str]:
    raw = os.getenv(ENV_VAR, "")
    names = {part.strip().lower() for part in raw.split(",") if part.strip()}
    if "all" in names:
        return frozenset(FEATURES)
    return frozenset(names & FEATURES.keys())


def is_unlocked(feature: str) -> bool:
    if feature not in FEATURES:
        raise KeyError(f"Unknown {ENV_VAR} feature: {feature}")
    return feature in _enabled()


def premium_or_unlocked(premium_user, feature: str):
    """Drop-in for a `premium_user` value at a gate: True when the feature is unlocked,
    otherwise the original value unchanged (so locked behaviour is identical to upstream)."""
    return True if is_unlocked(feature) else premium_user


def unknown_features() -> list[str]:
    raw = os.getenv(ENV_VAR, "")
    names = [part.strip().lower() for part in raw.split(",") if part.strip()]
    return [n for n in names if n != "all" and n not in FEATURES]


def sso_user_limit() -> int:
    """Return the configured billable-user limit; zero means unlimited."""
    raw = os.getenv("SSO_FREE_USER_LIMIT")
    if raw is not None:
        try:
            limit = int(raw)
        except ValueError:
            raise ValueError("SSO_FREE_USER_LIMIT must be a non-negative integer") from None
        if limit < 0:
            raise ValueError("SSO_FREE_USER_LIMIT must be a non-negative integer")
        return limit
    return 0 if is_unlocked("sso") else 5
