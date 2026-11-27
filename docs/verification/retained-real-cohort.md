# Retained real-cohort validation — 2026-11-27

**Verdict:** the existing KIMDIS readouts reproduce preserved real evidence and
return appropriately scoped data-fitness decisions. Commercial-company SQL
acceptance, positive two-source reconciliation and release acceptance remain open.
No application code, metric definition, source query, dependency or CI changed.

Baseline: main `65887b9` after owner-merged #235; its reviewed `ff2ea60` tree is
identical. This is automated builder-agent verification, not independent human
review, analyst usefulness or certification. The data is historical captured
evidence, not a current-source refresh.

Follow-up: #236 was owner-merged at `57ffdf9`, identical reviewed `3733d76` tree.
The separately approved [supported buyer/day capture](metlen-buyer-day-capture.md)
subsequently established a narrow company-key SQL path. The unexecuted proposal
and commercial SQL boundary below describe this earlier checkpoint.

## Preserved metric cohort

Verified all 40 integrity-listed files in the existing private evidence pack.
Restored its trusted SQL dump into a newly created owned PostgreSQL 17 database,
explicitly migrated that copy to schema 15, relocated request bindings and ran
the existing four readouts under the `analytics-reader` profile. Original input
bytes/mtimes and older SQL rows survived unchanged. All four reports reproduced
their earlier bytes, and repeat publication preserved their hashes/mtimes.

The four existing acceptance consumers then produced:

| Use | Fitness | Observed evidence and interpretation |
|---|---|---|
| U1 supplier/buyer participation | limited | Nine selected publications and one buyer within the 77-record buyer/day cohort; two supplier occurrences fall outside the Greek identifier profile |
| U2 reported CPV/month | ready | 74 cells, 90 memberships, 77 publications; all reported submission periods parse and all records have reported CPV coverage |
| U3 buyer participation concentration | limited | 75 resolved and two unresolved publications; 57 supplier keys, five joint records and 80 participations; top share 9/75, unresolved share 2/77 |
| U4 observed change | blocked | Different queries and incomplete capture; numeric-change validation is unavailable |

An independent script importing no Nima code checked all 77 records with **770
original field comparisons**, exact Decimal values, supplier/source membership,
CPV/month cells and rational denominators. It found **zero unexplained
discrepancies**. The two excluded identifier occurrences concern US suppliers;
they are outside the selected Greek-key format, not proven source errors or fraud.
Counting overlapping CPV cells or joint participations as distinct contracts would
overstate the evidence. The one-buyer selection does not establish market share.

Readouts and acceptance did not change any SQL table. A separate execution of
the existing U1 validation journal recorded a real `passed` check, reused the
same attempt and allowed SELECT-only inspection. Only its two legacy journal
rows were added in the disposable copy; source and processing tables stayed exact.
That legacy pass means byte equivalence; U1's per-use fitness remains limited.
The new citation-history slice has no real positive two-source proof here.

`ready` concerns this declared CPV/month use only. All four metric definitions
remain draft. The prior human worksheets and task observations remain unfilled.

## Separate commercial-company case: METLEN

The retained one-page METLEN capture contains nine publication IDs. Its raw hash,
complete pagination and selected reported-tax-filter membership pass. All nine
records normalize field for field identically under current code and the preserved
historical normalization. Raw-to-normalized amounts remain exact; all nine net/
gross amounts and currencies are present, and four source update dates are absent.

It reports **six buyer keys and six award references**; one award reference occurs
in **four publications**. This is evidence for preserving the distinction between
publication activity and economic transactions. It does not justify a revenue or
paid-spending total. Reported CPV values describe captured procurement, not an
exhaustive company-sector classification; legal identity remains unverified.

Two concrete boundaries prevent a broader acceptance claim:

- The retained query uses `vatNumber`, which current
  `KimdisAdapter.from_payload` does not admit. Its query was preserved; no SQL
  capture, altered scope or new source observations were invented. This check
  proves current normalization of archived bytes, not SQL-backed metric fitness.
- None of the nine records reports a Diavgeia citation. They cannot supply a
  positive cross-source example by adding guessed links.

A bounded manifest scan under the shared workspace inspected 65 manifests,
including 30 capture manifests and no Diavgeia capture manifest. Code environments,
caches and PostgreSQL storage were excluded. Backup copies are not additional
observations. This is not a search of other machines or unrelated personal files.
A loose single-decision probe was also found; it is not a selected source pair
in the restored cohort and was not used as a substitute. Earlier documented
Diavgeia pilots are historical evidence; their original positive source pair is
unavailable for this checkpoint.

## Next concrete action

A private proposal selects one supported buyer/day from METLEN's largest repeated
award-reference group. It is a declared convenience selection, not a representative
sample. Existing collection can express it without a new library or source adapter.
Proposed ceiling: **two pages, one attempt per page, at most two HTTP requests,
120 seconds**, with no automatic budget increase or retry extension.

The proposal requires an explicitly approved protected capture route and a persistent
private archive. It has not been executed. The worker command omits `--database`
and receives no application credentials. Later isolated offline reconstruction
must preserve actual observation times and disclose reconstruction times. The old
pilot's consumed request allowance does not authorize another capture.

Positive citation pairs, a complete same-query change pair, missing real-case
coverage, human metric review, consenting analyst tasks and current freshness
remain separate gates. Builder familiarity and already exposed answers must be
disclosed during later task observation; no speedup has been measured.

Private proof and the exact proposal stay outside Git at
`/workspace/work/nima-real-cohort-20261127-proof`, including
`VERDICT.private.md`, current reports/acceptance sidecars, the independent checker,
input inventory, source index and reproduction records. Owned scratch databases
and roles were removed, and the owned validation PostgreSQL instance was stopped.
