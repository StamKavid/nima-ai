# Official taxonomy release assessment

Reviewed 2026-11-18. This records release boundaries for the next dictionary
increment; no dictionary, licence certification or company lookup is installed.

| Vocabulary | Primary source | Verified release fact | Application boundary |
|---|---|---|---|
| Procurement CPV | [TED CPV](https://ted.europa.eu/en/simap/cpv) | TED identifies CPV 2008 as current and offers XML/ODS/XLS releases | Pin the selected raw release, language and hash; a match does not supply a missing reported version |
| Supplier KAD | [AADE transition](https://aade.gr/allagi-antistoihisi-kad-me-toys-ishyontes-apo-132026) | KAD 2025 takes effect from 2026-03-01; official KAD 2008/2025 correspondence material is separate | Preserve reported version and dates; do not silently rewrite a historical company activity |
| Buyer function/legal class/type | [KIMDIS contract](https://cerpp.eprocurement.gov.gr/khmdhs-opendata/help) | The retained response exposes distinct key/value fields | Keep those source namespaces separate from CPV and KAD; no inferred sector mapping |

For CPV, main and supplementary vocabularies must remain separate. The existing
extractor checks main-code syntax only. No checksum or membership validation is
claimed. For KAD, a correspondence table provides classification mappings; it does
not prove that a particular company reported or adopted the destination activity.

C4 acceptance before installing dictionaries:

- Archive the official distribution and record URL, authority, retrieval time,
  release/effective dates, language, raw SHA-256, format and reuse terms.
- Inspect actual formats before implementing a bounded parser; reject ambiguous
  entries, unsupported versions and conflicting duplicate codes.
- Keep official labels and provenance separate from original reported labels.
- Require explicit release selection. Missing reported version stays unknown;
  a selected comparison release is application context, not a source assertion.
- Report match, no match, unavailable dictionary and version conflict separately.
  A missing code is not a finding against a company.
- Evaluate Greek labels and KAD multi-target/temporal mappings before proposing
  any reviewed crosswalk. No CPV-to-KAD or buyer-function-to-supplier inference.

The distribution files, their hashes, licences and parsers have not been verified
in this assessment. Only primary landing-page release statements were inspected.
C3's immutable SQL snapshots retain `taxonomy_validation: not_checked` and the
reported version until dictionary support is separately reviewed.

## C4 explicitly selected CPV implementation

The [offline CPV reference reader and annotations](cpv-reference.md) now support
the actual OP-TED SDK 1.15.1 genericode distribution and its CC BY 4.0 attribution.
That follow-up supersedes the unverified-distribution statement above for this
one CPV release only. Both Greek/English reads cover 9,454 entries. Base-code
membership is separate from full-code/check-digit validity, source correctness
and an unknown reported version. KAD crosswalk verification remains pending.
