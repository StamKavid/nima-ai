"""Immutable refresh intent; session locks serialize planning, dispatch and pause."""

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4, uuid5

from psycopg.types.json import Jsonb

from nima.ingestion.config import CONNECTOR_VERSION, Query
from nima.orchestration.refresh import CRON, TIMEZONE, VERSION, Policy, select_dates
from nima.storage.postgres import NORMALIZER_VERSION, Connection
from nima.storage.workflows import RequestStore, WorkflowError, _db


def _parameters(policy: Policy) -> dict[str, object]:
    return {
        "version": VERSION,
        "start_date": policy.start.isoformat(),
        "buyers": list(policy.buyers),
        "archive_root": str(policy.root),
        "connector_version": CONNECTOR_VERSION,
        "normalizer_version": NORMALIZER_VERSION,
        "cron": CRON,
        "timezone": TIMEZONE,
        "overlap": 7,
        "lag": 1,
        "child_cap": 14,
    }


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


# Gaps use known successful days, not a series expanding every date of an outage.
GAPS = """WITH done AS (
    SELECT DISTINCT query_date d FROM nima.refresh_windows
    WHERE policy_id=%s AND completed_at IS NOT NULL AND query_date BETWEEN %s AND %s
), boundaries AS (SELECT %s::date-1 d UNION SELECT d FROM done),
gaps AS (SELECT d+1 first, coalesce(lead(d) OVER (ORDER BY d),%s::date+1)-1 last
    FROM boundaries)
"""


def missing_dates(
    connection: Connection, policy_id: UUID, start: date, end: date
) -> tuple[date, ...]:
    if end < start:
        return ()
    rows = connection.execute(
        GAPS + "SELECT first+n FROM gaps CROSS JOIN generate_series(0,6) n "
        "WHERE first+n<=last ORDER BY 1 LIMIT 7",
        (policy_id, start, end, start, end),
    ).fetchall()
    return tuple(cast(date, row[0]) for row in rows)


@dataclass(frozen=True)
class Cycle:
    cycle_id: UUID
    day: date
    dates: tuple[date, ...]


@dataclass(frozen=True)
class Child:
    day: date
    request: UUID
    state: str
    complete: bool


class RefreshStore:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def create(self, policy_id: UUID, policy: Policy) -> None:
        value = _parameters(policy)
        with _db(self.dsn) as connection, connection.transaction():
            inserted = connection.execute(
                "INSERT INTO nima.refresh_policies "
                "(policy_id,configuration,configuration_sha256,start_date) VALUES (%s,%s,%s,%s) "
                "ON CONFLICT DO NOTHING RETURNING 1",
                (policy_id, Jsonb(value), _digest(value), policy.start),
            ).fetchone()
            row = connection.execute(
                "SELECT configuration,configuration_sha256 FROM nima.refresh_policies "
                "WHERE policy_id=%s",
                (policy_id,),
            ).fetchone()
            if row != (value, _digest(value)):
                raise WorkflowError("policy_conflict")
            if inserted:
                connection.execute(
                    "INSERT INTO nima.refresh_events(policy_id,state) VALUES (%s,'paused')",
                    (policy_id,),
                )

    def options(self, policy_id: UUID) -> Policy:
        with _db(self.dsn) as connection:
            row = connection.execute(
                "SELECT configuration,configuration_sha256 FROM nima.refresh_policies "
                "WHERE policy_id=%s",
                (policy_id,),
            ).fetchone()
        if row is None:
            raise WorkflowError("policy_unavailable")
        value = cast(dict[str, object], row[0])
        try:
            policy = Policy(
                date.fromisoformat(cast(str, value["start_date"])),
                tuple(cast(list[str], value["buyers"])),
                Path(cast(str, value["archive_root"])),
            )
            if value != _parameters(policy) or row[1] != _digest(value):
                raise ValueError
            return policy
        except (ValueError, TypeError, KeyError, OSError):
            raise WorkflowError("policy_invalid") from None

    def plan(self, policy_id: UUID, day: date) -> dict[str, object]:
        policy = self.options(policy_id)
        with _db(self.dsn) as connection:
            missing = missing_dates(
                connection, policy_id, policy.start, date.fromordinal(day.toordinal() - 1)
            )
        return {
            "policy_id": str(policy_id),
            "business_date": day.isoformat(),
            "query_dates": [d.isoformat() for d in select_dates(policy, day, missing)],
        }

    @contextmanager
    def lease(self, policy_id: UUID) -> Iterator["RefreshSession"]:
        policy = self.options(policy_id)
        key = int.from_bytes(hashlib.sha256(b"refresh" + policy_id.bytes).digest()[:8], signed=True)
        with _db(self.dsn) as connection:
            if connection.execute("SELECT pg_try_advisory_lock(%s)", (key,)).fetchone() != (True,):
                raise WorkflowError("policy_busy", True)
            yield RefreshSession(self, connection, policy_id, policy)


