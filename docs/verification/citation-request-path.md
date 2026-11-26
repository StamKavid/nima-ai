# Citation request-path correction

Date: 2026-11-26 (Europe/Athens). Fixes an input-validation omission in merged
#225 under its already-approved [B2 contract](../specs/SPEC-citation-acceptance-readout.md#owner-decisions).
Delivered in #226 at `fcfa11d`, reviewed `935762d` reachable with the same
application changes. All three jobs passed in run 45763209671; 4,600 tests,
95.11% overall and 100% adapter/command coverage, audit and isolated-wheel
valid/relative-request proof pass. Report/output paths were checked for absolute form, but the request reader first
resolved its argument to an absolute path. A valid private request could therefore
be accepted through a relative path, contrary to the command's contract.

`export_citation_acceptance` now checks the request path with the existing path
guard before reading it, as it already does for output configuration. Valid
absolute requests, report/sidecar bytes, counters, policy, source limits and the
underlying legacy request reader are unchanged. No source, schema, dependency,
CI, grant or journal change.

Two regression cases create a real valid mode-0600 request in an owned private
directory, then invoke the library and CLI with a relative filename. Both must
reject it before reconstruction, preserve the input and create no output. The CLI
returns exit 2 and the fixed `acceptance_input` result without printing private
configuration. Both tests fail on the previous guard and pass on the correction.
Removing the new guard again rejects both cases; source bytes are restored and
SHA-256 checked.

All 137 focused citation-acceptance cases pass, with 100% adapter/command line and
branch coverage. Narrow strict types, Bandit and full-project lint pass. The full
local gate/audit and exact-head hosted jobs are recorded on the correction PR
before merge readiness; focused proof is not a replacement for those gates.

The next U1 acceptance contract is a separate draft; this correction does not approve that consumer. Private
proof stays outside Git in `/workspace/work/nima-u1-acceptance-contract-proof`.
