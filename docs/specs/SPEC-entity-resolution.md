# Spec: evidence-backed party identity

Module: `entity-resolution` in CAPABILITIES.md. Depends on `source-ingestion`.
Status: **approved**, 2026-11-10, by user merge of PR #15 (`33115f0`) and continuation.
Base: PR #14 merged at `d6c8e53`. First-release implementation follows tasks/plan.md.

## Objective and assumptions

Help journalists, investigators and researchers identify which reported parties
may refer to the same real entity, explain the supporting and conflicting evidence,
and correct a decision without changing source history. A mistaken merge can
invent a company connection, so unresolved cases must remain usable and explicit.

Assume the next release is a local, offline assessment of one collected run, using
existing PostgreSQL projections. It creates review candidates, not verified company
nodes. Registry enrichment, a review-decision ledger, probabilistic matching and a
graph store are subsequent increments with their own acceptance gates. This spec
does not authorize new external accounts, credentials or paid services.

## Evidence informing the policy

Official sources checked on 2026-11-10:

- [OECD Greece TIN sheet](https://www.oecd.org/content/dam/oecd/en/topics/policy-issue-focus/aeoi/greece-tin.pdf):
  a Greek TIN has nine digits and can identify a natural person, legal person or
  legal entity. The sheet is historical; its old online-checker statement is not
  used as a current access contract. Nine digits do not establish legal form.
- [KIMDIS documentation](https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help):
  supplier tax numbers, country fields and public-buyer keys are source assertions.
  Neither source country nor a Greek procurement record establishes the issuing
  jurisdiction of every reported identifier. Preserve these claims separately.
- [EU VAT identifiers](https://taxation-customs.ec.europa.eu/taxation/vat/vat-directive/vat-identification-numbers_en):
  identifier formats vary by country. Foreign identifiers need separate policies.
- [VIES scope](https://europa.eu/youreurope/business/finance-and-tax/vat/check-vat-number-vies/index_en.htm):
  an invalid result can mean intra-EU activation is missing or registration is
  unfinished; it is not proof that a business is fictitious or evading tax.
- [AADE registry access](https://www.aade.gr/en/research-business-registry-basic-details):
  TAXISnet registration and special credentials are required for that service.
- [GEMI API](https://opendata.businessportal.gr/techdocs/) and
  [license](https://opendata.businessportal.gr/license/): production access requires
  a personal API key; the documentation's limited test key is not a production
  substitute. The published license is ODC-BY-1.0. A future connector must retain
  original responses, retrieval times, attribution and source-specific coverage.

Offline inspection of the existing 2026-11-06 cache found 1,118 contracts and
1,157 supplier mentions: 1,140 reported GR/EL country values and 17 other countries.
There were 835 distinct literal country/tax-number pairs, of which 91 had varying
name values. These are descriptive counts before assessment, not company counts,
verified matches, or matching-accuracy measurements. No names/identifiers were
exported during this inspection and the source archive was not modified.

## First release: identifier assessment and review candidates

### Input and cohort

Select one run UUID and an explicit participation projection version. Read only
that run's observations, versioned contract facts, party occurrences and receipts
in one consistent database snapshot. Validate schema/version compatibility first.
Every accepted observation must have its requested projection receipt; otherwise
fail with `projection_incomplete`, rather than treating unprojected parties as absent.

Retain reported run state, page/observation/quarantine counts and unknown/empty
supplier-list counts. Incomplete or unmanaged collection may be assessed, but its
coverage limitations must accompany the report. A completed assessment does not
certify collection completeness, source freshness or archive-byte integrity.

### Comparison policy v1

| Input | Treatment |
|---|---|
| Original name, tax number, country and buyer key | Preserve exact values; separate derived comparison fields |
| Surrounding ASCII space/tab/CR/LF | Remove only in comparison fields; retain original text |
| Nine ASCII digits | Label `nine_ascii_digits`; preserve leading zeros; checksum and authority status remain `not_checked` |
| All-zero tax number | Label `placeholder` and exclude from tax-based candidate groups; this is a project exclusion, not a registry determination |
| Tax number with missing country | Keep unresolved; never assume Greece from length or source location |
| Reported country GR or EL plus nine ASCII digits | Permit a source-scoped reported-country/tax candidate key; country remains reported party context, not verified identifier jurisdiction |
| GR versus EL country values | Keep distinct keys in v1; no implicit alias merge |
| Foreign, prefixed, punctuated or other identifier format | Preserve and label `unassessed`; do not strip a VAT prefix, punctuation, or apply Greek rules |
| Missing/unsupported identifiers | Retain the occurrence and reason; never group all unknowns together |
| Public-buyer source key | Separate `kimdis.buyer-key` candidate namespace, buyer role only; never equate it to a tax number or company registration |
| Same literal identifier, varying names | Emit `name_variation` for review; neither accept a match nor declare a contradiction automatically |
| Same literal name, different identifiers | Keep separate; names, addresses and co-participation do not create identity links |

Reported-country/tax keys are scoped to KIMDIS and the policy version. They must
not be exported as canonical Greek AFM identities or reused as cross-source joins.
The first release does not implement a checksum algorithm: the verified sources
above establish structure, not an independently tested algorithm contract.
An issuer-country claim, party country, format check, checksum, authority response
and reviewed identity decision are distinct evidence dimensions.

A buyer key with varying tax numbers generates a review issue without erasing any
claim. Multiple buyer keys sharing a tax number remain distinct source keys; this
can reflect administrative structure. A party may belong to more than one
candidate namespace. Never take transitive closure of these groups as identity.
Do not classify a supplier as a company, person or public body from its name,
procurement role or tax-number shape.

### Output and operational contract

First-release command:

```bash
uv run --frozen python -m nima identities assess RUN_ID \
  --projection-version kimdis-participation-v1 \
  --output-dir work/identity-review --max-mentions 10000
```

NIMA_DATABASE_URL remains environment-only. No HTTP, registry requests, database
writes, migrations or new dependency are required. Default maximum: 10,000 party
occurrences; accept limits 1–10,000. A report is limited to 32 MiB of UTF-8 JSON.
Exceeding either budget fails visibly without publishing a truncated report.
Group by indexed comparison keys; do not generate all pairwise combinations.

The private JSON artifact contains a report-format/policy version, run/projection
selection, coverage, every occurrence (including unresolved ones), candidate
groups, issue codes and zero automatic identity links. Each member retains its
source ID, normalizer/content hash, role/ordinal and observation evidence: original
body hash, record JSON pointer and observed time. Repeated observations remain
evidence, not additional entities. Observation time is not legal validity time.
Archive integrity is `not_checked`; existing archived evidence remains independently
inspectable. No amount allocation or candidate-based spending totals are produced.

Canonical ordering and serialization give identical report content/hash for
identical inputs and policy. Candidate IDs include their namespace and policy.
Hashes of tax numbers are not anonymization. Reports contain source identifiers
and may include natural-person names: keep them outside Git in private directories
(0700) and files (0600), reject unsafe symlink/collision paths, and publish atomically.
An identical rerun may reuse a verified artifact; a different/corrupt artifact must
never be overwritten silently. Interrupted writes must not expose a completed report.

Stdout contains only status, policy/report hash and counters; no names, tax numbers,
connection strings or driver messages. Exit 0 means the selected cohort was fully
assessed within limits, even with unresolved parties. Configuration errors exit 2;
schema, missing-run, incomplete-projection, budget, database or output failures
exit 1 with a fixed redacted reason. No automatic work is acknowledged in ingestion.

## Later identity capabilities and gates

1. **Registry corroboration:** separately authorize and verify a bounded GEMI
   connector. A returned registry number, tax identifier and legal form are dated
   source claims with archived evidence. Current registry status does not establish
   a historical director, owner or company status. Absence is not proof of nonexistence.
2. **Reviewed decisions:** append-only accept/reject/revoke decisions cite exact
   occurrences, evidence, reviewer identity, rationale, policy and relevant dates.
   Stable internal party IDs are independent of any one tax number. Disputes and
   reversals preserve history; a correction cannot silently rewrite past results.
   Define reviewer authentication/permissions before exposing a decision-write API.
3. **Evaluated candidate matching:** exact identifiers remain the baseline. Consider
   Splink/Fellegi–Sunter only after a reviewed Greek-data pair set includes aliases,
   unrelated same-name parties, changed names, foreign IDs and difficult negatives.
   Report candidate recall and false-merge analysis with counts/uncertainty; split
   by entity/time to avoid leakage. Agree release thresholds before automatic links.

Temporal graph work consumes an explicit reviewed resolution snapshot. It preserves
unresolved occurrences and source assertions alongside accepted entity links.
Neither candidate group membership nor a model score establishes ownership,
collusion, fraud or tax evasion. GNNs and investigative risk models remain later modules.

## Stack, structure and code style

Retain Python 3.12, PostgreSQL 17 and pinned Psycopg 3.3.8. Implementation
lives in `src/nima/identity/`, with CLI routing in `src/nima/__main__.py`; tests live
in `tests/test_identity_*.py` and verification notes in `docs/verification/`.
Pure comparison policy is separate from SQL cohort reads and artifact publication.
Do not modify the installed skill snapshot or existing projection/source history.

Use immutable typed values, explicit unknowns, snake_case, Ruff formatting and
strict mypy. Illustrative style only, not an implemented interface:

```python
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class IdentifierAssessment:
    reported_tax_id: str | None
    format_status: Literal["missing", "nine_ascii_digits", "unassessed"]
    authority_status: Literal["not_checked"] = "not_checked"
```

Existing verification commands:

```bash
just check
just audit
```

Focused verification:

```bash
uv run --frozen pytest tests/test_identity_policy.py tests/test_identity_report.py \
  tests/test_identity_crash.py
```

## Testing and success criteria

Use pytest plus disposable real PostgreSQL tests under the existing fixtures.
Keep the repository's combined line/branch coverage floor of 90%; no skipped tests
or weaker checks. Write failing behavioral tests before implementation. Verify:

- Leading-zero and literal Greek preservation; ASCII-only digit checks; missing,
  placeholder, Unicode-lookalike, foreign, prefixed and ambiguous-country inputs.
- Equal names/different identifiers stay separate; equal reported keys/varying
  names create review issues. Buyer-key and country/tax namespaces never coalesce.
- Every selected occurrence and its exact evidence survives assessment, including
  zero-candidate cohorts, unknown/empty supplier lists and repeated observations.
- Missing receipts and unknown projection versions fail; other runs/versions cannot
  leak into the report. Coverage describes partial/unmanaged/quarantined runs honestly.
- Deterministic replay, bounds without truncation, read-only SQL, no HTTP, redacted
  failures, safe output paths and actual worker interruption at publication boundaries.
- A guard mutation causes a relevant regression test to fail, then is restored.
- Offline cached replay reconciles counts and leaves original evidence unchanged.
  This verifies mechanics, not empirical matching accuracy or company identity.

Before review, run checks/audit and the five-axis code review; publish one private,
main-targeted PR as StamKavid with hosted CI evidence. Do not merge or deploy automatically.

## Boundaries and review decision

Always preserve source assertions, evidence and unknowns; version comparison policy;
separate assessed/reported/reviewed states; document unsupported cases and coverage.
Ask before adding registry credentials/calls, dependencies, schema or CI changes,
automatic identity links, a decision-write interface or public data publication.
Never merge by name alone, infer legal form/ownership/fraud, equate source country
with issuing jurisdiction, overwrite evidence, or treat checksum/VIES as company proof.

The offline scope and comparison policy were approved through PR #15. No unresolved
external-access question blocks that scope. Registry access and later
decision/matching gates stay deferred.