class RefreshSession:
    def __init__(
        self, store: RefreshStore, connection: Connection, policy_id: UUID, policy: Policy
    ):
        self.store, self.connection, self.policy_id, self.policy = (
            store,
            connection,
            policy_id,
            policy,
        )

    def state(self, state: str) -> None:
        if state not in {"paused", "pending", "enabled"}:
            raise ValueError("policy_state")
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE nima.refresh_policies SET state=%s WHERE policy_id=%s",
                (state, self.policy_id),
            )
            self.connection.execute(
                "INSERT INTO nima.refresh_events(policy_id,state) VALUES (%s,%s)",
                (self.policy_id, state),
            )

    def enabled(self) -> bool:
        return self.connection.execute(
            "SELECT state FROM nima.refresh_policies WHERE policy_id=%s", (self.policy_id,)
        ).fetchone() == ("enabled",)

    def cycle(self, day: date) -> Cycle | None:
        if not self.enabled():
            raise WorkflowError("policy_paused")
        self.connection.execute(
            "UPDATE nima.refresh_policies SET last_tick_at=clock_timestamp() WHERE policy_id=%s",
            (self.policy_id,),
        )
        row = self.connection.execute(
            "SELECT cycle_id,business_date,query_dates FROM nima.refresh_cycles "
            "WHERE policy_id=%s AND (business_date=%s OR completed_at IS NULL) "
            "ORDER BY business_date LIMIT 1",
            (self.policy_id, day),
        ).fetchone()
        if row:
            if row[1] != day:
                raise WorkflowError("cycle_unresolved")
            return Cycle(cast(UUID, row[0]), day, tuple(cast(list[date], row[2])))
        dates = select_dates(
            self.policy,
            day,
            missing_dates(
                self.connection,
                self.policy_id,
                self.policy.start,
                date.fromordinal(day.toordinal() - 1),
            ),
        )
        if not dates:
            return None
        cycle = Cycle(uuid4(), day, dates)
        self.connection.execute(
            "INSERT INTO nima.refresh_cycles(cycle_id,policy_id,business_date,query_dates) "
            "VALUES (%s,%s,%s,%s)",
            (cycle.cycle_id, self.policy_id, day, list(dates)),
        )
        return cycle

    def children(self, cycle: Cycle) -> tuple[Child, ...]:
        for day in cycle.dates:
            request = uuid5(cycle.cycle_id, day.isoformat())
            RequestStore(self.store.dsn).submit(
                request, Query(day, day, self.policy.buyers), self.policy.root
            )
            self.connection.execute(
                "INSERT INTO nima.refresh_windows(cycle_id,policy_id,query_date,request_id) "
                "VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (cycle.cycle_id, self.policy_id, day, request),
            )
        rows = self.connection.execute(
            "SELECT query_date,request_id,dispatch_state,completed_at IS NOT NULL "
            "FROM nima.refresh_windows WHERE cycle_id=%s ORDER BY query_date",
            (cycle.cycle_id,),
        ).fetchall()
        return tuple(Child(*cast(tuple[date, UUID, str, bool], row)) for row in rows)

    def dispatch_state(self, request: UUID, state: str) -> None:
        if state not in {"sending", "accepted"}:
            raise ValueError("dispatch_state")
        self.connection.execute(
            "UPDATE nima.refresh_windows SET dispatch_state=%s "
            "WHERE policy_id=%s AND request_id=%s",
            (state, self.policy_id, request),
        )
