"""
Tests for litellm/proxy/branding.py. The module is loaded straight from the patched
upstream checkout so the full LiteLLM dependency tree isn't needed.

    BRANDING_MODULE=path/to/litellm/proxy/branding.py pytest tests/
"""

import importlib.util
import os
import sys

import pytest
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route
from starlette.testclient import TestClient

_path = os.environ.get("BRANDING_MODULE", "upstream/litellm/proxy/branding.py")
_spec = importlib.util.spec_from_file_location("branding", _path)
branding = importlib.util.module_from_spec(_spec)
sys.modules["branding"] = branding
_spec.loader.exec_module(branding)

BRAND_ENV = [k for k in os.environ if k.startswith("BRAND_")]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in list(os.environ):
        if k.startswith("BRAND_"):
            monkeypatch.delenv(k)
    branding.get_branding.cache_clear()
    yield
    branding.get_branding.cache_clear()


def cfg(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    branding.get_branding.cache_clear()
    return branding.get_branding()


# ---------- text rewriting ----------


def test_disabled_is_noop():
    text = "Thanks for using LiteLLM! https://docs.litellm.ai/x"
    assert branding.brand_text(text, branding.BrandingConfig()) == text


def test_name_replaced_on_word_boundaries_only(monkeypatch):
    c = cfg(monkeypatch, BRAND_NAME="Acme AI")
    src = 'a="Thanks for using LiteLLM!";b="LiteLLM_TeamTable";c=LiteLLMParams;d="LiteLLM-side name";e=$LiteLLM'
    out = branding.brand_text(src, c)
    assert '"Thanks for using Acme AI!"' in out
    assert '"LiteLLM_TeamTable"' in out
    assert "LiteLLMParams" in out
    assert '"Acme AI-side name"' in out
    assert "$LiteLLM" in out


def test_preserved_phrases_untouched(monkeypatch):
    c = cfg(monkeypatch, BRAND_NAME="Acme", BRAND_PRESERVE_PHRASES="LiteLLM Proxy Server|LiteLLM Foo")
    src = "LiteLLM Content Filter / LiteLLM LLM as a Judge / LiteLLM Enterprise / LiteLLM Proxy Server / LiteLLM"
    out = branding.brand_text(src, c)
    assert out == "LiteLLM Content Filter / LiteLLM LLM as a Judge / LiteLLM Enterprise / LiteLLM Proxy Server / Acme"


def test_train_emoji_dropped_with_name(monkeypatch):
    c = cfg(monkeypatch, BRAND_NAME="Acme")
    assert branding.brand_text("<h1>\U0001f685 LiteLLM</h1>", c) == "<h1>Acme</h1>"


def test_title_and_description(monkeypatch):
    c = cfg(monkeypatch, BRAND_NAME="Acme", BRAND_DESCRIPTION="Internal AI gateway")
    out = branding.brand_text('<title>LiteLLM Dashboard</title><meta content="LiteLLM Proxy Admin UI">', c, html=True)
    assert out == '<title>Acme Dashboard</title><meta content="Internal AI gateway">'
    c = cfg(monkeypatch, BRAND_TITLE="AI Portal")
    assert branding.brand_text("<title>LiteLLM Dashboard</title>", c) == "<title>AI Portal</title>"


def test_links(monkeypatch):
    c = cfg(
        monkeypatch,
        BRAND_DOCS_URL="https://wiki.example/ai",
        BRAND_GITHUB_URL="https://git.example/ai",
        BRAND_WEBSITE_URL="https://example.com",
    )
    src = (
        '"https://docs.litellm.ai/docs/proxy/users" '
        '"https://github.com/BerriAI/litellm/issues" '
        '"https://raw.githubusercontent.com/BerriAI/litellm/main/x.json" '
        '"https://litellm.ai" "https://api.litellm.ai/v1"'
    )
    out = branding.brand_text(src, c)
    assert '"https://wiki.example/ai"' in out
    assert '"https://git.example/ai"' in out
    assert "raw.githubusercontent.com/BerriAI/litellm/main/x.json" in out
    assert '"https://example.com"' in out
    assert "https://api.litellm.ai/v1" in out


def test_bare_object_keys_left_alone(monkeypatch):
    # Regression: minified `{...,LiteLLM:"..."}` became `Acme AI:` (a JS syntax error).
    c = cfg(monkeypatch, BRAND_NAME="Acme AI")
    src = 'let m={Bedrock:"x",LiteLLM:"y"},n={LiteLLM : 1};f("LiteLLM: ok")'
    assert branding.brand_text(src, c) == 'let m={Bedrock:"x",LiteLLM:"y"},n={LiteLLM : 1};f("Acme AI: ok")'


def test_url_rewrite_stops_at_template_expressions(monkeypatch):
    # Regression: the GitHub URL rule consumed `${r.toString()` from a template literal.
    c = cfg(monkeypatch, BRAND_GITHUB_URL="https://git.example/ai", BRAND_DOCS_URL="https://wiki.example")
    src = "`https://github.com/BerriAI/litellm/issues/new?${r.toString()}`;f(`https://docs.litellm.ai/docs/${p}`)"
    out = branding.brand_text(src, c)
    assert out == "`https://git.example/ai${r.toString()}`;f(`https://wiki.example${p}`)"


def test_html_escaping_of_name(monkeypatch):
    c = cfg(monkeypatch, BRAND_NAME="R&D <AI>")
    assert branding.brand_text("<p>LiteLLM</p>", c, html=True) == "<p>R&amp;D &lt;AI&gt;</p>"
    assert branding.brand_text('x="LiteLLM"', c) == 'x="R&D <AI>"'


# ---------- CSS ----------


def test_css_injection(monkeypatch):
    c = cfg(
        monkeypatch,
        BRAND_PRIMARY_COLOR="#0a5c8a",
        BRAND_PRIMARY_FOREGROUND="#fff",
        BRAND_PRIMARY_COLOR_DARK="#4fb3e8",
        BRAND_CSS_VARS="--sidebar=#f5f7fa; radius=0.25rem",
        BRAND_FONT_FAMILY="'Source Sans 3', sans-serif",
        BRAND_FONT_URL="https://fonts.example/css?f=1&g=2",
        BRAND_CUSTOM_CSS=".x{color:red}",
        BRAND_CUSTOM_CSS_URL="https://cdn.example/brand.css",
    )
    head = branding.build_head_injection(c)
    assert "html:root{--primary:#0a5c8a;--sidebar-primary:#0a5c8a;--ring:#0a5c8a;" in head
    assert "--primary-foreground:#fff;" in head
    assert "--sidebar:#f5f7fa;--radius:0.25rem;" in head
    assert "html.dark{--primary:#4fb3e8;" in head
    assert "--primary-foreground:#fff;" in head.split("html.dark")[1]
    assert "font-family:'Source Sans 3', sans-serif !important" in head
    assert 'href="https://fonts.example/css?f=1&amp;g=2"' in head
    assert ".x{color:red}" in head
    assert head.index("brand-overrides") < head.index("cdn.example/brand.css")


@pytest.mark.parametrize(
    "env",
    [
        {"BRAND_CUSTOM_CSS": "</style><script>alert(1)</script>"},
        {"BRAND_PRIMARY_COLOR": "red</style>"},
        {"BRAND_CSS_VARS": "bad name=1"},
        {"BRAND_CSS_VARS": "nameonly"},
    ],
)
def test_css_rejects_unsafe_values(monkeypatch, env):
    with pytest.raises(ValueError):
        cfg(monkeypatch, **env)


def test_head_injection_only_once(monkeypatch):
    c = cfg(monkeypatch, BRAND_PRIMARY_COLOR="red")
    once = branding.brand_html_document("<head></head>", c, inject_head=True)
    assert once.count("brand-overrides") == 1
    assert branding.brand_html_document(once, c, inject_head=True).count("brand-overrides") == 1


# ---------- middleware ----------


def make_app():
    big_js = 'var a="LiteLLM";' * 10

    async def ui_html(request):
        return HTMLResponse("<html><head><title>LiteLLM Dashboard</title></head><body>LiteLLM</body></html>")

    async def ui_js(request):
        return Response(big_js, media_type="application/javascript")

    async def api_js(request):
        return Response('"LiteLLM"', media_type="application/javascript")

    async def server_html(request):
        return HTMLResponse("<html><head></head><body>\U0001f685 LiteLLM login</body></html>")

    async def api_json(request):
        return JSONResponse({"name": "LiteLLM"})

    async def stream(request):
        async def gen():
            yield b"data: LiteLLM\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    app = Starlette(
        routes=[
            Route("/ui/index.html", ui_html),
            Route("/_next/static/app.js", ui_js),
            Route("/other.js", api_js),
            Route("/sso/login", server_html),
            Route("/v1/models", api_json),
            Route("/v1/stream", stream),
        ]
    )
    app.add_middleware(branding.BrandingMiddleware)
    return TestClient(app)


