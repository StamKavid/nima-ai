# Diavgeia source acceptance dossier (V1-06, step 1)

Status: **draft; decision 1 taken, decisions 2-5 open.** The owner answered "yes to pilot" on 2026-11-20
(decision 1 below); nothing else has been decided. No Diavgeia code exists and no Diavgeia data or search
endpoint has been called. This dossier is built only from the two official documentation pages
below, read on 2026-11-20. Nothing here is from memory: every claim names where it was found, and
what was not found is listed as **unverified**. Quotes are short, in the original Greek with an
English gloss, and the source must be cited as Diavgeia (see the reuse terms).

## What was read, and how it is preserved

| Page | Raw template read | Bytes | SHA-256 | Server `Last-Modified` | Read at (UTC) |
|---|---|---|---|---|---|
| API documentation, <https://diavgeia.gov.gr/api/help> | `/views/static/apiHelp.html` | 338,718 | `4fb3cadeb4ab3b1943e69dbd6ed2f888dd409988341757cd32b4ec39d9796734` | 2026-10-21 14:51:28 | 2026-11-20 10:43:59 |
| Terms of use, <https://diavgeia.gov.gr/termsOfUse> | `/views/static/termsOfUse.html` | 23,487 | `0c1ae4110990b06b13d695c9052ec99b71631c99ddb74134525854c42d0d97bb` | 2026-10-21 14:51:44 | 2026-11-20 10:44:00 |

Both pages are a single-page web app: a plain fetch returns only an app shell, so the text was read
by rendering each page in a headless browser. Rendering was restricted to `diavgeia.gov.gr`, to
`GET`, and blocked any path under `/luminapi/` or `/opendata/`. Two requests were blocked: a
Google Analytics script and the portal's own server-status call. No search or decision endpoint was
requested. The originals are kept outside Git (a local scratch directory, not durable), so the owner
should copy them into the evidence archive if this dossier is accepted.

The documentation shows a pilot system with public test accounts. Those credentials are not copied
here and must not be used: they belong to the pilot system and are not ours.

## Findings

### Access and authentication

- Production base URL, from the page: `https://diavgeia.gov.gr/opendata`. The same page's examples
  use the pilot host `https://test3.diavgeia.gov.gr/luminapi/opendata`, and its sample search output
  shows `url` and `documentUrl` values of the form `BASE_URL/luminapi/api/decisions/<ADA>` (and
  `.../document`). **Which prefix is canonical for production document URLs is unverified.**
- Reads: JSON or XML, chosen by `Accept` header or a `.json`/`.xml` suffix.
- Authentication is HTTP Basic, required "for protected resources" (`προστατευμένους πόρους`).
  Public decision search and retrieval are described without credentials. **How a production
  "registered user" is obtained is not described: unverified.**
- Anonymous clients get smaller pages: "Για μη εγγεγραμμένους χρήστες το μέγιστο μέγεθος της
  σελίδας είναι 500 αποτελέσματα, ενώ για εγγεγραμμένους χρήστες το αντίστιχο όριο είναι 1000"
  (maximum page size 500 for unregistered users, 1000 for registered).

### Rate and fair-use limits

**None stated.** A search of the documentation text for rate, throttling, request-frequency and
429 wording found nothing. Absence of a stated limit is not permission for unlimited use, so any
pilot should use the engine's existing request-rate limits and stop on error status. Whether the
server enforces limits at runtime is unverified.

### Reuse and licence (from the terms of use)

- "Το συνολικό περιεχόμενο … διατίθεται στο κοινό δωρεάν με τους ειδικότερους όρους της Ελληνικής
  άδειας Creative Commons Αναφορά Προέλευσης (CC BY v.4.0) … εκτός εάν ορίζεται διαφορετικά"
  (site content is available under the Greek Creative Commons Attribution licence, CC BY 4.0,
  unless stated otherwise). Third-party intellectual property is excluded from that licence.
- "Τα έγγραφα και πληροφορίες δημοσίου τομέα που αναρτώνται … μπορούν να χρησιμοποιηθούν,
  επαναχρησιμοποιηθούν, διαδοθούν μέσω συνδέσμων και να αναδημοσιευθούν, για εμπορικούς ή μη
  σκοπούς, χωρίς να απαιτείται άδεια ή καταβολή οικονομικού ανταλλάγματος, υπό τους όρους του Ν.
  3448/2006 … και σε κάθε περίπτωση υπό τον όρο αναφοράς της πηγής τους" (public-sector documents
  may be used, reused, linked and republished, commercially or not, without permission or fee,
  under Law 3448/2006 and always with the source cited).
