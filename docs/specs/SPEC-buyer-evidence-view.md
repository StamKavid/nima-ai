# Spec: one buyer-to-original-evidence view

Status: **approved for implementation, 2026-11-28**, by the owner's “go with
implementation” instruction following #244. V1–V3 below are the implementation
scope; this does not approve metric promotion or human reconciliation. Module: `market-analytics`,
bounded V1-10/V1-11 slice of the approved capability map. Depends on delivered U3
readout, acceptance and insight interfaces. This specifies one local research
flow; general serving, company search, other views and R7 completion remain open.

## Objective and assumptions

A researcher selects an operator-approved saved buyer/cohort, inspects supplier
participation and its trust limits, then opens a contributing record's original
evidence. First delivery is a **private offline HTML export**: no new server,
login, source request, SQL query engine or frontend framework. The existing typed
Python preparation/export APIs supply the data. This is a proposed product choice;
the owner was offered a local-web-application alternative.

The view can make current draft readouts inspectable while human review is
pending. It does not certify a metric. An approved insight headline still requires
the existing certified-definition/compatible-policy/ready-data gate. Historical
definition compatibility and metric promotion are separately reviewed work.

## Flow and states

1. Select one of at most two configured saved buyer/cohort entries. Display its
   explicit captured scope, source, cutoff and reported-identifier meaning.
2. Inspect the existing U3 readout: supplier rows in provider order, all tied
   groups, exact numerator/denominator, unresolved and joint-record context.
3. Select a contributing publication and follow its selected observation, source
   version, raw-body hash, page and JSON pointer.
4. Display/download the embedded exact original response bytes, with the selected
   record's reference/pointer visible. Also retain the exact parent report and
   assessment as local downloadable data. No remote link is opened automatically.

Display data fitness, metric review state and evidence-verification scope
separately. Draft numeric tables must say **draft descriptive readout**. When
`answer` is null, the insight area preserves `review_required` or
`insufficient_evidence` and every reason; it contains no approved ranking/headline.
Limited cohorts keep diagnostic values and unknowns visibly scoped. Empty means
no captured records for this selection, never no real-world activity. An answered
fixture must retain every tied group and its witnesses; certified real admission
is unproven until the separate human/profile gates actually pass.

The file states: evidence was verified when exported; opening/reloading it performs
no fresh SQL, archive or source verification. Source freshness remains whatever
the parent reports. Entries keep independent snapshots; the view claims no shared
transaction or comparable time series and does not aggregate their numbers.

## Backend and artifact contract

Proposed `prepare_buyer_evidence_view(dsn, entries)` and file export wrapper use
the public insight preparation once per entry, retaining its existing two
read-only connections per entry. Safely read the parent bytes and require their
hash to equal the fresh prepared subject. Do not import private consumer helpers,
re-evaluate metrics, select revisions or create an alternative acceptance policy.

For original-page embedding, reuse the public safe descriptor-based file readers,
explicit request archive bindings and fresh verified-page references. Read only
expected content-addressed bodies, require the expected SHA-256 and fail if any
disappears/changes. Use existing private directory/publication primitives for a
generated `<sha256>.html` filename and `.gitignore`; no new no-clobber filesystem
implementation or user-controlled output filename.

The HTML embeds its view-definition/asset versions, exact parent/assessment bytes,
entry request/cohort/metric/policy hashes and original page bytes. Use stable
serialization and static template assets; same inputs give identical bytes and
retry preserves mtime. A failure in either entry publishes no new partial view.

Bounds: configuration at most 16 KiB; 1–2 distinct entries; inherit each existing
request/readout limit, plus aggregate at most 500 admitted observations and 32
verified pages (sum entry budgets even if shared). Total unique raw page bytes
at most 8 MiB; final HTML at most 16 MiB including embedded data. Fail rather than
truncate suppliers, ties, evidence or limits. These are export limits, not a claim
of national coverage or measured performance.

## Proposed command and configuration

This command **does not exist yet**. `NIMA_DATABASE_URL` supplies the existing
restricted reader; no credential argument or stored browser credential:

```sh
uv run --frozen python -m nima analytics buyer-evidence-view \
  --config /PRIVATE/buyer-view.json --output-dir /PRIVATE/views
```

