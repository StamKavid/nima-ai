"""Explicit self-hosted configuration; no implicit ephemeral server or cloud fallback."""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from nima.storage.workflows import WorkflowError


@dataclass(frozen=True)
class LocalConfig:
    api_url: str
    dsn: str
    archive_root: Path


def local_config() -> LocalConfig:
    url = os.environ.get("PREFECT_API_URL", "")
    try:
        parts = urlsplit(url)
        if (
            parts.scheme != "http"
            or parts.hostname not in {"localhost", "127.0.0.1", "::1", "prefect-server"}
            or parts.username is not None
            or parts.password is not None
            or parts.path.rstrip("/") != "/api"
            or parts.query
            or parts.fragment
            or not 1 <= (parts.port or 80) <= 65535
            or os.environ.get("PREFECT_API_KEY")
        ):
            raise ValueError
        dsn, root = os.environ.get("NIMA_DATABASE_URL", ""), os.environ.get("NIMA_ARCHIVE_ROOT", "")
        if not dsn.strip() or not root.strip():
            raise ValueError
    except ValueError:
        raise WorkflowError("configuration") from None
    os.environ["PREFECT_SERVER_EPHEMERAL_ENABLED"] = "false"
    os.environ["PREFECT_SERVER_ALLOW_EPHEMERAL_MODE"] = "false"
    os.environ["PREFECT_SERVER_ANALYTICS_ENABLED"] = "false"
    home = Path(os.environ.get("PREFECT_HOME", str(Path(root).absolute().parent / ".nima-prefect")))
    if any(p.is_symlink() for p in (home, *home.parents)):
        raise WorkflowError("configuration")
    try:
        home.mkdir(mode=0o700, parents=True, exist_ok=True)
        home.chmod(0o700)
    except OSError:
        raise WorkflowError("configuration") from None
    os.environ["PREFECT_HOME"] = str(home)
    return LocalConfig(url.rstrip("/"), dsn, Path(root))
