# Local development/verification image; production packaging is a separate decision.
FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY infra/requirements-orchestration.txt /tmp/requirements.txt
RUN --mount=type=secret,id=ca_bundle \
    PIP_CERT=/run/secrets/ca_bundle python -m pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt \
    && python -m pip install --no-deps --no-build-isolation . \
    && useradd --uid 10001 --create-home nima \
    && mkdir -p /evidence /control \
    && chown nima:nima /evidence /control \
    && chmod 700 /evidence /control
USER 10001:10001
