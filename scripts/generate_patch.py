#!/usr/bin/env python3
"""Generate the complete patch from a clean upstream checkout without modifying it."""

from __future__ import annotations

import argparse
import ast
import difflib
import sys
from pathlib import Path

ROOT = Path("upstream")
FILES: dict[str, str] = {}
HERE = Path(__file__).resolve().parent
IMPORT = (
    "from litellm.proxy.oss_unlock import is_unlocked as _oss_unlocked, premium_or_unlocked as _premium_or_unlocked\n"
)


class EditError(RuntimeError):
    pass


def read(rel: str) -> str:
    return FILES[rel] if rel in FILES else (ROOT / rel).read_text()


def write(rel: str, text: str) -> None:
    FILES[rel] = text


def ensure_import(rel: str) -> None:
    text = read(rel)
    if IMPORT in text:
        return
    tree = ast.parse(text)
    idx = 0
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            idx = node.end_lineno
        elif isinstance(node, ast.ImportFrom) and node.module == "__future__":
            idx = node.end_lineno
        else:
            break
    lines = text.splitlines(keepends=True)
    lines.insert(idx, IMPORT)
    write(rel, "".join(lines))


def gate(rel: str, anchor: str, old: str, new: str, *, window: int = 900, after: bool = False) -> None:
    """Replace `old` with `new` at the occurrence nearest to the unique `anchor`
    (searching backwards from the anchor by default, or forwards with after=True)."""
    text = read(rel)
    count = text.count(anchor)
    if count != 1:
        raise EditError(f"{rel}: anchor found {count} times: {anchor!r}")
    a = text.index(anchor)
    if after:
        start = a
        pos = text.find(old, a, a + window + len(old))
    else:
        start = max(0, a - window)
        pos = text.rfind(old, start, a + len(anchor))
    if pos == -1:
        raise EditError(f"{rel}: {old!r} not found near anchor {anchor!r}")
    write(rel, text[:pos] + new + text[pos + len(old) :])
    ensure_import(rel)


def P(feature: str) -> str:
    return f'_premium_or_unlocked(premium_user, "{feature}")'


EDITS_DONE: list[str] = []


def edit(feature: str, rel: str, anchor: str, old: str = "premium_user is not True", **kw) -> None:
    new = old.replace("premium_user", P(feature), 1)
    gate(rel, anchor, old, new, **kw)
    EDITS_DONE.append(f"{feature}\t{rel}")


