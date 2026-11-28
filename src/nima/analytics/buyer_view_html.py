"""Static offline presentation; provider numbers and witness selection stay upstream."""

import base64
import hashlib
import json
from html import escape
from importlib.resources import files
from string import Template
from typing import Any

from nima.analytics.buyer_view import MAX_HTML_BYTES, PreparedBuyerView, PreparedViewEntry
from nima.analytics.buyer_view_request import ViewError
from nima.identity.artifacts import encode


def _text(value: object) -> str:
    return escape(str(value), quote=True)


def _download(digest: str, label: str) -> str:
    return f'<button type="button" data-download="{_text(digest)}">{_text(label)}</button>'


def _original(digest: str, pointer: str = "") -> str:
    return (
        f'<button type="button" data-original="{_text(digest)}" '
        f'data-pointer="{_text(pointer)}">View original page</button>'
        + _download(digest, "Download exact original")
    )


def _publications(report: dict[str, Any], prefix: str) -> str:
    evidence = {e["observation_id"]: e for e in report["evidence"]}
    pages = {(p["run_id"], p["page_number"]): p for p in report["verified_pages"]}
    sections = []
    for index, record in enumerate(report["metric"]["result"]["records"]):
        witnesses = []
        for oid in record["observation_ids"]:
            row = evidence[oid]
            page = pages[row["run_id"], row["page_number"]]
            detail = {
                "Observation": oid,
                "Observed at": row["observed_at"],
                "Run": row["run_id"],
                "Page": row["page_number"],
                "Pointer": row["json_pointer"],
                "Version": row["content_sha256"],
                "Raw SHA-256": page["raw_sha256"],
            }
            fields = "".join(
                f'<dt>{_text(k)}</dt><dd class="mono">{_text(v)}</dd>' for k, v in detail.items()
            )
            witnesses.append(
                '<div class="witness"><h3>Selected observation</h3><dl>'
                + fields
                + '</dl><div class="actions">'
                + _original(page["raw_sha256"], row["json_pointer"])
                + "</div></div>"
            )
        sections.append(
            f'<details class="publication" id="{prefix}-r{index}"><summary>'
            + _text(record["source_id"])
            + "<span>"
            + _text(record["resolution"])
            + " · reported cancellation: "
            + _text({True: "true", False: "false", None: "unknown"}[record["cancelled"]])
            + "</span></summary>"
            + "".join(witnesses)
            + "</details>"
        )
    return "".join(sections) or (
        '<p class="muted">No captured buyer publications for this selection. '
        "This does not establish absence of real-world activity.</p>"
    )


