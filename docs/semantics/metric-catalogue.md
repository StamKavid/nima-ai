# Metric catalogue

The metrics of the [V1-05 semantic model](../specs/SPEC-semantic-model.md), one per acceptance scenario of
the [v1.0 release contract](../specs/SPEC-release-v1.0.md), with the hashes that bind each definition. The
table below is checked against the code by a test (`tests/test_metric_catalogue.py`): a changed rule, a
changed reference SQL or a changed status makes the test fail until this page is updated deliberately.

## Status meanings

| Status | Meaning | Who decides |
|---|---|---|
| `draft` | Defined, tested against hand-calculated examples, not reviewed | the maintainer |
| `reviewed` | The owner has reviewed the definition against its hand-calculated tests; recorded below | the owner |
| `certified` | A real-data reconciliation and sign-off are recorded | the owner |

A status never moves because tests pass. `reviewed` needs a dated **Review record** line for the metric on
this page, and `certified` needs `docs/verification/reconciliation-<metric id>.md`; the catalogue test refuses
a promotion that leaves neither. A change in behaviour needs a new metric version, so an artifact that names a
definition hash always keeps its meaning. Changing a status changes the definition hash by design.

## The metrics

| Scenario | Metric | Status | Definition hash | Reference SQL hash |
|---|---|---|---|---|
| U1 | `captured_contract_record_count.v1` | draft | `7d8b5f8ecf6ae366482f4b06cd245f16d23408b489ad9bcb44af493282ac043f` | `85134c5d800350adfedf7dce6d995a36c48b194d919912695992f83369e11d5f` |
| U2 | `captured_record_count_by_cpv_period.v1` | draft | `577d91161d92e5a954d773427762fc4d7060b537a0300f4f54ecdac0002f132d` | `7d9e7cb716e4184daf3601df7bd75a8064a8fe9a984880f73126cc5a714218e0` |
| U3 | `buyer_supplier_record_concentration.v1` | draft | `756f73916ccc0bcb03e2975d5c7419e137fb9004fda72a9ed0eba717c0530e11` | `dcc0586db13667925d2d080fbaa4bb7a9defa1282009697ccb38c9938272118c` |
| U4 | `observed_change_between_captures.v1` | draft | `5ef663ebc1c297e9db184a5cfbf87afd2ea4c1231e1b2feb378cd082157cd2de` | `76cf61bd7285eea0c4834cb1439cd5a42c62903f80c7cff9e3f8017d481f259d` |

All four read the same selection of captured records (the latest observed version of each source record, ties
excluded and listed), count captured records only, never money, and make no identity, market-share or
misconduct claim.

## What each one answers

| Scenario | Question | Grain | Definition |
|---|---|---|---|
| U1 | Which buyers repeatedly appear with this reported supplier? | distinct records per supplier key and buyer key | [participation](participation.md) |
| U2 | What procurement activity is captured for this CPV code and month? | distinct records per CPV base code and reported month | [cpv-period](cpv-period.md) |
| U3 | How concentrated is a buyer's captured supplier participation? | record-participation counts per supplier, with an unresolved share | [buyer-concentration](buyer-concentration.md) |
| U4 | What changed between two captures of the same query? | per source record: added, changed, missing, unchanged; abstains otherwise | [observed-change](observed-change.md) |

## Evidence available for review

| Metric | Hand-calculated example | Pure and SQL parity | Other proof |
|---|---|---|---|
| U1 | the synthetic fixture (eight source IDs, eleven observations: B1=3, B2=1, unassigned=1, total 5) | `tests/test_semantics.py` on PostgreSQL | nine characterisation pins that held across the S3 refactor (`tests/test_semantic_pins.py`); a bounded readout command exists |
| U2 | the spec example (March: A=2, B=1, unclassified=1; unknown period B=1) | `tests/test_cpv_period.py` | 57 tests, 100% line and branch, 52 rule breaks caught; a bounded readout command exists (`nima analytics cpv-period`, 39 tests, 100% line and branch on the new modules, 15 of 15 rule breaks caught) |
| U3 | the spec example (buyer B1: S1=2, S2=2, overlap 4, one joint record, share 2/3, unresolved 2/5) | `tests/test_buyer_concentration.py` | 34 tests, 100% line and branch, 50 rule breaks caught; a bounded readout command exists (`nima analytics buyer-concentration`, 32 tests plus shared request tests, 100% line and branch on the new modules, 22 of 22 rule breaks caught) |
| U4 | the spec example (X unchanged, Y changed, Z missing, W added; incomparable when incomplete) | `tests/test_observed_change.py` | 44 tests, 100% line and branch, 54 rule breaks caught; a bounded readout command exists (`nima analytics observed-change`, 100% line and branch on the new modules, 20 of 20 rule breaks caught after fixes) |

These establish that each definition does what it says on synthetic inputs. They establish nothing about
publisher truth, national coverage or usefulness to an analyst.

## Review checklist (for promotion to `reviewed`)

For each metric the owner confirms, and records with a date:

1. The question and grain above are the ones wanted.
2. The definition document's rules say what the metric should do, including what it excludes and discloses.
3. The hand-calculated example is the right example and the tests reproduce it.
4. The unknown and unresolved buckets are shown, and no unknown is turned into a zero.
5. The metric makes no monetary, identity, market-share or misconduct claim.
6. The version name is acceptable; later behaviour changes will use a new one.

The record is one line per metric, added by the same change that moves the status:

`Review record: <metric id>: reviewed by <owner> on <date>; checklist items 1 to 6 confirmed.`

No review record exists yet.

## Plan for certification (real-data reconciliation)

`certified` needs a recorded reconciliation on real data. It cannot be done from synthetic tests and is the
owner's check. The plan, in order:

1. **Prerequisites.** The readout commands for U1 to U4 and U4's completeness rule are built. A real capture
   whose **original archive is preserved** (mount an output folder and copy the archive out); the archives of
   runs 2 to 5 of the local sample were lost with their temporary containers.
2. **Choose the cohort** (for example one buyer over a bounded window, or the whole-day capture) and record
   the exact request, run IDs, cutoff and each metric's definition hash.
3. **Run the metric** through its readout and keep the result file private.
4. **Reproduce independently.** For a stratified sample of records (at least the extremes: a joint record, an
   unclassified record, an unknown date, a revised record), the owner reads the original source records and
   works out each metric's cell by hand, without the tool.
5. **Reconcile exactly.** Every hand result must equal the tool's. Any difference is a finding that blocks
   certification until it is explained and fixed under a new version if the rule changes.
6. **Record it** in `docs/verification/reconciliation-<metric id>.md`: request, hashes, sample, hand results,
   outcome and the owner's sign-off, with no source values, names or tax numbers. Only then does the status
   change, in its own change.

U4 additionally needs two captures of the same query taken at different times, with the second complete; the
five records that really changed between the two local captures are the first evidence for it, not yet a
reconciliation.
