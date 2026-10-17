"""Check installed patch files, imports, and UI JavaScript inside the candidate image."""

from __future__ import annotations

import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    import litellm

    root = Path(litellm.__file__).resolve().parent.parent
    manifest = json.load(sys.stdin)
    for rel, expected in manifest.items():
        path = root / rel
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Installed patch content differs: {rel}")
        importlib.import_module(rel.removesuffix(".py").replace("/", "."))
    print(f"Verified content and imports for {len(manifest)} installed modules", flush=True)

    from litellm.proxy.branding import BrandingConfig, brand_text

    config = BrandingConfig.from_env()
    ui = root / "litellm/proxy/_experimental/out"
    if not (ui / "index.html").is_file():
        raise RuntimeError("Built UI index is missing from the image")
    checked = 0
    for path in ui.rglob("*.js"):
        original = path.read_text()
        rewritten = brand_text(original, config, javascript=True)
        if original != rewritten:
            result = subprocess.run(
                ["node", "--input-type=module", "--check"], input=rewritten, text=True, capture_output=True, timeout=30
            )
            if result.returncode:
                raise RuntimeError(f"Branded JavaScript does not parse: {path}\n{result.stderr[:2000]}")
            checked += 1
    if config.name and not checked:
        raise RuntimeError("No built JavaScript assets were exercised by branding")
    print(f"Syntax checked {checked} branded JavaScript assets", flush=True)


if __name__ == "__main__":
    main()
