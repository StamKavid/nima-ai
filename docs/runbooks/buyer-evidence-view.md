# Private buyer-to-original evidence view

The [approved bounded view](../specs/SPEC-buyer-evidence-view.md) exports a single
offline HTML file: saved buyer/cohort → supplier group → contributing publication
→ selected observation → exact original page. It needs no server or browser
credential. Opening it performs no fresh database, archive or source verification.

## Export

Use existing U3 requests and content-named reports. Set `NIMA_DATABASE_URL` to
the restricted analytics reader through the environment. Create a private config
(directory 0700, file 0600), replacing the example paths and `READOUT_SHA256`:

```json
{
  "version": "nima-buyer-evidence-view-request-v1",
  "entries": [
    {
      "label": "Selected buyer / captured window",
      "request_path": "/PRIVATE/buyer-request.json",
      "report_path": "/PRIVATE/READOUT_SHA256.json"
    }
  ]
}
```

```sh
uv run --frozen python -m nima analytics buyer-evidence-view \
  --config /PRIVATE/buyer-view.json --output-dir /PRIVATE/views
```

Stdout reports `artifact_sha256` and ordered `entry_states`. The output is
`<artifact_sha256>.html`, mode 0600 in a 0700 directory with a private `.gitignore`.
Identical inputs produce identical bytes; retry preserves the file and mtime.
Every export freshly verifies through the existing provider; missing originals
cannot reuse an earlier pass. Either entry failing prevents a new partial view.

Exit 0 means the view was generated, including draft/limited entries; 2 means
invalid input, 1 a fixed operational failure, and 130 interruption. Terminal
failures disclose no source values, paths, credentials or driver details.

## Interpretation and evidence

- **Descriptive readout:** provider-order groups, all ties, exact fractions and
  unresolved/partial publications. Joint eligible-group counts overlap. The
  denominator counts publications with an eligible reported Greek identifier.
  It establishes no money, market share, legal identity or lifecycle count.
- **Data fitness:** independent `ready`/`limited`/other assessment state. Ready
  data does not certify a draft metric. All insight refusal reasons remain visible.
- **Insight decision:** current draft definitions yield `review_required` or
  `insufficient_evidence`, with a null answer. Certified positive composition is
  tested only with a clearly fictional compatible profile; real admission is open.
- **Evidence trail:** only provider-selected observations become contributing
  witnesses. Run/page/version/hash and JSON pointer are inspectable. Exact parent,
  assessment and insight files retain the other observations and policy metadata.
- **Original page:** bytes are embedded once per digest and downloaded unchanged.
  Text display uses UTF-8 decoding; browser JSON number parsing never touches
  original identifiers or money. Keep the HTML private: it contains original responses.

Entries retain independent snapshots; their numbers are not added and no shared
transaction or comparable time series is claimed. Source freshness stays what
the parent reports. [Source meanings and analytical choices](../semantics/u3-source-mapping.md)
remain distinct; the view does not promote the metric.

## Bounds and implementation

Closed configuration is at most 16 KiB, with 1–2 distinct labels/selections and
absolute safe request/report paths. Unknown/duplicate fields and duplicate
subjects are refused. Aggregate source-page observations are capped at 500 and
verified pages at 32, counting each entry budget even if shared. Unique raw bytes
are at most 8 MiB; final HTML at most 16 MiB. Per-entry admission limits also
apply. The export refuses overflow instead of truncating evidence or supplier rows.

Preparation calls the public insight provider once per entry, retaining its two
existing read-only SQL connections. No query, metric or revision calculation is
added. Original embedding repeats public descriptor-based recovery after the
fresh provider. Publication reuses the existing no-clobber writer. No dependency,
migration, service, profile, source request or schedule is added.

Fixed packaged assets use CSP hashes. Source text is escaped or assigned through
text nodes; downloads use base64 bytes and metadata escapes script terminators.
CSP blocks document network requests, objects and frames. JavaScript navigates
prepared content and downloads bytes; it performs no metric arithmetic or joins.

## Verification and remaining acceptance

Focused tests cover restricted SQL, exact bytes, entry states, bindings, retry,
relocation, disappearing evidence, old/future observations, actual 500/501
admission and publication failures. The three new Python modules reach 100%
line/branch coverage. Actual mutation, installed-wheel, retained-source, full-gate
and hosted results are recorded in the delivery PR.

The explicit browser checker uses existing Playwright and sandboxed Chromium;
it is not a skipped pytest test. With the prepared fictional fixture manifest:

```sh
unshare --user --map-current-user --net -- \
  uv run --frozen python tests/buyer_view_browser.py \
  /PRIVATE/browser-fixtures.private.json /PRIVATE/browser-proof
```

It checks keyboard/mobile use, exact downloads, large identifiers, empty/limited/
hostile states, CSP tamper refusal and no external page requests. The managed
cloud browser blocks direct `file://` navigation, so interaction proof loads the
exact export through `set_content`. Local file opening remains an operator-browser
check. Automation is not human reconciliation, certification or an observed
analyst task; use the existing [task protocol](../product/buyer-evidence-task-protocol.md).

Browser references checked: [CSP hashes](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/script-src#unsafe_inline_script),
[binary Blob downloads](https://developer.mozilla.org/en-US/docs/Web/API/Blob#creating_a_url_representing_the_contents_of_a_typed_array)
and the installed Playwright binding/runtime namespace/seccomp sandbox report.