def test_middleware_passthrough_when_disabled():
    client = make_app()
    r = client.get("/ui/index.html")
    assert "LiteLLM Dashboard" in r.text


def test_middleware_rewrites_ui_and_injects_css(monkeypatch):
    cfg(monkeypatch, BRAND_NAME="Acme", BRAND_PRIMARY_COLOR="#123456")
    client = make_app()
    r = client.get("/ui/index.html")
    assert r.status_code == 200
    assert "<title>Acme Dashboard</title>" in r.text
    assert "<body>Acme</body>" in r.text
    assert "--primary:#123456" in r.text
    assert int(r.headers["content-length"]) == len(r.content)

    js = client.get("/_next/static/app.js")
    assert js.text == 'var a="Acme";' * 10


def test_middleware_scope(monkeypatch):
    cfg(monkeypatch, BRAND_NAME="Acme", BRAND_PRIMARY_COLOR="#123456")
    client = make_app()
    # JS outside UI paths: untouched
    assert client.get("/other.js").text == '"LiteLLM"'
    # Server-rendered HTML anywhere: name rewritten, but no UI CSS injected
    r = client.get("/sso/login")
    assert "Acme login" in r.text and "brand-overrides" not in r.text
    # API JSON and streams: untouched
    assert client.get("/v1/models").json() == {"name": "LiteLLM"}
    assert "LiteLLM" in client.get("/v1/stream").text


