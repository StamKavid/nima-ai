# Approved scope: operator-run remote worker egress pilot

Status: **owner-approved**, 2026-11-16, through owner-merged #104 at `f894800`
and the instruction to continue. The [implementation plan](../../tasks/plan.md)
is proposed for review; commands below remain unimplemented. Provider capability:
`source-ingestion`. This specifies one capability: prepare and verify an isolated
worker boundary on an operator-owned remote host. It extends the approved
[fixture contract](source-worker-egress.md) and
[Publicity-first design](gemi-publicity-fallback.md). PE1 is owner-merged in #103
at `b3ee7eb`; its fixture checks do not establish remote Internet egress.

## Objective and assumptions

Give Nima's operator reproducible configuration and measured evidence that HTTPX
and sandboxed Chromium use the intended gateway, including when settings change
or that gateway fails. This is the prerequisite for later Publicity capture while
the GEMI API key is pending. Configuration preparation and its controlled-endpoint
verification are parts of this single boundary, not separate ingestion products.

Assume one operator-owned Linux/amd64 host, one stable IPv4 egress, Docker Engine
and private SSH-based administration. A 4-vCPU/8-GiB host is a starting sizing
candidate, not measured capacity. The existing supported-host checks, including
Docker disk capacity and kernel/browser isolation, remain mandatory. A remote
host and separately reachable operator-controlled probe endpoints are not available
yet. The public origin must run outside the worker host; local private canaries
serve separate negative/control experiments. Their absence blocks the real experiment, not offline development/tests.

Scope includes a private configuration preparer, a local-on-host verifier and
versioned receipts. It excludes cloud provisioning/billing, SSH fleet management,
Publicity/GEMI requests, company capture/extraction/import, a remote desktop product,
production scheduling and search/vector services. The API remains secondary.
Ordinary Publicity navigation and its source contract follow this infrastructure
gate; a successful probe never authorizes source automation or identity decisions.

## Operator interface and configuration

Proposed interfaces below **do not exist yet**. The operator runs them on the
selected remote host; Nima does not receive an SSH key or provision a machine:

```bash
uv run --frozen python -m nima.egress.remote prepare \
  --config /PRIVATE_CONFIG/remote-worker.json --output-dir /PRIVATE_STATE/bundle
uv run --frozen python -m nima.egress.remote verify \
  --bundle-dir /PRIVATE_STATE/bundle --output-dir /PRIVATE_STATE/receipts
```

`prepare` validates a closed, versioned owner-only JSON configuration and publishes
a private no-clobber bundle. It makes no network/Docker/SSH calls and reads no API
key. Required configuration binds the operator's host label, expected gateway
public IPv4, explicit controlled-probe authorities/roles, secret-file references,
private state locations, namespace ranges, runtime image digests and resource
ceilings. Unknown/duplicate fields, non-exact types, placeholders and unsafe paths
fail before any runtime action. Configuration records declared intent, not host or
network attestation. The later implementation plan defines its exact wire schema.

Probe destinations are explicitly approved operator-controlled hosts, with at most
three HTTPS authorities on port 443. No wildcard, raw-IP URL, URL credentials,
arbitrary user URL or government target is accepted. Gateway resolution is bounded
to at most eight public IPv4 addresses per host, rejects mixed private/public
answers and pins the permitted address set for the run. A changed destination set
requires a new validated policy. Worker DNS and IPv6 cannot create bypass paths.
Do not apply test-only private-address exceptions to this profile.

`verify` requires existing pinned images, the declared host's prerequisites and
controlled endpoints. It never pulls/builds images, installs packages, migrates
SQL or activates a schedule. Missing prerequisites produce a fixed failure, without
starting a browser or falling back to a different network route. Dependency/image
acquisition and administrator host setup are separate explicit actions.
Both commands use fixed redacted `remote_` failures and 0/1/2/130 exits for
scoped success, runtime failure, invalid invocation/configuration and interruption.
Parser/driver errors never echo input values, addresses, paths or credentials.

## Runtime and evidence boundary

