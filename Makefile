export UV_CACHE_DIR ?= $(CURDIR)/.cache/uv
export PIP_CACHE_DIR ?= $(CURDIR)/.cache/pip
GITLEAKS ?= .tools/bin/gitleaks

.PHONY: setup setup-security skills-check lint typecheck test build security secrets audit check

setup:
	uv sync --frozen
	$(MAKE) setup-security

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
	$(GITLEAKS) dir . --redact --no-banner

security:
	uv run --frozen bandit -q -r scripts src
	$(MAKE) secrets

audit:
	mkdir -p work
	uv export --frozen --all-groups --no-emit-project --output-file work/audit-requirements.txt > /dev/null
	uv run --frozen pip-audit --strict --require-hashes --disable-pip -r work/audit-requirements.txt --cache-dir .cache/pip-audit

check: skills-check lint typecheck test build security
