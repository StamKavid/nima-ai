"""Only explicit local Prefect configuration is supported by the initial deployment."""

from pathlib import Path

import pytest

from nima.orchestration.config import local_config
from nima.storage.workflows import WorkflowError


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://api.prefect.cloud/api",
        "http://example.com/api",
        "http://user:secret@localhost:4200/api",
        "http://localhost:4200/api?key=x",
    ],
)
def test_nonlocal_or_missing_server_is_rejected(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("PREFECT_API_URL", url)
    with pytest.raises(WorkflowError, match="configuration"):
        local_config()


def test_explicit_configuration_disables_ephemeral_and_analytics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PREFECT_API_URL", "http://127.0.0.1:4200/api")
    monkeypatch.setenv("NIMA_DATABASE_URL", "synthetic-placeholder")
    monkeypatch.setenv("NIMA_ARCHIVE_ROOT", str(tmp_path / "raw"))
    monkeypatch.setenv("PREFECT_HOME", str(tmp_path / "control"))
    monkeypatch.delenv("PREFECT_API_KEY", raising=False)
    config = local_config()
    assert config.api_url == "http://127.0.0.1:4200/api"
    assert not config.archive_root.exists()
    import os

    assert os.environ["PREFECT_SERVER_EPHEMERAL_ENABLED"] == "false"
    assert os.environ["PREFECT_SERVER_ANALYTICS_ENABLED"] == "false"
    broken = tmp_path / "file"
    broken.write_text("not a directory")
    monkeypatch.setenv("PREFECT_HOME", str(broken))
    with pytest.raises(WorkflowError, match="configuration"):
        local_config()