Keep the application/data network separate from the collection namespace. Only
the fixed allowlisting gateway has the approved external route. The unprivileged
worker has no PostgreSQL credentials, observer controls, Docker socket, host
network/PID namespace or general network path. It uses read-only code/configuration,
bounded disposable browser state, dropped capabilities, no-new-privileges, normal
TLS validation and Chromium sandboxing. Namespace-only setup may use the existing
scoped helper model; the workload cannot retain NET_ADMIN. No privileged container
or manual host-wide firewall edits/flushes are included. Docker-managed rules for
owned networks are expected and must be observed/scoped; unrelated rules survive.

Use reviewed immutable image/package/browser/policy pins. Existing fixture images
are suitable only for controlled test work; this scope does not approve them for
untrusted Publicity pages. Fixture configuration/receipts keep their current format
and false deployment/privacy flags. Implement a separate remote profile and refuse
to interpret the fixture-only runner as a deployment command.

The gateway validates authority/port and enforces the run's destination set.
Preserve any mandatory environment upstream proxy rather than bypassing it.
Never forward investigator IP headers or source credentials to probe endpoints.
The default egress is the remote host's stable public IP. Hiding that worker IP
behind an external proxy/VPN is a separate choice, with its own failure tests;
neither proxy rotation nor direct fallback belongs in this increment.

The operator supplies independent observer access to the controlled origin and
denied canary. Responses/counters must be bounded, versioned and tied to a fresh
run nonce. Observer credentials and control endpoints are unavailable to the
worker. Authenticate observer reads normally; an IP-echo page alone cannot establish
negative results. Never compare against or collect the investigator's home IP.
Observe actual gateway egress and absent forwarding headers instead.
Host-service/metadata negative tests use identified operator-controlled canaries,
with verified namespace/address ownership before probes. They must not query real
cloud metadata or unrelated private services if a rule is missing.

| Required experiment | Evidence needed on this actual host/profile |
|---|---|
| Allowed HTTPX and Chromium traffic | Observer sees expected public gateway IPv4, correct run nonce and clean headers; browser HTML/script/image/XHR/fetch routes are covered |
| Direct IPv4, removed proxy settings and bypass options | Reachable denied canary receives zero worker deliveries; independent positive control and packet-policy observations succeed |
| DNS/UDP/QUIC/STUN, host services and metadata routes | Working controls and zero forbidden deliveries; no success inferred from a timeout or send syscall alone |
| IPv6 | Disabled mode is actually configured/observed; no claim of a tested active IPv6 route |
| Gateway outage, invalid/missing authentication | Bounded failure and zero alternate-route deliveries, with measured gateway state |
| Invalid TLS and redirects outside policy | Normal certificate rejection or gateway rejection, with a reachable controlled target and no denied request delivery |
| Missing capability, deadline and interruption | Visible failure, owned cleanup evidence and no accepted successful receipt |

Bind configuration hash, actual image IDs, policy/namespace/process observations,
case outcomes and observer results to the same run. Do not stitch results from
different profiles or namespaces into one success. Reuse existing tested primitives
where their contracts fit; keep fixture-specific assumptions out of the remote
profile. A material policy-bypass experiment must fail before exact restoration.

Cleanup targets only exact run-owned resources and verifies identities/labels.
No prune, broad Compose teardown or deletion of unrelated data. An independent
supervisor must account for a controller killed before its finally block can run;
incomplete cleanup blocks a successful result. Server/power loss, kernel compromise
and a malicious host administrator are outside this measured guarantee. Browser state and temporary secrets
are private and disposed according to the recorded run outcome.

## Storage, receipts and bounds

Non-secret templates and pinned code belong in Git. Actual configuration, addresses,
secret references and bundle/receipt files stay in owner-only 0700 directories with
0600 files outside Git. Credentials use private secret files/environment injection;
they never enter canonical receipts, stdout, search databases or company evidence.
Receipt generation reuses private canonical no-clobber publication and unchanged
file reuse; readers reject symlinks, unsafe modes, changed files and conflicting
bytes. Terminal summaries contain fixed reasons, hashes/counts and bounded status.

