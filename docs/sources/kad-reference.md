# KAD reference acceptance — C5

Reviewed 2026-11-18. This is a source/implementation contract, not an installed
crosswalk. Existing reported GEMI KAD values remain unchanged. No company lookup,
private myAADE session, model, schema migration or source schedule is added.

## Primary material actually inspected

| Material | Publisher link | Observed format and boundary |
|---|---|---|
| Transition and supporting material | [AADE transition page](https://aade.gr/allagi-antistoihisi-kad-me-toys-ishyontes-apo-132026) | Links the catalogue and correspondence material; base KAD 2025 regime applies from 2026-03-01 |
| Selected catalogue | [AADE KAD 2025 PDF](https://aade.gr/sites/default/files/2026-11/NEW%20ACTIVITY%20CODE%20NUMBER%E2%80%99S%20TABLE%202025.pdf) | Captured PDF, 430 pages; code, description and short-description columns |
| Selected correspondence | [AADE KAD 2008/2025 PDF](https://aade.gr/sites/default/files/2026-11/MAPPING%20TABLE%20KAD%202008%20WITH%20KAD%202025.pdf) | Captured PDF, 617 pages; five distinct published columns |
| In-year classification amendment | [AADE A.1117/2026](https://www.aade.gr/egkyklioi-kai-apofaseis/1117-28-05-2026) | Adds codes/changes a description; a taxonomy year alone cannot identify every release |
| Reuse conditions | [AADE site terms, clause 6](https://aade.gr/oroi-hrisis-toy-diktyakoy-topoy-tis-aade) | Faithful reproduction with AADE attribution is permitted; sale and modification are restricted |

The raw PDFs and landing/terms HTML were boundedly captured with HTTP status,
retrieval time, URL, byte count and SHA-256 outside Git. PDF page counts match the
publisher-rendered documents. Pages 2–3 (one-based) were sampled with layout text
and the correspondence's first table page was visually inspected. Complete table
extraction, all row counts, one-to-many incidence and label accuracy have **not**
been validated. No inferred completeness or latest-release claim follows.

The selected documents display May 2026 publication context and have November
URL paths. Capture time, file path, document publication and classification/legal
effective dates are different fields. Do not derive an entry's validity interval
from its capture timestamp or the directory name.

## Column and identity contract

The correspondence columns are not interchangeable:

1. Five-digit transitional identifiers for the migration process. The source says
   these are not selectable company activity codes; keep them in a separate field.
2. The source's KAD 2008 comparison code representation.
3. Its original KAD 2008 code representation and description.
4. The candidate KAD 2025 activity code.
5. The candidate activity description.

Sampled representations differ in leading-zero preservation. Retain exact code
text from each column, original Greek labels and coordinates/page/row identity.
Do not infer an eight-digit canonical identifier by stripping or padding zeros,
and do not cast codes to integers. A future comparison key must have its own
published convention and evaluated test cases.

The catalogue includes administrative/non-activity categories as well as economic
activities. Membership does not by itself justify an industry/sector assignment.
Do not derive CPV-to-KAD, buyer-function-to-supplier-sector or legal-company identity
from these tables. Eurostat NACE context cannot substitute for Greek national KAD
extensions or prove a company's reported activity.

## Reuse decision for this increment

Preserve faithful private source captures with attribution and link to the
publisher. Do not label the material CC BY/openly licensed, bundle transformed
AADE tables into the code distribution, or activate commercial redistribution
based on the general site terms. Dataset-specific permission or a suitably
licensed authoritative distribution must resolve the intended normalized/indexed
and commercial use before that deployment decision. This records the actual
publisher restriction and an unresolved scope question; it is not a claim that
all internal indexing is legally prohibited.

The public supporting page supplies PDFs for these selections. A decree/search
result mentioning an Excel file does not establish a downloadable, reusable
spreadsheet. Do not guess hidden file URLs or treat third-party tables as the
publisher's distribution. The scoped discovery did not establish a usable,
clearly licensed official CSV/XLSX replacement. Keep that result open.

## Runtime acceptance before implementation/adoption

No parser dependency is selected at C5. First prove the exact downloaded layout
and permitted use. Then freeze an offline adapter with these requirements:

- Explicit raw hash, publisher URL, language, taxonomy edition, document/release
  identity and capture time; effective interval is known only from supporting
  authority. Preserve unknown legal/entry dates and all amendments' evidence.
- Exact published strings and all five correspondence columns; page/table/row and
  bounded cell coordinates. Text extraction that joins wrapped rows or adjacent
  columns must fail validation, not guess a mapping. No LLM-generated row repair.
- Directed 2008→2025 candidate relations, preserving every supported target and
  source row. Never select the first target, assume invertibility, merge separate
  rows or assert that a company adopted a candidate activity.
- Separate reference membership, crosswalk candidates and a company's reported
  assertion. Unknown reported version remains unknown; unsupported/ambiguous
  representation, version conflict and unavailable reference are explicit outcomes.
- Full row/grain reconciliation, duplicate/conflicting-cell handling, a complete
  known-answer synthetic fixture and stratified page/cell comparison of real
  source output. Partial page extraction cannot become a complete dictionary.
- Explicit byte/page/row/text/time ceilings established from the selected files;
  bounded regular no-follow input and existing private atomic publication. PDF
  tool/dependency security and licensing need review before runtime use.
- Evaluation includes leading zeros, the transitional column, inactivity
  categories, repeated/multi-target rows, wrapped labels, amendments and unknown
  dates/versions. A deliberate wrong-column/missing-target mutation must fail.
- A CLI remains offline and emits fixed counts/status; every annotation links the
  exact source capture and original assertion. Existing CPV/metadata/analytics
  artifacts must remain byte-compatible.

## Checkpoint and independent work

C5 completes source inspection and the analytics-readiness assessment. It does
not implement, certify or activate KAD matching. Reuse acceptance and a complete
extraction evaluation precede the runtime slice. Continue DataOps observability
and additional descriptive metric work independently; these need no KAD table,
company-source request, new schedule or model adoption.
