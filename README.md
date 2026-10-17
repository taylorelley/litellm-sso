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

| Variable | Type | Default | Example | Effect |
|---|---|---|---|---|
| `LITELLM_OSS_UNLOCK` | comma-separated feature names | unset, all gates locked | `sso,audit_logs` | Enable listed MIT-code features; `all` includes every name in the feature table |
| `SSO_FREE_USER_LIMIT` | non-negative integer | 5, or 0 with sso/all unlocked | `20` | Explicit value overrides sso/all; 0 is unlimited |

Feature names ignore case and surrounding spaces. Unknown names produce a startup warning and remain disabled. Unlocking a feature does not configure it: upstream settings, credentials, permissions and dependencies still apply. The global premium/licence state is not changed.

Do not enable the custom SSO handler (`custom_sso_handler`), which lives in enterprise-licensed code. The opt-in SSO debug endpoint keeps its upstream licence check.

## 2. Branding

The patch adds `litellm/proxy/branding.py` and wires it in. Nothing on disk is modified: text responses are rewritten as they're served, so changing an env var and restarting changes the branding, and unsetting everything restores stock behaviour. With no `BRAND_*` variable set, the middleware is a pass-through. Whitespace-only branding values are treated as unset, except `BRAND_EMAIL_FOOTER`, where an empty value removes the footer. CSS values containing `<` are rejected. Set these values in the container environment and restart after changes. Branding settings are cached after first use; the unlock switch and SSO limit are read at call time. API docs settings are read during module import, so set them before startup rather than in YAML `environment_variables`.

| Variable | Type | Default | Example | Effect |
|---|---|---|---|---|
| `BRAND_NAME` | string | unset | `Acme AI` | Product name in UI, server pages, emails and default API title |
| `BRAND_TITLE` | string | `<BRAND_NAME> Dashboard`, otherwise stock | `AI Portal` | UI browser title; overrides name-derived title |
| `BRAND_DESCRIPTION` | string | stock description | `Internal AI gateway` | UI meta description |
| `BRAND_DOCS_URL` | URL | upstream links | `https://wiki.example/ai` | Replace docs.litellm.ai links |
| `BRAND_GITHUB_URL` | URL | upstream links | `https://git.example/ai` | Replace GitHub repository links |
| `BRAND_WEBSITE_URL` | URL | upstream links | `https://example.internal` | Replace litellm.ai links |
| `BRAND_PRIMARY_COLOR` | CSS value | stock theme | `#0a5c8a` | Primary, sidebar-primary and ring in light mode |
| `BRAND_PRIMARY_FOREGROUND` | CSS value | stock theme | `#ffffff` | Primary and sidebar-primary text in light mode |
| `BRAND_PRIMARY_COLOR_DARK` | CSS value | BRAND_PRIMARY_COLOR | `#4fb3e8` | Primary, sidebar-primary and ring in dark mode |
| `BRAND_PRIMARY_FOREGROUND_DARK` | CSS value | BRAND_PRIMARY_FOREGROUND | `#001122` | Primary and sidebar-primary text in dark mode |
| `BRAND_CSS_VARS` | name=value pairs | none | `sidebar=#f5f7fa;radius=0.25rem` | Light CSS overrides; these win over primary shortcuts |
| `BRAND_CSS_VARS_DARK` | name=value pairs | none | `background=#111;card=#222` | Dark CSS overrides; these win over dark primary shortcuts |
| `BRAND_FONT_FAMILY` | CSS font-family | stock font | `"Source Sans 3", sans-serif` | UI font family |
| `BRAND_FONT_URL` | stylesheet URL | none | `https://fonts.example/font.css` | Font stylesheet link |
| `BRAND_CUSTOM_CSS` | CSS text | none | `body{letter-spacing:0.01em}` | Inline UI CSS after variable overrides |
| `BRAND_CUSTOM_CSS_URL` | stylesheet URL | none | `https://cdn.example/brand.css` | Extra stylesheet loaded after inline overrides |
| `BRAND_EMAIL_FOOTER` | HTML | stock footer | `<footer>Internal service</footer>` | Replace email footer; an explicitly empty value removes it |
| `BRAND_PRESERVE_PHRASES` | pipe-separated strings | built-in protected phrases | `LiteLLM Proxy Server` | Extra exact phrases excluded from name replacement |
| `DOCS_TITLE` | string | `<BRAND_NAME> API`, otherwise LiteLLM API | `Acme API` | OpenAPI and API documentation title |
| `DOCS_DESCRIPTION` | string | upstream description | `Internal model gateway` | API documentation description |
| `DOCS_FILTERED` | exact string True or False | False | `True` | Remove admin routes from API docs; does not disable those routes |

