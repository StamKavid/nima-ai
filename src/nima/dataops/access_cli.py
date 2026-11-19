"""Access audit publication and print-only grants, with fixed operational diagnostics."""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

from nima.dataops.access_audit import AuditError, AuditResult, assess
from nima.dataops.access_audit_store import read_snapshot
from nima.dataops.access_contract import ContractError, get_profile
from nima.dataops.access_grants import GrantError, render_grants
from nima.dataops.health import HealthError
from nima.dataops.health_store import validate_path
from nima.identity import AssessmentError
from nima.identity.artifacts import encode, publish

REPORT_VERSION = "access-audit-v1"


class _Parser(argparse.ArgumentParser):
    reason = "access_audit_configuration"

    def error(self, message: str) -> NoReturn:
        raise HealthError(self.reason)


def _event(component: str, event: str, **fields: str) -> None:
    print(json.dumps({"component": component, "event": event, **fields}), file=sys.stderr)


def _report(result: AuditResult, observed_at: datetime) -> bytes:
    return encode(
        {
            "version": REPORT_VERSION,
            "contract_version": result.contract_version,
            "profile": result.profile,
            "role": result.role,
            "observed_at": observed_at.isoformat(timespec="seconds"),
            "status": "checks_passed" if result.passed else "attention",
            "reasons": [
                {"code": r.code.value, "subject": r.subject, "detail": r.detail}
                for r in result.reasons
            ],
            "limitations": list(result.limitations),
            "scope": "catalogue privileges and protections at one point in time",
        }
    )


def _exit_code(reason: str) -> int:
    if reason == "access_audit_interrupted":
        return 130
    return 2 if reason == "access_audit_configuration" else 1


def run_audit(argv: list[str]) -> int:
    component = "dataops.access_audit"
    _event(component, "started")
    try:
        parser = _Parser(prog="python -m nima dataops", allow_abbrev=False)
        parser.add_argument("operation", choices=("access-audit",))
        parser.add_argument("--role", required=True)
        parser.add_argument("--profile", required=True)
        parser.add_argument("--output-dir", type=Path, required=True)
        args = parser.parse_args(argv)
        try:
            validate_path(args.output_dir)
            get_profile(args.profile)
        except (HealthError, ContractError):
            raise HealthError("access_audit_configuration") from None
        snapshot = read_snapshot(os.environ.get("NIMA_DATABASE_URL", ""), args.role)
        result = assess(snapshot, args.profile)
        publish(args.output_dir, _report(result, datetime.now(UTC)))
    except HealthError as error:
        reason = str(error)
    except AuditError:
        reason = "access_audit_evidence"
    except (AssessmentError, OSError):
        reason = "access_audit_output"
    except KeyboardInterrupt:
        reason = "access_audit_interrupted"
    else:
        status = "checks_passed" if result.passed else "attention"
        _event(component, "completed", assessment=status)
        print(json.dumps({"status": status, "attention_count": len(result.reasons)}))
        return 0 if result.passed else 3
    _event(component, "failed", reason=reason)
    print(json.dumps({"status": "failed", "failure": reason}))
    return _exit_code(reason)


def run_grants(argv: list[str]) -> int:
    """Print reviewed statements only; never reads configuration or opens a connection."""
    component = "dataops.access_grants"
    _event(component, "started")
    try:
        parser = _Parser(prog="python -m nima dataops", allow_abbrev=False)
        parser.reason = "access_grants_configuration"
        parser.add_argument("operation", choices=("access-grants",))
        parser.add_argument("--profile", required=True)
        parser.add_argument("--role", required=True)
        args = parser.parse_args(argv)
        text = render_grants(args.profile, args.role)
    except (HealthError, ContractError, GrantError):
        _event(component, "failed", reason="access_grants_configuration")
        return 2
    sys.stdout.write(text)
    _event(component, "completed")
    return 0
