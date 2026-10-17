import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import smoke_image


@pytest.mark.parametrize("failure", ["capture", "write"])
def test_log_failure_still_removes_container(tmp_path, monkeypatch, failure):
    def docker(*args, **kwargs):
        if args[0] == "run":
            return SimpleNamespace(stdout="container-id\n")
        if args[0] == "port":
            raise RuntimeError("stop before HTTP checks")
        if args[0] == "logs":
            if failure == "capture":
                raise OSError("log capture failed")
            return SimpleNamespace(stdout="stdout", stderr="stderr")
        return SimpleNamespace(stdout="")

    calls = Mock(side_effect=docker)
    monkeypatch.setattr(smoke_image, "docker", calls)
    write_text = Path.write_text

    def write(path, *args, **kwargs):
        if path.suffix == ".log":
            raise OSError("log write failed")
        return write_text(path, *args, **kwargs)

    if failure == "write":
        monkeypatch.setattr(Path, "write_text", write)
    with pytest.raises(OSError, match=f"log {failure} failed"):
        smoke_image.exercise_proxy("image", "smoke", {}, tmp_path)
    assert calls.call_args_list[-1] == call(
        "rm", "--force", "container-id", capture_output=True
    )
