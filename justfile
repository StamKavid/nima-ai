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

skills-check:
    uv run --frozen python scripts/verify_skills.py

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

check: skills-check container-lock-check lint typecheck test build security
