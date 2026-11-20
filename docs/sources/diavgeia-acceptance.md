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

**Caution on what a citation proves.** Diavgis's methodology warns that an umbrella reference (an
annual expenditure approval cited by thousands of acts) is not a link between stages of one
procurement. Our typed references must keep that distinction: an ADA citation records a reference,
never by itself a merge. If many KIMDIS records cite one `diavgeiaADA`, that is an umbrella, not a
one-to-one link, and must not be turned into a single chain.

## Measure first

Before any Diavgeia request, count what our own KIMDIS data already contains. The command below is
read-only (its session cannot write), is tested against synthetic records, and prints counts and public
ADA identifiers only: no record content, names, tax numbers or amounts. A record counts once however
many versions it has. Run it against the pilot database:

```sh
NIMA_DATABASE_URL="<read-only connection to the pilot database>" \
  uv run python -m scripts.diavgeia_link_census --top 20
```

It prints, as JSON: `kimdis_records`, `cite_a_diavgeia_ada`, `distinct_cited_decisions`,
`decisions_cited_by_more_than_one_record`, `max_records_citing_one_decision`, and `most_shared`
(the cited decisions with the most records citing each). It reads the typed references stored in
each record's normalized JSON (`source_field` `diavgeiaADA`, target `diavgeia:<ADA>`).

How to read the result: if few records cite an ADA, the explicit key is too sparse for the pilot
and the fallback in decision 4 applies. If most cited ADAs are shared by many records, the key
points at umbrella decisions and cannot identify a single procurement. If a healthy share cite a
distinct ADA each, the explicit-key pilot is worth running.

## Prior art: who else links these sources

Read on 2026-11-20 from the original pages (raw HTML archived outside Git; SHA-256 of each below).
A first web search also produced leads; summaries in search results are not sources and are used
only to find pages.

**Diavgis**, <https://data.open-contracting.org/en/publication/161> (Open Contracting Partnership
data registry entry; SHA-256 `d4d1f6b8e801ce719fecb961c6207259e0444e54ac2a50845d88316143ef2009`,
retrieved by the registry 2026-11-03, read here 2026-11-20). What the page says:

- "an independent project that publishes public procurement data aggregated from three official
  sources": Diavgeia, KIMDIS and TED, covering planning, tender, award, contract and
  implementation, as OCDS (the Open Contracting Data Standard), with the OCID prefix `ocds-r3r7e7`.
- "Records across these sources that belong to the same contracting process are identified and
  linked together." **That page does not say by which keys or fields.** It points to the project's
  own publication policy, <https://diavgis.gr/ocds-policy>, described next.
- Licence CC BY 4.0. Data starts 2026-03-01; coverage is "a large sample rather than a full census";
  "The details of natural persons are redacted"; four OCDS fields are withheld for a paid service.
  Counts shown: about 2.56 million parties, 381 thousand tenders, 1.41 million awards, 1.25 million
  contracts, daily updates.