- **Attribution is required.** Every export or display of Diavgeia-derived data needs a source
  statement; the exact wording is for the owner to set.
- The terms say nothing, in the text read, about automated, bulk or API access, caching, or
  archiving. The detailed "Άδεια Χρήσης" licence page the terms refer to was **not read**:
  unverified.

### Personal data

- Decisions carry personal data. The tax-number field (`afm`) covers individuals as well as
  companies: its documented types include "Φυσικό ή Νομικό πρόσωπο εντός της Ελλάδας" and
  "Φυσικό πρόσωπο κράτους-μέλους της ΕΕ" (natural or legal person in Greece; natural person of an
  EU member state). Records also carry `privateData`, "Ένδειξη για το αν η πράξη περιλαμβάνει
  προσωπικά δεδομένα" (flag for whether the decision includes personal data).
- The terms limit the purpose: posting is for transparency of state action "όπως καθορίζονται στο
  Ν. 3861/2010", and "Περαιτέρω χρήση των εγγράφων … γίνεται πάντοτε με την επιφύλαξη τήρησης των
  διατάξεων για την προστασία του ατόμου από την επεξεργασία δεδομένων προσωπικού χαρακτήρα"
  (further use is always subject to personal-data protection law). The terms cite older Greek
  statutes "as in force each time"; they were not interpreted legally here.
- **Consequence for this project:** a data-protection decision is needed before any real
  retrieval, covering what is kept about natural persons and for how long. Real decisions and
  documents stay out of Git, and test fixtures must be synthetic.

### Identity, versions, corrections and cancellations

- Every published decision has an **ADA** ("Αριθμός Διαδικτυακής Ανάρτησης"), for example the
  documented sample `ΒΛΕΖΝ-Ρ7Ν`; the ADA contains Greek letters. It is not a KIMDIS identifier.
  Proposed namespace: `diavgeia:<ADA>`.
- `versionId` "αλλάζει σε περίπτωση που γίνει διόρθωση των μεταδεδομένων μιας αναρτημένης πράξης,
  ή όταν αλλάξει η κατάστασή της" (changes when metadata is corrected or the status changes).
- `status` for public decisions: `PUBLISHED` (in force), `PENDING_REVOCATION` (in force, a
  revocation has been requested), `REVOKED`. `GET /decisions/:ada/versionlog` returns the ordered
  versions, each with `versionId`, `status`, `versionTimestamp`, `creator`, `description` (which
  carries the revocation reason) and `correctedVersionId`.
- `correctedVersionId`: "Η ύπαρξη αυτής της τιμή σημαίνει ότι έχει γίνει ορθή επανάληψη της
  πράξης, δηλαδή αντικατάσταση του εγγράφου" (its presence means the decision document was
  replaced to fix an error).
- **Default search hides revoked decisions.** `status` defaults to `published`; `revoked`,
  `pending_revocation` or `all` must be asked for. Tracking cancellations therefore needs
  `status=all` or per-ADA history calls, and the first is not free of cost.

### Dates

| Field | Documented meaning |
|---|---|
| `issueDate` | Issue date of the decision, Unix timestamp in milliseconds |
| `submissionTimestamp` | "Ημερομηνία και ώρα τελευταίας τροποποίησης" — date and time of last modification, milliseconds |
| `versionTimestamp` (history) | Last modification of that version, milliseconds |

No separate "first published" field is documented. The first publication time can only be
inferred from the earliest entry of the version log: **an inference, not a documented meaning**.
Source dates stay unknown where unsupported, and source text is kept next to any parsed value.

### Paging, windows and ordering

- `GET /search`: `page` is 0-based and `size` is capped as above. Filters include `from_date` /
  `to_date` (last modification) and `from_issue_date` / `to_issue_date` (issue date), `org`,
  `type`, `status`, `sort` (`recent`, the default, or `relative`).
- The server rewrites date ranges: issue-date windows longer than 180 days are shortened to 180 days,
  and missing bounds are filled in (the page lists the rules). Collections must request explicit
  windows of at most 180 days and check what was actually applied.
- The engine already addresses pages by number, so **no cursor support is needed** (the deferred
  item stays deferred). One risk to test in a bounded pilot: the default order is "most recently
  modified first", so a decision modified while paging could shift between pages. The engine's
  `pagination_changed` check would stop the run; how often this happens is unverified.

### Documents and attachments

- Each decision has a digitally signed PDF; `documentUrl` points to it and `documentChecksum` is
  its **SHA-1**. Attachments carry `id`, `filename`, `mimeType` and a **SHA-1** `checksum`.
