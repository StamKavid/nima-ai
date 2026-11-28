# Spec: captured buyer participation insight

Status: **I1–I3 approved by the owner on 2026-11-28**. Module:
`buyer-participation-insight`; first bounded V1-09 / R6 contract. #240 is merged
at `15ae224`, with the identical reviewed `55e4c32` tree. The
[implementation plan](../../tasks/plan.md) was approved by the owner's instruction
to begin implementation on 2026-11-28. BI1–BI4 are delivered in #242 at `0c03404`,
with the identical reviewed `6bb7e14` tree;
[verification](../verification/buyer-participation-insight.md) records actual
proof and remaining gates. Approval does not certify a metric, activate a source
or authorize a release. All three exact-head jobs and downloaded reports passed;
human metric certification remains separate.

## Objective and assumptions

Answer one question for a company/market researcher: **for this reported buyer in
the selected KIMDIS captures, which reported supplier groups have the largest
captured publication participation, and what limits that answer?**

Approved choices: CLI/private export first; reuse U3 unchanged;
fixed descriptive wording; a numerical insight requires a certified metric and
ready per-use data. Existing draft readouts remain available in their own right.
One record is a contract publication, not a unique procurement, award, payment or
company. This slice defines no comparison period, trend, peer group, threshold,
HHI, market-share estimate, money allocation or competition/fraud judgement.

Dependencies: [U3 semantics](../semantics/buyer-concentration.md),
[verified readout](SPEC-metric-readouts.md),
[U3 acceptance consumer](SPEC-buyer-acceptance-readout.md),
[metric catalogue](../semantics/metric-catalogue.md), and
[release contract R6](SPEC-release-v1.0.md). PostgreSQL and private originals
remain authoritative; no new framework, model, graph store or dependency.

## Eligibility and result states

Use `buyer_supplier_record_concentration.v1` and the fresh U3 assessment. Data
fitness and metric certification are separate gates. Apply this precedence:

| State | Conditions | Result |
|---|---|---|
| `insufficient_evidence` | A genuinely returned assessment is limited, blocked or not assessed; or the provider is not `observed_concentration`, or has no resolved denominator | `answer: null`; retain every applicable reason |
| `review_required` | Otherwise eligible ready data, but the admitted metric definition is draft or reviewed | `answer: null`; `metric_not_certified` |
| `answered` | Ready assessment, observed provider result with positive denominator, certified definition and explicitly compatible acceptance profile | Cited exact result and interpretation limits |

Reasons are deterministic, sorted and deduplicated. Preserve original assessment
and provider statuses/reasons, including non-certification alongside insufficient
data. Unknown/unsupported artifact or definition versions, missing/tampered bytes,
SQL/access failures and input-limit violations are operational errors: no new
artifact. Preserve the provider's own refusal when it cannot produce an assessment
(for example an incomplete managed run); do not manufacture one to fit this table.

**Current dependency:** all four metrics are draft. Dataset acceptance 1.0.0 pins
their current definition hashes. Changing review status changes the definition
hash. Consequently no current real cohort qualifies for `answered`, including the
16-record ready U3 pilot. Metric certification needs human review and separately
reviewed acceptance-profile/version compatibility; this spec neither chooses the
new version nor edits historical definitions or reports. A certified definition
with an unsupported profile fails closed. No flag can bypass either gate.

## Data path and scope

The insight prepares the existing public `prepare_buyer_acceptance(dsn, request,
report_path)` once. That consumer freshly verifies the parent readout, originals,
cohort and reference-SQL parity through the existing two read-only connections.
Use public safe `read_subject` for the parent bytes and require their digest to
equal the freshly prepared subject digest. Retain byte/hash bindings if a file
changes between reads. No extra cohort query, metric evaluation, SQL selection,
private-function import, source HTTP call or database write is introduced.

Reuse the existing `BuyerRequest`, its explicit run selection and observation
cutoff. The parent has no source-query-window block: never infer a continuous
date range from capture timestamps or fetch it through extra SQL. Preserve the
existing snapshot/revision selection and cancellation rules unchanged. Capture
time is not a source-effective event or a guarantee of current freshness.

Inherit the readout bounds: at most 10 runs, 32 pages, 500 observations, 8 MiB
snapshot input; parent report at most 1 MiB, fresh acceptance sidecar at most
64 KiB. These are not the larger pure-metric or citation-reader bounds.

## Output contract

Definition ID: `captured_buyer_participation_summary.v1`; artifact
version: `nima-buyer-participation-insight-v1`. One canonical JSON artifact:

| Field | Required meaning |
|---|---|
| `definition` | Insight ID/version, fixed template/rules and canonical definition hash |
| `subject` | Parent readout, request, cohort, metric definition, metric SQL, acceptance policy and embedded data-fitness hashes; observation cutoff |
| `data_fitness` | Full freshly prepared acceptance sidecar as a JSON object; canonical encoding must reproduce its original bytes and hash |
| `status`, `reason_codes` | States and precedence above; fixed codes, no source-derived exception text |
| `scope` | Source `kimdis.contract`, stage `contract_publication`, parent buyer and run-selection pointers, cutoff, comparison `not_applicable` |
| `answer` | Null on refusal; otherwise fixed statement template with exact integer/rational arguments, all top groups and evidence pointers |
| `interpretation_limits` | Capture/sample scope, reported-key identity limits, overlap, cancellation and freshness limitations inherited from both parents |

The parent report remains a separately retained content-named artifact. Do not
copy company names, tax numbers or untrusted source text into the insight: point
to supplier rows in that private parent. This adds no new entity identifier.

