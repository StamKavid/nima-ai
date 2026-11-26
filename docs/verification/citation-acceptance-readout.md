# Citation-acceptance readout checkpoint

Date: 2026-11-26 (Europe/Athens). B1–B3 were approved after the
[contract](../specs/SPEC-citation-acceptance-readout.md) in #224. That PR is merged
at `39519c2`; its documentation head `c4343d3` is reachable with an identical tree
and all three main CI jobs passed in run 45714441006. The implementation is
delivered in [#225](https://github.com/StamKavid/nima-ai/pull/225), main `e6c869d`,
with reviewed `fd35041` reachable and an identical tree. All three exact-head PR
jobs passed in [run 45719893571](https://github.com/StamKavid/nima-ai/actions/runs/45719893571).

## Boundary and focused proof

`dataops assess-citations` reads one private hash-named report, reconstructs it
once through `prepare_citation_readout`, requires exact byte equality, assembles
fourteen explicit measured counters and invokes the unchanged pure policy.
A separate bounded sidecar carries the binding, policy definition and assessment.
No journal, source acquisition, schema, dependency, CI or legacy artifact change.

Policy: `nima.dataset-acceptance` 1.0.0, SHA-256
`f0a50c1b405ed1a581022641f69d7fd272da85e2d5ab6c69ac4e83c46ef9ef06`.
The current citation definition/SQL pins remain unchanged. Model-definition
hashing retains the producer's encoding convention, distinct from policy hashing.

Focused tests: **135 passed**. The adapter and command have **100% line/branch
coverage**, 269 statements and 92 branches combined. Native PostgreSQL 17 tests
use owned synthetic captures, actual original bytes and a restricted reader.
They exercise complete/empty/partial/quarantined/no-page captures, both sources
without pages, actual publication/CLI, exact connection count on retry/relocation,
missing originals after an earlier successful sidecar, corrupted normalized facts,
omitted observations, page disagreements and refused owner credentials.
SQL table hashes and source/request/report bytes and metadata are preserved.
HTTP is forbidden on success and failure paths.

Hand-computed mapping cases cover shared revoked targets at edge grain,
re-observation without repeated cancellation, source and target ties, A→B→A,
unknown versus empty reference lists, evidence after cutoff, missing/mismatched
kinds and pending revocation. Every required outcome is explicit. Strict producer
shape/binding/type checks, report modes/hash/symlink/hardlink/size checks,
policy drift and returned-assessment vocabulary failures are exercised.
Negative policy decisions are tested separately with controlled verified-producer
frames; those tests do not claim a damaged real cohort passed reconstruction.

Four real process cases send SIGKILL or SIGINT before/after the final publication
link. There is no source SQL session at that boundary. Retry through the normal
CLI reconstructs and produces the same bytes; a previously completed result's
mtime is preserved, and no source rows or evidence change. A SIGKILL may leave a
private temporary file, never an extra completed assessment.

## Delivery verification

Early full-project lint, strict mypy (394 files), Bandit and Gitleaks pass.
All **22 targeted mutations are rejected**, covering all fourteen counters,
completeness, report hashing/byte equality, single-snapshot behavior, publication,
returned bindings and sidecar bounds. The adapter is restored byte-for-byte with
SHA-256 checked. The final local `just check` passes **4,598 tests** with
**95.12%** overall combined line/branch coverage and the unchanged 90% floor.
One pre-existing Prefect home-directory warning remains. Source/wheel builds,
Bandit, Gitleaks and `just audit` pass; all three existing ODCS contracts are
unchanged. The full suite retains 100% coverage for both new modules.

The final built wheel was loaded through Python isolated mode from a private
working directory, with source bytes checked against the archive. Its normal
CLI reconstructed actual PostgreSQL 17/original fixture evidence using a restricted
reader and returned `ready` with all fourteen counters. No checkout module or
stubbed verifier supplied that packaged result; source table hashes are unchanged.

Hosted quality, orchestration-compose and source-worker-egress passed on
`fd35041db457b648346b6f4ef450d3378b74d5a3` in run 45719893571; hosted quality
also reports 4,598 tests passed. Reachability and tree comparison confirm main
contains the reviewed content. The subsequent absolute-request-path correction
is isolated in #226; no real-cohort acceptance follows from either proof.

Private logs and owned test resources stay outside Git under
`/workspace/work/nima-citation-acceptance-proof`; that workspace path is a local
proof location, not an input or portable evidence identity.

## Limits and next work

This proves the bounded software path against synthetic originals. It does not
reconcile the owner's unavailable four-positive originals, establish market
coverage, certify a draft model, approve numeric analytics or complete V1-08.
Next contracts concern U1–U4 verified consumers and durable acceptance history;
real-cohort reconciliation remains open. [Operator command](../runbooks/citation-acceptance.md).