def transform() -> None:
    write("litellm/proxy/oss_unlock.py", (HERE / "oss_unlock.py").read_text())
    write("litellm/proxy/branding.py", (HERE / "branding.py").read_text())
    apply_branding()
    apply_sso()

    # ---- secret managers ----
    edit(
        "secret_managers",
        "litellm/secret_managers/google_secret_manager.py",
        "Google Secret Manager requires an Enterprise License",
    )
    edit(
        "secret_managers",
        "litellm/secret_managers/hashicorp_secret_manager.py",
        "Hashicorp secret manager is only available for premium users",
    )
    edit(
        "secret_managers",
        "litellm/secret_managers/cyberark_secret_manager.py",
        "CyberArk secret manager is only available for premium users",
    )
    gate(
        "litellm/secret_managers/aws_secret_manager.py",
        "AWSKeyManagementService V2 is an Enterprise Feature",
        "if is_litellm_license_in_env is False:",
        'if is_litellm_license_in_env is False and not _oss_unlocked("secret_managers"):',
    )
    EDITS_DONE.append("secret_managers\tlitellm/secret_managers/aws_secret_manager.py")

    # ---- logging destinations ----
    edit(
        "logging_destinations",
        "litellm/integrations/gcs_bucket/gcs_bucket.py",
        "AdditionalLoggingUtils.__init__(self)",
        after=True,
        window=200,
    )
    # second GCS check (in async_log_success_event): anchor on its enclosing def
    edit(
        "logging_destinations",
        "litellm/integrations/gcs_bucket/gcs_bucket.py",
        "async def async_log_success_event",
        after=True,
    )
    edit(
        "logging_destinations",
        "litellm/integrations/azure_storage/azure_storage.py",
        "AzureBlobStorageLogger is only available for premium users",
    )
    for anchor in (
        "credentials_path (str, optional): Path to Google Cloud credentials JSON file",
        "get_logging_payload,\n        )\n        from litellm.proxy.utils import _premium_user_check",
    ):
        gate(
            "litellm/integrations/gcs_pubsub/pub_sub.py",
            anchor,
            "_premium_user_check()",
            '_premium_user_check(unlock="logging_destinations")',
            after=True,
            window=300,
        )
    EDITS_DONE.append("logging_destinations\tlitellm/integrations/gcs_pubsub/pub_sub.py")

    # ---- shared helper: _premium_user_check(feature, unlock=...) ----
    gate(
        "litellm/proxy/utils.py",
        "def _premium_user_check(feature: str | None = None):",
        "def _premium_user_check(feature: str | None = None):",
        "def _premium_user_check(feature: str | None = None, unlock: str | None = None):",
    )
    gate(
        "litellm/proxy/utils.py",
        "def _premium_user_check(feature: str | None = None, unlock: str | None = None):",
        "    if not premium_user:\n        raise HTTPException(",
        "    if not premium_user and not (unlock is not None and _oss_unlocked(unlock)):\n        raise HTTPException(",
        after=True,
    )
    EDITS_DONE.append("key_team_settings\tlitellm/proxy/utils.py (_premium_user_check)")

    for rel, old, new, expected in (
        (
            "litellm/proxy/litellm_pre_call_utils.py",
            "_premium_user_check()",
            '_premium_user_check(unlock="key_team_settings")',
            6,
        ),
        (
            "litellm/proxy/management_endpoints/common_utils.py",
            "_premium_user_check(field_name)",
            '_premium_user_check(field_name, unlock="key_team_settings")',
            1,
        ),
        (
            "litellm/proxy/management_endpoints/common_utils.py",
            "_premium_user_check()",
            '_premium_user_check(unlock="key_team_settings")',
            1,
        ),
        (
            "litellm/proxy/management_endpoints/key_management_endpoints.py",
            "_premium_user_check(k)",
            '_premium_user_check(k, unlock="key_team_settings")',
            1,
        ),
    ):
        text = read(rel)
        if text.count(old) != expected:
            raise EditError(f"{rel}: expected {expected} calls to {old}")
        write(rel, text.replace(old, new))

    # ---- email customisation ----
    edit(
        "email_customization",
        "litellm/integrations/SlackAlerting/slack_alerting.py",
        "Trying to Customize Email Alerting",
    )

    # ---- guardrails ----
    edit(
        "guardrail_dynamic_params",
        "litellm/integrations/custom_guardrail.py",
        "Trying to use premium guardrail without premium user",
    )

    # ---- proxy_server.py ----
    edit(
        "allowed_ips",
        "litellm/proxy/proxy_server.py",
        "allowed_ips is an Enterprise Feature",
        old="premium_user is False",
    )
    edit("enforced_params", "litellm/proxy/proxy_server.py", 'raise ValueError("Trying to use `enforced_params`"')
    edit("worker_registry", "litellm/proxy/proxy_server.py", 'raise ValueError("Trying to use `worker_registry`"')
    edit(
        "model_audit_fields",
        "litellm/proxy/proxy_server.py",
        'is a LiteLLM Enterprise Feature\n            model.model_info["created_at"]',
        old="premium_user is True",
    )
    edit(
        "request_size_limits",
        "litellm/proxy/proxy_server.py",
        "is_request_size_limit_enabled=lambda: premium_user is True",
        old="premium_user is True",
        window=60,
    )

    # ---- pre-call ----
    edit(
        "dynamic_callback_disabling",
        "litellm/proxy/litellm_pre_call_utils.py",
        "if litellm.allow_dynamic_callback_disabling is not True or not premium_user:",
        old="not premium_user",
    )
    edit("enforced_params", "litellm/proxy/litellm_pre_call_utils.py", "Enforced Params is an Enterprise feature")

    # ---- request / response / file size ----
    edit(
        "request_size_limits",
        "litellm/proxy/common_utils/http_parsing_utils.py",
        "Tried setting max_file_size_mb for /audio/transcriptions",
        old="not premium_user",
    )
    edit(
        "request_size_limits",
        "litellm/proxy/auth/auth_utils.py",
        "def check_if_request_size_is_safe",
        after=True,
        window=1500,
    )
    edit(
        "request_size_limits",
        "litellm/proxy/auth/auth_utils.py",
        "def check_response_size_is_safe",
        after=True,
        window=1500,
    )

    # ---- routes / IPs ----
    edit(
        "allowed_routes",
        "litellm/proxy/auth/auth_utils.py",
        "Trying to set allowed_routes. This is an Enterprise feature",
    )
    edit(
        "allowed_routes",
        "litellm/proxy/auth/auth_utils.py",
        "def route_in_additonal_public_routes",
        after=True,
        window=900,
    )
    edit(
        "admin_only_routes",
        "litellm/proxy/auth/route_checks.py",
        "Trying to use 'admin_only_routes' this is an Enterprise only feature",
    )

    # ---- auth ----
    edit(
        "oauth2_auth",
        "litellm/proxy/auth/user_api_key_auth.py",
        '"Oauth2 token validation is only available for premium users. "',
    )
    edit(
        "oauth2_auth",
        "litellm/proxy/auth/oauth2_check.py",
        "Oauth2 token validation is only available for premium users",
    )
    edit("jwt_auth", "litellm/proxy/auth/user_api_key_auth.py", 'message=f"JWT Auth is an enterprise only feature.')
    edit(
        "jwt_auth",
        "litellm/proxy/_experimental/mcp_server/bridge_token_flow.py",
        'if general_settings.get("enable_jwt_auth") is not True or premium_user is not True or prisma_client is None:',
    )
    edit(
        "jwt_auth",
        "litellm/proxy/_experimental/mcp_server/idp_token_exchange.py",
        "licensed=premium_user is True,",
        old="premium_user is True",
    )

    # ---- management ----
    edit(
        "model_max_budget",
        "litellm/proxy/management_endpoints/common_utils.py",
        "Setting model_max_budget on a team is an enterprise feature",
    )
    edit(
        "model_max_budget",
        "litellm/proxy/management_endpoints/key_management_endpoints.py",
        "You must have an enterprise license to set model_max_budget",
    )
    edit(
        "organizations",
        "litellm/proxy/management_endpoints/organization_endpoints.py",
        "async def _enterprise_license_required(",
        old="not premium_user",
        after=True,
    )
    edit(
        "team_admins",
        "litellm/proxy/management_endpoints/team_endpoints.py",
        'raise ValueError(f"Assigning team admins is a premium feature. {CommonProxyErrors.not_premium_user.value}")',
    )
    edit(
        "team_admins",
        "litellm/proxy/management_endpoints/team_endpoints.py",
        'f"Assigning team admins is a premium feature. Got={m}.',
    )
    edit(
        "team_admins",
        "litellm/proxy/management_endpoints/team_endpoints.py",
        'if data.role == "admin" and not premium_user:',
        old="not premium_user",
    )
    edit(
        "key_team_settings",
        "litellm/proxy/management_endpoints/key_management_endpoints.py",
        "Only premium users can add tags to keys",
    )
    edit(
        "model_access_groups",
        "litellm/proxy/management_endpoints/key_management_endpoints.py",
        "Setting a model access group on a wildcard model is only available",
        old="not premium_user",
    )
    edit(
        "spend_reports",
        "litellm/proxy/management_endpoints/key_management_endpoints.py",
        'if "get_spend_routes" in saved_token["permissions"] and premium_user is not True:',
    )
    edit(
        "key_rotation",
        "litellm/proxy/management_endpoints/key_management_endpoints.py",
        "Regenerating Virtual Keys is an Enterprise feature",
    )
    edit(
        "team_models",
        "litellm/proxy/management_endpoints/model_management_endpoints.py",
        "def can_user_make_team_model_call(",
        old="premium_user is False",
        after=True,
    )
    edit(
        "team_models",
        "litellm/proxy/management_endpoints/model_management_endpoints.py",
        "if model_params.model_info.team_id is not None and premium_user is not True:",
    )
    edit(
        "audit_logs",
        "litellm/proxy/management_helpers/audit_logs.py",
        "    return premium_user is True\n",
        old="premium_user is True",
    )
    edit(
        "audit_logs",
        "litellm/proxy/management_helpers/audit_logs.py",
        "async def create_audit_log_for_update(",
        after=True,
        window=1500,
    )
    edit(
        "auto_router",
        "litellm/proxy/management_helpers/auto_router_permissions.py",
        "raise HTTPException(status_code=403, detail=CommonProxyErrors.not_premium_user.value)",
        old="not premium_user",
    )
    edit(
        "custom_team_metadata_validation",
        "litellm/proxy/management_helpers/team_metadata_validation.py",
        "custom_team_metadata_validate is an Enterprise feature",
    )
    gate(
        "litellm/proxy/auth/litellm_license.py",
        "def auto_router_capability_limit(self) -> int | None:",
        "        if self.grants_feature(AUTO_ROUTER_LICENSE_FEATURE):",
        '        if self.grants_feature(AUTO_ROUTER_LICENSE_FEATURE) or _oss_unlocked("auto_router"):',
        after=True,
    )
    EDITS_DONE.append("auto_router\tlitellm/proxy/auth/litellm_license.py")

    # ---- endpoints ----
    for anchor in (
        "async def create_fine_tuning_job(",
        "async def retrieve_fine_tuning_job(",
        "async def list_fine_tuning_jobs(",
        "async def cancel_fine_tuning_job(",
    ):
        edit("fine_tuning", "litellm/proxy/fine_tuning_endpoints/endpoints.py", anchor, after=True, window=6000)
    edit(
        "spend_reports",
        "litellm/proxy/spend_tracking/spend_management_endpoints.py",
        'accessing /spend/report but not a premium user")',
    )
    edit(
        "spend_reports",
        "litellm/proxy/spend_tracking/spend_management_endpoints.py",
        "def _spend_report_prereqs() -> PrismaClient:",
        after=True,
        window=1500,
    )

    # ---- router ----
    edit("tag_budgets", "litellm/router_strategy/budget_limiter.py", "Tag budgets are an Enterprise only feature")

    # ---- priority reservation (gated on the env var merely being present) ----
    for rel in ("litellm/proxy/hooks/dynamic_rate_limiter.py", "litellm/proxy/hooks/dynamic_rate_limiter_v3.py"):
        gate(
            rel,
            "PREMIUM FEATURE: Reserving tpm/rpm by priority is a premium feature.",
            'if os.getenv("LITELLM_LICENSE", None) is None:',
            'if os.getenv("LITELLM_LICENSE", None) is None and not _oss_unlocked("priority_reservation"):',
        )
        EDITS_DONE.append(f"priority_reservation\t{rel}")

    # ---- admin UI premium flag ----
    for rel, anchor in (
        ("litellm/proxy/management_endpoints/ui_sso.py", "returned_ui_token_object: Final = ReturnedUITokenObject("),
        ("litellm/proxy/auth/login_utils.py", "return ReturnedUITokenObject("),
    ):
        gate(rel, anchor, "premium_user=premium_user,", f"premium_user={P('ui')},", after=True, window=800)
        EDITS_DONE.append(f"ui\t{rel}")
    for anchor in ("returned_ui_token_object: Final = ReturnedUITokenObject(",):
        text = read("litellm/proxy/proxy_server.py")
        n = text.count(anchor)
        if n != 2:
            raise EditError(f"proxy_server.py: expected 2 UI token sites, found {n}")
        parts = text.split(anchor)
        for i in range(1, len(parts)):
            seg = parts[i]
            if "premium_user=premium_user," not in seg[:800]:
                raise EditError("proxy_server.py: UI token site without premium_user kwarg")
            parts[i] = seg.replace("premium_user=premium_user,", f"premium_user={P('ui')},", 1)
        write("litellm/proxy/proxy_server.py", anchor.join(parts))
        ensure_import("litellm/proxy/proxy_server.py")
        EDITS_DONE.append("ui\tlitellm/proxy/proxy_server.py (x2)")

    # ---- warn on typos at startup ----
    gate(
        "litellm/proxy/proxy_server.py",
        "## CHECK PREMIUM USER",
        "## CHECK PREMIUM USER\n",
        "## CHECK PREMIUM USER\n"
        "    from litellm.proxy.oss_unlock import unknown_features as _oss_unknown\n\n"
        "    if _oss_unknown():\n"
        '        verbose_proxy_logger.warning("LITELLM_OSS_UNLOCK: unknown feature(s) ignored: %s", _oss_unknown())\n',
        after=True,
        window=40,
    )

    for rel in sorted(
        {e.split("\t")[1].split(" ")[0] for e in EDITS_DONE}
        | {"litellm/proxy/proxy_server.py", "litellm/proxy/utils.py"}
    ):
        ast.parse(read(rel), filename=rel)


