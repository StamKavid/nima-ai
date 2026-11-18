"""Bounded SQL and no-follow filesystem measurements without source or state writes.

https://www.postgresql.org/docs/17/sql-set-transaction.html
https://www.psycopg.org/psycopg3/docs/api/rows.html#psycopg.rows.class_row
https://docs.python.org/3.12/library/os.html#os.fstatvfs
"""

import os
from dataclasses import replace
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import cast
from uuid import UUID

import psycopg
from psycopg.rows import class_row

from nima.dataops.health import (
    CapacitySample,
    CaptureSample,
    HealthError,
    HealthResult,
    build_report,
    validate_thresholds,
)
from nima.evidence import EvidenceError
from nima.evidence.artifacts import directory
from nima.identity import AssessmentError
from nima.projections.worker import PROJECTION_VERSION
from nima.storage.connection import connect
from nima.storage.postgres import MigrationError, validate_schema


def validate_path(path: Path) -> None:
    if (
        not isinstance(path, Path)
        or not path.is_absolute()
        or any(p in {"..", ".git"} for p in path.parts)
        or "\x00" in str(path)
    ):
        raise HealthError("health_configuration")


def read_snapshot(dsn: str, run_id: UUID) -> CaptureSample:
    if not isinstance(run_id, UUID) or not isinstance(dsn, str) or not dsn.strip():
        raise HealthError("health_configuration")
    try:
        query = files("nima.dataops").joinpath("health.sql").read_text(encoding="utf-8")
        with connect(dsn) as c, c.transaction():
            c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            c.execute("SET LOCAL TIME ZONE 'UTC'")
            c.execute("SET LOCAL statement_timeout = 5000")
            c.execute("SET LOCAL lock_timeout = 2000")
            validate_schema(c)
            with c.cursor(row_factory=class_row(CaptureSample)) as cursor:
                row = cursor.execute(
                    query, {"run_id": run_id, "projection_version": PROJECTION_VERSION}
                ).fetchone()
            if row is None:
                raise HealthError("health_unavailable")
            clock = c.execute("SELECT clock_timestamp()").fetchone()
            if clock is None:
                raise HealthError("health_database")
            return replace(row, sampled_at=cast(datetime, clock[0]))
    except MigrationError:
        raise HealthError("health_schema") from None
    except psycopg.Error:
        raise HealthError("health_database") from None
    except OSError:
        raise HealthError("health_resource") from None


def sample_capacity(path: Path) -> CapacitySample:
    validate_path(path)
    try:
        fd = directory(path, private=True)
        try:
            stat = os.fstatvfs(fd)
            if (
                stat.f_frsize <= 0
                or stat.f_bavail < 0
                or stat.f_files < 0
                or (stat.f_files and stat.f_favail < 0)
            ):
                raise HealthError("health_capacity")
            return CapacitySample(
                str(path),
                datetime.now(UTC),
                stat.f_bavail * stat.f_frsize,
                None if stat.f_files == 0 else stat.f_favail,
            )
        finally:
            os.close(fd)
    except (EvidenceError, OSError):
        raise HealthError("health_capacity") from None


def prepare_health(
    dsn: str,
    run_id: UUID,
    capacity_dir: Path,
    *,
    max_age_hours: int,
    min_free_bytes: int,
) -> HealthResult:
    validate_thresholds(max_age_hours, min_free_bytes)
    validate_path(capacity_dir)
    captured = read_snapshot(dsn, run_id)
    capacity = sample_capacity(capacity_dir)
    try:
        return build_report(
            captured, capacity, max_age_hours=max_age_hours, min_free_bytes=min_free_bytes
        )
    except AssessmentError:
        raise HealthError("health_limit") from None
