"""The reported-date parser accepts only the shapes measured on real KIMDIS records.

Measured on 2026-11-20 (1,317 records): the submission date is a zone-less ISO date-time with a
fraction of one to six digits (one to three digits chosen by the owner, six seen on 4 records and
added), the update date is date-only, and no value carries a zone. Anything else is `unparseable`,
counted and never guessed; a missing value is `absent`. The source text is always kept as given.
"""

from collections.abc import Callable
from datetime import date
from typing import Final

import pytest

from nima.semantics.timemodel import (
    TIME_MODEL_VERSION,
    ReportedDate,
    parse_reported_submission,
    parse_reported_update,
)

ATHENS_ASSUMED: Final = "zone_less_read_as_athens_civil"
Parse = Callable[[object], ReportedDate]


@pytest.mark.parametrize("fraction", ["1", "12", "123", "1234", "12345", "123456"])
def test_the_measured_submission_shape_is_parsed_with_a_fraction_of_one_to_six_digits(
    fraction: str,
) -> None:
    text = f"2026-03-10T08:15:30.{fraction}"
    assert parse_reported_submission(text) == ReportedDate(
        source_text=text,
        outcome="parsed",
        shape="datetime_fraction",
        day=date(2026, 3, 10),
        period="2026-03",
        basis=ATHENS_ASSUMED,
    )


def test_the_measured_update_shape_is_a_plain_date() -> None:
    assert parse_reported_update("2026-03-11") == ReportedDate(
        source_text="2026-03-11",
        outcome="parsed",
        shape="date_only",
        day=date(2026, 3, 11),
        period="2026-03",
        basis=None,
    )


@pytest.mark.parametrize("parse", [parse_reported_submission, parse_reported_update])
def test_a_missing_value_is_absent_not_unparseable(parse: Parse) -> None:
    assert parse(None) == ReportedDate(None, "absent", None, None, None, None)


@pytest.mark.parametrize(
    "text",
    [
        "",
        " 2026-03-10T08:15:30.123",
        "2026-03-10T08:15:30.123 ",
        "2026-03-10T08:15:30.123\n",
        "2026-03-10T08:15:30",
        "2026-03-10T08:15:30.",
        "2026-03-10T08:15:30.1234567",
        "2026-03-10 08:15:30.123",
        "2026-03-10t08:15:30.123",
        "2026-03-10T08:15:30.123Z",
        "2026-03-10T08:15:30.123+02:00",
        "2026-03-10T08:15",
        "2026-03-10",
        "10/03/2026",
        "10-03-2026T08:15:30.123",
        "2026-3-10T08:15:30.123",
        "2026-13-01T00:00:00.000",
        "2026-00-10T00:00:00.000",
        "2026-02-30T00:00:00.000",
        "2026-02-29T00:00:00.000",
        "2026-03-10T24:00:00.000",
        "2026-03-10T23:60:00.000",
        "2026-03-10T23:59:60.000",
        "2026-03-10T08:15:30.١٢٣",
        "２０２６-03-10T08:15:30.123",
        "0000-03-10T08:15:30.123",
        "not a date",
    ],
)
def test_any_other_submission_text_is_unparseable_and_kept_verbatim(text: str) -> None:
    assert parse_reported_submission(text) == ReportedDate(
        text, "unparseable", None, None, None, None
    )


@pytest.mark.parametrize(
    "text",
    [
        "",
        " 2026-03-11",
        "2026-03-11 ",
        "2026-03-11\n",
        "2026-03-11T08:15:30.123",
        "11/03/2026",
        "2026-3-11",
        "2026-02-30",
        "2026-13-11",
        "٢٠٢٦-03-11",
    ],
)
def test_any_other_update_text_is_unparseable_and_kept_verbatim(text: str) -> None:
    assert parse_reported_update(text) == ReportedDate(text, "unparseable", None, None, None, None)


@pytest.mark.parametrize("value", [1, 1.5, True, b"2026-03-10", ["2026-03-10"], {"a": 1}])
@pytest.mark.parametrize("parse", [parse_reported_submission, parse_reported_update])
def test_a_value_that_is_not_text_is_unparseable(parse: Parse, value: object) -> None:
    result = parse(value)
    assert (result.outcome, result.day, result.period) == ("unparseable", None, None)
    assert result.source_text is None


def test_the_submission_text_is_not_accepted_as_an_update_date_and_vice_versa() -> None:
    assert parse_reported_update("2026-03-10T08:15:30.123").outcome == "unparseable"
    assert parse_reported_submission("2026-03-10").outcome == "unparseable"


@pytest.mark.parametrize(
    ("text", "period"),
    [
        ("2026-03-31T23:59:59.999", "2026-03"),
        ("2026-04-01T00:00:00.000", "2026-04"),
        ("2025-12-31T23:59:59.999", "2025-12"),
        ("2026-01-01T00:00:00.000", "2026-01"),
        ("2024-02-29T12:00:00.000", "2024-02"),
        ("2026-10-25T03:30:00.000", "2026-10"),
        ("2026-03-29T03:30:00.000", "2026-03"),
    ],
)
def test_the_period_is_the_calendar_month_of_the_reported_civil_date_with_no_conversion(
    text: str, period: str
) -> None:
    result = parse_reported_submission(text)
    assert (result.outcome, result.period) == ("parsed", period)
    assert result.day is not None and f"{result.day:%Y-%m}" == period


def test_the_original_fraction_digits_stay_in_the_source_text() -> None:
    assert parse_reported_submission("2026-03-10T08:15:30.50").source_text == (
        "2026-03-10T08:15:30.50"
    )


def test_the_same_text_always_gives_the_same_result() -> None:
    text = "2026-03-10T08:15:30.123"
    assert parse_reported_submission(text) == parse_reported_submission(text)


def test_the_model_version_is_named() -> None:
    assert TIME_MODEL_VERSION == "kimdis-reported-time-v1"
