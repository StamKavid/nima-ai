"""Pure, versioned policy and bounded query-date selection; not a change-feed cursor."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

VERSION = "kimdis-refresh-v1"
TIMEZONE = "Europe/Athens"
CRON = "0 4 * * *"


@dataclass(frozen=True)
class Policy:
    start: date
    buyers: tuple[str, ...]
    root: Path

    def __post_init__(self) -> None:
        if (
            not 1 <= len(self.buyers) <= 10
            or len(set(self.buyers)) != len(self.buyers)
            or any(not b.isascii() or not b.isdecimal() or int(b) <= 0 for b in self.buyers)
        ):
            raise ValueError("policy_invalid")
        root = self.root.absolute()
        if (
            ".." in root.parts
            or len(str(root)) > 4096
            or root.is_file()
            or any(p.is_symlink() for p in (root, *root.parents))
        ):
            raise ValueError("archive_invalid")
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "buyers", tuple(sorted(self.buyers)))


def business_date(instant: datetime) -> date:
    if instant.utcoffset() is None:
        raise ValueError("timezone_required")
    return instant.astimezone(ZoneInfo(TIMEZONE)).date()


def select_dates(policy: Policy, day: date, missing: tuple[date, ...]) -> tuple[date, ...]:
    if len(missing) > 7:
        raise ValueError("backlog_limit")
    recent = {day - timedelta(days=n) for n in range(1, 8) if day.toordinal() > n}
    return tuple(sorted(d for d in recent.union(missing) if policy.start <= d < day))
