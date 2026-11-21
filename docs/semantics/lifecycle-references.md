# Lifecycle references (M4)

`lifecycle_references.v1` (`draft`) classifies the **explicit references** that captured KIMDIS records
make to other records. It is a model piece of the [V1-05 semantic model](../specs/SPEC-semantic-model.md),
not a metric: it counts nothing about money or activity, and it feeds the later cross-source joins. It reuses
the shared [record selection](../../src/nima/semantics/selection.py).

## Edges

Only references a source states form edges, and the relation is fixed by the source field:

| Source field | Relation | Target namespace |
|---|---|---|
| `auctionRefNo` | `award` | `kimdis:` |
| `prevReferenceNo` | `previous_record` | `kimdis:` |
| `paymentRefNo` | `payment_order` | `kimdis:` |
| `diavgeiaADA` | `commitment_decision` | `diavgeia:` |

A reference records that one record **cites** another. It never says the cited record is superseded:
an amendment with a new ID stays a separate publication, nothing is removed or merged, and a count over
records is unchanged by being cited. No chain is inferred from the edges.

## Status of each edge

| Status | Meaning |
|---|---|
| `resolved` | the target is selected in the cohort (latest observed version, not ambiguous) |
| `unresolved` | a `kimdis:` target not selected in the cohort: another stage that the feed does not collect, a record outside the window, or a later one |
| `target_ambiguous` | the target is a record whose latest versions tie in this cohort |
| `external` | the target is in another namespace (a Diavgeia decision) and cannot resolve inside a KIMDIS cohort |
| `self_reference` | a record citing itself |

`unresolved` describes the cohort, not a defect. Duplicate references inside one record collapse to one
edge. A record with an unknown reference list (`unknown_reference_source_ids`) is different from one with
no references; an ambiguous record's own references are unknown and are not read.

## Sharing and the umbrella threshold (decision D5)

The result discloses, per relation and per target, how many distinct records cite it, lists every target
cited by two or more records, and reports `max_citing_records`. An **umbrella** is flagged only when the
caller passes a threshold, and only for targets cited by *more* records than that number. **No default
threshold is adopted**: the first measurement below shows no umbrella pattern, so a number would be a
guess. Choose one from a larger sample.

## Measured on real records (2026-11-21, 1,317 records)

Counts only. The sample is one whole day plus about 90 days of one buyer.

| Source field | References | Records citing | Distinct targets | Targets cited by 2 or more | Most citing one target | Resolved in the sample |
|---|---:|---:|---:|---:|---:|---:|
| `auctionRefNo` | 1,138 | 1,135 | 1,004 | 68 | 9 | 0 |
| `prevReferenceNo` | 117 | 116 | 115 | 1 | 2 | 19 |
| `paymentRefNo` | 69 | 64 | 69 | 0 | 1 | 0 |
| `diavgeiaADA` | 4 | 4 | 4 | 0 | 1 | not applicable (external) |

Read: 86 percent of records cite an award reference, mostly to a target no other record cites (936 of 1,004);
the most shared award target has nine citing records, which fits one award split into several contracts
and not an umbrella. Award and payment targets never resolve here because those are other procurement
stages. Only a previous-record reference can resolve inside a contract-only capture, and 19 of 115 do. The
Diavgeia citations are rare (4 of 1,317) and unshared.

## Not part of this slice

No reference SQL (it comes when a metric consumes the edges, as in the cross-source joins of V1-07), no
stage model joining awards, contracts and payments, and no chain collapsing: the owner decision D5 keeps
amendments as separate publications.
