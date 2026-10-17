"""
Env-var driven branding for the proxy UI, server-rendered HTML pages and emails.

Nothing on disk is modified. Text responses are rewritten as they are served, so
branding can be changed (or removed) by changing env vars and restarting.

All settings are optional; with none set, the middleware is a pass-through.

    BRAND_NAME                 Replaces the product name "LiteLLM" in UI text, page titles,
                               server-rendered pages, emails and the API docs title.
    BRAND_TITLE                Browser tab title for the UI (default: "<BRAND_NAME> Dashboard").
    BRAND_DESCRIPTION          HTML meta description for the UI.
    BRAND_DOCS_URL             Replaces links to docs.litellm.ai.
    BRAND_GITHUB_URL           Replaces links to github.com/BerriAI/litellm.
    BRAND_WEBSITE_URL          Replaces links to litellm.ai.
    BRAND_PRIMARY_COLOR        Primary colour (buttons, active nav, focus ring), light mode.
    BRAND_PRIMARY_FOREGROUND   Text colour on primary, light mode.
    BRAND_PRIMARY_COLOR_DARK   Primary colour, dark mode (defaults to BRAND_PRIMARY_COLOR).
    BRAND_PRIMARY_FOREGROUND_DARK
    BRAND_CSS_VARS             Any UI CSS variables, light mode: "background=#fff;sidebar=#f4f4f5".
    BRAND_CSS_VARS_DARK        Same, dark mode.
    BRAND_FONT_FAMILY          CSS font-family for the UI.
    BRAND_FONT_URL             Stylesheet URL for the font (e.g. Google Fonts).
    BRAND_CUSTOM_CSS           Raw CSS appended to the UI.
    BRAND_CUSTOM_CSS_URL       Stylesheet URL appended to the UI.
    BRAND_PRESERVE_PHRASES     Extra "|"-separated phrases containing "LiteLLM" to leave unchanged.
    BRAND_EMAIL_FOOTER         HTML replacing the default email footer (empty string removes it).

Logos and favicon use upstream's existing settings: UI_LOGO_PATH, UI_LOGO_PATH_DARK,
LITELLM_FAVICON_URL and EMAIL_LOGO_URL.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Final

from starlette.types import ASGIApp, Message, Receive, Scope, Send

UPSTREAM_NAME: Final = "LiteLLM"

# Phrases that the UI compares against values returned by the API (or that name
# upstream's commercial offering); rewriting them would break behaviour or misattribute.
_DEFAULT_PRESERVED: Final = (
    "LiteLLM Content Filter",
    "LiteLLM LLM as a Judge",
    "LiteLLM Enterprise",
)

_NAME_RE: Final = re.compile(r"(?:\U0001F685\s?)?(?<![\w$])LiteLLM(?![\w$])")
# URL bodies stop at quotes, whitespace and anything that could belong to surrounding code
# (template-literal ${...}, call parentheses), so only the literal URL text is replaced.
_URL_BODY: Final = r"[^\s\"'`<>(){}$\\]*"
_DOCS_URL_RE: Final = re.compile(r"https?://docs\.litellm\.ai" + _URL_BODY)
_GITHUB_URL_RE: Final = re.compile(r"https?://github\.com/BerriAI/litellm(?![\w-])" + _URL_BODY, re.IGNORECASE)
_WEBSITE_URL_RE: Final = re.compile(r"https?://(?:www\.)?litellm\.ai(?![\w.-])/?(?=[\s\"'`<>)\\]|$)")

_CSS_VAR_NAME_RE: Final = re.compile(r"^[A-Za-z0-9-]+$")

UI_PATH_MARKERS: Final = ("/ui", "/_next/", "/litellm-asset-prefix/")
_TEXT_TYPES_ANY_PATH: Final = ("text/html",)
_TEXT_TYPES_UI: Final = (
    "text/html",
    "application/javascript",
    "text/javascript",
    "text/css",
    "text/plain",
    "text/x-component",
)
_MAX_BODY: Final = 16 * 1024 * 1024
_CACHE_SIZE: Final = 512


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _safe_css(value: str, setting: str) -> str:
    """Env values are operator-controlled, but never let one close the <style> element."""
    if "<" in value:
        raise ValueError(f"{setting} must not contain '<'")
    return value


def _parse_css_vars(raw: str | None, setting: str) -> dict[str, str]:
    result: dict[str, str] = {}
    if not raw:
        return result
    for part in raw.split(";"):
        if not part.strip():
            continue
        if "=" not in part:
            raise ValueError(f"{setting}: expected name=value, got {part!r}")
        name, value = (s.strip() for s in part.split("=", 1))
        name = name.removeprefix("--")
        if not _CSS_VAR_NAME_RE.match(name):
            raise ValueError(f"{setting}: invalid CSS variable name {name!r}")
        result[name] = _safe_css(value, setting)
    return result


@dataclass(frozen=True)
class BrandingConfig:
    name: str | None = None
    title: str | None = None
    description: str | None = None
    docs_url: str | None = None
    github_url: str | None = None
    website_url: str | None = None
    css_vars: dict[str, str] = field(default_factory=dict)
    css_vars_dark: dict[str, str] = field(default_factory=dict)
    font_family: str | None = None
    font_url: str | None = None
    custom_css: str | None = None
    custom_css_url: str | None = None
    preserved: tuple[str, ...] = _DEFAULT_PRESERVED
    email_footer: str | None = None

    @property
    def enabled(self) -> bool:
        return any(
            (
                self.name,
                self.title,
                self.description,
                self.docs_url,
                self.github_url,
                self.website_url,
                self.css_vars,
                self.css_vars_dark,
                self.font_family,
                self.font_url,
                self.custom_css,
                self.custom_css_url,
            )
        )

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(repr(self).encode()).hexdigest()[:16]

    @classmethod
    def from_env(cls) -> BrandingConfig:
        css_vars: dict[str, str] = {}
        css_vars_dark: dict[str, str] = {}

        primary = _env("BRAND_PRIMARY_COLOR")
        primary_fg = _env("BRAND_PRIMARY_FOREGROUND")
        primary_dark = _env("BRAND_PRIMARY_COLOR_DARK") or primary
        primary_fg_dark = _env("BRAND_PRIMARY_FOREGROUND_DARK") or primary_fg
        for target, color, fg, suffix in (
            (css_vars, primary, primary_fg, ""),
            (css_vars_dark, primary_dark, primary_fg_dark, "_DARK"),
        ):
            if color:
                color = _safe_css(color, f"BRAND_PRIMARY_COLOR{suffix}")
                target.update({"primary": color, "sidebar-primary": color, "ring": color})
            if fg:
                fg = _safe_css(fg, f"BRAND_PRIMARY_FOREGROUND{suffix}")
                target.update({"primary-foreground": fg, "sidebar-primary-foreground": fg})

        css_vars.update(_parse_css_vars(_env("BRAND_CSS_VARS"), "BRAND_CSS_VARS"))
        css_vars_dark.update(_parse_css_vars(_env("BRAND_CSS_VARS_DARK"), "BRAND_CSS_VARS_DARK"))

        extra_preserved = tuple(p.strip() for p in (_env("BRAND_PRESERVE_PHRASES") or "").split("|") if p.strip())
        font_family = _env("BRAND_FONT_FAMILY")
        custom_css = _env("BRAND_CUSTOM_CSS")
        name = _env("BRAND_NAME")
        return cls(
            name=name,
            title=_env("BRAND_TITLE") or (f"{name} Dashboard" if name else None),
            description=_env("BRAND_DESCRIPTION"),
            docs_url=_env("BRAND_DOCS_URL"),
            github_url=_env("BRAND_GITHUB_URL"),
            website_url=_env("BRAND_WEBSITE_URL"),
            css_vars=css_vars,
            css_vars_dark=css_vars_dark,
            font_family=_safe_css(font_family, "BRAND_FONT_FAMILY") if font_family else None,
            font_url=_env("BRAND_FONT_URL"),
            custom_css=_safe_css(custom_css, "BRAND_CUSTOM_CSS") if custom_css else None,
            custom_css_url=_env("BRAND_CUSTOM_CSS_URL"),
            preserved=_DEFAULT_PRESERVED + extra_preserved,
            # None = keep upstream footer; "" = remove it.
            email_footer=os.getenv("BRAND_EMAIL_FOOTER"),
        )


@lru_cache(maxsize=1)
def get_branding() -> BrandingConfig:
    """Read once, on first use, so env vars loaded from the proxy YAML are seen."""
    return BrandingConfig.from_env()


def _html_attr(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def _html_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _is_bare_object_key(text: str, match: re.Match[str]) -> bool:
    """`{LiteLLM: ...}` / `,LiteLLM:` in minified JS is code, not display text."""
    before = text[max(0, match.start() - 2) : match.start()].rstrip()
    after = text[match.end() : match.end() + 2].lstrip()
    return before.endswith(("{", ",")) and after.startswith(":")


def brand_text(text: str, config: BrandingConfig | None = None, *, html: bool = False, javascript: bool = False) -> str:
    """Apply name and link substitutions. Safe on HTML, JS, CSS and plain text."""
    config = config or get_branding()
    if not config.enabled:
        return text

    def replacement(value: str) -> str:
        if javascript:
            encoded = json.dumps(value, ensure_ascii=True)[1:-1]
            for char in "'`$<>":
                encoded = encoded.replace(char, f"\\u{ord(char):04x}")
            return encoded
        return _html_attr(value) if html else value

    if config.docs_url:
        text = _DOCS_URL_RE.sub(lambda _m: replacement(config.docs_url or ""), text)
    if config.github_url:
        text = _GITHUB_URL_RE.sub(lambda _m: replacement(config.github_url or ""), text)
    if config.website_url:
        text = _WEBSITE_URL_RE.sub(lambda _m: replacement(config.website_url or ""), text)

    if config.title:
        title = replacement(config.title)
        text = text.replace("LiteLLM Dashboard", title)
    if config.description:
        desc = replacement(config.description)
        text = text.replace("LiteLLM Proxy Admin UI", desc)

    if config.name and UPSTREAM_NAME in text:
        placeholders: dict[str, str] = {}
        for i, phrase in enumerate(sorted(config.preserved, key=len, reverse=True)):
            if phrase in text:
                token = f"\x00BRANDKEEP{i}\x00"
                placeholders[token] = phrase
                text = text.replace(phrase, token)
        name = replacement(config.name)
        text = _NAME_RE.sub(lambda m: m.group(0) if _is_bare_object_key(text, m) else name, text)
        for token, phrase in placeholders.items():
            text = text.replace(token, phrase)
    return text


def build_head_injection(config: BrandingConfig) -> str:
    parts: list[str] = []
    if config.font_url:
        parts.append(f'<link rel="stylesheet" href="{_html_attr(config.font_url)}">')

    css: list[str] = []
    if config.css_vars:
        decls = "".join(f"--{k}:{v};" for k, v in config.css_vars.items())
        css.append(f"html:root{{{decls}}}")
    if config.css_vars_dark:
        decls = "".join(f"--{k}:{v};" for k, v in config.css_vars_dark.items())
        css.append(f"html.dark{{{decls}}}")
    if config.font_family:
        css.append(f"html body{{font-family:{config.font_family} !important}}")
    if config.custom_css:
        css.append(config.custom_css)
    if css:
        parts.append(f'<style id="brand-overrides">{"".join(css)}</style>')

    if config.custom_css_url:
        parts.append(f'<link rel="stylesheet" href="{_html_attr(config.custom_css_url)}">')
    return "".join(parts)


def brand_html_document(text: str, config: BrandingConfig | None = None, *, inject_head: bool) -> str:
    config = config or get_branding()
    parts = re.split(r"(<script\b[^>]*>)(.*?)(</script\s*>)", text, flags=re.IGNORECASE | re.DOTALL)
    for i in range(len(parts)):
        if i % 4 == 2:
            parts[i] = brand_text(parts[i], config, javascript=True)
        elif i % 4 != 3:
            parts[i] = brand_text(parts[i], config, html=True)
    text = "".join(parts)
    if inject_head:
        injection = build_head_injection(config)
        if injection and "</head>" in text and 'id="brand-overrides"' not in text:
            text = text.replace("</head>", injection + "</head>", 1)
    return text


def brand_email(subject: str, html: str) -> tuple[str, str]:
    config = get_branding()
    if config.email_footer is not None:
        from litellm.integrations.email_templates.email_footer import EMAIL_FOOTER

        html = html.replace(EMAIL_FOOTER, config.email_footer)
    return brand_text(subject, config), brand_text(html, config, html=True)


def _is_ui_path(path: str) -> bool:
    return any(marker in path for marker in UI_PATH_MARKERS)


class BrandingMiddleware:
    """
    Rewrites text responses for branding. Only buffers responses whose content type is
    HTML (any path) or a UI asset type (UI paths only); everything else, including
    streamed LLM responses, passes straight through.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._cache: OrderedDict[tuple[str, str, bool, bool], tuple[bytes, str]] = OrderedDict()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") != "GET":
            await self.app(scope, receive, send)
            return
        config = get_branding()
        if not config.enabled:
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        ui_path = _is_ui_path(path)

        # Conditional requests would let browsers keep unbranded or stale-branded copies,
        # so the inner app always sends a full body and this middleware owns validation.
        client_etag: str | None = None
        headers = []
        for k, v in scope.get("headers", []):
            if k == b"if-none-match":
                client_etag = v.decode("latin-1")
                continue
            if k == b"if-modified-since":
                continue
            headers.append((k, v))
        inner_scope = dict(scope, headers=headers)

        start: Message | None = None
        chunks: list[bytes] = []
        passthrough = False
        size = 0

        async def wrapped_send(message: Message) -> None:
            nonlocal start, passthrough, size
            if message["type"] == "http.response.start":
                content_type = ""
                encoded = False
                for k, v in message.get("headers", []):
                    if k == b"content-type":
                        content_type = v.decode("latin-1").lower()
                    elif k == b"content-encoding":
                        encoded = True
                allowed = _TEXT_TYPES_UI if ui_path else _TEXT_TYPES_ANY_PATH
                if encoded or message.get("status") != 200 or not content_type.startswith(allowed):
                    passthrough = True
                    await send(message)
                    return
                start = message
                return
            if passthrough:
                await send(message)
                return
            if message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))
                size += len(chunks[-1])
                if size > _MAX_BODY:
                    # Too large to rewrite safely: flush what we have unmodified.
                    passthrough = True
                    assert start is not None
                    await send(start)
                    await send({"type": "http.response.body", "body": b"".join(chunks), "more_body": True})
                    if not message.get("more_body", False):
                        await send({"type": "http.response.body", "body": b"", "more_body": False})
                    return
                if not message.get("more_body", False):
                    await self._finish(start, b"".join(chunks), path, config, client_etag, send)
                return
            await send(message)

        await self.app(inner_scope, receive, wrapped_send)

    async def _finish(
        self,
        start: Message | None,
        body: bytes,
        path: str,
        config: BrandingConfig,
        client_etag: str | None,
        send: Send,
    ) -> None:
        assert start is not None
        source_hash = hashlib.sha256(body).hexdigest()
        content_type = next((v for k, v in start.get("headers", []) if k == b"content-type"), b"").decode("latin-1")
        is_html = content_type.lower().startswith("text/html")
        key = (source_hash, config.fingerprint, is_html, _is_ui_path(path))
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            new_body, etag = cached
        else:
            try:
                text = body.decode("utf-8")
            except UnicodeDecodeError:
                new_body, etag = body, f'"{source_hash[:32]}"'
            else:
                if is_html:
                    text = brand_html_document(text, config, inject_head=_is_ui_path(path))
                else:
                    text = brand_text(text, config, javascript="javascript" in content_type.lower())
                new_body = text.encode("utf-8")
                etag = f'"{hashlib.sha256(new_body).hexdigest()[:32]}"'
            self._cache[key] = (new_body, etag)
            if len(self._cache) > _CACHE_SIZE:
                self._cache.popitem(last=False)

        drop = {b"content-length", b"etag", b"last-modified"}
        headers = [(k, v) for k, v in start.get("headers", []) if k not in drop]
        headers.append((b"etag", etag.encode("latin-1")))

        if client_etag is not None and etag in (t.strip() for t in client_etag.split(",")):
            await send({"type": "http.response.start", "status": 304, "headers": headers})
            await send({"type": "http.response.body", "body": b""})
            return

        headers.append((b"content-length", str(len(new_body)).encode("latin-1")))
        await send({"type": "http.response.start", "status": 200, "headers": headers})
        await send({"type": "http.response.body", "body": new_body})
