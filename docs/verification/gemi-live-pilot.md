# GEMI access and pilot runbook

Status, 2026-11-10: PR #18 is merged (`2fc4f40`). No credentialed live pilot has
run. The user reports submitting the personal-key application; the environment
has no NIMA_GEMI_API_KEY binding and pilot registry IDs have not been selected.

## Access while approval is pending

The [official registration page](https://opendata.businessportal.gr/register/)
embeds a form saying high request volume means applicants should allow **a few
days**, with the reply sent to the submitted email. This is an estimate, not a
guaranteed SLA; no expedited personal-key procedure was found.

For limited developer exploration, [official technical instructions](https://opendata.businessportal.gr/techdocs/)
publish `api-docs-key` for the [Swagger interface](https://opendata-api.businessportal.gr/opendata/docs/).
Open **Authorize**, enter that published test key, then try one explicitly selected
`GET /companies/{arGemi}` lookup. Calls are limited per IP; no numeric quota or
current validity of this key has been verified here. Testing does not replace
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
