"""Read two stored captures, decide comparability from counters, verify and publish the change."""

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from psycopg.types.json import Jsonb

from nima.analytics.change_request import ChangeRequest, read_change_request
from nima.analytics.metric_readout import (
    cohort_hash,
    definition_hash,
    encode_artifact,
    require_parity,
)
from nima.analytics.reconcile import ReconciliationError, VerifiedPage, verify_pages
from nima.analytics.request import RequestError
from nima.analytics.result import ReadoutError
from nima.analytics.run_facts import read_run_facts
from nima.analytics.snapshot import Cohort, SnapshotError, connected, read_cohort_in
from nima.graph.pilot_archive import PilotArchiveError
from nima.identity import AssessmentError
from nima.identity.artifacts import publish
from nima.semantics.observed_change import (
    Capture,
    CapturedVersion,
    MetricResult,
    RunFacts,
    definition,
    evaluate,
    reference_sql,
    sql_rows,
)
from nima.semantics.participation import SemanticError
from nima.storage.connection import Connection


@dataclass(frozen=True)
class ChangeExport:
    artifact_sha256: str
    outcome: str
    added: int
    changed: int
    missing_from_later_capture: int
    unchanged: int


@dataclass(frozen=True)
class _Read:
    earlier: tuple[RunFacts, ...]
    later: tuple[RunFacts, ...]
    cohort: Cohort | None


def _read(connection: Connection, request: ChangeRequest) -> _Read:
    """Counters, and the frozen cohort only if the captures can be compared, on one snapshot."""
    facts = read_run_facts(connection, request.run_ids)
    earlier = tuple(facts[run] for run in request.earlier_run_ids)
    later = tuple(facts[run] for run in request.later_run_ids)
    if evaluate(Capture(earlier, ()), Capture(later, ())).reasons:
        return _Read(earlier, later, None)
    return _Read(earlier, later, read_cohort_in(connection, request.run_ids))


def _captures(
    request: ChangeRequest, read: _Read
) -> tuple[Capture, Capture, dict[int, dict[str, object]]]:
    if read.cohort is None:
        return Capture(read.earlier, ()), Capture(read.later, ()), {}
    pages = {
        (cast(str, page["run_id"]), cast(int, page["page_number"])): page
        for page in cast(list[dict[str, object]], read.cohort.document["pages"])
    }
    earlier_runs = {str(run) for run in request.earlier_run_ids}
    cited: dict[int, dict[str, object]] = {}
    versions: dict[str, list[CapturedVersion]] = {"earlier": [], "later": []}
    for record in cast(list[dict[str, object]], read.cohort.document["records"]):
        label = "earlier" if record["run_id"] in earlier_runs else "later"
        page = pages[cast(str, record["run_id"]), cast(int, record["page_number"])]
        observation_id = cast(int, record["observation_id"])
        versions[label].append(
            CapturedVersion(
                observation_id,
                cast(str, record["source_id"]),
                cast(str, record["content_sha256"]),
                datetime.fromisoformat(cast(str, page["observed_at"])),
            )
        )
        cited[observation_id] = {
            "observation_id": observation_id,
            "capture": label,
            "source_id": record["source_id"],
            "content_sha256": record["content_sha256"],
            "run_id": record["run_id"],
            "page_number": record["page_number"],
            "json_pointer": f"/content/{record['record_index']}",
            "observed_at": page["observed_at"],
        }
    return (
        Capture(read.earlier, tuple(versions["earlier"])),
        Capture(read.later, tuple(versions["later"])),
        cited,
    )


def _body(
    request: ChangeRequest,
    read: _Read,
    result: MetricResult,
    cited: dict[int, dict[str, object]],
    pages: tuple[VerifiedPage, ...],
) -> bytes:
    policy = definition()
    return encode_artifact(
        {
            "version": "nima-observed-change-v1",
            "source": "kimdis.contract",
            "metric": {
                "definition": policy,
                "definition_sha256": definition_hash(policy),
                "result": result.payload(),
            },
            "request": request.semantic_payload(),
            "request_sha256": request.request_sha256,
            "cohort_sha256": None if read.cohort is None else cohort_hash(read.cohort.document),
            "run_facts": {
                "earlier": [_fact(fact) for fact in read.earlier],
                "later": [_fact(fact) for fact in read.later],
            },
            "quality": {
                "completeness": "decided_from_stored_counters",
                "raw_bytes": "not_performed_incomparable"
                if read.cohort is None
                else "verified_against_archived_bytes",
                "source_current": "not_established",
                "lineage": "record_to_original_not_field_level",
            },
            "interpretation_limits": [
                "Compares what two captures contained, not what the publisher changed or deleted.",
                "A changed record has different content, for an unknown field and reason.",
                "A record missing from the later capture is not a deletion or a legal event.",
                "An incomparable result states why the captures could not be compared.",
            ],
            "verified_pages": [{**asdict(page), "run_id": str(page.run_id)} for page in pages],
            "evidence": [cited[key] for key in sorted(cited)],
        }
    )


def _fact(fact: RunFacts) -> dict[str, object]:
    return {
        **asdict(fact),
        "observed_from": fact.observed_from.isoformat(),
        "observed_to": fact.observed_to.isoformat(),
    }


def prepare_change_readout(dsn: str, request: ChangeRequest) -> tuple[bytes, MetricResult]:
    """Reconstruct and validate without publishing or writing SQL/source evidence."""
    try:
        read = connected(dsn, lambda connection: _read(connection, request))
        earlier, later, cited = _captures(request, read)
        pages: tuple[VerifiedPage, ...] = ()
        if read.cohort is not None:
            pages, _ = verify_pages(read.cohort.document, request.archive_bindings)
        result = evaluate(earlier, later)
        runs, versions = sql_rows(earlier, later)
        require_parity(dsn, reference_sql(), (Jsonb(runs), Jsonb(versions)), result.payload())
        return _body(request, read, result, cited, pages), result
    except ReadoutError:
        raise
    except (SnapshotError, ReconciliationError, RequestError) as error:
        raise ReadoutError(error.reason) from None
    except PilotArchiveError:
        raise ReadoutError("analytics_archive") from None
    except SemanticError:
        raise ReadoutError("analytics_input") from None
    except (KeyError, TypeError, ValueError, IndexError):
        raise ReadoutError("analytics_evidence") from None
    except OSError:
        raise ReadoutError("analytics_output") from None


def export_change_readout(dsn: str, request_file: Path, output_directory: Path) -> ChangeExport:
    """No network, SQL writes or original repair; validate fully before publication."""
    try:
        request = read_change_request(request_file)
        body, result = prepare_change_readout(dsn, request)
        digest = publish(output_directory, body)
        counts = result.counts
        return ChangeExport(
            digest,
            result.status,
            counts.added,
            counts.changed,
            counts.missing_from_later_capture,
            counts.unchanged,
        )
    except RequestError as error:
        raise ReadoutError(error.reason) from None
    except AssessmentError as error:
        raise ReadoutError(
            "analytics_limit" if error.reason == "assessment_limit" else "analytics_output"
        ) from None
    except OSError:
        raise ReadoutError("analytics_output") from None
