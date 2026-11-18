# Explicit CPV references

The offline reader supports the [OP-TED eForms SDK 1.15.1 catalogue](https://github.com/OP-TED/eForms-SDK/blob/1.15.1/codelists/cpv.gc).
Its [publisher licence](https://github.com/OP-TED/eForms-SDK/blob/1.15.1/LICENSE)
is CC BY 4.0. Attribution and modification notices travel in derived artifacts.
This selects one release; it makes no claim that the release is the latest.

`prepare_reference` takes raw captured genericode bytes, an explicitly selected
SHA-256, `ell` or `eng`, and a timezone-aware capture timestamp. It requires CPV
2008 identification and validates the complete catalogue before returning a
reference. Raw bytes and canonical reference artifacts stay outside Git. The
caller supplies capture provenance: a matching hash proves byte identity, not
independent authentication of the publisher or freshness. There is no downloader.

The reader limits input to 64 MiB, 10,000 rows, 1,000,000 elements, depth 12 and
4,096 characters per text value. It rejects DTDs, entities, external references,
duplicate codes/columns/cells, incomplete selected-language coverage and invalid
parent graphs. Greek text is retained exactly; there is no language fallback.
Entries are sorted by code, retaining the source's zero-based row ordinal and
label column so the original capture can be inspected.

The source uses **eight-digit main base codes**. A reported procurement code has
an additional check digit. This reader does not implement check-digit validation;
all results say `match_scope: cpv_main_base_code` and
`check_digit_validation: not_checked`. SDK release 1.15.1 and taxonomy version
2008 are distinct fields. An unknown reported taxonomy version stays unknown.
A CPV describes the procurement subject; it does not establish a supplier's KAD,
company sector, identity, eligibility or source correctness.

Implementation uses [defusedxml 0.7.1](https://github.com/tiran/defusedxml/tree/v0.7.1#defusedxml)
with explicit `forbid_dtd`, `forbid_entities` and `forbid_external`. It was already
locked through the audit tooling and is now declared directly at runtime (PSFL,
no transitive runtime dependencies). Development-only type stubs keep the parser
boundary typed. A bounded byte buffer and row-wise clearing avoid retaining the
full XML tree. No application schema, source schedule or HTTP budget changes.

A real-release offline check observed all 9,454 entries in Greek; this is a single
release's completeness check, not a performance SLA or a correctness certificate
for source-reported codes. The empty HTTP-202 TED response was rejected and is
not a usable reference. KAD 2008/2025 crosswalks remain separate work.