- Proposed handling: archive the original bytes first, compute our own SHA-256, and also check the
  source's SHA-1 as an integrity signal, never as our primary identity. Document links come from
  response bodies, which are untrusted: they must be checked against the declared endpoint before
  any request (the N1 guard does this for requests the adapter builds).

### Availability

No maintenance notice is displayed in the rendered pages read on 2026-11-20. A maintenance message
("η αναζήτηση πράξεων είναι δυνατή μόνο βάσει του ΑΔΑ", search limited to ADA, statistics
suspended) exists in the page's static HTML as a hidden template. An earlier project note
(`gemi-publicity-fallback.md`) recorded that notice as displayed; it was not displayed on this
date, so that note is out of date. Live API health is untested.

### Decision types worth considering first

The documentation specifies the special fields of six procurement and spending types: Β.1.3
ανάληψη υποχρέωσης, Β.2.1 έγκριση δαπάνης, Β.2.2 οριστικοποίηση πληρωμής, Δ.1 ανάθεση, Δ.2.1
περίληψη διακήρυξης and Δ.2.2 κατακύρωση.

| Type | Special fields (documented) | Note |
|---|---|---|
| **Δ.2.2 ΚΑΤΑΚΥΡΩΣΗ** (award) | `person` (list: `afm`, `afmType`, `afmCountry`, `name`, `noVATOrg`), `awardAmount` (`amount`, `currency`), `textRelatedADA` (ADA of the related expenditure approval) | Smallest field set. All three fields are `required: false` in the documented specification, so completeness cannot be assumed |
| **Β.1.3 ΑΝΑΛΗΨΗ ΥΠΟΧΡΕΩΣΗΣ** (commitment) | `financialYear`, `budgettype`, `partialead` and `kae` (required), `entryNumber`, `recalledExpenseDecision`, `amountWithVAT`, `amountWithKae` (list: `sponsorAFMName` with `afm`/`name`, `kae`, `amountWithVAT`, remainders), `partialead`, `relatedPartialADA` | The type KIMDIS's `diavgeiaADA` plausibly points at. Larger than Δ.2.2 and carries supplier names and tax numbers |
| Δ.1 ΑΝΑΘΕΣΗ (assignment) | the above plus `assignmentType`, `cpv` | Adds CPV, which the project already holds as a reference |
| Δ.2.1 ΠΕΡΙΛΗΨΗ ΔΙΑΚΗΡΥΞΗΣ (tender summary) | `cpv`, procedure, selection criterion, contract type, `estimatedAmount`, `textRelatedADA` | Estimated value, not an awarded value |

**No Diavgeia field refers to a KIMDIS contract identifier, but KIMDIS records cite Diavgeia.** A keyword search of the whole
documentation text (every decision type) for ΑΔΑΜ, ΚΗΜΔΗΣ, ΕΣΗΔΗΣ, ADAM and ΠΡΟΜΗΘΕΥΣ found
nothing. The field lists of Δ.1, Δ.2.1 and Δ.2.2 were read in full; those of Β.1.3, Β.2.1 and
Β.2.2 were covered by that search only. The explicit key sits on the
KIMDIS side (next section). Any join beyond those explicit keys, on supplier tax number, amount,
dates or CPV, is an inferred link and must stay an investigative signal, not a recorded fact, in
line with the rule against invented identities. Whether PDF text carries an explicit KIMDIS
reference is unverified.

### Linking keys that already exist

Checked in this repository's own KIMDIS parsing (`src/nima/sources/kimdis.py`, `_references`) and
in the Diavgeia documentation read above. These are documented or coded keys, not inferences.

| From | Field | Points to | Status |
|---|---|---|---|
| KIMDIS record | `diavgeiaADA` | a Diavgeia decision's `ada`, parsed here as relation `commitment_decision`, namespace `diavgeia:` | In our code and test fixture. What KIMDIS means by it was taken from earlier project work and **not re-read in KIMDIS's own documentation today**: unverified |
| KIMDIS record | `auctionRefNo`, `prevReferenceNo`, `paymentRefNo` | other KIMDIS records (award, previous record, payment orders) | In our code |
| Diavgeia Δ.2.1 | `textRelatedADA` | the related commitment decision | Documented |
| Diavgeia Δ.1, Δ.2.2 | `textRelatedADA` | the related expenditure approval | Documented |
| Diavgeia Β.1.3 | `relatedPartialADA` | the initial partial commitment | Documented |
| Diavgeia, types shown in the samples (Γ.3.5, Ε.3) | `relatedDecisions[].relatedDecisionsADA` | other decisions | Documented in sample responses; whether every type has it is unverified |
| Both | `afm` (Diavgeia, with `afmType`, `afmCountry`) and the reported tax identifier (KIMDIS) | a party | Grouping key only, never a legal-identity finding; Diavgeia covers natural persons too |

