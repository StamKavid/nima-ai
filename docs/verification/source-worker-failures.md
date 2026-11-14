# Controlled-worker failure experiments

These are E10 tests of the approved fixture boundary. Run the complete explicit
suite on the same supported Linux/amd64 host and pinned images as the
[browser matrix](source-worker-browser.md):

```sh
uv run --frozen pytest tests/source_worker_integration.py
```

The suite must pass without skipped cases. Ordinary quality tests, source security,
the locked advisory audit and Compose remain required. The local executor lacks
the disposable PostgreSQL database and sufficient Docker data capacity; hosted
verification supplies the physical fixture evidence. Candidate revisions and
exact-head hosted measurements are recorded in the linked delivery PRs.

## Packet-rule mutation and restoration

[PR #57](https://github.com/StamKavid/nima-ai/pull/57) adds a narrow UID/address/port
allow rule inside the disposable worker namespace. The original policy validator
must reject the modified table, and the browser negative probe must fail while
the independent canary confirms a forbidden request arrived. The test deletes
only the newly observed kernel rule handle in finally, checks original handles,
policy bytes/digest and namespace, then verifies restored blocking. After cleanup,
the full 28-case runner must pass on fresh, independently owned fixtures.

## Worker deadline and missing setup capability

[PR #59](https://github.com/StamKavid/nima-ai/pull/59) stalls a real sandboxed
Chromium attempt with live child-driver kernel observations. The original
15-second worker alarm must report `browser_attempt_deadline` and exit 1. The
container must disappear before controller cleanup; the controller must fail,
clean its resources and publish no success receipt.

[PR #60](https://github.com/StamKavid/nima-ai/pull/60) omits only NET_ADMIN from the
setup helper. The test observes root UID, zero effective/permitted/bounding
capabilities, no-new-privileges, seccomp and a read-only root. The original setup
helper must reject the process. The real controller must fail and clean its
owned resources without publishing a receipt. This does not add a production
capability override or make a missing prerequisite optional.

## Controller interruption and independent reclamation

[PR #61](https://github.com/StamKavid/nima-ai/pull/61) uses actual SIGINT, SIGTERM
and SIGKILL. The controller pauses at a synchronized boundary after successful
gateway/packet controls, between Docker commands. PID file descriptors pin the
child identity for signaling. SIGINT must return 130 with the controller's own
cleanup complete. Hard signals must leave owned fixtures for the independently
owning test supervisor; a killed Python process cannot run its finally block.

The supervisor generates ownership before forking and uses the original strict
project/run/role cleanup checks. An unrelated, separately owned network-none
container must survive interrupted-run cleanup. It is then removed by its own
owner. Empty temporary contexts are reclaimed only beneath the known private test
root with rmdir, which refuses unexpected nonempty data. No prune, broad filesystem
deletion, host firewall change or unfiltered diagnostic artifact is involved.

These experiments cover the stated between-command boundary. They do not supply
a deployed supervisor or establish recovery from every possible in-flight host
command failure. Deployment-specific supervision and public-IP verification are
separate work.

## Diagnostics and limits

Runtime-generated fixture credentials must be absent from captured diagnostics.
Checks use fixed failures so pytest cannot expand a secret-bearing comparison.
Controller trace files are owner-only and bounded when read; SIGINT emits only a
fixed interruption result, while hard signals must leave the trace empty. No
failure experiment may publish an accepted success receipt or broaden cleanup.

The ordinary full validator, case catalog, certificate verification, Chromium
sandbox, worker capabilities and 25-minute CI limit remain unchanged. Every
fixture receipt keeps Internet-egress verification, deployed investigator IP
protection and production readiness false. No live-source request or deployment
is performed by these tests.