Closed configuration: `version: nima-buyer-evidence-view-request-v1` and `entries`,
each with a short display `label`, absolute `request_path` and content-named
`report_path`. Reject unknown/duplicate fields, duplicate entries, unsafe paths,
unsupported versions and malformed types. Labels are untrusted display text.
Source values/paths/credentials stay out of terminal failures. Proposed exits:
0 view generated (entry states reported separately), 2 input error, 1 operational
failure, 130 interruption. No force, certification override or source-fetch flag.

## Structure, implementation style and browser boundary

Use a small `src/nima/analytics/buyer_view.py` preparation/export module, packaged
static HTML/JS/CSS assets and a thin addition to the existing analytics CLI.
Focused unit/native/browser tests stay under `tests/`; usage belongs in a linked
runbook. No runtime dependency, schema migration, new service or generic UI engine.

```python
@dataclass(frozen=True)
class BuyerViewExport:
    artifact_sha256: str
    entry_states: tuple[Status, ...]
```

Use Python 3.12+, strict typing, Ruff and existing byte/hash helpers. Browser code
only navigates/presents prepared data; it performs no metric arithmetic or joins.
Preserve Greek UTF-8. Display long identifiers as exact text, never JS `Number`.
Original response bytes are downloaded/displayed verbatim; do not parse and
re-serialize monetary numbers through browser floating point. Evidence pointers
remain the provider's pointers, not inferred source locations.

Use text nodes/escaped templates for untrusted content; no `innerHTML`, `eval`,
remote asset, tracking, auto-opened URL or arbitrary path input. Embed JSON/bytes
without script-terminator injection. Content Security Policy blocks network,
objects and child frames and admits only the packaged script; no inline event handlers.
Keyboard labels/focus, readable Greek, explicit status text and mobile layout
must work without relying on color alone. The output is private 0700/0600 data.

## Testing and success criteria

- Known answers use the existing hand-labelled tie/joint/unresolved fixtures.
  Draft-ready and limited real cohorts remain correctly labelled with no approved
  insight; sparse/old/after-cutoff observations never become selected witnesses.
- Real restricted-role PostgreSQL 17 tests prove one fresh consumer/two existing
  connections per entry, no HTTP or DB writes, old report/assessment invariance,
  exact retry/relocation and no new output after evidence disappears or any limit
  fails. CLI/library output bytes agree; no partial multi-entry artifact.
- Browser tests exercise cohort → supplier → record → exact original-byte
  display/download, empty/limited/review-required states, keyboard/mobile use,
  hostile Greek/source strings, script terminators, large identifiers and zero
  external requests. Compare bytes/hashes, not screenshots alone. Reuse pinned
  browser infrastructure; needed verification recipes are reviewed with the plan,
  preserving all existing gates and Chromium sandboxing.
- Require 100% new Python-module line/branch coverage and meaningful gate/witness/output
  mutations, the existing ≥90% overall floor, installed-wheel/native proof,
  `just check`, `just audit` and exact-head hosted reports. Relevant existing
  commands are `just lint`, `just typecheck`, `just test`, `just build`,
  `just security`; future focused pytest targets are selected in the reviewed plan.

Success: a target user can navigate one selected captured buyer to its supporting
original and explain its limits through this single artifact. Record actual
usefulness separately with the [task protocol](../product/buyer-evidence-task-protocol.md).
Do not claim user success from an automated browser run.

## Boundaries and review decisions

- **Always:** reuse verified providers, retain exact evidence/unknowns and scope,
  fail closed on bindings/limits, preserve historical bytes and private data.
- **Review before scope changes:** dependencies, CI recipes, schema, hosting,
  live sources, profile promotion, broader queries or additional views.
- **Never:** publish raw evidence, activate captures/schedules, contact users,
  certify by implication, run generated SQL or calculate another metric in JS.

Owner decisions: **V1** private offline export as the first view; **V2** two saved
entries/global limits and explicit draft/insight separation; **V3** embedded exact
evidence with private publication, fixed network-free browser behavior and the
verification requirements above. Recommendations are the choices written here.
Implementation planning/code wait for this spec's review. Human U3 reconciliation
and definition/policy compatibility remain separate real inputs, not assumed.