def replace_once(rel: str, old: str, new: str) -> None:
    text = read(rel)
    count = text.count(old)
    if count != 1:
        raise EditError(f"{rel}: expected one exact match, found {count}: {old[:100]!r}")
    write(rel, text.replace(old, new, 1))


BRANDING_EDITS = [
    (
        "litellm/proxy/proxy_server.py",
        ")\n"
        "\n"
        "### CUSTOM BRANDING [ENTERPRISE FEATURE] ###\n"
        '_title: Final = os.getenv("DOCS_TITLE", "LiteLLM API") if premium_user else "LiteLLM API"\n'
        "_description: Final = (\n"
        "    os.getenv(\n"
        '        "DOCS_DESCRIPTION",\n'
        '        f"Enterprise Edition \\n\\nProxy Server to call 100+ LLMs in the OpenAI format. '
        '{custom_swagger_message}\\n\\n{ui_message}",\n'
        "    )\n"
        "    if premium_user\n"
        '    else f"Proxy Server to call 100+ LLMs in the OpenAI format. {custom_swagger_message}\\n\\n{ui_message}"\n'
        ")\n"
        "\n"
        "\n",
        ")\n"
        "\n"
        "### CUSTOM BRANDING [ENTERPRISE FEATURE] ###\n"
        "# Patched: docs branding is configurable without a licence (see litellm/proxy/branding.py).\n"
        '_title: Final = os.getenv("DOCS_TITLE") or (f"{os.getenv(\'BRAND_NAME\')} API" if os.getenv("BRAND_NAME") else '
        '"LiteLLM API")\n'
        "_description: Final = os.getenv(\n"
        '    "DOCS_DESCRIPTION",\n'
        '    ("Enterprise Edition \\n\\n" if premium_user else "")\n'
        '    + f"Proxy Server to call 100+ LLMs in the OpenAI format. {custom_swagger_message}\\n\\n{ui_message}",\n'
        ")\n"
        "\n"
        "\n",
    ),
    (
        "litellm/proxy/proxy_server.py",
        "    return app.openapi_schema\n"
        "\n"
        "\n"
        'if os.getenv("DOCS_FILTERED", "False") == "True" and premium_user:\n'
        "    app.openapi = custom_openapi\n"
        "else:\n"
        "    # For regular users, use get_openapi_schema to include LLM API schemas\n",
        "    return app.openapi_schema\n"
        "\n"
        "\n"
        'if os.getenv("DOCS_FILTERED", "False") == "True":\n'
        "    app.openapi = custom_openapi\n"
        "else:\n"
        "    # For regular users, use get_openapi_schema to include LLM API schemas\n",
    ),
    (
        "litellm/proxy/proxy_server.py",
        "app.add_middleware(RedisRequestBatchMiddleware)\n"
        "app.add_middleware(InFlightRequestsMiddleware)\n"
        "app.add_middleware(SecurityHeadersMiddleware)\n"
        "app.add_middleware(GZipBufferedResponseMiddleware)\n"
        "\n"
        "\n",
        "app.add_middleware(RedisRequestBatchMiddleware)\n"
        "app.add_middleware(InFlightRequestsMiddleware)\n"
        "app.add_middleware(SecurityHeadersMiddleware)\n"
        "# Patched: env-var branding. Added before GZip so it runs inside it (rewrites uncompressed bodies).\n"
        "from litellm.proxy.branding import BrandingMiddleware\n"
        "\n"
        "app.add_middleware(BrandingMiddleware)\n"
        "app.add_middleware(GZipBufferedResponseMiddleware)\n"
        "\n"
        "\n",
    ),
    (
        "litellm/proxy/utils.py",
        "    if html is None:\n"
        '        raise ValueError(f"No HTML body provided for SMTP email. {html}")\n'
        "\n"
        "    ## EMAIL SETUP ##\n"
        "    email_message: Final = MIMEMultipart()\n"
        '    email_message["From"] = sender_email\n',
        "    if html is None:\n"
        '        raise ValueError(f"No HTML body provided for SMTP email. {html}")\n'
        "\n"
        "    # Patched: env-var branding (see litellm/proxy/branding.py).\n"
        "    from litellm.proxy.branding import brand_email\n"
        "\n"
        "    subject, html = brand_email(subject, html)\n"
        "\n"
        "    ## EMAIL SETUP ##\n"
        "    email_message: Final = MIMEMultipart()\n"
        '    email_message["From"] = sender_email\n',
    ),
]


