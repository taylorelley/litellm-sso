"""Start and test a locally built image before it can be published."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
KEY = "sk-image-smoke-test"


def docker(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], text=True, check=True, timeout=900, **kwargs)


def request(base: str, path: str, *, data: dict | None = None, authenticated: bool = True, headers: dict | None = None):
    headers = dict(headers or {})
    if authenticated:
        headers["Authorization"] = f"Bearer {KEY}"
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        base + path, data=json.dumps(data).encode() if data is not None else None, headers=headers
    )
    try:
        response = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        return response.status, response.headers, response.read()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def exercise_proxy(image: str, name: str, env: dict[str, str], directory: Path) -> None:
    config = directory / "config.yaml"
    config.write_text("""model_list:
  - model_name: smoke
    litellm_params:
      model: openai/smoke
      api_key: sk-fake
      mock_response: "smoke response"
general_settings:
  master_key: sk-image-smoke-test
""")
    command = [
        "run",
        "--detach",
        "--publish",
        "127.0.0.1::4000",
        "--name",
        name,
        "--volume",
        f"{config}:/smoke.yaml:ro",
        "--env",
        "LITELLM_LOCAL_MODEL_COST_MAP=True",
    ]
    for key, value in env.items():
        command.extend(["--env", f"{key}={value}"])
    container = docker(
        *command, image, "--config", "/smoke.yaml", "--port", "4000", "--num_workers", "1", capture_output=True
    ).stdout.strip()
    try:
        port = docker("port", container, "4000", capture_output=True).stdout.strip()
        base = f"http://{port}"
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if (
                docker("inspect", "--format", "{{.State.Running}}", container, capture_output=True).stdout.strip()
                != "true"
            ):
                raise RuntimeError(f"{name} exited during startup")
            try:
                if request(base, "/health/readiness")[0] == 200:
                    break
            except (OSError, TimeoutError):
                pass
            time.sleep(2)
        else:
            raise RuntimeError(f"{name} did not become ready")
        require(request(base, "/health/liveliness")[0] == 200, "Liveness failed")
        require(request(base, "/v1/models", authenticated=False)[0] in (401, 403), "Authentication was bypassed")
        status, _, body = request(base, "/v1/models")
        require(status == 200 and "smoke" in body.decode(), "Authenticated model listing failed")
        status, _, body = request(
            base, "/v1/chat/completions", data={"model": "smoke", "messages": [{"role": "user", "content": "hi"}]}
        )
        require(
            status == 200 and json.loads(body)["choices"][0]["message"]["content"] == "smoke response",
            "Completion failed",
        )
        status, _, body = request(
            base,
            "/v1/chat/completions",
            data={"model": "smoke", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        require(status == 200 and b"data:" in body and b"[DONE]" in body, "Streaming completion failed")
        status, _, schema = request(base, "/openapi.json")
        require(status == 200, "OpenAPI failed")
        schema = json.loads(schema)
        info = schema["info"]
        if env.get("DOCS_FILTERED") == "True":
            require("/v1/chat/completions" in schema["paths"], "Filtered docs lost the completion route")
            require(
                "/key/generate" not in schema["paths"] and "/policies" not in schema["paths"],
                "Filtered docs still expose admin or lazy routes",
            )
        require(info["title"] == env.get("DOCS_TITLE", "LiteLLM API"), "Docs title differs")
        if "DOCS_DESCRIPTION" in env:
            require(info["description"] == env["DOCS_DESCRIPTION"], "Docs description differs")
        status, headers, html = request(base, "/ui/", headers={"Accept-Encoding": "gzip"})
        require(status == 200, "Admin UI failed")
        if headers.get("Content-Encoding") == "gzip":
            import gzip

            html = gzip.decompress(html)
        text = html.decode()
        if env.get("BRAND_NAME"):
            require("Acme" in text and "brand-overrides" in text, "Branded UI or CSS missing")
        else:
            require("LiteLLM" in text and "brand-overrides" not in text, "Default UI changed")
        asset = re.search(r'<script[^>]+src="([^"]+\.js)"', text)
        require(asset is not None, "UI JavaScript assets are missing")
        require(request(base, asset.group(1))[0] == 200, "UI asset could not be served")
        print(f"PASS {name}: startup, auth, models, completion, SSE, docs, UI, compression, assets", flush=True)
    finally:
        logs = docker("logs", container, capture_output=True)
        (directory / f"{name}.log").write_text(logs.stdout + logs.stderr)
        docker("rm", "--force", container, capture_output=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("--upstream", type=Path, default=Path("upstream"))
    parser.add_argument("--logs", type=Path, default=Path("smoke-logs"))
    args = parser.parse_args()
    args.logs.mkdir(parents=True, exist_ok=True)
    (args.logs / "tested-image-id.txt").unlink(missing_ok=True)
    image_id = docker("image", "inspect", "--format", "{{.Id}}", args.image, capture_output=True).stdout.strip()
    files = [
        line[6:]
        for line in (ROOT / "patches/0001-oss-customizations.patch").read_text().splitlines()
        if line.startswith("+++ b/")
    ]
    manifest = {rel: hashlib.sha256((args.upstream / rel).read_bytes()).hexdigest() for rel in files}
    docker(
        "run",
        "--rm",
        "--interactive",
        "--network",
        "none",
        "--entrypoint",
        "python",
        "--env",
        "LITELLM_LOCAL_MODEL_COST_MAP=True",
        "--env",
        'BRAND_NAME=Acme "AI" $`',
        "--volume",
        f"{HERE / 'check_installed.py'}:/check_installed.py:ro",
        image_id,
        "/check_installed.py",
        input=json.dumps(manifest),
    )
    docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--entrypoint",
        "python",
        "--env",
        "LITELLM_LOCAL_MODEL_COST_MAP=True",
        "--volume",
        f"{ROOT / 'tests/image/runtime_checks.py'}:/runtime_checks.py:ro",
        image_id,
        "/runtime_checks.py",
    )
    for name, env in (
        ("stock", {}),
        ("sso", {"LITELLM_OSS_UNLOCK": "sso", "SSO_FREE_USER_LIMIT": "0"}),
        (
            "all-branded",
            {
                "LITELLM_OSS_UNLOCK": "all",
                "BRAND_NAME": 'Acme "AI"',
                "BRAND_PRIMARY_COLOR": "#123456",
                "DOCS_TITLE": "Acme API",
                "DOCS_DESCRIPTION": "Internal gateway",
                "DOCS_FILTERED": "True",
            },
        ),
    ):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            try:
                exercise_proxy(image_id, f"litellm-smoke-{name}", env, directory)
            finally:
                for log in directory.glob("*.log"):
                    (args.logs / log.name).write_bytes(log.read_bytes())
    (args.logs / "tested-image-id.txt").write_text(image_id + "\n")
    print(f"All smoke checks passed for {image_id}")


if __name__ == "__main__":
    main()
