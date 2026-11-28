"""Private-safe command adapter; root CLI composition owns analytics delegation."""

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Never

from nima.views.buyer_evidence import export_buyer_evidence_view
from nima.views.request import ViewError


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ViewError("view_input")


def run(argv: list[str]) -> int:
    try:
        parser = _Parser(prog="python -m nima analytics buyer-evidence-view", allow_abbrev=False)
        parser.add_argument(
            "--config", type=Path, required=True, help="Private saved-cohort configuration"
        )
        parser.add_argument("--output-dir", type=Path, required=True, help="Private HTML directory")
        args = parser.parse_args(argv)
        dsn = os.environ.get("NIMA_DATABASE_URL", "")
        if not dsn.strip():
            raise ViewError("view_input")
        result = export_buyer_evidence_view(dsn, args.config, args.output_dir)
    except ViewError as error:
        reason = str(error)
    except KeyboardInterrupt:
        reason = "view_interrupted"
    except SystemExit as error:
        return 0 if error.code == 0 else 2
    else:
        print(json.dumps({"status": "complete", **asdict(result)}, allow_nan=False))
        return 0
    print(json.dumps({"status": "failed", "failure": reason}))
    return 2 if reason == "view_input" else 130 if reason == "view_interrupted" else 1