def _entry(frame: PreparedViewEntry, index: int, template: str) -> str:
    report, insight = json.loads(frame.report_body), json.loads(frame.insight_body)
    result = report["metric"]["result"]
    prefix = f"e{index}"
    ids = {r["source_id"]: i for i, r in enumerate(result["records"])}
    rows = []
    for supplier in result["suppliers"]:
        links = "".join(
            (
                f'<li><a href="#{prefix}-r{ids[s]}" '
                f'data-publication="{prefix}-r{ids[s]}">{_text(s)}</a></li>'
            )
            for s in supplier["source_ids"]
        )
        tie = (
            '<span class="tie-note">Highest captured count · all ties retained</span>'
            if supplier["supplier_key"] in result["top_supplier_keys"]
            else ""
        )
        rows.append(
            '<tr><td><details class="supplier"><summary>'
            + _text(supplier["supplier_key"])
            + "</summary><ul>"
            + links
            + "</ul></details>"
            + tie
            + "</td><td>"
            + _text(supplier["record_count"])
            + '</td><td class="draft-share">'
            + f"{supplier['record_count']}/{result['resolved_records']}"
            + "</td><td>"
            + _text(supplier["cancelled_count"])
            + " / "
            + _text(supplier["unknown_cancellation_count"])
            + "</td></tr>"
        )
    stats = "".join(
        f'<div class="stat"><span>{label}</span><strong>{result[key]}</strong></div>'
        for label, key in (
            ("Captured publications", "buyer_records"),
            ("Resolved denominator", "resolved_records"),
            ("Unresolved publications", "unresolved_records"),
            ("Joint eligible-group records", "joint_records"),
        )
    )
    review = report["metric"]["definition"]["status"]
    reasons = "".join(
        "<li>"
        + _text(reason.replace("_", " ").capitalize())
        + ' <span class="mono">('
        + _text(reason)
        + ")</span></li>"
        for reason in insight["reason_codes"]
    )
    statement = (
        _text(insight["answer"]["statement"])
        if insight["answer"] is not None
        else "No approved insight. Inspect the descriptive readout and its limitations."
    )
    limits = "".join("<li>" + _text(limit) + "</li>" for limit in insight["interpretation_limits"])
    snapshots = "".join(
        _download(hashlib.sha256(body).hexdigest(), label)
        for body, label in (
            (frame.report_body, "Exact readout"),
            (frame.assessment_body, "Data assessment"),
            (frame.insight_body, "Insight decision"),
        )
    )
    raw_links = "".join(
        '<div class="actions">' + _original(page["raw_sha256"]) + "</div>"
        for page in report["verified_pages"]
    )
    return Template(template).substitute(
        prefix=prefix,
        hidden=" hidden" if index else "",
        label=_text(frame.label),
        buyer=_text(report["request"]["buyer"]),
        cutoff=_text(report["request"]["observation_cutoff"]),
        review=_text(review.capitalize()),
        fitness=_text(insight["data_fitness"]["assessment"]["status"]),
        source_current=_text(report["quality"]["source_current"].replace("_", " ")),
        stats=stats,
        rows="".join(rows),
        participations=_text(result["participation_total"]),
        status=_text(frame.status.replace("_", " ")),
        status_code=_text(frame.status),
        statement=statement,
        reasons=reasons,
        limits=limits,
        ambiguous=_text(", ".join(result["ambiguous_source_ids"]) or "None observed"),
        partial=_text(", ".join(result["partial_source_ids"]) or "None observed"),
        snapshots=snapshots,
        publications=_publications(report, prefix),
        raw_links=raw_links,
    )


def render_view(prepared: PreparedBuyerView) -> bytes:
    assets = {
        name: files("nima.analytics").joinpath("buyer_view_assets", name).read_bytes()
        for name in ("view.html", "entry.html", "view.css", "view.js")
    }
    manifest = {
        "version": "nima-buyer-evidence-view-v1",
        "view_definition": "buyer_to_original_evidence.v1",
        "asset_version": "1",
        "assets": {k: hashlib.sha256(v).hexdigest() for k, v in assets.items()},
        "entries": [
            {
                "label": e.label,
                "status": e.status,
                "readout_sha256": hashlib.sha256(e.report_body).hexdigest(),
                "insight_sha256": hashlib.sha256(e.insight_body).hexdigest(),
                "assessment_sha256": hashlib.sha256(e.assessment_body).hexdigest(),
                **json.loads(e.insight_body)["subject"],
            }
            for e in prepared.entries
        ],
    }
    downloads = {
        digest: {"filename": digest + ".body", "base64": base64.b64encode(body).decode()}
        for digest, body in prepared.originals
    }
    for entry in prepared.entries:
        for body in (entry.report_body, entry.insight_body, entry.assessment_body):
            digest = hashlib.sha256(body).hexdigest()
            downloads[digest] = {
                "filename": digest + ".json",
                "base64": base64.b64encode(body).decode(),
            }
    data = (
        encode({"manifest": manifest, "downloads": downloads}, limit=MAX_HTML_BYTES)
        .decode()
        .replace("<", "\\u003c")
        .replace("&", "\\u0026")
    )
    hashes = {
        name: base64.b64encode(hashlib.sha256(assets[name]).digest()).decode()
        for name in ("view.css", "view.js")
    }
    csp = (
        f"default-src 'none'; script-src 'sha256-{hashes['view.js']}'; "
        f"style-src 'sha256-{hashes['view.css']}'; connect-src 'none'; "
        "object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'"
    )
    options = "".join(
        f'<option value="e{i}">{_text(e.label)}</option>' for i, e in enumerate(prepared.entries)
    )
    body = (
        Template(assets["view.html"].decode())
        .substitute(
            csp=_text(csp),
            style=assets["view.css"].decode(),
            script=assets["view.js"].decode(),
            options=options,
            entries="".join(
                _entry(e, i, assets["entry.html"].decode()) for i, e in enumerate(prepared.entries)
            ),
            data=data,
        )
        .encode()
    )
    if len(body) > MAX_HTML_BYTES:
        raise ViewError("view_limit")
    return body
