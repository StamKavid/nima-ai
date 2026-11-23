# GEMI AFM lookup, L5c: import and comparison of the L6 archives, offline

Source: GEMI Open Data API, ODC-BY-1.0; data retrieved on 2026-11-23 (the L6 pilot). Spec:
[SPEC-gemi-afm-import](../specs/SPEC-gemi-afm-import.md). Counts only: no AFM, name or registry number is
recorded here. No request was made.

## What was run

The L6 archives (one AFM search of three large listed legal entities, and the head-office profile of each) were
imported into a **throwaway** PostgreSQL database with `nima gemi import-afm` and `nima gemi import`, compared
against a **synthetic** procurement cohort, and the database was dropped. The cohort had five synthetic
suppliers: one for each searched AFM, one carrying an AFM that was never searched, one with no tax number.
The comparison ran three ways: the search alone, the profiles alone, and both together.

## Import

| Item | Result |
|---|---|
| Search run | 3 AFMs, 3 requests, 12 hits, 0 unconfirmed quarantines; imported |
| Profile run | 3 profiles, 0 not found; imported |
| Importing the search run again | reused, nothing written |

## Comparison

| | Search only | Profiles only | Both |
|---|---|---|---|
| Policy / report format | v2 / v2 | v1 / v1 | v2 / v2 |
| Registry observations | 12 | 3 | 15 |
| Suppliers in agreement | 3 | 3 | 3 |
| Supplier not searched | no candidate | no candidate | no candidate |
| Supplier without a tax number | unassessed | unassessed | unassessed |
| Agreements resting on more than one registry number | 3 | 0 | 3 |
| `multiple_registry_numbers_for_reported_afm` on suppliers | 3 | 0 | 3 |
| Same report on a second run | yes | yes | yes |
| Automatic identity links | 0 | 0 | 0 |

Hits: 12 returned, all 12 report the queried AFM, 9 are branches, 4 carry a deletion status (one by merger).
Each searched AFM answered `hit_multiple`; none was truncated, quarantined or mismatching.

## Findings

- **The comparison works on real answers**, and the search-only and profile-only results agree on which parties
  agree with the registry. Profile-only output is the old format and policy, unchanged.
- **Branches make the multiple-registry-numbers issue the rule, not the exception.** All three companies have
  branches that repeat the head office's AFM, so all three agreements carry
  `multiple_registry_numbers_for_reported_afm`. It is true (several registry numbers share the AFM) but it no
  longer separates a real conflict from an ordinary head office with branches. See decision L5c-1.
- **`queried_not_found_at_observation` was not exercised by real data.** The only real 404 in the pilot was a
  personal AFM, which is not used here. That outcome is covered by synthetic tests only.
- **Deleted registrations were imported and reported, not filtered** (decision L5-3). Four of twelve hits shows
  that a comparison cannot treat a registry number as "the company" without its status.

## Correction

The L6 record said 3 of the 12 hits carry a deletion status. The count is 4 (two for one company, two for
another, one of those by merger); the L6 record and the spec table are corrected in the same change.

## After decision L5c-1 (policy v3)

The owner decided L5c-1 as recommended, and the same offline run was repeated under `registry-comparison-v3`:
the three agreements are unchanged and **no supplier carries `multiple_registry_numbers_for_reported_afm`**
in any of the three modes (3 head offices and 9 branches, none of the branches counted towards a conflict).
Search-only and combined runs still show 3 agreements resting on more than one registry number; profile-only
shows 0. The first table above records the v1/v2 result that prompted the decision.

## Decision for the owner (decided: as recommended)

| # | Decision | Recommendation |
|---|---|---|
| L5c-1 | Should `multiple_registry_numbers_for_reported_afm` be raised when the extra registry numbers are branches of one head office? | Raise it only when more than one **non-branch** registry number shares the AFM. A head office plus its branches stays an ordinary agreement, with `is_branch` and status in the report. This changes the policy for profile and search evidence alike, so it needs a spec line and a policy version |
