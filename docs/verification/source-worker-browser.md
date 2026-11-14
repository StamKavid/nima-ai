# Browser and complete fixture matrix

This is E9 and checkpoint C of the approved source-worker egress plan. The
implementation extends the [bounded HTTP runner](source-worker-runner.md) with
ten sandboxed Chromium cases and a combined 28-case receipt. Candidate `c6e9c39`
in PR #54 passes hosted acceptance; its correction still requires human merge.
There is no live
source profile, Internet-egress measurement or deployed investigator IP protection.

## Commands and prerequisites

Use the same Linux/amd64, local-daemon, native-host-listener, free-space and
prebuilt-image prerequisites as the HTTP runner. The existing CI job builds the
pinned images before running the explicit integration file. Builds and pulls
are outside the controller's 600-second runtime budget; its final 60 seconds
remain reserved for owned cleanup.

```sh
uv run --frozen python -m nima.egress.runner \
  --profile fixtures --stage all --output-dir data/source-worker/matrix

uv run --frozen pytest tests/source_worker_integration.py
```

The ordinary `--stage http` interface remains available. `just source-worker-check`
and the proposed protection-context update remain E11 work. Do not treat this
command as a government-source collector or production deployment procedure.

## What counts as browser evidence

Every browser attempt verifies the pinned Playwright/Chromium versions, actual
worker UID/capability/seccomp/root state, inaccessible private controls and the
reported PID/network/seccomp Chromium sandboxes. Chromium runs with its sandbox
and certificate verification enabled. Its existing private NSS database trusts
the generated public fixture CA; the observer alone can trust the bad-certificate
fixture for its positive control.

The ten cases cover page/script/image/XHR/fetch through CONNECT, an explicit
proxy-bypass attempt, local metadata, DNS, forced QUIC, WebRTC STUN, redirects,
invalid proxy credentials, invalid TLS and actual gateway outage. Each uses only
fixed fixture targets. DNS/QUIC/STUN cases explicitly attempt direct transports;
the controller requires an increase in the corresponding named kernel drop
counter and zero independent target delivery. An exception or absent network
infrastructure cannot satisfy a blocked-transport case.

Hosted investigation found that pinned Chromium reports
`ERR_QUIC_HANDSHAKE_FAILED` for the forced-QUIC attempt. This is classified only
as a client network failure. The independent positive QUIC packet control, named
drop increase and zero target delivery remain mandatory. Unknown client failures
produce fixed diagnostic codes; captured driver/Docker output is never copied
into exception text or the public summary.

Navigation and resource waits have short fixed bounds. A 15-second process alarm
exits the worker even if driver cleanup stalls; Docker terminates its descendants.
Unit tests verify the handler and command configuration. Actual worker/controller
termination experiments remain E10 work.

## Observed runtime and publication

The combined run retains all ten actual browser observations. The trusted
observer reports its own kernel process state. A cap-free read-only helper joins
the gateway namespace and reads its real IPv4 forwarding flag. The host inspects
the exact run-owned internal networks and running-service attachments before
and after the matrix, rejecting external attachments or changed ownership.

Before accepting privilege evidence, independent packet controls prove every
sink is alive, counters reset, and actual worker probes exercise forbidden UID
changes, socket marks, nft modification and nested-user-namespace administration.
The host requires all seven corresponding packet-drop deltas and zero canary,
host or metadata delivery. Namespace identity and packet-policy digest remain
stable. Runtime evidence is never filled from Compose declarations or defaults.

Each gateway-outage case starts from a healthy positive control, stops the actual
gateway and checks its state. The next case starts that exact stopped container;
the final restart case also requires a healthy successful application request.

Only after all 28 named cases reconcile and owned resources/private temporary
configuration are removed may the existing full receipt publisher run. It writes
an atomic 0600 JSON file under an owner-only directory with marker
`.nima-source-worker` and local Git exclusion. The strict full validator is
unchanged: all required runtime fields and named cases remain mandatory. HTTP
stage reports have a different marker and cannot pass as full receipts.

Even a successful controlled-fixture receipt keeps `internet_egress_verified`,
`investigator_ip_protection_verified` and `production_ready` false. It does not
authenticate a remote host or establish a public outbound IP.

## Verification status

Focused tests exercise browser classification/redaction, canonical tamper
rejection, runtime/process observations, forwarding/topology guards and complete
receipt publication. Deliberate sandbox, forwarding and initial-topology guard
mutations were caught and restored. The full local check was attempted; its
PostgreSQL tests have setup errors because this executor lacks a disposable
`NIMA_TEST_DSN`, and the Docker data filesystem is below the 8 GiB prerequisite.
No tests are skipped and the 90% hosted coverage floor is unchanged.

The user merged #51–#53 at main `c02ef94`. The combined implementation at
`b314cfd` passed hosted quality with 963 tests and 91.52% coverage in run
43569432234; the later ICE timing test adds another case. Real Docker checks
passed QUIC/STUN and reached browser gateway outage, where a connection timeout
was rejected by an overly narrow client classifier. Run 43570012078 therefore
failed two of six Docker tests; checkpoint C is not complete.

The outage correction is published in #54. A stopped container can leave
unanswered address resolution instead of immediately refusing TCP. Recognized
connection timeouts are only client outcomes; actual stopped-container state,
healthy preceding controls and zero independent delivery remain mandatory.
All 391 focused source-worker tests pass, including the timeout regressions and
a caught/restored classifier mutation. Lint, strict types, build and security
pass. The local full check has 836 passing tests and 131 PostgreSQL setup errors;
it is not a passing full gate.

Candidate `c6e9c393246820ee8a1638d11c374d420a75c84f` passes all three jobs in
[push run 43613463647](https://github.com/StamKavid/nima-ai/actions/runs/43613463647)
and [PR run 43613476257](https://github.com/StamKavid/nima-ai/actions/runs/43613476257).
Hosted quality supplies real PostgreSQL: 967 tests, 91.55% combined coverage,
successful build/security and no known dependency advisories. All six real Docker
tests pass in 334.31 seconds, including the full 28-case matrix and strict runtime
receipt after cleanup. This passes checkpoint C for controlled fixtures.

The owner explicitly confirmed public repository hosting on 2026-11-14. This
supersedes the old private-hosting requirement; evidence, credentials and databases
remain outside Git. Current branch-protection observations and the effective-rules
gap are documented in [repository settings](../repository-settings.md).

E10 interruption/real packet-guard mutation, E11 complete CI recipe/protection
payload and E12 final delivery review remain subsequent tasks. No dependencies,
TLS rules, browser sandbox permissions or acceptance validators were weakened.
