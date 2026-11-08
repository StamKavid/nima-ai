# Bounded KIMDIS collector verification

Date: 2026-11-08. Scope: page validation, private response archival, bounded HTTP
collection, and a CLI. The accepted ingestion spec also requires database history,
durable handoff, and crash recovery; those are not implemented in this slice.

## Behavioral checks

Tests failed before the page API, archive, collector, and command existed. The
current suite has 134 passing tests, including real local filesystem operations
and HTTPX MockTransport through the full collection/normalization/archive path.
Cases include pagination/count changes, empty windows, unknown/malformed rows,
exact money, duplicate/missing IDs, corrupt reused blobs, unsafe paths, atomic
manifest failures, bounded streaming, time/rate/retry limits, HTTP-date backoff,
429s, 5xxs, permanent errors, redirects, and interruption. These are not live
source mocks standing in for crash-recovery experiments.

A targeted mutation disabled the identity-coverage guard; the duplicate-ID test
failed because the mutated run claimed completeness. The original source was
restored byte-for-byte. An isolated bytecode-cache prefix avoided stale imports.

Local formatting, lint, strict types, package build, Bandit, Gitleaks, skill
integrity, coverage, and locked-dependency audit passed. The 90% combined
line/branch coverage floor remains unchanged; measured full-stack coverage is
97.94%. Each dependent branch was checked locally in a separate worktree:
page/archive: 84 tests, 97.23%; HTTP collection: 126 tests, 98.04%.

## Live source evidence

A one-page run for 2026-11-06 archived and normalized all 50 returned records,
then stopped with `page_limit`, exit 1, and both completeness flags false. The
source reported 1,118 records over 23 pages.

A bounded full-window attempt normalized 1,050 records from 21 pages before the
source returned 429 twice. Both error bodies were archived before status handling;
the run ended with `retry_exhausted` and false completeness. No source records or
identifiers were added to Git. This exposed rate limiting below the documented
350 requests/minute ceiling. The default was reduced from 60 to 20 requests/minute,
and missing `Retry-After` on 429 now receives a 30-second initial backoff.

The follow-up run completed all 23 pages and all 1,118 reported records, using
24 attempts. It encountered one 429, waited 30 seconds, then recovered. Both
completeness flags were true; no duplicates, missing IDs, or quarantined rows were
observed. Every normalized record resolved to an archived body. This is one
bounded daily sample, not proof of full-source availability or snapshot consistency.
Live source behavior is not a substitute for offline checks.

## Review and limits

Review covered correctness, readable boundaries, source validation, privacy,
resource bounds, and traceability. Identity encoding is requested and enforced to
avoid unbounded decompressor allocation. Error receipts omit cookies and preserve
only whitelisted response headers. Console summaries omit titles/tax identifiers.

Bodies are immutable SHA-256 objects; atomic/fsynced manifests record attempts.
These guarantees assume a single trusted local owner, not hostile concurrent
filesystem writers. A killed process can leave a running manifest or incomplete
derived artifacts; no resume command is exposed. Offset-page reconciliation does
not prove an unchanged source snapshot. Run time is a cooperative I/O budget,
not an OS-enforced hard deadline. Branch administration controls remain a separate
open task because the GitHub integration lacks that permission.

## Hosted verification and delivery

Repository visibility and authenticated user were verified as private and
`StamKavid` before push. GitHub resolves new author/committer attribution to
`StamKavid`. Delivery is split into dependent, unmerged draft PRs:

1. [#7: page/archive](https://github.com/StamKavid/nima-ai/pull/7) → `main`.
2. [#8: HTTP collection](https://github.com/StamKavid/nima-ai/pull/8) → #7's branch.
3. [#9: CLI/docs](https://github.com/StamKavid/nima-ai/pull/9) → #8's branch.

Retarget each dependent PR to main after its predecessor merges. Review/merge
authorization remains with the user. No deployment is part of these changes.

The following hosted quality runs passed at the reviewed code boundaries:

- #7 PR run: https://github.com/StamKavid/nima-ai/actions/runs/42520907137
- #7 push (`da7517b`): https://github.com/StamKavid/nima-ai/actions/runs/42520862857
- #8 push (`7bccf2e`): https://github.com/StamKavid/nima-ai/actions/runs/42520862835
- #9 push (`722d8a8`): https://github.com/StamKavid/nima-ai/actions/runs/42520862805

The existing CI's pull-request trigger targets main, so #8/#9 have push checks
until retargeted. Their branches contain the complete dependency chain. CI gates
were not changed; further documentation commits receive fresh push checks.
