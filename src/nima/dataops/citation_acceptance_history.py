"""Record one actual citation assessment; completed IDs are historical reads."""

import json
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from nima.analytics.citation_request import read_citation_request
from nima.analytics.request import RequestError
from nima.contracts import acceptance as policy
from nima.contracts.acceptance_history import (
    POLICY_SHA256,
    HistoryError,
    Intent,
    Outcome,
    assessed_outcome,
    digest,
)
from nima.contracts.history import valid_digest
from nima.dataops.acceptance_files import AcceptanceError, valid_path
from nima.dataops.citation_acceptance import (
    PreparedCitationAcceptance,
    prepare_citation_acceptance,
)
from nima.storage.acceptance_history import Journal


def current_intent(request_sha256: str, subject_sha256: str) -> Intent:
    """Only new attempts consult today's profile; recorded identities never do."""
    metadata = policy.definition()
    if (
        digest(metadata) != POLICY_SHA256
        or metadata.get("id") != "nima.dataset-acceptance"
        or metadata.get("version") != "1.0.0"
    ):
        raise HistoryError("acceptance_history_policy")
    return Intent(request_sha256, subject_sha256)


def record_citation_acceptance(
    source_dsn: str, journal_dsn: str, attempt: UUID, request_file: Path, report: Path
) -> dict[str, object]:
    if (
        not isinstance(source_dsn, str)
        or not source_dsn.strip()
        or not valid_path(request_file)
        or not valid_path(report)
        or report.suffix != ".json"
        or not valid_digest(report.stem)
    ):
        raise HistoryError("acceptance_history_configuration")
    try:
        request = read_citation_request(request_file)
    except RequestError:
        raise HistoryError("acceptance_history_configuration") from None
    try:
        with Journal(journal_dsn, attempt).session() as journal:
            stored = journal.lookup()
            if stored is None:
                stored = journal.register(current_intent(request.request_sha256, report.stem))
            elif (
                stored.intent.request_sha256 != request.request_sha256
                or stored.intent.subject_sha256 != report.stem
            ):
                raise HistoryError("acceptance_history_conflict")
            if stored.outcome is not None:
                return stored.payload()
            intent = stored.intent
            body = None
            if not intent.supported:
                outcome = Outcome(intent.digest, "refused", None, None, "acceptance_contract")
            else:
                try:
                    prepared = prepare_citation_acceptance(source_dsn, request, report)
                except AcceptanceError as error:
                    if str(error) == "acceptance_interrupted":
                        raise KeyboardInterrupt from None
                    outcome = Outcome(intent.digest, "refused", None, None, str(error))
                else:
                    if (
                        not isinstance(prepared, PreparedCitationAcceptance)
                        or prepared.subject_sha256 != intent.subject_sha256
                    ):
                        raise HistoryError("acceptance_history_integrity")
                    outcome = assessed_outcome(intent, prepared.body)
                    if digest(json.loads(prepared.body)["assessment"]) != digest(
                        asdict(prepared.assessment)
                    ):
                        raise HistoryError("acceptance_history_integrity")
                    body = prepared.body
            return journal.finish(outcome, body).payload(reused=False)
    except HistoryError:
        raise
    except Exception:
        # No fabricated terminal result for an unexpected verification failure.
        raise HistoryError("acceptance_history_integrity") from None
