"""Prepare fictional browser fixtures in a new private directory, without source HTTP."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from nima.analytics.buyer_readout import prepare_buyer_result
from nima.analytics.buyer_request import BuyerRequest
from nima.views.buyer_evidence import export_buyer_evidence_view
from tests.buyer_acceptance_samples import request_file
from tests.test_analytics_reconcile import captured
from tests.test_analytics_snapshot import reader
from tests.test_buyer_readout import record, request_for
from tests.test_buyer_view_native import selection
from tests.test_citation_acceptance import subject
from tests.test_cpv_readout import seed


def build(output: Path) -> Path:
    """Use only an explicitly configured local nima_test server and owned scratch DB."""
    dsn = os.environ.get("NIMA_TEST_DSN", "")
    connection = conninfo_to_dict(dsn)
    if (
        connection.get("host") not in {"127.0.0.1", "localhost", "::1"}
        or connection.get("dbname") != "nima_test"
    ):
        raise ValueError("Set NIMA_TEST_DSN to a disposable local database named nima_test")
    if not output.is_absolute() or ".git" in output.parts or ".." in output.parts:
        raise ValueError("Use a new absolute private directory outside Git")
    os.umask(0o077)
    output.mkdir(mode=0o700, parents=True)
    manifest = {}
    name = "nima_test_buyer_view_" + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
        owner = make_conninfo(dsn, dbname=name)
        try:
            primary = output / "primary"
            primary.mkdir(mode=0o700)
            root = primary / "raw"
            rows = [
                {
                    **record("900719925474099312345", "B1", ["111111111"]),
                    "title": 'Σύμβαση </script><img src=x onerror="alert(1)">',
                    "totalCostWithoutVAT": 123456789012345678901234567890,
                    "cancelled": False,
                },
                {**record("B", "B1", ["222222222"]), "cancelled": False},
                {**record("C", "B1", ["111111111", "222222222"]), "cancelled": False},
            ]
            request = request_for(seed(owner, root, rows), root)
            with reader(owner) as (restricted, _):
                parent = prepare_buyer_result(restricted, request)
            first = {
                "label": "Fictional — clear cohort",
                "request_path": str(request_file(request, primary / "request.json")),
                "report_path": str(subject(primary / "reports", parent.body)),
            }
            other = selection(owner, output / "limited", unknown=True)
            second = {
                "label": "Fictional — limited cohort",
                "request_path": str(other.request_path),
                "report_path": str(other.report_path),
            }
            empty = output / "empty"
            empty.mkdir(mode=0o700)
            saved, _ = captured(owner, empty / "raw", empty=True)
            blank = BuyerRequest(
                saved.run_ids, saved.observation_cutoff, "B1", saved.archive_bindings
            )
            with reader(owner) as (restricted, _):
                parent = prepare_buyer_result(restricted, blank)
            empty_entry = {
                "label": "Fictional — empty capture",
                "request_path": str(request_file(blank, empty / "request.json")),
                "report_path": str(subject(empty / "reports", parent.body)),
            }
            cases = {
                "paired": [first, second],
                "empty": [empty_entry],
                "hostile": [{**first, "label": 'Ελληνικά </script><img src=x onerror="alert(1)">'}],
            }
            for label, entries in cases.items():
                config = output / (label + ".json")
                config.write_text(
                    json.dumps(
                        {"version": "nima-buyer-evidence-view-request-v1", "entries": entries},
                        ensure_ascii=False,
                    )
                )
                directory = output / (label + "-views")
                with reader(owner) as (restricted, _):
                    result = export_buyer_evidence_view(restricted, config, directory)
                artifact = directory / (result.artifact_sha256 + ".html")
                assert hashlib.sha256(artifact.read_bytes()).hexdigest() == result.artifact_sha256
                manifest[label] = {
                    "path": str(artifact),
                    "sha256": result.artifact_sha256,
                    "states": result.entry_states,
                }
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
    path = output / "browser-fixtures.private.json"
    path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(build(args.output))
