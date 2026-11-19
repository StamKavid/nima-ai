"""Shared policy lock without source-intent or filesystem dependencies."""

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from nima.storage.connection import Connection
from nima.storage.workflows import WorkflowError, _db


@contextmanager
def policy_session(dsn: str, policy_id: UUID) -> Iterator[Connection]:
    key = int.from_bytes(hashlib.sha256(b"refresh" + policy_id.bytes).digest()[:8], signed=True)
    with _db(dsn) as connection:
        if connection.execute("SELECT pg_try_advisory_lock(%s)", (key,)).fetchone() != (True,):
            raise WorkflowError("policy_busy", True)
        yield connection
