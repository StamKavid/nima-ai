# Controlled source-worker delivery

Verified 2026-11-14. This is the E12 delivery runbook for the approved fixture-only
worker increment.
The worker proves a configured network boundary against controlled synthetic
services. It provides no government-source collector, remote host, live gateway,
public-IP measurement or production supervisor.

## Supported host and setup

Use a Linux/amd64 checkout, Python 3.12, uv, just 1.59.0, host iproute2 and a local
Docker daemon at `/var/run/docker.sock`. The controller must be able to inspect
Docker's data filesystem, which must have at least 8 GiB free, and share the
daemon's host network namespace. The fixed test subnets `172.30.240.0/24` and
`172.30.241.0/24` must not conflict with existing routes or Docker networks.
Containers do not use host networking or mount the Docker socket.

```bash
sh scripts/install-just.sh
export PATH="$PWD/.tools/bin:$PATH"
uv sync --frozen
```

Before testing locally, execute the ordered setup commands in the
[`source-worker-egress` CI job](../../.github/workflows/ci.yml), from the host and
free-space check through the actual Chromium sandbox check. That is the canonical
executable setup: it derives the hash-verified seccomp overlay, pulls the pinned
Envoy image, builds the helper/worker Dockerfiles, and verifies NET_ADMIN setup,
unprivileged namespace primitives and real sandboxed Chromium. Pins are in
[`pins.json`](../../infra/source-worker/pins.json). Missing prerequisites fail;
do not bypass the checks to run on an unsupported host.

Image/dependency acquisition is a separate build phase using the environment's
proxy and CA trust. Runtime fixtures have closed networks. The command below
does not build images, contact a source, require GEMI credentials or change
Prefect schedules or the SQL source ledger.

## Complete verification command

```bash
just source-worker-check
just check
just audit
```

`just check` additionally needs a disposable PostgreSQL 17 database named
`nima_test`, with `NIMA_TEST_DSN` configured as described in the README.

The source-worker recipe creates a new private directory under ignored
`data/source-worker/receipts/`, runs all 12 explicitly selected Docker tests and
validates one full receipt exported after the normal matrix's runtime/cleanup
assertions. An optional directory argument must be empty and private. A populated
directory fails before Docker execution; existing receipts are never deleted or
accepted as a new run.

The tests include 18 HTTPX and ten Chromium cases, working observer controls,
actual kernel/process/topology observations, TLS/auth rejection, gateway outage,
a real worker deadline, missing setup capability, three actual controller signals
and narrow packet-rule mutation followed by exact restoration and fresh full-matrix
replay. The matrix's case results and runtime observations must reconcile.
See the [browser evidence](source-worker-browser.md) and
[failure experiments](source-worker-failures.md) for the detailed boundaries.

Each controller retains its 600-second budget with the final 60 seconds reserved
for cleanup. Multiple invocations make the complete integration suite longer
than ten minutes; the CI job retains its 25-minute limit. Per-attempt, response,
receipt, command-output and container-resource limits remain enforced.

The lower-level `python -m nima.egress.runner --profile fixtures --stage all`
interface runs one full matrix. Its `--stage http` alternative publishes a partial
HTTP-stage report. Neither replaces the complete failure/mutation gate above.

## Receipts and failure handling

The final verifier reuses the unchanged canonical full-receipt validator. It
requires all 28 cases and actual runtime evidence, private 0700/0600 publication,
one correctly named UUID JSON file and the exact marker/ignore files. Extra files,
symlinks, hardlinks, unsafe modes, observed replacement during reads, oversized
reports and incomplete/noncanonical documents fail. This validates the publication
on the trusted CI host; it is not remote-host attestation.

CI uploads only that validated JSON in `source-worker-fixture-receipt`, after
every integration test and final validation succeed, with seven-day retention.
The separate bounded prerequisite artifact is retained even on failure. Generated
credentials, private CA keys, configurations, browser state and raw traces are
excluded. Do not upload the broader temporary/test directory as diagnostics.

The tested deadline, capability and interruption failures produce no accepted
new full receipt. If another test
fails after the normal matrix has exported its valid receipt, the overall gate
still fails and CI does not upload that full-receipt artifact. Inspect fixed
failure codes and private local state; avoid expanding credential-bearing errors.

Normal and SIGINT cleanup verifies exact IDs, run/project/role labels and residual
resources. A killed controller cannot run its finally block. The hard-signal
tests use an independently owning supervisor and prove unrelated resources
survive. That test harness is not a deployed recovery service or a general
in-flight command recovery guarantee. No prune or broad deletion is authorized.

## Measured delivery evidence

E10 is merged through #61 at `920472e`. Candidate `f3a063e` passed all three jobs
in [run 43622181210](https://github.com/StamKavid/nima-ai/actions/runs/43622181210):
967 quality tests, 91.55% coverage and 12 real Docker tests in 853.96 seconds.

E11 is merged through #63 at `9a4eddf`; its tree matches candidate `4fe920d`,
which passed all three jobs in
[run 43625798326](https://github.com/StamKavid/nima-ai/actions/runs/43625798326):
987 quality tests, 91.58% coverage and 12 real Docker tests in 616.42 seconds.
The recipe's final verifier accepted one full 28-case receipt with all deployment/
privacy flags false. Predecessor `6362671` also passed all three jobs in run
43625478906, including 12 real Docker tests in 834.32 seconds.

The published ZIP, artifact 14126851164, was downloaded and independently checked:
its SHA-256 matches GitHub's recorded digest, it contains exactly one UUID-named
JSON file (10,109 bytes), and the unchanged canonical validator accepts all 28
cases and actual runtime evidence. No marker, configuration or trace is in that
ZIP. Internet-egress verification, investigator-IP protection and production
readiness are false. The later documentation candidate's checks are recorded in
its delivery PR; these measurements belong to the stated implementation commits.

Locally, E11 lint, strict types, build, Bandit, redacted Gitleaks and locked
dependency audit pass; 43 focused receipt tests pass. `just check` reports
856 passes and 131 setup errors without PostgreSQL. The Docker suite fails its
host prerequisite because this executor cannot inspect Docker's data directory.
Those local failures do not substitute for hosted physical fixture evidence.

The five-axis review checks correctness against the fixed matrix and publication
failure paths; readable, small typed modules; reuse of existing evidence/receipt
boundaries; unchanged TLS/sandbox/privilege/ownership and redaction controls; and
bounded, serial work without an extra normal matrix invocation. The unchanged
quality, Compose, audit and 90% coverage gates remain required. The proposed
ruleset names all three CI checks; effective main/dev protection was empty at the
last verification. See [repository settings](../repository-settings.md).

Every accepted fixture receipt keeps `internet_egress_verified`,
`investigator_ip_protection_verified` and `production_ready` false. There is no
deployment, purchase, live-source automation, accepted company identity, graph
edge or trained model in this increment. The product's next step is the pending
offline registry-comparison specification, then reviewed reversible identities
and an evidence-backed temporal graph. The GEMI live-key pilot remains separate.
