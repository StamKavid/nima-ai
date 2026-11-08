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
| Skill integrity | Zero differences from the pinned snapshot, including shared references | `make skills-check` | Local and CI |
| Formatting and lint | Zero findings; one consistent style | `make lint` | Local and CI |
| Types | Zero strict mypy errors in first-party Python | `make typecheck` | Local and CI |
| Bootstrap tooling tests | At least 90% line/branch combined coverage; the integrity gate's failure paths matter | `make test` | Local and CI |
| Package | Wheel and source distribution build successfully | `make build` | Local and CI |
| Code security | Zero Bandit findings in first-party code | `make security` | Local and CI |
| Secret detection | Zero Gitleaks findings; output is redacted | `make secrets` | Local and CI |
| Dependency advisories | Zero known advisories for locked third-party dependencies applicable to the current environment; audit failures fail the check | `make audit` | Task end and CI |

The hash lockfile detects local drift, not a compromised upstream or a coordinated
change to both files and hashes. Skill updates require human review. Dependencies
are locked in `uv.lock`; action references and the secret-scanner archive are
pinned. First-party tools do not execute scripts from the skill bundle.

## Remote controls

Intended GitHub controls: private visibility, PR-only changes to main, one
approval, required `quality` check, resolved conversations, and blocked force
pushes/deletions. These controls are pending remote authentication and host-plan
support. A workflow file alone does not enforce branch protection.

## Measurements

Initial bootstrap-tool coverage: 96.43% combined line/branch coverage.
No runtime performance, data coverage, extraction accuracy, or model-quality
baseline has been measured. Add such gates when the relevant capability exists.

## Exceptions

None. Third-party example code is preserved unchanged and is outside first-party
Python lint/type/coverage scope; the integrity and secret checks still inspect it.