def apply_branding() -> None:
    for rel, old, new in BRANDING_EDITS:
        replace_once(rel, old, new)
    rel = "litellm/proxy/proxy_server.py"
    replace_once(
        rel,
        "from litellm.proxy.branding import BrandingMiddleware\n",
        "from litellm.proxy.branding import BrandingMiddleware, filter_openapi_paths\n",
    )
    gate(
        rel,
        "def custom_openapi():",
        "return app.openapi_schema",
        "return filter_openapi_paths(app.openapi_schema, LiteLLMRoutes.openai_routes.value)",
        after=True,
        window=200,
    )
    gate(
        rel,
        'if os.getenv("DOCS_FILTERED", "False") == "True":',
        "return app.openapi_schema",
        "return filter_openapi_paths(app.openapi_schema, LiteLLMRoutes.openai_routes.value)",
        window=500,
    )


def apply_sso() -> None:
    rel = "litellm/proxy/management_endpoints/ui_sso.py"
    replace_once(
        rel,
        '"""Free tier allows SSO for up to 5 billable users; beyond that requires an Enterprise license."""',
        '"""Enforce the configured billable-user limit for built-in SSO providers."""',
    )
    gate(
        rel,
        "async def _raise_if_sso_exceeds_free_user_limit(",
        "    billable_users: Final = await UserRepository(prisma_client).count_billable_users()\n"
        "    if billable_users and billable_users > 5:",
        "    from litellm.proxy.oss_unlock import sso_user_limit\n\n"
        "    sso_limit: Final = sso_user_limit()\n"
        "    if sso_limit == 0:\n"
        "        return\n"
        "    billable_users: Final = await UserRepository(prisma_client).count_billable_users()\n"
        "    if billable_users and billable_users > sso_limit:",
        after=True,
        window=1000,
    )
    replace_once(
        rel,
        'message="You must be a LiteLLM Enterprise user to use SSO for more than 5 users.',
        'message=f"The configured SSO user limit of {sso_limit} has been exceeded.',
    )


