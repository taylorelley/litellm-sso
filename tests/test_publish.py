import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import publish_image


@pytest.mark.parametrize("receipt", [None, "sha256:" + "b" * 64])
def test_failed_or_wrong_smoke_cannot_publish(tmp_path, monkeypatch, receipt):
    calls = Mock()
    monkeypatch.setattr(publish_image.subprocess, "run", calls)
    path = tmp_path / "receipt"
    if receipt:
        path.write_text(receipt)
    with pytest.raises((FileNotFoundError, ValueError)):
        publish_image.publish("sha256:" + "a" * 64, "ghcr.io/example/image:test", path)
    calls.assert_not_called()


def test_publishes_tested_id_without_rebuilding(tmp_path, monkeypatch):
    calls = Mock()
    monkeypatch.setattr(publish_image.subprocess, "run", calls)
    image = "sha256:" + "a" * 64
    path = tmp_path / "receipt"
    path.write_text(image)
    publish_image.publish(image, "ghcr.io/example/image:test", path)
    assert [call.args[0] for call in calls.call_args_list] == [
        ["docker", "tag", image, "ghcr.io/example/image:test"],
        ["docker", "push", "ghcr.io/example/image:test"],
    ]
