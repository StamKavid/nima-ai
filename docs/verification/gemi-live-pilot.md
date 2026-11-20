# GEMI access and pilot runbook

Update, 2026-11-20: first authenticated collector pilot, run on Linux (Docker, since the
archive code does not run on Windows). Registry number `1037501000` (OTE, chosen because it is the
number the earlier public-key attempt used and a large, well-known listed company). The key is kept
in the owner's untracked `.env` and is never recorded here.

| Item | Result |
|---|---|
| Smoke checks | `GET /health` HTTP 200; `GET /companies?name=COSMOTE&resultsSize=1` HTTP 200 |
| Run `fe6b918a98d14655937d5462808cce64` | complete; requested 1, found 1, not found 0, quarantined 0, attempts 1; exit 0 |
| Limits recorded | 8 requests/minute, 60 s request timeout, 300 s run budget, 3 attempts |
| Versions | connector `gemi-profile-v1`, normalizer `gemi-company-v1`; licence ODC-BY-1.0 |
| Body | HTTP 200, 95,040 bytes, complete; SHA-256 recorded in the private manifest |
| Archive check | `verify_run` passed: original bytes re-parsed, 1 response, 1 observation |
| Normalized record | 14 scalar fields, each with a JSON pointer, plus 166 activity rows |
| KAD coverage | 88 rows `kad_2026`, 78 rows `kad_2008`; 88 open-ended; 149 distinct codes |
| Personal data | `persons`, `capital`, `stocks` and `branch` are not kept in the normalized record |

Findings from this pilot, each fixed or recorded:

1. **Timeout.** The first run failed `retry_exhausted`: all three attempts hit the 20 s client
   timeout with a transport error. A direct request showed the server needed about 29 s to the
   first byte and 33 s in total for this profile. The default and ceiling are now 60 s.
2. **Registry number type.** The second run was quarantined at `/arGemi`: the live API sends
   `"arGemi": "1037501000"` as a string, although the published Swagger schema declares an
   integer. The parser now accepts an integer or a canonical decimal string (ASCII digits, no
   leading zero, equal to the requested number). The original quarantined body was kept as
   evidence and its stored SHA-256 matched the received bytes.
3. **Rate limit.** The provider allows 8 requests/minute; the client now defaults to and is
   capped at 8.
4. **Duplicate KAD rows.** Activities repeat per KAD revision with date ranges. Any KAD logic must
   key on code and version together.
5. **Not covered by this pilot.** One company only; no 404 or 429 live case; no import into
   PostgreSQL; no KIMDIS comparison. Profile-path compatibility is established for one large
   company, not for the registry.

Raw responses, manifest and normalized rows stay in the private archive outside Git
(`data/` is ignored). They include named individuals and must not be copied into issues or PRs.

Status, 2026-11-10: PR #18 is merged (`2fc4f40`). The personal-key collector pilot
is pending. The user submitted the application; no NIMA_GEMI_API_KEY is configured.
A separate direct HTTPS request equivalent to Swagger's profile operation used
the published test key and OTE's publicly documented registry number `1037501000`.
It returned HTTP 401, so no profile was accepted or parsed. The response and
retrieval metadata are retained privately outside Git. This was not a collector run.

## Access while approval is pending

The [official registration page](https://opendata.businessportal.gr/register/)
embeds a form saying high request volume means applicants should allow **a few
days**, with the reply sent to the submitted email. This is an estimate, not a
guaranteed SLA; no expedited personal-key procedure was found.

For limited developer exploration, [official technical instructions](https://opendata.businessportal.gr/techdocs/)
publish `api-docs-key` for the [Swagger interface](https://opendata-api.businessportal.gr/opendata/docs/).
Open **Authorize**, enter that published test key, then try one explicitly selected
`GET /companies/{arGemi}` lookup. Calls are limited per IP; no numeric quota is
verified. The test key was rejected from this environment as recorded above; that
does not establish whether it works from another IP. Testing does not replace
the personal-key application or establish personal-credential acceptance.

Use this test key in Swagger. The Nima collector requires a personal key and
explicitly rejects the published test key. No code or authentication rule changes
are needed for manual exploration. Stop on rejection/rate limiting; preserve that
outcome rather than claiming a successful profile test.

OpenData pages list **support@uhc.gr** for access/support. A follow-up can include
the application date, registration email, Nima's research purpose and small pilot
volume, asking about application status or temporary development access.
The [general technical contact page](https://www.businessportal.gr/en/contact/)
also lists **gemi@uhc.gr** with subject “GEMI: Technical Question”. No message has
been sent by this project, and neither contact guarantees faster issuance.

## Check a manual test export offline

Save a JSON response privately as `work/gemi-trial/profile.json`; keep the folder
0700 and file 0600. Work files are Git-ignored. Record its source URL, HTTP status,
retrieval time and test-key context separately, excluding authentication headers.
A Swagger export may be reformatted: do not label it a collector raw-body capture.

Set `NIMA_GEMI_PILOT_ID` to the registry number you selected, then run the following
from the repository root with `uv run --frozen python -`. This performs no HTTP
and prints no company names or tax IDs:

```python
import json
import os
from pathlib import Path

from nima.sources.gemi import MAX_BODY, InvalidProfile, normalize_profile

with Path("work/gemi-trial/profile.json").open("rb") as stream:
    raw = stream.read(MAX_BODY + 1)
try:
    profile = normalize_profile(raw, os.environ["NIMA_GEMI_PILOT_ID"])
except InvalidProfile as exc:
    print(json.dumps({"parser_accepted": False, "field": str(exc)}))
    raise SystemExit(1) from None
print(
    json.dumps(
        {
            "parser_accepted": True,
            "non_null_fields": sum(a.value is not None for a in profile.fields.values()),
            "activity_count": None if profile.activities is None else len(profile.activities),
            "auto_registered": profile.fields["auto_registered"].value,
        }
    )
)
```

Acceptance here only means the current normalizer accepted that export. It does
not validate the collector transport, every optional field, personal-key access,
historical company state or resolved identity. Report malformed fields by their
paths/types; keep original payloads private and never truncate them to pass a limit.

## Personal-key collector pilot

1. Add the issued personal key as NIMA_GEMI_API_KEY in environment settings. Choose
   1–3 explicit registry numbers and record why those profiles were selected.
2. Invoke the existing collector with a new pilot archive:

   ```bash
   uv run --frozen python -m nima ingest gemi \
     --gemi-id REGISTRY_NUMBER --archive-dir data/gemi-pilot
   ```

   Repeat `--gemi-id` for the selected profiles. Keep the existing request/retry,
   body, array and cooperative-time ceilings; do not add broad discovery filters.
3. Record the run ID, counters, outcome codes, schema/extraction versions and
   source/license. Exit 0 also permits 404 outcomes: require at least one accepted
   200 profile before claiming profile-path compatibility. A 404 proves neither
   company nonexistence nor successful authentication across all provider routes.
4. Inspect the private manifest, original bodies and assertions. Verify requested
   registry identity, body SHA-256, field pointers and observed types. Record
   missing/empty fields, partial registration and KAD version/date coverage.
   A schema mismatch stays quarantined until its contract/adapter is reviewed.
5. A repeat lookup is a fresh run. Check that earlier evidence stays unchanged;
   a changed new body hash can reflect source/format changes, not necessarily a
   legal or financial event. Reparse each verified body with its extraction version.

Record credential acceptance and the small observed payload sample separately
from source completeness/freshness, which this pilot cannot establish. Keep test
exports, collected evidence and personal credentials out of Git. SQL persistence,
accepted identity links, graph projection and automatic resume remain later gates.