So the chain of a spend is already expressed by ADA references inside Diavgeia, and KIMDIS reaches
into it through `diavgeiaADA`. Matching that field to a Diavgeia type (Β.1.3 commitment of
obligation, "ΑΝΑΛΗΨΗ ΥΠΟΧΡΕΩΣΗΣ") is an inference from the names and must be confirmed on real
records.

## Prior art: who else links these sources (leads only, not yet read)

A web search on 2026-11-20 found the projects below. **Everything here comes from search-result
snippets and summaries, which are not sources, and none of the pages could be read** because their
hosts are not on this environment's allowlist. Treat each as a lead to verify.

| Lead | What it reportedly is | Why it matters |
|---|---|---|
| "Greece: Diavgis", <https://data.open-contracting.org/en/publication/161> | An independent project listed in the Open Contracting registry, reported to aggregate Diavgeia, KIMDIS and TED, with natural persons redacted and coverage described as a sample | Closest prior art. Its methodology would show which keys it joins on; the page and its linked documentation are the thing to read |
| iMEdD Lab, <https://lab.imedd.org/en/?p=9919> | Appeared with Diavgis in results; content unknown | Unread |
| arXiv 2512.05647, <https://arxiv.org/abs/2512.05647> | A corpus of roughly a million Diavgeia decisions with text extracted from PDFs, linking a GitHub repository | Diavgeia side only; useful for field shapes and scale, not for linking to KIMDIS |
| "Public spending as LOD: the case of Greece", <https://semantic-web-journal.net/node/464> | An older linked-data effort on Greek public spending | Prior art for a typed-reference model |
| ΚΥΑ 4968/22-01-2026, new article 6α "Ανοικτά δεδομένα ΚΗΜΔΗΣ", and a later amendment 87338/14-10-2026 (ΦΕΚ Β΄ 6275/16-10-2026) | Reported legal basis for KIMDIS open data | Bears on KIMDIS reuse terms, which this project currently records as CC BY 4.0. The primary FEK text must be read; the search hits were tax-news sites |
| Vouliwatch and Solomon, "Consultocracy" report (2026) | Reported analysis of KIMDIS contracts 2017-2025 | Evidence that others use KIMDIS at scale; method unread |

What the search did **not** find: any page documenting the keys or field mappings used to join
KIMDIS, Diavgeia, GEMI and TED. Search summaries described ADA as Diavgeia's identifier and ADAM as
KIMDIS's; that is a summary's wording, not a verified statement, and it is not used above.

## Not verified (explicitly)

1. How production API access or a registered user is obtained, and any key or registration terms.
2. Runtime rate limiting, and the real behaviour of paging while data changes.
3. The canonical production prefix for document URLs (`/opendata` versus `/luminapi/api`).
4. The detailed licence page and whether any clause limits automated or bulk access.
5. Whether revoked decisions keep their documents available.
6. Whether any decision type links explicitly to a KIMDIS identifier, in metadata or in PDF text.
7. Real response shapes: this dossier read documentation and sample JSON, not live responses.
8. Anything in the prior-art table: none of those pages were read.
9. What KIMDIS officially says `diavgeiaADA` refers to, and how often it is filled.

## Decisions for the owner

1. **Accept Diavgeia as the second source for a bounded pilot?** **Decided: yes** (owner,
   2026-11-20), subject to 2-5.
2. **Reuse and attribution.** Accept CC BY 4.0 plus Law 3448/2006 with a fixed source statement,
   and set its wording. Recommended: accept.
3. **Personal data.** Choose what is retained about natural persons (names, tax numbers, document
   text), how long, and who may see it. Recommended: archive originals privately, keep fixtures
   synthetic, and project supplier tax numbers only for legal entities until a policy exists.
4. **First decision class and how it is found.** Revised recommendation: take the ADAs that KIMDIS
   records already cite in `diavgeiaADA` for one small KIMDIS cohort, and fetch exactly those
   decisions one by one with `GET /decisions/:ada` (and their `versionlog`). That tests the
   explicit KIMDIS-to-Diavgeia key end to end, avoids search paging and window rules, keeps the
   run small enough to review by hand, and touches only decisions we already have a reason to
   read. Δ.2.2 by organisation and window remains the fallback if too few records carry the field.
5. **Network.** A pilot needs `diavgeia.gov.gr` on the source worker's egress allowlist and a rate
   limit the owner chooses. Nothing is fetched until you approve both.

If you accept, the next steps are a spec for the Diavgeia adapter (identity, versions, status
handling, window rules), recorded synthetic samples for the conformance suite, and then the
approved bounded real run.