For `answered`, copy U3's exact `top_record_count / resolved_records`, every tied
top group in existing supplier-row order, `unresolved_records / buyer_records`,
`joint_records` and `participation_total`. Never use participation total as the
denominator or sum overlapping supplier counts into a record total. A sample of
one can be described with its explicit denominator; it cannot support a general
claim that a supplier is dominant. Keep cancellation context; do not silently
filter cancelled or unknown-status publications.

Each numerator points to the contributing selected `metric.result.records` and
supplier rows. Cite the denominator's resolved records too. Resolve their selected
observation IDs to the parent's evidence entries, which bind source version, raw
body hash and JSON pointer. Never use an older, after-cutoff or wrong-buyer
observation as the witness. Unresolved and joint-record context remains navigable.

Fixed English wording uses only validated numeric arguments and parent references,
for example: “Largest captured participation is 2 of 3 resolved buyer records;
2 groups tie. There are 0 unresolved records of 3; 1 joint record creates
overlapping participation.” No model-generated narrative or source-text template.

Publish through the existing private, fsynced, atomic no-clobber file primitive:
0700 directory, 0600 file, SHA-256 filename. Same inputs reproduce identical bytes
and retry preserves the existing file/mtime. No wall-clock generation time in
identity. Output is at most 1 MiB, including embedded assessment; fail rather than
truncate ties, evidence or limitations. No new multi-file transaction/history
framework. A later verification failure creates no new success artifact even if
an older artifact remains on disk.

## Commands and structure

The implementation provides this command. `NIMA_DATABASE_URL` supplies the restricted
reader configuration through the environment, never a credential argument:

```sh
uv run --frozen python -m nima insights buyer-participation \
  --request /PRIVATE/buyer-request.json \
  --report /PRIVATE/READOUT_SHA256.json \
  --output-dir /PRIVATE/insights
```

Exits: 0 answered; 3 review-required/insufficient; 2 invalid input;
1 operational failure; 130 interruption. Stdout follows existing machine-readable
export conventions; refusal exports are clearly labelled, with no headline rank.
No `--force`, `--allow-draft`, cached-acceptance input or generated SQL.

Small surface: `src/nima/insights/buyer_participation.py` owns composition;
a thin CLI adapter registers the command. Focused tests live under `tests/`;
the user-facing contract stays here. No generic insight engine or metric registry
replacement. Use Python 3.12+, existing frozen dataclasses, strict typing and Ruff:

```python
@dataclass(frozen=True)
class InsightExport:
    artifact_sha256: str
    status: Literal["answered", "review_required", "insufficient_evidence"]
```

## Validation and success criteria

Future implementation must satisfy these known answers and integrity checks:

- Fictional A→S1, B→S2, C→S1+S2: three resolved records, four overlapping
  participations, one joint record, two tied leaders at exactly 2/3 each. Ready
  draft metadata yields `review_required`; only an explicitly admitted certified
  profile yields `answered`. Add unknown-supplier D: unresolved 1/4, preserve the
  assessment's limitation and return no answer.
- Empty, unknown/all-ineligible, ambiguous-revision, cancellation and cutoff cases
  preserve existing provider decisions; partial/incomplete input preserves actual
  consumer refusal. No new revision-selection or cancellation algorithm.
- Ready real 16-record evidence remains review-required while draft; the earlier
  77-record limited cohort remains insufficient. Their preserved readout bytes
  and metrics do not change. These are software checks, not analyst certification.
- Verify every numerator/denominator witness, including sparse parent evidence;
  forged metric status, mismatched hashes/profile, missing original, unsafe path,
  denied SQL and output overflow produce no new artifact. Prove no source network
  request or DB write and no additional read-cohort/SQL-verification invocation.
- Retry/interruption/relocated-archive checks use existing publication guarantees;
  removing an original after an earlier success cannot reuse a cached pass.

Use pytest hand-labelled unit cases and owned PostgreSQL 17 restricted-role
integration fixtures. Require 100% genuinely new line/branch coverage, meaningful
gate/witness mutations, existing ≥90% overall floor, unchanged historical bytes,
`just check`, `just audit`, and all three exact-head hosted jobs. Commands for the
future implementation: `just lint`, `just typecheck`, `just test`, `just build`,
`just security`, `just check`, `just audit`. No new tests are necessary for this
documentation-only proposal.

Success is one reproducible cited description or an honest no-answer outcome,
with unchanged U3 arithmetic and acceptance semantics. It is not R6 completion:
the other three insight families, human certification, positive two-source proof,
observed analyst tasks, operations and release gates remain open.

## Boundaries and owner decisions

- **Always:** verify current evidence, preserve originals/exact arithmetic, expose
  scope and every refusal reason; follow existing attribution and PR delivery.
- **Ask before expanding scope:** new dependencies, schema/CI changes, threshold
  or metric changes, source requests, metric certification or policy promotion.
- **Never:** promote draft definitions by implication, accept stale verification,
  infer legal identity or misconduct, allocate joint value, commit private data,
  deploy/merge automatically or weaken quality gates.

Review decisions: **I1** approve this single U3 question and descriptive wording;
**I2** approve state precedence and the certified-metric/compatible-profile gate;
**I3** approve CLI-first single-artifact composition and inherited bounds.
The owner approved I1–I3 as written on 2026-11-28. Certification evidence and the
future compatible policy version must be reviewed separately; neither is supplied
by accepting this design. The implementation is owner-merged; metric promotion
is not implied by that merge.
