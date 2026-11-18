"""Ingestion can import schema support without loading consumer/domain layers."""

import subprocess
import sys


def test_schema_import_does_not_load_semantics_analytics_or_storage() -> None:
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import nima.contracts.schema; "
            "assert not any(n.startswith(('nima.semantics', 'nima.analytics', 'nima.storage')) "
            "for n in sys.modules)",
        ],
        check=True,
    )
