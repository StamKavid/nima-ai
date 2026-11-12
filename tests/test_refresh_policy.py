"""Athens calendar selection is explicit, bounded and independent of source I/O."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from nima.orchestration.refresh import Policy, business_date, select_dates


@pytest.mark.parametrize(
    ("instant", "expected"),
    [
        ("2026-03-28T22:30:00+00:00", "2026-03-29"),
        ("2026-03-29T21:30:00+00:00", "2026-03-30"),
        ("2026-10-25T21:30:00+00:00", "2026-10-25"),
        ("2026-10-25T22:30:00+00:00", "2026-10-26"),
        ("2027-01-01T00:00:00+00:00", "2027-01-01"),
    ],
)
def test_athens_business_date(instant: str, expected: str) -> None:
    assert business_date(datetime.fromisoformat(instant)) == date.fromisoformat(expected)
    with pytest.raises(ValueError):
        business_date(datetime(2026, 11, 12))


def test_clipping_overlap_and_long_gap_remain_bounded(tmp_path: Path) -> None:
    start, today = date(2000, 1, 1), date(2026, 11, 12)
    policy = Policy(start, ("21", "3"), tmp_path / "raw")
    oldest = tuple(start + timedelta(days=i) for i in range(7))
    planned = select_dates(policy, today, oldest)
    assert len(planned) == 14 and planned[:7] == oldest
    assert planned[-1] == today - timedelta(days=1)
    assert policy.buyers == ("21", "3") and not policy.root.exists()
    recent = Policy(today - timedelta(days=2), ("21",), policy.root)
    assert select_dates(recent, today, (today - timedelta(days=2),)) == (
        today - timedelta(days=2),
        today - timedelta(days=1),
    )
    assert select_dates(Policy(today, ("21",), policy.root), today, ()) == ()
    leap = Policy(date(2024, 2, 28), ("21",), policy.root)
    assert date(2024, 2, 29) in select_dates(leap, date(2024, 3, 2), ())


@pytest.mark.parametrize(
    "buyers", [(), ("0",), ("-1",), ("１",), ("1", "1"), tuple(str(i) for i in range(1, 12))]
)
def test_invalid_or_ambiguous_cohort_is_rejected(tmp_path: Path, buyers: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        Policy(date(2026, 11, 1), buyers, tmp_path / "raw")


def test_policy_rejects_unsafe_root_without_creating_it(tmp_path: Path) -> None:
    root = tmp_path / "link"
    root.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        Policy(date(2026, 11, 1), ("1",), root)
    with pytest.raises(ValueError):
        Policy(date(2026, 11, 1), ("1",), tmp_path / ".." / "raw")
    assert business_date(datetime(2026, 11, 12, tzinfo=UTC)) == date(2026, 11, 12)
