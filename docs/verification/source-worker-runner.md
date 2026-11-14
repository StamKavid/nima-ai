# Bounded HTTP fixture runner

This implements E8 of the approved source-worker egress plan. HTTP-stage success
requires all 18 fixed HTTP cases and independent controls, stable packet policy
and namespace identity, actual gateway outage/restart and verified removal of
the run's Docker resources. Browser cases and full isolation acceptance remain
E9–E12 work. There is no live profile or production deployment.

## Run from the checkout

Use Linux/amd64, a local Docker daemon at `/var/run/docker.sock`, host `iproute2`
and at least 8 GiB free on Docker's data filesystem. The controller and daemon
must share host networking so the controller can bind the disposable test bridge
listener. It does not request host networking for containers or edit host routes.
The fixed subnets `172.30.240.0/24` and `172.30.241.0/24` must not overlap existing
host routes or Docker networks. Default routes are not treated as conflicts.

The helper and worker images must already be built with the pinned Dockerfiles,
and the pinned gateway must already be pulled. The existing `source-worker-egress`
job in `.github/workflows/ci.yml` contains those build/pull commands and verifies
the prerequisite sandbox. Builds and image downloads are outside the runtime
budget. Keep the platform proxy and CA settings for those external downloads.
No source API key is needed for these closed fixtures.

```sh
uv run --frozen python -m nima.egress.runner \
  --profile fixtures --stage http --output-dir data/source-worker/http
```

The runner requires the repository's reviewed infrastructure files; installing
the ordinary application wheel alone does not provision this fixture stack.
The future `just source-worker-check` complete-matrix gate remains E11 work.

## What is bounded and owned

- Each Docker command captures stdout and stderr incrementally, with a combined
  1 MiB limit. Output overflow or deadline expiry kills only that command's
  process group. The leader remains unreaped until group cleanup, preventing its
  PID from being recycled before signaling. No shell is used.
- The monotonic runtime budget is 600 seconds. The final 60 seconds are reserved
  for cleanup, so ordinary work cannot consume the entire allowance. Command
  capture uses the remaining allowance as an upper bound. The budget is not a
  real-time scheduling guarantee for a blocked kernel or filesystem operation.
- The controller generates its own UUID/project, private state directory and
  fixture credentials. Docker endpoint/context overrides are cleared; registry
  authentication configuration is preserved. Operator project names and remote
  Docker endpoints are not command options.
- Before deleting anything, cleanup checks every selected container/network/
  volume ID, run and project labels, allowed container role and exact permitted
  volume name. It removes those exact IDs and verifies that no labelled resources
  remain. A foreign or malformed ownership observation stops deletion. There is
  no prune, Compose down, unrelated image cleanup or host firewall mutation.
- The controller marks creation before attempting startup, so partial startup
  still runs owned cleanup. Preparation failures do not query Docker for cleanup.
  Private configuration is removed before report publication.

The process layer has two narrow, explained Bandit annotations for subprocess
import/Popen. Its only application caller supplies fixed Docker/ip executables
and structured arguments; there is no operator-selected shell command. The
earlier nft/ip helper annotations remain separate. No global exclusion, quality
threshold, privilege, TLS or sandbox setting changes.

## Report meaning

Successful execution publishes `<run-uuid>.json` atomically in an owner-only
directory, with file mode 0600, a local Git exclusion and its own marker
`.nima-source-worker-http`. Unrelated nonempty directories, symlinks, broad
permissions and conflicting existing reports are rejected.

`source-worker-http-stage-v1` records actual image IDs, packet-policy digest,
network namespace inode, fixture-policy/runtime-profile digests, UTC times,
monotonic elapsed time, case evidence and cleanup verification. Its explicit
boundaries are:

```json
{
  "http_stage_passed": true,
  "complete_matrix": false,
  "isolation_checks_passed": false,
  "internet_egress_verified": false,
  "investigator_ip_protection_verified": false,
  "production_ready": false
}
```

The report lists all ten pending browser cases. The original full receipt
validator still requires all 28 cases and actual browser runtime evidence;
HTTP-stage reports cannot pass it. These files are infrastructure evidence,
not company-registry observations or source-collection receipts.

The CLI returns 0 for the completed HTTP stage, 1 for runtime/publication failure,
2 for invalid options, and 130 for a handled keyboard interruption. It emits only
a redacted summary. No successful stage is published when controls, cases or
owned cleanup fail. Actual SIGKILL/termination and packet-guard mutation
experiments remain E10 work; the normal cleanup path cannot recover a controller
that the operating system has already killed.

## Verification

Real child-process tests exercise stream floods, timeouts, closed/held pipes,
background descendants, environment isolation and private result representation.
Controller tests cover partial startup, host/Docker route conflicts, malformed
observations, image/network/policy rejection, ownership conflicts across resource
classes, cleanup expiry and residual resources. Stage/runner tests verify exact
HTTP case coverage, failed controls, packet drops/deliveries, interruption,
canonical tamper rejection, full-receipt rejection and safe publication.

The fourth explicit Docker test now invokes `run_http` and reads its published
report. The other three real tests continue exercising fixtures/private controls,
HTTPX/Chromium gateway protocols and packet/user-namespace enforcement. Unit
doubles test controller failure behavior; they are not the packet-enforcement gate.
Final-head hosted run links and measurements are recorded in the delivery PRs.

Local `just check` was attempted; real PostgreSQL tests remain blocked in this
executor because its disposable test database is unavailable and Docker storage
is insufficient. Lint, strict types, focused tests, build, source security and
the locked dependency audit pass. Hosted quality uses real PostgreSQL and keeps
the existing 90% combined line/branch coverage requirement.