def test_middleware_etag_and_304(monkeypatch):
    cfg(monkeypatch, BRAND_NAME="Acme")
    client = make_app()
    r = client.get("/ui/index.html")
    etag = r.headers["etag"]
    r2 = client.get("/ui/index.html", headers={"If-None-Match": etag})
    assert r2.status_code == 304
    # A stale validator (e.g. from before branding changed) gets a full response
    r3 = client.get("/ui/index.html", headers={"If-None-Match": '"stale"'})
    assert r3.status_code == 200 and "Acme" in r3.text


def test_etag_changes_with_branding(monkeypatch):
    cfg(monkeypatch, BRAND_NAME="Acme")
    etag1 = make_app().get("/ui/index.html").headers["etag"]
    cfg(monkeypatch, BRAND_NAME="Other")
    etag2 = make_app().get("/ui/index.html").headers["etag"]
    assert etag1 != etag2


@pytest.mark.parametrize("first", ["/login", "/ui/", "/ui/asset.js"])
def test_cache_respects_html_and_ui_context(monkeypatch, first):
    cfg(monkeypatch, BRAND_NAME="Acme & Co", BRAND_CUSTOM_CSS="body{color:red}")
    content = "<html><head></head><body>LiteLLM</body></html>"

    async def page(request):
        media_type = "application/javascript" if request.url.path.endswith(".js") else "text/html"
        return Response(content, media_type=media_type)

    app = Starlette(routes=[Route("/login", page), Route("/ui/", page), Route("/ui/asset.js", page)])
    app.add_middleware(branding.BrandingMiddleware)
    with TestClient(app) as client:
        client.get(first)
        login = client.get("/login").text
        ui = client.get("/ui/").text
        js = client.get("/ui/asset.js").text
    assert "brand-overrides" not in login
    assert "brand-overrides" in ui
    assert "brand-overrides" not in js
    assert "Acme &amp; Co" in login and "Acme &amp; Co" in ui
    assert "Acme & Co" in js


@pytest.mark.parametrize("name", ['Acme "AI"', "Acme's AI", "${alert(1)}`\\\n", "</script><script>alert(1)</script>"])
def test_branding_keeps_javascript_literals_valid(monkeypatch, name):
    import json
    import subprocess

    config = cfg(monkeypatch, BRAND_NAME=name)
    source = "const a=\"LiteLLM\";const b='LiteLLM';const c=`LiteLLM`;console.log(JSON.stringify([a,b,c]));"
    rewritten = branding.brand_text(source, config, javascript=True)
    result = subprocess.run(["node", "-e", rewritten], text=True, capture_output=True, check=True)
    assert json.loads(result.stdout) == [name.strip(), name.strip(), name.strip()]
    html = branding.brand_html_document(f"<head></head><script>{source}</script>", config, inject_head=True)
    assert html.count("</script>") == 1
    script = html.split("<script>", 1)[1].split("</script>", 1)[0]
    result = subprocess.run(["node", "-e", script], text=True, capture_output=True, check=True)
    assert json.loads(result.stdout) == [name.strip(), name.strip(), name.strip()]


def test_dark_foreground_and_custom_variables(monkeypatch):
    config = cfg(monkeypatch, BRAND_PRIMARY_FOREGROUND_DARK="#eee", BRAND_CSS_VARS_DARK="card=#123")
    assert config.css_vars_dark["primary-foreground"] == "#eee"
    assert config.css_vars_dark["card"] == "#123"
    assert "--card:#123" in branding.build_head_injection(config)


