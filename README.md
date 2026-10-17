# litellm-sso

Builds the upstream [LiteLLM](https://github.com/BerriAI/litellm) proxy image with one generated patch. Runtime changes are configured by environment variables:

1. **SSO user limit**: read from `SSO_FREE_USER_LIMIT` instead of being fixed at 5.
2. **Branding**: product name, titles, links, colours, fonts and custom CSS for the UI, server-rendered pages, emails and API docs.
3. **Licence-gated features in MIT code**: opt in per feature with `LITELLM_OSS_UNLOCK`.

## 1. SSO user limit

`LITELLM_OSS_UNLOCK=sso` removes the billable-user cap for built-in SSO providers. `all` includes SSO. The original `SSO_FREE_USER_LIMIT` setting is still supported and takes priority when set. The database requirement and the premium-user bypass stay as upstream.

| `SSO_FREE_USER_LIMIT` | Behaviour |
|---|---|
| unset | 5 users, or unlimited when `sso` / `all` is unlocked |
| `N` | SSO allowed for up to N billable users |
| `0` | No limit |
| negative, empty or invalid | Configuration error, never silently unlimited |

Do not enable the custom SSO handler (`custom_sso_handler`), which lives in enterprise-licensed code. The opt-in SSO debug endpoint keeps its upstream licence check.

## 2. Branding

The patch adds `litellm/proxy/branding.py` and wires it in. Nothing on disk is modified: text responses are rewritten as they're served, so changing an env var and restarting changes the branding, and unsetting everything restores stock behaviour. With no `BRAND_*` variable set, the middleware is a pass-through.

| Variable | Effect |
|---|---|
| `BRAND_NAME` | Replaces "LiteLLM" in the UI, sign-in and CLI auth pages, emails, and the API docs title |
| `BRAND_TITLE` | Browser tab title (default `<BRAND_NAME> Dashboard`) |
| `BRAND_DESCRIPTION` | UI meta description |
| `BRAND_DOCS_URL` | Replaces links to docs.litellm.ai |
| `BRAND_GITHUB_URL` | Replaces links to github.com/BerriAI/litellm |
| `BRAND_WEBSITE_URL` | Replaces links to litellm.ai |
| `BRAND_PRIMARY_COLOR` / `BRAND_PRIMARY_FOREGROUND` | Primary colour and the text on it (buttons, active nav, focus ring), light mode |
| `BRAND_PRIMARY_COLOR_DARK` / `BRAND_PRIMARY_FOREGROUND_DARK` | Same for dark mode (default to the light values) |
| `BRAND_CSS_VARS` / `BRAND_CSS_VARS_DARK` | Any UI theme variable, e.g. `sidebar=#f5f7fa;radius=0.25rem;background=#fff` |
| `BRAND_FONT_FAMILY` / `BRAND_FONT_URL` | UI font, and a stylesheet to load it from |
| `BRAND_CUSTOM_CSS` / `BRAND_CUSTOM_CSS_URL` | Extra CSS, inline or from a URL, for anything the variables don't cover |
| `BRAND_EMAIL_FOOTER` | HTML replacing the default email footer; set to empty to remove it |
| `BRAND_PRESERVE_PHRASES` | Extra `\|`-separated phrases containing "LiteLLM" to leave unchanged |
| `DOCS_TITLE` / `DOCS_DESCRIPTION` / `DOCS_FILTERED` | API docs title, description, and hiding admin routes from the docs (no longer licence-gated) |

Logos and favicon use upstream's existing variables, which already work without a licence: `UI_LOGO_PATH`, `UI_LOGO_PATH_DARK`, `LITELLM_FAVICON_URL` and `EMAIL_LOGO_URL`.

UI theme variables you can set with `BRAND_CSS_VARS` include `background`, `foreground`, `card`, `primary`, `primary-foreground`, `secondary`, `muted`, `accent`, `border`, `input`, `ring`, `radius`, `sidebar`, `sidebar-foreground`, `sidebar-primary`, `sidebar-accent` and `chart-1` to `chart-5`. Colours accept any CSS value (`#0a5c8a`, `rgb(...)`, `oklch(...)`).

**Deliberately left unchanged:**
- Data values the UI compares against API responses ("LiteLLM Content Filter", "LiteLLM LLM as a Judge"), and "LiteLLM Enterprise" so licence messages stay accurate.
- Internal identifiers such as `LiteLLM_TeamTable`, and API/JSON responses, logs and response headers.
- Text that arrives from the API at runtime (for example guardrail provider names) still says LiteLLM.

## 3. Licence-gated features in MIT code

The patch adds `litellm/proxy/oss_unlock.py` and makes each licence check in MIT-licensed code opt-in per feature:

```
LITELLM_OSS_UNLOCK=jwt_auth,audit_logs,priority_reservation,ui   # specific features
LITELLM_OSS_UNLOCK=all                                            # everything below
```

With no unlock, SSO limit or branding settings, upstream behavior is preserved. Misspelt names are ignored with a warning at startup.

| Feature | What it enables |
|---|---|
| `admin_only_routes` | `general_settings.admin_only_routes` |
| `allowed_ips` | `general_settings.allowed_ips` |
| `allowed_routes` | `general_settings.allowed_routes` and extra public routes |
| `audit_logs` | Audit logs for management changes |
| `auto_router` | Unlimited auto-routers per classifier/customisation capability |
| `custom_team_metadata_validation` | `general_settings.custom_team_metadata_validate` |
| `dynamic_callback_disabling` | Disabling callbacks per request |
| `email_customization` | Custom logo and support contact in alert emails |
| `enforced_params` | `general_settings.enforced_params` |
| `fine_tuning` | `/fine_tuning` endpoints |
| `guardrail_dynamic_params` | Per-request guardrail `extra_body` |
| `jwt_auth` | JWT auth for the proxy and MCP token exchange |
| `key_rotation` | Regenerating virtual keys |
| `key_team_settings` | Guardrails, policies, tags, prompts, logging, secret manager settings, passthrough routes and key duration on keys/teams/projects |
| `logging_destinations` | GCS bucket, GCS Pub/Sub and Azure Blob logging |
| `model_access_groups` | Model access groups on wildcard routes |
| `model_audit_fields` | created/updated by/at on model info |
| `model_max_budget` | Per-model budgets on keys and teams |
| `oauth2_auth` | OAuth2 token validation |
| `organizations` | `/organization` endpoints |
| `priority_reservation` | TPM/RPM reservation by priority (`litellm_settings.priority_reservation`) |
| `request_size_limits` | `max_request_size_mb`, `max_response_size_mb`, `max_file_size_mb` |
| `secret_managers` | AWS KMS v2, Google, HashiCorp and CyberArk secret managers |
| `sso` | Unlimited users for built-in SSO providers |
| `spend_reports` | `/global/spend/report` and the `get_spend_routes` key permission |
| `tag_budgets` | Budgets per request tag |
| `team_admins` | Team admin role |
| `team_models` | Team-scoped models |
| `ui` | Shows licence-gated features in the admin UI |
| `worker_registry` | `general_settings.worker_registry` |

**Not unlockable (enterprise-licensed code):** Llama Guard, LLM Guard, secret detection, OpenAI and Google text moderation, blocked-user lists and banned keywords (all loaded from `enterprise/` or `litellm_enterprise`), tag-based guardrail modes, the custom SSO handler, enterprise email senders and the enterprise key/route hooks. Their checks are untouched. With `ui` unlocked the admin UI may still show some of these; using them fails with upstream's licence error.

**Not changed:** the licence health endpoint still reports `community`, and user/team count limits only apply to signed licences, so they never block without one.

## Patch maintenance

`patches/0001-oss-customizations.patch` contains all changes. `scripts/branding.py` and `scripts/oss_unlock.py` are the runtime module sources. `scripts/generate_patch.py` owns the integration edits. Edit these sources, then regenerate the patch. Do not edit the generated patch by hand.

Both local validation and CI use the same command against a **clean** upstream checkout:

```bash
python scripts/apply_patch.py upstream --check
python scripts/apply_patch.py upstream
```

The check regenerates the patch in memory, compares it with the committed patch, parses every changed Python file, checks added imports and target paths, then runs `git apply --check`. Applying uses one atomic `git apply` operation. Drift, stale generated output and repeat application fail without partially applying a patch. The check and generator do not modify the upstream checkout.

Each integration edit uses an exact source match or a unique anchor with a bounded search. If an upstream upgrade breaks an anchor, review and update that edit before regenerating. The shared licence helper requires an explicit feature name at reviewed call sites. New upstream callers keep their licence checks.

## Licence

Upstream LiteLLM outside `enterprise/` is MIT under its root licence. This repo contains patch sources, a generated patch, tests and a build workflow. It is not affiliated with or endorsed by BerriAI. Refer to the built image by this repo's name, not as "LiteLLM Enterprise".

Validation rejects patch targets outside `litellm/`, enterprise paths, and added direct or literal dynamic imports of `enterprise` / `litellm_enterprise`. This static check does not audit transitive imports or runtime behavior. Existing upstream enterprise integrations keep their checks. Preserve upstream licence notices when distributing images.

## Upgrading

Start with a clean checkout of the new upstream tag or commit, update `UPSTREAM_REF`, then run:

```bash
python scripts/generate_patch.py upstream
python scripts/apply_patch.py upstream --check
python scripts/apply_patch.py upstream
BRANDING_MODULE=upstream/litellm/proxy/branding.py \
OSS_UNLOCK_MODULE=upstream/litellm/proxy/oss_unlock.py \
python -m pytest -q tests
```

Commit the source changes, `UPSTREAM_REF` and regenerated patch together. Pull requests run validation and tests without publishing images. Main-branch pushes and manual runs validate first, then build the same resolved upstream commit and publish to GHCR.

Images receive the upstream tag and an upstream-tag plus patch-commit tag. `latest` changes only for main-branch builds using `UPSTREAM_REF`. A manual run may specify another upstream ref, but its generated patch must still match. Regenerate and commit it first when upstream code differs.

## Use

```yaml
services:
  litellm:
    image: ghcr.io/<owner>/litellm-sso:v1.105.1
    environment:
      LITELLM_OSS_UNLOCK: sso
      # Optional finite cap, even with sso/all enabled:
      # SSO_FREE_USER_LIMIT: "20"
      GENERIC_CLIENT_ID: ...
      GENERIC_CLIENT_SECRET: ...
      GENERIC_AUTHORIZATION_ENDPOINT: ...
      GENERIC_TOKEN_ENDPOINT: ...
      GENERIC_USERINFO_ENDPOINT: ...
      PROXY_BASE_URL: https://llm.example.internal

      BRAND_NAME: Acme AI
      BRAND_DOCS_URL: https://wiki.example.internal/ai-gateway
      BRAND_PRIMARY_COLOR: "#0a5c8a"
      BRAND_PRIMARY_FOREGROUND: "#ffffff"
      BRAND_PRIMARY_COLOR_DARK: "#4fb3e8"
      BRAND_FONT_FAMILY: "'Source Sans 3', sans-serif"
      BRAND_FONT_URL: https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600&display=swap
      UI_LOGO_PATH: https://cdn.example.internal/logo.svg
      UI_LOGO_PATH_DARK: https://cdn.example.internal/logo-dark.svg
      LITELLM_FAVICON_URL: https://cdn.example.internal/favicon.ico
```

## Tests

```bash
pip install 'starlette>=0.40,<1' 'httpx>=0.27,<1' 'pytest>=8,<10'
BRANDING_MODULE=upstream/litellm/proxy/branding.py \
OSS_UNLOCK_MODULE=upstream/litellm/proxy/oss_unlock.py \
python -m pytest -q tests
```

Tests load the patched runtime modules and selected gate functions without installing the full proxy. They cover SSO boundaries, configuration precedence, the database and premium paths, branding, and patch failure handling. They do not replace a live SSO-provider login test or a full image build.
