"""Run the patched docs function with lazy-route injection and cache reuse."""

import ast
import os
import sys
import types
from pathlib import Path
from typing import Final

from test_branding import branding


def test_docs_filter_survives_lazy_injection_and_cached_schema(monkeypatch):
    module_path = Path(os.environ.get("OSS_UNLOCK_MODULE", "upstream/litellm/proxy/oss_unlock.py"))
    tree = ast.parse((module_path.parent / "proxy_server.py").read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "custom_openapi")
    spec = types.ModuleType("litellm.proxy.common_utils.custom_openapi_spec")
    spec.CustomOpenAPISpec = types.SimpleNamespace(add_llm_api_request_schema_body=lambda schema: schema)
    lazy = types.ModuleType("litellm.proxy._lazy_features")

    def inject(schema, modules):
        schema["paths"]["/policies"] = {"get": {}}
        return schema

    lazy.inject_lazy_stubs = inject
    lazy.loaded_lazy_modules = lambda app: set()
    monkeypatch.setitem(sys.modules, spec.__name__, spec)
    monkeypatch.setitem(sys.modules, lazy.__name__, lazy)
    app = types.SimpleNamespace(openapi_schema=None)
    namespace = {
        "app": app,
        "Final": Final,
        "get_openapi_schema": lambda: {
            "info": {"title": "Acme"},
            "paths": {"/v1/chat/completions": {"post": {}}, "/key/generate": {"post": {}}},
        },
        "LiteLLMRoutes": types.SimpleNamespace(openai_routes=types.SimpleNamespace(value=["/v1/chat/completions"])),
        "ensure_unique_openapi_operation_ids": lambda schema: schema,
        "server_root_path": None,
        "filter_openapi_paths": branding.filter_openapi_paths,
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), "proxy_server.py", "exec"), namespace)
    result = namespace[function.name]()
    assert result["paths"] == {"/v1/chat/completions": {"post": {}}}
    assert result["info"]["title"] == "Acme"
    app.openapi_schema["paths"]["/policies"] = {"get": {}}
    assert "/policies" not in namespace[function.name]()["paths"]