def test_email_footer(monkeypatch):
    import types

    footer = types.ModuleType("litellm.integrations.email_templates.email_footer")
    footer.EMAIL_FOOTER = "<footer>stock</footer>"
    monkeypatch.setitem(sys.modules, footer.__name__, footer)
    cfg(monkeypatch, BRAND_NAME="Acme", BRAND_EMAIL_FOOTER="<footer>ours</footer>")
    subject, body = branding.brand_email("LiteLLM alert", "<p>LiteLLM</p><footer>stock</footer>")
    assert subject == "Acme alert"
    assert body == "<p>Acme</p><footer>ours</footer>"
    cfg(monkeypatch, BRAND_EMAIL_FOOTER="")
    assert branding.brand_email("subject", "x<footer>stock</footer>") == ("subject", "x")
    monkeypatch.delenv("BRAND_EMAIL_FOOTER")
    cfg(monkeypatch)
    assert branding.brand_email("subject", "x<footer>stock</footer>") == ("subject", "x<footer>stock</footer>")


def test_middleware_large_or_encoded_response_is_unchanged(monkeypatch):
    cfg(monkeypatch, BRAND_NAME="Acme")
    monkeypatch.setattr(branding, "_MAX_BODY", 4)

    async def large(request):
        return Response(b"LiteLLM", media_type="text/html")

    async def encoded(request):
        return Response(b"LiteLLM", media_type="text/html", headers={"Content-Encoding": "identity"})

    app = Starlette(routes=[Route("/ui/large", large), Route("/ui/encoded", encoded)])
    app.add_middleware(branding.BrandingMiddleware)
    with TestClient(app) as client:
        for path in ("/ui/large", "/ui/encoded"):
            assert client.get(path).content == b"LiteLLM"


def test_filtered_docs_drop_late_added_and_cached_admin_routes():
    schema = {
        "info": {"title": "Acme"},
        "paths": {"/v1/chat/completions": {"post": {}}, "/key/generate": {"post": {}}, "/policies": {"get": {}}},
    }
    result = branding.filter_openapi_paths(schema, ["/v1/chat/completions"])
    assert result["paths"] == {"/v1/chat/completions": {"post": {}}}
    assert result["info"] == {"title": "Acme"}
    result["paths"]["/policies"] = {"get": {}}
    assert "/policies" not in branding.filter_openapi_paths(result, ["/v1/chat/completions"])["paths"]


def test_custom_title_and_urls_are_not_branded_twice(monkeypatch):
    config = cfg(monkeypatch, BRAND_NAME="LiteLLM Internal", BRAND_DOCS_URL="https://wiki.example/LiteLLM")
    text = '<title>LiteLLM Dashboard</title><a href="https://docs.litellm.ai/docs">Docs</a><p>LiteLLM</p>'
    assert branding.brand_text(text, config, html=True) == (
        '<title>LiteLLM Internal Dashboard</title><a href="https://wiki.example/LiteLLM">Docs</a><p>LiteLLM Internal</p>'
    )


@pytest.mark.parametrize("first", ["/ui/notes", "/ui/asset.js"])
def test_plain_text_cache_cannot_supply_unescaped_javascript(monkeypatch, first):
    import subprocess

    cfg(monkeypatch, BRAND_NAME='Acme "AI"')

    async def response(request):
        kind = "application/javascript" if request.url.path.endswith(".js") else "text/plain"
        return Response('console.log("LiteLLM")', media_type=kind)

    app = Starlette(routes=[Route("/ui/notes", response), Route("/ui/asset.js", response)])
    app.add_middleware(branding.BrandingMiddleware)
    with TestClient(app) as client:
        client.get(first)
        plain = client.get("/ui/notes").text
        script = client.get("/ui/asset.js").text
    assert 'Acme "AI"' in plain
    result = subprocess.run(["node", "-e", script], text=True, capture_output=True, check=True)
    assert result.stdout.strip() == 'Acme "AI"'


@pytest.mark.parametrize("path,kind", [("/ui/flight", "text/x-component"), ("/ui/index.txt", "text/plain")])
def test_branded_react_flight_stays_valid_json(monkeypatch, path, kind):
    import json

    cfg(monkeypatch, BRAND_NAME='Acme "AI"')

    async def response(request):
        return Response('1c:{"title":"LiteLLM Dashboard"}', media_type=kind)

    app = Starlette(routes=[Route(path, response)])
    app.add_middleware(branding.BrandingMiddleware)
    with TestClient(app) as client:
        payload = client.get(path).text.split(":", 1)[1]
    assert json.loads(payload) == {"title": 'Acme "AI" Dashboard'}
