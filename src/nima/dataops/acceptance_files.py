"""Private subject bytes and fixed errors; no policy, SQL or source access."""

import hashlib
import os
from pathlib import Path

from nima.evidence import EvidenceError, artifacts


class AcceptanceError(ValueError):
    """Only closed operation codes may cross an acceptance command boundary."""

    def __init__(self, reason: str) -> None:
        codes = {
            "acceptance_input",
            "acceptance_limit",
            "acceptance_evidence",
            "acceptance_database",
            "acceptance_contract",
            "acceptance_output",
            "acceptance_interrupted",
        }
        super().__init__(reason if reason in codes else "acceptance_contract")


def valid_path(value: object) -> bool:
    return (
        isinstance(value, Path)
        and value.is_absolute()
        and "\x00" not in str(value)
        and not str(value).startswith("//")
        and not {"..", ".git"}.intersection(value.parts)
    )


def read_subject(path: Path, *, limit: int) -> bytes:
    """Stable owned single-link bytes, hash-bound to the basename; callers check format."""
    if type(limit) is not int or not 1 <= limit <= 8 * 1024 * 1024:
        raise AcceptanceError("acceptance_limit")
    if not valid_path(path):
        raise AcceptanceError("acceptance_input")
    fd = -1
    try:
        fd = artifacts.directory(path.parent, private=True)
        info = os.stat(path.name, dir_fd=fd, follow_symlinks=False)
        if info.st_size > limit:
            raise AcceptanceError("acceptance_limit")
        if info.st_nlink != 1:
            raise AcceptanceError("acceptance_evidence")
        body = artifacts.read(fd, path.name, limit=limit, private=True)
        if (
            os.stat(path.name, dir_fd=fd, follow_symlinks=False).st_nlink != 1
            or hashlib.sha256(body).hexdigest() != path.stem
        ):
            raise AcceptanceError("acceptance_evidence")
        return body
    except (EvidenceError, OSError):
        raise AcceptanceError("acceptance_evidence") from None
    finally:
        if fd >= 0:
            os.close(fd)
