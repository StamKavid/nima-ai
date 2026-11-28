"""HTML retains verified data and exact downloads without approving draft results."""

import base64
import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from nima.analytics.buyer_view import prepare_buyer_evidence_view
from nima.analytics.buyer_view_html import render_view
from tests.test_analytics_snapshot import reader
from tests.test_buyer_view_native import selection


def test_offline_document_preserves_exact_sources_ties_and_independent_trust_states(
    pg_dsn: str, tmp_path: Path
) -> None:
    entries = (
        selection(pg_dsn, tmp_path / "one"),
        selection(pg_dsn, tmp_path / "two", unknown=True),
    )
    with reader(pg_dsn) as (dsn, _):
        prepared = prepare_buyer_evidence_view(dsn, entries)
    body = render_view(prepared)
    assert body == render_view(prepared)
    text = body.decode()
    assert "Draft descriptive readout" in text and "review_required" in text
    assert "insufficient_evidence" in text and "unresolved_suppliers" in text
    assert "GR:111111111" in text and "GR:222222222" in text
    assert text.count('class="draft-share">2/3') == 4
    groups = re.findall(
        r'<details class="supplier"><summary>.*?</summary><ul>(.*?)</ul>', text, re.S
    )
    assert [re.findall(r'data-publication="e0-r([0-9]+)"', row) for row in groups[:2]] == [
        ["0", "2"],
        ["1", "2"],
    ]
    selected_pointers = re.findall(
        r'data-original="[0-9a-f]{64}" data-pointer="(/content/[0-9]+)"', text
    )
    assert selected_pointers == [
        "/content/0",
        "/content/1",
        "/content/2",
        "/content/0",
        "/content/1",
        "/content/2",
        "/content/3",
    ]
    assert "Verified during export" in text and "Opening this file" in text
    assert 'http-equiv="Content-Security-Policy"' in text and "connect-src &#x27;none&#x27;" in text
    match = re.search(r'<script id="view-data" type="application/json">(.*?)</script>', text, re.S)
    assert match
    data = json.loads(match[1])
    for digest, raw in prepared.originals:
        assert base64.b64decode(data["downloads"][digest]["base64"]) == raw
    for frame in prepared.entries:
        for exact in (frame.report_body, frame.insight_body, frame.assessment_body):
            digest = hashlib.sha256(exact).hexdigest()
            assert base64.b64decode(data["downloads"][digest]["base64"]) == exact
    assert data["manifest"]["version"] == "nima-buyer-evidence-view-v1"
    assert len(data["manifest"]["entries"]) == 2


def test_hostile_label_is_text_and_cannot_terminate_a_script(pg_dsn: str, tmp_path: Path) -> None:
    label = 'Ελληνικά </script><img src=x onerror="alert(1)">'
    entry = replace(selection(pg_dsn, tmp_path / "one"), label=label)
    with reader(pg_dsn) as (dsn, _):
        body = render_view(prepare_buyer_evidence_view(dsn, (entry,)))
    assert label.encode() not in body
    assert b"&lt;/script&gt;&lt;img" in body
    assert b"<img" not in body


def test_browser_assets_are_bound_by_csp_and_have_no_network_or_html_evaluation(
    pg_dsn: str, tmp_path: Path
) -> None:
    entry = selection(pg_dsn, tmp_path / "one")
    with reader(pg_dsn) as (dsn, _):
        body = render_view(prepare_buyer_evidence_view(dsn, (entry,)))
    text = body.decode()
    script = re.search(r'<script id="view-script">(.*?)</script>', text, re.S)
    style = re.search(r"<style>(.*?)</style>", text, re.S)
    assert script and style
    for asset in (script[1], style[1]):
        digest = base64.b64encode(hashlib.sha256(asset.encode()).digest()).decode()
        assert "sha256-" + digest in text
    for forbidden in ("innerHTML", "eval(", "fetch(", "XMLHttpRequest", "https://", "http://"):
        assert forbidden not in script[1]


def test_final_html_limit_is_enforced_after_embedding(
    pg_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from nima.analytics import buyer_view_html as renderer
    from nima.analytics.buyer_view_request import ViewError

    entry = selection(pg_dsn, tmp_path / "one")
    with reader(pg_dsn) as (dsn, _):
        prepared = prepare_buyer_evidence_view(dsn, (entry,))
    maximum = len(render_view(prepared)) - 1
    monkeypatch.setattr(renderer, "MAX_HTML_BYTES", maximum)
    with pytest.raises(ViewError, match="^view_limit$"):
        render_view(prepared)


def test_empty_capture_keeps_no_answer_and_its_original_page(pg_dsn: str, tmp_path: Path) -> None:
    from nima.analytics.buyer_readout import prepare_buyer_result
    from nima.analytics.buyer_request import BuyerRequest
    from nima.analytics.buyer_view_request import BuyerViewEntry
    from tests.buyer_acceptance_samples import request_file
    from tests.test_analytics_reconcile import captured
    from tests.test_citation_acceptance import subject

    saved, _ = captured(pg_dsn, tmp_path / "raw", empty=True)
    request = BuyerRequest(saved.run_ids, saved.observation_cutoff, "B1", saved.archive_bindings)
    with reader(pg_dsn) as (dsn, _):
        parent = prepare_buyer_result(dsn, request)
        entry = BuyerViewEntry(
            "Empty",
            request_file(request, tmp_path / "request.json"),
            subject(tmp_path / "reports", parent.body),
        )
        prepared = prepare_buyer_evidence_view(dsn, (entry,))
    html = render_view(prepared).decode()
    assert "No captured buyer publications" in html
    assert "absence of real-world activity" in html and "No approved insight" in html
    assert "provider_empty_capture" in html and len(prepared.originals) == 1


def test_fictional_certified_frame_keeps_all_ties_and_selected_witnesses(
    pg_dsn: str, tmp_path: Path
) -> None:
    from nima.analytics.buyer_request import read_buyer_request
    from nima.analytics.buyer_view import PreparedBuyerView, PreparedViewEntry
    from nima.dataops.buyer_acceptance import prepare_buyer_acceptance
    from nima.insights import buyer_participation
    from tests.buyer_insight_samples import certified

    entry = selection(pg_dsn, tmp_path / "one")
    request = read_buyer_request(entry.request_path)
    with reader(pg_dsn) as (dsn, _):
        prepared = prepare_buyer_evidence_view(dsn, (entry,))
        fitness = prepare_buyer_acceptance(dsn, request, entry.report_path)
    parent, hypothetical = certified(prepared.entries[0].report_body, fitness)
    insight = buyer_participation._compose(request, parent, hypothetical)
    fixture = PreparedBuyerView(
        (
            PreparedViewEntry(
                "Fictional certified fixture",
                parent,
                insight.body,
                hypothetical.body,
                insight.status,
            ),
        ),
        prepared.originals,
    )
    text = render_view(fixture).decode()
    assert 'data-insight-status="answered"' in text
    assert "Largest captured participation is 2 of 3" in text
    assert text.count('class="draft-share">2/3') == 2
    assert text.count("<h3>Selected observation</h3>") == 3
    assert "No approved insight" not in text
