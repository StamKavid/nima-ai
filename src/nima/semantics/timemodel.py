"""Reported KIMDIS dates as typed values, from the shapes actually measured on real records.

Measured on 2026-11-20 over 1,317 records (see ``docs/semantics/date-format-measurements.md``):
the submission date is a zone-less ISO date-time whose fraction has one to three digits (owner
decision) or, on 4 records, six digits (added), the update date is date-only, and no value carries
a zone. Only those shapes are parsed.
Everything else is ``unparseable`` and counted by the caller, never guessed, and a missing value is
``absent``. The source text is always kept exactly as given.

A zone-less value is read as Europe/Athens civil time and says so in ``basis``; nothing is claimed
about the instant it denotes. A value with a zone suffix or offset is unparseable until a measured
shape justifies a rule, so no time zone data and no daylight-saving logic are needed here.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

TIME_MODEL_VERSION = "kimdis-reported-time-v1"

type Outcome = Literal["parsed", "absent", "unparseable"]
type Shape = Literal["datetime_fraction", "date_only"]
type Basis = Literal["zone_less_read_as_athens_civil"]

_DATETIME = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})\.[0-9]{1,6}"
)
_DATE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")


@dataclass(frozen=True)
class ReportedDate:
    source_text: str | None
    outcome: Outcome
    shape: Shape | None
    day: date | None
    period: str | None
    basis: Basis | None


def _absent() -> ReportedDate:
    return ReportedDate(None, "absent", None, None, None, None)


def _unparseable(text: str | None) -> ReportedDate:
    return ReportedDate(text, "unparseable", None, None, None, None)


def _parsed(text: str, shape: Shape, day: date, basis: Basis | None) -> ReportedDate:
    return ReportedDate(text, "parsed", shape, day, f"{day.year:04d}-{day.month:02d}", basis)


def parse_reported_submission(value: object) -> ReportedDate:
    """``source_submitted_at``: zone-less ``YYYY-MM-DDTHH:MM:SS.f``, 1-6 fraction digits."""
    if value is None:
        return _absent()
    if not isinstance(value, str):
        return _unparseable(None)
    match = _DATETIME.fullmatch(value)
    if match is None:
        return _unparseable(value)
    year, month, day, hour, minute, second = (int(part) for part in match.groups())
    try:
        datetime(year, month, day, hour, minute, second)
    except ValueError:
        return _unparseable(value)
    return _parsed(
        value, "datetime_fraction", date(year, month, day), "zone_less_read_as_athens_civil"
    )


def parse_reported_update(value: object) -> ReportedDate:
    """``source_updated_at``: a plain ``YYYY-MM-DD`` date; never an ordering key."""
    if value is None:
        return _absent()
    if not isinstance(value, str):
        return _unparseable(None)
    match = _DATE.fullmatch(value)
    if match is None:
        return _unparseable(value)
    year, month, day = (int(part) for part in match.groups())
    try:
        parsed = date(year, month, day)
    except ValueError:
        return _unparseable(value)
    return _parsed(value, "date_only", parsed, None)