- Its own data-quality notes, which are relevant to us: some `parties/id` values are not unique, so
  organisations cannot always be told apart; all awards and contracts carry status `active`; many
  releases share one release date; some releases have incoherent dates (for example an award dated
  after a related contract's signature); and amounts contain extreme outliers.

**Diavgis publication policy, text supplied by the owner on 2026-11-20.** The page answers
automated clients with a bot challenge (HTTP 403, "Just a moment..."), so it was not fetched here and
no workaround was attempted; the owner copied its text from a browser. There is no original file or
hash for it. What it says (Greek, with a gloss):

- Format OCDS 1.1 release packages, OCID prefix `ocds-r3r7e7`, Greece from 2026-03-01, with the
  pagination extension. It publishes procurement processes from "τα επίσημα ανοικτά δεδομένα της
  Διαύγειας, του ΚΗΜΔΗΣ και του EU TED" (the official open data of Diavgeia, KIMDIS and EU TED).
- **"Οι εγγραφές της ίδιας προμήθειας μοιράζονται ένα ocid"**: records of the same procurement
  share one `ocid`. This is the link, but the page **does not name the keys or fields used to
  decide that records belong together**. It refers to a "Μεθοδολογία" (methodology) page, not yet
  seen.
- Access is free without a key or account, with a request limit per IP address. New records daily;
  when a source corrects or completes records after publication, "οι αλλαγές δημοσιεύονται ως νέες
  εγγραφές" (the changes are published as new releases).
- Personal data: "Δεν δημοσιεύεται ποτέ ΑΦΜ φυσικού προσώπου. Φυσικό πρόσωπο που είναι ανάδοχος
  εμφανίζεται με όνομα και ψευδώνυμο αναγνωριστικό· τα υπόλοιπα προσωπικά δεδομένα παραλείπονται"
  (a natural person's tax number is never published; a natural person who is a contractor appears
  with a name and a pseudonymous identifier; other personal data is omitted). This is a useful
  precedent for our own personal-data policy.
- "Τα δεδομένα αποδίδουν τις πηγές όπως δημοσιεύονται": the data reproduces sources as published,
  so source errors in amounts or dates can appear here too. Licence CC BY 4.0, credit "Diavgis,
  https://diavgis.gr".

**Diavgis methodology page, text supplied by the owner on 2026-11-20** (same caveats: not fetched
here, no original file or hash). What it says:

- The headline figure reads "0% αλυσίδες με ρητή απόδειξη" (0% of chains with explicit proof), and
  the text: "Σήμερα 0% των αλυσίδων στηρίζονται σε επιβεβαιωμένη αντιστοίχιση, όχι σε εκτίμηση"
  (today 0% of chains rest on a confirmed match, not on an estimate). The stages of one procurement
  are published "σε διαφορετικά μητρώα και χωρίς κοινό αναγνωριστικό" (in different registers and
  without a common identifier). Each link carries a degree of certainty shown on the chain page.
  **The text supplied does not describe how the estimate is made.**
- What it does **not** join: administrative umbrellas such as an annual "Έγκριση Δαπάνης"
  (expenditure approval) that thousands of acts of one body can cite. "μια αναφορά που τη μοιράζονται
  πολλές πράξεις δεν δημιουργεί αλυσίδα" (a reference shared by many acts does not create a chain);
  it stays visible as a directly linked act.
- Spend is counted once per chain, and tender budgets are estimates, not spend. Amounts pass an
  automatic plausibility check because sources contain typing errors (a figure a thousand times too
  large); extreme ones are checked on the original document.
- Indicators are neutral published facts (single-bidder awards, awards just under the Law 4412
  thresholds, repeated identical amounts, direct awards, cancellations), with a minimum volume. The
  near-threshold ones use KIMDIS only, "γιατί μόνο εκεί δημοσιεύεται το καθαρό ποσό χωριστά από το
  ποσό με ΦΠΑ" (because only there is the net amount published separately from the amount with VAT).
- Stated limits: natural persons appear only as contractors and their tax number is never
  published. Diavgeia names a contractor in 62% of assignments and KIMDIS in 99%; "Το κενό είναι της
  δημοσίευσης, όχι της ανάλυσης" (the gap is in publication, not in analysis): the field is empty at
  source. These figures are the project's own and were not checked. The page also shows a count of
  acts withheld for GDPR that appears as 0 in the pasted text; it is not relied on.

**Diavgis "API & MCP" page, text supplied by the owner on 2026-11-20** (same caveats: not fetched
here, no original file or hash; it is the project's own product page, so its claims are the
project's). What it says:

- The same data is offered four ways: a REST API at `api.diavgis.gr/v1` (free account and key, with
  plans and limits), an MCP server for AI agents (`mcp.diavgis.gr`), a keyless OCDS 1.1 feed at
  `api.diavgis.gr/ocds`, and Parquet files on Hugging Face (acts, suppliers, CPV codes, entities and
  **chains**), all CC BY 4.0 from 2026-03-01.
- Its sample record keys an act by an identifier shaped like an ADA (not verified as one) and carries
  `kind`, buyer and supplier tax numbers and names, net amount, primary CPV, NUTS region, issue
  date, `source` (here `diavgeia`) and a `source_url` back to the original. A separate call returns
  an act's "parties, CPVs and its whole chain".
- The page invites AI agents to use its key, its MCP server and its `llms.txt`. None of that is
  used here: it is third-party content, and connecting an agent to an outside service or creating an
  account is the owner's decision, not part of this research.

**A cross-check option, not yet taken.** Diavgis's published chains could be compared with the links
our own records make, on a small sample, to see where the two agree. That would need the owner's
approval of the attribution wording and of a network host for the keyless feed or the dataset, and
the comparison would use it as an oracle with known errors, never as a source of truth.

**What this means.** Someone has already built a three-source linked dataset, so the idea is
feasible and Diavgis is a possible cross-check. But by its own account **its links are estimates,
none confirmed by explicit proof, because the registers share no common identifier**. Our KIMDIS
parser reads an explicit `diavgeiaADA` field. Either that field is rarely filled or unreliable
(which would explain why Diavgis does not treat it as proof), or Diavgis does not use it. This is
the most important thing to measure before building anything (next section). Three further lessons:
a reference shared by many records is not a link between stages of one procurement; a contractor's
tax number is missing in a large share of Diavgeia assignments, so joins on it will miss many; and
Diavgis's non-unique party identifiers and its "all active" status support our rules that a tax
number is a grouping key and not an identity, and that we track revocation ourselves (see the
version log above). It is a derived product with its own errors: it should be compared with, never
used as a source of truth.

**Others, read 2026-11-20 (not linking projects):**

- arXiv 2512.05647, <https://arxiv.org/abs/2512.05647> (SHA-256
  `6530296f3559b4ab309e63005fd8ff6bfd05de9f555fdfdb964e49923d77a73a`): a corpus of one million
  Diavgeia decisions with text extracted from PDFs and an extraction pipeline. The abstract mentions
  no KIMDIS link. Whether it names a code repository is unverified (none was found in the page).
- iMEdD Lab, "The slow death of open data in Greece", <https://lab.imedd.org/en/the-slow-death-of-open-data-in-greece/>
  (SHA-256 `c744b9db76a6483230ee62469209dd7b11695461ac87dfee452d7da0598bf5c9`): policy commentary
  on open data. It quotes a ministry statement that KIMDIS then had no API; that is older context
  and says nothing about linking.

**Still unread leads (found by search, pages not opened):** the Open Contracting entry's linked
tutorials; "Public spending as LOD: the case of Greece" (<https://semantic-web-journal.net/node/464>);
the joint decision ΚΥΑ 4968/22-01-2026 adding article 6α "Ανοικτά δεδομένα ΚΗΜΔΗΣ", and a later
amendment 87338/14-10-2026 (ΦΕΚ Β΄ 6275/16-10-2026), which bear on KIMDIS reuse terms (this project
records CC BY 4.0) and need the primary gazette text; the Vouliwatch and Solomon "Consultocracy"
report on KIMDIS 2017-2025.

## Not verified (explicitly)

1. How production API access or a registered user is obtained, and any key or registration terms.
2. Runtime rate limiting, and the real behaviour of paging while data changes.
3. The canonical production prefix for document URLs (`/opendata` versus `/luminapi/api`).
4. The detailed licence page and whether any clause limits automated or bulk access.
5. Whether revoked decisions keep their documents available.
6. Whether any decision type links explicitly to a KIMDIS identifier, in metadata or in PDF text.
7. Real response shapes: this dossier read documentation and sample JSON, not live responses.
8. How Diavgis estimates its links: its policy and methodology texts (both supplied by the owner) say that records of one procurement share an `ocid` and that 0% of links are confirmed by explicit proof, but they do not describe the matching method. Its 62% and 99% contractor-named figures were not checked. The leads listed as unread remain unread.
9. What KIMDIS officially says `diavgeiaADA` refers to, how often it is filled and whether its ADAs are shared by many records (the counts in "Measure first" answer the last two).

## Decisions (owner)

Recorded on 2026-11-20 on the owner's explicit instruction, "record decisions 2, 3, 4 and 5 as
decided", after the owner was shown the five lines below.

1. **Accept Diavgeia as the second source for a bounded pilot.** Decided: yes, 2026-11-20.
2. **Reuse and attribution.** Decided, 2026-11-20. Accept CC BY 4.0 plus Law 3448/2006. Wherever
   Diavgeia-derived data is shown or exported, the source statement is: "Source: Diavgeia
   (diavgeia.gov.gr), CC BY 4.0; data retrieved on `<date>`".
3. **Personal data.** Decided, 2026-11-20. Originals stay in the private archive only; test
   fixtures are synthetic; supplier tax numbers are projected only for legal entities until a
   written policy covers individuals. This matches the practice Diavgis states: no natural-person
   tax numbers, individual contractors by name with a pseudonymous identifier. It is a working rule,
   not legal advice.
4. **First step.** Decided, 2026-11-20: measure first. Run the census above on the pilot database.
   Only if a healthy share of records cite distinct ADAs, take the ADAs one small KIMDIS cohort
   cites and fetch exactly those decisions one by one with `GET /decisions/:ada` (and their
   `versionlog`). If the field is sparse or its ADAs are shared by many records, the choice is
   revisited before anything is fetched, and Δ.2.2 by organisation and window remains the fallback.
   Diavgis's published chains are at most a later cross-check; its results are not trusted in place
   of our own measurement.
5. **Network and rate.** Decided, 2026-11-20. The engine's existing default request rate, with
   `diavgeia.gov.gr` added to the source worker's egress allowlist only for the pilot and only in
   the change that introduces the adapter.

**What recording these decisions does not do.** It changes no code, environment or allowlist, and it
permits no Diavgeia request. Nothing is fetched before the census has been run and reviewed and the
adapter change, including its egress entry, has been reviewed and merged.

Next steps: the owner runs the census; then a spec for the Diavgeia adapter (identity, versions,
status handling), recorded synthetic samples for the conformance suite, and only then the approved
bounded real run.
