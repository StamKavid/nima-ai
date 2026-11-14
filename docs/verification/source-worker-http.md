# HTTP fixture matrix

This is the HTTP probe slice of E8 in `tasks/plan.md`. It adds no live source
access and does not establish deployed investigator IP protection. The bounded
host runner and private stage reports are now described in
[the runner runbook](source-worker-runner.md). The full receipt validator
still requires all 28 HTTP/browser cases and actual browser runtime evidence.

## What is exercised

`python -m nima.egress.probe_http CASE_NAME` accepts only 18 fixed synthetic
cases. The trusted controller selects the case; the worker cannot supply a URL,
proxy, resolver, certificate path or live profile through this command.

The cases cover an allowed HTTPS request, direct IPv4, removed proxy variables,
`NO_PROXY`, `trust_env=False`, the host bridge, the local metadata fixture,
DNS/UDP, disabled IPv6, three redirect destinations, missing/invalid credentials,
invalid TLS and gateway outage/restart. Each worker command checks its process
privileges and inaccessible private controls before attempting the case.

TLS verification stays enabled. The worker trusts only the public fixture CA.
A 15-second process alarm bounds the whole attempt, in addition to HTTPX's
two-second operation timeouts, one redirect and one-MiB response limit. Output
is a bounded canonical client result; it is not a successful isolation receipt.

## Independent observations

The explicit Docker test runs positive gateway/origin and packet-sink controls
before every attempt. The observer alone can read the deliberately untrusted
CA and establish a verified successful response from that origin. This prevents
a broken TLS server from being mistaken for certificate enforcement.

After resetting deliveries, the controller compares kernel policy identity,
network namespace identity, named packet counters, gateway allow/deny counters,
origin requests and canary/host/metadata deliveries. It feeds the evidence to
the existing case validator. Client errors alone cannot satisfy a negative case.

The outage case stops the real gateway container and checks its stopped state.
Origin counters remain available through private Unix sockets; an unavailable
gateway admin endpoint is never converted into fabricated zero counters. The
restart case checks the same container identity and a healthy successful path.
The first hosted matrix reached the restart case, where Compose also restarted
the one-shot initializer. Its existing refuse-overwrite guard rejected the
populated volume. The corrected test starts only the exact stopped gateway ID;
certificate initialization is never repeated or made permissive for restart.

## Verification and limitations

Focused command:

```sh
uv run --frozen pytest tests/test_source_worker_http.py tests/test_source_worker_observer.py
```

The 65 focused tests pass, including an actual alarm interrupting a stalled
probe and restoration of its signal state. Strict types, lint, build, Bandit, Gitleaks and
the locked dependency audit pass locally. `just check` ran with 670 passing
tests and 131 PostgreSQL setup errors because this executor has no disposable
test database and insufficient Docker storage. Its coverage measurement is
incomplete; the unchanged hosted gate supplies real PostgreSQL.

The mandatory `source-worker-egress` CI job runs
`uv run --frozen pytest tests/source_worker_integration.py`, including this
18-case test. Hosted results are recorded in the PR before merge readiness.
The initial quality head `d93848b` passed 801 tests with 90.84% coverage and all
security/audit checks in run 43492413275. Its matrix exposed the restart issue
described above. Final-head results and the corrected matrix are linked in
[PR #46](https://github.com/StamKavid/nima-ai/pull/46).

Review covered correctness, readability, architecture, security and performance.
The probe has no source-storage, database or orchestration side effects. It
reuses existing case validation. The later E8 slices replace the temporary test
controller with the bounded shared controller and verify its private stage report.
Browser cases remain E9 work. There are no dependency, permission, sandbox, TLS
or check changes.
