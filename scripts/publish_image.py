"""Publish only the exact local image that completed the smoke checks."""

import argparse
import re
import subprocess
from pathlib import Path


def publish(image_id: str, tags: str, receipt: Path) -> None:
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id):
        raise ValueError("A full candidate image ID is required")
    if receipt.read_text().strip() != image_id:
        raise ValueError("Smoke-test receipt does not match the candidate image")
    names = tags.split(",")
    if not names or any(
        not re.fullmatch(r"ghcr\.io/[a-z0-9._/-]+:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", t) for t in names
    ):
        raise ValueError("Invalid publish tags")
    for tag in names:
        subprocess.run(["docker", "tag", image_id, tag], check=True, timeout=60)
        subprocess.run(["docker", "push", tag], check=True, timeout=600)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--tags", required=True)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    publish(args.image_id, args.tags, args.receipt)
