# Spec: buyer-concentration data-fitness readout

Module ID: `buyer-acceptance-readout` (V1-08). Status: **proposed for owner review**,
2026-11-26 (Europe/Athens). Baseline: #229 merged at `c78eb72`.
Extends [A3](SPEC-dataset-acceptance.md#owner-decisions) after citation/U1/U2
consumers. This contract covers U3 only; implementation awaits E1–E3 approval.

## Objective and assumptions

A company/market researcher can assess whether a private buyer-concentration
report supports its declared captured-record use, with explicit unresolved,
partial and ambiguous participation. Concentration concerns reported supplier
participation in captured contract publications; it is neither spending nor
market share, a verified company identity, a cartel claim or a fraud score.

Assume Python 3.12+, PostgreSQL 17, one trusted local operator, the existing
restricted reader, explicit stored runs/UTC cutoff and private original archives.
Keep the draft metric, reference SQL, policy, source parsers and old report bytes
unchanged. No dependency, schema/grant, journal, CI, source activation or release.

## Public preparation and command

`analytics.buyer_readout.prepare_buyer_readout(dsn, request)` returns only
`(body, MetricResult)`. Its existing sequence reads one bounded cohort, reconciles
originals/projections, evaluates U3 and checks SQL parity against frozen inputs.
The report omits run profiles/quarantine counts and cites a subset of observations.
Neither saved flags nor its evidence-list length can supply whole-cohort facts.

Add public `prepare_buyer_result(dsn, request)` returning frozen
`PreparedBuyerReadout(body, metric, cohort_json, observations, pages)`, exposing
the already-read facts and verified pages. Preserve the old tuple function as a
wrapper around this one sequence; existing CLI/report bytes and errors stay stable.
The sequence retains two sequential read-only connections: a repeatable-read
source cohort, then reference SQL on bound frozen JSON, without another source
snapshot. Both close before publication. Prepare exactly once per call/retry.

Proposed command, available after implementation:

```sh
uv run --frozen python -m nima dataops assess-buyer \
  --request /PRIVATE/buyer-request.json \
  --report /PRIVATE/REPORT_SHA256.json \
  --output-dir /PRIVATE/acceptance
```

Use environment-only `NIMA_DATABASE_URL`; no journal DSN or attempt ID. Decode
the existing `nima-buyer-concentration-request-v1`, including programmatic inputs:
1–10 runs, UTC cutoff, exact reported buyer selection and one archive binding per
run. All three paths must be absolute/safe before SQL. Reuse the public file guards:
owned 0700/0600 directory/file, stable regular single-link read, no symlink
traversal, lowercase SHA-256 `.json` basename. Subject bound: **1 MiB**; preserve
the current 500-observation/32-page and original-byte/cohort bounds.

Require the saved hash/name and complete body bytes to match the fresh report.
Validate producer shapes/types and request/cohort/run/page/observation/definition/
SQL/typed-result bindings before the unchanged policy. No private producer import,
new verifier, extraction path, source request or second per-buyer metric evaluation.

## Counter and evidence scopes

U3's `MetricResult.records` contains only unambiguous records matching the buyer;
`ambiguous_source_ids` covers the whole cohort at the cutoff. To measure full
coverage without changing the model, the consumer may call the existing public
`semantics.selection.select_latest(prepared.observations, cutoff)` **once**, as a
bounded pure selection pass. This reuses the same algorithm; it reads no SQL or
archive and does not recompute U3. Freeze no mutable selector mappings in output.

Let S be the frozen cohort, D the typed U3 result, C the unambiguous selections
from that pass, and B = D.records. Validate that D's ambiguous IDs match the
shared selector, that B is a distinct subset of C, and that buyer/resolution/
supplier/share counts reconcile with the typed decisions. Measure all fourteen
counters explicitly, including zeros:

| Counter | Grain | Mapping |
|---|---|---|
| `observations` | observation | `len(prepared.observations)`, all admitted observations, including after cutoff |
| `pages` | page | `len(S["pages"])`, reconciled with verified pages |
| `page_records` | reported_record | Sum of admitted page `record_count` |
| `quarantined` | quarantined_record | Sum of admitted run `quarantine_count`, never an assumed zero |
| `selected_records` | source_record | `len(C)`, whole cohort at cutoff before buyer filtering |
| `ambiguous_records` | source_record | `len(D.ambiguous_source_ids)`, whole cohort at cutoff |
| `buyer_records` | source_record | `D.buyer_records == len(B)` |
| `resolved_records` | source_record | `D.resolved_records`, B records with `resolution == "resolved"` |
| `unresolved_suppliers` | source_record | `D.unresolved_records`, B records with unknown, empty or no eligible suppliers |
| `partial_suppliers` | source_record | `len(D.partial_source_ids)`, resolved B records with ineligible occurrences |
| `joint_records` | source_record | `D.joint_records`, resolved B records with at least two distinct eligible keys |
| `supplier_participations` | participation | `D.participation_total`, distinct eligible supplier keys per resolved B record |
| `unknown_cancellations` | source_record | Number of B records with `cancelled is None`, including unresolved records |
| `cancelled_records` | source_record | Number of B records with `cancelled is True`, including unresolved records |

`buyer_records = resolved_records + unresolved_suppliers`; partial and joint
records are subsets of resolved records and can overlap. Ineligible occurrences
are not partial-record counts. Duplicate ordinals and GR/EL aliases do not multiply
one eligible supplier's participation in a record. Sum of supplier counts can
exceed resolved records; supplier-cell cancellation counts can double-count a
joint record and omit unresolved records. Count cancellation from B instead.
Select the latest revision before buyer filtering; an older matching buyer is
not retained if the latest unambiguous revision reports a different buyer.

Preserve the provider's exact integer shares: top share uses resolved records;
unresolved share uses buyer records. A zero resolved denominator has no top share;
zero buyer records has no unresolved share. Keep all tied top keys in the original
report; never choose one or round/reduce fractions to change old bytes.

The report cites all observations whose source ID is in B or D's ambiguity list.
This includes earlier/after-cutoff observations of those sources, while other
buyers and future-only sources can be absent. Validate precisely that subset's
IDs/pointers/typed facts; **do not require report evidence to equal all cohort
observations**. Original verification still covers every admitted page. Missing
buyer assertions are not attributed to the selected buyer. Global ambiguity remains
the provider's disclosed scope even when candidate versions report another buyer.

A pure-provider/policy probe used thirteen synthetic observations: eight
unambiguous records, one ambiguous source and a six-record selected buyer. For
that buyer, four were resolved/two unresolved, one partial record had two ineligible
occurrences, one joint record produced two supplier cancellation contributions,
and participation total was five. Distinct cancellations and unknown cancellations
were each one; top share was 3/4 and unresolved share 2/6. Its report evidence
subset had ten observations, versus thirteen in the cohort. Other/missing buyer
selections yielded subsets of three/two observations. An all-unresolved buyer had
no top share. Page/run/check facts were synthetic probe inputs: this is no SQL/
archive verification, implemented consumer or actual company-data acceptance.

## Policy, output and refusals

Use unchanged `nima.dataset-acceptance` 1.0.0, `use="U3"`, SHA-256
`f0a50c1b405ed1a581022641f69d7fd272da85e2d5ab6c69ac4e83c46ef9ef06`.
Metric `buyer_supplier_record_concentration.v1` remains draft, definition hash
`756f73916ccc0bcb03e2975d5c7419e137fb9004fda72a9ed0eba717c0530e11`,
SQL hash `dcc0586db13667925d2d080fbaa4bb7a9defa1282009697ccb38c9938272118c`.
Preserve hashing conventions. Unknown policy metadata fails the contract;
supported producer shapes with an unadmitted definition retain `not_assessed`.

Successful reconstruction supplies all eight required check results; comparability
is explicit `not_applicable/not_required_for_use`. Monetary eligibility remains
`not_applicable`. The pure evaluator owns the actual decision. Preserve every
provider status: `empty_capture`, `no_observations_before_cutoff`,
`observed_concentration`, `buyer_records_unresolved`, `selection_unresolved` and
`no_observed_buyer_records`. No status proves buyer/market absence or certification.

Real partial/quarantined/no-page captures fail the existing verifier with **no
sidecar**. Complete-empty still needs its archived empty page. Publish the policy's
actual `ready`, `limited`, `blocked` or `not_assessed` only after reconstruction;
do not fabricate a verified capture to obtain a negative assessment.

New private canonical sidecar `nima-buyer-acceptance-v1`, at most **64 KiB**.
Bind subject format/hash, request/cohort hashes, cutoff, source/run profiles and
metric ID/status/definition/SQL hashes. Embed full policy metadata/hash and
assessment/checks/counts/grains/limitations, explicitly declaring cohort-selection
versus buyer-diagnostic scopes. Hash-bind selection; do not copy the buyer key,
request, supplier/tax IDs, names, source IDs, rankings, shares, amounts, normalized
records or physical paths. Detailed evidence remains in the private parent report.

Reuse the existing canonical encoder, atomic no-clobber publisher, permissions,
fsync and identical-content retry. Every retry reconstructs; previous output is
never a cached pass. Inspection and publication are not one atomic transaction;
a completed artifact may survive failure and a kill may leave a private temp file.
Reuse the seven closed errors, U1/U2 error mapping and fixed terminal vocabulary.
Exit 0 for published `ready`/`limited`, 3 for published `blocked`/`not_assessed`,
2 for input, 1 for operational/evidence/contract/size/output failure, 130 for
interruption. Never echo source values or arbitrary exceptions; never repair inputs.

## Structure, style and verification

Add `src/nima/dataops/buyer_acceptance.py` and extend the existing acceptance CLI/
DataOps dispatcher. The only producer change is the additive preparation result
and compatibility wrapper in `analytics/buyer_readout.py`. Use public guards,
policy, selector and publisher; no generic registry/framework. Match frozen records:

```python
@dataclass(frozen=True)
class BuyerAcceptanceExport:
    artifact_sha256: str
    subject_sha256: str
    decision: str
    policy_sha256: str
```

After approval, use pytest (`tests/test_buyer_acceptance*.py`), native PostgreSQL
17, owned synthetic originals and restricted readers. Require hand-computed
fourteen-counter answers, other/unknown buyers, sparse citations, after-cutoff
rows, ambiguity, A→B→A/re-observation, duplicate/alias supplier keys, unknown/empty/
all-ineligible/partial/joint suppliers, cancellation in unresolved and joint
records, tied leaders, exact share denominators and genuine complete-empty.

Prove original/SQL/projection/page/membership/principal/incomplete/quarantine
refusal, one preparation/one cohort read/two read-only connections, no HTTP/source
writes, fresh retry/relocation, missing originals after prior publication and
closed SQL at publication. Cover private paths, shapes/hash/binding drift, bounds,
all decisions and process interruption before/after final link. Require 100% new
line/branch coverage, meaningful behavior mutations, unchanged 90% overall floor,
legacy report/tuple/semantic/SQL/ODCS pins and isolated built-wheel/native operation.

```sh
uv run --frozen pytest tests/test_buyer_acceptance.py
just lint
just typecheck
just security
just check
just audit
```

Front-load cheap gates, freeze source during verification and overlap independent
local/hosted gates. Require all exact-head hosted jobs before merge readiness;
do not repeat an unchanged full suite solely for documentation status. U4,
durable history, source activation, metric review and actual investigator/cohort
proof remain separate. This contract introduces no new analytical definition.

## Owner decisions

Recommendations awaiting review:

- **E1 — scope:** one U3 command/sidecar over an additive frozen preparation result;
  preserve the old tuple/report bytes, metric/SQL and policy.
- **E2 — meaning:** fourteen counters with explicit cohort/buyer scopes; reuse the
  public selector once for cohort coverage, validate sparse report evidence and
  distinct-record cancellation/partial/joint/share accounting.
- **E3 — verification/privacy:** one fresh preparation, existing two-connection
  sequence, 1 MiB report/64 KiB sidecar, hash-only buyer selection and no sidecar
  on failed reconstruction. Implement only after owner review of this contract.
