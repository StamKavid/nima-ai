set dotenv-load := false

export UV_CACHE_DIR := env('UV_CACHE_DIR', justfile_directory() + '/.cache/uv')
export PIP_CACHE_DIR := env('PIP_CACHE_DIR', justfile_directory() + '/.cache/pip')
GITLEAKS := env('GITLEAKS', '.tools/bin/gitleaks')

# Run the same complete quality gate used in CI.
default: check

setup:
    uv sync --frozen
    {{quote(just_executable())}} setup-security

setup-security:
    sh scripts/install-gitleaks.sh

lint:
    uv run --frozen ruff format --check .
    uv run --frozen ruff check .

typecheck:
    uv run --frozen mypy

test:
    uv run --frozen pytest --cov=scripts --cov=nima --cov-report=term-missing --cov-report=xml

build:
    uv build

secrets:
    {{quote(GITLEAKS)}} dir . --redact --no-banner

security:
    uv run --frozen bandit -q -r scripts src
    {{quote(just_executable())}} secrets

audit:
    mkdir -p work
    uv export --frozen --all-groups --no-emit-project --output-file work/audit-requirements.txt > /dev/null
    uv run --frozen pip-audit --strict --require-hashes --disable-pip -r work/audit-requirements.txt --cache-dir .cache/pip-audit

container-lock:
    uv export --frozen --all-groups --no-emit-project --no-header --output-file infra/requirements-orchestration.txt > /dev/null

container-lock-check:
    mkdir -p work
    uv export --frozen --all-groups --no-emit-project --no-header --output-file work/image-requirements.txt > /dev/null
    cmp infra/requirements-orchestration.txt work/image-requirements.txt

# Compare committed metadata using explicit full commit IDs, independent of dirty files.
contracts-check base head:
    uv run --frozen python scripts/check_contracts.py --base {{quote(base)}} --head {{quote(head)}}

# Run every Docker case and validate one fresh full fixture receipt for export.
source-worker-check receipt_dir="":
    #!/usr/bin/env bash
    set -euo pipefail
    task_receipt_dir={{quote(receipt_dir)}}
    if [ -z "$task_receipt_dir" ]; then
        mkdir -p data/source-worker/receipts
        task_receipt_dir=$(mktemp -d data/source-worker/receipts/check.XXXXXXXX)
    fi
    uv run --frozen python -m nima.egress.receipt_check prepare "$task_receipt_dir"
    NIMA_SOURCE_WORKER_RECEIPT_DIR="$task_receipt_dir" uv run --frozen pytest tests/source_worker_integration.py
    uv run --frozen python -m nima.egress.receipt_check verify "$task_receipt_dir"

check: container-lock-check lint typecheck test build security
