#!/usr/bin/env python3
"""Validate and atomically apply the generated patch to a clean upstream checkout."""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

from generate_patch import FILES, EditError, generate

HERE = Path(__file__).resolve().parent
PATCH = HERE.parent / "patches/0001-oss-customizations.patch"


def enterprise_module(name: str) -> bool:
    return any(part in {"enterprise", "litellm_enterprise"} for part in name.split("."))


def imports(source: str) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names.add(module)
            names.update(f"{module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            if isinstance(node.func, ast.Name) and node.func.id == "__import__":
                names.add(str(node.args[0].value))
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "import_module":
                names.add(str(node.args[0].value))
    return names


def validate_scope(root: Path, files: dict[str, str]) -> None:
    for rel, source in files.items():
        path = Path(rel)
        if path.is_absolute() or ".." in path.parts or path.parts[0] != "litellm":
            raise EditError(f"Patch target is outside litellm/: {rel}")
        if any(part in {"enterprise", "litellm_enterprise"} for part in path.parts):
            raise EditError(f"Patch targets enterprise code: {rel}")
        original = (root / rel).read_text() if (root / rel).exists() else ""
        added_imports = imports(source) - imports(original)
        if any(enterprise_module(name) for name in added_imports):
            raise EditError(f"Patch adds an enterprise import: {rel}")


def apply(root: Path, *, check: bool = False) -> None:
    root = root.resolve()
    expected = generate(root)
    validate_scope(root, FILES)
    if PATCH.read_text() != expected:
        raise EditError("Patch differs from its sources; regenerate it against a clean upstream checkout")
    command = ["git", "-C", str(root), "apply", "--whitespace=error"]
    subprocess.run([*command, "--check", str(PATCH)], check=True)
    if not check:
        subprocess.run([*command, str(PATCH)], check=True)
    print(f"Patch {'validated' if check else 'applied'} ({len(FILES)} Python files)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path)
    parser.add_argument("--check", action="store_true", help="Validate without changing upstream files")
    args = parser.parse_args()
    apply(args.upstream, check=args.check)


if __name__ == "__main__":
    try:
        main()
    except (EditError, FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
