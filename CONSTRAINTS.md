# Engineering constraints

Established 2026-11-08 for the repository bootstrap. Application quality criteria
will be added with each approved feature spec; bootstrap checks do not prove an
ingestion pipeline exists.

## Floor

No committed secrets, skipped tests, unexplained suppressions, silent failures,
or implemented-looking stubs. Do not lower thresholds or remove checks to pass a
feature. Changes to constraints, CI, or security exclusions need an explicit
explanation and review. Qualitative items are review requirements; automated
checks below enforce only the properties each tool actually checks.

## Automated checks

| Property | Rule and reason | Command | Runs |
|---|---|---|---|
| Skill integrity | Zero differences from the pinned snapshot, including shared references | `just skills-check` | Local and CI |
| Formatting and lint | Zero findings; one consistent style | `just lint` | Local and CI |
| Types | Zero strict mypy errors in first-party Python | `just typecheck` | Local and CI |
| First-party tests | At least 90% line/branch combined coverage across tooling and `nima`; data integrity and failure paths matter | `just test` | Local and CI |
| Package | Wheel and source distribution build successfully | `just build` | Local and CI |
| Code security | Zero Bandit findings in first-party code | `just security` | Local and CI |
| Secret detection | Zero Gitleaks findings; output is redacted | `just secrets` | Local and CI |
| Dependency advisories | Zero known advisories for locked third-party dependencies applicable to the current environment; audit failures fail the check | `just audit` | Task end and CI |

The hash lockfile detects local drift, not a compromised upstream or a coordinated
change to both files and hashes. Skill updates require human review. Dependencies
are locked in `uv.lock`; action references and the secret-scanner archive are
pinned. First-party tools do not execute scripts from the skill bundle.

## Remote controls

Repository visibility: public, explicitly confirmed by the owner on 2026-11-14.
This supersedes the original private-hosting requirement; it changes no data,
secret-handling or quality requirement. Original source evidence and databases
remain outside Git.

Intended GitHub controls remain PR-only changes to main/dev, one independent
approval, required checks, resolved conversations and blocked force pushes/deletions.
Read-only verification on 2026-11-14 found active ruleset `protect-main` (26812073)
with an empty branch include list and only deletion/non-fast-forward rules.
The effective-rules endpoints for main and dev both returned empty lists. Do not
claim either branch is protected. The proposed full policy remains in
.github/rulesets/main-dev.json. Earlier settings writes returned integration HTTP
403; no administration or billing changes are part of this documentation update.
A workflow file or an active ruleset matching no branches does not enforce protection.

## Measurements

Initial bootstrap-tool coverage: 96.43% combined line/branch coverage.
No production runtime performance, full-source coverage, document extraction accuracy, or model-quality
baseline has been measured. Add such gates when the relevant capability exists.

## Exceptions

None. Third-party example code is preserved unchanged and is outside first-party
Python lint/type/coverage scope; the integrity and secret checks still inspect it.