def generate(root: Path) -> str:
    global ROOT
    ROOT = root.resolve()
    FILES.clear()
    EDITS_DONE.clear()
    transform()
    result = []
    for rel, new in sorted(FILES.items()):
        tree = ast.parse(new, filename=rel)
        if IMPORT in new:
            used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
            aliases = []
            if "_oss_unlocked" in used:
                aliases.append("is_unlocked as _oss_unlocked")
            if "_premium_or_unlocked" in used:
                aliases.append("premium_or_unlocked as _premium_or_unlocked")
            replacement = "from litellm.proxy.oss_unlock import " + ", ".join(aliases) + "\n" if aliases else ""
            new = new.replace(IMPORT, replacement)
            FILES[rel] = new
        ast.parse(new, filename=rel)
        path = ROOT / rel
        old = path.read_text() if path.exists() else ""
        if old == new:
            continue
        result.append(f"diff --git a/{rel} b/{rel}\n")
        if not path.exists():
            result.append("new file mode 100644\n")
        result.extend(
            difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=f"a/{rel}" if path.exists() else "/dev/null",
                tofile=f"b/{rel}",
            )
        )
    return "".join(result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path)
    parser.add_argument("--check", action="store_true", help="Fail if the committed patch is stale")
    args = parser.parse_args()
    patch = HERE.parent / "patches/0001-oss-customizations.patch"
    content = generate(args.upstream)
    if args.check:
        if patch.read_text() != content:
            raise EditError("Generated patch is stale; run scripts/generate_patch.py on a clean checkout")
        print("Generated patch matches the committed patch")
    else:
        patch.write_text(content)
        print(f"Generated {patch.name} ({len(FILES)} files)")


if __name__ == "__main__":
    try:
        main()
    except (EditError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
