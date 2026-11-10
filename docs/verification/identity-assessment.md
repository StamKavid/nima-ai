# Offline identity assessment verification

2026-11-10. Base: merged PR #15 (`33115f0`); approved SPEC-entity-resolution.md.
Local `make check`: 256 tests, 97.51% combined Python line/branch coverage; all
identity modules reach 100%. Formatting, lint, strict types, build, skill integrity,
Bandit and Gitleaks pass. Dependency audit reports no known vulnerabilities.

Tests failed before implementation. Real PostgreSQL tests verify receipt/fact/
mention completeness, supported versions, exact evidence, selected-run isolation,
unknown/empty supplier lists and byte/row bounds. A concurrent second connection
adds/projects a page after the report snapshot starts; the report sees its original
cohort. A SQL write inside the read-only transaction is rejected by PostgreSQL.

Actual SIGKILL tests pause at either side of report publication: pre-link leaves
no final JSON, post-link leaves complete bytes, and retry is idempotent. Concurrent
publishers, symlinks, FIFO/corrupt/public files and Git internals are covered.
Review found a relative-path escape into Git internals; its test failed before
the absolute-path guard fix. Outputs are Git-ignored before report publication.
Mutation: allowing one extra occurrence made the budget test fail; original source
bytes were restored with an isolated bytecode cache.

Offline cached replay: 1,118 contracts, 2,275 occurrences, 1,201 candidate groups,
91 name-variation groups, 12 buyer-key tax-variation groups and 17 unkeyed occurrences.
The 2,140,453-byte report replayed identically, with zero automatic identity links.
Original archive hashes stayed equal; disposable database/replay artifacts were removed.

Five-axis review covers snapshot/budget correctness, explicit typed policy and
namespace boundaries, separated SQL/policy/publication, parameterized SQL and private
no-follow directory descriptors, and grouped membership without pairwise expansion.
No registry calls, schemas, dependencies or CI controls changed. Groups are not
companies; format is not verification. Archive freshness/integrity, empirical match
accuracy, production scale and storage/server crash recovery remain unproven.
Private orphan temporary files can remain after SIGKILL. Hosted head checks are
recorded in the delivery PR; merging/deployment remain human decisions.