Logos and favicon use upstream's existing variables, which already work without a licence: `UI_LOGO_PATH`, `UI_LOGO_PATH_DARK`, `LITELLM_FAVICON_URL` and `EMAIL_LOGO_URL`.

UI theme variables you can set with `BRAND_CSS_VARS` include `background`, `foreground`, `card`, `primary`, `primary-foreground`, `secondary`, `muted`, `accent`, `border`, `input`, `ring`, `radius`, `sidebar`, `sidebar-foreground`, `sidebar-primary`, `sidebar-accent` and `chart-1` to `chart-5`. Colours accept any CSS value (`#0a5c8a`, `rgb(...)`, `oklch(...)`).

**Deliberately left unchanged:**
- Data values the UI compares against API responses ("LiteLLM Content Filter", "LiteLLM LLM as a Judge"), and "LiteLLM Enterprise" so licence messages stay accurate.
- Internal identifiers such as `LiteLLM_TeamTable`, and API/JSON responses, logs and response headers.
- Text that arrives from the API at runtime (for example guardrail provider names) still says LiteLLM.

## 3. Licence-gated features in MIT code

The patch adds `litellm/proxy/oss_unlock.py` and makes the audited licence checks in MIT-licensed code opt-in per feature:

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

Commit the source changes, `UPSTREAM_REF` and regenerated patch together. Pull requests validate the patch, run tests on Python 3.12 and 3.13, then build and smoke-test a candidate image without publishing. Main-branch pushes and manual runs use the same checks. Publishing tags happens only after that exact image ID passes smoke tests. A failed build, import, UI syntax check, runtime test or HTTP smoke test blocks publishing.

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
pip install -r requirements-test.txt
BRANDING_MODULE=upstream/litellm/proxy/branding.py \
OSS_UNLOCK_MODULE=upstream/litellm/proxy/oss_unlock.py \
python -m pytest -q tests
```

Unit tests exercise all audited gate sites with locked, selective, unrelated and all-feature settings, plus premium/false/unknown states. They cover SSO limits, defaults and precedence, every branding setting, email footers, JavaScript escaping, middleware behavior, patch failure handling, and README coverage. Node.js is needed for JavaScript regression tests. Keep the upstream directory as a Git checkout: gate comparisons use its unpatched `HEAD` as the expected behavior.

The candidate-image tests verify the installed bytes and import every patched module, parse rewritten JavaScript from the actual built UI, and run installed SSO, organization, audit and shared-gate checks. HTTP smoke tests start the stock, SSO-enabled and all-features-plus-branding configurations. They check readiness, liveness, authentication, model listing, a mock completion, SSE streaming, API docs, UI, compression and asset serving. No external model credentials are needed.

```bash
python scripts/smoke_image.py litellm-sso:candidate --upstream upstream --logs smoke-logs
```

Test tooling variables are `BRANDING_MODULE` (default `upstream/litellm/proxy/branding.py`) and `OSS_UNLOCK_MODULE` (default `upstream/litellm/proxy/oss_unlock.py`). They select files for unit tests and are not image runtime settings. CI's `REQUESTED_REF`, `IMAGE_REPOSITORY`, `TESTED_IMAGE_ID` and `IMAGE_TAGS` are internal workflow values, not proxy settings. The smoke harness uses upstream's `LITELLM_LOCAL_MODEL_COST_MAP=True` to avoid fetching prices.

These checks reduce release risk. They do not prove every upstream feature or deployment is correct. Live Authentik/OIDC login, real database migrations, production secret managers, external logging destinations and real model providers still need environment-specific acceptance tests. Keep a known-good immutable image tag or digest for rollback. Protect the default branch with the unit-test and image-smoke checks required before merging.