Ceilings: 16 KiB configuration, 1 MiB prepared bundle in total, one worker/browser,
30 named cases, one attempt per case, 15 seconds per attempt and 600 seconds per
run including the final 60 reserved for cleanup. Responses are at most 1 MiB and
the canonical receipt at most 64 KiB. Preserve existing subprocess/output/container
limits; tighter configured limits win. Overflow fails without truncation or new
retry allowances. Retrying an interrupted run never upgrades its incomplete receipt.

Use a new remote-verification receipt version/scope, separate from fixture receipts
and company archives. It records operator-declared host context separately from
observed runtime/network evidence. A successful result may assert only that the
specified controlled remote boundary passed at the recorded time. Its
`scope=controlled-remote-endpoints` separates `boundary_verified` from hard-false
`publicity_egress_verified`, `company_origin_verified` and `production_ready`. It cannot claim
Publicity egress, verified company origin/identity, anonymity or production readiness.
Every required case and positive control must complete; empty/partial case sets
remain unverified. Missing host/observer evidence remains explicitly unverified; a prepared bundle
alone sets no verification flag. Same-host backups alone do not protect evidence
against host loss; deployment handoff must include a private backup/restore check.

PostgreSQL stays authoritative for existing source/work/review data; original
company captures retain their private archive. This infrastructure receipt has
its own private artifact store and does not create a GEMI observation, graph edge,
SQL migration or search/vector index.

## Existing stack, structure, style and verification

Use Python 3.12, locked HTTPX 0.28.1 and Playwright 1.65.1, Docker/Compose and the
reviewed Envoy/nftables helper approach. Select any new runtime pins in the later
implementation review. `src/nima/egress/` owns this boundary; tests remain under
`tests/`, deployment assets under `infra/`, operational evidence under
`docs/verification/`. Keep the root application CLI and current collectors unchanged.

Follow the existing closed-profile/fixed-error style in `egress.policy`:

```python
if type(configuration) is not dict or configuration != {
    "version": "source-worker-policy-v1",
    "profile": "fixtures",
}:
    raise PolicyError("policy")
```

This is existing code illustrating validation style, not the new profile schema.
Official references: [Playwright Docker/sandbox guidance](https://playwright.dev/python/docs/docker),
[proxy configuration](https://playwright.dev/python/docs/network#http-proxy) and
[Docker bridge networking](https://docs.docker.com/engine/network/drivers/bridge/).
Application proxy settings and network names alone are not proof of isolation.

Current executable quality commands, after documented prerequisites:

```bash
just check
just audit
just source-worker-check
```

Use pytest for pure configuration/receipt checks, real private filesystem/command
boundaries, and controlled Docker integration. Test missing/incorrect configuration,
secret redaction, oversized/tampered artifacts, reachable controls, actual policy
failure/restoration and process termination. Preserve all existing tests and ≥90%
combined coverage. All three exact-head hosted jobs remain required; changes to
CI/dependencies/runtime assets need their own explicit explanation and review.
Hosted fixture success must never stand in for the actual remote experiment.

## Boundaries and acceptance

- **Always:** fail closed on missing policy/observer evidence; preserve TLS/sandbox,
  source privacy, bounded work, measured outcomes and precise owned cleanup.
- **Ask first:** provision/purchase a host or proxy, change production networking or
  host settings, add dependencies/CI privileges, or enable a new source destination.
- **Never:** contact GEMI/Publicity in this increment, disable TLS/sandboxing, bypass
  a mandatory proxy, export sessions/secrets, reuse fixture receipts as remote proof,
  or claim anonymity/identity/production success from an incomplete experiment.

Technical kit acceptance requires tested configuration/receipt behavior, complete
controlled rehearsal and normal gates with honest false/unverified remote flags.
The kit may be reviewed/merged while host inputs are missing; actual remote
acceptance stays incomplete until the measured experiment on the declared worker
host and cleanup pass against working controlled endpoints. This lets development continue without
a GEMI key or premature remote success. Future Publicity activation still needs
its own tested source-access/capture contract and deployment review.

Open prerequisites: operator-owned host/access, approved probe/observer endpoints
and credentials, intended stable egress, actual runtime pins and backup destination.
There is no configured host today. Scope approval permits subsequent planning;
it neither supplies those inputs nor authorizes billing, provisioning or source
collection. The already-authorized PE2–PE3 offline work remains preserved.
