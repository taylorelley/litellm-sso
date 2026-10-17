# litellm-sso

Builds the upstream [LiteLLM](https://github.com/BerriAI/litellm) proxy image with one small change: the SSO user limit is read from an environment variable instead of being fixed at 5.

## What the patch changes

`patches/sso-user-limit.patch` edits `_raise_if_sso_exceeds_free_user_limit` in
`litellm/proxy/management_endpoints/ui_sso.py`, which is MIT-licensed code (outside `enterprise/`).

| `SSO_FREE_USER_LIMIT` | Behaviour |
|---|---|
| unset | Upstream default (5 users) |
| `N` | SSO allowed for up to N billable users |
| `0` | No limit |

Nothing else changes. The patch does not touch, import or enable anything under upstream's `enterprise/` directory (the build fails if it ever does). Do not enable the custom SSO handler (`custom_sso_handler`), which lives in enterprise-licensed code. The opt-in SSO debug endpoint keeps its upstream licence check.

## Licence

Upstream LiteLLM outside `enterprise/` is MIT. This repo carries only the patch and build workflow. It is not affiliated with or endorsed by BerriAI; refer to the built image by this repo's name, not as "LiteLLM Enterprise".

## Upgrading

1. Change `UPSTREAM_REF` to the new upstream tag and push.
2. The workflow checks out that tag, applies the patch, and builds and pushes `ghcr.io/<owner>/litellm-sso:<tag>`.
3. If upstream has moved or renamed the check, `git apply --check` fails the build. Regenerate the patch against the new tag.

You can also run the workflow manually with any upstream tag or commit.

## Use

```yaml
services:
  litellm:
    image: ghcr.io/<owner>/litellm-sso:v1.105.1
    environment:
      SSO_FREE_USER_LIMIT: "0"
      GENERIC_CLIENT_ID: ...
      GENERIC_CLIENT_SECRET: ...
      GENERIC_AUTHORIZATION_ENDPOINT: ...
      GENERIC_TOKEN_ENDPOINT: ...
      GENERIC_USERINFO_ENDPOINT: ...
      PROXY_BASE_URL: https://llm.example.internal
```
