"""Fresh verified inputs for one private offline buyer-to-original view."""

import hashlib
import json
import os
from pathlib import Path
from uuid import UUID

from nima.analytics.buyer_request import read_buyer_request
from nima.analytics.request import RequestError
from nima.analytics.result import MAX_RESULT_BYTES
from nima.dataops.acceptance_files import AcceptanceError, read_subject, valid_path
from nima.evidence import EvidenceError, artifacts
from nima.graph.pilot_archive import PilotArchiveError, RawReference, RecoveryLimits, recover
from nima.identity import AssessmentError
from nima.identity.artifacts import encode
from nima.insights.buyer_participation import InsightError, prepare_buyer_insight
from nima.views.models import (
    BuyerViewExport as BuyerViewExport,
)
from nima.views.models import (
    PreparedBuyerView as PreparedBuyerView,
)
from nima.views.models import (
    PreparedViewEntry as PreparedViewEntry,
)
from nima.views.request import BuyerViewEntry, ViewError, decode_config, read_config

MAX_OBSERVATIONS = 500
MAX_PAGES = 32
MAX_RAW_BYTES = 8 * 1024 * 1024


def prepare_buyer_evidence_view(dsn: str, entries: tuple[BuyerViewEntry, ...]) -> PreparedBuyerView:
    """One public insight preparation per entry; no new SQL, source or metric path."""
    if not isinstance(dsn, str) or not dsn.strip() or not isinstance(entries, tuple):
        raise ViewError("view_input")
    try:
        # Reuse the closed decoder for library callers as well as the file boundary.
        configured = decode_config(
            encode(
                {
                    "version": "nima-buyer-evidence-view-request-v1",
                    "entries": [
                        {
                            "label": e.label,
                            "request_path": str(e.request_path),
                            "report_path": str(e.report_path),
                        }
                        for e in entries
                    ],
                },
                limit=16 * 1024,
            )
        )
        if entries != configured:
            raise ViewError("view_input")
        frames = []
        originals: dict[str, bytes] = {}
        pages = observations = 0
        subjects = set()
        for entry in entries:
            request = read_buyer_request(entry.request_path)
            parent = read_subject(entry.report_path, limit=MAX_RESULT_BYTES)
            digest = hashlib.sha256(parent).hexdigest()
            if digest in subjects:
                raise ViewError("view_input")
            subjects.add(digest)
            fresh = prepare_buyer_insight(dsn, request, entry.report_path)
            if fresh.subject_sha256 != digest:
                raise ViewError("view_evidence")
            report, insight = json.loads(parent), json.loads(fresh.body)
            assessment = encode(insight["data_fitness"])
            if (
                hashlib.sha256(assessment).hexdigest() != insight["subject"]["data_fitness_sha256"]
                or insight["subject"]["readout_sha256"] != digest
                or fresh.status != insight["status"]
            ):
                raise ViewError("view_contract")
            verified = report["verified_pages"]
            pages += len(verified)
            observations += sum(page["record_count"] for page in verified)
            if pages > MAX_PAGES or observations > MAX_OBSERVATIONS:
                raise ViewError("view_limit")
            refs = tuple(
                RawReference("kimdis", UUID(p["run_id"]), p["raw_sha256"]) for p in verified
            )
            used = {ref.run_id for ref in refs}
            bindings = tuple(b for b in request.archive_bindings if b.run_id in used)
            recovered = recover(
                refs, bindings, limits=RecoveryLimits(max_total_bytes=MAX_RAW_BYTES)
            )
            for obj in recovered.objects:
                originals[obj.raw_sha256] = obj.body
            if sum(len(body) for body in originals.values()) > MAX_RAW_BYTES:
                raise ViewError("view_limit")
            frames.append(
                PreparedViewEntry(entry.label, parent, fresh.body, assessment, fresh.status)
            )
        return PreparedBuyerView(tuple(frames), tuple(sorted(originals.items())))
    except ViewError:
        raise
    except InsightError as error:
        raise ViewError(str(error).replace("insight_", "view_", 1)) from None
    except RequestError as error:
        raise ViewError(
            "view_limit" if error.reason == "analytics_limit" else "view_input"
        ) from None
    except AcceptanceError as error:
        raise ViewError(str(error).replace("acceptance_", "view_", 1)) from None
    except PilotArchiveError as error:
        raise ViewError(
            "view_limit" if error.reason == "pilot_limit" else "view_evidence"
        ) from None
    except AssessmentError:
        raise ViewError("view_limit") from None
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, RecursionError):
        raise ViewError("view_contract") from None


def export_buyer_evidence_view(dsn: str, config: Path, output_dir: Path) -> BuyerViewExport:
    """Publish one immutable content-named HTML only after every entry verifies."""
    from nima.views.html import render_view

    if not valid_path(config) or not valid_path(output_dir):
        raise ViewError("view_input")
    prepared = prepare_buyer_evidence_view(dsn, read_config(config))
    try:
        body = render_view(prepared)
    except AssessmentError:
        raise ViewError("view_limit") from None
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        if isinstance(error, ViewError):
            raise
        raise ViewError("view_contract") from None
    digest = hashlib.sha256(body).hexdigest()
    try:
        descriptor = artifacts.directory(output_dir, create=True, private=True)
        try:
            artifacts.publish(descriptor, ".gitignore", b"*\n")
            artifacts.publish(descriptor, digest + ".html", body)
        finally:
            os.close(descriptor)
    except (OSError, EvidenceError):
        raise ViewError("view_output") from None
    return BuyerViewExport(digest, tuple(e.status for e in prepared.entries))
