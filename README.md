# litellm-unlocked

[LiteLLM](https://github.com/BerriAI/litellm) proxy images with configurable access to 30 licence-gated capabilities implemented in MIT-licensed code, plus UI, email and API documentation customisation. One generated patch applies the changes to a pinned upstream version.

Choose individual features with `LITELLM_OSS_UNLOCK`, or use `all`. SSO is one of the supported features alongside authentication, access controls, teams, organizations, budgets, routing, logging and secret-manager integrations. With no patch settings, upstream behaviour is preserved.

## What the patches add

| Area | Unlocked or enhanced functionality |
|---|---|
| Authentication and access | JWT and OAuth2 validation, MCP token exchange, built-in SSO without the default user cap, IP allowlists and route controls |
| Teams, organizations and keys | Organization endpoints, team admins, team-scoped models, virtual-key regeneration and additional key/team/project settings |
| Budgets and usage | Per-model budgets, tag budgets, spend reports and priority-based TPM/RPM reservation |
| Routing and request controls | Auto-router limits, wildcard model-access groups, required parameters, request/response/file size limits and per-request guardrail parameters |
| Operations and integrations | Management audit logs, model audit fields, worker registry, cloud logging destinations, secret managers, fine-tuning endpoints, custom metadata validation and per-request callback disabling |
| UI, emails and API docs | Admin UI feature visibility, product names, titles, links, light/dark themes, fonts, CSS, email footers, alert-email customisation and API docs titles, descriptions and route filtering |

These are targeted changes to MIT-licensed implementations. Unlocking a feature still requires its upstream configuration, credentials, permissions and dependencies. Separately licensed enterprise implementations retain their checks; see the scope below.

## Feature switches

```bash
# Enable selected capabilities:
LITELLM_OSS_UNLOCK=jwt_auth,organizations,audit_logs,tag_budgets,ui

# Enable all 30 feature switches:
LITELLM_OSS_UNLOCK=all
```

| Variable | Type | Default | Example | Effect |
|---|---|---|---|---|
| `LITELLM_OSS_UNLOCK` | comma-separated feature names | unset, all gates locked | `jwt_auth,audit_logs,organizations` | Enable listed MIT-code features; `all` includes every name in the feature table |

Feature names ignore case and surrounding spaces. Unknown names produce a startup warning and remain disabled. The switch is read at call time, including values supplied through the proxy config's `environment_variables`. It does not change the global premium/licence state or configure the features for you.

### Complete feature catalogue

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

### Scope and limits

**Not unlockable (enterprise-licensed code):** Llama Guard, LLM Guard, secret detection, OpenAI and Google text moderation, blocked-user lists and banned keywords (all loaded from `enterprise/` or `litellm_enterprise`), tag-based guardrail modes, the custom SSO handler, enterprise email senders and the enterprise key/route hooks. Their checks are untouched. With `ui` unlocked the admin UI may still show some of these; using them fails with upstream's licence error.

**Not changed:** the licence health endpoint still reports `community`, and user/team count limits only apply to signed licences, so they never block without one.

## Branding and API documentation

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

## Built-in SSO user limits

`LITELLM_OSS_UNLOCK=sso` removes the billable-user cap for built-in SSO providers. `all` includes SSO. The original `SSO_FREE_USER_LIMIT` setting is still supported and takes priority when set. The database requirement and the premium-user bypass stay as upstream.

| `SSO_FREE_USER_LIMIT` | Behaviour |
|---|---|
| unset | 5 users, or unlimited when `sso` / `all` is unlocked |
| `N` | SSO allowed for up to N billable users |
| `0` | No limit |
| negative, empty or invalid | Configuration error, never silently unlimited |

| Variable | Type | Default | Example | Effect |
|---|---|---|---|---|
| `SSO_FREE_USER_LIMIT` | non-negative integer | 5, or 0 with sso/all unlocked | `20` | Explicit value overrides sso/all; 0 is unlimited |

The database requirement and premium-user bypass remain as upstream. The custom SSO handler (`custom_sso_handler`) lives in enterprise-licensed code and is not unlocked. The opt-in SSO debug endpoint retains its upstream licence check.

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

Images receive `<sanitized-upstream-ref>-<ref-hash>` and `<sanitized-upstream-ref>-<ref-hash>-<build-sha>` tags. The ref hash is the first 16 hex characters of SHA-256 of the original ref; the build suffix is the first 12 characters of the project commit SHA. Long ref names are shortened to keep tags within 128 characters. Distinct refs that sanitize to the same name retain different ref hashes. `latest` changes only for main-branch builds using `UPSTREAM_REF`. A manual run may specify another upstream ref, but its generated patch must still match. Regenerate and commit it first when upstream code differs.

## Use

The workflow publishes `ghcr.io/taylorelley/litellm-unlocked` after a successful main-branch build. Select a tested tag or digest for deployment; `latest` follows the pinned upstream version. Renaming the repository does not move existing packages published under the old image name.

Add these settings to your existing LiteLLM Compose service. Keep your upstream model configuration, authentication settings and database connection as needed by the features you choose.

```yaml
services:
  litellm:
    image: ghcr.io/taylorelley/litellm-unlocked:latest
    command: ["--config", "/app/config.yaml", "--port", "4000"]
    ports:
      - "4000:4000"
    volumes:
      - ./config.yaml:/app/config.yaml:ro
    environment:
      LITELLM_OSS_UNLOCK: jwt_auth,organizations,audit_logs,tag_budgets,ui
      # Or enable every listed feature:
      # LITELLM_OSS_UNLOCK: all
      BRAND_NAME: Acme AI
      BRAND_DOCS_URL: https://wiki.example.internal/ai-gateway
      BRAND_PRIMARY_COLOR: "#0a5c8a"
      BRAND_PRIMARY_FOREGROUND: "#ffffff"
      BRAND_PRIMARY_COLOR_DARK: "#4fb3e8"
      DOCS_TITLE: Acme AI Gateway API
      DOCS_DESCRIPTION: Internal model gateway
      DOCS_FILTERED: "True"
```

The switches remove the reviewed licence gates. Configure the corresponding upstream settings separately, such as JWT validation, audit storage, budgets or your SSO provider. To include unlimited built-in SSO, add `sso` or use `all`; set `SSO_FREE_USER_LIMIT` only if you want an explicit cap.

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
python scripts/smoke_image.py litellm-unlocked:candidate --upstream upstream --logs smoke-logs
```

Test tooling variables are `BRANDING_MODULE` (default `upstream/litellm/proxy/branding.py`) and `OSS_UNLOCK_MODULE` (default `upstream/litellm/proxy/oss_unlock.py`). They select files for unit tests and are not image runtime settings. CI's `REQUESTED_REF`, `IMAGE_REPOSITORY`, `TESTED_IMAGE_ID` and `IMAGE_TAGS` are internal workflow values, not proxy settings. The smoke harness uses upstream's `LITELLM_LOCAL_MODEL_COST_MAP=True` to avoid fetching prices.

These checks reduce release risk. They do not prove every upstream feature or deployment is correct. Live Authentik/OIDC login, real database migrations, production secret managers, external logging destinations and real model providers still need environment-specific acceptance tests. Keep a known-good immutable image tag or digest for rollback. Protect the default branch with the unit-test and image-smoke checks required before merging.
